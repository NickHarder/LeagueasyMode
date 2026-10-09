from pathlib import Path
from typing import Final

from leagueasymode.accuracy_history import (
    GameAccuracy,
    append_game_accuracy,
    history_lines,
    read_accuracy_history,
)
from leagueasymode.scoring import EstimatorScore

SCORED_AT: Final = "2026-10-09T00:00:00+00:00"


def game_with(recording_name: str, roles: float, gold: float, brier: float) -> GameAccuracy:
    return GameAccuracy(
        recording_name=recording_name,
        game_id=None,
        game_version="16.19.1",
        scored_at=SCORED_AT,
        scores=(
            EstimatorScore("roles", 10, roles, "share_correct"),
            EstimatorScore("gold earned", 100, gold, "mean_absolute_error_gold"),
            EstimatorScore("win chance", 30, brier, "brier_score"),
        ),
    )


def test_each_game_is_kept_once_and_read_back(tmp_path: Path) -> None:
    history_path = tmp_path / "accuracy-history.jsonl"
    first = game_with("game-1.jsonl.xz", 0.8, 300.0, 0.2)
    append_game_accuracy(history_path, first)
    append_game_accuracy(history_path, game_with("game-2.jsonl.xz", 0.9, 250.0, 0.18))
    # Scoring a game again replaces its line.
    rescored = game_with("game-1.jsonl.xz", 1.0, 200.0, 0.1)
    append_game_accuracy(history_path, rescored)
    history = read_accuracy_history(history_path)
    assert [game.recording_name for game in history] == ["game-2.jsonl.xz", "game-1.jsonl.xz"]
    assert history[1] == rescored


def test_a_missing_file_is_no_history_and_a_broken_line_is_skipped(tmp_path: Path) -> None:
    history_path = tmp_path / "accuracy-history.jsonl"
    assert read_accuracy_history(history_path) == []
    append_game_accuracy(history_path, game_with("game-1.jsonl.xz", 0.8, 300.0, 0.2))
    with history_path.open("a") as history_file:
        history_file.write("{not json\n")
    assert len(read_accuracy_history(history_path)) == 1


def test_each_estimator_shows_its_last_game_its_average_and_where_it_is_heading() -> None:
    history = [
        game_with(f"game-{index}.jsonl.xz", 0.5 + index * 0.05, 400.0 - index * 20, 0.2)
        for index in range(10)
    ]
    assert history_lines(history) == [
        "roles: last game 95%; 10 games 72%; better",
        "gold earned: last game 220 gold off; 10 games 310 gold off; better",
        "win chance: last game Brier 0.200; 10 games Brier 0.200; steady",
    ]


def test_the_average_weighs_each_game_by_its_samples() -> None:
    small = GameAccuracy(
        recording_name="game-1.jsonl.xz",
        game_id=None,
        game_version=None,
        scored_at=SCORED_AT,
        scores=(EstimatorScore("roles", 2, 0.0, "share_correct"),),
    )
    large = GameAccuracy(
        recording_name="game-2.jsonl.xz",
        game_id=None,
        game_version=None,
        scored_at=SCORED_AT,
        scores=(EstimatorScore("roles", 8, 1.0, "share_correct"),),
    )
    assert history_lines([small, large]) == ["roles: last game 100%; 2 games 80%"]


def test_only_the_last_games_count() -> None:
    history = [game_with(f"game-{index}.jsonl.xz", 0.0, 100.0, 0.2) for index in range(5)]
    history.append(game_with("game-5.jsonl.xz", 1.0, 100.0, 0.2))
    assert history_lines(history, last_games=2)[0] == "roles: last game 100%; 2 games 50%"
