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
    jungle_start_timeline,
    match_history,
    past_game_id,
    puuid_of,
    ranked_stats,
    ten_minute_timeline,
    turret_killed_event,
)
from leagueasymode.cli import run_overlay
from leagueasymode.config import Settings
from leagueasymode.inference.rift_map import RIFT_MAP
from leagueasymode.league_client import GAMEFLOW_SESSION_PATH
from leagueasymode.overlay_state import OverlayPreferences
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH, GAME_VERSION_PATH, ITEMS_PATH
from leagueasymode.player_intel import MATCH_HISTORY_PATH_TEMPLATE, RANKED_STATS_PATH_TEMPLATE
from leagueasymode.preferences import save_preferences
from leagueasymode.recording.writer import RecordingWriter
from leagueasymode.replay import RecordingReplay, create_replay_application
from local_servers import serve
from test_player_intel import ZED_FIRST_GAME_ID, ZED_TEN_MINUTES

pytestmark = pytest.mark.browser

ENEMY_JUNGLER: Final = DEFAULT_PLAYERS[6].riot_id_game_name
VI_SEED: Final = DEFAULT_PLAYERS[6]
# Vi's recent jungle games, newest first: her team's id and where she was at 2:00 and at 4:00.
VI_STARTS: Final = (
    (100, "order_red_buff", "top_river_scuttle"),
    (200, "chaos_red_buff", "bot_river_scuttle"),
    (100, "order_blue_buff", "mid_center"),
    (200, "chaos_red_buff", "order_bot_lane_2"),
)
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
    turret_kills: tuple[tuple[int, float, str], ...] = (),
    first_game_time_seconds: float = 1395.0,
    map_number: int = 11,
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
        game_time_seconds = first_game_time_seconds + index * 0.5
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
        # Each turret enters the feed when it falls, so that an inhibitor can open mid-replay.
        events.extend(
            turret_killed_event(event_id, fell_at_seconds, turret_name, ENEMY_JUNGLER)
            for event_id, fell_at_seconds, turret_name in turret_kills
            if fell_at_seconds <= game_time_seconds
        )
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
                game_time_seconds,
                [event for event in events if has_happened(event, game_time_seconds)],
                players=players,
                map_terrain="Infernal",
                map_number=map_number,
            ),
        )
    writer.write_ended(received_at_seconds=snapshot_count * 0.5, reason="game ended")
    return writer.close()


