import json
import os
import shutil
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
        "# Final Research Report\n\n"
        "This is a synthesized narrative based on the completed research.\n",
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

    (run / "03_primary_selection.md").unlink()
    with pytest.raises(ValueError) as error:
        reporting._validate_artifacts(run)

    message = str(error.value)
    assert "missing 03_primary_selection.md" in message


def test_markdown_renderer_escapes_latex_and_supports_tables() -> None:
    rendered = reporting._markdown_to_latex(
        "# Test\n\nRevenue grew 12% & margin improved for **A_B**.\n\n"
        "| Name | Score |\n| --- | ---: |\n| A_B | 75 |\n"
    )

    assert r"12\%" in rendered
    assert r"\&" in rendered
    assert r"\textbf{A\_B}" in rendered
    assert r"\begin{longtable}" in rendered


def test_markdown_renderer_safely_handles_bare_urls_in_tables() -> None:
    rendered = reporting._markdown_to_latex(
        "| Source | URL |\n"
        "| --- | --- |\n"
        "| NSE | https://example.com/report?symbol=NIFTY%20MID%20SELECT |\n"
    )

    assert r"\url{https://example.com/report?symbol=NIFTY%20MID%20SELECT}" in rendered


def test_table_rows_cannot_treat_bracketed_source_ids_as_spacing() -> None:
    rendered = reporting._markdown_to_latex(
        "| Source | Title |\n"
        "| --- | --- |\n"
        "| [S01] | First |\n"
        "| [S02] | Second |\n"
    )

    assert r"First \\[0pt]" in rendered
    assert r"[S02] & Second" in rendered


def test_generate_report_compiles_and_publishes_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _make_run(tmp_path, monkeypatch)
    monkeypatch.setattr(reporting.shutil, "which", lambda _: "/fake/tectonic")

    def fake_run(command, **kwargs):
        outdir = Path(command[command.index("--outdir") + 1])
        (outdir / "final_report.pdf").write_bytes(b"%PDF-1.7\nmock")
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
    assert Path(response["pdf_path"]).parent == run
    assert Path(response["pdf_path"]).read_bytes().startswith(b"%PDF")


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


def test_generate_report_does_not_publish_failed_compilation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _make_run(tmp_path, monkeypatch)
    monkeypatch.setattr(reporting.shutil, "which", lambda _: "/fake/tectonic")
    monkeypatch.setattr(
        reporting.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="bad latex",
        ),
    )

    response = json.loads(
        reporting.generate_report.invoke(
            {"run_directory": "/output/research/nifty-it/20260729T120000Z"}
        )
    )

    assert response["ok"] is False
    assert "Tectonic compilation failed" in response["error"]
    assert not (run / "final_report.pdf").exists()


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MIDAS_RUN_INTEGRATION") != "1" or shutil.which("tectonic") is None,
    reason="Set MIDAS_RUN_INTEGRATION=1 and install Tectonic to run the PDF smoke test",
)
def test_generate_report_real_tectonic_smoke(
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
