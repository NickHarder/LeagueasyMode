"""What the engine sees, part by part (phase 8.1): the status page's facts and the test's report."""

import asyncio
import datetime
import json
import ssl
from collections.abc import Callable
from pathlib import Path
from typing import Final

import aiohttp
from aiohttp import web
from aiohttp.client_reqrep import ConnectionKey
from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    GAME_ID,
    all_game_data,
    champion_kill_event,
    game_start_event,
    gameflow_session,
)
from leagueasymode.cli import note_league_settings, run_overlay
from leagueasymode.config import Settings
from leagueasymode.data_dragon import PatchStats
from leagueasymode.engine import OverlayEngine, PatchStatsLoader
from leagueasymode.engine_status import (
    PART_TITLES,
    READ_EVENT_NAMES,
    EngineStatus,
    StatusBoard,
)
from leagueasymode.game_api import GameApiClient, no_answer_of
from leagueasymode.game_summary import MONSTER_BY_EVENT
from leagueasymode.inference import gold, objectives
from leagueasymode.inference.clues import PIT_BY_EVENT
from leagueasymode.league_client import ClientConnector, LeagueClient
from leagueasymode.league_settings import DEFAULT_MINIMAP_LAYOUT
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.recorder import GAME_END_EVENT_NAME, RecorderTimings, record_one_game
from local_servers import serve, unused_local_url

FAST_TIMINGS: Final = RecorderTimings(
    poll_interval_seconds=0.01,
    idle_poll_interval_seconds=0.01,
    game_end_grace_seconds=0.3,
    timeline_wait_seconds=0.3,
    timeline_retry_seconds=0.02,
    lookup_pause_seconds=0.0,
)
STAND_IN_PASSWORD: Final = "stand-in"  # noqa: S105  the stand-in client's password
REPORTED_AT: Final = datetime.datetime(2026, 10, 9, 21, 30, tzinfo=datetime.UTC)
# How many times a test looks, 10 ms apart, for the status it waits for: up to 5 s.
STATUS_WAIT_STEPS: Final = 500
GAME_CONNECTION: Final = ConnectionKey(
    host="127.0.0.1",
    port=2999,
    is_ssl=True,
    ssl=True,
    proxy=None,
    proxy_auth=None,
    proxy_headers_hash=None,
    server_hostname=None,
)


def fixed_clock() -> datetime.datetime:
    return REPORTED_AT


def part_of(status: EngineStatus, key: str) -> tuple[str, str]:
    part = next(part for part in status.parts if part.key == key)
    return part.state, part.detail


def scripted_game(answers: list[JsonValue | None], status_code: int = 404) -> web.Application:
    """Answer each request with the next item; None, or running out, answers `status_code`."""
    remaining_answers = list(answers)
    application = web.Application()

    async def all_game_data_route(_request: web.Request) -> web.Response:
        answer = remaining_answers.pop(0) if remaining_answers else None
        if answer is None:
            return web.json_response({"errorCode": "RESOURCE_NOT_FOUND"}, status=status_code)
        return web.json_response(answer)

    application.router.add_get("/liveclientdata/allgamedata", all_game_data_route)
    return application


async def engine_status_when(
    answers: list[JsonValue | None],
    is_reached: Callable[[EngineStatus], bool],
    *,
    status_code: int = 404,
    connect_to_client: ClientConnector | None = None,
    load_patch_stats: PatchStatsLoader | None = None,
) -> EngineStatus:
    """Run the engine on a scripted game until its status is what the test waits for."""
    async with (
        serve(scripted_game(answers, status_code)) as game_url,
        aiohttp.ClientSession() as session,
    ):
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            connect_to_client=connect_to_client,
            load_patch_stats=load_patch_stats,
            status=StatusBoard(clock=fixed_clock),
        )
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        try:
            for _ in range(STATUS_WAIT_STEPS):
                if is_reached(engine.status.report()):
                    break
                await asyncio.sleep(0.01)
        finally:
            stop_requested.set()
            await engine_task
        return engine.status.report()


def game_is(state: str) -> Callable[[EngineStatus], bool]:
    return lambda status: part_of(status, "game")[0] == state


def test_before_anything_every_part_waits_in_its_order() -> None:
    status = StatusBoard(clock=fixed_clock).report()
    assert [part.key for part in status.parts] == list(PART_TITLES)
    assert {part.state for part in status.parts} == {"waiting"}
    assert status.events == []
    assert status.unreadable_fields == []
    assert status.reported_at == "2026-10-09T21:30:00+00:00"


def test_a_refused_certificate_is_a_problem_that_says_why() -> None:
    certificate_error = ssl.SSLCertVerificationError(1, "certificate verify failed")
    certificate_error.verify_message = "self-signed certificate in certificate chain"
    for error in (
        certificate_error,
        aiohttp.ClientConnectorCertificateError(GAME_CONNECTION, certificate_error),
    ):
        no_answer = no_answer_of(error)
        assert no_answer.is_problem
        assert "self-signed certificate in certificate chain" in no_answer.text
        assert "certificate" in no_answer.text


