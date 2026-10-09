import asyncio
import contextlib
import dataclasses
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Final

import aiohttp
import pytest
from aiohttp import web
from pydantic import JsonValue

from data_dragon_fixtures import fixture_patch_stats
from game_payloads import DEFAULT_PLAYERS, all_game_data, dragon_kill_event, game_start_event
from leagueasymode.accuracy_history import GameAccuracy, append_game_accuracy
from leagueasymode.data_dragon import PatchStats
from leagueasymode.engine import OverlayEngine, compute_overlay_state
from leagueasymode.game_api import GameApiClient
from leagueasymode.league_client import LeagueClient
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.overlay_state import OverlayState
from leagueasymode.scoring import EstimatorScore
from local_servers import serve, unused_local_url

ENEMY_JUNGLER: Final = DEFAULT_PLAYERS[6].riot_id_game_name
SCHEMA_PATH: Final = Path(__file__).parents[1] / "overlay" / "web" / "overlay_state.schema.json"


def game_with_a_dragon_taken_at(kill_time_seconds: float, game_time_seconds: float) -> JsonValue:
    return all_game_data(
        game_time_seconds,
        [game_start_event(), dragon_kill_event(1, kill_time_seconds, ENEMY_JUNGLER)],
    )


def test_no_answer_is_no_game() -> None:
    assert compute_overlay_state(None) == OverlayState(is_game_running=False)


def test_an_answer_becomes_the_overlays_state() -> None:
    state = compute_overlay_state(game_with_a_dragon_taken_at(400.0, 450.0))
    assert state.is_game_running
    assert state.game_time_seconds == 450.0
    assert state.dragon is not None
    assert state.dragon.spawns_at_game_time_seconds == 700.0
    assert state.dragon.enemy_dragon_count == 1


def test_an_answer_in_a_shape_never_seen_is_no_game(caplog: pytest.LogCaptureFixture) -> None:
    assert compute_overlay_state({"gameData": "surprise"}) == OverlayState(is_game_running=False)
    assert "could not read" in caplog.text


def test_the_widgets_contract_file_is_current() -> None:
    # overlay/web/src/state.ts mirrors this schema. When the contract changes, change that file and
    # run: uv run python -m leagueasymode.overlay_state > overlay/web/overlay_state.schema.json
    assert json.loads(SCHEMA_PATH.read_text()) == OverlayState.model_json_schema()


def scripted_game(answers: list[JsonValue]) -> web.Application:
    application = web.Application()

    async def answer(_request: web.Request) -> web.Response:
        if answers:
            return web.json_response(answers.pop(0))
        return web.json_response({"errorCode": "RESOURCE_NOT_FOUND"}, status=404)

    application.router.add_get("/liveclientdata/allgamedata", answer)
    return application


async def test_the_engine_tells_each_subscriber_every_new_state() -> None:
    answers = [game_with_a_dragon_taken_at(400.0, 450.0 + index) for index in range(3)]
    async with serve(scripted_game(answers)) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None), poll_interval_seconds=0.01
        )
        updates = engine.subscribe()
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        received_times = [
            (await asyncio.wait_for(updates.get(), timeout=2)).game_time_seconds for _ in range(3)
        ]
        stop_requested.set()
        await engine_task
    assert received_times == [450.0, 451.0, 452.0]


async def test_the_state_and_its_stream_are_served() -> None:
    answers = [game_with_a_dragon_taken_at(400.0, 450.0 + index) for index in range(50)]
    async with serve(scripted_game(answers)) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None), poll_interval_seconds=0.02
        )
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        async with serve(create_overlay_application(engine)) as overlay_url:
            await asyncio.sleep(0.1)
            async with session.get(overlay_url + "/state") as state_response:
                state = OverlayState.model_validate(await state_response.json())
            assert state.is_game_running
            async with session.get(overlay_url + "/events") as events_response:
                assert events_response.headers["Content-Type"].startswith("text/event-stream")
                first_event = await asyncio.wait_for(
                    events_response.content.readuntil(b"\n\n"), timeout=2
                )
                second_event = await asyncio.wait_for(
                    events_response.content.readuntil(b"\n\n"), timeout=2
                )
        stop_requested.set()
        await engine_task
    first_state = OverlayState.model_validate_json(first_event.decode().removeprefix("data: "))
    second_state = OverlayState.model_validate_json(second_event.decode().removeprefix("data: "))
    assert first_state.game_time_seconds is not None and second_state.game_time_seconds is not None
    assert second_state.game_time_seconds > first_state.game_time_seconds


