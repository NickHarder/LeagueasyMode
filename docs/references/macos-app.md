---
type: Reference
title: The macOS overlay app
description: What the menu bar app does, how to run it from a clone, how to build, release and open the app that carries its own engine, its update check and open at login, and the steps for the tracer bullet's test on a Mac over League in each display mode.
tags: [macos, overlay, tracer-bullet]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-09T01:37:17Z }
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
  - id: cooldown-marking
    resource: ../../overlay/macos/Sources/OverlayCore/CooldownMarking.swift
  - id: bundled-engine
    resource: ../../overlay/macos/Sources/OverlayCore/BundledEngine.swift
  - id: build-app
    resource: ../../overlay/macos/scripts/build_app.sh
  - id: smoke-test
    resource: ../../overlay/macos/scripts/smoke_test_app.sh
  - id: update-check
    resource: ../../overlay/macos/Sources/OverlayCore/UpdateCheck.swift
  - id: login-item
    resource: ../../overlay/macos/Sources/OverlayCore/LoginItemState.swift
  - id: release-workflow
    resource: ../../.github/workflows/release.yml
---

# What it is

A menu bar app (no Dock icon) in Swift, in `overlay/macos/`. It starts the engine, the one the app
bundle carries or else the one in the clone it was built from (`uv run --project <clone>
leagueasymode run`), reads the overlay's address from the line the engine prints, and shows that
page in a window that covers the screen:[^panel]

- transparent, borderless, without a shadow, and with clicks passing through to the game;
- never key or main, and its panel does not activate the app, so League keeps the keyboard;
- on every Space, full-screen ones included, at the "Screen saver" window level by default.

It needs no macOS permission: no Screen Recording, no Accessibility, no Input Monitoring. The
shortcut ⌃⌥⌘L shows and hides the overlay through Carbon's hot keys, which need none.[^hotkey]
Each hot key checks that a press is its own, since every one hears all of the app's.

**Marking an enemy's spell:** hold ⌃⌥, press 1 to 5 for an enemy in role order (1 top, 2 jungle,
3 mid, 4 bottom, 5 support), then F for their Flash, D for their other summoner spell or R for
their ultimate, within three seconds. Every key carries ⌃⌥, so marking never takes a key League
uses. The app posts the mark to the engine's `/marks`, which starts the timer shown on that
enemy's row.[^cooldown-marking]
Quitting the app asks the engine to stop; the engine closes the game it is recording first.

The menu shows whether the engine runs, toggles the overlay and the click-through, and picks the
window level, since which level stays above League depends on how League draws:[^levels]
Floating, Status bar, Screen saver, and Above a captured display (one above the level a game that
captures the display draws at). "Last game…" opens the post-game window, "Settings…" the
settings page and "Status…" what the engine sees, in the default browser, normal windows rather
than the click-through overlay: the engine's pages `summary.html`, `settings.html` and
`status.html` beside the overlay's (`EnginePage` in `OverlayCore` builds their addresses); each
waits until the engine has announced its address.

`OverlayCore` holds what the app decides without AppKit (which engine to run, its command and
search path,[^engine-command] reading its output, finding the bundled engine or the clone) and has
unit tests; CI builds the app and runs them on a
macOS runner. The app is written for Swift 5 with strict concurrency checking as warnings. CI's
build shows some, which are to be cleared before it moves to the Swift 6 language mode.

# Run it from a clone

Needs the Xcode command line tools (`xcode-select --install`) and uv.

```bash
git clone https://github.com/NickHarder/LeagueasyMode.git && cd LeagueasyMode
cd overlay/macos && swift run LeagueasyOverlay
```

The engine's log appears in the same terminal. If the app cannot find the clone, set
`LEAGUEASYMODE_REPOSITORY` to its path.

# The app without a clone

`overlay/macos/scripts/build_app.sh` builds `LeagueasyMode.app` on a Mac with the Xcode command
line tools and uv, and zips it as `LeagueasyMode-<version>.zip`, into `dist/` unless given another
directory.[^build-app] CI builds it for every pull request (job `macos-app`), starts its engine as
the app would from an empty home folder and fetches each of its pages,[^smoke-test] then keeps the
zip with the run for 14 days: the run's summary page links to it.

