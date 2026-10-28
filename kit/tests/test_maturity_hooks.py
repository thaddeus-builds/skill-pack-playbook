#!/usr/bin/env python3
"""The hooks of kit.maturity: kit.lifecycle.judge, kit.compute_campaign and kit.alerts.check read a window on the estimate when they are given a `maturity.Reading`.
Every day below is generated as `true x F(age)` from known curves, so the estimate must come back as the truth, and what the rule did on the understated tail can be
shown beside what it does now. Every id and number is invented.
"""

import math
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import alerts, compute_campaign as cc, lifecycle as lc, maturity as m, messages  # noqa: E402
from kit.registry import Thresholds  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

W = 7
AS_OF = date(2026, 9, 30)
TAU_C, TAU_V = 1.5, 3.0


def thresholds() -> dict:
    empty = Path(tmp_dir("maturity-hooks-")) / "constants.tsv"
    empty.write_text("\t".join(["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why"]) + "\n", encoding="utf-8")
    return Thresholds(empty).load()


def F(age: int, tau: float) -> float:
    """The share visible at an age, by the formula, written out here and not taken from the module."""
    return 1.0 if age >= W else (1 - math.exp(-(age + 1) / tau)) / (1 - math.exp(-(W + 1) / tau))


def days(roas_at, n=28, spend=100.0, orders=4.0, observed_on=None) -> dict:
    """n days up to AS_OF as a platform shows them on `observed_on` (the day after AS_OF by default): the true figures times the share visible at their age."""
    obs = observed_on or AS_OF + timedelta(days=1)
    out = {}
    for i in range(n):
        d = AS_OF - timedelta(days=i)
        age = (obs - d).days
        out[d.isoformat()] = (spend, spend * roas_at(i) * F(age, TAU_V), orders * F(age, TAU_C), 1000, 20)
    return out


