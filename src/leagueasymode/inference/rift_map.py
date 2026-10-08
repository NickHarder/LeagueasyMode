"""The map of Summoner's Rift: walkable points, their regions, and the time it takes between them.

A hand-built graph in the game's coordinates (x to the right, y up, from the blue team's corner,
about 14,800 units a side): the fountains and bases, each lane with its turrets, every jungle camp,
the river with its scuttle crabs, Dragon's and Baron's pits, and paths between them that follow
where a champion can walk. The Rift is point-symmetric about its center, so only the blue team's
(ORDER's) half is written down; the red team's (CHAOS's) is that half turned half a turn, with
"order" and "chaos", "top" and "bot", and Dragon and Baron swapped in every name.

The coordinates are from memory of the map, to within a few hundred units; the timeline's
positions of the first recordings check them. Travel is along straight segments between points,
so it is a little shorter than a champion's real path around the walls.
"""

import heapq
import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from typing import Final

# The point the map turns about to make its red half.
MAP_CENTER: Final = (7400.0, 7400.0)
MIRRORED_NAME_PARTS: Final = {
    "order": "chaos",
    "chaos": "order",
    "top": "bot",
    "bot": "top",
    "dragon": "baron",
    "baron": "dragon",
}
NAME_SEPARATOR: Final = "_"
TEAM_PREFIX: Final = {"ORDER": "order", "CHAOS": "chaos"}
# Where a player of each role plays, as a point of their team's half: their lane's outer turret,
# or the middle of their jungle.
ROLE_POINTS: Final = {
    "TOP": "top_outer_turret",
    "JUNGLE": "red_buff",
    "MIDDLE": "mid_outer_turret",
    "BOTTOM": "bot_outer_turret",
    "UTILITY": "bot_outer_turret",
}
UNKNOWN_ROLE_POINT: Final = "mid_outer_turret"

