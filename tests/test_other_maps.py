"""Off the Rift: on ARAM, its Mayhem or Arena, the Rift's own widgets are left out."""

from typing import Final

from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    all_game_data,
    dragon_kill_event,
    game_start_event,
    turret_killed_event,
)
from leagueasymode.engine import compute_overlay_state
from leagueasymode.inference.backs import BackTracker
from leagueasymode.inference.clues import ClueTracker
from leagueasymode.inference.experience import ExperienceTracker
from leagueasymode.inference.gold import GoldTracker
from leagueasymode.inference.jungle_path import JunglePathTracker
from leagueasymode.inference.wards import WardTracker
from leagueasymode.overlay_state import OverlayState

HOWLING_ABYSS: Final = 12
ENEMY_KILLER: Final = DEFAULT_PLAYERS[7].riot_id_game_name


def answer(map_number: int, game_mode: str) -> JsonValue:
    events = [
        game_start_event(),
        dragon_kill_event(1, 300.0, ENEMY_KILLER),
        turret_killed_event(2, 400.0, "Turret_T1_L_03_A", ENEMY_KILLER),
    ]
    return all_game_data(600.0, events, map_number=map_number, game_mode=game_mode)


def state_of(map_number: int, game_mode: str) -> OverlayState:
    return compute_overlay_state(
        answer(map_number, game_mode),
        clue_tracker=ClueTracker(),
        jungle_tracker=JunglePathTracker(),
        ward_tracker=WardTracker(),
        gold_tracker=GoldTracker(),
        experience_tracker=ExperienceTracker(),
        back_tracker=BackTracker(),
    )


def test_on_the_rift_its_widgets_are_there() -> None:
    state = state_of(11, "CLASSIC")
    assert state.is_summoners_rift
    assert state.dragon is not None
    assert state.objectives
    assert state.structures
    assert all(card.gold is not None for card in state.players)
    assert all(card.level_estimate is not None for card in state.players)
    assert state.team_gold is not None
    assert state.win_chance is not None


def test_off_the_rift_only_what_holds_everywhere_is_shown() -> None:
    state = state_of(HOWLING_ABYSS, "ARAM")
    assert state.is_game_running
    assert not state.is_summoners_rift
    assert state.dragon is None
    assert state.objectives == []
    assert state.buffs == []
    assert state.inhibitors == []
    assert state.structures == []
    assert state.jungle_paths == []
    assert state.camp_timers == []
    assert state.control_wards == []
    assert state.contests == []
    assert all(card.location is None for card in state.players)
    # The players hold on any map. The gold, experience and backs models and the win chance
    # were set for the Rift's income, levels and fountain, so they stay hidden until tuned on
    # ARAM's games (the owner, 2026-10-28: "yes hide them in aram until tuned").
    assert len(state.players) == len(DEFAULT_PLAYERS)
    assert all(card.gold is None for card in state.players)
    assert all(card.level_estimate is None for card in state.players)
    assert all(card.last_back is None for card in state.players)
    assert state.team_gold is None
    assert state.win_chance is None


def test_an_answer_without_a_map_counts_as_the_rift() -> None:
    assert state_of(0, "").is_summoners_rift
