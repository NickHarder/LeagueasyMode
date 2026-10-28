"""Cooldowns the player marks: when an enemy's Flash, other summoner spell or ultimate is back.

The game never says when another player casts a spell, so the player marks it, with a hotkey in
the macOS app: an enemy by their place in role order (1 top to 5 support), then the spell. The
timer starts at the game time of the mark. Its length is the patch's cooldown (Data Dragon), the
ultimate's at the rank the enemy's level gives (6, 11 and 16), shortened by the haste the enemy's
items give: cooldown * 100 / (100 + haste). Runes and other haste are not known, so the spell may
be back a little sooner than shown.
"""

from typing import Final, Literal

from leagueasymode.data_dragon import ItemHaste, PatchStats
from leagueasymode.game_state import GameSnapshot, ScoreboardPlayer, SummonerSpell
from leagueasymode.inference.roles import assign_roles
from leagueasymode.overlay_state import CooldownTimer

type MarkedSpell = Literal["flash", "summoner", "ultimate"]

FLASH_SPELL_ID: Final = "SummonerFlash"
ROLE_ORDER: Final = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
# The levels at which an ultimate reaches rank 2 and rank 3.
ULTIMATE_RANK_LEVELS: Final = (11, 16)
# The levels at which a player can put a point in their ultimate: most learn it at 6.
ULTIMATE_POINT_LEVELS: Final = (6, 11, 16)
# How many ranks an ultimate has: three for most; four for those learned at level 1 (Karma, Jayce,
# Elise, Nidalee), which rank up at 6, 11 and 16 too.
USUAL_ULTIMATE_RANKS: Final = 3
EARLY_ULTIMATE_RANKS: Final = 4
ULTIMATE_LABEL: Final = "R"
ULTIMATE_NAME: Final = "ultimate"
# The widget's short label for each summoner spell; any other is its name's first three letters.
SUMMONER_SPELL_LABELS: Final = {
    "SummonerFlash": "F",
    "SummonerTeleport": "TP",
    "SummonerDot": "IGN",
    "SummonerHeal": "HEAL",
    "SummonerExhaust": "EXH",
    "SummonerBarrier": "BAR",
    "SummonerBoost": "CLN",
    "SummonerHaste": "GHO",
    "SummonerSmite": "SMT",
}
PERCENT: Final = 100.0


def enemies_in_role_order(snapshot: GameSnapshot) -> list[ScoreboardPlayer]:
    """Return the enemies in role order, top to support, as the enemy strip shows them.

    Args:
        snapshot: The game's state.

    Returns:
        The enemies; a role nobody has goes last, in scoreboard order.
    """
    ally_team = snapshot.ally_team()
    role_guesses = assign_roles(snapshot)
    enemies = [
        (index, player) for index, player in enumerate(snapshot.players) if player.team != ally_team
    ]
    ordered_enemies = sorted(
        enemies,
        key=lambda pair: (
            ROLE_ORDER.index(role_guesses[pair[0]].role)
            if role_guesses[pair[0]].role in ROLE_ORDER
            else len(ROLE_ORDER),
            pair[0],
        ),
    )
    return [player for _, player in ordered_enemies]


def marked_cooldown(
    snapshot: GameSnapshot,
    enemy_slot: int,
    spell: MarkedSpell,
    patch_stats: PatchStats | None,
) -> CooldownTimer | None:
    """Return the timer of a spell the player marked an enemy as having just used.

    Args:
        snapshot: The game's state at the mark.
        enemy_slot: The enemy's place in role order, 1 for top to 5 for support.
        spell: "flash", "summoner" for their other summoner spell, or "ultimate".
        patch_stats: The patch's cooldowns; None while unknown.

    Returns:
        The timer, or None when there is no such enemy or the patch's cooldowns are unknown.
    """
    enemies = enemies_in_role_order(snapshot)
    if patch_stats is None or not 1 <= enemy_slot <= len(enemies):
        return None
    enemy = enemies[enemy_slot - 1]
    item_hastes = [
        patch_stats.item_haste(item.item_id) for item in enemy.items for _ in range(item.count)
    ]
    marked_at_seconds = snapshot.game_data.game_time_seconds
    if spell == "ultimate":
        return _ultimate_timer(enemy, patch_stats, marked_at_seconds, item_hastes)
    summoner_spell = _summoner_spell_marked(enemy, is_flash=spell == "flash")
    base_cooldown_seconds = patch_stats.summoner_spell_cooldown(summoner_spell.spell_id())
    if base_cooldown_seconds is None:
        return None
    summoner_spell_haste = sum(haste.summoner_spell_haste for haste in item_hastes)
    return CooldownTimer(
        cooldown_id=f"{enemy.champion_name}-{spell}-{marked_at_seconds:.1f}",
        champion_name=enemy.champion_name,
        spell=spell,
        spell_name=summoner_spell.display_name,
        label=SUMMONER_SPELL_LABELS.get(
            summoner_spell.spell_id(), summoner_spell.display_name[:3].upper()
        ),
        marked_at_game_time_seconds=marked_at_seconds,
        ready_at_game_time_seconds=marked_at_seconds
        + _hasted(base_cooldown_seconds, summoner_spell_haste),
    )


