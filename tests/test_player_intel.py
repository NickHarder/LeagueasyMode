import asyncio
import dataclasses
from pathlib import Path
from typing import Final

import aiohttp
from aiohttp import web
from pydantic import JsonValue

from game_payloads import (
    CHAMPION_IDS,
    DEFAULT_PLAYERS,
    PastGame,
    all_game_data,
    champion_summary,
    gameflow_session,
    jungle_start_timeline,
    match_history,
    past_game_id,
    puuid_of,
    ranked_stats,
)
from leagueasymode.cli import run_overlay
from leagueasymode.config import Settings
from leagueasymode.engine import OverlayEngine, compute_overlay_state
from leagueasymode.game_api import GameApiClient
from leagueasymode.inference.intel import player_intel
from leagueasymode.inference.rift_map import RIFT_MAP
from leagueasymode.jungle_starts import FourMinuteSides, JungleStarts
from leagueasymode.league_client import LeagueClient
from leagueasymode.overlay_state import OverlayState, RankedStanding
from leagueasymode.player_intel import (
    PLAYER_LOOKUP_PATH_PREFIXES,
    PlayerRecord,
    RecentGame,
    history_position,
    jungle_timeline_paths,
    load_player_records,
    ranked_standing_of,
    recent_games_of,
)
from local_servers import serve

ZED: Final = DEFAULT_PLAYERS[7]
ZED_ID: Final = CHAMPION_IDS["Zed"]
AHRI_ID: Final = CHAMPION_IDS["Ahri"]
VI_SEED: Final = DEFAULT_PLAYERS[6]
VI_ID: Final = CHAMPION_IDS["Vi"]
FIRST_GAME_ID: Final = past_game_id(0)
# Where Vi was at 2:00 in each of her four jungle games, by game id: red, red, blue, red.
VI_START_POINTS: Final = {
    FIRST_GAME_ID: "order_red_buff",
    FIRST_GAME_ID + 1: "chaos_red_buff",
    FIRST_GAME_ID + 2: "order_blue_buff",
    FIRST_GAME_ID + 3: "chaos_red_buff",
}
# Where she was at 4:00: on her blue buff's side three times (the blue team's top, the red team's
# bottom), and mid once.
VI_FOUR_MINUTE_POINTS: Final = {
    FIRST_GAME_ID: "top_river_scuttle",
    FIRST_GAME_ID + 1: "bot_river_scuttle",
    FIRST_GAME_ID + 2: "mid_center",
    FIRST_GAME_ID + 3: "order_bot_lane_2",
}


def zed_history() -> JsonValue:
    # Newest first: three wins on Zed in mid, then two losses on Ahri in mid.
    return match_history(
        puuid_of(ZED),
        [
            PastGame(ZED_ID, "MIDDLE", "SOLO", is_win=True),
            PastGame(ZED_ID, "MIDDLE", "SOLO", is_win=True),
            PastGame(ZED_ID, "MIDDLE", "SOLO", is_win=True),
            PastGame(AHRI_ID, "MIDDLE", "SOLO", is_win=False),
            PastGame(AHRI_ID, "MIDDLE", "SOLO", is_win=False),
        ],
    )


def test_a_ranked_answer_gives_solo_queue_first() -> None:
    assert ranked_standing_of(ranked_stats("GOLD", "II", 45, 30, 25)) == RankedStanding(
        queue="solo", tier="GOLD", division="II", league_points=45, wins=30, losses=25
    )


def test_an_unranked_player_has_no_standing() -> None:
    assert ranked_standing_of(ranked_stats("", "NA", 0, 0, 0)) is None
    assert ranked_standing_of(ranked_stats("NONE", "NA", 0, 0, 0)) is None
    assert ranked_standing_of({"message": "not found"}) is None
    assert ranked_standing_of(None) is None


def test_flex_stands_in_when_there_is_no_solo_rank() -> None:
    flex_only: JsonValue = {
        "queueMap": {
            "RANKED_FLEX_SR": {
                "queueType": "RANKED_FLEX_SR",
                "tier": "SILVER",
                "division": "I",
                "leaguePoints": 10,
                "wins": 4,
                "losses": 6,
            }
        }
    }
    standing = ranked_standing_of(flex_only)
    assert standing is not None
    assert (standing.queue, standing.tier, standing.division) == ("flex", "SILVER", "I")


