# Handoff: LeagueasyMode

If you are picking this work up, human or model: read this file top to bottom first. The `handoff` skill
refreshes it; it describes the current state.

Last updated: 2026-11-04, at `f0c55ae` on `main` (pull request #126 merged). No pull request of
this session is open. Another session (roasts, phase 11) merges into `main` too.

## Where things stand

The owner plays with the app on an Apple silicon Mac (League windowed or borderless); each green
push to `main` publishes a prerelease `build-<n>`, which the app installs by itself only while
League's game is not running. Phases 0 to 10 are built; phase 11 (roasts) is the other session's.
An independent review on 2026-11-04 rated the project 4.5/10; its fixes are merged (`docs/log.md`,
2026-11-04), except that the enemy ultimate marks were restored on the owner's word (Settled).

| Area | State | Proof |
|---|---|---|
| Gate | Green: lint, 1435 tests (83 more in Chromium), secrets; about 55 s | `make gate`; `uv run pytest -m browser` (run 2026-11-04) |
| CI and builds | 11 jobs, none may fail; each green `main` publishes `build-<n>` (latest seen: `build-258`) | `.github/workflows/ci.yml`; GitHub releases |
| Real game data | 17 games in the recordings repository: 12 ARAM: Mayhem, 1 Swiftplay, 2 Draft Pick (one remade at 0:56), 2 Practice Tool | `NickHarder/LeagueasyMode-recordings`, `games/` |
| Tests on real games | Two trimmed, anonymized games replayed through the engine, scores pinned | `tests/test_real_recordings.py`, `tests/test_fixture_scores.py`, `tests/fixtures/recorded-games/` |
| Accuracy | On the Rift no estimator has yet beaten chance (1 full Draft Pick, 1 Swiftplay); CI's thresholds are empty until 20 Rift games | `uv run leagueasymode score <recording>`; `tests/accuracy_thresholds.json` |
| Experimental estimates | Win chance (in game and post-game), likely places, jungle path, estimated control wards: hidden unless "Show experimental estimates" is on | `tests/test_unproven_estimates.py` |
| Structures | Turrets and inhibitors read by the names real games send; ARAM's inhibitors respawn 4:10 (all 9 seen) | `src/leagueasymode/inference/structure_names.py`; `tests/test_other_maps.py` |
| Overlay | Quiet at a glance; details and the Tab overview only while Tab or Option is held | `tests/test_overlay_page.py` |
| Recording and sending | Each game recorded and sent to the private repository; a leftover name no longer withholds a game; the server address and spectator key are blanked | `tests/test_sender.py`, `tests/test_anonymize.py` |
| Updates | Never installed while League's game app runs | `AutomaticUpdate` in `overlay/macos/Sources/OverlayCore/BuildUpdate.swift` |

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

1. **Play Rift games** if the Rift's estimates matter: CI's accuracy thresholds, the win chance's
   fit and the turret weights wait for about 20 recorded Rift games (2 so far). Or say ARAM is the
   main mode, and the next feature work goes there.
2. **Say whether Tab shows the details** or only Option does (reading Tab may need Input
   Monitoring), and whether the shaded HUD regions in Edit layout sit on League's HUD.
3. **Roast work** (phase 11, the other session) goes on while the review asked to freeze it until
   the core use case is settled: the owner's call.
4. **Documents waiting for approval** (`make docs-status`): the references on the engine,
   recordings and the macOS app, the executors, all drafts.
5. **Auto-merge settings**: "Allow auto-merge" and a branch rule on `main` requiring CI's checks.
6. **Compare Riot's root certificate** once with Riot's own `riotgames.pem` (fingerprint in
   `src/leagueasymode/riot_tls.py`).

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

- The win chance, the likely places and the jungle path are hidden unless "Show experimental
  estimates" is on, until each beats its baseline on 20 or more Rift games (an independent
  review, 2026-11-04, which the owner asked to have acted on: "Make all the rec fixes"). The
  gold and experience bands are widened 1.7 and 2.55 times, measured on three Rift recordings,
  to measure again with more.

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
  automated". So the marks (⌃⌥1 to 5, then F, D or R) stay. Removed on 2026-11-04 after an
  independent review flagged them, then restored the same day: "I can confirm this is allowed. I
  asked riot support" (the owner); do not remove them again. They stay manual only because the
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

- The overlay is quiet at a glance and shows details only while Tab or Option is held, not while
  the player is dead (the owner, 2026-10-29: "maybe extra details onyl show if i hit tab"; "if it
  is goign to take my eyes off fights, it needs to be wort while info"; then, with the overview
  over ARAM's augment cards, "i should only show when i tab"). The Tab overview stands at the left
  edge, clear of League's scoreboard, augments and shop in the middle; `docs/log.md`.
- No kit eval suite for now (the owner, 2026-10-29: "Do we need evals? You can run it if you
  want"; Claude advised against it). The product is deterministic code with no model in the loop
  but the opt-in Claude's take; pytest and the browser tests guard behavior, and the accuracy
  history against each game's timeline, with CI's thresholds, is the eval of the estimators.
  Revisit when the recorded games are many enough to pin as cases (`enable_evals` is false in
  `.copier-answers.yml`).
- The layout plan and its decisions: widgets dropped on League's HUD move off automatically; ARAM
  times the inhibitors only (the owner, 2026-10-29: "approved, move them off automatically, no
  ARAM timers except inhib"); [docs/plans/overlay-layout.md](docs/plans/overlay-layout.md).
- Recorded games go, anonymized, to the owner's private repository
  `NickHarder/LeagueasyMode-recordings`, by themselves once a token is in the Keychain (the
  owner, 2026-10-28: "i want it automated if possible"; a private repository over a branch of the
  public one). Setup: `docs/references/recordings.md`, "Sending games".
- A name the anonymizer could not remove does not hold a game back: names it knows are replaced,
  the rest is sent (the owner, 2026-10-29: "i dont care about player names being anonmized tbh").
  `leagueasymode anonymize`, for copies committed to the public repository, still fails closed.

## Known limitations

- The gold and experience bands are widened on three Rift games only; the experience band holds
  the truth 73% of the time against the 80% it should. Measure again with more Rift games.
- Turret gold and the win chance's turret weight were hand-set before any turret was ever read
  (the names were wrong until 2026-10-30); they wait for Rift games to fit.
- League's HUD regions (layout slice L.3) are a guess at its default HUD, as shares of the
  window; the shading in Edit layout shows them for the owner to check.
- Whether macOS lets the app read Tab's state without Input Monitoring is not yet seen.

- The dragon rules (5:00 first spawn, 5:00 respawn, Elder 6:00 after the soul) are long-standing
  values, not yet checked against a recording of this season.
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
