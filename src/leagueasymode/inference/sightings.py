"""Sightings: when your team last saw each enemy, from what the game gives only in sight.

League's scoreboard is taken to show an enemy's creep score, items and level as they were when
your team last saw them, so that a change in any of them means your team sees them now. That is
the owner's idea (2026-10-28) and an assumption, to be checked on the first recording: if the
game gives them through the fog too, an enemy jungler farming out of sight reads as seen. A
champion kill is surer: an enemy who killed one of your team, or helped to, or whom your team
killed, was in their sight.

A sighting names no place. The minimap leaves out the likely place of an enemy seen in the last
few seconds (`positions.seen_for_seconds` in `tuning.json`): the player sees where they are on
League's own minimap.
"""

from dataclasses import dataclass
from typing import Final

from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.gold import (
    CHAMPION_KILL_EVENT,
    NEW_GAME_SLACK_SECONDS,
    PlayerKey,
    player_key,
)


@dataclass(frozen=True)
class _EnemyView:
    """What the scoreboard shows of an enemy, which changes only while they are in sight."""

    creep_score: int
    item_ids: tuple[int, ...]
    level: int


def kill_sightings(snapshot: GameSnapshot) -> dict[PlayerKey, float]:
    """Return when the feed's champion kills last put each enemy in your team's sight.

    Args:
        snapshot: The game's state.

    Returns:
        For each enemy seen so, the game time of the latest such kill.
    """
    ally_team = snapshot.ally_team()
    sightings: dict[PlayerKey, float] = {}
    for event in snapshot.event_list.events:
        if event.event_name != CHAMPION_KILL_EVENT:
            continue
        victim = snapshot.player_named(event.victim_name)
        killer = snapshot.player_named(event.killer_name)
        if victim is None:
            continue
        if victim.team == ally_team:
            takers = [killer, *(snapshot.player_named(name) for name in event.assister_names)]
            seen = [taker for taker in takers if taker is not None and taker.team != ally_team]
        else:
            seen = [victim] if killer is not None and killer.team == ally_team else []
        for enemy in seen:
            sightings[player_key(enemy)] = event.event_time_seconds
    return sightings


class SightingTracker:
    """Follows when your team last saw each enemy, one answer of the game's API after another.

    A game time well before the last one seen starts a new game, and the tracker over.
    """

    def __init__(self) -> None:
        """Start with no game."""
        self._views: Final[dict[PlayerKey, _EnemyView]] = {}
        self._last_seen: Final[dict[PlayerKey, float]] = {}
        self._last_game_time_seconds = 0.0

    def update(self, snapshot: GameSnapshot) -> dict[PlayerKey, float]:
        """Take in one answer of the game's API, and return when each enemy was last seen.

        Args:
            snapshot: The game's state.

        Returns:
            For each enemy seen this game, the game time of the latest sighting.
        """
        game_time_seconds = snapshot.game_data.game_time_seconds
        if game_time_seconds < self._last_game_time_seconds - NEW_GAME_SLACK_SECONDS:
            self._views.clear()
            self._last_seen.clear()
        self._last_game_time_seconds = game_time_seconds
        ally_team = snapshot.ally_team()
        for player in snapshot.players:
            if player.team == ally_team:
                continue
            key = player_key(player)
            view = _EnemyView(
                creep_score=player.scores.creep_score,
                item_ids=tuple(sorted(item.item_id for item in player.items)),
                level=player.level,
            )
            previous_view = self._views.get(key)
            self._views[key] = view
            # The first answer seen is no sighting, nor is shopping while dead, in base.
            if previous_view is not None and view != previous_view and not player.is_dead:
                self._last_seen[key] = game_time_seconds
        for killed_key, killed_at in kill_sightings(snapshot).items():
            self._last_seen[killed_key] = max(killed_at, self._last_seen.get(killed_key, killed_at))
        return dict(self._last_seen)
