"""Objective timers, from the kill feed: when the next dragon or Elder Dragon spawns.

These restate what the game announces (a dragon's death, the rift changing for the soul) with the
spawn rules applied; nothing is estimated. The rules are the long-standing ones in `DragonRules`;
each is checked against the owner's recorded games as they come in.
"""

from dataclasses import dataclass
from typing import Final, Literal

from leagueasymode.game_state import GameEvent, GameSnapshot
from leagueasymode.overlay_state import DragonTimer

DRAGON_KILL_EVENT: Final = "DragonKill"
ELDER_DRAGON_TYPE: Final = "Elder"
DEFAULT_MAP_TERRAIN: Final = "Default"


@dataclass(frozen=True)
class DragonRules:
    """When dragons spawn, in game seconds."""

    first_spawn_seconds: float = 300.0
    respawn_seconds: float = 300.0
    elder_respawn_seconds: float = 360.0
    dragons_for_soul: int = 4


DRAGON_RULES: Final = DragonRules()


def dragon_timer(snapshot: GameSnapshot, rules: DragonRules = DRAGON_RULES) -> DragonTimer:
    """Return the next dragon's timer, and each team's dragons, as of a snapshot.

    Args:
        snapshot: The game's state.
        rules: The spawn rules.

    Returns:
        The timer of the next dragon, which is the Elder Dragon once a team has the soul.
    """
    game_time_seconds = snapshot.game_data.game_time_seconds
    dragon_kills = sorted(
        (event for event in snapshot.event_list.events if event.event_name == DRAGON_KILL_EVENT),
        key=lambda event: event.event_time_seconds,
    )
    ally_team = snapshot.ally_team()
    elemental_kill_teams = [
        snapshot.team_of(event.killer_name)
        for event in dragon_kills
        if event.dragon_type != ELDER_DRAGON_TYPE
    ]
    ally_dragon_count = sum(1 for team in elemental_kill_teams if team == ally_team)
    enemy_dragon_count = sum(
        1 for team in elemental_kill_teams if team is not None and team != ally_team
    )
    soul_holder = _soul_holder(ally_dragon_count, enemy_dragon_count, rules)
    spawns_at_seconds = _next_spawn_seconds(dragon_kills, soul_holder is not None, rules)
    terrain = snapshot.game_data.map_terrain
    return DragonTimer(
        objective="elder_dragon" if soul_holder is not None else "dragon",
        status=_status(game_time_seconds, spawns_at_seconds, has_any_kill=bool(dragon_kills)),
        spawns_at_game_time_seconds=spawns_at_seconds,
        ally_dragon_count=ally_dragon_count,
        enemy_dragon_count=enemy_dragon_count,
        soul_type=terrain if terrain and terrain != DEFAULT_MAP_TERRAIN else None,
        soul_holder=soul_holder,
    )


def _soul_holder(
    ally_dragon_count: int, enemy_dragon_count: int, rules: DragonRules
) -> Literal["ally", "enemy"] | None:
    """Return which side has the dragon soul, if either.

    Args:
        ally_dragon_count: Elemental dragons the player's team has taken.
        enemy_dragon_count: Elemental dragons the other team has taken.
        rules: How many dragons make the soul.

    Returns:
        "ally", "enemy", or None.
    """
    if ally_dragon_count >= rules.dragons_for_soul:
        return "ally"
    if enemy_dragon_count >= rules.dragons_for_soul:
        return "enemy"
    return None


def _next_spawn_seconds(
    dragon_kills: list[GameEvent], has_soul_been_taken: bool, rules: DragonRules
) -> float:
    """Return when the next dragon spawns.

    Args:
        dragon_kills: Every dragon kill so far, oldest first.
        has_soul_been_taken: Whether a team has the soul, after which only the Elder spawns.
        rules: The spawn rules.

    Returns:
        The game time of the next spawn, in seconds.
    """
    if not dragon_kills:
        return rules.first_spawn_seconds
    last_kill_seconds = dragon_kills[-1].event_time_seconds
    if has_soul_been_taken:
        return last_kill_seconds + rules.elder_respawn_seconds
    return last_kill_seconds + rules.respawn_seconds


def _status(
    game_time_seconds: float, spawns_at_seconds: float, has_any_kill: bool
) -> Literal["not_spawned", "respawning", "alive"]:
    """Return whether the next dragon is waiting to spawn for the first time, respawning or up.

    Args:
        game_time_seconds: The game's clock.
        spawns_at_seconds: When the next dragon spawns.
        has_any_kill: Whether any dragon has died yet.

    Returns:
        The dragon's status.
    """
    if game_time_seconds >= spawns_at_seconds:
        return "alive"
    return "respawning" if has_any_kill else "not_spawned"
