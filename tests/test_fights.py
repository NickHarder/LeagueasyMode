import dataclasses
import math
from typing import Final

import pytest

from data_dragon_fixtures import fixture_patch_stats
from game_payloads import DEFAULT_PLAYERS, all_game_data
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.fights import (
    FIGHT_RULES,
    Fighter,
    fight_estimate,
    fighter_damage,
    team_fight,
)
from leagueasymode.overlay_state import CombatStats

BRUISER_STATS: Final = CombatStats(
    source="estimate",
    health=1500.0,
    armor=60.0,
    magic_resist=40.0,
    attack_damage=120.0,
    ability_power=0.0,
    attack_speed=0.8,
    move_speed=345.0,
)
BRUISER: Final = Fighter(stats=BRUISER_STATS, level=9, magic_share=0.0)
# All of a pure mage's damage is magic: no attack damage, so no auto attacks.
MAGE: Final = Fighter(
    stats=BRUISER_STATS.model_copy(update={"attack_damage": 0.0, "ability_power": 200.0}),
    level=9,
    magic_share=1.0,
)


def test_two_teams_alike_are_even() -> None:
    fight = fight_estimate([BRUISER] * 5, [BRUISER] * 5)
    assert fight is not None
    assert fight.ally_chance == pytest.approx(0.5)
    assert (fight.ally_fighters, fight.enemy_fighters) == (5, 5)
    assert fight.ally_physical_share == fight.enemy_physical_share == pytest.approx(1.0)


def test_five_against_four_follows_the_square_law() -> None:
    # By Lanchester's square law, strength is damage times health: (5/4) squared.
    fight = fight_estimate([BRUISER] * 5, [BRUISER] * 4)
    assert fight is not None
    expected_log_odds = FIGHT_RULES.steepness * math.log((5 / 4) ** 2)
    assert fight.ally_chance == pytest.approx(1 / (1 + math.exp(-expected_log_odds)))
    assert 0.65 < fight.ally_chance < 0.8


def test_armor_counts_against_physical_damage_only() -> None:
    armored = Fighter(
        stats=BRUISER_STATS.model_copy(update={"armor": 150.0}), level=9, magic_share=0.0
    )
    against_physical = fight_estimate([armored] * 5, [BRUISER] * 5)
    against_magic = fight_estimate(
        [dataclasses.replace(MAGE, stats=MAGE.stats.model_copy(update={"armor": 150.0}))] * 5,
        [MAGE] * 5,
    )
    assert against_physical is not None
    assert against_magic is not None
    assert against_physical.ally_chance > 0.6
    assert against_magic.ally_chance == pytest.approx(0.5)
    assert against_magic.enemy_physical_share == pytest.approx(0.0)


def test_a_fighters_damage_splits_into_physical_and_magic() -> None:
    physical, magic = fighter_damage(BRUISER)
    rules = FIGHT_RULES
    abilities = rules.ability_damage_per_level * 9 + rules.attack_damage_ratio * 120.0
    assert physical == pytest.approx(120.0 * 0.8 + abilities)
    assert magic == 0.0
    mage_physical, mage_magic = fighter_damage(MAGE)
    assert mage_physical == 0.0
    assert mage_magic == pytest.approx(
        rules.ability_damage_per_level * 9 + rules.ability_power_ratio * 200.0
    )


def test_a_team_with_nobody_alive_loses_and_no_fight_has_no_chance() -> None:
    fight = fight_estimate([BRUISER], [])
    assert fight is not None
    assert fight.ally_chance == 1.0
    assert fight_estimate([], []) is None


def test_the_game_gives_the_fighters_alive() -> None:
    patch_stats = fixture_patch_stats()
    even = team_fight(GameSnapshot.model_validate(all_game_data(600.0)), patch_stats)
    players = tuple(
        dataclasses.replace(seed, is_dead=True, respawn_timer_seconds=20.0)
        if seed.champion_name in {"Zed", "Vi"}
        else seed
        for seed in DEFAULT_PLAYERS
    )
    ahead = team_fight(
        GameSnapshot.model_validate(all_game_data(600.0, players=players)), patch_stats
    )
    assert even is not None
    assert ahead is not None
    assert (ahead.ally_fighters, ahead.enemy_fighters) == (5, 3)
    assert ahead.ally_chance > even.ally_chance


def test_without_the_patchs_stats_there_is_no_fight_estimate() -> None:
    assert team_fight(GameSnapshot.model_validate(all_game_data(600.0)), None) is None


def test_a_champions_damage_type_comes_from_data_dragon() -> None:
    patch_stats = fixture_patch_stats()
    # Data Dragon rates Ahri 3 for attack and 8 for magic, Zed 9 and 1.
    assert patch_stats.champion_magic_share("Ahri", "Ahri") == pytest.approx(8 / 11)
    assert patch_stats.champion_magic_share("Zed", "Zed") == pytest.approx(1 / 10)
    assert patch_stats.champion_magic_share("Nobody", "Nobody") is None


def test_the_overlay_shows_an_even_fight_now() -> None:
    state = compute_overlay_state(all_game_data(600.0), patch_stats=fixture_patch_stats())
    assert state.fight is not None
    assert 0.0 < state.fight.ally_chance < 1.0
    assert compute_overlay_state(all_game_data(600.0)).fight is None
