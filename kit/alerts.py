"""Alerts against an entity's own baseline, no database, no platform: the latest settled day against the mean of the (up to) 7
settled days before it, never against a fixed number.

  * `settled_points()`: the `n` most recent settled `Point`s, newest first;
  * `without_event_days()`: days that fall in a known sale or event are dropped from the baseline (the judged day stays) and the
    baseline refills from older settled days;
  * `check()`: a spend or a return against `threshold` times its baseline. `ge` is a spike (current >= threshold x baseline), `le`
    a drop. A return is the sum of sales over the sum of spend, never a mean of daily ratios. Fewer than 2 settled days, no spend
    now or in the baseline, or fewer than `min_clicks` clicks on the judged day give no verdict, with a reason. A hit against a
    baseline of zero is met, not measured, and says so (`spend_from_zero_baseline`, `return_from_zero_baseline`);
  * `in_cooldown()`: the same alert is not sent again inside its cooldown (with an hour of slack for scheduler jitter, at most
    half the cooldown).

From the paid-search skill pack (`compute_alerts`, `alerts`; its cases are this module's test).

Test: kit/tests/test_alerts.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Iterable, NamedTuple

BASELINE_DAYS = 7
COOLDOWN_SLACK = timedelta(hours=1)


class Point(NamedTuple):
    date: str
    spend: float
    sales: float
    clicks: int | None = None


def settled_points(daily: Iterable[Point], settled: set[str], n: int = BASELINE_DAYS + 1) -> list[Point]:
    pts = sorted((p for p in daily if p.date in settled), key=lambda p: p.date, reverse=True)
    return pts[:n]


def without_event_days(points: list[Point], is_event: Callable[[str], bool], baseline_days: int = BASELINE_DAYS
                       ) -> tuple[list[Point], list[str]]:
    """(`points` with event days dropped from the baseline, the dropped dates). `points` is newest first."""
    if not points:
        return [], []
    kept, dropped = [points[0]], []
    for p in points[1:]:
        if len(kept) > baseline_days:
            break
        if is_event(p.date):
            dropped.append(p.date)
        else:
            kept.append(p)
    return kept, sorted(dropped)


def check(points: list[Point], metric: str, comparison: str, threshold: float, baseline_days: int = BASELINE_DAYS,
          min_clicks: int | None = None) -> dict:
    """`points`: newest first, as `settled_points` returns them. `metric` is `spend` or `return`; `comparison` `ge` or `le`.
    {hit, current, baseline, current_date, baseline_days, reason, reason_params}; `hit` is None when there is no verdict."""
    if metric not in ("spend", "return") or comparison not in ("ge", "le") or threshold <= 0:
        raise ValueError(f"bad alert rule: {metric} {comparison} {threshold}")
    out = {"hit": None, "current": None, "baseline": None, "current_date": None, "baseline_days": 0, "reason": None,
           "reason_params": {}}
    if len(points) < 2:
        out["reason"] = "too_few_settled_days"
        return out
    cur, base = points[0], points[1:baseline_days + 1]
    out.update(current_date=cur.date, baseline_days=len(base))
    if min_clicks is not None and (cur.clicks or 0) < min_clicks:
        out["reason"] = "too_few_clicks"
        return out
    if metric == "spend":
        current = cur.spend
        baseline = sum(p.spend for p in base) / len(base)
        if not current and not baseline:
            out["reason"] = "no_spend_current_day"
            return out
    else:
        if not cur.spend:
            out["reason"] = "no_spend_current_day"
            return out
        base_spend = sum(p.spend for p in base)
        if not base_spend:
            out["reason"] = "no_spend_baseline"
            return out
        current = cur.sales / cur.spend
        baseline = sum(p.sales for p in base) / base_spend
    hit = current >= threshold * baseline if comparison == "ge" else current <= threshold * baseline
    out.update(current=round(current, 6), baseline=round(baseline, 6), hit=hit)
    if hit and not baseline and (metric == "spend" or not current):
        out["reason"] = "spend_from_zero_baseline" if metric == "spend" else "return_from_zero_baseline"
        out["reason_params"] = {"spend": round(cur.spend, 6), "date": cur.date, "baseline_days": len(base)}
    return out


def in_cooldown(last_fired: datetime | None, cooldown_hours: float, at: datetime) -> bool:
    if last_fired is None:
        return False
    cooldown = timedelta(hours=cooldown_hours)
    return at - last_fired < cooldown - min(COOLDOWN_SLACK, cooldown / 2)
