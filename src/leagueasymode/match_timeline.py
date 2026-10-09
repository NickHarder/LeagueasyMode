"""The match timeline the League client serves after a game: every player each minute, and events.

`/lol-match-history/v1/game-timelines/<game id>` holds a frame about once a minute, each with every
participant's position, gold and experience, and the events between frames: purchases, kills,
wards, epic monsters. The scoring harness reads the game's own as its ground truth; the player
lookups read past games' to see where a jungler started, and each player's creep score and gold
at 10:00.
"""

from typing import Final

from pydantic import Field, JsonValue, ValidationError, field_validator

from leagueasymode.game_state import RiotPayloadModel


class TimelinePosition(RiotPayloadModel):
    """A place on the map, in game units."""

    x: int = 0  # ai-kit: ignore-name  the timeline's own name for the coordinate
    y: int = 0  # ai-kit: ignore-name  as above


class TimelineParticipantFrame(RiotPayloadModel):
    """One participant's gold, experience and position at one frame of the match timeline."""

    participant_id: int = Field(default=0, alias="participantId")
    position: TimelinePosition | None = None
    current_gold: int = Field(default=0, alias="currentGold")
    total_gold: int = Field(default=0, alias="totalGold")
    experience: int = Field(default=0, alias="xp")
    minions_killed: int = Field(default=0, alias="minionsKilled")
    jungle_minions_killed: int = Field(default=0, alias="jungleMinionsKilled")

    @property
    def creep_score(self) -> int:
        """Lane minions and jungle monsters killed, as the scoreboard counts them."""
        return self.minions_killed + self.jungle_minions_killed


class TimelineEvent(RiotPayloadModel):
    """One event of the match timeline: a purchase or a kill, among others."""

    event_type: str = Field(default="", alias="type")
    timestamp_milliseconds: int = Field(default=0, alias="timestamp")
    # The buyer of a purchase, and what they bought.
    participant_id: int = Field(default=0, alias="participantId")
    item_id: int = Field(default=0, alias="itemId")
    # The champion a kill killed, who killed them (0 for a turret or a monster), who helped,
    # and where.
    victim_id: int = Field(default=0, alias="victimId")
    killer_id: int = Field(default=0, alias="killerId")
    assisting_participant_ids: list[int] = Field(
        default_factory=list, alias="assistingParticipantIds"
    )
    position: TimelinePosition | None = None
    # The placer of a ward, and its kind.
    creator_id: int = Field(default=0, alias="creatorId")
    ward_type: str = Field(default="", alias="wardType")
    # An epic monster's kill: the team that took it, and the monster.
    killer_team_id: int = Field(default=0, alias="killerTeamId")
    monster_type: str = Field(default="", alias="monsterType")
    monster_sub_type: str = Field(default="", alias="monsterSubType")


class TimelineFrame(RiotPayloadModel):
    """One frame of the match timeline: every participant, about once a minute."""

    timestamp_milliseconds: int = Field(default=0, alias="timestamp")
    participant_frames: list[TimelineParticipantFrame] = Field(
        default_factory=list, alias="participantFrames"
    )
    events: list[TimelineEvent] = Field(default_factory=list)

    @field_validator("participant_frames", mode="before")
    @classmethod
    def _frames_as_a_list(cls, value: object) -> object:
        """Take the participants' frames keyed by participant id, as the timeline sends them.

        Args:
            value: The frames, keyed by id or listed.

        Returns:
            The frames, listed.
        """
        return list(value.values()) if isinstance(value, dict) else value


class GameTimeline(RiotPayloadModel):
    """The match timeline from the League client, after the game."""

    frames: list[TimelineFrame] = Field(default_factory=list)


# A frame within this of a time stands for it: frames come about once a minute.
FRAME_TOLERANCE_MILLISECONDS: Final = 30_000


def participant_frame_at(
    timeline_payload: JsonValue | None, participant_id: int, at_milliseconds: int
) -> TimelineParticipantFrame | None:
    """Return a participant's frame nearest a time of a match timeline.

    Args:
        timeline_payload: The game's match timeline, as the League client serves it.
        participant_id: The participant.
        at_milliseconds: The time, from the game's start.

    Returns:
        The frame; None when the timeline cannot be read, has no frame within half a minute of
        the time, or does not hold the participant there.
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
            participant_frame
            for participant_frame in nearest_frame.participant_frames
            if participant_frame.participant_id == participant_id
        ),
        None,
    )
