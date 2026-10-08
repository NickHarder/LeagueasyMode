# The fields of a concept, its links, and the log

## The fields

| Field | Required by | What it holds |
|---|---|---|
| `type` | the format | The kind of thing the concept is. |
| `title` | this project | What the concept is called in an index. |
| `description` | this project | One sentence, on one line, on what the concept is about. |
| `status` | this project | `draft`, `stable` or `deprecated`. An agent writes `draft` on a new concept and leaves the status of an existing one alone. The owner's approval sets `stable`; what the kit ships is `stable` already. |
| `generated` | this project | Who wrote the text as it is, and when: `{ by: <actor>, at: <time> }`. |
| `tags` | nobody | A list of short words that cut across the directories: `[billing, latency]`. |
| `resource` | nobody | The address of the one thing the concept describes, when it describes one: a URL or a path. Leave it out for an idea, a plan or a rule. |
| `sources` | nobody | What the concept was drawn from. See below. |
| `stale_after` | nobody | The time after which the concept should be checked again. For a fact that moves: a measured number, a price, a limit someone else sets. |
| `verified` | never you | The checks on the concept, each `{ by: <actor>, at: <time> }`. `make docs-approve` writes the owner's. |
| `approved_sha256` | never you | A hash of what the owner approved: the body, and every field but `status`, `verified`, `generated` and the hash itself. `make docs-approve` writes it. |

Any other key is allowed, and a tool that rewrites a concept must keep it. Add one when a script of
this project needs a fact it can read without parsing the body.

Quote a value that holds a colon or starts with a bracket: `title: "Method: the gates"`.

## Actors and times

| Who | Written as | Example |
|---|---|---|
| An agent or a tool | `<producer>/<version>` | `claude-code/claude-fable-5-1` |
| A person | `human:<id>` | `human:mlopez` |
| A job that runs on its own | `process:<id>` | `process:nightly-export` |

What the kit rendered into the project says `ai-kit/<version>` and gives no time. Once you change
such a concept, it is yours: write yourself and the time.

A time is ISO 8601 with an offset: `2026-10-04T12:00:00Z`. A date alone is refused, because it names
a different instant in every time zone.

A reader works out how far to trust a concept from `verified`: no check, **unverified**; checks by
tools and jobs only, **machine-confirmed**; a check by a person, **human-reviewed**.

## Sources and footnotes

```markdown
---
type: Metric
title: Checkout completion rate
description: The share of started checkouts that end in a paid order.
status: draft
generated: { by: claude-code/claude-fable-5-1, at: 2026-10-04T12:00:00Z }
sources:
  - id: orders-export
    resource: /data/orders-export.md
    title: The nightly orders export
  - id: pricing-page
    resource: https://example.com/pricing
---

Checkout completion was 61.4% in September.[^orders-export]

[^orders-export]: The nightly orders export
```

- `resource` is required: a URL, a path, or a plain description of what was read ("every order
  placed in September"). One that starts with `/` is a concept of the bundle and must exist.
- A file outside `docs/`, such as the code a concept describes, is a path from the concept's own
  directory (`../src/<module>/config.py`). The gate notes it when git says the file changed after
  the concept was last written, approved or committed, and when the file is gone. A folder is not
  compared: name the files.
- `id` is what a footnote carries. Give one to every source the body cites, and never the same one
  twice. In a concept that has `sources`, every footnote names one of them.
- A number with no source is a guess. Do not write it. A number that has an attested computation
  is attested before it is written ([attested-computation.md](attested-computation.md)).

## Choosing a type

A `type` is what a reader filters and groups by: each index has one heading for each type.

- Use a type the index already shows when the concept is the same kind of thing.
- A skill that produces a document names the type that document carries. Use that one.
- Otherwise coin one: a short noun phrase, capitalised, that a newcomer would understand without a
  glossary. `Runbook`, `Metric`, `Decision`, `API Endpoint`.
- A type says what the concept is, not where it is filed or who wrote it.

Nobody registers types, and a reader must accept one it has never seen.

## Where a concept goes, and what it is called

The gate holds both, as the `layout` rule.

| Where | The file's name | Examples |
|---|---|---|
| The root of `docs/` | Capitals, digits and underscores. Only the few documents a reader starts from: the gate documents | `docs/PLAN.md`, `docs/KEY_METRICS.md` |
| A directory for its kind | Lowercase words joined by hyphens, or the concept's id. The directory is named the same way | `docs/guides/evals.md`, `docs/metrics/NS-01.md` |

Use a directory the index already shows (`metrics/`, `audit/`, `guides/`, `rules/`, `computations/`,
`references/`) before making a new one. A file that is not Markdown, such as an attester, keeps the
name its own tool gives it.

**Nothing a project knows is written outside `docs/`.** A Markdown file anywhere else is there
because a tool reads it at that place, and `docs/references/outside-the-bundle.md` lists each one
with the tool: the README, `AGENTS.md`, `HANDOFF.md`, the prompts. The gate fails on a
Markdown file that is neither a concept nor on that list. Add a line there only when a tool needs
the file where it is, and say in `read_by` which tool. A `README.md` beside a layer points at its
guide under `docs/guides/` and holds nothing a reader would have to find twice.

## Links

A link says that two concepts are related; the sentence around it says how.

| Form | Example | When |
|---|---|---|
| From the bundle's root | `[the checkout rate](/metrics/checkout-rate.md)` | Between concepts in different directories. It stays right when the file that holds it moves. |
| Relative | `[the other runbook](restore.md)` | Between neighbours. |
| Out of the bundle | `[the gate](../scripts/gate.sh)` | To a file of the repository that is not knowledge. Always relative. |

A leading `/` means `docs/`, not the repository. A link to a heading keeps its `#part`. A file name
with a space or a bracket in it goes between angle brackets: `[the plan](<the plan.md>)`.

An example is not a statement, and the gate reads neither its links nor its ids: text between
backticks, in a code fence, in an HTML comment, or on a line indented by four spaces. The last holds
inside a list too, so write a link at the start of a list item's own line, not on an indented line
under it.

## The log

`docs/log.md` is the history of the bundle: what changed and why, which a commit's diff does not
say. Newest first, one `##` heading for each date, one line for each change:

```markdown
# History

## 2026-10-04
* **Update**: moved the retry limit into [the settings](/settings.md); two concepts stated it
  differently.
* **Creation**: [the restore runbook](/operations/restore.md), after the failed restore test.

## 2026-09-30
* **Deprecation**: the weekly export, replaced by [the nightly one](/operations/export.md).
```

- The date is today's, as year-month-day. Add to the heading that is already there for today.
- The first word says what kind of change it was: `Creation`, `Update`, `Deprecation`, or another
  word that fits.
- Say why. "Updated the plan" is what the diff already shows.
- A subdirectory may keep a `log.md` of its own for what happens only there.
