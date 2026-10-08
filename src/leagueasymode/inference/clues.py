"""Clues to where each player is (phase 4.2): the moments the feed or the scoreboard pins a place.

- An objective's takers were at it: a turret's or an inhibitor's killer and assisters at it, an
  epic monster's at its pit.
- A champion a turret kills was at that turret.
- A respawn, or the shopping of a trip to base (`backs.py`), is in base.
- Creep score rising is a laner in their lane, or a jungler in a jungle: their own, or the other
  team's when invading, which the score cannot tell.

A kill between champions names no place, so it is no clue here; the position filter (4.3) reads it
as the two having been together.
"""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal

from leagueasymode.game_state import GameEvent, GameSnapshot, ScoreboardPlayer
from leagueasymode.inference.gold import (
    CHAMPION_KILL_EVENT,
    NEW_GAME_SLACK_SECONDS,
    TURRET_KILLED_EVENT,
    TURRET_NAME_PATTERN,
    TURRET_TIER_BY_LANE_AND_PLACE,
    PlayerKey,
    player_key,
)
from leagueasymode.inference.objectives import (
    BARON_KILL_EVENT,
    DRAGON_KILL_EVENT,
    INHIBITOR_KILLED_EVENT,
    INHIBITOR_NAME_PATTERN,
    LANE_BY_LETTER,
    TEAM_BY_NUMBER,
)
from leagueasymode.inference.rift_map import RIFT_MAP, TEAM_PREFIX, fountain_of, role_point_of
from leagueasymode.inference.roles import assign_roles
from leagueasymode.overlay_state import BackEstimate, PositionClue

# The epic monsters' pits, and their names in words. The Voidgrubs' event name is to be confirmed
# on a recording.
PIT_BY_EVENT: Final[Mapping[str, tuple[str, str]]] = {
    DRAGON_KILL_EVENT: ("dragon_pit", "Dragon"),
    BARON_KILL_EVENT: ("baron_pit", "Baron"),
    "HeraldKill": ("baron_pit", "Herald"),
    "HordeKill": ("baron_pit", "Voidgrubs"),
}
LANE_BY_ROLE: Final = {"TOP": "top", "MIDDLE": "mid", "BOTTOM": "bot", "UTILITY": "bot"}
JUNGLE_ROLE: Final = "JUNGLE"
# The clues of the scoreboard kept for each player, the latest ones.
KEPT_SCOREBOARD_CLUES: Final = 20


@dataclass
class _PlayerClues:
    """What the tracker remembers of one player between answers."""

    creep_score: int
    was_dead: bool
    scoreboard_clues: list[PositionClue] = field(default_factory=list)


def feed_clues(snapshot: GameSnapshot) -> dict[PlayerKey, list[PositionClue]]:
    """Return the clues the feed gives: the players at each objective and turret kill.

    Args:
        snapshot: The game's state.

    Returns:
        Each player's clues, oldest first; a player the feed places nowhere is left out.
    """
    clues: defaultdict[PlayerKey, list[PositionClue]] = defaultdict(list)
    for event in snapshot.event_list.events:
        for player, clue in _event_clues(event, snapshot):
            clues[player_key(player)].append(clue)
    return dict(clues)


class ClueTracker:
    """Gathers every player's clues through a game, one answer of the game's API after another.

    A game time well before the last one seen starts a new game, and the tracker over.
    """

    def __init__(self) -> None:
        """Start with no game."""
        self._players: Final[dict[PlayerKey, _PlayerClues]] = {}
        self._last_game_time_seconds = 0.0

    def update(
        self, snapshot: GameSnapshot, last_backs: Mapping[PlayerKey, BackEstimate]
    ) -> dict[PlayerKey, list[PositionClue]]:
        """Take in one answer of the game's API, and return every player's clues so far.

        Args:
            snapshot: The game's state.
            last_backs: Each player's last trip to base.

        Returns:
            Each player's clues, oldest first; a player with none is left out.
        """
        game_time_seconds = snapshot.game_data.game_time_seconds
        if game_time_seconds < self._last_game_time_seconds - NEW_GAME_SLACK_SECONDS:
            self._players.clear()
        self._last_game_time_seconds = game_time_seconds
        from_feed = feed_clues(snapshot)
        clues: dict[PlayerKey, list[PositionClue]] = {}
        for player, role_guess in zip(snapshot.players, assign_roles(snapshot), strict=True):
            key = player_key(player)
            state = self._players.setdefault(
                key,
                _PlayerClues(creep_score=player.scores.creep_score, was_dead=player.is_dead),
            )
            new_clues = _scoreboard_clues(state, player, role_guess.role, game_time_seconds)
            state.scoreboard_clues = [*state.scoreboard_clues, *new_clues][-KEPT_SCOREBOARD_CLUES:]
            state.creep_score = player.scores.creep_score
            state.was_dead = player.is_dead
            last_back = last_backs.get(key)
            back_clues = (
                [_in_base(player.team, last_back.shopped_at_game_time_seconds)] if last_back else []
            )
            player_clues = sorted(
                [*from_feed.get(key, []), *state.scoreboard_clues, *back_clues],
                key=lambda clue: clue.game_time_seconds,
            )
            if player_clues:
                clues[key] = player_clues
        return clues


