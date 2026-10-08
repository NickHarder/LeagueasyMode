"""The overlay page in Chromium, fed by a replayed game: what the player would see.

Run with `uv run pytest -m browser`. Chromium comes from Playwright's own install
(`uv run playwright install chromium`), or from PLAYWRIGHT_CHROMIUM_EXECUTABLE.
Set OVERLAY_SCREENSHOT_DIRECTORY to keep a screenshot of each state.
"""

import asyncio
import datetime
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final

import pytest
from playwright.async_api import Page, async_playwright, expect
from pydantic import JsonValue

from game_payloads import DEFAULT_PLAYERS, all_game_data, dragon_kill_event, game_start_event
from leagueasymode.cli import run_overlay
from leagueasymode.config import Settings
from leagueasymode.recording.writer import RecordingWriter
from leagueasymode.replay import RecordingReplay, create_replay_application
from local_servers import serve

pytestmark = pytest.mark.browser

ENEMY_JUNGLER: Final = DEFAULT_PLAYERS[6].riot_id_game_name
EN_DASH: Final = "\u2013"


def write_recording(directory: Path, snapshot_count: int) -> Path:
    writer = RecordingWriter(directory / "game.jsonl", keyframe_interval_seconds=60.0)
    writer.write_started(
        started_at=datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC),
        recorder_version="test",
        poll_interval_seconds=0.5,
    )
    for index in range(snapshot_count):
        game_time_seconds = 1395.0 + index * 0.5
        events: list[dict[str, JsonValue]] = [
            game_start_event(),
            dragon_kill_event(1, 400.0, ENEMY_JUNGLER, "Fire"),
            dragon_kill_event(2, 800.0, DEFAULT_PLAYERS[1].riot_id_game_name, "Water"),
            dragon_kill_event(3, 1390.0, ENEMY_JUNGLER, "Fire"),
        ]
        writer.write_snapshot(
            received_at_seconds=index * 0.5,
            payload=all_game_data(game_time_seconds, events, map_terrain="Infernal"),
        )
    writer.write_ended(received_at_seconds=snapshot_count * 0.5, reason="game ended")
    return writer.close()


async def open_overlay(tmp_path: Path, snapshot_count: int, speed: float) -> AsyncIterator[Page]:
    replay = RecordingReplay(write_recording(tmp_path, snapshot_count), speed=speed)
    overlay_urls: list[str] = []
    overlay_is_up = asyncio.Event()

    def note_overlay_url(overlay_url: str) -> None:
        overlay_urls.append(overlay_url)
        overlay_is_up.set()

    async with serve(create_replay_application(replay)) as game_url:
        settings = Settings(
            game_api_base_url=game_url, poll_interval_seconds=0.1, record_while_running=False
        )
        stop_requested = asyncio.Event()
        overlay_task = asyncio.create_task(run_overlay(settings, stop_requested, note_overlay_url))
        await overlay_is_up.wait()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            )
            page = await browser.new_page(viewport={"width": 1280, "height": 200})
            await page.goto(overlay_urls[0])
            try:
                yield page
            finally:
                await browser.close()
                stop_requested.set()
                await overlay_task


async def keep_screenshot(page: Page, name: str) -> None:
    screenshot_directory = os.environ.get("OVERLAY_SCREENSHOT_DIRECTORY")
    if screenshot_directory:
        await page.screenshot(
            path=str(Path(screenshot_directory) / f"{name}.png"), omit_background=True
        )


async def test_the_dragon_widget_counts_down_to_the_next_dragon(tmp_path: Path) -> None:
    async for page in open_overlay(tmp_path, snapshot_count=60, speed=1.0):
        widget = page.locator("#dragon-widget")
        await expect(widget).to_be_visible(timeout=5000)
        await expect(page.locator("#dragon-label")).to_have_text("Dragon")
        # Taken at 23:10, so the next one spawns at 28:10, about five minutes after 23:15.
        await expect(page.locator("#dragon-time")).to_have_text(re.compile(r"^4:5\d$|^5:00$"))
        await expect(page.locator("#dragon-detail")).to_have_text(f"1{EN_DASH}2 · Infernal rift")
        background = await page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert background == "rgba(0, 0, 0, 0)"
        await keep_screenshot(page, "dragon-countdown")


async def test_the_widget_hides_when_the_game_is_over(tmp_path: Path) -> None:
    # 20 seconds of game at 8x: shown first, then gone about 3 seconds in.
    async for page in open_overlay(tmp_path, snapshot_count=40, speed=8.0):
        await expect(page.locator("#dragon-widget")).to_be_visible(timeout=2000)
        await expect(page.locator("#dragon-widget")).to_be_hidden(timeout=10000)
