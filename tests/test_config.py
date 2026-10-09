import datetime as dt
from pathlib import Path

import pytest

from estimator.config import ConfigError, load

FIXTURE = Path(__file__).parent / "fixtures" / "fund.toml"
TODAY = dt.date(2026, 2, 1)  # two and a half weeks after the fixture's as_of


def write(tmp_path, text):
    path = tmp_path / "fund.toml"
    path.write_text(text)
    return path


def variant(tmp_path, old, new):
    text = FIXTURE.read_text()
    assert old in text, f"fixture no longer contains {old!r}"
    return write(tmp_path, text.replace(old, new))


def load_error(path, overrides=None, today=TODAY) -> str:
    with pytest.raises(ConfigError) as excinfo:
        load(path, overrides, today=today)
    return str(excinfo.value)


# --- The happy path ----------------------------------------------------------------------

def test_loads_every_field_and_keeps_case_order():
    config = load(FIXTURE, today=TODAY)
    fund = config.fund
    assert fund.name == "Test High Yield Fund"
    assert fund.as_of == dt.date(2026, 1, 15)
    assert fund.yield_to_worst == 0.072
    assert fund.option_adjusted_duration == 3.0
    assert fund.expense_ratio == 0.001
    assert fund.tracking_drag == 0.0003
    assert [(c.name, c.default_rate, c.recovery_rate) for c in config.cases] == [
        ("benign", 0.01, 0.40),
        ("stress", 0.08, 0.25),
    ]
    assert config.overrides == ()
    assert config.warnings == ()


def test_integers_are_accepted_as_numbers(tmp_path):
    path = variant(tmp_path, "tracking_drag = 0.0003", "tracking_drag = 0")
    assert load(path, today=TODAY).fund.tracking_drag == 0.0


# --- Missing, misspelled and unknown keys ------------------------------------------------

def test_missing_field_is_an_error(tmp_path):
    path = variant(tmp_path, "tracking_drag = 0.0003\n", "")
    assert "[fund]: missing tracking_drag" in load_error(path)


def test_misspelled_key_is_an_error_with_a_suggestion(tmp_path):
    path = variant(tmp_path, "yield_to_worst", "yeild_to_worst")
    message = load_error(path)
    assert "unknown key 'yeild_to_worst'" in message
    assert "did you mean 'yield_to_worst'?" in message


def test_unknown_case_key_is_an_error(tmp_path):
    path = variant(tmp_path, "recovery_rate = 0.25", "recovery = 0.25")
    message = load_error(path)
    assert "[cases.stress]: unknown key 'recovery'" in message
    assert "[cases.stress]: missing recovery_rate" in message


def test_unknown_section_is_an_error(tmp_path):
    path = write(tmp_path, FIXTURE.read_text() + "\n[market]\nspread = 0.03\n")
    assert "unknown section [market]" in load_error(path)


def test_all_problems_are_reported_together(tmp_path):
    text = FIXTURE.read_text().replace("yield_to_worst = 0.072", "yield_to_worst = 7.2")
    text = text.replace("recovery_rate = 0.40", "recovery_rate = 40")
    message = load_error(write(tmp_path, text))
    assert "yield_to_worst = 7.2" in message
    assert "recovery_rate = 40" in message


def test_no_cases_is_an_error(tmp_path):
    text = FIXTURE.read_text().split("[cases.benign]")[0]
    assert "no cases" in load_error(write(tmp_path, text))


def test_case_named_fund_is_reserved(tmp_path):
    path = variant(tmp_path, "[cases.benign]", "[cases.fund]")
    assert "'fund' is reserved" in load_error(path)


def test_unreadable_file_is_a_config_error(tmp_path):
    assert "can't read" in load_error(tmp_path / "nope.toml")


def test_invalid_toml_is_a_config_error(tmp_path):
    assert "not valid TOML" in load_error(write(tmp_path, "[fund\nname = 1"))


# --- Wrong units and impossible values ---------------------------------------------------

@pytest.mark.parametrize(
    "old, new, expected",
    [
        ("yield_to_worst = 0.072", "yield_to_worst = 7.2", "Enter it as a decimal: 0.072 for 7.2%."),
        ("expense_ratio = 0.001", "expense_ratio = 5", "Enter it as a decimal: 0.05 for 5%."),
        ("default_rate = 0.08", "default_rate = 3.4", "Enter it as a decimal: 0.034 for 3.4%."),
        ("recovery_rate = 0.25", "recovery_rate = 40", "Enter it as a decimal: 0.4 for 40%."),
    ],
)
def test_percent_typed_instead_of_decimal_is_an_error(tmp_path, old, new, expected):
    assert expected in load_error(variant(tmp_path, old, new))


@pytest.mark.parametrize(
    "old, new, expected",
    [
        ("recovery_rate = 0.25", "recovery_rate = -0.1", "must be between 0 and 1"),
        ("default_rate = 0.08", "default_rate = -0.01", "must be between 0 and 1"),
        ("expense_ratio = 0.001", "expense_ratio = -0.001", "can't be negative"),
        ("tracking_drag = 0.0003", "tracking_drag = -0.0003", "can't be negative"),
        ("yield_to_worst = 0.072", 'yield_to_worst = "7%"', "expected a number"),
        ("yield_to_worst = 0.072", "yield_to_worst = true", "expected a number"),
        ("yield_to_worst = 0.072", "yield_to_worst = nan", "expected a number"),
    ],
)
def test_impossible_values_are_errors(tmp_path, old, new, expected):
    assert expected in load_error(variant(tmp_path, old, new))


