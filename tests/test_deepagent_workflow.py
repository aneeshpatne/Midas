from midas.deepagents.prompts import (
    ADVERSARIAL_AGENT_PROMPT,
    DEEP_RESEARCH_AGENT_PROMPT,
    INVESTMENT_GRADE_SELECTION_STANDARD,
    LONG_HORIZON_RESEARCH_POLICY,
    MIDAS_PRIMARY_SYSTEM_PROMPT,
    REPORT_AGENT_PROMPT,
    REQUIRED_RESEARCH_ARTIFACTS,
    RESEARCH_AGENT_PROMPT,
    SCORING_RUBRIC,
)
from midas.deepagents.reporting import REPORT_TOOLS, generate_report
from midas.deepagents.tools import MIDAS_TOOLS


def test_research_artifact_contract_is_complete_and_ordered() -> None:
    assert REQUIRED_RESEARCH_ARTIFACTS == (
        "00_mandate.md",
        "01_universe.md",
        "02_primary_research.md",
        "03_primary_shortlist.md",
        "04_adversary_independent.md",
        "05_adversary_critique.md",
        "06_deep_dive_shortlist.md",
        "07_equal_depth_deep_research.md",
        "08_finalist_bear_cases.md",
        "09_investment_committee_decision.md",
    )


def test_primary_prompt_requires_blind_review_before_critique_and_reconciliation() -> None:
    prompt = " ".join(MIDAS_PRIMARY_SYSTEM_PROMPT.split())
    independent = prompt.index("BLIND independent screen")
    critique = prompt.index("red-team review")
    reconcile = prompt.index("Personally verify")
    deep_research = prompt.index("Launch `deep-research-agent`")
    bear = prompt.index("FINALIST BEAR MODE")
    committee = prompt.index(
        "`09_investment_committee_decision.md`"
    )
    report = prompt.index("Launch `report-agent`")

    assert independent < critique < reconcile
    assert reconcile < deep_research < bear < committee < report
    assert "never mechanically average" in prompt
    assert "zero to three final" in MIDAS_PRIMARY_SYSTEM_PROMPT
    assert "only report-agent" in MIDAS_PRIMARY_SYSTEM_PROMPT.lower()


def test_adversarial_prompt_forbids_primary_files_during_blind_pass() -> None:
    assert "Do not search the run directory for primary research" in ADVERSARIAL_AGENT_PROMPT
    assert "`02_` or `03_`" in ADVERSARIAL_AGENT_PROMPT
    assert "critical, material, minor, or unsupported" in ADVERSARIAL_AGENT_PROMPT
    assert "FINALIST BEAR MODE" in ADVERSARIAL_AGENT_PROMPT
    assert "strongest reason to own the index" in ADVERSARIAL_AGENT_PROMPT


def test_scoring_rubric_totals_one_hundred() -> None:
    rubric = " ".join(SCORING_RUBRIC.split())
    weights = [20, 20, 20, 15, 15, 10]
    assert sum(weights) == 100
    assert all(f": {weight}" in SCORING_RUBRIC for weight in set(weights))
    assert "Do not collapse these dimensions into a composite" in rubric
    assert "why it is not higher" in rubric
    assert "why it is not lower" in rubric
    assert "at least 75" in rubric


def test_long_horizon_policy_is_shared_by_every_agent_role() -> None:
    marker = "# Long-Horizon Indian Equity Research Policy"

    assert marker in LONG_HORIZON_RESEARCH_POLICY
    for prompt in (
        MIDAS_PRIMARY_SYSTEM_PROMPT,
        RESEARCH_AGENT_PROMPT,
        ADVERSARIAL_AGENT_PROMPT,
        DEEP_RESEARCH_AGENT_PROMPT,
        REPORT_AGENT_PROMPT,
    ):
        assert marker in prompt
        assert "seven to ten years" in prompt
        assert "Question 3 must never overwrite Questions 1 and 2" in prompt


def test_policy_preserves_expensive_quality_and_missing_data() -> None:
    policy = " ".join(LONG_HORIZON_RESEARCH_POLICY.split())
    assert "remains highly ranked for quality" in LONG_HORIZON_RESEARCH_POLICY
    assert "High-quality valuation watchlist" in LONG_HORIZON_RESEARCH_POLICY
    assert "Never reject, eliminate" in LONG_HORIZON_RESEARCH_POLICY
    assert "Category G:" in LONG_HORIZON_RESEARCH_POLICY
    assert "do not give it a final rank" in policy
    assert "Assign every company to exactly one primary category" in (
        LONG_HORIZON_RESEARCH_POLICY
    )
    assert "Select fewer than three companies, or none" in policy


def test_policy_blocks_short_term_score_leakage_and_false_diversification() -> None:
    policy = " ".join(LONG_HORIZON_RESEARCH_POLICY.split())

    assert "cannot materially increase Business Quality" in policy
    assert "Replace “Why now?”" in policy
    assert "do not call two lenders diversified" in policy
    assert "select at most one company from a narrow industry" in policy
    assert "rankings would remain broadly similar if the next result date were unknown" in (
        LONG_HORIZON_RESEARCH_POLICY
    )


