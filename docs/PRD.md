# bond_estimator — product requirements (draft v0.2)

_Status: planning. Decisions so far are in §9; remaining open questions in §10._

## 1. Goal

Estimate the range of total returns a bond fund is likely to deliver over the next _N_ years,
from numbers the user copies off the fund's fact sheet plus the user's own assumptions about
defaults, recoveries, interest rates and credit spreads. High‑yield funds (SPHY, SCYB) are the
main use case. Nothing is hard‑coded to high yield, so an investment‑grade fund (e.g. LQD) works
if the user enters investment‑grade assumptions.

The output is a **distribution** (histogram, percentile table, fan chart), not one number,
with every input shown next to the results.

Context: a lump sum held in a **Roth IRA**. Distributions are reinvested, so returns are total
returns. Returns are nominal: no taxes, no inflation, no contributions or withdrawals.

**Non‑goals:** picking bonds, timing the market, fetching live data, bond‑by‑bond modelling,
taxes, inflation, cash‑flow schedules.

## 2. The financial idea

The yield on the fact sheet is **not** the expected return. Yield‑to‑worst (YTW) is what you
would earn if **no bond defaulted** and rates and spreads never moved. Each simulated year:

```
return ≈ carry (yield at start of year)
       − fees and trading drag
       − default losses        = default rate × (1 − recovery rate)
       − rate duration   × change in Treasury yield
       − spread duration × change in credit spread
       + ½ × convexity × (change in yield)²
```

Then the fund **rolls**: it sells bonds that get too short and buys new ones, so duration
stays roughly constant and next year's carry is the _new_ yield. Every path is simulated year
by year for all _N_ years. Nothing is a one‑year estimate stretched out.

### 2.1 Which horizon can we reason about? ("2 × duration − 1")

- **The rule** (Leibowitz, Bova & Kogelman, _FAJ_ 2014). A fund that holds its duration
  constant earns an annualized return close to its **starting yield** after about
  **2 × duration − 1** years, whatever path rates take. If rates rise, prices fall now but
  coupons are reinvested at the higher rate, and after about that many years the two effects
  offset. It assumes parallel rate moves, constant duration, and **no defaults**.
- **For SPHY** (option‑adjusted duration 2.94): 2 × 2.94 − 1 ≈ **5 years**.
- **High yield doesn't fully obey it.** Fridson & Xu (_FAJ_ 2014, "Duration Targeting: No
  Magic for High‑Yield Investors") tested the rule on high yield. Realized returns spread much
  more widely around the starting yield and tended to land **below** it. Default losses are
  permanent: reinvesting at higher yields does not win them back. They also come together with
  spread blowouts and low recoveries.
- **What that means for the tool:** duration tells us the horizon at which _rate_ risk mostly
  cancels. Credit risk doesn't cancel at any horizon, so the simulation has to cover it.
- **Requirements that follow:**
  - Default horizon _N_ = round(2 × OAD − 1), minimum 1. The user can override it.
  - The report includes a **range‑vs‑horizon** chart: the P5–P95 band of annualized return for
    _N_ = 1…15. It shows where uncertainty is narrowest under the user's own assumptions.
  - The validation suite (§6.3) checks that the model reproduces the historical gap between
    starting yield and realized return.

## 3. Inputs

All inputs go in a per‑fund TOML file that the user writes (e.g. `funds/sphy.toml`). **There are
no built‑in defaults** for any number that affects results. A missing value is an error, not a
silent fallback. The repo ships an annotated `funds/example_high_yield.toml` whose values are
clearly labeled with their sources and as‑of dates.

The tool trusts the user's judgment. It rejects only values that are impossible or entered in
the wrong unit:

- recovery outside 0–100%
- YTW > YTM (yield‑to‑worst is the minimum by definition)
- negative duration
- `7.32` typed where `0.0732` was meant

It never rejects a value just because it looks unusual, such as investment‑grade default rates.

### 3.1 Fund snapshot (from the fact sheet)

| Input | Required | Why it matters |
|---|---|---|
| Yield to worst (YTW) | yes | Starting carry. Conservative for callable bonds. |
| Option‑adjusted spread (OAS) | yes | Splits yield into a Treasury part and a credit part, which move differently. |
| Option‑adjusted duration (OAD) | yes | Rate sensitivity and the default horizon (§2.1). |
| Expense ratio | yes | Index YTW is gross of fees. |
| Treasury yield at ≈ the fund's duration | yes | Starting level for the rate model. |
| Tracking drag beyond fees | yes (may be 0) | Funds lag their index by more than the fee because of trading costs. |
| Yield to maturity (YTM) | optional | Validation (YTW ≤ YTM) and an upper bound. |
| Spread duration | optional (= OAD if omitted) | Sensitivity to spread changes. |
| Effective convexity | optional (0 if omitted) | High yield tends to be slightly negative because calls cap gains. |
| As‑of date | yes | Shown in the report. Older than 90 days → warning. |

