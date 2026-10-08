# Handoff: LeagueasyMode

If you are picking this work up, human or model: read this file top to bottom first. The `handoff` skill
refreshes it; it describes the current state.

Last updated: 2026-10-08, on branch `feat/combat-stats` (local only, not pushed), which stacks
this season's timers and phase 2.8 on `feat/exact-facts` (pull request #3, green), which stacks on
`feat/overlay-and-inference` (pull request #2 into `main`, green).

## Where things stand

The plan is [docs/plans/overlay-and-inference.md](docs/plans/overlay-and-inference.md) (approved by
the owner on 2026-10-08). Phase 0 is done; phase 1, the tracer bullet, is built and waits for the
test on a Mac; phase 2 ([docs/plans/phase-2-exact-facts.md](docs/plans/phase-2-exact-facts.md)) is
built but for structures, left out until the first recordings.

| Area | State | Proof |
|---|---|---|
| Scaffold | ai-kit v0.11.1, Python layer, GitHub CI | `.copier-answers.yml` |
| Gate | Green: lint, 470 tests, secrets | `make gate` |
| Recorder | Records games, the client's patch data and the post-game timeline; anonymized copies | `uv run leagueasymode record`; `tests/test_recorder.py`, `tests/test_anonymize.py` |
| Replay | A recording served as a stand-in game API | `uv run leagueasymode replay <recording>`; `tests/test_replay.py` |
| Engine and overlay page | The dragon and Elder timer, from the game's answer to the page | `uv run leagueasymode run`; `tests/test_tracer_bullet.py` |
| Phase 2 facts | Objective strip, buffs, inhibitors, numbers window, enemy strip, callouts, item catalog and item gold, roles, combat stats | `tests/test_objective_strip.py`, `test_numbers_window.py`, `test_callouts.py`, `test_item_facts.py`, `test_roles.py`, `test_combat_stats.py`; eight browser tests |
| Patch stats | Each patch's champion and item stats from Data Dragon, fetched once a patch and kept on disk; **never fetched from the real Data Dragon yet** (this environment cannot reach it) | `tests/test_data_dragon.py` against a stand-in |
| Widgets in a browser | Rendered in Chromium against a replay | `uv run pytest -m browser` (needs Chromium); `tests/test_overlay_page.py` |
| macOS app | Builds on macOS 15 and passes its 9 unit tests in CI; **never run over League** | `overlay/macos/`; CI job `macos-overlay` |
| CI | All 10 jobs green on pull request #2, the widgets' and the macOS app's included | `.github/workflows/ci.yml`; PR #2's checks |
| Real game data | **None yet**: every test uses built payloads in the API's documented shape | `tests/game_payloads.py` |

## How to check your work

```bash
make bootstrap                     # once per clone
make gate                          # everything a push must pass
uv run pytest -m browser           # the overlay page in Chromium (uv run playwright install chromium)
(cd overlay/web && npm ci && npm run build)   # after changing the widgets' TypeScript
(cd overlay/macos && swift build && swift test)   # on a Mac
```

## Rules

In `AGENTS.md`, this project's own included: every session reads that file.

## Open, for the owner

1. **Review and merge pull request #2** (https://github.com/NickHarder/LeagueasyMode/pull/2), then
   #3 (https://github.com/NickHarder/LeagueasyMode/pull/3), which merges into #2's branch; GitHub
   moves #3 onto `main` when #2's branch is deleted on merge, or change its base by hand. Then say
   whether to push `feat/combat-stats` and open its pull request, stacked on #3.
2. **One new dependency**, in `feat/combat-stats`: `truststore`, so that HTTPS to Data Dragon trusts
   the Mac's own certificates (Python as uv installs it may find none of its own). Say if you would
   rather not have it.
3. **Data Dragon from this environment**: allowing `ddragon.leagueoflegends.com` in its network
   settings would let a session check the parsing against the real files, not only hand-written
   ones.
4. **The test on a Mac** in [docs/references/macos-app.md](docs/references/macos-app.md): run the
   app, play a Practice Tool game in each display mode, and record a game or two. The recordings
   (anonymized) become the test data every estimator needs.
5. **Riot's policy**: which estimates may show during a game (plan, decision 4). Riot's pages are
   blocked from this environment unless `developer.riotgames.com` and
   `support-leagueoflegends.riotgames.com` are allowed in its network settings.
6. **Compare Riot's root certificate** once with Riot's own `riotgames.pem`: the SHA-256
   fingerprint is in `src/leagueasymode/riot_tls.py`.
7. **The kit's gate skills** (`kickoff`, `audit-codebase`, `define-personas`, `plan-architecture`,
   `define-key-metrics`) have not been run; the approved plan stands in for the plan and the
   architecture. Say whether to run any of them.
8. **Documents waiting for approval** (`make docs-status`): both plans, the retrospective, and the
   references on recordings, the engine and the macOS app, all drafts.

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
- No enemy ultimate or summoner spell timers, and no instructions to the player: the plan's policy.

## Known limitations

- Nothing has met a real game: field names, the `KillerName` form, the lockfile path, the
  certificate check and the timeline endpoint are from documentation and libraries, not seen.
- The dragon rules (5:00 first spawn, 5:00 respawn, Elder 6:00 after the soul) are long-standing
  values, not yet checked against a recording of this season.
- The overlay covers the main screen only, and the widgets cannot be moved yet.
- The test item catalog (`tests/fixtures/client/items.json`) is hand-written: its prices are not
  this patch's, and the "finished item" rule (a full recipe of at least 2000 gold) and the support
  item names are to be checked on a real catalog.
- The role costs are a hand-set prior, not yet fitted on recorded games.
- Combat stats leave out runes, passives, stacks and buffs, so an estimate runs low for a champion
  that has them. Data Dragon's item stats leave out some stats (ability haste, lethality, magic
  penetration), which the overlay does not show anyway. The Data Dragon test files are
  hand-written, from memory, not this patch's.
- The Voidgrubs' 14:45 and the Herald's 19:45 leave times follow past seasons and one community
  guide; a recording confirms them.
- The Swift app is in the Swift 5 language mode with strict concurrency as warnings, and CI's build
  shows some (a `@Sendable` closure capturing the engine process, among others); they are to be
  cleared before it moves to the Swift 6 language mode.

## History

In `docs/log.md`, newest first.
