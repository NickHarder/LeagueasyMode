---
type: Reference
title: The macOS overlay app
description: What the menu bar app does, how to run it from a clone, and the steps for the tracer bullet's test on a Mac over League in each display mode.
tags: [macos, overlay, tracer-bullet]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-08T14:40:00Z }
sources:
  - id: panel
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/OverlayPanel.swift
  - id: delegate
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/AppDelegate.swift
  - id: hotkey
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/GlobalHotKey.swift
  - id: levels
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/WindowLevelChoice.swift
  - id: engine-command
    resource: ../../overlay/macos/Sources/OverlayCore/EngineCommand.swift
---

# What it is

A menu bar app (no Dock icon) in Swift, in `overlay/macos/`. It starts the engine
(`uv run --project <clone> leagueasymode run`), reads the overlay's address from the line the engine
prints, and shows that page in a window that covers the screen:[^panel]

- transparent, borderless, without a shadow, and with clicks passing through to the game;
- never key or main, and its panel does not activate the app, so League keeps the keyboard;
- on every Space, full-screen ones included, at the "Screen saver" window level by default.

It needs no macOS permission: no Screen Recording, no Accessibility, no Input Monitoring. The
shortcut ⌃⌥⌘L shows and hides the overlay through Carbon's hot keys, which need none.[^hotkey]
Quitting the app asks the engine to stop; the engine closes the game it is recording first.

The menu shows whether the engine runs, toggles the overlay and the click-through, and picks the
window level, since which level stays above League depends on how League draws:[^levels]
Floating, Status bar, Screen saver, and Above a captured display (one above the level a game that
captures the display draws at).

`OverlayCore` holds what the app decides without AppKit (the engine's command and search path,[^engine-command]
reading its output, finding the clone) and has unit tests; CI builds the app and runs them on a
macOS runner. The app is written for Swift 5 with strict concurrency checking as warnings; it moves
to the Swift 6 language mode once CI has compiled it, because nothing here can compile Swift.

# Run it from a clone

Needs the Xcode command line tools (`xcode-select --install`) and uv.

```bash
git clone https://github.com/NickHarder/LeagueasyMode.git && cd LeagueasyMode
git checkout feat/overlay-and-inference
cd overlay/macos && swift run LeagueasyOverlay
```

The engine's log appears in the same terminal. If the app cannot find the clone, set
`LEAGUEASYMODE_REPOSITORY` to its path.

# The tracer bullet's test on a Mac

The question it answers: does macOS let the overlay draw over League cleanly?

1. Start the app as above, then League, then a Practice Tool game.
2. Before 5:00 the overlay shows "Dragon" and a countdown at the top of the screen; kill the
   dragon and it counts down to the next one.
3. For each League display mode (Settings → Video → Window Mode: Full Screen, Borderless,
   Windowed), and for each window level in the menu where the default does not show, note:
   - whether the overlay is visible over the game;
   - whether League keeps the keyboard and mouse (type in chat, cast, click to move through
     the overlay);
   - the frame rate with and without the overlay (Ctrl+F in game);
   - whether ⌃⌥⌘L hides and shows it.
4. Quit the app from the menu. The game's recording is in
   `~/Library/Application Support/LeagueasyMode/recordings/`; run
   `uv run leagueasymode anonymize <recording>` on it.

The first recordings also settle what this project has assumed and not yet seen: the lockfile's
place, that Riot's root certificate verifies both the game and the client, the event names and
whether `KillerName` holds a game name or a Riot ID, and whether the client serves
`/lol-match-history/v1/game-timelines/<game id>`.

[^panel]: `overlay/macos/Sources/LeagueasyOverlay/OverlayPanel.swift`
[^hotkey]: `overlay/macos/Sources/LeagueasyOverlay/GlobalHotKey.swift`
[^levels]: `overlay/macos/Sources/LeagueasyOverlay/WindowLevelChoice.swift`
[^engine-command]: `overlay/macos/Sources/OverlayCore/EngineCommand.swift`
