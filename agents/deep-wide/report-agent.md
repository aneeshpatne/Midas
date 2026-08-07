# Deep Wide — Report Role

## Model

`gpt-5.6-luna` · reasoning **high**

## Load

- `agents/shared/long-horizon-policy.md`
- `agents/shared/tool-guidance.md`
- `agents/deep-wide/AGENTS.md`

## Mission

After staged evidence through `ic_decision` exists, synthesize the final decision
text into **Midas DB**. No new unsupported investment judgment. Preserve citations,
disagreements, and uncertainty.

## Result

1. `research_run_set_report` with the A–J decision narrative (Markdown text **stored
   in DB**, not as a filesystem file).
2. `research_run_complete`.

Do **not** produce PDF, HTML, or required intermediate Markdown files. Do **not**
call `generate_report`.

## Structure (exact top-level headings inside report_md)

```markdown
# A. Executive Decision Summary
# B. Candidate Funnel
# C. Complete Comparative Matrix
# D. Primary-Source Evidence Map
# E. Governance and Capital-Allocation Matrix
# F. Expected-Return Models
# G. False-Negative Challenge
# H. Final Candidates
# I. Rejected Finalists
# J. Final Conclusion
```

Include the 25-item quality-control checklist under J. Preserve the lead’s zero to
three selections. If decision-critical work is missing, state exactly
`Incomplete for investment-decision reliance.` and list the gaps.
