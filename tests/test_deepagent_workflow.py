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
    SOURCE_AND_ARTIFACT_RULES,
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


def test_primary_prompt_preserves_staged_independent_review() -> None:
    prompt = " ".join(MIDAS_PRIMARY_SYSTEM_PROMPT.split())
    independent = prompt.index("BLIND INDEPENDENT MODE")
    false_negative = prompt.index("RED-TEAM FALSE-NEGATIVE MODE")
    reconcile = prompt.index("Personally verify material disagreements")
    deep_research = prompt.index("Launch `deep-research-agent`")
    bear = prompt.index("FINALIST BEAR MODE")
    committee = prompt.index("`09_investment_committee_decision.md`")
    report = prompt.index("Launch `report-agent`")

    assert independent < false_negative < reconcile < deep_research
    assert deep_research < bear < committee < report
    assert "Never mechanically average" in prompt
    assert "zero to three selections" in prompt
    assert "Only report-agent" in MIDAS_PRIMARY_SYSTEM_PROMPT


def test_objectives_outputs_and_conclusions_are_separate() -> None:
    standard = INVESTMENT_GRADE_SELECTION_STANDARD
    for objective in (
        "best businesses regardless of valuation",
        "most attractive investments at current prices",
        "highest priority for deeper research",
        "suitable for a seven-to-ten-year holding period",
    ):
        assert objective in standard
    for output in (
        "Best Businesses",
        "Best-Valued Acceptable Businesses",
        "Highest-Priority Research Candidates",
        "High-Quality Companies That Are Currently Too Expensive",
        "Companies Failing business-quality",
    ):
        assert output in standard
    assert "Business Classification:" in standard
    assert "Investment Classification at Current Price:" in standard
    assert "Seven-to-Ten-Year Holding Suitability:" in standard
    assert "High-quality business — wait for valuation" in standard


def test_scoring_rubric_is_reproducible_and_refuses_false_precision() -> None:
    rubric = " ".join(SCORING_RUBRIC.split())
    weights = [20, 20, 20, 15, 15, 10]
    assert sum(weights) == 100
    assert all(f"| {weight} |" in SCORING_RUBRIC for weight in set(weights))
    for requirement in (
        "evidence supporting it",
        "evidence against it",
        "why it is not higher",
        "why it is not lower",
        "Evidence Confidence",
        "source IDs",
    ):
        assert requirement in rubric
    assert "Not scored — Insufficient Evidence" in rubric
    assert "do not impute zero" in rubric
    assert "Do not automatically favour asset-light companies" in rubric
    assert "numeric Valuation Score" in rubric


def test_candidate_funnel_uses_independent_entry_routes_and_dynamic_depth() -> None:
    standard = INVESTMENT_GRADE_SELECTION_STANDARD
    for screen in (
        "Durable business quality",
        "Cash-flow quality",
        "Governance",
        "Valuation",
        "Reinvestment runway",
        "Balance-sheet resilience",
        "Independent qualitative business-model review",
    ):
        assert screen in standard
    assert "at least two independent" in standard
    assert "five strongest excluded" in standard
    assert "deep-dive count is determined by evidence" in standard
    assert "not a fixed quota" in MIDAS_PRIMARY_SYSTEM_PROMPT
    assert "eight to ten" not in MIDAS_PRIMARY_SYSTEM_PROMPT.lower()


def test_equal_depth_packet_and_missing_evidence_rules_are_complete() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())
    rules = " ".join(SOURCE_AND_ARTIFACT_RULES.split())
    for packet_item in (
        "Business model and industry structure",
        "Competitive position",
        "Reinvestment runway",
        "Historical financials and cash-flow quality",
        "Balance-sheet quality",
        "Management and capital allocation",
        "Governance",
        "Sector-specific metrics",
        "Normalized earnings",
        "Valuation and expected returns",
        "Liquidity",
        "Thesis conditions and permanent thesis killers",
        "Evidence confidence",
    ):
        assert packet_item in standard
    assert "Missing data is not evidence of poor quality" in rules
    for forbidden_rejection in (
        "Not reviewed in depth",
        "Data unavailable",
        "No near-term catalyst",
        "No variant wedge",
        "Appears",
    ):
        assert forbidden_rejection in rules


def test_sector_specific_analysis_covers_all_required_models() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())
    for sector in (
        "Banks:",
        "NBFCs:",
        "Consumer companies:",
        "Industrials and manufacturing:",
        "Platforms and marketplaces:",
        "Exchanges and market infrastructure:",
        "Pharmaceutical companies:",
        "Commodity and cyclical companies:",
    ):
        assert sector in standard
    for metric in (
        "slippages",
        "asset-liability matching",
        "rural/urban exposure",
        "incremental ROCE",
        "multi-homing",
        "market-coupling risk",
        "US-generics exposure",
        "cost-curve position",
    ):
        assert metric in standard
    assert "Never value a cyclical company using peak-cycle earnings" in standard