Omitting an optional field is an explicit, documented modelling choice, not a hidden default.

The report also shows a computed check: YTW versus Treasury + OAS. Fund YTW is an average of
individual bond yields, and a few distressed bonds yielding 20%+ pull it up. A large gap means
the headline yield overstates what the typical bond pays.

### 3.2 Credit assumptions

| Input | Example (high yield, long‑run) | Note |
|---|---|---|
| Long‑run annual default rate (PD) | 3.4% | Use a **par‑weighted bond** series (e.g. J.P. Morgan). Moody's issuer‑weighted speculative‑grade rate covers a different universe and runs much higher (5.3% vs 2.0% today). |
| Recovery at the average default rate | 40% | Long‑run senior‑unsecured average. The last 5 years ran around 35.6%. |
| Recovery sensitivity to defaults | −2 pts per +1 pt of default rate | Recoveries collapse in default waves. |
| Default clumpiness (asset correlation ρ) | 0.10 | See §4.3. |
| Default persistence (year to year) | 0.5 | Bad years come in pairs (2001–02, 2008–09). |

### 3.3 Market behavior

The decision is **no view**: rates and spreads are expected to stay where they are today, but
they still move randomly around that level.

| Input | Example (high yield) |
|---|---|
| Treasury volatility (per year) | 0.9% |
| Treasury mean‑reversion speed | 0.15 |
| Spread volatility (per year) | 1.5% (investment grade is much lower) |
| Spread mean‑reversion speed | 0.3 |
| Spread link to the economy | 0.8 |
| Rate link to the economy | 0.3 |
| Spread floor | 2.0% |

The long‑run targets for rates and spreads are set to **today's values** from §3.1 and are not
separate inputs. Phase 3 adds a calibration script that estimates these parameters from
historical data, so the example values have a traceable source.

### 3.4 Run settings

