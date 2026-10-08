"""Control wards (estimator 9): where each player's control ward likely is.

A control ward leaves the inventory when it is placed: a player's count of them dropping while
they are alive is a placement, at that moment. Where is the position estimate's (`positions.py`)
likeliest region at that moment, with its chance. A player can have one control ward down at a
time, so a new one replaces their last; a ward's destruction is never seen, so each stays shown
until its owner places another, or for a few minutes.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal

from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.gold import NEW_GAME_SLACK_SECONDS, PlayerKey, player_key
from leagueasymode.overlay_state import PositionEstimate, WardEstimate

CONTROL_WARD_ITEM_ID: Final = 2055
# A ward is shown at most this long after it was placed: one is often cleared within minutes.
WARD_SHOWN_SECONDS: Final = 300.0


@dataclass
class _PlayerWards:
    """What the tracker remembers of one player between answers."""

    control_ward_count: int
    last_ward: WardEstimate | None = None
    placed_at_seconds: list[float] = field(default_factory=list)


class WardTracker:
    """Follows every player's control wards through a game, one answer after another.

    A game time well before the last one seen starts a new game, and the tracker over.
    """

    def __init__(self) -> None:
        """Start with no game."""
        self._players: Final[dict[PlayerKey, _PlayerWards]] = {}
        self._last_game_time_seconds = 0.0

    def update(
        self, snapshot: GameSnapshot, locations: Mapping[PlayerKey, PositionEstimate]
    ) -> list[WardEstimate]:
        """Take in one answer of the game's API, and return the control wards likely down.

        Args:
            snapshot: The game's state.
            locations: Where each living player likely is now.

        Returns:
            Each player's latest control ward, newest first, those older than five minutes left
            out.
        """
        game_time_seconds = snapshot.game_data.game_time_seconds
        if game_time_seconds < self._last_game_time_seconds - NEW_GAME_SLACK_SECONDS:
            self._players.clear()
        self._last_game_time_seconds = game_time_seconds
        ally_team = snapshot.ally_team()
        for player in snapshot.players:
            key = player_key(player)
            count = sum(item.count for item in player.items if item.item_id == CONTROL_WARD_ITEM_ID)
            state = self._players.setdefault(key, _PlayerWards(control_ward_count=count))
            location = locations.get(key)
            if count < state.control_ward_count and not player.is_dead:
                state.placed_at_seconds.append(game_time_seconds)
                side: Literal["ally", "enemy"] = "ally" if player.team == ally_team else "enemy"
                if location is not None:
                    state.last_ward = _ward_at(
                        player.champion_name, side, location, game_time_seconds
                    )
            state.control_ward_count = count
        wards = [
            state.last_ward
            for state in self._players.values()
            if state.last_ward is not None
            and game_time_seconds - state.last_ward.placed_at_game_time_seconds
            <= WARD_SHOWN_SECONDS
        ]
        return sorted(wards, key=lambda ward: ward.placed_at_game_time_seconds, reverse=True)

    def placements(self) -> dict[PlayerKey, tuple[float, ...]]:
        """Return when each player was seen placing a control ward this game.

        Returns:
            The game times by key; a player who placed none is left out.
        """
        return {
            key: tuple(state.placed_at_seconds)
            for key, state in self._players.items()
            if state.placed_at_seconds
        }


def _ward_at(
    champion_name: str,
    side: Literal["ally", "enemy"],
    location: PositionEstimate,
    game_time_seconds: float,
) -> WardEstimate | None:
    """Return a ward placed now, where its owner likely is.

    Args:
        champion_name: The owner's champion.
        side: Their side.
        location: Where they likely are.
        game_time_seconds: The game's clock.

    Returns:
        The ward, or None when their position names no region.
    """
    if not location.regions:
        return None
    likeliest = location.regions[0]
    return WardEstimate(
        champion_name=champion_name,
        side=side,
        placed_at_game_time_seconds=game_time_seconds,
        region=likeliest.region,
        label=likeliest.label,
        chance=likeliest.chance,
    )
