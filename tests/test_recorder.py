import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Final

import aiohttp
from aiohttp import web
from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    GAME_ID,
    all_game_data,
    champion_summary,
    game_start_event,
    gameflow_session,
    match_history,
    puuid_of,
    ranked_stats,
)
from leagueasymode.game_api import GameApiClient
from leagueasymode.league_client import LeagueClient
from leagueasymode.recorder import RecorderTimings, record_one_game
from leagueasymode.recording.file_format import ClientResource, RecordingEnded
from leagueasymode.recording.reader import iter_game_frames, iter_recording_lines
from local_servers import serve, unused_local_url

FAST_TIMINGS: Final = RecorderTimings(
    poll_interval_seconds=0.01,
    idle_poll_interval_seconds=0.01,
    game_end_grace_seconds=0.3,
    timeline_wait_seconds=1.0,
    timeline_retry_seconds=0.02,
    lookup_pause_seconds=0.0,
)
STAND_IN_PASSWORD: Final = "stand-in"  # noqa: S105  the stand-in client's password
TIMELINE: Final[JsonValue] = {"frames": [{"timestamp": 0, "participantFrames": {}}]}


def game_time_of(payload: JsonValue) -> JsonValue:
    game_data = payload.get("gameData") if isinstance(payload, dict) else None
    return game_data.get("gameTime") if isinstance(game_data, dict) else None


def game_end_event(event_time: float) -> dict[str, JsonValue]:
    return {"EventID": 9, "EventName": "GameEnd", "EventTime": event_time, "Result": "Win"}


def scripted_game(answers: list[JsonValue | None]) -> web.Application:
    """Answer each request with the next item; None, or running out, is the game not answering."""
    remaining_answers = list(answers)
    application = web.Application()

    async def all_game_data_route(_request: web.Request) -> web.Response:
        answer = remaining_answers.pop(0) if remaining_answers else None
        if answer is None:
            return web.json_response({"errorCode": "RESOURCE_NOT_FOUND"}, status=404)
        return web.json_response(answer)

    application.router.add_get("/liveclientdata/allgamedata", all_game_data_route)
    return application


def stand_in_client(timeline_misses: int) -> web.Application:
    """A League client whose timeline turns up after a few tries, as it does after a real game."""
    application = web.Application()
    timeline_requests: list[int] = []

    async def session_route(_request: web.Request) -> web.Response:
        return web.json_response(gameflow_session())

    async def items_route(_request: web.Request) -> web.Response:
        return web.json_response([{"id": 1001, "name": "Boots", "priceTotal": 300}])

    async def timeline_route(_request: web.Request) -> web.Response:
        timeline_requests.append(1)
        if len(timeline_requests) <= timeline_misses:
            return web.json_response({"message": "not found"}, status=404)
        return web.json_response(TIMELINE)

    application.router.add_get("/lol-gameflow/v1/session", session_route)
    application.router.add_get("/lol-game-data/assets/v1/items.json", items_route)
    application.router.add_get(f"/lol-match-history/v1/game-timelines/{GAME_ID}", timeline_route)
    return application


def a_game_of(snapshot_count: int, ends_with_game_end: bool) -> list[JsonValue | None]:
    loading: list[JsonValue | None] = [None, None]
    snapshots: list[JsonValue | None] = [
        all_game_data(float(index), [game_start_event()]) for index in range(snapshot_count)
    ]
    if ends_with_game_end:
        snapshots.append(
            all_game_data(
                float(snapshot_count), [game_start_event(), game_end_event(float(snapshot_count))]
            )
        )
    return loading + snapshots


async def record(
    tmp_path: Path,
    game_answers: list[JsonValue | None],
    client_application: web.Application | None,
) -> Path:
    async with serve(scripted_game(game_answers)) as game_url, aiohttp.ClientSession() as session:
        game_api = GameApiClient(session, game_url, tls_context=None)
        if client_application is None:
            recording_path = await record_one_game(game_api, no_client(), tmp_path, FAST_TIMINGS)
        else:
            async with serve(client_application) as client_url:
                recording_path = await record_one_game(
                    game_api, client_at(session, client_url), tmp_path, FAST_TIMINGS
                )
    assert recording_path is not None
    return recording_path


def client_at(
    session: aiohttp.ClientSession, client_url: str
) -> Callable[[], Awaitable[LeagueClient | None]]:
    async def connect() -> LeagueClient | None:
        return LeagueClient(session, client_url, password=STAND_IN_PASSWORD, tls_context=None)

    return connect


def no_client() -> Callable[[], Awaitable[LeagueClient | None]]:
    async def connect() -> LeagueClient | None:
        return None

    return connect


