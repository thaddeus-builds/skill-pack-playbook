# Maturity: reading a recent day before it has settled

A platform's number for a day is not final when the day ends. Purchases, and what they are worth, keep arriving until the attribution window has passed (seven days for a seven-day click window). So every recent day is understated, and any window that includes recent days, the ninety-day benchmark too, mixes days that are settled with days that are not. A pack that judges on those numbers either waits a whole window or judges on numbers it knows are low. `kit/maturity.py` (pack `ads-core`) says how much of a day's final number is visible at each age, and reads a recent day as what it will come to, with an interval. It is pure rules: no database, no clock, no platform.

It is not `kit.ledger.is_settled` (a day is settled once its export is `settle_days` after it; that stays) and not measurement's maturity classification (observed, unstable, unjudged, "never a forecast"; that stays too). This module estimates the part still to arrive; those two can read it later.

## The model

**Age** is the number of whole days from a day to the date a number was taken: age 0 is exported on the day itself (partial), age 1 the next day (complete), the same ages the ledger counts. **`W`** is the age from which a day is final: the attribution window in days (a pack whose platform counts the window the other way adds one). **`F(age)`** is the share of the final number visible at that age: it never falls with age, is in (0, 1], and is exactly 1 from `W` on.

```
F(a) = (1 - exp(-((a + 1) / tau)^k)) / (1 - exp(-((W + 1) / tau)^k))     for a < W
```

`tau` says how slowly a day matures. `k = 1` is the truncated exponential; another `k` is a Weibull. Counts (purchases) and value (what they are worth) mature differently, so each has its own curve. With `tau` 1.5 and a seven-day window, `F(0)` is 0.489: about half of a day's final orders are visible on the day itself.

## The fit

The input is **observations**: rows `(key, day, observed_at, spend, count, value)` where the same `(key, day)` appears at several ages, because a re-export or a daily pull restates it. For each `(key, day)` with an observation at or past `W` (its final) and an earlier one, the earlier one over the final estimates `F(age)`. The curve is the `tau` of least weighted squares over those ratios, pooled across keys.

- **Weights** are the final's number of orders, at most five times the median (one huge day does not decide the curve).
- **Outliers** are trimmed, not down-weighted: a pair more than four binomial standard deviations from the curve (`sqrt(F(1 - F) / orders)`) is left out. Near full maturity a ratio cannot exceed 1, so its raw error is skewed, and a symmetric robust loss on it biases the curve (it did, by 0.7 % of `tau`, in the first version). On the standardised error clean data is symmetric and only a real outage is trimmed.
- **The standard error** counts each `(key, day)` once, not once per age: its ratios at ages 0 to 6 are the same orders seen again, one draw. Treating them as independent made the error about a fifth too small in the test world (the fitted `tau` varied by 0.0123 between worlds while that error said 0.0102); counted by day it says 0.0154, a little wide.
- **A prior.** A cold-start `tau` per window (`maturity_prior_tau_1`, `_7`, `_28`) with a wide standard deviation (half of itself); the fit is shrunk toward it by precision, as `kit.allocation.shrink` does for the elasticity. Under `maturity_min_pairs` pairs or `maturity_min_ages` distinct ages the curve **is** the prior and says `prior_only`.
- **The family.** `family="auto"` keeps the exponential unless a Weibull beats it on keys held out (five folds) by `maturity_family_gain`. It has one parameter fewer, which is why it is the default.
- **Refunds.** A final below an earlier number is a ratio above 1: clipped to 1 and counted in `n_clipped`. A negative number, an unreadable day, or an observation before its day is refused (`maturity_bad_observation`, naming the row).

## The estimate and its interval

For a day seen at age `a` with number `x`: **estimate = x / F(a)**. The interval is a prediction interval for the final number: what is still to arrive is Poisson-like, with variance `x (1 - F) / F^2`, and a value's is `value^2 (1 - F) / (F^2 * orders)`. Both are scaled by the curve's **dispersion**, measured in the fit: about 1 for counts, and above 1 for value because orders are not all worth the same (1.25 estimated in the test world, where the spread of order worth predicts 1.28). The curve's own uncertainty is added, and for a window it is **shared** across the days (one wrong `tau` is wrong for every day), so it adds linearly while the days' remainders add in quadrature.

For a window, `summarize` gives the observed and estimated count and value, the **return** (estimated value over spend; spend is known at once) with its interval, the visible share, and `immature` when that share is under `maturity_immature_share` (0.9).

## The rule for judgement

`judge(window, threshold)` has no number of its own. A **mature** window is decided by its return, as before. An **immature** window whose whole interval is on one side of the threshold is decided; one whose interval straddles it is **`undecided_immature`**, never a verdict. A benchmark is read on days that have matured (age at or past `W`) or on the estimate.

## Refit, drift, stale

The pack stores each fitted curve (`to_dict`) with its `fitted_on` day and the data it saw (`data_from`, `data_to`), so a change is visible. `refit(old, observations)` fits again with the old curve as the prior and returns a new curve (pure). `drift(old, new)` says the lag moved when `tau` changed by more than `maturity_drift_se` (3) standard errors of the two fits together. `stale(curve, today)` says a curve is `maturity_refit_days` (7) old. **The kit schedules nothing**: the pack decides when to refit, and the kit only says whether a curve is stale or has drifted. `Curve.from_windows({1: n1, 7: n7, 28: n28})` builds a prior from the same days counted under different attribution windows; it is unverified against any platform and a prior builder, nothing more.

## What a pack hands over

