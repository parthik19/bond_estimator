"""Read a fund file (TOML), apply --set overrides, and validate everything.

The tool trusts the user's judgment and rejects only values that are impossible or entered in
the wrong unit (e.g. 7.32 where 0.0732 was meant). Every field is required; unknown keys are
errors so a typo can't silently drop an input.
"""

from __future__ import annotations

import datetime as dt
import difflib
import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

STALE_AFTER_DAYS = 90
# Fees above this are possible but almost always a units slip (0.05 typed for 0.05%).
FEE_WARNING_LEVEL = 0.02


class ConfigError(ValueError):
    """The fund file or a --set override is missing something, misspelled or impossible."""


@dataclass(frozen=True)
class Fund:
    name: str
    as_of: dt.date
    yield_to_worst: float
    option_adjusted_duration: float
    expense_ratio: float
    tracking_drag: float


@dataclass(frozen=True)
class Case:
    name: str
    default_rate: float
    recovery_rate: float


@dataclass(frozen=True)
class Config:
    fund: Fund
    cases: tuple[Case, ...]
    overrides: tuple[str, ...]  # "key = value" for each --set, in the order given
    warnings: tuple[str, ...]


FUND_FIELDS = (
    "name",
    "as_of",
    "yield_to_worst",
    "option_adjusted_duration",
    "expense_ratio",
    "tracking_drag",
)
CASE_FIELDS = ("default_rate", "recovery_rate")
SECTIONS = ("fund", "cases")


def load(path: str | Path, overrides: list[str] | None = None, today: dt.date | None = None) -> Config:
    path = Path(path)
    try:
        text = path.read_text()
    except OSError as e:
        raise ConfigError(f"can't read {path}: {e.strerror}") from None
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} is not valid TOML: {e}") from None
    applied = apply_overrides(raw, overrides or [])
    return validate(raw, applied, today or dt.date.today())


def apply_overrides(raw: dict, assignments: list[str]) -> tuple[str, ...]:
    """Apply `--set KEY=VALUE` edits to the parsed file, before validation.

    KEY is a fund field (`yield_to_worst` or `fund.yield_to_worst`) or an existing case's
    field (`benign.default_rate`). VALUE is read as a TOML value, so numbers and dates work;
    anything that isn't valid TOML is taken as plain text (handy for `name=...`).
    """
    applied = []
    for assignment in assignments:
        key, sep, value_text = assignment.partition("=")
        key, value_text = key.strip(), value_text.strip()
        if not sep or not key or not value_text:
            raise ConfigError(f"--set {assignment!r}: expected KEY=VALUE")
        value = _parse_value(value_text)
        parts = key.split(".")
        if len(parts) == 1 or (len(parts) == 2 and parts[0] == "fund"):
            field = parts[-1]
            if field not in FUND_FIELDS:
                raise ConfigError(f"--set {key}: unknown fund field{_suggest(field, FUND_FIELDS)}")
            raw.setdefault("fund", {})[field] = value
        elif len(parts) == 2:
            case, field = parts
            cases = raw.get("cases")
            if not isinstance(cases, dict) or case not in cases:
                known = list(cases) if isinstance(cases, dict) else []
                raise ConfigError(
                    f"--set {key}: no case named {case!r} in the fund file{_suggest(case, known)}"
                    " (--set edits existing cases; add new ones to the file)"
                )
            if field not in CASE_FIELDS:
                raise ConfigError(f"--set {key}: unknown case field{_suggest(field, CASE_FIELDS)}")
            cases[case][field] = value
        else:
            raise ConfigError(f"--set {key}: expected FIELD, fund.FIELD or CASE.FIELD")
        applied.append(f"{key} = {value_text}")
    return tuple(applied)


def _parse_value(text: str):
    try:
        return tomllib.loads(f"v = {text}")["v"]
    except tomllib.TOMLDecodeError:
        return text


