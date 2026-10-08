"""The tracer bullet: a recorded dragon kill, through the replay, the engine and the server."""

import asyncio
import datetime
from pathlib import Path
from typing import Final

import aiohttp
from pydantic import JsonValue

from game_payloads import DEFAULT_PLAYERS, all_game_data, dragon_kill_event, game_start_event
from leagueasymode.cli import run_overlay
from leagueasymode.config import Settings
from leagueasymode.overlay_state import OverlayState
from leagueasymode.recording.writer import RecordingWriter
from leagueasymode.replay import RecordingReplay, create_replay_application
from local_servers import serve

ENEMY_JUNGLER: Final = DEFAULT_PLAYERS[6].riot_id_game_name


def write_dragon_recording(directory: Path) -> Path:
    writer = RecordingWriter(directory / "game.jsonl", keyframe_interval_seconds=60.0)
    writer.write_started(
        started_at=datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC),
        recorder_version="test",
        poll_interval_seconds=0.5,
    )
    for index in range(40):
        game_time_seconds = 395.0 + index * 0.5
        events: list[dict[str, JsonValue]] = [game_start_event()]
        if game_time_seconds >= 400.0:
            events.append(dragon_kill_event(1, 400.0, ENEMY_JUNGLER, "Fire"))
        writer.write_snapshot(
            received_at_seconds=index * 0.5, payload=all_game_data(game_time_seconds, events)
        )
    writer.write_ended(received_at_seconds=20.0, reason="game ended")
    return writer.close()


async def test_a_recorded_dragon_kill_reaches_the_overlay(tmp_path: Path) -> None:
    replay = RecordingReplay(write_dragon_recording(tmp_path), speed=4.0)
    overlay_urls: list[str] = []
    async with serve(create_replay_application(replay)) as game_url:
        settings = Settings(
            game_api_base_url=game_url,
            poll_interval_seconds=0.02,
            record_while_running=False,
        )
        stop_requested = asyncio.Event()
        overlay_task = asyncio.create_task(
            run_overlay(settings, stop_requested, overlay_urls.append)
        )
        state = OverlayState(is_game_running=False)
        async with aiohttp.ClientSession() as session:
            for _ in range(200):
                await asyncio.sleep(0.02)
                if not overlay_urls:
                    continue
                async with session.get(overlay_urls[0] + "state") as response:
                    state = OverlayState.model_validate(await response.json())
                if state.dragon is not None and state.dragon.enemy_dragon_count == 1:
                    break
        stop_requested.set()
        await overlay_task
    assert overlay_urls[0].startswith("http://127.0.0.1:")
    assert state.is_game_running
    assert state.dragon is not None
    assert state.dragon.status == "respawning"
    assert state.dragon.spawns_at_game_time_seconds == 700.0
    assert (state.dragon.ally_dragon_count, state.dragon.enemy_dragon_count) == (0, 1)
