---
type: Plan
title: "Phase 10: roasts with receipts, after the game and in it"
description: How the overlay gets nothingsmyfault's cited roasts, a case file for anyone in the game in the post-game window and short moments about friends during it, both copied for chat with one shortcut and never posted, in a proposed build order with what each needs and where the owner decides.
tags: [plan, phase-10, roasts, post-game]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-28T20:30:33Z }
sources:
  - id: owner-2026-10-28
    resource: "The owner's messages of 2026-10-28, in the session that built nothingsmyfault"
  - id: nothingsmyfault
    resource: https://github.com/NickHarder/nothingsmyfault
    title: "nothingsmyfault: fact-cited case files for the last game (private)"
  - id: first-recording
    resource: "LeagueasyMode-recordings, games/game-2026-10-28T00-11-38Z-anonymized.jsonl.xz"
    title: A Practice Tool game, cancelled 0.05 s in, before any player loaded
  - id: recorder
    resource: ../../src/leagueasymode/recorder.py
  - id: global-hot-key
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/GlobalHotKey.swift
  - id: app-delegate
    resource: ../../overlay/macos/Sources/LeagueasyOverlay/AppDelegate.swift
  - id: callouts
    resource: ../../src/leagueasymode/inference/callouts.py
  - id: update-check
    resource: ../../overlay/macos/Sources/OverlayCore/UpdateCheck.swift
  - id: engine-size
    resource: "wc -l over nothingsmyfault's src/ on 2026-10-28: the engine (evidence/, verdict.py, roast/, casefile.py) 2,993 lines and roast/templates.yaml 599; the site and Riot plumbing (app.py, riot/, cache.py, recordings.py, ddragon.py, ledger.py, roster.py, web/) 3,273"
  - id: game-state
    resource: ../../src/leagueasymode/game_state.py
---

# Phase 10: roasts with receipts, after the game and in it

The owner, 2026-10-28: "is there any way to put this in leagueasymode overlay so i can have ammo to
tease my friends ... it could either read at the end or during the events through the local server
like the overlay does".[^owner-2026-10-28] "This" is nothingsmyfault, the owner's other
project.[^nothingsmyfault] It turns a game into a **case file**: a verdict (team diff, a lane's
diff, guilty and others), roast lines, and a closing line to paste into chat. Every number in a
line is an exact value with its source, and a validator drops any line that states a number it
cannot cite. The owner approved its voice on 2026-10-08.

nothingsmyfault reads Riot's web API, which needs a developer key that expires every day. The
overlay already has what the case file needs without one. After a game, the recorder saves the
client's game details, the game's timeline and the end-of-game stats.[^recorder] During a game,
the game's API gives every player's score and the kill feed.[^game-state] So the overlay can roast
any game you play, with no key. The engine moves here; nothingsmyfault stays private and as it
is (see "Where the engine lives").

The owner's answers so far:[^owner-2026-10-28]

- **Who it is for:** "this will only be used with friends so dont worry", so roasting friends
  during a game is allowed.
- **Chat:** "we def wont do auto posting but there should be a short cut to copy and then i can
  manually paste it in chat". The overlay copies; the owner pastes.
- **When:** "post game is probably how it would be used most, but depending on the moment it could
  be fun to flame friends".
- **Whom:** "make sure the end game chat can work for anyone not just my friends". The post-game
  case can name any player in the game.

## Slices, proposed build order

