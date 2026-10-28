---
type: Reference
title: The macOS overlay app
description: What the menu bar app does, how to run it from a clone, how to build, release and open the app that carries its own engine, its update check and open at login, and the steps for the tracer bullet's test on a Mac over League in each display mode.
tags: [macos, overlay, tracer-bullet]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-28T23:20:00Z }
sources:
  - id: build-update
    resource: ../../overlay/macos/Sources/OverlayCore/BuildUpdate.swift
  - id: panel
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/OverlayPanel.swift
  - id: delegate
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/AppDelegate.swift
  - id: hotkey
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/GlobalHotKey.swift
  - id: roast-copy
    resource: ../../overlay/macos/Sources/OverlayCore/RoastCopy.swift
  - id: toast
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/ToastPanel.swift
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
  - id: game-window
    resource: ../../overlay/macos/Sources/OverlayCore/GameWindow.swift
  - id: layout-editing
    resource: ../../overlay/web/src/layout.ts
  - id: speech
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/SpeechBridge.swift
  - id: release-workflow
    resource: ../../.github/workflows/release.yml
---

# What it is

A menu bar app (no Dock icon) in Swift, in `overlay/macos/`. It starts the engine, the one the app
bundle carries or else the one in the clone it was built from (`uv run --project <clone>
leagueasymode run`), reads the overlay's address from the line the engine prints, and shows that
page in a window over League:[^panel]

- transparent, borderless, without a shadow, and with every click passing through to the game
  outside edit mode, with no setting to change that;
- never key or main, and its panel does not activate the app, so League keeps the keyboard;
  should it find itself key outside edit mode anyway, as on the first try on a Mac, it hides and
  shows itself at once (at most once a second), which leaves the keyboard to League, and the menu
  counts it ("Keyboard: handed back to the game once");
- on every Space, full-screen ones included, at the "Screen saver" window level by default;
- over the screen League is on, or over League's window below its title bar when it is windowed,
  so the minimap layer lines up there too; over the main screen when no game window is on
  screen.[^game-window] Every two seconds the app looks for League's game window in the window
  server's list, by its owner's name ("League of Legends") and bounds, which need no permission,
  and follows it when it moves, resizes or changes screens. The menu says what it found: "League:
  full screen, 1920 × 1080", "League: windowed, 1280 × 720", or "League: no game window seen".

It needs no macOS permission: no Screen Recording, no Accessibility, no Input Monitoring. The
shortcut ⌃⌥⌘L shows and hides the overlay through Carbon's hot keys, which need none.[^hotkey]
Each hot key checks that a press is its own, since every one hears all of the app's.

**Marking an enemy's spell:** hold ⌃⌥, press 1 to 5 for an enemy in role order (1 top, 2 jungle,
3 mid, 4 bottom, 5 support), then F for their Flash, D for their other summoner spell or R for
their ultimate, within three seconds. Every key carries ⌃⌥, so marking never takes a key League
uses. The app posts the mark to the engine's `/marks`, which starts the timer shown on that
enemy's row.[^cooldown-marking]

**Or with a click.** With "Click to mark spells" on in Settings (off unless turned on), each
living enemy's row has three buttons, their Flash, their other summoner spell and R, and a press
on one posts the same mark, naming the enemy by the same place in role order, which the engine
puts on each card (`enemy_slot`). The page tells the app where the buttons are
(`ClickRegions`); the panel looks where the pointer is 30 times a second, takes the mouse only
while it is over a button, and lets every other click through to the game. The panel still never
becomes key, so League keeps the keyboard, and the page's view takes the first click on a panel
that is not key. In edit mode the strip has no buttons, as a press there drags it.
Quitting the app asks the engine to stop; the engine closes the game it is recording first.