def test_report_prompt_requires_the_long_horizon_output_contract() -> None:
    prompt = " ".join(REPORT_AGENT_PROMPT.split())
    for heading in (
        "A. Investment decision summary",
        "B. Candidate funnel",
        "C. Full finalist comparison",
        "D. Final selections",
        "E. Rejected finalists",
        "F. Final conclusion",
    ):
        assert heading in prompt
    assert "`10_final_report.md`" in prompt
    assert "zero to three selections" in prompt
    assert "fifteen-question quality-control" in prompt


def test_investment_grade_standard_has_current_price_and_primary_source_gates() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())

    assert "exact time, and timezone" in standard
    assert "Stale price data prohibit" in standard
    assert "shares outstanding" in standard
    assert "material announcements through the cut-off" in standard
    assert "Secondary sites" in standard
    assert "cannot be the sole support for decisive" in standard
    assert "Internal research artifacts are not independent evidence" in standard


def test_investment_grade_standard_requires_equal_depth_models_and_governance() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())

    assert "eight to ten strongest business-quality candidates" in standard
    assert "same minimum deep-dive for every one" in standard
    assert "at least the previous ten years" in standard
    assert (
        "Strong, Acceptable, Material concern, Unacceptable, or Insufficient evidence"
        in standard
    )
    assert "at least two appropriate valuation methods" in standard
    assert "seven-to-ten-year bear, base, and bull annualized" in standard
    assert "Do not assume base-case multiple expansion" in standard
    assert "at least three relevant peers where possible" in standard


def test_investment_grade_standard_requires_alternatives_bears_and_conditional_selection() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())

    assert "Nifty 50 TRI" in standard
    assert "Indian ten-year government-security yield" in standard
    assert "assign an independent bear analyst" in standard
    assert "strongest reason to own the index" in standard
    assert "Advance as high-conviction candidate" in standard
    assert "Select fewer than three companies, or none" in standard
    assert "unquestionable, certain, guaranteed, objectively proven" in standard
    assert "fewer than three companies currently meet the required quality" in standard
    assert "no company in the current universe offers a sufficiently attractive" in standard
    assert "all fifteen questions" in standard


def test_report_role_declares_exactly_one_tool() -> None:
    assert REPORT_TOOLS == (generate_report,)


def test_research_tool_names_are_unique() -> None:
    names = [item.name for item in MIDAS_TOOLS]
    assert len(names) == len(set(names))


def test_research_and_adversarial_roles_receive_the_primary_research_tools() -> None:
    from midas.deepagents.deepagent import MIDAS_TOOL_GUIDANCE, build_subagents

    by_name = {spec["name"]: spec for spec in build_subagents()}

    assert by_name["research-agent"]["tools"] is MIDAS_TOOLS
    assert by_name["adversarial-agent"]["tools"] is MIDAS_TOOLS
    assert by_name["deep-research-agent"]["tools"] is MIDAS_TOOLS
    report_runnable = by_name["report-agent"]["runnable"]
    report_tool_node = report_runnable.nodes["tools"].bound
    assert "generate_report" in report_tool_node.tools_by_name
    assert {"read_file", "write_file"}.issubset(report_tool_node.tools_by_name)
    assert "Run all scraping and market-data tools sequentially, never in parallel" in (
        MIDAS_TOOL_GUIDANCE
    )
    assert "Only web_research calls are exempt" in MIDAS_TOOL_GUIDANCE
    assert "must never increase the Long-Term" in MIDAS_TOOL_GUIDANCE
    assert "classify missing evidence as Insufficient Evidence" in MIDAS_TOOL_GUIDANCE
    assert "never force three final selections" in MIDAS_TOOL_GUIDANCE


def test_deep_research_role_is_equal_depth_and_runs_before_final_selection() -> None:
    prompt = " ".join(DEEP_RESEARCH_AGENT_PROMPT.split())

    assert "eight to ten explicitly assigned companies" in prompt
    assert "same minimum depth" in prompt
    assert "do not narrow or broaden the shortlist" in prompt
    assert "two-method valuation" in prompt
    assert "Write only `07_equal_depth_deep_research.md`" in DEEP_RESEARCH_AGENT_PROMPT


def test_deep_research_role_uses_its_dedicated_model_factory(monkeypatch) -> None:
    from midas.deepagents import deepagent

    standard_model = object()
    deep_model = object()
    monkeypatch.setattr(deepagent, "get_research_model", lambda: standard_model)
    monkeypatch.setattr(deepagent, "get_deep_research_model", lambda: deep_model)
    monkeypatch.setattr(deepagent, "get_summarizer_model", lambda: object())
    monkeypatch.setattr(deepagent, "create_deep_agent", lambda **kwargs: object())

    by_name = {spec["name"]: spec for spec in deepagent.build_subagents()}

    assert by_name["research-agent"]["model"] is standard_model
    assert by_name["adversarial-agent"]["model"] is standard_model
    assert by_name["deep-research-agent"]["model"] is deep_model
