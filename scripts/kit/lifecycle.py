"""The life of a campaign: the rules alone, no database, no platform. A campaign is where creatives share a budget and a purpose; its
state is read from what the platform says of it and what it spent, returned and delivered in a window. Every number is a field of
`Params`; nothing here writes.

The order the states are checked in (the first that holds):

    never spent        setup if the platform says active, else ended (never_ran)
    blocked            disapproved, or the share of the last 7 days' spend on ads with issues is over `issue_share`
    ended              stopped (not active) and no spend for `end_idle_days`
    learning           under `learning_days` of delivery. There is no "slow" state: a campaign with too few conversions is not slow,
                       it is `unjudged`
    unjudged           the window holds under the judging spend or conversions: not a verdict, the reason says why
    fatigued           the creatives are wearing out: its click-through rate, relative to the account's and shrunk, was once high
                       (the best 20% of its own weekly history) and is now low (the worst 20%), and has fallen by `fatigue_ctr_drop`
                       from that peak. A delivery-side signal: results alone are too noisy at this volume
    earning            its return is at least `earn_margin` above the benchmark's
    declining          its return fell by `decline_drop` against the window before and is not above the benchmark: a fall with no
                       exposure evidence, which new creatives are not known to fix
    lagging            its return is under the benchmark's by `earn_margin` or more and it did not fall
    steady             judged, none of the above

`hold()` keeps one week's noise from moving a state that status and time do not decide.

A window that includes recent days is understated (`kit.maturity`). Given a `maturity.Reading`, `windows()` adds each window's matured reading and `judge()` reads the return on
the estimate: a window whose visible share is under the threshold is *immature*, and a rule on its return (earning, declining, lagging) is decided only when the whole interval
is on one side of its threshold; where it cannot tell the state is `unjudged` with the reason `immature`. A mature window is judged as it always was, and without a reading
nothing changes.

From the video-ads skill pack (`campaign`).

Test: kit/tests/test_lifecycle.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from kit import maturity

FORCED = ("blocked", "ended", "setup", "learning")      # decided by status or by time, never by noise: entered and left at once
STATES = ("blocked", "ended", "setup", "learning", "earning", "steady", "lagging", "declining", "fatigued", "unjudged")
ACTIVE = "active"            # the pack maps its platform's delivery status to these three words (or None: the export never said)
DISAPPROVED = "disapproved"


@dataclass
class Params:
    window_days: int
    learning_days: int
    judge_spend: float
    min_conversions: float
    earn_margin: float
    use_share: float
    decline_drop: float
    issue_share: float
    end_idle_days: int
    budget_step: float
    hold_weeks: int = 2
    fatigue_good_pct: float = 80
    fatigue_bad_pct: float = 20
    fatigue_ctr_drop: float = 0.20
    fatigue_min_weeks: int = 8
    fatigue_min_impressions: float = 5000
    fatigue_prior_impressions: float = 1000


@dataclass
class Campaign:
    """What the rules read of one campaign. `days` is {YYYY-MM-DD: (spend, revenue, conversions[, impressions, clicks])} for the days it
    spent; `status` the platform's delivery status (None when the export never said); `budget` its daily budget or None; `ctr` its weekly click
    readings (campaign_ctr_weeks) and `ctr_account` the account's, over the same weeks."""
    id: str
    status: str | None
    days: dict
    budget: float | None
    issue_share: float = 0.0                  # the share of the last 7 days' spend on ads with issues
    basis: str = "unknown"                    # where `budget` came from: the campaign, its ad groups, unknown
    ctr: list = field(default_factory=list)
    ctr_account: list = field(default_factory=list)


@dataclass
class Verdict:
    state: str
    reason: str
    since_first_spend: int | None
    window: dict
    previous: dict
    use_share: float | None
    benchmark_roas: float | None = None
    proposals: list | None = None
    ctr: dict | None = None


def _sum(days: dict, lo: date, hi: date) -> dict:
    spend = rev = conv = 0.0
    n = 0
    for d, x in days.items():
        if lo <= date.fromisoformat(d) <= hi:
            spend, rev, conv, n = spend + x[0], rev + x[1], conv + x[2], n + (1 if x[0] > 0 else 0)
    return {"spend": spend, "revenue": rev, "conversions": conv, "days": n, "roas": (rev / spend) if spend > 0 else None}


