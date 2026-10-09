"""The settings page in Chromium (phase 7.1): each switch changes what the overlay shows.

Run with `uv run pytest -m browser`. Set OVERLAY_SCREENSHOT_DIRECTORY to keep a screenshot.
"""

import contextlib
import os
from collections.abc import AsyncIterator
from pathlib import Path

import aiohttp
import pytest
from playwright.async_api import Page, async_playwright, expect

from leagueasymode.engine import OverlayEngine
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.overlay_state import OverlayPreferences
from leagueasymode.preferences import load_preferences
from local_servers import serve, unused_local_url

pytestmark = pytest.mark.browser


@contextlib.asynccontextmanager
async def open_settings(preferences_path: Path) -> AsyncIterator[tuple[Page, OverlayEngine]]:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None),
            poll_interval_seconds=1,
            preferences=load_preferences(preferences_path),
        )
        application = create_overlay_application(engine, preferences_path=preferences_path)
        async with serve(application) as overlay_url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            )
            page = await browser.new_page(viewport={"width": 800, "height": 900})
            await page.goto(overlay_url + "/settings.html")
            try:
                yield page, engine
            finally:
                await browser.close()


async def test_each_switch_starts_as_its_default_and_a_change_is_kept(tmp_path: Path) -> None:
    preferences_path = tmp_path / "preferences.json"
    async with open_settings(preferences_path) as (page, engine):
        switches = page.locator(".settings-row input")
        await expect(switches).to_have_count(9, timeout=5000)
        # Everything shows; only speaking the callouts waits to be turned on.
        for index in range(8):
            await expect(switches.nth(index)).to_be_checked()
        await expect(page.get_by_label("Speak callouts")).not_to_be_checked()
        await page.get_by_label("Win chance").uncheck()
        await expect(page.locator(".settings-status")).to_have_text("Saved")
        assert not engine.preferences.show_win_chance
        await page.get_by_label("Speak callouts").check()
        await expect(page.locator(".settings-status")).to_have_text("Saved")
        assert engine.preferences.speak_callouts
        screenshot_directory = os.environ.get("OVERLAY_SCREENSHOT_DIRECTORY")
        if screenshot_directory:
            await page.screenshot(path=str(Path(screenshot_directory) / "settings.png"))
    assert load_preferences(preferences_path) == OverlayPreferences(
        show_win_chance=False, speak_callouts=True
    )


async def test_the_page_shows_what_was_kept(tmp_path: Path) -> None:
    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text(OverlayPreferences(show_minimap=False).model_dump_json())
    async with open_settings(preferences_path) as (page, _engine):
        await expect(page.get_by_label("Minimap layer")).not_to_be_checked(timeout=5000)
        await expect(page.get_by_label("Callouts", exact=True)).to_be_checked()
