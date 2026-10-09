"""The post-game window in Chromium, fed by a built game's summary and history (phase 6.4).

Run with `uv run pytest -m browser`. Set OVERLAY_SCREENSHOT_DIRECTORY to keep a screenshot.
"""

import contextlib
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final

import aiohttp
import pytest
from playwright.async_api import Page, async_playwright, expect

from data_dragon_fixtures import fixture_patch_stats
from game_payloads import DEFAULT_PLAYERS, champion_kill_event, turret_killed_event
from leagueasymode.accuracy_history import (
    append_game_accuracy,
    game_accuracy_of,
    read_accuracy_history,
)
from leagueasymode.engine import OverlayEngine
from leagueasymode.game_api import GameApiClient
from leagueasymode.game_summary import game_summary
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.scoring import read_recorded_game, score_game
from local_servers import serve, unused_local_url
from recorded_games import game_timeline, write_scored_recording

pytestmark = pytest.mark.browser

SCORED_AT: Final = "2026-10-09T00:00:00+00:00"
FEED: Final = [
    champion_kill_event(1, 400.0, "Shadow Step", "Ahri", []),
    turret_killed_event(2, 610.0, "Turret_T2_L_03_A", "Garen Main"),
]


def write_summary_and_history(tmp_path: Path) -> tuple[Path, Path]:
    summary_path = tmp_path / "last-game.json"
    history_path = tmp_path / "accuracy-history.jsonl"
    for index in range(3):
        directory = tmp_path / f"game-{index}"
        directory.mkdir()
        recording = write_scored_recording(
            directory,
            DEFAULT_PLAYERS,
            timeline=game_timeline(gold_off_by=100 * index),
            winning_team_id=100,
            feed_events=FEED,
        )
        game = read_recorded_game(recording)
        scores = score_game(game, fixture_patch_stats())
        append_game_accuracy(
            history_path,
            game_accuracy_of(directory / f"game-{index}.jsonl.xz", game, scores, SCORED_AT),
        )
        summary_path.write_text(game_summary(recording.name, game, scores).model_dump_json())
    return summary_path, history_path


@contextlib.asynccontextmanager
async def open_summary(summary_path: Path, history_path: Path) -> AsyncIterator[Page]:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        application = create_overlay_application(
            engine, summary_path=summary_path, history_path=history_path
        )
        async with serve(application) as overlay_url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            )
            page = await browser.new_page(viewport={"width": 900, "height": 1400})
            await page.goto(overlay_url + "/summary.html")
            try:
                yield page
            finally:
                await browser.close()


async def keep_screenshot(page: Page, name: str) -> None:
    screenshot_directory = os.environ.get("OVERLAY_SCREENSHOT_DIRECTORY")
    if screenshot_directory:
        await page.screenshot(path=str(Path(screenshot_directory) / f"{name}.png"), full_page=True)


async def test_the_window_shows_the_last_game_reconstructed(tmp_path: Path) -> None:
    summary_path, history_path = write_summary_and_history(tmp_path)
    async with open_summary(summary_path, history_path) as page:
        await expect(page.locator(".summary-result")).to_have_text("Victory", timeout=5000)
        await expect(page.locator(".summary-detail")).to_have_text("Ahri · 15:00")
        # The win chance and the gold lead, each a line; the gold lead has two, with a legend.
        await expect(page.locator(".chart").first.locator(".chart-line")).to_have_count(1)
        await expect(page.locator(".chart").nth(1).locator(".chart-line")).to_have_count(2)
        await expect(page.locator(".chart-legend-item")).to_have_text(
            ["Estimated", "Timeline", "your team's", "their team's"]
        )
        await expect(page.locator(".summary-swings li")).to_have_count(3)
        await expect(page.locator(".summary-moments li")).to_have_text(
            [
                re.compile(r"^6:40\s*Zed killed Ahri$"),
                re.compile(r"^10:10\s*your team took their top outer turret$"),
            ]
        )
        await keep_screenshot(page, "post-game-window")


async def test_the_crosshair_reads_out_a_minute(tmp_path: Path) -> None:
    summary_path, history_path = write_summary_and_history(tmp_path)
    async with open_summary(summary_path, history_path) as page:
        plot = page.locator(".chart-plot").first
        await expect(plot).to_be_visible(timeout=5000)
        bounds = await plot.bounding_box()
        assert bounds is not None
        await page.mouse.move(bounds["x"] + bounds["width"] * 0.5, bounds["y"] + 40)
        tooltip = page.locator(".chart-tooltip").first
        await expect(tooltip).to_be_visible()
        await expect(tooltip).to_contain_text(re.compile(r"\d+:00\s*\d+%\s*Win chance"))


async def test_each_estimator_shows_this_game_and_the_last_games(tmp_path: Path) -> None:
    summary_path, history_path = write_summary_and_history(tmp_path)
    async with open_summary(summary_path, history_path) as page:
        gold_scores = [
            score
            for game in read_accuracy_history(history_path)
            for score in game.scores
            if score.estimator == "gold earned"
        ]
        # Every game's estimator is scored on as many player-minutes: the plain average.
        average = sum(score.value for score in gold_scores) / len(gold_scores)
        gold_row = page.locator(".summary-accuracy tr", has_text="gold earned")
        await expect(gold_row).to_contain_text(
            f"{gold_scores[-1].value:.0f} gold off", timeout=5000
        )
        await expect(gold_row).to_contain_text(f"{average:.0f} gold off (3)")
        await expect(gold_row.locator(".sparkline-line")).to_have_count(1)


async def test_before_any_game_the_window_says_so(tmp_path: Path) -> None:
    async with open_summary(tmp_path / "none.json", tmp_path / "none.jsonl") as page:
        await expect(page.locator(".summary-result")).to_have_text("No game yet", timeout=5000)
