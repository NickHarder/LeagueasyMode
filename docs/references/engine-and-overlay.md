---
type: Reference
title: The engine and the overlay page
description: How the engine turns the game's answers into the overlay's state, how that state reaches the widgets, how the page is built and tested, and how to run it all against a replay.
tags: [engine, overlay, architecture]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-09T04:50:00Z }
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
  - id: experience
    resource: ../../src/leagueasymode/inference/experience.py
  - id: backs
    resource: ../../src/leagueasymode/inference/backs.py
  - id: build-path
    resource: ../../src/leagueasymode/inference/build_path.py
  - id: rift-map
    resource: ../../src/leagueasymode/inference/rift_map.py
  - id: clues
    resource: ../../src/leagueasymode/inference/clues.py
  - id: positions
    resource: ../../src/leagueasymode/inference/positions.py
  - id: jungle-path
    resource: ../../src/leagueasymode/inference/jungle_path.py
  - id: wards
    resource: ../../src/leagueasymode/inference/wards.py
  - id: league-settings
    resource: ../../src/leagueasymode/league_settings.py
  - id: win-chance
    resource: ../../src/leagueasymode/inference/win_chance.py
  - id: fights
    resource: ../../src/leagueasymode/inference/fights.py
  - id: contests
    resource: ../../src/leagueasymode/inference/contests.py
  - id: you
    resource: ../../src/leagueasymode/inference/you.py
  - id: game-summary
    resource: ../../src/leagueasymode/game_summary.py
  - id: preferences
    resource: ../../src/leagueasymode/preferences.py
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
  - id: engine-status
    resource: ../../src/leagueasymode/engine_status.py
  - id: jungle-starts
    resource: ../../src/leagueasymode/jungle_starts.py
  - id: structures
    resource: ../../src/leagueasymode/inference/structures.py
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
| Where the enemy jungler starts (phase 9.1) | exact count of past games: restates where their recent jungle games' timelines placed them | for a likely jungler (at least half of their newest five games, and at least two, in the jungle), the side of their own jungle each of those games found them on at 2:00 (the timeline's frame nearest it, within 0:30): blue buff's half or red buff's; anywhere else counts for neither. The row says "starts red (top) 3/4": the side more games started on, the half of the map that side is for their team this game (the blue team's blue buff is in its top jungle, the red team's in its bottom), and the count. A callout before the camps spawn at 1:30, "Vi usually starts red, top side (3 of 4)", when at least 70% of at least two games started there[^jungle-starts] |
| Champion pools (phase 9.3) | exact: counts the League client's match history | how many champions a player's recent games were on; "main" when this game's champion was played more than any other, in at least three of them; "one-trick" when at least 70% of at least eight were on it. The row says "3 on champ (main)" or "14 on champ (one-trick)"; an enemy one-trick is called out before the camps spawn at 1:30, "Zed is a one-trick (14 of 20 games)"[^intel] |
| Where the enemy jungler is at 4:00 (phase 9.2) | exact count of past games: restates the same timelines | from the same games, the half of the whole map each placed them on at 4:00 (the frame nearest it, within 0:30), when a first clear is done: the lanes, the river and both jungles on one side of the mid lane count for that side, named for the buff of theirs in it; the mid lane is mid; the bases count for neither. The row adds "4:00 bot 3/4": the half more games found them on, turned into top or bot for their team this game. A callout from 2:45 to 3:30, "Vi is usually bot side at 4:00 (3 of 4)", on the same 70% of at least two games[^jungle-starts] |
| Marked cooldowns (phase 3.2) | estimate | the player marks an enemy's spell from the macOS app (an enemy in role order, then Flash, their other summoner spell, or their ultimate); the timer starts at the game time of the mark and lasts the patch's cooldown, the ultimate's at the rank the enemy's level gives (6, 11, 16), times 100 / (100 + haste), with the ability and summoner spell haste their items' descriptions state. Runes and other haste are not known, so a spell may be back sooner. A callout says when it is back; a new game clears them[^cooldowns] |
| Suggestions (phase 3.3) | a rule over the facts above; first-draft wording | callouts that name an action, made once when their facts line up, never from the first state seen: an objective up or spawning within 0:30 while more enemies than allies are dead for at least 0:20 ("Baron up, 2 enemies down for 0:40: take it"); their jungler dead for at least 0:20 ("take Dragon" when one is up or within a minute, else "invade or push"); a Flash or ultimate just marked ("punish it", "fight now"); a Baron or Elder buff just taken, by who holds it ("group and push", "group and defend", "force a fight", "avoid fights"). Text only[^suggestions] |
| Hidden gold (estimator 3, phase 3.5) | exact for the player on this machine (`activePlayer.currentGold`); an estimate with a band for the others | an income model: 500 to start; passive gold of 2.1 a second from 1:30, 2.3 from 15:00, 2.6 from 25:00 (patch 26.16); each creep at the rate of when it died, about 18.5 gold a lane creep before 15:00, 20.1 to 25:00 and 23.9 after (melee 19, ranged 14, cannons by wave), 22 a point of a jungler's (one with Smite) creep score, unconfirmed; a kill 300 gold up to level 6 and 10 more a level to 420, plus a bounty of a third of the victim's kill and assist gold since their last death less 100 (up to 700, unconfirmed), and half the base shared by the assisters (patch 25.9); turrets 50/25/25 to each of the destroying team and 250/425/375 shared by the champions the feed credits (outer, inner, inhibitor), an inhibitor 50 shared, Baron 300 each, all unconfirmed; the support item's quest at 0.75 gold a second within its stage (World Atlas below 400, Runic Compass below 1200), pinned when it reaches the next. A filter corrects it: total gold is a normal estimate carried forward by that income and widened by how unsure each kind is (12% of creep gold, 25% of kill gold, 30% of objective and quest gold, and 0.15 gold a second unseen, turret plates among it); it is never below what the inventory cost plus what was drunk, placed or lost on a sale (30%); a shopping trip of at least 300 gold, over once nothing is bought for 5 seconds, is a measurement of the inventory's cost plus 300 ± 175 left in hand, weighed against the model as a Kalman filter weighs one. Gold per creep is tuned for your kind (lane or jungle) by the gold your own creeps must have paid, weighed 1 per 1000 of it against the model's 1, between 0.75 and 1.33. The band holds the truth about 4 times in 5 (1.28 standard deviations); each team's total is the sum, its band the bands in quadrature. A clock that runs back starts a new game[^gold] |
| Hidden experience (estimator 4, phase 3.6) | an estimate for every player, yours included: the game gives levels, not experience | a level takes 280 experience at 2 and 100 more at each level after (18,360 by 18). A level-up seen pins a player's experience at what the level takes; between level-ups it grows at their own rate while they are alive, never leaving the level the scoreboard gives. Each level-up seen after another measures a rate (the experience between them over the time alive between them), weighed 0.6 against the rate before. Until one is seen, a prior by role from 1:30: 8.5 a second for a solo laner, 6 for a duo laner, 8 for a jungler, a first guess. A player first seen above level 1 is at the prior's estimate when it falls inside their level, else halfway through it, with the spread of a value anywhere in the level. The band adds 30% of the prior's growth (20% of a measured rate's); a power level's time (6, 11, 16) starts when a dead player respawns. Kill experience and time in base are in the measured rate, on average. A callout "Zed hits 6 in ~0:15" comes when an enemy is estimated within 0:20 of 6, 11 or 16 and that time is sure to within 0:20[^experience] |
| Build path (estimator 5, phase 3.8) | estimate | every finished Summoner's Rift item in the store a player does not own is a candidate, unless it is boots, for another champion, or made by an ally. Each scores 3 × the share of its price the components held already pay (walking its recipe down: a component held counts at its price, one not held is looked into), plus 2 × the share of the player's recent games on this champion that ended with it (half the share over their other games when they have none on it), plus 1 × how many of its stat categories suit the champion's main class (0.7) and second (0.3), from Data Dragon's tags; the weights and the class's categories are a first guess. The best is the next item, its likelihood its share of exp(3 × score) over all. What is left to pay is its price less the components held toward it; the gold estimate gives the chance they hold that much now and, at their income so far, when they will. A callout says when an enemy becomes likely (75%) to afford it ("Caitlyn can likely buy Infinity Edge"): their next trip to base brings it[^build-path] |
| Backs (estimator 6, phase 3.7) | inferred; the way back an estimate | buying needs the fountain, so a purchase made alive is a trip to base: not one before 1:30, nor one while dead or within 0:30 of respawning, and purchases within 0:30 of a trip's first belong to it. The way back is 5 seconds of shopping, then the walk along the map from the fountain to where they play (their lane's outer turret, or their red buff for a jungler) at the player's move speed: the game's own for you, the combat stats estimate for the others, 380 without the patch's stats. A callout says when the enemy jungler, whom the map rarely shows, has gone back ("Vi went back: in the jungle again in ~0:20"), not for a trip made before the overlay starts[^backs] |
| The map (phase 4.1) | a hand-built model of the Rift | 81 walkable points in the game's coordinates (fountains, bases, every lane's turrets, every camp, the river, the scuttle crabs, both pits) in regions (each lane, each team's jungle above and below mid, each side of the river, each base), joined by paths a champion can walk; the blue half is written down and the red half is its turn about the center. Walks are shortest paths along straight segments (Dijkstra), so a little short of a real path around the walls. The coordinates are from memory, to within a few hundred units; the harness measures how far the timeline's positions lie from the paths[^rift-map] |
| Clues to positions (phase 4.2) | inferred | the moments a player's place is pinned: the killer and assisters of a turret or inhibitor at it, of Dragon at its pit, of Baron, the Herald or the Voidgrubs (`HordeKill`, to confirm) at Baron's; a champion a turret kills at that turret; a respawn, or a trip to base's shopping, in base; creep score rising, a laner in their lane (at its outer turret, for the map) or a jungler in a jungle (theirs or, invading, the other's: the score cannot tell). A kill between champions names no place and is no clue here. Each enemy's row shows the latest for two minutes, unless they are dead ("at Dragon 0:40 ago")[^clues] |
| Positions (estimator 7, phase 4.3) | estimate | a chance for each of the map's points (a histogram filter, the exact form of the particle filter the plan names). From a player's latest clue (a point, or a lane's or a jungle's points), they can be at any point they could have walked to since at their move speed for 80% of the time; each is weighed by how much a player of their role is found in its region (a laner's lane 1.0, the river beside it 0.3, their own jungle behind it 0.15 to 0.2; a jungler's own jungle 1.0, the river 0.5, the other jungle 0.3; anything else 0.05, the bases less), a first guess to fit on the timeline's positions. Without a clue they start in their fountain at 0:00. Out of it: the three likeliest regions in words from your side ("their top jungle"), the chance they are away from where they play, the time unseen, and the soonest they could be in the middle of each lane (the walk at full speed less the time since). An enemy unseen 0:10 shows "likely bot lane 60% · unseen 0:25". The callout "Zed missing 0:25: can reach mid in ~0:12" names the enemy unseen 0:20 or more, likely (50%) away, who could reach your lane soonest within 0:20; one at a time, at most once every 0:30. Each card now says whether it is you (`is_you`). From 3:00 to 5:00, a jungler whose past games say where they usually are at 4:00 (phase 9.2) has each half of the map weighed by three times their share of games there, a game added to each half (3 of 4 on one half gives it 12/7, an even record 1 each), so the "missing" callouts and the minimap lean the way they usually go (phase 9.7)[^positions] |
| Jungle path (estimator 8, phase 4.4) | estimate | each jungler's (the player in the jungle role) creep score rises in bursts, rises within 6 seconds being one camp finished at the last. Which camp each burst was is decoded from what fits: a camp is up at its first spawn (1:30; the scuttle crabs 3:30) and its respawn after its last clear (buffs 5:00, other camps 2:15, the scuttles 2:30), all unconfirmed this season; between two camps the jungler walks the map at their move speed and takes the camp's clear time (8 to 12 seconds, a first guess). The likeliest path wastes the least time between camps (a unit of log chance for each 20 seconds) and stays in their own jungle (a camp of the other's is 0.3 as likely); a burst nothing could have finished costs 5 units more. The respawn rule needs the whole path, so the decoding keeps the 40 best paths with their history (a beam search, Viterbi with memory); a burst under way waits until it is over. Out of it: the last three camps, the next camp (the one of their own they could start soonest) and when, and each camp cleared that is not back yet. The enemy jungler's row shows "path their red → their krugs · next their raptors ~0:15", and the strip "Camps: their krugs 1:10 · their red 3:40" (the four soonest back). One burst alone cannot tell a camp from another that fits as well, such as the two buffs at 1:42; the next bursts settle it. When their past games say where they usually start (phase 9.1), the first camp, when finished by 2:00 (so not the first one an overlay started later sees), also weighs the log of twice their share of starts on its side of their jungle, with a game added on each side (3 red of 4 gives red 4/6), so an even record weighs nothing; since a red-side clear and its blue-side mirror fit the bursts about as well, a habit can turn the whole early path. Post-game scoring decodes the same way, and scores each habit against the game's own start and 4:00 (phase 9.6)[^jungle-path] |
| Control wards (estimator 9, phase 4.5) | estimate | a player's count of control wards dropping while alive is a placement, at that moment; where is the position estimate's likeliest region then, with its chance. One control ward per player is down at a time, so a new one replaces their last; a ward's destruction is never seen, so each shows until its owner places another, or for five minutes. The strip shows the enemies' latest three: "Wards: Vi likely top river 60% · 2:10 ago"[^wards] |
| The minimap layer (phase 4.6) | draws the estimates above | `leagueasymode run` reads League's own settings file once (`game.cfg`, in League's `Config` folder; `LEAGUEASYMODE_LEAGUE_GAME_CONFIG` for another place): the minimap's scale and whether it is flipped to the left. The layer sits in that corner, sized 22% of the window's height times the scale (a first guess, to check against League's minimap on the Mac), and draws each living enemy's likeliest region (a circle, larger and darker with its chance, and the champion's first three letters), each camp down with the time until it is back, and each enemy control ward. A settings file that is missing or cannot be read leaves a scale of 1 on the right[^league-settings] |
| Fights (estimator 10, phase 5.2) | estimate | an even fight now: every living player of both teams at full health, all at once. Each player's damage a second, from their combat stats: auto attacks, attack damage times attack speed, physical; abilities, 4 a level plus 0.4 of ability power and 0.2 of attack damage, magic in the share Riot rates the champion (Data Dragon's `info`, magic over attack and magic; half when unrated). Each player's effective health is their health over the share of the other team's damage mix that gets through their armor and magic resist (100 / (100 + resistance)). By Lanchester's square law the side whose damage times health is greater wins; the chance is a logistic of 2 × the logarithm of the ratio, so 5 against 4 alike is about 71%. Runes, penetration, shields, heals, crowd control, range and cooldowns are left out; the weights are first guesses, to refit on recorded fights (phase 5.5). The strip's header shows "Fight now ~71% 5v4 · their damage 70% physical", the counts only when they differ[^fights] |
| Objective contests (estimator 11, phase 5.3) | estimate | for Dragon, the Elder Dragon and Baron, once up or within 0:30 of spawning: how long your living team takes to kill it, and the chance the enemy reaches its pit first. The monster's health (2026, from patch 26.1's notes, unconfirmed): Baron 16,300 + 190 a minute from the start, armor 34, magic resist 32; the Elder 11,500 + 290 a minute after 25:00, 34 and 32; a drake 3,625 + 375 a level of the champions' average level (6 to 18), 21 and 30; less a Smite when an ally has one (600; 1,000 from 12:00, taken as upgraded). Over the team's damage a second (estimator 10) through its armor and magic resist. A living enemy's chance to arrive is the share of the position filter's chance (estimator 7) on points within that time of the pit at their full speed, counting the wait for the spawn; a dead one arrives once respawned and walked from their fountain. The enemy contests when any one arrives: 1 less the product of each one's chance of not. The objective strip shows "Baron ~0:38 with 4 · contest ~60% (Vi)", naming the likeliest from 20%[^contests] |
| You (estimator 13, phase 5.4) | exact numbers through formulas | from your own stats and gold, which the game gives in full. What to build: for armor, magic resist and health, the effective health a hundred gold of it buys now, against the enemy's damage mix (estimator 10, the dead counted too); effective health is health over the share of their damage that gets through, so its rise per point is exact (armor: health × physical share × (100 / (100 + armor))² / 100 over the share taken, squared). Each stat's price is the patch's basic item for it (Cloth Armor, Null-Magic Mantle, Ruby Crystal: the client's price over Data Dragon's amount), else 20, 18 and 2.67 gold a point. Holding gold: how long your unspent gold has stayed at 1,300 or more while alive (a first guess), shown from 0:30. Creep score a minute from 3:00, against yours over your recent Summoner's Rift games (the client's match history: minions and monsters over the games' minutes). A panel on the left shows "HP 1.7× Armor · their damage 88% physical", "1.5k held 2:10" and "CS 7.2/min · your usual 6.4"[^you] |
| Win chance (estimator 12, phase 5.1) | estimate | a logistic model from your side: the log-odds of a win add 10 per unit of the gold lead over what a team has earned on average (at least 12,500, so that an early kill is not a won game), 0.3 per level of lead per player, 0.1 per turret (theirs down less yours, from the feed), 0.4 per inhibitor down, 0.1 per dragon, 0.5 for the soul, 0.7 for a Baron buff running and 1.0 for an Elder's (minus the same for theirs), 0.6 per player alive of lead at 30:00 (less before, up to 0.9 after 45:00), and 0.05 for the blue side. A medium gold lead at 15:00 (2.5k) is set to win about 3 in 4 and a large one (5k) about 9 in 10, as seasons 7 to 10 did. The gold lead is the team gold estimate, with its band; the item gold lead stands in while it is unknown. The chance is averaged over the gold lead's band (the probit approximation), so an unsure lead counts for less. All weights are first guesses, to refit on recorded games (phase 5.5). The strip's header shows "Win ~64% · gold +2.1k, Baron": the two things moving it most, from your side[^win-chance] |
| Inhibitors down | exact | back 5:00 after they fall, or when the feed says they respawned; `Barracks_T1_L1` is team 1's top inhibitor (L, C and R taken as top, mid and bottom, to be confirmed) |
| Structures (phase 8.5) | exact | each side's outer, inner and inhibitor turrets down per lane, from the feed's turret names (`Turret_T2_R_01_A`: team 2's bottom inhibitor turret, the names the gold and the clues read, to be confirmed), and whether each inhibitor is open: its turret down and it standing. The nexus turrets are left out, since the feed does not say whether they come back. The strip shows "Enemy turrets bot 3, inhib open" and "Your turrets mid 1"; an inhibitor opening is called out once a game ("Enemy bot inhibitor is open")[^structures] |

The win chance's weights and the fights' steepness can be refit on recorded games
(`leagueasymode fit`, in [recordings](recordings.md)); `leagueasymode run` reads the weights kept
from `model-weights.json` at its start, and uses the hand-set ones without it.

Every rule is checked again against the first recordings. The widgets show the dragon always,
and beside it the numbers window while it is open, any other monster up or within 90 seconds of
spawning, each running buff, each inhibitor down, each side's turrets down by lane, and for Dragon, the Elder or Baron up or
within 0:30, how long your team takes and the chance of a contest; on the right, each team's item-gold lead
and estimated gold lead ("Gold −1.8k ±0.6k") under the win chance ("Win ~64% · gold +2.1k, Baron") and an even fight's ("Fight now ~71% 5v4 · their damage 70% physical"), the camps down with their respawns, the enemies' control wards likely
down, and each enemy
in role order with their role (in
italics when worked out, with "?" when only a guess), champion, level, item gold and death timer,
and under each the spells marked ("F 4:12", "R 1:05"), their record ("P4 · 3–2 W3 · 3 on champ ·
off-role (MID)"), their health, armor and magic resist ("1.3k HP · 59 AR · 39 MR"), when they
reach their next power level once it is within 1:30 ("6 in ~0:35"), their last trip to base for
1:30 after it ("went back 7:42 · returns ~0:24"), the latest clue to where they are for 2:00
after it ("at Dragon 0:40 ago"), where they likely are once unseen for 0:10 ("likely bot lane 60%
· unseen 0:25"), their likely next item ("next Infinity Edge ·
2.1k left · 40% now", with "?" when less likely than not, in the enemy color from 75%), and the
gold they hold ("1.4k ±0.3k unspent"; a band under 50 gold is left out).

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
restart. Since 16.5.1, Data Dragon gives every champion an attack damage growth of 0, while the
game's own data still has it (Ahri's 3 a level, checked on 16.20.1): a patch without any growth
takes each champion's from the newest older patch that has it (16.4.1), found by halving the
older patches' `champion.json` (eight requests once a patch) and kept beside the patch as
`attack-damage-growth-<version>.json`. A champion newer than that patch keeps 0. The status page
says when the growth is borrowed.[^data-dragon]

# Players' records

When a game starts, the engine reads the League client's gameflow session for each player's PUUID
and champion, and asks the client for each player's ranked stats
(`/lol-ranked/v1/ranked-stats/<puuid>`) and last 20 games
(`/lol-match-history/v1/products/lol/<puuid>/matches`), and for a likely jungler the timelines
of up to five of their recent jungle games (`/lol-match-history/v1/game-timelines/<gameId>`).
The client asks Riot with its own session, so no developer key is involved. Each player is asked about once, one request at a time, and kept
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
listening.[^overlay-server] It also serves the last game's summary (`/summary`, 404 until a game
is recorded) and the accuracy history (`/history`, `{"games": [...]}`), for the post-game window.

# After a game

Once `leagueasymode run` has recorded a game and its timeline has come, the game is scored, its
scores are added to the accuracy history, and its summary is written to `last-game.json` in the
application's directory (`LEAGUEASYMODE_LAST_GAME_SUMMARY` moves it), all off the engine's loop.
The summary is the game reconstructed: the result, your champion and the game's length; your
team's win chance at the start of each minute; the gold lead each minute as the overlay estimated
it and as the timeline has it; the feed's kills, monsters, turrets and inhibitors in words from
your side ("Zed killed Ahri", "your team took their top outer turret"); the three minutes that
moved the win chance most, with what happened in each; and every estimator's score. Its contract
is `overlay/web/game_summary.schema.json`, kept current by a test.[^game-summary]

# Settings

`/settings.html` (`overlay/web/src/settings.ts`), opened by the macOS app's "Settings…", has a
switch for each part of the overlay: the win chance, the fight chance, the objective contests,
the You panel, the minimap layer, the enemy estimates (unspent gold, next item, last back, clues,
likely places, camps down and wards), callouts, and suggestions; and one to speak each new
callout as it shows, in macOS's voice. Everything shows by default, and nothing is spoken until
that switch is turned on; the exact facts of the enemy strip (levels, death timers, items, stats)
always show. A change is sent
with `PUT /preferences`, only with the header `X-LeagueasyMode-Request: preferences`, which a page
elsewhere cannot send; the engine sends it with its next state, so the overlay changes at once,
and keeps it in `preferences.json` in the application's directory (`LEAGUEASYMODE_PREFERENCES`
moves it). A file that cannot be read leaves everything showing.[^preferences]

