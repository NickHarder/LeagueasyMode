import dataclasses
from pathlib import Path
from typing import Final

from pydantic import JsonValue, TypeAdapter

from game_payloads import DEFAULT_PLAYERS, all_game_data
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.players import player_cards, team_item_gold
from leagueasymode.patch_data import ItemCatalog

ITEMS_FIXTURE: Final = Path(__file__).parent / "fixtures" / "client" / "items.json"
INFINITY_EDGE: Final = (3031, "Infinity Edge", 1150)
LONG_SWORD: Final = (1036, "Long Sword", 350)
CONTROL_WARD: Final = (2055, "Control Ward", 75)


def catalog() -> ItemCatalog:
    return ItemCatalog.from_client_items(
        TypeAdapter[JsonValue](JsonValue).validate_json(ITEMS_FIXTURE.read_bytes())
    )


def snapshot_with_items(
    items_by_champion: dict[str, tuple[tuple[int, str, int], ...]],
) -> GameSnapshot:
    players = tuple(
        dataclasses.replace(seed, items=items_by_champion.get(seed.champion_name, ()))
        for seed in DEFAULT_PLAYERS
    )
    return GameSnapshot.model_validate(all_game_data(900.0, [], players=players))


def test_a_players_item_gold_is_the_total_price_of_their_items() -> None:
    snapshot = snapshot_with_items({"Caitlyn": (INFINITY_EDGE, LONG_SWORD, CONTROL_WARD)})
    caitlyn = next(
        card for card in player_cards(snapshot, catalog()) if card.champion_name == "Caitlyn"
    )
    assert caitlyn.item_gold == 3400 + 350 + 75
    assert caitlyn.finished_item_names == ["Infinity Edge"]


def test_without_the_catalog_item_gold_is_unknown() -> None:
    snapshot = snapshot_with_items({"Caitlyn": (INFINITY_EDGE,)})
    caitlyn = next(card for card in player_cards(snapshot, None) if card.champion_name == "Caitlyn")
    assert caitlyn.item_gold is None
    assert caitlyn.finished_item_names == []


def test_each_team_has_its_item_gold() -> None:
    snapshot = snapshot_with_items({"Caitlyn": (INFINITY_EDGE,), "Jinx": (LONG_SWORD, LONG_SWORD)})
    gold = team_item_gold(player_cards(snapshot, catalog()))
    assert gold is not None
    assert (gold.ally_item_gold, gold.enemy_item_gold) == (700, 3400)


def test_the_overlay_state_carries_item_facts_once_the_catalog_is_known() -> None:
    payload = all_game_data(
        900.0,
        [],
        players=tuple(
            dataclasses.replace(seed, items=(INFINITY_EDGE,))
            if seed.champion_name == "Zed"
            else seed
            for seed in DEFAULT_PLAYERS
        ),
    )
    with_catalog = compute_overlay_state(payload, catalog())
    without_catalog = compute_overlay_state(payload)
    assert with_catalog.team_item_gold is not None
    assert with_catalog.team_item_gold.enemy_item_gold == 3400
    assert without_catalog.team_item_gold is None
