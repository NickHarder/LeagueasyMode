---
type: Audit Area
title: "Architecture"
description: How the engine, the widgets and the macOS app are layered, where each file on the Mac is written, which League APIs the code relies on and which of them a real recording has confirmed, and how the engine-to-page contract is held.
tags: [audit, architecture]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T06:46:49Z }
---

# Architecture audit

**This audit is late.** The audit gate comes before any product code. Here the product code
already exists. The findings below describe live code at `003aeb6`, not a design still to come
(ARCH-01). Every reproduction was run in this repository on 2026-10-29, and the output quoted is
what came back. The real recording was only read from `/home/user/leagueasymode-recordings/games/`.

## What holds

| # | Probe | Result |
|---|---|---|
| 1 | `inference/`, `roast/` and `recording/` do not import `engine`, `overlay_server`, `cli` or `recorder` | **Holds.** The grep finds nothing (exit 1). |
| 1 | No import cycles | **Holds.** 87 modules, and `graphlib` orders them all. |
| 3 | Nothing pretends to know enemy cooldowns | **Holds** (ARCH-07). |
| 4 | Pydantic model → `overlay_state.schema.json` | **Holds.** A test checks it, and the regenerated schema diffs clean. |
| 4 | Schema → `state.ts` interfaces | **Holds today.** The fields of all 37 objects match. The check is by hand, though (ARCH-08). |
| 4 | Committed `overlay_web/*.js` is the compiled TypeScript | **Holds.** `tsc` into a scratch folder gives files identical to the committed ones. CI checks this too. |
| 5 | Layout and preferences: one owner | **Holds.** The engine owns both. The pages `GET` and `PUT` them, and nothing uses `localStorage`. Swift keeps no copy. Only update checks and "shown how-to-use" live in `UserDefaults`. |

Reproductions for the rows that hold:

```sh
grep -rlE "from leagueasymode\.(engine|overlay_server|cli|recorder)\b" src/leagueasymode/inference src/leagueasymode/roast src/leagueasymode/recording; echo "exit=$?"   # exit=1
.venv/bin/python -c "import ast,pathlib,graphlib
r=pathlib.Path('src');g={}
for p in r.rglob('*.py'):
  m='.'.join(p.relative_to(r).with_suffix('').parts).removesuffix('.__init__')
  g[m]={n.module for n in ast.walk(ast.parse(p.read_text())) if isinstance(n,ast.ImportFrom) and (n.module or '').startswith('leagueasymode')}
graphlib.TopologicalSorter(g).static_order();print(len(g),'modules, no cycle')"   # 87 modules, no cycle
.venv/bin/python -m leagueasymode.overlay_state | diff -q - overlay/web/overlay_state.schema.json && echo same   # same
(cd overlay/web && ./node_modules/.bin/tsc -p tsconfig.json --outDir "$SCRATCH/tsout") && diff -rq "$SCRATCH/tsout" src/leagueasymode/overlay_web   # only non-JS files listed as "Only in"
```

## Layout

| Layer | Where | Largest files (`wc -l`) |
|---|---|---|
| Inputs | `game_api.py` (Live Client), `league_client.py` + `player_intel.py` + `patch_data.py` (League client), `data_dragon.py` | `data_dragon.py` 835, `player_intel.py` 743 |
| State | `game_state.py` (Riot payload models), `overlay_state.py` (wire contract) | `overlay_state.py` 751 |
| Estimators | `inference/` (24 modules) | `gold.py` 1039, `callouts.py` 828 |
| Orchestration | `engine.py`, `overlay_server.py`, `cli.py` | `cli.py` 1152, `engine.py` 774, `overlay_server.py` 587 |
| After the game | `recorder.py`, `recording/`, `scoring.py`, `roast/` | `scoring.py` 1780, `roast/client_timeline.py` 923 |
| Widgets | `overlay/web/src/*.ts` → `src/leagueasymode/overlay_web/*.js` | `overlay.ts` 1362, `state.ts` 1029 |
| macOS app | `OverlayCore` (pure, tested) + `LeagueasyOverlay` (AppKit) | `AppDelegate.swift` 998 |

## Where data lives on the Mac

The application directory is `~/Library/Application Support/LeagueasyMode`
(`src/leagueasymode/config.py:20`). Each setting in `config.py` can move its file.

