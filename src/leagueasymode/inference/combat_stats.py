"""Each player's combat stats: exact for the player on this machine, estimated for the others.

The game gives the stats of the player on this machine in full (`activePlayer.championStats`).
For everyone else they are estimated from what the scoreboard shows, a champion, a level and the
items, with this patch's numbers from Data Dragon: the champion's base stats grown to the level by
the game's own growth formula, plus each item's stats. Runes, passives, stacks and buffs are not
counted, so an estimate runs low for a champion that has them; the recordings, which hold the
exact stats of the player on this machine all game long, measure by how much.
"""

from collections.abc import Callable
from typing import Final

from leagueasymode.data_dragon import ChampionBaseStats, ItemStatBonuses, PatchStats
from leagueasymode.game_state import ActiveChampionStats, GameSnapshot, ScoreboardPlayer
from leagueasymode.overlay_state import CombatStats

# The growth formula's constants (League of Legends Wiki, "Champion statistic"): at level 18 the
# growth is exactly 17 times the per-level value.
GROWTH_BASE: Final = 0.7025
GROWTH_STEP: Final = 0.0175
# Attack speed stops here for nearly every champion.
ATTACK_SPEED_CAP: Final = 2.5
# Move speed slows above these, and is raised below the floor (League of Legends Wiki).
MOVE_SPEED_FIRST_CAP: Final = 415.0
MOVE_SPEED_SECOND_CAP: Final = 490.0
MOVE_SPEED_FLOOR: Final = 220.0
PERCENT: Final = 100.0
# A champion's move speed when the patch's stats are not known: a base speed with boots.
DEFAULT_MOVE_SPEED: Final = 380.0


def stat_growth(level: int) -> float:
    """Return how many times its per-level value a stat has grown by at a level.

    Args:
        level: The champion's level, from 1.

    Returns:
        The multiple: 0 at level 1, 17 at level 18.
    """
    levels_gained = level - 1
    return levels_gained * (GROWTH_BASE + GROWTH_STEP * levels_gained)


def move_speed_after_caps(raw_move_speed: float) -> float:
    """Return the move speed the game applies for a raw one.

    Args:
        raw_move_speed: The base move speed plus every flat bonus, times every percent bonus.

    Returns:
        The move speed: slowed above 415 and more above 490, raised below 220.
    """
    if raw_move_speed > MOVE_SPEED_SECOND_CAP:
        return raw_move_speed * 0.5 + 230.0
    if raw_move_speed > MOVE_SPEED_FIRST_CAP:
        return raw_move_speed * 0.8 + 83.0
    if raw_move_speed < MOVE_SPEED_FLOOR:
        return raw_move_speed * 0.5 + 110.0
    return raw_move_speed


def estimated_combat_stats(player: ScoreboardPlayer, patch_stats: PatchStats) -> CombatStats | None:
    """Return a player's stats from their champion, level and items.

    Args:
        player: The player.
        patch_stats: This patch's champion and item stats.

    Returns:
        The estimate, or None for a champion the patch's stats do not have.
    """
    base_stats = patch_stats.champion_base_stats(player.raw_champion_name, player.champion_name)
    if base_stats is None:
        return None
    growth = stat_growth(player.level)
    item_bonuses = [
        bonuses
        for item in player.items
        for bonuses in [patch_stats.item_bonuses(item.item_id)] * item.count
        if bonuses is not None
    ]
    return CombatStats(
        source="estimate",
        health=round(
            _grown(base_stats.health, base_stats.health_per_level, growth)
            + _sum_of(item_bonuses, lambda bonuses: bonuses.flat_health),
            1,
        ),
        armor=round(
            _grown(base_stats.armor, base_stats.armor_per_level, growth)
            + _sum_of(item_bonuses, lambda bonuses: bonuses.flat_armor),
            1,
        ),
        magic_resist=round(
            _grown(base_stats.magic_resist, base_stats.magic_resist_per_level, growth)
            + _sum_of(item_bonuses, lambda bonuses: bonuses.flat_magic_resist),
            1,
        ),
        attack_damage=round(
            _grown(base_stats.attack_damage, base_stats.attack_damage_per_level, growth)
            + _sum_of(item_bonuses, lambda bonuses: bonuses.flat_attack_damage),
            1,
        ),
        ability_power=round(_sum_of(item_bonuses, lambda bonuses: bonuses.flat_ability_power), 1),
        attack_speed=round(_attack_speed(base_stats, growth, item_bonuses), 3),
        move_speed=round(
            move_speed_after_caps(
                (
                    base_stats.move_speed
                    + _sum_of(item_bonuses, lambda bonuses: bonuses.flat_move_speed)
                )
                * (1 + _sum_of(item_bonuses, lambda bonuses: bonuses.move_speed_fraction))
            ),
            1,
        ),
    )


