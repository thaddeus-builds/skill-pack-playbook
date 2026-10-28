#!/usr/bin/env python3
"""kit.compute_demand: the demand document over a hand-made account (invented DEMO ids, invented numbers). The cases are the video-ads skill pack's `creative_demand`
block of its pacing document: how many creatives to ask for from the exploration money, the cost of a verdict measured from the creatives' own history, earlier
requests in production and the lead time measured from them, the platform's range binding, who pays whom (the ad groups' say), nothing to ask for without a plan.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import compute_demand as cd, compute_life as cl, compute_pacing as cp, creative_life as life, messages  # noqa: E402
from kit.registry import Thresholds  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

START = date(2026, 9, 1)


def thresholds() -> dict:
    empty = Path(tmp_dir("compute-demand-")) / "constants.tsv"
    empty.write_text("\t".join(["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why"]) + "\n", encoding="utf-8")
    return Thresholds(empty).load()


def days(n, spend=20.0, imp=400, clicks=8, conv=0.0, start=START) -> list:
    return [life.Day(date=(start + timedelta(days=i)).isoformat(), spend=spend, impressions=imp, clicks=clicks, conversions=conv) for i in range(n)]


def account() -> dict:
    """Six winners (3 a day from the first day: mature on the 7th), three that spent and never converted (parked), one three days old; in ad groups."""
    out = {f"WIN-{i}": {"days": days(30, conv=3.0), "group": f"G{i % 2}"} for i in range(6)}
    out.update({f"DUD-{i}": {"days": days(30, spend=5.0, imp=50, clicks=0), "group": "G2"} for i in range(3)})
    out["NEW"] = {"days": days(3, imp=300, start=date(2026, 9, 28)), "group": "G3"}
    return out


def pacing(creatives, k, month="2026-10", spend=9000.0):
    """The pacing document of the same creatives: the plan and who pays whom, as the demand document reads them."""
    lf = cl.compute(cl.Source(creatives), k)
    rows = {r["creative"]: r for r in lf["rows"]}
    ds, dc = {}, {}
    for c in creatives.values():
        for d in c["days"]:
            ds[d.date] = ds.get(d.date, 0.0) + d.spend
            dc[d.date] = dc.get(d.date, 0.0) + d.conversions
    cre = {c: {"wallet": rows[c]["wallet"], "group": v.get("group"), "spend7": rows[c]["spend7"], "conv7": rows[c]["conv7"]} for c, v in creatives.items()}
    return cp.compute(cp.Source(ds, dc, cre, month=month, spend_target=spend, spend_source="given", result_target=400.0, result_source="given"), k)


def codes(doc) -> list:
    return [w["code"] for w in doc["warning_codes"]]


def refused(s, k):
    try:
        cd.compute(s, k)
    except Exception as e:  # noqa: BLE001
        f = messages.failure(e)
        return f["code"], f["params"].get("part")
    return None, None


def main() -> int:
    _shop.use()
    k = thresholds()
    cr = account()
    ls = cl.Source(cr)
    pa = pacing(cr, k)
    plan, paid = pa["plan"], pa["creative_wallets"]

    print("[1] the pacing document says who pays whom; the request follows the exploration money")
    check("each creative's paid wallet: the winners perform, the parked ones nobody, the new one explore", paid["WIN-0"] == "perform" and paid["DUD-0"] is None and paid["NEW"] == "explore"
          and set(paid) == set(cr), paid)
    d = cd.compute(cd.Source(ls, plan, paid=paid), k)
    b = d["demand"]
    check("the month is the plan's", d["month"] == "2026-10" == plan["month"])
    check("the exploration money of the next 7 days is the plan's own", b["explore_next_7_days"] == round(sum(r["explore"] for r in plan["days"][:7]), 2) > 0, b["explore_next_7_days"])
    check("nine creatives left exploration: six reached mature (wins), three were parked for no conversion (losses); a cost per verdict was measured",
          b["verdicts"] == 9 and b["wins"] == 6 and b["basis"] == "measured" and b["unit_cost"] > 0, (b["verdicts"], b["wins"], b["basis"]))
    check("a request is in whole batches of the size in force (5), the daily budget of each given, and what it cost is within what the plan could carry",
          b["n"] == b["batch_size"] == 5 and b["batches"] == [{"size": 5, "daily_budget": b["batches"][0]["daily_budget"]}] and b["capacity"] >= b["n"] and b["money"] > 0, b)
    check("the diagnosis and its warning agree: a surplus of exploration money over what replacing the fading ones takes", b["diagnostic"]["flag"] == "surplus" and "pacing_surplus" in codes(d), (b["diagnostic"], codes(d)))
    check("the limits are said even when unknown, and the earlier requests are none", b["limits"] == {"min": None, "max": None} and b["in_production"] == 0.0 and b["lead_basis"] == "draft" and b["lead_days"] == 14.0)
    check("the document is plain data and every warning has a code", json.dumps(d) and len(d["warnings"]) == len(d["warning_codes"]))
    check("the life document's own warning is kept (a short history deriving the thresholds)", "life_history_insufficient" in codes(d), codes(d))

    print("[2] earlier requests, and the lead time measured from them")
    unseen = cd.compute(cd.Source(ls, plan, paid=paid, requests=[{"date": "2026-09-10", "n": 10, "batches": 2}]), k)["demand"]
    check("a request no ad group has started from yet: its 10 creatives are in production, and the request now is for what is not already coming",
          unseen["in_production"] == 10.0 and unseen["lost"] == 0.0 and unseen["lead_basis"] == "draft" and unseen["committed"] > b["committed"] and unseen["n"] <= b["n"], unseen)
    groups = {"G3": {"days": {d_.date: (d_.spend, d_.conversions) for d_ in cr["NEW"]["days"]}, "active": True},
              "G0": {"days": {d_.date: (d_.spend, d_.conversions) for d_ in cr["WIN-0"]["days"]}, "active": True}}
    seen = cd.compute(cd.Source(ls, plan, paid=paid, groups=groups, requests=[{"date": "2026-09-10", "n": 10, "batches": 2}]), k)["demand"]
    check("an ad group that first spent on 28 September answers the request of 10 September: a lead time of 18 days, measured; the group that began on the 1st, before it, does not",
          seen["lead_days"] == 18 and seen["lead_basis"] == "measured" and 0 < seen["in_production"] < 10, (seen["lead_days"], seen["lead_basis"], seen["in_production"]))
    lost = cd.compute(cd.Source(ls, plan, paid=paid, requests=[{"date": "2026-07-01", "n": 4, "batches": 1}]), k)["demand"]
    check("a request with no first spend after twice the lead time is taken as lost, not as in production", lost["lost"] == 4.0 and lost["in_production"] == 0.0, (lost["lost"], lost["in_production"]))

    print("[3] the platform's range")
    low = cd.compute(cd.Source(ls, plan, paid=paid, limits={"min": 5000.0}), k)
    check("an ad group's lowest daily budget above what the exploration money can pay: no batch, the limit named, and it is said",
          low["demand"]["n"] == 0 and low["demand"]["batches"] == [] and low["demand"]["binding"] == "min_daily_budget" and "pacing_limit_binds" in codes(low), low["demand"]["binding"])
    high = cd.compute(cd.Source(ls, plan, paid=paid, limits={"max": 20.0}), k)
    check("a highest daily budget of 20: the batch is held to it, the limit named, and it is said",
          high["demand"]["batches"][0]["daily_budget"] == 20.0 and high["demand"]["binding"] == "max_daily_budget" and "pacing_limit_binds" in codes(high), high["demand"]["batches"])

    print("[4] the ad groups' say, and the cases with nothing to ask")
    held = cd.compute(cd.Source(ls, plan, paid={**paid, "WIN-0": "explore"}), k)["demand"]
    check("a winner whose ad group is not judged is paid from exploration: it no longer counts among the proven (6 to 5)", b["diagnostic"]["proven_then"] == 6.0 and held["diagnostic"]["proven_then"] == 5.0,
          (b["diagnostic"], held["diagnostic"]))
    own = cd.compute(cd.Source(ls, plan), k)["demand"]
    check("without the pacing document's wallets each creative keeps its own state's (the new one explores, the winners perform): the same request", own["n"] == b["n"] and own["diagnostic"] == b["diagnostic"])
    gone = cd.compute(cd.Source(ls, plan, paid={**paid, "NEW": None}), k)["demand"]
    check("a creative still in exploration that nobody pays does not count in what the exploration has committed", gone["committed"] < b["committed"], (gone["committed"], b["committed"]))
    none = cd.compute(cd.Source(ls, None), k)
    check("no plan (no spend target for the month): nothing to ask for, and no month", none["demand"] is None and none["month"] is None, none)
    sep = cd.compute(cd.Source(ls, pacing(cr, k, month="2026-09")["plan"], paid=paid), k)["demand"]
    check("a month with no day left to plan: no money to ask by, no diagnosis, and no failure", sep["explore_next_7_days"] == 0 and sep["diagnostic"] is None, sep["explore_next_7_days"])
    young = {"NEW": cr["NEW"]}
    yp = pacing(young, k)
    y = cd.compute(cd.Source(cl.Source(young), yp["plan"], paid=yp["creative_wallets"]), k)
    check("no creative has left exploration and no doubt line is known: no cost, no number to ask for, said", y["demand"]["unit_cost"] is None and y["demand"]["n"] is None
          and y["demand"]["basis"] != "measured" and "pacing_demand_unknown" in codes(y), (y["demand"]["unit_cost"], codes(y)))
    empty = cd.compute(cd.Source(cl.Source({}), plan), k)
    check("no creative at all: nothing to ask for, said once", empty["demand"] is None and codes(empty).count("life_no_creatives") == 1, codes(empty))

    print("[5] a Source the rules cannot read is refused, naming the part")
    bad = {"a plan that is not the pacing plan": ("plan", cd.Source(ls, {"month": "2026-10"})), "a plan whose days are not {day, explore}": ("plan", cd.Source(ls, {**plan, "days": [{"day": "2026-10-01"}]})),
           "a wallet that is neither": ("paid[WIN-0]", cd.Source(ls, plan, paid={"WIN-0": "other"})), "a group without days": ("groups[G]", cd.Source(ls, plan, groups={"G": {"active": True}})),
           "a request without its batches": ("requests[0]", cd.Source(ls, plan, requests=[{"date": "2026-09-10", "n": 3}])), "a limit that is a word": ("limits", cd.Source(ls, plan, limits={"min": "50"})),
           "a creative without days": ("creatives[X]", cd.Source(cl.Source({"X": {"label": "x"}}), plan))}
    got = {name: refused(s, k) for name, (_, s) in bad.items()}
    check("each is compute_input_invalid, naming its part", all(c == "compute_input_invalid" for c, _ in got.values()) and [p for _, p in got.values()] == [x for x, _ in bad.values()], got)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
