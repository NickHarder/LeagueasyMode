"""What a player's record says about them in this game: rank, form, champion and role.

Counted from the League client's answers for the player (`player_intel.py`): their recent games on
Summoner's Rift, newest first. The usual position needs enough games and a clear favourite, so
that a player who fills every role is not called off-role; the same games say whether this game's
champion is their main or the only one they play. A likely jungler's usual start, and
where they usually are at 4:00, are the sides most of their recent jungle games found them on
(`jungle_starts.py`).
"""

from collections import Counter
from typing import Final

from pydantic import BaseModel, ConfigDict

from leagueasymode.jungle_starts import four_minute_half, start_half
from leagueasymode.overlay_state import PlayerIntel
from leagueasymode.player_intel import PlayerRecord


class IntelRules(BaseModel):
    """The intel's hand-set thresholds: `tuning.json`'s "intel"."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # The usual position is the one at least this share of at least this many recent games were
    # in.
    usual_position_min_games: int = 5
    usual_position_min_share: float = 0.6
    # A champion is their main when they played it more than any other, in at least this many
    # games; a one-trick when at least this share of at least this many recent games were on it.
    main_champion_min_games: int = 3
    one_trick_min_games: int = 8
    one_trick_min_share: float = 0.7


INTEL_RULES: Final = IntelRules()


def player_intel(
    record: PlayerRecord,
    champion_id: int,
    game_position: str,
    *,
    team: str = "",
    rules: IntelRules = INTEL_RULES,
) -> PlayerIntel:
    """Return what a player's record says, given the champion and position they have this game.

    Args:
        record: The player's rank and recent games.
        champion_id: The client's id of the champion they play this game.
        game_position: Their position this game, as given or estimated; empty when unknown.
        team: Their team this game, "ORDER" or "CHAOS", which puts a jungle start on the top or
            the bottom half of the map; empty when unknown.
        rules: The hand-set thresholds.

    Returns:
        The intel.
    """
    games = record.recent_games
    champion_games = [game for game in games if game.champion_id == champion_id]
    usual_position = _usual_position([game.position for game in games], rules)
    jungle_starts = record.jungle_starts
    jungle_start_side = jungle_starts.usual_side if jungle_starts else None
    four_minute_sides = record.four_minute_sides
    usual_four_minute_side = four_minute_sides.usual_side if four_minute_sides else None
    usual_four_minute_half = (
        four_minute_half(usual_four_minute_side, team) if usual_four_minute_side else None
    )
    return PlayerIntel(
        ranked=record.ranked,
        recent_game_count=len(games),
        recent_win_count=sum(1 for game in games if game.is_win),
        streak=_streak([game.is_win for game in games]),
        champion_game_count=len(champion_games),
        champion_win_count=sum(1 for game in champion_games if game.is_win),
        usual_position=usual_position,
        is_off_role=bool(usual_position and game_position and game_position != usual_position),
        jungle_start_side=jungle_start_side,
        jungle_start_half=start_half(jungle_start_side, team) if jungle_start_side else None,
        jungle_start_count=jungle_starts.usual_count if jungle_starts else 0,
        jungle_start_games=jungle_starts.game_count if jungle_starts else 0,
        four_minute_half=usual_four_minute_half,
        four_minute_count=four_minute_sides.usual_count if four_minute_sides else 0,
        four_minute_games=four_minute_sides.game_count if four_minute_sides else 0,
        champion_pool_size=len({game.champion_id for game in games}),
        is_main_champion=_is_main_champion(
            [game.champion_id for game in games], champion_id, rules
        ),
        is_one_trick=len(games) >= rules.one_trick_min_games
        and len(champion_games) >= rules.one_trick_min_share * len(games),
    )


def _is_main_champion(champion_ids: list[int], champion_id: int, rules: IntelRules) -> bool:
    """Return whether a champion is the one a player's recent games were on most.

    Args:
        champion_ids: Each recent game's champion.
        champion_id: The champion they play this game.
        rules: The hand-set thresholds.

    Returns:
        Whether it was played in more recent games than any other, and in at least three.
    """
    most_played = Counter(champion_ids).most_common(2)
    if not most_played or most_played[0][0] != champion_id:
        return False
    game_count = most_played[0][1]
    runner_up_count = most_played[1][1] if len(most_played) > 1 else 0
    return game_count >= rules.main_champion_min_games and game_count > runner_up_count


def _usual_position(positions: list[str], rules: IntelRules) -> str:
    """Return the position most recent games were in, when one clearly was.

    Args:
        positions: Each recent game's position; empty where unknown.
        rules: The hand-set thresholds.

    Returns:
        The position, or empty when there are too few games or no clear favourite.
    """
    known_positions = [position for position in positions if position]
    if len(known_positions) < rules.usual_position_min_games:
        return ""
    position, count = Counter(known_positions).most_common(1)[0]
    return position if count / len(known_positions) >= rules.usual_position_min_share else ""


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
