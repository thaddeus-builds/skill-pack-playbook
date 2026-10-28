#!/usr/bin/env python3
"""kit.compute_campaign: a pack's tables through the campaign rules, as one document. Every id and number is synthetic (`DEMO`).

  1. The document: every campaign has a state and a reason, read from its days; the budget says where it came from; the window, the
     parameters from the thresholds in effect, and the summary are there; a proposal carries its coded sentence.
  2. The benchmark and the kinds: a campaign is compared with the account's other judged campaigns, or with its kind's when two share one;
     no registry is a coded warning; a pattern that is no regular expression is refused, coded.
  3. The hold: a state among earning, steady, declining, fatigued and unjudged changes only after the last readings agree, and the raw state
     stays in the document; a checkpoint with no complete day is no reading.
  4. `compute()` filters by state and by campaign (id or name) and sorts by the order of the states.
  5. A pack's adapter that omits or mis-shapes a part is refused, coded, naming the part; a market with no complete day is refused.
  6. It reads: the `Source` the adapter handed over is not changed.
  7. The module emits exactly the codes of its message fragment.
"""

import copy
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import compute_campaign as cc  # noqa: E402
from kit import lifecycle, messages  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.registry import Thresholds  # noqa: E402
from kit.testing.check import check, finish, raises, tmp_dir  # noqa: E402

LAST = "2026-10-15"
END = date.fromisoformat(LAST)


def span(n: int, spend=100.0, roas=4.0, conv=5.0, back=0) -> dict:
    """n consecutive days ending `back` days before LAST: (spend, revenue, conversions, impressions, clicks)."""
    return {(END - timedelta(days=back + i)).isoformat(): (spend, spend * roas, conv, 20000.0, 200.0) for i in range(n)}


def info(name, status="active", budget=None, group_budget=0.0) -> dict:
    return {"name": name, "type": "sales", "status": status, "budget": budget, "group_budget": group_budget}


def tables() -> dict:
    """Five campaigns: one that earns, one that lags (its budget is its ad groups'), one that never ran, one new, one whose return rose
    in the last two weeks."""
    days = {"DEMO-C1": span(60, roas=5.0), "DEMO-C2": span(60, roas=4.0), "DEMO-C4": span(3),
            "DEMO-C5": {**span(14, roas=4.5), **span(46, roas=4.0, back=14)}}
    return {
        "campaigns": {"DEMO-C1": info("DEMO sales a", budget=100.0), "DEMO-C2": info("DEMO sales b", group_budget=300.0),
                      "DEMO-C3": info("DEMO idle", status="paused"), "DEMO-C4": info("DEMO new", budget=100.0),
                      "DEMO-C5": info("DEMO sales c", budget=100.0)},
        "days": days,
        "ads": {"DEMO-A1": ("DEMO-C1", False), "DEMO-A2": ("DEMO-C1", False), "DEMO-A3": ("DEMO-C2", False)},
        "ad_spend": {"DEMO-A1": span_spend(60), "DEMO-A2": span_spend(60), "DEMO-A3": span_spend(60)},
        "creative_state": {"DEMO-A1": "mature", "DEMO-A2": "testing", "DEMO-A3": "mature"},
    }


def span_spend(n: int) -> dict:
    return {d: x[0] for d, x in span(n).items()}


def source(as_of: str | None = LAST, kinds=(), **over) -> cc.Source:
    t = copy.deepcopy(tables())
    if as_of is not None:                      # the tables read no further than as_of
        t["days"] = {c: {d: x for d, x in ds.items() if d <= as_of} for c, ds in t["days"].items()}
        t["ad_spend"] = {a: {d: s for d, s in ds.items() if d <= as_of} for a, ds in t["ad_spend"].items()}
    return cc.Source(**{"as_of": as_of, "currency": "EUR", "doubt_spend": 50.0, "kinds": list(kinds), "kinds_file": "kinds.tsv", **t, **over})


def read_at(until: str | None = None, **over) -> cc.Source:
    return source(min(until or LAST, LAST), **over)


def coded(fn) -> dict | None:
    e = raises(fn, SkillPackError)
    return None if e is None else messages.code(e.message)