| File | Writer | How |
|---|---|---|
| `preferences.json`, `layout.json` | `preferences.py:41`, `:69` via `_write_whole` (`:79`), called from `overlay_server.py:346`, `:365` | fixed `.partial` + rename |
| `friends.json` | `friends.py:83` | fixed `.partial` + rename |
| `tuning.json` | `tuning.py:117` `write_tuning` | `mkstemp` + rename |
| `claude-take.json` | `roast/claude_take.py:351` | fixed `.partial` + rename |
| `model-weights.json` | `refit.py:169` | fixed `.partial` + rename |
| `accuracy-history.jsonl` | `accuracy_history.py:93`. The whole history is rewritten for each game. | fixed `.partial` + rename |
| `last-game.json`, and the roast beside it | `cli.py:675` via `cli.py:847` `_write_whole` | fixed `.partial` + rename |
| `patch-data/<patch>/` | `data_dragon.py:521`, `:828` | `mkstemp` + rename |
| `recordings/*.jsonl` → `*.jsonl.xz` | `recording/writer.py` (append, then `compress_recording` `:166`) | `.partial` + rename |
| `recordings/sent-games.json` | `recording/sender.py:52`, `:494` | `mkstemp` + rename |
| `recordings/crash-reports/` | `crash_reports.py:161`, directory from `cli.py:981` | direct write |
| `recordings/reports/report-<time>/` | `problem_report.py:136` | direct write |
| `settings.env` | read only (`config.py:33`). Nothing in the code writes it. | — |
| `~/Library/Logs/LeagueasyMode/engine.log` (+ `.1`, `.2`) | Swift `OverlayCore/EngineLog.swift:27`, `EngineProcess.swift` | file handle, rotated per run |
| `UserDefaults` (update checks, how-to-use shown) | `AppDelegate.swift:145` and below | macOS |
| `accuracy-thresholds` file | `accuracy_thresholds.py:136`, only from the developer command at `cli.py:620` | direct write, not on players' Macs |

## Findings

### [ARCH-01] The audit gate runs after the product, not before it
- **Severity:** medium
- **Location:** `docs/METHOD.md` (gate order); `git log -- src`
- **Reproduction:** `git log --reverse --format='%h %ad %s' --date=short -- src | head -2; git ls-files src overlay | wc -l` → `2537133 2026-10-08 feat: record games ...` as the first product commit, and 167 tracked product files.
- **Impact on the project:** The audit cannot shape the design. Each finding is a change to code that already ships, so it costs more than a constraint would have.
- **Mitigation:** Say so in `docs/AUDIT.md`. Treat each finding as a backlog item with an owner. Do not present the audit as having preceded the build.

### [ARCH-02] The estimator layer imports the HTTP client and returns wire types
- **Severity:** low
- **Location:** `src/leagueasymode/inference/players.py:40` → `player_intel.py:29` (`league_client`); 20 `from leagueasymode.overlay_state` imports in `inference/`
- **Reproduction:** `.venv/bin/python -c "import sys,importlib,pkgutil,leagueasymode.inference as i; [importlib.import_module('leagueasymode.inference.'+m.name) for m in pkgutil.iter_modules(i.__path__)]; print('leagueasymode.league_client' in sys.modules, 'aiohttp' in sys.modules)"` → `True True`
- **Impact on the project:** The estimators cannot be loaded without the League-client stack and aiohttp. They also build the page's DTOs directly. A change to the wire contract therefore touches about 20 estimator modules, and an estimator change can change the contract.
- **Mitigation:** Move `PlayerRecord`/`PlayerRecords` out of `player_intel.py` into a model module with no I/O. Decide, with `defend-decision`, whether estimators keep returning `overlay_state` types or get their own. Deferral is acceptable.

### [ARCH-03] A few modules hold most of the logic, and the largest Swift file has no tests
- **Severity:** low
- **Location:** `src/leagueasymode/scoring.py` (1780), `overlay/web/src/overlay.ts` (1362), `src/leagueasymode/cli.py` (1152), `inference/gold.py` (1039), `overlay/web/src/state.ts` (1029), `overlay/macos/Sources/LeagueasyOverlay/AppDelegate.swift` (998)
- **Reproduction:** `wc -l` on the files above (counts as shown). `grep -c "func test" overlay/macos/Tests/OverlayCoreTests/OverlayCoreTests.swift` → 94. Every one of them targets `OverlayCore`. The `macos-overlay` CI job comment says "The window itself is tried by hand".
- **Impact on the project:** `scoring.py` scores every estimator, so any estimator change touches it. `AppDelegate.swift` holds the menu, update install, edit mode and engine lifecycle, and only a person checks it.
- **Mitigation:** Split `scoring.py` per estimator when the next estimator is added. Keep moving decisions from `AppDelegate` into `OverlayCore`, where they are tested.

