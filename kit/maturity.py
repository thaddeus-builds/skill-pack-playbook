"""How much of a day's final number is visible at a given age, and what a recent day will come to: the rules alone, no database, no clock, no platform.

A platform's number for a day is not final when the day ends: purchases and their value keep arriving until the attribution window has passed. So every recent day is
understated, and any window that includes recent days mixes matured and unmatured days. This module fits a curve `F(age)`, the share of a day's final number that is
visible `age` days after the day (age 0 = exported on the day itself, partial; the same age `kit.ledger` counts), and reads a recent day as a matured estimate with an
interval, so a judgement need not wait for the return to settle.

    F(a) = (1 - exp(-((a + 1) / tau)^k)) / (1 - exp(-((W + 1) / tau)^k))   for a < W,   F(a) = 1   for a >= W

`W` is the age from which a day is final (the attribution window in days; a pack whose platform counts the window the other way adds one). `k = 1` is the truncated
exponential, a Weibull shape `k` other than 1 is allowed; `tau` is how slowly the day matures. It is fitted separately for *counts* (purchases) and *value* (their
worth), which mature differently.

  * `fit(observations, window, prior, params, kind)`: from rows `(key, day, observed_at, spend, count, value)` where the same `(key, day)` is seen at several ages (a re-export
    or a daily pull restates it). For each `(key, day)` with an observation at or past `W` (the final) the earlier ones give `obs / final = F(age)`; a weighted least
    squares by the final's volume, trimmed of gross outliers, pooled across the keys; its standard error by the sandwich; then shrunk toward a prior
    (`prior_tau`, per window) by precision, as `kit.allocation.shrink` does. Under `maturity_min_pairs` pairs or `maturity_min_ages` distinct ages the curve IS the prior
    and says `prior_only`. `family="auto"` keeps the exponential unless a Weibull shape beats it on keys held out;
  * `share(curve, age)`: `(F, low, high)`;
  * `adjust(days, as_of, count_curve, value_curve)` and `summarize(adjusted, first, last)`: each day's estimate with an interval (a prediction interval: the remainder still to
    arrive is a Poisson-like draw, and the curve's own uncertainty is shared by every day), and for a window the estimated return with an interval and whether it is
    `immature` (its visible share is under `maturity_immature_share`);
  * `judge(window, threshold)`: a verdict with no number of its own: a mature window is decided by its estimate, an immature one whose interval straddles the threshold is
    `undecided_immature`, never a verdict;
  * `Reading`, `window_reading`, `day_reading`: what a judgement (`kit.lifecycle`, `kit.alerts`) needs to read days on the estimate: the two curves, the date the days
    were taken and the parameters, and the estimate of a window of daily rows or of one day;
  * `refit`, `drift`, `stale`: the pack stores each fitted curve with the day it was fitted on and the data it saw; `drift` flags a parameter that moved by more than
    `maturity_drift_se` standard errors; `stale` says a curve is older than `maturity_refit_days`. The kit never schedules: the pack decides the cadence.

What it assumes: that the lag has the same shape across days and across the keys pooled (a promotion, a change of attribution window, a tracking outage break it: see
docs/maturity.md). A refund (a later number below an earlier one) is clipped to a ratio of 1 and counted in `n_clipped`; a negative number, an unreadable day or an
observation before its day is refused (`maturity_bad_observation`).

Test: kit/tests/test_maturity.py.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field, replace
from datetime import date

from kit.contract import SkillPackError
from kit.messages import msg

KINDS = ("count", "value")
FAMILIES = ("exp", "weibull", "auto")
SHAPES = (0.5, 0.7, 1.0, 1.5, 2.0, 3.0)         # the Weibull shapes tried; 1.0 is the exponential
TAU_MIN, TAU_MAX = 0.05, 200.0
FOLDS = 5
WEIGHT_CAP = 5.0                                 # a key's weight is at most this many times the median final: one huge day does not decide the curve
TRIM = 4.0                                       # a pair whose ratio is more than this many binomial standard deviations from the curve is an outlier (an outage), and is left out
SD_FLOOR = 0.02
FIELDS = ("key", "day", "observed_at", "spend", "count", "value")


@dataclass(frozen=True)
class Params:
    min_pairs: int               # (key, day) pairs with a final and an earlier observation, before a fit counts
    min_ages: int                # distinct earlier ages among them
    immature_share: float        # a window whose visible share is under this is immature
    refit_days: int              # a curve older than this is stale
    drift_se: float              # a parameter that moved by more than this many standard errors has drifted
    interval_z: float            # 1.645 is a 90 % interval
    prior_sd_share: float        # the prior's standard deviation as a share of its tau
    family_gain: float           # a Weibull must beat the exponential on held-out keys by this share to be kept


@dataclass(frozen=True)
class Curve:
    family: str                  # "exp" or "weibull"
    tau: float
    k: float                     # 1.0 for the exponential
    se: float                    # the standard error of tau (the prior's when prior_only)
    window: int
    kind: str                    # "count" | "value"
    n_pairs: int
    n_ages: int
    prior_only: bool
    n_clipped: int = 0           # ratios above 1 (a refund) clipped to 1
    fitted_on: str | None = None
    data_from: str | None = None  # the first and last day the fit saw
    data_to: str | None = None
    dispersion: float = 1.0      # how much more the ratios scatter than the binomial says: about 1 for counts, 1 + cv^2 for values (orders of unequal worth)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Curve":
        return Curve(**d)

    @staticmethod
    def from_windows(counts: dict[int, float], p: Params, prior_sd_share: float | None = None, kind: str = "count") -> "Curve":
        """A prior from the same days counted under different attribution windows ({window days: conversions}, e.g. 1-day, 7-day, 28-day click): the share the
        shorter window shows of the longest is the share visible at about that age. UNVERIFIED against any platform's own numbers: a prior builder, nothing more
        (`prior_only` stays true, and the standard error is the prior's wide one)."""
        ws = sorted(w for w, c in counts.items() if c > 0)
        if len(ws) < 2:
            raise SkillPackError(msg("maturity_bad_observation", "windows: need two attribution windows with conversions", where="windows", problem="need two windows"))
        top = ws[-1]
        pts = [(w - 1, counts[w] / counts[top], 1.0, "windows", f"windows|{w}", 100.0) for w in ws[:-1]]
        tau, k = _best(pts, top, "exp")[:2]
        return Curve("exp", tau, k, (prior_sd_share if prior_sd_share is not None else p.prior_sd_share) * tau, top, kind, 0, 0, True)


# ---- the curve ---------------------------------------------------------------------------------

def _f(age: float, tau: float, k: float, window: int) -> float:
    if age >= window:
        return 1.0
    den = 1.0 - math.exp(-(((window + 1) / tau) ** k))
    return (1.0 - math.exp(-(((age + 1) / tau) ** k))) / den if den > 0 else 1.0


def _dtau(age: float, tau: float, k: float, window: int) -> float:
    """dF/dtau, numerically."""
    if age >= window:
        return 0.0
    h = 1e-4 * tau
    return (_f(age, tau + h, k, window) - _f(age, max(tau - h, TAU_MIN / 2), k, window)) / (tau + h - max(tau - h, TAU_MIN / 2))


def share(curve: Curve, age: int, z: float = 1.645) -> tuple[float, float, float]:
    """(F, low, high) at `age`: the share of a day's final number visible then, with the interval the curve's own standard error gives. A larger tau matures slower, so
    the low end is at tau + z se and the high end at tau - z se. From the window on the share is 1 and the interval has no width."""
    m = _f(age, curve.tau, curve.k, curve.window)
    if age >= curve.window:
        return 1.0, 1.0, 1.0
    lo = _f(age, curve.tau + z * curve.se, curve.k, curve.window)
    hi = _f(age, max(curve.tau - z * curve.se, TAU_MIN), curve.k, curve.window)
    return m, min(lo, m), max(hi, m)


# ---- the observations ---------------------------------------------------------------------------

def _bad(i: int, problem: str) -> SkillPackError:
    return SkillPackError(msg("maturity_bad_observation", f"observations[{i}] {problem}", where=f"observations[{i}]", problem=problem))


def _day(i: int, field_: str, value) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise _bad(i, f"has {field_} {value!r}, which is not a day (YYYY-MM-DD)") from None


def check_observations(rows: list[dict]) -> list[tuple]:
    """[(key, day, age, spend, count, value)] from the rows, refused (`maturity_bad_observation`, naming the row) when a field is missing, a day unreadable, a number
    negative or not a number, or the observation is before its day."""
    out = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or any(f not in r for f in FIELDS):
            raise _bad(i, f"lacks {', '.join(f for f in FIELDS if not isinstance(r, dict) or f not in r)}")
        day, seen = _day(i, "day", r["day"]), _day(i, "observed_at", r["observed_at"])
        if seen < day:
            raise _bad(i, f"was observed on {seen}, before its day {day}")
        for f in ("spend", "count", "value"):
            v = r[f]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v) or v < 0:
                raise _bad(i, f"has {f} {v!r}, which is not a number of 0 or more")
        out.append((r["key"], day.isoformat(), (seen - day).days, float(r["spend"]), float(r["count"]), float(r["value"])))
    return out


