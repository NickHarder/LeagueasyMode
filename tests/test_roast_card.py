"""The overlay's roast card after a game, in Chromium: three lines for chat, a click copies one.

Run with `uv run pytest -m browser`. Set OVERLAY_SCREENSHOT_DIRECTORY to keep a screenshot.
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Final

import aiohttp
import pytest
from aiohttp import web
from playwright.async_api import async_playwright, expect

from client_game_payloads import end_of_game_payload
from game_payloads import all_game_data
from leagueasymode.engine import OverlayEngine
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.roast.end_of_game import quick_game_roast
from leagueasymode.roast.last_game import roast_path_beside
from local_servers import serve

pytestmark = pytest.mark.browser

# Stands in for the macOS app: the line the card hands it to copy is kept to be read back.
APP_COPY_STAND_IN: Final = """
window.copiedLines = [];
window.webkit = {messageHandlers: {leagueasymodeCopy: {
    postMessage: (text) => window.copiedLines.push(text),
}}};
"""
AN_HOUR_SECONDS: Final = 3600


def game_until(game_over: asyncio.Event) -> web.Application:
    """A game that runs at 10:00 until the test ends it, then answers as the client does after."""
    application = web.Application()

    async def answer(_request: web.Request) -> web.Response:
        if game_over.is_set():
            return web.json_response({"errorCode": "RESOURCE_NOT_FOUND"}, status=404)
        return web.json_response(all_game_data(600.0))

    application.router.add_get("/liveclientdata/allgamedata", answer)
    return application


def keep_quick_case(summary_path: Path, *, kept_hours_ago: float = 0) -> None:
    quick = quick_game_roast(end_of_game_payload())
    assert quick is not None
    roast_path = roast_path_beside(summary_path)
    roast_path.write_text(quick.model_dump_json())
    kept_at = time.time() - kept_hours_ago * AN_HOUR_SECONDS
    os.utime(roast_path, (kept_at, kept_at))


async def test_after_a_game_the_card_offers_three_lines_and_copies_one(tmp_path: Path) -> None:
    summary_path = tmp_path / "last-game.json"
    # An older game's case is on file: the card never shows it.
    keep_quick_case(summary_path, kept_hours_ago=1)
    game_over = asyncio.Event()
    async with serve(game_until(game_over)) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None), poll_interval_seconds=0.1
        )
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        application = create_overlay_application(engine, summary_path=summary_path)
        try:
            async with serve(application) as overlay_url, async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
                )
                page = await browser.new_page(viewport={"width": 1280, "height": 720})
                await page.add_init_script(APP_COPY_STAND_IN)
                await page.goto(overlay_url + "/")
                card = page.locator("#roast-card")
                await expect(page.locator("#dragon-widget")).to_be_visible(timeout=5000)
                game_over.set()
                await page.wait_for_timeout(1500)
                await expect(card).to_be_hidden()
                # This game's quick case is kept a moment after it ends.
                keep_quick_case(summary_path)
                lines = card.locator(".roast-card-line")
                await expect(lines).to_have_count(3, timeout=10000)
                salty = await lines.all_text_contents()
                assert all(line.startswith("gg") for line in salty)
                await expect(card.locator(".roast-card-level[aria-pressed=true]")).to_have_text("2")
                screenshot_directory = os.environ.get("OVERLAY_SCREENSHOT_DIRECTORY")
                if screenshot_directory:
                    await page.screenshot(path=str(Path(screenshot_directory) / "roast-card.png"))
                await lines.nth(1).click()
                assert await page.evaluate("window.copiedLines") == [salty[1]]
                await expect(lines.nth(1)).to_have_attribute("data-copied", "true")
                # Another spice, other lines.
                await card.get_by_role("button", name="4 Chat-Restricted Speedrun").click()
                await expect(lines.first).not_to_have_text(salty[0], timeout=5000)
                await card.get_by_role("button", name="Close").click()
                await expect(card).to_be_hidden()
                await browser.close()
        finally:
            stop_requested.set()
            await engine_task
