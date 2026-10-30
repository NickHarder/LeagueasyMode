"""Off the Rift: on ARAM, its Mayhem or Arena, the Rift's own widgets are left out."""

from typing import Final

from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    all_game_data,
    dragon_kill_event,
    game_start_event,
    inhibitor_killed_event,
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
        inhibitor_killed_event(3, 500.0, "Barracks_T1_C1", ENEMY_KILLER),
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


def test_on_the_rift_an_inhibitors_timer_is_confirmed() -> None:
    (timer,) = state_of(11, "CLASSIC").inhibitors
    assert timer.is_rule_verified


def test_in_aram_an_inhibitor_comes_back_after_four_minutes_ten() -> None:
    # The owner, 2026-10-29: "no ARAM timers except inhib". The Rift's 5:00 stood in, unconfirmed,
    # until recorded ARAMs set it: in the owner's games of 2026-10-29 every one of 9 inhibitors
    # came back 250 seconds after it fell, to the second. Now confirmed.
    (timer,) = state_of(HOWLING_ABYSS, "ARAM").inhibitors
    assert timer.side == "ally"
    assert timer.lane == "mid"
    assert timer.respawns_at_game_time_seconds == 750.0
    assert timer.is_rule_verified


def test_on_another_map_the_rifts_inhibitor_time_stands_in_unconfirmed() -> None:
    (timer,) = state_of(30, "CHERRY").inhibitors
    assert timer.respawns_at_game_time_seconds == 800.0
    assert not timer.is_rule_verified


def test_an_answer_without_a_map_counts_as_the_rift() -> None:
    assert state_of(0, "").is_summoners_rift