async def test_the_page_and_its_script_are_served() -> None:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        async with serve(create_overlay_application(engine)) as overlay_url:
            async with session.get(overlay_url + "/") as page_response:
                page = await page_response.text()
            async with session.get(overlay_url + "/overlay.js") as script_response:
                script_type = script_response.headers["Content-Type"]
    assert '<script type="module" src="/overlay.js">' in page
    assert script_type.startswith("text/javascript")


async def test_a_request_for_another_host_is_refused() -> None:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        async with serve(create_overlay_application(engine)) as overlay_url:
            async with session.get(
                overlay_url + "/state", headers={"Host": "attacker.example:80"}
            ) as refused_response:
                assert refused_response.status == 403
            async with session.get(
                overlay_url + "/state", headers={"Host": "localhost"}
            ) as allowed_response:
                assert allowed_response.status == 200


def test_the_state_carries_every_objective_buff_and_inhibitor() -> None:
    state = compute_overlay_state(game_with_a_dragon_taken_at(400.0, 450.0))
    assert [timer.objective for timer in state.objectives] == ["voidgrubs", "rift_herald", "baron"]
    assert state.buffs == []
    assert state.inhibitors == []


async def test_the_server_stops_promptly_while_a_page_still_listens() -> None:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        runner = web.AppRunner(create_overlay_application(engine))
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        host, port = runner.addresses[0][:2]
        async with session.get(f"http://{host}:{port}/events") as events_response:
            await events_response.content.readuntil(b"\n\n")
            started_at = asyncio.get_running_loop().time()
            await asyncio.wait_for(runner.cleanup(), timeout=10)
            stop_seconds = asyncio.get_running_loop().time() - started_at
    assert stop_seconds < 2.0


def test_the_state_carries_the_players_and_the_numbers_window() -> None:
    state = compute_overlay_state(game_with_a_dragon_taken_at(400.0, 450.0))
    assert len(state.players) == 10
    assert state.numbers_window is None


async def test_the_engine_adds_a_callout_when_an_enemy_reaches_level_six() -> None:
    def game_at(game_time_seconds: float, zed_level: int) -> JsonValue:
        players = tuple(
            dataclasses.replace(seed, level=zed_level) if seed.champion_name == "Zed" else seed
            for seed in DEFAULT_PLAYERS
        )
        return all_game_data(game_time_seconds, [game_start_event()], players=players)

    answers = [game_at(400.0, 5), game_at(401.0, 6)]
    async with serve(scripted_game(answers)) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None), poll_interval_seconds=0.01
        )
        updates = engine.subscribe()
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        first_state = await asyncio.wait_for(updates.get(), timeout=2)
        second_state = await asyncio.wait_for(updates.get(), timeout=2)
        stop_requested.set()
        await engine_task
    assert first_state.callouts == []
    assert [callout.text for callout in second_state.callouts] == ["Zed is level 6"]


async def test_the_engine_loads_the_item_catalog_from_the_client_when_a_game_starts() -> None:
    answers = [game_with_a_dragon_taken_at(400.0, 450.0 + index) for index in range(20)]
    client_application = web.Application()

    async def items_route(_request: web.Request) -> web.Response:
        return web.json_response([{"id": 3031, "name": "Infinity Edge", "priceTotal": 3400}])

    client_application.router.add_get("/lol-game-data/assets/v1/items.json", items_route)
    async with (
        serve(scripted_game(answers)) as game_url,
        serve(client_application) as client_url,
        aiohttp.ClientSession() as session,
    ):

        async def connect_to_client() -> LeagueClient | None:
            return LeagueClient(session, client_url, password="", tls_context=None)

        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            connect_to_client=connect_to_client,
        )
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        for _ in range(100):
            if engine.item_catalog is not None:
                break
            await asyncio.sleep(0.01)
        stop_requested.set()
        await engine_task
    assert engine.item_catalog is not None
    assert engine.item_catalog.total_price(3031) == 3400


