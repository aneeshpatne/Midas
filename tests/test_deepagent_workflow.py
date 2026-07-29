from midas.deepagents.prompts import (
    ADVERSARIAL_AGENT_PROMPT,
    MIDAS_PRIMARY_SYSTEM_PROMPT,
    REQUIRED_RESEARCH_ARTIFACTS,
    SCORING_RUBRIC,
)
from midas.deepagents.reporting import REPORT_TOOLS, generate_report
from midas.deepagents.tools import MIDAS_TOOLS


def test_research_artifact_contract_is_complete_and_ordered() -> None:
    assert REQUIRED_RESEARCH_ARTIFACTS == (
        "00_mandate.md",
        "01_universe.md",
        "02_primary_research.md",
        "03_primary_selection.md",
        "04_adversary_independent.md",
        "05_adversary_critique.md",
        "06_reconciliation.md",
        "07_final_selection.md",
    )


def test_primary_prompt_requires_blind_review_before_critique_and_reconciliation() -> None:
    independent = MIDAS_PRIMARY_SYSTEM_PROMPT.index("BLIND independent screen")
    critique = MIDAS_PRIMARY_SYSTEM_PROMPT.index("red-team review")
    reconcile = MIDAS_PRIMARY_SYSTEM_PROMPT.index("Personally verify")

    assert independent < critique < reconcile
    assert "Never mechanically average" in MIDAS_PRIMARY_SYSTEM_PROMPT
    assert "only report-agent" in MIDAS_PRIMARY_SYSTEM_PROMPT


def test_adversarial_prompt_forbids_primary_files_during_blind_pass() -> None:
    assert "Do not search the run directory for primary research" in ADVERSARIAL_AGENT_PROMPT
    assert "`02_` or `03_`" in ADVERSARIAL_AGENT_PROMPT
    assert "critical, material, minor, or unsupported" in ADVERSARIAL_AGENT_PROMPT


def test_scoring_rubric_totals_one_hundred() -> None:
    weights = [20, 20, 20, 15, 15, 10]
    assert sum(weights) == 100
    assert all(f": {weight}" in SCORING_RUBRIC for weight in set(weights))


def test_report_role_declares_exactly_one_tool() -> None:
    assert REPORT_TOOLS == (generate_report,)


def test_research_tool_names_are_unique() -> None:
    names = [item.name for item in MIDAS_TOOLS]
    assert len(names) == len(set(names))


def test_research_and_adversarial_roles_receive_the_primary_research_tools() -> None:
    from midas.deepagents.deepagent import build_subagents

    by_name = {spec["name"]: spec for spec in build_subagents()}

    assert by_name["research-agent"]["tools"] is MIDAS_TOOLS
    assert by_name["adversarial-agent"]["tools"] is MIDAS_TOOLS
    report_runnable = by_name["report-agent"]["runnable"]
    report_tool_node = report_runnable.nodes["tools"].bound
    assert set(report_tool_node.tools_by_name) == {"generate_report"}
