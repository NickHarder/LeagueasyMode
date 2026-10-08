import datetime
from pathlib import Path

import aiohttp

from game_payloads import all_game_data
from leagueasymode.recording.writer import RecordingWriter
from leagueasymode.replay import RecordingReplay, create_replay_application
from local_servers import serve


class ManualClock:
    def __init__(self) -> None:
        self.now_seconds = 100.0

    def __call__(self) -> float:
        return self.now_seconds


def write_recording(directory: Path) -> Path:
    writer = RecordingWriter(directory / "game.jsonl", keyframe_interval_seconds=1.0)
    writer.write_started(
        started_at=datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC),
        recorder_version="test",
        poll_interval_seconds=0.5,
    )
    for index in range(10):
        writer.write_snapshot(
            received_at_seconds=5.0 + index * 0.5, payload=all_game_data(60.0 + index * 0.5)
        )
    writer.write_ended(received_at_seconds=10.0, reason="game ended")
    return writer.close()


def game_time(payload: object) -> object:
    assert isinstance(payload, dict)
    game_data = payload["gameData"]
    assert isinstance(game_data, dict)
    return game_data["gameTime"]


def test_the_replay_starts_at_the_first_snapshot(tmp_path: Path) -> None:
    replay = RecordingReplay(write_recording(tmp_path), speed=1.0, clock=ManualClock())
    assert game_time(replay.payload_now()) == 60.0


def test_the_replay_serves_the_snapshot_of_the_moment(tmp_path: Path) -> None:
    clock = ManualClock()
    replay = RecordingReplay(write_recording(tmp_path), speed=1.0, clock=clock)
    clock.now_seconds += 1.2
    assert game_time(replay.payload_now()) == 61.0
    clock.now_seconds += 2.0
    assert game_time(replay.payload_now()) == 63.0


def test_a_faster_replay_moves_through_the_game_faster(tmp_path: Path) -> None:
    clock = ManualClock()
    replay = RecordingReplay(write_recording(tmp_path), speed=10.0, clock=clock)
    # Between two snapshots, not on one, so that rounding cannot pick the neighbour.
    clock.now_seconds += 0.32
    assert game_time(replay.payload_now()) == 63.0


def test_after_the_last_snapshot_the_game_is_gone(tmp_path: Path) -> None:
    clock = ManualClock()
    replay = RecordingReplay(write_recording(tmp_path), speed=1.0, clock=clock)
    clock.now_seconds += 60.0
    assert replay.payload_now() is None


async def test_the_replay_answers_like_the_game(tmp_path: Path) -> None:
    clock = ManualClock()
    replay = RecordingReplay(write_recording(tmp_path), speed=1.0, clock=clock)
    async with (
        serve(create_replay_application(replay)) as base_url,
        aiohttp.ClientSession() as session,
    ):
        async with session.get(base_url + "/liveclientdata/allgamedata") as all_data_response:
            assert all_data_response.status == 200
            assert game_time(await all_data_response.json()) == 60.0
        async with session.get(base_url + "/liveclientdata/gamestats") as game_stats_response:
            assert (await game_stats_response.json())["gameTime"] == 60.0
        clock.now_seconds += 60.0
        async with session.get(base_url + "/liveclientdata/allgamedata") as gone_response:
            assert gone_response.status == 404


def write_recording_with_client_data(directory: Path) -> Path:
    writer = RecordingWriter(directory / "client.jsonl", keyframe_interval_seconds=1.0)
    writer.write_started(
        started_at=datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC),
        recorder_version="test",
        poll_interval_seconds=0.5,
    )
    writer.write_snapshot(received_at_seconds=0.0, payload=all_game_data(10.0))
    writer.write_client_resource(
        received_at_seconds=0.2,
        path="/lol-game-data/assets/v1/items.json",
        payload=[{"id": 1036, "name": "Long Sword", "priceTotal": 350}],
    )
    writer.write_client_resource(
        received_at_seconds=30.0,
        path="/lol-match-history/v1/game-timelines/1",
        payload={"frames": []},
    )
    for index in range(1, 80):
        writer.write_snapshot(
            received_at_seconds=index * 0.5, payload=all_game_data(10.0 + index * 0.5)
        )
    writer.write_ended(received_at_seconds=40.0, reason="game ended")
    return writer.close()


async def test_the_replay_serves_the_clients_resources_once_reached(tmp_path: Path) -> None:
    clock = ManualClock()
    replay = RecordingReplay(write_recording_with_client_data(tmp_path), speed=1.0, clock=clock)
    async with (
        serve(create_replay_application(replay)) as base_url,
        aiohttp.ClientSession() as session,
    ):
        clock.now_seconds += 1.0
        async with session.get(base_url + "/lol-game-data/assets/v1/items.json") as items_response:
            assert items_response.status == 200
            assert (await items_response.json())[0]["name"] == "Long Sword"
        async with session.get(
            base_url + "/lol-match-history/v1/game-timelines/1"
        ) as early_response:
            assert early_response.status == 404
        async with session.get(base_url + "/lol-gameflow/v1/session") as unknown_response:
            assert unknown_response.status == 404
        clock.now_seconds += 30.0
        async with session.get(
            base_url + "/lol-match-history/v1/game-timelines/1"
        ) as late_response:
            assert late_response.status == 200
