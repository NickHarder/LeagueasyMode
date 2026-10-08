---
type: Plan
title: "Phase 2: patch data and exact facts"
description: The slices of phase 2 of the approved plan, in build order, with what each shows, what it needs and the points where the owner decides.
tags: [plan, phase-2]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-08T14:50:00Z }
---

# Phase 2: patch data and exact facts

Phase 2 of [the approved plan](overlay-and-inference.md): every fact the overlay can show without
estimating anything, plus the patch data the later estimators need. Everything here restates the
scoreboard or the kill feed (the policy's "exact"), except role assignment, which is "likely".

Each slice goes through every layer: the fact in the engine with its tests, the overlay contract,
a widget, and a browser test against a replay. The look of every widget is a first draft for the
owner's notes.

## Slices, in build order

| # | Slice | Shows | Needs |
|---|---|---|---|
| 2.1 | Objective strip | Dragon and Elder (built), Baron, Herald, Voidgrubs, each team's Baron and Elder buff time left, inhibitor respawns | The kill feed; a table of this season's spawn times |
| 2.2 | Enemy strip and numbers window | Each enemy's level and death timer; "3 enemies down for 22s" while more of them are dead than of yours | The scoreboard |
| 2.3 | Callouts | Short notices for a moment: a numbers window opening, an enemy reaching level 6, 11 or 16, an objective a minute from spawning | 2.1, 2.2; voice later |
| 2.4 | Patch data | The item catalog (total price, recipe tree, finished or not, stats from the item's text) and the champion summary, from the League client or from a recording | The client's `lol-game-data` resources |
| 2.5 | Item spikes and gold lead | Each enemy's finished items, a callout on a finished item, each team's item gold and the lead | 2.4 |
| 2.6 | Structures | Turrets and inhibitors down per lane, exposed inhibitors | Turret and inhibitor names from the feed |
| 2.7 | Roles (estimator 1) | Each enemy's role in queues that do not assign one | 2.4; Smite, support item, summoner spells, CS pattern |
| 2.8 | Combat stats (estimator 2) | Each player's HP, armor, MR, AD, AP, attack speed, move speed | 2.4 and champion base stats: decision 1 |

The engine also learns to read patch data when it runs against a replay: the replay serves the
recording's client resources beside the game API, so `run` against a replay sees what it saw live.

Housekeeping that rides along: the Swift build's strict-concurrency warnings are cleared, then the
app moves to the Swift 6 language mode.

## Where the owner decides

1. **Champion base stats (needed by 2.8).** The League client's game data has none: its champion
   files hold abilities, roles and art, not health or armor. The choices:
   - a table generated each patch from Riot's public Data Dragon by a CI job, committed, and read
     locally at run time (recommended: the overlay still talks only to League's local APIs);
   - learned from recordings, which knows only the champions the owner plays;
   - no combat stats, and phase 5's fight model goes without them.
2. **This season's objective timers (2.1).** Spawn times have changed season by season. The table
   starts from long-standing values (dragon 5:00, Baron buff 3:00, Elder buff 2:30, inhibitor
   respawn 5:00) and, for the rest, from the first version's code (Voidgrubs 8:00, Herald 15:00,
   Baron 20:00), each marked unverified until a recording or the owner confirms it.
3. **The widgets' look and places**, as each lands.
4. **Pushing this branch**, which stacks on pull request #2.
