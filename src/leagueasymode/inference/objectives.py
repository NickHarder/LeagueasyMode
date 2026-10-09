"""Objective timers, from the kill feed: epic monsters, the buffs they give, and inhibitors.

These restate what the game announces (a monster's death, an inhibitor falling, the rift changing
for the soul) with the spawn rules applied; nothing is estimated. A rule is written as verified once
it is long-standing or the owner has confirmed it for this season; a rule that changes with a new
season goes back to unverified, and the overlay marks its times as provisional, until it is
confirmed again.
"""

import re
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from leagueasymode.game_state import GameEvent, GameSnapshot
from leagueasymode.overlay_state import BuffTimer, DragonTimer, InhibitorTimer, ObjectiveTimer

DRAGON_KILL_EVENT: Final = "DragonKill"
BARON_KILL_EVENT: Final = "BaronKill"
INHIBITOR_KILLED_EVENT: Final = "InhibKilled"
INHIBITOR_RESPAWNED_EVENT: Final = "InhibRespawned"
ELDER_DRAGON_TYPE: Final = "Elder"
DEFAULT_MAP_TERRAIN: Final = "Default"
BARON_BUFF_SECONDS: Final = 180.0
ELDER_BUFF_SECONDS: Final = 150.0
INHIBITOR_RESPAWN_SECONDS: Final = 300.0
# "Barracks_T1_L1": team 1 (ORDER) or 2 (CHAOS), then the lane. L, C and R are taken as top, mid
# and bottom, which the first recordings confirm or correct.
INHIBITOR_NAME_PATTERN: Final = re.compile(r"^Barracks_T(?P<team>[12])_(?P<lane>[LCR])1$")
TEAM_BY_NUMBER: Final = {"1": "ORDER", "2": "CHAOS"}
LANE_BY_LETTER: Final[dict[str, Literal["top", "mid", "bot"]]] = {
    "L": "top",
    "C": "mid",
    "R": "bot",
}


