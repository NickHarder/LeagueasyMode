"""Objective contests (estimator 11): whether the enemy can reach a monster before it dies.

For Dragon, the Elder Dragon and Baron, once up or within 30 seconds of spawning: how long the
player's living team takes to kill it, and the chance at least one enemy reaches its pit before
then.

- **The kill:** the monster's health at this time (2026: Baron 16,300 and 190 a minute from the
  start; the Elder 11,500 and 290 a minute after 25:00; a drake 3,625 and 375 a level of the
  champions' average level, from 6 to 18), less a Smite when an ally has one (600, 1,000 from
  12:00 once upgraded), over the team's damage a second (`fights.py`) through its armor and magic
  resist. All unconfirmed this season; the drakes' differences are left out.
- **The arrival:** a living enemy's chance to reach the pit is the share of the position filter's
  chance (`positions.py`) on points within the kill's time of it at their full speed; a dead
  enemy reaches it once respawned and walked from their fountain. The enemy contests when any
  one of them arrives: 1 less the chance that none does, as if they moved on their own.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from leagueasymode.data_dragon import PatchStats
from leagueasymode.game_state import GameSnapshot, ScoreboardPlayer
from leagueasymode.inference.combat_stats import move_speed_of
from leagueasymode.inference.fights import Fighter, fighter_damage, fighter_of
from leagueasymode.inference.gold import PlayerKey, creep_kind_of, player_key
from leagueasymode.inference.positions import point_chances
from leagueasymode.inference.rift_map import RIFT_MAP, fountain_of
from leagueasymode.inference.roles import assign_roles
from leagueasymode.overlay_state import (
    DragonTimer,
    ObjectiveContest,
    ObjectiveTimer,
    PositionClue,
)

type ContestedObjective = Literal["dragon", "elder_dragon", "baron"]

SECONDS_PER_MINUTE: Final = 60.0
RESISTANCE_SCALE: Final = 100.0
PIT_OF: Final[Mapping[ContestedObjective, str]] = {
    "dragon": "dragon_pit",
    "elder_dragon": "dragon_pit",
    "baron": "baron_pit",
}


@dataclass(frozen=True)
class ContestRules:
    """The monsters' health and resistances, Smite's damage, and when a monster is weighed.

    The 2026 season's, from patch 26.1's notes as trackers list them; unconfirmed.
    """

    baron_health: float = 16_300.0
    baron_health_per_minute: float = 190.0
    baron_armor: float = 34.0
    baron_magic_resist: float = 32.0
    elder_health: float = 11_500.0
    elder_health_per_minute: float = 290.0
    elder_growth_from_minutes: float = 25.0
    elder_armor: float = 34.0
    elder_magic_resist: float = 32.0
    drake_health: float = 3625.0
    drake_health_per_level: float = 375.0
    drake_lowest_level: float = 6.0
    drake_highest_level: float = 18.0
    drake_armor: float = 21.0
    drake_magic_resist: float = 30.0
    smite_damage: float = 600.0
    upgraded_smite_damage: float = 1000.0
    smite_upgraded_from_seconds: float = 720.0
    # A monster is weighed from this long before it spawns.
    weighed_before_spawn_seconds: float = 30.0


CONTEST_RULES: Final = ContestRules()


def monster_health(
    objective: ContestedObjective,
    game_time_seconds: float,
    mean_level: float,
    rules: ContestRules = CONTEST_RULES,
) -> float:
    """Return a monster's health at a time.

    Args:
        objective: The monster.
        game_time_seconds: The game's clock.
        mean_level: The champions' average level, which a drake's level follows.
        rules: The monsters' numbers.

    Returns:
        Its health.
    """
    minutes = game_time_seconds / SECONDS_PER_MINUTE
    if objective == "baron":
        return rules.baron_health + rules.baron_health_per_minute * minutes
    if objective == "elder_dragon":
        return rules.elder_health + rules.elder_health_per_minute * max(
            0.0, minutes - rules.elder_growth_from_minutes
        )
    drake_level = min(max(mean_level, rules.drake_lowest_level), rules.drake_highest_level)
    return rules.drake_health + rules.drake_health_per_level * (drake_level - 1)


def kill_seconds(
    objective: ContestedObjective,
    allies: Sequence[Fighter],
    *,
    game_time_seconds: float,
    mean_level: float,
    has_smite: bool,
    rules: ContestRules = CONTEST_RULES,
) -> float | None:
    """Return how long a team takes to kill a monster.

    Args:
        objective: The monster.
        allies: The team's fighters at it.
        game_time_seconds: The game's clock.
        mean_level: The champions' average level.
        has_smite: Whether one of them has Smite, used at the end.
        rules: The monsters' numbers and Smite's damage.

    Returns:
        The seconds; None when the team deals no damage.
    """
    armor, magic_resist = _resistances(objective, rules)
    damages = [fighter_damage(fighter) for fighter in allies]
    damage_per_second = sum(
        physical * _through(armor) + magic * _through(magic_resist) for physical, magic in damages
    )
    if damage_per_second <= 0:
        return None
    smite = (
        (
            rules.upgraded_smite_damage
            if game_time_seconds >= rules.smite_upgraded_from_seconds
            else rules.smite_damage
        )
        if has_smite
        else 0.0
    )
    health = monster_health(objective, game_time_seconds, mean_level, rules)
    return max(0.0, health - smite) / damage_per_second


def reach_chance(
    player: ScoreboardPlayer,
    role: str,
    clues: Sequence[PositionClue],
    *,
    pit: str,
    move_speed: float,
    game_time_seconds: float,
    within_seconds: float,
) -> float:
    """Return the chance a player can reach a pit within some time.

    Args:
        player: The player.
        role: Their role, given or worked out; empty when unknown.
        clues: Their clues so far, oldest first.
        pit: The map's point of the pit.
        move_speed: Their move speed, in game units a second.
        game_time_seconds: The game's clock.
        within_seconds: The time they have.

    Returns:
        The chance: of a living player, the share of where they may be that is close enough; of
        a dead one, 1 when their respawn and the walk from their fountain fit in the time.
    """
    if player.is_dead:
        walk_seconds = RIFT_MAP.distance(fountain_of(player.team), pit) / move_speed
        return 1.0 if player.respawn_timer_seconds + walk_seconds <= within_seconds else 0.0
    chances = point_chances(
        player.team, role, clues, move_speed=move_speed, game_time_seconds=game_time_seconds
    )
    return sum(
        chance
        for name, chance in chances.items()
        if RIFT_MAP.distance(name, pit) / move_speed <= within_seconds
    )


def contest_chance(arrival_chances: Sequence[float]) -> float:
    """Return the chance at least one of several players arrives, each on their own.

    Args:
        arrival_chances: Each player's chance.

    Returns:
        1 less the chance that none arrives.
    """
    return 1.0 - math.prod(1.0 - chance for chance in arrival_chances)


def objective_contests(
    snapshot: GameSnapshot,
    *,
    dragon: DragonTimer,
    objectives: Sequence[ObjectiveTimer],
    position_clues: Mapping[PlayerKey, Sequence[PositionClue]],
    patch_stats: PatchStats | None,
    rules: ContestRules = CONTEST_RULES,
) -> list[ObjectiveContest]:
    """Return each monster up or soon: how long your team takes, and the chance of a contest.

    Args:
        snapshot: The game's state.
        dragon: The next dragon or Elder Dragon.
        objectives: The other monsters' timers.
        position_clues: Each player's clues to where they are.
        patch_stats: The patch's stats; None while unknown.
        rules: The monsters' numbers.

    Returns:
        The contests, Dragon or the Elder first, then Baron; none while any living ally's combat
        stats are unknown.
    """
    game_time_seconds = snapshot.game_data.game_time_seconds
    spawns: list[tuple[ContestedObjective, float | None]] = [
        (dragon.objective, dragon.spawns_at_game_time_seconds),
        *(
            ("baron", timer.spawns_at_game_time_seconds)
            for timer in objectives
            if timer.objective == "baron" and timer.status != "gone"
        ),
    ]
    weighed = [
        (objective, max(0.0, spawns_at - game_time_seconds))
        for objective, spawns_at in spawns
        if spawns_at is not None
        and spawns_at - game_time_seconds <= rules.weighed_before_spawn_seconds
    ]
    ally_team = snapshot.ally_team()
    allies = [player for player in snapshot.players if player.team == ally_team]
    fighters = [
        fighter_of(snapshot, player, patch_stats) for player in allies if not player.is_dead
    ]
    known_fighters = [fighter for fighter in fighters if fighter is not None]
    if not weighed or not fighters or len(known_fighters) != len(fighters):
        return []
    mean_level = sum(player.level for player in snapshot.players) / len(snapshot.players)
    has_smite = any(creep_kind_of(player) == "jungle" for player in allies if not player.is_dead)
    roles = {
        player_key(player): role_guess.role
        for player, role_guess in zip(snapshot.players, assign_roles(snapshot), strict=True)
    }
    enemies = [player for player in snapshot.players if player.team != ally_team]
    contests: list[ObjectiveContest] = []
    for objective, wait_seconds in weighed:
        seconds = kill_seconds(
            objective,
            known_fighters,
            game_time_seconds=game_time_seconds,
            mean_level=mean_level,
            has_smite=has_smite,
            rules=rules,
        )
        if seconds is None:
            continue
        arrivals = [
            (
                enemy.champion_name,
                reach_chance(
                    enemy,
                    roles.get(player_key(enemy), ""),
                    position_clues.get(player_key(enemy), []),
                    pit=PIT_OF[objective],
                    move_speed=move_speed_of(snapshot, enemy, patch_stats),
                    game_time_seconds=game_time_seconds,
                    within_seconds=wait_seconds + seconds,
                ),
            )
            for enemy in enemies
        ]
        likeliest = max(arrivals, key=lambda arrival: arrival[1], default=None)
        contests.append(
            ObjectiveContest(
                objective=objective,
                kill_seconds=round(seconds, 1),
                ally_fighters=len(known_fighters),
                contest_chance=round(contest_chance([chance for _, chance in arrivals]), 3),
                likeliest_contester=likeliest[0] if likeliest and likeliest[1] > 0 else None,
                likeliest_chance=round(likeliest[1], 3) if likeliest else 0.0,
            )
        )
    return contests


def _resistances(objective: ContestedObjective, rules: ContestRules) -> tuple[float, float]:
    """Return a monster's armor and magic resist.

    Args:
        objective: The monster.
        rules: The monsters' numbers.

    Returns:
        Its armor and magic resist.
    """
    if objective == "baron":
        return rules.baron_armor, rules.baron_magic_resist
    if objective == "elder_dragon":
        return rules.elder_armor, rules.elder_magic_resist
    return rules.drake_armor, rules.drake_magic_resist


def _through(resistance: float) -> float:
    """Return the share of damage that gets through a resistance.

    Args:
        resistance: Armor or magic resist.

    Returns:
        100 / (100 + resistance).
    """
    return RESISTANCE_SCALE / (RESISTANCE_SCALE + max(resistance, 0.0))
