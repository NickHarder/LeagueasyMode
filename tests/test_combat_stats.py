import dataclasses
from typing import Final

import pytest

from data_dragon_fixtures import fixture_patch_stats
from game_payloads import DEFAULT_PLAYERS, PlayerSeed, all_game_data, player_payload
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot, ScoreboardPlayer
from leagueasymode.inference.combat_stats import (
    ATTACK_SPEED_CAP,
    estimated_combat_stats,
    move_speed_after_caps,
    stat_growth,
)
from leagueasymode.inference.players import player_cards
from leagueasymode.overlay_state import CombatStats

CAITLYN: Final = DEFAULT_PLAYERS[8]
INFINITY_EDGE: Final = (3031, "Infinity Edge", 3400)
BERSERKERS_GREAVES: Final = (3006, "Berserker's Greaves", 1000)
PHANTOM_DANCER: Final = (3046, "Phantom Dancer", 2650)


def scoreboard_player(seed: PlayerSeed) -> ScoreboardPlayer:
    return ScoreboardPlayer.model_validate(player_payload(seed))


def estimate_for(seed: PlayerSeed) -> CombatStats:
    stats = estimated_combat_stats(scoreboard_player(seed), fixture_patch_stats())
    assert stats is not None
    return stats


def test_a_stat_grows_by_the_wikis_formula() -> None:
    assert stat_growth(1) == 0.0
    # At level 18 the growth is exactly 17 times the per-level value.
    assert stat_growth(18) == pytest.approx(17.0)
    # The wiki's worked example: 2.5% attack speed per level is 19.35% at level 10.
    assert 2.5 * stat_growth(10) == pytest.approx(19.35)


def test_a_level_one_champion_without_items_has_its_base_stats() -> None:
    ahri = estimate_for(dataclasses.replace(DEFAULT_PLAYERS[2], level=1))
    assert ahri == CombatStats(
        source="estimate",
        health=590.0,
        armor=21.0,
        magic_resist=30.0,
        attack_damage=53.0,
        ability_power=0.0,
        attack_speed=0.668,
        move_speed=330.0,
    )


def test_level_and_items_add_to_the_base_stats() -> None:
    caitlyn = estimate_for(
        dataclasses.replace(CAITLYN, level=9, items=(INFINITY_EDGE, BERSERKERS_GREAVES))
    )
    growth = 8 * (0.7025 + 0.0175 * 8)
    assert caitlyn.health == pytest.approx(580 + 107 * growth, abs=0.05)
    assert caitlyn.armor == pytest.approx(27 + 4.7 * growth, abs=0.05)
    assert caitlyn.magic_resist == pytest.approx(30 + 1.3 * growth, abs=0.05)
    assert caitlyn.attack_damage == pytest.approx(60 + 3.8 * growth + 65, abs=0.05)
    # Bonus attack speed adds up: 4% a level, grown, and the Greaves' 25%.
    assert caitlyn.attack_speed == pytest.approx(0.681 * (1 + 0.04 * growth + 0.25), abs=0.0005)
    assert caitlyn.move_speed == pytest.approx(325 + 45)


def test_two_of_one_item_count_twice() -> None:
    long_sword = (1036, "Long Sword", 350)
    jinx = estimate_for(dataclasses.replace(DEFAULT_PLAYERS[3], level=1, items=(long_sword,) * 2))
    assert jinx.attack_damage == pytest.approx(59 + 2 * 10)


def test_an_item_with_a_count_counts_that_many_times() -> None:
    payload = player_payload(dataclasses.replace(DEFAULT_PLAYERS[3], level=1))
    payload["items"] = [{"itemID": 1036, "count": 3, "displayName": "Long Sword", "price": 350}]
    stats = estimated_combat_stats(ScoreboardPlayer.model_validate(payload), fixture_patch_stats())
    assert stats is not None
    assert stats.attack_damage == pytest.approx(59 + 3 * 10)


def test_ability_power_comes_from_items() -> None:
    rabadons = (3089, "Rabadon's Deathcap", 3600)
    lux = estimate_for(dataclasses.replace(DEFAULT_PLAYERS[9], level=11, items=(rabadons,)))
    assert lux.ability_power == pytest.approx(130)


def test_percent_move_speed_multiplies_the_flat_total() -> None:
    boots = (1001, "Boots", 300)
    ahri = estimate_for(
        dataclasses.replace(DEFAULT_PLAYERS[2], level=1, items=(boots, PHANTOM_DANCER))
    )
    assert ahri.move_speed == pytest.approx((330 + 25) * 1.08)


def test_move_speed_slows_above_415_and_490_and_below_220() -> None:
    assert move_speed_after_caps(400.0) == pytest.approx(400.0)
    assert move_speed_after_caps(450.0) == pytest.approx(450.0 * 0.8 + 83)
    assert move_speed_after_caps(500.0) == pytest.approx(500.0 * 0.5 + 230)
    assert move_speed_after_caps(200.0) == pytest.approx(200.0 * 0.5 + 110)
    # The caps meet where they change.
    assert move_speed_after_caps(415.0) == pytest.approx(415.0)
    assert move_speed_after_caps(490.0) == pytest.approx(475.0)


def test_attack_speed_stops_at_the_cap() -> None:
    caitlyn = estimate_for(dataclasses.replace(CAITLYN, level=18, items=(PHANTOM_DANCER,) * 4))
    assert caitlyn.attack_speed == ATTACK_SPEED_CAP


def test_an_item_the_patch_lacks_adds_nothing() -> None:
    unknown_item = (999999, "Mystery", 100)
    zed = estimate_for(dataclasses.replace(DEFAULT_PLAYERS[7], level=1, items=(unknown_item,)))
    assert zed.attack_damage == pytest.approx(63)


def test_a_champion_the_patch_lacks_has_no_estimate() -> None:
    newcomer = dataclasses.replace(DEFAULT_PLAYERS[7], champion_name="Newcomer")
    assert estimated_combat_stats(scoreboard_player(newcomer), fixture_patch_stats()) is None


def test_the_player_on_this_machine_has_the_games_exact_stats() -> None:
    snapshot = GameSnapshot.model_validate(all_game_data(600.0))
    cards = player_cards(snapshot, patch_stats=fixture_patch_stats())
    own_card = next(card for card in cards if card.champion_name == "Ahri")
    # From the game's `championStats` for the active player, runes and all.
    assert own_card.combat_stats == CombatStats(
        source="exact",
        health=590.0,
        armor=21.0,
        magic_resist=30.0,
        attack_damage=53.0,
        ability_power=0.0,
        attack_speed=0.668,
        move_speed=330.0,
    )
    other_sources = {
        card.combat_stats.source for card in cards if card.combat_stats and card != own_card
    }
    assert other_sources == {"estimate"}


def test_without_the_patch_stats_only_the_player_on_this_machine_has_stats() -> None:
    snapshot = GameSnapshot.model_validate(all_game_data(600.0))
    cards = player_cards(snapshot)
    assert [card.champion_name for card in cards if card.combat_stats is not None] == ["Ahri"]


def test_the_overlay_state_carries_every_players_stats_once_the_patch_stats_are_known() -> None:
    state = compute_overlay_state(all_game_data(600.0), patch_stats=fixture_patch_stats())
    assert all(card.combat_stats is not None for card in state.players)