def main() -> int:
    _shop.use()
    k = thresholds()
    P = m.params(k)
    cnt = m.Curve("exp", TAU_C, 1.0, 0.15, W, "count", 600, 7, False)
    val = m.Curve("exp", TAU_V, 1.0, 0.3, W, "value", 600, 7, False, dispersion=1.3)
    R = m.Reading(cnt, val, (AS_OF + timedelta(days=1)).isoformat(), P)
    LP = lc.Params(window_days=7, learning_days=7, judge_spend=500.0, min_conversions=3.0, earn_margin=0.15, use_share=0.85, decline_drop=0.25, issue_share=0.30,
                   end_idle_days=14, budget_step=0.2)
    asof = AS_OF.isoformat()

    def judge(roas_at, bench=4.0, reading=R, **kw):
        return lc.judge(lc.Campaign("C", lc.ACTIVE, days(roas_at, **kw), 400.0), asof, LP, bench, reading)

    print("[1] lifecycle.judge reads an immature window on its estimate")
    seen = sum(F(a, TAU_V) for a in range(1, 8)) * 400.0 / 700.0
    steady = lambda i: 4.0                                                      # noqa: E731
    a, b = judge(steady, reading=None), judge(steady)
    check("a campaign whose true return IS the benchmark's, 4.0, shows 3.29 on its last seven days (the share visible at ages 1 to 7) and is called lagging on it",
          abs(a.window["roas"] - seen) < 1e-9 and 3.29 < seen < 3.30 and (a.state, a.reason) == ("lagging", "below_benchmark") and "matured" not in a.window, (a.window["roas"], a.state))
    w = b.window["matured"]
    check("given the reading its estimate is the truth to the last digit, from a window 82 % visible, and the interval is round it", abs(w["roas"] - 4.0) < 1e-9 and w["immature"]
          and abs(w["share"] - seen / 4.0) < 1e-6 and w["low"] < 4.0 < w["high"], w)
    check("the interval holds both bars (3.4 for lagging, 4.6 for earning): the rules cannot tell, so the state is unjudged, for the reason immature", w["low"] < 4.0 * 0.85 and w["high"] > 4.0 * 1.15
          and (b.state, b.reason) == ("unjudged", "immature"), (w["low"], w["high"], b.state, b.reason))
    lag, earn = judge(lambda i: 1.0), judge(lambda i: 9.0)
    check("a campaign far under the benchmark (true 1.0) is still lagging: the whole interval is under 3.4, so it is decided", lag.window["matured"]["immature"] and lag.window["matured"]["high"] < 3.4
          and (lag.state, lag.reason) == ("lagging", "below_benchmark"), (lag.window["matured"], lag.state))
    check("and one far over (true 9.0) is still earning", earn.window["matured"]["low"] > 4.6 and earn.state == "earning", (earn.window["matured"], earn.state))
    late = AS_OF + timedelta(days=30)
    old_a, old_b = judge(steady, reading=None, observed_on=late), judge(steady, reading=m.Reading(cnt, val, late.isoformat(), P), observed_on=late)
    check("the same campaign seen a month later, every day settled: not immature, and judged as it always was, with or without the reading",
          not old_b.window["matured"]["immature"] and old_b.window["matured"]["share"] == 1.0 and (old_a.state, old_a.reason) == (old_b.state, old_b.reason) == ("steady", "near_benchmark")
          and abs(old_a.window["roas"] - old_b.window["matured"]["roas"]) < 1e-9, (old_b.window["matured"], old_b.state))
    check("no reading, no change: the window has no matured key and the state is what it was", "matured" not in a.window and (a.state, a.reason) == ("lagging", "below_benchmark"))

    print("[2] the other rules on the interval: a fall, the gates, the held state")
    prev_good = lambda i: 4.0 if i >= 7 else 2.0                                  # noqa: E731  the week before at 4.0, this week at 2.0
    fall = judge(prev_good, bench=2.5)
    check("a return that fell by half against the week before (4.0 to 2.0), the interval wholly under 4.0 x 0.75 = 3.0: declining, decided", fall.window["matured"]["high"] < 3.0 and
          (fall.state, fall.reason) == ("declining", "return_falling"), (fall.window["matured"], fall.state, fall.reason))
    maybe = judge(lambda i: 4.0 if i >= 7 else 3.2, bench=3.2)
    mw = maybe.window["matured"]
    check("a return that fell from 4.0 to 3.2 (the threshold is 3.0) with an interval of [2.7, 3.7] across it: not decided, unjudged for immaturity",
          mw["low"] < 3.0 < mw["high"] and (maybe.state, maybe.reason) == ("unjudged", "immature"), (mw, maybe.state, maybe.reason))
    thin = lc.judge(lc.Campaign("C", lc.ACTIVE, days(steady, orders=0.45), 400.0), asof, LP, 4.0, R)
    check("the evidence gates stay on what was seen: 0.45 orders a day estimate to 3.15 in the week but 2.92 were seen against 3 needed, so the campaign is unjudged as thin, not immature",
          thin.window["conversions"] < 3.0 <= thin.window["matured"]["conversions"] and (thin.state, thin.reason) == ("unjudged", "thin"), (thin.window["conversions"], thin.state, thin.reason))
    check("a week of unjudged/immature does not by itself move a held state (hold keeps a non-forced change until it has been said twice)",
          lc.hold(["steady", "unjudged"], ["near_benchmark", "immature"], 2) == ("steady", "near_benchmark", "unjudged"))
    check("the interval helper: all of it under the threshold is True, none of it False, across it None, a point is the plain comparison",
          [lc._below(1, 2, 3, 3), lc._below(4, 5, 3, 3), lc._below(2, 4, 3, 3), lc._below(2.9, 2.9, 3, 3), lc._below(3, 3, 3, 3)] == [True, False, None, True, False])

    print("[3] compute_campaign: the benchmark on estimates, the matured window in the document")
    kk = {**k, "campaign_window_days": 7, "campaign_learning_days": 7}

    def src(maturity=None, as_of=asof):
        camps = {c: {"name": f"DEMO {c}", "type": "T", "status": lc.ACTIVE, "budget": 400.0, "group_budget": None} for c in "ABC"}
        return cc.Source(as_of, "EUR", camps, {c: days(steady) for c in "ABC"}, {}, {}, {}, 50.0, maturity=maturity)

    plain, matured = cc.read(src(), kk, market="XX"), cc.read(src(R), kk, market="XX")
    bp, bm = plain["campaigns"][0]["benchmark"]["roas"], matured["campaigns"][0]["benchmark"]["roas"]
    check("three campaigns that truly return 4.0: the benchmark each is held to is 3.29 on the understated tail and 4.0 on the estimates", abs(bp - seen) < 0.01 and abs(bm - 4.0) < 0.01, (bp, bm))
    row = matured["campaigns"][0]
    check("the document keeps what was seen and adds what it will come to, rounded: roas 3.29 seen, matured {roas 4.0, low, high, share, immature}",
          row["window"]["roas"] == round(seen, 2) and row["window"]["matured"]["roas"] == 4.0 and row["window"]["matured"]["immature"] is True and row["window"]["matured"]["low"] < 4.0 < row["window"]["matured"]["high"]
          and "matured" not in plain["campaigns"][0]["window"], row["window"])
    check("with the reading these campaigns, at the benchmark and not far enough from it to tell, are unjudged for immaturity; without it they are called steady on a benchmark that is as low as they are",
          {r["state"] for r in matured["campaigns"]} == {"unjudged"} and {r["reason"] for r in matured["campaigns"]} == {"immature"} and {r["state"] for r in plain["campaigns"]} == {"steady"}, matured["summary"])
    check("the document says what it was read on: the date the days were taken and each curve's tau, family, whether it is only the prior, when it was fitted", matured["maturity"]["observed_on"] == "2026-10-01"
          and matured["maturity"]["count"]["tau"] == 1.5 and matured["maturity"]["value"]["prior_only"] is False and plain["maturity"] is None)
    prior = m.Reading(m.Curve("exp", 1.5, 1.0, 0.75, W, "count", 0, 0, True), m.Curve("exp", 3.0, 1.0, 1.5, W, "value", 0, 0, True), "2026-10-01", P)
    pw = cc.read(src(prior), kk, market="XX")
    check("curves that are only the cold start are said so, once each, coded", [x["code"] for x in pw["warning_codes"]].count("campaign_maturity_prior_only") == 2, [x["code"] for x in pw["warning_codes"]])

    def refused(s):
        try:
            cc.read(s, kk, market="XX")
        except Exception as e:  # noqa: BLE001
            f = messages.failure(e)
            return f["code"], f["params"].get("part")
        return None, None

    bad = {"something that is not a Reading": ("maturity", src("soon")), "a date that is not a day": ("maturity.observed_on", src(m.Reading(cnt, val, "later", P))),
           "days taken on the last complete day itself, which would make it partial": ("maturity.observed_on", src(m.Reading(cnt, val, asof, P)))}
    got = {name: refused(s) for name, (_, s) in bad.items()}
    check("each is compute_input_invalid, naming the part", all(c == "compute_input_invalid" for c, _ in got.values()) and [p for _, p in got.values()] == [x for x, _ in bad.values()], got)

    def read_at(until):
        cut = {c: {d: x for d, x in days(steady).items() if until is None or d <= until} for c in "ABC"}
        camps = {c: {"name": f"DEMO {c}", "type": "T", "status": lc.ACTIVE, "budget": 400.0, "group_budget": None} for c in "ABC"}
        return cc.Source(until or asof, "EUR", camps, cut, {}, {}, {}, 50.0, maturity=R)

    line = cc.timeline(read_at, kk, market="XX", until=None, weeks=3)
    old = [x for x in line if x["day"] <= (AS_OF - timedelta(days=14)).isoformat()][-1]["doc"]["campaigns"][0]["window"]["matured"]
    check("a replay over the weeks: the checkpoints a fortnight back have settled (share 1, not immature); only the latest is read on an interval", old["share"] == 1.0 and not old["immature"]
          and line[-1]["doc"]["campaigns"][0]["window"]["matured"]["immature"], (old, len(line)))

    print("[4] alerts.check: a return on an unsettled day")
    base = [alerts.Point((AS_OF - timedelta(days=i)).isoformat(), 1000.0, 4000.0, None, 40.0) for i in range(8, 15)]          # seven settled days at 4.0 (ages 9 to 15: past the window)
    cur_day = AS_OF.isoformat()
    age = 1

    def point(orders=40.0 * F(age, TAU_C), sales=4000.0 * F(age, TAU_V)):
        return alerts.Point(cur_day, 1000.0, sales, None, orders)

    plain_c = alerts.check([point(), *base], "return", "le", 0.7)
    check("a day seen the next morning (age 1) shows 52 % of its sales: 2.09 against a baseline of 4.0, and a rule 'under 0.7 of the baseline' fires on it", plain_c["hit"] is True and
          abs(plain_c["current"] - 4.0 * F(1, TAU_V)) < 1e-6, plain_c)
    big = alerts.check([point(), *base], "return", "le", 0.7, reading=R)
    check("read on the estimate (40 orders a day): 4.0, the interval above the 2.8 line (0.7 x 4.0), so it is silent, decided", big["hit"] is False and abs(big["current"] - 4.0) < 1e-6 and
          big["current_low"] > 2.8 and big["immature"] is True and big["reason"] is None, big)
    small = alerts.check([alerts.Point(cur_day, 100.0, 400.0 * F(1, TAU_V), None, 4.0 * F(1, TAU_C)), *base], "return", "le", 0.7, reading=R)
    check("the same day on a tenth of the volume (4 orders): the interval is wide and runs from under the 2.8 line to over it, so there is no verdict and it says why",
          small["hit"] is None and small["reason"] == "immature_undecided" and small["current_low"] < 2.8 < small["current_high"] and abs(small["current"] - 4.0) < 1e-6, small)
    near = alerts.check([alerts.Point(cur_day, 100.0, 250.0 * F(1, TAU_V), None, 2.5 * F(1, TAU_C)), *base], "return", "le", 0.7, reading=R)
    check("a day on little volume whose estimate (2.5) is under the 2.8 line but whose interval is not wholly under it: no alert and no all-clear, only no verdict (an alert on the point would be one the data cannot back)",
          near["hit"] is None and near["reason"] == "immature_undecided" and near["current"] < 2.8 < near["current_high"], near)
    deep = alerts.check([point(sales=4000.0 * F(1, TAU_V) * 0.2, orders=40.0 * F(1, TAU_C) * 0.2), *base], "return", "le", 0.7, reading=R)
    check("a day truly at a fifth of the baseline (a real collapse, 0.8 on the estimate) still fires, on the interval: the whole of it is under the line", deep["hit"] is True and deep["current_high"] < 2.8, deep)
    ge = alerts.check([point(), *base], "return", "ge", 1.5, reading=R)
    check("the mirror, 'at least 1.5 times the baseline': silent when the interval is wholly under 6.0", ge["hit"] is False and ge["current_high"] < 6.0, ge)
    settled = alerts.check([alerts.Point(cur_day, 1000.0, 4000.0, None, 40.0), *base], "return", "le", 0.7, reading=m.Reading(cnt, val, (AS_OF + timedelta(days=30)).isoformat(), P))
    check("a day that has settled is read as it was seen, and the decision is the old one", settled["hit"] is False and settled["current"] == 4.0 and settled["immature"] is False and settled["current_low"] == settled["current_high"] == 4.0, settled)
    unknown = alerts.check([alerts.Point(cur_day, 1000.0, 2092.0, None, None), *base], "return", "le", 0.7, reading=R)
    check("an unsettled day with no orders cannot be put on a curve: no verdict, and it says orders_unknown", unknown["hit"] is None and unknown["reason"] == "orders_unknown", unknown)
    check("spend is final at once: the spend rule does not change with a reading", alerts.check([alerts.Point(cur_day, 3000.0, 0.0), *[alerts.Point(p.date, 1000.0, 0.0) for p in base]], "spend", "ge", 2.0, reading=R)["hit"] is True)
    check("a rule without a reading, given Points that now carry orders, is unchanged", alerts.check([point(), *base], "return", "le", 0.7)["hit"] is True and "immature" not in alerts.check([point(), *base], "return", "le", 0.7))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
