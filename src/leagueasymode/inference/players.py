"""The players, from the scoreboard: who is on which side, their level, and when the dead return.

Exact: the scoreboard gives every player's level and, while they are dead, the seconds until they
respawn. The numbers window follows from those alone, since a death to come cannot be known.
"""

from collections.abc import Mapping

from leagueasymode.data_dragon import PatchStats
from leagueasymode.game_state import GameSnapshot, ScoreboardPlayer
from leagueasymode.inference.build_path import next_item
from leagueasymode.inference.combat_stats import estimated_combat_stats, exact_combat_stats
from leagueasymode.inference.gold import PlayerKey, player_key
from leagueasymode.inference.intel import player_intel
from leagueasymode.inference.roles import RoleGuess, assign_roles
from leagueasymode.overlay_state import (
    BackEstimate,
    CombatStats,
    GoldEstimate,
    LevelEstimate,
    NextItemEstimate,
    NumbersWindow,
    PlayerCard,
    PlayerIntel,
    PositionClue,
    TeamItemGold,
)
from leagueasymode.patch_data import ItemCatalog
from leagueasymode.player_intel import PlayerRecords


def player_cards(
    snapshot: GameSnapshot,
    item_catalog: ItemCatalog | None = None,
    *,
    patch_stats: PatchStats | None = None,
    player_records: PlayerRecords | None = None,
    gold_estimates: Mapping[PlayerKey, GoldEstimate] | None = None,
    level_estimates: Mapping[PlayerKey, LevelEstimate] | None = None,
    last_backs: Mapping[PlayerKey, BackEstimate] | None = None,
    position_clues: Mapping[PlayerKey, list[PositionClue]] | None = None,
) -> list[PlayerCard]:
    """Return a card for every player, the player's own team first, each team in scoreboard order.

    Args:
        snapshot: The game's state.
        item_catalog: The patch's items, for item gold and finished items; None while unknown.
        patch_stats: The patch's champion and item stats, for the combat stats; None while
            unknown.
        player_records: Each player's record from the League client, for their intel; None
            while unknown.
        gold_estimates: Each player's gold, by key; None while the game's gold is not followed.
        level_estimates: Each player's experience, by key; None while it is not followed.
        last_backs: Each player's last trip to base, by key; None while trips are not followed.
        position_clues: Each player's clues to where they are, oldest first, by key; None while
            they are not gathered.

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
            combat_stats=_combat_stats(snapshot, player, patch_stats),
            intel=_intel(player, role_guesses[index], player_records),
            gold=gold_estimates.get(player_key(player)) if gold_estimates is not None else None,
            level_estimate=(
                level_estimates.get(player_key(player)) if level_estimates is not None else None
            ),
            last_back=last_backs.get(player_key(player)) if last_backs is not None else None,
            next_item=_next_item(
                snapshot,
                player,
                item_catalog,
                patch_stats,
                player_records=player_records,
                gold=gold_estimates.get(player_key(player)) if gold_estimates is not None else None,
            ),
            last_clue=_last_clue(player, position_clues),
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


def _combat_stats(
    snapshot: GameSnapshot, player: ScoreboardPlayer, patch_stats: PatchStats | None
) -> CombatStats | None:
    """Return a player's combat stats: the game's own for the player on this machine.

    Args:
        snapshot: The game's state.
        player: The player.
        patch_stats: The patch's stats; None while unknown.

    Returns:
        The stats, or None while they cannot be had.
    """
    active_player = snapshot.active_player
    if (
        active_player is not None
        and active_player.champion_stats is not None
        and snapshot.is_active_player(player)
    ):
        return exact_combat_stats(active_player.champion_stats)
    if patch_stats is None:
        return None
    return estimated_combat_stats(player, patch_stats)


def _next_item(
    snapshot: GameSnapshot,
    player: ScoreboardPlayer,
    item_catalog: ItemCatalog | None,
    patch_stats: PatchStats | None,
    *,
    player_records: PlayerRecords | None,
    gold: GoldEstimate | None,
) -> NextItemEstimate | None:
    """Return a player's likely next finished item, with what their record says they build.

    Args:
        snapshot: The game's state.
        player: The player.
        item_catalog: The patch's items; None while unknown.
        patch_stats: The patch's stats, for the champion's classes; None while unknown.
        player_records: Each player's record; None while unknown.
        gold: Their gold; None while it is not followed.

    Returns:
        The item, or None without the catalog or any candidate.
    """
    game_record = (
        player_records.get((player.team, player.champion_alias().lower()))
        if player_records is not None
        else None
    )
    return next_item(
        player,
        item_catalog,
        patch_stats,
        record=game_record.record if game_record is not None else None,
        champion_id=game_record.champion_id if game_record is not None else 0,
        gold=gold,
        game_time_seconds=snapshot.game_data.game_time_seconds,
    )


def _last_clue(
    player: ScoreboardPlayer, position_clues: Mapping[PlayerKey, list[PositionClue]] | None
) -> PositionClue | None:
    """Return the latest clue to where a player is.

    Args:
        player: The player.
        position_clues: Each player's clues, oldest first; None while they are not gathered.

    Returns:
        The clue, or None without one.
    """
    clues = position_clues.get(player_key(player), []) if position_clues is not None else []
    return clues[-1] if clues else None


def _intel(
    player: ScoreboardPlayer, role_guess: RoleGuess, player_records: PlayerRecords | None
) -> PlayerIntel | None:
    """Return what a player's record says, matched to them by team and champion.

    Args:
        player: The player.
        role_guess: Their role this game; a guess is not used to call them off-role.
        player_records: Each player's record; None while unknown.

    Returns:
        The intel, or None when the player has no record.
    """
    game_record = (
        player_records.get((player.team, player.champion_alias().lower()))
        if player_records is not None
        else None
    )
    if game_record is None:
        return None
    is_position_known = role_guess.confidence in {"given", "likely"}
    return player_intel(
        game_record.record, game_record.champion_id, role_guess.role if is_position_known else ""
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
