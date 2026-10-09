import dataclasses
from typing import Final

import pytest

from data_dragon_fixtures import fixture_patch_stats
from game_payloads import (
    DEFAULT_PLAYERS,
    all_game_data,
    dragon_kill_event,
    game_start_event,
    player_payload,
)
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import ScoreboardPlayer
from leagueasymode.inference.clues import ClueTracker
from leagueasymode.inference.contests import (
    CONTEST_RULES,
    contest_chance,
    kill_seconds,
    monster_health,
    reach_chance,
)
from leagueasymode.inference.fights import Fighter, fighter_damage
from leagueasymode.inference.rift_map import RIFT_MAP
from leagueasymode.overlay_state import CombatStats, PositionClue

MOVE_SPEED: Final = 380.0
CARRY: Final = Fighter(
    stats=CombatStats(
        source="estimate",
        health=2000.0,
        armor=80.0,
        magic_resist=50.0,
        attack_damage=250.0,
        ability_power=0.0,
        attack_speed=1.4,
        move_speed=380.0,
    ),
    level=16,
    magic_share=0.0,
)


def scoreboard_player(champion_name: str, *, is_dead: bool = False) -> ScoreboardPlayer:
    seed = next(seed for seed in DEFAULT_PLAYERS if seed.champion_name == champion_name)
    return ScoreboardPlayer.model_validate(
        player_payload(dataclasses.replace(seed, is_dead=is_dead, respawn_timer_seconds=10.0))
    )


def at_point(point_name: str, game_time_seconds: float) -> PositionClue:
    return PositionClue(
        kind="turret",
        game_time_seconds=game_time_seconds,
        place="somewhere",
        point_name=point_name,
        region=RIFT_MAP.points[point_name].region,
    )


def test_each_monsters_health_grows_with_the_game() -> None:
    rules = CONTEST_RULES
    # 2026: Baron 16,300 and 190 a minute from the start; Elder 11,500 and 290 a minute after
    # 25:00; a drake 3,625 and 375 a level of the champions' average, from 6 to 18.
    assert monster_health("baron", 1200.0, 9.0, rules) == 16_300 + 190 * 20
    assert monster_health("elder_dragon", 2100.0, 16.0, rules) == 11_500 + 290 * 10
    assert monster_health("dragon", 600.0, 9.0, rules) == 3625 + 375 * 8
    assert monster_health("dragon", 300.0, 3.0, rules) == 3625 + 375 * 5
    assert monster_health("dragon", 2000.0, 18.0, rules) == 3625 + 375 * 17


def test_the_kill_takes_the_monsters_health_over_your_damage_through_its_armor() -> None:
    rules = CONTEST_RULES
    physical, _ = fighter_damage(CARRY)
    through_armor = 100 / (100 + rules.baron_armor)
    health = monster_health("baron", 1500.0, 14.0, rules)
    seconds = kill_seconds(
        "baron", [CARRY] * 5, game_time_seconds=1500.0, mean_level=14.0, has_smite=False
    )
    assert seconds == pytest.approx(health / (5 * physical * through_armor))
    with_smite = kill_seconds(
        "baron", [CARRY] * 5, game_time_seconds=1500.0, mean_level=14.0, has_smite=True
    )
    assert with_smite == pytest.approx(
        (health - rules.upgraded_smite_damage) / (5 * physical * through_armor)
    )
    assert (
        kill_seconds("baron", [], game_time_seconds=1500.0, mean_level=14.0, has_smite=False)
        is None
    )


def reach(player: ScoreboardPlayer, clues: list[PositionClue], within_seconds: float) -> float:
    return reach_chance(
        player,
        "JUNGLE",
        clues,
        pit="baron_pit",
        move_speed=MOVE_SPEED,
        game_time_seconds=1300.0,
        within_seconds=within_seconds,
    )


def test_an_enemy_at_the_pit_can_contest_and_one_at_home_only_with_time() -> None:
    vi_jungler = scoreboard_player("Vi")
    assert reach(vi_jungler, [at_point("baron_pit", 1300.0)], 1.0) == pytest.approx(1.0)
    walk_seconds = RIFT_MAP.distance("chaos_fountain", "baron_pit") / MOVE_SPEED
    at_home = [at_point("chaos_fountain", 1300.0)]
    assert reach(vi_jungler, at_home, walk_seconds - 1.0) == 0.0
    assert reach(vi_jungler, at_home, walk_seconds + 1.0) == pytest.approx(1.0)


def test_a_dead_enemy_can_contest_only_after_their_respawn_and_the_walk() -> None:
    dead_vi = scoreboard_player("Vi", is_dead=True)
    # Dead with 10 seconds to their respawn.
    walk_seconds = RIFT_MAP.distance("chaos_fountain", "baron_pit") / MOVE_SPEED
    assert reach(dead_vi, [], 10.0 + walk_seconds - 1.0) == 0.0
    assert reach(dead_vi, [], 10.0 + walk_seconds + 1.0) == 1.0


def test_any_enemy_arriving_is_a_contest() -> None:
    assert contest_chance([0.5, 0.5]) == pytest.approx(0.75)
    assert contest_chance([]) == 0.0


def test_the_overlay_weighs_each_monster_up_or_soon() -> None:
    players = tuple(dataclasses.replace(seed, level=11) for seed in DEFAULT_PLAYERS)
    # 20:30: Baron is up since 20:00; the first dragon was taken at 5:30, the next is up at 10:30.
    events = [game_start_event(), dragon_kill_event(1, 330.0, "Jungle Diff")]
    state = compute_overlay_state(
        all_game_data(1230.0, events, players),
        patch_stats=fixture_patch_stats(),
        clue_tracker=ClueTracker(),
    )
    assert [contest.objective for contest in state.contests] == ["dragon", "baron"]
    baron = state.contests[1]
    assert baron.ally_fighters == 5
    assert baron.kill_seconds > 0
    assert 0.0 <= baron.contest_chance <= 1.0
    assert compute_overlay_state(all_game_data(1230.0, events, players)).contests == []


def test_a_monster_spawning_later_is_not_weighed_yet() -> None:
    state = compute_overlay_state(all_game_data(200.0), patch_stats=fixture_patch_stats())
    assert state.contests == []
    soon = compute_overlay_state(all_game_data(275.0), patch_stats=fixture_patch_stats())
    assert [contest.objective for contest in soon.contests] == ["dragon"]
