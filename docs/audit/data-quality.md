---
type: Audit Area
title: "Data quality"
description: How much of what the estimators assume about the game's and the League client's answers is confirmed by real recordings, where the built test data disagrees with them, and what that leaves unproven.
tags: [audit, data-quality]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T06:44:31Z }
---

# Scope and timing

This area profiles the data every estimator is built and scored on: the recordings described in
[Recordings](../references/recordings.md). **The audit is late.** The audit gate asks for it
before any product code exists, but the recorder, the anonymizer, the sender, the engine, the
estimators, the scoring and the refit are already written and tested. What follows judges the
data those were built on, after the fact.

The evidence is the profile script [`data_profile.py`](data_profile.py), run on:

- the private recordings repository's clone, `/home/user/leagueasymode-recordings` (read only),
  which holds **one** recording, `games/game-2026-10-28T00-11-38Z-anonymized.jsonl.xz`;
- a recording built from the tests' payloads (`tests/game_payloads.py`, `tests/recorded_games.py`)
  by the script's `--build-from-test-payloads` option, the recording the scoring tests write.

## Profile of the real recording

```
$ uv run python docs/audit/data_profile.py /home/user/leagueasymode-recordings
== game-2026-10-28T00-11-38Z-anonymized.jsonl.xz
recorder 0.1.0, poll 0.5 s; ended: recording cancelled
duration 0.053 s wall; game clock 0.0 -> 0.0 s
frames 1 (keyframes 1, deltas 0)
game mode {'PRACTICETOOL': 1}; map {'11': 1}
gameTime going backwards: 0 []
gaps between answers > 2.0 s: 0 (largest 0.0 s)
frames with no allPlayers: 1; frames whose activePlayer is an error: 1
player rows: 0
riotIdGameName: pseudonyms 0, not pseudonyms 0
events (unique ids): {}
ChampionKill events 0; KillerName/VictimName missing 0
duplicate event ids within a frame 0; ids whose content changed between frames 0
implausible: negative gold 0, level outside 1..18 0, creep score decreasing 0, negative respawnTimer 0
client resources: gameflow session 1, game version 1, items 1, champion summary 1,
  champion details 0, summoner spells 1, runes 1, rune styles 1, ranked stats 1,
  match history 0, timeline 0, game details 0, end-of-game stats 0, other 0
```

## Profile of the built test recording

```
$ uv run python docs/audit/data_profile.py --build-from-test-payloads <scratch dir>/built
== game.jsonl.xz
recorder test, poll 0.5 s; ended: game ended
duration 1000.000 s wall; game clock 0.0 -> 900.0 s
frames 16 (keyframes 16, deltas 0)
game mode {'CLASSIC': 16}; map {'11': 16}
gameTime going backwards: 0 []
gaps between answers > 2.0 s: 15 (largest 60.0 s)
frames with no allPlayers: 0; frames whose activePlayer is an error: 0
player rows: 160
  championName, rawChampionName, team, level, scores.creepScore, respawnTimer, position,
  riotIdGameName, riotId, summonerName, summonerSpells: missing 0.0%  null 0.0%  empty 0.0%
  items                missing   0.0%  null   0.0%  empty 100.0%
riotIdGameName: pseudonyms 0, not pseudonyms 160
events (unique ids): {'GameStart': 1, 'ChampionKill': 1}
ChampionKill events 1; KillerName/VictimName missing 0
duplicate event ids within a frame 0; ids whose content changed between frames 0
implausible: negative gold 0, level outside 1..18 0, creep score decreasing 0, negative respawnTimer 0
client resources: gameflow session 1, game version 1, champion summary 1, timeline 1,
  game details 1, every other kind 0
```

The field table and the resource list are folded onto fewer lines here; the script prints one
line each. The detectors were checked on a recording built to be wrong (clock stepping back,
a repeated event id, a nameless killer, gold of -5, level 19, creep score falling): each was
counted.

# Findings

### [DQ-01] One real recording, a Practice Tool game cancelled at 0:00, confirms almost nothing
- **Severity:** critical
- **Location:** `/home/user/leagueasymode-recordings/games/` (one file);
  `tests/fixtures/recorded-games/` (only `.gitkeep`); `tests/accuracy_thresholds.json`
  (`"thresholds": {}`)
- **Reproduction:** `uv run python docs/audit/data_profile.py /home/user/leagueasymode-recordings`
  and `ls -la tests/fixtures/recorded-games; cat tests/accuracy_thresholds.json`
- **Impact on the project:** the real corpus is one frame, 0.053 s long, with zero scoreboard rows
  and zero events. Not one null rate, value range, cadence, event shape or kill-feed name the
  estimators rely on has been seen in a real game. Confirmed: the line format reads, the game
  clock field exists, `gameMode`/`mapNumber` are present, the recorder asks the client in the
  documented order. Everything else (gold, experience, roles, jungle, fights, win chance) is
  shaped by built data only, and CI's accuracy gate holds no recording and no threshold.
