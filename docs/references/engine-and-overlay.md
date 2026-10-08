---
type: Reference
title: The engine and the overlay page
description: How the engine turns the game's answers into the overlay's state, how that state reaches the widgets, how the page is built and tested, and how to run it all against a replay.
tags: [engine, overlay, architecture]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-08T22:00:20Z }
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
  - id: data-dragon
    resource: ../../src/leagueasymode/data_dragon.py
  - id: combat-stats
    resource: ../../src/leagueasymode/inference/combat_stats.py
  - id: player-intel
    resource: ../../src/leagueasymode/player_intel.py
  - id: intel
    resource: ../../src/leagueasymode/inference/intel.py
  - id: cooldowns
    resource: ../../src/leagueasymode/inference/cooldowns.py
  - id: suggestions
    resource: ../../src/leagueasymode/inference/suggestions.py
  - id: gold
    resource: ../../src/leagueasymode/inference/gold.py
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
| Baron, Rift Herald and Voidgrubs timers | exact | first spawns this season (Voidgrubs 8:00, Herald 15:00, Baron 20:00) confirmed by the owner on 2026-10-08; Baron respawns 6:00 after he dies; the Voidgrubs leave at 14:45 and an untaken Herald at 19:45, 15 seconds before the next monster takes the pit, and the Herald does not return once taken. A rule a new season changes goes back to unverified and its times show with "~" until confirmed[^objectives] |
| Baron and Elder buffs | exact | to the team of the player who took the monster: Baron 3:00, Elder 2:30 |
| Players and death timers | exact | each player's side, role as the game names it, level, and, while dead, when they respawn (`respawnTimer` added to the clock) |
| Numbers window | exact | open while more enemies than allies are dead; it closes at the first respawn after which no more enemies than allies are dead; a death to come cannot be known, so it is never counted |
| Callouts | exact: each states a fact at the moment it becomes true | "Zed is level 6" when an enemy crosses 6, 11 or 16 between two answers (not for levels already reached when the overlay starts); "2 enemies down for 0:24" when a numbers window opens or widens; "Baron in 1:00" (with "~" when the spawn time is provisional) when an objective comes within a minute; each once per game, shown for six game seconds; a clock that runs back more than five seconds starts a new game |
| Item gold, finished items, each team's item gold | exact, at the patch's prices | each player's inventory priced at the catalog's total price (the scoreboard's price for an item the catalog lacks); a finished item is built from parts and into nothing, is not boots or a consumable, and costs at least 2000 gold, a floor to check on real data; a team's item gold is gold earned and spent, not gold in hand |
| Item callouts | exact | "Caitlyn finished Infinity Edge" when a finished item appears in an enemy's inventory between two answers whose items were both known |
| Roles (estimator 1) | given where the game assigns them; otherwise likely or a guess | each player gets a cost for each role from Smite, a support item, the other summoner spells and, after 3:00, the least CS on the team; each team's open roles go to its open players in the assignment of least total cost, found by trying all of them (120 for five); a player's role is "likely" when every assignment that changes it costs at least 2 more, otherwise a "guess". The costs are a hand-set prior, to be fitted on the roles the post-game timeline records |
| Combat stats (estimator 2) | exact for the player on this machine; an estimate for the others | the game gives the player on this machine's stats in full (`activePlayer.championStats`). For the others: the champion's base stats from the patch's Data Dragon files, each grown to the level by the game's formula, base + per-level × (level − 1) × (0.7025 + 0.0175 × (level − 1)), plus each item's stats; bonus attack speed adds up before it multiplies the base, up to 2.5; move speed slows above 415 and 490. Runes, passives, stacks and buffs are not counted, so an estimate runs low for a champion that has them; the recordings, which hold the exact stats of the player on this machine all game, are to measure by how much[^combat-stats] |
| Loading-screen intel (phase 3.1) | exact: restates the League client's answers | each player's solo rank (flex when solo has none); wins and losses over their last 20 games on Summoner's Rift, remakes (under 5:00) left out; the streak from the latest game; games and wins on this game's champion; the position at least 60% of at least five recent games were in, and "off-role" when this game's position, given or likely, differs[^intel] |
| Marked cooldowns (phase 3.2) | estimate | the player marks an enemy's spell from the macOS app (an enemy in role order, then Flash, their other summoner spell, or their ultimate); the timer starts at the game time of the mark and lasts the patch's cooldown, the ultimate's at the rank the enemy's level gives (6, 11, 16), times 100 / (100 + haste), with the ability and summoner spell haste their items' descriptions state. Runes and other haste are not known, so a spell may be back sooner. A callout says when it is back; a new game clears them[^cooldowns] |
| Suggestions (phase 3.3) | a rule over the facts above; first-draft wording | callouts that name an action, made once when their facts line up, never from the first state seen: an objective up or spawning within 0:30 while more enemies than allies are dead for at least 0:20 ("Baron up, 2 enemies down for 0:40: take it"); their jungler dead for at least 0:20 ("take Dragon" when one is up or within a minute, else "invade or push"); a Flash or ultimate just marked ("punish it", "fight now"); a Baron or Elder buff just taken, by who holds it ("group and push", "group and defend", "force a fight", "avoid fights"). Text only[^suggestions] |
| Hidden gold (estimator 3, phase 3.5) | exact for the player on this machine (`activePlayer.currentGold`); an estimate with a band for the others | an income model: 500 to start; passive gold of 2.1 a second from 1:30, 2.3 from 15:00, 2.6 from 25:00 (patch 26.16); each creep at the rate of when it died, about 18.5 gold a lane creep before 15:00, 20.1 to 25:00 and 23.9 after (melee 19, ranged 14, cannons by wave), 22 a point of a jungler's (one with Smite) creep score, unconfirmed; a kill 300 gold up to level 6 and 10 more a level to 420, plus a bounty of a third of the victim's kill and assist gold since their last death less 100 (up to 700, unconfirmed), and half the base shared by the assisters (patch 25.9); turrets 50/25/25 to each of the destroying team and 250/425/375 shared by the champions the feed credits (outer, inner, inhibitor), an inhibitor 50 shared, Baron 300 each, all unconfirmed; the support item's quest at 0.75 gold a second within its stage (World Atlas below 400, Runic Compass below 1200), pinned when it reaches the next. A filter corrects it: total gold is a normal estimate carried forward by that income and widened by how unsure each kind is (12% of creep gold, 25% of kill gold, 30% of objective and quest gold, and 0.15 gold a second unseen, turret plates among it); it is never below what the inventory cost plus what was drunk, placed or lost on a sale (30%); a shopping trip of at least 300 gold, over once nothing is bought for 5 seconds, is a measurement of the inventory's cost plus 300 ± 175 left in hand, weighed against the model as a Kalman filter weighs one. Gold per creep is tuned for your kind (lane or jungle) by the gold your own creeps must have paid, weighed 1 per 1000 of it against the model's 1, between 0.75 and 1.33. The band holds the truth about 4 times in 5 (1.28 standard deviations); each team's total is the sum, its band the bands in quadrature. A clock that runs back starts a new game[^gold] |
| Inhibitors down | exact | back 5:00 after they fall, or when the feed says they respawned; `Barracks_T1_L1` is team 1's top inhibitor (L, C and R taken as top, mid and bottom, to be confirmed) |

Every rule is checked again against the first recordings. The widgets show the dragon always,
and beside it the numbers window while it is open, any other monster up or within 90 seconds of
spawning, each running buff, and each inhibitor down; on the right, each team's item-gold lead
and estimated gold lead ("Gold −1.8k ±0.6k"), and each enemy in role order with their role (in
italics when worked out, with "?" when only a guess), champion, level, item gold and death timer,
and under each the spells marked ("F 4:12", "R 1:05"), their record ("P4 · 3–2 W3 · 3 on champ ·
off-role (MID)"), their health, armor and magic resist ("1.3k HP · 59 AR · 39 MR") and the gold
they hold ("1.4k ±0.3k unspent"; a band under 50 gold is left out).

# Patch data

The patch's item catalog comes from the League client (`/lol-game-data/assets/v1/items.json`),
which the engine asks for when a game starts and keeps; until it has it, the item facts are
absent rather than guessed.[^patch-data] Against a replay, the replay serves the client's recorded
resources too, under their own paths, from the moment of the recording they were received at, so
`LEAGUEASYMODE_LEAGUE_CLIENT_BASE_URL` points the engine at the replay as its client.

The champions' base stats and the items' stats are in no resource of the League client, so they
come from Riot's Data Dragon: each patch's `championFull.json` (base stats and spells), `item.json`
and `summoner.json`, public files that need
no key and no account. When a game starts, the engine asks the client for the game's version
(`/lol-patch/v1/game-version`) and reads that patch's files from disk
(`~/Library/Application Support/LeagueasyMode/patch-data/<version>/`); only a patch not yet there
is fetched, so the overlay reaches the internet once a patch, and only for those three files and
Data Dragon's list of versions. A version that is not a patch number never names a file. Without
the client, Data Dragon's newest patch is used; without Data Dragon, the newest patch on disk
stands in; `LEAGUEASYMODE_DOWNLOAD_PATCH_STATS=False` keeps the engine to what is on disk. HTTPS to
Data Dragon trusts the Mac's own certificate store. The engine loads the patch's data again at
every game's start, so a patch that lands between two games is picked up without a
restart.[^data-dragon]

# Players' records

When a game starts, the engine reads the League client's gameflow session for each player's PUUID
and champion, and asks the client for each player's ranked stats
(`/lol-ranked/v1/ranked-stats/<puuid>`) and last 20 games
(`/lol-match-history/v1/products/lol/<puuid>/matches`). The client asks Riot with its own session,
so no developer key is involved. Each player is asked about once, one request at a time, and kept
for the engine's lifetime; a player the client does not answer for is asked again at the next
game. The answers are matched to the scoreboard by team and champion, through the champion
summary's aliases. The last game's players are forgotten as soon as a new game starts. The shapes
read are the client's as other tools describe them, and the recorder keeps each answer so that the
first recorded game confirms them.[^player-intel]

# The local server

It listens on 127.0.0.1 only, on a free port, and refuses any request whose `Host` is not
`127.0.0.1` or `localhost`, so that a web page elsewhere cannot reach it by pointing a domain at
127.0.0.1. It serves the page (`/`), its script and style, the state as JSON (`/state`) and as
server-sent events (`/events`): the current state at once, then each new one, and a keep-alive
comment every 15 seconds. It takes marks at `POST /marks`, `{"enemy_slot": 1-5, "spell":
"flash" | "summoner" | "ultimate"}`, only with the header `X-LeagueasyMode-Request: mark`, which a
web page elsewhere cannot send without a preflight the server never answers. When the server shuts
down, open streams end at once, so quitting does not wait on a page that is still
listening.[^overlay-server]

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
[^data-dragon]: `src/leagueasymode/data_dragon.py`
[^combat-stats]: `src/leagueasymode/inference/combat_stats.py`
[^player-intel]: `src/leagueasymode/player_intel.py`
[^intel]: `src/leagueasymode/inference/intel.py`
[^cooldowns]: `src/leagueasymode/inference/cooldowns.py`
[^suggestions]: `src/leagueasymode/inference/suggestions.py`
[^gold]: `src/leagueasymode/inference/gold.py`
