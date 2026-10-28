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
from leagueasymode.friends import FriendsList, load_friends, save_friends
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.overlay_state import OverlayPreferences
from leagueasymode.preferences import load_preferences
from leagueasymode.roast.claude_take import ClaudeTakeSettings, load_claude_take_settings
from local_servers import serve, unused_local_url

pytestmark = pytest.mark.browser


@contextlib.asynccontextmanager
async def open_settings(
    preferences_path: Path, friends_path: Path | None = None, claude_take_path: Path | None = None
) -> AsyncIterator[tuple[Page, OverlayEngine]]:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None),
            poll_interval_seconds=1,
            preferences=load_preferences(preferences_path),
            friends=load_friends(friends_path) if friends_path is not None else None,
        )
        application = create_overlay_application(
            engine,
            preferences_path=preferences_path,
            friends_path=friends_path,
            claude_take_path=claude_take_path,
        )
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
        # Twelve switches: "Click to mark spells", beside the app's shortcuts, "Moments about
        # friends" (phase 11.6) and "Team calls" (11.9), on by default like the others.
        await expect(switches).to_have_count(12, timeout=5000)
        # Everything shows; speaking the callouts and clicking to mark wait to be turned on.
        for index in range(10):
            await expect(switches.nth(index)).to_be_checked()
        await expect(page.get_by_label("Speak callouts")).not_to_be_checked()
        await expect(page.get_by_label("Click to mark spells")).not_to_be_checked()
        await page.get_by_label("Win chance").uncheck()
        await expect(page.locator(".settings-status")).to_have_text("Saved")
        assert not engine.preferences.show_win_chance
        await page.get_by_label("Speak callouts").check()
        await expect(page.locator(".settings-status")).to_have_text("Saved")
        assert engine.preferences.speak_callouts
        await page.get_by_label("Click to mark spells").check()
        await expect(page.locator(".settings-status")).to_have_text("Saved")
        assert engine.preferences.click_to_mark
        screenshot_directory = os.environ.get("OVERLAY_SCREENSHOT_DIRECTORY")
        if screenshot_directory:
            await page.screenshot(path=str(Path(screenshot_directory) / "settings.png"))
    assert load_preferences(preferences_path) == OverlayPreferences(
        show_win_chance=False, speak_callouts=True, click_to_mark=True
    )


async def test_the_page_shows_what_was_kept(tmp_path: Path) -> None:
    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text(OverlayPreferences(show_minimap=False).model_dump_json())
    async with open_settings(preferences_path) as (page, _engine):
        await expect(page.get_by_label("Minimap layer")).not_to_be_checked(timeout=5000)
        await expect(page.get_by_label("Callouts", exact=True)).to_be_checked()


async def test_the_friends_list_is_saved_and_a_wrong_line_is_explained(tmp_path: Path) -> None:
    friends_path = tmp_path / "friends.json"
    save_friends(friends_path, FriendsList(riot_ids=("Zed Main#NA1",)))
    async with open_settings(tmp_path / "preferences.json", friends_path) as (page, engine):
        box = page.get_by_role("textbox", name="Friends")
        await expect(box).to_have_value("Zed Main#NA1", timeout=5000)
        await box.fill("Zed Main#NA1\n\n  Lux Enjoyer#EUW  \nnot a riot id")
        await page.get_by_role("button", name="Save friends").click()
        status = page.locator(".settings-friends-status")
        await expect(status).to_contain_text("Not saved: not a Riot ID")
        await expect(status).to_contain_text("'not a riot id'")
        assert engine.friends == FriendsList(riot_ids=("Zed Main#NA1",))
        await box.fill("Zed Main#NA1\n\n  Lux Enjoyer#EUW  ")
        await page.get_by_role("button", name="Save friends").click()
        await expect(status).to_have_text("Saved: 2 friends")
        await expect(box).to_have_value("Zed Main#NA1\nLux Enjoyer#EUW")
    assert load_friends(friends_path) == FriendsList(riot_ids=("Zed Main#NA1", "Lux Enjoyer#EUW"))


async def test_claudes_take_is_turned_on_with_a_style(tmp_path: Path) -> None:
    claude_take_path = tmp_path / "claude-take.json"
    async with open_settings(tmp_path / "preferences.json", claude_take_path=claude_take_path) as (
        page,
        engine,
    ):
        section = page.locator(".settings-claude")
        status = section.locator(".settings-claude-status")
        # The engine here has no claude command, and says so.
        await expect(status).to_contain_text("was not found", timeout=5000)
        await section.get_by_label("Reword with Claude").check()
        await section.get_by_label("Style").fill("pirate")
        await section.get_by_role("button", name="Save Claude's take").click()
        await expect(status).to_contain_text("Saved.")
        assert engine.claude_take.settings == ClaudeTakeSettings(enabled=True, style="pirate")
    assert load_claude_take_settings(claude_take_path) == ClaudeTakeSettings(
        enabled=True, style="pirate"
    )
