# Handoff: LeagueasyMode

If you are picking this work up, human or model: read this file top to bottom first. The `handoff` skill
refreshes it; it describes the current state.

Last updated: 2026-10-08, on branch `feat/overlay-and-inference`, at the commit that adds the macOS
app (the one after `8c1d2ea`). Nothing is pushed: the repository on GitHub is still archived.

## Where things stand

The plan is [docs/plans/overlay-and-inference.md](docs/plans/overlay-and-inference.md) (approved by
the owner on 2026-10-08). Phase 0 is done here; phase 1, the tracer bullet, is built and waits for
the test on a Mac.

| Area | State | Proof |
|---|---|---|
| Scaffold | ai-kit v0.11.1, Python layer, GitHub CI | `.copier-answers.yml` |
| Gate | Green: lint, 388 tests, secrets | `make gate` |
| Recorder | Records games, the client's patch data and the post-game timeline; anonymized copies | `uv run leagueasymode record`; `tests/test_recorder.py`, `tests/test_anonymize.py` |
| Replay | A recording served as a stand-in game API | `uv run leagueasymode replay <recording>`; `tests/test_replay.py` |
| Engine and overlay page | The dragon and Elder timer, from the game's answer to the page | `uv run leagueasymode run`; `tests/test_tracer_bullet.py` |
| Widgets in a browser | Rendered in Chromium against a replay | `uv run pytest -m browser` (needs Chromium); `tests/test_overlay_page.py` |
| macOS app | Written, **never compiled**: no Swift here | `overlay/macos/`; CI job `macos-overlay` |
| CI | Jobs added for the widgets and the macOS app; **never run** | `.github/workflows/ci.yml` |
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

1. **Unarchive the repository** on GitHub (Settings → General → Danger Zone), then say whether to
   push `feat/overlay-and-inference` and open a pull request. The first CI run is the first time
   the Swift app compiles; expect a fix or two there.
2. **The test on a Mac** in [docs/references/macos-app.md](docs/references/macos-app.md): run the
   app, play a Practice Tool game in each display mode, and record a game or two. The recordings
   (anonymized) become the test data every estimator needs.
3. **Riot's policy**: which estimates may show during a game (plan, decision 4). Riot's pages are
   blocked from this environment unless `developer.riotgames.com` and
   `support-leagueoflegends.riotgames.com` are allowed in its network settings.
4. **Compare Riot's root certificate** once with Riot's own `riotgames.pem`: the SHA-256
   fingerprint is in `src/leagueasymode/riot_tls.py`.
5. **The kit's gate skills** (`kickoff`, `audit-codebase`, `define-personas`, `plan-architecture`,
   `define-key-metrics`) have not been run; the approved plan stands in for the plan and the
   architecture. Say whether to run any of them.
6. **Documents waiting for approval** (`make docs-status`): the plan, the retrospective, and the
   references on recordings, the engine and the macOS app, all drafts.

## Where everything is

- `src/leagueasymode/`: the engine. `recording/` and `recorder.py` record; `replay.py` replays;
  `game_state.py` reads the game's answer; `inference/` holds the estimators; `engine.py`,
  `overlay_server.py` and `overlay_state.py` serve the overlay.
- `overlay/web/`: the widgets' TypeScript, compiled into `src/leagueasymode/overlay_web/`.
- `overlay/macos/`: the Swift menu bar app.
- `docs/references/`: how recordings, the engine and the macOS app work.
- `docs/plans/overlay-and-inference.md`: the plan; `docs/log.md`: what changed and why.

## Do not commit

In `AGENTS.md`. Also: a raw recording (it holds other players' names); only `anonymize` copies.

## Settled; do not reopen without the owner

- An overlay on the Mac, not a second screen; only League's local APIs. The plan, and the owner's
  messages of 2026-10-08.
- Python engine, Swift shell, TypeScript widgets: the plan's recommended stack, approved with it.
- The client's post-game timeline as ground truth for scoring estimators: the plan, approved.
- No enemy ultimate or summoner spell timers, and no instructions to the player: the plan's policy.

## Known limitations

- Nothing has met a real game: field names, the `KillerName` form, the lockfile path, the
  certificate check and the timeline endpoint are from documentation and libraries, not seen.
- The dragon rules (5:00 first spawn, 5:00 respawn, Elder 6:00 after the soul) are long-standing
  values, not yet checked against a recording of this season.
- The overlay covers the main screen only, and the widgets cannot be moved yet.
- The Swift app is in the Swift 5 language mode with strict concurrency as warnings; it moves to
  Swift 6 once CI has compiled it.

## History

In `docs/log.md`, newest first.
