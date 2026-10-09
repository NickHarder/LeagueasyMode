---
type: Plan
title: "Phase 6: the post-game window and accuracy history"
description: The slices of phase 6 of the approved plan, the accuracy history, the accuracy thresholds CI holds, the game reconstructed and the post-game window, in a proposed build order with what each needs and where the owner decides.
tags: [plan, phase-6, post-game]
status: stable
generated: { by: claude-code/cloud, at: 2026-10-09T00:30:00Z }
verified:
  - { by: human:nickharder, at: 2026-10-09T04:38:24Z }
approved_sha256: 873196ee2de0800c1da78b6408c99586f403fa3515584ae0eb14f64498a87e28
---

# Phase 6: the post-game window and accuracy history

Phase 6 of [the approved plan](overlay-and-inference.md) is what the player sees after a game,
and how the estimators are held to account across games. The plan says: a post-game window with
"the game reconstructed, plus how accurate each estimator was"; "the engine stores each
estimator's accuracy per game"; and "CI fails if any estimator drops below its threshold on the
recorded games. The thresholds get set from the first batch of recordings and are never lowered
to make a test pass."

The scoring harness (phase 3.4, extended in every phase since) already scores a recorded game
against its timeline; phase 6 keeps those scores, checks them, and shows them.

## Slices, proposed build order

| # | Slice | Shows | Needs |
|---|---|---|---|
| 6.1 | Accuracy history | `leagueasymode history`: each estimator's last game, its average over the last 10 games, and whether it is getting better or worse | Each game `leagueasymode run` records is scored once its timeline has come, off the engine's loop; `score --keep` scores one by hand. One line a game in `accuracy-history.jsonl` in the application's directory, naming the recording's file, the game's id and version, never a player |
| 6.2 | Thresholds in CI | A failing check when an estimator falls below its threshold on the recordings in the repository | Anonymized recordings in `tests/fixtures/recorded-games/`, each estimator's threshold in `tests/accuracy_thresholds.json`, set from the first batch and never lowered; until then there is nothing to hold |
| 6.3 | The game reconstructed | Nothing alone; 6.4 shows it | From the recording: the result, the win chance each minute, the gold lead each minute estimated and as the timeline has it, the moments that moved the win chance most and what happened then, the kills and objectives, and each estimator's score; served by the engine at `/summary` for the last game recorded |
| 6.4 | The post-game window | The game reconstructed, and the accuracy history over the last games | A page of its own at `/summary.html`, a normal window rather than the click-through overlay; the macOS app's menu gains "Last game…", which opens it |

## How each is verified

- **6.1** on built recordings: the history keeps each game once, reads back what it wrote,
  averages by samples, and names the trend; the engine's step after a recording is tested on
  its own.
- **6.2** by a test that scores every recording in `tests/fixtures/recorded-games/` and fails
  below a threshold; and by a test that every threshold names an estimator the harness scores,
  so that a misspelled one cannot pass unnoticed.
- **6.3** on built recordings whose truth is known.
- **6.4** in Chromium against a built summary, as the overlay's widgets are; the menu item by
  the macOS build in CI.

## Where the owner decides

Proposed, built on a best guess until the owner says otherwise:

1. **When the window opens (6.4).** Proposed: from the menu only, so that nothing opens over the
   client between games; opening it by itself when the timeline arrives is a one-line change.
2. **What counts as a threshold (6.2).** Proposed: the average over the first 20 recorded games,
   less a margin of one standard deviation across them, so that one unlucky game does not fail
   CI.
