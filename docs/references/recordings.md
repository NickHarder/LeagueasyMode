---
type: Reference
title: Recordings
description: What a recording of a game holds, how it is written and read, what is asked of the League client and when, and how a copy is anonymized before it may enter the repository.
tags: [recording, data, privacy]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-09T05:13:00Z }
sources:
  - id: file-format
    resource: ../../src/leagueasymode/recording/file_format.py
  - id: delta
    resource: ../../src/leagueasymode/recording/delta.py
  - id: recorder
    resource: ../../src/leagueasymode/recorder.py
  - id: anonymize
    resource: ../../src/leagueasymode/recording/anonymize.py
  - id: riot-tls
    resource: ../../src/leagueasymode/riot_tls.py
  - id: league-client
    resource: ../../src/leagueasymode/league_client.py
  - id: scoring
    resource: ../../src/leagueasymode/scoring.py
  - id: refit
    resource: ../../src/leagueasymode/refit.py
  - id: accuracy-history
    resource: ../../src/leagueasymode/accuracy_history.py
  - id: accuracy-thresholds
    resource: ../../src/leagueasymode/accuracy_thresholds.py
---

# What a recording is for

Every estimator in [the plan](../plans/overlay-and-inference.md) is built and scored against
recorded games. A recording keeps everything the game's API answered during one game and what the
League client served around it, so a game can be replayed as if it were running and compared with
the match timeline, which is the ground truth.

`uv run leagueasymode score <recording>` prints how far each estimator is from the truth on one
recorded game: the role estimator against the positions the game gave or its details recorded
(with the positions hidden from it), the combat stats estimate against the exact stats the game
gives for the player on this machine, once a minute, and the gold estimates of every other player
against the match timeline's earned and unspent gold at the start of each minute, and every
player's experience against the timeline's, each with how often its band holds the truth (it
should, about 4 times in 5), each player's predicted next item at the end of each minute against
the next finished item the timeline shows them buy, and the trips to base seen against the
timeline's purchases made alive, both ways; each player's likely regions at the start of each
minute against the region nearest their timeline position (how often the likeliest was right, and
the chance on the true one); each jungler's decoded camp, by how far the timeline puts them from
it at a minute that came within 30 seconds of it, decoded with each jungler's usual start as the
engine has it; each jungler's habits from their past games (the side they usually start on, and
the half of the map they are usually on at 4:00) against where this game's timeline puts them,
the players' records rebuilt from the client's recorded answers as the engine had them; the
control wards seen placed against the
timeline's, both ways (it records when, not where); the map, by how far the timeline's position
of each player each minute lies from its paths; each fight of the timeline (two kills or more,
each within 15 seconds of the last and 3000 units of the first), the chance its players had from
the last answer before it against the team that lost fewer, by its Brier score; each of your
team's takes of Dragon, the Elder or Baron, the chance of a contest given 20 seconds before
against whether the other team fought there (a kill with one of theirs in it within 3000 units,
from 30 seconds before to 10 after), by its Brier score; and the win chance at the start of each
minute
against the result the game's details record, by its Brier score (0.25 for a coin flip every
minute, lower is better).[^scoring]

`uv run leagueasymode fit <recording>... [--write]` refits the hand-set models on recorded games:
the win chance's weights on every minute of every game with its result, and the fights'
steepness on every fight of the timelines. It needs 20 games or more for each. Each fit is checked
on games it did not see (the games split into ten folds, each scored by a fit made without it),
and printed against the hand-set weights by the Brier score; a fit is kept only when it scores
better. The fit is a logistic regression pulled toward the hand-set weights, so that a few games
move them little. With `--write`, the weights kept go to `model-weights.json` in the
application's directory (`LEAGUEASYMODE_MODEL_WEIGHTS` moves it), which `leagueasymode run` reads
at its start; without the file, or with one that cannot be read, the hand-set weights stand.[^refit]

Every game `uv run leagueasymode run` records is scored the same way once its timeline has come,
and its scores are kept, one line a game, in `accuracy-history.jsonl` in the application's
directory (`LEAGUEASYMODE_ACCURACY_HISTORY` moves it); `leagueasymode score <recording> --keep`
adds a game by hand, and scoring a game again replaces its line. A line names the recording's
file, the game's id and version, and the scores; never a player. `uv run leagueasymode history`
prints each estimator's last game, its average over the last ten games weighed by their samples,
and, from six games, whether the newer half beats the older half: "better", "worse" or "steady"
(within 2%).[^accuracy-history]

CI holds the anonymized recordings in `tests/fixtures/recorded-games/` to each estimator's
threshold in `tests/accuracy_thresholds.json`: a share must reach it, an error stay at or under
it, and a test fails on the first recording that misses. The thresholds come from the first batch
of recordings: `uv run leagueasymode thresholds <recordings> --write` proposes, for each estimator
scored on 20 games or more, its average less one standard deviation toward the worse side, and
writes it only where it is stricter than the threshold held, so a threshold is never loosened.
The patch's Data Dragon files for those recordings go in
`tests/fixtures/recorded-games/patch-data/<version>/`, as `leagueasymode` keeps them, so that the
combat stats, fights and contests are scored too. Only anonymized copies may be committed there
(`.gitignore` keeps every folder named `recordings/` out), and a test checks every file's
name.[^accuracy-thresholds]

