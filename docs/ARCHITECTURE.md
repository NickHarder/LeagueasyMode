---
type: Architecture
title: Architecture
description: How LeagueasyMode is built, from League's local APIs through the Python engine to the overlay drawn over the game, with its trust boundaries, failure behavior, deviations from the plan, and each capability traced to a use case, an audit finding and a key metric.
tags: [architecture]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T21:40:32Z }
---

# Architecture

Written after the product, as the audit was ([AUDIT.md](AUDIT.md), ARCH-01): it describes the
system as built and checked on 2026-10-29, against the approved plan
([plans/overlay-and-inference.md](plans/overlay-and-inference.md), which stands in for the kit's
`PLAN.md`) and the users ([USERS.md](USERS.md)).

## 1. Summary

LeagueasyMode is three programs on one Mac. A Python engine reads League's local APIs, works out
what the scoreboard hides, and serves the result on 127.0.0.1. A Swift menu-bar app starts the
engine, draws a transparent window over League's window, and shows the engine's page in a web
view inside it. The page, written in TypeScript, draws the widgets. Nothing reads the screen,
nothing sends input to the game, and the engine talks only to 127.0.0.1, Data Dragon and, for
anonymized recordings, the owner's private GitHub repository.

The engine polls the game's API every half second. Each answer becomes a typed snapshot; the
estimators turn changes in it into clues and estimates (gold, experience, items, backs, positions,
the jungle path, wards, fights, contests, the win chance); the engine folds them, with the exact
facts, into one overlay state and pushes it to the page over server-sent events. The page keeps no
state of its own beyond the key held and the layout being dragged: the engine owns preferences
and layout and writes them to disk. One answer costs about 20 ms of the 500 ms budget (PERF-01).

The decisions that shaped it, all approved with the plan or by the owner since: a Python engine,
because its estimators are built and tested where Swift cannot run, against recorded games; a
thin Swift app, because only native code can float a window over League and read keys without an
Accessibility prompt; web widgets, because they render and are tested in Chromium here. The
contract between engine and page is a pydantic model with a generated JSON schema; the page's
type guards mirror it.

Ground truth is the match timeline the League client gives after each game. Every recorded game
is scored against it, estimator by estimator, into an accuracy history; the key metrics read that
history ([KEY_METRICS.md](KEY_METRICS.md)). That is also the design's largest blind spot today:
only one real recording exists, cancelled at 0:00 (DQ-01), so every estimator is a hand-set guess
until the owner's games arrive.

Since the owner's first real games the design leans hard toward restraint. At a glance the overlay
shows timers, the newest two callouts that ask for an action, and one short line an enemy; the
details, the Tab overview and the spell buttons show only while Tab or Option is held or the player
is dead, and only then does the window take a click. Off Summoner's Rift, the Rift's timers,
roles and models are left out. These came from the owner's own words, not the plan, and the
deviation register records them.

The tradeoffs accepted: a web view costs more than native drawing (measured small: 3% of a core);
the engine recomputes everything on every answer rather than incrementally (PERF-03), which is
simpler and well within budget; updates are installed from unsigned builds (SEC-01), acceptable
for one user and not for a public download; and enemy ultimate marks stay, against the risk Riot's
2025 rule carries (CMP-01), by the owner's decision.

## 2. Trust boundaries

| Boundary | What crosses it | Who enforces it |
|---|---|---|
| League's game API → engine | The game's answers, over TLS | The engine pins Riot's root certificate (`riot_tls.py`); pydantic validates every answer (`game_state.py`) |
| League client → engine | Player records, timelines, patch data | The lockfile's password and the pinned certificate (`league_client.py`) |
| Data Dragon → engine | Each patch's stats | HTTPS with the system's store (`truststore`); kept on disk per patch |
| Engine → page | The overlay state, over SSE on 127.0.0.1 | Binding to 127.0.0.1; the Host check against DNS rebinding; the request header on every route that changes state (SEC, "checked, holds") |
| Page → app | Speech, click regions | Two WebKit message handlers only; the panel takes a click only over a reported button |
| Mac → recordings repository | Anonymized games, crash and problem reports | The anonymizer fails closed (`anonymize.py`), with a known gap (CMP-05); a token in the Keychain, never written or logged |
| Mac → `claude` CLI | Wording and style only, opt-in | Placeholders for every name and number (`claude_take.py`; CMP-08) |
| GitHub releases → app | New builds | A SHA-256 from the same release: integrity, not authenticity (SEC-01) |

