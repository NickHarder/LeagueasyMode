"""Fights (estimator 10): the chance the player's team wins an even fight now.

Each living player's sustained damage, physical and magic, comes from their combat stats
(estimator 2): auto attacks deal their attack damage times their attack speed, physical; abilities
deal a little per level plus shares of their ability power and attack damage, split between magic
and physical as Riot rates the champion (Data Dragon's `info`, magic over attack and magic). Their
effective health is their health over the share of the other team's damage that gets through
their armor and magic resist (100 / (100 + resistance) of each kind).

Teams fight as Lanchester's square law has it: when each side's damage spreads over the other's
health and shrinks as its own players fall, the side whose damage times health is greater wins.
The chance is a logistic of the logarithm of the two sides' ratio, so equal teams are even and a
team twice as strong wins about 4 times in 5. Runes, penetration, shields, heals, crowd control,
range and cooldowns are not counted: the weights are first guesses, to refit on the fights of
recorded games (phase 5.5).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from leagueasymode.data_dragon import PatchStats
from leagueasymode.game_state import GameSnapshot, ScoreboardPlayer
from leagueasymode.inference.combat_stats import combat_stats_of
from leagueasymode.overlay_state import CombatStats, FightEstimate

RESISTANCE_SCALE: Final = 100.0


@dataclass(frozen=True)
class FightRules:
    """How damage is worked out from the stats, and how steep the chance is. First guesses."""

    # An ability's damage a second: this much per level, plus these shares of ability power and
    # attack damage.
    ability_damage_per_level: float = 4.0
    ability_power_ratio: float = 0.4
    attack_damage_ratio: float = 0.2
    # The chance's log-odds per unit of the logarithm of the strengths' ratio.
    steepness: float = 2.0
    # The magic share of a champion Riot does not rate.
    default_magic_share: float = 0.5


FIGHT_RULES: Final = FightRules()


@dataclass(frozen=True)
class Fighter:
    """One player in a fight: their stats, level, and the magic share of their abilities' damage."""

    stats: CombatStats
    level: int
    magic_share: float


def fighter_damage(fighter: Fighter, rules: FightRules = FIGHT_RULES) -> tuple[float, float]:
    """Return a fighter's sustained damage a second, physical and magic.

    Args:
        fighter: The fighter.
        rules: How damage is worked out.

    Returns:
        The physical damage and the magic damage, a second.
    """
    stats = fighter.stats
    auto_attacks = stats.attack_damage * stats.attack_speed
    abilities = (
        rules.ability_damage_per_level * fighter.level
        + rules.ability_power_ratio * stats.ability_power
        + rules.attack_damage_ratio * stats.attack_damage
    )
    return auto_attacks + abilities * (1 - fighter.magic_share), abilities * fighter.magic_share


def effective_health(stats: CombatStats, physical_share: float) -> float:
    """Return the damage a player takes to die, from a mix of physical and magic damage.

    Args:
        stats: Their stats.
        physical_share: The share of the damage that is physical, the rest magic.

    Returns:
        Their health over the share of the mix that gets through their resistances.
    """
    taken_share = physical_share * _through(stats.armor) + (1 - physical_share) * _through(
        stats.magic_resist
    )
    return stats.health / taken_share


def fight_estimate(
    allies: Sequence[Fighter], enemies: Sequence[Fighter], rules: FightRules = FIGHT_RULES
) -> FightEstimate | None:
    """Return the chance the allies win a fight against the enemies, all at once.

    Args:
        allies: The player's team's fighters.
        enemies: The other team's.
        rules: How damage is worked out, and how steep the chance is.

    Returns:
        The estimate; None when nobody fights.
    """
    if not allies and not enemies:
        return None
    ally_physical, ally_magic = _team_damage(allies, rules)
    enemy_physical, enemy_magic = _team_damage(enemies, rules)
    ally_physical_share = _share(ally_physical, ally_magic)
    enemy_physical_share = _share(enemy_physical, enemy_magic)
    ally_strength = (ally_physical + ally_magic) * sum(
        effective_health(fighter.stats, enemy_physical_share) for fighter in allies
    )
    enemy_strength = (enemy_physical + enemy_magic) * sum(
        effective_health(fighter.stats, ally_physical_share) for fighter in enemies
    )
    return FightEstimate(
        ally_chance=_chance(ally_strength, enemy_strength, rules),
        ally_fighters=len(allies),
        enemy_fighters=len(enemies),
        ally_physical_share=ally_physical_share,
        enemy_physical_share=enemy_physical_share,
    )


