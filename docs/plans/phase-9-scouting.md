---
type: Plan
title: "Phase 9: scouting from the players' past games"
description: What the players' past games can say before and early in this one, starting with where the enemy jungler usually starts, read from the timelines of their recent jungle games through the League client, in a proposed build order with what each needs and where the owner decides.
tags: [plan, phase-9, scouting]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-09T03:05:00Z }
---

# Phase 9: scouting from the players' past games

Phase 8 left only work that waits on the test on a Mac, on recordings, or on the owner. The
owner, 2026-10-09: "what are we waiting on? we cant proceed without manula tests?". The players'
past games are one thing that needs none of these. The League client already answers each
player's last 20 games (phase 3.1), and it serves each past game's timeline the same way it serves
the post-game one (phase 3.4). The owner's policy covers this: "anything we can calculate /
estimate / derive / inferset / interpolate we should if it would be useful". Player lookups go
through the client's own session, "just not with a dev key".

## Slices, proposed build order

| # | Slice | Shows | Needs |
|---|---|---|---|
| 9.1 | Where the enemy jungler starts | For a likely jungler (at least half of their newest five games, and at least two, in the jungle), the side of their jungle each of those games found them on at 2:00: blue buff's or red buff's half. Their row says "starts red (top) 3/4", with the half of the map that is for their team this game. Before the camps spawn, a callout: "Vi usually starts red, top side (3 of 4)" | Up to five more requests per likely jungler, one at a time; the timeline's shape, which the recorder keeps |
| 9.2 | Where they go after the first clear | From the same timelines: the half of the map the jungler was on at 3:00 and 4:00 (top, mid or bot side), so the row and a callout before 3:00 can say "Vi's first gank: bot 3 of 4". It also makes a prior for the jungle path (estimator 8) in the first minutes | Nothing new to ask: the timelines 9.1 reads |
| 9.3 | Champion pools | For each enemy: how many different champions their last 20 games were on, and whether this game's is their most played ("one-trick", "comfort pick", "first time") | Nothing new to ask: the match history 3.1 reads |
| 9.4 | Early leads in lane | For each enemy laner: their creep score and gold at 10:00 in their recent games in this position, from the same timelines, beside your own pace in the You panel | A timeline for each laner's recent games: up to five requests per player, fifty a game. Proposed only once 9.1's requests are seen to be fine |

## How each is verified

- **9.1:** the engine's tests: which side a position at 2:00 falls on, for both teams; which
  players count as likely junglers and which of their games are read; the count, the callout and
  its thresholds. The recorder keeps each timeline read. A Chromium test shows the row. Whether the
  client serves other players' past timelines at this path, and in this shape, is seen in the
  first recording.
- **9.2 to 9.4:** the same way, on the same built timelines and match history, then on the first
  recordings.

## Where the owner decides

1. **The thresholds (9.1).** Proposed: a likely jungler is one with at least half of their newest
   five games, and at least two, in the jungle. The callout needs at least 70% of at least two
   games on one side. The row shows the count whatever it is, so a 2/2 says how little it rests on.
2. **The requests (9.1, 9.4).** Proposed: five timelines at most per likely jungler, one at a
   time with the usual pause, once per player for the engine's lifetime. 9.4 would ask for about
   ten times as many and waits for the owner's word.
3. **The order.** 9.1 first, then 9.2 and 9.3, which ask for nothing new.
