#!/usr/bin/env python3
"""kit.creative_demand: the rules of the request for creatives on planted numbers.
"""

import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import creative_demand as demand  # noqa: E402
from kit.creative_life import Day  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

P = demand.Params(batch_size=5, min_batch=3, min_verdicts=10, max_batches=4, lead_days=14, weeks=8, prior_verdicts=5.0, lost_factor=2.0, fallback_days=14)
T = date(2026, 10, 20)


def mv(day, frm, to, reason="x"):
    return {"date": day, "from": frm, "to": to, "reason": reason}


def days(first, n, spend=100.0):
    start = date.fromisoformat(first).toordinal()
    return [Day(date=date.fromordinal(start + i).isoformat(), spend=spend) for i in range(n)]


def main() -> int:
    moves = {"w": [mv("2026-10-05", "learning", "mature", "learned")], "l": [mv("2026-10-06", "doubt", "parked", "no_conversion")],
             "off": [mv("2026-10-07", "testing", "parked", "stopped_unjudged")], "run": []}
    ds = {c: days("2026-10-01", 10) for c in moves}
    vs = demand.verdicts(moves, ds)
    check("a win and a loss are verdicts, a switch-off and a creative still running are not", sorted((v.creative, v.win) for v in vs) == [("l", False), ("w", True)], vs)
    w = next(v for v in vs if v.creative == "w")
    check("the cost is the spend from the first day to the verdict, the days the same", w.cost == 500.0 and w.days == 4, w)
    check("only the exploration days count in the flow", demand.explore_spend(moves, ds, "2026-10-01", "2026-10-10") == 500 + 600 + 700 + 1000, demand.explore_spend(moves, ds, "2026-10-01", "2026-10-10"))

    e = demand.estimate(vs, 1100.0, 300.0, "2026-10-20", P)
    check("the cost leans on the doubt line while verdicts are few: (flow + 5 x doubt) / (n + 5)", abs(e["cost"] - (1100 + 5 * 300) / 7) < 1e-9 and e["basis"] == "measured", e)
    check("the win rate has a prior: (wins + 1) / (n + 2)", e["win_rate"] == 0.5 and e["days"] == 4.5, e)
    e0 = demand.estimate([], 0.0, 300.0, "2026-10-20", P)
    check("no verdict yet: the doubt line is the cost, said, and the days are the draft", e0["cost"] == 300.0 and e0["basis"] == "doubt_spend" and e0["days_basis"] == "draft" and e0["win_rate"] is None, e0)
    check("no verdict and no doubt line: no cost", demand.estimate([], 0.0, None, "2026-10-20", P)["cost"] is None)

    check("whole batches: 12 is 5 + 5 and a batch of 2 is not worth one", demand.batches_of(12, P) == [5, 5] and demand.batches_of(13, P) == [5, 5, 3] and demand.batches_of(2, P) == [])

    plan = [(date.fromordinal(T.toordinal() + i).isoformat(), 100.0) for i in range(60)]
    none = {"min": None, "max": None}
    r = demand.request(100.0, 10, 5, plan, T, [], 0.0, 50, none, P)
    check("1,000 of exploration money at 100 a verdict carries 10 creatives: two batches of 5, each 50 a day", r["capacity"] == 10 and r["n"] == 10
          and [b["size"] for b in r["batches"]] == [5, 5] and r["batches"][0]["daily_budget"] == 50.0 and r["money"] == 1000.0, r)
    r = demand.request(100.0, 10, 5, plan, T, [30.0, 80.0], 2.0, 50, none, P)
    check("what is already promised is taken off: two in exploration (70 + 20) and two asked for earlier (200) leave 710, seven creatives, one batch of 5",
          r["committed"] == 290.0 and r["capacity"] == 7 and r["n"] == 5, r)
    r = demand.request(100.0, 10, 5, plan, T, [], 0.0, 3, none, P)
    check("before enough verdicts one batch only", r["n"] == 5 and "few_verdicts" in r["constraints"], r)
    r = demand.request(10.0, 10, 5, plan, T, [], 0.0, 50, none, P)
    check("never more than the most batches", len(r["batches"]) == 4 and "max_batches" in r["constraints"], r)
    r = demand.request(100.0, 10, 5, plan, T, [], 0.0, 50, {"min": 80.0, "max": None}, P)
    check("a platform minimum raises a batch's budget to it, and the money then carries one batch, not two: the limit is named",
          r["n"] == 5 and r["batches"][0]["daily_budget"] == 80.0 and r["binding"] == "min_daily_budget", r)
    r = demand.request(100.0, 10, 5, plan[:3], T, [], 0.0, 50, {"min": 500.0, "max": None}, P)
    check("when the minimum is more than the money can carry, no ad group is asked for", r["n"] == 0 and r["batches"] == [], r)
    check("no cost, no request", demand.request(None, 10, 5, plan, T, [], 0.0, 50, none, P)["constraints"] == ["cost_unknown"])
    r = demand.request(100.0, 10, 5, [], T, [], 0.0, 50, none, P)
    check("no exploration money: no request, said", r["n"] == 0 and "no_exploration_money" in r["constraints"], r)
    r = demand.request(100.0, 10, 5, plan[:12], T, [], 0.0, 50, none, P)
    check("a plan that ends before the window is extended at its own average, said", "window_extended" in r["constraints"] and r["money"] == 1000.0, r)

    reqs = [{"date": "2026-10-01", "n": 10, "batches": 2}, {"date": "2026-10-15", "n": 5, "batches": 1}]
    pl = demand.pipeline(reqs, ["2026-09-20", "2026-10-09"], "2026-10-20", P)
    check("a request is matched to the first ad group started on or after it (one that started before it is not its)", pl["leads"] == [8] and pl["lead_basis"] == "measured" and pl["lead"] == 8, pl)
    check("the batch with no start yet is in production, the new request too", pl["in_production"] == 10.0 and pl["lost"] == 0.0, pl)
    pl = demand.pipeline(reqs, [], "2026-11-15", P)
    check("with no start after two lead times it is taken as lost and the lead time stays the draft", pl["lost"] == 15.0 and pl["in_production"] == 0.0 and pl["lead"] == 14.0 and pl["lead_basis"] == "draft", pl)

    fm = {"a": [mv("2026-09-01", "learning", "mature")], "b": [mv("2026-09-01", "learning", "mature"), mv("2026-09-15", "mature", "ended")]}
    f = demand.fade(fm, "2026-09-01", "2026-09-28")
    check("fade: one of two proven creatives ended in 4 weeks: 1 per (28 + 15 proven days / 7)", abs(f - 1 / ((28 + 15) / 7)) < 1e-9, f)
    check("no proven day, no fade", demand.fade({}, "2026-09-01", "2026-09-28") is None)

    d = demand.diagnose(100.0, 10.0, 6, 0.2, 14, 10, 0.5, 2)
    check("10 proven are wanted, 6 left of 6 after 24 days at a 20% weekly fade is about 2: the shortfall over the win rate beats the 2 the money carries: money_limited", d["flag"] == "money_limited" and d["need"] > 2, d)
    check("money for more than the shortfall: surplus", demand.diagnose(30.0, 10.0, 6, 0.0, 14, 10, 0.5, 5)["flag"] == "surplus")
    check("no performance money, nothing to say", demand.diagnose(0.0, 10.0, 6, 0.2, 14, 10, 0.5, 5) is None)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
