"""Deterministic Markdown-to-PDF reporting for completed Midas research runs."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from langchain_core.tools import tool

from .prompts import REQUIRED_RESEARCH_ARTIFACTS

_OUTPUT_ROOT = Path("output/research")
_TECTONIC_BINARY = "/opt/homebrew/bin/tectonic"
_SOURCE_LEDGER_HEADING = re.compile(r"(?im)^##\s+Source ledger\s*$")
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _research_root() -> Path:
    return (Path.cwd() / _OUTPUT_ROOT).resolve()


def _resolve_run_directory(run_directory: str) -> Path:
    value = run_directory.strip()
    if not value:
        raise ValueError("run_directory must not be empty")

    # DeepAgent's virtual filesystem presents paths from the workspace root as
    # `/output/...`; convert that stable virtual path to the real project path.
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
        if not _SOURCE_LEDGER_HEADING.search(content):
            errors.append(f"{name} has no `## Source ledger` section")
            continue
        artifacts.append((name, content))
    if errors:
        raise ValueError("Research artifact validation failed: " + "; ".join(errors))
    return artifacts


def _latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def _inline_to_latex(text: str) -> str:
    placeholders: list[str] = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"@@MIDAS{len(placeholders) - 1}@@"

    def link(match: re.Match[str]) -> str:
        label = _latex_escape(match.group(1))
        url = match.group(2)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return _latex_escape(match.group(0))
        return stash(rf"\href{{\detokenize{{{url}}}}}{{{label}}}")

    text = _MARKDOWN_LINK.sub(link, text)
    text = _INLINE_CODE.sub(
        lambda match: stash(rf"\texttt{{{_latex_escape(match.group(1))}}}"),
        text,
    )
    text = _BOLD.sub(lambda match: stash(rf"\textbf{{{_latex_escape(match.group(1))}}}"), text)
    escaped = _latex_escape(text)
    for index, value in enumerate(placeholders):
        escaped = escaped.replace(f"@@MIDAS{index}@@", value)
    return escaped


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _table_to_latex(lines: list[str]) -> str:
    rows = [_split_table_row(line) for line in lines]
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    spec = "p{" + str(round(0.92 / width, 3)) + r"\linewidth}"
    body = [
        r"\begin{longtable}{" + (" ".join([spec] * width)) + "}",
        r"\toprule",
        " & ".join(_inline_to_latex(cell) for cell in normalized[0]) + r" \\",
        r"\midrule",
        r"\endhead",
    ]
    for row in normalized[1:]:
        body.append(" & ".join(_inline_to_latex(cell) for cell in row) + r" \\")
    body.extend([r"\bottomrule", r"\end{longtable}"])
    return "\n".join(body)


def _markdown_to_latex(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    in_code = False
    list_kind: str | None = None
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            output.append(_inline_to_latex(" ".join(part.strip() for part in paragraph)))
            output.append("")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            output.append(rf"\end{{{list_kind}}}")
            output.append("")
            list_kind = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            output.append(r"\end{Verbatim}" if in_code else r"\begin{Verbatim}[breaklines=true]")
            in_code = not in_code
            index += 1
            continue
        if in_code:
            output.append(line)
            index += 1
            continue
        if "|" in line and index + 1 < len(lines) and _is_table_separator(lines[index + 1]):
            flush_paragraph()
            close_list()
            table_lines = [line]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            output.append(_table_to_latex(table_lines))
            output.append("")
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            command = {1: "section", 2: "subsection", 3: "subsubsection"}.get(
                level, "paragraph"
            )
            output.append(rf"\{command}{{{_inline_to_latex(heading.group(2))}}}")
            output.append("")
            index += 1
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        numbered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if bullet or numbered:
            flush_paragraph()
            required_kind = "itemize" if bullet else "enumerate"
            if list_kind != required_kind:
                close_list()
                list_kind = required_kind
                output.append(rf"\begin{{{list_kind}}}")
            match = bullet or numbered
            assert match is not None
            output.append(r"\item " + _inline_to_latex(match.group(1)))
            index += 1
            continue
        if not stripped:
            flush_paragraph()
            close_list()
            index += 1
            continue
        if stripped == "---":
            flush_paragraph()
            close_list()
            output.append(r"\medskip\hrule\medskip")
            index += 1
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            close_list()
            output.append(
                r"\begin{quote}" + _inline_to_latex(stripped.lstrip("> ")) + r"\end{quote}"
            )
            index += 1
            continue

        close_list()
        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    close_list()
    if in_code:
        output.append(r"\end{Verbatim}")
    return "\n".join(output)


def _document_latex(artifacts: list[tuple[str, str]], title: str) -> str:
    sections = []
    for name, content in artifacts:
        friendly_name = name.removesuffix(".md").split("_", 1)[-1].replace("_", " ").title()
        sections.append(rf"\part{{{_latex_escape(friendly_name)}}}")
        sections.append(_markdown_to_latex(content))
    body = "\n\n".join(sections)
    return rf"""\documentclass[10pt,a4paper]{{article}}
