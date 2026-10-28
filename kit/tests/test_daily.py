#!/usr/bin/env python3
"""kit.daily: the day's advice composed from planted documents.

  1. One item per campaign proposal, audit finding and budget move under a stable id; an ended campaign gives none; the order is severity, layer, id; an
     item keeps its id across two runs; every item names the command that reports back.
  2. A move has its sentence, evidence, steps and doubts including the platform's limit; a campaign proposal and an audit finding keep the sentence they came with.
  3. The request for creatives: its number, or the reason there is none, or only a note when there is no month target.
  4. The latest answer sits on its item; an answered item that no longer comes up is `solved`.
  5. A thing the composer does not know is left out, not an error: a doubt name, a severity, a pacing warning, a missing proposal.
  6. daily.py's msg() calls are closed over kit/message_codes.d/daily.tsv.
"""

import copy
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import daily, messages  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402


def coded(code, **params):
    return {"message": code, "message_code": {"code": code, "params": params}}


CAMP = {"as_of": "2026-10-21", "currency": "USD", "campaigns": [
    {"campaign": "111", "name": "Fatigued <b>one</b>", "state": "fatigued", "status": "ACTIVE", "proposals": [
        {"action": "rest_creatives", "evidence": "x", **coded("campaign_rest_creatives", declining=4, now=0.39, peak=0.64)}]},
    {"campaign": "222", "name": "Old", "state": "ended", "status": "PAUSED", "proposals": [
        {"action": "add_creative", "evidence": "x", **coded("campaign_add_creative", mature=2)}]},
    {"campaign": "333", "name": "Quiet", "state": "steady", "status": "ACTIVE", "proposals": []}]}
AUDIT = {"findings": [{"finding": "audit_issues", "severity": "high", **coded("audit_issues", ads=2, spend=3.0, days=14, examples=[]),
                       "steps": [{"text": "look", **coded("audit_issues_where", count=2)}]}]}
MOVE = {"campaign": "111", "name": "Fatigued <b>one</b>", "from": 400.0, "to": 355.0, "change": -0.1125, "cap": 0.1, "fast": False, "z": -2.9, "level": 2.1,
        "marginal": {"value": 1.49, "se": 0.47, "low": 1.01, "high": 1.96}, "binding": "min_daily_budget", "doubt": ["no_counterfactual", "elasticity_pooled"]}
ALLOC = {"proposal": {"moves": [MOVE], "held": [{"campaign": "333", "why": "no_evidence"}], "followed": {"taken": 1, "not_taken": 2, "open": 3}}}
PACING = {"warnings": [], "warning_codes": [], "creative_demand": {"n": 10, "batch_size": 5, "capacity": 12, "money": 1000.0, "committed": 100.0, "unit_cost": 80.0, "basis": "measured",
          "batches": [{"size": 5, "daily_budget": 40.0}, {"size": 5, "daily_budget": 40.0}], "constraints": []}}


def build(camp=CAMP, audit=AUDIT, alloc=ALLOC, pacing=PACING, answers=None):
    return daily.build("TW", "ads", camp, audit, alloc, pacing, answers or {})


def test_items() -> None:
    print("[1] one item per finding, under a stable id")
    d = build()
    ids = [i["id"] for i in d["items"]]
    check("a proposal, a finding, a move and the request; the ended campaign gives none",
          set(ids) == {"campaign:rest_creatives:111", "audit:audit_issues", "move:111", "request:creatives"}, ids)
    check("sorted by severity, then layer, then id", ids == ["audit:audit_issues", "request:creatives", "campaign:rest_creatives:111", "move:111"], ids)
    check("the same documents give the same ids and the same document", [i["id"] for i in build()["items"]] == ids and build() == d)
    check("every item names the command that reports back",
          all(i["report"] == f"ads import action --market TW --item {i['id']} --answer done" for i in d["items"]))
    check("the summary counts severities and answers", d["summary"] == {"items": 4, "high": 1, "medium": 2, "info": 1, "answered": 0, "solved": 0}, d["summary"])
    check("what became of the earlier moves, and how many campaigns stay put", d["followed"] == {"taken": 1, "not_taken": 2, "open": 3} and d["held"] == 1)
    check("the followed counts have their coded sentence", d["followed_text"]["message_code"] == {"code": "daily_followed", "params": {"taken": 1, "not_taken": 2, "open": 3}})


def test_sentences() -> None:
    print("[2] each item's sentence")
    it = {i["id"]: i for i in build()["items"]}
    check("a campaign proposal keeps the sentence it came with", it["campaign:rest_creatives:111"]["message_code"]["code"] == "campaign_rest_creatives"
          and it["campaign:rest_creatives:111"]["severity"] == "medium" and it["campaign:rest_creatives:111"]["subject"]["state"] == "fatigued")
    check("an audit finding keeps its sentence and its steps", it["audit:audit_issues"]["message_code"]["code"] == "audit_issues"
          and [s["message_code"]["code"] for s in it["audit:audit_issues"]["steps"]] == ["audit_issues_where"] and it["audit:audit_issues"]["severity"] == "high")
    mv = it["move:111"]
    check("a move has its sentence, evidence, two steps, and doubts including the platform's limit",
          mv["message_code"]["code"] == "daily_move" and mv["evidence"]["message_code"]["code"] == "daily_move_evidence" and len(mv["steps"]) == 2
          and [x["message_code"]["code"] for x in mv["doubt"]] == ["daily_doubt_no_counterfactual", "daily_doubt_elasticity_pooled", "daily_limit_min_daily_budget"], mv["doubt"])
    check("a move that is not fast is info, a fast one medium", mv["severity"] == "info"
          and {i["id"]: i for i in build(alloc={"proposal": {"moves": [{**MOVE, "fast": True}]}})["items"]}["move:111"]["severity"] == "medium")