def test_history_gives_each_game_newest_first_with_its_champion_position_and_result() -> None:
    games = recent_games_of(zed_history(), puuid_of(ZED))
    assert games[0] == RecentGame(
        champion_id=ZED_ID,
        position="MIDDLE",
        is_win=True,
        duration_seconds=1800,
        game_id=FIRST_GAME_ID,
        team_id=100,
        participant_id=1,
    )
    assert [game.is_win for game in games] == [True, True, True, False, False]


def test_remakes_and_games_off_the_rift_are_left_out() -> None:
    history = match_history(
        puuid_of(ZED),
        [
            PastGame(ZED_ID, "MIDDLE", "SOLO", is_win=True),
            PastGame(ZED_ID, "MIDDLE", "SOLO", is_win=False, duration_seconds=190),
            PastGame(ZED_ID, "MIDDLE", "SOLO", is_win=False, map_id=12),
        ],
    )
    assert len(recent_games_of(history, puuid_of(ZED))) == 1


def test_only_the_looked_up_players_own_line_counts() -> None:
    history = match_history("someone-else", [PastGame(ZED_ID, "MIDDLE", "SOLO", is_win=True)])
    assert recent_games_of(history, puuid_of(ZED)) == []


def test_a_history_answer_that_is_not_one_has_no_games() -> None:
    assert recent_games_of({"message": "not found"}, puuid_of(ZED)) == []
    assert recent_games_of(None, puuid_of(ZED)) == []


def test_lane_and_role_give_the_position() -> None:
    assert history_position("TOP", "SOLO", "") == "TOP"
    assert history_position("JUNGLE", "NONE", "") == "JUNGLE"
    assert history_position("MIDDLE", "SOLO", "") == "MIDDLE"
    assert history_position("BOTTOM", "CARRY", "") == "BOTTOM"
    assert history_position("BOTTOM", "DUO_CARRY", "") == "BOTTOM"
    assert history_position("BOTTOM", "SUPPORT", "") == "UTILITY"
    assert history_position("BOTTOM", "DUO_SUPPORT", "") == "UTILITY"
    assert history_position("NONE", "DUO", "") == ""
    # The game's own position, where the answer has it, wins.
    assert history_position("BOTTOM", "DUO", "UTILITY") == "UTILITY"


def zed_record() -> PlayerRecord:
    return PlayerRecord(
        ranked=ranked_standing_of(ranked_stats("PLATINUM", "IV", 12, 40, 38)),
        recent_games=tuple(recent_games_of(zed_history(), puuid_of(ZED))),
    )


def test_intel_counts_recent_games_the_streak_and_games_on_the_champion() -> None:
    intel = player_intel(zed_record(), ZED_ID, "MIDDLE")
    assert (intel.recent_game_count, intel.recent_win_count) == (5, 3)
    assert intel.streak == 3
    assert (intel.champion_game_count, intel.champion_win_count) == (3, 3)
    assert intel.ranked is not None
    assert intel.ranked.tier == "PLATINUM"


def test_a_losing_streak_is_negative() -> None:
    record = PlayerRecord(
        ranked=None,
        recent_games=(
            RecentGame(champion_id=ZED_ID, position="MIDDLE", is_win=False),
            RecentGame(champion_id=ZED_ID, position="MIDDLE", is_win=False),
            RecentGame(champion_id=ZED_ID, position="MIDDLE", is_win=True),
        ),
    )
    assert player_intel(record, ZED_ID, "MIDDLE").streak == -2


def test_a_player_away_from_their_usual_position_is_off_role() -> None:
    intel = player_intel(zed_record(), ZED_ID, "TOP")
    assert intel.usual_position == "MIDDLE"
    assert intel.is_off_role is True
    assert player_intel(zed_record(), ZED_ID, "MIDDLE").is_off_role is False


