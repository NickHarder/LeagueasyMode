"""The players, from the scoreboard: who is on which side, their level, and when the dead return.

Exact: the scoreboard gives every player's level and, while they are dead, the seconds until they
respawn. The numbers window follows from those alone, since a death to come cannot be known.
"""

from leagueasymode.game_state import GameSnapshot, ScoreboardPlayer
from leagueasymode.inference.roles import assign_roles
from leagueasymode.overlay_state import NumbersWindow, PlayerCard, TeamItemGold
from leagueasymode.patch_data import ItemCatalog


def player_cards(
    snapshot: GameSnapshot, item_catalog: ItemCatalog | None = None
) -> list[PlayerCard]:
    """Return a card for every player, the player's own team first, each team in scoreboard order.

    Args:
        snapshot: The game's state.
        item_catalog: The patch's items, for item gold and finished items; None while unknown.

    Returns:
        The cards.
    """
    ally_team = snapshot.ally_team()
    game_time_seconds = snapshot.game_data.game_time_seconds
    role_guesses = assign_roles(snapshot)
    indexed_players = list(enumerate(snapshot.players))
    allies = [(index, player) for index, player in indexed_players if player.team == ally_team]
    enemies = [(index, player) for index, player in indexed_players if player.team != ally_team]
    return [
        PlayerCard(
            champion_name=player.champion_name,
            side="ally" if player.team == ally_team else "enemy",
            position=player.position,
            role=role_guesses[index].role,
            role_confidence=role_guesses[index].confidence,
            level=player.level,
            is_dead=player.is_dead,
            respawns_at_game_time_seconds=_respawns_at_seconds(player, game_time_seconds),
            item_gold=_item_gold(player, item_catalog),
            finished_item_names=_finished_item_names(player, item_catalog),
        )
        for index, player in [*allies, *enemies]
    ]


def team_item_gold(cards: list[PlayerCard]) -> TeamItemGold | None:
    """Return what each team's items are worth, or None while any player's is unknown.

    Args:
        cards: Every player's card.

    Returns:
        Each team's item gold, or None.
    """
    item_golds_by_side = {
        side: [card.item_gold for card in cards if card.side == side] for side in ("ally", "enemy")
    }
    all_item_golds = [*item_golds_by_side["ally"], *item_golds_by_side["enemy"]]
    if not all_item_golds or any(item_gold is None for item_gold in all_item_golds):
        return None
    return TeamItemGold(
        ally_item_gold=sum(gold for gold in item_golds_by_side["ally"] if gold is not None),
        enemy_item_gold=sum(gold for gold in item_golds_by_side["enemy"] if gold is not None),
    )


def _item_gold(player: ScoreboardPlayer, item_catalog: ItemCatalog | None) -> int | None:
    """Return what a player's inventory is worth at this patch's prices.

    An item the catalog does not have counts at the price the scoreboard gives it.

    Args:
        player: The player.
        item_catalog: The patch's items; None while unknown.

    Returns:
        The gold, or None while the catalog is unknown.
    """
    if item_catalog is None:
        return None
    return sum(
        (item_catalog.total_price(item.item_id) or item.price) * item.count for item in player.items
    )


def _finished_item_names(player: ScoreboardPlayer, item_catalog: ItemCatalog | None) -> list[str]:
    """Return the names of a player's finished items, in inventory order.

    Args:
        player: The player.
        item_catalog: The patch's items; None while unknown.

    Returns:
        The names; empty while the catalog is unknown.
    """
    if item_catalog is None:
        return []
    return [
        item_catalog.name_of(item.item_id) or item.display_name
        for item in player.items
        if item_catalog.is_finished(item.item_id)
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
