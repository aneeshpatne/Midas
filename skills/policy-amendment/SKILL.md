---
name: policy-amendment
description: >
  Change a named paper portfolio's rules after an explicit policy
  request. Use when the user amends portfolio policy or runs
  /policy-amendment.
metadata:
  short-description: "Amend portfolio policy"
---
# Policy-amendment skill

Load `skills/paper-portfolio-core/SKILL.md` and
`skills/paper-portfolio-tools/SKILL.md` with this skill.

Use only when the user explicitly changes a named portfolio's rules.

1. Read the current policy and identify the exact requested fields. A capital
   flow, thesis review, or rebalance is not authority to amend policy.
2. Validate the proposed policy as a complete DB-backed policy. Increment
   `policy_version`; preserve immutable portfolio identity and creation time.
3. Persist the complete old/new values for every changed field, effective date,
   reason, and user authorization through the relevant midas-db-mcp policy or
   portfolio update record.
4. Derive the updated state from DB records. Report new warnings or allocation
   gaps. Intermediate files are allowed, but the amendment is final only in DB;
   do not trade automatically.
