---
type: Plan
title: "Phase 10: testing on the Mac without the back and forth"
description: A review of the first tests over real games on the owner's Mac and of what made each round slow, and a proposed build order for what removes the owner from the loop, versions told apart, the engine's log kept, a one-click problem report, a tutorial, builds that install themselves, and what is the owner's call.
tags: [plan, phase-10, field-testing]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-28T20:30:00Z }
---

# Phase 10: testing on the Mac without the back and forth

The owner, 2026-10-28, after the first evening of tests over real games: "can you do a review and
try to figure out some next steps and QoL improvements rather then having this back and forth
constantly", naming a version on show, a tutorial for the shortcuts, "a snap shot way to upload
issues for you easily" for debugging, and recordings sent with "less human in the loop".

## What the first tests showed

Over four tries the overlay went from showing nothing to showing over the game, and each round
found a real fault: an invisible layer that caught the mouse, a panel that held the keyboard, a
minimap circle for an enemy in sight, and an engine that stopped with "exit 1" after an ARAM game.
Each is fixed or reported in pull requests #50 to #53. What made the rounds slow was rarely the
fault itself:

| Step of each round | Who | Cost |
|---|---|---|
| Describe what happened, in words, sometimes screenshots | owner | the most: guesses on both sides |
| Merge the pull requests | owner | four waiting now; stacked ones conflict in the docs |
| Find the build: a test branch, a CI run, a 14-day download | both | a new link each time |
| Download, unzip, replace the app, "Open Anyway" | owner | every build |
| Tell which build is running | nobody can | every build is "0.1.0" |
| Know why the engine stopped | nobody can | its output goes nowhere when the app is opened from Finder |
| Get the recordings | owner, then automatic | done by #52 once a token is set up; #53 adds those a crash cut short |

## Slices, proposed build order

| # | Slice | What changes for the owner |
|---|---|---|
| 10.1 | Versions told apart | Each build is `0.1.0 (build 62, b0d63a8)`: CI's run number and the commit. The menu's first line, the status page, the report, each crash report and each sent game carry it, so "which build was that" is never asked again |
| 10.2 | The engine's log kept | The app writes the engine's output to `~/Library/Logs/LeagueasyMode/engine.log` instead of dropping it, the last three runs kept; "Open engine log" in the menu. A stop like "exit 1" then has its reason on disk |
| 10.3 | Report a problem | One menu item, and ⌃⌥⌘R, sends a snapshot to the private repository's `reports/`: the build, the menu's lines (engine, overlay, League's window, keyboard), the status page's report, the crash reports, the end of the engine's log with every player's name removed, the last two minutes of the game's recording anonymized, and a line of the owner's words if they type one. The app sends it itself, so it works when the engine has stopped. The menu says "Report sent"; the owner's message is then just "sent a report" |
| 10.4 | How to use | A page, opened once on the first start and from the menu ("How to use…"): each shortcut in Mac and Windows-keyboard names (Ctrl + Alt + Windows + L), each widget and minimap mark with what it means and how sure it is, the menu items, and what to do when the mouse or keyboard acts up |
| 10.5 | Off the Rift | On a map other than Summoner's Rift (ARAM, its Mayhem, Arena) the Rift's widgets hide: the dragon and objective timers, the jungle, the minimap layer. The enemy list, gold, items, fights and win chance stay |
| 10.6 | Builds that come to the app | Each merge to `main` publishes a build as a prerelease. The app's daily update check (7.3) gains "Install update": it downloads the build, replaces itself and starts again. A file the app downloads itself is not marked as from the internet, so no "Open Anyway" either; that is checked on the Mac |
| 10.7 | No wait on merges | Each of Claude's pull requests merges by itself once CI is green (GitHub's auto-merge). The owner can still hold or revert one |
| 10.8 | Games read without being asked | A scheduled cloud session, daily, reads what arrived in the private repository (games, crash reports, problem reports), scores the games, and opens pull requests for what they show, or says in one line that nothing new came |

With 10.6 to 10.8 the round is: the owner plays; the game, any crash and any report travel by
themselves; a fix is built, merged and installed by itself; the owner plays again.

## Already automatic, once set up

Sending games (#52) needs nothing after the token is in the Keychain: every finished game goes at
the engine's start and after each game, and a recording a crash cut short goes too (#53). It waits
on #52 and #53 being merged and installed, which 10.6 and 10.7 make the last manual install.

## How each is verified

- 10.1, 10.2, 10.4, 10.5: tests in the engine, the page in Chromium, the app's unit tests in CI;
  the first build after them shows its version and log on the Mac.
- 10.3: a stand-in GitHub in the tests, as for the games; the report searched for every name of
  the recording it comes from, as the anonymizer's own copies are.
- 10.6: the release workflow builds and checks the app as CI's `macos-app` job does (7.3); the
  replace-and-restart is first seen on the Mac.
- 10.8: its first runs say what they read.

## Where the owner decides

1. **Publishing builds (10.6).** Each merge would publish a prerelease on GitHub (the repository
   is public, so anyone could download the app). Releases so far wait for the owner's tag; this
   makes a prerelease automatic and leaves full releases to the owner.
2. **Auto-merge (10.7).** Claude's pull requests would merge when green without the owner's look.
3. **The daily session (10.8).** A routine on the owner's account that wakes a cloud session once
   a day.
4. **The order.** Proposed: 10.1 and 10.2 together, then 10.3, 10.5, 10.4, then 10.6 to 10.8 as
   the owner allows.
