# Deep Wide — Report Role

## Model

`gpt-5.6-luna` · reasoning **high**

## Load

- `agents/shared/long-horizon-policy.md`
- `agents/deep-wide/AGENTS.md`

## Mission

After `00`–`09` exist and are non-empty, synthesize the final report. No new
unsupported investment judgment. Preserve citations, disagreements, and uncertainty.

## Result

Write only this Markdown file in the current run folder:

- `10_final_report.md`

That file is the full result of this role. **No HTML, PDF, or other formats.**

## Structure (exact top-level headings)

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

Include the 25-item quality-control checklist under J. Preserve the lead’s
zero-to-three selections. If incomplete, state
`Incomplete for investment-decision reliance.` and list missing work.
