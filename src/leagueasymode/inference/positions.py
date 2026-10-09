"""Positions (estimator 7): where each player likely is now, from their latest clue.

The plan names a particle filter. Over the map's 81 points, the exact filter it approximates, a
chance for each point (a histogram filter), does the same work without sampling noise, so that is
what runs. From a player's latest clue (`clues.py`) they can be at any point they could have
walked to since, at their move speed for the share of the time a champion moves. Each such point
is weighed by how much a player of their role is found in its region: a laner in their lane, the
river beside it and their own jungle behind it; a jungler in their jungle, the river, and the
other team's jungle less. With no clue for long, the reach covers the map and the role's habits
alone remain. Around 4:00, a jungler's own habit from past games, the half of the map they are
usually on then (`jungle_starts.py`), weighs each half too. The soonest they could reach each
lane is the walk from the clue's place at full speed, less the time since.
"""

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from leagueasymode.game_state import ScoreboardPlayer
from leagueasymode.inference.rift_map import RIFT_MAP, TEAM_PREFIX, fountain_of, region_center
from leagueasymode.jungle_starts import (
    MAP_HALF_BY_REGION,
    FourMinuteSides,
    four_minute_half_weights,
)
from leagueasymode.overlay_state import PositionClue, PositionEstimate, RegionChance

# How much a player of each role is found in each region, as the region stands to their team:
# "own" and "enemy" stand for the team's prefix. A first guess, to fit on the timeline's positions.
ROLE_HABITS: Final[Mapping[str, Mapping[str, float]]] = {
    "TOP": {"top_lane": 1.0, "top_river": 0.3, "own_top_jungle": 0.2, "mid_lane": 0.1},
    "MIDDLE": {
        "mid_lane": 1.0,
        "top_river": 0.3,
        "bot_river": 0.3,
        "own_top_jungle": 0.15,
        "own_bot_jungle": 0.15,
        "top_lane": 0.1,
        "bot_lane": 0.1,
    },
    "BOTTOM": {"bot_lane": 1.0, "bot_river": 0.3, "own_bot_jungle": 0.15, "mid_lane": 0.1},
    "UTILITY": {
        "bot_lane": 0.8,
        "bot_river": 0.4,
        "top_river": 0.15,
        "mid_lane": 0.15,
        "own_top_jungle": 0.15,
        "own_bot_jungle": 0.15,
    },
    "JUNGLE": {
        "own_top_jungle": 1.0,
        "own_bot_jungle": 1.0,
        "top_river": 0.5,
        "bot_river": 0.5,
        "enemy_top_jungle": 0.3,
        "enemy_bot_jungle": 0.3,
        "top_lane": 0.2,
        "mid_lane": 0.2,
        "bot_lane": 0.2,
    },
}
# A region a role's habits do not name, or any region for an unknown role.
OTHER_REGION_WEIGHT: Final = 0.05
OWN_BASE_WEIGHT: Final = 0.05
ENEMY_BASE_WEIGHT: Final = 0.01
HOME_REGIONS: Final[Mapping[str, frozenset[str]]] = {
    "TOP": frozenset({"top_lane"}),
    "MIDDLE": frozenset({"mid_lane"}),
    "BOTTOM": frozenset({"bot_lane"}),
    "UTILITY": frozenset({"bot_lane"}),
    "JUNGLE": frozenset({"own_top_jungle", "own_bot_jungle"}),
}
# The middle of each lane, where its fights are.
LANE_MIDDLES: Final = {"top": "top_lane_corner", "mid": "mid_center", "bot": "bot_lane_corner"}
REGION_WORDS: Final = {
    "top_lane": "top lane",
    "mid_lane": "mid lane",
    "bot_lane": "bot lane",
    "top_river": "top river",
    "bot_river": "bot river",
}
SHOWN_REGION_COUNT: Final = 3


@dataclass(frozen=True)
class PositionRules:
    """How much of the time a champion moves."""

    # Between clues a champion farms, fights and waits as well as walks.
    moving_share: float = 0.8
    # A jungler's 4:00 habit weighs the halves of the map from 3:00 to 5:00.
    four_minute_habit_from_seconds: float = 180.0
    four_minute_habit_until_seconds: float = 300.0


POSITION_RULES: Final = PositionRules()


