import math

import pytest

from leagueasymode.inference.rift_map import (
    MAP_CENTER,
    RIFT_MAP,
    fountain_of,
    mirrored_name,
    role_point_of,
)


def test_every_point_has_its_mirror_turned_about_the_center() -> None:
    center_x, center_y = MAP_CENTER
    for point in RIFT_MAP.points.values():
        mirror = RIFT_MAP.points[mirrored_name(point.name)]
        assert mirror.x_position == pytest.approx(2 * center_x - point.x_position)
        assert mirror.y_position == pytest.approx(2 * center_y - point.y_position)
        assert mirror.region == mirrored_name(point.region)


def test_every_point_can_be_walked_to_from_either_fountain() -> None:
    for team in ("ORDER", "CHAOS"):
        assert set(RIFT_MAP.distances_from(fountain_of(team))) == set(RIFT_MAP.points)


def test_no_path_jumps_further_than_a_few_seconds_walk() -> None:
    for name in RIFT_MAP.points:
        assert all(length < 3000 for _, length in RIFT_MAP.neighbours(name))


def test_both_teams_walk_the_same_distances_to_their_mirrored_places() -> None:
    for role in ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", ""):
        order_distance = RIFT_MAP.distance(fountain_of("ORDER"), role_point_of("ORDER", role))
        chaos_distance = RIFT_MAP.distance(
            fountain_of("CHAOS"), mirrored_name(role_point_of("ORDER", role))
        )
        assert order_distance == pytest.approx(chaos_distance)


def test_the_way_to_each_lane_is_about_the_lanes_length() -> None:
    def walk_to(role: str) -> float:
        return RIFT_MAP.distance(fountain_of("ORDER"), role_point_of("ORDER", role))

    # A side lane's outer turret is about 10,500 units' walk from the fountain, mid's about 8,000.
    assert 9500 < walk_to("TOP") < 11500
    assert 9500 < walk_to("BOTTOM") < 11500
    assert 7000 < walk_to("MIDDLE") < 9000
    assert walk_to("MIDDLE") < walk_to("TOP")


def test_a_walk_is_never_shorter_than_the_straight_line() -> None:
    order_fountain = RIFT_MAP.points[fountain_of("ORDER")]
    for name, walked in RIFT_MAP.distances_from(order_fountain.name).items():
        point = RIFT_MAP.points[name]
        straight = math.hypot(
            point.x_position - order_fountain.x_position,
            point.y_position - order_fountain.y_position,
        )
        assert walked >= straight - 1e-6


def test_the_nearest_point_names_the_place() -> None:
    assert RIFT_MAP.nearest_point(1000.0, 10400.0).name == "order_top_outer_turret"
    assert RIFT_MAP.nearest_point(9900.0, 4400.0).name == "dragon_pit"
    assert RIFT_MAP.points["chaos_blue_buff"].region == "chaos_bot_jungle"
    assert RIFT_MAP.points["baron_pit"].region == "top_river"
