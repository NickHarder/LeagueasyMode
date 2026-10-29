"""The post-game window in Chromium, fed by a built game's summary and history (phase 6.4).

Run with `uv run pytest -m browser`. Set OVERLAY_SCREENSHOT_DIRECTORY to keep a screenshot.
"""

import contextlib
import os
import re
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final

import aiohttp
import pytest
from playwright.async_api import Page, async_playwright, expect

from client_game_payloads import (
    details_payload,
    end_of_game_payload,
    summary_payload,
    timeline_payload,
)
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
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH
from leagueasymode.roast.claude_take import ClaudeTake, ClaudeTakeSettings
from leagueasymode.roast.end_of_game import quick_game_roast
from leagueasymode.roast.last_game import last_game_roast, roast_path_beside
from leagueasymode.roast.rules import LaneRules
from leagueasymode.scoring import read_recorded_game, score_game
from local_servers import serve, unused_local_url
from recorded_games import game_timeline, players_at, write_scored_recording

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
async def open_summary(
    summary_path: Path, history_path: Path, claude_take: ClaudeTake | None = None
) -> AsyncIterator[Page]:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None),
            poll_interval_seconds=1,
            claude_take=claude_take,
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


def write_last_game_roast(tmp_path: Path, summary_path: Path) -> None:
    """Keep a case beside the summary, from a game whose details have the whole scoreboard."""
    directory = tmp_path / "roasted"
    directory.mkdir()
    recording = write_scored_recording(
        directory,
        players_at(are_positions_given=True),
        timeline=timeline_payload(),
        details=details_payload(),
        client_answers={CHAMPION_SUMMARY_PATH: summary_payload()},
    )
    game = read_recorded_game(recording)
    roast = last_game_roast(
        game.client_resources, game.minute_snapshots[-1], lane_rules=LaneRules()
    )
    assert roast is not None
    roast_path_beside(summary_path).write_text(roast.model_dump_json())


async def test_the_case_file_shows_under_the_result(tmp_path: Path) -> None:
    summary_path, history_path = write_summary_and_history(tmp_path)
    write_last_game_roast(tmp_path, summary_path)
    async with open_summary(summary_path, history_path) as page:
        case_file = page.locator(".case-file")
        await expect(case_file.locator(".case-stamp")).not_to_be_empty(timeout=5000)
        await expect(case_file.locator(".case-board tr[data-outcome]")).to_have_count(5)
        await expect(case_file.locator(".case-board tr", has_text="Mid")).to_contain_text(
            re.compile(r"Ahri\s*LeBlanc\s*-1,400[A-Z]+\s*-14\s*lost")
        )
        assert await case_file.locator(".case-lines li").count() > 0
        await expect(case_file.locator(".case-closing-line")).not_to_be_empty()
        await expect(case_file.locator(".case-closing-caption")).to_contain_text("/ 140 characters")
        await expect(case_file.locator(".case-chip[aria-pressed=true]")).to_have_text(
            ["Our team", "2 Salty"]
        )
        await expect(case_file.locator(".case-chip-row[aria-label=Ours] .case-chip")).to_have_text(
            ["Jax", "Lee Sin", "Ahri (you)", "Jinx", "Lulu"]
        )
        await expect(case_file.locator(".case-risk")).to_have_count(0)
        await keep_screenshot(page, "post-game-case-file")


async def test_any_of_the_ten_can_be_put_on_trial(tmp_path: Path) -> None:
    summary_path, history_path = write_summary_and_history(tmp_path)
    write_last_game_roast(tmp_path, summary_path)
    async with open_summary(summary_path, history_path) as page:
        case_file = page.locator(".case-file")
        leblanc = case_file.locator(".case-chip", has_text="LeBlanc")
        await leblanc.click(timeout=5000)
        await expect(leblanc).to_have_attribute("aria-pressed", "true")
        await expect(case_file.locator(".case-lines")).to_contain_text("LeBlanc")
        await case_file.locator(".case-chip", has_text="Tilted").click()
        await expect(case_file.locator(".case-risk")).to_contain_text("Instant Feedback System")
        await expect(case_file.locator(".case-chip[aria-pressed=true]")).to_have_text(
            ["LeBlanc", "3 Tilted"]
        )
        # A letter opens the exhibits at the one it cites.
        letter = case_file.locator(".case-letter").first
        letter_text = await letter.text_content()
        await letter.click()
        await expect(page.locator(f"#case-exhibit-{letter_text}")).to_be_visible()


async def test_a_game_without_a_case_says_so(tmp_path: Path) -> None:
    summary_path, history_path = write_summary_and_history(tmp_path)
    async with open_summary(summary_path, history_path) as page:
        await expect(page.locator(".case-file .case-empty")).to_contain_text(
            "No case for this game", timeout=5000
        )


async def test_claudes_take_shows_under_the_closing_line(tmp_path: Path) -> None:
    summary_path, history_path = write_summary_and_history(tmp_path)
    write_last_game_roast(tmp_path, summary_path)
    # A stand-in `claude` that answers with the line it was sent, slots and all, after "Yarr! ".
    command = tmp_path / "claude"
    command.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "line = sys.stdin.read().split('Line:', 1)[1].strip()\n"
        "sys.stdout.write('Yarr! ' + line)\n"
    )
    command.chmod(0o755)
    take = ClaudeTake(ClaudeTakeSettings(enabled=True, style="pirate"), command)
    async with open_summary(summary_path, history_path, take) as page:
        claude_take = page.locator(".case-claude-take")
        await expect(claude_take.locator(".case-closing-line")).to_have_text(
            re.compile(r"^Yarr! gg\."), timeout=8000
        )
        await expect(claude_take).to_contain_text("not one of your approved lines")
        closing = await page.locator(".case-closing > .case-closing-line").text_content()
        await expect(claude_take.locator(".case-closing-line")).to_have_text(f"Yarr! {closing}")
        await keep_screenshot(page, "post-game-claudes-take")


async def test_a_quick_case_says_so_until_the_full_one_comes(tmp_path: Path) -> None:
    summary_path, history_path = write_summary_and_history(tmp_path)
    quick = quick_game_roast(end_of_game_payload())
    assert quick is not None
    roast_path_beside(summary_path).write_text(quick.model_dump_json())
    async with open_summary(summary_path, history_path) as page:
        case_file = page.locator(".case-file")
        await expect(case_file.locator(".case-quick")).to_contain_text(
            "quick case from the end-of-game scoreboard", timeout=5000
        )
        await expect(case_file.locator(".case-stamp")).to_have_text("NO LANE VERDICT")
        await expect(case_file.locator(".case-board")).to_have_count(0)
        assert await case_file.locator(".case-lines li").count() > 0


async def test_the_closing_line_has_a_copy_button(tmp_path: Path) -> None:
    summary_path, history_path = write_summary_and_history(tmp_path)
    write_last_game_roast(tmp_path, summary_path)
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
            context = await browser.new_context(permissions=["clipboard-read", "clipboard-write"])
            page = await context.new_page()
            await page.goto(overlay_url + "/summary.html")
            try:
                closing = page.locator(".case-closing > .case-closing-line")
                await expect(closing).not_to_be_empty(timeout=5000)
                copy = page.locator(".case-closing .case-copy")
                await copy.click()
                await expect(copy).to_have_text("Copied")
                copied = await page.evaluate("navigator.clipboard.readText()")
                assert copied == await closing.text_content()
            finally:
                await browser.close()
