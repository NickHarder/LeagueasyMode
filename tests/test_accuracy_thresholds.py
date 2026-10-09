"""The estimators' thresholds on the recorded games in the repository (phase 6.2).

The plan: "CI fails if any estimator drops below its threshold on the recorded games. The
thresholds get set from the first batch of recordings and are never lowered to make a test pass."
Until the first anonymized recordings land in `tests/recordings/`, there is nothing to hold.
"""

import asyncio
from pathlib import Path
from typing import Final

import pytest

from leagueasymode.accuracy_thresholds import (
    MIN_GAMES_FOR_THRESHOLDS,
    is_within,
    load_thresholds,
    proposed_thresholds,
    stricter_thresholds,
    threshold_misses,
)
from leagueasymode.data_dragon import PatchStatsStore, load_patch_stats
from leagueasymode.patch_data import GAME_VERSION_PATH, game_version_of
from leagueasymode.scoring import ESTIMATOR_NAMES, EstimatorScore, read_recorded_game, score_game

RECORDINGS_DIRECTORY: Final = Path(__file__).parent / "recordings"
THRESHOLDS_PATH: Final = Path(__file__).parent / "accuracy_thresholds.json"


def recordings_in_the_repository() -> list[Path]:
    return sorted(RECORDINGS_DIRECTORY.glob("*.jsonl.xz"))


def test_every_recording_in_the_repository_meets_its_thresholds() -> None:
    thresholds = load_thresholds(THRESHOLDS_PATH)
    misses: list[str] = []
    for recording_path in recordings_in_the_repository():
        game = read_recorded_game(recording_path)
        patch_stats = asyncio.run(
            load_patch_stats(
                None,
                PatchStatsStore(RECORDINGS_DIRECTORY / "patch-data"),
                game_version_of(game.client_resources.get(GAME_VERSION_PATH)),
            )
        )
        misses.extend(
            threshold_misses(recording_path.name, score_game(game, patch_stats), thresholds)
        )
    assert misses == []


def test_only_anonymized_copies_of_recordings_are_in_the_repository() -> None:
    # A raw recording holds other players' names; `leagueasymode anonymize` writes the copy.
    assert all(
        recording_path.name.endswith("-anonymized.jsonl.xz")
        for recording_path in recordings_in_the_repository()
    )


def test_every_threshold_names_an_estimator_the_harness_scores() -> None:
    assert set(load_thresholds(THRESHOLDS_PATH)) <= ESTIMATOR_NAMES


def test_a_share_must_reach_its_threshold_and_an_error_stay_under_it() -> None:
    assert is_within("share_correct", 0.9, 0.85)
    assert not is_within("share_correct", 0.8, 0.85)
    assert is_within("mean_absolute_error_gold", 300.0, 350.0)
    assert not is_within("brier_score", 0.26, 0.2)


def test_a_miss_names_the_recording_the_estimator_and_both_numbers() -> None:
    scores = [
        EstimatorScore("roles", 10, 0.7, "share_correct"),
        EstimatorScore("gold earned", 90, 280.0, "mean_absolute_error_gold"),
        EstimatorScore("map", 100, 900.0, "mean_distance_units"),
    ]
    thresholds = {"roles": 0.8, "gold earned": 300.0}
    assert threshold_misses("game-1.jsonl.xz", scores, thresholds) == [
        "game-1.jsonl.xz: roles scored 0.700, its threshold is 0.800 (higher is better)"
    ]


def scores_of(index: int) -> list[EstimatorScore]:
    return [
        EstimatorScore("roles", 10, 0.8 + 0.01 * (index % 3), "share_correct"),
        EstimatorScore("win chance", 30, 0.2 + 0.01 * (index % 3), "brier_score"),
    ]


def test_thresholds_are_proposed_as_the_average_less_a_deviation() -> None:
    games = [scores_of(index) for index in range(MIN_GAMES_FOR_THRESHOLDS + 1)]
    proposed = proposed_thresholds(games)
    # Seven games each of 0.80, 0.81 and 0.82: the average 0.81, a deviation of about 0.0082.
    assert proposed["roles"] == pytest.approx(0.81 - 0.0082, abs=1e-3)
    assert proposed["win chance"] == pytest.approx(0.21 + 0.0082, abs=1e-3)


def test_no_threshold_is_proposed_from_too_few_games() -> None:
    games = [scores_of(index) for index in range(MIN_GAMES_FOR_THRESHOLDS - 1)]
    assert proposed_thresholds(games) == {}


def test_a_proposal_never_loosens_a_threshold() -> None:
    measures = {"roles": "share_correct", "win chance": "brier_score", "map": "mean_distance_units"}
    existing = {"roles": 0.85, "win chance": 0.2}
    proposed = {"roles": 0.8, "win chance": 0.18, "map": 900.0}
    assert stricter_thresholds(existing, proposed, measures) == {
        "roles": 0.85,
        "win chance": 0.18,
        "map": 900.0,
    }
