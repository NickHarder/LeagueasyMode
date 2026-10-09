"""Where a jungler starts their first clear: blue buff's side of their jungle or red buff's.

Read from past games' match timelines (`match_timeline.py`): at the frame nearest 2:00, half a
minute after the camps first spawn, the jungler is at or near their first camp. The side is the
half of their own jungle their position falls in, the half that holds their blue buff or the one
that holds their red buff; anywhere else (the enemy's jungle, a lane, the base) says nothing.
Counted over a jungler's recent games, it is how a player usually starts: a scouting fact the
overlay shows before the camps spawn.
"""

from dataclasses import dataclass
from typing import Final, Literal

from pydantic import JsonValue, ValidationError

from leagueasymode.inference.rift_map import RIFT_MAP, TEAM_PREFIX
from leagueasymode.match_timeline import GameTimeline, TimelinePosition

type StartSide = Literal["blue", "red"]
type MapHalf = Literal["top", "bot"]

# The frame read: 2:00, give or take half a minute.
START_FRAME_MILLISECONDS: Final = 120_000
START_FRAME_TOLERANCE_MILLISECONDS: Final = 30_000
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
    position = _position_at_start(timeline_payload, participant_id)
    if team is None or position is None:
        return None
    region = RIFT_MAP.nearest_point(position.x, position.y).region
    team_prefix = TEAM_PREFIX[team]
    if region == RIFT_MAP.points[f"{team_prefix}_blue_buff"].region:
        return "blue"
    if region == RIFT_MAP.points[f"{team_prefix}_red_buff"].region:
        return "red"
    return None


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


def _position_at_start(
    timeline_payload: JsonValue | None, participant_id: int
) -> TimelinePosition | None:
    """Return where a participant was at the frame nearest 2:00.

    Args:
        timeline_payload: The game's match timeline.
        participant_id: The participant.

    Returns:
        The position; None when the timeline cannot be read, has no frame near 2:00, or does
        not place the participant there.
    """
    try:
        timeline = GameTimeline.model_validate(timeline_payload)
    except ValidationError:
        return None
    frames_near_start = [
        frame
        for frame in timeline.frames
        if abs(frame.timestamp_milliseconds - START_FRAME_MILLISECONDS)
        <= START_FRAME_TOLERANCE_MILLISECONDS
    ]
    if not frames_near_start:
        return None
    start_frame = min(
        frames_near_start,
        key=lambda frame: abs(frame.timestamp_milliseconds - START_FRAME_MILLISECONDS),
    )
    return next(
        (
            participant_frame.position
            for participant_frame in start_frame.participant_frames
            if participant_frame.participant_id == participant_id
        ),
        None,
    )
