"""The `ads.demand/1` file: the demand document's request for the makers. It is `kit.compute_demand`'s `demand` block as the body of a contract file, never a new
rule: one request with the count (the number the exploration money can carry to a verdict, in whole batches), the day it is needed by (the first day of the plan
plus the measured lead time), the window of a verdict in days, the cost of judging one creative with the currency it is in (`unit_cost` and `currency`, ISO 4217, when the client's money is known; never a converted figure), and the batches with their daily budgets in the note. A request is a number wanted, never a
budget or a promise (the contract's rules). No database, no file, no clock, no platform: the pack hands over the demand document and the words of its platform, and
writes what `compute()` returns.

    {body {producer, produced_at, requests [{request_id, platform, format, count, needed_by, window_days, note, ...}]} | None, count, request_id, needed_by,
     warnings, warning_codes}

`body` is None when there is nothing to ask for (the document has no plan, no cost of a verdict yet, or the exploration money carries no whole batch); the warning
`demand_nothing_to_ask` says why, and no file should be written. Writing is the pack's: `kit.contracts.write("ads.demand", 1, doc["body"], out)` checks the body as a
reader would, writes it once (the same bytes again are a no-op, other bytes under that name are refused). `produced_at` is the given day at 00:00 UTC, so the same
document on the same day is the same bytes. The contract is a draft (ROADMAP X11) until a first maker reads it.

From the video-ads skill pack (`scripts/export_demand.py` `request` and `export`; its cases are this module's test, over a synthetic fixture).

Test: kit/tests/test_export_demand.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from kit.contract import SkillPackError
from kit.messages import coded, msg

KIND, VERSION = "ads.demand", 1
NEEDED = ("n", "batches", "batch_size", "lead_days", "days_to_verdict", "unit_cost", "basis", "verdicts")      # what a request is written from
WHY = ("pacing_demand_unknown",)             # the document's own warnings that explain an empty request


@dataclass
class Source:
    """What the pack hands over.

    document   `kit.compute_demand.compute`'s document: `{month, demand, warnings, warning_codes}`
    producer   the pack's CLI word, written into the file
    platform   the platform id the creatives are for, as in ads.creatives/1
    format     the creative's format in the operator's words (for example video_9x16)
    start      the first day of the plan, or the day after the last day read: the lead time counts from it (needed when there is something to ask for)
    subject    what the request is about (a market, a platform): part of its id; default the platform
    currency   the client's money (ISO 4217, three capitals), or None when unknown: the cost of a verdict is written with it, and not at all without it
    product    optional: the sku the creatives are for
    slot       optional: the placement they are for
    """
    document: dict
    producer: str
    platform: str
    format: str
    start: str | None = None
    subject: str | None = None
    currency: str | None = None
    product: str | None = None
    slot: str | None = None


def _bad(part: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("compute_input_invalid", f"the pack's tables give {part} {problem}", part=part, problem=problem))


def _day(part: str, value) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise _bad(part, f"{value!r}, which is not a day (YYYY-MM-DD)") from None


def asks(src: Source) -> bool:
    """Whether the document has something to ask for (a count of 1 or more)."""
    block = src.document.get("demand") if isinstance(src.document, dict) else None
    return isinstance(block, dict) and bool(block.get("n"))


def check(src: Source, day: str) -> None:
    """Refuse a `Source` the file cannot be written from, naming the part (`compute_input_invalid`)."""
    _day("day", day)
    if not isinstance(src.document, dict) or "demand" not in src.document:
        raise _bad("document", "that is not the demand document (a dict with a demand block, or None)")
    for name in ("producer", "platform", "format"):
        v = getattr(src, name)
        if not isinstance(v, str) or not v.strip():
            raise _bad(name, f"{v!r}, which is not a word")
    for name in ("subject", "currency", "product", "slot"):
        v = getattr(src, name)
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise _bad(name, f"{v!r}, which is not a word or None")
    if src.currency is not None and not (len(src.currency) == 3 and src.currency.isascii() and src.currency.isalpha() and src.currency.isupper()):
        raise _bad("currency", f"{src.currency!r}, which is not an ISO 4217 code (three capitals) or None")
    block = src.document["demand"]
    if block is not None and not isinstance(block, dict):
        raise _bad("document.demand", f"{block!r}, which is not a block (a dict) or None")
    if asks(src):
        absent = [x for x in NEEDED if x not in src.document["demand"]]
        if absent:
            raise _bad("document.demand", f"without {', '.join(absent)}")
        _day("start", src.start)


def compute(src: Source, day: str) -> dict:
    """The body of the file for `day` (ISO date), or None with the reason it is empty."""
    check(src, day)
    subject = src.subject or src.platform
    block = src.document["demand"]
    if not asks(src):
        why = (block or {}).get("constraints") or [c["code"] for c in src.document.get("warning_codes", ()) if c.get("code") in WHY]
        warn = msg("demand_nothing_to_ask", f"{subject}: nothing to ask for now ({', '.join(why) or 'no creative_demand'}): no file was written",
                   subject=subject, why=", ".join(why) or "no_creative_demand")
        return {"body": None, "count": 0, "request_id": None, "needed_by": None, **coded("warnings", [warn])}
    needed = (_day("start", src.start) + timedelta(days=math.ceil(block["lead_days"]))).isoformat()
    per = ", ".join(f"{b['size']} at {b['daily_budget']} a day" for b in block["batches"])
    unit = f"; cost of one verdict {' '.join(str(x) for x in (block['unit_cost'], src.currency) if x)} ({block['basis']}, {block['verdicts']} verdicts)"
    req = {"request_id": f"demand-{subject}-{day}", "platform": src.platform, "format": src.format, "count": block["n"], "needed_by": needed,
           "window_days": max(1, round(block["days_to_verdict"])),
           "note": f"in {len(block['batches'])} batch(es) of at most {block['batch_size']}: {per}{unit}. A count, not a budget."}
    for name in ("product", "slot"):
        if getattr(src, name):
            req[name] = getattr(src, name)
    if src.currency and block.get("unit_cost"):
        req["unit_cost"], req["currency"] = block["unit_cost"], src.currency
    return {"body": {"producer": src.producer, "produced_at": f"{day}T00:00:00Z", "requests": [req]}, "count": req["count"],
            "request_id": req["request_id"], "needed_by": needed, **coded("warnings", [])}
