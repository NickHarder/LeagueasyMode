---
type: Reference
title: The engine and the overlay page
description: How the engine turns the game's answers into the overlay's state, how that state reaches the widgets, how the page is built and tested, and how to run it all against a replay.
tags: [engine, overlay, architecture]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-08T14:20:00Z }
sources:
  - id: engine
    resource: ../../src/leagueasymode/engine.py
  - id: game-state
    resource: ../../src/leagueasymode/game_state.py
  - id: objectives
    resource: ../../src/leagueasymode/inference/objectives.py
  - id: overlay-state
    resource: ../../src/leagueasymode/overlay_state.py
  - id: overlay-server
    resource: ../../src/leagueasymode/overlay_server.py
  - id: replay
    resource: ../../src/leagueasymode/replay.py
  - id: cli
    resource: ../../src/leagueasymode/cli.py
  - id: widgets
    resource: ../../overlay/web/src/overlay.ts
---

# The path of one answer

```
game API ─▶ GameApiClient ─▶ GameSnapshot ─▶ estimators ─▶ OverlayState ─▶ /events (SSE) ─▶ widgets
 (2999)      game_api.py     game_state.py    inference/    overlay_state.py  overlay_server.py  overlay.ts
```

- **`leagueasymode run`** starts the engine and the overlay's local server, records every game
  as `record` does (`LEAGUEASYMODE_RECORD_WHILE_RUNNING`), and prints one line,
  `LEAGUEASYMODE_OVERLAY_URL=http://127.0.0.1:<port>/`, which the macOS app reads to load the
  page.[^cli]
- **The engine** asks the game twice a second, reads the answer into typed models, runs the
  estimators and, when the result differs from the last, hands it to every subscriber. A reader
  that falls behind gets the latest state only.[^engine]
- **The models of Riot's answer ignore fields they do not know**, unlike the project's own
  contracts, which refuse them: Riot adds fields between patches, and refusing one would stop the
  overlay mid-game on a patch day. The recorder keeps every answer whole, so nothing is lost.[^game-state]
- **The overlay's state** (`OverlayState`) is the contract with the widgets. Its JSON Schema is kept
  in `overlay/web/overlay_state.schema.json` beside `overlay/web/src/state.ts`, which mirrors it; a
  test fails when the schema file is out of date.[^overlay-state]

# Estimators so far

| Estimator | Kind | Rules |
|---|---|---|
| Dragon and Elder Dragon timer, each side's dragons, the soul | exact: restates the kill feed and the map | first dragon at 5:00, a dragon respawns 5:00 after it dies, the Elder 6:00 after the soul dragon or the last Elder; the soul at 4 dragons[^objectives] |

The rules are the long-standing ones; each is to be checked against the first recordings.

# The local server

It listens on 127.0.0.1 only, on a free port, and refuses any request whose `Host` is not
`127.0.0.1` or `localhost`, so that a web page elsewhere cannot reach it by pointing a domain at
127.0.0.1. It serves the page (`/`), its script and style, the state as JSON (`/state`) and as
server-sent events (`/events`): the current state at once, then each new one, and a keep-alive
comment every 15 seconds.[^overlay-server]

# The widgets

TypeScript in `overlay/web/src/`, under `strict` and every stricter check TypeScript has,
compiled by `npm run build` (in `overlay/web/`) into `src/leagueasymode/overlay_web/`, so running
the overlay never needs Node; the compiled files are committed and CI checks they are current.
Between two states the countdown moves on from the time the last one arrived, by at most two
seconds, so it ticks smoothly without running down during a pause.[^widgets]

# Working without a game

```bash
uv run leagueasymode replay <recording> --speed 10          # a stand-in game API on 127.0.0.1:2998
LEAGUEASYMODE_GAME_API_BASE_URL=http://127.0.0.1:2998 uv run leagueasymode run
```

Then open the printed address in a browser.[^replay] `uv run pytest -m browser` renders the page in
Chromium against a replay (Chromium from `uv run playwright install chromium`, or
`PLAYWRIGHT_CHROMIUM_EXECUTABLE`); `OVERLAY_SCREENSHOT_DIRECTORY` keeps a screenshot.

[^cli]: `src/leagueasymode/cli.py`
[^engine]: `src/leagueasymode/engine.py`
[^game-state]: `src/leagueasymode/game_state.py`
[^overlay-state]: `src/leagueasymode/overlay_state.py`
[^objectives]: `src/leagueasymode/inference/objectives.py`
[^overlay-server]: `src/leagueasymode/overlay_server.py`
[^widgets]: `overlay/web/src/overlay.ts`
[^replay]: `src/leagueasymode/replay.py`
