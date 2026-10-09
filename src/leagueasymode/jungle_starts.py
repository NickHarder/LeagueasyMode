"""Where a jungler starts their first clear, and where they are once it is done.

Read from past games' match timelines (`match_timeline.py`). At the frame nearest 2:00, half a
minute after the camps first spawn, the jungler is at or near their first camp. The start's side
is the half of their own jungle their position falls in, the half that holds their blue buff or
the one that holds their red buff; anywhere else (the enemy's jungle, a lane, the base) says
nothing. At the frame nearest 4:00 a first clear is done, and the jungler is ganking, at the
scuttle crab, or back in their jungle: that side is the half of the whole map they are on, named
for the buff of theirs in it, or mid. Counted over a jungler's recent games, both are how a player
usually plays the first minutes: scouting facts the overlay shows before they happen.
"""

from dataclasses import dataclass
from typing import Final, Literal

from pydantic import JsonValue, ValidationError

from leagueasymode.inference.rift_map import RIFT_MAP, TEAM_PREFIX
from leagueasymode.match_timeline import GameTimeline, TimelinePosition

type StartSide = Literal["blue", "red"]
type FourMinuteSide = Literal["blue", "red", "mid"]
type MapHalf = Literal["top", "bot"]

# The frames read: 2:00 and 4:00, each give or take half a minute.
START_FRAME_MILLISECONDS: Final = 120_000
FOUR_MINUTE_FRAME_MILLISECONDS: Final = 240_000
FRAME_TOLERANCE_MILLISECONDS: Final = 30_000
# The half of the map each of the map's regions is in; the bases are in none.
MAP_HALF_BY_REGION: Final[dict[str, MapHalf | Literal["mid"]]] = {
    "top_lane": "top",
    "top_river": "top",
    "order_top_jungle": "top",
    "chaos_top_jungle": "top",
    "mid_lane": "mid",
    "bot_lane": "bot",
    "bot_river": "bot",
    "order_bot_jungle": "bot",
    "chaos_bot_jungle": "bot",
}
# The match history's team ids.
TEAM_BY_ID: Final = {100: "ORDER", 200: "CHAOS"}


@dataclass(frozen=True)
class JungleStarts:
    """How many of a jungler's recent games started on each side."""

    blue_count: int
    red_count: int

    @property
    def game_count(self) -> int:
        """The games read."""
        return self.blue_count + self.red_count

    @property
    def usual_side(self) -> StartSide | None:
        """The side more games started on; None for an even split or no games."""
        if self.blue_count == self.red_count:
            return None
        return "blue" if self.blue_count > self.red_count else "red"

    @property
    def usual_count(self) -> int:
        """How many games started on the usual side."""
        return max(self.blue_count, self.red_count)


@dataclass(frozen=True)
class FourMinuteSides:
    """How many of a jungler's recent games found them on each side at 4:00."""

    blue_count: int
    red_count: int
    mid_count: int

    @property
    def game_count(self) -> int:
        """The games read."""
        return self.blue_count + self.red_count + self.mid_count

    @property
    def usual_side(self) -> FourMinuteSide | None:
        """The side more games found them on; None for a tie at the top or no games."""
        counts: dict[FourMinuteSide, int] = {
            "blue": self.blue_count,
            "red": self.red_count,
            "mid": self.mid_count,
        }
        most = max(counts.values())
        sides_with_most = [side for side, count in counts.items() if count == most]
        return sides_with_most[0] if most > 0 and len(sides_with_most) == 1 else None

    @property
    def usual_count(self) -> int:
        """How many games found them on the usual side."""
        return max(self.blue_count, self.red_count, self.mid_count)


