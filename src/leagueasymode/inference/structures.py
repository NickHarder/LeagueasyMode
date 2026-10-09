"""Structures, from the kill feed: each side's turrets down per lane, and the inhibitors they open.

Exact: it restates the feed's `TurretKilled` and inhibitor announcements, read by the turret names
the gold and the clues already read ("Turret_T2_L_03_A": the enemy's top outer turret, when you
play on the blue side). The two nexus turrets are left out: whether they come back, and when, the
feed does not say.
"""

from typing import Final, Literal

from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.gold import (
    TURRET_KILLED_EVENT,
    TURRET_NAME_PATTERN,
    TURRET_TIER_BY_LANE_AND_PLACE,
)
from leagueasymode.inference.objectives import LANE_BY_LETTER, TEAM_BY_NUMBER, inhibitor_timers
from leagueasymode.overlay_state import LaneStructures

type Side = Literal["ally", "enemy"]
type Lane = Literal["top", "mid", "bot"]

SIDES: Final[tuple[Side, ...]] = ("ally", "enemy")
LANES: Final[tuple[Lane, ...]] = ("top", "mid", "bot")
# A lane's turrets, outer to inhibitor; the nexus turrets have no lane.
LANE_TURRET_TIERS: Final = frozenset({"outer", "inner", "inhibitor"})
INHIBITOR_TURRET_TIER: Final = "inhibitor"


def lane_structures(snapshot: GameSnapshot) -> list[LaneStructures]:
    """Return each lane that has lost a turret: how many, and whether its inhibitor is open.

    A turret the feed announces twice counts once; a name this module does not recognize, and
    a nexus turret, are left out. An inhibitor is open while its turret is down and it stands; while
    it is down itself, its timer shows instead.

    Args:
        snapshot: The game's state.

    Returns:
        The lanes, the player's side first, top to bot.
    """
    ally_team = snapshot.ally_team()
    turrets_down: set[tuple[Side, Lane, str]] = set()
    for event in snapshot.event_list.events:
        name_match = (
            TURRET_NAME_PATTERN.match(event.turret_killed_name or "")
            if event.event_name == TURRET_KILLED_EVENT
            else None
        )
        if name_match is None:
            continue
        tier = TURRET_TIER_BY_LANE_AND_PLACE.get(
            (name_match.group("lane"), int(name_match.group("place")))
        )
        if tier not in LANE_TURRET_TIERS:
            continue
        owner_side: Side = (
            "ally" if TEAM_BY_NUMBER[name_match.group("team")] == ally_team else "enemy"
        )
        turrets_down.add((owner_side, LANE_BY_LETTER[name_match.group("lane")], tier))
    inhibitors_down = {(timer.side, timer.lane) for timer in inhibitor_timers(snapshot)}
    lanes: list[LaneStructures] = []
    for side in SIDES:
        for lane in LANES:
            tiers_down = {
                tier
                for down_side, down_lane, tier in turrets_down
                if (down_side, down_lane) == (side, lane)
            }
            if not tiers_down:
                continue
            lanes.append(
                LaneStructures(
                    side=side,
                    lane=lane,
                    turrets_down=len(tiers_down),
                    is_inhibitor_exposed=INHIBITOR_TURRET_TIER in tiers_down
                    and (side, lane) not in inhibitors_down,
                )
            )
    return lanes
