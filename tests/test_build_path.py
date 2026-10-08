import dataclasses
from typing import Final

import pytest
from pydantic import JsonValue

from data_dragon_fixtures import fixture_patch_stats
from game_payloads import DEFAULT_PLAYERS, PlayerSeed, all_game_data, player_payload
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import ScoreboardPlayer
from leagueasymode.inference.build_path import next_item
from leagueasymode.inference.callouts import CalloutTracker
from leagueasymode.overlay_state import GoldEstimate, NextItemEstimate, OverlayState, PlayerCard
from leagueasymode.patch_data import CatalogItem, ItemCatalog
from leagueasymode.player_intel import PlayerRecord, RecentGame

LONG_SWORD: Final = (1036, "Long Sword", 350)
BF_SWORD: Final = (1038, "B. F. Sword", 1300)
SERRATED_DIRK: Final = (3134, "Serrated Dirk", 1100)
INFINITY_EDGE: Final = (3031, "Infinity Edge", 3400)
CATALOG: Final = ItemCatalog(
    [
        CatalogItem.model_validate(item)
        for item in list[dict[str, JsonValue]](
            [
                {"id": 1036, "name": "Long Sword", "priceTotal": 350, "to": [3031, 3134]},
                {"id": 1038, "name": "B. F. Sword", "priceTotal": 1300, "to": [3031]},
                {"id": 1018, "name": "Cloak of Agility", "priceTotal": 600, "to": [3031]},
                {"id": 1052, "name": "Amplifying Tome", "priceTotal": 400, "to": [3089]},
                {"id": 1058, "name": "Needlessly Large Rod", "priceTotal": 1200, "to": [3089]},
                {"id": 1029, "name": "Cloth Armor", "priceTotal": 300, "to": [3068]},
                {
                    "id": 3134,
                    "name": "Serrated Dirk",
                    "priceTotal": 1100,
                    "from": [1036, 1036],
                    "to": [3142],
                },
                {
                    "id": 3031,
                    "name": "Infinity Edge",
                    "priceTotal": 3400,
                    "from": [1038, 1018, 1036],
                    "categories": ["Damage", "CriticalStrike"],
                },
                {
                    "id": 3089,
                    "name": "Rabadon's Deathcap",
                    "priceTotal": 3600,
                    "from": [1058, 1058, 1052],
                    "categories": ["SpellDamage"],
                },
                {
                    "id": 3142,
                    "name": "Youmuu's Ghostblade",
                    "priceTotal": 2800,
                    "from": [3134, 1036],
                    "categories": ["Damage", "ArmorPenetration", "NonbootsMovement"],
                },
                {
                    "id": 3068,
                    "name": "Sunfire Aegis",
                    "priceTotal": 2700,
                    "from": [1029],
                    "categories": ["Health", "Armor"],
                },
                {
                    "id": 3172,
                    "name": "Kalista's Spear",
                    "priceTotal": 3000,
                    "from": [1036],
                    "requiredChampion": "Kalista",
                    "categories": ["Damage", "CriticalStrike", "AttackSpeed"],
                },
                {
                    "id": 1001,
                    "name": "Boots",
                    "priceTotal": 300,
                    "to": [3006],
                    "categories": ["Boots"],
                },
                {
                    "id": 3006,
                    "name": "Berserker's Greaves",
                    "priceTotal": 2100,
                    "from": [1001],
                    "categories": ["Boots", "AttackSpeed"],
                },
            ]
        )
    ]
)


def player(champion_name: str, *items: tuple[int, str, int]) -> ScoreboardPlayer:
    seed = next(seed for seed in DEFAULT_PLAYERS if seed.champion_name == champion_name)
    return ScoreboardPlayer.model_validate(player_payload(dataclasses.replace(seed, items=items)))


def record_of(champion_id: int, item_ids_per_game: list[tuple[int, ...]]) -> PlayerRecord:
    return PlayerRecord(
        ranked=None,
        recent_games=tuple(
            RecentGame(champion_id=champion_id, position="MIDDLE", is_win=True, item_ids=item_ids)
            for item_ids in item_ids_per_game
        ),
    )


def predicted(
    champion_name: str,
    *items: tuple[int, str, int],
    record: PlayerRecord | None = None,
    champion_id: int = 0,
    gold: GoldEstimate | None = None,
    game_time_seconds: float = 900.0,
) -> NextItemEstimate:
    estimate = next_item(
        player(champion_name, *items),
        CATALOG,
        fixture_patch_stats(),
        record=record,
        champion_id=champion_id,
        gold=gold,
        game_time_seconds=game_time_seconds,
    )
    assert estimate is not None
    return estimate


def test_held_components_point_to_the_item_they_build_into() -> None:
    caitlyn = predicted("Caitlyn", BF_SWORD)
    assert (caitlyn.item_name, caitlyn.remaining_gold) == ("Infinity Edge", 2100)
    assert caitlyn.likelihood > 0.5


