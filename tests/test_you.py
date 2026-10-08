import dataclasses
import json
from typing import Final

import pytest

from data_dragon_fixtures import FIXTURE_FILES, fixture_patch_stats
from game_payloads import DEFAULT_PLAYERS, PastGame, all_game_data, match_history
from leagueasymode.data_dragon import PatchStats
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.you import (
    YOU_RULES,
    YouTracker,
    defense_values,
    gold_per_point,
    usual_creep_score_per_minute,
)
from leagueasymode.overlay_state import CombatStats
from leagueasymode.patch_data import ItemCatalog
from leagueasymode.player_intel import PlayerRecord, recent_games_of

YOUR_STATS: Final = CombatStats(
    source="exact",
    health=1200.0,
    armor=50.0,
    magic_resist=40.0,
    attack_damage=90.0,
    ability_power=0.0,
    attack_speed=0.9,
    move_speed=345.0,
)
PUUID: Final = "your-puuid"


def test_against_physical_damage_armor_buys_the_most_health() -> None:
    values = defense_values(YOUR_STATS, enemy_physical_share=1.0)
    assert values[0].stat == "armor"
    # Effective health against physical damage alone is health times (100 + armor) / 100; a point
    # of armor adds health / 100, and 20 gold buys a point.
    armor = next(value for value in values if value.stat == "armor")
    assert armor.effective_health_per_hundred_gold == pytest.approx(1200.0 / 100 * 100 / 20)
    magic_resist = next(value for value in values if value.stat == "magic_resist")
    assert magic_resist.effective_health_per_hundred_gold == pytest.approx(0.0)


def test_against_magic_damage_magic_resist_does() -> None:
    values = defense_values(YOUR_STATS, enemy_physical_share=0.0)
    assert values[0].stat == "magic_resist"


def test_health_wins_once_resistances_are_high() -> None:
    tank = YOUR_STATS.model_copy(update={"armor": 250.0, "magic_resist": 250.0})
    assert defense_values(tank, enemy_physical_share=0.5)[0].stat == "health"


def patch_stats_with_basic_items() -> PatchStats:
    items = json.loads(FIXTURE_FILES.items)
    items["data"] |= {
        "1029": {"name": "Cloth Armor", "stats": {"FlatArmorMod": 15}},
        "1033": {"name": "Null-Magic Mantle", "stats": {"FlatSpellBlockMod": 25}},
        "1028": {"name": "Ruby Crystal", "stats": {"FlatHPPoolMod": 150}},
    }
    patch_stats = PatchStats.from_data_dragon(
        "16.19.1",
        dataclasses.replace(FIXTURE_FILES, items=json.dumps(items).encode()),
    )
    assert patch_stats is not None
    return patch_stats


def test_each_stats_price_comes_from_the_patchs_basic_items() -> None:
    catalog = ItemCatalog.from_client_items(
        [
            {"id": 1029, "name": "Cloth Armor", "priceTotal": 300},
            {"id": 1033, "name": "Null-Magic Mantle", "priceTotal": 450},
            {"id": 1028, "name": "Ruby Crystal", "priceTotal": 400},
        ]
    )
    patch_stats = patch_stats_with_basic_items()
    assert gold_per_point("armor", catalog, patch_stats) == pytest.approx(20.0)
    assert gold_per_point("magic_resist", catalog, patch_stats) == pytest.approx(18.0)
    assert gold_per_point("health", catalog, patch_stats) == pytest.approx(400 / 150)
    # Without them, the first guesses stand.
    assert gold_per_point("magic_resist", None, None) == YOU_RULES.gold_per_magic_resist


def snapshot_at(
    game_time_seconds: float, current_gold: float, *, is_dead: bool = False
) -> GameSnapshot:
    players = tuple(
        dataclasses.replace(seed, is_dead=is_dead, respawn_timer_seconds=10.0)
        if seed.champion_name == "Ahri"
        else seed
        for seed in DEFAULT_PLAYERS
    )
    return GameSnapshot.model_validate(
        all_game_data(game_time_seconds, players=players, current_gold=current_gold)
    )


def test_holding_gold_counts_from_when_it_passed_the_threshold() -> None:
    tracker = YouTracker()
    assert tracker.update(snapshot_at(590.0, 900.0)) is None
    assert tracker.update(snapshot_at(600.0, 1500.0)) == 0.0
    assert tracker.update(snapshot_at(700.0, 1600.0)) == 100.0
    # Spending ends it; a death does not start it.
    assert tracker.update(snapshot_at(710.0, 200.0)) is None
    assert tracker.update(snapshot_at(720.0, 1500.0, is_dead=True)) is None
    assert tracker.update(snapshot_at(730.0, 1500.0)) == 0.0


def test_a_new_game_starts_the_holding_over() -> None:
    tracker = YouTracker()
    tracker.update(snapshot_at(600.0, 1500.0))
    tracker.update(snapshot_at(700.0, 1500.0))
    assert tracker.update(snapshot_at(30.0, 1500.0)) == 0.0


def test_your_usual_creep_score_comes_from_your_recent_games() -> None:
    games = recent_games_of(
        match_history(
            PUUID,
            [
                PastGame(
                    103, "MIDDLE", "SOLO", is_win=True, duration_seconds=1800, creep_score=210
                ),
                PastGame(
                    103, "MIDDLE", "SOLO", is_win=False, duration_seconds=1200, creep_score=160
                ),
            ],
        ),
        PUUID,
    )
    record = PlayerRecord(ranked=None, recent_games=tuple(games))
    assert usual_creep_score_per_minute(record) == pytest.approx(370 / 50)
    assert usual_creep_score_per_minute(PlayerRecord(ranked=None, recent_games=())) is None


def test_the_overlay_shows_your_panel() -> None:
    players = tuple(
        dataclasses.replace(seed, creep_score=90) if seed.champion_name == "Ahri" else seed
        for seed in DEFAULT_PLAYERS
    )
    state = compute_overlay_state(
        all_game_data(600.0, players=players, current_gold=1500.0),
        patch_stats=fixture_patch_stats(),
        you_tracker=YouTracker(),
    )
    assert state.you is not None
    assert state.you.creep_score_per_minute == pytest.approx(9.0)
    assert state.you.usual_creep_score_per_minute is None
    assert (state.you.unspent_gold, state.you.holding_gold_seconds) == (1500, 0.0)
    assert {value.stat for value in state.you.defenses} == {"armor", "magic_resist", "health"}
    assert state.you.enemy_physical_share is not None
    assert 0.0 <= state.you.enemy_physical_share <= 1.0
    assert compute_overlay_state(all_game_data(600.0)).you is None
