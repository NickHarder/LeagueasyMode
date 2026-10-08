"""Estimator 1: each player's role, in queues that do not assign one.

The game names each player's position in queues that assign roles; that is taken as given. Where
it does not, each player gets a cost for each role from what the scoreboard shows (Smite, a support
item, the other summoner spells, and, after the first minutes, who has the least CS), and the five
roles go to the five players of each team in the assignment of least total cost.

The assignment is found by trying every one: for five roles that is 120, so the search is exact and
gives what the Hungarian algorithm would, with a fraction of its code. How far the best assignment
is ahead of the cheapest one that gives a player another role says how sure that player's role is.

The costs are a hand-set prior, to be fitted on the roles the post-game timeline records.
"""

import itertools
from dataclasses import dataclass
from typing import Final, Literal

from leagueasymode.game_state import GameSnapshot, ScoreboardPlayer

ROLES: Final = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
# The support item's every stage, this season's, from the first version's knowledge of the game;
# checked against the first recordings.
SUPPORT_ITEM_NAMES: Final = frozenset(
    {
        "World Atlas",
        "Runic Compass",
        "Bounty of Worlds",
        "Celestial Opposition",
        "Dream Maker",
        "Solstice Sleigh",
        "Bloodsong",
        "Zaz'Zak's Realmspike",
    }
)
# The cost of each role for a player who has the spell; a role not named costs the default.
SPELL_ROLE_COSTS: Final[dict[str, tuple[dict[str, float], float]]] = {
    "Smite": ({"JUNGLE": 0.0}, 8.0),
    "Teleport": ({"TOP": 0.0, "MIDDLE": 1.0}, 2.5),
    "Heal": ({"BOTTOM": 0.0, "UTILITY": 1.5}, 2.5),
    "Exhaust": ({"UTILITY": 0.0, "MIDDLE": 1.5}, 2.0),
    "Ignite": ({"MIDDLE": 0.0, "UTILITY": 0.5, "TOP": 0.5}, 1.5),
    "Barrier": ({"MIDDLE": 0.0, "BOTTOM": 0.5}, 1.5),
    "Cleanse": ({"BOTTOM": 0.0, "MIDDLE": 0.5}, 1.5),
    "Ghost": ({"TOP": 0.0, "BOTTOM": 0.5}, 1.0),
}
JUNGLE_WITHOUT_SMITE_COST: Final = 6.0
SUPPORT_ITEM_ELSEWHERE_COST: Final = 8.0
SUPPORT_WITHOUT_SUPPORT_ITEM_COST: Final = 3.0
# After this, the player with the least CS on a team is most likely its support.
CS_RANK_FROM_SECONDS: Final = 180.0
LEAST_CS_ELSEWHERE_COST: Final = 1.5
MORE_CS_AS_SUPPORT_COST: Final = 2.5
# The best assignment must be this far ahead of the next for the guess to count as likely.
LIKELY_MARGIN: Final = 2.0


@dataclass(frozen=True)
class RoleGuess:
    """One player's role, and whether and how surely it was worked out."""

    role: str
    is_inferred: bool
    confidence: Literal["given", "likely", "guess"]


def assign_roles(snapshot: GameSnapshot) -> list[RoleGuess]:
    """Return each player's role, in the scoreboard's order.

    Args:
        snapshot: The game's state.

    Returns:
        One guess per player.
    """
    guesses_by_index: dict[int, RoleGuess] = {}
    for team_name in sorted({player.team for player in snapshot.players}):
        team_indexes = [
            index for index, player in enumerate(snapshot.players) if player.team == team_name
        ]
        guesses_by_index.update(_assign_team(snapshot, team_indexes))
    return [guesses_by_index[index] for index in range(len(snapshot.players))]


