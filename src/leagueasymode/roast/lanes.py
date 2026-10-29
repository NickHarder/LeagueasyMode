"""Who laned against whom, and how a lane went by our thresholds."""

from leagueasymode.roast.players import RoastPlayer
from leagueasymode.roast.rules import LaneRules


def lane_opponents(players: list[RoastPlayer]) -> dict[int, int]:
    """Pair each player with the enemy in the same position.

    Args:
        players: Every player of the game.

    Returns:
        Each participant id's lane opponent. A position a team lacks, or fills twice, pairs nobody,
        nor does a player with no position.
    """
    by_team_and_position: dict[tuple[int, str], list[RoastPlayer]] = {}
    for player in players:
        by_team_and_position.setdefault((player.team_id, player.position), []).append(player)
    opponents: dict[int, int] = {}
    for (team_id, position), team_players in by_team_and_position.items():
        enemy_players = [
            same_position_players
            for (other_team_id, other_position), same_position_players in (
                by_team_and_position.items()
            )
            if other_team_id != team_id and other_position == position
        ]
        has_one_opponent = len(enemy_players) == 1 and len(enemy_players[0]) == 1
        if position and len(team_players) == 1 and has_one_opponent:
            opponents[team_players[0].participant_id] = enemy_players[0][0].participant_id
    return opponents


def lane_outcome(gold_difference: int, rules: LaneRules) -> str:
    """Name a lane's outcome from the gold difference at 14:00, by our thresholds.

    Args:
        gold_difference: The player's gold minus their opponent's.
        rules: The thresholds.

    Returns:
        "won", "even", "lost" or "gap".
    """
    if gold_difference >= rules.won_gold:
        return "won"
    if gold_difference <= -rules.gap_gold:
        return "gap"
    if gold_difference <= -rules.won_gold:
        return "lost"
    return "even"


def lane_outcome_formula(rules: LaneRules) -> str:
    """Say the lane rule in words, for the outcome exhibit's source.

    Args:
        rules: The thresholds.

    Returns:
        The rule, with its numbers.
    """
    return (
        f"our rule: gold difference at 14:00 of +{rules.won_gold:,} or more is won, "
        f"-{rules.gap_gold:,} or less is a gap, -{rules.won_gold:,} or less is lost, anything "
        "else is even"
    )
