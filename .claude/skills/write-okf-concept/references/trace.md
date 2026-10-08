# The trace: ids, the chain they make, and its floors

## The chain

```
NS-01  the north star
  DR-01, DR-02 ...  drivers      supports: NS-01
  GR-01, GR-02 ...  guardrails   supports: NS-01
    each key metric              proves: [UC-01, UC-03]     the use cases whose promise it proves
      each eval case             guards: [UC-01]            what it protects
                                 metrics: [DR-01]           whose number its verdict feeds
```

`make trace` prints it for this project: each metric with its status and how far it has been
checked, the cases under it with their last verdicts, the cases that guard each use case, and the
gaps.

## Where an id is defined

An id is one to five capitals, a hyphen, and two or more digits.

| The id of | Is defined by | Example |
|---|---|---|
| A key metric | Its file name under `docs/metrics/` | `docs/metrics/NS-01.md` |
| A persona, a use case | A heading that starts with it, in `docs/USERS.md` | `### UC-01: Ask about an invoice` |
| A finding | A heading that starts with it, in `docs/audit/<area>.md` | `### [SEC-01] A key in the history` |
| A deviation | The first cell of its row in the register | `\| DV-01 \| ... \|` |
| An eval case | Its `id` | `id: G-01` |

Define an id once. A table that lists ids defined elsewhere, such as the audit's summary or the
architecture's traceability matrix, names them and does not define them again. A row defines an id
only when no heading, file name or case defines an id with the same capitals, as in the register of
deviations. So a `UC-07` that only the matrix lists is defined nowhere, and the gate says so.

A word such as SHA-256 is taken for an id only when its capitals start an id this project has
defined. If a project defines `G-01`, do not write "G-20" in prose to mean something else.

## A key metric's fields

```yaml
---
type: Metric
title: Answers that quote the source
description: The share of answers in which every figure is quoted exactly from the source.
status: draft
generated: { by: claude-code/claude-fable-5-1, at: 2026-10-04T12:00:00Z }
role: north-star
proves: [UC-01, UC-02]
---
```

A driver or a guardrail also has `supports: NS-01`. There is one north star.

## What fails the gate, always

- An id that is named and defined nowhere: in a case's `guards` or `metrics`, in a metric's
  `supports` or `proves`, or in the text of any concept.
- An id that two headings define, or a heading and a file name, or a heading and an eval case. A
  key metric's own heading may repeat the id its file is named after.
- A second north star, a driver or a guardrail with no `supports`, or one that supports something
  other than the north star.
- A `role` that is not `north-star`, `driver` or `guardrail`; a key metric whose file name is not
  its id.

## Gaps, and their floors

A gap is something the trace does not reach yet. It is a note in the gate until its floor is on,
under `trace:` in `evals/thresholds.yaml`. The owner's review covers that file, and it says when a
floor may be turned off. Turn a floor on in the change that closes its gaps.

| A gap | Its floor |
|---|---|
| A case with no `guards` | `every_case_names_a_use_case_or_finding` |
| A case with no `metrics` | `every_case_names_a_metric` |
| A use case no case guards | `every_use_case_has_a_case` |
| A key metric that no case feeds and that links to no computation | `every_metric_has_a_case_or_a_computation` |
| A north star with no case in the core tier | `north_star_has_a_core_case` |
| A guardrail with no `boundary` and no `regression` case | `every_guardrail_has_a_boundary_or_regression_case` |

A floor is written `true` or `false`. Anything else (`1`, `"true"`), or a name that is not one of
the six, fails the gate: the eval runner reads the same file, and the two must never disagree.

A project with no eval suite has no gaps: its documents alone are traced.
