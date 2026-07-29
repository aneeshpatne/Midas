import json
import os
import subprocess
from pathlib import Path

import pytest

from midas.deepagents import reporting
from midas.deepagents.prompts import REQUIRED_RESEARCH_ARTIFACTS


def _make_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    run = tmp_path / "output" / "research" / "nifty-it" / "20260729T120000Z"
    run.mkdir(parents=True)
    for index, name in enumerate(REQUIRED_RESEARCH_ARTIFACTS):
        (run / name).write_text(
            (
                f"# Artifact {index}\n\n"
                f"Evidence with 12% growth & risk for **candidate_{index}** [S{index}].\n\n"
                "| Name | Score |\n"
                "| --- | ---: |\n"
                f"| Candidate {index} | {70 + index} |\n\n"
                "## Source ledger\n\n"
                f"- [S{index}] [NSE](https://www.nseindia.com), official, "
                "2026-07-29, accessed 2026-07-29.\n"
            ),
            encoding="utf-8",
        )
    (run / reporting.REPORT_MARKDOWN).write_text(
        "\n\n".join(
            f"# {heading}\n\nSynthesized decision narrative."
            for heading in reporting._REQUIRED_HEADINGS
        ),
        encoding="utf-8",
    )
    return run


def test_resolve_run_directory_accepts_virtual_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _make_run(tmp_path, monkeypatch)

    assert reporting._resolve_run_directory("/output/research/nifty-it/20260729T120000Z") == run


def test_resolve_run_directory_rejects_path_outside_research_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_run(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="must be inside"):
        reporting._resolve_run_directory(str(tmp_path))


def test_validate_artifacts_requires_files_but_not_specific_markdown_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _make_run(tmp_path, monkeypatch)
    (run / "02_primary_research.md").write_text("# No ledger", encoding="utf-8")

    artifacts = reporting._validate_artifacts(run)
    assert dict(artifacts)["02_primary_research.md"] == "# No ledger"

    (run / "03_primary_shortlist.md").unlink()
    with pytest.raises(ValueError) as error:
        reporting._validate_artifacts(run)

    message = str(error.value)
    assert "missing 03_primary_shortlist.md" in message


def test_report_lint_requires_exact_heading_order() -> None:
    with pytest.raises(ValueError, match="top-level headings"):
        reporting._lint_report("# A. Investment decision summary\n\n# C. Wrong")


def test_report_lint_rejects_tables_wider_than_six_columns() -> None:
    markdown = "\n\n".join(f"# {heading}\n\nText." for heading in reporting._REQUIRED_HEADINGS)
    markdown += (
        "\n\n| A | B | C | D | E | F | G |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 1 | 2 | 3 | 4 | 5 | 6 | 7 |\n"
    )
    with pytest.raises(ValueError, match="maximum is 6"):
        reporting._lint_report(markdown)


def test_html_renderer_assigns_table_layout_and_escapes_raw_html(
    tmp_path: Path,
) -> None:
    rendered = reporting._report_html(
        "# Report\n\n<script>alert(1)</script>\n\n"
        "| Stage | Count | Companies / disposition |\n"
        "|---|---:|---|\n| Screen | 10 | Complete |",
        "Midas Test",
        tmp_path,
    )
    assert 'class="funnel-table"' in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>alert(1)</script>" not in rendered


def test_generate_report_compiles_and_publishes_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _make_run(tmp_path, monkeypatch)
    monkeypatch.setattr(reporting, "_browser_path", lambda: "/fake/chrome")

    def fake_run(command, **kwargs):
        output = next(part for part in command if part.startswith("--print-to-pdf="))
        Path(output.split("=", 1)[1]).write_bytes(b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(reporting.subprocess, "run", fake_run)

    response = json.loads(
        reporting.generate_report.invoke(
            {
                "run_directory": "/output/research/nifty-it/20260729T120000Z",
                "title": "Nifty IT Research",
            }
        )
    )

    assert response["ok"] is True
    assert response["status"] == "compiled"
    assert response["included_files"] == [reporting.REPORT_MARKDOWN]
    assert response["validated_research_files"] == list(REQUIRED_RESEARCH_ARTIFACTS)
    assert Path(response["pdf_path"]).parent == run
    assert Path(response["pdf_path"]).read_bytes().startswith(b"%PDF")
    assert Path(response["html_path"]).is_file()
    assert "class=\"report-header\"" in Path(response["html_path"]).read_text()


def test_generate_report_returns_structured_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_run(tmp_path, monkeypatch)

    response = json.loads(
        reporting.generate_report.invoke(
            {"run_directory": "/output/research/nifty-it/missing"}
        )
    )

    assert response["ok"] is False
    assert response["status"] == "failed"
    assert "does not exist" in response["error"]


def test_generate_report_requires_synthesized_report_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _make_run(tmp_path, monkeypatch)
    (run / reporting.REPORT_MARKDOWN).unlink()

    response = json.loads(
        reporting.generate_report.invoke(
            {"run_directory": "/output/research/nifty-it/20260729T120000Z"}
        )
    )

    assert response["ok"] is False
    assert f"missing {reporting.REPORT_MARKDOWN}" in response["error"]


def test_generate_report_validates_research_artifacts_before_rendering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _make_run(tmp_path, monkeypatch)
    (run / "07_equal_depth_deep_research.md").unlink()
    response = json.loads(reporting.generate_report.invoke({"run_directory": str(run)}))
    assert response["ok"] is False
    assert "missing 07_equal_depth_deep_research.md" in response["error"]


def test_generate_report_does_not_publish_failed_compilation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _make_run(tmp_path, monkeypatch)
    monkeypatch.setattr(reporting, "_browser_path", lambda: "/fake/chrome")
    monkeypatch.setattr(
        reporting.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="bad chromium",
        ),
    )

    response = json.loads(
        reporting.generate_report.invoke(
            {"run_directory": "/output/research/nifty-it/20260729T120000Z"}
        )
    )

    assert response["ok"] is False
    assert "Chromium PDF generation failed" in response["error"]
    assert not (run / "final_report.pdf").exists()
    assert not (run / "10_final_report.html").exists()


def test_print_pdf_accepts_complete_output_when_chrome_lingers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "report.pdf"

    def lingering(command, **kwargs):
        output = next(part for part in command if part.startswith("--print-to-pdf="))
        Path(output.split("=", 1)[1]).write_bytes(
            b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF"
        )
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(reporting.subprocess, "run", lingering)
    reporting._print_pdf(
        "/fake/chrome",
        tmp_path / "report.html",
        pdf,
        tmp_path / "profile",
    )
    assert reporting._is_complete_pdf(pdf)


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MIDAS_RUN_INTEGRATION") != "1",
    reason="Set MIDAS_RUN_INTEGRATION=1 to run the Chromium PDF smoke test",
)
def test_generate_report_real_chromium_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_run(tmp_path, monkeypatch)

    response = json.loads(
        reporting.generate_report.invoke(
            {
                "run_directory": "/output/research/nifty-it/20260729T120000Z",
                "title": "Nifty IT Research",
            }
        )
    )

    assert response["ok"] is True, response
    pdf_path = Path(response["pdf_path"])
    assert pdf_path.stat().st_size > 1_000
    assert pdf_path.read_bytes().startswith(b"%PDF")