def start_side(
    timeline_payload: JsonValue | None, participant_id: int, team_id: int
) -> StartSide | None:
    """Return the side of their jungle a player was on at 2:00 in a past game.

    Args:
        timeline_payload: The game's match timeline, as the League client serves it.
        participant_id: The player's participant id in that game.
        team_id: Their team's id in that game: 100 for blue, 200 for red.

    Returns:
        "blue" or "red"; None without a frame near 2:00, without their position, or when they
        were outside their own jungle.
    """
    team = TEAM_BY_ID.get(team_id)
    position = _position_at(timeline_payload, participant_id, START_FRAME_MILLISECONDS)
    if team is None or position is None:
        return None
    region = RIFT_MAP.nearest_point(position.x, position.y).region
    team_prefix = TEAM_PREFIX[team]
    if region == RIFT_MAP.points[f"{team_prefix}_blue_buff"].region:
        return "blue"
    if region == RIFT_MAP.points[f"{team_prefix}_red_buff"].region:
        return "red"
    return None


def four_minute_side(
    timeline_payload: JsonValue | None, participant_id: int, team_id: int
) -> FourMinuteSide | None:
    """Return the side of the map a player was on at 4:00 in a past game.

    Args:
        timeline_payload: The game's match timeline, as the League client serves it.
        participant_id: The player's participant id in that game.
        team_id: Their team's id in that game: 100 for blue, 200 for red.

    Returns:
        "blue" or "red" for the half of the map that holds that buff of theirs, "mid" for the mid
        lane; None without a frame near 4:00, without their position, or in a base.
    """
    team = TEAM_BY_ID.get(team_id)
    position = _position_at(timeline_payload, participant_id, FOUR_MINUTE_FRAME_MILLISECONDS)
    if team is None or position is None:
        return None
    half = MAP_HALF_BY_REGION.get(RIFT_MAP.nearest_point(position.x, position.y).region)
    if half is None or half == "mid":
        return half
    return "blue" if start_half("blue", team) == half else "red"


def four_minute_half(side: FourMinuteSide, team: str) -> MapHalf | Literal["mid"] | None:
    """Return the half of the map a four-minute side is for the team a jungler plays this game.

    Args:
        side: The side: one of their buffs' halves, or mid.
        team: The jungler's team this game, "ORDER" or "CHAOS".

    Returns:
        "top", "bot" or "mid"; None for a buff's side when the team is not known.
    """
    return "mid" if side == "mid" else start_half(side, team)


def start_half(side: StartSide, team: str) -> MapHalf | None:
    """Return the half of the map a start is on for the team a jungler plays this game.

    The blue team's blue buff is in its top jungle and its red buff in its bottom jungle; the red
    team's are the other way round.

    Args:
        side: The buff the start is at.
        team: The jungler's team this game, "ORDER" or "CHAOS".

    Returns:
        "top" or "bot"; None when the team is not known.
    """
    team_prefix = TEAM_PREFIX.get(team)
    if team_prefix is None:
        return None
    region = RIFT_MAP.points[f"{team_prefix}_{side}_buff"].region
    return "top" if region == f"{team_prefix}_top_jungle" else "bot"


def _position_at(
    timeline_payload: JsonValue | None, participant_id: int, at_milliseconds: int
) -> TimelinePosition | None:
    """Return where a participant was at the frame nearest a time.

    Args:
        timeline_payload: The game's match timeline.
        participant_id: The participant.
        at_milliseconds: The time, from the game's start.

    Returns:
        The position; None when the timeline cannot be read, has no frame within half a minute
        of the time, or does not place the participant there.
    """
    try:
        timeline = GameTimeline.model_validate(timeline_payload)
    except ValidationError:
        return None
    frames_near = [
        frame
        for frame in timeline.frames
        if abs(frame.timestamp_milliseconds - at_milliseconds) <= FRAME_TOLERANCE_MILLISECONDS
    ]
    if not frames_near:
        return None
    nearest_frame = min(
        frames_near, key=lambda frame: abs(frame.timestamp_milliseconds - at_milliseconds)
    )
    return next(
        (
            participant_frame.position
            for participant_frame in nearest_frame.participant_frames
            if participant_frame.participant_id == participant_id
        ),
        None,
    )
