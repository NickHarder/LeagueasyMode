---
name: define-personas
description: Writes docs/USERS.md with the primary persona, the secondary personas that mark authorization boundaries, the moments in their day and the use cases the product serves. Use when producing or updating the user gate, after the audit and before the architecture.
disable-model-invocation: true
metadata:
  version: "2.1.1"
---

# Define personas and use cases

Produce `docs/USERS.md`. It is a concept of the knowledge bundle and carries `type: Users`.
The `write-okf-concept` skill has the rules for the frontmatter, the index and the log.

Every persona, anti-persona and use case sits under a heading that starts with its id:
`### P-01: <name>`, `### AP-01: <who is refused>`, `### UC-01: <the question, in a few words>`. The
heading is what defines the id. Eval cases guard a use case by it (`guards: [UC-01]`), metrics prove it
by it (`proves: [UC-01]`), and the gate fails on an id that is defined nowhere or by two headings.

Do not write a generic "users need help" thesis. Every field below is mandatory. `make gate` cannot
check that; the owner's review does, and sends back an empty field. Where the brief or the audit does
not answer a field, ask the owner rather than invent it.

## Persona template

For each persona (ids `P-01`, `P-02`, …):

- Name and role; the account they sign in with
- Setting (size of the organization, staffing, equipment)
- Volume (how many cases, customers or requests a day)
- A full day, by the clock
- The tools and screens they touch today, in order
- What they type and what they read
- Interruptions and physical environment
- Trust posture (how they treat an unsourced claim; whether "I don't know" is acceptable)
- Tolerances (latency ceiling, acceptable miss rate, error classes that are never acceptable)
- What they must never be shown
- Authorization scope, in the system's own terms
- Success, in one sentence

Secondary personas exist to mark authorization boundaries: specify each one as fully as the primary.
Anti-personas (`AP-01`, …) are the users the product must refuse; say how it recognizes them.

## Moment template

- Clock time
- What they were doing 30 seconds before
- The question, in their own words
- What they would open today to answer it
- Time available
- What they do with the answer

## Use-case template

For each use case (ids `UC-01`, …):

- The moment it serves
- The exact question or questions
- The data it needs, and where that lives
- Required latency
- What a wrong answer costs, and to whom
- Why this product and not the thing they already have (name the alternative: a dashboard, a sorted
  list, a better existing view)
- Refusal behaviors
- Whether it needs several turns or chained tools (if not, say so)
- The eval categories that guard it
- The metric that proves it worked (by its id, such as `DR-02`, once `docs/metrics/` exists)

Each use case must survive "would they choose this over what they open today?" or be cut. Keep the cut
ones in a "Considered and cut" list with the reason.

## Sections of `docs/USERS.md`

1. The setting · 2. Primary persona · 3. Secondary personas and anti-personas · 4. Moments in the day ·
5. Use cases, then "Considered and cut" · 6. Traceability (use case → persona → moment) ·
7. The demo, described against the real seeded data once it exists.

## Acceptance

- [ ] Every persona, moment and use case has every field
- [ ] Authorization scope is stated in the system's own terms
- [ ] Every use case names the alternative it beats
- [ ] The cut list has reasons
- [ ] The document carries `type: Users`, `make docs-index` was run, and `docs/log.md` has its entry
