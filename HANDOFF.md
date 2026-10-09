# Handoff: LeagueasyMode

If you are picking this work up, human or model: read this file top to bottom first. The `handoff` skill
refreshes it; it describes the current state.

Last updated: 2026-10-09, on branch `feat/status-page`. `main` holds phases 0 to 7 (pull requests
#2 to #33, merged).

## Where things stand

The plan is [docs/plans/overlay-and-inference.md](docs/plans/overlay-and-inference.md) (approved by
the owner on 2026-10-08). Phase 0 is done; phase 1, the tracer bullet, is built and waits for the
test on a Mac; phase 2 ([docs/plans/phase-2-exact-facts.md](docs/plans/phase-2-exact-facts.md)) is
built, its structures in phase 8.5. Phases 3 to 7 are built and merged
([phase 3](docs/plans/phase-3-economy-and-open-policy.md), approved;
[phase 4](docs/plans/phase-4-positions.md), [phase 5](docs/plans/phase-5-models.md),
[phase 6](docs/plans/phase-6-post-game.md) and [phase 7](docs/plans/phase-7-packaging.md), drafts
built on their best guesses, phase 7 without signing as the owner chose); phase 5's models are
hand-set and phase 6's thresholds empty until 20 recorded games exist. Phase 8
([docs/plans/phase-8-first-test.md](docs/plans/phase-8-first-test.md), a draft) goes past the
approved plan: 8.1 to 8.4 (the status page and the report after a test, the overlay over League's
own screen and window, moving the widgets, spoken callouts) are merged (#34 to #37); 8.5,
structures, is on `feat/structures` (#38); 8.6, the Swift 6 language mode, on `feat/swift-6`.
None waits for the test on a Mac, which confirms them. Phase 8 is built. Each slice goes up as its own pull request into `main` without
waiting for the one before to merge.

| Area | State | Proof |
|---|---|---|
| Scaffold | ai-kit v0.11.1, Python layer, GitHub CI | `.copier-answers.yml` |
| Gate | Green: lint, 769 tests (and 38 in Chromium), secrets | `make gate` |
| Recorder | Records games, the client's patch data and the post-game timeline; anonymized copies | `uv run leagueasymode record`; `tests/test_recorder.py`, `tests/test_anonymize.py` |
| Replay | A recording served as a stand-in game API | `uv run leagueasymode replay <recording>`; `tests/test_replay.py` |
| Engine and overlay page | The dragon and Elder timer, from the game's answer to the page | `uv run leagueasymode run`; `tests/test_tracer_bullet.py` |
| Phase 2 facts | Objective strip, buffs, inhibitors, numbers window, enemy strip, callouts, item catalog and item gold, roles, combat stats | `tests/test_objective_strip.py`, `test_numbers_window.py`, `test_callouts.py`, `test_item_facts.py`, `test_roles.py`, `test_combat_stats.py`; eight browser tests |
| Patch stats | Each patch's champion and item stats from Data Dragon, fetched once a patch and kept on disk; **never fetched from the real Data Dragon yet** (this environment cannot reach it) | `tests/test_data_dragon.py` against a stand-in |
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

1. **Data Dragon from this environment**: the owner said yes on 2026-10-08; the environment's
   network settings still deny `ddragon.leagueoflegends.com`. Once it is allowed, a session checks
   the parsing against the real files.
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
6. **Phase 4's plan** ([docs/plans/phase-4-positions.md](docs/plans/phase-4-positions.md)), a
   draft: its order, and its three proposals (the minimap layer drawn over League's own minimap,
   dead camp timers shown, one "missing" callout at a time).
7. **The minimap layer on the Mac (4.6)**: it is drawn where League's minimap is, from League's
   `game.cfg`, at 22% of the window's height times League's minimap scale; whether that lines up
   with League's own minimap can only be seen on the Mac. Say how far off it is, or send a
   screenshot.
8. **Phase 5's plan** ([docs/plans/phase-5-models.md](docs/plans/phase-5-models.md)), a draft:
   its order, and its four proposals (win chance shown with its two reasons, the fight chance's
   wording, contests shown only near a monster, "holding gold" from 1,300).
9. **Phase 6's plan** ([docs/plans/phase-6-post-game.md](docs/plans/phase-6-post-game.md)), a
   draft: its order, and its two proposals (the post-game window opened from the menu only;
   thresholds at the first 20 games' average less a standard deviation).
10. **Phase 7's plan** ([docs/plans/phase-7-packaging.md](docs/plans/phase-7-packaging.md)), a
    draft: its order, and its proposals (the update check on, once a day, off from the menu; the
    eight switches of the settings page).
11. **Phase 8's plan** ([docs/plans/phase-8-first-test.md](docs/plans/phase-8-first-test.md)), a
    draft: its order, what the report holds, and spoken callouts off unless turned on.
12. **The first release**: when the app has been tried on a Mac, tag `v0.1.0` on `main` and push
    the tag (`docs/references/macos-app.md`, "Releases, updates and opening at login"). Publishing
    is the owner's call; no session tags a release unasked.
13. **Documents waiting for approval** (`make docs-status`): the approved plan v2 and phase 2's
   plan, the retrospective, and the references on recordings, the engine and the macOS app, all
   drafts. Phase 3's plan is approved.

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
  window of at least 0:20) are hand-set; the owner tunes both.
- Loading-screen intel reads the client's ranked stats and match history in the shapes other tools
  describe; no real answer has been seen. If the client does not answer for other players, or
  answers in another shape, the line under each enemy stays empty until the first recording shows
  what to read.
- Combat stats leave out runes, passives, stacks and buffs, so an estimate runs low for a champion
  that has them. Data Dragon's item stats leave out some stats (ability haste, lethality, magic
  penetration), which the overlay does not show anyway. The Data Dragon test files are
  hand-written, from memory, not this patch's.
- The Voidgrubs' 14:45 and the Herald's 19:45 leave times follow past seasons and one community
  guide; a recording confirms them.
- The Swift app moved to the Swift 6 language mode (8.6), whose concurrency checks it passes in
  CI; its threads are as before (AppKit's side on the main thread), which the test on a Mac
  confirms at run time.

## History

In `docs/log.md`, newest first.
