---
type: Rule
title: Python conventions
description: How names, single assignment, types, documentation, data at the boundaries, errors and suppressions are written and checked in this project's Python.
tags: [python, conventions]
status: stable
generated: { by: ai-kit/v0.11.1 }
---
# Python conventions

`make gate` checks most of this (ruff, `mypy --strict`, `scripts/check_python_rules.py`, pytest). The
rest is how code is written here.

## Names say what the thing is

- Use long and descriptive names: `unpaid_invoice_count`, not `n` or `cnt`.
- Include the unit in the name where there is one: `retry_delay_seconds`, not `delay`.
- Do not use an abbreviation a newcomer would have to look up, and give every name at least three
  characters. The exceptions are a one-letter variable of a loop or a comprehension of at most two
  lines, a type variable, and a standard symbol in a formula, which says so on its line:
  `# ai-kit: ignore-name  x and y are the axes`.
- A function is named for what it does (`load_open_orders`), a boolean reads as a question
  (`is_expired`, `has_attachments`), a collection is plural.

## Assign once

- Create a new name for each intermediate value instead of overwriting a variable: `raw_rows`, then
  `valid_rows`, then `rows_by_customer`. Every stage then shows up, by name, in a debugger and in a
  stack trace.
- Never rebind a parameter, and never reuse a name. The exception is a name bound before a loop
  and updated inside it, such as a counter or an accumulator; name it for what it holds. Branches
  that exclude each other (`if` and `else`, `try` and `except`, the arms of a `match`) may each
  bind the name once. A loop variable belongs to its loop, so a later loop may use the name again.
- Never overwrite a loop variable inside its loop (ruff `PLW2901`; `PLR1704` catches a rebound
  argument).
- A module-level constant is annotated `Final`.
- `scripts/check_python_rules.py`, in the gate's lint group, enforces this section and the
  three-character minimum. Where a rebinding is truly needed, say why on the line:
  `# ai-kit: ignore-assign  <why>` (`ignore-final` and `ignore-name` work the same way). A hatch
  with no reason, or one that silences nothing, fails the gate.

## Types

- Annotate every parameter, return value and attribute. `mypy --strict` passes with zero errors; run it
  on the whole project (`make gate-lint`), never on a single file.
- No `Any`, except where a third-party library hands one over; narrow it on the next line.
- Narrow with `isinstance` or a type guard; do not `cast` to quiet the checker.
- Write `list[str] | None`, not `Optional[List[str]]`.

## Documentation

- A Google-style docstring on every module, class, function and method, private ones included: a
  one-sentence summary ending in a period, then `Args:`, `Returns:`, `Raises:` and `Yields:` as they
  apply. Tests are exempt: a test's name says what it checks.
- A comment says why, not what. No commented-out code.
- When behavior changes, its docstring and the document that describes it change in the same commit.

## Data and boundaries

- Pydantic v2 models are the contracts at every boundary (requests, responses, files, settings, model
  output), with `extra="forbid"`. Parse input into a model at the edge; never pass a raw dict between
  modules.
- A new `Settings` field goes into the root `.env.example` in the same commit
  (`tests/test_env_example.py`). Every key and setting lives in the one `.env` at the repository root.
- Async for I/O; no blocking call inside async code.

## Errors and logs

- Catch the narrowest exception you can handle. Never a bare `except:`, and never catch, log and carry
  on. The exception is a loop that must survive one bad item (a worker, a batch): catch the narrowest
  exception there, log the item's identifier, count the failure, and go on to the next item.
- Log identifiers and counts, never values: no secrets, no personal data, no request bodies.

## Suppressions

- Fix a finding rather than silence it. A suppression names its rule and gives its reason on the same
  line: `# noqa: S608  the table name comes from an enum`, `# type: ignore[arg-type]  # <why>`,
  `# ai-kit: ignore-assign  <why>`.