## 3. Data flow: one answer, end to end

1. The engine's poll (`engine.py`, `OverlayEngine.run`) asks `GET /liveclientdata/allgamedata`
   on 127.0.0.1:2999 (`game_api.py`); the recorder asks the same, separately (PERF-09).
2. `game_state.py` validates the answer into a `GameSnapshot`.
3. `compute_overlay_state` (`engine.py`) runs the trackers (gold, experience, backs, clues,
   jungle path, wards, sightings) and the estimators under `inference/`, with the patch's stats
   (`patch_data.py`) and the players' records (`player_intel.py`), into an `OverlayState`
   (`overlay_state.py`).
4. The callouts tracker, the moments and the team calls add their callouts; the engine adds the
   preferences and the layout, and publishes the state if it changed.
5. `overlay_server.py` sends it as one SSE event on `/events`.
6. The page (`overlay/web/src/overlay.ts`) validates it with its type guards (`state.ts`) and
   draws the widgets four times a second, at a glance or with details as the key and the
   player's death say (`areDetailsShown`).
7. The Swift panel (`OverlayPanel.swift`) shows the page over League's window, tells it when Tab
   or Option is held (`DetailsKey`), and takes a click only over a spell button.
8. After the game the recorder closes the recording with the client's timeline, the engine scores
   it into the accuracy history, and the sender sends an anonymized copy.

## 4. Verification design

- **The gate** (`make gate`): ruff, mypy strict, the project's Python rules, the knowledge bundle,
  1,079 unit tests, a secrets scan; on every push and in CI.
- **The page in Chromium** (`uv run pytest -m browser`, 80 tests): the real engine serving a
  replay of a built recording, the page driven by Playwright.
- **The Swift app on macOS runners**: `swift test` for `OverlayCore`, and the built bundle started
  from an empty home folder (`smoke_test_app.sh`).
- **Accuracy**: each recorded game scored against its timeline (`scoring.py`), kept in the
  accuracy history; CI holds the recorded games in `tests/fixtures/recorded-games/` to
  `tests/accuracy_thresholds.json`.

Blind spots: the recorded-games test passes over none (ARCH-09); the built payloads differ from a
real game in shape (DQ-05); nothing runs over a real League window except on the owner's Mac;
`AppDelegate.swift` has no tests (ARCH-03); WKWebView's cost on the Mac is not measured (PERF-05).

## 5. Failure behavior per dependency

| Dependency | Down | Slow | Wrong |
|---|---|---|---|
| The game's API | No game: the overlay hides; the status page says "no game is running" | The overlay lags by the delay; the page interpolates timers between answers | A field missing becomes a plausible default (DQ-04); an unknown map counts as the Rift |
| The League client | No ranks, records or timeline; the status page says so; the overlay shows the rest | Lookups wait; the overlay never waits on them | A record in another shape shows nothing for that player, not a guess |
| Data Dragon | The last patch on disk is used; combat stats and next items wait | Loaded in the background | Growth of 0 since 16.5.1 is borrowed from 16.4.1 |
| The engine | The app restarts it, up to 5 times in 10 minutes; a crash report is written | The page keeps the last state and counts its timers down | A crash on one estimator stops the whole answer until fixed (as on 2026-10-29) |
| The web view | The app reloads the page when its process stops | (not measured on the Mac) | — |
| GitHub | Games and reports wait on the Mac; the next round retries; open recordings are closed after 20 minutes | — | A refused token stops the round; the status page says so |

## 6. Speed against completeness