Inside are the app, a copy of uv in `Contents/Helpers`, and in `Contents/Resources/engine` the
engine as a wheel (its overlay pages with it), the versions `uv.lock` pins and the project's Python
version. The app runs `uv tool run --from <wheel> --constraints <pins> --python 3.12 leagueasymode
run`:[^bundled-engine] the first start downloads the engine's dependencies into uv's cache
(`~/.cache/uv`), and Python 3.12 if none is installed, which takes a minute or so; later starts
reuse them. The app prefers the engine it carries; setting `LEAGUEASYMODE_REPOSITORY` makes it run
a clone's instead, to try a change to the engine.

With no clone there is no `.env`: the engine's settings are read from
`~/Library/Application Support/LeagueasyMode/settings.env`, in the form of `.env.example`, and its
files (recordings, the accuracy history, the last game, the preferences) are kept beside it.

**Opening it the first time.** The app is signed ad hoc, not with a Developer ID, so macOS stops
it the first time it opens, once:

- macOS 15 and later: open it, then in System Settings → Privacy & Security, choose "Open
  Anyway" beside LeagueasyMode, and confirm.
- macOS 13 and 14: Control-click the app, choose Open, then Open again.
- Or, in Terminal: `xattr -dr com.apple.quarantine /Applications/LeagueasyMode.app`.

It is built for the architecture of the Mac that builds it. CI's runner is Apple silicon, so the
zip from CI runs on Apple silicon only.

# Releases, updates and opening at login

**Releasing.** A tag `v<version>` publishes a release on GitHub with the zipped app and its
SHA-256 (`.github/workflows/release.yml`).[^release-workflow] The tag must be the version in
`pyproject.toml`, which the app takes as its own: bump it in a pull request
(`uv version --bump minor`), merge, then `git tag v0.2.0 origin/main && git push origin v0.2.0`.
The workflow builds and checks the app as CI's `macos-app` job does before it publishes.

**The update check.** Once a day at most, the bundled app asks GitHub's API for the repository's
latest release, without a token; a draft, a prerelease, or a version not newer than the app's is
ignored.[^update-check] A newer one adds "LeagueasyMode 0.2.0 is out…" to the menu, which opens the
release's page; the page's address is always built from the tag on this repository, whatever
GitHub's answer says. Installing it is by hand: download, unzip, replace the app in
Applications. "Check for updates daily" in the menu turns the check off; it is the app's only
request beyond this Mac, League's servers and Data Dragon. An app run from a clone has no version
and does not check.

**Open at login.** The menu's "Open at login" asks macOS to open the app when the player logs in
(`SMAppService`, macOS 13 and later).[^login-item] macOS may ask the player to allow it in System
Settings → General → Login Items, which the app then opens; until then the item reads "allow in
System Settings…". Only the bundled app offers it. Whether macOS accepts an app signed ad hoc as
a login item is yet to be seen on a Mac.

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
   - whether ⌃⌥⌘L hides and shows it;
   - whether a mark (⌃⌥3 then ⌃⌥F) puts "F 5:00" on the mid laner's row, and whether League
     ignores the keys.
4. After the game, and a few minutes on the client's end-of-game screen while the timeline
   comes, open "Status…" from the menu, choose "Copy report" and paste the report into a
   message: it says which parts worked, and names no player. Do the same mid-game if something
   looks wrong.
5. Quit the app from the menu. The game's recording is in
   `~/Library/Application Support/LeagueasyMode/recordings/`; run
   `uv run leagueasymode anonymize <recording>` on it.

The first recordings also settle what this project has assumed and not yet seen: the lockfile's
place, that Riot's root certificate verifies both the game and the client, the event names and
whether `KillerName` holds a game name or a Riot ID, and whether the client serves
`/lol-match-history/v1/game-timelines/<game id>`.

[^panel]: `overlay/macos/Sources/LeagueasyOverlay/OverlayPanel.swift`
[^hotkey]: `overlay/macos/Sources/LeagueasyOverlay/GlobalHotKey.swift`
[^cooldown-marking]: `overlay/macos/Sources/OverlayCore/CooldownMarking.swift`
[^levels]: `overlay/macos/Sources/LeagueasyOverlay/WindowLevelChoice.swift`
[^engine-command]: `overlay/macos/Sources/OverlayCore/EngineCommand.swift`
[^bundled-engine]: `overlay/macos/Sources/OverlayCore/BundledEngine.swift`
[^build-app]: `overlay/macos/scripts/build_app.sh`
[^smoke-test]: `overlay/macos/scripts/smoke_test_app.sh`
[^release-workflow]: `.github/workflows/release.yml`
[^update-check]: `overlay/macos/Sources/OverlayCore/UpdateCheck.swift`
[^login-item]: `overlay/macos/Sources/OverlayCore/LoginItemState.swift`
