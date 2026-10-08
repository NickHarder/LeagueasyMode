---
type: Reference
title: Recordings
description: What a recording of a game holds, how it is written and read, what is asked of the League client and when, and how a copy is anonymized before it may enter the repository.
tags: [recording, data, privacy]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-08T22:45:47Z }
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
the chance on the true one); and the map, by how far the timeline's position of each player each
minute lies from its paths.[^scoring]

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
  then each champion in the game, then each player's ranked stats and last 20 games, one request
  at a time (`LEAGUEASYMODE_PLAYER_LOOKUP_PAUSE_SECONDS` apart); while `leagueasymode run` also
  shows the overlay, the engine and the recorder share those answers, so each player is asked
  about once. After the game: the end-of-game stats, then the match timeline
  every 15 seconds for up to 10 minutes, and the game's details once the timeline has come. A path
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