def windows(days: dict, as_of: str, p: Params, reading: "maturity.Reading | None" = None) -> tuple[dict, dict]:
    """(the window ending at as_of, the one before it). With a `reading` each carries `matured`: its return read on the estimate (`maturity.window_reading`), or None when it
    spent nothing."""
    end = date.fromisoformat(as_of)
    mid = end - timedelta(days=p.window_days)
    spans = ((mid + timedelta(days=1), end), (mid - timedelta(days=p.window_days - 1), mid))
    out = [_sum(days, lo, hi) for lo, hi in spans]
    if reading is not None:
        for w, (lo, hi) in zip(out, spans):
            w["matured"] = maturity.window_reading(days, lo, hi, reading)
    return out[0], out[1]


def _band(w: dict) -> tuple[float | None, float | None]:
    """(low, high) of a window's return for a rule to compare: the estimate's interval when the window is immature, else a point (the estimate when there is one, else the
    observed return)."""
    m = w.get("matured")
    if m is None:
        return w["roas"], w["roas"]
    return (m["low"], m["high"]) if m["immature"] else (m["roas"], m["roas"])


def _below(lo: float, hi: float, t_lo: float, t_hi: float) -> bool | None:
    """Whether a return in [lo, hi] is under a threshold in [t_lo, t_hi]: True when all of it is, False when none of it is, None when the interval cannot tell. For a point and a
    point it is the plain comparison."""
    if hi < t_lo:
        return True
    if lo >= t_hi:
        return False
    return None


