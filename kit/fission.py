"""A creative's fission score: the rules alone, no database, no clock.

A number from 0 to 1 per creative: how much the downstream wants the creative to go on being multiplied (neighbours made by changing
one or two dimensions). It is not the conversion: a creative that converted a lot and is fading scores low, so the score is read over
the creative's recent days, against the account's own proven creatives (the benchmark is their median cost per conversion and
conversions per delivery day, from at least 3). Only a creative that has earned a verdict (mature, declining, or ended as faded or a
weak creative) is scored; the others are unknown, never 0.

From the video-ads skill pack (`fission`).

Test: kit/tests/test_fission.py.
"""

from __future__ import annotations

import math
import statistics

from kit import creative_portfolio

SPEAKS = ("mature", "declining")          # plus ended with reason faded or weak_creative


def speaks(state: str, reason: str | None) -> bool:
    return state in SPEAKS or (state == "ended" and reason in ("faded", "weak_creative"))


def stats(totals: dict) -> dict | None:
    """{cost, volume} of lifetime totals (spend, conversions, delivery_days); None without conversions."""
    c, d = totals.get("conversions") or 0, totals.get("delivery_days") or 0
    if c <= 0 or d <= 0:
        return None
    return {"cost": totals["spend"] / c, "volume": c / d}


def recent(days: list, n: int) -> dict | None:
    """{cost, volume} over the last `n` counted days that delivered; None with no conversion in them."""
    window = [d for d in days[-n:] if d.spend > 0 or d.impressions > 0]
    return stats({"spend": sum(d.spend for d in window), "conversions": sum(d.conversions for d in window),
                  "delivery_days": len(window)})


def benchmark(proven: list[dict], minimum: int) -> dict | None:
    """The account's median cost and daily volume over its proven creatives; None below `minimum` (at least 3)."""
    if len(proven) < max(3, minimum):
        return None
    return {"cost": statistics.median(p["cost"] for p in proven), "volume": statistics.median(p["volume"] for p in proven),
            "n": len(proven)}


def _half(x: float) -> float:
    return min(1.0, max(0.0, x / 2))


def score(s: dict, bench: dict, ratio: float | None = None) -> dict:
    """The score: the square root of efficiency times impact, times the trend (the last 7 days over the 7 before) when it is
    under 1: a creative that earns less each week is multiplied by that ratio, one that grows is not boosted."""
    eff, imp = _half(bench["cost"] / s["cost"]), _half(s["volume"] / bench["volume"])
    damp = 1.0 if ratio is None else min(1.0, max(0.0, ratio))
    return {"fission": round(math.sqrt(eff * imp) * damp, 2), "efficiency": round(eff, 3), "impact": round(imp, 3),
            "trend": None if ratio is None else round(ratio, 3)}


def scores(rows: list[dict], days_of: dict, window_days: int, minimum: int) -> tuple[dict, dict | None, dict]:
    """({creative: {state, reason, fission | None, ...}}, the benchmark, {omitted state: count}) from the creatives' rows
    (`creative_life`'s) and their days. Only a creative that has earned a verdict is scored; the others are
    unknown, never 0."""
    proven = [stats(r["totals"]) for r in rows if speaks(r["state"], r["reason"]) and r["reason"] != "weak_creative"]
    bench = benchmark([p for p in proven if p], minimum)
    out, omitted = {}, {}
    for r in rows:
        base = {"state": r["state"], "reason": r["reason"], "label": r["label"], "fission": None}
        if not speaks(r["state"], r["reason"]):
            omitted[r["state"]] = omitted.get(r["state"], 0) + 1
            out[r["creative"]] = base
        elif r["reason"] == "weak_creative":
            out[r["creative"]] = {**base, "fission": 0.0, "efficiency": 0.0, "impact": 0.0, "cost": None, "volume": None}
        elif bench is None:
            omitted[r["state"]] = omitted.get(r["state"], 0) + 1
            out[r["creative"]] = base
        else:
            counted = [d for d in days_of[(r["source"], r["creative"])] if d.complete and not d.blocked]
            s = recent(counted, window_days)
            if s is None:                                   # nothing earned lately: dug enough
                out[r["creative"]] = {**base, "fission": 0.0, "efficiency": 0.0, "impact": 0.0, "cost": None, "volume": None}
            else:
                ratio = creative_portfolio.trend([d.conversions for d in counted])["ratio"]
                out[r["creative"]] = {**base, **score(s, bench, ratio), "cost": round(s["cost"], 2),
                                      "volume": round(s["volume"], 3)}
    return out, bench, omitted