def test_too_few_games_or_no_clear_favourite_gives_no_usual_position() -> None:
    few = PlayerRecord(
        ranked=None,
        recent_games=tuple(RecentGame(ZED_ID, "MIDDLE", is_win=True) for _ in range(3)),
    )
    assert player_intel(few, ZED_ID, "TOP").usual_position == ""
    spread = PlayerRecord(
        ranked=None,
        recent_games=tuple(
            RecentGame(ZED_ID, position, is_win=True)
            for position in ("TOP", "MIDDLE", "TOP", "MIDDLE", "JUNGLE", "BOTTOM")
        ),
    )
    intel = player_intel(spread, ZED_ID, "TOP")
    assert intel.usual_position == ""
    assert intel.is_off_role is False


def games_on(game_counts: dict[int, int]) -> PlayerRecord:
    return PlayerRecord(
        ranked=None,
        recent_games=tuple(
            RecentGame(champion_id, "MIDDLE", is_win=True)
            for champion_id, game_count in game_counts.items()
            for _ in range(game_count)
        ),
    )


def test_a_champion_played_more_than_any_other_is_their_main() -> None:
    # Zed's history: three games on Zed, two on Ahri.
    intel = player_intel(zed_record(), ZED_ID, "MIDDLE")
    assert (intel.champion_pool_size, intel.is_main_champion, intel.is_one_trick) == (
        2,
        True,
        False,
    )
    assert player_intel(zed_record(), AHRI_ID, "MIDDLE").is_main_champion is False


def test_a_main_needs_a_few_games_and_no_tie_for_the_most() -> None:
    assert player_intel(games_on({ZED_ID: 2}), ZED_ID, "MIDDLE").is_main_champion is False
    tie = games_on({ZED_ID: 3, AHRI_ID: 3})
    assert player_intel(tie, ZED_ID, "MIDDLE").is_main_champion is False


def test_most_of_many_recent_games_on_one_champion_is_a_one_trick() -> None:
    intel = player_intel(games_on({ZED_ID: 14, AHRI_ID: 6}), ZED_ID, "MIDDLE")
    assert (intel.is_one_trick, intel.is_main_champion) == (True, True)
    under_the_share = games_on({ZED_ID: 13, AHRI_ID: 7})
    assert player_intel(under_the_share, ZED_ID, "MIDDLE").is_one_trick is False
    too_few_games = games_on({ZED_ID: 7})
    assert player_intel(too_few_games, ZED_ID, "MIDDLE").is_one_trick is False


def vi_history() -> JsonValue:
    # Newest first: four jungle games on Vi, on alternating sides, then one game in top.
    return match_history(
        puuid_of(VI_SEED),
        [
            *(
                PastGame(
                    VI_ID, "JUNGLE", "NONE", is_win=True, team_id=100 if index % 2 == 0 else 200
                )
                for index in range(4)
            ),
            PastGame(VI_ID, "TOP", "SOLO", is_win=False),
        ],
    )


def start_timeline(point_name: str, four_minute_point_name: str | None = None) -> JsonValue:
    start_point = RIFT_MAP.points[point_name]
    four_minute_point = (
        RIFT_MAP.points[four_minute_point_name] if four_minute_point_name is not None else None
    )
    return jungle_start_timeline(
        start_point.x_position,
        start_point.y_position,
        (four_minute_point.x_position, four_minute_point.y_position)
        if four_minute_point is not None
        else None,
    )


def test_history_keeps_each_games_id_team_and_participant() -> None:
    games = recent_games_of(vi_history(), puuid_of(VI_SEED))
    assert [(game.game_id, game.team_id, game.participant_id) for game in games[:2]] == [
        (FIRST_GAME_ID, 100, 1),
        (FIRST_GAME_ID + 1, 200, 1),
    ]


def test_a_likely_junglers_jungle_games_have_their_timelines_read() -> None:
    assert jungle_timeline_paths(recent_games_of(vi_history(), puuid_of(VI_SEED))) == [
        f"/lol-match-history/v1/game-timelines/{FIRST_GAME_ID + index}" for index in range(4)
    ]


