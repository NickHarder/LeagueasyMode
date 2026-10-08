# Attested computations: a number, and proof of how it was got

A source says where a claim came from. An attested computation says how a number is produced, in a
form that lets anyone confirm it was produced that way and not improvised.

## The three parts

| Part | Where | What it is |
|---|---|---|
| The contract | `docs/computations/<name>.md`, `type: Attested Computation` | The computation, its parameters, and the two files below. |
| The executor | `docs/references/executors/<name>.md` | How to run the computation, and the fields of the receipt a run hands back. |
| The attester | `docs/references/attesters/<name>.py` | Code that reads a receipt and returns a verdict. |

A concept that needs the number, such as a metric, links to the contract. One computation can back
several concepts.

## The contract

```markdown
---
type: Attested Computation
title: The eval pass rate
description: The share of eval cases that pass when the suite is replayed from its recordings.
status: draft
generated: { by: claude-code/claude-fable-5-1, at: 2026-10-04T12:00:00Z }
runtime: shell
parameters:
  - { name: tier, type: string, required: true }
executor:
  resource: /references/executors/run-evals.md
  receipt: [arguments, results_file, results_sha256]
attester:
  resource: /references/attesters/eval_results.py
---

# Computation

    my-project-evals --mode replay --tier {tier} --compare-baseline --out evals/out
```

| Field | Required | What it holds |
|---|---|---|
| `runtime` | yes | How the computation is run: `shell`, `python`, `postgres`, `bigquery`. It also says what a parameter means: an argument, a bind variable. |
| `parameters` | no | The named holes a caller may fill, each `{ name, type, required }`. A type is `string`, `integer`, `number` or `boolean`. |
| `computation` | one of the two | A path to the file that holds the computation. |
| A block of code under `# Computation` | one of the two | The computation itself, when it is short. Exactly one block. |
| `executor` | yes | `resource`: the run instructions. `receipt`: the fields a run must hand back. |
| `attester` | yes | `resource`: the code that checks a receipt. |

A caller supplies values for the declared `parameters` and nothing else. Nobody rewrites the
computation to make a run work: a run that needed a different computation is a different number.

## The attester

A Python file with one function:

```python
def attest(
    *,
    computation: str,
    parameters: dict[str, object],
    receipt: dict[str, object],
    claimed_value: object,
) -> dict[str, object]:
    """Return whether the claimed value is the one the sanctioned run produced."""
    ...
    return {"ok": True, "reason": None, "details": {"rows": 12}}
```

That is `attest(*, computation, parameters, receipt, claimed_value)`, returning `ok`, `reason` and
`details`. It checks two things, from the receipt and from what the receipt points at, never from
what anyone says:

1. **Provenance.** What ran is the computation with the parameters filled in. A changed query, an
   added filter or another file fails. Split the computation into words first, then fill each
   parameter into the word that holds its place: a value must never be able to bring an argument of
   its own into the run (`tier=core --tier all`).
2. **Fidelity.** The claimed value is the one the run produced, read again from the run's own output.

An attester imports the standard library and nothing else, and the gate holds it to that: no model
and no service stands behind a verdict, so any reader can run it and get the same one. The gate and
CI hold it to the project's Python rules like any other code: ruff, `mypy --strict` and
`scripts/check_python_rules.py`.

## Using one

```bash
make evals
make attest C=docs/computations/eval-pass-rate.md CLAIMED=1.0 P="tier=core"
```

`make attest` refuses, before it asks the attester:

- a computation that is `deprecated`, or past its `stale_after`;
- a parameter that is not written `name=value`, is given twice, is not declared by the contract, or
  is not of the type the contract gives it;
- a required parameter left out;
- a receipt without a field the contract names.

It prints `attested:` or `refused:` with the reason, and exits 0 or 1. It exits 2, with no verdict,
when the computation breaks a rule of the bundle, the receipt cannot be read, or the attester fails
or raises `SystemExit`. This is the whole list; other documents point here. `RECEIPT=<file>` names a
receipt other than `evals/out/receipt.json`.

In the concept that states the number, write the value, its date, and a link to the computation:

```markdown
Measured 2026-10-04: 1.0 over 2 cases ([the eval pass rate](/computations/eval-pass-rate.md),
`tier=core`, attested).
```

Give a computation a `stale_after` when the number it produces moves. A receipt is the evidence of
one run and is not committed; the contract, the executor and the attester are.

## What this project decided for itself

OKF 0.2 fixes the contract and leaves the shapes of a receipt and of a verdict to a later version.
The receipt as a JSON object, the `attest` function and its three keys are this project's own, and
they change when the format settles them.
