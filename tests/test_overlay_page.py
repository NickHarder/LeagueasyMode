"""The overlay page in Chromium, fed by a replayed game: what the player would see.

Run with `uv run pytest -m browser`. Chromium comes from Playwright's own install
(`uv run playwright install chromium`), or from PLAYWRIGHT_CHROMIUM_EXECUTABLE.
Set OVERLAY_SCREENSHOT_DIRECTORY to keep a screenshot of each state.
"""

import asyncio
import contextlib
import dataclasses
import datetime
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final

import pytest
from playwright.async_api import Page, async_playwright, expect
from pydantic import JsonValue, TypeAdapter

from data_dragon_fixtures import FIXTURE_VERSIONS, fake_data_dragon
from game_payloads import (
    CHAMPION_IDS,
    DEFAULT_PLAYERS,
    PastGame,
    PlayerSeed,
    all_game_data,
    baron_kill_event,
    champion_summary,
    dragon_kill_event,
    game_start_event,
    gameflow_session,
    inhibitor_killed_event,
    match_history,
    puuid_of,
    ranked_stats,
)
from leagueasymode.cli import run_overlay
from leagueasymode.config import Settings
from leagueasymode.league_client import GAMEFLOW_SESSION_PATH
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH, GAME_VERSION_PATH, ITEMS_PATH
from leagueasymode.player_intel import MATCH_HISTORY_PATH_TEMPLATE, RANKED_STATS_PATH_TEMPLATE
from leagueasymode.recording.writer import RecordingWriter
from leagueasymode.replay import RecordingReplay, create_replay_application
from local_servers import serve

pytestmark = pytest.mark.browser

ENEMY_JUNGLER: Final = DEFAULT_PLAYERS[6].riot_id_game_name
EN_DASH: Final = "\u2013"
MINUS_SIGN: Final = "\u2212"
ITEMS_FIXTURE: Final = Path(__file__).parent / "fixtures" / "client" / "items.json"
ITEMS_BY_CHAMPION: Final = {
    "Caitlyn": ((3031, "Infinity Edge", 1150),),
    "Jinx": ((1036, "Long Sword", 350), (1036, "Long Sword", 350)),
}


def scoreboard_at(
    game_time_seconds: float,
    respawn_at_by_champion: dict[str, float],
    zed_reaches_six_at_seconds: float | None = None,
    zed_buys_at_seconds: float | None = None,
    vi_farms_at_seconds: tuple[float, ...] = (),
    vi_wards_at_seconds: float | None = None,
) -> tuple[PlayerSeed, ...]:
    def level_of(seed: PlayerSeed) -> int:
        if seed.champion_name != "Zed" or zed_reaches_six_at_seconds is None:
            return 9
        return 6 if game_time_seconds >= zed_reaches_six_at_seconds else 5

    def creep_score_of(seed: PlayerSeed) -> int:
        if seed.champion_name != "Vi":
            return 0
        return 4 * sum(1 for farmed_at in vi_farms_at_seconds if game_time_seconds >= farmed_at)

    def items_of(seed: PlayerSeed) -> tuple[tuple[int, str, int], ...]:
        has_bought = (
            seed.champion_name == "Zed"
            and zed_buys_at_seconds is not None
            and game_time_seconds >= zed_buys_at_seconds
        )
        if seed.champion_name == "Vi" and vi_wards_at_seconds is not None:
            holds_ward = game_time_seconds < vi_wards_at_seconds
            return ((2055, "Control Ward", 75),) if holds_ward else ()
        return (
            ((1036, "Long Sword", 350),)
            if has_bought
            else ITEMS_BY_CHAMPION.get(seed.champion_name, ())
        )

    return tuple(
        dataclasses.replace(
            seed,
            items=items_of(seed),
            level=level_of(seed),
            creep_score=creep_score_of(seed),
            is_dead=True,
            respawn_timer_seconds=respawn_at_by_champion[seed.champion_name] - game_time_seconds,
        )
        if respawn_at_by_champion.get(seed.champion_name, 0.0) > game_time_seconds
        else dataclasses.replace(
            seed, level=level_of(seed), items=items_of(seed), creep_score=creep_score_of(seed)
        )
        for seed in DEFAULT_PLAYERS
    )