def _pairs(rows: list[tuple], kind: str, window: int) -> tuple[list[tuple[int, float, float, str, str, float]], int, str | None, str | None]:
    """([(age, ratio, weight, key, cluster, volume)], n_clipped, first day, last day), the cluster being the (key, day) whose observations the pairs share: for each (key, day)
    with an observation at or past the window, the earlier ones over that final. The volume is the final's count of orders (for a value too: it is what sets how much a
    ratio may scatter). A later row of one (key, day, age) replaces an earlier. A ratio above 1 (a refund) is clipped to 1 and counted. The weight is the volume, at most
    WEIGHT_CAP times the median volume."""
    at = 4 if kind == "count" else 5
    by: dict[tuple, dict[int, tuple[float, float]]] = {}
    for r in rows:
        by.setdefault((r[0], r[1]), {})[r[2]] = (r[at], r[4])
    vols = [seen[max(a for a in seen if a >= window)][1] for seen in by.values() if any(a >= window for a in seen)]
    vols = [v for v in vols if v > 0]
    cap = WEIGHT_CAP * statistics.median(vols) if vols else 0.0
    out, clipped, days = [], 0, []
    for (key, day), seen in sorted(by.items()):
        past, early = [a for a in seen if a >= window], [a for a in seen if a < window]
        if not past or not early:
            continue
        final, volume = seen[max(past)]
        if final <= 0 or volume <= 0:
            continue
        days.append(day)
        for a in sorted(early):
            ratio = seen[a][0] / final
            if ratio > 1.0:
                ratio, clipped = 1.0, clipped + 1
            out.append((a, ratio, min(volume, cap), key, f"{key}|{day}", volume))
    return out, clipped, (min(days) if days else None), (max(days) if days else None)


