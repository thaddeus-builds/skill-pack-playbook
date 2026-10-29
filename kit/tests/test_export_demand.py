#!/usr/bin/env python3
"""kit.export_demand: the `ads.demand/1` body from the demand document, over the hand-made account of test_compute_demand (invented DEMO ids, invented numbers).
The cases are the video-ads skill pack's `export demand`: one request with the count, the day it is needed by (the plan's first day plus the lead time), the window of a
verdict, the cost of one verdict in CNY only when the money is CNY, the batches in the note; nothing to ask for is said and writes nothing; the body passes the
playbook's schema and is written once.
"""

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
import test_compute_demand as base  # noqa: E402
from kit import compute_demand as cd, compute_life as cl, contracts, export_demand as ed, messages  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

DAY = "2026-10-29"


def codes(doc) -> list:
    return [w["code"] for w in doc["warning_codes"]]


def refused(src, day=DAY):
    try:
        ed.compute(src, day)
    except Exception as e:  # noqa: BLE001
        f = messages.failure(e)
        return f["code"], f["params"].get("part")
    return None, None


def main() -> int:
    _shop.use()
    _shop.data_dir()
    k = base.thresholds()
    cr = base.account()
    pa = base.pacing(cr, k)
    plan, paid = pa["plan"], pa["creative_wallets"]
    doc = cd.compute(cd.Source(cl.Source(cr), plan, paid=paid), k)
    blk = doc["demand"]
    start = plan["day"]["day"]
    src = ed.Source(doc, producer="demo", platform="meta", format="video_9x16", start=start, subject="HK", currency="HKD")

    print("[1] the request follows the demand block")
    out = ed.compute(src, DAY)
    body = out["body"]
    req = body["requests"][0]
    check("one request, with the count of the block, its own id and the platform and format the pack named",
          len(body["requests"]) == 1 and req["count"] == blk["n"] == 5 and req["request_id"] == f"demand-HK-{DAY}" and req["platform"] == "meta" and req["format"] == "video_9x16", req)
    check("needed by the plan's first day plus the lead time, rounded up",
          req["needed_by"] == (date.fromisoformat(start) + timedelta(days=math.ceil(blk["lead_days"]))).isoformat() == out["needed_by"] and blk["lead_days"] == 14.0, req["needed_by"])
    check("the window of a verdict is the days it takes, at least 1, whole", req["window_days"] == max(1, round(blk["days_to_verdict"])) and isinstance(req["window_days"], int), req)
    odd = ed.compute(ed.Source({**doc, "demand": {**blk, "lead_days": 13.2, "days_to_verdict": 0.2}}, "demo", "meta", "video_9x16", start=start), DAY)["body"]["requests"][0]
    check("a lead time of 13.2 days is 14 (rounded up, a request is never late) and a verdict in under a day is a window of 1",
          odd["needed_by"] == (date.fromisoformat(start) + timedelta(days=14)).isoformat() and odd["window_days"] == 1, odd)
    batches = ", ".join(f"{b['size']} at {b['daily_budget']} a day" for b in blk["batches"])
    check("the note names the batches, the cost of one verdict in the client's money and says it is a count, not a budget",
          req["note"] == f"in 1 batch(es) of at most 5: {batches}; cost of one verdict {blk['unit_cost']} HKD (measured, {blk['verdicts']} verdicts). A count, not a budget.", req["note"])
    check("the cost of a verdict is written in the client's money with its currency, as measured: no converted figure, no CNY field", req["unit_cost"] == blk["unit_cost"] > 0
          and req["currency"] == "HKD" and not [x for x in req if x.endswith("_cny")], req)
    check("the producer is the pack's and produced_at is the day at 00:00 UTC", body["producer"] == "demo" and body["produced_at"] == f"{DAY}T00:00:00Z" and set(body) == {"producer", "produced_at", "requests"})
    check("the document is plain data and has no warning", json.dumps(out) and out["warnings"] == [] and out["count"] == 5 and out["request_id"] == req["request_id"])
    cny = ed.compute(ed.Source(doc, "demo", "qianchuan", "video_9x16", start=start, currency="CNY"), DAY)["body"]["requests"][0]
    check("a client whose money is CNY gets the same two fields, and a request id without a market from the platform", cny["unit_cost"] == blk["unit_cost"] > 0 and cny["currency"] == "CNY"
          and cny["request_id"] == f"demand-qianchuan-{DAY}", cny)
    unk = ed.compute(ed.Source(doc, "demo", "meta", "video_9x16", start=start), DAY)["body"]["requests"][0]
    check("a money that is not known is not named in the note, leaves no double space, and the figure is not written without its currency",
          f"cost of one verdict {blk['unit_cost']} (measured, 9 verdicts). A count" in unk["note"] and "unit_cost" not in unk and "currency" not in unk, unk)
    more = ed.compute(ed.Source(doc, "demo", "meta", "image_1x1", start=start, product="DEMO-SKU", slot="feed"), DAY)["body"]["requests"][0]
    check("the product and the placement are written when the pack names them, and only then", more["product"] == "DEMO-SKU" and more["slot"] == "feed" and "product" not in req and "slot" not in req)

    print("[2] the body is a valid ads.demand/1, written once")
    check("it fits the playbook's schema", contracts.problems(ed.KIND, ed.VERSION, body) == [] and contracts.problems(ed.KIND, ed.VERSION, cny) != [], contracts.problems(ed.KIND, ed.VERSION, body))
    lower = {**body, "requests": [{**req, "currency": "hkd"}]}
    check("the schema holds the currency to three capitals, and has no `_cny` field any more", contracts.problems(ed.KIND, ed.VERSION, lower) != []
          and "unit_cost_cny" not in contracts.schema(ed.KIND, ed.VERSION)["properties"]["requests"]["items"]["properties"], contracts.problems(ed.KIND, ed.VERSION, lower))
    out_dir = Path(tmp_dir("export-demand-"))
    path = contracts.write(ed.KIND, ed.VERSION, body, out_dir / "demand.json")
    again = ed.compute(src, DAY)["body"]
    check("the same document on the same day is the same bytes: writing it again is a no-op", contracts.render(ed.KIND, ed.VERSION, again) == contracts.render(ed.KIND, ed.VERSION, body)
          and contracts.write(ed.KIND, ed.VERSION, again, path) == path)
    read = contracts.read(path, ed.KIND, ed.VERSION, "demand-test")
    check("a reader gets the request back", read.body["requests"][0]["count"] == 5 and read.body["requests"][0]["needed_by"] == req["needed_by"], read.body)
    nxt = ed.compute(src, "2026-10-30")["body"]
    try:
        contracts.write(ed.KIND, ed.VERSION, nxt, path)
        other = None
    except Exception as e:  # noqa: BLE001
        other = messages.failure(e)["code"]
    check("the next day's document is other bytes (its request id has the day): under the same name it is refused, and the file is untouched", other == "exchange_would_overwrite"
          and path.read_bytes() == contracts.render(ed.KIND, ed.VERSION, body), other)

    print("[3] nothing to ask for is said, and nothing is written")
    none = ed.compute(ed.Source(cd.compute(cd.Source(cl.Source(cr), None), k), "demo", "meta", "video_9x16"), DAY)
    check("no plan (no spend target): no body, no count, and the code says why", none["body"] is None and none["count"] == 0 and codes(none) == ["demand_nothing_to_ask"]
          and none["warning_codes"][0]["params"]["why"] == "no_creative_demand", none)
    low = cd.compute(cd.Source(cl.Source(cr), plan, paid=paid, limits={"min": 5000.0}), k)
    lo = ed.compute(ed.Source(low, "demo", "meta", "video_9x16", start=start), DAY)
    check("a platform minimum above what the money carries: a count of 0, no body, and the constraint named", lo["body"] is None and low["demand"]["n"] == 0
          and codes(lo) == ["demand_nothing_to_ask"] and lo["warning_codes"][0]["params"]["why"] == ", ".join(low["demand"]["constraints"]) and "limit_binds" in low["demand"]["constraints"], lo["warning_codes"])
    young = {"NEW": cr["NEW"]}
    yp = base.pacing(young, k)
    yd = cd.compute(cd.Source(cl.Source(young), yp["plan"], paid=yp["creative_wallets"]), k)
    yo = ed.compute(ed.Source(yd, "demo", "meta", "video_9x16"), DAY)
    check("no cost of a verdict is known yet: no body, and the reason is the block's own constraint", yo["body"] is None and yd["demand"]["n"] is None
          and yo["warning_codes"][0]["params"]["why"] == "cost_unknown" == ", ".join(yd["demand"]["constraints"]), yo["warning_codes"])
    unconstrained = {**yd, "demand": {**yd["demand"], "constraints": []}}
    check("with no constraint named the document's own warning explains it", ed.compute(ed.Source(unconstrained, "demo", "meta", "video_9x16"), DAY)["warning_codes"][0]["params"]["why"]
          == "pacing_demand_unknown", yd["warning_codes"])
    check("nothing to ask for needs no start day", ed.asks(ed.Source(none_doc := {"month": None, "demand": None}, "d", "p", "f")) is False and none_doc["demand"] is None)

    print("[4] a Source the file cannot be written from is refused, naming the part")
    thin = {**doc, "demand": {x: v for x, v in blk.items() if x != "lead_days"}}
    bad = {"a document that is not the demand document": ("document", ed.Source({"month": "2026-10"}, "demo", "meta", "video_9x16", start=start)),
           "a block that is not a block": ("document.demand", ed.Source({"demand": [1]}, "demo", "meta", "video_9x16", start=start)),
           "a block without its lead time": ("document.demand", ed.Source(thin, "demo", "meta", "video_9x16", start=start)),
           "no start day while there is something to ask for": ("start", ed.Source(doc, "demo", "meta", "video_9x16")),
           "a start that is not a day": ("start", ed.Source(doc, "demo", "meta", "video_9x16", start="soon")),
           "no producer": ("producer", ed.Source(doc, "", "meta", "video_9x16", start=start)),
           "no platform": ("platform", ed.Source(doc, "demo", None, "video_9x16", start=start)),
           "no format": ("format", ed.Source(doc, "demo", "meta", " ", start=start)),
           "a currency that is a number": ("currency", ed.Source(doc, "demo", "meta", "video_9x16", start=start, currency=1)),
           "a currency in lower case": ("currency", ed.Source(doc, "demo", "meta", "video_9x16", start=start, currency="hkd")),
           "a currency of four letters": ("currency", ed.Source(doc, "demo", "meta", "video_9x16", start=start, currency="HKDD")),
           "a subject that is empty": ("subject", ed.Source(doc, "demo", "meta", "video_9x16", start=start, subject=""))}
    got = {name: refused(s) for name, (_, s) in bad.items()}
    check("each is compute_input_invalid, naming its part", all(c == "compute_input_invalid" for c, _ in got.values()) and [p for _, p in got.values()] == [x for x, _ in bad.values()], got)
    check("a day that is not a day is refused as the day", refused(src, "today") == ("compute_input_invalid", "day"))
    lacks = [x for x in ed.NEEDED if x != "n" and refused(ed.Source({**doc, "demand": {y: v for y, v in blk.items() if y != x}}, "demo", "meta", "video_9x16", start=start))[1] != "document.demand"]
    check("every part a request is written from is named when missing", lacks == [], lacks)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
