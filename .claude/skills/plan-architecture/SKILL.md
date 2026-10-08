---
name: plan-architecture
description: Writes docs/ARCHITECTURE.md from docs/AUDIT.md and docs/USERS.md, with a 500-word summary, trust boundaries, one request traced end to end, verification design, a deviation register, a traceability matrix and the tracer bullet. Use when the audit and persona gates have passed and before the build starts.
disable-model-invocation: true
metadata:
  version: "2.1.0"
---

# Plan the architecture

Produce `docs/ARCHITECTURE.md` from `docs/AUDIT.md`, `docs/USERS.md` and `docs/PLAN.md`. Every
capability must resolve to a `docs/USERS.md` use case. Use the `defend-decision` block for each choice.

It is a concept of the knowledge bundle and carries `type: Architecture`. Link to the audit, the
users and the plan where the text depends on them. The `write-okf-concept` skill has the rules for
the frontmatter, the index and the log.

## Required sections

1. **Summary, about 500 words** (450 to 550; count them): the key decisions, what drove them, the
   tradeoffs.
2. **Trust boundaries**, and who enforces each one.
3. **Data flow:** one request, end to end, naming each component it passes through.
4. **Verification design** and its known blind spots.
5. **Failure behavior per dependency:** what the user sees when each one is down, slow or wrong.
6. **Speed against completeness:** the latency budget and what is dropped to meet it.
7. **Deviation register:** where this design departs from the brief or the plan. A table:
   `| Id | The brief said | Reality (evidence) | Substitute |`, with ids `DV-01`, `DV-02` and so on.
8. **Traceability matrix:** use case → capability → data → audit finding → eval category → metric,
   each named by id (`UC-02`, `SEC-01`, `DR-01`); the metric column takes ids once `docs/metrics/`
   exists. The gate fails on an id that is defined nowhere, so the matrix cannot drift from the
   documents it draws on. `make trace` prints the chain from the north star down.
9. **Tracer bullet:** the one feature that will be built first, the layers it crosses, and the command
   that proves it works end to end. Then the order of the vertical slices that follow.
10. **Cut order:** what is removed first if time runs short, and what is never cut.
11. **Not built:** what was designed but left out, and why.

## Locked decisions

The decisions the owner locked are in `docs/PLAN.md`. Restate them here with their evidence. Do not
reopen one unless the evidence has changed; if it has, say what changed and ask the owner.

## Build order

The architecture is a claim until one feature has gone through all of it. Section 9 is that test:
choose a feature thin enough to finish quickly and wide enough to touch every layer. Anything it proves
wrong goes into the deviation register before the next slice starts. No horizontal work (a complete
data layer, a full API surface, a shared abstraction) is planned ahead of the slice that needs it.

## Acceptance

- [ ] The summary is 450 to 550 words
- [ ] Every capability row cites a `docs/USERS.md` use case id
- [ ] The deviation register is present, with evidence for each row
- [ ] The tracer bullet names its feature, its layers and its proving command
- [ ] The cut order is stated
- [ ] The document carries `type: Architecture`, `make docs-index` was run, and `docs/log.md` has
      its entry
