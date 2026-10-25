#!/usr/bin/env python3
"""kit.pacing, on planted months: the video-ads skill pack's cases, then the paid-search skill pack's monthly cap.

  * flat until each weekday has enough weeks, then weighted by the account's own weekdays (mean 1);
  * the day's budget divides the money left over the days left by weight; the money already spent comes off first;
  * the perform wallet takes what the result still to reach needs at the proven creatives' efficiency, never more than the
    day's budget; explore is the rest and may be zero; with no efficiency to read it is all explore;
  * flags, not floors: shortfall, result met, no performance, flat;
  * a monthly cap: the golden month (17,989 of 30,000 on the 20th, 1,285 a day lately), the dates the warn line and the cap
    are crossed, a missing day makes the spend a lower bound (only a crossing already shown stands), over the cap, today's budget.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import pacing  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402



def series(start: date, days: int, fn) -> dict[str, float]:
    return {(start + timedelta(days=i)).isoformat(): fn(start + timedelta(days=i)) for i in range(days)}


def main() -> int:
    print("[1] the weekday weights")
    flat = series(date(2026, 9, 1), 10, lambda d: 100.0)
    w, kind, least = pacing.weekday_weights(flat, date(2026, 9, 10), 8, 4)
    check("ten days: flat (each weekday under 4 weeks), the least weekday count is reported",
          kind == "flat" and w == [1.0] * 7 and least == 1, (kind, w, least))
    wk = series(date(2026, 8, 3), 56, lambda d: 120.0 if d.weekday() == 2 else 100.0)     # Wednesdays 20% over
    w, kind, least = pacing.weekday_weights(wk, date(2026, 9, 27), 8, 4)
    check("eight weeks of data: weighted, mean 1, a Wednesday heavier than a Monday",
          kind == "weighted" and abs(sum(w) / 7 - 1) < 1e-9 and w[2] > w[0] and least == 8, (kind, w, least))
    check("an exact ratio: 120 against a mean of 102.857", abs(w[2] - 120 / (sum([100.0] * 6 + [120.0]) / 7)) < 1e-9, w)

    print("[2] the day's budget")
    ds = series(date(2026, 10, 1), 15, lambda d: 100.0)
    p = pacing.plan("2026-10", 3100.0, None, ds, {}, date(2026, 10, 15), None, 8, 4)
    check("1,500 spent of 3,100 over 15 days: 1,600 left over 16 days = 100 a day, flat",
          p["money_left"] == 1600.0 and p["days_left"] == 16 and p["day"]["budget"] == 100.0 and "flat" in p["flags"], p)
    check("the days left add up to the money left", abs(sum(r["budget"] for r in p["days"]) - 1600.0) < 0.2, sum(r["budget"] for r in p["days"]))
    check("no result target: all of the day is explore", p["day"]["perform"] == 0.0 and p["day"]["explore"] == 100.0, p["day"])
    p = pacing.plan("2026-10", 3100.0, None, ds, {}, date(2026, 10, 31), None, 8, 4)
    check("the month's last day done: nothing left to plan", p["days_left"] == 0 and p["day"] is None, p)
    wkly = series(date(2026, 8, 3), 56, lambda d: 120.0 if d.weekday() == 2 else 100.0)
    p = pacing.plan("2026-09", 6000.0, None, wkly, {}, date(2026, 9, 27), None, 8, 4, day=date(2026, 9, 30))
    mon = next(r for r in p["days"] if r["weekday"] == "Mon")
    wed = next(r for r in p["days"] if r["weekday"] == "Wed")
    check("a Wednesday gets more than a Monday by their weights", wed["budget"] > mon["budget"]
          and abs(wed["budget"] / mon["budget"] - wed["weight"] / mon["weight"]) < 0.01, (wed, mon))

    print("[3] the two wallets")
    conv = series(date(2026, 10, 1), 15, lambda d: 2.0)
    p = pacing.plan("2026-10", 3100.0, 100.0, ds, conv, date(2026, 10, 15), 0.05, 8, 4)
    check("70 still to reach at 0.05 a unit of money needs 1,400 of 1,600: 87.5 a day to perform, the rest explore",
          p["result_left"] == 70.0 and p["perform_need_total"] == 1400.0 and p["day"]["perform"] == 87.5
          and p["day"]["explore"] == 12.5 and "shortfall" not in p["flags"], p)
    p = pacing.plan("2026-10", 3100.0, 100.0, ds, conv, date(2026, 10, 15), 0.02, 8, 4)
    check("at 0.02 it would need 3,500 and 1,600 is left: shortfall, the whole day goes to perform, explore is zero",
          "shortfall" in p["flags"] and p["day"]["perform"] == p["day"]["budget"] and p["day"]["explore"] == 0.0, p)
    p = pacing.plan("2026-10", 3100.0, 30.0, ds, conv, date(2026, 10, 15), 0.05, 8, 4)
    check("the result already met: result_met, perform needs nothing", "result_met" in p["flags"] and p["day"]["perform"] == 0.0, p)
    p = pacing.plan("2026-10", 3100.0, 100.0, ds, conv, date(2026, 10, 15), None, 8, 4)
    check("no efficiency to read (a new account): no_performance, all explore",
          "no_performance" in p["flags"] and p["day"]["perform"] == 0.0 and p["perform_need_total"] is None, p)

    print("[4] the pace")
    p = pacing.plan("2026-10", 3100.0, None, ds, {}, date(2026, 10, 15), None, 8, 4)
    check("15 of 31 even days = 1,500 of 3,100 against an even 1,500: pace 1.0", p["pace_ratio"] == 1.0, p["pace_ratio"])
    ds2 = series(date(2026, 10, 1), 15, lambda d: 200.0)
    p = pacing.plan("2026-10", 3100.0, None, ds2, {}, date(2026, 10, 15), None, 8, 4)
    check("spending twice as fast: pace 2.0 and the days left share what remains", p["pace_ratio"] == 2.0 and p["money_left"] == 100.0, p)

    print("[5] a monthly cap")
    sep = date(2026, 9, 1)
    gold = {sep + timedelta(days=i): (700.0 if i < 12 else 594.0 if i == 12 else 1285.0) for i in range(20)}
    c = pacing.cap_status(sep, date(2026, 9, 20), date(2026, 9, 30), gold, 30000.0, 0.8, 7)
    check("the golden month: 17,989 spent, 1,285 a day lately, 30,839 projected",
          c["spent"] == 17989.0 and c["run_rate"] == 1285.0 and c["projected"] == 30839.0, c)
    check("projected over the cap, nothing crossed yet: projected_over", c["status"] == "projected_over" and c["missing_days"] == [], c)
    th = {t["name"]: t for t in c["thresholds"]}
    check("the warn line (24,000) is crossed on the 25th, the cap on the 30th, at that rate",
          th["warn"]["state"] == "on" and th["warn"]["date"] == date(2026, 9, 25)
          and th["cap"]["state"] == "on" and th["cap"]["date"] == date(2026, 9, 30), th)
    check("today's budget: 12,011 left over the 10 days after the 20th", abs(c["today_budget"] - 1201.1) < 1e-9 and not c["upper_bound"], c)
    low = pacing.cap_status(sep, date(2026, 9, 20), date(2026, 9, 30), {d: v for d, v in gold.items() if d != date(2026, 9, 5)},
                            30000.0, 0.8, 7)
    lth = {t["name"]: t["state"] for t in low["thresholds"]}
    check("a missing day: the spend is a lower bound, nothing not yet crossed is known, never `ok`",
          low["status"] == "unknown" and lth == {"warn": "unknown", "cap": "unknown"} and low["upper_bound"] and len(low["missing_days"]) == 1, low)
    cross = pacing.cap_status(sep, date(2026, 9, 20), date(2026, 9, 30), {d: v for d, v in gold.items() if d != date(2026, 9, 5)},
                              15000.0, 0.8, 7)
    check("a lower bound that already passes a line proves the crossing", cross["status"] == "over_cap"
          and {t["name"]: t["state"] for t in cross["thresholds"]} == {"warn": "reached", "cap": "reached"}, cross)
    ok = pacing.cap_status(sep, date(2026, 9, 20), date(2026, 9, 30), gold, 60000.0, 0.8, 7)
    check("far under the cap and the projection: ok", ok["status"] == "ok" and ok["warn_reason"] is None, ok)
    warn_now = pacing.cap_status(sep, date(2026, 9, 20), date(2026, 9, 30), gold, 21000.0, 0.8, 7)
    check("spent past the warn line, not the cap: warn because of the spend", warn_now["status"] == "warn" and warn_now["warn_reason"] == "spent", warn_now)
    warn_proj = pacing.cap_status(sep, date(2026, 9, 20), date(2026, 9, 30), gold, 38000.0, 0.8, 7)
    check("a projection past the warn line only: warn because of the projection", warn_proj["status"] == "warn" and warn_proj["warn_reason"] == "projected", warn_proj)
    over = pacing.cap_status(sep, date(2026, 9, 20), date(2026, 9, 30), gold, 10000.0, 0.8, 7)
    check("over the cap: today's budget is 0", over["status"] == "over_cap" and over["today_budget"] == 0.0, over)
    last_day = pacing.cap_status(sep, date(2026, 9, 30), date(2026, 9, 30), {**gold, **{date(2026, 9, d): 1285.0 for d in range(21, 31)}}, 40000.0, 0.8, 7)
    check("on the month's last day there is nothing left to budget", last_day["today_budget"] is None and last_day["days_left"] == 0, last_day)
    check("reach: no rate, no crossing; a crossing after the month's end is not this month's",
          pacing.reach(0.0, 10.0, 0.0, date(2026, 9, 1), date(2026, 9, 30)) == ("not_reached", None)
          and pacing.reach(0.0, 1000.0, 1.0, date(2026, 9, 1), date(2026, 9, 30)) == ("not_reached_this_month", None), None)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