def looked_up_players() -> list[tuple[str, JsonValue]]:
    """The client's answers about each player.

    Zed has a record, with his creep score and gold at 10:00 in each game, and Vi has four games
    in the jungle, three of them started at red buff; everyone else has a bare rank.
    """
    zed = DEFAULT_PLAYERS[7]
    zed_id = CHAMPION_IDS["Zed"]
    answers: list[tuple[str, JsonValue]] = [
        (GAMEFLOW_SESSION_PATH, gameflow_session()),
        (CHAMPION_SUMMARY_PATH, champion_summary()),
        *vis_jungle_starts(),
        *(
            (
                f"/lol-match-history/v1/game-timelines/{game_id}",
                ten_minute_timeline(creep_score, gold),
            )
            for game_id, (creep_score, gold) in ZED_TEN_MINUTES.items()
        ),
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
        if is_zed:
            past_games = [PastGame(zed_id, "MIDDLE", "SOLO", is_win=True)] * 3 + [
                PastGame(CHAMPION_IDS["Ahri"], "MIDDLE", "SOLO", is_win=False)
            ] * 2
        elif seed is VI_SEED:
            past_games = [
                PastGame(CHAMPION_IDS["Vi"], "JUNGLE", "NONE", is_win=True, team_id=team_id)
                for team_id, _, _ in VI_STARTS
            ]
        else:
            past_games = []
        answers.append(
            (
                MATCH_HISTORY_PATH_TEMPLATE.format(puuid=puuid_of(seed)),
                match_history(puuid_of(seed), past_games, ZED_FIRST_GAME_ID if is_zed else None),
            )
        )
    return answers


def has_happened(event: dict[str, JsonValue], game_time_seconds: float) -> bool:
    """Whether an event is in the feed by a time: a replay that starts early has not had all."""
    event_time = event["EventTime"]
    return isinstance(event_time, int | float) and event_time <= game_time_seconds


def vis_jungle_starts() -> list[tuple[str, JsonValue]]:
    """Each of Vi's past jungle games' timelines: at a buff at 2:00, and somewhere at 4:00."""
    answers: list[tuple[str, JsonValue]] = []
    for index, (_, start_point_name, four_minute_point_name) in enumerate(VI_STARTS):
        start_point = RIFT_MAP.points[start_point_name]
        four_minute_point = RIFT_MAP.points[four_minute_point_name]
        answers.append(
            (
                f"/lol-match-history/v1/game-timelines/{past_game_id(index)}",
                jungle_start_timeline(
                    start_point.x_position,
                    start_point.y_position,
                    (four_minute_point.x_position, four_minute_point.y_position),
                ),
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
    preferences: OverlayPreferences | None = None,
    init_script: str | None = None,
    turret_kills: tuple[tuple[int, float, str], ...] = (),
    first_game_time_seconds: float = 1395.0,
    map_number: int = 11,
    hold_details: bool = True,
) -> AsyncIterator[Page]:
    # Details show only while Tab or Option is held (the owner: "maybe extra details onyl show if
    # i hit tab"); the tests of what they show hold the key, as the app tells the page.
    if preferences is not None:
        save_preferences(tmp_path / "preferences.json", preferences)
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
            turret_kills,
            first_game_time_seconds,
            map_number,
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
            model_weights=tmp_path / "no-model-weights.json",
            preferences=tmp_path / "preferences.json",
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
            if init_script is not None:
                await page.add_init_script(init_script)
            await page.goto(overlay_urls[0])
            if hold_details:
                await hold_the_details_key(page, is_held=True)
            try:
                yield page
            finally:
                await browser.close()
                stop_requested.set()
                await overlay_task


async def hold_the_details_key(page: Page, *, is_held: bool) -> None:
    """Do what the macOS app does while Tab or Option is held, or let go."""
    await page.wait_for_function("window.leagueasymodeSetDetailsHeld !== undefined")
    await page.evaluate(f"window.leagueasymodeSetDetailsHeld({'true' if is_held else 'false'})")


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


async def test_the_strip_shows_each_sides_turrets_down_and_an_inhibitor_opening(
    tmp_path: Path,
) -> None:
    turret_kills = (
        (20, 1000.0, "Turret_T2_R_03_A"),
        (21, 1200.0, "Turret_T2_R_02_A"),
        (22, 1300.0, "Turret_T1_C_05_A"),
        # Their bot inhibitor turret falls a few seconds into the replay, opening the inhibitor.
        (23, 1398.0, "Turret_T2_R_01_A"),
    )
    async with open_overlay(
        tmp_path, snapshot_count=60, speed=1.0, turret_kills=turret_kills
    ) as page:
        enemy_turrets = page.locator(
            '#objective-pills .pill[data-kind="structures"][data-side="enemy"]'
        )
        await expect(enemy_turrets).to_have_text(
            re.compile(r"^Enemy turrets\s*bot 3, inhib open$"), timeout=8000
        )
        ally_turrets = page.locator(
            '#objective-pills .pill[data-kind="structures"][data-side="ally"]'
        )
        await expect(ally_turrets).to_have_text(re.compile(r"^Your turrets\s*mid 1$"))
        callout = page.locator('#callouts .callout[data-kind="inhibitor_open"]')
        await expect(callout).to_have_text("Enemy bot inhibitor is open")
        await keep_screenshot(page, "structures")


async def test_an_epic_monster_that_is_up_shows_in_the_strip(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0, is_baron_taken=False) as page:
        # Baron spawned at 20:00 and nobody has taken him; no "~", since his spawn time is
        # confirmed for this season.
        baron_pill = page.locator("#objective-pills .pill").first
        await expect(baron_pill).to_have_text(re.compile(r"^Baron\s*up$"), timeout=5000)
        await keep_screenshot(page, "monster-up")


async def test_a_monster_that_is_up_shows_how_long_it_takes_and_whether_they_contest(
    tmp_path: Path,
) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0, is_baron_taken=False) as page:
        # Baron is up at 23:15: how long your five take on him, and the chance they come.
        contest = page.locator('#objective-pills .pill[data-kind="contest"]')
        await expect(contest).to_have_text(
            re.compile(r"^Baron ~\d+:\d\d with 5\s*contest ~\d+%( \(\w+\))?$"), timeout=5000
        )
        await keep_screenshot(page, "objective-contest")


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


# Stands in for the macOS app's voice: what the page hands it is kept to be read back.
APP_VOICE_STAND_IN: Final = """
window.spokenCallouts = [];
window.webkit = {messageHandlers: {leagueasymodeSpeak: {
    postMessage: (text) => window.spokenCallouts.push(text),
}}};
"""


async def test_a_new_callout_is_spoken_once_when_the_player_turned_speech_on(
    tmp_path: Path,
) -> None:
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        zed_reaches_six_at_seconds=1397.0,
        preferences=OverlayPreferences(speak_callouts=True),
        init_script=APP_VOICE_STAND_IN,
    ) as page:
        callout = page.locator('#callouts .callout[data-kind="level_spike"]')
        await expect(callout).to_have_text("Zed is level 6", timeout=5000)
        # Drawn again four times a second while it shows, and spoken once.
        await expect(callout).to_have_count(0, timeout=10000)
        spoken = await page.evaluate("window.spokenCallouts")
    assert isinstance(spoken, list)
    assert spoken.count("Zed is level 6") == 1
    # Every callout shown is spoken once, the item ones at the start too.
    assert len(spoken) == len(set(spoken))


