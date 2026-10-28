#!/usr/bin/env python3
"""kit.compute_portfolio: the portfolio document over hand-made creatives (invented DEMO ids, invented numbers). The cases are the video-ads skill pack's
document test: the states add up to the creatives, a new account has nothing to project, a result gives the gap and what closing it takes, a short history
gives no number of new creatives and says why, a bad part refused. The numbers are worked out by hand.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import compute_life as cl, compute_portfolio as cp, creative_life as life, messages  # noqa: E402
from kit.registry import Thresholds  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

START = date(2026, 9, 1)


def thresholds() -> dict:
    empty = Path(tmp_dir("compute-portfolio-")) / "constants.tsv"
    empty.write_text("\t".join(["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why"]) + "\n", encoding="utf-8")
    return Thresholds(empty).load()


def days(n, spend=20.0, imp=400, clicks=8, conv=0.0, start=START) -> list:
    return [life.Day(date=(start + timedelta(days=i)).isoformat(), spend=spend, impressions=imp, clicks=clicks, conversions=conv) for i in range(n)]


def account(winners=6, duds=6, young=True) -> dict:
    """Winners earn 3 a day from the first day (mature on the 7th day); duds spend and never convert; a young one has two days."""
    out = {f"WIN-{i}": {"days": days(30, conv=3.0)} for i in range(winners)}
    out.update({f"DUD-{i}": {"days": days(30, spend=5.0, imp=50, clicks=0)} for i in range(duds)})
    if young:
        out["NEW"] = {"days": days(2, imp=50, start=date(2026, 9, 29))}
    return out


def src(creatives=None, **kw) -> cp.Source:
    return cp.Source(cl.Source(account() if creatives is None else creatives), **kw)


def codes(doc) -> list:
    return [w["code"] for w in doc["warning_codes"]]


def refused(s, k, **kw):
    try:
        cp.compute(s, k, **kw)
    except Exception as e:  # noqa: BLE001
        f = messages.failure(e)
        return f["code"], f["params"].get("part")
    return None, None


def main() -> int:
    _shop.use()
    k = thresholds()

    print("[1] the states and the projection")
    d = cp.compute(src(), k)
    st = d["states"]
    check("the states add up to the creatives the life document lists", sum(s["creatives"] for s in st.values()) == 13 == len(cl.compute(cl.Source(account()), k)["rows"]), st)
    check("six winners: mature, 7 days x 20 spent and 7 days x 3 converted each; they became mature on the 7th day, 23 days before the last one",
          st["mature"] == {"creatives": 6, "spend_7d": 840.0, "conversions_7d": 126.0, "mean_age_days": 23.0} and st["testing"]["creatives"] == 1, st["mature"])
    check("as of the last complete day; the month is the next day's", d["as_of"] == "2026-09-30" and d["month"] == "2026-10" and d["horizon_days"] == 84)
    pf = {p["creative"]: p for p in d["performance"]}
    check("only the creatives paid from the performance wallet are projected: the six winners, 21 conversions in 7 days each, flat (ratio 1)",
          sorted(pf) == [f"WIN-{i}" for i in range(6)] and all(p["conv_7d"] == 21.0 and p["prev_conv_7d"] == 21.0 and p["ratio"] == 1.0 and p["daily_now"] == 3.0 and p["daily_factor"] == 1.0 for p in pf.values()), d["performance"][:1])
    check("six at 3 a day make 18 a day now and 126 a week, twelve weeks by default; flat earners never halve",
          d["projection"]["daily_now"] == 18.0 and len(d["projection"]["by_week"]) == 12 and d["projection"]["by_week"][0] == {"week": 1, "conversions": 126.0}
          and d["projection"]["half_life_days"] is None, d["projection"])
    check("the horizon is respected", len(cp.compute(src(), k, horizon=28)["projection"]["by_week"]) == 4)
    fade_days = days(23, conv=4.0) + days(7, conv=2.0, start=START + timedelta(days=23))
    f = cp.compute(src({"WIN-0": {"days": days(30, conv=3.0)}, "FADE": {"days": fade_days}}), k)
    fp = {p["creative"]: p for p in f["performance"]}
    check("a creative whose last 7 days earned half the 7 before: ratio 0.5, 2 a day now, a factor under 1, beside a flat one that stays at 1",
          fp["FADE"]["ratio"] == 0.5 and fp["FADE"]["daily_now"] == 2.0 and fp["FADE"]["daily_factor"] < 1.0 and fp["WIN-0"]["daily_factor"] == 1.0, fp["FADE"])
    check("beside a flat earner the total never halves in twelve weeks, so there is no half-life", f["projection"]["half_life_days"] is None, f["projection"])
    alone = cp.compute(src({"FADE": {"days": fade_days}}), k)
    check("a portfolio of the fading creative alone: a factor of 0.9057 a day halves in a week (0.9057 to the 7th is 0.5)",
          alone["projection"]["half_life_days"] is not None and 6 <= alone["projection"]["half_life_days"] <= 8 and abs(alone["performance"][0]["daily_factor"] ** 7 - 0.5) < 0.01, alone["projection"])

    print("[2] the history, the month, and what closing the gap takes")
    h = d["history"]
    check("twelve creatives old enough, six became mature, a yield of one half, after 6 days at the median (the 1st to the 7th)", h == {"cohort": 12, "matured": 6, "yield": 0.5, "median_days_to_mature": 6.0}, h)
    d2 = cp.compute(src(result_target=2000.0), k)
    mv, rp = d2["month_view"], d2["replenishment"]
    check("nothing converted in October yet: 2,000 still to reach; the six earners give 18 x 31 = 558; the gap is 1,442 over 31 days",
          mv == {"month": "2026-10", "result_left": 2000.0, "projected": 558.0, "gap": 1442.0, "days_left": 31}, mv)
    check("to close it: a mature creative earns 3 a day for the 25 days left after the 6 it takes, so ceil(1442 / 75) = 20 mature, and at a yield of a half 40 new ones, entering within 25 days",
          (rp["gap"], rp["needed_mature"], rp["needed_testing"], rp["lead_days"], rp["enter_within_days"], rp["flags"]) == (1442.0, 20, 40, 6.0, 25, []), rp)
    check("the gap is warned, coded", "portfolio_gap" in codes(d2), codes(d2))
    sep = cp.compute(src(month="2026-09", result_target=600.0), k)
    check("a month already over: the 540 converted in September come off (6 x 90), 60 are left, no day remains, so new creatives are too late, and it is said",
          sep["month_view"] == {"month": "2026-09", "result_left": 60.0, "projected": 0.0, "gap": 60.0, "days_left": 0}
          and sep["replenishment"]["flags"] == ["too_late"] and {"portfolio_gap", "portfolio_too_late"} <= set(codes(sep)), sep["month_view"])
    met = cp.compute(src(month="2026-09", result_target=500.0), k)
    check("a result already reached: nothing left, no gap, no warning, no number of new creatives", met["month_view"]["result_left"] == 0.0 and met["month_view"]["gap"] == 0.0
          and met["replenishment"]["needed_mature"] is None and met["replenishment"]["flags"] == [] and "portfolio_gap" not in codes(met), met["month_view"])
    check("no result: the states are there and the month view and replenishment are not", d["month_view"] is None and d["replenishment"] is None)
    few = cp.compute(src(account(winners=3, duds=0, young=False), result_target=2000.0), k)
    check("a short history (three creatives, ten needed): no number of new creatives, said, the gap warned too",
          few["replenishment"]["needed_testing"] is None and "history_insufficient" in few["replenishment"]["flags"]
          and {"portfolio_gap", "portfolio_history_insufficient"} <= set(codes(few)), codes(few))

    print("[3] a new account, no creative at all, a Source the rules cannot read")
    young = cp.compute(src(account(winners=0, duds=0)), k)
    check("no creative in a performance state: nothing to project, said", young["performance"] == [] and young["projection"]["daily_now"] == 0 and young["projection"]["half_life_days"] is None
          and "portfolio_no_performance" in codes(young), codes(young))
    none = cp.compute(src({}, month="2026-10", result_target=100.0), k)
    check("no creative: no day, no states, no month view even with a result, and the month asked for is kept", none["as_of"] is None and none["states"] == {} and none["month"] == "2026-10"
          and none["month_view"] is None and none["history"]["cohort"] == 0 and "portfolio_no_performance" in codes(none), none)
    check("no creative and no month named: no month", cp.compute(src({}), k)["month"] is None)
    check("the document is plain data and every warning has a code", json.dumps(d2) and len(d2["warnings"]) == len(d2["warning_codes"]))
    bad = {"a horizon under a week": ("horizon", dict(s=src(), kw={"horizon": 3})), "a horizon over a year": ("horizon", dict(s=src(), kw={"horizon": 400})),
           "a month that is not": ("month", dict(s=src(month="nope"), kw={})), "a result that is a word": ("result_target", dict(s=src(result_target="40"), kw={})),
           "a creative without days": ("creatives[X]", dict(s=src({"X": {"label": "x"}}), kw={}))}
    got = {name: refused(v["s"], k, **v["kw"]) for name, (_, v) in bad.items()}
    check("each is compute_input_invalid, naming its part", all(c == "compute_input_invalid" for c, _ in got.values()) and [p for _, p in got.values()] == [x for x, _ in bad.values()], got)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