def write_recording(
    directory: Path,
    snapshot_count: int,
    respawn_at_by_champion: dict[str, float] | None = None,
    zed_reaches_six_at_seconds: float | None = None,
    is_baron_taken: bool = True,
    zed_buys_at_seconds: float | None = None,
    vi_farms_at_seconds: tuple[float, ...] = (),
    vi_wards_at_seconds: float | None = None,
) -> Path:
    writer = RecordingWriter(directory / "game.jsonl", keyframe_interval_seconds=60.0)
    writer.write_started(
        started_at=datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC),
        recorder_version="test",
        poll_interval_seconds=0.5,
    )
    writer.write_client_resource(
        received_at_seconds=0.0,
        path=ITEMS_PATH,
        payload=TypeAdapter[JsonValue](JsonValue).validate_json(ITEMS_FIXTURE.read_bytes()),
    )
    writer.write_client_resource(
        received_at_seconds=0.0, path=GAME_VERSION_PATH, payload="16.19.712.1234"
    )
    for client_path, client_payload in looked_up_players():
        writer.write_client_resource(
            received_at_seconds=0.0, path=client_path, payload=client_payload
        )
    for index in range(snapshot_count):
        game_time_seconds = 1395.0 + index * 0.5
        events: list[dict[str, JsonValue]] = [
            game_start_event(),
            dragon_kill_event(1, 400.0, ENEMY_JUNGLER, "Fire"),
            dragon_kill_event(2, 800.0, DEFAULT_PLAYERS[1].riot_id_game_name, "Water"),
            dragon_kill_event(3, 1390.0, ENEMY_JUNGLER, "Fire"),
            inhibitor_killed_event(
                5, 1385.0, "Barracks_T2_L1", DEFAULT_PLAYERS[0].riot_id_game_name
            ),
        ]
        if is_baron_taken:
            events.append(baron_kill_event(4, 1380.0, ENEMY_JUNGLER))
        players = scoreboard_at(
            game_time_seconds,
            respawn_at_by_champion or {},
            zed_reaches_six_at_seconds,
            zed_buys_at_seconds,
            vi_farms_at_seconds,
            vi_wards_at_seconds,
        )
        writer.write_snapshot(
            received_at_seconds=index * 0.5,
            payload=all_game_data(
                game_time_seconds, events, players=players, map_terrain="Infernal"
            ),
        )
    writer.write_ended(received_at_seconds=snapshot_count * 0.5, reason="game ended")
    return writer.close()


def looked_up_players() -> list[tuple[str, JsonValue]]:
    """The client's answers about each player: Zed has a record, everyone else a bare rank."""
    zed = DEFAULT_PLAYERS[7]
    zed_id = CHAMPION_IDS["Zed"]
    answers: list[tuple[str, JsonValue]] = [
        (GAMEFLOW_SESSION_PATH, gameflow_session()),
        (CHAMPION_SUMMARY_PATH, champion_summary()),
    ]
    for seed in DEFAULT_PLAYERS:
        is_zed = seed is zed
        answers.append(
            (
                RANKED_STATS_PATH_TEMPLATE.format(puuid=puuid_of(seed)),
                ranked_stats("PLATINUM", "IV", 12, 40, 38)
                if is_zed
                else ranked_stats("GOLD", "I", 75, 20, 18),
            )
        )
        past_games = (
            [PastGame(zed_id, "MIDDLE", "SOLO", is_win=True)] * 3
            + [PastGame(CHAMPION_IDS["Ahri"], "MIDDLE", "SOLO", is_win=False)] * 2
            if is_zed
            else []
        )
        answers.append(
            (
                MATCH_HISTORY_PATH_TEMPLATE.format(puuid=puuid_of(seed)),
                match_history(puuid_of(seed), past_games),
            )
        )
    return answers