def test_evidence_hierarchy_claim_types_and_conflicts_are_explicit() -> None:
    rules = " ".join(SOURCE_AND_ARTIFACT_RULES.split())
    assert rules.index("1. Audited annual reports") < rules.index("2. NSE and BSE filings")
    for claim_type in (
        "Company-reported fact",
        "Regulator-reported fact",
        "Third-party estimate",
        "Management claim",
        "Agent calculation",
        "Analyst inference",
        "Unverified claim",
    ):
        assert claim_type in rules
    assert "working papers, not independent evidence" in rules
    assert "Never silently choose the more convenient number" in rules


def test_normalization_governance_and_allocation_contracts_are_complete() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())
    for item in (
        "deferred-revenue timing",
        "working-capital timing",
        "Reported PAT",
        "Normalized PAT",
        "Reported EPS",
        "Normalized EPS",
        "maintenance capex",
        "growth capex",
        "Normalized FCF",
        "return on incremental capital",
    ):
        assert item in standard
    for governance_item in (
        "auditor identity and tenure",
        "emphasis-of-matter",
        "exchange penalties",
        "ESOP dilution",
        "minority-shareholder disputes",
        "Requires Monitoring",
    ):
        assert governance_item in standard
    for allocation_item in (
        "debt issuance",
        "management's stated rationale",
        "actual result",
        "approximate return",
        "effect on per-share value",
        "confidence in management increased or decreased",
    ):
        assert allocation_item in standard


def test_valuation_returns_benchmarks_hurdle_and_zones_are_reproducible() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())
    assert "at least two appropriate valuation methods" in standard
    assert "Analyst target prices are not valuation evidence" in standard
    for zone in ("Attractive", "Reasonable", "Watch", "Full", "Speculative"):
        assert f"- {zone}" in standard
    for row in (
        "Starting normalized revenue",
        "Terminal margin",
        "Share-count change",
        "Terminal EPS or FCF per share",
        "Cumulative dividends",
        "Nominal annualized return",
        "Real annualized return",
    ):
        assert row in standard
    assert "no base-case multiple expansion" in standard
    for benchmark in (
        "Nifty Smallcap 250 TRI",
        "Nifty 200 TRI",
        "Nifty 50 TRI",
        "Indian ten-year government securities",
        "Indian CPI",
    ):
        assert benchmark in standard
    assert "quantified required excess return" in standard
    assert "whether the base case clears it" in standard


def test_liquidity_is_measured_classified_and_gated() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())
    for metric in (
        "free-float market capitalization",
        "median daily traded value and volume",
        "bid-ask spread",
        "low-volume-day frequency",
        "circuit-limit frequency",
        "estimated entry/exit days",
        "stress-period liquidity",
    ):
        assert metric in standard
    for classification in ("Strong", "Adequate", "Limited", "Poor", "Unacceptable"):
        assert classification in standard
    assert "0.5%, 1% and 2% of free-float" in standard
    assert "Poor and Unacceptable cannot be final selections" in standard


def test_bear_opportunity_cost_and_ordered_gates_are_explicit() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())
    for bear_item in (
        "Most optimistic assumption",
        "Weakest moat claim",
        "Governance, regulatory and liquidity risks",
        "Historical analogue",
        "Evidence that would invalidate the bear case",
    ):
        assert bear_item in standard
    for comparator in (
        "closest rejected alternative",
        "strongest industry competitor",
        "different economic model",
        "diversified index",
    ):
        assert comparator in standard
    gates = [
        "1. Data sufficiency",
        "2. Governance",
        "3. Liquidity",
        "4. Business-quality threshold",
        "5. Reinvestment-runway threshold",
        "6. Permanent-capital-loss assessment",
        "7. Normalized valuation",
        "8. Bear-case downside",
        "9. Base expected return",
        "10. Benchmark-relative expected return",
        "11. Evidence confidence",
        "12. Portfolio concentration and correlation",
    ]
    assert all(gate in standard for gate in gates)
    assert "earliest failed gate as the controlling failed gate" in standard
    assert "Not selected — concentration/correlation" in standard


def test_gate_thresholds_are_precommitted_and_structural_failures_are_not_price_cured() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())
    for threshold in (
        "Data sufficiency passes only for Complete or Mostly Complete",
        "Business quality passes at 75/100 or above",
        "Reinvestment runway passes at 12/20 or above",
        "two-year operating downturn",
        "precommitted permanent-loss tolerance",
        "Base expected return must be positive in real terms",
        "Moderate-High or High",
        "precommitted mandate limits",
    ):
        assert threshold in standard
    assert "do not relax them after seeing company names or results" in standard
    assert "Not applicable — no price cures this gate" in standard


