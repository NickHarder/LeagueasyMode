"""Refitting the hand-set models on recorded games (phase 5.5), and keeping their weights.

The win chance (estimator 12) is refit on every minute of every recorded game with its result; the
fights (estimator 10) on every fight of the timelines, by the logarithm of the two sides'
strengths. Each fit is checked on games it did not see: the games are split into ten folds, each
scored by a fit made without its fold, and the fitted weights are kept only when those held-out
scores beat the hand-set weights'. A model is
not refit on fewer than 20 games. The weights kept are written to a file the engine reads at its
start (`LEAGUEASYMODE_MODEL_WEIGHTS`); without it, the hand-set weights stand.
"""

import dataclasses
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from leagueasymode.inference.fights import FIGHT_RULES, FightRules
from leagueasymode.inference.fitting import brier_score, fit_logistic, logistic
from leagueasymode.inference.win_chance import (
    WEIGHT_FIELDS,
    WIN_CHANCE_RULES,
    WinChanceRules,
    WinFeatures,
    feature_vector,
    rules_with_weights,
    weights_of,
    win_chance,
)

MIN_GAMES_TO_FIT: Final = 20
# Games are held out in this many folds: each game is scored by a fit made without its fold.
FOLD_COUNT: Final = 10
# How hard each fit is pulled toward the hand-set weights, in log-likelihood.
PRIOR_STRENGTH: Final = 5.0
WEIGHTS_FILE_VERSION: Final = 1

logger = logging.getLogger(__name__)

# One game's samples: what a model read, and the result (1 for your team, 0 for the other).
type WinSamples = Sequence[tuple[WinFeatures, float]]
type FightSamples = Sequence[tuple[float, float]]


@dataclass(frozen=True)
class RefitResult[Rules]:
    """One model refit: its scores before and after, and the weights fitted on every game."""

    model: str
    game_count: int
    sample_count: int
    # The Brier score of the hand-set weights, and of fits each made without the game scored.
    hand_set_brier: float
    fitted_brier: float
    rules: Rules

    @property
    def is_kept(self) -> bool:
        """Whether the fitted weights scored better on games they did not see."""
        return self.fitted_brier < self.hand_set_brier

    def describe(self) -> str:
        """Return the refit in one line, as `leagueasymode fit` prints it.

        Returns:
            Such as "win chance: 24 games, 712 samples: hand-set 0.201, refit 0.188: kept".
        """
        verdict = "kept" if self.is_kept else "not kept, the hand-set weights stand"
        return (
            f"{self.model}: {self.game_count} games, {self.sample_count} samples: hand-set "
            f"{self.hand_set_brier:.3f}, refit {self.fitted_brier:.3f} (each game held out): "
            f"{verdict}"
        )


@dataclass(frozen=True)
class ModelWeights:
    """The weights the engine uses for the refit models."""

    win_rules: WinChanceRules = WIN_CHANCE_RULES
    fight_rules: FightRules = FIGHT_RULES


def refit_win_chance(
    games: Sequence[WinSamples], rules: WinChanceRules = WIN_CHANCE_RULES
) -> RefitResult[WinChanceRules] | None:
    """Refit the win chance's weights, and check them game by game.

    Args:
        games: Each game's minutes and its result.
        rules: The hand-set weights, which the fit is pulled toward and compared with.

    Returns:
        The refit; None on fewer than 20 games with samples.
    """
    games_with_samples = [game for game in games if game]
    if len(games_with_samples) < MIN_GAMES_TO_FIT:
        return None
    hand_set_weights = weights_of(rules)
    prior = [hand_set_weights[feature] for feature in WEIGHT_FIELDS]

    def fitted(training: Sequence[WinSamples]) -> WinChanceRules:
        samples = [
            (feature_vector(features, rules), result)
            for game in training
            for features, result in game
        ]
        weights = fit_logistic(samples, prior=prior, prior_strength=PRIOR_STRENGTH)
        return rules_with_weights(rules, weights)

    def chances(game: WinSamples, game_rules: WinChanceRules) -> list[float]:
        return [win_chance(features, game_rules).ally_chance for features, _ in game]

    held_out_chances = _held_out(games_with_samples, fitted, chances)
    results = [result for game in _by_fold(games_with_samples) for _, result in game]
    return RefitResult(
        model="win chance",
        game_count=len(games_with_samples),
        sample_count=len(results),
        hand_set_brier=brier_score(
            [chance for game in _by_fold(games_with_samples) for chance in chances(game, rules)],
            results,
        ),
        fitted_brier=brier_score(held_out_chances, results),
        rules=fitted(games_with_samples),
    )


