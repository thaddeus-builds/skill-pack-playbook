"""The `ads.changes/1` file: what changed on the ad platform, for the pack that sets the platform's numbers against the company's own (a change is not an effect). No
database, no file, no clock, no platform: the pack hands over what its pulls and its daily page recorded and writes the body `compute()` returns.

Two kinds of change, each with a stable `change_id` (a later file repeats it and never alters it). Times are compared as moments, whatever zone they are given in:

  * seen by the pulls: a campaign's or ad set's budget or delivery status that differs from what the pull before said, `by_kind` unknown (the pulls cannot tell a person's
    edit from the platform's rule). The first time an entity is seen is a baseline, not a change, and so is a pull the window begins after;
  * done by a person and reported on the daily page (`kit.daily`'s items, answered `done`): `by_kind` person, `by` the reporter. A budget move says its budget before and
    after as the allocation advised it that day or the latest day before (the advice record), the other items say what was done by the item's own words.

    {body {producer, produced_at, changes [{change_id, at, platform, entity_kind, entity_id, what, by_kind, before?, after?, by?, account?}]}, count, observed, reported,
     warnings, warning_codes}

An empty list is a document too (no change seen is also a fact). An absent optional key means unknown, never null and never an empty string. Writing is the pack's:
`kit.contracts.write("ads.changes", 1, doc["body"], out)` checks the body as a reader would and writes it once. `produced_at` is the given day at 00:00 UTC, so the same
document on the same day is the same bytes. The contract is a draft (ROADMAP X11) until a first measurement reads it.

From the video-ads skill pack (`scripts/export_changes.py` `observed`, `reported` and `export`; its cases are this module's test, over a synthetic fixture).

Test: kit/tests/test_export_changes.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from kit.contract import SkillPackError
from kit.messages import coded, msg

KIND, VERSION = "ads.changes", 1
WATCHED = (("status", 3), ("daily_budget", 4), ("lifetime_budget", 5))          # what a pull is compared on, and where it stands in a history row
TIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}(:?[0-9]{2})?)$")
ASKED = "asked the maker for creatives"


@dataclass
class Source:
    """What the pack hands over.

    history    [(level, entity_id, as_of, delivery_status, daily_budget, lifetime_budget)], any order: one row for each pull of an entity that changed (or each pull);
               `as_of` is ISO 8601 with its zone; the three values may be None
    answers    [{seq, day, item, answer, at, by?}]: what people said about the daily page's items, oldest first (`kit.daily`'s ids); only `done` is a change
    advised    [{day, moves [{campaign, from, to}]}]: the allocation's advice of each day, for the budget before and after of a `move:` item
    producer   the pack's CLI word, written into the file
    platform   the platform id, as in ads.creatives/1
    subject    the entity id of an account-wide change (a market, an account)
    account    optional: the platform account, written on every change
    """
    history: list
    answers: list
    advised: list
    producer: str
    platform: str
    subject: str
    account: str | None = None
    warnings: list = field(default_factory=list)


def _bad(part: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("compute_input_invalid", f"the pack's tables give {part} {problem}", part=part, problem=problem))


def _word(part: str, v) -> None:
    if not isinstance(v, str) or not v.strip():
        raise _bad(part, f"{v!r}, which is not a word")


def _time(part: str, v) -> None:
    if not isinstance(v, str) or not TIME.match(v):
        raise _bad(part, f"{v!r}, which is not a time (ISO 8601 with its zone)")


def _day(part: str, v) -> date:
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        raise _bad(part, f"{v!r}, which is not a day (YYYY-MM-DD)") from None


def check(src: Source, day: str, days: int) -> None:
    """Refuse a `Source` the file cannot be written from, naming the part (`compute_input_invalid`)."""
    _day("day", day)
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise _bad("days", f"{days!r}, which is not a number of days of 1 or more")
    for name in ("producer", "platform", "subject"):
        _word(name, getattr(src, name))
    if src.account is not None:
        _word("account", src.account)
    for part, v in (("history", src.history), ("answers", src.answers), ("advised", src.advised)):
        if not isinstance(v, (list, tuple)):
            raise _bad(part, "that are not a list")
    for i, h in enumerate(src.history):
        if not isinstance(h, (list, tuple)) or len(h) != 6:
            raise _bad(f"history[{i}]", "that is not (level, entity_id, as_of, delivery_status, daily_budget, lifetime_budget)")
        _word(f"history[{i}].level", h[0])
        _word(f"history[{i}].entity_id", h[1])
        _time(f"history[{i}].as_of", h[2])
        if h[3] is not None and not isinstance(h[3], str):
            raise _bad(f"history[{i}].delivery_status", f"{h[3]!r}, which is not text or None")
        for j, name in ((4, "daily_budget"), (5, "lifetime_budget")):
            if h[j] is not None and (isinstance(h[j], bool) or not isinstance(h[j], (int, float, str))):
                raise _bad(f"history[{i}].{name}", f"{h[j]!r}, which is not a number or None")
    seqs: dict = {}
    for i, a in enumerate(src.answers):
        part = f"answers[{i}]"
        if not isinstance(a, dict):
            raise _bad(part, "that is not a dict")
        absent = [c for c in ("seq", "day", "item", "answer", "at") if a.get(c) is None]
        if absent:
            raise _bad(part, f"without {', '.join(absent)}")
        _word(f"{part}.item", a["item"])
        _word(f"{part}.answer", a["answer"])
        _time(f"{part}.at", a["at"])
        _day(f"{part}.day", a["day"])
        if a["seq"] in seqs:
            raise _bad(f"{part}.seq", f"{a['seq']!r}, which answers[{seqs[a['seq']]}] has too: a change is written once")
        seqs[a["seq"]] = i
        if a.get("by") is not None:
            _word(f"{part}.by", a["by"])
    for i, rec in enumerate(src.advised):
        if not isinstance(rec, dict) or "day" not in rec or not isinstance(rec.get("moves"), list):
            raise _bad(f"advised[{i}]", "that is not {day, moves [..]}")
        _day(f"advised[{i}].day", rec["day"])
        for m in rec["moves"]:
            if not isinstance(m, dict) or not {"campaign", "from", "to"} <= set(m):
                raise _bad(f"advised[{i}].moves", "that are not {campaign, from, to}")


def _instant(s: str) -> datetime:
    """The moment a checked time names, so two zones compare as what they are."""
    return datetime.fromisoformat(s.replace(" ", "T", 1))


def _num(v) -> str:
    return str(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else str(v)


def observed(history: list, since: datetime, platform: str) -> list[dict]:
    """Changes between consecutive pulls of one entity (`history` as in `Source`, any order); the first pull of an entity is a baseline."""
    out, last = [], {}
    for h in sorted(history, key=lambda r: (r[0], r[1], _instant(r[2]))):
        level, eid, at = h[0], h[1], h[2]
        key = (level, eid)
        if key in last:
            for what, idx in WATCHED:
                a, b = last[key][idx], h[idx]
                if a != b and _instant(at) >= since:
                    c = {"change_id": f"{level}:{eid}:{at}:{what}", "at": at, "platform": platform, "entity_kind": level, "entity_id": eid, "what": what, "by_kind": "unknown"}
                    if a is not None:
                        c["before"] = _num(a)
                    if b is not None:
                        c["after"] = _num(b)
                    out.append(c)
        last[key] = h
    return out


def reported(answers: list, advised: list, subject: str, platform: str, since: datetime) -> list[dict]:
    """What a person said they did (`done`): one change per answer, its budget move taken from the advice recorded for the same campaign when there is one."""
    moves = {}
    for rec in advised:
        for m in rec["moves"]:
            moves[(m["campaign"], rec["day"])] = m
    out = []
    for r in answers:
        if r["answer"] != "done" or _instant(r["at"]) < since:
            continue
        kind, _, rest = r["item"].partition(":")
        entity_kind, entity_id, what, before, after = "account", subject, r["item"], None, None
        if kind == "move":
            entity_kind, entity_id, what = "campaign", rest, "daily_budget"
            m = next((v for (c, d), v in sorted(moves.items(), reverse=True) if c == rest and d <= r["day"]), None)
            if m:
                before, after = _num(m["from"]), _num(m["to"])
        elif kind == "campaign":
            action, _, cid = rest.partition(":")
            entity_kind, entity_id, what = "campaign", cid, action
        elif kind == "audit":
            what = rest
        elif r["item"] == "request:creatives":
            what = ASKED
        c = {"change_id": f"action:{r['seq']}", "at": r["at"], "platform": platform, "entity_kind": entity_kind, "entity_id": entity_id, "what": what, "by_kind": "person"}
        if before is not None:
            c["before"], c["after"] = before, after
        if r.get("by"):
            c["by"] = r["by"]
        out.append(c)
    return out


def compute(src: Source, day: str, *, days: int = 90) -> dict:
    """The body of the file for `day` (ISO date): the changes of the last `days` days, oldest first."""
    check(src, day, days)
    since = datetime.combine(date.fromisoformat(day) - timedelta(days=days), datetime.min.time(), tzinfo=timezone.utc)
    seen = observed(list(src.history), since, src.platform)
    said = reported(list(src.answers), list(src.advised), src.subject, src.platform, since)
    changes = sorted(seen + said, key=lambda c: (_instant(c["at"]), c["change_id"]))
    if src.account:
        for c in changes:
            c["account"] = src.account
    return {"body": {"producer": src.producer, "produced_at": f"{day}T00:00:00Z", "changes": changes}, "count": len(changes), "observed": len(seen), "reported": len(said),
            **coded("warnings", list(src.warnings))}