- **Mitigation:** treat every estimator as unvalidated. Before any further estimator work, get at
  least one full Summoner's Rift game (and the ARAM/Swiftplay games the owner already played)
  through the sender, run this profile on them, and add each anonymized copy to
  `tests/fixtures/recorded-games/`; re-run this audit area with 20 or more games before the
  thresholds are proposed.

### [DQ-02] The first answer comes from the loading screen, so champion details are never asked for
- **Severity:** high
- **Location:** `src/leagueasymode/recorder.py:398` and `:583` (`_champion_ids_in_game` reads
  `allPlayers` of the first answer); `_wait_for_game` accepts any answer with a `gameData` object
- **Reproduction:** `xz -dc /home/user/leagueasymode-recordings/games/game-2026-10-28T00-11-38Z-anonymized.jsonl.xz | python3 -c "import sys,json; [print(json.loads(l)['kind'], json.loads(l).get('path','')) for l in sys.stdin]"`
  shows the session, the static files, then ranked stats, and no `/lol-game-data/assets/v1/champions/`
  path; the profile prints `frames with no allPlayers: 1` and `champion details 0`.
- **Impact on the project:** the recorder asks for champion details between the static files and
  the ranked stats; ranked stats were recorded, so the step ran and found no champions, because
  the first answer had `allPlayers: []`. Real games start the same way, so recordings will lack
  champion details, and anything replayed from them (combat stats, ability cooldowns) loses its
  input silently. Every test recording starts with ten players, so no test sees it.
- **Mitigation:** take the champions from the gameflow session's `playerChampionSelections` or
  wait for the first answer with players; add a test whose first answer is the real loading one.

### [DQ-03] The loading-screen `activePlayer` is an error object that validates as an empty player
- **Severity:** medium
- **Location:** `src/leagueasymode/game_state.py:163` (`ActivePlayer`, every field defaulted,
  `extra="ignore"`)
- **Reproduction:** `uv run python -c "from leagueasymode.recording.reader import iter_game_frames; from leagueasymode.game_state import GameSnapshot; from pathlib import Path; f=next(iter_game_frames(Path('/home/user/leagueasymode-recordings/games/game-2026-10-28T00-11-38Z-anonymized.jsonl.xz'))); print(GameSnapshot.model_validate(f.payload).active_player)"`
  prints `summoner_name='' riot_id='' riot_id_game_name='' level=1 current_gold=0.0 champion_stats=None`
  for a payload whose `activePlayer` is `{"error": "Spectator mode doesn't currently support this feature"}`.
- **Impact on the project:** "we do not know who you are" reads as "you are level 1 with 0 gold".
  Any code that checks `active_player is None` to mean "unknown" is wrong for these frames.
  The built payloads never contain this shape.
- **Mitigation:** reject or map the error object to `None` at the boundary, and add the real
  loading payload as a fixture.

### [DQ-04] Missing scoreboard fields become plausible values, so null rates cannot be measured downstream
- **Severity:** medium
- **Location:** `src/leagueasymode/game_state.py:100` (`creepScore` default 0), `:111`
  (`position` default `""`), `:112` (`level` default 1), `:114` (`respawnTimer` default 0.0)
- **Reproduction:** `sed -n 95,120p src/leagueasymode/game_state.py`; the real profile prints
  `player rows: 0`, so no real missing rate exists to compare with.
- **Impact on the project:** a field the game drops (in another mode, on a new patch, or for a
  spectator) turns into a level-1, zero-CS, alive, roleless player, and the gold, experience,
  role and respawn estimates are fed confident zeros. Nothing logs it.
- **Mitigation:** keep these defaults (they make the overlay resilient) but count missing fields
  per game in the engine's status and in the recording's scoring; re-run this profile on real
  games and record the observed missing rates here.

### [DQ-05] The built test data disagrees with the real recording's shape
- **Severity:** medium
- **Location:** `tests/recorded_games.py:136` (`keyframe_interval_seconds=60.0`, one answer a
  minute), `:149` (version `16.19.712.1234`); `tests/game_payloads.py:271` (`gameflow_session`),
  `:299` (`ranked_stats`)
- **Reproduction:** both profile commands above; `xz -dc <real recording> | sed -n 3p` (session)
  and `sed -n 4p` (version), `sed -n 10p` (ranked stats)