### [ARCH-04] Concurrent saves of one file collide on the fixed `.partial` name
- **Severity:** low
- **Location:** `src/leagueasymode/preferences.py:79` (`_write_whole`), used by `overlay_server.py:365` (`change_layout`) through `asyncio.to_thread`. The same pattern recurs in `cli.py:847`, `friends.py`, `refit.py`, `accuracy_history.py` and `roast/claude_take.py`. Three other writers use `mkstemp`. That is nine hand-written atomic writes, with two strategies.
- **Reproduction:**
  ```sh
  .venv/bin/python -c "
  import tempfile,pathlib,collections,concurrent.futures as cf
  from leagueasymode.preferences import save_layout
  from leagueasymode.overlay_state import OverlayLayout
  p=pathlib.Path(tempfile.mkdtemp())/'layout.json'; e=[]
  def go(i):
    try: save_layout(p, OverlayLayout(opacity=0.4+(i%6)/10))
    except Exception as x: e.append(type(x).__name__)
  with cf.ThreadPoolExecutor(16) as ex: list(ex.map(go, range(2000)))
  print(collections.Counter(e))"
  ```
  → `Counter({'FileNotFoundError': 888})`
- **Impact on the project:** Suppose two `PUT /layout` requests overlap, such as a drag on the overlay and a slider on the settings page. The second rename then finds no partial file, the handler raises, and the page gets a 500. The engine already holds the new layout in memory, so memory and disk can disagree until the next save.
- **Mitigation:** Use one shared `write_whole` helper with a unique temporary name (`mkstemp`), and serialize saves of one path with a lock. Add a test like the reproduction.

### [ARCH-05] Of the APIs relied on, the one real recording confirms only the pre-game resources
- **Severity:** high
- **Location:** `game_api.py` (`/liveclientdata/allgamedata`); `league_client.py:39`; `patch_data.py:15-19`; `player_intel.py:34-44`; `recorder.py:48-55`; `scoring.py:114-115`
- **Reproduction:** `xz -dc /home/user/leagueasymode-recordings/games/game-2026-10-28T00-11-38Z-anonymized.jsonl.xz | .venv/bin/python -I -c "import sys,json; [print(r['kind'], r.get('path'), str(r.get('payload'))[:120]) for r in map(json.loads, sys.stdin)]"` → 11 records. One snapshot, at `gameTime 0.0`, `PRACTICETOOL`, with `allPlayers: []`, empty `Events`, and `activePlayer: {"error": "Spectator mode doesn't currently support this feature"}`. Eight client resources. Then `recording cancelled` at 0.053 s.
- **Impact on the project:** The table below is the integration surface. Every in-game estimator and all post-game scoring rest on fields and endpoints that only docs and hand-written fixtures describe. `tests/fixtures/client/README.md` says the items fixture is "written by hand, from memory".

| Integration point | Used by | Real recording |
|---|---|---|
| `/liveclientdata/allgamedata`: top-level keys, `gameData.gameMode/gameTime/mapNumber` | `game_api.py`, `game_state.py` | **confirmed** |
| `allPlayers[*]` (items, scores, spells, `riotId`, `isDead`, `respawnTimer`), `events.Events[*]`, `activePlayer.championStats`, `currentGold` | `game_state.py:28-206`, all of `inference/` | **not seen** (empty) |
| `/lol-gameflow/v1/session`, `/lol-patch/v1/game-version`, `/lol-game-data/assets/v1/{items,champion-summary,summoner-spells,perks,perkstyles}.json` | `league_client.py`, `patch_data.py`, `recorder.py` | **confirmed** |
| `/lol-ranked/v1/ranked-stats/{puuid}` | `player_intel.py:34` | **confirmed** |
| `/lol-match-history/v1/products/lol/{puuid}/matches`, `/lol-match-history/v1/game-timelines/{id}`, `/lol-match-history/v1/games/{id}` | `player_intel.py`, `recorder.py:53-54`, `scoring.py:114-115` | **not seen** |
| `/lol-end-of-game/v1/eog-stats-block`, `/lol-game-data/assets/v1/champions/{id}.json` | `recorder.py:52`, `:55` | **not seen** |

- **Mitigation:** Before any more estimator or scoring work, record one full Summoner's Rift game with the match timeline. Make it the replay fixture (see ARCH-09). This overlaps DQ-01, which covers the data side.

### [ARCH-06] An `activePlayer` error object becomes a blank player, so "spectating" checks miss it
- **Severity:** medium
- **Location:** `src/leagueasymode/game_state.py:163` (`ActivePlayer`, documented as "Absent when spectating"), `engine_status.py:210`. There are 10 `active_player is (not) None` checks in `src/`.
- **Reproduction:** Take the snapshot line, `xz -dc <recording> | sed -n 2p > snap.json`, then run `.venv/bin/python -c "import json; from leagueasymode.game_state import GameSnapshot; from leagueasymode.engine_status import StatusBoard; s=GameSnapshot.model_validate(json.load(open('snap.json'))['payload']); print(repr(s.active_player)); b=StatusBoard(); b.note_game(s); print(b._parts['game'].detail)"` → `ActivePlayer(summoner_name='', riot_id='', ..., level=1, ...)` and `Answering: PRACTICETOOL on map 11, 0:00 in, 0 players`, without the `; no player of yours` that the code adds when `active_player is None`.
- **Impact on the project:** Code that branches on `active_player is None` treats the API's refusal as a real player with empty names and level 1. Name matching fails closed today, because `is_named` rejects empty names. Status and any future `is not None` logic are still wrong. This shares a root with DQ-03.
- **Mitigation:** Add a `model_validator` that maps a payload with `error` to `None`. Add a test built from this real snapshot.

