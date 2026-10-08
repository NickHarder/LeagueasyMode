"""What a player's record says about them in this game: rank, form, champion and role.

Counted from the League client's answers for the player (`player_intel.py`): their recent games on
Summoner's Rift, newest first. The usual position needs enough games and a clear favourite, so
that a player who fills every role is not called off-role.
"""

from collections import Counter
from typing import Final

from leagueasymode.overlay_state import PlayerIntel
from leagueasymode.player_intel import PlayerRecord

# The usual position is the one at least this share of at least this many recent games were in.
USUAL_POSITION_MIN_GAMES: Final = 5
USUAL_POSITION_MIN_SHARE: Final = 0.6


def player_intel(record: PlayerRecord, champion_id: int, game_position: str) -> PlayerIntel:
    """Return what a player's record says, given the champion and position they have this game.

    Args:
        record: The player's rank and recent games.
        champion_id: The client's id of the champion they play this game.
        game_position: Their position this game, as given or estimated; empty when unknown.

    Returns:
        The intel.
    """
    games = record.recent_games
    champion_games = [game for game in games if game.champion_id == champion_id]
    usual_position = _usual_position([game.position for game in games])
    return PlayerIntel(
        ranked=record.ranked,
        recent_game_count=len(games),
        recent_win_count=sum(1 for game in games if game.is_win),
        streak=_streak([game.is_win for game in games]),
        champion_game_count=len(champion_games),
        champion_win_count=sum(1 for game in champion_games if game.is_win),
        usual_position=usual_position,
        is_off_role=bool(usual_position and game_position and game_position != usual_position),
    )


def _usual_position(positions: list[str]) -> str:
    """Return the position most recent games were in, when one clearly was.

    Args:
        positions: Each recent game's position; empty where unknown.

    Returns:
        The position, or empty when there are too few games or no clear favourite.
    """
    known_positions = [position for position in positions if position]
    if len(known_positions) < USUAL_POSITION_MIN_GAMES:
        return ""
    position, count = Counter(known_positions).most_common(1)[0]
    return position if count / len(known_positions) >= USUAL_POSITION_MIN_SHARE else ""


def _streak(results_newest_first: list[bool]) -> int:
    """Return the run of equal results from the latest game.

    Args:
        results_newest_first: Each recent game's result, True for a win.

    Returns:
        The run's length, positive for wins and negative for losses; 0 without games.
    """
    if not results_newest_first:
        return 0
    latest = results_newest_first[0]
    run_length = next(
        (index for index, result in enumerate(results_newest_first) if result != latest),
        len(results_newest_first),
    )
    return run_length if latest else -run_length
