"""Validated Markdown → HTML → Chromium PDF reporting for Midas research runs."""

from __future__ import annotations

import base64
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import markdown as md
from bs4 import BeautifulSoup
from langchain_core.tools import tool

from .prompts import REQUIRED_RESEARCH_ARTIFACTS

_OUTPUT_ROOT = Path("output/research")
_DEFAULT_BROWSER_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
REPORT_MARKDOWN = "10_final_report.md"
REPORT_HTML = "10_final_report.html"
REPORT_PDF = "final_report.pdf"

_REQUIRED_HEADINGS = (
    "A. Investment decision summary",
    "B. Candidate funnel",
    "C. Full finalist comparison",
    "D. Final selections",
    "E. Rejected finalists",
    "F. Final conclusion",
)
_MARKDOWN_IMAGE = re.compile(
    r"!\[([^\]]*)\]\(\s*(?:<([^>]+)>|\"([^\"]+)\"|'([^']+)'|([^)\s]+))\s*\)"
)
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?")
_NUMERIC_CELL = re.compile(
    r"^\s*(?:[₹$€£]?\s*)?(?:[~<>≤≥+\-–—]?\s*)?\d[\d,.]*(?:\s*[%xX])?"
)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _research_root() -> Path:
    return (Path.cwd() / _OUTPUT_ROOT).resolve()


def _resolve_run_directory(run_directory: str) -> Path:
    value = run_directory.strip()
    if not value:
        raise ValueError("run_directory must not be empty")
    candidate = Path(value)
    if candidate.is_absolute() and candidate.parts[:2] == ("/", "output"):
        candidate = Path.cwd() / candidate.relative_to("/")
    elif not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    resolved = candidate.resolve()
    root = _research_root()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"run_directory must be inside {root}") from None
    if not resolved.is_dir():
        raise ValueError(f"run_directory does not exist: {resolved}")
    return resolved


def _validate_artifacts(run_directory: Path) -> list[tuple[str, str]]:
    artifacts: list[tuple[str, str]] = []
    errors: list[str] = []
    for name in REQUIRED_RESEARCH_ARTIFACTS:
        path = run_directory / name
        if not path.is_file():
            errors.append(f"missing {name}")
            continue
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            errors.append(f"empty {name}")
            continue
        artifacts.append((name, content))
    if errors:
        raise ValueError("Research artifact validation failed: " + "; ".join(errors))
    return artifacts


def _read_report(run_directory: Path) -> str:
    path = run_directory / REPORT_MARKDOWN
    if not path.is_file():
        raise ValueError(
            f"missing {REPORT_MARKDOWN}; the report agent must synthesize it from "
            "the research Markdown files before rendering"
        )
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"empty {REPORT_MARKDOWN}")
    return content


def _split_markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _lint_report(markdown: str) -> list[str]:
    """Reject structural errors that reliably produce incomplete or rough reports."""
    errors: list[str] = []
    headings = re.findall(r"^#\s+(.+?)\s*$", markdown, re.MULTILINE)
    if tuple(headings) != _REQUIRED_HEADINGS:
        errors.append(
            "top-level headings must appear exactly once and in this order: "
            + "; ".join(_REQUIRED_HEADINGS)
        )

    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if (
            "|" not in line
            or index + 1 >= len(lines)
            or not _TABLE_SEPARATOR.match(lines[index + 1])
        ):
            continue
        columns = len(_split_markdown_row(line))
        separator_columns = len(_split_markdown_row(lines[index + 1]))
        if columns != separator_columns:
            errors.append(f"table near line {index + 1} has a mismatched separator row")
        if columns > 6:
            errors.append(
                f"table near line {index + 1} has {columns} columns; maximum is 6"
            )
    if errors:
        raise ValueError("Final report validation failed: " + "; ".join(errors))
    return []