### [ARCH-07] Enemy cooldowns are marked by the player, never read from the API
- **Severity:** info
- **Location:** `src/leagueasymode/game_state.py:63` ("its cooldown is never sent"); `inference/cooldowns.py:1-8`; `overlay_state.py:387` (`CooldownTimer`, "An estimate"); `overlay/macos/Sources/OverlayCore/CooldownMarking.swift`
- **Reproduction:** `grep -ni "cooldown\|abilities" src/leagueasymode/game_state.py src/leagueasymode/game_api.py` → one line, the docstring at `game_state.py:63`. `grep -rniE "cooldown_?(remaining|left)" src/leagueasymode overlay/web/src` → nothing.
- **Impact on the project:** None. A timer starts only from a hotkey mark. Its length is the patch cooldown, with item haste only. The model says that runes are unknown.
- **Mitigation:** None needed. Keep the "estimate" wording in the widget.

### [ARCH-08] Schema → TypeScript is a hand mirror, and the bounds are written three times
- **Severity:** low
- **Location:** `overlay/web/src/state.ts:1-5`, `:408-444` (`MOVABLE_WIDGETS`, `MIN_WIDGET_SCALE`, …), `:998` (`isOverlayState`); `src/leagueasymode/overlay_state.py:658-712`; `tests/test_overlay_server.py:55`
- **Reproduction:** `.venv/bin/python -c "import json,re; s=json.load(open('overlay/web/overlay_state.schema.json')); d={**s['\$defs'],'OverlayState':s}; t=open('overlay/web/src/state.ts').read(); ts={m[1]:set(re.findall(r'readonly (\w+)\??:',m[2])) for m in re.finditer(r'export interface (\w+) \{(.*?)\n\}',t,re.S)}; print([n for n,x in d.items() if 'properties' in x and set(x['properties'])!=ts.get(n)])"` → `[]`. All 37 objects match today. No test or CI step runs a check like this. The widget list and the bounds (0.6–1.6, 0.5–1.5, ±0.1, 0.4) are written separately in pydantic, the schema and `state.ts`.
- **Impact on the project:** A contract change reaches the schema by test, but it reaches the TypeScript only if a reviewer notices. A field the TS lacks is dropped silently. A guard that rejects a new shape blanks the overlay. The browser tests (81, `-m browser`) catch this only for shapes their replayed game produces.
- **Mitigation:** Generate `state.ts` types from the schema (for example, `json-schema-to-typescript`), or add the field comparison above as a pytest. Keep the hand guards.

### [ARCH-09] The real-recording test passes over zero recordings
- **Severity:** low
- **Location:** `tests/test_accuracy_thresholds.py:28`, `:36`; `tests/fixtures/recorded-games/` (only `.gitkeep`)
- **Reproduction:** `ls -a tests/fixtures/recorded-games` → `. .. .gitkeep`. `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_accuracy_thresholds.py` → `8 passed`.
- **Impact on the project:** "Every recording meets its thresholds" is green with no real game behind it. The suite (1081 unit and 81 browser tests) exercises only built payloads (`tests/game_payloads.py`), so it cannot catch ARCH-05 or ARCH-06.
- **Mitigation:** Make the test fail, or report as skipped, when no recording is present. Commit the anonymized real game, once a full one exists, as the first fixture.

## Test layout and CI

| Suite | Where | Runs in |
|---|---|---|
| Unit (pytest, `-m 'not browser'` by default) | `tests/` (84 files), 1081 passed in 20.9 s | `make gate`, CI `pytest` |
| Browser (Playwright, Chromium, replayed game) | `tests/test_{overlay,layout,settings,status,summary}_page.py`, 81 tests | CI `widgets` only, after `npm run build` and a `git diff --exit-code` on `overlay_web/` |
| Swift (`swift test`, `OverlayCore` only) | `overlay/macos/Tests/OverlayCoreTests` | CI `macos-overlay` (macOS 15). No Swift here. |
| Packaged app smoke test | `overlay/macos/scripts/smoke_test_app.sh` | CI `macos-app`, `prerelease` |
| Static | ruff, mypy, `check_python_rules.py`, pip-audit, gitleaks, okf bundle, skills | CI, one job each |

`.github/workflows/ci.yml` runs every job on every pull request, with no path filter. A push to
`main` publishes a prerelease that the app installs, after all jobs pass except `macos-app`
(which `prerelease` re-runs itself).