def test_a_player_who_rarely_jungles_has_no_timelines_read() -> None:
    assert jungle_timeline_paths(recent_games_of(zed_history(), puuid_of(ZED))) == []
    one_jungle_game = [
        RecentGame(VI_ID, "JUNGLE", is_win=True, game_id=FIRST_GAME_ID),
        *(
            RecentGame(VI_ID, "TOP", is_win=True, game_id=FIRST_GAME_ID + index)
            for index in range(1, 5)
        ),
    ]
    assert jungle_timeline_paths(one_jungle_game) == []


def test_past_games_timelines_are_shared_between_the_engine_and_the_recorder() -> None:
    assert "/lol-match-history/v1/game-timelines/" in PLAYER_LOOKUP_PATH_PREFIXES


def test_the_intel_says_where_a_jungler_usually_starts() -> None:
    record = PlayerRecord(
        ranked=None,
        recent_games=(RecentGame(VI_ID, "JUNGLE", is_win=True),),
        jungle_starts=JungleStarts(blue_count=1, red_count=3),
    )
    intel = player_intel(record, VI_ID, "JUNGLE", team="CHAOS")
    assert (
        intel.jungle_start_side,
        intel.jungle_start_half,
        intel.jungle_start_count,
        intel.jungle_start_games,
    ) == ("red", "top", 3, 4)
    assert player_intel(record, VI_ID, "JUNGLE").jungle_start_half is None
    assert (
        player_intel(
            dataclasses.replace(record, jungle_starts=None), VI_ID, "JUNGLE"
        ).jungle_start_side
        is None
    )


async def test_a_junglers_usual_start_is_read_from_their_past_games() -> None:
    requested_paths: list[str] = []
    async with (
        serve(fake_league_client(requested_paths, set(), with_vi_jungling=True)) as client_url,
        aiohttp.ClientSession() as session,
    ):
        client = LeagueClient(session, client_url, password="", tls_context=None)
        records = await load_player_records(client, {}, pause_seconds=0.0)
    vi_record = records[("CHAOS", "vi")]
    assert vi_record.record.jungle_starts == JungleStarts(blue_count=1, red_count=3)
    assert records[("CHAOS", "zed")].record.jungle_starts is None
    timeline_paths = [path for path in requested_paths if "game-timelines" in path]
    assert len(timeline_paths) == 4


def test_the_intel_says_where_a_jungler_usually_is_at_four_minutes() -> None:
    record = PlayerRecord(
        ranked=None,
        recent_games=(RecentGame(VI_ID, "JUNGLE", is_win=True),),
        four_minute_sides=FourMinuteSides(blue_count=3, red_count=0, mid_count=1),
    )
    intel = player_intel(record, VI_ID, "JUNGLE", team="CHAOS")
    assert (intel.four_minute_half, intel.four_minute_count, intel.four_minute_games) == (
        "bot",
        3,
        4,
    )
    assert player_intel(record, VI_ID, "JUNGLE").four_minute_half is None
    assert (
        player_intel(
            dataclasses.replace(record, four_minute_sides=None), VI_ID, "JUNGLE", team="CHAOS"
        ).four_minute_half
        is None
    )


async def test_where_a_jungler_usually_is_at_four_minutes_is_read_from_the_same_games() -> None:
    requested_paths: list[str] = []
    async with (
        serve(fake_league_client(requested_paths, set(), with_vi_jungling=True)) as client_url,
        aiohttp.ClientSession() as session,
    ):
        client = LeagueClient(session, client_url, password="", tls_context=None)
        records = await load_player_records(client, {}, pause_seconds=0.0)
    vi_record = records[("CHAOS", "vi")].record
    assert vi_record.four_minute_sides == FourMinuteSides(blue_count=3, red_count=0, mid_count=1)
    assert records[("CHAOS", "zed")].record.four_minute_sides is None
    # No more questions than for the starts: the same four timelines.
    assert len([path for path in requested_paths if "game-timelines" in path]) == 4