async def test_callouts_are_not_spoken_unless_the_player_turned_speech_on(tmp_path: Path) -> None:
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        zed_reaches_six_at_seconds=1397.0,
        init_script=APP_VOICE_STAND_IN,
    ) as page:
        callout = page.locator('#callouts .callout[data-kind="level_spike"]')
        await expect(callout).to_have_text("Zed is level 6", timeout=5000)
        spoken = await page.evaluate("window.spokenCallouts")
    assert spoken == []


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


async def test_jungler_and_roamers_only_leaves_laners_in_lane_off_the_minimap(
    tmp_path: Path,
) -> None:
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        preferences=OverlayPreferences(minimap_roamers_only=True),
    ) as page:
        minimap = page.locator("#minimap")
        # The jungler always shows.
        await expect(minimap.locator('circle[data-champion="Vi"]')).to_have_count(1, timeout=5000)
        state_response = await page.request.get(page.url + "state")
        enemies = [
            card for card in (await state_response.json())["players"] if card["side"] == "enemy"
        ]
        shown = {
            card["champion_name"]
            for card in enemies
            if card["location"] is not None and (card["role"] == "JUNGLE" or card["is_roaming"])
        }
        hidden = {card["champion_name"] for card in enemies} - shown
        # The replay has laners in their lanes, so the setting has someone to leave off.
        assert hidden
        for champion_name in hidden:
            await expect(minimap.locator(f'circle[data-champion="{champion_name}"]')).to_have_count(
                0
            )
        await keep_screenshot(page, "minimap-roamers-only")


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


async def test_an_enemy_in_sight_has_no_mark_on_the_minimap(tmp_path: Path) -> None:
    # Vi's creep score rises at 23:20, which the game shows only while your team sees her.
    async with open_overlay(
        tmp_path, snapshot_count=40, speed=1.0, vi_farms_at_seconds=(1400.0,)
    ) as page:
        minimap = page.locator("#minimap")
        vi_mark = minimap.locator('circle[data-champion="Vi"]')
        await expect(vi_mark).to_have_count(0, timeout=10000)
        await expect(minimap.locator('circle[data-champion="Zed"]')).to_have_count(1)
        await keep_screenshot(page, "minimap-enemy-in-sight")
        # Three seconds on, unseen again, she has her mark back.
        await expect(vi_mark).to_have_count(1, timeout=10000)


