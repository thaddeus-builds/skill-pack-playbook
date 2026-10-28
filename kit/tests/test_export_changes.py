#!/usr/bin/env python3
"""kit.export_changes: the `ads.changes/1` body from the pulls' history and the daily page's answers (invented DEMO ids, invented numbers). The cases are the video-ads skill
pack's `export changes`: a change between two pulls of one entity (the first pull is a baseline), a person's reported action with the budget before and after the allocation
advised, stable ids, oldest first, an empty list is a document; the body passes the playbook's schema and is written once; a part the file cannot be written from is refused
by name.
"""

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import contracts, export_changes as ec, messages  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

DAY = "2026-10-29"

HISTORY = [("campaign", "C1", "2026-09-20T02:00:00Z", "ACTIVE", 400.0, 0.0), ("campaign", "C1", "2026-08-15T02:00:00Z", "ACTIVE", 350.0, 0.0),
           ("campaign", "C2", "2026-08-15T02:00:00Z", "ACTIVE", 200.0, 0.0), ("campaign", "C2", "2026-10-02T02:00:00Z", "PAUSED", 200.0, 0.0),
           ("adset", "S1", "2026-10-01T00:00:00Z", None, 50.0, None), ("adset", "S1", "2026-10-05T00:00:00Z", None, None, 900.0),
           ("campaign", "C3", "2026-10-20T02:00:00Z", "ACTIVE", 100.0, 0.0)]
ANSWERS = [{"seq": 1, "day": "2026-10-10", "item": "move:C1", "answer": "done", "at": "2026-10-10T09:00:00Z", "by": "Ann"},
           {"seq": 2, "day": "2026-10-10", "item": "move:C2", "answer": "declined", "at": "2026-10-10T09:05:00Z", "by": "Ann"},
           {"seq": 3, "day": "2026-10-11", "item": "campaign:pause:C2", "answer": "done", "at": "2026-10-11T08:00:00Z"},
           {"seq": 4, "day": "2026-10-11", "item": "audit:no_pixel", "answer": "done", "at": "2026-10-11T08:10:00Z", "by": "Bo"},
           {"seq": 5, "day": "2026-10-12", "item": "request:creatives", "answer": "done", "at": "2026-10-12T08:00:00Z", "by": "Ann"},
           {"seq": 6, "day": "2026-10-12", "item": "move:C3", "answer": "later", "at": "2026-10-12T08:30:00Z"},
           {"seq": 7, "day": "2026-10-13", "item": "move:C3", "answer": "done", "at": "2026-10-13T08:30:00Z"}]
ADVISED = [{"day": "2026-10-09", "moves": [{"campaign": "C1", "from": 400.0, "to": 440.5}]}, {"day": "2026-10-10", "moves": [{"campaign": "C1", "from": 440.5, "to": 460.0}]},
           {"day": "2026-10-20", "moves": [{"campaign": "C1", "from": 460.0, "to": 480.0}]}]


def source(**kw):
    base = dict(history=HISTORY, answers=ANSWERS, advised=ADVISED, producer="demo", platform="meta", subject="HK")
    base.update(kw)
    return ec.Source(**base)


def refused(src, day=DAY, days=90):
    try:
        ec.compute(src, day, days=days)
    except Exception as e:  # noqa: BLE001
        f = messages.failure(e)
        return f["code"], f["params"].get("part")
    return None, None


