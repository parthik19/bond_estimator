"""The return arithmetic. docs/PRD.md §2 explains the reasoning."""

from __future__ import annotations

import math


def default_loss(default_rate: float, recovery_rate: float, yield_to_worst: float) -> float:
    """Fraction of the fund lost to defaults in a year.

    The unrecovered principal on the bonds that default, plus half a year's income on them:
    defaults happen throughout the year, so on average a defaulted bond paid half its yield.
    """
    return default_rate * (1 - recovery_rate) + default_rate * yield_to_worst / 2


def expected_irr(
    yield_to_worst: float,
    expense_ratio: float,
    tracking_drag: float,
    default_rate: float,
    recovery_rate: float,
) -> float:
    """Annualized return (= IRR for a lump sum with distributions reinvested)."""
    return (
        yield_to_worst
        - expense_ratio
        - tracking_drag
        - default_loss(default_rate, recovery_rate, yield_to_worst)
    )


def horizon_years(option_adjusted_duration: float) -> float:
    """2 × duration − 1: the horizon over which gradual rate and spread moves cancel out."""
    return 2 * option_adjusted_duration - 1


def rounded_years(years: float) -> int:
    """Whole years, rounding halves up (Python's round() would turn 4.5 into 4)."""
    return math.floor(years + 0.5)