def test_a_timeout_is_waiting_and_any_other_failure_a_problem() -> None:
    assert not no_answer_of(TimeoutError()).is_problem
    assert no_answer_of(aiohttp.ServerDisconnectedError()).is_problem


async def test_nothing_listening_is_waiting_for_a_game() -> None:
    async with aiohttp.ClientSession() as session:
        game_api = GameApiClient(session, unused_local_url(), tls_context=None)
        assert await game_api.fetch_all_game_data() is None
        no_answer = game_api.last_no_answer
    assert no_answer is not None
    assert not no_answer.is_problem
    assert "no game is running" in no_answer.text


async def test_a_game_that_answers_says_so_and_lists_the_feeds_event_names() -> None:
    events: list[dict[str, JsonValue]] = [
        game_start_event(),
        champion_kill_event(1, 400.0, "Shadow Step", "Ahri", []),
        {"EventID": 2, "EventName": "FeatUpdate", "EventTime": 410.0},
    ]
    status = await engine_status_when([all_game_data(754.0, events)] * 200, game_is("ok"))
    assert part_of(status, "game") == ("ok", "Answering: CLASSIC on map 11, 12:34 in, 10 players")
    assert [(event.name, event.count, event.is_read) for event in status.events] == [
        ("ChampionKill", 1, True),
        ("FeatUpdate", 1, False),
        ("GameStart", 1, False),
    ]
    report_text = status.model_dump_json()
    for seed in DEFAULT_PLAYERS:
        assert seed.riot_id not in report_text
        assert (
            seed.riot_id_game_name == seed.champion_name
            or seed.riot_id_game_name not in report_text
        )


async def test_an_answer_that_cannot_be_read_is_a_problem_naming_the_fields() -> None:
    unreadable = all_game_data(60.0)
    assert isinstance(unreadable, dict)
    unreadable.pop("allPlayers")
    game_data = unreadable["gameData"]
    assert isinstance(game_data, dict)
    game_data["gameTime"] = "a minute"
    status = await engine_status_when([unreadable] * 200, game_is("problem"))
    state, detail = part_of(status, "game")
    assert state == "problem"
    assert detail.startswith("Answering, but 2 fields could not be read")
    assert status.unreadable_fields == ["allPlayers: missing", "gameData.gameTime: float_parsing"]


async def test_a_game_that_stops_answering_keeps_when_it_last_did() -> None:
    status = await engine_status_when(
        [all_game_data(60.0)],
        lambda status: "last answer" in part_of(status, "game")[1],
    )
    assert part_of(status, "game") == (
        "waiting",
        "The game is loading, or has ended (it answered 404); the last answer came at 21:30:00 UTC",
    )


async def test_an_error_status_is_a_problem() -> None:
    status = await engine_status_when([], game_is("problem"), status_code=500)
    assert part_of(status, "game") == ("problem", "The game answered HTTP 500")


async def test_without_the_client_or_patch_stats_each_part_says_so() -> None:
    async def no_client() -> LeagueClient | None:
        return None

    async def no_patch_stats(_game_version: str | None) -> PatchStats | None:
        return None

    status = await engine_status_when(
        [all_game_data(60.0)] * 200,
        lambda status: part_of(status, "patch")[0] == "problem",
        connect_to_client=no_client,
        load_patch_stats=no_patch_stats,
    )
    assert part_of(status, "client") == (
        "problem",
        "Not found when the game started: no lockfile, and no LeagueClientUx process",
    )
    assert part_of(status, "players") == (
        "problem",
        "Not looked up: the League client was not found",
    )
    assert part_of(status, "patch") == (
        "problem",
        "No stats for game version unknown: Data Dragon was not reached, and none are kept",
    )


def test_paths_start_at_the_home_folder() -> None:
    board = StatusBoard(home_directory=Path("/Users/player"))
    assert board.path_text(Path("/Users/player/Library/LeagueasyMode/x.json")) == (
        "~/Library/LeagueasyMode/x.json"
    )
    assert board.path_text(Path("/Applications/League of Legends.app")) == (
        "/Applications/League of Legends.app"
    )


def test_the_event_names_read_are_those_the_estimators_read() -> None:
    estimators_event_names = {
        objectives.DRAGON_KILL_EVENT,
        objectives.BARON_KILL_EVENT,
        objectives.INHIBITOR_KILLED_EVENT,
        objectives.INHIBITOR_RESPAWNED_EVENT,
        gold.CHAMPION_KILL_EVENT,
        gold.TURRET_KILLED_EVENT,
        GAME_END_EVENT_NAME,
        *MONSTER_BY_EVENT,
        *PIT_BY_EVENT,
    }
    assert estimators_event_names == READ_EVENT_NAMES


def stand_in_client(*, gives_timeline: bool) -> web.Application:
    application = web.Application()

    async def session_route(_request: web.Request) -> web.Response:
        return web.json_response(gameflow_session())

    async def timeline_route(_request: web.Request) -> web.Response:
        if gives_timeline:
            return web.json_response({"frames": []})
        return web.json_response({"message": "not found"}, status=404)

    application.router.add_get("/lol-gameflow/v1/session", session_route)
    application.router.add_get(f"/lol-match-history/v1/game-timelines/{GAME_ID}", timeline_route)
    return application


