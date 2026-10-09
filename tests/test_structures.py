"""Structures (phase 8.5): each side's turrets down per lane, and the inhibitors they open."""

from typing import Final

from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    all_game_data,
    game_start_event,
    inhibitor_killed_event,
    inhibitor_respawned_event,
    turret_killed_event,
)
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.callouts import CalloutTracker
from leagueasymode.inference.structures import lane_structures
from leagueasymode.overlay_state import LaneStructures, OverlayState

ALLY_TOP: Final = DEFAULT_PLAYERS[0].riot_id_game_name
ENEMY_JUNGLER: Final = DEFAULT_PLAYERS[6].riot_id_game_name


def snapshot_at(game_time_seconds: float, *later_events: dict[str, JsonValue]) -> GameSnapshot:
    events: list[dict[str, JsonValue]] = [game_start_event(), *later_events]
    return GameSnapshot.model_validate(all_game_data(game_time_seconds, events))


def enemy_turret(event_id: int, name: str) -> dict[str, JsonValue]:
    return turret_killed_event(event_id, 600.0 + 60 * event_id, name, ALLY_TOP)


def test_before_any_turret_falls_there_is_nothing_to_show() -> None:
    assert lane_structures(snapshot_at(300.0)) == []


def test_each_sides_turrets_down_are_counted_by_lane() -> None:
    structures = lane_structures(
        snapshot_at(
            1500.0,
            enemy_turret(1, "Turret_T2_L_03_A"),
            enemy_turret(2, "Turret_T2_L_02_A"),
            enemy_turret(3, "Turret_T2_R_03_A"),
            turret_killed_event(4, 900.0, "Turret_T1_C_05_A", ENEMY_JUNGLER),
        )
    )
    assert structures == [
        LaneStructures(side="ally", lane="mid", turrets_down=1, is_inhibitor_exposed=False),
        LaneStructures(side="enemy", lane="top", turrets_down=2, is_inhibitor_exposed=False),
        LaneStructures(side="enemy", lane="bot", turrets_down=1, is_inhibitor_exposed=False),
    ]


def test_the_inhibitor_turret_down_opens_the_inhibitor() -> None:
    structures = lane_structures(
        snapshot_at(
            1500.0,
            enemy_turret(1, "Turret_T2_C_05_A"),
            enemy_turret(2, "Turret_T2_C_04_A"),
            enemy_turret(3, "Turret_T2_C_03_A"),
        )
    )
    assert structures == [
        LaneStructures(side="enemy", lane="mid", turrets_down=3, is_inhibitor_exposed=True)
    ]


def test_an_inhibitor_down_is_not_open_until_it_is_back() -> None:
    turrets = [
        enemy_turret(1, "Turret_T2_R_03_A"),
        enemy_turret(2, "Turret_T2_R_02_A"),
        enemy_turret(3, "Turret_T2_R_01_A"),
    ]
    inhibitor_down = inhibitor_killed_event(4, 1400.0, "Barracks_T2_R1", ALLY_TOP)
    while_down = lane_structures(snapshot_at(1500.0, *turrets, inhibitor_down))
    back = lane_structures(
        snapshot_at(
            1701.0,
            *turrets,
            inhibitor_down,
            inhibitor_respawned_event(5, 1700.0, "Barracks_T2_R1"),
        )
    )
    assert [lane.is_inhibitor_exposed for lane in while_down] == [False]
    assert [lane.is_inhibitor_exposed for lane in back] == [True]


def test_nexus_turrets_and_names_never_seen_are_left_out() -> None:
    structures = lane_structures(
        snapshot_at(
            2000.0,
            enemy_turret(1, "Turret_T2_C_01_A"),
            enemy_turret(2, "Turret_T2_C_02_A"),
            enemy_turret(3, "Turret_Something_New"),
        )
    )
    assert structures == []


def test_a_turret_announced_twice_counts_once() -> None:
    structures = lane_structures(
        snapshot_at(
            1500.0, enemy_turret(1, "Turret_T2_L_03_A"), enemy_turret(2, "Turret_T2_L_03_A")
        )
    )
    assert [lane.turrets_down for lane in structures] == [1]


def opened_state(game_time_seconds: float, structures: list[LaneStructures]) -> OverlayState:
    return OverlayState(
        is_game_running=True, game_time_seconds=game_time_seconds, structures=structures
    )


def test_an_inhibitor_opening_is_called_out_once() -> None:
    tracker = CalloutTracker()
    closed = [LaneStructures(side="enemy", lane="bot", turrets_down=2, is_inhibitor_exposed=False)]
    opened = [LaneStructures(side="enemy", lane="bot", turrets_down=3, is_inhibitor_exposed=True)]
    assert tracker.update(opened_state(1500.0, closed)) == []
    callouts = tracker.update(opened_state(1501.0, opened))
    assert [(callout.kind, callout.text) for callout in callouts] == [
        ("inhibitor_open", "Enemy bot inhibitor is open")
    ]
    later = tracker.update(opened_state(1520.0, opened))
    assert later == []


def test_your_own_inhibitor_opening_is_called_out_too() -> None:
    tracker = CalloutTracker()
    opened = [LaneStructures(side="ally", lane="top", turrets_down=3, is_inhibitor_exposed=True)]
    tracker.update(opened_state(1500.0, []))
    callouts = tracker.update(opened_state(1501.0, opened))
    assert [callout.text for callout in callouts] == ["Your top inhibitor is open"]
