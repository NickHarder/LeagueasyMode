"""Crash reports: what went wrong in the engine, with nothing of the game in it."""

import asyncio
import datetime
import json
import lzma
import traceback
from pathlib import Path
from typing import Final

import aiohttp
import pytest
from aiohttp import web

from game_payloads import all_game_data
from leagueasymode import cli, engine
from leagueasymode.crash_reports import (
    CRASH_REPORTS_FOLDER,
    ErrorReporter,
    code_frames,
    crash_report,
    keep_running,
)
from leagueasymode.engine import OverlayEngine
from leagueasymode.engine_status import StatusBoard
from leagueasymode.game_api import GameApiClient
from leagueasymode.recording.reader import iter_recording_lines
from leagueasymode.recording.sender import finish_interrupted_recordings
from local_servers import serve
from test_anonymize import write_source_recording

NOW: Final = datetime.datetime(2026, 10, 28, 2, 30, tzinfo=datetime.UTC)
PLAYER_NAME: Final = "Shadow Step"


def a_raised_error() -> KeyError:
    try:
        raise KeyError(PLAYER_NAME)
    except KeyError as error:
        return error


def test_the_frames_name_the_code_and_no_folder_of_the_player() -> None:
    frames = [
        traceback.FrameSummary(
            "/Users/someone/project/.venv/lib/python3.12/asyncio/tasks.py", 314, "step"
        ),
        traceback.FrameSummary(
            "/Users/someone/.cache/uv/archive/site-packages/leagueasymode/engine.py", 433, "run"
        ),
        traceback.FrameSummary(
            "/Users/someone/.cache/uv/archive/site-packages/aiohttp/client.py", 703, "_request"
        ),
        traceback.FrameSummary("/Users/someone/Desktop/notes/script.py", 7, "main"),
    ]
    assert code_frames(frames) == [
        "asyncio/tasks.py:314 in step",
        "leagueasymode/engine.py:433 in run",
        "aiohttp/client.py:703 in _request",
        "script.py:7 in main",
    ]


def test_a_report_holds_the_errors_kind_and_never_its_message() -> None:
    report = crash_report("the engine", a_raised_error(), now=NOW)
    assert report.where == "the engine"
    assert report.error_type == "KeyError"
    assert report.happened_at == NOW
    assert report.frames[-1].endswith("in a_raised_error")
    report_json = report.model_dump_json()
    assert PLAYER_NAME not in report_json
    assert "/home/" not in report_json and "/Users/" not in report_json


def test_each_new_error_is_written_once_and_shown(tmp_path: Path) -> None:
    board = StatusBoard(home_directory=tmp_path)
    reporter = ErrorReporter(tmp_path / CRASH_REPORTS_FOLDER, board, clock=lambda: NOW)
    for _ in range(3):
        reporter.report("the engine", a_raised_error())
    reporter.report("the recorder", ValueError("bad"))
    written = sorted((tmp_path / CRASH_REPORTS_FOLDER).iterdir())
    assert len(written) == 2
    assert {json.loads(path.read_text())["where"] for path in written} == {
        "the engine",
        "the recorder",
    }
    part = next(part for part in board.report().parts if part.key == "errors")
    assert part.state == "problem"
    assert part.detail.startswith("4 so far; the last in the recorder: ValueError at ")


async def test_a_job_that_fails_is_reported_and_started_again(tmp_path: Path) -> None:
    board = StatusBoard(home_directory=tmp_path)
    reporter = ErrorReporter(tmp_path / CRASH_REPORTS_FOLDER, board, clock=lambda: NOW)
    runs: list[int] = []

    async def flaky_job() -> None:
        runs.append(len(runs))
        if len(runs) < 3:
            raise RuntimeError("not yet")

    await keep_running(
        "the recorder", flaky_job, reporter, asyncio.Event(), restart_pause_seconds=0.0
    )
    assert runs == [0, 1, 2]
    assert len(list((tmp_path / CRASH_REPORTS_FOLDER).iterdir())) == 1


async def test_the_engine_goes_on_after_an_answer_it_could_not_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    board = StatusBoard(home_directory=tmp_path)
    reporter = ErrorReporter(tmp_path / CRASH_REPORTS_FOLDER, board, clock=lambda: NOW)
    real_compute = engine.compute_overlay_state
    calls: list[int] = []

    def failing_once(*arguments: object, **options: object) -> object:
        calls.append(1)
        if len(calls) == 1:
            raise ZeroDivisionError("division by zero")
        return real_compute(*arguments, **options)  # type: ignore[arg-type]

    monkeypatch.setattr(engine, "compute_overlay_state", failing_once)
    game = web.Application()

    async def answer(_request: web.Request) -> web.Response:
        return web.json_response(all_game_data(60.0))

    game.router.add_get("/liveclientdata/allgamedata", answer)
    async with serve(game) as game_url, aiohttp.ClientSession() as session:
        overlay_engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            status=board,
            on_error=reporter.report,
        )
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(overlay_engine.run(stop_requested))
        for _ in range(200):
            if overlay_engine.current_state.is_game_running:
                break
            await asyncio.sleep(0.01)
        stop_requested.set()
        await engine_task
    assert overlay_engine.current_state.is_game_running
    reports = list((tmp_path / CRASH_REPORTS_FOLDER).iterdir())
    assert [json.loads(path.read_text())["error_type"] for path in reports] == ["ZeroDivisionError"]


def test_a_recording_cut_off_by_a_crash_is_finished_so_it_can_be_sent(tmp_path: Path) -> None:
    source = write_source_recording(tmp_path)
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    # The plain file a crash leaves: every line but the last whole, and no end.
    whole_text = lzma.decompress(source.read_bytes()).decode("utf-8")
    cut_text = whole_text.rsplit("\n", 2)[0] + '\n{"kind": "snapsh'
    (recordings / "game-cut.jsonl").write_text(cut_text)
    finished = finish_interrupted_recordings(recordings)
    assert [path.name for path in finished] == ["game-cut.jsonl.xz"]
    assert not (recordings / "game-cut.jsonl").exists()
    kinds = [type(line).__name__ for line in iter_recording_lines(finished[0])]
    assert kinds[0] == "RecordingStarted"
    assert "RecordingEnded" not in kinds


def test_a_crash_at_start_leaves_a_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def crashing_run_overlay(*_arguments: object) -> None:
        raise OSError("the port is taken")

    monkeypatch.setattr(cli, "run_overlay", crashing_run_overlay)
    monkeypatch.setenv("LEAGUEASYMODE_RECORDINGS_DIRECTORY", str(tmp_path))
    with pytest.raises(OSError, match="port"):
        cli.main(["run"])
    reports = list((tmp_path / CRASH_REPORTS_FOLDER).iterdir())
    assert [json.loads(path.read_text())["where"] for path in reports] == ["running the engine"]