The budget is one answer within the 500 ms poll, so that a fact on screen is at most a second
behind the game (P-01's tolerance). Measured: 20 ms late in a game, p95 33 ms (PERF-01). To stay
there the engine drops nothing today; it keeps two things for later if the budget tightens: the
next-item guess over the whole catalog (PERF-02) and the rescan of the event feed (PERF-03). What
it does drop is on the page's side: at a glance most of what is computed is not drawn.
Completeness is traded after the game, not during: scoring and anonymizing take about 52 s of CPU
and run in threads while the next game may start (PERF-06).

## 7. Deviation register

| Id | The plan said | Reality (evidence) | Substitute |
|---|---|---|---|
| DV-01 | Always excluded: enemy ultimate and summoner spell cooldowns (Policy) | The owner, 2026-10-08 and 2026-10-28: "everything is allowed"; "dont listen to rumors" (HANDOFF.md, Settled) | Manual marks (⌃⌥ keys, a click), shown as estimates; risk recorded (CMP-01) |
| DV-02 | Scouting enemies' past games: not for now (Decision 6) | The owner approved phase 9 on 2026-10-09 | Records read through the client's own session, ~70 requests a game |
| DV-03 | Packaging: a signed app (phase 7) | The owner chose no signing (phase 7 plan, approved) | Ad hoc signature, "Open Anyway" once, auto-update from prereleases (SEC-01) |
| DV-04 | Recordings anonymized before going into the public repo | The owner: a private repository (2026-10-28) | `NickHarder/LeagueasyMode-recordings`, anonymized copies only |
| DV-05 | The kit's gate order: audit, personas, architecture before the build | The audit and this document were written after the product (ARCH-01) | Findings are backlog items, each with a slice |
| DV-06 | Every estimate shown during a game, with a strict mode to hide them | The owner: "too much visual clutter", "maybe extra details onyl show if i hit tab" (2026-10-29) | At a glance: timers, two callouts, one line an enemy; the rest on Tab or Option only, not while dead (augments, shop) |
| DV-07 | Summoner's Rift only | The owner plays mostly ARAM and Swiftplay (USERS.md, P-01) | Off the Rift: no roles, inhibitor timers only, the Rift's models hidden (UC-09) |
| DV-08 | Hotkeys with Carbon, no Accessibility permission | Tab and Option are read with `CGEventSource` and `NSEvent.modifierFlags`; whether Tab needs Input Monitoring is not yet seen | Option works without it |

## 8. Traceability matrix

| Use case | Capability | Data | Audit finding | Eval category | Metric |
|---|---|---|---|---|---|
| UC-01 | Loading-screen intel; the Tab overview | Client ranked stats, match history | DQ-06, CMP-03 | exact facts | — |
| UC-02 | Positions, jungle path, minimap layer | Game API scoreboard and events | ARCH-05, DQ-01 | estimates | DR-02 |
| UC-03 | Marked cooldowns, R rank | Player's marks, patch cooldowns | CMP-01, ARCH-07 | exact facts | — |
| UC-04 | Objective timers, contests, numbers window | Event feed, death timers | DQ-07 | estimates | DR-04 |
| UC-05 | Fights, win chance, item lead | Combat stats, Data Dragon | PERF-02 | estimates | DR-03 |
| UC-06 | Layout: drag, resize, sliders, opacity, hide, HUD | `layout.json` | ARCH-04 | glance | GR-02 |
| UC-07 | Problem reports, crash reports | Engine log, status, recordings list | SEC-02, CMP-07 | privacy | GR-01 |
| UC-08 | Recording, sending, scoring, post-game window | Recordings, timeline | DQ-02, PERF-06, CMP-05 | privacy | DR-01 |
| UC-09 | Off-the-Rift rules | `mapNumber` | DQ-03 | off the Rift | NS-01 |

## 9. Tracer bullet

Built on 2026-10-08 and confirmed on the owner's Mac on 2026-10-28: the dragon timer drawn over
League. It crosses every layer: the game's API, the snapshot, an estimator (the dragon timer), the
overlay state, SSE, the page, the Swift panel over League's window. The proving commands:
`uv run leagueasymode replay <recording>` with `uv run leagueasymode run` against it, and
`uv run pytest -m browser tests/test_overlay_page.py -k dragon`.

The slices that followed are the plan's phases 2 to 11 and the layout plan, all merged. The next,
from the audit: one full Rift game recorded, with its timeline, as the replay fixture (DQ-01);
then the loading-screen fixes (DQ-02, DQ-03); then the anonymizer's game-content keys (CMP-05).

## 10. Cut order

First to go if time runs short: the roasts (phase 11), then the post-game window's narrative, then
the minimap layer's camps and wards, then the win chance. Never cut: the overlay taking no click at
a glance, the keyboard always the game's, nothing of another player's name leaving the Mac, the
recording and its timeline (without them nothing can be measured), and the gate.

## 11. Not built

- **A strict mode that hides every estimate** (plan, Policy): replaced by details on a key.
- **Enemy camp respawn timers by default**: off since the plan, for Riot's 25.17 change.
- **Spell casts detected by themselves**: the game's API reports none (ARCH-07).
- **Reading the screen or game memory**: ruled out by the owner (AP-01).
- **A signed update channel and Riot registration**: deferred until a public download (SEC-01,
  CMP-03).
- **SwiftUI widgets**: the plan's fallback if the web view cost FPS; it costs 3% of a core.