def test_full_and_zero_recovery_and_default_are_allowed(tmp_path):
    text = FIXTURE.read_text().replace("recovery_rate = 0.40", "recovery_rate = 1")
    text = text.replace("default_rate = 0.08", "default_rate = 1").replace("recovery_rate = 0.25", "recovery_rate = 0")
    stress = load(write(tmp_path, text), today=TODAY).cases[1]
    assert (stress.default_rate, stress.recovery_rate) == (1.0, 0.0)


def test_large_fee_is_a_warning_not_an_error(tmp_path):
    # 0.05 typed for SPHY's 0.05% is a 5% fee: possible in principle, so only a warning.
    config = load(variant(tmp_path, "expense_ratio = 0.001", "expense_ratio = 0.05"), today=TODAY)
    assert config.fund.expense_ratio == 0.05
    assert any("If you meant 0.05%, enter 0.0005" in w for w in config.warnings)


def test_duration_below_one_year_is_rejected(tmp_path):
    path = variant(tmp_path, "option_adjusted_duration = 3.0", "option_adjusted_duration = 0.9")
    assert "needs a duration of at least 1 year" in load_error(path)


def test_duration_of_exactly_one_year_is_allowed(tmp_path):
    path = variant(tmp_path, "option_adjusted_duration = 3.0", "option_adjusted_duration = 1")
    assert load(path, today=TODAY).fund.option_adjusted_duration == 1.0


# --- as_of -------------------------------------------------------------------------------

def test_future_as_of_is_an_error():
    assert "is in the future" in load_error(FIXTURE, today=dt.date(2026, 1, 14))


def test_as_of_today_is_fine():
    assert load(FIXTURE, today=dt.date(2026, 1, 15)).warnings == ()


def test_old_data_is_a_warning():
    config = load(FIXTURE, today=dt.date(2026, 4, 16))  # 91 days later
    assert config.warnings == (
        "fund data is 91 days old (as of 2026-01-15); check the fund page for current numbers",
    )


def test_ninety_day_old_data_is_not_yet_stale():
    assert load(FIXTURE, today=dt.date(2026, 4, 15)).warnings == ()


def test_as_of_may_be_quoted_text(tmp_path):
    path = variant(tmp_path, "as_of = 2026-01-15", 'as_of = "2026-01-15"')
    assert load(path, today=TODAY).fund.as_of == dt.date(2026, 1, 15)


@pytest.mark.parametrize("value", ['"last week"', "2026-01-15T10:00:00"])
def test_as_of_must_be_a_date(tmp_path, value):
    path = variant(tmp_path, "as_of = 2026-01-15", f"as_of = {value}")
    assert "expected a date" in load_error(path)


# --- --set overrides ---------------------------------------------------------------------

def test_set_fund_field_by_bare_name():
    config = load(FIXTURE, ["yield_to_worst=0.08"], today=TODAY)
    assert config.fund.yield_to_worst == 0.08
    assert config.overrides == ("yield_to_worst = 0.08",)


def test_set_fund_field_with_fund_prefix():
    assert load(FIXTURE, ["fund.expense_ratio = 0.002"], today=TODAY).fund.expense_ratio == 0.002


def test_set_case_field():
    config = load(FIXTURE, ["stress.default_rate=0.1", "benign.recovery_rate=0.5"], today=TODAY)
    assert [(c.default_rate, c.recovery_rate) for c in config.cases] == [(0.01, 0.5), (0.1, 0.25)]
    assert config.overrides == ("stress.default_rate = 0.1", "benign.recovery_rate = 0.5")


def test_set_text_and_date_fields():
    config = load(FIXTURE, ["name=My Fund", "as_of=2026-01-20"], today=TODAY)
    assert config.fund.name == "My Fund"
    assert config.fund.as_of == dt.date(2026, 1, 20)


def test_set_values_are_validated_like_the_file():
    assert "Enter it as a decimal: 0.075 for 7.5%." in load_error(FIXTURE, ["yield_to_worst=7.5"])


def test_set_unknown_fund_field_suggests_the_closest():
    message = load_error(FIXTURE, ["yeild_to_worst=0.08"])
    assert "unknown fund field" in message
    assert "did you mean 'yield_to_worst'?" in message


def test_set_cannot_create_a_case():
    message = load_error(FIXTURE, ["recession.default_rate=0.1"])
    assert "no case named 'recession'" in message


def test_set_unknown_case_field_is_an_error():
    assert "unknown case field" in load_error(FIXTURE, ["stress.default=0.1"])


@pytest.mark.parametrize("assignment", ["yield_to_worst", "=0.08", "yield_to_worst="])
def test_set_needs_key_and_value(assignment):
    assert "expected KEY=VALUE" in load_error(FIXTURE, [assignment])


def test_set_rejects_deeper_keys():
    assert "expected FIELD, fund.FIELD or CASE.FIELD" in load_error(FIXTURE, ["cases.stress.default_rate=0.1"])


def test_set_does_not_touch_the_file():
    before = FIXTURE.read_text()
    load(FIXTURE, ["yield_to_worst=0.08"], today=TODAY)
    assert FIXTURE.read_text() == before