def validate(raw: dict, overrides: tuple[str, ...], today: dt.date) -> Config:
    errors: list[str] = []
    warnings: list[str] = []

    for section in raw:
        if section not in SECTIONS:
            errors.append(f"unknown section [{section}]{_suggest(section, SECTIONS)}")

    fund_raw = raw.get("fund")
    if not isinstance(fund_raw, dict):
        errors.append("missing [fund] section")
        fund_raw = {}
    _check_keys(fund_raw, FUND_FIELDS, "[fund]", errors)

    fund_values = {
        "name": _text(fund_raw, "name", "[fund]", errors),
        "as_of": _as_of(fund_raw, today, errors, warnings),
        "yield_to_worst": _rate(fund_raw, "yield_to_worst", "[fund]", errors),
        "option_adjusted_duration": _duration(fund_raw, errors),
        "expense_ratio": _fee(fund_raw, "expense_ratio", errors, warnings),
        "tracking_drag": _fee(fund_raw, "tracking_drag", errors, warnings),
    }

    cases_raw = raw.get("cases")
    cases: list[Case] = []
    if not isinstance(cases_raw, dict) or not cases_raw:
        errors.append("no cases: add at least one [cases.NAME] with default_rate and recovery_rate")
        cases_raw = {}
    for name, case_raw in cases_raw.items():
        where = f"[cases.{name}]"
        if name == "fund":
            errors.append(f"{where}: 'fund' is reserved (it would clash with --set fund.FIELD)")
            continue
        if not isinstance(case_raw, dict):
            errors.append(f"{where}: expected a table with default_rate and recovery_rate")
            continue
        _check_keys(case_raw, CASE_FIELDS, where, errors)
        default_rate = _probability(case_raw, "default_rate", where, errors)
        recovery_rate = _probability(case_raw, "recovery_rate", where, errors)
        if default_rate is not None and recovery_rate is not None:
            cases.append(Case(name, default_rate, recovery_rate))

    if errors:
        raise ConfigError("\n".join(f"  - {e}" for e in errors))
    return Config(Fund(**fund_values), tuple(cases), overrides, tuple(warnings))


def _check_keys(table: dict, allowed: tuple[str, ...], where: str, errors: list[str]) -> None:
    for key in table:
        if key not in allowed:
            errors.append(f"{where}: unknown key {key!r}{_suggest(key, allowed)}")
    for key in allowed:
        if key not in table:
            errors.append(f"{where}: missing {key}")


def _suggest(word: str, choices) -> str:
    close = difflib.get_close_matches(word, list(choices), n=1)
    return f" (did you mean {close[0]!r}?)" if close else ""


def _number(table: dict, key: str, where: str, errors: list[str]) -> float | None:
    if key not in table:
        return None  # reported by _check_keys
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        errors.append(f"{where} {key}: expected a number, got {value!r}")
        return None
    return float(value)


def _looks_like_percent(key: str, value: float, where: str, errors: list[str]) -> bool:
    if abs(value) >= 1:
        errors.append(
            f"{where} {key} = {value:g} looks like a percentage. "
            f"Enter it as a decimal: {value / 100:g} for {value:g}%."
        )
        return True
    return False


def _rate(table: dict, key: str, where: str, errors: list[str]) -> float | None:
    value = _number(table, key, where, errors)
    if value is None or _looks_like_percent(key, value, where, errors):
        return None
    return value


def _fee(table: dict, key: str, errors: list[str], warnings: list[str]) -> float | None:
    value = _number(table, key, "[fund]", errors)
    if value is None or _looks_like_percent(key, value, "[fund]", errors):
        return None
    if value < 0:
        errors.append(f"[fund] {key} = {value:g}: can't be negative")
        return None
    if value > FEE_WARNING_LEVEL:
        warnings.append(
            f"{key} is {value:.2%} a year. If you meant {value:g}%, enter {value / 100:g}."
        )
    return value


def _probability(table: dict, key: str, where: str, errors: list[str]) -> float | None:
    value = _number(table, key, where, errors)
    if value is None:
        return None
    if value > 1:
        errors.append(
            f"{where} {key} = {value:g} looks like a percentage. "
            f"Enter it as a decimal: {value / 100:g} for {value:g}%."
        )
        return None
    if value < 0:
        errors.append(f"{where} {key} = {value:g}: must be between 0 and 1")
        return None
    return value


def _duration(table: dict, errors: list[str]) -> float | None:
    value = _number(table, "option_adjusted_duration", "[fund]", errors)
    if value is None:
        return None
    if value < 1:
        errors.append(
            f"[fund] option_adjusted_duration = {value:g}: the 2 × duration − 1 horizon needs a "
            "duration of at least 1 year, so this tool doesn't cover ultra-short funds"
        )
        return None
    return value


def _text(table: dict, key: str, where: str, errors: list[str]) -> str | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where} {key}: expected non-empty text, got {value!r}")
        return None
    return value.strip()


def _as_of(table: dict, today: dt.date, errors: list[str], warnings: list[str]) -> dt.date | None:
    if "as_of" not in table:
        return None
    value = table["as_of"]
    if isinstance(value, str):
        try:
            value = dt.date.fromisoformat(value)
        except ValueError:
            pass
    if isinstance(value, dt.datetime) or not isinstance(value, dt.date):
        errors.append(f"[fund] as_of: expected a date like 2026-09-04, got {value!r}")
        return None
    if value > today:
        errors.append(f"[fund] as_of = {value}: is in the future")
        return None
    age = (today - value).days
    if age > STALE_AFTER_DAYS:
        warnings.append(f"fund data is {age} days old (as of {value}); check the fund page for current numbers")
    return value
