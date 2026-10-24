"""Is a keyword getting dearer because rivals bid harder, or because we raised our own bid? A weekly reading, not a rule: nothing
acts on it. No database, no platform.

Per ISO week and keyword (`weekly()`, from the keyword's daily rows): `share`, the top-of-search impression share weighted by the
day's impressions (days the platform gave none are left out and counted, `share_days`, never read as 0; the scale is the platform's
own and not confirmed, so only its relative change is used), `cpc` (cost over clicks, None with no click) and `bid` (ours,
weighted by the day's impressions, None when no row carries one). `verdict()` compares a week with the one before (both need the
number); a change counts only past `move`, a fraction:

    heating   CPC up and our share down, our bid not raised
    bought    our share up after our bid went up
    cooling   our bid not raised, and CPC down or our share up
    flat      none of the three moved
    None      anything else, or a missing number: the reason says which (`missing_input`, `unclear`, `no_prior_week`)

From the paid-search skill pack (`auction_pressure`; its cases are the test).

Test: kit/tests/test_auction_pressure.py.
"""

from __future__ import annotations

from kit import dates


def _rel(new, old):
    """Relative change from old to new; None when either is missing or old is 0."""
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old)


def weekly(days: list[dict], weeks: list[str], move: float) -> list[dict]:
    """`days`: [{date, impressions, clicks, cost, share, bid}] of one keyword (all its match types together); `weeks`: the ISO
    weeks to report, oldest first. One row per week, with `verdict` and `reason` against the week before."""
    acc = {w: {"impressions": 0, "clicks": 0, "cost": 0.0, "is_w": 0.0, "is_imps": 0, "is_days": 0, "bid_w": 0.0, "bid_imps": 0}
           for w in weeks}
    for d in days:
        a = acc.get(dates.iso_week(d["date"]))
        if a is None:
            continue
        imps = d.get("impressions") or 0
        a["impressions"] += imps
        a["clicks"] += d.get("clicks") or 0
        a["cost"] += d.get("cost") or 0.0
        if d.get("share") is not None and imps:
            a["is_w"] += d["share"] * imps
            a["is_imps"] += imps
            a["is_days"] += 1
        if d.get("bid") is not None and imps:
            a["bid_w"] += d["bid"] * imps
            a["bid_imps"] += imps
    rows = []
    for w in weeks:
        a = acc[w]
        rows.append({"week": w, "impressions": a["impressions"], "clicks": a["clicks"], "cost": round(a["cost"], 2) + 0.0,
                     "cpc": round(a["cost"] / a["clicks"], 4) if a["clicks"] else None,
                     "share": round(a["is_w"] / a["is_imps"], 4) if a["is_imps"] else None, "share_days": a["is_days"],
                     "bid": round(a["bid_w"] / a["bid_imps"], 4) if a["bid_imps"] else None,
                     "verdict": None, "reason": "no_prior_week"})
    for prev, cur in zip(rows, rows[1:]):
        cur["verdict"], cur["reason"] = verdict(prev, cur, move)
    return rows


def verdict(prev: dict, cur: dict, move: float) -> tuple[str | None, str | None]:
    """(verdict, why none): `why none` is `missing_input` or `unclear`."""
    d = {k: _rel(cur[k], prev[k]) for k in ("cpc", "share", "bid")}
    if any(v is None for v in d.values()):
        return None, "missing_input"
    up = {k: v >= move for k, v in d.items()}
    down = {k: v <= -move for k, v in d.items()}
    if not any(up.values()) and not any(down.values()):
        return "flat", None
    if up["bid"]:
        return ("bought", None) if up["share"] else (None, "unclear")
    if down["bid"]:
        return None, "unclear"
    if up["cpc"] and down["share"]:
        return "heating", None
    if (down["cpc"] or up["share"]) and not (up["cpc"] or down["share"]):
        return "cooling", None
    return None, "unclear"