| # | Slice | Shows | Needs |
|---|---|---|---|
| 10.0 | The client's post-game answers, seen | Nothing. One real matchmade game, recorded through to the end, shows the client's game details, timeline and end-of-game stats as they really are | One game of the owner's with `leagueasymode record` running until the timeline is saved. The only recording so far is a Practice Tool game cancelled at 0:00, before any player loaded, so it holds none of the three[^first-recording] |
| 10.1 | The roast engine, here | Nothing yet. nothingsmyfault's engine ported into `src/leagueasymode/roast/`: exhibits, the verdict, the composer, the validator, the safety floor and the closing line, with the approved lines word for word. Its thresholds go into `tuning.json`; its checks, the independent "every number cited" scorer included, become tests | Built payloads in the client's shape, since nothingsmyfault's test games are in Riot's web format |
| 10.2 | A client game as a case | The families read the client's game details and timeline through this project's own models, so every exhibit cites the client's answer (its path in `/lol-match-history/v1/games/<id>` or the timeline) with no converted copy between. A field the client does not send gives no exhibit and no line, never a zero, as nothingsmyfault already does | 10.0's shapes; 10.1 |
| 10.3 | The case file in the post-game window | A section of the post-game window: the verdict, the lane board, the lines and the closing line. Targets cover anyone in the game: the whole team (the default), the enemy team, any lane, or any one of the ten players. Four spice levels, as on the site | 10.2 |
| 10.4 | The copy shortcut | ⌃⌥C copies the roast that is up: after a game, the closing line; during one, the newest moment (10.6). Pressed again within 5 seconds, it copies the next take, or the moment before. A toast says what was copied ("Copied: …"). Nothing is ever sent to chat | The overlay's Carbon hot keys,[^global-hot-key] which work while League has focus with no Accessibility permission; the clipboard written from Swift, not the page |
| 10.5 | The friends list | A setting of the friends' Riot IDs. The overlay marks which players in the game are friends, from the Riot IDs the game's API already sends | The settings page |
| 10.6 | Moments about friends | A short notice, of its own kind beside the callouts,[^callouts] when a friend's game hands over ammo, from exact facts only. See "The moments" below | 10.5; the scoreboard and kill feed the engine already reads |
| 10.7 | A quick scoreboard case | Right after the game, before the timeline comes, a case from the end-of-game stats: scoreboard lines, no lane verdict. The full case replaces it when the timeline arrives | 10.0's shape of the end-of-game stats; built only if they hold enough |

The tracer bullet is 10.2 to 10.4 on one recorded game: a case in the post-game window, its
closing line copied by the shortcut. 10.5 and 10.6 come next, then 10.7 if the end-of-game stats
are worth it.

## The moments (10.6)

Each is a fact a friend can check on the scoreboard or in the kill feed, so it carries no exhibit
letters. Each fires once per game per friend and threshold. The thresholds go in `tuning.json` like
every other.

- A friend dies to their lane opponent with no assists for the second time, or the third.
- A friend dies in the minute before the enemy takes a dragon, the Elder or Baron.
- A friend gives up first blood.
- A friend is a set number of creep score behind their lane opponent at 10:00 or 14:00.
- A friend's lane opponent kills them three times without the friend getting a kill.

**Lane opponents mid-game** come from the roles estimator. A moment uses a pairing only where both
roles are given or likely, never a guess, so a moment is never wrong about who laned against whom.

**Gold is left out.** The game's API gives gold for the active player only. Every other player's gold
is an estimate with a band, and a roast states only exact facts. Gold leads wait for the post-game
timeline.

## Where the engine lives