def _scoreboard_clues(
    state: _PlayerClues, player: ScoreboardPlayer, role: str, game_time_seconds: float
) -> list[PositionClue]:
    """Return the clues the scoreboard gives since the last answer: a respawn, creep score.

    Args:
        state: The player's state, from the last answer.
        player: The player now.
        role: Their role, given or worked out; empty when unknown.
        game_time_seconds: The game's clock.

    Returns:
        The new clues.
    """
    respawn_clues = (
        [_in_base(player.team, game_time_seconds)] if state.was_dead and not player.is_dead else []
    )
    has_farmed = player.scores.creep_score > state.creep_score and not player.is_dead
    farm_clue = _farming(player.team, role, game_time_seconds) if has_farmed else None
    return [*respawn_clues, *([farm_clue] if farm_clue is not None else [])]


def _in_base(team: str, game_time_seconds: float) -> PositionClue:
    """Return the clue of a player in their base.

    Args:
        team: Their team.
        game_time_seconds: When.

    Returns:
        The clue.
    """
    fountain = fountain_of(team)
    return PositionClue(
        kind="fountain",
        game_time_seconds=game_time_seconds,
        place="in base",
        point_name=fountain,
        region=RIFT_MAP.points[fountain].region,
    )


def _farming(team: str, role: str, game_time_seconds: float) -> PositionClue | None:
    """Return the clue of a player whose creep score rose: in their lane, or in a jungle.

    Args:
        team: Their team.
        role: Their role; empty when unknown.
        game_time_seconds: When.

    Returns:
        The clue, or None when their role, and so their lane, is unknown.
    """
    if role == JUNGLE_ROLE:
        return PositionClue(
            kind="jungle",
            game_time_seconds=game_time_seconds,
            place="in the jungle",
            point_name=None,
            region=f"{TEAM_PREFIX.get(team, 'order')}_jungle",
        )
    lane = LANE_BY_ROLE.get(role)
    if lane is None:
        return None
    return PositionClue(
        kind="lane",
        game_time_seconds=game_time_seconds,
        place=f"in the {lane} lane",
        point_name=role_point_of(team, role),
        region=f"{lane}_lane",
    )


def _event_clues(
    event: GameEvent, snapshot: GameSnapshot
) -> list[tuple[ScoreboardPlayer, PositionClue]]:
    """Return the players an entry of the feed places, and where.

    Args:
        event: The entry.
        snapshot: The game's state.

    Returns:
        Each player placed, with their clue; none for an entry that names no place.
    """
    if event.event_name == CHAMPION_KILL_EVENT:
        turret = _turret_place(event.killer_name)
        victim = snapshot.player_named(event.victim_name)
        if turret is None or victim is None:
            return []
        return [(victim, _clue_at("turret", event, *turret))]
    place = _structure_place(event) or _pit_place(event)
    if place is None:
        return []
    kind: Literal["turret", "objective"] = (
        "objective" if event.event_name in PIT_BY_EVENT else "turret"
    )
    credited = [
        player
        for player in (
            snapshot.player_named(name) for name in [event.killer_name, *event.assister_names]
        )
        if player is not None
    ]
    return [(player, _clue_at(kind, event, *place)) for player in credited]


def _clue_at(
    kind: Literal["turret", "objective"], event: GameEvent, point_name: str, place: str
) -> PositionClue:
    """Return the clue of a player at a point of the map when an entry of the feed happened.

    Args:
        kind: What pinned them.
        event: The entry.
        point_name: The map's point.
        place: The point in words.

    Returns:
        The clue.
    """
    return PositionClue(
        kind=kind,
        game_time_seconds=event.event_time_seconds,
        place=place,
        point_name=point_name,
        region=RIFT_MAP.points[point_name].region,
    )


def _structure_place(event: GameEvent) -> tuple[str, str] | None:
    """Return where a turret or an inhibitor the feed says fell stood.

    Args:
        event: An entry of the feed.

    Returns:
        The map's point and the place in words, or None for another entry.
    """
    if event.event_name == TURRET_KILLED_EVENT:
        return _turret_place(event.turret_killed_name)
    if event.event_name != INHIBITOR_KILLED_EVENT:
        return None
    inhibitor_match = INHIBITOR_NAME_PATTERN.match(event.inhibitor_killed_name or "")
    if inhibitor_match is None:
        return None
    team_prefix = TEAM_PREFIX[TEAM_BY_NUMBER[inhibitor_match["team"]]]
    lane = LANE_BY_LETTER[inhibitor_match["lane"]]
    return f"{team_prefix}_{lane}_inhibitor", f"at the {lane} inhibitor"


def _turret_place(turret_name: str | None) -> tuple[str, str] | None:
    """Return where a turret stands, by the name the feed gives it.

    Args:
        turret_name: Such as "Turret_T1_L_03_A".

    Returns:
        The map's point and the place in words, or None for a name not understood.
    """
    turret_match = TURRET_NAME_PATTERN.match(turret_name or "")
    if turret_match is None:
        return None
    tier = TURRET_TIER_BY_LANE_AND_PLACE.get((turret_match["lane"], int(turret_match["place"])))
    team_prefix = TEAM_PREFIX[TEAM_BY_NUMBER[turret_match["team"]]]
    lane = LANE_BY_LETTER[turret_match["lane"]]
    if tier is None:
        return None
    if tier == "nexus":
        return f"{team_prefix}_nexus", "at the nexus turrets"
    return f"{team_prefix}_{lane}_{tier}_turret", f"at the {lane} {tier} turret"


def _pit_place(event: GameEvent) -> tuple[str, str] | None:
    """Return the pit of an epic monster the feed says was taken.

    Args:
        event: An entry of the feed.

    Returns:
        The map's point and the place in words, or None for another entry.
    """
    pit = PIT_BY_EVENT.get(event.event_name)
    if pit is None:
        return None
    point_name, monster_name = pit
    return point_name, f"at {monster_name}"