def running_cooldowns(timers: list[CooldownTimer], game_time_seconds: float) -> list[CooldownTimer]:
    """Return the timers whose spell is not back yet.

    Args:
        timers: Every timer marked this game.
        game_time_seconds: The game's clock.

    Returns:
        The timers still running, in the order they were marked.
    """
    return [timer for timer in timers if timer.ready_at_game_time_seconds > game_time_seconds]


def _ultimate_timer(
    enemy: ScoreboardPlayer,
    patch_stats: PatchStats,
    marked_at_seconds: float,
    item_hastes: list[ItemHaste],
) -> CooldownTimer | None:
    """Return the timer of an enemy's ultimate, at the rank their level gives.

    Args:
        enemy: The enemy.
        patch_stats: The patch's cooldowns.
        marked_at_seconds: The game time of the mark.
        item_hastes: The haste of each item the enemy holds.

    Returns:
        The timer, or None when the patch's files do not have the champion.
    """
    cooldowns_by_rank = patch_stats.ultimate_cooldowns(enemy.raw_champion_name, enemy.champion_name)
    if not cooldowns_by_rank:
        return None
    # The rank the row shows, and at least 1: a marked ultimate was cast, so it was learned. An
    # ultimate ranked in another way takes the usual rule.
    shown_rank = ultimate_rank(enemy.level, len(cooldowns_by_rank))
    rank = (
        max(1, shown_rank)
        if shown_rank is not None
        else 1 + sum(1 for level in ULTIMATE_RANK_LEVELS if enemy.level >= level)
    )
    base_cooldown_seconds = cooldowns_by_rank[min(rank, len(cooldowns_by_rank)) - 1]
    ability_haste = sum(haste.ability_haste for haste in item_hastes)
    return CooldownTimer(
        cooldown_id=f"{enemy.champion_name}-ultimate-{marked_at_seconds:.1f}",
        champion_name=enemy.champion_name,
        spell="ultimate",
        spell_name=ULTIMATE_NAME,
        label=ULTIMATE_LABEL,
        marked_at_game_time_seconds=marked_at_seconds,
        ready_at_game_time_seconds=marked_at_seconds
        + _hasted(base_cooldown_seconds, ability_haste),
    )


def ultimate_rank(level: int, rank_count: int) -> int | None:
    """Return the rank of a player's ultimate at a level, as the game lets them put points in it.

    Args:
        level: The player's level.
        rank_count: How many ranks the ultimate has, from the patch's files.

    Returns:
        The rank, 0 before it is learned; None for an ultimate ranked in another way, as one that
        ranks like a basic ability, whose rank the level does not give.
    """
    points_by_level = sum(1 for point_level in ULTIMATE_POINT_LEVELS if level >= point_level)
    if rank_count == USUAL_ULTIMATE_RANKS:
        return points_by_level
    if rank_count == EARLY_ULTIMATE_RANKS:
        return 1 + points_by_level
    return None


def player_ultimate_rank(player: ScoreboardPlayer, patch_stats: PatchStats | None) -> int | None:
    """Return the rank of a player's ultimate now.

    Args:
        player: The player.
        patch_stats: The patch's files; None while unknown.

    Returns:
        The rank, 0 before it is learned; None while it cannot be known.
    """
    if patch_stats is None:
        return None
    cooldowns_by_rank = patch_stats.ultimate_cooldowns(
        player.raw_champion_name, player.champion_name
    )
    if not cooldowns_by_rank:
        return None
    return ultimate_rank(player.level, len(cooldowns_by_rank))


def marked_spell_names(enemy: ScoreboardPlayer) -> list[str]:
    """Return the spells a "flash" and a "summoner" mark name for an enemy, in that order.

    Args:
        enemy: The enemy.

    Returns:
        The two spells' names.
    """
    return [
        _summoner_spell_marked(enemy, is_flash=True).display_name,
        _summoner_spell_marked(enemy, is_flash=False).display_name,
    ]


def _summoner_spell_marked(enemy: ScoreboardPlayer, *, is_flash: bool) -> SummonerSpell:
    """Return which of an enemy's summoner spells a mark names.

    Flash is their Flash, and the other spell the one that is not; an enemy without Flash has
    their first spell marked as "Flash" and their second as the other.

    Args:
        enemy: The enemy.
        is_flash: Whether the mark is for Flash.

    Returns:
        The spell.
    """
    spells = (enemy.summoner_spells.first, enemy.summoner_spells.second)
    flash = next((spell for spell in spells if spell.spell_id() == FLASH_SPELL_ID), None)
    if flash is None:
        return spells[0] if is_flash else spells[1]
    if is_flash:
        return flash
    return next(spell for spell in spells if spell is not flash)


def _hasted(cooldown_seconds: float, haste: float) -> float:
    """Return a cooldown shortened by haste, as the game shortens it.

    Args:
        cooldown_seconds: The cooldown without haste.
        haste: The haste.

    Returns:
        The cooldown in seconds.
    """
    return cooldown_seconds * PERCENT / (PERCENT + haste)
