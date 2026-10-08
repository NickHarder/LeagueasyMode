---
name: define-key-metrics
description: Writes each key metric as a concept under docs/metrics/ that a skeptical executive could audit, and docs/KEY_METRICS.md as the list of them, with one north star, three to four drivers and two to three guardrails, each with a real data source. Use when docs/ARCHITECTURE.md exists and it is known what the system can measure.
disable-model-invocation: true
metadata:
  version: "3.1.1"
---

# Define key metrics

Produce `docs/KEY_METRICS.md` and one concept for each metric under `docs/metrics/`. Choosing
metrics is a business exercise: a small set that proves the promise made to the primary persona in
`docs/USERS.md`.

`docs/KEY_METRICS.md` is the overview and carries `type: Key Metrics`. Each metric is a concept of its
own that carries `type: Metric`, and its file name is its id: `docs/metrics/NS-01.md` for the north
star, `DR-01.md`, `DR-02.md` and so on for the drivers, `GR-01.md` and so on for the guardrails. The
`write-okf-concept` skill has the rules for the frontmatter, the index and the log.

## Where a metric sits in the trace

Three fields in a metric's frontmatter say where it sits. `make trace` prints the tree they make, and
the gate reads them:

| Field | Holds | Example |
|---|---|---|
| `role` | `north-star`, `driver` or `guardrail` | `role: driver` |
| `supports` | On a driver or a guardrail: the north star's id | `supports: NS-01` |
| `proves` | The use cases whose promise the metric proves | `proves: [UC-01, UC-03]` |

There is one north star, and every driver and every guardrail supports it. An id that is defined
nowhere fails the gate, and so does a second north star. Eval cases name the metric they feed by the
same id (`metrics: [DR-01]`), which is how a verdict reaches the north star.

## Metric card (every field mandatory)

The card is the body of the metric's concept. Its name is the concept's `title`.

- Name
- The promise it proves (the `docs/USERS.md` use case ids, which also go in `proves`)
- Exact definition and formula
- Unit and aggregation window
- Data source, and where it is computed (a trace attribute, a metrics series, the eval runner, a table)
- Target, and the reasoning behind it
- What gaming it looks like, and the guardrail against that
- What decision changes when it moves

## Rubric

- One north star
- Three to four drivers
- Two to three guardrails
- No metric without a source that already exists: a table, a log, an eval result, a panel
- A reviewer could audit each one from the dashboard, not from a slide

State the unit and hold it. A rate over items and a rate over requests are different metrics: for k
items a request they are related by `1-(1-p)^k`, and a band written for one is wrong for the other by
an order of magnitude. Band the quantity you can act on.

## Sections of `docs/KEY_METRICS.md`

1. North star · 2. Drivers · 3. Guardrails: under each, one line for each metric, a link to its
concept with its id and its name · 4. Considered and rejected, with reasons (raw request counts,
uninstrumented satisfaction, token counts as a product metric) · 5. Dashboard and alert mapping (which
panel and which alert carries each metric).

Above each card, in the metric's own concept, keep a dated line with the current measured value once
there is one. A number comes from a measured run; never write a placeholder as if it were a result.

## A measured value is attested

The way a metric is measured is a concept of its own: `type: Attested Computation`, under
`docs/computations/`, with the exact query or command, how to run it, and the code that checks a
run. The metric links to it. Write a value into a metric only after `make attest` has accepted
exactly that value, and put the date, the parameters and the link on the same line:

```markdown
Measured 2026-10-04: 1.0 over 2 cases ([the eval pass rate](/computations/eval-pass-rate.md),
`tier=core metric=NS-01`, attested).
```

A project with the eval suite ships one computation, the eval pass rate, which measures any metric
the eval cases feed. For a metric measured elsewhere (a trace attribute, a table, a dashboard), write
its computation and its attester first; the `write-okf-concept` skill has the contract. A metric with
neither an eval case nor a computation is a gap that `make trace` lists.

Then go back to `docs/USERS.md`: each use case names "the metric that proves it worked". Put the
metric's id there, and update that document's `generated`.

## Acceptance

- [ ] Every card is complete
- [ ] The north star and the guardrails appear in a dashboard or an alert
- [ ] Use cases are referenced by id
- [ ] Every number is measured, with its date
- [ ] The document carries `type: Key Metrics`, `make docs-index` was run, and `docs/log.md` has
      its entry
- [ ] Each metric is a concept under `docs/metrics/`, named by its id, with its `role`; each driver
      and each guardrail names the north star in `supports`
- [ ] `make trace` prints the north star with every driver and guardrail under it
- [ ] Every measured value was accepted by `make attest`, and its line links the computation