def _browser_path() -> str:
    configured = os.environ.get("REPORT_PDF_BROWSER")
    candidates = [
        configured,
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        _DEFAULT_BROWSER_PATH,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError(
        "Google Chrome or Chromium was not found. Set REPORT_PDF_BROWSER to "
        "a Chromium-based browser executable."
    )


def _image_source(match: re.Match[str]) -> str:
    return next((group.strip() for group in match.group(2, 3, 4, 5) if group), "")


def _embed_local_images(markdown: str, run_directory: Path) -> str:
    """Embed report-local images so PDF rendering has no filesystem dependency."""

    def replace(match: re.Match[str]) -> str:
        source = _image_source(match)
        if not source or source.startswith("data:"):
            return match.group(0)
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            return match.group(0)
        candidate = Path(parsed.path)
        if not candidate.is_absolute():
            candidate = run_directory / candidate
        resolved = candidate.resolve()
        allowed_roots = (run_directory.resolve(), (Path.cwd() / "output").resolve())
        if not any(resolved == root or root in resolved.parents for root in allowed_roots):
            return match.group(0)
        if not resolved.is_file():
            return match.group(0)
        mime, _ = mimetypes.guess_type(resolved.name)
        if not mime or not mime.startswith("image/"):
            return match.group(0)
        encoded = base64.b64encode(resolved.read_bytes()).decode("ascii")
        alt = match.group(1)
        return f"![{alt}](data:{mime};base64,{encoded})"

    return _MARKDOWN_IMAGE.sub(replace, markdown)


def _classify_tables(content: str) -> str:
    soup = BeautifulSoup(content, "html.parser")
    for table in soup.find_all("table"):
        headers = [cell.get_text(" ", strip=True).lower() for cell in table.find_all("th")]
        joined = " | ".join(headers)
        if "decision metric" in joined:
            kind = "summary-table"
        elif headers and headers[0] == "stage":
            kind = "funnel-table"
        elif "quality-control question" in joined:
            kind = "checklist-table"
        elif headers and headers[0] in {"id", "source id"}:
            kind = "source-table"
        elif "failure reason" in joined:
            kind = "rejection-table"
        elif "company" in headers and any("valuation" in header for header in headers):
            kind = "valuation-table"
        elif "company" in headers:
            kind = "scorecard-table"
        else:
            kind = "data-table"
        table["class"] = [kind]
        for row in table.find_all("tr"):
            for cell in row.find_all("td"):
                if _NUMERIC_CELL.match(cell.get_text(" ", strip=True)):
                    cell["class"] = [*(cell.get("class") or []), "numeric"]
        wrapper = soup.new_tag("div", attrs={"class": "table-wrap"})
        table.wrap(wrapper)
    for image in soup.find_all("img"):
        figure = soup.new_tag("figure")
        image.wrap(figure)
        alt = image.get("alt", "").strip()
        if alt:
            caption = soup.new_tag("figcaption")
            caption.string = alt
            figure.append(caption)
    return str(soup)


def _report_html(markdown: str, title: str, run_directory: Path) -> str:
    embedded = _embed_local_images(markdown, run_directory)
    # Escape raw HTML supplied by the model while preserving Markdown syntax.
    safe_markdown = html.escape(embedded, quote=False)
    content = md.markdown(
        safe_markdown,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        extension_configs={"toc": {"permalink": False}},
    )
    content = _classify_tables(content)
    safe_title = html.escape(title)
    generated = datetime.now(UTC).strftime("%d %B %Y")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<style>
@page {{ size: A4; margin: 16mm 15mm 18mm; }}
:root {{
  --ink: #182230; --muted: #52606d; --rule: #d7dde5; --paper: #fff;
  --navy: #173b67; --blue: #eaf1f8; --amber: #9a6700; --red: #a52727;
}}
* {{ box-sizing: border-box; }}
html {{
  background: var(--paper); color: var(--ink);
  font: 10.25pt/1.48 Arial, Helvetica, sans-serif;
}}
body {{ margin: 0 auto; max-width: 180mm; }}
.report-header {{
  border-bottom: 3px solid var(--navy); display: flex; justify-content: space-between;
  margin-bottom: 9mm; padding-bottom: 3mm;
}}
.brand {{ color: var(--navy); font-size: 16pt; font-weight: 800; letter-spacing: .08em; }}
.report-meta {{ color: var(--muted); font-size: 8pt; text-align: right; }}
article > h1:first-child {{
  color: var(--navy); font-size: 24pt; line-height: 1.12; margin: 0 0 7mm;
}}
h1 {{ break-before: page; color: var(--navy); font-size: 18pt; margin: 0 0 5mm; }}
article > h1:first-child {{ break-before: auto; }}
h2 {{ border-bottom: 1px solid var(--rule); break-after: avoid; color: var(--navy);
  font-size: 13pt; margin: 7mm 0 3mm; padding-bottom: 1.5mm; }}
h3 {{ break-after: avoid; color: var(--ink); font-size: 11pt; margin: 5mm 0 2mm; }}
p {{ margin: 0 0 3.2mm; orphans: 3; widows: 3; }}
ul, ol {{ margin: 2mm 0 4mm; padding-left: 6mm; }}
li {{ break-inside: avoid; margin-bottom: 1mm; }}
a {{ color: var(--navy); overflow-wrap: anywhere; text-decoration: none; }}
blockquote {{ border-left: 3px solid var(--navy); color: var(--muted); margin: 4mm 0;
  padding: 2mm 4mm; }}
.table-wrap {{ margin: 4mm 0 6mm; width: 100%; }}
table {{
  border-collapse: collapse; font-size: 8.4pt; line-height: 1.3;
  table-layout: fixed; width: 100%;
}}
thead {{ display: table-header-group; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
th {{ background: var(--navy); color: white; font-size: 7.6pt; letter-spacing: .025em;
  text-align: left; text-transform: uppercase; }}
th, td {{ border-bottom: 1px solid var(--rule); overflow-wrap: anywhere; padding: 2.1mm 2mm;
  vertical-align: top; }}
tbody tr:nth-child(even) {{ background: #f6f8fa; }}
td.numeric {{ font-variant-numeric: tabular-nums; text-align: right; }}
.summary-table th:nth-child(1) {{ width: 31%; }}
.summary-table th:nth-child(2) {{ width: 12%; text-align: right; }}
.summary-table th:nth-child(3) {{ width: 57%; }}
.funnel-table th:nth-child(1) {{ width: 27%; }}
.funnel-table th:nth-child(2) {{ width: 10%; text-align: right; }}
.funnel-table th:nth-child(3) {{ width: 63%; }}
.rejection-table th:nth-child(1) {{ width: 18%; }}
.rejection-table th:nth-child(2) {{ width: 42%; }}
.rejection-table th:nth-child(3) {{ width: 40%; }}
.checklist-table th:nth-child(1) {{ width: 7%; }}
.checklist-table th:nth-child(2) {{ width: 48%; }}
.checklist-table th:nth-child(3) {{ width: 45%; }}
.source-table {{ font-size: 7.2pt; }}
.source-table th, .source-table td {{ padding: 1.5mm 1.2mm; }}
figure {{ break-inside: avoid; margin: 5mm auto; text-align: center; }}
img {{ max-height: 110mm; max-width: 100%; object-fit: contain; }}
figcaption {{ color: var(--muted); font-size: 8pt; margin-top: 1.5mm; text-align: left; }}
code {{
  background: #eef1f4; font: .9em ui-monospace, SFMono-Regular, Menlo, monospace;
  padding: .1em .2em;
}}
pre {{
  background: #182230; color: white; overflow-wrap: anywhere;
  padding: 3mm; white-space: pre-wrap;
}}
.report-footer {{ color: var(--muted); font-size: 7.5pt; margin-top: 8mm; text-align: center; }}
@media print {{
  html, body {{ background: white; }}
  * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
</style>
</head>
<body>
<header class="report-header">
  <div class="brand">MIDAS</div>
  <div class="report-meta">Long-Horizon Equity Research<br>{html.escape(generated)}</div>
</header>
<article>{content}</article>
<footer class="report-footer">Research assessment · Not personalized investment advice</footer>
</body>
</html>"""


def _print_pdf(browser: str, html_path: Path, pdf_path: Path, profile: Path) -> None:
    command = [
        browser,
        "--headless=new",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-gpu",
        "--disable-javascript",
        "--no-default-browser-check",
        "--no-first-run",
        "--no-pdf-header-footer",
        f"--user-data-dir={profile}",
        f"--print-to-pdf={pdf_path}",
        html_path.as_uri(),
    ]
    try:
        process = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        # Some macOS Chrome builds finish printing but leave a background process
        # attached to the temporary profile. subprocess.run has killed it at this
        # point; accept the output only when the PDF is demonstrably complete.
        if _is_complete_pdf(pdf_path):
            return
        raise
    if process.returncode != 0 or not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        diagnostics = (process.stderr or process.stdout or "unknown error").strip()
        raise RuntimeError(
            f"Chromium PDF generation failed (exit {process.returncode}): {diagnostics[-2000:]}"
        )
    if not _is_complete_pdf(pdf_path):
        raise RuntimeError("Chromium PDF generation produced an incomplete PDF")


def _is_complete_pdf(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 100:
        return False
    with path.open("rb") as handle:
        header = handle.read(5)
        handle.seek(max(0, path.stat().st_size - 1024))
        trailer = handle.read()
    return header == b"%PDF-" and b"%%EOF" in trailer


@tool("generate_report")
def generate_report(run_directory: str, title: str | None = None) -> str:
    """Validate and render ``10_final_report.md`` as retained HTML and a Chromium PDF."""
    try:
        resolved_run = _resolve_run_directory(run_directory)
        research_artifacts = _validate_artifacts(resolved_run)
        markdown = _read_report(resolved_run)
        warnings = _lint_report(markdown)
        default_title = f"{resolved_run.parent.name.replace('-', ' ').title()} Research Report"
        report_title = (title or default_title).strip()
        if not report_title:
            raise ValueError("title must not be blank")
        browser = _browser_path()
        rendered_html = _report_html(markdown, report_title, resolved_run)

        with tempfile.TemporaryDirectory(prefix="midas-report-") as temp_dir:
            temp_path = Path(temp_dir)
            html_path = temp_path / REPORT_HTML
            pdf_path = temp_path / REPORT_PDF
            profile = temp_path / "chrome-profile"
            profile.mkdir()
            html_path.write_text(rendered_html, encoding="utf-8")
            _print_pdf(browser, html_path, pdf_path, profile)
            html_destination = resolved_run / REPORT_HTML
            pdf_destination = resolved_run / REPORT_PDF
            shutil.copy2(html_path, html_destination)
            shutil.copy2(pdf_path, pdf_destination)

        return _json(
            {
                "ok": True,
                "status": "compiled",
                "pdf_path": str(pdf_destination),
                "html_path": str(html_destination),
                "included_files": [REPORT_MARKDOWN],
                "validated_research_files": [name for name, _ in research_artifacts],
                "warnings": warnings,
            }
        )
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return _json({"ok": False, "status": "failed", "error": str(exc)})


REPORT_TOOLS = (generate_report,)
