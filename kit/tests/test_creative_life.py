#!/usr/bin/env python3
"""kit.creative_life: the life of a creative on planted series, one state machine rule at a time.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit.creative_life import Day, Params, replay  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402


P = Params(reach_impressions=1000, reach_floor=200, reach_days=7, learning_conversions=20, doubt_spend=300,
           doubt_extension=1, learning_max_days=14, weak_signal=0.02, decline_rise=0.5, decline_drop=0.5,
           decline_days=3, recover_days=3, end_spend_share=0.05, end_idle_days=14, park_review_days=30)
START = date(2026, 9, 1)


def days(rows, **kw):
    """rows: (spend, impressions, clicks, conversions) per day from START; kw is applied to each Day."""
    return [Day((START + timedelta(days=i)).isoformat(), *r, **kw) for i, r in enumerate(rows)]


def path(life):
    return [(m.frm, m.to, m.reason) for m in life.moves]


def main() -> int:
    print("[1] testing")
    life = replay(days([(10, 400, 5, 0)] * 3), P)
    check("1200 impressions in 3 days: learning, so nothing is waited for on reach", life.state == "learning", life.waiting)
    life = replay(days([(10, 400, 5, 0)] * 2), P)
    check("800 impressions: still testing, waiting for 1000", life.state == "testing"
          and life.waiting["impressions"] == [800, 1000], (life.state, life.waiting))
    life = replay(days([(10, 600, 5, 0)] * 2), P)
    check("1200 impressions: learning, by reach", path(life) == [("testing", "learning", "reach")], path(life))
    life = replay(days([(10, 30, 1, 0), (10, 30, 1, 1)]), P)
    check("a conversion with few impressions: learning, converted (it found people)",
          path(life) == [("testing", "learning", "converted")], path(life))
    life = replay(days([(5, 20, 0, 0)] * 7), P)
    check("7 delivery days under the floor: parked, low_reach, due for review in 30 days",
          path(life) == [("testing", "parked", "low_reach")] and life.review_due == (START + timedelta(days=36)).isoformat(),
          (path(life), life.review_due))
    rows = [(5, 20, 0, 0)] * 5 + [(0, 0, 0, 0)] + [(5, 20, 0, 0)]
    check("a day with no delivery is not a delivery day: 7 days with a gap is not yet parked",
          replay(days(rows), P).state == "testing")
    d = days([(5, 20, 0, 0)] * 8)
    d = [Day(x.date, x.spend, x.impressions, x.clicks, x.conversions, blocked="review") if i < 3 else x for i, x in enumerate(d)]
    check("three blocked days do not count toward low reach: still testing after 5 delivery days",
          replay(d, P).state == "testing", replay(d, P).state)

    print("[2] learning")
    life = replay(days([(10, 600, 20, 0), (10, 600, 20, 10), (10, 600, 20, 10)]), P)
    check("20 conversions: mature, learned", path(life)[-1] == ("learning", "mature", "learned"), path(life))
    life = replay([Day((START + timedelta(days=i)).isoformat(), 10, 600, 20, 1, platform_learning_over=(i == 2)) for i in range(3)], P)
    check("the platform's learning flag: mature, platform_learned",
          path(life)[-1] == ("learning", "mature", "platform_learned"), path(life))
    life = replay(days([(100, 600, 20, 0)] * 4), P)
    check("300 spent with no conversion: doubt, no_conversion", path(life)[-1] == ("learning", "doubt", "no_conversion"), path(life))
    rows = [(10, 600, 20, 0)] + [(1, 5, 0, 1 if i == 0 else 0) for i in range(16)]
    life = replay(days(rows), P)
    check("slow (conversions but 14 delivery days in learning): doubt, slow", path(life)[-1][1:] == ("doubt", "slow"), path(life))

    print("[3] doubt")
    base = [(100, 600, 20, 0)] * 4                      # into doubt at 400 spent
    life = replay(days(base + [(10, 100, 10, 1)]), P)
    check("a conversion in the extension: back to learning", path(life)[-1] == ("doubt", "learning", "converted"), path(life))
    life = replay(days(base + [(100, 600, 20, 0)] * 3), P)
    check("the extension spent, none, a healthy signal: parked, no_conversion (not ended)",
          path(life)[-1] == ("doubt", "parked", "no_conversion"), path(life))
    life = replay(days([(100, 600, 6, 0)] * 7), P)
    check("the extension spent, none, a weak signal: ended, weak_creative", path(life)[-1] == ("doubt", "ended", "weak_creative"), path(life))
    life = replay(days([(100, 600, 6, 0)] * 5), P)
    check("evidence floor: a weak signal alone ends nothing before the extension is spent", life.state == "doubt", path(life))
    life = replay(days(base + [(100, 600, 20, 0)] * 3), Params(**{**P.__dict__, "weak_signal": None}))
    check("no signal to read (weak_signal None): parked, never ended", life.state == "parked", path(life))

    print("[4] mature and declining")
    mature = [(100, 1000, 30, 4)] * 8                    # 32 conversions: mature after day 5, 100/day, cost 25
    life = replay(days(mature), P)
    check("mature with a peak", life.state == "mature", path(life))
    life = replay(days(mature + [(100, 1000, 30, 1)]), P)
    check("one bad day (cost up) moves nothing", life.state == "mature", path(life))
    life = replay(days(mature + [(100, 1000, 30, 0)] * 6), P)
    check("the 7-day cost per conversion past 1.5x its best for 3 days: declining, worse",
          path(life)[-1] == ("mature", "declining", "worse"), path(life))
    life = replay(days(mature + [(30, 300, 10, 1)] * 8), P)
    check("the 7-day spend under half its peak for 3 days: declining", life.state == "declining", path(life))
    rec = mature + [(100, 1000, 30, 0)] * 6 + [(100, 1000, 30, 8)] * 10
    life = replay(days(rec), P)
    check("recovery for 3 days: back to mature, recovered", path(life)[-1] == ("declining", "mature", "recovered"), path(life))
    life = replay(days(mature + [(30, 300, 10, 1)] * 8 + [(0.5, 10, 0, 0)] * 8), P)
    check("the 7-day spend under 5% of the peak: ended, faded", path(life)[-1] == ("declining", "ended", "faded"), path(life))
    life = replay(days(mature + [(30, 300, 10, 1)] * 8 + [(0, 0, 0, 0)] * 14), P)
    check("14 days without delivery: ended", life.state == "ended", path(life))
    longer = replay(days(mature + [(30, 300, 10, 1)] * 8 + [(0, 0, 0, 0)] * 30), P)
    check("an ended creative does not move again", len(longer.moves) == len(life.moves) and longer.state == "ended",
          (path(life), path(longer)))

    print("[5] blocked days, incomplete days, overrides")
    life = replay(days([(5, 100, 2, 0)] * 2) + [Day((START + timedelta(days=2 + i)).isoformat(), blocked="off") for i in range(14)], P)
    check("switched off for 14 days before it was judged: parked, stopped_unjudged",
          path(life)[-1] == ("testing", "parked", "stopped_unjudged"), path(life))
    life = replay(days([(5, 100, 2, 0)] * 2) + [Day((START + timedelta(days=2 + i)).isoformat(), blocked="review") for i in range(30)], P)
    check("rejected by review for 30 days: still testing, never parked or ended for it", life.state == "testing"
          and life.blocked_now == "review", (path(life), life.blocked_now))
    life = replay(days(mature + [(30, 300, 10, 1)] * 8) + [Day((START + timedelta(days=16 + i)).isoformat(), blocked="budget_cap") for i in range(30)], P)
    check("a blocked declining creative is not ended for the idle days", life.state == "declining", path(life))
    d = days([(100, 600, 20, 0)] * 3)
    check("the third day counts when complete: doubt", replay(d, P).state == "doubt", path(replay(d, P)))
    d[-1] = Day(d[-1].date, 100, 600, 20, 0, complete=False)
    check("an incomplete day is not read: no doubt yet", replay(d, P).state == "learning", path(replay(d, P)))
    life = replay(days([(5, 20, 0, 0)] * 8), P, overrides=[((START + timedelta(days=7)).isoformat(), "testing")])
    check("an override sets the state on its day (parked -> testing)", path(life)[-1] == ("parked", "testing", "override"), path(life))

    print("[6] totals and the shape")
    life = replay(days([(10, 600, 20, 1)] * 3), P)
    check("totals are the sums over the counted days", life.totals["conversions"] == 3 and life.totals["spend"] == 30
          and life.days_counted == 3, life.totals)
    check("the first day it was seen is when a creative started", replay([], P).state == "testing" and replay([], P).since is None)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
