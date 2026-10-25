"""Two routes of one platform's numbers side by side (an export against the API, a report against a stream): the rules alone, no
files, no database.

Each route is `{day: {metric: value, ..., ads: n}}`. A day is `match` when every metric of the two routes is within the tolerance
of the larger one, `differs` when one is not, `only_a` or `only_b` when a route has no row for that day. Money is compared only
when both routes name the same currency: otherwise the spend of the day is `currency` and the counts are still compared. The result
says where the routes agree and where they do not; it never says which is right. (Comparing a platform with the company's own
numbers is a different job: it belongs to measurement.)

From the video-ads skill pack (`reconcile`).

Test: kit/tests/test_reconcile.py.
"""

from __future__ import annotations

from datetime import date, timedelta

METRICS = ("spend", "impressions", "clicks", "conversions")
MONEY = "spend"


def totals(rows: list[dict], metrics: tuple[str, ...] = METRICS) -> dict[str, dict]:
    """{day: totals} of one route's daily rows (already one row per entity and day, each with a `date`)."""
    out: dict[str, dict] = {}
    for r in rows:
        d = out.setdefault(r["date"], {**{m: 0.0 for m in metrics}, "ads": 0})
        for m in metrics:
            d[m] += r.get(m) or 0.0
        d["ads"] += 1
    return {k: {m: round(v, 2) if isinstance(v, float) else v for m, v in t.items()} for k, t in out.items()}


def window(until: str, days: int) -> list[str]:
    end = date.fromisoformat(until)
    return [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def compare(a: dict, b: dict, days: list[str], tolerance: float, same_currency: bool,
            metrics: tuple[str, ...] = METRICS) -> list[dict]:
    """One row per day of `days` where either route has numbers: {day, a, b, diff {metric: b - a}, off [metrics beyond the
    tolerance], verdict}. The money metric is skipped when the routes' currencies differ."""
    out = []
    for day in days:
        ra, rb = a.get(day), b.get(day)
        if ra is None and rb is None:
            continue
        if ra is None or rb is None:
            out.append({"day": day, "a": ra, "b": rb, "diff": {}, "off": [], "verdict": "only_b" if ra is None else "only_a"})
            continue
        diff = {m: round(rb[m] - ra[m], 2) for m in metrics}
        off = [m for m in metrics if (m != MONEY or same_currency) and abs(diff[m]) > tolerance * max(abs(ra[m]), abs(rb[m]), 0.0)
               and max(abs(ra[m]), abs(rb[m])) > 0]
        verdict = "differs" if off else ("currency" if not same_currency else "match")
        out.append({"day": day, "a": ra, "b": rb, "diff": diff, "off": off, "verdict": verdict})
    return out


def summary(rows: list[dict], metrics: tuple[str, ...] = METRICS) -> dict:
    count = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("match", "differs", "currency", "only_a", "only_b")}
    both = [r for r in rows if r["a"] is not None and r["b"] is not None]
    sums = {m: {"a": round(sum(r["a"][m] for r in both), 2), "b": round(sum(r["b"][m] for r in both), 2)} for m in metrics}
    return {"days": len(rows), **count, "compared_days": len(both), "totals": sums}