Where the player moved the widgets (the macOS app's "Edit layout") travels the same way: each
movable widget's offset from its usual place, as shares of the overlay's width and height, sent
with `PUT /layout` only with the header `X-LeagueasyMode-Request: layout`, sent back with every
state, and kept in `layout.json` (`LEAGUEASYMODE_LAYOUT` moves it). A file that cannot be read
puts every widget in its usual place.

The engine's own settings come from the repository's `.env` in a clone. An installed app, which
has no clone, reads `settings.env` in the application's directory instead; where both exist, the
repository's wins, and a real environment variable wins over either.

# Status, and the report after a test

`/status.html` (`overlay/web/src/status.ts`), opened by the macOS app's "Status…", shows what the
engine sees, part by part, each with its state written out (OK, Waiting, Problem, Off) and a
sentence saying why:[^engine-status]

- **The game:** answering (its mode, map, clock and player count), loading, nothing listening, or
  a problem: an HTTP error, an answer that is not JSON, or a certificate Riot's root does not
  verify, with the reason the check gave. An answer whose fields cannot be read is a problem too,
  and each field is listed by its place in the answer (`allPlayers.3.scores.kills: int_parsing`),
  never by its value.
- **The League client, patch stats, player lookups:** found or not when the game started, the
  game's version and the number of items, the patch loaded, how many players were looked up.
- **Recording, match timeline, after the game:** the file being written, the timeline saved or
  not come in time, the game scored.
- **League's settings and the models:** `game.cfg` read or not, hand-set or refit weights.

It also lists each kind of event in the game's feed, marking those no estimator reads, which is
how an event new this patch shows. "Copy report" copies all of it as text, to paste into a message
after a test. Neither the page nor the report names a player, and a path starts at `~`. The page
asks `/status` every two seconds while it is open; its contract is
`overlay/web/engine_status.schema.json`, kept current by a test.

# The post-game window

`/summary.html`, a page of its own (`overlay/web/src/summary.ts`), opened by the macOS app's
"Last game…" in a normal window. It reads `/summary` and `/history` once and shows the result
("Victory", your champion and the game's length); your win chance each minute as a line, the
three biggest swings marked on it; the gold lead each minute, the overlay's estimate against the
timeline's, with a legend and labels at the lines' ends; the three swings with what happened in
each; the game's moments, a dot for whose good each was; and each estimator's score this game,
its average over the last ten games in the history, and a sparkline of them. Each chart has a
crosshair whose readout lists every line at the minute under the pointer, the same with the arrow
keys once focused, and a table of its values beneath. Light or dark with the system; the two
series colors pass every colorblindness and contrast check in both. Before any game it says so.

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
[^experience]: `src/leagueasymode/inference/experience.py`
[^backs]: `src/leagueasymode/inference/backs.py`
[^build-path]: `src/leagueasymode/inference/build_path.py`
[^rift-map]: `src/leagueasymode/inference/rift_map.py`
[^clues]: `src/leagueasymode/inference/clues.py`
[^positions]: `src/leagueasymode/inference/positions.py`
[^jungle-path]: `src/leagueasymode/inference/jungle_path.py`
[^wards]: `src/leagueasymode/inference/wards.py`
[^league-settings]: `src/leagueasymode/league_settings.py`
[^win-chance]: `src/leagueasymode/inference/win_chance.py`
[^fights]: `src/leagueasymode/inference/fights.py`
[^contests]: `src/leagueasymode/inference/contests.py`
[^you]: `src/leagueasymode/inference/you.py`
[^game-summary]: `src/leagueasymode/game_summary.py`
[^preferences]: `src/leagueasymode/preferences.py`
[^engine-status]: `src/leagueasymode/engine_status.py`
[^jungle-starts]: `src/leagueasymode/jungle_starts.py`
[^structures]: `src/leagueasymode/inference/structures.py`
