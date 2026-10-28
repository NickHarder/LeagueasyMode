"""The last game kept for its case after the game, and `/case` serving it (phase 11.3)."""

import asyncio
import dataclasses
from pathlib import Path
from typing import Final

import aiohttp
from aiohttp import web
from pydantic import JsonValue

from client_game_payloads import details_payload, summary_payload, timeline_payload
from data_dragon_fixtures import fixture_patch_stats
from game_payloads import ACTIVE_PLAYER_INDEX, DEFAULT_PLAYERS, all_game_data
from leagueasymode.cli import after_the_game
from leagueasymode.data_dragon import PatchStats
from leagueasymode.engine import OverlayEngine
from leagueasymode.game_api import GameApiClient
from leagueasymode.game_state import GameSnapshot
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH
from leagueasymode.recorder import GAME_DETAILS_PATH_TEMPLATE, TIMELINE_PATH_TEMPLATE
from leagueasymode.roast.last_game import LastGameRoast, last_game_roast, roast_path_beside
from leagueasymode.roast.rules import LaneRules
from leagueasymode.scoring import read_recorded_game
from local_servers import serve, unused_local_url
from recorded_games import game_details, game_timeline, players_at, write_scored_recording

CLIENT_GAME_ID: Final = 9000000202
# Ahri, the active player of the built games, is their third participant.
AHRI_ID: Final = 3
LEBLANC_ID: Final = 8


def snapshot_as(game_name: str, tag_line: str) -> GameSnapshot:
    """An answer of the game's API whose active player has this Riot ID."""
    players = tuple(
        dataclasses.replace(seed, riot_id_game_name=game_name, riot_id_tag_line=tag_line)
        if index == ACTIVE_PLAYER_INDEX
        else seed
        for index, seed in enumerate(DEFAULT_PLAYERS)
    )
    return GameSnapshot.model_validate(all_game_data(600.0, players=players))


def client_resources(details: JsonValue) -> dict[str, JsonValue]:
    return {
        CHAMPION_SUMMARY_PATH: summary_payload(),
        GAME_DETAILS_PATH_TEMPLATE.format(game_id=CLIENT_GAME_ID): details,
        TIMELINE_PATH_TEMPLATE.format(game_id=CLIENT_GAME_ID): timeline_payload(),
    }


async def no_patch_stats(_game_version: str | None) -> PatchStats | None:
    return fixture_patch_stats()


def test_the_player_here_is_found_by_their_riot_id() -> None:
    roast = last_game_roast(
        client_resources(details_payload()),
        snapshot_as("PLAYER 8", "test"),
        lane_rules=LaneRules(),
    )
    assert roast is not None
    assert roast.defendant_participant_id == LEBLANC_ID
    assert len(roast.game.players) == 10


def test_without_names_the_player_here_is_found_by_team_and_champion(tmp_path: Path) -> None:
    recording = write_scored_recording(
        tmp_path, players_at(are_positions_given=True), timeline=game_timeline()
    )
    game = read_recorded_game(recording)
    roast = last_game_roast(
        game.client_resources, game.minute_snapshots[-1], lane_rules=LaneRules()
    )
    assert roast is not None
    assert roast.defendant_participant_id == AHRI_ID
    assert [player.champion for player in roast.game.players][AHRI_ID - 1] == "Ahri"


def test_a_game_not_of_two_teams_of_five_has_no_case() -> None:
    details = details_payload()
    assert isinstance(details, dict)
    participants = details["participants"]
    assert isinstance(participants, list)
    arena_details: dict[str, JsonValue] = {**details, "participants": participants[:8]}
    assert (
        last_game_roast(
            client_resources(arena_details), snapshot_as("Player 3", "TEST"), lane_rules=LaneRules()
        )
        is None
    )


def test_without_details_or_an_answer_there_is_no_case() -> None:
    resources = client_resources(details_payload())
    without_details = {
        path: payload for path, payload in resources.items() if "/games/" not in path
    }
    snapshot = snapshot_as("Player 3", "TEST")
    assert last_game_roast(without_details, snapshot, lane_rules=LaneRules()) is None
    assert last_game_roast(resources, None, lane_rules=LaneRules()) is None


def test_the_roast_is_kept_beside_the_summary() -> None:
    assert roast_path_beside(Path("history") / "last-game.json") == (
        Path("history") / "last-game-roast.json"
    )


