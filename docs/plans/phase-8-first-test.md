---
type: Plan
title: "Phase 8: ready for the first test, and what v2 still promises"
description: The slices after the approved plan's seven phases, a status page that turns the first test on a Mac into a report, then what the plan's picture of the overlay promised and phases 1 to 7 left out (moving the widgets, spoken callouts, League's own screen and window, structures), in a proposed build order with where the owner decides.
tags: [plan, phase-8, first-test]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-09T02:05:00Z }
---

# Phase 8: ready for the first test, and what v2 still promises

[The approved plan](overlay-and-inference.md) ends at phase 7, and all seven are built. Two things
remain. First, nothing has met a real game yet. The owner, 2026-10-09: "keep building, whats
next after phase 7. i might do a test later tonight". Second, the plan's picture of the overlay,
"What you'd see", promises a few things that no phase built.

## Slices, proposed build order

| # | Slice | Shows | Why now |
|---|---|---|---|
| 8.1 | Status and the test report | "Status…" in the menu opens a page with what the engine sees, part by part: the game's API (answering, loading, refused, or its certificate refused), the League client, the patch's stats, the player lookups, the recording, the match timeline, the scoring after the game, League's settings file, the models. It also lists every feed event name seen, marking those no estimator reads, and every field of the game's answer that could not be read. "Copy report" copies it as text without any player's name, to paste into a message | Nothing has met a real game: the field names, the lockfile, the certificate check, the event names and the timeline endpoint come from documentation. A test that half works still says exactly what to fix |
| 8.2 | Moving the widgets | "Edit layout" in the menu makes the overlay take clicks: each widget can be dragged, and "Reset layout" puts them back. The places are kept with the settings | The plan: "You move the widgets around after switching on edit mode from the menu bar" |
| 8.3 | Spoken callouts | A switch in the settings, off unless turned on: each new callout is spoken by macOS's own voice | The plan: "Callouts: short facts, with optional voice" |
| 8.4 | League's screen and window | The overlay covers the screen League is on, not only the main one. In windowed mode it fits League's window, which also lines up the minimap layer | The overlay covers the main screen only (a known limitation) |
| 8.5 | Structures (2.6) | Turrets and inhibitors down per lane, and inhibitors exposed | Left out of phase 2 until a recording shows the turret names; it waits for the first recordings |
| 8.6 | The Swift 6 language mode | The app moves to Swift 6 with no concurrency warnings | A known limitation; it waits until the test on a Mac has run, so a change to the app does not land between two tests |

## How each is verified

- **8.1:** by the engine's tests: each part's state after the game's API answers, refuses, loads or sends an answer that cannot be read; the client, the patch, the recording, the timeline and the scoring, each found and not found. Chromium checks the page, the report it copies, and that no player's name is in either.
- **8.2:** in Chromium: dragging a widget in edit mode moves it, and its place is kept and served back; outside edit mode nothing moves. The app's switch between taking and passing clicks has a unit test.
- **8.3:** in Chromium: a new callout is handed to the app's voice once, and only with the switch on. The app's side is tried on a Mac.
- **8.4:** by unit tests of choosing the screen and the frame from League's window bounds. The window itself is tried on a Mac.
- **8.5:** against the first anonymized recordings.

## Where the owner decides

1. **What the report holds (8.1).** Proposed: each part's state, the event names, the unreadable fields, the game's version, macOS's and Python's versions. Never a player's name, a Riot ID, the client's password, or the home folder's name; paths start at `~`.
2. **Voice (8.3).** Proposed: off unless turned on, in the system's default voice.
3. **The order.** 8.1 is proposed first, for the test tonight; 8.5 and 8.6 wait for the test.