def league_client_with_game_version(game_version: str) -> web.Application:
    client_application = web.Application()

    async def items_route(_request: web.Request) -> web.Response:
        return web.json_response([{"id": 3031, "name": "Infinity Edge", "priceTotal": 3400}])

    async def game_version_route(_request: web.Request) -> web.Response:
        return web.json_response(game_version)

    client_application.router.add_get("/lol-game-data/assets/v1/items.json", items_route)
    client_application.router.add_get("/lol-patch/v1/game-version", game_version_route)
    return client_application


async def run_engine_until(engine: OverlayEngine, is_done: Callable[[], bool]) -> None:
    stop_requested = asyncio.Event()
    engine_task = asyncio.create_task(engine.run(stop_requested))
    for _ in range(200):
        if is_done():
            break
        await asyncio.sleep(0.01)
    stop_requested.set()
    await engine_task


async def test_the_engine_loads_the_patch_stats_of_the_clients_game_version() -> None:
    answers = [game_with_a_dragon_taken_at(400.0, 450.0 + index) for index in range(50)]
    asked_game_versions: list[str | None] = []

    async def load_patch_stats(game_version: str | None) -> PatchStats | None:
        asked_game_versions.append(game_version)
        return fixture_patch_stats()

    async with (
        serve(scripted_game(answers)) as game_url,
        serve(league_client_with_game_version("16.19.712.1234")) as client_url,
        aiohttp.ClientSession() as session,
    ):

        async def connect_to_client() -> LeagueClient | None:
            return LeagueClient(session, client_url, password="", tls_context=None)

        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            connect_to_client=connect_to_client,
            load_patch_stats=load_patch_stats,
        )
        await run_engine_until(
            engine,
            lambda: (
                all(card.combat_stats is not None for card in engine.current_state.players)
                and bool(engine.current_state.players)
            ),
        )
    assert asked_game_versions == ["16.19.712.1234"]
    assert engine.patch_stats is not None
    assert all(card.combat_stats is not None for card in engine.current_state.players)


async def test_without_the_league_client_the_patch_stats_are_loaded_for_no_version() -> None:
    answers = [game_with_a_dragon_taken_at(400.0, 450.0 + index) for index in range(50)]
    asked_game_versions: list[str | None] = []

    async def load_patch_stats(game_version: str | None) -> PatchStats | None:
        asked_game_versions.append(game_version)
        return fixture_patch_stats()

    async def no_client() -> LeagueClient | None:
        return None

    async with serve(scripted_game(answers)) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            connect_to_client=no_client,
            load_patch_stats=load_patch_stats,
        )
        await run_engine_until(engine, lambda: engine.patch_stats is not None)
    assert asked_game_versions == [None]


async def test_each_new_game_loads_the_patch_data_again() -> None:
    # A game, a pause between games, and a second game: a patch can land in between.
    first_game = [game_with_a_dragon_taken_at(400.0, 450.0 + index) for index in range(5)]
    second_game = [game_with_a_dragon_taken_at(400.0, 450.0 + index) for index in range(50)]
    answers: list[JsonValue] = [*first_game, None, None, None, *second_game]
    asked_game_versions: list[str | None] = []

    async def load_patch_stats(game_version: str | None) -> PatchStats | None:
        asked_game_versions.append(game_version)
        return fixture_patch_stats()

    async with (
        serve(scripted_game(answers)) as game_url,
        serve(league_client_with_game_version("16.20.1.1")) as client_url,
        aiohttp.ClientSession() as session,
    ):

        async def connect_to_client() -> LeagueClient | None:
            return LeagueClient(session, client_url, password="", tls_context=None)

        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            connect_to_client=connect_to_client,
            load_patch_stats=load_patch_stats,
        )
        await run_engine_until(engine, lambda: len(asked_game_versions) >= 2)
    assert asked_game_versions == ["16.20.1.1", "16.20.1.1"]


