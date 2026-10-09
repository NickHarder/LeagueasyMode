"""Moving the widgets in Chromium (phase 8.3): drag in edit mode, kept, and reset.

Run with `uv run pytest -m browser`. Set OVERLAY_SCREENSHOT_DIRECTORY to keep a screenshot.
"""

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final

import aiohttp
import pytest
from playwright.async_api import Page, async_playwright, expect

from leagueasymode.engine import OverlayEngine
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.overlay_state import OverlayLayout, WidgetOffset
from leagueasymode.preferences import load_layout
from local_servers import serve, unused_local_url

pytestmark = pytest.mark.browser

VIEWPORT_WIDTH: Final = 1000
VIEWPORT_HEIGHT: Final = 800


@contextlib.asynccontextmanager
async def open_overlay(layout_path: Path) -> AsyncIterator[tuple[Page, OverlayEngine]]:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None),
            poll_interval_seconds=1,
            layout=load_layout(layout_path),
        )
        application = create_overlay_application(engine, layout_path=layout_path)
        async with serve(application) as overlay_url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            )
            page = await browser.new_page(
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
            )
            await page.goto(overlay_url + "/")
            try:
                yield page, engine
            finally:
                await browser.close()


async def keep_screenshot(page: Page, name: str) -> None:
    screenshot_directory = os.environ.get("OVERLAY_SCREENSHOT_DIRECTORY")
    if screenshot_directory:
        await page.screenshot(path=str(Path(screenshot_directory) / f"{name}.png"))


async def drag(page: Page, selector: str, right: float, down: float) -> None:
    bounds = await page.locator(selector).bounding_box()
    assert bounds is not None
    start_x = bounds["x"] + bounds["width"] / 2
    start_y = bounds["y"] + bounds["height"] / 2
    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    await page.mouse.move(start_x + right, start_y + down, steps=5)
    await page.mouse.up()


async def layout_when(engine: OverlayEngine, expected: OverlayLayout) -> OverlayLayout:
    for _ in range(100):
        if engine.layout == expected:
            break
        await asyncio.sleep(0.02)
    return engine.layout


async def test_in_edit_mode_a_widget_is_dragged_and_kept(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.json"
    moved = OverlayLayout(offsets={"you_panel": WidgetOffset(x_share=0.25, y_share=0.1)})
    async with open_overlay(layout_path) as (page, engine):
        notice = page.locator(".layout-editor")
        await expect(notice).to_be_hidden()
        await page.evaluate("window.leagueasymodeSetEditing(true)")
        await expect(notice).to_be_visible()
        # Every movable widget is outlined and can be grabbed, the empty You panel too.
        await expect(page.locator("[data-movable]")).to_have_count(4)
        await expect(page.locator("#you-panel")).to_be_visible()
        await drag(page, "#you-panel", VIEWPORT_WIDTH * 0.25, VIEWPORT_HEIGHT * 0.1)
        assert await layout_when(engine, moved) == moved
        await expect(page.locator("#you-panel")).to_have_css("translate", "250px 80px")
        await keep_screenshot(page, "layout-editing")
    assert load_layout(layout_path) == moved
    async with open_overlay(layout_path) as (reopened_page, _reopened_engine):
        # A new page, as after a restart, puts it back where it was dropped.
        await expect(reopened_page.locator("#you-panel")).to_have_css("translate", "250px 80px")


async def test_out_of_edit_mode_nothing_moves(tmp_path: Path) -> None:
    async with open_overlay(tmp_path / "layout.json") as (page, engine):
        await page.evaluate("window.leagueasymodeSetEditing(true)")
        await page.evaluate("window.leagueasymodeSetEditing(false)")
        await expect(page.locator(".layout-editor")).to_be_hidden()
        await page.evaluate("document.getElementById('callouts').style.minHeight = '40px'")
        await drag(page, "#callouts", 120, 60)
        await asyncio.sleep(0.2)
        assert engine.layout == OverlayLayout()


async def test_reset_puts_every_widget_back(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.json"
    layout_path.write_text(
        OverlayLayout(
            offsets={"enemy_strip": WidgetOffset(x_share=-0.3, y_share=0.2)}
        ).model_dump_json()
    )
    async with open_overlay(layout_path) as (page, engine):
        await page.evaluate("window.leagueasymodeSetEditing(true)")
        await expect(page.locator("#enemy-strip")).to_have_css("translate", "-300px 160px")
        await page.get_by_role("button", name="Reset layout").click()
        assert await layout_when(engine, OverlayLayout()) == OverlayLayout()
        await expect(page.locator("#enemy-strip")).to_have_css("translate", "none")
