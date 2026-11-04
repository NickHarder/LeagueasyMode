"""Estimates not yet shown to beat chance on real games stay hidden unless the player asks.

An independent review, 2026-11-04, scored the owner's recorded Rift games: the win chance scored
a Brier of 0.404 and 0.249 (a coin flip scores 0.250), the likeliest region was right 25% to 38%
of the time, and the jungle path was some 4,500 units off. Until each beats its baseline on 20 or
more Rift games (`leagueasymode thresholds`), the overlay does not show them; "Show experimental
estimates" on the settings page brings them back.
"""

import asyncio
from typing import Final

import aiohttp
from aiohttp import web
from pydantic import JsonValue

from game_payloads import all_game_data, game_start_event
from leagueasymode.engine import OverlayEngine, compute_overlay_state, without_unproven_estimates
from leagueasymode.game_api import GameApiClient
from leagueasymode.inference.clues import ClueTracker
from leagueasymode.inference.jungle_path import JunglePathTracker
from leagueasymode.overlay_state import (
    JunglePath,
    OverlayPreferences,
    OverlayState,
    PositionEstimate,
    RegionChance,
)
from local_servers import serve

LIKELY_BOT: Final = PositionEstimate(
    regions=[
        RegionChance(
            region="bot_lane", label="bot lane", chance=0.6, x_position=12000.0, y_position=2000.0
        )
    ],
    away_chance=0.7,
    unseen_seconds=30.0,
    reach_top_seconds=40.0,
    reach_mid_seconds=20.0,
    reach_bot_seconds=0.0,
)
VI_PATH: Final = JunglePath(
    champion_name="Vi",
    side="enemy",
    recent_camps=["their red"],
    last_cleared_at_game_time_seconds=120.0,
    next_camp="their krugs",
    next_camp_at_game_time_seconds=140.0,
)


def rift_state_with_every_estimate() -> OverlayState:
    state = compute_overlay_state(
        all_game_data(600.0, [game_start_event()]),
        clue_tracker=ClueTracker(),
        jungle_tracker=JunglePathTracker(),
    )
    return state.model_copy(
        update={
            "jungle_paths": [VI_PATH],
            "players": [
                card.model_copy(update={"location": LIKELY_BOT, "is_roaming": True})
                for card in state.players
            ],
        }
    )


def test_the_win_chance_likely_places_and_jungle_paths_are_left_out() -> None:
    state = rift_state_with_every_estimate()
    assert state.win_chance is not None
    hidden = without_unproven_estimates(state)
    assert hidden.win_chance is None
    assert hidden.jungle_paths == []
    assert all(card.location is None for card in hidden.players)
    assert not any(card.is_roaming for card in hidden.players)
    # What has real support stays: the players, their items and levels.
    assert [card.champion_name for card in hidden.players] == [
        card.champion_name for card in state.players
    ]


def test_by_default_they_are_hidden() -> None:
    assert not OverlayPreferences().show_experimental_estimates


def scripted_game(answers: list[JsonValue]) -> web.Application:
    application = web.Application()

    async def answer(_request: web.Request) -> web.Response:
        if answers:
            return web.json_response(answers.pop(0))
        return web.json_response({"errorCode": "RESOURCE_NOT_FOUND"}, status=404)

    application.router.add_get("/liveclientdata/allgamedata", answer)
    return application


async def first_running_state(preferences: OverlayPreferences) -> OverlayState:
    answers: list[JsonValue] = [all_game_data(600.0 + index) for index in range(50)]
    async with serve(scripted_game(answers)) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            preferences=preferences,
        )
        updates = engine.subscribe()
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        state = await asyncio.wait_for(updates.get(), timeout=5)
        while not state.is_game_running:
            state = await asyncio.wait_for(updates.get(), timeout=5)
        stop_requested.set()
        await engine_task
    return state


async def test_the_engine_publishes_them_only_with_the_setting_on() -> None:
    hidden = await first_running_state(OverlayPreferences())
    shown = await first_running_state(OverlayPreferences(show_experimental_estimates=True))
    assert hidden.win_chance is None
    assert shown.win_chance is not None
