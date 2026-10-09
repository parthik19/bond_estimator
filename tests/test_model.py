import pytest

from estimator.model import default_loss, expected_irr, horizon_years, rounded_years
from tests.reference import irr, simulate


# --- Hand calculations -------------------------------------------------------------------

def test_default_loss_is_unrecovered_principal_plus_half_a_years_yield():
    # 5% default at 40% recovery loses 3% of principal; plus 5% × 8% / 2 = 0.2% of income.
    assert default_loss(0.05, 0.40, 0.08) == pytest.approx(0.032, abs=1e-15)


def test_no_defaults_means_yield_minus_costs():
    assert expected_irr(0.07, 0.001, 0.0005, 0.0, 0.4) == pytest.approx(0.0685, abs=1e-15)


@pytest.mark.parametrize(
    "default_rate, recovery_rate, expected",
    [
        # SPHY-like inputs: YTW 7.32%, expense ratio 0.05%, no tracking drag.
        # 7.32 − 0.05 − (1.5 × 0.60 + 1.5 × 7.32 / 2 / 100) = 6.3151%
        (0.015, 0.40, 0.063151),
        # 7.32 − 0.05 − (3.4 × 0.60 + 3.4 × 7.32 / 2 / 100) = 5.10556%
        (0.034, 0.40, 0.0510556),
        # 7.32 − 0.05 − (6.0 × 0.70 + 6.0 × 7.32 / 2 / 100) = 2.8504%
        (0.060, 0.30, 0.028504),
    ],
)
def test_irr_matches_hand_calculation(default_rate, recovery_rate, expected):
    assert expected_irr(0.0732, 0.0005, 0.0, default_rate, recovery_rate) == pytest.approx(
        expected, abs=1e-12
    )


def test_full_recovery_still_loses_half_a_years_income():
    assert default_loss(0.10, 1.0, 0.06) == pytest.approx(0.003, abs=1e-15)


def test_total_default_with_no_recovery_loses_everything_plus_income():
    assert default_loss(1.0, 0.0, 0.06) == pytest.approx(1.03, abs=1e-15)


# --- Direction of effects ----------------------------------------------------------------

def test_more_defaults_lower_the_irr():
    assert expected_irr(0.07, 0.001, 0, 0.05, 0.4) < expected_irr(0.07, 0.001, 0, 0.02, 0.4)


def test_higher_recovery_raises_the_irr():
    assert expected_irr(0.07, 0.001, 0, 0.05, 0.6) > expected_irr(0.07, 0.001, 0, 0.05, 0.3)


def test_higher_yield_raises_the_irr():
    assert expected_irr(0.08, 0.001, 0, 0.05, 0.4) > expected_irr(0.07, 0.001, 0, 0.05, 0.4)


def test_costs_subtract_one_for_one():
    base = expected_irr(0.07, 0.0, 0.0, 0.03, 0.4)
    assert expected_irr(0.07, 0.002, 0.001, 0.03, 0.4) == pytest.approx(base - 0.003, abs=1e-15)


# --- Horizon -----------------------------------------------------------------------------

def test_horizon_is_twice_duration_minus_one():
    assert horizon_years(2.94) == pytest.approx(4.88, abs=1e-12)
    assert horizon_years(1.0) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("years, whole", [(4.88, 5), (4.5, 5), (4.49, 4), (1.0, 1), (15.2, 15)])
def test_whole_years_round_halves_up(years, whole):
    assert rounded_years(years) == whole


# --- The formula agrees with a year-by-year simulation -----------------------------------

@pytest.mark.parametrize("years", [1, 5, 12])
def test_formula_equals_compounding_year_by_year_when_yields_hold(years):
    ytw, fees, default_rate, recovery_rate = 0.0732, 0.0008, 0.034, 0.40
    returns = simulate(ytw, 2.94, fees, [0.0] * years, [default_rate] * years, [recovery_rate] * years)
    assert irr(returns) == pytest.approx(
        expected_irr(ytw, fees, 0.0, default_rate, recovery_rate), abs=1e-12
    )


def test_reference_simulation_prices_a_rate_rise_by_duration():
    # Start-of-year timing: yields jump 1 point, price falls 3 × 1 = 3%, new 6% yield earned.
    [year_one] = simulate(0.05, 3.0, 0.0, [0.01], [0.0], [0.0])
    assert year_one == pytest.approx(0.06 - 0.03, abs=1e-15)


# --- Why N = 2 × duration − 1 -------------------------------------------------------------

@pytest.mark.parametrize("drift", [0.01, -0.01, 0.003])
def test_steady_yield_drift_cancels_exactly_at_twice_duration_minus_one(drift):
    # Summed yearly returns: the price losses (or gains) are exactly offset by the higher
    # (or lower) yield earned, at N = 2 × 3 − 1 = 5 years and no other N.
    duration, ytw, fees = 3.0, 0.07, 0.001
    for years in range(1, 11):
        returns = simulate(ytw, duration, fees, [drift] * years, [0.0] * years, [0.0] * years)
        gap = sum(returns) - years * (ytw - fees)
        if years == 5:
            assert gap == pytest.approx(0.0, abs=1e-12)
        else:
            assert abs(gap) > 1e-4


@pytest.mark.parametrize("drift", [0.01, -0.01])
def test_compounded_irr_is_closest_to_the_starting_yield_at_twice_duration_minus_one(drift):
    duration, ytw = 3.0, 0.07
    gaps = {}
    for years in range(1, 11):
        returns = simulate(ytw, duration, 0.0, [drift] * years, [0.0] * years, [0.0] * years)
        gaps[years] = abs(irr(returns) - ytw)
    assert min(gaps, key=gaps.get) == 5
    # A full point a year of steady drift moves the 5-year IRR by about 0.01 points.
    assert gaps[5] < 0.0005
