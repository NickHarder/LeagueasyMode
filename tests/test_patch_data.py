import json
from pathlib import Path
from typing import Final

from pydantic import JsonValue, TypeAdapter

from leagueasymode.patch_data import ItemCatalog

ITEMS_FIXTURE: Final = Path(__file__).parent / "fixtures" / "client" / "items.json"


def fixture_items() -> JsonValue:
    return TypeAdapter[JsonValue](JsonValue).validate_json(ITEMS_FIXTURE.read_bytes())


def test_an_item_costs_its_total_price() -> None:
    catalog = ItemCatalog.from_client_items(fixture_items())
    assert catalog.total_price(3031) == 3400
    assert catalog.total_price(1036) == 350


def test_an_item_the_catalog_does_not_have_costs_nothing_known() -> None:
    assert ItemCatalog.from_client_items(fixture_items()).total_price(999999) is None


def test_a_finished_item_is_built_from_parts_and_into_nothing() -> None:
    catalog = ItemCatalog.from_client_items(fixture_items())
    assert catalog.is_finished(3031) is True


def test_parts_boots_starters_and_consumables_are_not_finished_items() -> None:
    catalog = ItemCatalog.from_client_items(fixture_items())
    for item_id in (1036, 1038, 3006, 1055, 2055, 999999):
        assert catalog.is_finished(item_id) is False, item_id


def test_an_item_has_its_name() -> None:
    assert ItemCatalog.from_client_items(fixture_items()).name_of(3031) == "Infinity Edge"


def test_an_answer_that_is_not_a_list_of_items_is_an_empty_catalog() -> None:
    assert ItemCatalog.from_client_items({"message": "not found"}).total_price(3031) is None
    assert (
        ItemCatalog.from_client_items(json.loads('[{"id": "not a number"}]')).total_price(3031)
        is None
    )