**Claim:** nothingsmyfault's engine is ported into LeagueasyMode, and LeagueasyMode depends on nothing of nothingsmyfault's.
**Evidence:** the app's update check reads this repository's releases from GitHub's API without signing in, so this repository stays public;[^update-check] of nothingsmyfault's code, the engine is about 3,000 lines and its lines 600, while the other 3,300 (Riot's web client, a cache, the website, recording and scrubbing, Data Dragon) duplicate what this project has or are not needed;[^engine-size] the recorder, the client's models, the roles estimator, the callouts, the post-game window and the hot keys are already here.
**Alternative considered:** make nothingsmyfault public and depend on a pinned version of it, its website's dependencies made optional; one copy of the engine.
**Why rejected:** a second repository, release and gate for every change to a line; nothingsmyfault's engine reads Riot's web format, so a converter would sit between the client's answer and every exhibit; and its website would be published for no use. Depending on it while private would need a token in this public repository's CI.
**How to reverse:** if nothingsmyfault's site comes back, its `casefile.py` imports `leagueasymode.roast` instead of its own engine (a private project can depend on a public one with no token), and its copy is deleted.

The cost is a second copy of the engine while nothingsmyfault keeps its own; it is parked, and the
line above ends that if it comes back. The roast lines become public with this repository, as they
would with any option that ships them in the overlay.

## What changes from nothingsmyfault's site

- **The source** is the League client after the game, not Riot's web API, so no key is needed and
  nothing leaves the Mac.
- **The chat line drops the exhibit letters** ("(A)(B)"). They point to the site's evidence list,
  which nobody in chat can see; the numbers are on the post-game scoreboard. The
  "– nothingsmyfault.lol" signature is off unless the owner wants it.
- **The Mutual Defense Pact** spares friends from a team roast on the site. Here it is off by
  default, since teasing friends is the point.
- **Speech:** the overlay can read callouts aloud. Roasts and moments are never spoken, unless a
  setting of their own turns that on.

## Known limits

- **The client's older match format.** The overlay's models of the client's game details expect
  stats nested under each participant, identities in a list of their own, and a team's result as
  "Win" or "Fail". That is not the format nothingsmyfault reads now, hence 10.2. Some fields
  nothingsmyfault's families read may not exist there: pings, the damage share, the surrender. Their
  lines go quiet; nothing is guessed. 10.0 settles which ones.
- **The timeline comes a little after the game.** The case appears when it does. 10.7 would fill the
  wait.
- **The Mac only.** The overlay roasts games the owner plays. Friends' own games, without the
  owner, would need nothingsmyfault's site and a Riot key.
- **Chat lengths.** The post-game lobby's limit and the in-game chat's may differ, and neither is
  measured. nothingsmyfault starts at 140 characters.

## How each is verified

- **10.2:** tests on built answers in the client's shape, then on 10.0's recording. nothingsmyfault's
  own checks apply to every line: each number equals an exhibit it cites, and an independent
  scorer checks the rendered text again.
- **10.3:** a Chromium test of the section against a recorded game, as for the post-game window.
- **10.4:** a Swift unit test of which text the shortcut picks: after a game, during one, and pressed
  twice. On the Mac test, the owner checks that:
  - the shortcut works while League has focus;
  - League's chat takes ⌘V, in game and in the post-game lobby;
  - each chat's length limit is what the closing line fits.
- **10.6:** the engine's tests, one per moment and threshold, including a pairing the roles estimator
  only guesses (no moment).

## Where the owner decides

1. **Where the engine lives (10.1).** Proposed: ported here, as "Where the engine lives" says.
   The roast lines become public with it. To keep them private instead, the lines file can live
   outside the repository, read from the app's folder, with a test set of lines in the repository.
2. **The shortcut (10.4).** Proposed: ⌃⌥C. The overlay's own shortcuts are ⌃⌥⌘L, and ⌃⌥ with 1 to
   5, F, D and R,[^app-delegate] and League binds Ctrl with the ability keys. It is a setting.
3. **Who the moments are about (10.6).** Proposed: friends only, with a setting for everyone.
4. **The Pact, the spice and the signature.** Proposed: the Pact off, spice 2 (Salty) by default,
   no signature.
5. **Speech.** Proposed: roasts and moments never spoken unless their own setting is on.
6. **The thresholds (10.6).** Proposed starting points in `tuning.json`, to tweak as games show:
   - a second solo death;
   - a death within 60 seconds of the enemy's objective;
   - 20 creep score behind at 10:00, 30 at 14:00.

[^owner-2026-10-28]: The owner's messages of 2026-10-28, in the session that built nothingsmyfault
[^nothingsmyfault]: nothingsmyfault: fact-cited case files for the last game (private)
[^first-recording]: A Practice Tool game, cancelled 0.05 s in, before any player loaded
[^recorder]: `src/leagueasymode/recorder.py`
[^game-state]: `src/leagueasymode/game_state.py`
[^global-hot-key]: `overlay/macos/Sources/LeagueasyOverlay/GlobalHotKey.swift`
[^app-delegate]: `overlay/macos/Sources/LeagueasyOverlay/AppDelegate.swift`
[^callouts]: `src/leagueasymode/inference/callouts.py`
[^update-check]: `overlay/macos/Sources/OverlayCore/UpdateCheck.swift`
[^engine-size]: Line counts of nothingsmyfault's source, 2026-10-28
