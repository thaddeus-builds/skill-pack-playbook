"""A portfolio of creatives over time, the rules alone, no database, no clock: the last week's conversions against the week before,
the daily factor it implies, the projected output of the proven creatives, its half-life, the yield of creatives past a cohort age,
and what closing a gap takes (how many new mature creatives, how many entering testing, by when).

From the video-ads skill pack (`portfolio`).

Test: kit/tests/test_creative_portfolio.py.
"""

from __future__ import annotations

import math
import statistics
from datetime import date

FLOOR, CEIL = 0.05, 1.0


def trend(daily_conv: list[float]) -> dict:
    """The last 7 days' conversions, the 7 before, and their ratio (None without a previous week)."""
    last, prev = sum(daily_conv[-7:]), sum(daily_conv[-14:-7])
    return {"conv_7d": last, "prev_conv_7d": prev, "ratio": (last / prev) if prev > 0 else None}


def daily_factor(ratio: float | None) -> float:
    """The factor one day multiplies the output by: flat when it grows or is unknown, else the weekly ratio's 7th root."""
    if ratio is None:
        return 1.0
    return min(CEIL, max(FLOOR, ratio)) ** (1 / 7)


def project(items: list[tuple[float, float]], days: int) -> list[float]:
    """The projected total per day for t = 1..days from [(daily conversions now, daily factor)]."""
    return [sum(d * (f ** t) for d, f in items) for t in range(1, days + 1)]


def half_life(totals: list[float], now: float) -> int | None:
    if now <= 0:
        return None
    for t, v in enumerate(totals, 1):
        if v <= 0.5 * now + 1e-9:
            return t
    return None


def history(first_day: dict[str, str], mature_day: dict[str, str | None], as_of: date, cohort_days: int) -> dict:
    """The yield of creatives older than `cohort_days` and the median days they took to become mature."""
    old = [c for c, d in first_day.items() if (as_of - date.fromisoformat(d)).days >= cohort_days]
    matured = [c for c in old if mature_day.get(c)]
    took = [(date.fromisoformat(mature_day[c]) - date.fromisoformat(first_day[c])).days for c in matured]
    return {"cohort": len(old), "matured": len(matured), "yield": (len(matured) / len(old)) if old else None,
            "median_days_to_mature": statistics.median(took) if took else None}


def replenishment(gap: float, daily_per_mature: float | None, days_left: int, hist: dict, need_cohort: int) -> dict:
    """What closing `gap` conversions takes: new mature creatives, new testing entries, and by when."""
    out = {"gap": round(gap, 2), "needed_mature": None, "needed_testing": None, "lead_days": hist["median_days_to_mature"],
           "enter_within_days": None, "flags": []}
    if gap <= 0:
        return out
    lead = hist["median_days_to_mature"]
    if hist["cohort"] < need_cohort or hist["yield"] in (None, 0) or lead is None or not daily_per_mature:
        out["flags"].append("history_insufficient")
        return out
    after = days_left - lead
    if after <= 0:
        out["flags"].append("too_late")
        return out
    out["needed_mature"] = math.ceil(gap / (daily_per_mature * after))
    out["needed_testing"] = math.ceil(out["needed_mature"] / hist["yield"])
    out["enter_within_days"] = int(after)
    return out