# How to make one

`uv run leagueasymode record` waits for a game, records it, and goes back to waiting; Ctrl-C stops
it, closing a game in progress with what it has. Recordings go to
`~/Library/Application Support/LeagueasyMode/recordings/` on a Mac
(`LEAGUEASYMODE_RECORDINGS_DIRECTORY` moves them).

# The file

One JSON object a line, each a record with a `kind`:[^file-format]

| Kind | What it holds |
|---|---|
| `recording_started` | The format version (1), the recorder's version, the start time, the poll interval. |
| `snapshot_keyframe` | One answer of `/liveclientdata/allgamedata`, whole. |
| `snapshot_delta` | One answer as JSON Patch operations (`add`, `remove`, `replace`) from the answer before.[^delta] |
| `client_resource` | One answer of the League client, with the path it was asked for. |
| `recording_ended` | Why the recording stopped: `game ended`, `the game stopped answering`, `recording stopped` or `recording cancelled`. |

Every record carries `received_at_seconds`, the seconds since the recording started. The first
snapshot is a keyframe, and so is the first one at least 60 seconds after the last keyframe, so a
damaged line costs at most a minute.

While a game is being recorded the file is `game-<UTC start>.jsonl`, written and flushed a line at a
time, so a crash loses at most the line being written; a reader skips a last line cut off part way.
When the recording is closed it is compressed to `.jsonl.xz` (xz keeps an 8 MiB dictionary, so
each answer is compressed against the ones before it) and the plain file is removed only once the
compressed one is complete.

# What is asked, and when

- **The game**, at `https://127.0.0.1:2999`, twice a second (`LEAGUEASYMODE_POLL_INTERVAL_SECONDS`),
  and every 2 seconds while no game runs. A game that stops answering for 120 seconds is over; one
  that has sent the `GameEnd` event is over as soon as it stops answering, or 30 seconds later.[^recorder]
- **The League client**, found through its lockfile (`/Applications/League of Legends.app/Contents/LoL/lockfile`,
  or `LEAGUEASYMODE_LEAGUE_CLIENT_LOCKFILE`) or, failing that, the arguments of its `LeagueClientUx`
  process.[^league-client] At the start of a game: the gameflow session (which holds the game's id),
  the game version, and the patch's items, champion summary, summoner spells, runes and rune styles,
  then each champion in the game, then each player's ranked stats and last 20 games, and the
  timelines of each player's newest five games and, for a likely jungler, of up to five of their
  recent jungle games, one request at a time (`LEAGUEASYMODE_PLAYER_LOOKUP_PAUSE_SECONDS` apart);
  while `leagueasymode run` also shows the overlay, the engine and the recorder share those
  answers, so each player is asked about once (an answer is forgotten once both have had it, and
  at most the latest 80 are kept, so that past timelines do not pile up over a long session). After the game: the end-of-game stats, then the match timeline
  every 15 seconds for up to 10 minutes, and the game's details once the timeline has come. The
  scoring finds this game's timeline and details by the session's game id, never a past game's. A path
  the client does not have is skipped. Without the client, the game is recorded alone.

Both are HTTPS. The connection trusts Riot's "LoL Game Engineering Certificate Authority" root and
nothing else, and does not check the host name, since both listen only on 127.0.0.1.[^riot-tls]
The root was copied from two open-source clients of the game's API that carry the same bytes; its
SHA-256 fingerprint is in `riot_tls.py`, to be compared once with Riot's own `riotgames.pem`.

# Anonymized copies

A recording holds other players' names, so only an anonymized copy is committed:
`uv run leagueasymode anonymize <recording>` writes `<name>-anonymized.jsonl.xz` beside it.[^anonymize]

- Every Riot ID, summoner name, PUUID, account and summoner number and game id becomes a pseudonym,
  the same one everywhere: the scoreboard's first player is `Player 1` in the scoreboard, the kill
  feed and the client's answers alike, and a tag line becomes `ANON`.
- Game content (champion, item, rune and spell names and their texts, turret names) is left alone,
  so a player named like a champion does not rename the champion.
- It fails closed: the copy is searched again for every identity, and one found anywhere stops it
  with the JSON Pointer of where, and nothing is written. A new field holding a name then has to be
  added to `anonymize.py`.

`recordings/` and `*.lgrec` are in `.gitignore`.

[^file-format]: `src/leagueasymode/recording/file_format.py`
[^delta]: `src/leagueasymode/recording/delta.py`
[^recorder]: `src/leagueasymode/recorder.py`
[^league-client]: `src/leagueasymode/league_client.py`
[^riot-tls]: `src/leagueasymode/riot_tls.py`
[^anonymize]: `src/leagueasymode/recording/anonymize.py`
[^scoring]: `src/leagueasymode/scoring.py`
[^refit]: `src/leagueasymode/refit.py`
[^accuracy-history]: `src/leagueasymode/accuracy_history.py`
[^accuracy-thresholds]: `src/leagueasymode/accuracy_thresholds.py`
