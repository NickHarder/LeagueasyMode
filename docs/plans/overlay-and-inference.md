---
type: Plan
title: "Plan v2: a macOS overlay built around inference"
description: The plan the owner approved on 2026-10-08, word for word, for turning LeagueasyMode into a macOS overlay with an inference engine fed only by League's local APIs.
tags: [plan, overlay, inference]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-08T13:23:21Z }
approved_by_owner_in_session: 2026-10-08
---

# LeagueasyMode plan, v2: a macOS overlay built around inference

What changed from v1: it's now an overlay drawn on top of the game, not a second screen. The core is a set of estimators that reconstruct what the game hides. Every estimator is scored against what actually happened, after every game. Nothing from the old rules or metrics carries over by default.

## What you'd see

This layout is a first draft for your notes. It's a transparent layer over League that clicks pass through and that never takes focus from the game.

- **Objective strip:** timers for dragon, grubs, herald, Baron and Elder, plus the dragon soul race, each team's Baron or Elder buff time left, and inhibitor respawns.
- **Enemy strip:** for each enemy, their level and how far they are to the next one, estimated unspent gold and likely next item, "last known area, N seconds ago", and their death timer.
- **Minimap layer:** lined up with League's minimap, it shades where the enemy jungler (or any enemy you pick) probably is, and puts objective timers next to the pits.
- **Callouts:** short facts, with optional voice. For example, "Enemy jungler likely top side (70%)" or "4 enemies dead for 18s".
- **You panel:**
  - how long you've been holding unspent gold
  - whether armor or magic resist buys more survivability against their damage mix
  - your CS pace against your own history
- **Post-game window:** the game reconstructed, plus how accurate each estimator was.

You move the widgets around after switching on edit mode from the menu bar. A hotkey shows or hides the overlay, and it needs no macOS permissions.

## Data sources, all on your Mac

| Source | What it gives | When |
|---|---|---|
| The game's API (`127.0.0.1:2999`) | the scoreboard for all ten players, your exact stats and gold, the kill and objective feed | live |
| The League client's local API | this patch's item, champion and spell data; the game's id; **after the game, the match timeline** | patch data at start, timeline after |
| League's settings file | resolution, HUD scale, minimap size and side | placing the overlay |

The match timeline has every player's position, gold, XP and CS each minute, every purchase, every kill's position, and ward placements (time only).

There's no screen capture and no reading of game memory. The engine only ever talks to `localhost`; the client fetches the timeline from Riot itself.

The timeline is the key addition: it's ground truth. Every game you play becomes labeled data, comparing what each estimator said at 12:00 with where everyone actually was and what they actually had. The estimators are tuned on that, and their accuracy is a tested number.

## The inference engine

The game's API never gives positions, never gives anyone else's gold, and never says who is visible. So the engine turns changes in the scoreboard into timed clues:

