"""Where a jungler starts (phase 9.1): blue buff's side or red's, from a past game's timeline."""

from typing import Final

from pydantic import JsonValue

from leagueasymode.inference.rift_map import RIFT_MAP
from leagueasymode.jungle_starts import (
    FourMinuteSides,
    JungleStarts,
    four_minute_half,
    four_minute_side,
    start_half,
    start_side,
)

PARTICIPANT_ID: Final = 7
FOUR_MINUTES: Final = 240_000
BLUE_TEAM: Final = 100
RED_TEAM: Final = 200


def timeline_with(
    position: tuple[float, float] | None, *, at_milliseconds: int = 120_000
) -> JsonValue:
    frames: list[JsonValue] = [
        {"timestamp": 0, "participantFrames": {}},
        {"timestamp": 60_000, "participantFrames": {}},
    ]
    participant: dict[str, JsonValue] = {"participantId": PARTICIPANT_ID}
    if position is not None:
        participant["position"] = {"x": round(position[0]), "y": round(position[1])}
    frames.append(
        {"timestamp": at_milliseconds, "participantFrames": {str(PARTICIPANT_ID): participant}}
    )
    return {"frames": frames}


def point(name: str) -> tuple[float, float]:
    map_point = RIFT_MAP.points[name]
    return map_point.x_position, map_point.y_position


def test_a_blue_side_jungler_at_their_blue_buff_started_blue() -> None:
    assert start_side(timeline_with(point("order_blue_buff")), PARTICIPANT_ID, BLUE_TEAM) == "blue"


def test_a_blue_side_jungler_at_their_red_buff_started_red() -> None:
    assert start_side(timeline_with(point("order_red_buff")), PARTICIPANT_ID, BLUE_TEAM) == "red"


def test_a_red_side_jungler_is_read_against_their_own_buffs() -> None:
    assert start_side(timeline_with(point("chaos_blue_buff")), PARTICIPANT_ID, RED_TEAM) == "blue"
    assert start_side(timeline_with(point("chaos_red_buff")), PARTICIPANT_ID, RED_TEAM) == "red"


def test_near_a_camp_next_to_a_buff_counts_as_that_buffs_side() -> None:
    gromp_x, gromp_y = point("order_gromp")
    assert start_side(timeline_with((gromp_x, gromp_y)), PARTICIPANT_ID, BLUE_TEAM) == "blue"


def test_away_from_their_jungle_at_two_minutes_says_nothing() -> None:
    # In the enemy's jungle, invading, or in a lane: neither side of their own jungle.
    assert start_side(timeline_with(point("chaos_red_buff")), PARTICIPANT_ID, BLUE_TEAM) is None
    assert start_side(timeline_with(point("order_fountain")), PARTICIPANT_ID, BLUE_TEAM) is None


def test_without_a_frame_near_two_minutes_or_a_position_there_is_no_start() -> None:
    assert (
        start_side(
            timeline_with(point("order_blue_buff"), at_milliseconds=300_000),
            PARTICIPANT_ID,
            BLUE_TEAM,
        )
        is None
    )
    assert start_side(timeline_with(None), PARTICIPANT_ID, BLUE_TEAM) is None
    assert start_side(timeline_with(point("order_blue_buff")), 3, BLUE_TEAM) is None
    assert start_side({"message": "not found"}, PARTICIPANT_ID, BLUE_TEAM) is None
    assert start_side(timeline_with(point("order_blue_buff")), PARTICIPANT_ID, 0) is None


def test_the_usual_side_is_the_one_most_games_started_on() -> None:
    starts = JungleStarts(blue_count=1, red_count=4)
    assert starts.game_count == 5
    assert starts.usual_side == "red"
    assert starts.usual_count == 4


def test_an_even_split_has_no_usual_side() -> None:
    starts = JungleStarts(blue_count=2, red_count=2)
    assert starts.usual_side is None


def test_a_start_is_on_the_top_or_bottom_half_by_the_team_played_this_game() -> None:
    # The blue team's blue buff is in its top jungle, the red team's in its bottom jungle.
    assert start_half("blue", "ORDER") == "top"
    assert start_half("red", "ORDER") == "bot"
    assert start_half("blue", "CHAOS") == "bot"
    assert start_half("red", "CHAOS") == "top"
    assert start_half("red", "") is None


def at_four_minutes(point_name: str, team_id: int) -> str | None:
    return four_minute_side(
        timeline_with(point(point_name), at_milliseconds=FOUR_MINUTES), PARTICIPANT_ID, team_id
    )


def test_at_four_minutes_a_jungler_is_on_the_side_of_one_of_their_buffs_or_mid() -> None:
    # The blue team's top half holds its blue buff; the red team's top half holds its red buff.
    assert at_four_minutes("top_river_scuttle", BLUE_TEAM) == "blue"
    assert at_four_minutes("order_bot_lane_2", BLUE_TEAM) == "red"
    assert at_four_minutes("top_river_scuttle", RED_TEAM) == "red"
    assert at_four_minutes("chaos_blue_buff", RED_TEAM) == "blue"
    assert at_four_minutes("mid_center", BLUE_TEAM) == "mid"


def test_in_a_base_or_without_a_frame_near_four_minutes_there_is_no_side() -> None:
    assert at_four_minutes("order_fountain", BLUE_TEAM) is None
    assert (
        four_minute_side(timeline_with(point("top_river_scuttle")), PARTICIPANT_ID, BLUE_TEAM)
        is None
    )


def test_the_usual_four_minute_side_is_the_one_most_games_were_on() -> None:
    sides = FourMinuteSides(blue_count=1, red_count=0, mid_count=3)
    assert (sides.game_count, sides.usual_side, sides.usual_count) == (4, "mid", 3)
    assert FourMinuteSides(blue_count=2, red_count=2, mid_count=0).usual_side is None


def test_a_four_minute_side_is_a_half_of_the_map_by_the_team_played_this_game() -> None:
    assert four_minute_half("blue", "ORDER") == "top"
    assert four_minute_half("blue", "CHAOS") == "bot"
    assert four_minute_half("mid", "CHAOS") == "mid"
    assert four_minute_half("red", "") is None
