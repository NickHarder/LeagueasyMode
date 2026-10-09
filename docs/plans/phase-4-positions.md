---
type: Plan
title: "Phase 4: where the enemies are"
description: The slices of phase 4 of the approved plan, the map, the clues, the position filter, the jungle path, control wards and the minimap layer, in a proposed build order with what each needs and where the owner decides.
tags: [plan, phase-4, positions]
status: stable
generated: { by: claude-code/cloud, at: 2026-10-08T22:57:15Z }
verified:
  - { by: human:nickharder, at: 2026-10-09T04:38:23Z }
approved_sha256: cd9ba632e4a2be524e4caead9fcbfe4c88687fe719c46f3d742ae8f796b966e3
---

# Phase 4: where the enemies are

Phase 4 of [the approved plan](overlay-and-inference.md) estimates what the game never tells: where
each enemy is. The game's API gives no positions and no visibility, so every estimate is built
from clues in time, the same ones phase 3 reads: deaths and respawns, trips to base, kills at
turrets and monsters, creep score that rises in a lane or in the jungle, and the map's distances.
Each slice goes through every layer, as before, and every fact keeps its tag, exact or estimate.

## Slices, proposed build order

| # | Slice | Shows | Needs |
|---|---|---|---|
| 4.1 | The map | Nothing alone; every later slice walks it, and backs take their way home from it at once | A hand-built graph of Summoner's Rift: about 150 points (fountains, bases, lanes, turrets, camps, river, the two pits) with their game coordinates and regions, joined by walkable edges; travel times by shortest path at a move speed |
| 4.2 | Clues | Each enemy's last pinned place and how long ago ("Zed: at their mid turret 0:40 ago") | Every event that pins a place: a death (the fountain at respawn), a trip to base (the fountain), a kill or assist at a turret, Dragon, Baron or Herald, an inhibitor; creep score rising (a laner in their lane, a jungler at a camp) |
| 4.3 | Positions (estimator 7) | Each enemy's likely region, how sure "missing" is, and the earliest they could reach each lane | A filter per enemy over the map's points: a chance for each (a histogram filter, the exact form of the particle filter the approved plan names, which over 81 points needs no sampling), spread at the enemy's move speed from their latest clue and weighed by their role's habits |
| 4.4 | Jungle path (estimator 8) | The enemy jungler's likely clear, which side they are on, their likely next camp; each camp's respawn | A hidden Markov model over the camps: creep score bursts as evidence, travel times and camp respawns as constraints; since the respawn rule needs the whole path, decoded by a beam search (Viterbi decoding with memory) |
| 4.5 | Control wards (estimator 9) | Likely areas of enemy control wards | The control ward count dropping, at the place 4.3 puts them then |
| 4.6 | The minimap layer | Each enemy's likely region over the map | 4.3; how it is drawn is the owner's choice |

## How each is verified

- **4.1** is checked against the timeline's positions: every minute's position of every player
  must lie within a few hundred units of the map's walkable graph, and a recorded trip home must
  take about the map's travel time.
- **4.2 to 4.5** are scored by the harness against the timeline's positions each minute (mean
  distance, and the share in the estimated region), its kill positions, and its ward events.
- Before recordings exist, each is tested on built games whose truth is known.

## Where the owner decides

Proposed, built on a best guess until the owner says otherwise, as with phase 3's wording:

1. **The minimap layer (4.6).** Proposed: drawn over League's own minimap, placed from League's
   settings file (the minimap's scale and side, `game.cfg`), so each enemy's likely region shows
   where the player already looks; a small map of its own in a corner otherwise.
2. **Dead camp timers (4.4).** The open policy of 2026-10-08 allows them; proposed: shown on the
   minimap layer, each with its "~".
3. **"Missing" callouts (4.3).** Proposed: "Zed missing 0:25: can reach bot in ~0:12", only for
   the enemy most likely to reach the player's lane soon, at most once every 30 seconds.
