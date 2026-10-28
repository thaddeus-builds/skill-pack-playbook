#!/usr/bin/env python3
"""kit.creative_life: the life of a creative on planted series, one state machine rule at a time.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import messages  # noqa: E402
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
    _shop.use()
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
    print("[7] the last days are understated: read_cost")
    SEEN = [0.7, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05]          # the share of a day's conversions visible, the oldest tail day first

    def tail(true):
        """A creative whose days are `true` conversions each, the last 7 seen at SEEN of it: (days, {date: share})."""
        share = {}
        rows = []
        for i, t in enumerate(true):
            f = SEEN[i - (len(true) - 7)] if i >= len(true) - 7 else 1.0
            share[(START + timedelta(days=i)).isoformat()] = f
            rows.append((100, 1000, 30, t * f))
        return days(rows), share

    def reader(share):
        """What a pack builds from its curve: the window's conversions read at their share, the cost with a quarter either way while any day is unsettled."""
        def read(window):
            est = sum(d.conversions / share[d.date] for d in window)
            if est <= 0:
                return None
            cost = sum(d.spend for d in window) / est
            return (cost, cost, cost) if all(share[d.date] == 1.0 for d in window) else (cost, cost * 0.75, cost * 1.25)
        return read
    steady, share = tail([4] * 30)
    seen = replay(steady, P)
    check("a steady creative (a true cost of 25) is declining on its understated tail as it was seen", path(seen)[-1] == ("mature", "declining", "worse") and seen.moves[-1].date == steady[-1].date, path(seen))
    read = replay(steady, P, read_cost=reader(share))
    check("read on what the tail will come to it stays mature: no move after it learned", read.state == "mature" and path(read) == path(replay(steady[:-7], P)), path(read))
    check("and it is the same life as the settled numbers give", read.state == replay(days([(100, 1000, 30, 4)] * 30), P).state)
    old, _ = tail([4] * 20 + [1.5] * 10)
    check("a cost that really rose, in days older than the unsettled ones, is declining with or without the function", path(replay(old, P, read_cost=reader(share)))[-1] == ("mature", "declining", "worse"), path(replay(old, P, read_cost=reader(share))))
    new, sh2 = tail([4] * 23 + [0.4] * 7)
    got = replay(new, P, read_cost=reader(sh2))
    check("a rise that only the tail shows and that the interval backs (a true cost of 250 over the last 7 days, the line 37.5) is declining", path(got)[-1] == ("mature", "declining", "worse"), (path(got), got.moves[-1].read))
    check("its move says the cost it was read at, which is the estimate and not the cost as seen", got.moves[-1].read["cost7"] < 400 and got.moves[-1].read["cost7"] > 100
          and got.moves[-1].read["cost7"] != replay(new, P).moves[-1].read["cost7"], got.moves[-1].read)
    mid, sh3 = tail([4] * 23 + [2.2] * 7)
    check("a rise whose interval straddles the line (a true cost of 45.5 against 37.5, from 34 to 57) is no worse day: declining as seen, mature when read on the estimate",
          path(replay(mid, P))[-1] == ("mature", "declining", "worse") and replay(mid, P, read_cost=reader(sh3)).state == "mature", (path(replay(mid, P)), path(replay(mid, P, read_cost=reader(sh3)))))
    lucky_at = steady[27].date

    def lucky(window):
        return (10.0, 10.0, 40.0) if window[-1].date == lucky_at else None
    flat = days([(100, 1000, 30, 4)] * 31)
    check("a best cost is never set lower than the interval's high edge: one lucky reading (10, 10 to 40) does not make the later cost of 25 a decline",
          replay(flat, P, read_cost=lucky).state == "mature", path(replay(flat, P, read_cost=lucky)))
    check("a function with no answer reads the window as seen: the same moves as with none", [(m.date, m.frm, m.to, m.reason) for m in replay(steady, P, read_cost=lambda w: None).moves]
          == [(m.date, m.frm, m.to, m.reason) for m in seen.moves])

    def refused(fn):
        try:
            replay(steady, P, read_cost=fn)
        except Exception as e:  # noqa: BLE001
            f = messages.failure(e)
            return f["code"], f["params"].get("part")
        return None, None
    bad = {"a number": lambda w: 25.0, "a cost outside its interval": lambda w: (25.0, 30.0, 40.0), "text": lambda w: ("a", "b", "c"), "a flag": lambda w: (True, True, True)}
    got = {n: refused(f) for n, f in bad.items()}
    check("an answer that is not None or (cost, low, high) with low <= cost <= high is refused, naming read_cost", all(v == ("compute_input_invalid", "read_cost") for v in got.values()), got)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
