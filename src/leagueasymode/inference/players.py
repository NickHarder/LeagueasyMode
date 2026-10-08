"""The players, from the scoreboard: who is on which side, their level, and when the dead return.

Exact: the scoreboard gives every player's level and, while they are dead, the seconds until they
respawn. The numbers window follows from those alone, since a death to come cannot be known.
"""

from leagueasymode.game_state import GameSnapshot, ScoreboardPlayer
from leagueasymode.overlay_state import NumbersWindow, PlayerCard


def player_cards(snapshot: GameSnapshot) -> list[PlayerCard]:
    """Return a card for every player, the player's own team first, each team in scoreboard order.

    Args:
        snapshot: The game's state.

    Returns:
        The cards.
    """
    ally_team = snapshot.ally_team()
    game_time_seconds = snapshot.game_data.game_time_seconds
    allies = [player for player in snapshot.players if player.team == ally_team]
    enemies = [player for player in snapshot.players if player.team != ally_team]
    return [
        PlayerCard(
            champion_name=player.champion_name,
            side="ally" if player.team == ally_team else "enemy",
            position=player.position,
            level=player.level,
            is_dead=player.is_dead,
            respawns_at_game_time_seconds=_respawns_at_seconds(player, game_time_seconds),
        )
        for player in [*allies, *enemies]
    ]


def numbers_window(snapshot: GameSnapshot) -> NumbersWindow | None:
    """Return the window in which more enemies are dead than allies, or None when there is none.

    The window ends at the first respawn after which no more enemies than allies are dead.

    Args:
        snapshot: The game's state.

    Returns:
        The window, or None.
    """
    game_time_seconds = snapshot.game_data.game_time_seconds
    cards = player_cards(snapshot)
    respawn_times_by_side = {
        side: sorted(
            card.respawns_at_game_time_seconds
            for card in cards
            if card.side == side and card.respawns_at_game_time_seconds is not None
        )
        for side in ("ally", "enemy")
    }
    ally_dead_count = len(respawn_times_by_side["ally"])
    enemy_dead_count = len(respawn_times_by_side["enemy"])
    if enemy_dead_count <= ally_dead_count:
        return None
    respawn_instants = sorted(set(respawn_times_by_side["ally"] + respawn_times_by_side["enemy"]))
    ends_at_seconds = next(
        instant
        for instant in respawn_instants
        if _dead_after(respawn_times_by_side["enemy"], instant)
        <= _dead_after(respawn_times_by_side["ally"], instant)
    )
    return NumbersWindow(
        ally_dead_count=ally_dead_count,
        enemy_dead_count=enemy_dead_count,
        ends_at_game_time_seconds=max(ends_at_seconds, game_time_seconds),
    )


def _respawns_at_seconds(player: ScoreboardPlayer, game_time_seconds: float) -> float | None:
    """Return when a dead player respawns, or None for a living one.

    Args:
        player: The player.
        game_time_seconds: The game's clock.

    Returns:
        The game time of the respawn, or None.
    """
    if not player.is_dead:
        return None
    return game_time_seconds + max(player.respawn_timer_seconds, 0.0)


def _dead_after(respawn_times_seconds: list[float], instant_seconds: float) -> int:
    """Return how many of a side are still dead just after an instant.

    Args:
        respawn_times_seconds: When each dead player of the side respawns.
        instant_seconds: The instant.

    Returns:
        The count still dead.
    """
    return sum(1 for respawn_seconds in respawn_times_seconds if respawn_seconds > instant_seconds)
