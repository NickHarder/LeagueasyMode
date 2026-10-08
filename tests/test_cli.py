import asyncio
import datetime
from pathlib import Path

import pytest
from aiohttp import web
from pydantic import JsonValue

from game_payloads import all_game_data, game_start_event
from leagueasymode.cli import main, record_until_stopped
from leagueasymode.config import Settings, default_recordings_directory
from leagueasymode.recording.reader import iter_game_frames
from leagueasymode.recording.writer import RecordingWriter
from local_servers import serve


def write_recording(directory: Path, player_name: str) -> Path:
    writer = RecordingWriter(directory / "game.jsonl")
    writer.write_started(
        started_at=datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC),
        recorder_version="test",
        poll_interval_seconds=0.5,
    )
    writer.write_snapshot(received_at_seconds=0.0, payload=all_game_data(1.0))
    writer.write_client_resource(
        received_at_seconds=0.1, path="/lol-chat/v1/note", payload={"body": f"gg {player_name}"}
    )
    writer.write_ended(received_at_seconds=1.0, reason="game ended")
    return writer.close()


def test_anonymize_writes_a_copy_beside_the_recording(tmp_path: Path) -> None:
    source_path = write_recording(tmp_path, player_name="nobody in particular")
    assert main(["anonymize", str(source_path)]) == 0
    copy_path = tmp_path / "game-anonymized.jsonl.xz"
    assert len(list(iter_game_frames(copy_path))) == 1


def test_anonymize_refuses_when_a_name_would_stay(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source_path = write_recording(tmp_path, player_name="Shadow Step")
    assert main(["anonymize", str(source_path)]) == 1
    assert "an identity would stay" in caplog.text
    assert not (tmp_path / "game-anonymized.jsonl.xz").exists()


def test_the_command_list_is_shown_without_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
    assert "record" in capsys.readouterr().err


def test_recordings_go_to_application_support_on_a_mac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    assert default_recordings_directory() == (
        Path.home() / "Library" / "Application Support" / "LeagueasyMode" / "recordings"
    )


async def test_record_records_a_game_until_stopped(tmp_path: Path) -> None:
    game_over: JsonValue = all_game_data(
        2.0,
        [
            game_start_event(),
            {"EventID": 1, "EventName": "GameEnd", "EventTime": 2.0, "Result": "Win"},
        ],
    )
    answers: list[JsonValue] = [all_game_data(1.0), game_over]
    application = web.Application()

    async def game_route(_request: web.Request) -> web.Response:
        if answers:
            return web.json_response(answers.pop(0))
        return web.json_response({"errorCode": "RESOURCE_NOT_FOUND"}, status=404)

    application.router.add_get("/liveclientdata/allgamedata", game_route)
    async with serve(application) as game_url:
        settings = Settings(
            game_api_base_url=game_url,
            poll_interval_seconds=0.01,
            recordings_directory=tmp_path,
            league_client_lockfile=tmp_path / "no-lockfile",
        )
        stop_requested = asyncio.Event()
        recording_task = asyncio.create_task(
            record_until_stopped(settings, stop_requested, idle_poll_interval_seconds=0.01)
        )
        for _ in range(200):
            if await asyncio.to_thread(lambda: list(tmp_path.glob("*.jsonl.xz"))):
                break
            await asyncio.sleep(0.02)
        stop_requested.set()
        recording_paths = await recording_task
    assert len(recording_paths) == 1
    assert len(list(iter_game_frames(recording_paths[0]))) == 2