def _assign_team(snapshot: GameSnapshot, team_indexes: list[int]) -> dict[int, RoleGuess]:
    """Return the roles of one team's players, by their index on the scoreboard.

    Args:
        snapshot: The game's state.
        team_indexes: The team's players, as indexes into the scoreboard.

    Returns:
        Each player's guess.
    """
    players = snapshot.players
    given_indexes = [index for index in team_indexes if players[index].position in ROLES]
    open_indexes = [index for index in team_indexes if index not in given_indexes]
    given_guesses = {
        index: RoleGuess(role=players[index].position, is_inferred=False, confidence="given")
        for index in given_indexes
    }
    open_roles = [
        role for role in ROLES if role not in {players[index].position for index in given_indexes}
    ]
    if not open_indexes or len(open_roles) < len(open_indexes):
        return given_guesses
    least_cs_index = _least_cs_index(snapshot, team_indexes)
    costs = {
        (index, role): _role_cost(players[index], role, index == least_cs_index, least_cs_index)
        for index in open_indexes
        for role in open_roles
    }
    ranked_assignments = sorted(
        (
            sum(costs[index, role] for index, role in zip(open_indexes, roles, strict=True)),
            roles,
        )
        for roles in itertools.permutations(open_roles, len(open_indexes))
    )
    best_cost, best_roles = ranked_assignments[0]
    inferred_guesses = {
        index: RoleGuess(
            role=role,
            is_inferred=True,
            confidence=_confidence(
                best_cost, ranked_assignments, position_in_team=position, best_role=role
            ),
        )
        for position, (index, role) in enumerate(zip(open_indexes, best_roles, strict=True))
    }
    return {**given_guesses, **inferred_guesses}


def _confidence(
    best_cost: float,
    ranked_assignments: list[tuple[float, tuple[str, ...]]],
    position_in_team: int,
    best_role: str,
) -> Literal["likely", "guess"]:
    """Return how sure one player's role is: how much dearer any assignment that changes it is.

    Each player has their own margin, so that a team whose top and mid could swap does not make
    its only player with Smite a guess.

    Args:
        best_cost: The best assignment's cost.
        ranked_assignments: Every assignment with its cost, cheapest first.
        position_in_team: The player's place among the team's open players.
        best_role: The player's role in the best assignment.

    Returns:
        "likely" when every assignment that changes the role costs at least the margin more.
    """
    other_role_costs = [
        cost for cost, roles in ranked_assignments if roles[position_in_team] != best_role
    ]
    margin = (min(other_role_costs) - best_cost) if other_role_costs else LIKELY_MARGIN
    return "likely" if margin >= LIKELY_MARGIN else "guess"


def _least_cs_index(snapshot: GameSnapshot, team_indexes: list[int]) -> int | None:
    """Return the team's player with the least CS, once CS says anything.

    Args:
        snapshot: The game's state.
        team_indexes: The team's players.

    Returns:
        That player's index, or None in the first minutes.
    """
    if snapshot.game_data.game_time_seconds < CS_RANK_FROM_SECONDS or not team_indexes:
        return None
    return min(team_indexes, key=lambda index: snapshot.players[index].scores.creep_score)


def _role_cost(
    player: ScoreboardPlayer, role: str, has_least_cs: bool, least_cs_index: int | None
) -> float:
    """Return how unlikely a role is for a player, as a cost: lower is likelier.

    Args:
        player: The player.
        role: The role.
        has_least_cs: Whether the player has the least CS on the team.
        least_cs_index: The least-CS player's index, or None before CS says anything.

    Returns:
        The cost.
    """
    spell_names = player.summoner_spells.names()
    spell_cost = sum(
        role_costs.get(role, default_cost)
        for spell_key, (role_costs, default_cost) in SPELL_ROLE_COSTS.items()
        if any(spell_key in spell_name for spell_name in spell_names)
    )
    has_smite = any("Smite" in spell_name for spell_name in spell_names)
    smite_cost = JUNGLE_WITHOUT_SMITE_COST if role == "JUNGLE" and not has_smite else 0.0
    has_support_item = any(item.display_name in SUPPORT_ITEM_NAMES for item in player.items)
    support_item_cost = (
        SUPPORT_ITEM_ELSEWHERE_COST
        if has_support_item and role != "UTILITY"
        else SUPPORT_WITHOUT_SUPPORT_ITEM_COST
        if role == "UTILITY" and not has_support_item
        else 0.0
    )
    cs_cost = (
        0.0
        if least_cs_index is None
        else LEAST_CS_ELSEWHERE_COST
        if has_least_cs and role != "UTILITY"
        else MORE_CS_AS_SUPPORT_COST
        if not has_least_cs and role == "UTILITY"
        else 0.0
    )
    return spell_cost + smite_cost + support_item_cost + cs_cost