def position_estimate(
    player: ScoreboardPlayer,
    role: str,
    clues: Sequence[PositionClue],
    *,
    move_speed: float,
    game_time_seconds: float,
    ally_team: str,
    four_minute_sides: FourMinuteSides | None = None,
    rules: PositionRules = POSITION_RULES,
) -> PositionEstimate | None:
    """Return where a player likely is now.

    Args:
        player: The player.
        role: Their role, given or worked out; empty when unknown.
        clues: Their clues so far, oldest first.
        move_speed: Their move speed, in game units a second.
        game_time_seconds: The game's clock.
        ally_team: The team of the player on this machine, to put regions in their words.
        four_minute_sides: Where their past jungle games found them at 4:00; None when unknown.
        rules: How much of the time a champion moves.

    Returns:
        The estimate; None while they are dead, since their respawn is known.
    """
    if player.is_dead:
        return None
    last_clue = clues[-1] if clues else None
    start_points = _start_points(player.team, last_clue)
    since_seconds = max(
        0.0, game_time_seconds - (last_clue.game_time_seconds if last_clue is not None else 0.0)
    )
    chance_by_region: defaultdict[str, float] = defaultdict(float)
    for name, chance in point_chances(
        player.team,
        role,
        clues,
        move_speed=move_speed,
        game_time_seconds=game_time_seconds,
        four_minute_sides=four_minute_sides,
        rules=rules,
    ).items():
        chance_by_region[RIFT_MAP.points[name].region] += chance
    home_regions = {
        _team_region(region, player.team) for region in HOME_REGIONS.get(role, frozenset())
    }
    likeliest = sorted(chance_by_region.items(), key=lambda entry: entry[1], reverse=True)
    return PositionEstimate(
        regions=[
            RegionChance(
                region=region,
                label=_region_label(region, ally_team),
                chance=chance,
                x_position=region_center(region)[0],
                y_position=region_center(region)[1],
            )
            for region, chance in likeliest[:SHOWN_REGION_COUNT]
        ],
        away_chance=(
            1.0 - sum(chance_by_region.get(region, 0.0) for region in home_regions)
            if home_regions
            else 0.0
        ),
        unseen_seconds=since_seconds if last_clue is not None else None,
        reach_top_seconds=_reach_seconds(start_points, "top", move_speed, since_seconds),
        reach_mid_seconds=_reach_seconds(start_points, "mid", move_speed, since_seconds),
        reach_bot_seconds=_reach_seconds(start_points, "bot", move_speed, since_seconds),
    )


def point_chances(
    team: str,
    role: str,
    clues: Sequence[PositionClue],
    *,
    move_speed: float,
    game_time_seconds: float,
    four_minute_sides: FourMinuteSides | None = None,
    rules: PositionRules = POSITION_RULES,
) -> dict[str, float]:
    """Return the chance a living player is at each of the map's points now.

    Args:
        team: Their team.
        role: Their role, given or worked out; empty when unknown.
        clues: Their clues so far, oldest first.
        move_speed: Their move speed, in game units a second.
        game_time_seconds: The game's clock.
        four_minute_sides: Where a jungler's past games found them at 4:00, which weighs the
            halves of the map from 3:00 to 5:00; None when unknown.
        rules: How much of the time a champion moves.

    Returns:
        The chances by point name, adding up to 1; a point they cannot be at is left out.
    """
    last_clue = clues[-1] if clues else None
    start_points = _start_points(team, last_clue)
    since_seconds = max(
        0.0, game_time_seconds - (last_clue.game_time_seconds if last_clue is not None else 0.0)
    )
    nearest_start = {
        name: min(RIFT_MAP.distances_from(start).get(name, math.inf) for start in start_points)
        for name in RIFT_MAP.points
    }
    reach_units = move_speed * rules.moving_share * since_seconds
    is_four_minute_habit_on = (
        four_minute_sides is not None
        and role == "JUNGLE"
        and rules.four_minute_habit_from_seconds
        <= game_time_seconds
        <= rules.four_minute_habit_until_seconds
    )
    half_weights: Mapping[str, float] = (
        four_minute_half_weights(four_minute_sides, team)
        if four_minute_sides is not None and is_four_minute_habit_on
        else {}
    )
    reachable_weights = {
        name: _region_weight(role, team, RIFT_MAP.points[name].region)
        * _half_weight(RIFT_MAP.points[name].region, half_weights)
        for name, distance in nearest_start.items()
        if distance <= reach_units
    }
    point_weights = (
        reachable_weights
        if sum(reachable_weights.values()) > 0
        else dict.fromkeys(start_points, 1.0)
    )
    total_weight = sum(point_weights.values())
    return {name: weight / total_weight for name, weight in point_weights.items()}