# ---- the fit ------------------------------------------------------------------------------------

def _sums(pts, h=None) -> dict[int, list[float]]:
    """Per age, the sums of h w, h w r and h w r^2 over the pairs: the loss depends on a pair only through its age, so the search runs over these few numbers."""
    out: dict[int, list[float]] = {}
    for i, (a, r, w, *_x) in enumerate(pts):
        hw = (1.0 if h is None else h[i]) * w
        s = out.setdefault(a, [0.0, 0.0, 0.0])
        s[0] += hw
        s[1] += hw * r
        s[2] += hw * r * r
    return out


def _loss(sums: dict[int, list[float]], tau: float, k: float, window: int) -> float:
    return sum(s[2] - 2.0 * f * s[1] + f * f * s[0] for a, s in sums.items() for f in (_f(a, tau, k, window),))


def _argmin_tau(sums, k: float, window: int) -> float:
    """The tau of least loss: a coarse grid on the log scale, then a golden-section search around the best cell."""
    grid = [math.exp(math.log(TAU_MIN) + i * (math.log(TAU_MAX) - math.log(TAU_MIN)) / 60) for i in range(61)]
    best = min(range(61), key=lambda i: _loss(sums, grid[i], k, window))
    lo, hi = math.log(grid[max(best - 1, 0)]), math.log(grid[min(best + 1, 60)])
    g = (math.sqrt(5) - 1) / 2
    a, b = hi - g * (hi - lo), lo + g * (hi - lo)
    fa, fb = _loss(sums, math.exp(a), k, window), _loss(sums, math.exp(b), k, window)
    for _ in range(60):
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - g * (hi - lo)
            fa = _loss(sums, math.exp(a), k, window)
        else:
            lo, a, fa = a, b, fb
            b = lo + g * (hi - lo)
            fb = _loss(sums, math.exp(b), k, window)
    return math.exp((lo + hi) / 2)


