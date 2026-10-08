---
type: Plan
title: "Phase 3: the hidden economy, and what the open policy adds"
description: The slices of phase 3 of the approved plan, gold, XP, backs and build paths, plus what the owner's 2026-10-08 answer that everything may show adds, in a proposed build order with what each needs and where the owner decides.
tags: [plan, phase-3, policy]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-08T20:30:50Z }
---

# Phase 3: the hidden economy, and what the open policy adds

Phase 3 of [the approved plan](overlay-and-inference.md) estimates what the scoreboard hides about
money and experience. The owner's answer of 2026-10-08 to the plan's decision 4 widens what may be
built: "everything is allowed. anything we can calculate / estimate / derive / infer / interpolate
we should if it would be useful". So the plan's policy no longer excludes anything; this phase
adds the three things it used to rule out, and one new source.

Each slice goes through every layer, as in [phase 2](phase-2-exact-facts.md): the estimate in the
engine with its tests, the overlay's contract, a widget, and a browser test against a replay.
Every fact keeps its tag, exact or estimate, so the overlay can say how sure it is.

## What the open policy changes

| Was excluded | Now | What limits it |
|---|---|---|
| Enemy summoner spell and ultimate cooldowns | Timers, from a cast **you mark** with a hotkey | The local APIs never report another player's cast; guessing a Flash from movement needs phase 4's positions |
| Instructions to the player | Callouts may suggest an action ("Baron: 3 enemies down for 0:40") | Each suggestion is a rule over facts the overlay already has |
| Dead camp respawn timers | Shown, from phase 4's jungle path | Phase 4 |
| (new) Loading-screen intel | Each player's rank, recent form and games on their champion, from the League client | Which client endpoints answer for other players is checked on a recording |

## Slices, proposed build order

The first three are useful from the first game and need no tuning; the rest need recorded games
to measure, though their structure is built and tested now on built data.

| # | Slice | Shows | Needs |
|---|---|---|---|
| 3.1 | Loading-screen intel | For each player: rank and LP, wins and losses in recent games, games and win rate on this champion, usual role (and "off-role" when this game's differs) | The client's gameflow session (each player's PUUID), ranked stats and match history per PUUID |
| 3.2 | Marked cooldowns | After you mark "their mid used Flash" or "their jungler used ult", the time until it is back | A hotkey scheme in the macOS app; summoner spell cooldowns (Data Dragon `summoner.json`); ultimate cooldowns by rank (Data Dragon `championFull.json`, rank from level 6, 11, 16); haste from items, where the patch data gives it |
| 3.3 | Suggestions | Callouts that name an action when the facts line up: an objective up or soon, a numbers window, buffs, inhibitors down, marked cooldowns | 3.2, phase 2's facts; the owner's wording |
| 3.4 | Scoring harness | Each estimator's error against the post-game timeline, per game and per minute, with a CI check per estimator | Recordings with timelines; thresholds set from the first batch and never lowered to pass |
| 3.5 | Hidden gold (estimator 3) | Each enemy's unspent and total gold with an error band; the chance they can afford their next item | An income model (passive gold, minion gold by time, kill and assist gold with bounties from the feed, objective gold), corrected by purchases at the patch's prices and by thresholds such as the support item's quest; tuned live on your own exact gold |
| 3.6 | Hidden XP (estimator 4) | How far each enemy is to their next level; when they reach 6, 11 and 16 | The same filter for XP; each level-up pins the exact XP at that moment |
| 3.7 | Backs (estimator 6) | "Went back at 7:42", and when they are back in lane | Inventory changes; travel time from the fountain by role |
| 3.8 | Build path (estimator 5) | Each enemy's likely next finished item, and when their gold reaches it | The recipe tree, their components, their champion's class; your games as a prior |

## How each is verified

- **3.1:** the endpoints' shapes and which of them answer for other players are read off the
  first recording; the slice is built against built answers in the documented shape until then.
- **3.2 and 3.3:** exact arithmetic on patch data, tested on built games; the hotkeys are tested
  in the macOS app's unit tests and on the Mac.
- **3.4 to 3.8:** the harness scores each against the timeline. Before recordings exist, each is
  tested on built games whose truth is known; its accuracy is a number only once recordings come.
- **Your own gold and stats** are the live check: the game gives them exactly, so every income or
  stat model is measured on you in every game.

## Where the owner decides

1. **The hotkey scheme for marking cooldowns (3.2).** A proposal: ⌃⌥ and a digit picks an enemy in
   role order (1 top to 5 support), then F marks their Flash, D their other spell, R their ultimate.
   The look and keys are yours.
2. **Suggestions' wording (3.3)**, and whether they are spoken.
3. **Loading-screen intel's reach (3.1).** It asks the League client for other players' ranked
   stats and recent games; the client asks Riot. The answers stay on the Mac and are anonymized out
   of anything committed. Say if any of it should stay off.
4. **The order.** 3.1 to 3.3 first because they help from the first game; say if gold and XP
   should come first instead.

## A risk to the account

Riot's rules for third-party tools forbid some of this, enemy cooldown timers among them. A tool
that only reads the local APIs is unlikely to be noticed, but the risk falls on the owner's
account. It was raised with the owner on 2026-10-08, after the answer above.
