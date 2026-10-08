---
name: write-evals
description: Builds or extends the evaluation suite in evals/ as YAML cases, planned from the north star down through its drivers and guardrails, each case naming the boundary, invariant or regression it guards, the use case or finding it protects and the key metric it feeds, with a core tier that blocks every push and merge. Use when creating or extending evals, when a new vertical slice needs its case, or when a reported bug must become a regression case.
disable-model-invocation: true
metadata:
  version: "2.0.2"
---

# Write the evaluation suite

A suite of happy paths is not an eval suite. Every case names the failure it guards against.

Write the case before the code it tests, run it, and watch it fail. The tracer bullet gets the first
case; each vertical slice after it adds at least one.

## Plan the suite from the north star down

The suite exists to show that the key metrics hold. Read `docs/KEY_METRICS.md` and the metric
concepts in `docs/metrics/` before writing a case, and plan from the top:

1. **The north star** (`NS-01`). Which cases, passing, are the evidence that it holds? Put them in
   the core tier: a change that breaks the north star then never leaves the machine.
2. **Each driver** (`DR-nn`). The cases for what moves it, at every difficulty.
3. **Each guardrail** (`GR-nn`). Its card says what gaming the north star looks like. Write the
   `boundary` case at the edge of that, and a `regression` case for each time it has happened.
4. **Each use case** in `docs/USERS.md` (`UC-nn`), and each finding in `docs/AUDIT.md` that a case
   can guard.

Every case then says two things about itself: `guards`, the use cases or findings it protects, and
`metrics`, the key metrics its verdict feeds. `make trace` prints the chain from the north star down
to the cases and their last verdicts, and lists each gap. An id that is defined nowhere fails the
gate, so a case cannot point at a use case or a metric that does not exist.

## Case YAML schema

One file per case, under `evals/cases/<category>/`:

```yaml
id: G-01
category: grounding
type: invariant               # boundary | invariant | regression
tier: core                    # core | scenario (default); core cases all must pass on every commit
difficulty: straightforward   # straightforward | ambiguous | edge_case
statement: Every figure in the answer is quoted from the source.
failure_mode: The system rounds or invents a number.
input:                        # handed to the system under test as it is
  prompt: What was the March invoice total?
expect:
  contains: ["1,284.50"]
  must_not_contain: ["1,285"]
  refuses: false
  min_length: 1               # vacuity guard: an empty answer must not pass
history:                      # required whenever a core expectation changes
  - {date: 2026-01-15, reason: "tightened after the empty-answer finding", ref: R-06}
guards: [UC-02]               # the use cases or findings this case protects
metrics: [NS-01, DR-02]       # the key metrics this case's verdict feeds
```

The loader rejects a field it does not know, so a typo cannot silently disable a check.

## Rules

- **Types.** `boundary`: an input at the edge of what the system accepts or may answer. `invariant`:
  something that must hold for every answer. `regression`: a bug that happened, pinned so it cannot
  return.
- **Core tier.** A core case is never marked as a known failure and must be checkable from recordings.
  Never change an expected output to make a case pass. A core expectation changes only with a `history`
  entry in the same change, so a reviewer sees the reason next to the diff.
- **Deterministic scorers decide the gate.** A model judge may be reported next to the results; it
  never blocks or passes anything unless the owner asks for that and it has been calibrated against a
  person's labels.
- **Recordings make the gate free.** Model calls are recorded once and replayed (`--mode replay`), so
  the gate costs $0 and needs no network. Recording costs money: say the dollar estimate and get the
  owner's yes first.
- **Every reported bug becomes a case.** Write the `regression` case, confirm it is red, fix the bug,
  confirm it is green.
- **Coverage.** Each category in the plan has cases of every `type`; the summary's coverage matrix
  (category by difficulty) names the empty cells to write next.
- **The trace has floors.** What the trace does not reach yet is a gap. The gate only notes a gap
  until its floor is on, under `trace:` in `evals/thresholds.yaml`. Turn a floor on in the change
  that earns it, with the cases that close its gaps; `evals/thresholds.yaml` says when one may be
  turned off:

  | Floor | What it requires |
  |---|---|
  | `every_case_names_a_use_case_or_finding` | Every case has a `guards`. |
  | `every_case_names_a_metric` | Every case has a `metrics`. |
  | `every_use_case_has_a_case` | Every `UC-nn` is guarded by a case. |
  | `every_metric_has_a_case_or_a_computation` | Every key metric is fed by a case, or links to the computation that measures it. |
  | `north_star_has_a_core_case` | The north star is fed by a case in the core tier. |
  | `every_guardrail_has_a_boundary_or_regression_case` | Every guardrail is fed by a `boundary` or a `regression` case. |

## What the runner produces

`results.json`, `summary.md` and `junit.xml`, each headed by a versions block: the kit version, every
skill's version, and the name, version and content hash of every prompt the cases used. A result
without its prompt version is not a result. The summary opens with the pass rate by metric, the
north star first, and every case in the results carries its `guards` and its `metrics`. The runner exits non-zero when a threshold in
`evals/thresholds.yaml` fails or when a case regresses against `evals/baseline.json`; a change in
wording alone is never a regression.

## Acceptance

- [ ] Every case has `type` and `failure_mode`; every changed core expectation has a `history` entry
- [ ] The core tier passes in replay, in the pre-push gate and in CI
- [ ] `evals/baseline.json` is committed and compared on every run
- [ ] Every case names what it guards and the metric it feeds; the north star has a core case, and
      each guardrail a `boundary` or a `regression` case
- [ ] The results name the prompt versions they were produced with