def reach_seconds_of(estimate: PositionEstimate, lane: str) -> float | None:
    """Return the soonest a player could be in a lane's middle.

    Args:
        estimate: Their position.
        lane: "top", "mid" or "bot".

    Returns:
        The seconds; None for another word.
    """
    return {
        "top": estimate.reach_top_seconds,
        "mid": estimate.reach_mid_seconds,
        "bot": estimate.reach_bot_seconds,
    }.get(lane)


def _start_points(team: str, clue: PositionClue | None) -> list[str]:
    """Return the points a player was at, or among, at their latest clue.

    Args:
        team: Their team.
        clue: Their latest clue; None without one, when they started in their fountain.

    Returns:
        The points' names.
    """
    if clue is None:
        return [fountain_of(team)]
    if clue.kind not in {"lane", "jungle"} and clue.point_name is not None:
        return [clue.point_name]
    regions = _clue_regions(clue)
    in_regions = [name for name, point in RIFT_MAP.points.items() if point.region in regions]
    return in_regions or [fountain_of(team)]


def _clue_regions(clue: PositionClue) -> frozenset[str]:
    """Return the map's regions a clue that names no single point puts a player in.

    Args:
        clue: The clue: a lane's region, or a team's jungle ("chaos_jungle").

    Returns:
        The regions: the lane, or both halves of the team's jungle.
    """
    if clue.kind != "jungle":
        return frozenset({clue.region})
    team_prefix = clue.region.removesuffix("_jungle")
    return frozenset({f"{team_prefix}_top_jungle", f"{team_prefix}_bot_jungle"})


def _team_region(region: str, team: str) -> str:
    """Return a region of the habits' words ("own_top_jungle") as the map names it.

    Args:
        region: The region, with "own" or "enemy" for a team.
        team: The player's team.

    Returns:
        The map's region.
    """
    own_prefix = TEAM_PREFIX.get(team, "order")
    enemy_prefix = "chaos" if own_prefix == "order" else "order"
    return region.replace("own_", f"{own_prefix}_").replace("enemy_", f"{enemy_prefix}_")


def _half_weight(region: str, half_weights: Mapping[str, float]) -> float:
    """Return how much a habit weighs a region by the half of the map it is in.

    Args:
        region: The map's region.
        half_weights: The weight of each half; empty for none.

    Returns:
        The weight; 1 for a base, which is in no half, or without a habit.
    """
    half = MAP_HALF_BY_REGION.get(region)
    return half_weights.get(half, 1.0) if half is not None else 1.0


def _region_weight(role: str, team: str, region: str) -> float:
    """Return how much a player of a role and team is found in a region.

    Args:
        role: Their role; empty when unknown.
        team: Their team.
        region: The map's region.

    Returns:
        The weight.
    """
    own_prefix = TEAM_PREFIX.get(team, "order")
    if region.endswith("_base"):
        return OWN_BASE_WEIGHT if region.startswith(own_prefix) else ENEMY_BASE_WEIGHT
    habits = {
        _team_region(habit_region, team): weight
        for habit_region, weight in ROLE_HABITS.get(role, {}).items()
    }
    return habits.get(region, OTHER_REGION_WEIGHT)


def _region_label(region: str, ally_team: str) -> str:
    """Return a region in words, from the side of the player on this machine.

    Args:
        region: The map's region.
        ally_team: Their team.

    Returns:
        Such as "bot lane", "their top jungle" or "your base".
    """
    if region in REGION_WORDS:
        return REGION_WORDS[region]
    team_prefix, _, rest = region.partition("_")
    whose = "your" if team_prefix == TEAM_PREFIX.get(ally_team, "order") else "their"
    return f"{whose} {rest.replace('_', ' ')}"


def _reach_seconds(
    start_points: list[str], lane: str, move_speed: float, since_seconds: float
) -> float:
    """Return the soonest a player could be in a lane's middle, walking at full speed.

    Args:
        start_points: Where they were at their latest clue.
        lane: "top", "mid" or "bot".
        move_speed: Their move speed.
        since_seconds: The time since that clue.

    Returns:
        The seconds from now; 0 when they could be there already.
    """
    target = LANE_MIDDLES[lane]
    walk_units = min(RIFT_MAP.distance(start, target) for start in start_points)
    return max(0.0, walk_units / move_speed - since_seconds)