# The blue team's half: (name, x, y, region). A name with no team in it is shared ground: the
# lanes' far corners, the river and the pits, whose mirror is the other corner, river or pit.
ORDER_HALF_POINTS: Final[tuple[tuple[str, float, float, str], ...]] = (
    ("order_fountain", 400, 420, "order_base"),
    ("order_nexus", 1550, 1650, "order_base"),
    ("order_top_inhibitor", 1170, 3570, "order_base"),
    ("order_mid_inhibitor", 3200, 3200, "order_base"),
    ("order_bot_inhibitor", 3450, 1250, "order_base"),
    # The top lane, from the base to its far corner.
    ("order_top_inhibitor_turret", 1170, 4290, "top_lane"),
    ("order_top_lane_1", 1250, 5400, "top_lane"),
    ("order_top_inner_turret", 1510, 6640, "top_lane"),
    ("order_top_lane_2", 1300, 7800, "top_lane"),
    ("order_top_lane_3", 1100, 9000, "top_lane"),
    ("order_top_outer_turret", 980, 10440, "top_lane"),
    ("order_top_lane_4", 1150, 11700, "top_lane"),
    ("top_lane_corner", 1800, 13100, "top_lane"),
    # The bottom lane, from the base to just short of its far corner (the top corner's mirror).
    ("order_bot_inhibitor_turret", 4280, 1250, "bot_lane"),
    ("order_bot_lane_1", 5500, 1350, "bot_lane"),
    ("order_bot_inner_turret", 6900, 1460, "bot_lane"),
    ("order_bot_lane_2", 8100, 1200, "bot_lane"),
    ("order_bot_lane_3", 9300, 1100, "bot_lane"),
    ("order_bot_outer_turret", 10500, 1030, "bot_lane"),
    ("order_bot_lane_4", 11800, 1200, "bot_lane"),
    # The middle lane, from the base to the map's center.
    ("order_mid_inhibitor_turret", 3650, 3700, "mid_lane"),
    ("order_mid_inner_turret", 5050, 4800, "mid_lane"),
    ("order_mid_lane_1", 5450, 5600, "mid_lane"),
    ("order_mid_outer_turret", 5850, 6400, "mid_lane"),
    ("order_mid_lane_2", 6600, 6900, "mid_lane"),
    ("mid_center", 7400, 7400, "mid_lane"),
    # The top side of the river, from the top lane to the center, and Baron's pit.
    ("top_river_1", 2900, 11700, "top_river"),
    ("top_river_scuttle", 4400, 9600, "top_river"),
    ("top_river_2", 5600, 9000, "top_river"),
    ("top_river_3", 6600, 8100, "top_river"),
    ("baron_pit", 4950, 10400, "top_river"),
    # The blue team's jungle above the middle lane: Gromp, blue buff, the wolves.
    ("order_gromp", 2100, 8400, "order_top_jungle"),
    ("order_blue_buff", 3800, 7950, "order_top_jungle"),
    ("order_wolves", 3800, 6500, "order_top_jungle"),
    ("order_top_jungle_entrance", 3300, 5300, "order_top_jungle"),
    ("order_top_jungle_river_path", 4700, 8700, "order_top_jungle"),
    # Its jungle below the middle lane: the raptors, red buff, the krugs.
    ("order_raptors", 7000, 5400, "order_bot_jungle"),
    ("order_red_buff", 7800, 4100, "order_bot_jungle"),
    ("order_krugs", 8400, 2700, "order_bot_jungle"),
    ("order_bot_jungle_entrance", 5700, 3300, "order_bot_jungle"),
    ("order_bot_jungle_river_path", 9000, 4800, "order_bot_jungle"),
)
# Walkable paths between two points of the blue half, or from it to a point of the red half named
# by its own name; each path's mirror is added with the red half.
ORDER_HALF_PATHS: Final[tuple[tuple[str, str], ...]] = (
    ("order_fountain", "order_nexus"),
    ("order_nexus", "order_top_inhibitor"),
    ("order_nexus", "order_mid_inhibitor"),
    ("order_nexus", "order_bot_inhibitor"),
    ("order_top_inhibitor", "order_top_inhibitor_turret"),
    ("order_mid_inhibitor", "order_mid_inhibitor_turret"),
    ("order_bot_inhibitor", "order_bot_inhibitor_turret"),
    ("order_top_inhibitor_turret", "order_top_lane_1"),
    ("order_top_lane_1", "order_top_inner_turret"),
    ("order_top_inner_turret", "order_top_lane_2"),
    ("order_top_lane_2", "order_top_lane_3"),
    ("order_top_lane_3", "order_top_outer_turret"),
    ("order_top_outer_turret", "order_top_lane_4"),
    ("order_top_lane_4", "top_lane_corner"),
    ("order_bot_inhibitor_turret", "order_bot_lane_1"),
    ("order_bot_lane_1", "order_bot_inner_turret"),
    ("order_bot_inner_turret", "order_bot_lane_2"),
    ("order_bot_lane_2", "order_bot_lane_3"),
    ("order_bot_lane_3", "order_bot_outer_turret"),
    ("order_bot_outer_turret", "order_bot_lane_4"),
    ("order_bot_lane_4", "bot_lane_corner"),
    ("order_mid_inhibitor_turret", "order_mid_inner_turret"),
    ("order_mid_inner_turret", "order_mid_lane_1"),
    ("order_mid_lane_1", "order_mid_outer_turret"),
    ("order_mid_outer_turret", "order_mid_lane_2"),
    ("order_mid_lane_2", "mid_center"),
    ("top_lane_corner", "top_river_1"),
    ("top_river_1", "top_river_scuttle"),
    ("top_river_1", "baron_pit"),
    ("baron_pit", "top_river_scuttle"),
    ("top_river_scuttle", "top_river_2"),
    ("top_river_2", "top_river_3"),
    ("top_river_3", "mid_center"),
    ("order_top_lane_2", "order_gromp"),
    ("order_gromp", "order_blue_buff"),
    ("order_blue_buff", "order_wolves"),
    ("order_blue_buff", "order_top_jungle_river_path"),
    ("order_top_jungle_river_path", "top_river_scuttle"),
    ("order_top_jungle_river_path", "top_river_2"),
    ("order_wolves", "order_top_jungle_entrance"),
    ("order_wolves", "order_mid_lane_1"),
    ("order_top_jungle_entrance", "order_mid_inhibitor_turret"),
    ("order_top_jungle_entrance", "order_top_lane_1"),
    ("order_raptors", "order_mid_lane_2"),
    ("order_raptors", "order_red_buff"),
    ("order_raptors", "order_bot_jungle_river_path"),
    ("order_red_buff", "order_krugs"),
    ("order_red_buff", "order_bot_jungle_entrance"),
    ("order_red_buff", "order_bot_jungle_river_path"),
    ("order_krugs", "order_bot_lane_2"),
    ("order_bot_jungle_entrance", "order_mid_inhibitor_turret"),
    ("order_bot_jungle_entrance", "order_bot_lane_1"),
    ("order_bot_jungle_river_path", "bot_river_2"),
    ("order_bot_jungle_river_path", "bot_river_scuttle"),
)


@dataclass(frozen=True)
class MapPoint:
    """One walkable point of the map."""

    name: str
    x_position: float
    y_position: float
    # Such as "top_lane", "order_bot_jungle", "top_river" or "chaos_base".
    region: str