async def record_with_status(
    tmp_path: Path, client_application: web.Application | None
) -> EngineStatus:
    game_end: dict[str, JsonValue] = {"EventID": 9, "EventName": "GameEnd", "EventTime": 3.0}
    answers: list[JsonValue | None] = [
        all_game_data(float(index), [game_start_event()]) for index in range(3)
    ]
    answers.append(all_game_data(3.0, [game_start_event(), game_end]))
    board = StatusBoard(clock=fixed_clock)
    async with serve(scripted_game(answers)) as game_url, aiohttp.ClientSession() as session:
        game_api = GameApiClient(session, game_url, tls_context=None)

        async def no_client() -> LeagueClient | None:
            return None

        if client_application is None:
            await record_one_game(game_api, no_client, tmp_path, FAST_TIMINGS, status=board)
        else:
            async with serve(client_application) as client_url:

                async def connect() -> LeagueClient | None:
                    return LeagueClient(
                        session, client_url, password=STAND_IN_PASSWORD, tls_context=None
                    )

                await record_one_game(game_api, connect, tmp_path, FAST_TIMINGS, status=board)
    return board.report()


async def test_a_recorded_game_and_its_timeline_are_reported(tmp_path: Path) -> None:
    status = await record_with_status(tmp_path, stand_in_client(gives_timeline=True))
    recording_state, recording_detail = part_of(status, "recording")
    assert recording_state == "ok"
    assert recording_detail.startswith("Recorded game-") and recording_detail.endswith(
        ".jsonl.xz (game ended)"
    )
    assert part_of(status, "timeline") == ("ok", "Saved the timeline of the last game")


async def test_a_timeline_that_does_not_come_is_a_problem(tmp_path: Path) -> None:
    status = await record_with_status(tmp_path, stand_in_client(gives_timeline=False))
    assert part_of(status, "timeline") == (
        "problem",
        "The timeline of the last game did not come within 0.3 s; the game is scored without it",
    )


async def test_without_the_client_the_timeline_is_not_asked_for(tmp_path: Path) -> None:
    status = await record_with_status(tmp_path, None)
    assert part_of(status, "timeline") == (
        "problem",
        "Not asked for: the League client was not found when the game started",
    )


async def test_the_server_serves_the_status() -> None:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None),
            poll_interval_seconds=1,
            status=StatusBoard(clock=fixed_clock),
        )
        engine.status.set_part("models", "ok", "Hand-set weights: no refit yet")
        async with (
            serve(create_overlay_application(engine)) as overlay_url,
            session.get(overlay_url + "/status") as response,
        ):
            served = EngineStatus.model_validate(await response.json())
    assert part_of(served, "models") == ("ok", "Hand-set weights: no refit yet")


def test_the_contracts_schema_is_the_one_the_page_follows() -> None:
    schema_path = Path(__file__).parents[1] / "overlay" / "web" / "engine_status.schema.json"
    # run: uv run python -m leagueasymode.engine_status > overlay/web/engine_status.schema.json
    assert json.loads(schema_path.read_text()) == EngineStatus.model_json_schema()


async def test_the_command_reports_leagues_settings_the_models_and_recording(
    tmp_path: Path,
) -> None:
    game_config_path = tmp_path / "game.cfg"
    game_config_path.write_text("[HUD]\nMinimapScale=1.5000\nFlipMiniMap=1\n")
    settings = Settings(
        game_api_base_url=unused_local_url(),
        record_while_running=False,
        download_patch_stats=False,
        patch_data_directory=tmp_path / "patch-data",
        league_game_config=game_config_path,
    )
    overlay_urls: list[str] = []
    announced = asyncio.Event()

    def note_overlay_url(overlay_url: str) -> None:
        overlay_urls.append(overlay_url)
        announced.set()

    stop_requested = asyncio.Event()
    overlay_task = asyncio.create_task(run_overlay(settings, stop_requested, note_overlay_url))
    try:
        await asyncio.wait_for(announced.wait(), timeout=5)
        async with (
            aiohttp.ClientSession() as session,
            session.get(overlay_urls[0] + "status") as response,
        ):
            status = EngineStatus.model_validate(await response.json())
    finally:
        stop_requested.set()
        await overlay_task
    assert part_of(status, "settings") == (
        "ok",
        f"Read {game_config_path}: minimap scale 1.5, flipped",
    )
    assert part_of(status, "models") == ("ok", "Hand-set weights: no refit yet")
    assert part_of(status, "recording") == (
        "off",
        "Off: LEAGUEASYMODE_RECORD_WHILE_RUNNING is false",
    )


async def test_a_missing_settings_file_leaves_the_minimap_in_its_default_place(
    tmp_path: Path,
) -> None:
    board = StatusBoard(home_directory=tmp_path)
    note_league_settings(board, tmp_path / "Config" / "game.cfg", DEFAULT_MINIMAP_LAYOUT)
    assert part_of(board.report(), "settings") == (
        "waiting",
        "Not found at ~/Config/game.cfg: the minimap layer takes its default place",
    )
