# Handoff: LeagueasyMode

If you are picking this work up, human or model: read this file top to bottom first. The `handoff` skill
refreshes it; it describes the current state.

Last updated: not yet (the project was just created from the kit).

## Where things stand

| Area | State | Proof |
|---|---|---|
| Scaffold | Created from the kit | `.copier-answers.yml` |
| Gate | Not run yet | `make gate` |

## How to check your work

```bash
make bootstrap    # once per clone
make gate         # everything a push must pass
```

## Rules

In `AGENTS.md`, this project's own included: every session reads that file.

## Open, for the owner

- Run the `kickoff` skill with the brief to produce `docs/PLAN.md`.

## Where everything is

- `AGENTS.md`: instructions for coding agents (commands, working rules).
- `docs/index.md`: what the project knows, a level at a time; `docs/METHOD.md` is the gates and the
  build order.
- `docs/log.md`: what changed and why, newest first.
- `.claude/skills/`: the skill behind each gate.
- `scripts/gate.sh`: the one definition of what a push must pass.

## Do not commit

In `AGENTS.md`.

## Settled; do not reopen without the owner

Nothing yet.

## Known limitations

Nothing yet.

## History

In `docs/log.md`, newest first.
