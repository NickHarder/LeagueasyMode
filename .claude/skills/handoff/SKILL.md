---
name: handoff
description: Refreshes HANDOFF.md so the next session, human or model, can pick the work up from the repository alone. Use when a session ends with work in progress, after a checkpoint commit or a release, or when the owner asks where things stand.
metadata:
  version: "2.3.0"
---

# Refresh the handoff

`HANDOFF.md` is the first file a new session reads. Bring it up to date with what is true now. It
describes the current state; `docs/log.md` is the place for what used to be true of the project.
(An eval case keeps the reason for a change to its own expectation in its `history`.)

## Before writing

Check, do not recall:

- `git status`, `git log --oneline -15`, the current branch
- `make gate`, and what it printed
- what is deployed, if anything is, and at which version

## Sections

Keep these headings and their order:

1. **Where things stand.** A table: area, state, proof (a command, a file, a commit). Lead with the
   date and the commit this was written at.
2. **How to check your work.** The commands, starting with `make bootstrap` and `make gate`.
3. **Rules.** One line pointing at `AGENTS.md`. Every rule is written there, this project's own
   included, because every session reads that file and not always this one.
4. **Open, for the owner.** Decisions and actions only the owner can take, most urgent first.
   Name each document that waits for approval: `make docs-status` shows the drafts, and the ones
   changed since they were approved.
5. **Where everything is.** The documents and directories a newcomer needs, one line each.
   `docs/index.md` lists the documents themselves; do not copy its list here.
6. **Do not commit.** One line pointing at `AGENTS.md`, which lists it.
7. **Settled; do not reopen without the owner.** Each decision in a line, with where its reasoning
   lives.
8. **Known limitations.**
9. **History.** One line: "In `docs/log.md`, newest first." The entries go there, not here.

## The log

Add this session's entry to `docs/log.md`: under today's date, at the top, a line or two for each
release or checkpoint, saying what changed and why. The `write-okf-concept` skill has the format.
An entry is never rewritten later; a correction is a new entry.

## Rules

- Every state claim has a proof someone can run or open. If you did not check it this session, say so.
- A durable fact found during the work goes into the document it belongs to (`docs/ARCHITECTURE.md`,
  `docs/KEY_METRICS.md`, `docs/guides/evals.md`), with a pointer here; do not let the handoff become the only
  place it is written.
- No secrets, and no sensitive data.
- Keep it under about 250 lines. Move detail into the document it belongs to and link to it.
- Commit the refreshed file and the log with the work they describe.
