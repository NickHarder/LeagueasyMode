---
name: write-okf-concept
description: Writes or changes a document under docs/, the project's knowledge bundle, so that it stays an Open Knowledge Format bundle any tool can read. Every document is a concept whose frontmatter says what it is, who wrote it and where it is in its life, the index files are rewritten from that frontmatter, every link leads somewhere, and docs/log.md says what changed and why. Approval stays with the owner. Use when creating, moving, renaming or editing any file under docs/, or when the gate reports a finding from scripts/okf_bundle.py.
metadata:
  version: "1.8.0"
---

# Write a concept in the knowledge bundle

`docs/` is this project's knowledge, kept as an Open Knowledge Format (OKF 0.2) bundle: a directory
of Markdown files, each opening with YAML frontmatter. The format is small on purpose, so that a
person, an agent or any tool that reads files can use it. `scripts/okf_bundle.py` holds `docs/` to
it, in the gate's lint group and in CI.

One file is one **concept**: one thing worth knowing, such as a plan, a metric or a rule. Its path,
without `.md`, is its name.

## Read a level at a time

Open `docs/index.md` first. It lists each concept of that directory with its title and one sentence
on it, and each subdirectory with what it holds. Open only the concepts the task needs, then follow
their links. Never read the whole of `docs/` into context: the index exists so that you do not have
to.

To look across the whole bundle at once, `make docs-find` lists every concept that matches, one
index line each: `TYPE=Decision`, `STATUS=draft`, `TAG=security`, `TIER=unverified`, alone or
together.

## The rules

The gate fails on any of these, and names the file and the line.

| Rule | What it requires |
|---|---|
| `frontmatter` | The file opens with a `---` line, YAML, and a closing `---` line. |
| `type` | The frontmatter has a `type`: a short piece of text for the kind of thing this is. |
| `title-description` | It has a `title`, and a `description` that is one sentence on one line. |
| `link` | Every link in the body leads to a file that exists. |
| `index` | Every directory has an `index.md` that is exactly what `make docs-index` writes. |
| `log` | Each `##` heading of a `log.md` is a date, as `## 2026-10-04`, and they run newest first. |
| `generated` | It says who wrote the text and when: `generated: { by: <actor>, at: <time> }`. |
| `status` | It has a `status`: `draft`, `stable` or `deprecated`. A `stale_after` is a time. |
| `verified` | Each check on it names who made the check and when. |
| `sources` | Each source has a `resource`, no two share an `id`, and a footnote names a source's `id`. |
| `approval` | A concept that changed after the owner approved it says, in `generated`, who changed it. |
| `trace` | Every id that is named is defined; one north star, which each driver and guardrail supports. |
| `computation` | An attested computation has its whole contract, and an attester in plain Python. |
| `layout` | A concept at the root of `docs/` is named in capitals (`docs/PLAN.md`); any other is in a directory for its kind, named in lowercase words joined by hyphens (`eval-pass-rate.md`) or for its id (`NS-01.md`). A Markdown file outside `docs/` is listed, with who reads it there, in `docs/references/outside-the-bundle.md`. |

`index.md` and `log.md` are reserved names at every level. Never give a concept either name, and
never write an index by hand: `make docs-index` writes every one from the frontmatter.

## Who wrote it, and who approved it

Most of a bundle is written by agents, so every concept says who wrote its text, and the owner's
approval is recorded in it. Both are fields a tool can read.

- **A new concept** starts as `status: draft`, with `generated: { by: <you>, at: <now> }`. You are
  `<producer>/<version>`, such as `claude-code/claude-fable-5-1`. A person is `human:<id>`, and a job
  that runs on its own is `process:<id>`. The time has an offset: `date -u +%Y-%m-%dT%H:%M:%SZ`.
- **A change to an existing concept** updates `generated` to you and now, and leaves its `status`
  as it is. If the owner had approved it, the gate notes that it waits for approval again; say so in
  your report. An approved concept that changed with `generated` left alone fails the gate, whether
  the change is in its body or in a field.
- **Status and approval are two things.** `status` says where a concept is in its life. An approval
  is the owner's record of one exact text. What the kit ships is `stable` and carries no approval.
