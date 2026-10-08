---
type: Reference
title: The engine and the overlay page
description: How the engine turns the game's answers into the overlay's state, how that state reaches the widgets, how the page is built and tested, and how to run it all against a replay.
tags: [engine, overlay, architecture]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-08T16:10:00Z }
sources:
  - id: engine
    resource: ../../src/leagueasymode/engine.py
  - id: game-state
    resource: ../../src/leagueasymode/game_state.py
  - id: objectives
    resource: ../../src/leagueasymode/inference/objectives.py
  - id: players
    resource: ../../src/leagueasymode/inference/players.py
  - id: patch-data
    resource: ../../src/leagueasymode/patch_data.py
  - id: roles
    resource: ../../src/leagueasymode/inference/roles.py
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
  that falls behind gets the latest state only. The callouts are the one part that remembers:
  the engine compares each state with the one before.[^engine]
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
| Baron, Rift Herald and Voidgrubs timers | exact, with this season's spawn times provisional | Baron respawns 6:00 after it dies; first spawns (Voidgrubs 8:00, Herald 15:00, Baron 20:00) from the first version's code, marked unverified and shown with "~"; the Voidgrubs leave when the Herald comes, the Herald does not return once taken |
| Baron and Elder buffs | exact | to the team of the player who took the monster: Baron 3:00, Elder 2:30 |
| Players and death timers | exact | each player's side, role as the game names it, level, and, while dead, when they respawn (`respawnTimer` added to the clock) |
| Numbers window | exact | open while more enemies than allies are dead; it closes at the first respawn after which no more enemies than allies are dead; a death to come cannot be known, so it is never counted |
| Callouts | exact: each states a fact at the moment it becomes true | "Zed is level 6" when an enemy crosses 6, 11 or 16 between two answers (not for levels already reached when the overlay starts); "2 enemies down for 0:24" when a numbers window opens or widens; "Baron in 1:00" (with "~" when the spawn time is provisional) when an objective comes within a minute; each once per game, shown for six game seconds; a clock that runs back more than five seconds starts a new game |
| Item gold, finished items, each team's item gold | exact, at the patch's prices | each player's inventory priced at the catalog's total price (the scoreboard's price for an item the catalog lacks); a finished item is built from parts and into nothing, is not boots or a consumable, and costs at least 2000 gold, a floor to check on real data; a team's item gold is gold earned and spent, not gold in hand |
| Item callouts | exact | "Caitlyn finished Infinity Edge" when a finished item appears in an enemy's inventory between two answers whose items were both known |
| Roles (estimator 1) | given where the game assigns them; otherwise likely or a guess | each player gets a cost for each role from Smite, a support item, the other summoner spells and, after 3:00, the least CS on the team; each team's open roles go to its open players in the assignment of least total cost, found by trying all of them (120 for five); a player's role is "likely" when every assignment that changes it costs at least 2 more, otherwise a "guess". The costs are a hand-set prior, to be fitted on the roles the post-game timeline records |
| Inhibitors down | exact | back 5:00 after they fall, or when the feed says they respawned; `Barracks_T1_L1` is team 1's top inhibitor (L, C and R taken as top, mid and bottom, to be confirmed) |

The long-standing rules are written as verified; the rest are checked against the first
recordings. The widgets show the dragon always, and beside it the numbers window while it is
open, any other monster up or within 90 seconds of spawning, each running buff, and each
inhibitor down; on the right, each team's item-gold lead, and each enemy in role order with their
role (in italics when worked out, with "?" when only a guess), champion, level, item gold and death
timer.

# Patch data

The patch's item catalog comes from the League client (`/lol-game-data/assets/v1/items.json`),
which the engine asks for when a game starts and keeps; until it has it, the item facts are
absent rather than guessed.[^patch-data] Against a replay, the replay serves the client's recorded
resources too, under their own paths, from the moment of the recording they were received at, so
`LEAGUEASYMODE_LEAGUE_CLIENT_BASE_URL` points the engine at the replay as its client.

# The local server

It listens on 127.0.0.1 only, on a free port, and refuses any request whose `Host` is not
`127.0.0.1` or `localhost`, so that a web page elsewhere cannot reach it by pointing a domain at
127.0.0.1. It serves the page (`/`), its script and style, the state as JSON (`/state`) and as
server-sent events (`/events`): the current state at once, then each new one, and a keep-alive
comment every 15 seconds. When the server shuts down, open streams end at once, so quitting does
not wait on a page that is still listening.[^overlay-server]

# The widgets

TypeScript in `overlay/web/src/`, under `strict` and every stricter check TypeScript has,
compiled by `npm run build` (in `overlay/web/`) into `src/leagueasymode/overlay_web/`, so running
the overlay never needs Node; the compiled files are committed and CI checks they are current.
Between two states the countdown moves on from the time the last one arrived, by at most two
seconds, so it ticks smoothly without running down during a pause.[^widgets]

# Working without a game

```bash
uv run leagueasymode replay <recording> --speed 10          # a stand-in game API and client on 127.0.0.1:2998
LEAGUEASYMODE_GAME_API_BASE_URL=http://127.0.0.1:2998 \
LEAGUEASYMODE_LEAGUE_CLIENT_BASE_URL=http://127.0.0.1:2998 uv run leagueasymode run
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
[^patch-data]: `src/leagueasymode/patch_data.py`
