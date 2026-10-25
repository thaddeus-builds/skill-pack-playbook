"""Impression share with its clamped values, the rules alone.

A platform that reports a share clamps it at the ends: a share under 10% is reported as 0.0999, and a lost share (to budget or to
rank) over 90% as 0.9001. Doing arithmetic on a clamped value is wrong, so it is shown as `<10%` or `>90%` and never averaged as if
it were a number.

  * `show()`: a share as text: `<10%`, `>90%` or `NN%`; None is `n/a`, never 0;
  * `is_clamped()`: whether a value is one of the clamps, and which end;
  * `weighted()`: a week's share weighted by impressions, days with no share left out and counted; a clamped day makes the result a
    bound (`<` or `>`), not a number. Share and percentage of one's own impressions at the top are different metrics: they are not
    mixed here.
  * `fresh()`: the newest day a share may be read for (it can take 24 to 48 hours to update; click share 3 days).

From the google-ads skill pack's prior-art scan of 2026-10-22 (section 3) and the paid-search skill pack (the weekly weighting).

Test: kit/tests/test_impression_share.py.
"""

from __future__ import annotations

from datetime import date, timedelta

LOW_CLAMP, HIGH_CLAMP = 0.0999, 0.9001
SHARE_LAG_DAYS, CLICK_SHARE_LAG_DAYS = 2, 3


def is_clamped(value: float | None, kind: str = "share") -> str | None:
    """`low` for a `share` of 0.0999, `high` for a `lost` share of 0.9001, else None."""
    if value is None:
        return None
    if kind == "share" and abs(value - LOW_CLAMP) < 1e-9:
        return "low"
    if kind == "lost" and abs(value - HIGH_CLAMP) < 1e-9:
        return "high"
    return None


def show(value: float | None, kind: str = "share") -> str:
    """`kind` is `share` (0.1 to 1, 0.0999 stands for under 0.1) or `lost` (0 to 0.9, 0.9001 stands for over 0.9)."""
    if value is None:
        return "n/a"
    end = is_clamped(value, kind)
    if end == "low":
        return "<10%"
    if end == "high":
        return ">90%"
    return f"{round(value * 100):d}%"


def weighted(days: list[tuple[float | None, float]], kind: str = "share") -> dict:
    """`days`: [(share or None, impressions)]. {value, bound, share_days, days}: `bound` is None, `<` or `>` when a clamped day is
    in; days without a share (or without impressions) are left out and counted in `days - share_days`."""
    used = [(s, i) for s, i in days if s is not None and i]
    total = sum(i for _, i in used)
    if not total:
        return {"value": None, "bound": None, "share_days": 0, "days": len(days)}
    value = sum(s * i for s, i in used) / total
    ends = {is_clamped(s, kind) for s, _ in used} - {None}
    bound = None if not ends else ("<" if "low" in ends else ">")
    return {"value": round(value, 4), "bound": bound, "share_days": len(used), "days": len(days)}


def fresh(today: date, click_share: bool = False) -> date:
    """The newest day to read: none for yesterday or today (2 days back; 3 for click share)."""
    return today - timedelta(days=CLICK_SHARE_LAG_DAYS if click_share else SHARE_LAG_DAYS)