def fighter_of(
    snapshot: GameSnapshot,
    player: ScoreboardPlayer,
    patch_stats: PatchStats | None,
    rules: FightRules = FIGHT_RULES,
) -> Fighter | None:
    """Return a player as a fighter.

    Args:
        snapshot: The game's state.
        player: The player.
        patch_stats: The patch's stats; None while unknown.
        rules: The magic share of a champion Riot does not rate.

    Returns:
        The fighter, or None while their stats cannot be had.
    """
    stats = combat_stats_of(snapshot, player, patch_stats)
    if stats is None:
        return None
    magic_share = (
        patch_stats.champion_magic_share(player.raw_champion_name, player.champion_name)
        if patch_stats is not None
        else None
    )
    return Fighter(
        stats=stats,
        level=player.level,
        magic_share=magic_share if magic_share is not None else rules.default_magic_share,
    )


def team_fight(
    snapshot: GameSnapshot, patch_stats: PatchStats | None, rules: FightRules = FIGHT_RULES
) -> FightEstimate | None:
    """Return the chance the player's team wins an even fight now: everyone alive, at full health.

    Args:
        snapshot: The game's state.
        patch_stats: The patch's stats; None while unknown.
        rules: How damage is worked out, and how steep the chance is.

    Returns:
        The estimate; None while any living player's stats are unknown.
    """
    ally_team = snapshot.ally_team()
    fighters = [
        (player.team == ally_team, fighter_of(snapshot, player, patch_stats, rules))
        for player in snapshot.players
        if not player.is_dead
    ]
    known = [(is_ally, fighter) for is_ally, fighter in fighters if fighter is not None]
    if len(known) != len(fighters):
        return None
    return fight_estimate(
        [fighter for is_ally, fighter in known if is_ally],
        [fighter for is_ally, fighter in known if not is_ally],
        rules,
    )


def _team_damage(fighters: Sequence[Fighter], rules: FightRules) -> tuple[float, float]:
    """Return a team's damage a second, physical and magic.

    Args:
        fighters: The team's fighters.
        rules: How damage is worked out.

    Returns:
        The physical damage and the magic damage.
    """
    damages = [fighter_damage(fighter, rules) for fighter in fighters]
    return sum(physical for physical, _ in damages), sum(magic for _, magic in damages)


def _share(physical: float, magic: float) -> float:
    """Return the physical share of a team's damage; even when it deals none.

    Args:
        physical: Its physical damage.
        magic: Its magic damage.

    Returns:
        The share, from 0 to 1.
    """
    return physical / (physical + magic) if physical + magic > 0 else 0.5


def _through(resistance: float) -> float:
    """Return the share of damage that gets through a resistance.

    Args:
        resistance: Armor or magic resist, 0 or more.

    Returns:
        100 / (100 + resistance).
    """
    return RESISTANCE_SCALE / (RESISTANCE_SCALE + max(resistance, 0.0))


def _chance(ally_strength: float, enemy_strength: float, rules: FightRules) -> float:
    """Return the chance the stronger side's strength gives the allies.

    Args:
        ally_strength: The allies' damage times health.
        enemy_strength: The enemies'.
        rules: How steep the chance is.

    Returns:
        The chance: 1 when the enemies have no strength, 0 when the allies have none.
    """
    if enemy_strength <= 0:
        return 1.0 if ally_strength > 0 else 0.5
    if ally_strength <= 0:
        return 0.0
    log_odds = rules.steepness * math.log(ally_strength / enemy_strength)
    if log_odds < 0:
        return math.exp(log_odds) / (1 + math.exp(log_odds))
    return 1 / (1 + math.exp(-log_odds))