| Input | Default |
|---|---|
| Horizon _N_ (years) | round(2 × OAD − 1) |
| Starting amount | $10,000 (display only; returns don't depend on it) |
| Paths | 100,000 |
| Seed | fresh random, printed in the report; `--seed` reproduces a run |

### 3.5 Treasury comparison (opt‑in only)

Only when the config has a `[compare.treasury]` section with the _N_‑year Treasury yield, or
the user passes `--compare-treasury`, does the tool compute and show:

- the Treasury's held‑to‑maturity return over _N_ years
- the probability that the fund beats it

Otherwise nothing about Treasuries is computed or displayed.

## 4. Model

### 4.1 Layers, all on one engine

1. **Deterministic engine.** A pure function: given a year‑by‑year path of
   `(default rate, recovery, Δ Treasury, Δ spread)`, it returns yearly and cumulative returns
   using §2, resetting carry each year.
2. **Scenarios.** Named paths fed to that engine: _no change_, _2008‑style recession_,
   _2022‑style rate shock_, plus user‑defined.
3. **Monte Carlo.** Draws many random but realistic _N_‑year paths and feeds **each one** to
   the same engine.

Testing the engine therefore tests the simulation.

### 4.2 Why Monte Carlo

For high yield, bad things happen together. In a recession defaults spike, recoveries fall and
spreads widen at the same time. Average default × average recovery therefore understates the
average loss. Returns are also lopsided (−26% in 2008, +57% in 2009), and the order of events
matters for reinvestment. A simulation captures all three; a single formula doesn't.

### 4.3 Default model (Vasicek one‑factor)

Each year draws one number `Z` for "how the economy did": standard normal, with persistence
`Z_t = φ·Z_{t−1} + √(1−φ²)·ε_t`. That year's default rate is

```
DR_t = Φ( (Φ⁻¹(PD) − √ρ · Z_t) / √(1 − ρ) )
```

This is the model behind Basel bank‑capital rules. Its long‑run average is exactly `PD`. With
PD = 3.4%:

| ρ | Median year | 1‑in‑20 year | 1‑in‑100 year |
|---|---|---|---|
| 0.08 | 2.9% | 7.8% | 11.2% |
| **0.10** | **2.7%** | **8.5%** | **12.5%** |
| 0.12 | 2.6% | 9.0% | 13.9% |

Recovery: `RR_t = clip(RR̄ − β·(DR_t − PD) + noise, 10%, 80%)`.

### 4.4 Rates and spreads

- **Treasury yield:** mean‑reverting around today's level; shocks mildly linked to `Z`.
- **Spread:** mean‑reverting around today's level on a log scale, so it never goes negative
  and moves more when already wide; shocks strongly linked to `−Z`. The drift is adjusted so the
  _expected_ spread stays at today's level, which keeps the no‑view decision exact.
- **Carry each year** = fact‑sheet YTW + cumulative Δ Treasury + cumulative Δ spread.

### 4.5 Known simplifications (documented in the README)

- Portfolio‑level, annual steps. Crashes and recoveries within a year (March 2020) are invisible.
- Default loss is taken on par. Defaulting bonds usually fell in price first, which the spread
  change partly captures, so there is some double counting in bad years. The 2008/2009
  validation checks this.
- Constant duration and credit mix. Calls are handled only via YTW and convexity.
- ETF price‑vs‑NAV gaps are ignored. They matter only if you sell during a panic.

## 5. Outputs

Terminal summary plus a self‑contained Plotly HTML report, in the same style as `valuation_tool`:

1. Echo of every input with its as‑of date, the effective horizon, the seed, the path count and
   the YTW vs Treasury + OAS check.
2. **Percentile table** for annualized and cumulative return at _N_:
   - P5, P25, P50, P75, P95 and the mean
   - probability of a loss
   - average of the worst 5% of outcomes
3. **Histogram** of _N_‑year annualized return with P5/P50/P95 markers.
4. **Fan chart** of $10,000 over years 0…_N_ (5–95 and 25–75 bands).
5. **Range‑vs‑horizon chart** (§2.1).
6. **Scenario table** (deterministic).
7. **Median‑path attribution**: carry, fees, default losses, rate effect, spread effect.
8. Treasury comparison, only if opted in (§3.5).
9. Tornado sensitivity chart (Phase 3).

## 6. Correctness

### 6.1 Startup gate

- `main()` runs the full test suite in‑process **before** reading the user's config.
- Any failure prints the failing tests, exits non‑zero and produces no projections. There is no
  skip flag.
- Budget: about 3 seconds.

### 6.2 Tests are isolated from the real run

- **Separate random generators.** Every function takes an explicit `numpy.random.Generator`;
  nothing uses global random state. Tests build their own fixed‑seed generators. The real run
  builds its own from `--seed` or from fresh entropy.
- **Frozen fixtures.** Tests use frozen inputs stored under `tests/fixtures/`, never the user's
  config. Editing a fund's YTW, recovery or anything else can never break a test. Changing _how_
  results are calculated always will.
- **Golden results.** Fixed fixture plus fixed seed must reproduce stored results exactly, so
  any change in the method is caught and has to be deliberate (re‑bless the golden file in the
  same commit).
- **Stable real runs.** With a fresh seed, real runs differ slightly from run to run. At 100,000
  paths the wobble in P5 and P50 is about 0.02 percentage points, below the 0.1% display
  precision. A test asserts this using the Monte Carlo standard error.

### 6.3 Unit tests (does the code do what this document says?)

- **Identities:** no defaults and no rate/spread change → cumulative return is exactly
  `(1 + YTW − fees − drag)^N − 1`.
- **Hand calculations:** 5% defaults at 40% recovery → 3.00% loss. +1% rates at duration 3 →
  −3% plus the convexity term.
- **Duration approximation:** compared against exact cash‑flow repricing of a sample bond,
  within tolerance across the shock sizes the simulation produces.
- **Vasicek:** closed‑form quantiles match §4.3; simulated mean equals PD within 3 standard
  errors; ρ = 0 → constant PD.
- **No view:** the simulated mean spread and Treasury yield at every horizon equal today's,
  within the standard error.
- **Monotonicity:** higher PD → lower median; higher recovery → higher median; higher
  volatility → wider P5–P95.
- **Sanity:** percentiles are ordered and probabilities lie in [0, 1].
- **Input validation:** wrong units, YTW > YTM, recovery > 100% and missing required fields
  are all rejected.

### 6.4 Validation (is the model realistic?)

- **Historical replay.** Feed the actual historical yearly path through the engine and require
  it to land within tolerance of the index's real returns (2008 ≈ −26%, 2009 ≈ +57%,
  2022 ≈ −11%).
