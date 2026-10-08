# History

What changed in this project and why, newest first. A commit shows the difference; an entry here
gives the reason. The `handoff` skill adds to it at every checkpoint, and the `write-okf-concept`
skill has the format.

## 2026-10-08

- Phase 2.7, estimator 1: each player's role where the queue gives none, by the assignment of
  least cost over Smite, the support item, summoner spells and CS rank, with a per-player
  confidence. A team-wide margin first made the only Smite user a "guess" when top and mid could
  swap; each player now has their own margin.
- Phases 2.4 and 2.5: the patch's item catalog, from the League client or from a replay that now
  serves the recorded client resources too; each player's item gold and finished items, each
  team's item gold, and a callout when an enemy finishes an item. Items already owned when the
  catalog arrives are not called out, which the first browser run showed was happening.
- Phase 2.3, callouts: short notices when an enemy reaches 6, 11 or 16, a numbers window opens,
  or an objective comes within a minute, each once per game and shown for six game seconds. They
  state facts; the policy keeps instructions out.
- Phase 2.2: each player's card (side, role, level, respawn) and the numbers window, shown as a
  pill at the head of the strip and an enemy strip on the right. The strip is now centered across
  the whole width, where before it was held to half the screen and wrapped its pills.
- Phase 2.1, the objective strip: Baron, Herald and Voidgrubs timers, each team's Baron and Elder
  buff, and inhibitors down, beside the dragon. This season's spawn times are provisional and
  marked so. Also fixed: shutting the server down waited up to 15 seconds for each page still
  listening; the streams now end at once.
- Phase 2's slices planned in [plans/phase-2-exact-facts.md](plans/phase-2-exact-facts.md), on
  `feat/exact-facts`, stacked on pull request #2 while it waits for review.
- Pushed and opened as pull request #2. CI's first run is green on all 10 jobs: the Swift app
  compiled on macOS 15 and its 9 unit tests passed, and the overlay page rendered in Chromium. The
  build's strict-concurrency warnings are noted in `HANDOFF.md` for the move to Swift 6.
- The tracer bullet's macOS side: a menu bar app in Swift (`overlay/macos/`) that starts the engine
  and shows the overlay page in a transparent, click-through window that never takes focus, with a
  ⌃⌥⌘L shortcut and a choice of window level for trying each League display mode. It is written but
  not yet compiled anywhere: this environment has no Swift, so CI's new macOS job is its first
  build. [references/macos-app.md](references/macos-app.md) has the steps for the test on a Mac.
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
