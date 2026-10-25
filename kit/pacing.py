"""Budget pacing, the rules alone: no database, no clock, no platform. The caller hands over the month, the inputs and the history;
the module returns the plan.

  * `plan()`: the money left of a month's target spread over the days left by the account's own weekday weights (flat until
    every weekday has `min_weeks` weeks of history), and the day's budget split into two wallets: *perform* takes what the result
    still to reach needs at the proven creatives' efficiency (never more than the day's budget), *explore* is the rest. Flags,
    not floors: `shortfall`, `result_met`, `no_performance`, `flat`.
  * `cap_status()`: a monthly cap against what is spent so far, at the recent run-rate: `ok`, `warn`, `projected_over`,
    `over_cap`, or `unknown` while the spend so far is only a lower bound (days missing: a crossing is proved, never its absence).
    `reach()` is the date a target is crossed at that rate.

From the video-ads skill pack (`pacing`) and the paid-search skill pack (`compute_budget`); the second is the test set of `cap_status`.

Test: kit/tests/test_pacing.py.
"""

from __future__ import annotations

import calendar
import math
from datetime import date, timedelta



def month_days(month: str) -> list[date]:
    y, m = int(month[:4]), int(month[5:7])
    return [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]


def weekday_weights(daily_spend: dict[str, float], through: date, history_weeks: int, min_weeks: int) -> tuple[list[float], str, int]:
    """(7 weights Monday..Sunday with mean 1, 'weighted' | 'flat', the least occurrences of a weekday). The history is the
    complete days of the last `history_weeks` weeks up to `through`."""
    start = through - timedelta(days=7 * history_weeks - 1)
    sums, counts = [0.0] * 7, [0] * 7
    for iso, spend in daily_spend.items():
        d = date.fromisoformat(iso)
        if start <= d <= through:
            sums[d.weekday()] += spend
            counts[d.weekday()] += 1
    least = min(counts)
    if least < min_weeks:
        return [1.0] * 7, "flat", least
    means = [s / c for s, c in zip(sums, counts)]
    avg = sum(means) / 7
    if avg <= 0:
        return [1.0] * 7, "flat", least
    return [m / avg for m in means], "weighted", least


def plan(month: str, spend_target: float, result_target: float | None, daily_spend: dict[str, float],
         daily_conv: dict[str, float], last_day: date, efficiency: float | None, history_weeks: int, min_weeks: int,
         day: date | None = None) -> dict:
    """The plan for `day` (default: the day after `last_day`) and the days left of the month.

    efficiency: conversions per unit of money of the Performance creatives over their last 7 days, None when unknown."""
    days = month_days(month)
    elapsed = [d for d in days if d <= last_day]
    left = [d for d in days if d > last_day]
    spent = sum(v for iso, v in daily_spend.items() if date.fromisoformat(iso) in set(elapsed))
    conv = sum(v for iso, v in daily_conv.items() if date.fromisoformat(iso) in set(elapsed))
    weights, kind, least = weekday_weights(daily_spend, last_day, history_weeks, min_weeks)
    w = {d: weights[d.weekday()] for d in days}
    money_left = max(0.0, spend_target - spent)
    result_left = None if result_target is None else max(0.0, result_target - conv)
    wsum = sum(w[d] for d in left)
    perform_total = None
    if result_left is not None and efficiency and efficiency > 0:
        perform_total = result_left / efficiency
    rows = []
    for d in left:
        budget = money_left * w[d] / wsum if wsum else 0.0
        need = 0.0 if perform_total is None else min(budget, perform_total * w[d] / wsum)
        rows.append({"day": d.isoformat(), "weekday": d.strftime("%a"), "weight": round(w[d], 4),
                     "budget": round(budget, 2), "perform": round(need, 2), "explore": round(budget - need, 2)})
    even = spend_target * sum(w[d] for d in elapsed) / sum(w[d] for d in days) if elapsed else 0.0
    today = next((r for r in rows if day is None or r["day"] == day.isoformat()), None)
    flags = []
    if result_left == 0:
        flags.append("result_met")
    if perform_total is not None and perform_total > money_left + 1e-9:
        flags.append("shortfall")
    if efficiency is None or not efficiency:
        flags.append("no_performance")
    if kind == "flat":
        flags.append("flat")
    return {"month": month, "last_day": last_day.isoformat(), "weights": [round(x, 4) for x in weights], "weights_kind": kind,
            "weekday_weeks": least, "spend_to_date": round(spent, 2), "result_to_date": round(conv, 4),
            "money_left": round(money_left, 2), "result_left": None if result_left is None else round(result_left, 4),
            "days_left": len(left), "perform_need_total": None if perform_total is None else round(perform_total, 2),
            "pace_ratio": round(spent / even, 4) if even else None, "day": today, "days": rows, "flags": flags}


def reach(spent: float, target: float, rate: float, last: date, end: date) -> tuple[str, date | None]:
    """(state, date) for the spend crossing `target` at `rate` a day from `last`: `reached`, `not_reached` (no rate),
    `not_reached_this_month` (the crossing falls after `end`), or `on` with the date."""
    if spent >= target:
        return "reached", None
    if rate <= 0:
        return "not_reached", None
    hit = last + timedelta(days=math.ceil((target - spent) / rate))
    return ("not_reached_this_month", None) if hit > end else ("on", hit)


def cap_status(month_first: date, last: date, end: date, by_day: dict[date, float], cap: float, warn_ratio: float,
               run_rate_days: int) -> dict:
    """A monthly `cap` against the spend of `month_first`..`last` (`by_day`: money per day; a day absent is a day missing).

    run-rate = the mean of the last `run_rate_days` days present; projected = spent + run-rate x days left. A month with days
    missing has a lower-bound spend: a threshold it already crossed is `reached`, every other one and the status are `unknown`.
    `today_budget` = what is left of the cap over the days after `last` (None on the month's last day); `upper_bound` says
    it overstates when the spend is a lower bound."""
    spent = sum(by_day.values())
    window = sorted(by_day)[-run_rate_days:]
    rate = sum(by_day[d] for d in window) / len(window) if window else 0.0
    days_left = (end - last).days
    projected = spent + rate * days_left
    warn_at = warn_ratio * cap
    span = [month_first + timedelta(n) for n in range((last - month_first).days + 1)]
    missing = [d for d in span if d not in by_day]
    thresholds = []
    for name, target in (("warn", warn_at), ("cap", cap)):
        state, hit = reach(spent, target, rate, last, end)
        if missing and state != "reached":
            state, hit = "unknown", None
        thresholds.append({"name": name, "target": target, "state": state, "date": hit})
    status = ("over_cap" if spent >= cap else "warn" if spent >= warn_at else "unknown" if missing
              else "projected_over" if projected > cap else "warn" if projected >= warn_at else "ok")
    return {"spent": spent, "run_rate": rate, "run_rate_days_used": len(window), "projected": projected,
            "ratio_of_cap": spent / cap if cap else None, "thresholds": thresholds, "missing_days": missing, "status": status,
            "warn_reason": None if status != "warn" else ("spent" if spent >= warn_at else "projected"),
            "today_budget": max(0.0, cap - spent) / days_left if days_left else None, "days_left": days_left,
            "upper_bound": bool(missing)}