def refit_fights(
    games: Sequence[FightSamples], rules: FightRules = FIGHT_RULES
) -> RefitResult[FightRules] | None:
    """Refit the fights' steepness, and check it game by game.

    Args:
        games: Each game's fights: the logarithm of the two sides' strengths, and the result.
        rules: The hand-set rules, whose steepness the fit is pulled toward and compared with.

    Returns:
        The refit; None on fewer than 20 games with fights.
    """
    games_with_samples = [game for game in games if game]
    if len(games_with_samples) < MIN_GAMES_TO_FIT:
        return None

    def fitted(training: Sequence[FightSamples]) -> FightRules:
        samples = [([log_ratio], result) for game in training for log_ratio, result in game]
        (steepness,) = fit_logistic(samples, prior=[rules.steepness], prior_strength=PRIOR_STRENGTH)
        return dataclasses.replace(rules, steepness=steepness)

    def chances(game: FightSamples, game_rules: FightRules) -> list[float]:
        return [logistic(game_rules.steepness * log_ratio) for log_ratio, _ in game]

    results = [result for game in _by_fold(games_with_samples) for _, result in game]
    return RefitResult(
        model="fights",
        game_count=len(games_with_samples),
        sample_count=len(results),
        hand_set_brier=brier_score(
            [chance for game in _by_fold(games_with_samples) for chance in chances(game, rules)],
            results,
        ),
        fitted_brier=brier_score(_held_out(games_with_samples, fitted, chances), results),
        rules=fitted(games_with_samples),
    )


def save_model_weights(weights_path: Path, weights: ModelWeights) -> None:
    """Write the weights the engine uses, replacing the file whole.

    Args:
        weights_path: The file.
        weights: The weights.
    """
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = weights_path.with_suffix(".partial")
    partial_path.write_text(
        json.dumps(
            {
                "version": WEIGHTS_FILE_VERSION,
                "win_chance": dataclasses.asdict(weights.win_rules),
                "fights": dataclasses.asdict(weights.fight_rules),
            },
            indent=2,
        )
        + "\n"
    )
    partial_path.replace(weights_path)


def load_model_weights(weights_path: Path) -> ModelWeights | None:
    """Read the weights the engine uses.

    Args:
        weights_path: The file.

    Returns:
        The weights; None when the file is missing or cannot be read, so the hand-set ones stand.
    """
    try:
        payload = json.loads(weights_path.read_text())
        return ModelWeights(
            win_rules=WinChanceRules(**payload["win_chance"]),
            fight_rules=FightRules(**payload["fights"]),
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning(
            "could not read the model weights in %s; the hand-set ones stand", weights_path
        )
        return None


def _by_fold[Game](games: Sequence[Game]) -> list[Game]:
    """Return the games in the order the held-out scores take them: fold by fold.

    Args:
        games: The games.

    Returns:
        The games, those of the first fold first.
    """
    return [game for fold in range(FOLD_COUNT) for game in _fold(games, fold)]


def _fold[Game](games: Sequence[Game], fold: int) -> list[Game]:
    """Return the games of one fold: every tenth, from the fold's number.

    Args:
        games: The games.
        fold: The fold, from 0.

    Returns:
        Its games.
    """
    return [game for index, game in enumerate(games) if index % FOLD_COUNT == fold]


def _held_out[Game, Rules](
    games: Sequence[Game],
    fitted: Callable[[Sequence[Game]], Rules],
    chances: Callable[[Game, Rules], list[float]],
) -> list[float]:
    """Return each game's chances from a fit made without its fold, fold by fold.

    Args:
        games: The games.
        fitted: Fits rules on some games.
        chances: Gives a game's chances under some rules.

    Returns:
        The chances, in the order of `_by_fold`.
    """
    return [
        chance
        for fold in range(FOLD_COUNT)
        for fold_rules in [
            fitted([game for index, game in enumerate(games) if index % FOLD_COUNT != fold])
        ]
        for game in _fold(games, fold)
        for chance in chances(game, fold_rules)
    ]