class DragonRules(BaseModel):
    """When dragons spawn, in game seconds.

    `tuning.json`'s "dragon".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    first_spawn_seconds: float = 300.0
    respawn_seconds: float = 300.0
    elder_respawn_seconds: float = 360.0
    dragons_for_soul: int = 4


DRAGON_RULES: Final = DragonRules()


def dragon_timer(snapshot: GameSnapshot, rules: DragonRules = DRAGON_RULES) -> DragonTimer:
    """Return the next dragon's timer, and each team's dragons, as of a snapshot.

    Args:
        snapshot: The game's state.
        rules: The spawn rules.

    Returns:
        The timer of the next dragon, which is the Elder Dragon once a team has the soul.
    """
    game_time_seconds = snapshot.game_data.game_time_seconds
    dragon_kills = sorted(
        (event for event in snapshot.event_list.events if event.event_name == DRAGON_KILL_EVENT),
        key=lambda event: event.event_time_seconds,
    )
    ally_team = snapshot.ally_team()
    elemental_kill_teams = [
        snapshot.team_of(event.killer_name)
        for event in dragon_kills
        if event.dragon_type != ELDER_DRAGON_TYPE
    ]
    ally_dragon_count = sum(1 for team in elemental_kill_teams if team == ally_team)
    enemy_dragon_count = sum(
        1 for team in elemental_kill_teams if team is not None and team != ally_team
    )
    soul_holder = _soul_holder(ally_dragon_count, enemy_dragon_count, rules)
    spawns_at_seconds = _next_spawn_seconds(dragon_kills, soul_holder is not None, rules)
    terrain = snapshot.game_data.map_terrain
    return DragonTimer(
        objective="elder_dragon" if soul_holder is not None else "dragon",
        status=_status(game_time_seconds, spawns_at_seconds, has_any_kill=bool(dragon_kills)),
        spawns_at_game_time_seconds=spawns_at_seconds,
        ally_dragon_count=ally_dragon_count,
        enemy_dragon_count=enemy_dragon_count,
        soul_type=terrain if terrain and terrain != DEFAULT_MAP_TERRAIN else None,
        soul_holder=soul_holder,
    )


def _soul_holder(
    ally_dragon_count: int, enemy_dragon_count: int, rules: DragonRules
) -> Literal["ally", "enemy"] | None:
    """Return which side has the dragon soul, if either.

    Args:
        ally_dragon_count: Elemental dragons the player's team has taken.
        enemy_dragon_count: Elemental dragons the other team has taken.
        rules: How many dragons make the soul.

    Returns:
        "ally", "enemy", or None.
    """
    if ally_dragon_count >= rules.dragons_for_soul:
        return "ally"
    if enemy_dragon_count >= rules.dragons_for_soul:
        return "enemy"
    return None


def _next_spawn_seconds(
    dragon_kills: list[GameEvent], has_soul_been_taken: bool, rules: DragonRules
) -> float:
    """Return when the next dragon spawns.

    Args:
        dragon_kills: Every dragon kill so far, oldest first.
        has_soul_been_taken: Whether a team has the soul, after which only the Elder spawns.
        rules: The spawn rules.

    Returns:
        The game time of the next spawn, in seconds.
    """
    if not dragon_kills:
        return rules.first_spawn_seconds
    last_kill_seconds = dragon_kills[-1].event_time_seconds
    if has_soul_been_taken:
        return last_kill_seconds + rules.elder_respawn_seconds
    return last_kill_seconds + rules.respawn_seconds


def _status(
    game_time_seconds: float, spawns_at_seconds: float, has_any_kill: bool
) -> Literal["not_spawned", "respawning", "alive"]:
    """Return whether the next dragon is waiting to spawn for the first time, respawning or up.

    Args:
        game_time_seconds: The game's clock.
        spawns_at_seconds: When the next dragon spawns.
        has_any_kill: Whether any dragon has died yet.

    Returns:
        The dragon's status.
    """
    if game_time_seconds >= spawns_at_seconds:
        return "alive"
    return "respawning" if has_any_kill else "not_spawned"


@dataclass(frozen=True)
class ObjectiveRule:
    """When an epic monster other than the dragons spawns, respawns and leaves, in game seconds."""

    objective: Literal["baron", "rift_herald", "voidgrubs"]
    first_spawn_seconds: float
    # None: it does not come back once taken.
    respawn_seconds: float | None
    # When it leaves the map if nobody has taken it; None: it stays.
    leaves_at_seconds: float | None
    # The feed's event for its death; None while that event has not been seen in a recording.
    kill_event_name: str | None
    is_verified: bool
    source: str


# The 2026 season's rules. Each leaves 15 seconds before the next monster takes its pit, as in
# past seasons; a community guide of patch 26.15 gives the same 14:45 and 19:45.
OBJECTIVE_RULES: Final = (
    ObjectiveRule(
        objective="voidgrubs",
        first_spawn_seconds=480.0,
        respawn_seconds=None,
        leaves_at_seconds=885.0,
        kill_event_name=None,
        is_verified=True,
        source="8:00, confirmed by the owner on 2026-10-08; they leave at 14:45",
    ),
    ObjectiveRule(
        objective="rift_herald",
        first_spawn_seconds=900.0,
        respawn_seconds=None,
        leaves_at_seconds=1185.0,
        kill_event_name="HeraldKill",
        is_verified=True,
        source="15:00, confirmed by the owner on 2026-10-08; she leaves at 19:45",
    ),
    ObjectiveRule(
        objective="baron",
        first_spawn_seconds=1200.0,
        respawn_seconds=360.0,
        leaves_at_seconds=None,
        kill_event_name=BARON_KILL_EVENT,
        is_verified=True,
        source="20:00, confirmed by the owner on 2026-10-08; respawn the long-standing 6:00",
    ),
)


def objective_timers(
    snapshot: GameSnapshot, rules: tuple[ObjectiveRule, ...] = OBJECTIVE_RULES
) -> list[ObjectiveTimer]:
    """Return the timer of each epic monster other than the dragons, as of a snapshot.

    Args:
        snapshot: The game's state.
        rules: The spawn rules.

    Returns:
        One timer per rule, in the rules' order.
    """
    return [_objective_timer(snapshot, rule) for rule in rules]


def buff_timers(snapshot: GameSnapshot) -> list[BuffTimer]:
    """Return the Baron and Elder buffs still running, with the side that holds each.

    The buff goes to the team of the player who took the monster; a monster taken by nobody on the
    scoreboard gives no buff shown here.

    Args:
        snapshot: The game's state.

    Returns:
        The buffs still running, oldest first.
    """
    game_time_seconds = snapshot.game_data.game_time_seconds
    ally_team = snapshot.ally_team()
    candidate_buffs = [
        (buff_name, event, event.event_time_seconds + duration_seconds)
        for event in snapshot.event_list.events
        for buff_name, duration_seconds in _buff_given_by(event)
    ]
    return [
        BuffTimer(
            buff=buff_name,
            holder="ally" if holder_team == ally_team else "enemy",
            ends_at_game_time_seconds=ends_at_seconds,
        )
        for buff_name, event, ends_at_seconds in candidate_buffs
        if ends_at_seconds > game_time_seconds
        and (holder_team := snapshot.team_of(event.killer_name)) is not None
    ]


def inhibitor_timers(snapshot: GameSnapshot) -> list[InhibitorTimer]:
    """Return the inhibitors that are down, with when each comes back.

    An inhibitor is back when its respawn time passes or the feed says it respawned, whichever
    comes first. A name this module does not recognize is left out.

    Args:
        snapshot: The game's state.

    Returns:
        The inhibitors down, in the order they fell.
    """
    game_time_seconds = snapshot.game_data.game_time_seconds
    ally_team = snapshot.ally_team()
    last_kill_by_name = {
        event.inhibitor_killed_name: event
        for event in snapshot.event_list.events
        if event.event_name == INHIBITOR_KILLED_EVENT and event.inhibitor_killed_name
    }
    timers: list[InhibitorTimer] = []
    for inhibitor_name, kill_event in last_kill_by_name.items():
        name_match = INHIBITOR_NAME_PATTERN.match(inhibitor_name)
        respawns_at_seconds = kill_event.event_time_seconds + INHIBITOR_RESPAWN_SECONDS
        has_respawned = any(
            event.event_name == INHIBITOR_RESPAWNED_EVENT
            and event.inhibitor_respawned_name == inhibitor_name
            and event.event_time_seconds >= kill_event.event_time_seconds
            for event in snapshot.event_list.events
        )
        if name_match is None or has_respawned or game_time_seconds >= respawns_at_seconds:
            continue
        owner_team = TEAM_BY_NUMBER[name_match.group("team")]
        timers.append(
            InhibitorTimer(
                side="ally" if owner_team == ally_team else "enemy",
                lane=LANE_BY_LETTER[name_match.group("lane")],
                respawns_at_game_time_seconds=respawns_at_seconds,
            )
        )
    return timers


def _objective_timer(snapshot: GameSnapshot, rule: ObjectiveRule) -> ObjectiveTimer:
    """Return one epic monster's timer.

    Args:
        snapshot: The game's state.
        rule: The monster's spawn rule.

    Returns:
        The timer.
    """
    game_time_seconds = snapshot.game_data.game_time_seconds
    kills = [
        event
        for event in snapshot.event_list.events
        if rule.kill_event_name is not None and event.event_name == rule.kill_event_name
    ]
    has_left = rule.leaves_at_seconds is not None and game_time_seconds >= rule.leaves_at_seconds
    if has_left or (kills and rule.respawn_seconds is None):
        return ObjectiveTimer(
            objective=rule.objective,
            status="gone",
            spawns_at_game_time_seconds=None,
            is_rule_verified=rule.is_verified,
        )
    spawns_at_seconds = (
        max(event.event_time_seconds for event in kills) + rule.respawn_seconds
        if kills and rule.respawn_seconds is not None
        else rule.first_spawn_seconds
    )
    return ObjectiveTimer(
        objective=rule.objective,
        status=_status(game_time_seconds, spawns_at_seconds, has_any_kill=bool(kills)),
        spawns_at_game_time_seconds=spawns_at_seconds,
        is_rule_verified=rule.is_verified,
    )


def _buff_given_by(event: GameEvent) -> list[tuple[Literal["baron", "elder"], float]]:
    """Return the buff a feed event gives, with how long it lasts; empty for any other event.

    Args:
        event: One event of the feed.

    Returns:
        The buff and its duration in seconds, or nothing.
    """
    if event.event_name == BARON_KILL_EVENT:
        return [("baron", BARON_BUFF_SECONDS)]
    if event.event_name == DRAGON_KILL_EVENT and event.dragon_type == ELDER_DRAGON_TYPE:
        return [("elder", ELDER_BUFF_SECONDS)]
    return []
