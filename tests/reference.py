"""An independent, year-by-year simulation of a fund that keeps its duration constant.

Used only by the tests, to check that the one-line formula in estimator/model.py is what you
get by actually compounding year by year, and that rate moves cancel at 2 × duration − 1.

Timing: a yield change happens at the start of the year. The price moves by
−duration × change, and the fund earns the new yield for the whole year.
"""

from __future__ import annotations

import math


def simulate(
    yield_to_worst: float,
    duration: float,
    fees: float,
    yield_changes: list[float],
    default_rates: list[float],
    recovery_rates: list[float],
) -> list[float]:
    """Total return for each year."""
    assert len(yield_changes) == len(default_rates) == len(recovery_rates)
    current_yield = yield_to_worst
    returns = []
    for change, default_rate, recovery_rate in zip(yield_changes, default_rates, recovery_rates):
        current_yield += change
        price_effect = -duration * change
        defaults = default_rate * (1 - recovery_rate) + default_rate * current_yield / 2
        returns.append(current_yield - fees - defaults + price_effect)
    return returns


def irr(returns: list[float]) -> float:
    """Annualized return of a lump sum earning these yearly returns."""
    return math.prod(1 + r for r in returns) ** (1 / len(returns)) - 1
