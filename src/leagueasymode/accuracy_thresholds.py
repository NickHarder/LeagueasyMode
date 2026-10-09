"""The estimators' thresholds (phase 6.2): what CI holds every recorded game in the repository to.

The plan: "CI fails if any estimator drops below its threshold on the recorded games. The
thresholds get set from the first batch of recordings and are never lowered to make a test pass."
The thresholds live in `tests/accuracy_thresholds.json`, by estimator; whether a score must reach
its threshold or stay under it follows its measure (a share must reach it, an error stay under
it). `leagueasymode thresholds <recordings>` proposes them from 20 games or more: each estimator's
average less one standard deviation across the games, toward the worse side, so that one unlucky
game does not fail CI. A proposal is only ever adopted where it is not lower than the threshold
it replaces.
"""

import json
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from leagueasymode.scoring import MEASURE_DIRECTION, EstimatorScore

MIN_GAMES_FOR_THRESHOLDS: Final = 20
MARGIN_DEVIATIONS: Final = 1.0
THRESHOLD_DECIMALS: Final = 3


def load_thresholds(thresholds_path: Path) -> dict[str, float]:
    """Return each estimator's threshold.

    Args:
        thresholds_path: The thresholds file, `{"thresholds": {"roles": 0.9, ...}}`.

    Returns:
        The thresholds by estimator; none when the file is missing.
    """
    try:
        payload = json.loads(thresholds_path.read_text())
    except FileNotFoundError:
        return {}
    return {str(estimator): float(value) for estimator, value in payload["thresholds"].items()}


def is_within(measure: str, value: float, threshold: float) -> bool:
    """Return whether a score meets its threshold.

    Args:
        measure: How it is measured.
        value: The score.
        threshold: The threshold.

    Returns:
        Whether a share reaches it, or an error stays at or under it.
    """
    if MEASURE_DIRECTION.get(measure) == "higher":
        return value >= threshold
    return value <= threshold


def threshold_misses(
    recording_name: str, scores: Sequence[EstimatorScore], thresholds: Mapping[str, float]
) -> list[str]:
    """Return the scores of a recorded game that miss their thresholds, in words.

    Args:
        recording_name: The recording's file name.
        scores: The game's scores.
        thresholds: Each estimator's threshold; an estimator without one is not held.

    Returns:
        A line for each miss.
    """
    return [
        f"{recording_name}: {score.estimator} scored {score.value:.3f}, its threshold is "
        f"{thresholds[score.estimator]:.3f} ({MEASURE_DIRECTION.get(score.measure, 'lower')} is "
        "better)"
        for score in scores
        if score.estimator in thresholds
        and not is_within(score.measure, score.value, thresholds[score.estimator])
    ]


def proposed_thresholds(games: Sequence[Sequence[EstimatorScore]]) -> dict[str, float]:
    """Return a threshold for each estimator scored on 20 games or more.

    Args:
        games: Each game's scores.

    Returns:
        Each estimator's average less one standard deviation across the games, toward the worse
        side; an estimator scored on fewer games has none.
    """
    values: defaultdict[str, list[float]] = defaultdict(list)
    measures: dict[str, str] = {}
    for scores in games:
        for score in scores:
            values[score.estimator].append(score.value)
            measures[score.estimator] = score.measure
    return {
        estimator: round(
            statistics.fmean(estimator_values)
            + _worse_sign(measures[estimator])
            * MARGIN_DEVIATIONS
            * statistics.stdev(estimator_values),
            THRESHOLD_DECIMALS,
        )
        for estimator, estimator_values in values.items()
        if len(estimator_values) >= MIN_GAMES_FOR_THRESHOLDS
    }


def stricter_thresholds(
    existing: Mapping[str, float], proposed: Mapping[str, float], measures: Mapping[str, str]
) -> dict[str, float]:
    """Return the thresholds a proposal leaves: each the stricter of the two, never looser.

    Args:
        existing: The thresholds held now.
        proposed: The proposal.
        measures: Each estimator's measure, for which way is stricter.

    Returns:
        The thresholds: a new estimator's from the proposal, every other the stricter.
    """
    merged = dict(existing)
    for estimator, threshold in proposed.items():
        held = existing.get(estimator)
        if held is None:
            merged[estimator] = threshold
        elif MEASURE_DIRECTION.get(measures.get(estimator, "")) == "higher":
            merged[estimator] = max(held, threshold)
        else:
            merged[estimator] = min(held, threshold)
    return merged


def save_thresholds(thresholds_path: Path, thresholds: Mapping[str, float]) -> None:
    """Write the thresholds file.

    Args:
        thresholds_path: The file.
        thresholds: Each estimator's threshold.
    """
    thresholds_path.write_text(
        json.dumps({"thresholds": dict(sorted(thresholds.items()))}, indent=2) + "\n"
    )


def _worse_sign(measure: str) -> float:
    """Return the direction a score gets worse in.

    Args:
        measure: How it is measured.

    Returns:
        -1 for a share, which gets worse going down; 1 for an error.
    """
    return -1.0 if MEASURE_DIRECTION.get(measure) == "higher" else 1.0