async def test_off_the_rift_its_widgets_and_the_minimap_layer_hide(tmp_path: Path) -> None:
    # The same game on ARAM's map: the enemies show, the Rift's dragon, objectives and minimap not.
    # The fallen inhibitor stays, its time marked unconfirmed (the owner, 2026-10-29: "no ARAM
    # timers except inhib"); it was asserted hidden before that.
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0, map_number=12) as page:
        await expect(page.locator("#enemy-strip .enemy-row")).to_have_count(5, timeout=5000)
        await expect(page.locator("#dragon-widget")).to_be_hidden()
        pills = page.locator("#objective-pills .pill")
        await expect(pills).to_have_count(1)
        await expect(pills.nth(0)).to_have_text(re.compile(r"^Enemy top inhib\s*~4:[45]\d$"))
        await expect(page.locator("#minimap")).to_be_hidden()
        await keep_screenshot(page, "off-the-rift")


async def test_each_enemys_row_shows_their_ultimates_rank(tmp_path: Path) -> None:
    # Level 9 in the replay: their ultimate is learned, at rank 1; at 5, Zed's is not yet.
    async with open_overlay(
        tmp_path, snapshot_count=60, speed=1.0, zed_reaches_six_at_seconds=1450.0
    ) as page:
        darius_ultimate = page.locator("#enemy-strip .enemy-row", has_text="Darius").locator(
            ".enemy-ultimate"
        )
        await expect(darius_ultimate).to_have_text("R1", timeout=10000)
        zed_ultimate = page.locator("#enemy-strip .enemy-row", has_text="Zed").locator(
            ".enemy-ultimate"
        )
        await expect(zed_ultimate).to_have_text("no R")
        await keep_screenshot(page, "ultimate-ranks")


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
    # The detailed rows: the focused default keeps only what may change a decision now.
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        preferences=OverlayPreferences(detailed_enemy_rows=True),
    ) as page:
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
    # The detailed rows: the focused default keeps only what may change a decision now.
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        preferences=OverlayPreferences(detailed_enemy_rows=True),
    ) as page:
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


