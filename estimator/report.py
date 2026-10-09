"""Terminal output."""

from __future__ import annotations

from .config import Config
from .model import expected_irr, horizon_years, rounded_years


def render(config: Config) -> str:
    fund = config.fund
    years = horizon_years(fund.option_adjusted_duration)
    lines = [
        f"{fund.name}: fund data as of {fund.as_of}",
        f"  Yield to worst            {fund.yield_to_worst:7.2%}",
        f"  Option-adjusted duration  {fund.option_adjusted_duration:6.2f}  years",
        f"  Expense ratio             {fund.expense_ratio:7.2%}",
        f"  Tracking drag             {fund.tracking_drag:7.2%}",
    ]
    if config.overrides:
        lines.append("  Changed with --set: " + "; ".join(config.overrides))
    lines += [
        "",
        f"Expected IRR over the next ~{rounded_years(years)} years "
        f"({years:.2f} = 2 × {fund.option_adjusted_duration:g} − 1)",
        "",
    ]

    name_width = max(len("Case"), *(len(c.name) for c in config.cases))
    lines.append(f"  {'Case':<{name_width}}  Default rate  Recovery     IRR")
    for case in config.cases:
        irr = expected_irr(
            fund.yield_to_worst,
            fund.expense_ratio,
            fund.tracking_drag,
            case.default_rate,
            case.recovery_rate,
        )
        lines.append(
            f"  {case.name:<{name_width}}  {case.default_rate:12.2%}  {case.recovery_rate:8.2%}  {irr:6.2%}"
        )

    lines += [
        "",
        "IRR = yield to worst − expense ratio − tracking drag − default losses, where default losses",
        "= default rate × (1 − recovery) + half a year's yield on the bonds that default.",
        "Assumes rate and spread changes over the period are gradual. Sudden moves, especially late",
        "in the period, can push the result above or below these figures.",
    ]
    if config.warnings:
        lines += ["", "Warnings:"] + [f"  - {w}" for w in config.warnings]
    return "\n".join(lines)