def main() -> int:
    _shop.use()
    _shop.data_dir()

    print("[1] changes seen by the pulls")
    doc = ec.compute(source(answers=[]), DAY)
    ch = {c["change_id"]: c for c in doc["body"]["changes"]}
    check("a budget that differs from the pull before is a change, with its before and after as text, by an unknown hand",
          ch["campaign:C1:2026-09-20T02:00:00Z:daily_budget"] == {"change_id": "campaign:C1:2026-09-20T02:00:00Z:daily_budget", "at": "2026-09-20T02:00:00Z", "platform": "meta",
                                                                   "entity_kind": "campaign", "entity_id": "C1", "what": "daily_budget", "before": "350", "after": "400", "by_kind": "unknown"}, ch)
    check("the first pull of an entity is a baseline, not a change (C3 was seen once)", not any(i.startswith("campaign:C3") for i in ch))
    check("a delivery status that changed is a change", ch["campaign:C2:2026-10-02T02:00:00Z:status"]["before"] == "ACTIVE" and ch["campaign:C2:2026-10-02T02:00:00Z:status"]["after"] == "PAUSED")
    s1 = {i: c for i, c in ch.items() if i.startswith("adset:S1")}
    check("a value that appears or goes away has only the side that is known (an absent key means unknown, never empty)",
          "before" not in s1["adset:S1:2026-10-05T00:00:00Z:lifetime_budget"] and s1["adset:S1:2026-10-05T00:00:00Z:lifetime_budget"]["after"] == "900"
          and "after" not in s1["adset:S1:2026-10-05T00:00:00Z:daily_budget"] and s1["adset:S1:2026-10-05T00:00:00Z:daily_budget"]["before"] == "50", s1)
    check("the history may come in any order: the same changes", {c["change_id"] for c in ec.compute(source(answers=[], history=list(reversed(HISTORY))), DAY)["body"]["changes"]} == set(ch))
    check("the counts say what was seen and what was reported", doc["observed"] == len(ch) == doc["count"] == 4 and doc["reported"] == 0, (doc["observed"], doc["count"]))
    far = ec.compute(source(answers=[]), DAY, days=30)
    check("only the window counts: 30 days back from the 29th leaves the changes after 29 September", {c["change_id"] for c in far["body"]["changes"]} == {i for i, c in ch.items() if c["at"] >= "2026-09-29"}
          and far["observed"] == 3, [c["change_id"] for c in far["body"]["changes"]])
    zone = ec.compute(source(answers=[], history=[("campaign", "Z", "2026-10-01T00:00:00Z", "ACTIVE", 20.0, None), ("campaign", "Z", "2026-10-01T02:00:00+08:00", "ACTIVE", 10.0, None)]), DAY)
    check("a time is a moment whatever its zone: 02:00 at +08:00 is 18:00 UTC the day before, so that pull came first (10 then 20), not second",
          [(c["change_id"], c["before"], c["after"]) for c in zone["body"]["changes"]] == [("campaign:Z:2026-10-01T00:00:00Z:daily_budget", "10", "20")], zone["body"]["changes"])

    edge = ec.compute(source(answers=[], history=[("campaign", "W", "2026-07-01T00:00:00Z", "ACTIVE", 10.0, None), ("campaign", "W", "2026-07-31T07:00:00+08:00", "ACTIVE", 20.0, None),
                                                  ("campaign", "W", "2026-07-31T09:00:00+08:00", "ACTIVE", 30.0, None)]), DAY)
    check("the window begins at 00:00 UTC 90 days back (31 July): a pull at 07:00 +08:00 that day is 23:00 UTC on the 30th and is out, one at 09:00 +08:00 is 01:00 UTC and is in",
          [(c["at"], c["before"], c["after"]) for c in edge["body"]["changes"]] == [("2026-07-31T09:00:00+08:00", "20", "30")], edge["body"]["changes"])

    print("[2] what a person reported")
    full = ec.compute(source(), DAY)
    rep = {c["change_id"]: c for c in full["body"]["changes"] if c["by_kind"] == "person"}
    check("only an answer of done is a change: seq 2 (declined) and 6 (later) are not", set(rep) == {"action:1", "action:3", "action:4", "action:5", "action:7"} and full["reported"] == 5, set(rep))
    check("a budget move says its budget before and after as advised that day (the 10th, not the 9th)", rep["action:1"]["what"] == "daily_budget" and rep["action:1"]["entity_kind"] == "campaign"
          and rep["action:1"]["entity_id"] == "C1" and (rep["action:1"]["before"], rep["action:1"]["after"]) == ("440.5", "460"),
          rep["action:1"])
    check("the person is named when the record has one", rep["action:1"]["by"] == "Ann" and "by" not in rep["action:3"])
    check("a campaign action is the campaign's, in the item's own word", (rep["action:3"]["entity_kind"], rep["action:3"]["entity_id"], rep["action:3"]["what"]) == ("campaign", "C2", "pause"))
    check("an audit finding is the account's (the subject the pack gave)", (rep["action:4"]["entity_kind"], rep["action:4"]["entity_id"], rep["action:4"]["what"]) == ("account", "HK", "no_pixel"))
    check("a request for creatives says so", rep["action:5"]["what"] == ec.ASKED == "asked the maker for creatives" and rep["action:5"]["entity_kind"] == "account")
    check("a move with no advice recorded on or before its day has no before and no after (the advice of the 20th does not count for the 13th)",
          "before" not in rep["action:7"] and "after" not in rep["action:7"] and rep["action:7"]["what"] == "daily_budget", rep["action:7"])
    check("an item the kit does not know is the account's, with the item as its words, never guessed", [c["what"] for c in ec.compute(source(answers=[{**ANSWERS[0], "item": "other:thing"}]), DAY)["body"]["changes"]
          if c["by_kind"] == "person"] == ["other:thing"])
    check("the answers older than the window are left out", ec.compute(source(), DAY, days=17)["reported"] == 2, ec.compute(source(), DAY, days=17)["reported"])

    print("[3] the document: oldest first, stable, valid, written once")
    times = [c["at"] for c in full["body"]["changes"]]
    check("oldest first, ties by id", times == sorted(times) and full["count"] == len(full["body"]["changes"]) == 9, times)
    check("producer and produced_at are the pack's and the day at 00:00 UTC", full["body"]["producer"] == "demo" and full["body"]["produced_at"] == f"{DAY}T00:00:00Z")
    later = ec.compute(source(), "2026-10-30")["body"]
    check("a later document repeats a change with the same id and never alters it", {c["change_id"]: c for c in later["changes"]} == {c["change_id"]: c for c in full["body"]["changes"]}, None)
    check("an account on the source is written on every change, and only then", all(c["account"] == "ACC-1" for c in ec.compute(source(account="ACC-1"), DAY)["body"]["changes"])
          and not any("account" in c for c in full["body"]["changes"]))
    check("it fits the playbook's schema, with and without an account", contracts.problems(ec.KIND, ec.VERSION, full["body"]) == [] and contracts.problems(ec.KIND, ec.VERSION, ec.compute(source(account="ACC-1"), DAY)["body"]) == [])
    out_dir = Path(tmp_dir("export-changes-"))
    path = contracts.write(ec.KIND, ec.VERSION, full["body"], out_dir / "changes.json")
    check("the same document is the same bytes: writing it again is a no-op", contracts.write(ec.KIND, ec.VERSION, ec.compute(source(), DAY)["body"], path) == path)
    check("a reader gets the changes back", len(contracts.read(path, ec.KIND, ec.VERSION, "changes-test").body["changes"]) == 9)
    empty = ec.compute(ec.Source([], [], [], "demo", "meta", "HK"), DAY)
    check("no change seen is also a fact: an empty list is a document, and it is valid", empty["body"]["changes"] == [] and empty["count"] == 0 and contracts.problems(ec.KIND, ec.VERSION, empty["body"]) == [])
    check("the document is plain data and every warning has a code", json.dumps(full) and len(full["warnings"]) == len(full["warning_codes"]))

    print("[4] a Source the file cannot be written from is refused, naming the part")
    bad = {"a history row of five": ("history[0]", source(history=[("campaign", "C", "2026-10-01T00:00:00Z", None, None)])),
           "a history row without an entity": ("history[0].entity_id", source(history=[("campaign", " ", "2026-10-01T00:00:00Z", None, None, None)])),
           "a pull time with no zone": ("history[0].as_of", source(history=[("campaign", "C", "2026-10-01T00:00:00", None, None, None)])),
           "a budget that is a flag": ("history[0].daily_budget", source(history=[("campaign", "C", "2026-10-01T00:00:00Z", None, True, None)])),
           "an answer without its seq": ("answers[0]", source(answers=[{k: v for k, v in ANSWERS[0].items() if k != "seq"}])),
           "an answer time with no zone": ("answers[0].at", source(answers=[{**ANSWERS[0], "at": "2026-10-10"}])),
           "an answer day that is not a day": ("answers[0].day", source(answers=[{**ANSWERS[0], "day": "10 Oct"}])),
           "a seq on two answers": ("answers[1].seq", source(answers=[ANSWERS[0], {**ANSWERS[2], "seq": 1}])),
           "advice that is not {day, moves}": ("advised[0]", source(advised=[{"day": "2026-10-09"}])),
           "a move without its to": ("advised[0].moves", source(advised=[{"day": "2026-10-09", "moves": [{"campaign": "C1", "from": 1}]}])),
           "no producer": ("producer", source(producer="")),
           "no platform": ("platform", source(platform=None)),
           "no subject": ("subject", source(subject=" ")),
           "an account that is a number": ("account", source(account=3)),
           "a history that is not a list": ("history", source(history="x"))}
    got = {name: refused(s) for name, (_, s) in bad.items()}
    check("each is compute_input_invalid, naming its part", all(c == "compute_input_invalid" for c, _ in got.values()) and [p for _, p in got.values()] == [x for x, _ in bad.values()], got)
    check("a day that is not a day, and a window of no days, are refused", refused(source(), "today") == ("compute_input_invalid", "day") and refused(source(), DAY, 0) == ("compute_input_invalid", "days"))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
