#!/usr/bin/env python3
"""kit.creative_portfolio: the portfolio rules on planted numbers.
"""

import math
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import creative_portfolio as portfolio  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402



def main() -> int:
    print("[1] trend and projection")
    t = portfolio.trend([1.0] * 7 + [2.0] * 7)
    check("14 days of 1 then 2: last 14, previous 7, ratio 2", t == {"conv_7d": 14.0, "prev_conv_7d": 7.0, "ratio": 2.0}, t)
    check("under 8 days: no previous week, no ratio", portfolio.trend([1.0] * 5)["ratio"] is None, portfolio.trend([1.0] * 5))
    check("growth is projected flat, an unknown trend too", portfolio.daily_factor(2.0) == 1.0 and portfolio.daily_factor(None) == 1.0)
    check("a weekly ratio of 0.5 is a daily factor of its 7th root", abs(portfolio.daily_factor(0.5) - 0.5 ** (1 / 7)) < 1e-12)
    check("a collapse is floored at 0.05 a week, not zero", abs(portfolio.daily_factor(0.0) - 0.05 ** (1 / 7)) < 1e-12)
    totals = portfolio.project([(10.0, 1.0), (4.0, 0.5 ** (1 / 7))], 14)
    check("a flat one and a halving one: day 7 = 10 + 2, day 14 = 10 + 1", abs(totals[6] - 12.0) < 1e-9 and abs(totals[13] - 11.0) < 1e-9, totals[:7])
    check("the half-life: today 14, falls to 7 only if the flat 10 also falls: here never in 14 days",
          portfolio.half_life(totals, 14.0) is None)
    fall = portfolio.project([(10.0, 0.5 ** (1 / 7))], 20)
    check("one creative halving each week: its half-life is 7 days", portfolio.half_life(fall, 10.0) == 7, portfolio.half_life(fall, 10.0))
    check("no output today: no half-life", portfolio.half_life([0.0, 0.0], 0.0) is None)

    print("[2] the history")
    first = {"a": "2026-08-01", "b": "2026-08-01", "c": "2026-08-02", "d": "2026-09-14"}
    mature = {"a": "2026-08-10", "b": None, "c": "2026-08-14", "d": None}
    h = portfolio.history(first, mature, date(2026, 9, 15), 14)
    check("three creatives are old enough (d is a day old); two matured, after 9 and 12 days: yield 2/3, median 10.5",
          h == {"cohort": 3, "matured": 2, "yield": 2 / 3, "median_days_to_mature": 10.5}, h)
    h0 = portfolio.history({"d": "2026-09-14"}, {"d": None}, date(2026, 9, 15), 14)
    check("no creative old enough: no yield", h0["cohort"] == 0 and h0["yield"] is None, h0)

    print("[3] the replenishment")
    hist = {"cohort": 40, "matured": 8, "yield": 0.2, "median_days_to_mature": 10.0}
    r = portfolio.replenishment(100.0, 5.0, 20, hist, 10)
    check("a gap of 100 conversions, a new mature creative worth 5 a day for the 10 days after its lead: 2 mature, 10 testing, within 10 days",
          r["needed_mature"] == 2 and r["needed_testing"] == 10 and r["enter_within_days"] == 10 and r["flags"] == [], r)
    check("no gap: nothing needed", portfolio.replenishment(-5.0, 5.0, 20, hist, 10)["needed_mature"] is None)
    r = portfolio.replenishment(100.0, 5.0, 8, hist, 10)
    check("fewer days left than the lead time: too_late, no number", r["flags"] == ["too_late"] and r["needed_testing"] is None, r)
    r = portfolio.replenishment(100.0, 5.0, 20, {**hist, "cohort": 3}, 10)
    check("too little history: history_insufficient, no number", r["flags"] == ["history_insufficient"] and r["needed_testing"] is None, r)
    r = portfolio.replenishment(100.0, None, 20, hist, 10)
    check("no mature creative to take a rate from: history_insufficient", r["flags"] == ["history_insufficient"], r)
    check("the needed counts are whole numbers", isinstance(portfolio.replenishment(101.0, 5.0, 20, hist, 10)["needed_mature"], int)
          and math.isfinite(portfolio.replenishment(101.0, 5.0, 20, hist, 10)["needed_testing"]))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