async def test_the_enemy_strip_shows_the_win_chance_and_what_moves_it(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        # At 23:15 their team leads on gold (your Ahri holds 500 all game) and holds Baron.
        win = page.locator("#enemy-strip .win-chance")
        await expect(win).to_have_text(
            re.compile(rf"^Win\s*~\d+% \u00b7 gold {MINUS_SIGN}4\.\dk, their Baron$"),
            timeout=5000,
        )
        await expect(win).to_have_attribute("data-lead", "enemy")
        await keep_screenshot(page, "win-chance")


async def test_the_enemy_strip_shows_an_even_fights_chance(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        # Everyone is alive at 23:15; the stand-in patch rates their damage mostly physical.
        fight = page.locator("#enemy-strip .fight-chance")
        await expect(fight).to_have_text(
            re.compile(r"^Fight now\s*~\d+% \u00b7 their damage \d+% physical$"), timeout=5000
        )
        await keep_screenshot(page, "fight-chance")


async def test_the_you_panel_shows_what_to_build_and_your_pace(tmp_path: Path) -> None:
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        panel = page.locator("#you-panel")
        await expect(panel.locator(".you-defenses")).to_have_text(
            re.compile(
                r"^(Armor|MR|HP) \d+\.\d\u00d7 (Armor|MR|HP) \u00b7 their damage \d+% physical$"
            ),
            timeout=5000,
        )
        await expect(panel.locator(".you-pace")).to_have_text(re.compile(r"^CS \d+\.\d/min"))
        # Your Ahri holds 500 gold, under the 1,300 that counts as holding.
        await expect(panel.locator(".you-holding")).to_have_count(0)
        await keep_screenshot(page, "you-panel")


async def test_before_ten_minutes_the_you_panel_shows_your_lane_opponent(tmp_path: Path) -> None:
    async with open_overlay(
        tmp_path, snapshot_count=60, speed=1.0, first_game_time_seconds=300.0
    ) as page:
        # Zed, in mid against your Ahri, has 76.4 creep score and 3,440 gold at 10:00 in their
        # games; your Ahri has none yet, five minutes in.
        await expect(page.locator("#you-panel .you-opponent")).to_have_text(
            "Zed at 10:00 ~76 CS 3.4k \u00b7 you ~0", timeout=5000
        )
        await keep_screenshot(page, "you-panel-lane-opponent")


async def test_what_the_player_turned_off_does_not_show(tmp_path: Path) -> None:
    # With the detailed rows, to tell what is turned off from what the focused rows leave out.
    preferences = OverlayPreferences(
        show_win_chance=False,
        show_you_panel=False,
        show_enemy_estimates=False,
        detailed_enemy_rows=True,
    )
    async with open_overlay(
        tmp_path, snapshot_count=60, speed=1.0, preferences=preferences
    ) as page:
        # The fight chance still shows, and with it the strip's headers, but not the win chance.
        await expect(page.locator("#enemy-strip .fight-chance")).to_be_visible(timeout=5000)
        await expect(page.locator("#enemy-strip .win-chance")).to_have_count(0)
        await expect(page.locator("#you-panel")).to_be_hidden()
        caitlyn = page.locator("#enemy-strip .enemy-row", has_text="Caitlyn")
        await expect(caitlyn.locator(".enemy-unspent")).to_have_count(0)
        # Exact facts stay: her health, armor and magic resist.
        await expect(caitlyn.locator(".enemy-stats")).to_be_visible()


async def test_the_focused_rows_keep_only_what_may_change_a_decision(tmp_path: Path) -> None:
    # The owner, after a game: "so much info a lot of it is useless 90% of the time". At 23:15,
    # each row is one line of facts: no rank and record, no health, armor and magic resist, no
    # unspent gold; the laners' likely places are left to the minimap.
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0) as page:
        rows = page.locator("#enemy-strip .enemy-row")
        await expect(rows).to_have_count(5, timeout=5000)
        await expect(page.locator("#enemy-strip .enemy-ultimate").first).to_be_visible(
            timeout=10000
        )
        for line in (".enemy-intel", ".enemy-stats", ".enemy-unspent"):
            await expect(page.locator(f"#enemy-strip {line}")).to_have_count(0)
        darius = page.locator("#enemy-strip .enemy-row", has_text="Darius")
        await expect(darius.locator(".enemy-location")).to_have_count(0)
        await keep_screenshot(page, "focused-enemy-rows")


async def test_the_enemy_strip_shows_each_enemys_rank_and_record(tmp_path: Path) -> None:
    # The detailed rows: the focused default keeps only what may change a decision now.
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        preferences=OverlayPreferences(detailed_enemy_rows=True),
    ) as page:
        zed_intel = page.locator("#enemy-strip .enemy-row", has_text="Zed").locator(".enemy-intel")
        # Platinum IV; 3 wins and 2 losses lately, the last three in a row, all three on Zed, the
        # champion they played most; 76.4 creep score and 3,440 gold at 10:00 in their five games.
        await expect(zed_intel).to_have_text(
            f"P4 · 3{EN_DASH}2 W3 · 3 on champ (main) · 10:00 76 CS 3.4k", timeout=5000
        )
        await expect(zed_intel).to_have_attribute("data-off-role", "false")
        caitlyn_intel = page.locator("#enemy-strip .enemy-row", has_text="Caitlyn").locator(
            ".enemy-intel"
        )
        await expect(caitlyn_intel).to_have_text("G1")
        # Vi won her four recent games, all in the jungle, three of them started at red buff,
        # which is the top half of the map for her team this game; at 4:00 three found her on
        # her blue buff's half, the bottom one this game.
        vi_intel = page.locator("#enemy-strip .enemy-row", has_text="Vi").locator(".enemy-intel")
        await expect(vi_intel).to_have_text(
            f"G1 · 4{EN_DASH}0 W4 · 4 on champ (main) · starts red (top) 3/4 · 4:00 bot 3/4"
        )
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


