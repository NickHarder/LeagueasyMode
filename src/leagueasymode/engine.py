"""The engine: ask the game, read its answer, run the estimators, and tell the overlay."""

import asyncio
import logging
from typing import Final

from pydantic import JsonValue, ValidationError

from leagueasymode.game_api import GameApiClient
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.callouts import CalloutTracker
from leagueasymode.inference.objectives import (
    buff_timers,
    dragon_timer,
    inhibitor_timers,
    objective_timers,
)
from leagueasymode.inference.players import numbers_window, player_cards, team_item_gold
from leagueasymode.league_client import ClientConnector
from leagueasymode.overlay_state import OverlayState
from leagueasymode.patch_data import ITEMS_PATH, ItemCatalog

NOT_RUNNING: Final = OverlayState(is_game_running=False)

logger = logging.getLogger(__name__)


def compute_overlay_state(
    payload: JsonValue | None, item_catalog: ItemCatalog | None = None
) -> OverlayState:
    """Return what the overlay shows for one answer of the game's API.

    Args:
        payload: The answer, or None when no game answered.
        item_catalog: The patch's items, for the item facts; None while unknown.

    Returns:
        The overlay's state; no game running when there is no answer or it cannot be read.
    """
    if payload is None:
        return NOT_RUNNING
    try:
        snapshot = GameSnapshot.model_validate(payload)
    except ValidationError as error:
        logger.warning("could not read the game's answer (%d problems)", error.error_count())
        return NOT_RUNNING
    cards = player_cards(snapshot, item_catalog)
    return OverlayState(
        is_game_running=True,
        game_time_seconds=snapshot.game_data.game_time_seconds,
        dragon=dragon_timer(snapshot),
        objectives=objective_timers(snapshot),
        buffs=buff_timers(snapshot),
        inhibitors=inhibitor_timers(snapshot),
        players=cards,
        numbers_window=numbers_window(snapshot),
        team_item_gold=team_item_gold(cards),
    )


class OverlayEngine:
    """Keeps the overlay's state current and passes each new state to its subscribers.

    The state of one answer is worked out on its own (`compute_overlay_state`); the callouts, which
    depend on what changed since the last answer, are added by the engine, which remembers.
    """

    def __init__(
        self,
        game_api: GameApiClient,
        poll_interval_seconds: float,
        connect_to_client: ClientConnector | None = None,
    ) -> None:
        """Keep the game's API, how often to ask it, and how to reach the League client.

        Args:
            game_api: The game's API.
            poll_interval_seconds: How often to ask.
            connect_to_client: Finds the League client, for the patch's item catalog when a game
                starts; None to go without it.
        """
        self.game_api: Final = game_api
        self.poll_interval_seconds: Final = poll_interval_seconds
        self.connect_to_client: Final = connect_to_client
        self._item_catalog: ItemCatalog | None = None
        self._catalog_task: asyncio.Task[None] | None = None
        self._current_state = NOT_RUNNING
        self._callouts: Final = CalloutTracker()
        self._subscribers: Final[set[asyncio.Queue[OverlayState]]] = set()

    @property
    def current_state(self) -> OverlayState:
        """The latest state."""
        return self._current_state

    @property
    def item_catalog(self) -> ItemCatalog | None:
        """The patch's item catalog, once the League client has given it."""
        return self._item_catalog

    def subscribe(self) -> asyncio.Queue[OverlayState]:
        """Return a queue that receives each new state; a slow reader gets the latest only.

        Returns:
            The queue. Pass it to `unsubscribe` when done.
        """
        updates: asyncio.Queue[OverlayState] = asyncio.Queue(maxsize=1)
        self._subscribers.add(updates)
        return updates

    def unsubscribe(self, updates: asyncio.Queue[OverlayState]) -> None:
        """Stop sending states to a queue.

        Args:
            updates: A queue from `subscribe`.
        """
        self._subscribers.discard(updates)

    async def run(self, stop_requested: asyncio.Event) -> None:
        """Ask the game and publish the overlay's state until a stop is requested.

        Args:
            stop_requested: Set to stop.
        """
        while not stop_requested.is_set():
            answer_state = compute_overlay_state(
                await self.game_api.fetch_all_game_data(), self._item_catalog
            )
            if answer_state.is_game_running and not self._current_state.is_game_running:
                self._start_loading_the_catalog()
            new_state = answer_state.model_copy(
                update={"callouts": self._callouts.update(answer_state)}
            )
            if new_state != self._current_state:
                self._current_state = new_state
                self._publish(new_state)
            try:
                await asyncio.wait_for(stop_requested.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue

    def _start_loading_the_catalog(self) -> None:
        """Ask the League client for the item catalog in the background, once per game start."""
        is_loading = self._catalog_task is not None and not self._catalog_task.done()
        if self.connect_to_client is None or self._item_catalog is not None or is_loading:
            return
        self._catalog_task = asyncio.create_task(self._load_the_catalog(self.connect_to_client))

    async def _load_the_catalog(self, connect_to_client: ClientConnector) -> None:
        """Ask the League client for the item catalog, and keep it when it has items.

        Args:
            connect_to_client: Finds the League client.
        """
        client = await connect_to_client()
        if client is None:
            return
        catalog = ItemCatalog.from_client_items(await client.get_json(ITEMS_PATH))
        if catalog.items_by_id:
            self._item_catalog = catalog
            logger.info("loaded the item catalog: %d items", len(catalog.items_by_id))

    def _publish(self, new_state: OverlayState) -> None:
        """Put a state in every subscriber's queue, replacing one not yet read.

        Args:
            new_state: The state.
        """
        for updates in self._subscribers:
            if updates.full():
                updates.get_nowait()
            updates.put_nowait(new_state)