def fake_league_client(
    requested_paths: list[str], failing_puuids: set[str], *, with_vi_jungling: bool = False
) -> web.Application:
    application = web.Application()
    history_by_puuid = {
        puuid_of(seed): match_history(puuid_of(seed), []) for seed in DEFAULT_PLAYERS
    }
    history_by_puuid[puuid_of(ZED)] = zed_history()
    if with_vi_jungling:
        history_by_puuid[puuid_of(VI_SEED)] = vi_history()

    async def session_route(_request: web.Request) -> web.Response:
        return web.json_response(gameflow_session())

    async def summary_route(_request: web.Request) -> web.Response:
        return web.json_response(champion_summary())

    async def ranked_route(request: web.Request) -> web.Response:
        requested_paths.append(request.path_qs)
        if request.match_info["puuid"] in failing_puuids:
            return web.json_response({"message": "busy"}, status=429)
        return web.json_response(ranked_stats("GOLD", "I", 75, 20, 18))

    async def history_route(request: web.Request) -> web.Response:
        requested_paths.append(request.path_qs)
        if request.match_info["puuid"] in failing_puuids:
            return web.json_response({"message": "busy"}, status=429)
        return web.json_response(history_by_puuid[request.match_info["puuid"]])

    application.router.add_get("/lol-gameflow/v1/session", session_route)
    application.router.add_get("/lol-game-data/assets/v1/champion-summary.json", summary_route)
    application.router.add_get("/lol-ranked/v1/ranked-stats/{puuid}", ranked_route)

    async def timeline_route(request: web.Request) -> web.Response:
        requested_paths.append(request.path_qs)
        game_id = int(request.match_info["game_id"])
        point_name = VI_START_POINTS.get(game_id)
        if point_name is None:
            return web.json_response({"message": "not found"}, status=404)
        return web.json_response(start_timeline(point_name, VI_FOUR_MINUTE_POINTS.get(game_id)))

    application.router.add_get("/lol-match-history/v1/products/lol/{puuid}/matches", history_route)
    application.router.add_get("/lol-match-history/v1/game-timelines/{game_id}", timeline_route)
    return application


async def test_each_player_is_looked_up_once_and_kept_for_the_next_game() -> None:
    requested_paths: list[str] = []
    cache: dict[str, PlayerRecord] = {}
    async with (
        serve(fake_league_client(requested_paths, set())) as client_url,
        aiohttp.ClientSession() as session,
    ):
        client = LeagueClient(session, client_url, password="", tls_context=None)
        first = await load_player_records(client, cache, pause_seconds=0.0)
        paths_after_the_first = list(requested_paths)
        second = await load_player_records(client, cache, pause_seconds=0.0)
    # Two questions per player, ten players, and nothing more the second time.
    assert len(paths_after_the_first) == 20
    assert requested_paths == paths_after_the_first
    assert f"/lol-ranked/v1/ranked-stats/{puuid_of(ZED)}" in requested_paths
    assert (
        f"/lol-match-history/v1/products/lol/{puuid_of(ZED)}/matches?begIndex=0&endIndex=20"
        in requested_paths
    )
    zed = first.get(("CHAOS", "zed"))
    assert zed is not None
    assert zed.champion_id == ZED_ID
    assert len(zed.record.recent_games) == 5
    assert second == first


async def test_a_player_the_client_will_not_answer_for_is_left_out_and_asked_again_later() -> None:
    requested_paths: list[str] = []
    cache: dict[str, PlayerRecord] = {}
    async with (
        serve(fake_league_client(requested_paths, {puuid_of(ZED)})) as client_url,
        aiohttp.ClientSession() as session,
    ):
        client = LeagueClient(session, client_url, password="", tls_context=None)
        records = await load_player_records(client, cache, pause_seconds=0.0)
    assert ("CHAOS", "zed") not in records
    assert ("CHAOS", "caitlyn") in records
    assert puuid_of(ZED) not in cache


async def test_without_a_game_in_the_client_there_are_no_records() -> None:
    application = web.Application()

    async def lobby_route(_request: web.Request) -> web.Response:
        return web.json_response({"phase": "Lobby", "gameData": {"teamOne": [], "teamTwo": []}})

    application.router.add_get("/lol-gameflow/v1/session", lobby_route)
    async with serve(application) as client_url, aiohttp.ClientSession() as session:
        client = LeagueClient(session, client_url, password="", tls_context=None)
        assert await load_player_records(client, {}, pause_seconds=0.0) == {}


