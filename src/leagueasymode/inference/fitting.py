"""Logistic regression for refitting the hand-set models (phase 5.5), with no new dependency.

The fit maximizes the likelihood of the results less a pull toward the hand-set weights (a normal
prior, a ridge around them): with few games the hand-set weights stand, with many the data speaks.
Newton's method finds the optimum, a linear system solved by Gaussian elimination at each step;
with a dozen weights or fewer that is quick, and the optimum is unique since the objective is
strictly concave.
"""

import math
from collections.abc import Sequence
from typing import Final

MAX_NEWTON_STEPS: Final = 50
# The fit stops once no weight moves by more than this in a step.
CONVERGED_STEP: Final = 1e-9


def solve_linear(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    """Return the solution of a square linear system, by Gaussian elimination.

    Args:
        matrix: The system's matrix, one row a list.
        vector: Its right-hand side.

    Returns:
        The solution.

    Raises:
        ValueError: When the matrix is singular.
    """
    size = len(vector)
    rows = [[*matrix[index], vector[index]] for index in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda index: abs(rows[index][column]))
        if abs(rows[pivot][column]) < 1e-12:
            message = "the matrix is singular"
            raise ValueError(message)
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for index in range(column + 1, size):
            factor = rows[index][column] / rows[column][column]
            rows[index] = [
                value - factor * pivot_value
                for value, pivot_value in zip(rows[index], rows[column], strict=True)
            ]
    solution = [0.0] * size
    for index in reversed(range(size)):
        known = sum(rows[index][other] * solution[other] for other in range(index + 1, size))
        solution[index] = (rows[index][size] - known) / rows[index][index]
    return solution


def fit_logistic(
    samples: Sequence[tuple[Sequence[float], float]],
    *,
    prior: Sequence[float],
    prior_strength: float,
) -> list[float]:
    """Return the weights of a logistic model fitted to samples, pulled toward a prior.

    Args:
        samples: Each sample's inputs and result (1 for a win, 0 for a loss); no intercept is
            added, so a model that needs one carries a constant input.
        prior: The weights the fit is pulled toward, the hand-set ones.
        prior_strength: How hard: the log-likelihood a unit of distance from them costs, squared
            and halved.

    Returns:
        The fitted weights, in the inputs' order.
    """
    weights = list(prior)
    for _ in range(MAX_NEWTON_STEPS):
        gradient = [
            prior_strength * (weight - start) for weight, start in zip(weights, prior, strict=True)
        ]
        hessian = [
            [prior_strength if row == column else 0.0 for column in range(len(prior))]
            for row in range(len(prior))
        ]
        for inputs, result in samples:
            # Most inputs are 0 at most moments (no Baron, no soul), so only the others count.
            nonzero = [(index, value) for index, value in enumerate(inputs) if value]
            chance = logistic(sum(weights[index] * value for index, value in nonzero))
            spread = chance * (1 - chance)
            for row, row_value in nonzero:
                gradient[row] += (chance - result) * row_value
                for column, column_value in nonzero:
                    hessian[row][column] += spread * row_value * column_value
        step = solve_linear(hessian, gradient)
        weights = [weight - change for weight, change in zip(weights, step, strict=True)]
        if max((abs(change) for change in step), default=0.0) < CONVERGED_STEP:
            break
    return weights


def brier_score(chances: Sequence[float], results: Sequence[float]) -> float:
    """Return the mean squared distance of chances from results.

    Args:
        chances: The chances given.
        results: What happened, 1 or 0 each.

    Returns:
        The score: 0.25 for a coin flip each time, 0 for a sure and right answer each time.
    """
    return sum(
        (chance - result) ** 2 for chance, result in zip(chances, results, strict=True)
    ) / len(chances)


def logistic(log_odds: float) -> float:
    """Return the chance of log-odds, without overflow.

    Args:
        log_odds: The log-odds.

    Returns:
        The chance.
    """
    if log_odds < 0:
        return math.exp(log_odds) / (1 + math.exp(log_odds))
    return 1 / (1 + math.exp(-log_odds))
