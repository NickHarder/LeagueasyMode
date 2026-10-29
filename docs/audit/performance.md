---
type: Audit Area
title: "Performance"
description: Measured cost of the engine's answer, the overlay stream, the page, the recording and the after-game send round, against the 0.5 s poll and the player's machine.
tags: [audit, performance]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T06:58:38Z }
---

# Performance

## Scope, and that this audit is late

The audit gate is meant to run before any product code exists. Here it runs late: the engine,
about 25 estimators, the SSE server, the page, the recorder and the sender are already built. So
every number below comes from the product's own code, run on built inputs.

**Where it was measured:** a Linux cloud container (Intel Xeon @ 2.10 GHz, 4 cores, Python 3.12
from the project's `.venv`, Chromium 1194 from Playwright). This is not the owner's Mac, which is
probably faster per core. No number here was taken on the real game.

**Inputs:**

- **A simulated 30:00 game.** `/tmp/perf/simgame.py` builds one answer per 0.5 s with
  `tests/game_payloads.py` `all_game_data`. Ten players' levels, CS, items and deaths go up over
  the game, and the event feed grows evenly to 300 events at 30:00 (kills, dragons, heralds,
  barons, turrets). One answer at 30:00 is 72,521 bytes of JSON. The item catalog is the real
  `items.json` (863 items), taken from the real recording. Patch stats come from
  `tests/data_dragon_fixtures.py`.
- **The only real recording**,
  `/home/user/leagueasymode-recordings/games/game-2026-10-28T00-11-38Z-anonymized.jsonl.xz`.
  It is a Practice Tool game cancelled after 0.05 s, so it holds **one** game snapshot. It shows
  how big the fixed client data is. It cannot show the cost of a game, or how fast a recording
  grows.
- **The limits of the simulation.** The built answers change less from one answer to the next
  than a real game does: champion stats, scores, abilities and runes are fixed. So the recording
  deltas below are a lower bound.

All the scripts are in `/tmp/perf/`. None is in the repository. Each is run from the repository
root with `.venv/bin/python`.

## Summary

| Probe | Measured | Against |
|---|---|---|
| One answer, end to end, at 25:00 to 30:00 | median 19.6 ms, p95 33.0 ms, max 58.7 ms | 500 ms poll (about 4%) |
| Slowest estimator | `build_path.next_item`: 5.84 ms of the 22.2 ms answer | about 26% of the engine |
| One SSE event | 24.7 kB, 2 per second (3,600 of 3,600 answers published) | localhost |
| Page, details key up / held | 2.6% / 3.3% of one core, 0 long tasks | 250 ms re-render |
| Recording, simulated | 67 kB per game minute plain; 2.87 MB to 118 kB with xz (4.1%) | disk |
| Recording, real | 884,430 bytes plain to 86,896 bytes xz; `items.json` alone is 678,980 | per game, fixed |
| After the game | scoring 24.7 s, then anonymizing 27.5 s, on worker threads | the next game's engine |
| Memory | traced heap 1.15 MB at 5:00, 1.78 MB at 15:00, 1.94 MB at 30:00 | bounded per game |

**Nothing measured comes near the 0.5 s budget.** The largest cost is the work after the game
(PERF-06), which grows with the game's length.

**Correction to a first run.** A first run had `tracemalloc` and later `cProfile` switched on. It
showed answers 5 to 10 times slower (a median of 104 ms with tracemalloc, 206 ms with the profiler
too), and its cProfile shares overstate the functions that make many small calls. The timings
above come from runs with both switched off. Where an estimator's share is given, it comes from
`perf_counter` wrappers (PERF-02).

## Findings

### [PERF-01] One answer costs about 20 ms late in a 30-minute game: 4% of the poll
- **Severity:** info
- **Location:** `src/leagueasymode/engine.py:538` (`_take_one_answer`), `src/leagueasymode/engine.py:75` (`compute_overlay_state`)
- **Reproduction:** `TRACE=0 .venv/bin/python /tmp/perf/run_engine.py 999999`. This drives a real `OverlayEngine` with every tracker through 3,600 answers (0:00 to 30:00), with the real item catalog and the fixture patch stats, and times each `_take_one_answer`. Output:
  ```
  ticks 0:00-5:00  : median 12.8 ms, p95 18.6 ms, max 40.8 ms
  ticks 25:00-30:00: median 19.6 ms, p95 33.0 ms, max 58.7 ms
  whole game total compute: 67.8 s for 1800 s of game
  ```
- **Impact on the project:** The engine keeps up with the poll with a wide margin, about 25 times
  the work it does now, on this slower host. The cost goes up about 1.5 times from early to late
  game (see PERF-03), and a 60-minute game was not measured.
- **Mitigation:** None needed now. Keep this script's number as a regression floor: a later phase
  that adds an estimator should run it again and keep p95 under about 100 ms.

### [PERF-02] The slowest estimator is the next-item guess, which scans the whole catalog for every player on every answer
- **Severity:** low
- **Location:** `src/leagueasymode/inference/build_path.py:118` (loops over `item_catalog.items_by_id.values()`), called from `src/leagueasymode/inference/players.py:168`; then `src/leagueasymode/inference/positions.py:202` (`point_chances`)
- **Reproduction:** `.venv/bin/python /tmp/perf/attribute.py`. This wraps each estimator in `perf_counter` and runs the same 30:00 game; the window is answers 3,001 to 3,600. Output (top):
  ```
  25:00-30:00, 600 answers: 22.2 ms per answer in _take_one_answer
    21.01 ms  compute_overlay_state
    10.36 ms  player_cards
     5.84 ms    in player_cards: next_item
     3.56 ms  GoldTracker.update
     3.37 ms    in player_cards: position_estimate
     2.10 ms  SightingTracker.update
     1.78 ms  GameSnapshot.model_validate
     1.37 ms  ClueTracker.update
     0.84 ms  JunglePathTracker.update
     0.30 ms  numbers_window
  ```
  The earlier cProfile run counted 5,178,000 `_is_candidate` calls in 600 answers: 863 per player
  per answer, every item in the catalog.
- **Impact on the project:** It takes a quarter of the engine's time to work out a result that can
  only change when a player's items or gold change.
- **Mitigation:** Deferred. Do it only if PERF-01's floor is threatened: index the catalog by
  component once per patch, or cache the result per (player, items, gold bucket).

### [PERF-03] The event feed is scanned again from the start on every answer, so the cost grows with the feed
- **Severity:** low
- **Location:** `src/leagueasymode/inference/gold.py:310`, `src/leagueasymode/inference/sightings.py:47`, `src/leagueasymode/inference/clues.py:74`, `src/leagueasymode/inference/objectives.py:234`, `:269`, `:309`, `src/leagueasymode/inference/structures.py:45`, `src/leagueasymode/inference/win_chance.py:333`. Each kill looks its players up with `GameSnapshot.player_named` (`src/leagueasymode/game_state.py:221`), which builds two sets for each player it checks (`game_state.py:144`).
- **Reproduction:** `.venv/bin/python /tmp/perf/events_scaling.py` (the 30:00 snapshot with feeds of different lengths):
  ```
    50 events: feed_gold   0.6 ms, kill_sightings   0.5 ms
   150 events: feed_gold   2.0 ms, kill_sightings   0.9 ms
   300 events: feed_gold   3.4 ms, kill_sightings   2.0 ms
   600 events: feed_gold   6.8 ms, kill_sightings   4.3 ms
  ```
- **Impact on the project:** Each answer costs time in proportion to the events so far, so over a
  whole game the cost is quadratic. A long, kill-heavy game (600 or more events) adds roughly 11
  ms per answer for these two scans alone. That is still well inside the budget.
- **Mitigation:** Deferred. If needed, fold events in as they arrive (event ids only go up), and
  index the players by name once per snapshot.

### [PERF-04] The engine computes on the event loop, and waits the whole poll after computing
- **Severity:** low
- **Location:** `src/leagueasymode/engine.py:545` (synchronous `compute_overlay_state` inside the async loop that also serves SSE and HTTP), `src/leagueasymode/engine.py:534` (waits `poll_interval_seconds` after the work, not from the start of the last poll)
- **Reproduction:** `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/opt/pw-browsers/chromium-1194/chrome-linux/chrome .venv/bin/python /tmp/perf/run_page.py` runs the real `OverlayEngine.run` with a 0.5 s poll for 20 s per phase. Output: `20.0 s wall, 38 answers taken`, which is 1.9 answers per second where the poll alone would give 2.0. PERF-01's max of 58.7 ms is the longest stretch during which the loop serves nothing.
- **Impact on the project:** Answers come every 0.5 s plus the compute time, so about 4% fewer than
  configured. While an answer is computed, a click to mark a cooldown (`/mark`) and the SSE write
  wait for up to about 60 ms. A player does not notice either today.
- **Mitigation:** Deferred. If the engine's cost grows, compute in `asyncio.to_thread` and
  schedule each poll from the start of the last one.

### [PERF-05] Every answer is pushed to the page: 24.7 kB twice a second; the page's work is small
- **Severity:** info
- **Location:** `src/leagueasymode/engine.py:594` (publishes whenever the state differs, which it always does, since `game_time_seconds` changes), `src/leagueasymode/overlay_server.py:518`; page: `overlay/web/src/overlay.ts:1329` (`render`), `:1351` (renders on each message), `:1362` (`setInterval(render, 250)`), and `replaceChildren` at `:394`, `:397`, `:746`, `:963`, `:1009`, `:1031`, `:1199`, `:1201`, `:1326`
- **Reproduction:** Size: `TRACE=0 .venv/bin/python /tmp/perf/run_engine.py 999999` printed
  ```
  states published: 3600 of 3600 answers (2.00 per second of game)
  SSE event at 1799s: 24752 bytes, serialize 0.21 ms
  SSE event at 60s: 18946 bytes, serialize 0.35 ms
  ```
  Page: `run_page.py` (above) opens the real page in headless Chromium at 1920x1080, fed by the
  engine at about 28:00. It reads CDP `Performance.getMetrics` over 20 s, counts nodes added and
  removed with a `MutationObserver`, and records long tasks:
  ```
  details held=False: script 119 ms, layout 155 ms (116 layouts), style 73 ms (116), task 527 ms => 2.6% of one core
    DOM nodes now 772; nodes added+removed 3364 (168/s); JS heap 1.3 MB; long tasks >50ms: 0
  details held=True: script 140 ms, layout 222 ms (118 layouts), style 54 ms (118), task 668 ms => 3.3% of one core
    DOM nodes now 1828; nodes added+removed 5481 (274/s); JS heap 1.4 MB; long tasks >50ms: 0
  ```
- **Impact on the project:** The stream is about 49 kB/s, or about 89 MB in a 30-minute game, all
  on localhost. The page renders about 6 times a second (4 on the timer and 2 on messages) and
  rebuilds its widgets each time. That costs 3% of a core and no frame over 50 ms in Chromium.
  WKWebView on the Mac was not measured, and League itself shares that machine's GPU and CPU.
- **Mitigation:** None needed. If the page is ever profiled on the Mac and found to cost frames,
  render only when the state or a running timer changes, and patch the DOM instead of replacing
  it.

### [PERF-06] After each game, scoring and anonymizing take about 52 s of CPU, and the next game's engine runs slower meanwhile
- **Severity:** medium
- **Location:** `src/leagueasymode/cli.py:664`, `:668` (`read_recorded_game` and `score_game` replay the recording through the trackers), then `src/leagueasymode/cli.py:276` calls `send_unsent`, which runs `src/leagueasymode/recording/sender.py:373` (`anonymize_recording`). `src/leagueasymode/recording/anonymize.py:204` reads the file twice to collect identities and once more to write it (`:346`), and every delta is replayed with `copy.deepcopy` (`src/leagueasymode/recording/delta.py:90`). The upload is one base64 PUT (`sender.py:399`) with a 120 s timeout (`sender.py:55`).
- **Reproduction:**
  - `.venv/bin/python -c "...runpy.run_path('/tmp/perf/run_recording.py')..."` writes the 30:00 game with `RecordingWriter`, compresses it and anonymizes it:
    ```
    anonymize_recording: 27.5 s -> 117336 bytes; base64 upload body ~156448 bytes
    max RSS MB 79.8984375
    ```
  - `.venv/bin/python -c "from leagueasymode.scoring import read_recorded_game; ..."` on the same file: `read_recorded_game: 24.7 s, 31 minute snapshots`.
  - cProfile of `anonymize_recording`, by own time: `copy.deepcopy` 20.3 s, `IdentityMap.leaks_in` 16.3 s, `find_identity_leaks` 9.6 s, `delta._collect_operations` 9.2 s (the profile runs about 4.6 times slow).
  - `.venv/bin/python /tmp/perf/gil.py` (the engine at about 28:00, alone and then with `anonymize_recording` in `asyncio.to_thread`, as the sender runs it):
    ```
    alone:             median 18.3 ms, max 44.1 ms
    during anonymize:  median 45.1 ms, max 96.1 ms
    ```
- **Impact on the project:** The anonymized game reaches the repository about a minute after the
  game ends, and later for a longer game, since both steps grow linearly with its length. The two
  steps run on threads but hold the GIL. If the next game starts within that minute, its engine
  runs 2.5 times slower until they finish. That is still within the poll. The upload is small
  (about 156 kB), so its time depends on the network, not on the code.
- **Mitigation:** A later phase should keep the send round from running while a game is running,
  and make the anonymizer do one pass without `deepcopy` (apply patches in place on a private
  copy). Before that, measure it on a real full-length recording, which does not exist yet.

### [PERF-07] Recordings grow by about 67 kB of plain text per game minute, and xz shrinks them about 24 times
- **Severity:** info
- **Location:** `src/leagueasymode/recording/writer.py:79` (keyframe every 60 s, otherwise a delta), `:163` (each line flushed), `:183` (xz preset 6 at close)
- **Reproduction:** `run_recording.py` (above):
  ```
  client answers at start: 868830 bytes
  plain size at minute: {10: 1358016, 20: 2025747, 30: 2872612} -> snapshots only 67 kB per game minute
  plain total 2872690 bytes; compressed 117824 bytes; ratio 0.041
  write_snapshot: 0.87 ms each on average; close+xz: 0.58 s
  ```
  The real recording: `xz -l` gives `84.9 KiB  863.7 KiB  0.098`, and a breakdown of its lines
  gives `678980 /lol-game-data/assets/v1/items.json` out of 884,430 bytes, with 1 snapshot in
  0.053 s.
- **Impact on the project:** A 30-minute game is about 3 MB on disk while it is played, and about
  120 kB once closed (simulated). About 0.87 MB per game is client data that is the same in every
  game of a patch, and most of it is `items.json`. Real games change more per answer, so expect
  real recordings to be larger than this.
- **Mitigation:** None needed. Measure again on the first real full game. If storage or upload
  matters, record `items.json` once per patch rather than once per game.

### [PERF-08] Memory does not grow without bound over a game
- **Severity:** info
- **Location:** The trackers keep a dictionary keyed by player and clear it when a new game's clock starts, for example `src/leagueasymode/inference/wards.py:57`. The lists that grow during a game are small: `wards.py:67` (`placed_at_seconds`) and `jungle_path.py:262` (bursts; the paths are cut to the beam width at `jungle_path.py:330`). `src/leagueasymode/engine.py:338` (`seen_identities`) grows by about 30 names per game for as long as the app runs.
- **Reproduction:** `TRACE=1 .venv/bin/python /tmp/perf/run_engine.py 3001` printed `traced python heap (MB): {300.0: 1.15, 900.0: 1.78, 1800.0: 2.06}`; another run without the profiler printed `{300.0: 1.15, 900.0: 1.78, 1800.0: 1.94}`. The search was `grep -n "\.append(\|..." src/leagueasymode/inference/*.py`.
- **Impact on the project:** None at today's sizes: under 1 MB of growth over 30 minutes, and it
  goes away when the next game starts.
- **Mitigation:** None.

### [PERF-09] The engine and the recorder each ask the game for the same answer
- **Severity:** info
- **Location:** `src/leagueasymode/engine.py:540` and `src/leagueasymode/recorder.py:354`. `src/leagueasymode/cli.py:212` and `:286` start both with `settings.poll_interval_seconds`.
- **Reproduction:** `grep -n "fetch_all_game_data" src/leagueasymode/engine.py src/leagueasymode/recorder.py` gives `engine.py:540` and `recorder.py:354` (plus `recorder.py:320`, which runs while it waits for a game). The parse is cheap: `JSON_VALUE_ADAPTER.validate_json` of the 72,521-byte 30:00 answer takes 0.46 ms.
- **Impact on the project:** League's local API gets 4 requests a second instead of 2. The
  recording can also hold an answer the overlay never showed, and the other way round. What this
  costs League's own process was not measured.
- **Mitigation:** Deferred. Make it one poller that feeds both, if a later phase needs the
  recording to match exactly what was shown.

## Not measured, and why

- **WKWebView on macOS, and League running at the same time.** No Mac is reachable from this
  container. Chromium stands in for the page (PERF-05).
- **A real full-length game.** The only real recording lasts 0.05 s.
- **Upload time to GitHub.** No network request was made. Only the body size is given (PERF-06).

Noted for the data-quality and security areas, not for performance: running `anonymize_recording`
on the already-anonymized real recording fails with `IdentityLeakError`, because pseudonyms such as
`1` and `anonymous-puuid-1` match ordinary values in the gameflow session.
