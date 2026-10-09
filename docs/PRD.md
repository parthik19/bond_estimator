# bond_estimator — product requirements (v0.3)

_v0.3 replaces the Monte Carlo design of v0.2 with a simpler tool that answers one question._

## 1. The question

> Given what's on a bond fund's page (yield to worst, duration, expense ratio) and my own
> default and recovery assumptions, what IRR can I expect, and over how many years?

Context: a lump sum in a Roth IRA, distributions reinvested. That means no taxes, no
contributions or withdrawals, and nominal returns. For a lump sum with reinvested
distributions, IRR equals the annualized total return.

## 2. The answer

**Horizon: N = 2 × option‑adjusted duration − 1** (Leibowitz, Bova & Kogelman, _FAJ_ 2014).

- A fund that keeps its duration roughly constant reinvests at whatever yields prevail. When
  yields rise, prices fall at first, but the higher yield earned afterwards makes it up. Falling
  yields work the other way round.
- For a steady drift in yields, the two effects cancel exactly after 2 × duration − 1 years, so
  the starting yield is what you earn over that horizon.
- For SPHY (duration 2.94) that's 4.88 years, shown as "~5 years (4.88)".
- Funds with duration under 1 year are rejected.

**IRR over N:**

```
IRR = yield to worst − expense ratio − tracking drag − default losses
default losses = default rate × (1 − recovery rate)        # unrecovered principal
               + default rate × yield to worst / 2         # half a year's income on defaulters
```

Default losses are the one thing that doesn't cancel over time. Fridson & Xu (_FAJ_ 2014)
found high‑yield returns land below the starting yield for exactly this reason. So the range
of outcomes comes from the user's default/recovery cases, one table row each.

**Caveat shown with every result:** it assumes rate and spread changes are gradual. Sudden
moves, especially late in the period, push the result above or below.

## 3. Inputs (one TOML file per fund, e.g. `funds/sphy.toml`)

| Field | Source |
|---|---|
| `name`, `as_of` | Fund page |
| `yield_to_worst` | Fund page; used as the yearly return, with no compounding conversion |
| `option_adjusted_duration` | Fund page |
| `expense_ratio` | Fund page |
| `tracking_drag` | User. Required, may be 0: how much the fund lags its index beyond the fee |
| `[cases.NAME]` `default_rate`, `recovery_rate` | User. Average yearly rates over N, one row per case |

- Rates are decimals (0.0732 = 7.32%).
- Every field is required, and unknown keys are errors, with a "did you mean" suggestion.
- **Rejected:**
  - values ≥ 1 where a rate is expected (a percentage typed as a decimal)
  - negative fees
  - default or recovery rates outside 0–1
  - duration < 1
  - an `as_of` date in the future
  - a case named `fund`
- **Warned about:**
  - fees above 2% (usually 0.05 typed for 0.05%)
  - `as_of` older than 90 days

`--set KEY=VALUE` (repeatable) overrides a value without editing the file:

- a fund field, as `yield_to_worst=0.075` or `fund.yield_to_worst=0.075`
- an existing case's field, as `benign.default_rate=0.02`

Overrides are validated like the file, and the output lists them.

## 4. Output (terminal)

1. The fund's inputs, and any `--set` changes.
2. "Expected IRR over the next ~5 years (4.88 = 2 × 2.94 − 1)".
3. A table with one row per case: default rate, recovery, IRR.
4. The formula and the caveat.
5. Warnings, if any.

## 5. Correctness

- **Tests run before every estimate.** `bond_estimator.py` runs the full pytest suite in a
  separate Python process before reading the fund file. Any failure prints the failures and
  exits without an estimate. There is no skip option. The suite takes well under a second.
- **Tests use only frozen inputs** (`tests/fixtures/`), never the user's fund files. Editing a
  fund's numbers can't break a test; changing how results are calculated always will.
- **What the tests check:**
  - **Hand calculations:** the SPHY‑like cases (6.3151%, 5.10556%, 2.8504%), default‑loss
    edge cases, and costs subtracting one for one.
  - **An independent year‑by‑year reference simulation** (`tests/reference.py`). With yields
    held constant, compounding year by year reproduces the formula. Under a steady yield drift:
    - summed returns cancel exactly at N = 2 × duration − 1 and at no other N
    - the compounded IRR is closest to the starting yield at that N (within 0.05 points for a
      1‑point‑a‑year drift)
  - Every validation rule, `--set` form, and the gate itself: it runs in a separate process,
    blocks on any failure, and can't recurse.
- **Reference simulation timing:** a yield change takes effect at the start of the year, and
  the fund earns the new yield for that whole year. Under that convention, cancellation happens
  exactly at 2 × duration − 1, matching the paper.

## 6. Out of scope (dropped in v0.3)

Monte Carlo and histograms, market‑volatility settings, historical replays, hypothetical rate
paths, Treasury comparison, live data fetching, HTML reports.

## Sources

- Leibowitz, Bova & Kogelman, ["Long‑Term Bond Returns under Duration Targeting"](https://rpc.cfainstitute.org/research/financial-analysts-journal/2014/long-term-bond-returns-under-duration-targeting), _FAJ_ 2014
- Fridson & Xu, ["Duration Targeting: No Magic for High‑Yield Investors"](https://rpc.cfainstitute.org/research/financial-analysts-journal/2014/duration-targeting-no-magic-for-high-yield-investors), _FAJ_ 2014
- SPHY: [State Street fund page](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-portfolio-high-yield-bond-etf-sphy)
- Default/recovery context: [J.P. Morgan recap, Aug 31 2026 (IBKR)](https://www.interactivebrokers.com/campus/traders-insight/securities/macro/weekly-market-recap-week-of-august-31-2026/), [New Capital](https://www.newcapital.com/en/insights/Managing-Defaults-in-a-High-Yield-Portfolio.html)
