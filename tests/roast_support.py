"""Built games for the roast's tests: players and exhibits as the families will make them.

Slice 11.2's families build these from the client's answers; until then a test states a game's
lanes and scoreboard and gets the same exhibits, sourced the same way.
"""

from typing import Final

from leagueasymode.roast.exhibits import Exhibit, ExhibitLedger, ExhibitSource
from leagueasymode.roast.lanes import lane_outcome, lane_outcome_formula
from leagueasymode.roast.numbers import format_count, format_signed
from leagueasymode.roast.players import RoastPlayer
from leagueasymode.roast.rules import LaneRules

POSITIONS: Final = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
OUR_CHAMPIONS: Final = ("Garen", "Lee Sin", "Ahri", "Jinx", "Lulu")
THEIR_CHAMPIONS: Final = ("Darius", "Vi", "Syndra", "Kai'Sa", "Nautilus")
GAME_ID: Final = 9000000101
DEFENDANT_ID: Final = 3
# Fixture 101 of nothingsmyfault: mid won its lane, top and bot lost theirs, the jungle was a gap.
TEAM_DIFF_GOLD: Final = (-792, -1661, 1013, -810, -131)
TEAM_DIFF_SCORES: Final = (
    (1, 6, 3),
    (1, 9, 4),
    (7, 2, 3),
    (2, 7, 4),
    (0, 2, 8),
    (6, 3, 5),
    (8, 2, 12),
    (2, 4, 6),
    (9, 2, 7),
    (1, 0, 18),
)


def built_players(
    *, our_team_won: bool = False, friends: frozenset[int] = frozenset()
) -> list[RoastPlayer]:
    """Return ten players: participants 1 to 5 on blue side, 6 to 10 on red, top to support.

    Args:
        our_team_won: Whether blue side, the defendant's, won.
        friends: The participant ids on the owner's friends list.

    Returns:
        The players.
    """
    return [
        RoastPlayer(
            participant_id=index + 1 + side * 5,
            team_id=100 if side == 0 else 200,
            position=POSITIONS[index],
            champion=(OUR_CHAMPIONS if side == 0 else THEIR_CHAMPIONS)[index],
            won=our_team_won if side == 0 else not our_team_won,
            is_friend=index + 1 + side * 5 in friends,
        )
        for side in (0, 1)
        for index in range(5)
    ]


def built_ledger(
    gold_differences: tuple[int | None, ...] = TEAM_DIFF_GOLD,
    scores: tuple[tuple[int, int, int], ...] = TEAM_DIFF_SCORES,
    *,
    distinct_victims: dict[int, int] | None = None,
) -> ExhibitLedger:
    """Return a game's exhibits: the scoreboard, and each lane's gold against its opponent at 14:00.

    Args:
        gold_differences: Blue side's gold minus red side's in each lane, top to support; None for
            a lane the game did not pair.
        scores: Each participant's kills, deaths and assists, 1 to 10.
        distinct_victims: How many different players a participant killed, where it matters.

    Returns:
        The ledger.
    """
    exhibits: list[Exhibit] = [
        Exhibit(
            key="clock_14",
            label="The timeline's frame for minute 14",
            value=840000,
            display="14:00",
            unit="game clock",
            source=ExhibitSource(kind="timeline", path="frames[14].timestamp"),
        )
    ]
    for participant_index, (kills, deaths, assists) in enumerate(scores):
        participant_id = participant_index + 1
        for name, value in (("kills", kills), ("deaths", deaths), ("assists", assists)):
            exhibits.append(
                Exhibit(
                    key=f"{name}/p{participant_id}",
                    label=f"Participant {participant_id}'s {name}",
                    value=value,
                    display=format_count(value),
                    unit=name,
                    source=ExhibitSource(
                        kind="game", path=f"participants[{participant_index}].stats.{name}"
                    ),
                    participant_id=participant_id,
                )
            )
    for killer_id, victim_count in (distinct_victims or {}).items():
        exhibits.append(
            Exhibit(
                key=f"distinct_victims/p{killer_id}",
                label=f"Different players participant {killer_id} killed",
                value=victim_count,
                display=format_count(victim_count),
                unit="players",
                source=ExhibitSource(kind="computation", formula="different victims"),
                participant_id=killer_id,
            )
        )
    for lane_index, difference in enumerate(gold_differences):
        if difference is not None:
            exhibits.extend(_lane_exhibits(lane_index + 1, lane_index + 6, difference))
            exhibits.extend(_lane_exhibits(lane_index + 6, lane_index + 1, -difference))
    return ExhibitLedger(game_id=GAME_ID, exhibits={exhibit.key: exhibit for exhibit in exhibits})


def _lane_exhibits(participant_id: int, opponent_id: int, difference: int) -> list[Exhibit]:
    """Return one side of a lane's exhibits at 14:00: the difference, its size and the outcome.

    Args:
        participant_id: The player.
        opponent_id: Their lane opponent.
        difference: The player's gold minus the opponent's.

    Returns:
        The exhibits.
    """
    difference_key = f"gold_diff_14/p{participant_id}"
    sided_name = "gold_ahead_14" if difference > 0 else "gold_behind_14"
    sided = (
        [
            Exhibit(
                key=f"{sided_name}/p{participant_id}",
                label=f"How far participant {participant_id} was from {opponent_id} at 14:00",
                value=abs(difference),
                display=format_count(abs(difference)),
                unit="gold",
                source=ExhibitSource(
                    kind="computation",
                    formula="the gold difference at minute 14, without its sign",
                    input_keys=(difference_key,),
                ),
                participant_id=participant_id,
            )
        ]
        if difference
        else []
    )
    return [
        Exhibit(
            key=difference_key,
            label=f"Participant {participant_id}'s gold against {opponent_id} at 14:00",
            value=difference,
            display=format_signed(difference),
            unit="gold",
            source=ExhibitSource(kind="computation", formula="gold minus the opponent's"),
            participant_id=participant_id,
        ),
        *sided,
        Exhibit(
            key=f"lane_outcome_14/p{participant_id}",
            label=f"Participant {participant_id}'s lane",
            value=lane_outcome(difference, LaneRules()),
            display=lane_outcome(difference, LaneRules()),
            unit="",
            source=ExhibitSource(
                kind="computation",
                formula=lane_outcome_formula(LaneRules()),
                input_keys=(difference_key,),
            ),
            participant_id=participant_id,
        ),
    ]