def main() -> int:
    _shop.use()
    empty = Path(tmp_dir("compute-campaign-")) / "constants.tsv"
    empty.write_text("name\tdefault\tunit\tmin\tmax\tgroup\tlabel_en\tlabel_zh\texplain\twhy\n", encoding="utf-8")
    k = Thresholds(empty).load()                 # the kit's own defaults: this pack lists nothing

    print("[1] the document")
    doc = cc.read(source(), k, market="DE")
    by = {c["campaign"]: c for c in doc["campaigns"]}
    check("every campaign of the tables has a state and a reason",
          set(by) == {"DEMO-C1", "DEMO-C2", "DEMO-C3", "DEMO-C4", "DEMO-C5"}
          and (by["DEMO-C3"]["state"], by["DEMO-C3"]["reason"]) == ("ended", "never_ran")
          and (by["DEMO-C4"]["state"], by["DEMO-C4"]["reason"]) == ("learning", "new"), {c: (v["state"], v["reason"]) for c, v in by.items()})
    check("a return 15% over the account's, spending its budget: earning, with a raise-the-budget proposal",
          (by["DEMO-C1"]["state"], by["DEMO-C1"]["reason"]) == ("earning", "above_benchmark")
          and [p["action"] for p in by["DEMO-C1"]["proposals"]] == ["raise_budget"]
          and by["DEMO-C1"]["proposals"][0]["message_code"]["code"] == "campaign_raise_budget"
          and by["DEMO-C1"]["proposals"][0]["evidence"], by["DEMO-C1"])
    check("a return under the account's by the margin that did not fall: lagging",
          (by["DEMO-C2"]["state"], by["DEMO-C2"]["reason"]) == ("lagging", "below_benchmark")
          and by["DEMO-C2"]["proposals"][0]["message_code"]["code"] == "campaign_lagging", by["DEMO-C2"])
    check("the budget says where it came from: the campaign, its ad groups, unknown",
          (by["DEMO-C1"]["budget"], by["DEMO-C2"]["budget"], by["DEMO-C3"]["budget"])
          == ({"daily": 100.0, "basis": "campaign"}, {"daily": 300.0, "basis": "ad groups"}, {"daily": None, "basis": "unknown"}))
    check("the creatives of a campaign are counted by state", by["DEMO-C1"]["creatives"] == {"mature": 1, "testing": 1}
          and by["DEMO-C2"]["creatives"] == {"mature": 1}, by["DEMO-C1"]["creatives"])
    blocked = cc.read(source(ads={"DEMO-A3": ("DEMO-C2", True)}), k, market="DE")
    c2 = next(c for c in blocked["campaigns"] if c["campaign"] == "DEMO-C2")
    check("the spend on ads with issues makes a campaign blocked, and the proposal is to name them",
          (c2["state"], c2["reason"]) == ("blocked", "ads_with_issues") and c2["proposals"][0]["action"] == "fix_issue", c2["state"])
    p = doc["params"]
    check("the parameters come from the thresholds in effect; the judging spend is a multiple of the doubt line",
          p["window_days"] == 14 and p["learning_days"] == 7 and p["judge_spend"] == 500.0 and p["min_conversions"] == 3
          and p["end_idle_days"] == 14 and p["hold_weeks"] == 2, p)
    check("window, currency, market, as_of and the summary",
          doc["window"] == {"from": "2026-10-02", "to": LAST, "days": 14} and doc["currency"] == "EUR" and doc["market"] == "DE"
          and doc["as_of"] == LAST and sum(doc["summary"].values()) == 5, (doc["window"], doc["summary"]))
    check("the thresholds are said to be drafts, in a coded warning",
          any(w["code"] == "campaign_thresholds_draft" for w in doc["warning_codes"]), doc["warning_codes"])
    check("the document carries no meta: that is the pack's", "meta" not in doc)

    print("[2] the benchmark and the kinds")
    check("no registry: every campaign is unclassified and a coded warning names the file",
          {c["kind"] for c in doc["campaigns"]} == {cc.UNCLASSIFIED} and doc["kinds"] == {"source": None, "n": 0}
          and [w["params"] for w in doc["warning_codes"] if w["code"] == "campaign_kinds_missing"] == [{"file": "kinds.tsv"}], doc["warning_codes"])
    check("benchmark of a campaign: the others judged, not itself", by["DEMO-C1"]["benchmark"]["n"] == 2
          and by["DEMO-C1"]["benchmark"]["basis"] == "the account's other campaigns", by["DEMO-C1"]["benchmark"])
    kinds = cc.read(source(kinds=[("DEMO sales [ab]$", "built"), ("DEMO sales c", "other")]), k, market="DE")
    kb = {c["campaign"]: c for c in kinds["campaigns"]}
    check("with a registry the first match gives the kind, the warning is gone",
          [kb[c]["kind"] for c in ("DEMO-C1", "DEMO-C2", "DEMO-C5", "DEMO-C3")] == ["built", "built", "other", cc.UNCLASSIFIED]
          and kinds["kinds"] == {"source": "kinds.tsv", "n": 2}
          and not any(w["code"] == "campaign_kinds_missing" for w in kinds["warning_codes"]))
    kinds3 = cc.read(source(kinds=[("DEMO sales", "built")]), k, market="DE")
    k3 = {c["campaign"]: c for c in kinds3["campaigns"]}
    check("two other judged campaigns of its kind: the benchmark is theirs", k3["DEMO-C1"]["benchmark"]["basis"] == "kind built"
          and k3["DEMO-C1"]["benchmark"]["n"] == 2 and k3["DEMO-C3"]["benchmark"]["basis"] == "the account's other campaigns",
          k3["DEMO-C1"]["benchmark"])
    e = coded(lambda: cc.read(source(kinds=[("(", "Broken")]), k, market="DE"))
    check("a pattern that is no regular expression: campaign_kind_pattern_invalid with the file and the pattern",
          e is not None and e["code"] == "campaign_kind_pattern_invalid" and e["params"] == {"file": "kinds.tsv", "pattern": "("}, e)

    print("[3] the hold")
    tl = cc.timeline(read_at, k, market="DE", until=None, weeks=2)
    check("three checkpoints a week apart, oldest first, the last on as_of",
          [t["day"] for t in tl] == ["2026-10-01", "2026-10-08", LAST] and all(t["doc"] for t in tl), [t["day"] for t in tl])
    last = {c["campaign"]: c for c in tl[-1]["doc"]["campaigns"]}
    raw = {cid: [next(c for c in t["doc"]["campaigns"] if c["campaign"] == cid)["raw_state"] for t in tl] for cid in last}
    check("each campaign's state is the hold of its raw states", all(
        (last[c]["state"], last[c]["pending"]) == lifecycle.hold(raw[c], [""] * len(raw[c]), 2)[::2] for c in last), raw)
    moved = {c: v for c, v in last.items() if v["raw_state"] != v["state"]}
    check("a state that changed on the last reading alone waits: the old one stands, the new one is named, no proposal",
          moved and all(v["pending"] == v["raw_state"] and v["proposals"] == [] for v in moved.values()), {c: (v["state"], v["raw_state"]) for c, v in last.items()})
    early = cc.timeline(lambda until, **o: read_at(until, **o) if (until or LAST) > "2026-10-10" else source(None), k, market="DE", until=None, weeks=2)
    check("a checkpoint with no complete day is no reading, never a guess",
          [t["doc"] is None for t in early] == [True, True, False], [t["day"] for t in early])

    print("[4] compute(): the last reading, filtered and sorted")
    full = cc.compute(read_at, k, market="DE")
    order = [lifecycle.STATES.index(c["state"]) for c in full["campaigns"]]
    check("sorted by the order of the states", order == sorted(order) and len(full["campaigns"]) == 5, [c["state"] for c in full["campaigns"]])
    one = cc.compute(read_at, k, market="DE", state="ended")
    check("--state keeps that state only", [c["campaign"] for c in one["campaigns"]] == ["DEMO-C3"] and one["summary"] == {"ended": 1}, one["summary"])
    check("--campaign takes an id or an exact name",
          [c["campaign"] for c in cc.compute(read_at, k, market="DE", campaign="DEMO-C2")["campaigns"]] == ["DEMO-C2"]
          and [c["campaign"] for c in cc.compute(read_at, k, market="DE", campaign="DEMO idle")["campaigns"]] == ["DEMO-C3"])
    check("--until is passed to the adapter", cc.compute(lambda until, **o: read_at(until, **o), k, market="DE", until="2026-10-08")["as_of"] == "2026-10-08")

    print("[5] a pack's adapter is refused, coded, naming the part")
    bad = lambda **over: coded(lambda: cc.read(source(**over), k, market="DE"))   # noqa: E731
    e = bad(campaigns={"DEMO-C1": {"name": "x", "type": "t", "status": "active", "budget": 1.0}})
    check("a campaign without group_budget", e and e["code"] == "compute_input_invalid" and e["params"]["part"] == "campaigns[DEMO-C1]"
          and "group_budget" in e["params"]["problem"], e)
    e = bad(days={"DEMO-C1": {LAST: (1.0, 2.0, 3.0)}})
    check("a day that is not five numbers", e and e["code"] == "compute_input_invalid" and e["params"]["part"] == f"days[DEMO-C1][{LAST}]", e)
    e = bad(ads={"DEMO-A1": "DEMO-C1"})
    check("an ad that is not (campaign, has_issue)", e and e["code"] == "compute_input_invalid" and e["params"]["part"] == "ads[DEMO-A1]", e)
    e = coded(lambda: cc.read(cc.Source(as_of="yesterday", currency=None, campaigns={}, days={}, ads={}, ad_spend={}, creative_state={},
                                        doubt_spend=None), k, market="DE"))
    check("an as_of that is no day", e and e["code"] == "compute_input_invalid" and e["params"]["part"] == "as_of", e)
    e = coded(lambda: cc.read(source(None), k, market="DE"))
    check("a market with no complete day: campaign_no_data", e and e["code"] == "campaign_no_data" and e["params"] == {"market": "DE"}, e)
    e = coded(lambda: cc.compute(lambda until, **o: source(None), k, market="DE"))
    check("...also through compute()", e and e["code"] == "campaign_no_data", e)
    unknown = cc.read(source(doubt_spend=None), k, market="DE")
    check("no doubt line: nothing is judged (the judging spend is 0, the rules read the window as thin or learning)",
          unknown["params"]["judge_spend"] == 0.0, unknown["params"]["judge_spend"])

    print("[6] it reads")
    src = source()
    before = copy.deepcopy(src)
    cc.compute(lambda until, **o: src, k, market="DE")
    check("the Source handed over is not changed", src == before)

    print("[7] the module keeps its message fragment closed")
    mine = {c: r for c, r in messages.registry().items() if Path(r["file"]).name == "compute_campaign.tsv"}
    probs = messages.check_registry_closed(_shop.KIT, ["compute_campaign.py"], mine, strict_kit=True)
    check("every msg() is literal, registered with exact params, and every code of compute_campaign.tsv is emitted", probs == [], probs)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
