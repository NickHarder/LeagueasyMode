import datetime
import lzma
from pathlib import Path
from typing import Final

import pytest
from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    GAME_ID,
    all_game_data,
    champion_kill_event,
    dragon_kill_event,
    game_start_event,
    gameflow_session,
)
from leagueasymode.recording.anonymize import IdentityLeakError, anonymize_recording
from leagueasymode.recording.file_format import ClientResource
from leagueasymode.recording.reader import iter_game_frames, iter_recording_lines
from leagueasymode.recording.writer import RecordingWriter

STARTED_AT: Final = datetime.datetime(2026, 10, 8, 14, 0, tzinfo=datetime.UTC)
TIMELINE_PATH: Final = f"/lol-match-history/v1/game-timelines/{GAME_ID}"


def write_source_recording(directory: Path, extra_payload: JsonValue = None) -> Path:
    events: list[dict[str, JsonValue]] = [
        game_start_event(),
        champion_kill_event(1, 200.0, "Gank Plz", "Garen Main", ["Top Dog"]),
        dragon_kill_event(2, 320.0, "Jungle Diff"),
        {
            "EventID": 3,
            "EventName": "TurretKilled",
            "EventTime": 600.0,
            "TurretKilled": "Turret_T2_L_03_A",
            "KillerName": "Turret_T1_L_03_A",
            "Assisters": [],
        },
    ]
    writer = RecordingWriter(directory / "game.jsonl", keyframe_interval_seconds=60.0)
    writer.write_started(started_at=STARTED_AT, recorder_version="test", poll_interval_seconds=0.5)
    writer.write_client_resource(
        received_at_seconds=0.0, path="/lol-gameflow/v1/session", payload=gameflow_session()
    )
    writer.write_snapshot(received_at_seconds=0.5, payload=all_game_data(10.0, events[:1]))
    writer.write_snapshot(received_at_seconds=1.0, payload=all_game_data(610.0, events))
    if extra_payload is not None:
        writer.write_client_resource(
            received_at_seconds=1.2, path="/lol-chat/v1/whatever", payload=extra_payload
        )
    writer.write_client_resource(
        received_at_seconds=1.5, path=TIMELINE_PATH, payload={"gameId": GAME_ID, "frames": []}
    )
    writer.write_ended(received_at_seconds=2.0, reason="game ended")
    return writer.close()


def recording_text(recording_path: Path) -> str:
    with lzma.open(recording_path, "rt", encoding="utf-8") as recording_file:
        return recording_file.read()


def identity_strings() -> list[str]:
    riot_ids = [seed.riot_id for seed in DEFAULT_PLAYERS]
    # "Ahri" is also a champion's name, which stays.
    game_names = [
        seed.riot_id_game_name for seed in DEFAULT_PLAYERS if seed.riot_id_game_name != "Ahri"
    ]
    puuids = [
        f"puuid-{seed.riot_id_game_name.lower().replace(' ', '-')}-0000" for seed in DEFAULT_PLAYERS
    ]
    return [*riot_ids, *game_names, *puuids, str(GAME_ID), "41000000", "42000004"]


def test_no_name_id_or_game_id_survives(tmp_path: Path) -> None:
    source_path = write_source_recording(tmp_path)
    anonymized_path = anonymize_recording(source_path, tmp_path / "anonymized.jsonl")
    anonymized_text = recording_text(anonymized_path)
    for identity in identity_strings():
        assert identity not in anonymized_text, identity


def test_each_player_keeps_one_pseudonym_everywhere(tmp_path: Path) -> None:
    source_path = write_source_recording(tmp_path)
    anonymized_path = anonymize_recording(source_path, tmp_path / "anonymized.jsonl")
    last_frame = list(iter_game_frames(anonymized_path))[-1].payload
    assert isinstance(last_frame, dict)
    active_player = last_frame["activePlayer"]
    all_players = last_frame["allPlayers"]
    events = last_frame["events"]
    assert (
        isinstance(active_player, dict)
        and isinstance(all_players, list)
        and isinstance(events, dict)
    )
    first_player = all_players[0]
    assert isinstance(first_player, dict)
    assert first_player["riotId"] == "Player 1#ANON"
    assert first_player["riotIdGameName"] == "Player 1"
    assert first_player["riotIdTagLine"] == "ANON"
    assert active_player["riotId"] == "Player 3#ANON"
    event_list = events["Events"]
    assert isinstance(event_list, list)
    champion_kill = event_list[1]
    assert isinstance(champion_kill, dict)
    assert champion_kill["KillerName"] == "Player 7"
    assert champion_kill["VictimName"] == "Player 1"
    assert champion_kill["Assisters"] == ["Player 6"]


def test_game_content_is_left_as_it_was(tmp_path: Path) -> None:
    source_path = write_source_recording(tmp_path)
    anonymized_path = anonymize_recording(source_path, tmp_path / "anonymized.jsonl")
    last_frame = list(iter_game_frames(anonymized_path))[-1].payload
    assert isinstance(last_frame, dict)
    all_players = last_frame["allPlayers"]
    events = last_frame["events"]
    assert isinstance(all_players, list) and isinstance(events, dict)
    # A player called Ahri plays Ahri: the champion keeps its name.
    assert [player["championName"] for player in all_players if isinstance(player, dict)][
        2
    ] == "Ahri"
    event_list = events["Events"]
    assert isinstance(event_list, list)
    turret_kill = event_list[3]
    assert isinstance(turret_kill, dict)
    assert turret_kill["KillerName"] == "Turret_T1_L_03_A"
    assert last_frame["gameData"] == {
        "gameMode": "CLASSIC",
        "gameTime": 610.0,
        "mapName": "Map11",
        "mapNumber": 11,
        "mapTerrain": "Default",
    }


def test_the_frames_and_their_times_are_kept(tmp_path: Path) -> None:
    source_path = write_source_recording(tmp_path)
    anonymized_path = anonymize_recording(source_path, tmp_path / "anonymized.jsonl")
    assert [frame.received_at_seconds for frame in iter_game_frames(anonymized_path)] == [0.5, 1.0]


def test_the_client_paths_lose_the_game_id(tmp_path: Path) -> None:
    source_path = write_source_recording(tmp_path)
    anonymized_path = anonymize_recording(source_path, tmp_path / "anonymized.jsonl")
    resource_paths = [
        line.path
        for line in iter_recording_lines(anonymized_path)
        if isinstance(line, ClientResource)
    ]
    assert resource_paths == ["/lol-gameflow/v1/session", "/lol-match-history/v1/game-timelines/1"]


def test_a_name_left_in_free_text_stops_the_copy(tmp_path: Path) -> None:
    source_path = write_source_recording(
        tmp_path, extra_payload={"body": "gg Shadow Step, well played"}
    )
    with pytest.raises(IdentityLeakError, match="body"):
        anonymize_recording(source_path, tmp_path / "anonymized.jsonl")
    assert not (tmp_path / "anonymized.jsonl").exists()
    assert not (tmp_path / "anonymized.jsonl.xz").exists()
