"""The status page in Chromium (phase 8.1): what the engine sees, and the report to copy.

Run with `uv run pytest -m browser`. Set OVERLAY_SCREENSHOT_DIRECTORY to keep a screenshot.
"""

import asyncio
import contextlib
import datetime
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from playwright.async_api import Page, async_playwright, expect
from pydantic import JsonValue

from game_payloads import DEFAULT_PLAYERS, all_game_data, champion_kill_event, game_start_event
from leagueasymode.engine import OverlayEngine
from leagueasymode.engine_status import StatusBoard
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import create_overlay_application
from local_servers import serve

pytestmark = pytest.mark.browser


def fixed_clock() -> datetime.datetime:
    return datetime.datetime(2026, 10, 9, 21, 30, tzinfo=datetime.UTC)


def endless_game(answer: JsonValue) -> web.Application:
    application = web.Application()

    async def all_game_data_route(_request: web.Request) -> web.Response:
        return web.json_response(answer)

    application.router.add_get("/liveclientdata/allgamedata", all_game_data_route)
    return application


@contextlib.asynccontextmanager
async def open_status(answer: JsonValue) -> AsyncIterator[Page]:
    async with serve(endless_game(answer)) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.05,
            status=StatusBoard(clock=fixed_clock),
        )
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        try:
            async with (
                serve(create_overlay_application(engine)) as overlay_url,
                async_playwright() as playwright,
            ):
                browser = await playwright.chromium.launch(
                    executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
                )
                context = await browser.new_context(viewport={"width": 860, "height": 1200})
                await context.grant_permissions(
                    ["clipboard-read", "clipboard-write"], origin=overlay_url
                )
                page = await context.new_page()
                # Opened once the engine has had a few answers, as after a minute of play.
                await asyncio.sleep(0.3)
                await page.goto(overlay_url + "/status.html")
                try:
                    yield page
                finally:
                    await browser.close()
        finally:
            stop_requested.set()
            await engine_task


async def keep_screenshot(page: Page, name: str) -> None:
    screenshot_directory = os.environ.get("OVERLAY_SCREENSHOT_DIRECTORY")
    if screenshot_directory:
        await page.screenshot(path=str(Path(screenshot_directory) / f"{name}.png"), full_page=True)


def a_game_with_a_new_event() -> JsonValue:
    return all_game_data(
        754.0,
        [
            game_start_event(),
            champion_kill_event(1, 400.0, "Shadow Step", "Ahri", []),
            {"EventID": 2, "EventName": "FeatUpdate", "EventTime": 410.0},
        ],
    )


async def test_each_part_shows_its_state_in_words() -> None:
    async with open_status(a_game_with_a_new_event()) as page:
        game_row = page.locator(".status-part[data-key='game']")
        await expect(game_row.locator(".status-badge")).to_have_text("OK", timeout=5000)
        await expect(game_row.locator(".status-detail")).to_have_text(
            "Answering: CLASSIC on map 11, 12:34 in, 10 players"
        )
        # The game, the client, the patch, the lookups, the recording, the timeline, the scoring,
        # League's settings, the models and the tuning.
        await expect(page.locator(".status-part")).to_have_count(10)
        await expect(page.locator(".status-part[data-key='tuning'] .status-detail")).to_have_text(
            "Read when the engine starts"
        )
        await expect(page.locator(".status-events li")).to_have_text(
            [
                "ChampionKill \u00d71",
                "FeatUpdate \u00d71 (no estimator reads it)",
                "GameStart \u00d71 (no estimator reads it)",
            ]
        )
        await expect(page.locator(".status-fields")).to_be_hidden()
        await keep_screenshot(page, "status-page")


async def test_the_report_is_copied_and_names_no_player() -> None:
    async with open_status(a_game_with_a_new_event()) as page:
        await expect(page.locator(".status-part[data-key='game'] .status-badge")).to_have_text(
            "OK", timeout=5000
        )
        await page.get_by_role("button", name="Copy report").click()
        await expect(page.locator(".status-copied")).to_have_text(
            "Copied: paste it into a message."
        )
        copied = await page.evaluate("navigator.clipboard.readText()")
        assert isinstance(copied, str)
        assert copied == await page.locator(".status-report").input_value()
        assert re.search(r"^\[OK\] The game: Answering: CLASSIC on map 11", copied, re.MULTILINE)
        assert (
            "Feed events: ChampionKill \u00d71, FeatUpdate \u00d71 (no estimator reads it)"
            in copied
        )
        assert "reported 21:30:00 UTC" in copied
        page_text = await page.locator("body").inner_text()
        for seed in DEFAULT_PLAYERS:
            for shown_text in (copied, page_text):
                assert seed.riot_id not in shown_text
                assert (
                    seed.riot_id_game_name == seed.champion_name
                    or seed.riot_id_game_name not in shown_text
                )


async def test_an_answer_that_cannot_be_read_lists_its_fields() -> None:
    unreadable = all_game_data(60.0)
    assert isinstance(unreadable, dict)
    unreadable.pop("allPlayers")
    async with open_status(unreadable) as page:
        await expect(page.locator(".status-part[data-key='game'] .status-badge")).to_have_text(
            "Problem", timeout=5000
        )
        await expect(page.locator(".status-fields li")).to_have_text(["allPlayers: missing"])
        await expect(page.locator(".status-report")).to_have_value(
            re.compile(r"Fields not read: allPlayers: missing$")
        )
