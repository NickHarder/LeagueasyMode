from typing import Final

from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    all_game_data,
    dragon_kill_event,
    game_start_event,
)
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.objectives import dragon_timer

ALLY_JUNGLER: Final = DEFAULT_PLAYERS[1].riot_id_game_name
ENEMY_JUNGLER: Final = DEFAULT_PLAYERS[6].riot_id_game_name


def snapshot_at(
    game_time_seconds: float, *dragon_kills: tuple[float, str, str], terrain: str = "Default"
) -> GameSnapshot:
    kill_events = [
        dragon_kill_event(index + 1, kill_time, killer, dragon_type)
        for index, (kill_time, killer, dragon_type) in enumerate(dragon_kills)
    ]
    events: list[dict[str, JsonValue]] = [game_start_event(), *kill_events]
    return GameSnapshot.model_validate(
        all_game_data(game_time_seconds, events, map_terrain=terrain)
    )


def test_the_first_dragon_spawns_at_five_minutes() -> None:
    timer = dragon_timer(snapshot_at(120.0))
    assert timer.objective == "dragon"
    assert timer.status == "not_spawned"
    assert timer.spawns_at_game_time_seconds == 300.0


def test_a_dragon_nobody_has_taken_is_alive_after_its_spawn() -> None:
    assert dragon_timer(snapshot_at(301.0)).status == "alive"


def test_a_taken_dragon_respawns_five_minutes_later() -> None:
    timer = dragon_timer(snapshot_at(500.0, (410.5, ALLY_JUNGLER, "Fire")))
    assert timer.status == "respawning"
    assert timer.spawns_at_game_time_seconds == 710.5
    assert timer.ally_dragon_count == 1
    assert timer.enemy_dragon_count == 0


def test_each_team_counts_its_own_dragons() -> None:
    timer = dragon_timer(
        snapshot_at(
            1500.0,
            (400.0, ALLY_JUNGLER, "Fire"),
            (800.0, ENEMY_JUNGLER, "Water"),
            (1200.0, ENEMY_JUNGLER, "Water"),
        )
    )
    assert (timer.ally_dragon_count, timer.enemy_dragon_count) == (1, 2)


def test_the_soul_type_shows_once_the_rift_has_changed() -> None:
    assert dragon_timer(snapshot_at(500.0)).soul_type is None
    assert dragon_timer(snapshot_at(1300.0, terrain="Infernal")).soul_type == "Infernal"


def test_the_fourth_dragon_of_a_team_brings_the_elder_six_minutes_later() -> None:
    kills = [(400.0 + 400 * index, ENEMY_JUNGLER, "Water") for index in range(4)]
    timer = dragon_timer(snapshot_at(1700.0, *kills))
    assert timer.objective == "elder_dragon"
    assert timer.soul_holder == "enemy"
    assert timer.spawns_at_game_time_seconds == 1600.0 + 360.0


def test_a_taken_elder_respawns_six_minutes_later() -> None:
    kills = [(400.0 + 400 * index, ALLY_JUNGLER, "Earth") for index in range(4)]
    elder_kill = (2100.0, ENEMY_JUNGLER, "Elder")
    timer = dragon_timer(snapshot_at(2200.0, *kills, elder_kill))
    assert timer.objective == "elder_dragon"
    assert timer.status == "respawning"
    assert timer.spawns_at_game_time_seconds == 2460.0
    assert timer.ally_dragon_count == 4
    assert timer.soul_holder == "ally"


def test_a_killer_not_on_the_scoreboard_still_starts_the_timer() -> None:
    timer = dragon_timer(snapshot_at(500.0, (420.0, "SRU_Dragon_Fire6.1.1", "Fire")))
    assert timer.spawns_at_game_time_seconds == 720.0
    assert (timer.ally_dragon_count, timer.enemy_dragon_count) == (0, 0)


def test_a_riot_id_as_killer_name_is_matched_too() -> None:
    timer = dragon_timer(snapshot_at(500.0, (420.0, DEFAULT_PLAYERS[6].riot_id, "Fire")))
    assert timer.enemy_dragon_count == 1


def test_unknown_fields_in_the_answer_are_ignored() -> None:
    payload = all_game_data(10.0)
    assert isinstance(payload, dict)
    payload["somethingRiotAddedLater"] = {"nested": True}
    snapshot = GameSnapshot.model_validate(payload)
    assert snapshot.game_data.game_time_seconds == 10.0


def test_the_stolen_flag_is_read_from_riots_text() -> None:
    event = dragon_kill_event(1, 300.0, ENEMY_JUNGLER)
    event["Stolen"] = "True"
    snapshot = GameSnapshot.model_validate(all_game_data(310.0, [game_start_event(), event]))
    assert snapshot.event_list.events[1].is_stolen is True
