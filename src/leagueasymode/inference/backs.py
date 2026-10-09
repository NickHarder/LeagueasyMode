"""Backs (estimator 6): when each player last went back to base, and when they return.

Buying needs the fountain, so a purchase made alive is a trip to base: not one at the game's
start, nor one while dead or just after respawning, which a death explains. Purchases within 30
seconds of a trip's first belong to it. The way back is a few seconds of shopping, then the walk
from the fountain to their lane's outer turret, or the middle of their jungle, along the map
(`rift_map.py`), at their move speed: the game's own for you, the estimate (`combat_stats.py`) for
the others, and 380 without the patch's stats.
"""

from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict

from leagueasymode.data_dragon import PatchStats
from leagueasymode.game_state import GameSnapshot, ScoreboardPlayer
from leagueasymode.inference.combat_stats import move_speed_of
from leagueasymode.inference.gold import (
    NEW_GAME_SLACK_SECONDS,
    PlayerKey,
    inventory_worth,
    player_key,
)
from leagueasymode.inference.rift_map import RIFT_MAP, fountain_of, role_point_of
from leagueasymode.inference.roles import assign_roles
from leagueasymode.overlay_state import BackEstimate
from leagueasymode.patch_data import ItemCatalog


class BackRules(BaseModel):
    """What counts as a trip to base, and how long the way back takes.

    `tuning.json`'s "backs".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Shopping before this is the game's start.
    starts_at_seconds: float = 90.0
    # Shopping this soon after respawning is the death's, not a trip's.
    respawn_shopping_seconds: float = 30.0
    # A purchase this soon after a trip's first belongs to it.
    same_trip_seconds: float = 30.0
    shopping_seconds: float = 5.0


BACK_RULES: Final = BackRules()


@dataclass
class _PlayerBacks:
    """What the tracker remembers of one player between answers."""

    inventory_worth: float
    was_dead: bool
    respawned_at_seconds: float | None = None
    last_back: BackEstimate | None = None


class BackTracker:
    """Follows every player's trips to base through a game, one answer after another.

    A game time well before the last one seen starts a new game, and the tracker over.
    """

    def __init__(self, rules: BackRules = BACK_RULES) -> None:
        """Start with no game.

        Args:
            rules: What counts as a trip, and how long the way back takes.
        """
        self.rules: Final = rules
        self._players: Final[dict[PlayerKey, _PlayerBacks]] = {}
        self._last_game_time_seconds = 0.0

    def update(
        self,
        snapshot: GameSnapshot,
        item_catalog: ItemCatalog | None,
        patch_stats: PatchStats | None = None,
    ) -> dict[PlayerKey, BackEstimate]:
        """Take in one answer of the game's API, and return each player's last trip to base.

        Args:
            snapshot: The game's state.
            item_catalog: The patch's items, for what an inventory is worth; None while unknown.
            patch_stats: The patch's stats, for move speeds; None while unknown.

        Returns:
            Each player's last trip, by key; a player not seen going back is left out.
        """
        game_time_seconds = snapshot.game_data.game_time_seconds
        if game_time_seconds < self._last_game_time_seconds - NEW_GAME_SLACK_SECONDS:
            self._players.clear()
        self._last_game_time_seconds = game_time_seconds
        for player, role_guess in zip(snapshot.players, assign_roles(snapshot), strict=True):
            key = player_key(player)
            worth = inventory_worth(player.items, item_catalog)
            state = self._players.setdefault(
                key, _PlayerBacks(inventory_worth=worth, was_dead=player.is_dead)
            )
            if state.was_dead and not player.is_dead:
                state.respawned_at_seconds = game_time_seconds
            if self._is_a_new_trip(state, player, worth, game_time_seconds):
                travel_seconds = RIFT_MAP.distance(
                    fountain_of(player.team), role_point_of(player.team, role_guess.role)
                ) / move_speed_of(snapshot, player, patch_stats)
                state.last_back = BackEstimate(
                    shopped_at_game_time_seconds=game_time_seconds,
                    returns_at_game_time_seconds=(
                        game_time_seconds + self.rules.shopping_seconds + travel_seconds
                    ),
                )
            state.inventory_worth = worth
            state.was_dead = player.is_dead
        return {
            key: state.last_back
            for key, state in self._players.items()
            if state.last_back is not None
        }

    def _is_a_new_trip(
        self, state: _PlayerBacks, player: ScoreboardPlayer, worth: float, game_time_seconds: float
    ) -> bool:
        """Return whether a player's inventory shows a new trip to base.

        Args:
            state: The player's state.
            player: The player now.
            worth: What their inventory cost now.
            game_time_seconds: The game's clock.

        Returns:
            Whether they bought something alive, past the start, not just after respawning, and
            not on a trip already counted.
        """
        rules = self.rules
        respawned_at_seconds = state.respawned_at_seconds
        last_back = state.last_back
        return (
            worth > state.inventory_worth
            and not player.is_dead
            and game_time_seconds >= rules.starts_at_seconds
            and (
                respawned_at_seconds is None
                or game_time_seconds - respawned_at_seconds > rules.respawn_shopping_seconds
            )
            and (
                last_back is None
                or game_time_seconds - last_back.shopped_at_game_time_seconds
                > rules.same_trip_seconds
            )
        )