- **Inventory changes:**
  - A new item means they were in base (items that upgrade in place don't count).
  - The control ward count dropping means they placed one.
  - An elixir disappearing means it was drunk.
  - A potion being used means they're probably trading.
- **Items that transform at fixed thresholds:** the support item's quest steps (gold earned), the jungle pet's evolutions (camps taken), Tear turning into Manamune. Each one pins a hidden counter to an exact value.
- **CS ticks:** a laner gaining CS is in lane near a wave. A burst of jungle CS is a camp.
- **Level-ups:** the exact moment someone crossed an XP threshold.
- **Kills, objectives and structures:** everyone named was at that place at that moment. A death to a turret or monster pins the exact spot.
- **Deaths and respawns:** in the fountain at a known time.
- **Nothing changing while alive:** weak evidence that they're moving, roaming or waiting.

| # | Estimator | Method | Output | Scored against (from the timeline) |
|---|---|---|---|---|
| 1 | Roles | optimal assignment (Hungarian algorithm) over Smite, support item, summoner spells, CS pattern and champion class | each enemy's role, even in blind pick | timeline roles |
| 2 | Combat stats | champion base stats plus per-level growth, plus item stats (exact); runes approximated | HP, armor, MR, AD, AP, attack speed and move speed for all ten | your own exact stats, live |
| 3 | Hidden gold | a filter per enemy: an income model (passive gold, minion gold by wave type, kill bounties, assists, objectives), corrected by what they've bought and by item thresholds; the income model is tuned live on your own exact gold | unspent and total gold with an error band; the chance they can afford a given item | gold per minute for all ten |
| 4 | Hidden XP | the same structure for XP (shared minion XP, monsters, kills weighted by level gap) | how far to the next level; when they'll reach 6, 11 and 16 | XP per minute |
| 5 | Build path | the patch's item recipe tree, plus their components, plus champion class, plus your past games as a prior | likely next finished item, and when their estimated gold reaches it | purchase events |
| 6 | Backs | inventory changes plus respawn logic | "went back at 7:42", when they'll be back in lane | purchase timestamps |
| 7 | Positions | a particle filter per enemy over a hand-built map of the Rift (about 150 points); movement from move speed, role and travel times; updated by every clue above | probability by map region, how confident "missing" is, earliest arrival time anywhere | positions per minute, kill positions |
| 8 | Jungle path | a hidden Markov model (Viterbi decoding) over the camp map: CS bursts as evidence, travel times and camp respawns as constraints | likely clear order, which side of the map they're on, likely next camp | positions and jungle CS per minute |
| 9 | Control wards | when the ward count drops, combined with where the filter thinks they were at that moment | likely areas of enemy control wards | ward placement times |
| 10 | Fights | combat stats turned into survivability × sustained damage per side (Lanchester-style), tuned by logistic regression on your recorded fights | chance of winning an even fight now; team strength over time | fight outcomes from clusters of kills |
| 11 | Objective contest | the objective's health at that time ÷ your team's damage, against each enemy's arrival time (from #7) and respawn timer | chance the enemy contests before it dies | objective kills and steals |
| 12 | Win chance | logistic model over gold, XP, structures, objectives, players alive and time; starts hand-set, then refit on your games | win % over the game | game results |
| 13 | You | survivability per gold for armor vs MR against their damage mix; time spent holding gold; CS pace | facts about your build and pace | none |

The engine stores each estimator's accuracy per game. CI fails if any estimator drops below its threshold on the recorded games. The thresholds get set from the first batch of recordings and are never lowered to make a test pass.

**Known limits:**
- With no positions or visibility, position estimates stay wide unless an event has just pinned someone.
- Minion wave state can't be inferred.
- For enemies, ability ranks and runes beyond the keystone are unknown.
- Field names and event details get checked against your first recordings.

## Policy

Every module is tagged one of three ways:
- **Exact:** it restates the scoreboard or kill feed.
- **Estimate:** it reconstructs hidden state.
- **Excluded:** never built.

A strict mode hides every estimate during the game; the post-game window shows everything.

Always excluded:
- enemy ultimate and summoner spell cooldowns, including guessing Flash or Teleport from impossible movement
- instructions like "go gank"

The jungle path estimator also implies which enemy camps are down. Riot cut back what players can learn from dead camps in patches 25.17–25.18, so showing those respawn timers is the most likely thing to be prohibited, and it stays off unless you decide otherwise.

## How it's built

```
League ── game API ───┐
       ── client API ─┤
                      ▼
  engine (Python, runs as a child process of the app)        overlay app (Swift, menu bar)
  poll → recorder → model → clues → estimators → facts ──► 127.0.0.1 ──► web view inside a transparent,
                     ▲                                                       click-through window
            replay (a fake game API) for development and tests
```

- **The engine is Python:** numpy for the filters, strict type checking, pytest and your kit's gate. I can build and test all of it here against recorded games.
- **The overlay is a small Swift app**, about 300 lines:
  - The window sits above the game, never takes focus, lets clicks through, and is set to appear over fullscreen apps.
  - It lives in the menu bar.
  - Hotkeys use the old Carbon API, so no Accessibility permission is needed.
  - It starts the engine and can launch at login.
- **The widgets are TypeScript and HTML** inside that window. I can render and screenshot them here with the pre-installed Chromium against replays, and you can tune the look without touching Swift.
- The engine listens on `localhost` only. The Swift app builds and runs its tests on GitHub's macOS runners, which are free for a public repo.

Why not all Swift? It would be lighter at runtime, but this environment has no Swift toolchain and can't reach swift.org to get one. I'd be writing it blind and waiting on CI for every compile. If the tracer bullet shows the web view costs FPS or CPU, the widgets move to SwiftUI and the engine stays as it is.

## Phases

Each phase lands as small vertical slices, tests first.

0. **Setup, and data first:**
   - You unarchive the repo.
   - I make a branch, set it up from ai-kit's template with the Python layer, and add CI (Linux for the engine, macOS for the Swift app).
   - I write a standard-library-only recorder you can run right away; it also saves the post-game timeline.
   - Recordings are anonymized (Riot IDs replaced) before anything goes into the public repo.
1. **Tracer bullet: the dragon timer drawn over League.** It's the Swift window, the engine and one widget. You try it in Practice Tool in fullscreen, borderless and windowed, and watch FPS and focus. This answers the biggest risk first: whether macOS lets us draw over League cleanly.
2. **Model, patch data and exact facts:** objectives, death windows, structures, item and level spikes, roles (#1), combat stats (#2).
3. **Hidden economy:** gold (#3), XP (#4), build path (#5), backs (#6), and the scoring harness against timelines.
4. **Positions:** the map, the particle filter (#7), jungle path (#8), control wards (#9), the minimap layer.
5. **Models tuned on your games:** fights (#10), objective contest (#11), win chance (#12). These need a few dozen recorded games.
6. **The post-game window** and accuracy history.
7. **Packaging:** a signed app, auto-update, settings.

## Decisions

**Before I start:**
1. **Unarchive the repo** (GitHub → Settings → General → Danger Zone).
2. **Can the engine use the client's post-game timeline as ground truth?** I recommend yes. Without it, accuracy can only be checked against your own stats. Whether the client serves it gets confirmed on your Mac in phase 0.
3. **Stack:** Python engine + Swift app + web widgets (recommended), all Swift, or all Python (using PyObjC for the window).

**Before phase 1 runs on your Mac:**

4. **Which estimates may show during a game:** all of them, exact facts only, or a list you pick. This depends on Riot's current policy. Either you read it, or you add `developer.riotgames.com` and `support-leagueoflegends.riotgames.com` under Allowed domains in this environment's network settings and I'll summarize it.

**Later:**

5. **Signing:** giving the app to other people without macOS security warnings needs the $99/year Apple Developer Program. You don't need it for your own use.
6. **Scouting:** the client API can fetch enemies' recent games, which would be a strong prior for jungle paths and builds. I recommend not doing this for now, for policy and privacy reasons.

From v1, I'm taking these as approved: the client API for patch data, ai-kit's scaffolding, and recording your games as test data. When you say go, I'll commit this plan word for word to `docs/plans/` alongside phase 0.

Sources: [Mein-MMO on Riot's jungle timer changes](https://mein-mmo.de/en/riot-update-lol-zugeben-spiel-viel-zu-leicht,1522961)