def test_request() -> None:
    print("[3] the request for creatives")
    r = {i["id"]: i for i in build()["items"]}["request:creatives"]
    check("its number and its batches in the evidence", r["message_code"]["code"] == "daily_request" and r["message_code"]["params"] == {"n": 10, "batches": 2, "size": 5}
          and "40.0" in r["evidence"]["message_code"]["params"]["per"] and len(r["steps"]) == 2, r["message_code"])
    for constraint, code in (("money_committed", "daily_request_none_committed"), ("no_exploration_money", "daily_request_none_money"),
                             ("cost_unknown", "daily_request_none_cost"), ("limit_binds", "daily_request_none_limit"), ("something_new", "daily_request_none")):
        none = {**PACING, "creative_demand": {**PACING["creative_demand"], "n": 0, "constraints": [constraint]}}
        got = {i["id"]: i for i in build(pacing=none)["items"]}["request:creatives"]
        check(f"no request, {constraint}: the reason is its sentence", got["message_code"]["code"] == code and got["severity"] == "info" and got["subject"] == {"n": 0}, got["message_code"])
    nt = {"warnings": ["no target"], "warning_codes": [{"code": "pacing_no_target", "params": {"month": "2026-10"}}]}
    d = build(pacing=nt)
    check("no month target: no request item, the note says why", "request:creatives" not in [i["id"] for i in d["items"]]
          and d["note_codes"][0]["code"] == "pacing_no_target" and d["notes"] == ["no target"])


def test_answers() -> None:
    print("[4] the answers")
    ans = {"audit:audit_issues": {"answer": "done", "day": "2026-10-20", "note": "fixed", "by": "a1", "extra": 1},
           "move:999": {"answer": "declined", "day": "2026-10-19", "note": "", "by": "a1"}}
    d = build(answers=ans)
    got = {i["id"]: i for i in d["items"]}
    check("the latest answer sits on its item, with its four fields", got["audit:audit_issues"]["last"] == {"answer": "done", "day": "2026-10-20", "note": "fixed", "by": "a1"}
          and got["move:111"]["last"] is None)
    check("an answer for an item that no longer comes up is solved", d["solved"] == [{"item": "move:999", "answer": "declined", "day": "2026-10-19", "note": ""}]
          and d["summary"]["answered"] == 1 and d["summary"]["solved"] == 1, d["summary"])
    check("the answers given are not changed", ans["move:999"] == {"answer": "declined", "day": "2026-10-19", "note": "", "by": "a1"})


def test_unknown() -> None:
    print("[5] what the composer does not know is left out")
    odd = copy.deepcopy(ALLOC)
    odd["proposal"]["moves"][0]["doubt"] = ["no_counterfactual", "a_doubt_from_the_future"]
    odd["proposal"]["moves"][0]["binding"] = "a_limit_from_the_future"
    mv = {i["id"]: i for i in build(alloc=odd)["items"]}["move:111"]
    check("an unknown doubt or limit is dropped, the known one stays", [x["message_code"]["code"] for x in mv["doubt"]] == ["daily_doubt_no_counterfactual"], mv["doubt"])
    odd_audit = {"findings": [{**AUDIT["findings"][0], "severity": "urgent"}]}
    d = build(audit=odd_audit)
    check("an unknown severity is info", {i["id"]: i for i in d["items"]}["audit:audit_issues"]["severity"] == "info" and d["summary"]["info"] == 2, d["summary"])
    warn = {"warnings": ["a", "b"], "warning_codes": [{"code": "pacing_demand_unknown", "params": {}}, {"code": "pacing_other", "params": {}}]}
    d = build(pacing=warn)
    check("only the two pacing notes this page cares about are kept", d["notes"] == ["a"] and [c["code"] for c in d["note_codes"]] == ["pacing_demand_unknown"], d["notes"])
    d = build(alloc={}, pacing={})
    check("no allocation proposal and no pacing document: no moves, no request, nothing raised",
          [i["id"] for i in d["items"]] == ["audit:audit_issues", "campaign:rest_creatives:111"] and d["followed"] == {"taken": 0, "not_taken": 0, "open": 0} and d["held"] == 0)
    check("a campaign in a state the composer does not know is info",
          {i["id"]: i for i in build(camp={**CAMP, "campaigns": [{**CAMP["campaigns"][0], "state": "brand_new"}]})["items"]}["campaign:rest_creatives:111"]["severity"] == "info")


def test_closure() -> None:
    print("[6] daily.py's codes are closed over its fragment")
    reg = messages.registry()
    own = {c: r for c, r in reg.items() if Path(r["file"]).name == "daily.tsv"}
    check("the fragment holds daily_* codes only", own and all(c.startswith("daily_") for c in own), sorted(own))
    check("no meaning names a platform or a pack", not [c for c, r in own.items() if any(w in (r["meaning_en"] + r["meaning_zh"]).lower() for w in ("smartly", "meta", "adcut", "vads", "tiktok"))])
    probs = messages.check_registry_closed(_shop.KIT, ["daily.py"], own, strict_kit=True)
    check("every msg() in daily.py is literal, registered with exact params, and every daily.tsv code is emitted", probs == [], probs)


def main() -> int:
    _shop.use()
    for fn in (test_items, test_sentences, test_request, test_answers, test_unknown, test_closure):
        fn()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
