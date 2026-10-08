---
name: kickoff
description: Turns a brief, a PRD or a planning conversation into docs/PLAN.md (tracer bullet first, then vertical slices), the gate ladder in docs/METHOD.md and a requirement-coverage table in docs/DELIVERABLES.md. Use when starting a new project or a new phase of work, before any other gate skill and before any code is written.
disable-model-invocation: true
metadata:
  version: "2.0.0"
---

# Kick off a project or a phase

Produce three things, in this order, and write no product code:

1. `docs/PLAN.md`: the plan the owner approves.
2. `docs/METHOD.md`: the gate ladder, adjusted to this project.
3. `docs/DELIVERABLES.md`: every requirement, with where it will be met and how that will be proved.

All three are concepts of the knowledge bundle in `docs/`. `docs/PLAN.md` carries `type: Plan`,
`docs/DELIVERABLES.md` carries `type: Deliverables`, and `docs/METHOD.md` keeps the `type: Method`
it came with. The `write-okf-concept` skill has the rules for the frontmatter, the index and the log.

The brief is the file or text given with this command. If none was given, ask for it. If the brief is a
PDF that cannot be read here, say so and ask for the text; do not plan from a title.

## Step 1: read the brief and list what it requires

Read the whole brief. Extract every requirement, hard gate, deliverable and deadline into a table:

| Id | Requirement (the brief's own words, shortened) | Where in the brief | Due |
|---|---|---|---|

Mark the hard gates (what must exist before something else may start). Convert every relative date to
an absolute date and time zone.

## Step 2: verify the ground

Before planning, check what is actually there, read-only: the repository, the tools on the machine, any
system the brief builds on, the provider and deploy accounts. Record each fact with its evidence
(`path:line`, a command and its output). A fact that changes the plan goes into the plan's Context; a
guess does not go in at all.

## Step 3: ask the owner what is theirs to decide

Stack, deploy target, model choices, budget, what to cut. Ask once, with a recommendation for each.
Record the answers with the date. Do not reopen them later unless the evidence changes.

## Step 4: write `docs/PLAN.md`

Sections, in this order:

1. **Context.** Why this work exists, the deadline, and the verified facts from step 2.
2. **Decisions locked with the owner (date).** A table: decision, choice.
3. **Invariants.** What is never cut, whatever happens to the schedule.
4. **Phases.** See the build-order rules below.
5. **Cut order.** What goes first if time runs short.
6. **Budget.** Dollars per phase for paid model runs; say "$0, no model calls" where that is true.
7. **Verification.** The exact commands that prove the whole thing works (`make gate`, a live check).
8. **Not doing, and why.**

### Build order: tracer bullet, then vertical slices

- **Phase 1 is always the tracer bullet.** Name the one feature, the layers it crosses (input, logic,
  model call, storage, output, one test, one eval case, the gate, CI, and the deploy path if there is
  one), and the single command that proves it works end to end. Keep the feature thin: it exists to
  prove the architecture, not to impress.
- **Every later phase is a vertical slice:** one user-visible capability, with its own test and eval
  case, that leaves the gate green.
- **Reject a plan whose phases are layers.** "Build the data layer", "build the API", "add tests" are
  not phases. If a draft has one, rewrite it as the slices that need that layer.
- A layer is widened only when a slice needs it.

Each phase states: **Files** · **Tests and eval cases** (written first) · **Verify** (exact commands) ·
**Effort** (about how many hours) · **Cost** (dollars) · **Owner gate**, if the owner must act or
approve before the next phase.

## Step 5: adjust `docs/METHOD.md`

Keep the ladder's order. Remove a gate only with a reason written next to it (for example, no existing
system to audit); rename an artifact if the brief names it differently.

## Step 6: write `docs/DELIVERABLES.md`

One row per requirement from step 1:

| Requirement | Status | Where | Proof |
|---|---|---|---|

Status is one of: `Not yet` · `Met` · `Met differently: <why>` · `Owner to do`. At kickoff every row is
`Not yet` or `Owner to do`; "Where" names the phase that will meet it.

## Acceptance

- [ ] Every requirement in the brief has a row in `docs/DELIVERABLES.md` and a phase that meets it
- [ ] Phase 1 is a tracer bullet with a named proving command; no phase is a layer
- [ ] Every phase has tests or eval cases listed before its files, and a dollar cost
- [ ] Deadlines are absolute dates; owner gates are marked
- [ ] No product code was written
- [ ] Both new documents carry their `type`, `make docs-index` was run, and `docs/log.md` has the
      kickoff's entry