- **Impact on the project:** differences seen, real versus built:

  | Aspect | Real | Built |
  |---|---|---|
  | Cadence | 0.5 s polls, deltas between keyframes | 1 answer a minute, 16 keyframes, 0 deltas, 15 gaps of 60 s |
  | First answer | `allPlayers: []`, `activePlayer` an error | ten players, full `activePlayer` |
  | Game version | `16.21.8298620+branch.releases-16-21...` | `16.19.712.1234` |
  | Session players | `summonerName: ""`, `selectedPosition: "NONE"`, plus `playerChampionSelections`, `gameClient`, `map` | `summonerName` = Riot ID, no selections |
  | Ranked stats | 6 queues, incl. `JADE_RANKED_SOLO_5x5`, TFT | 2 queues |
  | Scoreboard values | (none seen) | levels and creep scores constant all game, items empty in 100% of rows |

  The version string still parses (`_patch_of_game_version` returns `(16, 21)`, checked), and
  delta reading has its own tests (`tests/test_recording_delta.py`), but the scoring tests never
  replay a game at the real cadence or with values that change.
- **Mitigation:** add the real loading answer, session, version and ranked answer as fixtures
  (they are anonymized already); give the built game progressing values and a 0.5 s stretch.

### [DQ-06] The ground truth (timeline, game details, end-of-game stats, match history) has never been seen
- **Severity:** high
- **Location:** `tests/recorded_games.py:54` (`game_details`), `:91` (`game_timeline`);
  `src/leagueasymode/recorder.py` (`TIMELINE_PATH_TEMPLATE`, `GAME_DETAILS_PATH_TEMPLATE`,
  `END_OF_GAME_STATS_PATH`)
- **Reproduction:** the real profile prints `match history 0, timeline 0, game details 0,
  end-of-game stats 0`.
- **Impact on the project:** every score in `leagueasymode score`, every refit and every
  threshold compares against these answers, whose shapes are hand-written from the public match
  format (lane/role in `participants[].timeline`, `participantFrames` keyed by id). If the client's
  shape differs, scoring silently finds no truth and reports nothing, not a failure.
- **Mitigation:** make the scoring say when it found no timeline or details for a game, and check
  the first real ones against these builders before trusting any score.

### [DQ-07] The kill feed's name join is unconfirmed
- **Severity:** low
- **Location:** `src/leagueasymode/game_state.py:132` (`is_named` accepts summoner name, Riot ID
  or game name)
- **Reproduction:** real profile: `ChampionKill events 0`; built: `KillerName/VictimName missing 0`
  with game names only.
- **Impact on the project:** fights, deaths and respawns depend on joining `KillerName` and
  `VictimName` to scoreboard rows; which form the current patch uses is not observed, nor whether
  the anonymizer maps feed names to the same pseudonym as the scoreboard in a real game.
- **Mitigation:** the three-form match is a sound hedge; confirm on the first real game that every
  ChampionKill name resolves to a row (add that count to the profile when it exists).

### [DQ-08] The anonymized copy keeps the session's server address and spectator key
- **Severity:** info
- **Location:** `/lol-gameflow/v1/session` in the real recording: `gameClient.serverIp`,
  `serverPort`, `gameData.spectatorKey`
- **Reproduction:** `xz -dc /home/user/leagueasymode-recordings/games/game-2026-10-28T00-11-38Z-anonymized.jsonl.xz | sed -n 3p | grep -o '"serverIp":"[^"]*"\|"spectatorKey":"[^"]*"'`
- **Impact on the project:** not an identity the anonymizer promises to remove, and stale after the
  game, but it is a per-game value in a committed file. Data quality is unaffected.
- **Mitigation:** deferred to the security and compliance areas to decide.

# Test-data defense

**Why the built payloads are safe.** Every name in `tests/game_payloads.py` is invented (its module
docstring says so), the PUUIDs are `puuid-<name>-0000`, the game ids are constants, and no real
answer is copied in. They hold no player's data, cost nothing, and run offline in the gate.

**How they are reproduced.** They are deterministic builders, not seeded random data: the same call
gives the same payload. `uv run python docs/audit/data_profile.py --build-from-test-payloads <dir>`
writes and profiles the recording the scoring tests use (`write_scored_recording` with the default
ten players at level 9, positions given, a flat timeline, a win for team 100, one kill at 5:00).

**Which of their flaws become product failures.**

- Ten players in the first answer hides DQ-02 (no champion details) and DQ-03 (error `activePlayer`).
- Fields always present hides DQ-04: no test feeds the engine a row missing `level` or `position`.
- One answer a minute and constant values never exercise the 0.5 s cadence, values that change
  between answers, a creep score or clock that steps back, or a gap in answers.
- Hand-written timelines and details (DQ-06) make the scoring agree with its own assumptions; a
  wrong field name there passes every test and scores nothing on real games.
- Names that are not pseudonyms mean the scoring tests never run on anonymized data, which is all
  that may be committed (`riotIdGameName: pseudonyms 0, not pseudonyms 160`).

**What they cannot show.** Real null and missing rates, real value ranges and their progression,
event ids and shapes across patches and modes (ARAM, Swiftplay, Arena), how often the game stops
answering mid-game, the client's real timeline and details, whether estimator accuracy holds on
real games, and anything the thresholds would be set from.
