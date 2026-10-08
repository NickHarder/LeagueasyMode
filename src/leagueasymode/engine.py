"""The engine: ask the game, read its answer, run the estimators, and tell the overlay."""

import asyncio
import logging
from typing import Final

from pydantic import JsonValue, ValidationError

from leagueasymode.game_api import GameApiClient
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.objectives import (
    buff_timers,
    dragon_timer,
    inhibitor_timers,
    objective_timers,
)
from leagueasymode.overlay_state import OverlayState

NOT_RUNNING: Final = OverlayState(is_game_running=False)

logger = logging.getLogger(__name__)


def compute_overlay_state(payload: JsonValue | None) -> OverlayState:
    """Return what the overlay shows for one answer of the game's API.

    Args:
        payload: The answer, or None when no game answered.

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
    return OverlayState(
        is_game_running=True,
        game_time_seconds=snapshot.game_data.game_time_seconds,
        dragon=dragon_timer(snapshot),
        objectives=objective_timers(snapshot),
        buffs=buff_timers(snapshot),
        inhibitors=inhibitor_timers(snapshot),
    )


class OverlayEngine:
    """Keeps the overlay's state current and passes each new state to its subscribers."""

    def __init__(self, game_api: GameApiClient, poll_interval_seconds: float) -> None:
        """Keep the game's API and how often to ask it.

        Args:
            game_api: The game's API.
            poll_interval_seconds: How often to ask.
        """
        self.game_api: Final = game_api
        self.poll_interval_seconds: Final = poll_interval_seconds
        self._current_state = NOT_RUNNING
        self._subscribers: Final[set[asyncio.Queue[OverlayState]]] = set()

    @property
    def current_state(self) -> OverlayState:
        """The latest state."""
        return self._current_state

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
            new_state = compute_overlay_state(await self.game_api.fetch_all_game_data())
            if new_state != self._current_state:
                self._current_state = new_state
                self._publish(new_state)
            try:
                await asyncio.wait_for(stop_requested.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue

    def _publish(self, new_state: OverlayState) -> None:
        """Put a state in every subscriber's queue, replacing one not yet read.

        Args:
            new_state: The state.
        """
        for updates in self._subscribers:
            if updates.full():
                updates.get_nowait()
            updates.put_nowait(new_state)