class RiftMap:
    """The walkable points of Summoner's Rift and the paths between them."""

    def __init__(self, points: list[MapPoint], paths: list[tuple[str, str]]) -> None:
        """Index the points and their paths.

        Args:
            points: Every point.
            paths: Every walkable path, by its two points' names, each way.
        """
        self.points: Final[Mapping[str, MapPoint]] = {point.name: point for point in points}
        neighbours: dict[str, list[tuple[str, float]]] = {point.name: [] for point in points}
        for first_name, second_name in paths:
            length = _distance_between(self.points[first_name], self.points[second_name])
            neighbours[first_name].append((second_name, length))
            neighbours[second_name].append((first_name, length))
        self._neighbours: Final[Mapping[str, list[tuple[str, float]]]] = neighbours

    def neighbours(self, name: str) -> list[tuple[str, float]]:
        """Return the points one path from a point, with each path's length.

        Args:
            name: The point.

        Returns:
            The neighbours' names and the lengths, in game units.
        """
        return list(self._neighbours[name])

    def distance(self, from_name: str, to_name: str) -> float:
        """Return the length of the shortest walk between two points.

        Args:
            from_name: Where the walk starts.
            to_name: Where it ends.

        Returns:
            The length, in game units; infinite when no walk joins them.
        """
        return self.distances_from(from_name).get(to_name, math.inf)

    def distances_from(self, from_name: str) -> Mapping[str, float]:
        """Return the shortest walk from a point to every point (Dijkstra's algorithm).

        Args:
            from_name: Where the walks start.

        Returns:
            Each reachable point's distance, in game units.
        """
        return _shortest_distances(self, from_name)

    def nearest_point(self, x_position: float, y_position: float) -> MapPoint:
        """Return the point of the map nearest a place.

        Args:
            x_position: The place's x, in game units.
            y_position: Its y.

        Returns:
            The point.
        """
        return min(
            self.points.values(),
            key=lambda point: math.hypot(
                point.x_position - x_position, point.y_position - y_position
            ),
        )


def region_center(region: str) -> tuple[float, float]:
    """Return the middle of a region of the map: the mean of its points.

    Args:
        region: The map's region.

    Returns:
        The middle's x and y, in game units; the map's center for a region with no point.
    """
    points = [point for point in RIFT_MAP.points.values() if point.region == region]
    if not points:
        return MAP_CENTER
    return (
        sum(point.x_position for point in points) / len(points),
        sum(point.y_position for point in points) / len(points),
    )


def fountain_of(team: str) -> str:
    """Return the name of a team's fountain.

    Args:
        team: "ORDER" or "CHAOS".

    Returns:
        The point's name.
    """
    return f"{TEAM_PREFIX.get(team, 'order')}_fountain"


def role_point_of(team: str, role: str) -> str:
    """Return the point where a player of a team plays their role.

    Args:
        team: "ORDER" or "CHAOS".
        role: The role as the game names positions; empty when unknown, taken as mid.

    Returns:
        The point's name.
    """
    return f"{TEAM_PREFIX.get(team, 'order')}_{ROLE_POINTS.get(role, UNKNOWN_ROLE_POINT)}"


def mirrored_name(name: str) -> str:
    """Return the name of a point's mirror on the other half of the map.

    Args:
        name: The point's name, or a region's.

    Returns:
        The mirror's: teams, top and bottom, and Dragon and Baron swapped.
    """
    return NAME_SEPARATOR.join(
        MIRRORED_NAME_PARTS.get(part, part) for part in name.split(NAME_SEPARATOR)
    )


def build_rift_map() -> RiftMap:
    """Return the whole map: the blue team's half as written, and its mirror.

    Returns:
        The map.
    """
    center_x, center_y = MAP_CENTER
    order_points = [MapPoint(name, x, y, region) for name, x, y, region in ORDER_HALF_POINTS]
    chaos_points = [
        MapPoint(
            mirrored_name(point.name),
            2 * center_x - point.x_position,
            2 * center_y - point.y_position,
            mirrored_name(point.region),
        )
        for point in order_points
        if mirrored_name(point.name) != point.name
    ]
    paths = [
        *ORDER_HALF_PATHS,
        *((mirrored_name(first), mirrored_name(second)) for first, second in ORDER_HALF_PATHS),
    ]
    return RiftMap([*order_points, *chaos_points], sorted(set(paths)))


@cache
def _shortest_distances(rift_map: RiftMap, from_name: str) -> Mapping[str, float]:
    """Return the shortest walk from a point to every point, kept for the next ask.

    Args:
        rift_map: The map.
        from_name: Where the walks start.

    Returns:
        Each reachable point's distance, in game units.
    """
    distances: dict[str, float] = {from_name: 0.0}
    frontier = [(0.0, from_name)]
    while frontier:
        walked, name = heapq.heappop(frontier)
        if walked > distances.get(name, math.inf):
            continue
        for neighbour, length in rift_map.neighbours(name):
            if walked + length < distances.get(neighbour, math.inf):
                distances[neighbour] = walked + length
                heapq.heappush(frontier, (walked + length, neighbour))
    return distances


def _distance_between(first: MapPoint, second: MapPoint) -> float:
    """Return the straight distance between two points.

    Args:
        first: One point.
        second: The other.

    Returns:
        The distance, in game units.
    """
    return math.hypot(first.x_position - second.x_position, first.y_position - second.y_position)


RIFT_MAP: Final = build_rift_map()