# Stands in for the macOS app's handler, keeping each list of button places the page reports.
CLICK_REGIONS_RECORDER: Final = """
window.reportedClickRegions = [];
window.webkit = { messageHandlers: { leagueasymodeClickRegions: {
  postMessage: (regionsText) => window.reportedClickRegions.push(JSON.parse(regionsText)),
} } };
"""


# Where Zed's Flash button is now, measured in the page as the strip is drawn again.
ZED_FLASH_BUTTON_CENTER: Final = """() => {
  const row = [...document.querySelectorAll("#enemy-strip .enemy-row")]
    .find((element) => element.textContent.includes("Zed"));
  const button = row?.querySelector(".mark-button");
  if (button === undefined || button === null) return null;
  const box = button.getBoundingClientRect();
  return [box.left + box.width / 2, box.top + box.height / 2];
}"""


async def test_a_click_on_an_enemys_spell_button_marks_it(tmp_path: Path) -> None:
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        preferences=OverlayPreferences(click_to_mark=True),
        init_script=CLICK_REGIONS_RECORDER,
    ) as page:
        # A screen's height, so that the enemy strip's buttons are on the page to press.
        await page.set_viewport_size({"width": 1280, "height": 900})
        zed_row = page.locator("#enemy-strip .enemy-row", has_text="Zed")
        zed_buttons = zed_row.locator(".mark-button")
        await expect(zed_buttons).to_have_text(["Flash", "Ignite", "R"], timeout=5000)
        # The page tells the app where each button is, so that it takes those clicks only.
        regions = await page.evaluate("window.reportedClickRegions.at(-1)")
        assert len(regions) == await page.locator(".mark-button").count()
        assert all(width > 0 and height > 0 for _, _, width, height in regions)
        # A press where the button is, as a player's: the strip is drawn again every quarter
        # second, and the press counts on the strip itself, whichever row is under it then. The
        # engine takes marks once the patch's cooldowns are in, so the press is made again until
        # the timer shows, as the app's shortcut test asks again.
        zed_cooldowns = zed_row.locator(".enemy-cooldowns")
        for _ in range(40):
            flash_center = await page.evaluate(ZED_FLASH_BUTTON_CENTER)
            if flash_center is not None:
                await page.mouse.click(flash_center[0], flash_center[1])
            await asyncio.sleep(0.3)
            if await zed_cooldowns.count() > 0:
                break
        await expect(zed_cooldowns).to_have_text(re.compile(r"^F 4:5\d$|^F 5:00$"), timeout=5000)
        await keep_screenshot(page, "click-to-mark")


async def test_without_the_setting_there_are_no_buttons_to_click(tmp_path: Path) -> None:
    async with open_overlay(
        tmp_path, snapshot_count=40, speed=1.0, init_script=CLICK_REGIONS_RECORDER
    ) as page:
        await expect(page.locator("#enemy-strip .enemy-row")).to_have_count(5, timeout=5000)
        await expect(page.locator(".mark-button")).to_have_count(0)
        assert await page.evaluate("window.reportedClickRegions.at(-1)") == []


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


async def test_at_a_glance_each_enemy_is_one_short_line_and_details_wait_for_the_key(
    tmp_path: Path,
) -> None:
    # The owner, 2026-10-29: "thers still too much visual clutter and it messes with my mouse.
    # maybe extra details onyl show if i hit tab or somethign".
    async with open_overlay(tmp_path, snapshot_count=60, speed=1.0, hold_details=False) as page:
        rows = page.locator("#enemy-strip .enemy-row")
        await expect(rows).to_have_count(5, timeout=5000)
        # Role, name, R, level, a respawn and the marked cooldowns: no gold, no second line, no
        # win chance or gold leads, no You panel.
        await expect(page.locator("#enemy-strip .enemy-gold")).to_have_text([""] * 5)
        await expect(page.locator("#enemy-strip .enemy-next-item")).to_have_count(0)
        await expect(page.locator("#enemy-strip .item-lead")).to_have_count(0)
        await expect(page.locator("#you-panel")).to_be_hidden()
        await expect(page.locator("#objective-pills .pill").first).to_be_visible()
        await keep_screenshot(page, "at-a-glance")
        await hold_the_details_key(page, is_held=True)
        await expect(page.locator("#enemy-strip .item-lead").first).to_be_visible()
        await expect(page.locator("#you-panel")).to_be_visible()
        await keep_screenshot(page, "details-held")
        await hold_the_details_key(page, is_held=False)
        await expect(page.locator("#enemy-strip .item-lead")).to_have_count(0)
        await expect(page.locator("#you-panel")).to_be_hidden()


