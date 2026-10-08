---
type: Plan
title: "Phase 5: models over the whole game"
description: The slices of phase 5 of the approved plan, win chance, fights, objective contests and the You panel, hand-set first and refit on recorded games, in a proposed build order with what each needs and where the owner decides.
tags: [plan, phase-5, models]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-08T23:40:00Z }
---

# Phase 5: models over the whole game

Phase 5 of [the approved plan](overlay-and-inference.md) turns what phases 2 to 4 estimate into
answers about the whole game: who is likely to win, who wins a fight now, whether the enemy can
contest an objective, and what to build. The plan says these "need a few dozen recorded games".
They need them to be **fitted**; they do not need them to be **built**. Each model starts with
hand-set weights, from the game's own numbers and published rates, written down as first guesses
beside the rules of phases 3 and 4. The scoring harness measures each on every recording, and a
refit command fits them once enough recordings exist.

Each slice goes through every layer, as before, and every fact keeps its tag: all of phase 5 is
estimate.

## Slices, proposed build order

| # | Slice | Shows | Needs |
|---|---|---|---|
| 5.1 | Win chance (estimator 12) | "Win ~64%", the two things moving it most ("gold +2.1k", "Baron"), and a line of it over the game | A logistic model over the gold lead as a share of the gold earned, the level lead, turrets, inhibitors down, dragons, the soul, the Baron and Elder buffs, and the players alive, weighed by time. The gold lead is an estimate with a band, so the chance is averaged over that band rather than read at its middle |
| 5.2 | Fights (estimator 10) | "Fight now ~58%": the chance the living players of your team win an even fight; each team's damage, physical against magic | Each team's sustained damage and effective health against the other's damage mix, from the combat stats (estimator 2). By Lanchester's square law the side whose damage times health is greater wins, so the chance is a logistic of the ratio's logarithm |
| 5.3 | Objective contest (estimator 11) | On a monster that is up: "Baron ~0:38 with 4 · they contest ~60%" | The monster's health at this time (Baron 16,300 + 190 a minute from the start in 2026) over your living team's damage against it, against the chance each enemy can reach the pit before it dies (estimator 7's chances over the map, walked at their speed; a dead enemy from the fountain after the respawn) |
| 5.4 | You (estimator 13) | "Armor 1.8× MR against their 70% physical"; how long you have held unspent gold; your creep score a minute against your own recent games | Your exact stats and gold; the enemy's damage mix (5.2); each stat's price from the patch's basic items; your recent games from the League client |
| 5.5 | Refit | Nothing in a game; `leagueasymode fit` prints each model's score before and after, and writes the new weights | Logistic regression (Newton's method, no new dependency) over every recording's moments for 5.1, and its fights for 5.2. It refuses to fit on fewer than 20 games, and keeps the hand-set weights where the fitted ones score no better on held-out games |

## How each is verified

- **5.1** is scored against each game's result, from the client's game details: the Brier score
  over the game's minutes (0.25 is a coin flip; lower is better).
- **5.2** is scored against the fights in the timeline: kills of both teams close in time and
  place, won by the team that loses fewer champions; the Brier score of the chance before each.
- **5.3** is scored against the timeline's epic monster kills: whether the other team's champions
  were at the pit, or took it, against the chance given when the take began.
- **5.4** restates exact numbers through formulas; it is tested on built cases, not scored.
- Before recordings exist, each is tested on built games whose answer is known.

## Where the owner decides

Proposed, built on a best guess until the owner says otherwise, as before:

1. **Win chance on screen (5.1).** Some players play worse watching a falling number. Proposed:
   shown, small, at the head of the enemy strip above the gold leads, with its two reasons; the
   line over the game only in the post-game window (phase 6) at first.
2. **Fight chance wording (5.2).** Proposed: "Fight now ~58% · their damage 70% physical" in
   the enemy strip's header, under the win chance, with "5v4" after the chance when the counts
   differ.
3. **Contest wording (5.3).** Proposed: "Baron ~0:38 with 4 · contest ~60% (Vi)" in the
   objective strip, only while a monster is up or due within 0:30.
4. **The You panel's threshold (5.4).** Proposed: "holding gold" counts from the moment your
   unspent gold passes 1,300 (about a component and a ward) while alive and out of base.
