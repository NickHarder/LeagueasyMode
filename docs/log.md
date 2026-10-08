# History

What changed in this project and why, newest first. A commit shows the difference; an entry here
gives the reason. The `handoff` skill adds to it at every checkpoint, and the `write-okf-concept`
skill has the format.

## 2026-10-08

- Phase 3.1, loading-screen intel: each player's rank, recent record, streak, games on their
  champion and whether they are off-role, from the League client's own lookups, never a developer
  key. Each player is asked about once, one request at a time; the recorder keeps the answers to
  confirm their shapes, and shares them with the engine so the client is not asked twice. The
  replay now serves a recorded path with its query.
- Phase 3's plan approved by the owner, with their answers: the hotkey scheme as proposed,
  suggestions worded by best guess to iterate on, and other players' stats looked up through the
  League client's own session rather than a developer key, to keep clear of rate limits.
- Phase 3 planned in [plans/phase-3-economy-and-open-policy.md](plans/phase-3-economy-and-open-policy.md):
  the hidden economy from the approved plan, plus what the owner's open policy adds (loading-screen
  intel, cooldowns the player marks, suggestions), with the three that help from the first game
  proposed first.
- Pull requests #2, #3 and #4 merged; #3 and #4 went into the branches they were stacked on, so
  pull request #5 brings `feat/exact-facts`, which holds all of them, into `main`.
- The owner's answers: `truststore` stays; Data Dragon may be allowed in this environment's network
  settings; and the plan's decision 4, what may show during a game, is "everything": anything that
  can be calculated, estimated, derived, inferred or interpolated, where it is useful. Enemy
  ultimate and summoner spell timers and instructions to the player are no longer ruled out.
- This season's timers and phase 2.8 pushed and opened as pull request #4, stacked on #3.
- Phase 2.8, estimator 2: each player's combat stats, exact for the player on this machine and
  estimated for the others from their champion, level and items. The owner chose where champion
  base stats come from: Riot's Data Dragon, fetched by the engine once a patch and kept on disk.
  It is the overlay's one request beyond the Mac, said so in the README, and can be turned off.
  The engine now loads the patch's data at every game's start, so a patch day needs no restart.
- This season's spawn times confirmed by the owner: Voidgrubs 8:00, Herald 15:00, Baron 20:00, no
  longer marked "~". The Voidgrubs now leave at 14:45 and an untaken Herald at 19:45, 15 seconds
  before the next monster, as in past seasons; the browser test that showed the Herald up at 23:15
  now shows Baron up instead.
- Phase 2 pushed and opened as pull request #3, stacked on #2 so that its diff shows phase 2 alone.
- Phase 2 stands built but for structures, left out because League's own scoreboard shows tower
  counts and the lane naming is unconfirmed, and combat stats, which wait on the owner's choice of
  a source for champion base stats. The handoff and the phase 2 plan say where each slice is.
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
