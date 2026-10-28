#!/usr/bin/env python3
"""kit.compute_pacing: the pacing document over a hand-made account (invented DEMO ids, invented numbers). The cases are the video-ads skill pack's
document test: given targets, flat weights on a short history, a new account all exploration, the ad groups' wallets paying the creatives, no target,
a bad month or day refused; the numbers are worked out by hand.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import compute_pacing as cp, messages  # noqa: E402
from kit.registry import Thresholds  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

LAST = date(2026, 9, 3)


def thresholds() -> dict:
    empty = Path(tmp_dir("compute-pacing-")) / "constants.tsv"
    empty.write_text("\t".join(["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why"]) + "\n", encoding="utf-8")
    return Thresholds(empty).load()


def account(start: date, end: date, spend=100.0, conv=2.0) -> tuple[dict, dict]:
    ds, dc, d = {}, {}, start
    while d <= end:
        ds[d.isoformat()], dc[d.isoformat()] = spend, conv
        d += timedelta(days=1)
    return ds, dc


def src(**kw) -> cp.Source:
    ds, dc = account(date(2026, 8, 1), LAST)
    base = dict(daily_spend=ds, daily_conv=dc, creatives={}, spend_target=3000.0, spend_source="given", result_target=None, result_source=None)
    return cp.Source(**{**base, **kw})


def part_refused(s: cp.Source, k: dict) -> tuple[str | None, str | None]:
    try:
        cp.compute(s, k)
    except Exception as e:  # noqa: BLE001
        f = messages.failure(e)
        return f["code"], f["params"].get("part")
    return None, None


def group_days(per_day: float, conv_total: float, n=14, back=0) -> dict:
    return {(LAST - timedelta(days=back + i)).isoformat(): (per_day, conv_total / n) for i in range(n)}


def codes(doc: dict) -> list[str]:
    return [w["code"] for w in doc["warning_codes"]]


def main() -> int:
    _shop.use()
    k = thresholds()

    print("[1] given targets: the plan covers the days left")
    d = cp.compute(src(result_target=None), k)
    p = d["plan"]
    check("the inputs say where they came from, the month is the next day's, the last day is the last complete one",
          d["inputs"]["spend"] == {"value": 3000.0, "source": "given"} and d["month"] == "2026-09" and d["last_day"] == "2026-09-03", d["inputs"])
    check("3,000 less the 300 spent in the three days of the month is 2,700 over 27 days: 100 a day with weights of 1 (a flat 100 a day history)",
          p["days_left"] == 27 and p["money_left"] == 2700.0 and p["day"]["day"] == "2026-09-04" and p["day"]["budget"] == 100.0 and p["weights_kind"] == "weighted", p["day"])
    check("the days left add up to the money left", abs(sum(r["budget"] for r in p["days"]) - p["money_left"]) < 0.005 * len(p["days"]))
    check("no creative at all: all exploration, no efficiency, said", "no_performance" in p["flags"] and p["day"]["perform"] == 0.0 and d["efficiency"]["conversions_per_money"] is None
          and d["ad_groups"] is None and d["wallets_now"] == {"explore": 0.0, "perform": 0.0, "other": 0.0}, d)
    check("the document is plain data: it survives json and carries a code for each warning", json.dumps(d) and len(d["warnings"]) == len(d["warning_codes"]))
    ds, dc = account(date(2026, 9, 1), LAST)
    f = cp.compute(src(daily_spend=ds, daily_conv=dc), k)
    check("a short history: flat weights, said in a coded warning", f["plan"]["weights_kind"] == "flat" and "pacing_flat" in codes(f), codes(f))

    print("[2] the wallets and the efficiency")
    proven = {"A": {"wallet": "perform", "group": None, "spend7": 700.0, "conv7": 14.0}}
    w = cp.compute(src(creatives=proven, result_target=20.0), k)
    check("the performance creative earned 14 in 700: 0.02 a unit; 14 still to reach in a month with 6 so far needs 700, a day of 100 gives 25.93 to performance",
          abs(w["efficiency"]["conversions_per_money"] - 0.02) < 1e-9 and w["plan"]["perform_need_total"] == 700.0
          and w["plan"]["day"]["perform"] == 25.93 and w["plan"]["day"]["explore"] == 74.07 and w["wallets_now"] == {"explore": 0.0, "perform": 700.0, "other": 0.0}, w["plan"]["day"])
    s = cp.compute(src(creatives=proven, result_target=100.0), k)
    check("a result out of reach: the shortfall is said and the whole day goes to performance", "shortfall" in s["plan"]["flags"] and s["plan"]["day"]["perform"] == 100.0
          and "pacing_shortfall" in codes(s), codes(s))
    m = cp.compute(src(creatives=proven, result_target=6.0), k)
    check("a result already met: said, performance needs nothing", "result_met" in m["plan"]["flags"] and m["plan"]["day"]["perform"] == 0.0 and "pacing_result_met" in codes(m))
    thin = cp.compute(src(creatives={"A": {**proven["A"], "conv7": 2.0}}, result_target=20.0), k)
    check("two conversions are under the floor (pacing_min_conversions, 3): no efficiency, all exploration, said",
          thin["efficiency"]["conversions_per_money"] is None and "pacing_no_performance" in codes(thin) and thin["plan"]["day"]["perform"] == 0.0, thin["efficiency"])
    noresult = cp.compute(src(creatives={}), k)
    check("with no result target there is nothing to say about the missing performance creatives", "pacing_no_performance" not in codes(noresult), codes(noresult))

    print("[3] the ad groups pay the creatives (the learning stage is the ad group's)")
    groups = {"G1": {"days": group_days(20.0, 4.0), "active": True},                   # 20 a day for 14 days, 4 conversions: judged
              "G2": {"days": group_days(20.0, 1.0), "active": True},                   # the same with 1 conversion: not judged
              "G3": {"days": group_days(20.0, 4.0, back=20), "active": False}}         # stopped and idle for 20 days
    cs = {"C1": {"wallet": "perform", "group": "G1", "spend7": 100.0, "conv7": 4.0},
          "C2": {"wallet": "explore", "group": "G1", "spend7": 30.0, "conv7": 0.0},
          "C3": {"wallet": "perform", "group": "G2", "spend7": 50.0, "conv7": 1.0},
          "C4": {"wallet": "perform", "group": "G3", "spend7": 10.0, "conv7": 0.0},
          "C5": {"wallet": "perform", "group": None, "spend7": 200.0, "conv7": 6.0},
          "C6": {"wallet": None, "group": "G1", "spend7": 5.0, "conv7": 0.0}}
    g = cp.compute(src(creatives=cs, groups=groups, result_target=20.0), k)
    check("three ad groups: one judged (performance), one not judged (exploration), one stopped idle (nobody)",
          g["ad_groups"] == {"count": 3, "wallets": {"perform": 1, "explore": 1, "none": 1}, "by_reason": {"judged": 1, "unjudged": 1, "stopped_idle": 1}}, g["ad_groups"])
    check("a creative is paid by its group only as far as its own wallet allows: C1 and C5 perform, C2 (no verdict of its own) and C3 (unjudged group) explore, C4 and C6 nobody",
          g["wallets_now"] == {"explore": 80.0, "perform": 300.0, "other": 15.0}, g["wallets_now"])
    check("the document says which wallet pays each creative, as the groups leave it (what kit.compute_demand reads): C2 and C3 explore, C4 and C6 nobody",
          g["creative_wallets"] == {"C1": "perform", "C2": "explore", "C3": "explore", "C4": None, "C5": "perform", "C6": None}, g["creative_wallets"])
    check("the efficiency is read from the creatives the groups leave in performance: 10 conversions in 300", g["efficiency"]["performance_creatives"] == 2
          and g["efficiency"]["conversions_7d"] == 10.0 and abs(g["efficiency"]["conversions_per_money"] - 10 / 300) < 1e-12, g["efficiency"])
    g0 = cp.compute(src(creatives=cs, result_target=20.0), k)
    check("with no ad groups handed over the creatives' own wallets pay", g0["ad_groups"] is None and g0["creative_wallets"] == {c: v["wallet"] for c, v in cs.items()} and g0["wallets_now"] == {"explore": 30.0, "perform": 360.0, "other": 5.0}, g0["wallets_now"])

    print("[4] no target, no data, a day to plan")
    n = cp.compute(src(spend_target=None), k)
    check("no spend target: nothing planned, a coded warning, never a guess", n["plan"] is None and "pacing_no_target" in codes(n), codes(n))
    e = cp.compute(cp.Source(daily_spend={}, daily_conv={}, creatives={}, spend_target=100.0), k)
    check("no complete day: nothing planned, said, and no month to name", e["plan"] is None and e["month"] is None and e["last_day"] is None and "pacing_no_data" in codes(e), e)
    ds, dc = account(date(2026, 9, 1), date(2026, 9, 30))
    nm = cp.compute(src(daily_spend=ds, daily_conv=dc), k)
    check("the last day of a month: the month planned is the next one", nm["month"] == "2026-10" and nm["plan"]["days_left"] == 31, nm["month"])
    pd = cp.compute(src(day="2026-09-15"), k)
    check("a day asked for is the day planned", pd["plan"]["day"]["day"] == "2026-09-15", pd["plan"]["day"])
    kept = cp.compute(src(warnings=[messages.msg("pacing_flat", "the pack's own", have=1, need=4)]), k)
    check("the pack's own coded warnings are kept in the document", codes(kept)[0] == "pacing_flat", codes(kept))

    print("[5] a Source the rules cannot read is refused, naming the part")
    bad = {"a month that is not": src(month="2026-9x"), "a day outside the month": src(month="2026-09", day="2026-10-02"), "a day that is not a day": src(day="soon"),
           "a spend target that is a word": src(spend_target="3000"), "a day of the account that is not a day": src(daily_spend={"yesterday": 1.0}),
           "a creative without its group": src(creatives={"A": {"wallet": "perform", "spend7": 1.0, "conv7": 0.0}}),
           "a wallet that is neither": src(creatives={"A": {"wallet": "other", "group": None, "spend7": 1.0, "conv7": 0.0}}),
           "a creative of a group not given": src(creatives={"A": {"wallet": "perform", "group": "GX", "spend7": 1.0, "conv7": 0.0}}, groups=groups),
           "a group day that is not (spend, conversions)": src(groups={"G": {"days": {"2026-09-01": (1.0,)}, "active": True}}),
           "event days that are not days": src(event_days={"2026-09-16"})}
    got = {name: part_refused(s, k) for name, s in bad.items()}
    check("each is compute_input_invalid", all(c == "compute_input_invalid" for c, _ in got.values()), got)
    check("and names the part", [p for _, p in got.values()] == ["month", "day", "day", "spend_target", "daily_spend[yesterday]", "creatives[A]", "creatives[A].wallet",
                                                                 "creatives[A].group", "groups[G].days[2026-09-01]", "event_days"], got)

    print("[6] what the plan adds, passed through (issues #263 and #265)")
    band = cp.compute(src(creatives=proven, result_target=100.0), {**k, "pacing_explore_min_share": 0.2})
    check("the exploration floor in the thresholds reaches the plan: 20 of the 100 explore, the performance given up is said",
          band["plan"]["day"]["explore"] == 20.0 and band["plan"]["day"]["explore_clip"] == "explore_floor" and "explore_floor" in band["plan"]["flags"], band["plan"]["day"])
    ds, dc = account(date(2026, 8, 1), LAST)
    ds["2026-08-26"] = 400.0
    ev = cp.compute(src(daily_spend=ds, daily_conv=dc, event_days={date(2026, 8, 26), date(2026, 9, 16)}), k)
    check("event days reach the plan: the earlier one gives a lift and the one of the month is planned higher",
          ev["plan"]["event_lift_days"] == 1 and ev["plan"]["event_lift"] > 1.0
          and {r["day"]: r for r in ev["plan"]["days"]}["2026-09-16"]["budget"] > {r["day"]: r for r in ev["plan"]["days"]}["2026-09-09"]["budget"], ev["plan"].get("event_lift"))
    check("no event days and the defaults: the plan has no event or clip key", not any(x.startswith("event") for x in d["plan"]) and not any("explore_clip" in r for r in d["plan"]["days"]))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