- **Starting yield vs. realized return.** Check that the historical gap between starting yield
  and realized _N_‑year return (Fridson & Xu) falls inside the model's simulated range.
- **Data** is checked into the repo, so validation runs offline and can be part of the startup
  gate:
  - ICE BofA high‑yield yield, OAS and total return (FRED `BAMLH0A0HYM2EY`, `BAMLH0A0HYM2`,
    `BAMLHYH0A0HYM2TRIV`; check how much history FRED still serves)
  - annual default and recovery rates (J.P. Morgan / Moody's studies, about 35 rows entered by
    hand)

## 7. Tech

- Python 3.11+, NumPy, SciPy, Plotly, pytest; TOML via the standard library `tomllib`.
- Same conventions as `valuation_tool`: `.venv`, `requirements.txt`, `pytest.ini`.
- Repo: `parthik19/bond_estimator` (private); local path `~/dev/finances/bond_estimator`.

```
bond_estimator.py funds/sphy.toml [--years N] [--paths 100000] [--seed S]
                  [--scenario NAME] [--compare-treasury] [-o report.html] [--no-open]
```

## 8. Phases

| Phase | Scope | Done when |
|---|---|---|
| 0 | Repo, this PRD | PRD agreed |
| 1 | Deterministic engine, scenarios, TOML loader and validation, startup gate, terminal output | Hand calculations reproduced; gate blocks on a failing test |
| 2 | Monte Carlo; HTML report (histogram, fan chart, percentiles, range vs horizon) | Statistical, no‑view and stability tests pass within the time budget |
| 3 | Historical data, validation suite, calibration script, tornado chart | 2008/2009/2022 and the Fridson–Xu gap reproduced within tolerance |
| 4 | Opt‑in Treasury comparison; side‑by‑side funds | — |

## 9. Decisions

| Topic | Decision |
|---|---|
| Who supplies the numbers | The user, in a TOML file. The tool rejects only impossible or wrong‑unit values. |
| Horizon | Default round(2 × OAD − 1), overridable; range‑vs‑horizon chart shows the trade‑off. |
| Spread and rate view | No view: centered on today's levels, still volatile. |
| Account | Roth IRA: no taxes, nominal returns, distributions reinvested. |
| Cash flows | Lump sum only. |
| Treasury comparison | Opt‑in; not computed or shown otherwise. |
| Seeds | Tests use their own fixed seeds; real runs use a fresh, printed seed. |
| Repo | Private `parthik19/bond_estimator` at `~/dev/finances/bond_estimator`. |

## 10. Open questions

1. Market‑behavior parameters (§3.3): required in the config like everything else (proposal,
   with the example file and the Phase 3 calibration script as the source), or built‑in
   historical defaults that the config can override?
2. Should Phase 1 accept CLI overrides of single inputs (e.g. `--set pd=0.05`) for quick
   what‑ifs, or is editing the TOML enough?

## Sources

- Leibowitz, Bova & Kogelman, ["Long‑Term Bond Returns under Duration Targeting"](https://rpc.cfainstitute.org/research/financial-analysts-journal/2014/long-term-bond-returns-under-duration-targeting), _FAJ_ 2014
- Fridson & Xu, ["Duration Targeting: No Magic for High‑Yield Investors"](https://rpc.cfainstitute.org/research/financial-analysts-journal/2014/duration-targeting-no-magic-for-high-yield-investors), _FAJ_ 2014
- Leibowitz, Bova & Kogelman, ["Bond Ladders and Rolling Yield Convergence"](https://rpc.cfainstitute.org/research/financial-analysts-journal/2015/bond-ladders-and-rolling-yield-convergence), _FAJ_ 2015
- SPHY: [State Street](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-portfolio-high-yield-bond-etf-sphy), [ETFdb](https://etfdb.com/etf/SPHY/)
- Defaults and recoveries: [J.P. Morgan recap, Aug 31 2026 (IBKR)](https://www.interactivebrokers.com/campus/traders-insight/securities/macro/weekly-market-recap-week-of-august-31-2026/), [Moody's via Bloomberg Gov](https://news.bgov.com/bankruptcy-law/modest-default-rate-masks-shaky-credit-foundation-moodys-says), [New Capital](https://www.newcapital.com/en/insights/Managing-Defaults-in-a-High-Yield-Portfolio.html)