def test_with_no_components_the_champions_class_decides() -> None:
    assert predicted("Lux").item_name == "Rabadon's Deathcap"
    assert predicted("Zed").item_name == "Youmuu's Ghostblade"


def test_what_the_player_built_on_the_champion_lately_weighs_in() -> None:
    zed_id = 238
    history = record_of(zed_id, [(3031, 1001), (3031,), (3031, 3068)])
    zed = predicted("Zed", record=history, champion_id=zed_id)
    assert zed.item_name == "Infinity Edge"


def test_a_finished_item_already_owned_is_not_next() -> None:
    assert predicted("Caitlyn", INFINITY_EDGE).item_name != "Infinity Edge"


def test_an_item_for_another_champion_or_boots_are_never_next() -> None:
    caitlyn = predicted("Caitlyn", LONG_SWORD)
    assert caitlyn.item_name not in {"Kalista's Spear", "Berserker's Greaves"}


def test_a_component_inside_a_component_counts_once() -> None:
    assert predicted("Zed", SERRATED_DIRK, LONG_SWORD).remaining_gold == 2800 - 1100 - 350
    # Three Long Swords: two go into the Serrated Dirk Youmuu's needs, one into Youmuu's itself.
    assert predicted("Zed", LONG_SWORD, LONG_SWORD, LONG_SWORD).remaining_gold == 2800 - 1050


def test_the_chance_to_afford_it_comes_from_their_gold() -> None:
    # 2100 to go with 2100 in hand, give or take: an even chance, and affordable now.
    in_hand = GoldEstimate(source="estimate", total_gold=6100, unspent_gold=2100, band_gold=256)
    caitlyn = predicted("Caitlyn", BF_SWORD, gold=in_hand, game_time_seconds=1290.0)
    assert caitlyn.chance_to_afford == pytest.approx(0.5, abs=0.01)
    assert caitlyn.affordable_at_game_time_seconds == 1290.0


def test_when_their_gold_reaches_it_follows_their_income_so_far() -> None:
    # 5600 earned past the start in 20 minutes since 1:30 is 4.67 a second; 1000 more to go.
    short = GoldEstimate(source="estimate", total_gold=6100, unspent_gold=1100, band_gold=256)
    caitlyn = predicted("Caitlyn", BF_SWORD, gold=short, game_time_seconds=1290.0)
    assert caitlyn.affordable_at_game_time_seconds == pytest.approx(1290.0 + 1000 / (5600 / 1200))


def test_without_gold_there_is_no_chance_or_time() -> None:
    caitlyn = predicted("Caitlyn", BF_SWORD)
    assert caitlyn.chance_to_afford is None
    assert caitlyn.affordable_at_game_time_seconds is None


def test_without_the_catalog_there_is_no_next_item() -> None:
    assert next_item(player("Zed"), None, fixture_patch_stats(), game_time_seconds=900.0) is None


def test_the_overlay_shows_each_players_next_item() -> None:
    players = tuple(
        dataclasses.replace(seed, items=(BF_SWORD,)) if seed.champion_name == "Caitlyn" else seed
        for seed in DEFAULT_PLAYERS
    )
    state = compute_overlay_state(
        all_game_data(900.0, players=players), CATALOG, patch_stats=fixture_patch_stats()
    )
    caitlyn = next(card for card in state.players if card.champion_name == "Caitlyn")
    assert caitlyn.next_item is not None
    assert caitlyn.next_item.item_name == "Infinity Edge"


def card_with_chance(chance_to_afford: float) -> PlayerCard:
    seed: PlayerSeed = DEFAULT_PLAYERS[8]
    return PlayerCard(
        champion_name=seed.champion_name,
        side="enemy",
        position=seed.position,
        level=11,
        is_dead=False,
        respawns_at_game_time_seconds=None,
        next_item=NextItemEstimate(
            item_id=3031,
            item_name="Infinity Edge",
            likelihood=0.8,
            remaining_gold=2100,
            chance_to_afford=chance_to_afford,
            affordable_at_game_time_seconds=1300.0,
        ),
    )


def state_with(game_time_seconds: float, card: PlayerCard) -> OverlayState:
    return OverlayState(is_game_running=True, game_time_seconds=game_time_seconds, players=[card])


def test_an_enemy_who_can_likely_afford_their_next_item_is_called_out_once() -> None:
    callouts = CalloutTracker()
    assert callouts.update(state_with(1290.0, card_with_chance(0.5))) == []
    made = callouts.update(state_with(1291.0, card_with_chance(0.8)))
    assert [(callout.kind, callout.text) for callout in made] == [
        ("item_soon", "Caitlyn can likely buy Infinity Edge")
    ]
    callouts.update(state_with(1292.0, card_with_chance(0.5)))
    again = callouts.update(state_with(1293.0, card_with_chance(0.8)))
    assert [callout.callout_id for callout in again] == [made[0].callout_id]