- **Never write `verified` or `approved_sha256`,** and never set a concept to `stable`. The owner
  approves with `make docs-approve DOC=<file>` and reopens with `make docs-reopen DOC=<file>`. Run
  either only when the owner has said to, in this session, for that document.
- **A fact taken from somewhere** names where: an entry in `sources`, and a footnote on the claim
  that carries the entry's `id`.
- **A concept that describes code** names each file it describes in `sources`, by a path from the
  concept's directory (`../src/<module>/config.py`). When git says one changed after the concept
  was last written, approved or committed, or that it is gone, the gate notes it. Read both, and
  change whichever is wrong in the same change as the other.

`make docs-status` lists where each concept stands: its status, how far it has been checked, whether
the approval still covers the text, and whether it is past its `stale_after`.

## What a concept looks like

```markdown
---
type: Runbook
title: Restore the database from a snapshot
description: The steps to bring the database back from last night's snapshot, and how to check it.
tags: [operations, database]
status: draft
generated: { by: claude-code/claude-fable-5-1, at: 2026-10-04T12:00:00Z }
---

# When to use this

The nightly check in [the monitoring plan](/operations/monitoring.md) reports a failed restore test.
```

[references/frontmatter.md](references/frontmatter.md) has every field, how to choose a `type`, the
two ways to write a link, and the shape of a log entry. Read it before writing a new concept.

## Ids tie the bundle to the eval suite

A use case is `UC-02`, a finding `SEC-01`, a metric `NS-01`, an eval case `G-01`. Each is defined
once: by a heading that starts with it, by a metric's file name, by a case's `id`, or, for a
register that is kept only as a table, by the first cell of its row. It is named wherever something
depends on it. The gate fails on an id that is defined nowhere, so write the id only for a thing
that exists, and define it before you name it.
[references/trace.md](references/trace.md) has the chain, the fields and the floors; read it before
writing a metric, a use case or a finding. `make trace` prints the chain as it stands.

## A number that can be checked

Every number goes into a concept with where it came from: a source, or the computation that
produced it. A number the project measures again and again has its way of being got written down
as a concept of its own, of `type: Attested Computation` under `docs/computations/`: the sanctioned
computation, how to run it, what a run hands back, and the code that checks a run. `make attest`
asks that code whether the receipt of a run backs a number. A number that has a computation is
written only after `make attest` has accepted it, and is never worked out some other way.
[references/attested-computation.md](references/attested-computation.md) has the contract; read it
before writing a computation or stating a measured value.

## Steps

1. **Find where the fact belongs.** Read `docs/index.md`, then the index of the directory that looks
   right. A fact goes into the concept that already covers its subject. Write a new concept only
   when none does, and put it beside the concepts it is most like: in the directory for its kind,
   under a name in lowercase words joined by hyphens. Never write a document outside `docs/`, beside
   the code it is about. [references/frontmatter.md](references/frontmatter.md) has the layout.
2. **Write the frontmatter first:** `type`, `title`, `description`, `status: draft`, and
   `generated` with you and the time. Use a `type` the index already shows before coining a new one.
   The description is what a reader sees before opening the file, so say what the concept is about,
   not that it exists. For a change to an existing concept, update `generated` and leave the rest.
3. **Write the body** with headings, lists and tables rather than long paragraphs. Link to another
   concept wherever this one depends on it.
4. **Run `make docs-index`** after any concept is added, removed, moved, retitled or described anew.
5. **Add to `docs/log.md`:** under today's date, at the top, one line on what changed and why.
6. **Run `make gate-lint`** and fix what it reports. Never change a rule in `scripts/okf/` to make
   a document pass.

## Acceptance

- [ ] The concept has a `type`, a `title` and a one-sentence `description`
- [ ] `generated` names you and the time of this change; you wrote no `verified` and approved nothing
- [ ] Its links lead to files that exist
- [ ] No `index.md` was edited by hand, and `make docs-index` finds nothing left to write
- [ ] `docs/log.md` has a line for the change, under a date heading, newest first
- [ ] `make gate-lint` is green