**Moving the widgets:** "Edit layout (Esc to finish)" in the menu makes the overlay take clicks,
tints the whole overlay so that the layer catching them shows even when the page shows nothing,
and outlines each movable widget with its name, an empty one too: the objective strip, the
callouts, the enemy strip and the You panel (the minimap layer stays over League's minimap). Drag
one and drop it; it stays there, kept by the engine in `layout.json` in the application's
directory as shares of the overlay's width and height, so it keeps its place when League's window
changes size. Escape, ⌃⌥⌘L, the menu item again, hiding the overlay, or two minutes end it, and
every click goes to the game again; "Reset layout", in the menu or on the notice at the bottom of
the overlay while editing, puts every widget back.[^layout-editing]

**Spoken callouts:** with "Speak callouts" turned on in the settings (it is off until then),
the overlay page hands each new callout to the app as it shows, and the app speaks it once in
macOS's own voice (`AVSpeechSynthesizer`, the system's default voice).[^speech] In a browser, as
against a replay, the browser's own speech speaks it instead.

**Which build, and the engine's log.** The menu's first line names the build: "LeagueasyMode
0.1.0 (build 62, b0d63a8)", its version, CI's run number and the commit (`BuildInfo`; "from source"
under `swift run`). The app hands the same words to the engine in `LEAGUEASYMODE_BUILD`, so the
status page, its report and each crash report name the build too. The engine's output, which an app
opened from Finder has nowhere to show, goes to `~/Library/Logs/LeagueasyMode/engine.log`, a new
one each start with the last three runs' kept (`EngineLog`); "Open engine log" in the menu opens
it.

**Report a problem, and an engine that stops.** "Report a problem…" in the menu asks for an
optional note and has the engine make a report: the app's own menu lines (the build, the engine,
the overlay page, League's window, the keyboard, the window level, macOS's version), the status
page's report, the end of this run's and the last run's engine log, the crash reports' names and
the game so far, anonymized, with every player's name and the home folder taken out. The engine
writes it to `reports/` beside the recordings and sends it to the games' repository at once
(`recordings.md`); ⌃⌥⌘R sends one without a note, from inside a game. The menu then says
"Report: made at 21:40, being sent", or why it could not be made (`ProblemReportRequest`;
`problem_report.py`). An engine that stops is started again three seconds later, with a new log,
at most five times in ten minutes; after that the menu says "Engine: stopped (exit 1) after
repeated restarts" (`EngineRestartPolicy`).

**Copying the roast.** After a game, ⌃⌥C puts the closing line the post-game window shows on the
clipboard, for the player to paste in chat themselves; the app never sends anything to chat.
Pressed again within five seconds of the press before, it copies the next take, then the one
after (`CopyPresses`). The engine gives the line (`/closing-line`, from the last case the window
showed, the whole team at Salty before it shows one) and refuses during a game, until moments
about friends come in phase 11.6. A toast near the top of League's window says what was copied
("Copied: …", the line cut at 60 characters) or why nothing was. The toast is a borderless panel
that does not activate the app and lets every click through, so it never takes the mouse or the
keyboard from League (`ToastPanel`).

The menu shows whether the engine runs and whether the overlay page loaded in the overlay's
window ("Overlay: page loaded", or "Overlay: the page did not load (…)" with the web view's
reason; a page whose process stops is loaded again), toggles the overlay, and picks the window
level, since which level stays above League depends on how League draws:[^levels]
Floating, Status bar, Screen saver, and Above a captured display (one above the level a game that
captures the display draws at). "How to use…" opens the shortcuts, in Mac and Windows-keyboard
names (⌃⌥⌘L is Ctrl + Alt + Windows + L), what each widget and minimap mark means, the menu, and
what to do when the mouse or keyboard acts up; the app opens it by itself once, the first time
the engine is up. "Last game…" opens the post-game window, "Settings…" the settings page and
"Status…" what the engine sees, in the default browser, normal windows rather than the
click-through overlay: the engine's pages `how-to-use.html`, `summary.html`, `settings.html` and
`status.html` beside the overlay's (`EnginePage` in `OverlayCore` builds their addresses); each
waits until the engine has announced its address. A test checks that each key the app registers
is on the How to use page (`tests/test_how_to_use_page.py`).

