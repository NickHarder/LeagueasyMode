"""Turret and inhibitor names, as the game's feed gives them.

The game names a turret `Turret_TOrder_L0_P3_3795288474_0` and an inhibitor
`Inhib_TChaos_L1_P1_2432143522_0`: the team that owns it, its lane and its place in the lane. Read
against the match timelines of the owner's games of 2026-10-29, whose `BUILDING_KILL` events name
each one's lane and tier at the same second: lane 0 is bot, 1 mid and 2 top; place 3 is the outer
turret, 2 the inner, 1 the inhibitor turret (and the inhibitor), 4 and 5 the nexus turrets, which
stand in lane 1. ARAM's single lane is lane 1.

The older names that open-source readers of the game's API give (`Turret_T1_L_03_A`,
`Barracks_T1_L1`) never came in a recorded game; they are still read, the way they were, so that
nothing that once read them stops.
"""

import re
from dataclasses import dataclass
from typing import Final, Literal

type Team = Literal["ORDER", "CHAOS"]
type Lane = Literal["top", "mid", "bot"]
type TurretTier = Literal["outer", "inner", "inhibitor", "nexus"]

TEAM_BY_NAME: Final[dict[str, Team]] = {"Order": "ORDER", "Chaos": "CHAOS"}
LANE_BY_NUMBER: Final[dict[str, Lane]] = {"0": "bot", "1": "mid", "2": "top"}
TIER_BY_PLACE: Final[dict[str, TurretTier]] = {
    "3": "outer",
    "2": "inner",
    "1": "inhibitor",
    "4": "nexus",
    "5": "nexus",
}
TURRET_NAME_PATTERN: Final = re.compile(
    r"^Turret_T(?P<team>Order|Chaos)_L(?P<lane>[012])_P(?P<place>[1-5])(_|$)"
)
INHIBITOR_NAME_PATTERN: Final = re.compile(
    r"^Inhib_T(?P<team>Order|Chaos)_L(?P<lane>[012])_P1(_|$)"
)

OLD_TEAM_BY_NUMBER: Final[dict[str, Team]] = {"1": "ORDER", "2": "CHAOS"}
OLD_LANE_BY_LETTER: Final[dict[str, Lane]] = {"L": "top", "C": "mid", "R": "bot"}
OLD_TIER_BY_LANE_AND_PLACE: Final[dict[tuple[str, int], TurretTier]] = {
    ("L", 3): "outer",
    ("C", 5): "outer",
    ("R", 3): "outer",
    ("L", 2): "inner",
    ("C", 4): "inner",
    ("R", 2): "inner",
    ("L", 1): "inhibitor",
    ("C", 3): "inhibitor",
    ("R", 1): "inhibitor",
    ("C", 2): "nexus",
    ("C", 1): "nexus",
}
OLD_TURRET_NAME_PATTERN: Final = re.compile(
    r"^Turret_T(?P<team>[12])_(?P<lane>[LCR])_(?P<place>\d{2})_A$"
)
OLD_INHIBITOR_NAME_PATTERN: Final = re.compile(r"^Barracks_T(?P<team>[12])_(?P<lane>[LCR])1$")


@dataclass(frozen=True)
class TurretName:
    """What a turret's name says: whose it is, its lane, and how deep in the lane it stands."""

    team: Team
    # The nexus turrets' is mid.
    lane: Lane
    tier: TurretTier


@dataclass(frozen=True)
class InhibitorName:
    """What an inhibitor's name says: whose it is, and its lane."""

    team: Team
    lane: Lane


def read_turret_name(name: str | None) -> TurretName | None:
    """Read a turret's name.

    Args:
        name: Such as "Turret_TOrder_L0_P3_3795288474_0", or None.

    Returns:
        The turret, or None for a name not understood.
    """
    new_match = TURRET_NAME_PATTERN.match(name or "")
    if new_match is not None:
        return TurretName(
            team=TEAM_BY_NAME[new_match["team"]],
            lane=LANE_BY_NUMBER[new_match["lane"]],
            tier=TIER_BY_PLACE[new_match["place"]],
        )
    old_match = OLD_TURRET_NAME_PATTERN.match(name or "")
    if old_match is None:
        return None
    tier = OLD_TIER_BY_LANE_AND_PLACE.get((old_match["lane"], int(old_match["place"])))
    if tier is None:
        return None
    return TurretName(
        team=OLD_TEAM_BY_NUMBER[old_match["team"]],
        lane=OLD_LANE_BY_LETTER[old_match["lane"]],
        tier=tier,
    )


def read_inhibitor_name(name: str | None) -> InhibitorName | None:
    """Read an inhibitor's name.

    Args:
        name: Such as "Inhib_TChaos_L1_P1_2432143522_0", or None.

    Returns:
        The inhibitor, or None for a name not understood.
    """
    new_match = INHIBITOR_NAME_PATTERN.match(name or "")
    if new_match is not None:
        return InhibitorName(
            team=TEAM_BY_NAME[new_match["team"]], lane=LANE_BY_NUMBER[new_match["lane"]]
        )
    old_match = OLD_INHIBITOR_NAME_PATTERN.match(name or "")
    if old_match is None:
        return None
    return InhibitorName(
        team=OLD_TEAM_BY_NUMBER[old_match["team"]], lane=OLD_LANE_BY_LETTER[old_match["lane"]]
    )