def test_false_negative_report_rule_handles_small_universes() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())
    assert (
        "five strongest false-negative challenges, or all excluded companies when "
        "fewer than five exist"
    ) in standard


def test_zero_selection_calibration_confidence_and_final_principle() -> None:
    standard = " ".join(INVESTMENT_GRADE_SELECTION_STANDARD.split())
    assert "three, fewer than three, or zero companies" in standard
    for calibration in (
        "only in crashes",
        "systematically rejects compounders",
        "unrealistically low terminal multiples",
        "excessive hurdle",
        "favours mature cash generators",
        "over-penalizes small-cap uncertainty",
        "positive selections in normal markets",
    ):
        assert calibration in standard
    for confidence in ("High", "Moderate-High", "Moderate", "Low", "Insufficient Evidence"):
        assert confidence in standard
    assert "Do not optimize for producing an impressive answer" in standard
    assert "At the current price, does this company offer a" in standard


def test_report_contract_has_a_to_j_and_twenty_five_qc_items() -> None:
    headings = (
        "A. Executive Decision Summary",
        "B. Candidate Funnel",
        "C. Complete Comparative Matrix",
        "D. Primary-Source Evidence Map",
        "E. Governance and Capital-Allocation Matrix",
        "F. Expected-Return Models",
        "G. False-Negative Challenge",
        "H. Final Candidates",
        "I. Rejected Finalists",
        "J. Final Conclusion",
    )
    for heading in headings:
        assert heading in INVESTMENT_GRADE_SELECTION_STANDARD
        assert f"# {heading}" in REPORT_AGENT_PROMPT
    assert INVESTMENT_GRADE_SELECTION_STANDARD.count("\n25.") == 1
    assert "Incomplete for investment-decision reliance." in REPORT_AGENT_PROMPT


def test_policy_is_shared_by_every_agent_role() -> None:
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
        assert "Current Valuation" in prompt
        assert "Liquidity" in prompt


def test_progressive_policy_reduces_fixed_prompt_overhead() -> None:
    prompts = (
        MIDAS_PRIMARY_SYSTEM_PROMPT,
        RESEARCH_AGENT_PROMPT,
        ADVERSARIAL_AGENT_PROMPT,
        DEEP_RESEARCH_AGENT_PROMPT,
        REPORT_AGENT_PROMPT,
    )
    optimized_characters = sum(map(len, prompts))
    repeated_full_policy_floor = len(LONG_HORIZON_RESEARCH_POLICY) * len(prompts)

    assert optimized_characters < repeated_full_policy_floor * 0.20
    assert "research_policy" in "\n".join(prompts)


def test_adversarial_and_deep_research_roles_enforce_new_contract() -> None:
    adversarial = " ".join(ADVERSARIAL_AGENT_PROMPT.split())
    deep = " ".join(DEEP_RESEARCH_AGENT_PROMPT.split())
    assert "Do not search the run directory for primary research" in adversarial
    assert "five strongest excluded companies" in adversarial
    assert "including expensive high-quality names" in adversarial
    assert "every explicitly assigned evidence-qualified company" in deep
    assert "same minimum depth" in deep
    assert "do not narrow or broaden" in deep
    assert "two-method valuation" in deep


def test_report_role_declares_exactly_one_tool() -> None:
    assert REPORT_TOOLS == (generate_report,)


def test_research_tool_names_are_unique() -> None:
    names = [item.name for item in MIDAS_TOOLS]
    assert len(names) == len(set(names))


def test_research_roles_receive_expected_tools_and_guidance() -> None:
    from midas.deepagents.deepagent import MIDAS_TOOL_GUIDANCE, build_subagents

    by_name = {spec["name"]: spec for spec in build_subagents()}

    assert by_name["research-agent"]["tools"] is MIDAS_TOOLS
    assert by_name["adversarial-agent"]["tools"] is MIDAS_TOOLS
    assert by_name["deep-research-agent"]["tools"] is MIDAS_TOOLS
    report_tool_node = by_name["report-agent"]["runnable"].nodes["tools"].bound
    assert "generate_report" in report_tool_node.tools_by_name
    assert {"read_file", "write_file"}.issubset(report_tool_node.tools_by_name)
    assert "Run all scraping and market-data tools sequentially" in MIDAS_TOOL_GUIDANCE
    assert "Only web_research calls are exempt" in MIDAS_TOOL_GUIDANCE
    assert "median traded value/volume" in MIDAS_TOOL_GUIDANCE
    assert "government-security benchmark" in MIDAS_TOOL_GUIDANCE


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