@contextlib.asynccontextmanager
async def open_overlay(
    tmp_path: Path,
    snapshot_count: int,
    speed: float,
    respawn_at_by_champion: dict[str, float] | None = None,
    zed_reaches_six_at_seconds: float | None = None,
    is_baron_taken: bool = True,
    zed_buys_at_seconds: float | None = None,
    vi_farms_at_seconds: tuple[float, ...] = (),
    vi_wards_at_seconds: float | None = None,
) -> AsyncIterator[Page]:
    replay = RecordingReplay(
        write_recording(
            tmp_path,
            snapshot_count,
            respawn_at_by_champion,
            zed_reaches_six_at_seconds,
            is_baron_taken,
            zed_buys_at_seconds,
            vi_farms_at_seconds,
            vi_wards_at_seconds,
        ),
        speed=speed,
    )
    overlay_urls: list[str] = []
    overlay_is_up = asyncio.Event()

    def note_overlay_url(overlay_url: str) -> None:
        overlay_urls.append(overlay_url)
        overlay_is_up.set()

    async with (
        serve(create_replay_application(replay)) as game_url,
        serve(fake_data_dragon([], FIXTURE_VERSIONS)) as data_dragon_url,
    ):
        settings = Settings(
            game_api_base_url=game_url,
            league_client_base_url=game_url,
            data_dragon_base_url=data_dragon_url,
            patch_data_directory=tmp_path / "patch-data",
            league_game_config=tmp_path / "no-game.cfg",
            player_lookup_pause_seconds=0.0,
            poll_interval_seconds=0.1,
            record_while_running=False,
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
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
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
    async with open_overlay(tmp_path, snapshot_count=40, speed=8.0) as page:
        await expect(page.locator("#dragon-widget")).to_be_visible(timeout=2000)
        await expect(page.locator("#dragon-widget")).to_be_hidden(timeout=10000)


async def test_the_strip_shows_the_enemy_buff_and_the_fallen_inhibitor(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        pills = page.locator("#objective-pills .pill")
        # Baron was taken at 23:00 and respawns at 29:00, too far off to show; the Voidgrubs left
        # at 14:45 and the Herald at 19:45. At 23:15: the enemy's Baron buff has 2:45 left, and
        # the enemy's top inhibitor, down since 23:05, has 4:50.
        await expect(pills).to_have_count(2, timeout=5000)
        await expect(pills.nth(0)).to_have_text(re.compile(r"^Enemy baron buff\s*2:[34]\d$"))
        await expect(pills.nth(1)).to_have_text(re.compile(r"^Enemy top inhib\s*4:[45]\d$"))
        await expect(pills.nth(0)).to_have_attribute("data-side", "enemy")
        await keep_screenshot(page, "objective-strip")


async def test_an_epic_monster_that_is_up_shows_in_the_strip(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0, is_baron_taken=False) as page:
        # Baron spawned at 20:00 and nobody has taken him; no "~", since his spawn time is
        # confirmed for this season.
        baron_pill = page.locator("#objective-pills .pill").first
        await expect(baron_pill).to_have_text(re.compile(r"^Baron\s*up$"), timeout=5000)
        await keep_screenshot(page, "monster-up")


async def test_two_enemies_down_open_a_numbers_window_and_show_in_the_enemy_strip(
    tmp_path: Path,
) -> None:
    # Zed is back at 23:40 and Caitlyn at 23:55; from 23:15, two enemies are down for 40s.
    respawns = {"Zed": 1420.0, "Caitlyn": 1435.0}
    async with open_overlay(
        tmp_path, snapshot_count=60, speed=1.0, respawn_at_by_champion=respawns
    ) as page:
        numbers = page.locator('#objective-pills .pill[data-kind="numbers"]')
        await expect(numbers).to_have_text(
            re.compile(r"^2 enemies down \(0 of yours\)\s*0:[34]\d$"), timeout=5000
        )
        rows = page.locator("#enemy-strip .enemy-row")
        await expect(rows).to_have_count(5)
        zed_row = rows.filter(has_text="Zed")
        await expect(zed_row).to_have_attribute("data-dead", "true")
        await expect(zed_row.locator(".enemy-respawn")).to_have_text(re.compile(r"^0:[12]\d$"))
        await expect(rows.filter(has_text="Lux")).to_have_attribute("data-dead", "false")
        await keep_screenshot(page, "numbers-and-enemies")


async def test_an_enemy_reaching_level_six_is_called_out(tmp_path: Path) -> None:
    async with open_overlay(
        tmp_path, snapshot_count=60, speed=1.0, zed_reaches_six_at_seconds=1397.0
    ) as page:
        callout = page.locator('#callouts .callout[data-kind="level_spike"]')
        await expect(callout).to_have_text("Zed is level 6", timeout=5000)
        await keep_screenshot(page, "callout")
        # Shown for six seconds of game time, then gone.
        await expect(callout).to_have_count(0, timeout=10000)


async def test_an_enemy_close_to_six_shows_when_they_reach_it(tmp_path: Path) -> None:
    async with open_overlay(
        tmp_path, snapshot_count=60, speed=1.0, zed_reaches_six_at_seconds=1420.0
    ) as page:
        zed_power_level = page.locator("#enemy-strip .enemy-row", has_text="Zed").locator(
            ".enemy-power-level"
        )
        # First seen at level 5 at 23:15, behind the prior: halfway through it, 340 experience
        # from 6 at a solo laner's 8.5 a second.
        await expect(zed_power_level).to_have_text(re.compile(r"^6 in ~0:[1-4]\d$"), timeout=5000)
        await keep_screenshot(page, "power-level")
        # Once Zed is 6, the next power level, 11, is too far off to show.
        await expect(zed_power_level).to_have_count(0, timeout=40000)


async def test_an_enemy_who_buys_alive_has_gone_back(tmp_path: Path) -> None:
    async with open_overlay(
        tmp_path, snapshot_count=60, speed=1.0, zed_buys_at_seconds=1405.0
    ) as page:
        zed_back = page.locator("#enemy-strip .enemy-row", has_text="Zed").locator(".enemy-back")
        # Zed buys a Long Sword at 23:25 alive: back in mid 5 seconds of shopping and 7,500 units
        # at the stand-in patch's 345 later.
        await expect(zed_back).to_have_text(
            re.compile(r"^went back 23:25 \u00b7 returns ~0:[12]\d$"), timeout=15000
        )
        await keep_screenshot(page, "went-back")
        # With a Long Sword, Infinity Edge is the stand-in catalog's one finished item left.
        zed_next_item = page.locator("#enemy-strip .enemy-row", has_text="Zed").locator(
            ".enemy-next-item"
        )
        await expect(zed_next_item).to_have_text(
            re.compile(r"^next Infinity Edge \u00b7 3\.[01]k left \u00b7 \d+% now$")
        )


async def test_an_enemy_seen_at_an_objective_shows_where_and_how_long_ago(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        vi_seen = page.locator("#enemy-strip .enemy-row", has_text="Vi").locator(".enemy-seen")
        # Their jungler took the third dragon at 23:10, after Baron at 23:00.
        await expect(vi_seen).to_have_text(re.compile(r"^at Dragon 0:[0-4]\d ago$"), timeout=5000)
        await expect(vi_seen).to_have_attribute("data-kind", "objective")
        await keep_screenshot(page, "last-seen")
        # Ten seconds after that, where they likely are shows too.
        vi_location = page.locator("#enemy-strip .enemy-row", has_text="Vi").locator(
            ".enemy-location"
        )
        await expect(vi_location).to_have_text(
            re.compile(r"^likely .+ \d+% \u00b7 unseen 0:[1-4]\d$"), timeout=10000
        )


async def test_the_enemy_junglers_path_and_the_camps_down_show(tmp_path: Path) -> None:
    async with open_overlay(
        tmp_path, snapshot_count=80, speed=1.0, vi_farms_at_seconds=(1412.0, 1422.0)
    ) as page:
        vi_path = page.locator("#enemy-strip .enemy-row", has_text="Vi").locator(
            ".enemy-jungle-path"
        )
        await expect(vi_path).to_have_text(
            re.compile(r"^path .+ \u2192 .+ \u00b7 next .+ ~\d:\d\d$"),
            # The second camp is decoded once its burst is over, at 23:48 of the replay.
            timeout=60000,
        )
        await expect(page.locator("#enemy-strip .camp-timers")).to_have_text(
            re.compile(r"^Camps: .+ \d:\d\d")
        )
        await keep_screenshot(page, "jungle-path")


async def test_an_enemy_control_ward_shows_where_it_likely_is(tmp_path: Path) -> None:
    async with open_overlay(
        tmp_path, snapshot_count=60, speed=1.0, vi_wards_at_seconds=1410.0
    ) as page:
        await expect(page.locator("#enemy-strip .ward-list")).to_have_text(
            re.compile(r"^Wards: Vi likely .+ \d+% \u00b7 0:\d\d ago$"), timeout=20000
        )
        await keep_screenshot(page, "control-wards")


async def test_the_minimap_layer_marks_where_each_enemy_likely_is(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        minimap = page.locator("#minimap")
        # League's settings file is missing: the layer takes the default place.
        await expect(minimap).to_have_attribute("data-side", "right", timeout=5000)
        for champion_name in ("Darius", "Vi", "Zed", "Caitlyn", "Lux"):
            await expect(minimap.locator(f'circle[data-champion="{champion_name}"]')).to_have_count(
                1
            )
        await keep_screenshot(page, "minimap")


async def test_the_enemy_strip_shows_item_gold_and_the_lead(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        lead = page.locator("#enemy-strip .item-lead.items")
        # Your Jinx holds two Long Swords (700), their Caitlyn an Infinity Edge (3400).
        await expect(lead).to_have_text(
            re.compile(rf"^Item gold\s*{MINUS_SIGN}2\.7k$"), timeout=5000
        )
        await expect(lead).to_have_attribute("data-lead", "enemy")
        caitlyn_gold = page.locator("#enemy-strip .enemy-row", has_text="Caitlyn").locator(
            ".enemy-gold"
        )
        await expect(caitlyn_gold).to_have_text("3.4k")
        # In role order, with the roles the game gave.
        await expect(page.locator("#enemy-strip .enemy-role")).to_have_text(
            ["TOP", "JGL", "MID", "BOT", "SUP"]
        )
        await keep_screenshot(page, "item-gold")


async def test_the_enemy_strip_shows_each_enemys_health_armor_and_magic_resist(
    tmp_path: Path,
) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        caitlyn_stats = page.locator("#enemy-strip .enemy-row", has_text="Caitlyn").locator(
            ".enemy-stats"
        )
        # Level 9 with an Infinity Edge, at the stand-in patch's numbers: an estimate.
        await expect(caitlyn_stats).to_have_text("1.3k HP · 59 AR · 39 MR", timeout=5000)
        await expect(caitlyn_stats).to_have_attribute("data-source", "estimate")
        await keep_screenshot(page, "combat-stats")


async def test_the_enemy_strip_shows_what_each_enemy_holds_and_the_gold_lead(
    tmp_path: Path,
) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        caitlyn_unspent = page.locator("#enemy-strip .enemy-row", has_text="Caitlyn").locator(
            ".enemy-unspent"
        )
        # At 23:15 Caitlyn has earned about 3.6k (starting and passive gold, and Baron's 300) and
        # holds an Infinity Edge (3.4k): about 0.2k in hand, give or take 0.3k.
        await expect(caitlyn_unspent).to_have_text(
            re.compile(r"^0\.[23]k \u00b10\.3k unspent$"), timeout=5000
        )
        await expect(caitlyn_unspent).to_have_attribute("data-source", "estimate")
        # The built game gives your Ahri 500 gold all game, so their team leads.
        gold_lead = page.locator("#enemy-strip .gold-lead")
        await expect(gold_lead).to_have_text(
            re.compile(rf"^Gold\s*{MINUS_SIGN}4\.\dk \u00b10\.8k$")
        )
        await expect(gold_lead).to_have_attribute("data-lead", "enemy")
        await keep_screenshot(page, "hidden-gold")


async def test_the_enemy_strip_shows_each_enemys_rank_and_record(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        zed_intel = page.locator("#enemy-strip .enemy-row", has_text="Zed").locator(".enemy-intel")
        # Platinum IV; 3 wins and 2 losses lately, the last three in a row, all three on Zed.
        await expect(zed_intel).to_have_text(f"P4 · 3{EN_DASH}2 W3 · 3 on champ", timeout=5000)
        await expect(zed_intel).to_have_attribute("data-off-role", "false")
        caitlyn_intel = page.locator("#enemy-strip .enemy-row", has_text="Caitlyn").locator(
            ".enemy-intel"
        )
        await expect(caitlyn_intel).to_have_text("G1")
        await keep_screenshot(page, "player-intel")


async def test_a_marked_flash_shows_on_the_enemys_row_and_counts_down(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        mark_status = 0
        for _ in range(50):
            # As the macOS app sends it: Zed is third in role order.
            mark_response = await page.request.post(
                page.url + "marks",
                data={"enemy_slot": 3, "spell": "flash"},
                headers={"X-LeagueasyMode-Request": "mark"},
            )
            mark_status = mark_response.status
            if mark_status == 200:
                break
            await asyncio.sleep(0.1)
        assert mark_status == 200
        zed_cooldowns = page.locator("#enemy-strip .enemy-row", has_text="Zed").locator(
            ".enemy-cooldowns"
        )
        await expect(zed_cooldowns).to_have_text(re.compile(r"^F 4:5\d$|^F 5:00$"), timeout=5000)
        await keep_screenshot(page, "marked-cooldown")


async def test_a_marked_flash_brings_a_suggestion(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        for _ in range(50):
            mark_response = await page.request.post(
                page.url + "marks",
                data={"enemy_slot": 3, "spell": "flash"},
                headers={"X-LeagueasyMode-Request": "mark"},
            )
            if mark_response.status == 200:
                break
            await asyncio.sleep(0.1)
        suggestion = page.locator('#callouts .callout[data-kind="suggestion"]')
        await expect(suggestion).to_have_text(
            re.compile(r"^Zed has no Flash for (4:5\d|5:00): punish it$"), timeout=5000
        )
        await keep_screenshot(page, "suggestion")
