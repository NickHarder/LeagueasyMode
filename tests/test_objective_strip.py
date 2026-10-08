from typing import Final

from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    all_game_data,
    baron_kill_event,
    dragon_kill_event,
    game_start_event,
    herald_kill_event,
    inhibitor_killed_event,
    inhibitor_respawned_event,
)
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.objectives import buff_timers, inhibitor_timers, objective_timers
from leagueasymode.overlay_state import ObjectiveTimer

ALLY_JUNGLER: Final = DEFAULT_PLAYERS[1].riot_id_game_name
ENEMY_JUNGLER: Final = DEFAULT_PLAYERS[6].riot_id_game_name
ALLY_TOP: Final = DEFAULT_PLAYERS[0].riot_id_game_name


def snapshot_at(game_time_seconds: float, *later_events: dict[str, JsonValue]) -> GameSnapshot:
    events: list[dict[str, JsonValue]] = [game_start_event(), *later_events]
    return GameSnapshot.model_validate(all_game_data(game_time_seconds, events))


def timer_of(snapshot: GameSnapshot, objective: str) -> ObjectiveTimer:
    return next(timer for timer in objective_timers(snapshot) if timer.objective == objective)


def test_baron_waits_for_its_first_spawn() -> None:
    baron = timer_of(snapshot_at(600.0), "baron")
    assert baron.status == "not_spawned"
    assert baron.spawns_at_game_time_seconds == 1200.0
    # Confirmed by the owner for this season, so shown without the provisional mark.
    assert baron.is_rule_verified is True


def test_a_taken_baron_respawns_six_minutes_later() -> None:
    baron = timer_of(snapshot_at(1600.0, baron_kill_event(1, 1500.0, ENEMY_JUNGLER)), "baron")
    assert baron.status == "respawning"
    assert baron.spawns_at_game_time_seconds == 1860.0


def test_the_herald_spawns_once_and_is_gone_once_taken() -> None:
    assert timer_of(snapshot_at(600.0), "rift_herald").spawns_at_game_time_seconds == 900.0
    assert timer_of(snapshot_at(901.0), "rift_herald").status == "alive"
    taken = timer_of(snapshot_at(1000.0, herald_kill_event(1, 950.0, ALLY_JUNGLER)), "rift_herald")
    assert taken.status == "gone"
    assert taken.spawns_at_game_time_seconds is None


def test_voidgrubs_leave_at_fourteen_forty_five_before_the_herald_comes() -> None:
    assert timer_of(snapshot_at(300.0), "voidgrubs").spawns_at_game_time_seconds == 480.0
    assert timer_of(snapshot_at(500.0), "voidgrubs").status == "alive"
    assert timer_of(snapshot_at(884.0), "voidgrubs").status == "alive"
    assert timer_of(snapshot_at(885.0), "voidgrubs").status == "gone"


def test_an_untaken_herald_leaves_at_nineteen_forty_five_before_baron_comes() -> None:
    assert timer_of(snapshot_at(1184.0), "rift_herald").status == "alive"
    assert timer_of(snapshot_at(1185.0), "rift_herald").status == "gone"


def test_every_spawn_rule_is_confirmed_for_this_season() -> None:
    timers = objective_timers(snapshot_at(600.0))
    assert [timer.is_rule_verified for timer in timers] == [True, True, True]


def test_the_baron_buff_lasts_three_minutes_for_the_team_that_took_it() -> None:
    buffs = buff_timers(snapshot_at(1600.0, baron_kill_event(1, 1500.0, ENEMY_JUNGLER)))
    assert [(buff.buff, buff.holder, buff.ends_at_game_time_seconds) for buff in buffs] == [
        ("baron", "enemy", 1680.0)
    ]


def test_an_expired_buff_is_not_shown() -> None:
    assert buff_timers(snapshot_at(1700.0, baron_kill_event(1, 1500.0, ENEMY_JUNGLER))) == []


def test_the_elder_buff_lasts_two_and_a_half_minutes() -> None:
    elder_kill = dragon_kill_event(1, 2100.0, ALLY_JUNGLER, "Elder")
    buffs = buff_timers(snapshot_at(2150.0, elder_kill))
    assert [(buff.buff, buff.holder, buff.ends_at_game_time_seconds) for buff in buffs] == [
        ("elder", "ally", 2250.0)
    ]


def test_a_destroyed_inhibitor_respawns_five_minutes_later() -> None:
    inhibitor_kill = inhibitor_killed_event(1, 1800.0, "Barracks_T2_L1", ALLY_TOP)
    inhibitors = inhibitor_timers(snapshot_at(1900.0, inhibitor_kill))
    assert [
        (timer.side, timer.lane, timer.respawns_at_game_time_seconds) for timer in inhibitors
    ] == [("enemy", "top", 2100.0)]


def test_a_respawned_inhibitor_is_no_longer_shown() -> None:
    inhibitor_kill = inhibitor_killed_event(1, 1800.0, "Barracks_T1_C1", ENEMY_JUNGLER)
    respawned = inhibitor_respawned_event(2, 2100.0, "Barracks_T1_C1")
    assert inhibitor_timers(snapshot_at(2101.0, inhibitor_kill, respawned)) == []
    assert inhibitor_timers(snapshot_at(2101.0, inhibitor_kill)) == []


def test_an_inhibitor_name_never_seen_is_ignored() -> None:
    odd_kill = inhibitor_killed_event(1, 1800.0, "Barracks_Something_New", ALLY_TOP)
    assert inhibitor_timers(snapshot_at(1900.0, odd_kill)) == []
