---
name: defend-decision
description: Writes a defensible decision block (claim, evidence, alternative considered, why rejected, how to reverse) for an architecture, data, tooling or testing choice. Use when documenting a tradeoff or a deviation from the plan in docs/AUDIT.md, docs/USERS.md, docs/ARCHITECTURE.md, docs/KEY_METRICS.md or any other project document.
metadata:
  version: "1.1.1"
---

# Defend a decision

Every architecture, data, tooling and testing choice in this project must hold up when a reviewer asks
"why this, and not the obvious alternative?". When documenting a decision, write this block (no extra
headings):

```markdown
**Claim:** <one sentence of what we decided>
**Evidence:** <code path:line, query, command and its output, measurement, or a citation from the brief>
**Alternative considered:** <the strongest rejected option>
**Why rejected:** <one or two sentences, including cost and risk>
**How to reverse:** <the smallest change that undoes this if the evidence changes>
```

Rules:

- A claim without evidence is not a decision. Drop it or go and gather the evidence.
- The alternative must be a real option a reviewer would propose, not a straw man.
- "How to reverse" must name a file, an interface or a configuration flag, not "rewrite the system".
- If the decision departs from the original plan or brief, also add a row to the deviation register in
  `docs/ARCHITECTURE.md`.