async def test_cards_carry_each_players_intel_once_the_records_are_known() -> None:
    requested_paths: list[str] = []
    async with (
        serve(fake_league_client(requested_paths, set())) as client_url,
        aiohttp.ClientSession() as session,
    ):
        client = LeagueClient(session, client_url, password="", tls_context=None)
        records = await load_player_records(client, {}, pause_seconds=0.0)
    players = tuple(
        dataclasses.replace(seed, position="TOP") if seed is ZED else seed
        for seed in DEFAULT_PLAYERS
    )
    state = compute_overlay_state(all_game_data(600.0, players=players), player_records=records)
    zed_card = next(card for card in state.players if card.champion_name == "Zed")
    assert zed_card.intel is not None
    assert zed_card.intel.champion_game_count == 3
    assert zed_card.intel.is_off_role is True
    assert all(card.intel is not None for card in state.players)
    assert compute_overlay_state(all_game_data(600.0)).players[0].intel is None


async def test_the_engine_looks_the_players_up_when_a_game_starts() -> None:
    requested_paths: list[str] = []
    client_application = fake_league_client(requested_paths, set())
    game_application = web.Application()
    answers: list[JsonValue] = [all_game_data(60.0 + index) for index in range(80)]

    async def answer(_request: web.Request) -> web.Response:
        return web.json_response(answers.pop(0) if answers else None)

    game_application.router.add_get("/liveclientdata/allgamedata", answer)
    async with (
        serve(game_application) as game_url,
        serve(client_application) as client_url,
        aiohttp.ClientSession() as session,
    ):

        async def connect_to_client() -> LeagueClient | None:
            return LeagueClient(session, client_url, password="", tls_context=None)

        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            connect_to_client=connect_to_client,
            intel_pause_seconds=0.0,
        )
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        for _ in range(200):
            if any(card.intel for card in engine.current_state.players):
                break
            await asyncio.sleep(0.01)
        stop_requested.set()
        await engine_task
    zed_card = next(card for card in engine.current_state.players if card.champion_name == "Zed")
    assert zed_card.intel is not None
    assert zed_card.intel.champion_game_count == 3
    assert len(requested_paths) == 20


async def test_running_and_recording_together_ask_about_each_player_once(tmp_path: Path) -> None:
    requested_paths: list[str] = []
    client_application = fake_league_client(requested_paths, set())
    game_application = web.Application()
    answers: list[JsonValue] = [all_game_data(60.0 + index * 0.1) for index in range(400)]

    async def answer(_request: web.Request) -> web.Response:
        return web.json_response(answers.pop(0) if answers else None)

    game_application.router.add_get("/liveclientdata/allgamedata", answer)
    overlay_urls: list[str] = []
    async with (
        serve(game_application) as game_url,
        serve(client_application) as client_url,
        aiohttp.ClientSession() as session,
    ):
        settings = Settings(
            game_api_base_url=game_url,
            league_client_base_url=client_url,
            recordings_directory=tmp_path / "recordings",
            download_patch_stats=False,
            patch_data_directory=tmp_path / "patch-data",
            poll_interval_seconds=0.01,
            player_lookup_pause_seconds=0.0,
        )
        stop_requested = asyncio.Event()
        overlay_task = asyncio.create_task(
            run_overlay(settings, stop_requested, overlay_urls.append)
        )
        state = OverlayState(is_game_running=False)
        for _ in range(300):
            await asyncio.sleep(0.01)
            if not overlay_urls:
                continue
            async with session.get(overlay_urls[0] + "state") as response:
                state = OverlayState.model_validate(await response.json())
            if len(requested_paths) >= 20 and any(card.intel for card in state.players):
                break
        # Give the slower of the two time to ask, had it not shared the answers.
        await asyncio.sleep(0.3)
        stop_requested.set()
        await overlay_task
    assert any(card.intel for card in state.players)
    assert len(requested_paths) == 20
    assert len(set(requested_paths)) == 20