@contextlib.asynccontextmanager
async def running_overlay_with_patch_stats() -> AsyncIterator[tuple[str, OverlayEngine]]:
    answers = [game_with_a_dragon_taken_at(400.0, 600.0 + index * 0.01) for index in range(3000)]

    async def load_patch_stats(_game_version: str | None) -> PatchStats | None:
        return fixture_patch_stats()

    async with serve(scripted_game(answers)) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            load_patch_stats=load_patch_stats,
        )
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        for _ in range(200):
            if engine.patch_stats is not None and engine.current_state.is_game_running:
                break
            await asyncio.sleep(0.01)
        try:
            async with serve(create_overlay_application(engine)) as overlay_url:
                yield overlay_url, engine
        finally:
            stop_requested.set()
            await engine_task


async def test_a_marked_flash_reaches_the_overlays_state() -> None:
    async with (
        running_overlay_with_patch_stats() as (overlay_url, engine),
        aiohttp.ClientSession() as session,
    ):
        async with session.post(
            overlay_url + "/marks",
            json={"enemy_slot": 3, "spell": "flash"},
            headers={"X-LeagueasyMode-Request": "mark"},
        ) as response:
            assert response.status == 200
            marked = await response.json()
        for _ in range(100):
            if engine.current_state.cooldowns:
                break
            await asyncio.sleep(0.01)
    assert marked["champion_name"] == "Zed"
    assert [timer.label for timer in engine.current_state.cooldowns] == ["F"]


async def test_a_mark_without_the_apps_header_is_refused() -> None:
    async with (
        running_overlay_with_patch_stats() as (overlay_url, engine),
        aiohttp.ClientSession() as session,
        session.post(overlay_url + "/marks", json={"enemy_slot": 3, "spell": "flash"}) as response,
    ):
        assert response.status == 403
    assert engine.current_state.cooldowns == []


async def test_a_mark_that_names_nothing_is_refused() -> None:
    async with (
        running_overlay_with_patch_stats() as (overlay_url, _engine),
        aiohttp.ClientSession() as session,
    ):
        headers = {"X-LeagueasyMode-Request": "mark"}
        for body in ({"enemy_slot": 9, "spell": "flash"}, {"enemy_slot": 3, "spell": "dance"}, {}):
            async with session.post(
                overlay_url + "/marks", json=body, headers=headers
            ) as refused_response:
                assert refused_response.status == 400, body
        async with session.post(
            overlay_url + "/marks", data=b"not json", headers=headers
        ) as garbled_response:
            assert garbled_response.status == 400


async def test_the_last_games_summary_and_the_accuracy_history_are_served(tmp_path: Path) -> None:
    summary_path = tmp_path / "last-game.json"
    history_path = tmp_path / "accuracy-history.jsonl"
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        application = create_overlay_application(
            engine, summary_path=summary_path, history_path=history_path
        )
        async with serve(application) as overlay_url:
            async with session.get(overlay_url + "/summary") as no_game_response:
                no_game_status = no_game_response.status
            summary_path.write_text('{"recording_name": "game.jsonl.xz"}')
            append_game_accuracy(
                history_path,
                GameAccuracy(
                    recording_name="game.jsonl.xz",
                    game_id=None,
                    game_version=None,
                    scored_at="2026-10-09T00:00:00+00:00",
                    scores=(EstimatorScore("roles", 10, 0.9, "share_correct"),),
                ),
            )
            async with session.get(overlay_url + "/summary") as summary_response:
                summary = await summary_response.json()
            async with session.get(overlay_url + "/history") as history_response:
                history = await history_response.json()
    assert no_game_status == 404
    assert summary == {"recording_name": "game.jsonl.xz"}
    assert history["games"][0]["scores"][0]["estimator"] == "roles"
