"""The patch's game data, as the League client serves it: the item catalog.

The client serves the items of the patch it runs at `/lol-game-data/assets/v1/items.json`, so the
overlay's prices and recipes are always this patch's without any web service. The recorder keeps
that answer in every recording, and the replay serves it again.
"""

import logging
from typing import Final

from pydantic import Field, JsonValue, TypeAdapter, ValidationError

from leagueasymode.game_state import RiotPayloadModel

ITEMS_PATH: Final = "/lol-game-data/assets/v1/items.json"
BOOTS_CATEGORY: Final = "Boots"
CONSUMABLE_CATEGORY: Final = "Consumable"
# A finished item is a full recipe; below this total price, a "finished" item is a component
# upgrade or a quest step rather than a power spike worth showing. To be checked on real data.
FINISHED_ITEM_PRICE_FLOOR: Final = 2000

logger = logging.getLogger(__name__)


class CatalogItem(RiotPayloadModel):
    """One item of the patch: its price, its recipe, and what it is."""

    item_id: int = Field(alias="id")
    name: str
    price_total: int = Field(default=0, alias="priceTotal")
    builds_from: list[int] = Field(default_factory=list, alias="from")
    builds_into: list[int] = Field(default_factory=list, alias="to")
    categories: list[str] = Field(default_factory=list)


CATALOG_ITEMS_ADAPTER: Final = TypeAdapter[list[CatalogItem]](list[CatalogItem])


class ItemCatalog:
    """The patch's items by id."""

    def __init__(self, items: list[CatalogItem]) -> None:
        """Index the items by id.

        Args:
            items: The patch's items.
        """
        self.items_by_id: Final = {item.item_id: item for item in items}

    @classmethod
    def from_client_items(cls, payload: JsonValue) -> "ItemCatalog":
        """Return the catalog from the client's answer for `items.json`; empty if it cannot be read.

        Args:
            payload: The answer.

        Returns:
            The catalog.
        """
        try:
            items = CATALOG_ITEMS_ADAPTER.validate_python(payload)
        except ValidationError as error:
            logger.warning("could not read the item catalog (%d problems)", error.error_count())
            return cls([])
        return cls(items)

    def total_price(self, item_id: int) -> int | None:
        """Return an item's full price, its components included.

        Args:
            item_id: The item.

        Returns:
            The price in gold, or None for an item the catalog does not have.
        """
        item = self.items_by_id.get(item_id)
        return item.price_total if item is not None else None

    def name_of(self, item_id: int) -> str | None:
        """Return an item's name.

        Args:
            item_id: The item.

        Returns:
            The name, or None for an item the catalog does not have.
        """
        item = self.items_by_id.get(item_id)
        return item.name if item is not None else None

    def is_finished(self, item_id: int) -> bool:
        """Return whether an item is a finished one: a power spike when it is bought.

        Finished: built from parts and into nothing, not boots, not a consumable, and dear enough
        to be a full recipe.

        Args:
            item_id: The item.

        Returns:
            Whether it is finished; False for an item the catalog does not have.
        """
        item = self.items_by_id.get(item_id)
        if item is None:
            return False
        return (
            bool(item.builds_from)
            and not item.builds_into
            and BOOTS_CATEGORY not in item.categories
            and CONSUMABLE_CATEGORY not in item.categories
            and item.price_total >= FINISHED_ITEM_PRICE_FLOOR
        )