async def test_a_whole_game_is_recorded_with_the_clients_data_and_timeline(tmp_path: Path) -> None:
    recording_path = await record(
        tmp_path, a_game_of(5, ends_with_game_end=True), stand_in_client(timeline_misses=2)
    )
    assert recording_path.name.startswith("game-") and recording_path.name.endswith(".jsonl.xz")
    game_times = [game_time_of(frame.payload) for frame in iter_game_frames(recording_path)]
    assert game_times == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    lines = list(iter_recording_lines(recording_path))
    resources = {line.path: line.payload for line in lines if isinstance(line, ClientResource)}
    assert resources["/lol-gameflow/v1/session"] == gameflow_session()
    assert resources["/lol-game-data/assets/v1/items.json"] == [
        {"id": 1001, "name": "Boots", "priceTotal": 300}
    ]
    assert resources[f"/lol-match-history/v1/game-timelines/{GAME_ID}"] == TIMELINE
    assert isinstance(lines[-1], RecordingEnded)
    assert lines[-1].reason == "game ended"


async def test_without_the_client_the_game_is_still_recorded(tmp_path: Path) -> None:
    recording_path = await record(tmp_path, a_game_of(3, ends_with_game_end=True), None)
    lines = list(iter_recording_lines(recording_path))
    assert len(list(iter_game_frames(recording_path))) == 4
    assert not [line for line in lines if isinstance(line, ClientResource)]


async def test_a_game_that_stops_answering_is_closed_after_the_grace_period(tmp_path: Path) -> None:
    recording_path = await record(tmp_path, a_game_of(3, ends_with_game_end=False), None)
    last_line = list(iter_recording_lines(recording_path))[-1]
    assert isinstance(last_line, RecordingEnded)
    assert last_line.reason == "the game stopped answering"


async def test_a_timeline_that_never_comes_is_given_up_on(tmp_path: Path) -> None:
    recording_path = await record(
        tmp_path, a_game_of(2, ends_with_game_end=True), stand_in_client(timeline_misses=10_000)
    )
    paths = [
        line.path
        for line in iter_recording_lines(recording_path)
        if isinstance(line, ClientResource)
    ]
    assert f"/lol-match-history/v1/game-timelines/{GAME_ID}" not in paths
    assert "/lol-gameflow/v1/session" in paths


async def test_stopping_mid_game_keeps_what_was_recorded(tmp_path: Path) -> None:
    endless_game = [all_game_data(float(index), [game_start_event()]) for index in range(200)]
    async with (
        serve(scripted_game(list(endless_game))) as game_url,
        aiohttp.ClientSession() as session,
    ):
        game_api = GameApiClient(session, game_url, tls_context=None)
        stop_requested = asyncio.Event()
        recording_task = asyncio.create_task(
            record_one_game(game_api, no_client(), tmp_path, FAST_TIMINGS, stop_requested)
        )
        await asyncio.sleep(0.3)
        stop_requested.set()
        recording_path = await recording_task
    assert recording_path is not None
    last_line = list(iter_recording_lines(recording_path))[-1]
    assert isinstance(last_line, RecordingEnded)
    assert last_line.reason == "recording stopped"
    assert len(list(iter_game_frames(recording_path))) > 3


async def test_nothing_is_written_until_a_game_answers(tmp_path: Path) -> None:
    async with aiohttp.ClientSession() as session:
        game_api = GameApiClient(session, unused_local_url(), tls_context=None)
        stop_requested = asyncio.Event()
        waiting = asyncio.create_task(
            record_one_game(game_api, no_client(), tmp_path, FAST_TIMINGS, stop_requested)
        )
        await asyncio.sleep(0.2)
        stop_requested.set()
        recording_path = await waiting
    assert recording_path is None
    assert await asyncio.to_thread(lambda: list(tmp_path.iterdir())) == []


async def test_each_players_rank_and_recent_games_are_recorded(tmp_path: Path) -> None:
    client_application = stand_in_client(timeline_misses=0)
    zed_puuid = puuid_of(DEFAULT_PLAYERS[7])

    async def summary_route(_request: web.Request) -> web.Response:
        return web.json_response(champion_summary())

    async def ranked_route(_request: web.Request) -> web.Response:
        return web.json_response(ranked_stats("GOLD", "I", 75, 20, 18))

    async def history_route(request: web.Request) -> web.Response:
        return web.json_response(match_history(request.match_info["puuid"], []))

    client_application.router.add_get(
        "/lol-game-data/assets/v1/champion-summary.json", summary_route
    )
    client_application.router.add_get("/lol-ranked/v1/ranked-stats/{puuid}", ranked_route)
    client_application.router.add_get(
        "/lol-match-history/v1/products/lol/{puuid}/matches", history_route
    )
    recording_path = await record(
        tmp_path, a_game_of(5, ends_with_game_end=True), client_application
    )
    paths = {
        line.path
        for line in iter_recording_lines(recording_path)
        if isinstance(line, ClientResource)
    }
    assert f"/lol-ranked/v1/ranked-stats/{zed_puuid}" in paths
    assert f"/lol-match-history/v1/products/lol/{zed_puuid}/matches?begIndex=0&endIndex=20" in paths