def _best(pts, window: int, family: str) -> tuple[float, float, list[float]]:
    """(tau, k, the trim weights): weighted least squares; pairs more than TRIM binomial standard deviations from the curve (sd = sqrt(F (1 - F) / final), floored) are left
    out and the fit repeated, at most 6 times; for the Weibull the shape of least loss among SHAPES. Robustness acts on the standardised residual: the raw one is
    skewed near full maturity (a ratio cannot exceed 1), and a symmetric loss on it biases the curve."""
    fits = []
    for k in ((1.0,) if family == "exp" else SHAPES):
        h = [1.0] * len(pts)
        tau = _argmin_tau(_sums(pts, h), k, window)
        for _ in range(6):
            keep = []
            for a, r, w, _key, _cl, final in pts:
                f = _f(a, tau, k, window)
                keep.append(1.0 if abs(r - f) <= TRIM * max(math.sqrt(max(f * (1.0 - f), 0.0) / max(final, 1.0)), SD_FLOOR) else 0.0)
            if keep == h or sum(keep) < 3:
                break
            h = keep
            tau = _argmin_tau(_sums(pts, h), k, window)
        fits.append((_loss(_sums(pts, h), tau, k, window), tau, k, h))
    _, tau, k, h = min(fits, key=lambda t: t[0])
    return tau, k, h


def _se(pts, tau: float, k: float, window: int, h) -> float:
    """The standard error of tau by the sandwich over clusters: (sum w F'^2)^-1 sqrt(sum over (key, day) of (sum w F' e)^2). The pairs of one (key, day) are the same
    realised orders seen at several ages, so they are one draw, not many: the clusters are what is independent."""
    a_, score = 0.0, {}
    for i, (a, r, w, _key, cluster, _final) in enumerate(pts):
        d = _dtau(a, tau, k, window)
        a_ += h[i] * w * d * d
        score[cluster] = score.get(cluster, 0.0) + h[i] * w * d * (r - _f(a, tau, k, window))
    return math.sqrt(sum(s * s for s in score.values())) / a_ if a_ > 0 else float("inf")


def prior_tau(window: int, k: dict) -> float:
    """The cold-start tau for an attribution window of `window` days, from the thresholds' rows for 1, 7 and 28 days (the nearest on the log scale)."""
    rows = {1: k["maturity_prior_tau_1"], 7: k["maturity_prior_tau_7"], 28: k["maturity_prior_tau_28"]}
    return rows[min(rows, key=lambda w: abs(math.log(max(window, 1)) - math.log(w)))]


def params(k: dict) -> Params:
    """The rules' parameters from the thresholds in effect."""
    return Params(int(k["maturity_min_pairs"]), int(k["maturity_min_ages"]), k["maturity_immature_share"], int(k["maturity_refit_days"]), k["maturity_drift_se"],
                  k["maturity_interval_z"], k["maturity_prior_sd_share"], k["maturity_family_gain"])


