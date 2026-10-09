import dataclasses
import math
import random
from pathlib import Path
from typing import Final

import pytest

from leagueasymode.inference.fights import FIGHT_RULES
from leagueasymode.inference.fitting import brier_score, fit_logistic, solve_linear
from leagueasymode.inference.win_chance import WIN_CHANCE_RULES, WinFeatures, win_chance
from leagueasymode.refit import (
    MIN_GAMES_TO_FIT,
    ModelWeights,
    load_model_weights,
    refit_fights,
    refit_win_chance,
    save_model_weights,
)

SEED: Final = 20261009


def test_a_linear_system_is_solved() -> None:
    solution = solve_linear(
        [[2.0, 1.0, -1.0], [-3.0, -1.0, 2.0], [-2.0, 1.0, 2.0]], [8.0, -11.0, -3.0]
    )
    assert solution == pytest.approx([2.0, 3.0, -1.0])


def logistic(log_odds: float) -> float:
    return 1 / (1 + math.exp(-log_odds))


def test_the_fit_finds_the_weights_the_data_came_from() -> None:
    draws = random.Random(SEED)  # noqa: S311  seeded, so that every case can be reproduced
    true_weights = [1.5, -0.8]
    samples = [
        (
            inputs,
            1.0
            if draws.random()
            < logistic(
                sum(weight * value for weight, value in zip(true_weights, inputs, strict=True))
            )
            else 0.0,
        )
        for inputs in ([draws.uniform(-2, 2), draws.uniform(-2, 2)] for _ in range(4000))
    ]
    fitted = fit_logistic(samples, prior=[0.0, 0.0], prior_strength=0.1)
    assert fitted == pytest.approx(true_weights, abs=0.15)


def test_without_data_the_prior_stands_and_a_strong_prior_holds() -> None:
    assert fit_logistic([], prior=[0.4, 2.0], prior_strength=1.0) == pytest.approx([0.4, 2.0])
    samples = [([1.0], 1.0)] * 5 + [([1.0], 0.0)] * 5
    assert fit_logistic(samples, prior=[2.0], prior_strength=1e6) == pytest.approx([2.0], abs=1e-3)


def test_the_brier_score_is_the_mean_squared_miss() -> None:
    assert brier_score([0.5, 0.5], [1.0, 0.0]) == pytest.approx(0.25)
    assert brier_score([0.9, 0.2], [1.0, 0.0]) == pytest.approx((0.01 + 0.04) / 2)


def features_at(game_minutes: float, gold_lead: float) -> WinFeatures:
    return WinFeatures(
        game_minutes=game_minutes,
        is_blue_side=True,
        gold_lead=gold_lead,
        gold_lead_deviation=0.0,
        team_gold_scale=30_000.0,
        level_lead=0,
        turret_lead=0,
        inhibitor_lead=0,
        dragon_lead=0,
        soul=0,
        baron=0,
        elder=0,
        ally_alive=5,
        enemy_alive=5,
    )


def games_from(true_gold_weight: float, game_count: int) -> list[list[tuple[WinFeatures, float]]]:
    """Games whose results follow a gold weight other than the hand-set one."""
    draws = random.Random(SEED)  # noqa: S311  seeded, so that every case can be reproduced
    true_rules = dataclasses.replace(WIN_CHANCE_RULES, gold_share_weight=true_gold_weight)
    games: list[list[tuple[WinFeatures, float]]] = []
    for _ in range(game_count):
        lead = draws.uniform(-6000.0, 6000.0)
        features = [features_at(float(minute), lead * minute / 30.0) for minute in range(5, 31)]
        has_won = draws.random() < win_chance(features[-1], true_rules).ally_chance
        games.append([(feature, 1.0 if has_won else 0.0) for feature in features])
    return games


def test_the_win_chance_is_refit_when_held_out_games_score_better() -> None:
    result = refit_win_chance(games_from(true_gold_weight=25.0, game_count=60), WIN_CHANCE_RULES)
    assert result is not None
    assert (result.model, result.game_count, result.sample_count) == ("win chance", 60, 60 * 26)
    assert result.fitted_brier < result.hand_set_brier
    assert result.is_kept
    assert result.rules.gold_share_weight > WIN_CHANCE_RULES.gold_share_weight


def test_too_few_games_are_not_refit() -> None:
    assert refit_win_chance(games_from(25.0, MIN_GAMES_TO_FIT - 1), WIN_CHANCE_RULES) is None


def test_the_fights_steepness_is_refit_from_their_strength_ratios() -> None:
    draws = random.Random(SEED)  # noqa: S311  seeded, so that every case can be reproduced
    games: list[list[tuple[float, float]]] = []
    for _ in range(40):
        ratios = [draws.uniform(-1.0, 1.0) for _ in range(5)]
        games.append(
            [(ratio, 1.0 if draws.random() < logistic(5.0 * ratio) else 0.0) for ratio in ratios]
        )
    result = refit_fights(games, FIGHT_RULES)
    assert result is not None
    assert result.model == "fights"
    assert result.rules.steepness > FIGHT_RULES.steepness


def test_the_weights_are_kept_on_disk_and_read_back(tmp_path: Path) -> None:
    weights_path = tmp_path / "model-weights.json"
    weights = ModelWeights(
        win_rules=dataclasses.replace(WIN_CHANCE_RULES, gold_share_weight=12.5),
        fight_rules=dataclasses.replace(FIGHT_RULES, steepness=2.6),
    )
    save_model_weights(weights_path, weights)
    assert load_model_weights(weights_path) == weights
    assert load_model_weights(tmp_path / "none.json") is None
    (tmp_path / "broken.json").write_text("{not json")
    assert load_model_weights(tmp_path / "broken.json") is None
