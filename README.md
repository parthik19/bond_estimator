# bond_estimator

What IRR can you expect from a bond fund, and over how many years? Given the fund page's yield
to worst, option‑adjusted duration and expense ratio, plus your own default and recovery
assumptions, it prints one IRR per case over **2 × duration − 1 years**. That's the horizon
over which gradual rate and spread moves cancel out. [docs/PRD.md](docs/PRD.md) has the reasoning.

```
Expected IRR over the next ~5 years (4.88 = 2 × 2.94 − 1)

  Case              Default rate  Recovery     IRR
  benign                   1.50%    40.00%   6.32%
  long_run_average         3.40%    40.00%   5.11%
  recession_heavy          6.00%    30.00%   2.85%
```

## Setup (one time)

Needs Python 3.11 or newer. Everything lives in a virtualenv inside this folder.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

## Usage

```bash
.venv/bin/python bond_estimator.py funds/sphy.toml
```

Every run first runs the full test suite. If any test fails, it prints the failures and stops
without an estimate.

Try a what‑if without editing the file. `--set` is repeatable:

```bash
.venv/bin/python bond_estimator.py funds/sphy.toml --set yield_to_worst=0.075 --set recession_heavy.default_rate=0.08
```

`--set` takes a fund field (`yield_to_worst=…` or `fund.yield_to_worst=…`) or an existing case's
field (`benign.default_rate=…`). New cases go in the file.

## Fund files

Copy `funds/sphy.toml` and fill in the numbers from the fund's page. Rates are decimals:
`0.0732` means 7.32%.

```toml
[fund]
name = "SPDR Portfolio High Yield Bond ETF (SPHY)"
as_of = 2026-09-04
yield_to_worst = 0.0732
option_adjusted_duration = 2.94
expense_ratio = 0.0005
tracking_drag = 0.0          # how much the fund lags its index beyond the fee; 0 is allowed

[cases.long_run_average]     # one table per case; the name is yours
default_rate = 0.034         # average yearly default rate you expect over the horizon
recovery_rate = 0.40         # cents on the dollar recovered from defaulted bonds
```

- Every field is required, and misspelled keys are errors.
- A rate entered as a percentage (`7.32` instead of `0.0732`) is an error.
- A fee above 2% or data older than 90 days prints a warning.
- Duration must be at least 1 year.

## How the IRR is calculated

```
IRR = yield to worst − expense ratio − tracking drag − default losses
default losses = default rate × (1 − recovery) + default rate × yield to worst / 2
```

The second term of the default losses is the half‑year of income that, on average, a bond
that defaults never pays.

**Caveat:** this assumes rate and spread changes over the period are gradual. Sudden moves,
especially late in the period, can push the result either way.

## Tests

```bash
.venv/bin/python -m pytest -q
```

- The tests use frozen inputs in `tests/fixtures/`, never your fund files, so editing a fund
  can't break a test.
- `tests/reference.py` is an independent year‑by‑year simulation. The tests use it to confirm
  two things:
  - the formula is what you get by compounding year by year
  - a steady yield drift cancels exactly at 2 × duration − 1 years