def _choose_family(pairs, window: int, gain: float) -> str:
    """Keep the exponential unless a Weibull shape beats it on keys held out (5 folds by key): the held-out loss is the sum over folds of the loss of the pairs of the
    keys left out against the curve fitted on the others."""
    keys = sorted({p[3] for p in pairs})
    if len(keys) < FOLDS * 2:
        return "exp"
    fold = {key: i % FOLDS for i, key in enumerate(keys)}
    held = {"exp": 0.0, "weibull": 0.0}
    for f in range(FOLDS):
        train = [p for p in pairs if fold[p[3]] != f]
        test = [p for p in pairs if fold[p[3]] == f]
        if not train or not test:
            continue
        for fam in held:
            tau, k, _ = _best(train, window, fam)
            held[fam] += _loss(_sums(test), tau, k, window)
    return "weibull" if held["weibull"] < held["exp"] * (1.0 - gain) else "exp"


def fit(observations: list[dict], window: int, prior_tau_: float, p: Params, kind: str = "count", *, family: str = "exp", fitted_on: str | None = None) -> Curve:
    """The curve of `kind` ("count" or "value") from the observation rows, pooled across their keys. With under `p.min_pairs` pairs or `p.min_ages` distinct ages, or too
    few to estimate a spread, the curve is the prior and `prior_only` is true (its standard error is the prior's, wide)."""
    if kind not in KINDS or family not in FAMILIES or isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise SkillPackError(msg("maturity_bad_observation", f"fit: kind {kind!r}, family {family!r} or window {window!r} not understood", where="fit", problem="kind, family or window"))
    pairs, clipped, first, last = _pairs(check_observations(observations), kind, window)
    sd0 = p.prior_sd_share * prior_tau_
    ages = {a for a, *_x in pairs}
    prior = Curve("exp", prior_tau_, 1.0, sd0, window, kind, len(pairs), len(ages), True, clipped, fitted_on, first, last)
    if len(pairs) < max(p.min_pairs, 3) or len(ages) < p.min_ages:
        return prior
    fam = _choose_family(pairs, window, p.family_gain) if family == "auto" else family
    tau, k, h = _best(pairs, window, fam)
    se = _se(pairs, tau, k, window, h)
    if not math.isfinite(se) or se <= 0:
        return prior
    z2 = [((r - _f(a, tau, k, window)) / math.sqrt(_f(a, tau, k, window) * (1.0 - _f(a, tau, k, window)) / vol)) ** 2
          for (a, r, _w, _key, _cl, vol), keep in zip(pairs, h) if keep and 0.0 < _f(a, tau, k, window) < 1.0
          and math.sqrt(_f(a, tau, k, window) * (1.0 - _f(a, tau, k, window)) / vol) >= SD_FLOOR]
    dispersion = min(max(statistics.fmean(z2), 1.0), 25.0) if z2 else 1.0
    w_fit, w_prior = 1.0 / se ** 2, 1.0 / sd0 ** 2                      # shrunk toward the prior by precision, as allocation.shrink does
    post = max((w_fit * tau + w_prior * prior_tau_) / (w_fit + w_prior), TAU_MIN)
    return Curve(fam, post, k, math.sqrt(1.0 / (w_fit + w_prior)), window, kind, len(pairs), len(ages), False, clipped, fitted_on, first, last, dispersion)


# ---- reading recent days ------------------------------------------------------------------------

