import datetime
import json
import lzma
from pathlib import Path
from typing import Final

import pytest
from pydantic import JsonValue

from leagueasymode.recording.file_format import (
    ClientResource,
    RecordingEnded,
    RecordingFormatError,
    RecordingStarted,
    SnapshotDelta,
    SnapshotKeyframe,
)
from leagueasymode.recording.reader import iter_game_frames, iter_recording_lines
from leagueasymode.recording.writer import RecordingWriter

STARTED_AT: Final = datetime.datetime(2026, 10, 8, 14, 0, tzinfo=datetime.UTC)


def game_state(game_time_seconds: float, creep_score: int) -> JsonValue:
    return {
        "gameData": {"gameTime": game_time_seconds, "gameMode": "CLASSIC"},
        "allPlayers": [{"championName": "Ahri", "scores": {"creepScore": creep_score}}],
        "events": {"Events": [{"EventID": 0, "EventName": "GameStart", "EventTime": 0.0}]},
    }


def write_game(path: Path, snapshot_count: int, keyframe_interval_seconds: float) -> Path:
    writer = RecordingWriter(path, keyframe_interval_seconds=keyframe_interval_seconds)
    writer.write_started(started_at=STARTED_AT, recorder_version="test", poll_interval_seconds=0.5)
    for index in range(snapshot_count):
        writer.write_snapshot(
            received_at_seconds=index * 0.5, payload=game_state(index * 0.5, index)
        )
    writer.write_client_resource(
        received_at_seconds=99.0, path="/lol-gameflow/v1/session", payload={"phase": "EndOfGame"}
    )
    writer.write_ended(received_at_seconds=100.0, reason="game ended")
    return writer.close()


def test_every_snapshot_comes_back_as_it_was_written(tmp_path: Path) -> None:
    recording_path = write_game(
        tmp_path / "game.jsonl", snapshot_count=30, keyframe_interval_seconds=5.0
    )
    frames = list(iter_game_frames(recording_path))
    assert [frame.received_at_seconds for frame in frames] == [index * 0.5 for index in range(30)]
    assert [frame.payload for frame in frames] == [
        game_state(index * 0.5, index) for index in range(30)
    ]


def test_a_closed_recording_is_compressed_and_the_plain_file_is_gone(tmp_path: Path) -> None:
    recording_path = write_game(
        tmp_path / "game.jsonl", snapshot_count=3, keyframe_interval_seconds=60.0
    )
    assert recording_path == tmp_path / "game.jsonl.xz"
    assert not (tmp_path / "game.jsonl").exists()
    with lzma.open(recording_path, "rt", encoding="utf-8") as compressed_file:
        first_line = json.loads(compressed_file.readline())
    assert first_line["kind"] == "recording_started"


def test_the_first_snapshot_and_one_per_interval_are_whole(tmp_path: Path) -> None:
    recording_path = write_game(
        tmp_path / "game.jsonl", snapshot_count=30, keyframe_interval_seconds=5.0
    )
    lines = list(iter_recording_lines(recording_path))
    keyframe_times = [
        line.received_at_seconds for line in lines if isinstance(line, SnapshotKeyframe)
    ]
    delta_count = sum(1 for line in lines if isinstance(line, SnapshotDelta))
    assert keyframe_times == [0.0, 5.0, 10.0]
    assert delta_count == 27


def test_the_lines_say_what_happened_in_order(tmp_path: Path) -> None:
    recording_path = write_game(
        tmp_path / "game.jsonl", snapshot_count=2, keyframe_interval_seconds=60.0
    )
    lines = list(iter_recording_lines(recording_path))
    assert isinstance(lines[0], RecordingStarted)
    assert lines[0].started_at == STARTED_AT
    assert lines[0].poll_interval_seconds == 0.5
    assert isinstance(lines[-2], ClientResource)
    assert lines[-2].payload == {"phase": "EndOfGame"}
    assert isinstance(lines[-1], RecordingEnded)
    assert lines[-1].reason == "game ended"


def test_a_recording_cut_off_mid_line_reads_up_to_the_cut(tmp_path: Path) -> None:
    plain_path = tmp_path / "game.jsonl"
    writer = RecordingWriter(plain_path, keyframe_interval_seconds=60.0)
    writer.write_started(started_at=STARTED_AT, recorder_version="test", poll_interval_seconds=0.5)
    writer.write_snapshot(received_at_seconds=0.0, payload=game_state(0.0, 0))
    writer.write_snapshot(received_at_seconds=0.5, payload=game_state(0.5, 1))
    writer.abandon()
    with plain_path.open("a", encoding="utf-8") as plain_file:
        plain_file.write('{"kind": "snapshot_delta", "received_at_sec')
    frames = list(iter_game_frames(plain_path))
    assert [frame.payload for frame in frames] == [game_state(0.0, 0), game_state(0.5, 1)]


def test_a_file_that_is_not_a_recording_is_refused(tmp_path: Path) -> None:
    not_a_recording = tmp_path / "notes.jsonl"
    not_a_recording.write_text('{"hello": "world"}\n')
    with pytest.raises(RecordingFormatError, match="recording_started"):
        list(iter_recording_lines(not_a_recording))


def test_a_newer_format_is_refused_rather_than_misread(tmp_path: Path) -> None:
    future_recording = tmp_path / "future.jsonl"
    future_recording.write_text(
        json.dumps(
            {
                "kind": "recording_started",
                "format_version": 99,
                "recorder_version": "later",
                "started_at": STARTED_AT.isoformat(),
                "poll_interval_seconds": 0.5,
            }
        )
        + "\n"
    )
    with pytest.raises(RecordingFormatError, match="version 99"):
        list(iter_recording_lines(future_recording))


def test_writing_starts_with_the_header(tmp_path: Path) -> None:
    writer = RecordingWriter(tmp_path / "game.jsonl", keyframe_interval_seconds=60.0)
    with pytest.raises(RecordingFormatError, match="write_started"):
        writer.write_snapshot(received_at_seconds=0.0, payload=game_state(0.0, 0))
