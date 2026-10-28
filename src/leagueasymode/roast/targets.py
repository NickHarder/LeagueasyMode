"""Whom a case roasts: the whole team, one lane, one player, or the enemy team.

Any of the game's ten players can be a target after the game (phase 11.3), friends or not.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from leagueasymode.roast.players import RoastPlayer

POSITIONS: Final = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
PARTICIPANT_IDS: Final = range(1, 11)


class Target(BaseModel):
    """A case's target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["team", "enemy", "lane", "player"]
    position: str | None = None
    participant_id: int | None = None

    @property
    def is_narrow(self) -> bool:
        """Say whether the target is one lane or one player rather than a whole team.

        Returns:
            True for a lane or a player.
        """
        return self.kind in ("lane", "player")


def parse_target(typed_text: str) -> Target:
    """Read a target from its text.

    Args:
        typed_text: "team", "enemy", "lane:<POSITION>" or "player:<participant id>".

    Returns:
        The target.

    Raises:
        ValueError: If the text is not a target.
    """
    kind, _, value = typed_text.partition(":")
    if kind in ("team", "enemy") and not value:
        return Target(kind="team" if kind == "team" else "enemy")
    if kind == "lane" and value in POSITIONS:
        return Target(kind="lane", position=value)
    if kind == "player" and value.isdigit() and int(value) in PARTICIPANT_IDS:
        return Target(kind="player", participant_id=int(value))
    message = f"{typed_text!r} is not a target: use team, enemy, lane:<position> or player:<1-10>"
    raise ValueError(message)


def subjects_for_target(
    players: list[RoastPlayer],
    defendant: RoastPlayer,
    target: Target,
    *,
    spare_friends: bool = False,
) -> dict[str, list[RoastPlayer]]:
    """Return who each template subject may be, for a target.

    Args:
        players: Every player of the game.
        defendant: The player whose case it is.
        target: The target.
        spare_friends: Leave friends on the defendant's team out of a team roast (the Mutual
            Defense Pact); off by default here, since teasing friends is the point. A lane or player
            chosen on purpose is roasted either way.

    Returns:
        The players for "ally", "enemy" and "defendant".
    """
    allies = [
        player
        for player in players
        if player.team_id == defendant.team_id and player.participant_id != defendant.participant_id
    ]
    enemies = [player for player in players if player.team_id != defendant.team_id]
    if target.kind == "enemy":
        return {"ally": [], "enemy": enemies, "defendant": []}
    if target.kind == "lane":
        in_lane = [player for player in players if player.position == target.position]
        return _split(in_lane, allies, enemies, defendant)
    if target.kind == "player":
        chosen = [player for player in players if player.participant_id == target.participant_id]
        return _split(chosen, allies, enemies, defendant)
    team_allies = [ally for ally in allies if not (spare_friends and ally.is_friend)]
    return {"ally": team_allies, "enemy": [], "defendant": [defendant]}


def _split(
    chosen: list[RoastPlayer],
    allies: list[RoastPlayer],
    enemies: list[RoastPlayer],
    defendant: RoastPlayer,
) -> dict[str, list[RoastPlayer]]:
    """Sort chosen players into allies, enemies and the defendant.

    Args:
        chosen: The players the target names.
        allies: The defendant's teammates.
        enemies: The other team.
        defendant: The player whose case it is.

    Returns:
        The chosen players for "ally", "enemy" and "defendant".
    """
    return {
        "ally": [player for player in chosen if player in allies],
        "enemy": [player for player in chosen if player in enemies],
        "defendant": [player for player in chosen if player == defendant],
    }