def exact_combat_stats(champion_stats: ActiveChampionStats) -> CombatStats:
    """Return the stats the game gives for the player on this machine.

    Args:
        champion_stats: The game's `activePlayer.championStats`.

    Returns:
        The stats, marked exact.
    """
    return CombatStats(
        source="exact",
        health=champion_stats.max_health,
        armor=champion_stats.armor,
        magic_resist=champion_stats.magic_resist,
        attack_damage=champion_stats.attack_damage,
        ability_power=champion_stats.ability_power,
        attack_speed=champion_stats.attack_speed,
        move_speed=champion_stats.move_speed,
    )


def _grown(base: float, per_level: float, growth: float) -> float:
    """Return a stat at a level: its base and its per-level value times the growth.

    Args:
        base: The stat at level 1.
        per_level: What it grows by per level.
        growth: `stat_growth` of the level.

    Returns:
        The stat.
    """
    return base + per_level * growth


def _attack_speed(
    base_stats: ChampionBaseStats, growth: float, item_bonuses: list[ItemStatBonuses]
) -> float:
    """Return a champion's attack speed: the base, raised by every bonus, up to the cap.

    Per-level attack speed is a bonus like an item's, so the bonuses add up before they multiply
    the base.

    Args:
        base_stats: The champion's base stats.
        growth: `stat_growth` of the level.
        item_bonuses: The bonuses of every item held, once per item.

    Returns:
        The attack speed, in attacks a second.
    """
    bonus_fraction = base_stats.attack_speed_per_level_percent / PERCENT * growth + _sum_of(
        item_bonuses, lambda bonuses: bonuses.attack_speed_fraction
    )
    return min(base_stats.attack_speed * (1 + bonus_fraction), ATTACK_SPEED_CAP)


def _sum_of(
    item_bonuses: list[ItemStatBonuses], stat_of: Callable[[ItemStatBonuses], float]
) -> float:
    """Return one stat summed over items.

    Args:
        item_bonuses: The items' bonuses.
        stat_of: Picks the stat from one item's bonuses.

    Returns:
        The sum.
    """
    return sum(stat_of(bonuses) for bonuses in item_bonuses)


def move_speed_of(
    snapshot: GameSnapshot, player: ScoreboardPlayer, patch_stats: PatchStats | None
) -> float:
    """Return a player's move speed: the game's own for you, the estimate for the others.

    Args:
        snapshot: The game's state.
        player: The player.
        patch_stats: The patch's stats; None while unknown.

    Returns:
        The speed, in game units a second; 380 when it cannot be estimated.
    """
    active_player = snapshot.active_player
    if (
        active_player is not None
        and active_player.champion_stats is not None
        and snapshot.is_active_player(player)
    ):
        return active_player.champion_stats.move_speed
    estimate = estimated_combat_stats(player, patch_stats) if patch_stats is not None else None
    return estimate.move_speed if estimate is not None else DEFAULT_MOVE_SPEED
