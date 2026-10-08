# History

What changed in this project and why, newest first. A commit shows the difference; an entry here
gives the reason. The `handoff` skill adds to it at every checkpoint, and the `write-okf-concept`
skill has the format.

## 2026-10-08

- The tracer bullet's engine side: the dragon and Elder timer, from the game's answer through the
  engine and the local server to the overlay page, tested end to end against a replay and in
  Chromium. `leagueasymode run` and `leagueasymode replay` added;
  [references/engine-and-overlay.md](references/engine-and-overlay.md) describes them.
- Added the recorder (`leagueasymode record`) and anonymized copies (`leagueasymode anonymize`),
  described in [references/recordings.md](references/recordings.md). One change from the plan,
  which said "a standard-library-only recorder": the recorder is the engine's own client code,
  run with `uv run`, because uv sets up its dependencies in the same one command and the recorder
  and the engine then share one tested client of the game's API instead of two.
- Rebuilt from ai-kit v0.11.1 with the Python layer (no evals, demo or MCP layers). The first
  version's Flask HUD, rules and champion files are removed: the approved plan
  ([plans/overlay-and-inference.md](plans/overlay-and-inference.md)) starts the engine over and keeps
  nothing from the old rules by default. Its README is kept word for word as
  [history/first-version-retrospective.md](history/first-version-retrospective.md).