def weekly_clicks(days: dict, as_of: str, weeks: int) -> list[tuple[float, float]]:
    """[(impressions, clicks)] for each of the last `weeks` 7-day windows ending at as_of, oldest first (a day with no figures counts nothing)."""
    end = date.fromisoformat(as_of)
    out = [[0.0, 0.0] for _ in range(weeks)]
    for d, x in days.items():
        k = (end - date.fromisoformat(d)).days
        if 0 <= k < 7 * weeks and len(x) > 4:
            out[weeks - 1 - k // 7][0] += x[3] or 0.0
            out[weeks - 1 - k // 7][1] += x[4] or 0.0
    return [(a, b) for a, b in out]


def relative_ctr(own: list, account: list, p: Params) -> list[float | None]:
    """Each week's click-through rate of the campaign over the account's, shrunk toward the account's with a prior of `fatigue_prior_impressions`
    impressions (a Beta-Binomial smoothing: a thin week says little and is pulled to 1); None for a week under `fatigue_min_impressions`.
    Dividing by the account's removes what hits every campaign at once (the season, the auction)."""
    out = []
    for (imp, clk), (ai, ac) in zip(own, account):
        base = (ac / ai) if ai else 0.0
        if imp < p.fatigue_min_impressions or base <= 0:
            out.append(None)
            continue
        out.append(((clk + p.fatigue_prior_impressions * base) / (imp + p.fatigue_prior_impressions)) / base)
    return out


def _quantile(xs: list[float], pct: float) -> float:
    xs = sorted(xs)
    pos = (len(xs) - 1) * pct / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def fatigue(rel: list, p: Params) -> dict | None:
    """The owner's definition of fatigue on the weekly relative click-through rates `rel` (oldest first, None for a thin week): was high, now low.

    `ref` is every reading but the last two (so the peak is not the latest swing); the peak is the mean of the best 20% of them (at least two weeks, which
    keeps one lucky week from being the peak); now is the last reading. Fatigued when now is at or under the worst 20% of `ref` and at least
    `fatigue_ctr_drop` under the peak. None when there are fewer than `fatigue_min_weeks` readings or the last is thin: no reading, never a guess."""
    vals = [v for v in rel if v is not None]
    if len(vals) < p.fatigue_min_weeks or not rel or rel[-1] is None:
        return None
    ref = vals[:-2]
    top = sorted(ref, reverse=True)[:max(2, round(len(ref) * (100 - p.fatigue_good_pct) / 100))]
    peak = sum(top) / len(top)
    now = rel[-1]
    low = _quantile(ref, p.fatigue_bad_pct)
    return {"now": round(now, 3), "peak": round(peak, 3), "low": round(low, 3), "weeks": len(vals),
            "fatigued": now <= low and now <= peak * (1 - p.fatigue_ctr_drop)}


def judge(c: Campaign, as_of: str, p: Params, benchmark: float | None, reading: "maturity.Reading | None" = None) -> Verdict:
    """The state of one campaign on `as_of` and the reason; `benchmark` the return it is compared with (its kind's, else the
    account's), None when there is none to compare with (then nothing is `earning`). With a `reading` the return is read on the estimate (see the module's note); an
    immature window that a rule cannot decide is `unjudged` for the reason `immature`."""
    cur, prev = windows(c.days, as_of, p, reading)
    spent = sorted(d for d, x in c.days.items() if x[0] > 0 and d <= as_of)
    first = spent[0] if spent else None
    last = spent[-1] if spent else None
    age = (date.fromisoformat(as_of) - date.fromisoformat(first)).days + 1 if first else None
    active = c.status == ACTIVE or (c.status is None and last is not None and
                                    (date.fromisoformat(as_of) - date.fromisoformat(last)).days <= 2)
    use = None
    if c.budget and c.budget > 0:
        use = cur["spend"] / (c.budget * p.window_days)
    fat = fatigue(relative_ctr(c.ctr, c.ctr_account, p), p) if c.ctr else None

    def out(state: str, reason: str) -> Verdict:
        return Verdict(state, reason, age, cur, prev, use, benchmark, [], fat)

    if first is None:
        return out("setup", "no_spend_yet") if c.status == ACTIVE else out("ended", "never_ran")
    if c.status == DISAPPROVED or (active and c.issue_share >= p.issue_share):
        return out("blocked", "disapproved" if c.status == DISAPPROVED else "ads_with_issues")
    idle = (date.fromisoformat(as_of) - date.fromisoformat(last)).days
    if not active and idle >= p.end_idle_days:
        return out("ended", "stopped_idle")
    if age < p.learning_days:
        return out("learning", "new")
    if cur["spend"] < p.judge_spend or cur["conversions"] < p.min_conversions:        # the evidence is what was seen: a graduation needs real conversions
        return out("unjudged", "thin")
    if fat and fat["fatigued"]:
        return out("fatigued", "ctr_worn_out")
    lo, hi = _band(cur)
    if benchmark and lo is not None:
        t = benchmark * (1 + p.earn_margin)
        above = _below(lo, hi, t, t)
        if above is False:
            return out("earning", "above_benchmark" if use is None or use >= p.use_share else "creative_limited")
        if above is None:
            return out("unjudged", "immature")
    if prev["spend"] >= p.judge_spend and _band(prev)[0] and lo is not None:
        plo, phi = _band(prev)
        fell = _below(lo, hi, plo * (1 - p.decline_drop), phi * (1 - p.decline_drop))
        if fell is True:
            return out("declining", "return_falling")
        if fell is None:
            return out("unjudged", "immature")
    if not benchmark or lo is None:
        return out("steady", "no_benchmark")
    behind = _below(lo, hi, benchmark * (1 - p.earn_margin), benchmark * (1 - p.earn_margin))
    if behind is True:
        return out("lagging", "below_benchmark")
    if behind is None:
        return out("unjudged", "immature")
    return out("steady", "near_benchmark")


def hold(states: list[str], reasons: list[str], weeks: int) -> tuple[str, str, str | None]:
    """The held state after the readings `states` (oldest first, one per weekly checkpoint): (state, reason, the raw state waiting to take over or None).

    The states that status or time decide (FORCED: blocked, ended, setup, learning) are entered and left at once. Among the others (earning, steady,
    declining, fatigued, unjudged) a change is taken only when the last `weeks` readings all say the new state: one week's noise moves nothing. While a change
    is pending the old state and its reason stand, and the pending one is named."""
    held, why = states[0], reasons[0]
    for i in range(1, len(states)):
        s = states[i]
        if s in FORCED or held in FORCED or s == held:
            held, why = s, reasons[i]
        elif weeks <= 1 or (i + 1 >= weeks and all(x == s for x in states[i + 1 - weeks:i + 1])):
            held, why = s, reasons[i]
    pending = states[-1] if states[-1] != held else None
    return held, why, pending