def adjust(days: list[dict], as_of: str, count_curve: Curve, value_curve: Curve, p: Params) -> list[dict]:
    """Each day's matured estimate: `days` = [{day, spend, count, value}] observed on `as_of` (a row may carry its own `observed_at`). {day, age, spend, count {observed,
    share, estimate, low, high}, value {...}}. The estimate is the visible number over the share visible at that age. The interval is a prediction interval for the final
    number: the part still to arrive is Poisson-like (variance x (1 - f) / f^2 for a count x seen at share f; a value's is value^2 (1 - f) / (f^2 count)), both times the curve's dispersion (orders of unequal worth
    scatter more than the binomial says), widened by the curve's own uncertainty. A day at or past the window is its own final: share 1, no width."""
    out = []
    for i, d in enumerate(days):
        if not isinstance(d, dict) or any(f not in d for f in ("day", "spend", "count", "value")):
            raise _bad(i, "lacks day, spend, count or value")
        day, seen = _day(i, "day", d["day"]), _day(i, "observed_at", d.get("observed_at", as_of))
        if seen < day:
            raise _bad(i, f"was observed on {seen}, before its day {day}")
        for f in ("spend", "count", "value"):
            if isinstance(d[f], bool) or not isinstance(d[f], (int, float)) or math.isnan(d[f]) or d[f] < 0:
                raise _bad(i, f"has {f} {d[f]!r}, which is not a number of 0 or more")
        age = (seen - day).days
        row = {"day": day.isoformat(), "age": age, "spend": float(d["spend"])}
        for name, curve in (("count", count_curve), ("value", value_curve)):
            f = share(curve, age, p.interval_z)[0]
            x = float(d[name])
            est = x / f if f > 0 else x
            n = max(float(d["count"]), 1.0)
            var = curve.dispersion * (x * (1.0 - f) / (f * f) if name == "count" else x * x * (1.0 - f) / (f * f * n)) if f > 0 else 0.0
            dtau = -x * _dtau(age, curve.tau, curve.k, curve.window) / (f * f) if f > 0 else 0.0
            sd = math.sqrt(var + (dtau * curve.se) ** 2)
            row[name] = {"observed": x, "share": round(f, 6), "estimate": est, "low": max(x, est - p.interval_z * sd), "high": est + p.interval_z * sd,
                         "_var": var, "_dtau": dtau, "_se": curve.se}
        out.append(row)
    return out


def summarize(adjusted: list[dict], first: str, last: str, p: Params) -> dict:
    """The window from `first` to `last` (inclusive) of `adjust`'s days: {days, spend, count {observed, estimate, low, high}, value {...}, return {observed, estimate, low,
    high}, share, immature}. The days' remainders are independent; the curve's uncertainty is shared, so it adds linearly across them. The return is the value estimate
    over the spend (spend is known at once)."""
    rows = [r for r in adjusted if first <= r["day"] <= last]
    out = {"days": len(rows), "spend": sum(r["spend"] for r in rows)}
    for name in ("count", "value"):
        obs = sum(r[name]["observed"] for r in rows)
        est = sum(r[name]["estimate"] for r in rows)
        var = sum(r[name]["_var"] for r in rows) + (sum(r[name]["_dtau"] for r in rows) * (rows[0][name]["_se"] if rows else 0.0)) ** 2
        sd = math.sqrt(var)
        out[name] = {"observed": obs, "estimate": est, "low": max(obs, est - p.interval_z * sd), "high": est + p.interval_z * sd}
    sp = out["spend"]
    v = out["value"]
    out["return"] = {"observed": v["observed"] / sp if sp else None, "estimate": v["estimate"] / sp if sp else None,
                     "low": v["low"] / sp if sp else None, "high": v["high"] / sp if sp else None}
    out["share"] = v["observed"] / v["estimate"] if v["estimate"] > 0 else 1.0
    out["immature"] = out["share"] < p.immature_share
    return out


def judge(window: dict, threshold: float, p: Params | None = None) -> str:
    """`above`, `below` or `undecided_immature`: the return of a summarized window against a threshold (a benchmark, a target), with no number of its own. A mature window
    is decided by its return as before; an immature one is decided only when its whole interval is on one side, else it is `undecided_immature`, never a verdict."""
    r = window["return"]
    if r["estimate"] is None:
        return "undecided_immature" if window["immature"] else "below"
    if not window["immature"]:
        return "above" if r["estimate"] >= threshold else "below"
    if r["low"] is not None and r["low"] >= threshold:
        return "above"
    if r["high"] is not None and r["high"] < threshold:
        return "below"
    return "undecided_immature"