`OverlayCore` holds what the app decides without AppKit (which engine to run, its command and
search path,[^engine-command] reading its output, finding the bundled engine or the clone) and has
unit tests; CI builds the app and runs them on a
macOS runner. The app is in Swift 6's language mode, which checks concurrency in full: AppKit's
side of the app runs on the main actor, the engine's output is read off it behind a lock, and a
call that could race does not compile.

# Run it from a clone

Needs the Xcode 16 command line tools or later (`xcode-select --install`), for Swift 6, and uv.

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

**The icon.** A gold scope over a faint minimap, on a dark blue body: an original drawing, with
no game's artwork in it. `overlay/macos/Resources/AppIcon.svg` is the drawing and `AppIcon.png`
its 1024-pixel rendering (`overlay/macos/scripts/render_icon.py`, in Chromium, after a change to
the drawing); `build_app.sh` makes `AppIcon.icns` from the PNG with macOS's `sips` and
`iconutil`, and the smoke test checks it is in the app. The menu bar keeps macOS's "scope"
symbol, which follows the menu bar's light and dark look.

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

**Builds of main.** Each push to `main` whose checks pass is published as a prerelease, tagged
`build-<run number>`, with `LeagueasyMode-<version>-build-<run number>.zip` and its SHA-256 (CI's
`prerelease` job). The run number is CI's, the one every build carries in its Info.plist, so a pull
request's test build and the builds of main are ordered alike. The owner allowed this on
2026-10-28 ("Auto-published builds"); full releases stay the owner's tags.[^build-update]

**The update check.** Once a day at most, the bundled app asks GitHub's API for the repository's
latest release, without a token; a draft, a prerelease, a release without the zipped app (as the
repository's old v1.0.0, which led to an empty page), or a version not newer than the app's is
ignored.[^update-check] A newer one adds "LeagueasyMode 0.2.0 is out…" to the menu, which opens the
release's page; the page's address is always built from the tag on this repository, whatever
GitHub's answer says. The same check, one at every start and one every hour ask for the newest
builds of main: one with a higher build number and a version no lower than the app's adds "Install
update: build 75 (0.1.0)…". With "Install updates automatically (not during a game)" on, as it is
unless turned off, the app installs it by itself as soon as no game window of League's is on
screen, the widgets are not being moved and no install runs (`AutomaticUpdate`), and after the
restart the menu says "Update: build 75 installed"; a build whose automatic install failed is not
tried again by itself. Otherwise the menu item, once confirmed, downloads the zip and its checksum from this repository's
release, checks one against the other, unpacks the app with `ditto`, checks it is LeagueasyMode
and that its signature holds, puts it in place of the running app, starts it and quits
(`UpdateInstaller`). A file the app downloads itself is not marked as from the internet, so the
new build opens without "Open Anyway"; that is first seen on the Mac. A folder the app cannot
write to, or any failed step, leaves the app as it was and says why in the menu ("Update: not
installed (…)"). "Check for updates now" asks at once. "Check for updates" in the menu turns the
checks off; they are the app's only requests beyond this Mac, League's servers, Data Dragon
and the games' repository. An app run from a clone has no version and does not check.

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
   - what the menu's "League:" line says, and in windowed mode whether the overlay fits the
     game's picture, its top edge level with the picture's;
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
[^game-window]: `overlay/macos/Sources/OverlayCore/GameWindow.swift`
[^layout-editing]: `overlay/web/src/layout.ts`
[^speech]: `overlay/macos/Sources/LeagueasyOverlay/SpeechBridge.swift`
[^bundled-engine]: `overlay/macos/Sources/OverlayCore/BundledEngine.swift`
[^build-app]: `overlay/macos/scripts/build_app.sh`
[^smoke-test]: `overlay/macos/scripts/smoke_test_app.sh`
[^release-workflow]: `.github/workflows/release.yml`
[^update-check]: `overlay/macos/Sources/OverlayCore/UpdateCheck.swift`
[^build-update]: `overlay/macos/Sources/OverlayCore/BuildUpdate.swift`
[^login-item]: `overlay/macos/Sources/OverlayCore/LoginItemState.swift`