async def test_at_a_glance_only_callouts_to_act_on_now_show(tmp_path: Path) -> None:
    # The owner, 2026-10-29: "league is already a very bsy game so if it is goign to take my eyes
    # off fights, it needs to be wort while info". Zed reaching 6 is; four enemies who can likely
    # buy an item wait for the key (this test once saw two of those at a glance).
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        zed_reaches_six_at_seconds=1397.0,
        hold_details=False,
    ) as page:
        level_six = page.locator('#callouts .callout[data-kind="level_spike"]')
        await expect(level_six).to_have_text("Zed is level 6", timeout=5000)
        items = page.locator('#callouts .callout[data-kind="item_soon"]')
        await expect(items).to_have_count(0)
        await hold_the_details_key(page, is_held=True)
        await expect(items).to_have_count(4)


async def test_at_a_glance_the_newest_line_for_chat_shows_too(tmp_path: Path) -> None:
    # The owner, 2026-10-29: "make moments and team calls show at a glance". The newest one shows
    # beside the action callouts, without taking their place. At 18:30 Baron spawns in 1:30, and
    # Vi has been missing since 11:50.
    async with open_overlay(
        tmp_path, snapshot_count=60, speed=1.0, first_game_time_seconds=1110.0, hold_details=False
    ) as page:
        team_call = page.locator('#callouts .callout[data-kind="team_call"]')
        await expect(team_call).to_have_text(re.compile(r"^Baron in 1:\d\d\. "), timeout=10000)
        await expect(page.locator('#callouts .callout[data-kind="missing"]')).to_have_count(1)
        await keep_screenshot(page, "chat-line-at-a-glance")


async def test_while_you_are_dead_the_details_show_by_themselves(tmp_path: Path) -> None:
    # Dead, the player's eyes are free: the death screen shows the details without a key, and
    # they go when the player is back. Ahri is the player in these games.
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        respawn_at_by_champion={"Ahri": 1405.0},
        hold_details=False,
    ) as page:
        leads = page.locator("#enemy-strip .item-lead")
        await expect(leads.first).to_be_visible(timeout=5000)
        items = page.locator('#callouts .callout[data-kind="item_soon"]')
        await expect(items.first).to_be_visible()
        await expect(leads).to_have_count(0, timeout=15000)


async def test_the_spell_buttons_show_only_while_the_key_is_held(tmp_path: Path) -> None:
    # A button takes the clicks on it, a right click to move too; at a glance there are none, so
    # the overlay takes no click at all.
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        preferences=OverlayPreferences(click_to_mark=True),
        hold_details=False,
    ) as page:
        await expect(page.locator("#enemy-strip .enemy-row")).to_have_count(5, timeout=5000)
        await expect(page.locator(".mark-button")).to_have_count(0)
        await hold_the_details_key(page, is_held=True)
        await expect(page.locator(".mark-button").first).to_be_visible()


async def test_with_details_always_shown_nothing_waits_for_the_key(tmp_path: Path) -> None:
    async with open_overlay(
        tmp_path,
        snapshot_count=60,
        speed=1.0,
        preferences=OverlayPreferences(details_on_hold=False),
        hold_details=False,
    ) as page:
        await expect(page.locator("#enemy-strip .item-lead").first).to_be_visible(timeout=5000)
        await expect(page.locator("#you-panel")).to_be_visible()
