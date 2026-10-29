# Handoff: LeagueasyMode

If you are picking this work up, human or model: read this file top to bottom first. The `handoff` skill
refreshes it; it describes the current state.

Last updated: 2026-10-29, at `ff23895` on `main` (pull request #94 merged). No pull request of
this session is open. Another session (roasts, phase 11) merges into `main` too.

## Where things stand

The owner plays with the app on an Apple silicon Mac (League windowed) and updates arrive by
themselves: each green push to `main` publishes a prerelease `build-<n>` (latest `build-190`), and
the app installs it when no game window is on screen. Every plan is approved; phases 0 to 10 are
built, phase 11 (roasts) is the other session's. Since the owner's first real games (2026-10-28
and 29) the work is field fixes and the approved layout plan
([docs/plans/overlay-layout.md](docs/plans/overlay-layout.md), all five slices merged) tied to the
use cases in [docs/USERS.md](docs/USERS.md).

| Area | State | Proof |
|---|---|---|
| Gate | Green: lint, 1079 tests (and 80 in Chromium), secrets | `make gate`; `uv run pytest -m browser` |
| CI and builds | 11 jobs, none may fail; each green `main` publishes `build-<n>` | `.github/workflows/ci.yml`; GitHub releases |
| App on the owner's Mac | Runs over League, installs updates itself (seen 107 → 119, then to 176) | the owner's messages; `reports/` in the recordings repository |
| Overlay at a glance | Timers, the newest two callouts that ask for an action now, one short line an enemy | `tests/test_overlay_page.py` (glance tests) |
| Details on a key | Tab or Option held, or the player dead: everything else, the spell buttons and the Tab overview of both teams | `overlay/macos/Sources/OverlayCore/DetailsKey.swift`; `areDetailsShown`, `renderOverview` in `overlay/web/src/overlay.ts` |
| Layout | Drag, resize (60–160%), sliders, opacity, hide, kept off League's HUD | `tests/test_layout_page.py`, `tests/test_settings_page.py` |
| Off the Rift (ARAM, Arena) | No roles; inhibitor timers only, marked "~"; the Rift's models hidden | `tests/test_other_maps.py` |
| Recording and sending | Records each game; recordings left open are closed after 20 minutes and sent | `tests/test_sender.py`, `tests/test_recording_file.py` |
| Real game data | **One game** in the recordings repository (Practice Tool, cancelled at 0:00); the owner's ARAM and Swiftplay games were left open on the Mac and go with build 184 or later | `NickHarder/LeagueasyMode-recordings`, `games/` |

## How to check your work

```bash
make bootstrap                     # once per clone
make gate                          # everything a push must pass
uv run pytest -m browser           # the overlay page in Chromium (uv run playwright install chromium)
(cd overlay/web && npm ci && npm run build)   # after changing the widgets' TypeScript
(cd overlay/macos && swift build && swift test)   # on a Mac
overlay/macos/scripts/build_app.sh && overlay/macos/scripts/smoke_test_app.sh dist/LeagueasyMode.app   # on a Mac
```

## Rules

In `AGENTS.md`, this project's own included: every session reads that file.

## Open, for the owner

1. **Install build 184 or later** (it installs itself when no game is on screen). The games
   already played then close and go to the recordings repository. The menu's "Status…", "Sending
   games", says how many went. If none do, "Report a problem…" sends the log and now the
   recordings folder's list.
2. **Try the new overlay in a game** and say: whether holding **Tab** shows the details or only
   **Option** does (reading Tab may need macOS's Input Monitoring permission; Option needs none);
   whether the mouse now behaves; whether the shaded HUD regions in Edit layout sit on League's
   HUD, and the minimap layer on League's minimap.
3. **USERS.md's open fields**: games a day, when the owner plays, main role and rank.
4. **Documents waiting for approval** (`make docs-status`): the phase 10 plan and the references
   on recordings, the engine and the macOS app, all drafts.
5. **Auto-merge settings** (10.7): "Allow auto-merge" and a branch rule on `main` requiring CI's
   checks; until then sessions merge green pull requests themselves, as the owner allowed.
6. **The first release**: tag `v0.1.0` when the owner wants; the prereleases need nothing.
7. **Compare Riot's root certificate** once with Riot's own `riotgames.pem`: the SHA-256
   fingerprint is in `src/leagueasymode/riot_tls.py`.

## Where everything is

- `src/leagueasymode/`: the engine. `recording/` and `recorder.py` record; `replay.py` replays;
  `game_state.py` reads the game's answer; `patch_data.py` and `data_dragon.py` hold the patch's
  items and stats; `inference/` holds the estimators; `engine.py`,
  `overlay_server.py` and `overlay_state.py` serve the overlay.
- `overlay/web/`: the widgets' TypeScript, compiled into `src/leagueasymode/overlay_web/`.
- `overlay/macos/`: the Swift menu bar app.
- `docs/references/`: how recordings, the engine and the macOS app work.
- `docs/plans/overlay-and-inference.md`: the plan; `docs/log.md`: what changed and why.

## Do not commit

In `AGENTS.md`. Also: a raw recording (it holds other players' names); only `anonymize` copies.

## Settled; do not reopen without the owner

- An overlay on the Mac, not a second screen; League's local APIs, plus each patch's champion and
  item stats from Riot's Data Dragon, fetched once a patch and kept on disk (the owner, 2026-10-08:
  "pull the info from an API and then store it and refresh on patches / updates"). The plan, and
  the owner's messages of 2026-10-08.
- This season's spawn times: Voidgrubs 8:00, Herald 15:00, Baron 20:00 (the owner, 2026-10-08).
- Python engine, Swift shell, TypeScript widgets: the plan's recommended stack, approved with it.
- The client's post-game timeline as ground truth for scoring estimators: the plan, approved.
- What may show during a game (the plan's decision 4): everything. The owner, 2026-10-08:
  "everything is allowed. anything we can calculate / estimate / derive / infer / interpolate we
  should if it would be useful". This replaces the plan's policy, which left out enemy ultimate and
  summoner spell timers and instructions to the player. Facts are still tagged exact or estimate,
  so the overlay can say how sure it is. Restated 2026-10-28, when a session suggested dropping
  the ultimate marks over reports of Riot's 2025 rule on ultimate timers: "dont listen to rumors.
  if we can get the info from the local host server we can use it wither its manual or
  automated". So the marks (⌃⌥1 to 5, then F, D or R) stay. They stay manual only because the
  game's local API gives no enemy's spell casts or cooldowns: each player's two summoner spells
  by name, and cooldowns for the player on this machine alone. If a recorded game ever shows a
  field that changes when an enemy casts, the marks become automatic.
- `truststore` as a dependency, for HTTPS to Data Dragon (the owner, 2026-10-08).
- Pushing and opening pull requests need no asking; deletions on GitHub and force pushes stay off
  limits (the owner, 2026-10-08; `AGENTS.md`, rule 1).
- Keep building through the plan without waiting for merges: open each slice's pull request into
  `main` as it is ready, assuming the earlier ones will be merged (the owner, 2026-10-08: "keep
  building as well and putting in new mrs even if i havent merged"). A slice built on an unmerged
  one says so in its pull request, and targets `main` all the same.
- The hand-set thresholds are tweaked as games show what they should be, in one file anyone can
  edit: `tuning.json` (the owner, 2026-10-09: "we will tweak as needed. make sure there is an
  easy way to update them"; `docs/references/engine-and-overlay.md`, "Tuning").
- Reading each player's newest five timelines for their numbers at 10:00 (9.4): about 70
  requests a game at most, through the client's own session (the owner, 2026-10-09: "I am fine
  with this if the free developer key can handle this"; no developer key is used, and the pace
  would fit one's limits).

- The overlay is quiet at a glance and shows details only while Tab or Option is held or the
  player is dead (the owner, 2026-10-29: "maybe extra details onyl show if i hit tab"; "if it is
  goign to take my eyes off fights, it needs to be wort while info"); `docs/log.md`.
- The layout plan and its decisions: widgets dropped on League's HUD move off automatically; ARAM
  times the inhibitors only (the owner, 2026-10-29: "approved, move them off automatically, no
  ARAM timers except inhib"); [docs/plans/overlay-layout.md](docs/plans/overlay-layout.md).
- Recorded games go, anonymized, to the owner's private repository
  `NickHarder/LeagueasyMode-recordings`, by themselves once a token is in the Keychain (the
  owner, 2026-10-28: "i want it automated if possible"; a private repository over a branch of the
  public one). Setup: `docs/references/recordings.md`, "Sending games".

## Known limitations

- League's HUD regions (layout slice L.3) are a guess at its default HUD, as shares of the
  window; the shading in Edit layout shows them for the owner to check.
- ARAM's inhibitor respawn time is unknown: the Rift's 5:00 stands in, marked "~", until a
  recorded ARAM game shows `InhibKilled` and `InhibRespawned`.
- Whether macOS lets the app read Tab's state without Input Monitoring is not yet seen.

- Nothing has met a real game: field names, the `KillerName` form, the lockfile path, the
  certificate check and the timeline endpoint are from documentation and libraries, not seen.
- The dragon rules (5:00 first spawn, 5:00 respawn, Elder 6:00 after the soul) are long-standing
  values, not yet checked against a recording of this season.
- The overlay follows League's window (8.2) on the guess that the game's window is owned by
  "League of Legends" and has a title bar when windowed; the test on a Mac confirms both.
- The first try on a Mac (the owner, 2026-10-28, an Apple silicon MacBook Pro, League
  windowed): the overlay showed nothing, and with "Let clicks through" turned off and "Edit
  layout" on, its invisible layer caught every click until the app was stopped. The menu item is
  gone, edit mode is tinted and ends on Escape, ⌃⌥⌘L or after two minutes, and the menu says
  whether the overlay page loaded. The second try (that build) showed the overlay over the game,
  but League's keys did nothing until ⌃⌥⌘L hid and showed it: the overlay held the keyboard
  without edit mode, by a path not yet known. It now hands the keyboard back by itself and the
  menu counts it; the next try says whether that was the path.
- Sightings (an enemy in sight has no circle on the minimap) rest on League's scoreboard
  showing an enemy's creep score, items and level only while your team sees them; if the game
  gives them through the fog, an enemy farming out of sight loses their circle for 3 seconds at
  a time. The first recording settles it. The owner ruled out reading the screen (2026-10-28).
- Edit mode (8.3) makes the overlay's panel key so its widgets take drags; that a
  non-activating panel takes them without bringing the app forward is seen on a Mac.
- The test item catalog (`tests/fixtures/client/items.json`) is hand-written: its prices are not
  this patch's, and the "finished item" rule (a full recipe of at least 2000 gold) and the support
  item names are to be checked on a real catalog.
- The role costs are a hand-set prior, not yet fitted on recorded games.
- The suggestions' wording is a first draft, and their thresholds (an objective within 0:30, a
  window of at least 0:20) are hand-set, like every other threshold, in `tuning.json`.
- Loading-screen intel reads the client's ranked stats and match history in the shapes other tools
  describe; no real answer has been seen. If the client does not answer for other players, or
  answers in another shape, the line under each enemy stays empty until the first recording shows
  what to read. The same holds for the past games' timelines that say where a jungler starts
  (9.1, 9.4): the path is the one the post-game timeline uses, and whether the client serves
  other players' games there is first seen in a recording.
- Combat stats leave out runes, passives, stacks and buffs, so an estimate runs low for a champion
  that has them. Data Dragon's item stats leave out some stats (ability haste, lethality, magic
  penetration), which the overlay does not show anyway. The Data Dragon test files are
  hand-written; the reading is checked against the real 16.20.1 files. Data Dragon has given
  every champion an attack damage growth of 0 since 16.5.1, so the engine borrows 16.4.1's; a
  champion released since (Locke) has none, and a growth changed since is a patch behind.
- The Voidgrubs' 14:45 and the Herald's 19:45 leave times follow past seasons and one community
  guide; a recording confirms them.
- The Swift app moved to the Swift 6 language mode (8.6), whose concurrency checks it passes in
  CI; its threads are as before (AppKit's side on the main thread), which the test on a Mac
  confirms at run time.

## History

In `docs/log.md`, newest first.
