"""The accuracy history (phase 6.1): every estimator's score on every game played, kept on disk.

`leagueasymode run` scores each game it records once the match timeline has come, and
`leagueasymode score <recording> --keep` scores one by hand; each adds a line to
`accuracy-history.jsonl` in the application's directory (`LEAGUEASYMODE_ACCURACY_HISTORY` moves
it). A game scored again replaces its line. `leagueasymode history` prints, for each estimator,
its last game, its average over the last games weighed by their samples, and whether it is getting
better or worse: the newer half of those games against the older half.

A line names the recording's file, the game's id, its version and the scores; never a player.
"""

import dataclasses
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from leagueasymode.patch_data import GAME_VERSION_PATH, game_version_of
from leagueasymode.scoring import (
    GAME_DETAILS_PATH_PREFIX,
    MEASURE_DIRECTION,
    EstimatorScore,
    RecordedGame,
)

DEFAULT_SHOWN_GAMES: Final = 10
# A trend needs at least this many games in each half.
SMALLEST_TREND_HALF: Final = 3
# A change smaller than this share of the older average is steady.
STEADY_SHARE: Final = 0.02
PERCENT: Final = 100.0
VALUE_FORMATS: Final = {
    "share_correct": "{percent:.0f}%",
    "share_within_band": "{percent:.0f}%",
    "share_matched": "{percent:.0f}%",
    "mean_chance": "{percent:.0f}%",
    "mean_absolute_percent_error": "{value:.1f}% off",
    "mean_absolute_error_gold": "{value:.0f} gold off",
    "mean_absolute_error_experience": "{value:.0f} experience off",
    "mean_distance_units": "{value:.0f} units off",
    "brier_score": "Brier {value:.3f}",
    "fight_brier_score": "Brier {value:.3f}",
    "contest_brier_score": "Brier {value:.3f}",
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameAccuracy:
    """Every estimator's score on one game."""

    # The recording's file name, which says when the game was played and nothing about who.
    recording_name: str
    game_id: int | None
    game_version: str | None
    scored_at: str
    scores: tuple[EstimatorScore, ...]


def game_accuracy_of(
    recording_path: Path, game: RecordedGame, scores: Sequence[EstimatorScore], scored_at: str
) -> GameAccuracy:
    """Return a recorded game's line of the history.

    Args:
        recording_path: The recording.
        game: What the harness read from it.
        scores: Its scores.
        scored_at: When it was scored, as an ISO time.

    Returns:
        The line.
    """
    game_ids = [
        int(path.removeprefix(GAME_DETAILS_PATH_PREFIX))
        for path in game.client_resources
        if path.startswith(GAME_DETAILS_PATH_PREFIX)
        and path.removeprefix(GAME_DETAILS_PATH_PREFIX).isdigit()
    ]
    return GameAccuracy(
        recording_name=recording_path.name,
        game_id=game_ids[0] if game_ids else None,
        game_version=game_version_of(game.client_resources.get(GAME_VERSION_PATH)),
        scored_at=scored_at,
        scores=tuple(scores),
    )


def append_game_accuracy(history_path: Path, accuracy: GameAccuracy) -> None:
    """Add a game's scores to the history, replacing its earlier line; the file is written whole.

    Args:
        history_path: The history file.
        accuracy: The game's scores.
    """
    kept = [
        game
        for game in read_accuracy_history(history_path)
        if game.recording_name != accuracy.recording_name
    ]
    history_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = history_path.with_suffix(".partial")
    partial_path.write_text(
        "".join(json.dumps(dataclasses.asdict(game)) + "\n" for game in [*kept, accuracy])
    )
    partial_path.replace(history_path)


def read_accuracy_history(history_path: Path) -> list[GameAccuracy]:
    """Return the games scored so far, oldest first.

    Args:
        history_path: The history file.

    Returns:
        The games; none when the file is missing. A line that cannot be read is left out.
    """
    try:
        lines = history_path.read_text().splitlines()
    except FileNotFoundError:
        return []
    games: list[GameAccuracy] = []
    for line in lines:
        try:
            payload = json.loads(line)
            games.append(
                GameAccuracy(
                    recording_name=payload["recording_name"],
                    game_id=payload["game_id"],
                    game_version=payload["game_version"],
                    scored_at=payload["scored_at"],
                    scores=tuple(EstimatorScore(**score) for score in payload["scores"]),
                )
            )
        except (ValueError, KeyError, TypeError):
            logger.warning("left out a line of %s that could not be read", history_path)
    return games


def history_lines(
    history: Sequence[GameAccuracy], last_games: int = DEFAULT_SHOWN_GAMES
) -> list[str]:
    """Return each estimator's line: its last game, its average, and where it is heading.

    Args:
        history: The games scored, oldest first.
        last_games: How many of the latest games the average and the trend take.

    Returns:
        A line for each estimator, in the order they first appear.
    """
    shown_games = list(history)[-last_games:]
    estimators = list(
        dict.fromkeys(
            (score.estimator, score.measure) for game in shown_games for score in game.scores
        )
    )
    return [_estimator_line(estimator, measure, shown_games) for estimator, measure in estimators]


def _estimator_line(estimator: str, measure: str, games: Sequence[GameAccuracy]) -> str:
    """Return one estimator's line.

    Args:
        estimator: The estimator.
        measure: How it is measured.
        games: The games shown, oldest first.

    Returns:
        Such as "roles: last game 95%; 10 games 72%; better".
    """
    scores = [
        score
        for game in games
        for score in game.scores
        if (score.estimator, score.measure) == (estimator, measure)
    ]
    line = (
        f"{estimator}: last game {_value_text(measure, scores[-1].value)}; "
        f"{len(scores)} games {_value_text(measure, _weighted_mean(scores))}"
    )
    trend = _trend(measure, scores)
    return f"{line}; {trend}" if trend is not None else line


def _trend(measure: str, scores: Sequence[EstimatorScore]) -> str | None:
    """Return whether an estimator is getting better: its newer half of games against its older.

    Args:
        measure: How it is measured.
        scores: Its scores, oldest first.

    Returns:
        "better", "worse" or "steady"; None with too few games.
    """
    half = len(scores) // 2
    if half < SMALLEST_TREND_HALF:
        return None
    older = _weighted_mean(scores[:half])
    newer = _weighted_mean(scores[-half:])
    if abs(newer - older) <= STEADY_SHARE * abs(older):
        return "steady"
    is_higher_better = MEASURE_DIRECTION.get(measure) == "higher"
    return "better" if (newer > older) == is_higher_better else "worse"


def _weighted_mean(scores: Sequence[EstimatorScore]) -> float:
    """Return scores' average, each game weighed by its samples.

    Args:
        scores: The scores.

    Returns:
        The average.
    """
    samples = sum(score.sample_count for score in scores)
    if samples == 0:
        return sum(score.value for score in scores) / len(scores)
    return sum(score.value * score.sample_count for score in scores) / samples


def _value_text(measure: str, value: float) -> str:
    """Return a score in words.

    Args:
        measure: How it is measured.
        value: The score.

    Returns:
        Such as "95%", "220 gold off" or "Brier 0.200".
    """
    return VALUE_FORMATS.get(measure, "{value:.3f}").format(value=value, percent=value * PERCENT)