Observations: every export of a day with the time it was taken. A pack that already keeps every export (the ledger, raw) rebuilds this table from raw; it is a cache, never a source. Per key it chooses what is pooled: an account, a campaign type, an attribution setting. Then days to read: `{day, spend, count, value}` with the date they were taken, and the two curves: a `maturity.Reading(count, value, observed_on, params)`, which the three hooks below take.

**Where the pairs come from (seen once, on the first real account, 2026-10-29).** A fit needs the same `(key, day)` seen at two ages, one before the window closes and one at or after it. So:

- A pack with no daily pull gets pairs only by **repeating the export on consecutive days**, each time over the same trailing range (at least `W + 1` days: then every day has a reading at each age from 0 to `W - 1` and a final one). A one-time history download gives none: every old day is seen once, at one very late age. Plan for about eight days of daily exports before a fit leaves the prior; the first pack had 6 usable pairs against the 30 the fit needs, and one distinct early age against three.
- **Spacing in days is what matters.** A second download inside the same day returns the same numbers for settled days and adds nothing.
- **The age is in the account's own days.** Age 0 is the account's day, so a pack must convert the time an export was taken to the account's time zone before it counts days (the first pack had counted UTC days, which moved a day's age by one for an account eight hours ahead). With a platform that exports part-way through the day, that day is age 0 and partial.
- **What six pairs did show:** age `W - 1` against age `W` was exactly 1.0 for counts and value, nothing arrived on the last day, which fits `F = 1` at `W`. It says nothing about the shape below.

Until a fit leaves the prior (`prior_only` is true) the interval is the prior's, wide by design, and cannot be called calibrated or not; the check that the 90 % interval holds about nine times in ten needs days that were read young and then settled, so it waits for those days.

## The hooks: where a judgement reads the estimate

Given a `Reading`, three places read a window on the estimate and none gives a verdict the interval cannot back. Without one they are exactly as they were.

- **`kit.lifecycle.judge`** reads a campaign's return on the estimate. A rule on the return (earning, declining, lagging) is decided only when the whole interval of an *immature* window is on one side of its threshold; where it cannot tell, the state is **`unjudged` with the reason `immature`**. That is an existing state, so the closed list of states is unchanged, and `hold` already keeps one week of it from moving a held state. A mature window is judged as before. The evidence gates (enough spend, enough conversions) stay on what was **seen**: a graduation needs real conversions, and an estimate must not manufacture them.
- **`kit.compute_campaign`** takes `Source.maturity` (the reading; its `observed_on` must be after the last complete day). The benchmark a campaign is held to is built from the other campaigns' **estimated** revenue, not their understated tail. Each campaign's `window` keeps what was seen and adds `matured {roas, low, high, revenue, conversions, share, immature}`; the document says which curves it was read on (`tau`, family, `prior_only`, `fitted_on`) and warns, coded, when a curve is only the cold start.
- **`kit.alerts.check`** (`reading=...`) reads a *return* on the current day's estimate, so an alert need not wait for the ledger's settle days: it fires only when the whole interval is on the firing side of `threshold x baseline`, is silent only when none of it is, and otherwise has **no verdict** (`immature_undecided`). The baseline's days are read as point estimates. An unsettled day with no `orders` cannot be put on a curve (`orders_unknown`). Spend is final at once and is never read on a curve.

**Left alone on purpose: `kit.creative_life`'s cost reading.** It replays a creative's whole history day by day on today's numbers, so the last few days are understated, and a short run of them is what its "declining" rule looks for. That is the same flaw, but mending it changes a state machine's replay, which is its own change with its own tests (issue filed); its conversion counts for graduation stay observed in any case.

What it does to a campaign whose true return equals the benchmark (4.0 against 4.0), seen on its last seven days at 82 % visible: observed 3.29, called **lagging** without a reading; with one, an estimate of 4.0 with an interval of 3.3 to 4.7 across both the lagging bar (3.4) and the earning bar (4.6), so **unjudged, immature**. A campaign truly at 1.0 is still lagging and one at 9.0 still earning, because their intervals clear the bars.

## What the test world showed

On a synthetic world with a known lag (a seven-day window, `tau` 1.5 for counts and 3.0 for value, orders of unequal worth), not on any real account:

| | |
| --- | --- |
| The fitted `tau`, ten worlds | within two standard errors of the truth in at least eight; four times the data halves the interval |
| A day seen at age 2, 200 runs | the 90 % interval holds the true final count 91 % of the time, the true value 89 % |
| 8 % of mid-age numbers lost (an outage) | the curve moves by less than 0.05 |
| A lag that doubles between two fits | `drift` fires at more than ten standard errors; two fits of the same lag do not |
| Held-out family choice | an exponential world keeps the exponential; a Weibull world of shape 2 keeps the Weibull and finds shape 2 |

## What it assumes, and what breaks it

It assumes the **lag has the same shape across days and across the keys pooled.** What breaks that:

- a **promotion** or a big sale: orders arrive differently on those days (leave event days, `kit.event_days`, out of the observations, or fit them apart);
- a **change of attribution window** or setting: a new curve, not a refit;
- a **tracking outage**: the trim copes with a few bad numbers, not with weeks of them;
- **thin data**: with four keys and twelve days the value interval was a little too narrow (84 % for a nominal 90 %), and under `maturity_min_pairs` the curve is only the prior;
- a lag with a **heavy early part and a long tail** (Weibull shape under about 0.7) may keep the exponential, which then misreads the tail;
- **a new account** has nothing to fit: it reads on the prior and says so.

Every threshold above is a draft until a person confirms it for a client (`constants.d/maturity.tsv`).