\usepackage[margin=1.8cm]{{geometry}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern}}
\usepackage{{microtype}}
\usepackage{{booktabs}}
\usepackage{{longtable}}
\usepackage{{array}}
\usepackage{{fancyvrb}}
\usepackage[table]{{xcolor}}
\usepackage[hidelinks]{{hyperref}}
\usepackage{{parskip}}
\setlength{{\parindent}}{{0pt}}
\setcounter{{secnumdepth}}{{0}}
\hypersetup{{pdftitle={{{_latex_escape(title)}}}}}
\title{{\Huge\bfseries {_latex_escape(title)}\\[0.4em]\large Midas Equity Research}}
\author{{Research-priority analysis; not personalized investment advice}}
\date{{}}
\begin{{document}}
\maketitle
\begin{{abstract}}
This report consolidates the primary screen, an independent competing analysis,
adversarial critique, and the lead analyst's evidence-backed reconciliation.
Selections are candidates for deeper research, not buy or sell recommendations.
\end{{abstract}}
\tableofcontents
\clearpage
{body}
\end{{document}}
"""


@tool("generate_report")
def generate_report(run_directory: str, title: str | None = None) -> str:
    """Validate a completed Midas research run and compile its Markdown into a PDF.

    This is a publication-only tool: it reads the required 00–07 Markdown artifacts
    in numeric order, preserves their text and citations, renders a controlled LaTeX
    document with Tectonic, and publishes ``final_report.pdf`` in the run directory.

    Args:
        run_directory: Completed directory under ``output/research``.
        title: Optional report title. Defaults to a title derived from the topic slug.
    """
    try:
        resolved_run = _resolve_run_directory(run_directory)
        artifacts = _validate_artifacts(resolved_run)
        default_title = f"{resolved_run.parent.name.replace('-', ' ').title()} Research Report"
        report_title = (title or default_title).strip()
        if not report_title:
            raise ValueError("title must not be blank")

        tectonic = shutil.which("tectonic") or (
            _TECTONIC_BINARY if Path(_TECTONIC_BINARY).is_file() else None
        )
        if tectonic is None:
            raise RuntimeError("Tectonic is not installed or available on PATH")

        with tempfile.TemporaryDirectory(prefix="midas-report-") as temp_dir:
            temp_path = Path(temp_dir)
            tex_path = temp_path / "final_report.tex"
            tex_path.write_text(_document_latex(artifacts, report_title), encoding="utf-8")
            process = subprocess.run(
                [
                    tectonic,
                    "--keep-logs",
                    "--outdir",
                    str(temp_path),
                    str(tex_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            rendered_pdf = temp_path / "final_report.pdf"
            if process.returncode != 0 or not rendered_pdf.is_file():
                diagnostics = (process.stderr or process.stdout or "unknown error").strip()
                raise RuntimeError(f"Tectonic compilation failed: {diagnostics[-2000:]}")

            destination = resolved_run / "final_report.pdf"
            shutil.copy2(rendered_pdf, destination)

        return _json(
            {
                "ok": True,
                "status": "compiled",
                "pdf_path": str(destination),
                "included_files": [name for name, _ in artifacts],
                "warnings": [],
            }
        )
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return _json(
            {
                "ok": False,
                "status": "failed",
                "error": str(exc),
            }
        )


REPORT_TOOLS = (generate_report,)
