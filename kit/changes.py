"""The change record, no database, no platform: what was changed, by whom, and what the numbers did after it.

  * `merge()`: our own sent writes and the platform's recorded events become one list. A recorded event that one of our writes
    explains (the same object and the same new value, within `slack` of each other) is dropped; the others are `external` (a hand
    edit in the platform's console, another tool, the platform's automation). Without the platform's history only our own
    writes are seen: no event seen is not no change made (`history_missing`);
  * `after_start()`: the first whole day that shows a change made at a time: the day after the day `hours` (the learning
    window) past it. Report days are the market's own and changes UTC, so whole days;
  * `effect_windows()`, `episodes()`: a chain of changes to one object is one episode, a change on or before the episode's
    after-window's last day joins it; the before window is `days` days ending 2 days before the first change, the after window
    `days` days from `after_start`;
  * `overlaps()`: other changes to the object's parents (`ancestors`) or inside it (`inner`) that fall in the episode's span, so a
    comparison says what else moved;
  * `beyond_noise()`: the after-minus-before difference against the days' own spread: a t-like ratio, beyond noise past `k`.

A change is a dict `{object: (grain, id), parents: [(grain, id), ...], at: ISO time, before, after, source}`; the pack builds it.

From the paid-search skill pack (`change_history`, `compute_changes`; its cases are the test) and the video-ads skill pack
(`ads.changes/1`, which records the same facts).

Test: kit/tests/test_changes.py.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta, timezone

OWN, EXTERNAL = "own", "external"
OWN_WRITE_SLACK = timedelta(hours=1)


def utc(ts) -> datetime:
    t = ts if isinstance(ts, datetime) else datetime.fromisoformat(ts)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _num(v) -> float | None:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def merge(own: list[dict], recorded: list[dict], since: datetime, slack: timedelta = OWN_WRITE_SLACK) -> list[dict]:
    """Our sent writes `{object, at, before, after}` and the platform's `recorded` events (same keys), at or after `since`,
    oldest first, each with `source` own or external. Values are numbers rounded to the cent where they are numbers."""
    mine = [{**c, "at": utc(c["at"]), "before": _num(c.get("before")), "after": _num(c.get("after")), "source": OWN} for c in own]
    ext = []
    for c in recorded:
        at, after = utc(c["at"]), _num(c.get("after"))
        if not any(o["object"] == c["object"] and o["after"] == after and abs(o["at"] - at) <= slack for o in mine):
            ext.append({**c, "at": at, "before": _num(c.get("before")), "after": after, "source": EXTERNAL})
    return sorted((c for c in mine + ext if c["at"] >= since), key=lambda c: c["at"])


def history_missing(objects: set, covered: set) -> int | None:
    """None when the platform's history was read in full for every object at least once; else how many were never read."""
    gone = len(set(objects) - set(covered))
    return None if not gone else gone


def after_start(at: datetime, hours: float) -> date:
    return (utc(at) + timedelta(hours=hours)).date() + timedelta(1)


def effect_windows(first: datetime, last: datetime, hours: float, days: int) -> tuple[tuple[date, date], tuple[date, date]]:
    """((before start, end), (after start, end)) of changes first..last."""
    b_end = utc(first).date() - timedelta(2)
    a_start = after_start(last, hours)
    return (b_end - timedelta(days - 1), b_end), (a_start, a_start + timedelta(days - 1))


def episodes(found: list[dict], hours: float, days: int) -> list[dict]:
    """One per object and chain of its changes (`found` oldest first)."""
    by_object: dict[tuple, list] = {}
    for c in found:
        if c.get("object"):
            by_object.setdefault(tuple(c["object"]), []).append(c)
    out = []
    for obj, cs in by_object.items():
        ep = None
        for c in cs:
            at = utc(c["at"])
            if ep is None or at.date() > ep["after"][1]:
                ep = {"object": obj, "parents": [], "changes": [], "first": at}
                out.append(ep)
            ep["changes"].append(c)
            ep["parents"] = ep["parents"] or [tuple(p) for p in c.get("parents", [])]
            ep["before"], ep["after"] = effect_windows(ep["first"], at, hours, days)
    return out


def overlaps(ep: dict, found: list[dict]) -> tuple[int, int]:
    """(changes to ep's parents, changes inside ep) whose UTC day falls in ep's span, before start to after end."""
    lo, hi = ep["before"][0], ep["after"][1]
    parents = {tuple(p) for p in ep["parents"]}
    anc = inner = 0
    for c in found:
        obj = tuple(c["object"]) if c.get("object") else None
        if not obj or not lo <= utc(c["at"]).date() <= hi:
            continue
        anc += obj in parents
        inner += ep["object"] in {tuple(p) for p in c.get("parents", [])}
    return anc, inner


def beyond_noise(before: list[float], after: list[float], k: float) -> tuple[float | None, bool | None]:
    """(t, beyond) of two windows' daily values: t = the difference of the means over the standard error of the difference.
    Fewer than two days in a window: (None, None). No spread at all: (None, True) when the means differ, else (None, None)."""
    if min(len(before), len(after)) < 2:
        return None, None
    diff = statistics.fmean(after) - statistics.fmean(before)
    se = math.sqrt(statistics.variance(before) / len(before) + statistics.variance(after) / len(after))
    if not se:
        return None, (True if abs(diff) > 1e-9 else None)
    t = diff / se
    return round(t, 6), abs(t) >= k
