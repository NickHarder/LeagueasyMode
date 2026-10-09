# Handoff: LeagueasyMode

If you are picking this work up, human or model: read this file top to bottom first. The `handoff` skill
refreshes it; it describes the current state.

Last updated: 2026-10-09, on branch `feat/ten-minute-leads` (pull request #49). `main` holds
phases 0 to 8, phase 9 but for 9.4, the Data Dragon growth fix, the plans' approval and
`tuning.json` (pull requests #2 to #48, merged); the estimators' priors in `tuning.json` were
pushed to #48 after it merged and ride with #49.

## Where things stand

The plan is [docs/plans/overlay-and-inference.md](docs/plans/overlay-and-inference.md) (approved by
the owner on 2026-10-08). Phase 0 is done; phase 1, the tracer bullet, is built and waits for the
test on a Mac; phase 2 ([docs/plans/phase-2-exact-facts.md](docs/plans/phase-2-exact-facts.md)) is
built, its structures in phase 8.5. Phases 3 to 7 are built and merged
([phase 3](docs/plans/phase-3-economy-and-open-policy.md), approved;
[phase 4](docs/plans/phase-4-positions.md), [phase 5](docs/plans/phase-5-models.md),
[phase 6](docs/plans/phase-6-post-game.md) and [phase 7](docs/plans/phase-7-packaging.md), built
on their best guesses and approved on 2026-10-09, phase 7 without signing as the owner chose);
phase 5's models are hand-set and phase 6's thresholds empty until 20 recorded games exist. Phase 8
([docs/plans/phase-8-first-test.md](docs/plans/phase-8-first-test.md), approved) goes past the
approved plan: 8.1 to 8.6 (the status page and the report after a test, the overlay over League's
own screen and window, moving the widgets, spoken callouts, structures, the Swift 6 language mode)
are merged (#34 to #39). None waits for the test on a Mac, which confirms them. Phase 8 is built.
Phase 9 ([docs/plans/phase-9-scouting.md](docs/plans/phase-9-scouting.md), approved) reads the
players' past games: 9.1 to 9.3, 9.5 and 9.6 (where the enemy jungler usually starts and is at
4:00, champion pools, the usual start as a prior for the jungle path, scouting scored after the
game) and 9.7 (the 4:00 habit in the positions) are merged (#40 to #45); 9.4 (each player's
creep score and gold at 10:00, which the owner said yes to on 2026-10-09) is built in pull
request #49, after one `tuning.json` for the hand-set thresholds (#48, merged). Each slice goes
up as its own pull request into `main` without waiting for the one before to merge.

| Area | State | Proof |
|---|---|---|
| Scaffold | ai-kit v0.11.1, Python layer, GitHub CI | `.copier-answers.yml` |
| Gate | Green: lint, 839 tests (and 39 in Chromium), secrets | `make gate` |
| Recorder | Records games, the client's patch data and the post-game timeline; anonymized copies | `uv run leagueasymode record`; `tests/test_recorder.py`, `tests/test_anonymize.py` |
| Replay | A recording served as a stand-in game API | `uv run leagueasymode replay <recording>`; `tests/test_replay.py` |
| Engine and overlay page | The dragon and Elder timer, from the game's answer to the page | `uv run leagueasymode run`; `tests/test_tracer_bullet.py` |
| Phase 2 facts | Objective strip, buffs, inhibitors, numbers window, enemy strip, callouts, item catalog and item gold, roles, combat stats | `tests/test_objective_strip.py`, `test_numbers_window.py`, `test_callouts.py`, `test_item_facts.py`, `test_roles.py`, `test_combat_stats.py`; eight browser tests |
| Patch stats | Each patch's champion and item stats from Data Dragon, fetched once a patch and kept on disk; checked against the real 16.20.1 files on 2026-10-09, with the attack damage growth Data Dragon leaves out since 16.5.1 borrowed from 16.4.1 | `tests/test_data_dragon.py` against a stand-in |
| Widgets in a browser | Rendered in Chromium against a replay | `uv run pytest -m browser` (needs Chromium); `tests/test_overlay_page.py` |
| macOS app | Builds on macOS 15 and passes its 58 unit tests in CI; **never run over League** | `overlay/macos/`; CI job `macos-overlay` |
| App bundle | `LeagueasyMode.app` with the engine inside, signed ad hoc, built by CI, its engine started from an empty home folder; **never opened on a Mac by a person** | `overlay/macos/scripts/build_app.sh`; CI job `macos-app`, which keeps the zip with each run |
| CI | 11 jobs, the widgets', the macOS app's and the app bundle's included; none may fail | `.github/workflows/ci.yml` |
| Releases | A tag `v<version>` publishes the zipped app; the app checks for a newer release once a day; **no release published yet** | `.github/workflows/release.yml`; `docs/references/macos-app.md` |
| Real game data | **None yet**: every test uses built payloads in the API's documented shape | `tests/game_payloads.py` |

## How to check your work

```bash
make bootstrap                     # once per clone
make gate                          # everything a push must pass
uv run pytest -m browser           # the overlay page in Chromium (uv run playwright install chromium)
(cd overlay/web && npm ci && npm run build)   # after changing the widgets' TypeScript
(cd overlay/macos && swift build && swift test)   # on a Mac
overlay/macos/scripts/build_app.sh && overlay/macos/scripts/smoke_test_app.sh dist/LeagueasyMode.app   # on a Mac
```

## Rules

In `AGENTS.md`, this project's own included: every session reads that file.

## Open, for the owner

1. **Data Dragon from this environment**: allowed (the owner, 2026-10-08 and 2026-10-09), and
   reachable since 2026-10-09; the parsing is checked against the real 16.20.1 files.
2. **The test on a Mac** in [docs/references/macos-app.md](docs/references/macos-app.md): run the
   app, play a Practice Tool game in each display mode, and record a game or two. The recordings
   (anonymized) become the test data every estimator needs. With 7.2 the app needs no clone: the
   `macos-app` job of a pull request's CI run keeps `LeagueasyMode-<version>.zip` (Apple silicon),
   and the reference says how to open an unsigned app the first time. After the game, "Status…"
   in the menu, then "Copy report", gives a report to paste back: it says what worked and names
   no player.
3. **Compare Riot's root certificate** once with Riot's own `riotgames.pem`: the SHA-256
   fingerprint is in `src/leagueasymode/riot_tls.py`.
4. **The kit's gate skills** (`kickoff`, `audit-codebase`, `define-personas`, `plan-architecture`,
   `define-key-metrics`) have not been run; the approved plan stands in for the plan and the
   architecture. Say whether to run any of them.
5. **Hidden gold's wording and look (3.5)**, on a best guess as with the suggestions: each
   enemy's row says "1.4k ±0.3k unspent" in gold, and the strip's header adds "Gold −1.8k ±0.6k"
   under the item-gold lead. The chance an enemy can afford their next item is worked out
   (`chance_of_affording`) and shows with 3.8's next item ("next Infinity Edge · 2.1k left · 40%
   now", and the callout "Caitlyn can likely buy Infinity Edge"). Hidden experience (3.6)
   adds "6 in ~0:35" on an enemy's row within 1:30 of 6, 11 or 16, and the callout "Zed hits 6
   in ~0:15"; backs (3.7) add "went back 7:42 · returns ~0:24" and, for their jungler only, the
   callout "Vi went back: in the jungle again in ~0:20". The same applies to both.
6. **The minimap layer on the Mac (4.6)**: it is drawn where League's minimap is, from League's
   `game.cfg`, at 22% of the window's height times League's minimap scale; whether that lines up
   with League's own minimap can only be seen on the Mac. Say how far off it is, or send a
   screenshot.
7. **The first release**: when the app has been tried on a Mac, tag `v0.1.0` on `main` and push
   the tag (`docs/references/macos-app.md`, "Releases, updates and opening at login"). Publishing
   is the owner's call; no session tags a release unasked.
8. **Documents waiting for approval** (`make docs-status`): the retrospective, and the references
   on recordings, the engine and the macOS app, all drafts. Every plan is approved (phase 3's on
   2026-10-08, the rest on 2026-10-09).

## Where everything is

- `src/leagueasymode/`: the engine. `recording/` and `recorder.py` record; `replay.py` replays;
  `game_state.py` reads the game's answer; `patch_data.py` and `data_dragon.py` hold the patch's
  items and stats; `inference/` holds the estimators; `engine.py`,
  `overlay_server.py` and `overlay_state.py` serve the overlay.
- `overlay/web/`: the widgets' TypeScript, compiled into `src/leagueasymode/overlay_web/`.
- `overlay/macos/`: the Swift menu bar app.
- `docs/references/`: how recordings, the engine and the macOS app work.
- `docs/plans/overlay-and-inference.md`: the plan; `docs/log.md`: what changed and why.

## Do not commit

In `AGENTS.md`. Also: a raw recording (it holds other players' names); only `anonymize` copies.

## Settled; do not reopen without the owner

- An overlay on the Mac, not a second screen; League's local APIs, plus each patch's champion and
  item stats from Riot's Data Dragon, fetched once a patch and kept on disk (the owner, 2026-10-08:
  "pull the info from an API and then store it and refresh on patches / updates"). The plan, and
  the owner's messages of 2026-10-08.
- This season's spawn times: Voidgrubs 8:00, Herald 15:00, Baron 20:00 (the owner, 2026-10-08).
- Python engine, Swift shell, TypeScript widgets: the plan's recommended stack, approved with it.
- The client's post-game timeline as ground truth for scoring estimators: the plan, approved.
- What may show during a game (the plan's decision 4): everything. The owner, 2026-10-08:
  "everything is allowed. anything we can calculate / estimate / derive / infer / interpolate we
  should if it would be useful". This replaces the plan's policy, which left out enemy ultimate and
  summoner spell timers and instructions to the player. Facts are still tagged exact or estimate,
  so the overlay can say how sure it is.
- `truststore` as a dependency, for HTTPS to Data Dragon (the owner, 2026-10-08).
- Pushing and opening pull requests need no asking; deletions on GitHub and force pushes stay off
  limits (the owner, 2026-10-08; `AGENTS.md`, rule 1).
- Keep building through the plan without waiting for merges: open each slice's pull request into
  `main` as it is ready, assuming the earlier ones will be merged (the owner, 2026-10-08: "keep
  building as well and putting in new mrs even if i havent merged"). A slice built on an unmerged
  one says so in its pull request, and targets `main` all the same.
- The hand-set thresholds are tweaked as games show what they should be, in one file anyone can
  edit: `tuning.json` (the owner, 2026-10-09: "we will tweak as needed. make sure there is an
  easy way to update them"; `docs/references/engine-and-overlay.md`, "Tuning").
- Reading each player's newest five timelines for their numbers at 10:00 (9.4): about 70
  requests a game at most, through the client's own session (the owner, 2026-10-09: "I am fine
  with this if the free developer key can handle this"; no developer key is used, and the pace
  would fit one's limits).

## Known limitations

- Nothing has met a real game: field names, the `KillerName` form, the lockfile path, the
  certificate check and the timeline endpoint are from documentation and libraries, not seen.
- The dragon rules (5:00 first spawn, 5:00 respawn, Elder 6:00 after the soul) are long-standing
  values, not yet checked against a recording of this season.
- The overlay follows League's window (8.2) on the guess that the game's window is owned by
  "League of Legends" and has a title bar when windowed; the test on a Mac confirms both.
- Edit mode (8.3) makes the overlay's panel key so its widgets take drags; that a
  non-activating panel takes them without bringing the app forward is seen on a Mac.
- The test item catalog (`tests/fixtures/client/items.json`) is hand-written: its prices are not
  this patch's, and the "finished item" rule (a full recipe of at least 2000 gold) and the support
  item names are to be checked on a real catalog.
- The role costs are a hand-set prior, not yet fitted on recorded games.
- The suggestions' wording is a first draft, and their thresholds (an objective within 0:30, a
  window of at least 0:20) are hand-set, like every other threshold, in `tuning.json`.
- Loading-screen intel reads the client's ranked stats and match history in the shapes other tools
  describe; no real answer has been seen. If the client does not answer for other players, or
  answers in another shape, the line under each enemy stays empty until the first recording shows
  what to read. The same holds for the past games' timelines that say where a jungler starts
  (9.1, 9.4): the path is the one the post-game timeline uses, and whether the client serves
  other players' games there is first seen in a recording.
- Combat stats leave out runes, passives, stacks and buffs, so an estimate runs low for a champion
  that has them. Data Dragon's item stats leave out some stats (ability haste, lethality, magic
  penetration), which the overlay does not show anyway. The Data Dragon test files are
  hand-written; the reading is checked against the real 16.20.1 files. Data Dragon has given
  every champion an attack damage growth of 0 since 16.5.1, so the engine borrows 16.4.1's; a
  champion released since (Locke) has none, and a growth changed since is a patch behind.
- The Voidgrubs' 14:45 and the Herald's 19:45 leave times follow past seasons and one community
  guide; a recording confirms them.
- The Swift app moved to the Swift 6 language mode (8.6), whose concurrency checks it passes in
  CI; its threads are as before (AppKit's side on the main thread), which the test on a Mac
  confirms at run time.

## History

In `docs/log.md`, newest first.