async def test_after_a_game_its_roast_is_kept_and_a_game_without_one_forgets_it(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "history" / "last-game.json"
    history_path = tmp_path / "history" / "accuracy-history.jsonl"
    first = tmp_path / "first"
    first.mkdir()
    recording = write_scored_recording(
        first, players_at(are_positions_given=True), timeline=game_timeline()
    )
    await after_the_game(
        recording, no_patch_stats, history_path=history_path, summary_path=summary_path
    )
    roast_path = roast_path_beside(summary_path)
    kept = LastGameRoast.model_validate_json(roast_path.read_text())
    assert kept.defendant_participant_id == AHRI_ID
    # The file names no one: champions only.
    assert "#" not in roast_path.read_text()

    # A recording with eight players stands in for Arena: no case, and the last one is forgotten.
    trimmed = tmp_path / "third"
    trimmed.mkdir()
    details = game_details({seed.champion_name: seed.position for seed in DEFAULT_PLAYERS})
    assert isinstance(details, dict)
    participants = details["participants"]
    assert isinstance(participants, list)
    eight_players = write_scored_recording(
        trimmed,
        players_at(are_positions_given=True),
        timeline=game_timeline(),
        details={**details, "participants": participants[:8]},
    )
    await after_the_game(
        eight_players, no_patch_stats, history_path=history_path, summary_path=summary_path
    )
    assert not roast_path.exists()


async def test_the_case_is_served_for_any_target(tmp_path: Path) -> None:
    summary_path = tmp_path / "last-game.json"
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        application = create_overlay_application(engine, summary_path=summary_path)
        async with serve(application) as overlay_url:
            async with session.get(overlay_url + "/case") as no_game_response:
                no_game_status = no_game_response.status
            roast = last_game_roast(
                client_resources(details_payload()),
                snapshot_as("Player 3", "TEST"),
                lane_rules=LaneRules(),
            )
            assert roast is not None
            roast_path_beside(summary_path).write_text(roast.model_dump_json())
            async with session.get(overlay_url + "/case?spice=9") as refused_response:
                refused_status = refused_response.status
            async with session.get(
                overlay_url + "/case?target=player:8&spice=3&take=1"
            ) as case_response:
                case_status = case_response.status
                case = await case_response.json()
    assert no_game_status == 404
    assert refused_status == 400
    assert case_status == 200
    assert (case["target"], case["spice"], case["take"]) == ("player:8", 3, 1)
    assert len(case["players"]) == 10
    assert case["risk_warning"]


def a_game_in_progress() -> web.Application:
    """The game's API, answering that a game is on at every ask."""
    application = web.Application()

    async def answer(_request: web.Request) -> web.Response:
        return web.json_response(all_game_data(600.0))

    application.router.add_get("/liveclientdata/allgamedata", answer)
    return application


def keep_a_case_beside(summary_path: Path) -> None:
    roast = last_game_roast(
        client_resources(details_payload()),
        snapshot_as("Player 3", "TEST"),
        lane_rules=LaneRules(),
    )
    assert roast is not None
    roast_path_beside(summary_path).write_text(roast.model_dump_json())


async def test_the_shortcut_copies_the_closing_line_the_window_shows(tmp_path: Path) -> None:
    summary_path = tmp_path / "last-game.json"
    keep_a_case_beside(summary_path)
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        application = create_overlay_application(engine, summary_path=summary_path)
        async with serve(application) as overlay_url:
            async with session.get(overlay_url + "/closing-line") as default_response:
                default_line = await default_response.json()
            async with session.get(overlay_url + "/case") as default_case_response:
                default_case = await default_case_response.json()
            async with session.get(
                overlay_url + "/case?target=player:8&spice=3&take=1"
            ) as shown_response:
                shown = await shown_response.json()
            async with session.get(overlay_url + "/closing-line") as copied_response:
                copied = await copied_response.json()
            async with session.get(overlay_url + "/closing-line?next=1") as next_response:
                next_line = await next_response.json()
            async with session.get(
                overlay_url + "/case?target=player:8&spice=3&take=2"
            ) as next_case_response:
                next_case = await next_case_response.json()
            async with session.get(overlay_url + "/closing-line?next=x") as refused_response:
                refused_status = refused_response.status
    # Before the window picks anything, the whole team at Salty, as the window opens on.
    assert default_line == {"text": default_case["closing_line"], "take": 0}
    assert copied == {"text": shown["closing_line"], "take": 1}
    assert next_line == {"text": next_case["closing_line"], "take": 2}
    assert refused_status == 400


async def test_without_a_case_there_is_nothing_to_copy(tmp_path: Path) -> None:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        application = create_overlay_application(engine, summary_path=tmp_path / "last-game.json")
        async with (
            serve(application) as overlay_url,
            session.get(overlay_url + "/closing-line") as response,
        ):
            assert response.status == 404


async def test_during_a_game_the_last_games_line_is_not_copied(tmp_path: Path) -> None:
    summary_path = tmp_path / "last-game.json"
    keep_a_case_beside(summary_path)
    async with serve(a_game_in_progress()) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None), poll_interval_seconds=0.01
        )
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        for _ in range(200):
            if engine.current_state.is_game_running:
                break
            await asyncio.sleep(0.01)
        try:
            application = create_overlay_application(engine, summary_path=summary_path)
            async with (
                serve(application) as overlay_url,
                session.get(overlay_url + "/closing-line") as response,
            ):
                status = response.status
                message = (await response.json())["message"]
        finally:
            stop_requested.set()
            await engine_task
    assert status == 409
    assert "during a game" in message