# ---- refit, drift, stale -------------------------------------------------------------------------

def refit(old: Curve, observations: list[dict], p: Params, *, family: str = "exp", fitted_on: str | None = None) -> Curve:
    """The curve fitted again on `observations` with the old curve as its prior (its tau, its standard error widened by the thresholds' prior spread so the new data can
    move it). Pure: it returns the new curve; the pack stores both."""
    sd_share = max(old.se, p.prior_sd_share * old.tau) / old.tau
    return fit(observations, old.window, old.tau, replace(p, prior_sd_share=sd_share), old.kind, family=family, fitted_on=fitted_on)


def drift(old: Curve, new: Curve, p: Params) -> dict:
    """{drifted, z, tau_old, tau_new}: whether tau moved by more than `p.drift_se` standard errors between two fits (the combined error of both). A prior-only curve has
    not been measured, so it cannot show a drift."""
    if old.prior_only or new.prior_only:
        return {"drifted": False, "z": None, "tau_old": old.tau, "tau_new": new.tau}
    z = (new.tau - old.tau) / math.sqrt(old.se ** 2 + new.se ** 2)
    return {"drifted": abs(z) > p.drift_se, "z": z, "tau_old": old.tau, "tau_new": new.tau}


def stale(curve: Curve, today: str, p: Params) -> bool:
    """A curve with no fit day, or fitted `p.refit_days` or more days before `today`, is stale. The kit schedules nothing: the pack decides when to refit."""
    if curve.fitted_on is None:
        return True
    return (date.fromisoformat(today) - date.fromisoformat(curve.fitted_on)).days >= p.refit_days


# ---- what a judgement reads ---------------------------------------------------------------------

@dataclass(frozen=True)
class Reading:
    """The days a judgement reads, taken on `observed_on`: a day's age is that date less the day. `kit.lifecycle.judge` and `kit.alerts.check` read a window on the estimate
    when they are given one, and decide nothing from an immature window whose interval straddles the rule's threshold."""
    count: Curve
    value: Curve
    observed_on: str
    params: Params


def window_reading(days: dict, first: date, last: date, reading: Reading) -> dict | None:
    """The window from `first` to `last` (inclusive) of a campaign's `days` ({YYYY-MM-DD: (spend, revenue, conversions, ...)}), read on the estimate: {roas, low, high, revenue,
    conversions, share, immature}, or None when it spent nothing. `roas` is the estimated revenue over the spend, `low` and `high` its interval (equal to `roas` when the
    window is not immature)."""
    rows = [{"day": d, "spend": x[0], "count": x[2], "value": x[1]} for d, x in days.items() if first <= date.fromisoformat(d) <= last]
    if not rows or sum(r["spend"] for r in rows) <= 0:
        return None
    s = summarize(adjust(rows, reading.observed_on, reading.count, reading.value, reading.params), first.isoformat(), last.isoformat(), reading.params)
    r = s["return"]
    lo, hi = (r["low"], r["high"]) if s["immature"] else (r["estimate"], r["estimate"])
    return {"roas": r["estimate"], "low": lo, "high": hi, "revenue": s["value"]["estimate"], "conversions": s["count"]["estimate"], "share": s["share"], "immature": s["immature"]}


def day_reading(day: str, spend: float, orders: float, sales: float, reading: Reading) -> dict | None:
    """One day's sales read on the estimate: {sales, low, high, share, immature} (low and high equal to sales when the day is not immature), or None when the day has no spend."""
    if spend <= 0:
        return None
    a = adjust([{"day": day, "spend": spend, "count": orders, "value": sales}], reading.observed_on, reading.count, reading.value, reading.params)[0]["value"]
    immature = a["share"] < reading.params.immature_share
    return {"sales": a["estimate"], "low": a["low"] if immature else a["estimate"], "high": a["high"] if immature else a["estimate"], "share": a["share"], "immature": immature}
