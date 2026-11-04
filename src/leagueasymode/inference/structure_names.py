"""Turret and inhibitor names, as the game's feed gives them.

The game names a turret `Turret_TOrder_L0_P3_3795288474_0` and an inhibitor
`Inhib_TChaos_L1_P1_2432143522_0`: the team that owns it, its lane and its place in the lane. Read
against the match timelines of the owner's games of 2026-10-29, whose `BUILDING_KILL` events name
each one's lane and tier at the same second: lane 0 is bot, 1 mid and 2 top; place 3 is the outer
turret, 2 the inner, 1 the inhibitor turret (and the inhibitor), 4 and 5 the nexus turrets, which
stand in lane 1. ARAM's single lane is lane 1.

The names that open-source readers of the game's API give (`Turret_T1_L_03_A`, `Barracks_T1_L1`),
which the code read until 2026-10-30, never came in a recorded game, and are not read.
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
    name_match = TURRET_NAME_PATTERN.match(name or "")
    if name_match is None:
        return None
    return TurretName(
        team=TEAM_BY_NAME[name_match["team"]],
        lane=LANE_BY_NUMBER[name_match["lane"]],
        tier=TIER_BY_PLACE[name_match["place"]],
    )


def read_inhibitor_name(name: str | None) -> InhibitorName | None:
    """Read an inhibitor's name.

    Args:
        name: Such as "Inhib_TChaos_L1_P1_2432143522_0", or None.

    Returns:
        The inhibitor, or None for a name not understood.
    """
    name_match = INHIBITOR_NAME_PATTERN.match(name or "")
    if name_match is None:
        return None
    return InhibitorName(
        team=TEAM_BY_NAME[name_match["team"]], lane=LANE_BY_NUMBER[name_match["lane"]]
    )
