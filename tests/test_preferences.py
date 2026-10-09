import asyncio
from pathlib import Path

import aiohttp
from aiohttp import web
from pydantic import JsonValue

from game_payloads import all_game_data
from leagueasymode.engine import OverlayEngine
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import PREFERENCES_REQUEST_VALUE, create_overlay_application
from leagueasymode.overlay_state import OverlayPreferences
from leagueasymode.preferences import load_preferences, save_preferences
from local_servers import serve, unused_local_url


def scripted_game(answers: list[JsonValue]) -> web.Application:
    application = web.Application()

    async def answer(_request: web.Request) -> web.Response:
        if answers:
            return web.json_response(answers.pop(0))
        return web.json_response({"errorCode": "RESOURCE_NOT_FOUND"}, status=404)

    application.router.add_get("/liveclientdata/allgamedata", answer)
    return application


def test_without_a_file_everything_shows(tmp_path: Path) -> None:
    preferences = load_preferences(tmp_path / "preferences.json")
    assert preferences == OverlayPreferences()
    assert preferences.show_win_chance


def test_callouts_are_spoken_only_once_the_player_turns_it_on() -> None:
    assert not OverlayPreferences().speak_callouts


def test_preferences_are_kept_and_read_back(tmp_path: Path) -> None:
    preferences_path = tmp_path / "app" / "preferences.json"
    chosen = OverlayPreferences(show_win_chance=False, show_suggestions=False)
    save_preferences(preferences_path, chosen)
    assert load_preferences(preferences_path) == chosen


def test_a_file_that_cannot_be_read_leaves_everything_showing(tmp_path: Path) -> None:
    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text('{"show_win_chance": "maybe"}')
    assert load_preferences(preferences_path) == OverlayPreferences()


def test_a_preference_added_later_takes_its_default(tmp_path: Path) -> None:
    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text('{"show_win_chance": false}')
    preferences = load_preferences(preferences_path)
    assert not preferences.show_win_chance
    assert preferences.show_minimap


async def put_preferences(
    session: aiohttp.ClientSession, overlay_url: str, body: JsonValue, *, with_header: bool
) -> int:
    headers = {"X-LeagueasyMode-Request": PREFERENCES_REQUEST_VALUE} if with_header else {}
    async with session.put(overlay_url + "/preferences", json=body, headers=headers) as response:
        return response.status


async def test_the_settings_page_changes_what_the_overlay_shows(tmp_path: Path) -> None:
    preferences_path = tmp_path / "preferences.json"
    answers: list[JsonValue] = [all_game_data(600.0 + index) for index in range(200)]
    async with serve(scripted_game(answers)) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            preferences=load_preferences(preferences_path),
        )
        updates = engine.subscribe()
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        application = create_overlay_application(engine, preferences_path=preferences_path)
        async with serve(application) as overlay_url:
            first_state = await asyncio.wait_for(updates.get(), timeout=5)
            refused = await put_preferences(
                session, overlay_url, {"show_win_chance": False}, with_header=False
            )
            not_preferences = await put_preferences(
                session, overlay_url, {"show_everything": False}, with_header=True
            )
            accepted = await put_preferences(
                session,
                overlay_url,
                OverlayPreferences(show_win_chance=False).model_dump(),
                with_header=True,
            )
            changed_state = await asyncio.wait_for(updates.get(), timeout=5)
            while changed_state.preferences.show_win_chance:
                changed_state = await asyncio.wait_for(updates.get(), timeout=5)
            async with session.get(overlay_url + "/preferences") as response:
                served = OverlayPreferences.model_validate(await response.json())
        stop_requested.set()
        await engine_task
    assert first_state.preferences.show_win_chance
    assert (refused, not_preferences, accepted) == (403, 400, 200)
    assert not changed_state.preferences.show_win_chance
    assert not served.show_win_chance
    assert load_preferences(preferences_path) == OverlayPreferences(show_win_chance=False)


async def test_without_a_game_a_change_still_reaches_the_page(tmp_path: Path) -> None:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        updates = engine.subscribe()
        engine.set_preferences(OverlayPreferences(show_minimap=False))
        published = await asyncio.wait_for(updates.get(), timeout=1)
    assert not published.is_game_running
    assert not published.preferences.show_minimap
