#!/usr/bin/env python3
"""kit.lifecycle: the rules of a campaign's life, each state reached by hand-made days in the order the module documents, and the
reason says why. Every number is synthetic."""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import lifecycle  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

P = lifecycle.Params(window_days=14, learning_days=7, judge_spend=500, min_conversions=3, earn_margin=0.15, use_share=0.85, decline_drop=0.25,
                    issue_share=0.30, end_idle_days=14, budget_step=0.20)
AS_OF = "2026-10-15"
END = date.fromisoformat(AS_OF)


def days(n, spend=100.0, roas=4.0, conv=5.0, back=0, impressions=20000.0, ctr=0.01):
    """n consecutive days ending `back` days before AS_OF: (spend, revenue, purchases, impressions, clicks) each."""
    return {(END - timedelta(days=back + i)).isoformat(): (spend, spend * roas, conv, impressions, impressions * ctr) for i in range(n)}


def verdict(status="active", d=None, budget=None, bench=4.0, **kw):
    return lifecycle.judge(lifecycle.Campaign("c", status, d if d is not None else {}, budget, **kw), AS_OF, P, bench)


def main() -> int:
    v = verdict(d={})
    check("no spend and active: setup", (v.state, v.reason) == ("setup", "no_spend_yet"), v)
    v = verdict(status="paused", d={})
    check("no spend and stopped: ended, never_ran", (v.state, v.reason) == ("ended", "never_ran"), v)
    v = verdict(d=days(40))
    check("a settled campaign near its benchmark: steady", (v.state, v.reason) == ("steady", "near_benchmark"), v)
    v2 = verdict(d=days(40, roas=2.5))
    check("well under its benchmark and not falling: lagging , never 'steady near the benchmark'", (v2.state, v2.reason) == ("lagging", "below_benchmark"), v2)
    check("its window and the one before are read apart", v.window["spend"] == 1400 and v.previous["spend"] == 1400, (v.window, v.previous))
    v = verdict(d=days(40, roas=5.0), budget=100.0)
    check("a return 15% over the benchmark that spends its budget: earning", (v.state, v.reason) == ("earning", "above_benchmark")
          and v.use_share == 1.0, v)
    v = verdict(d=days(40, roas=5.0), budget=500.0)
    check("the same return that spends a fifth of its budget: earning, creative_limited", (v.state, v.reason) ==
          ("earning", "creative_limited") and round(v.use_share, 2) == 0.2, v)
    v = verdict(d=days(40, roas=5.0), bench=None)
    check("no benchmark to compare with: nothing is earning", (v.state, v.reason) == ("steady", "no_benchmark"), v)
    v = verdict(d={**days(14, roas=2.0), **days(14, roas=4.0, back=14), **days(12, roas=4.0, back=28)})
    check("a return that fell by a quarter and is not above the benchmark: declining (not fatigue: no sign the creatives wore out)",
          (v.state, v.reason) == ("declining", "return_falling"), v)
    v = verdict(d={**days(14, roas=6.0), **days(14, roas=9.0, back=14), **days(12, roas=9.0, back=28)})
    check("a return that fell by a third but is still far above the benchmark is earning, not declining (7.37 against 4.43)",
          v.state == "earning", v)
    v = verdict(d=days(3))
    check("three days old: learning", (v.state, v.reason) == ("learning", "new"), v)
    v = verdict(d=days(30, conv=1.0))
    check("a month old with 30 conversions in all (under the old 50): not 'learning', not 'slow': judged on its window", v.state != "learning"
          and v.reason != "slow", v)
    v = verdict(d=days(40, conv=0.0))
    check("a window with no conversion: unjudged (thin), the only place a lack of conversions shows", (v.state, v.reason) == ("unjudged", "thin"), v)
    v = verdict(d=days(40, spend=10.0))
    check("a window under the judging spend: unjudged (thin)", (v.state, v.reason) == ("unjudged", "thin"), v)
    v = verdict(d=days(40), issue_share=0.5)
    check("half its recent spend on ads with issues: blocked", (v.state, v.reason) == ("blocked", "ads_with_issues"), v)
    v = verdict(status="disapproved", d=days(40))
    check("disapproved: blocked", (v.state, v.reason) == ("blocked", "disapproved"), v)
    v = verdict(status="paused", d=days(40, back=20))
    check("stopped and idle for 20 days: ended (stopped_idle)", (v.state, v.reason) == ("ended", "stopped_idle"), v)
    v = verdict(status="paused", d=days(40, back=3))
    check("stopped three days ago is not over yet: judged on its days", v.state in ("steady", "earning", "declining", "fatigued", "lagging"), v)
    v = verdict(status=None, d=days(40))
    check("a status the export never gave: active if it spent in the last two days", v.state == "steady", v)

    print("[1b] fatigue: once good, now bad, on the relative click-through rate")
    flat = [1.0] * 12
    worn = [1.0, 1.0, 1.4, 1.5, 1.4, 1.3, 1.1, 1.0, 0.9, 0.8, 0.7, 0.6]                        # a good run, then it wears out
    acct = [(50000.0, 500.0)] * 12
    own = lambda rel: [(imp, imp * 0.01 * r) for (imp, _), r in zip(acct, rel)]
    f = lifecycle.fatigue(lifecycle.relative_ctr(own(worn), acct, P), P)
    check("a campaign that was in the best 20% of its history and is now in the worst 20%, well under its peak: fatigued", f and f["fatigued"], f)
    check("the same series flat: not fatigued", not lifecycle.fatigue(lifecycle.relative_ctr(own(flat), acct, P), P)["fatigued"])
    f = lifecycle.fatigue(lifecycle.relative_ctr(own([1.0, 1.0, 1.3, 1.0, 1.0, 1.0, 1.0, 1.0, 0.8, 1.0, 1.0, 0.95]), acct, P), P)
    check("one lucky week is not a peak (the peak is the mean of at least two best weeks): a small dip after it is not fatigue", f and not f["fatigued"], f)
    check("under eight readings: no reading, never a guess", lifecycle.fatigue(lifecycle.relative_ctr(own(worn[:6]), acct[:6], P), P) is None)
    thin = [(1000.0, 10.0)] * 12
    check("weeks under the impression floor are no reading", all(v is None for v in lifecycle.relative_ctr(thin, acct, P)))
    thin_w, fat_w = (lifecycle.relative_ctr([(i, c)], [(50000.0, 500.0)], P)[0] for i, c in ((5000.0, 25.0), (50000.0, 250.0)))
    check("a thin week is pulled toward the account's rate (shrunk): the same half-rate on a tenth of the volume reads nearer 1 than on the full volume",
          0.5 < fat_w < thin_w < 1.0, (thin_w, fat_w))
    sh = lambda rel: [(imp * 0.1, imp * 0.1 * 0.01 * r) for (imp, _), r in zip(acct, rel)]
    check("what hits the whole account at once is not the campaign's fatigue: its rate divided by the account's stays flat",
          not lifecycle.fatigue(lifecycle.relative_ctr([(i, c * 0.5) for i, c in own(flat)], [(i, c * 0.5) for i, c in acct], P), P)["fatigued"])
    v = verdict(d=days(60), ctr=own(worn), ctr_account=acct)
    check("judge: a settled campaign whose click-through rate wore out is fatigued, whatever its return (a leading signal)",
          (v.state, v.reason) == ("fatigued", "ctr_worn_out") and v.ctr and v.ctr["fatigued"], v)
    v = verdict(d=days(60, roas=5.0), ctr=own(worn), ctr_account=acct)
    check("even above its benchmark: it is earning today and its creatives are wearing out, the proposal says so", v.state == "fatigued", v)
    v = verdict(d=days(60), ctr=own(flat), ctr_account=acct)
    check("judge: a flat click-through rate is not fatigue", v.state == "steady", v)

    print("[2] the hold ")
    h = lambda states, w=2: lifecycle.hold(states, [f"r{i}" for i in range(len(states))], w)
    check("a change among earning, steady, fatiguing and unjudged waits for two readings in a row", h(["steady", "earning"])[:1] == ("steady",)
          and h(["steady", "earning"])[2] == "earning" and h(["steady", "earning", "earning"])[:2] == ("earning", "r2"), h(["steady", "earning"]))
    check("one reading of another state between two of the same moves nothing", h(["fatiguing", "steady", "fatiguing", "fatiguing"])[0] == "fatiguing"
          and h(["fatiguing", "fatiguing", "steady", "fatiguing", "steady"])[0] == "fatiguing")
    check("a change is held back until the new state has held: no pending state is named once it has", h(["steady", "earning", "earning"])[2] is None
          and h(["steady", "steady", "fatiguing"])[2] == "fatiguing")
    check("while it waits the old state and its reason stand", h(["steady", "steady", "fatiguing"])[:2] == ("steady", "r1"))
    check("blocked, ended, setup and learning are entered and left at once", all(h([a, b])[0] == b for a, b in (
        ("steady", "blocked"), ("blocked", "earning"), ("earning", "ended"), ("setup", "learning"), ("learning", "steady"), ("fatiguing", "learning"))))
    check("with a hold of 1 week nothing waits", h(["steady", "earning"], 1)[0] == "earning")
    weekly = [4.0, 5.0, 6.0, 4.0, 3.5, 6.5, 5.0, 3.0, 6.0, 4.5, 5.5, 3.5]      # the return a campaign made each week: it hovers at the benchmark, noise on top
    d = {}
    for w, roas in enumerate(weekly):
        for i in range(7):
            d[(date(2026, 7, 6) + timedelta(days=7 * w + i)).isoformat()] = (100.0, 100.0 * roas, 5.0)
    end = date(2026, 7, 6) + timedelta(days=7 * len(weekly) - 1)
    marks = [(end - timedelta(days=7 * i)).isoformat() for i in range(len(weekly) - 5, -1, -1)]
    raw = [lifecycle.judge(lifecycle.Campaign("c", "active", d, 800.0), m, P, 4.0).state for m in marks]
    held = [lifecycle.hold(raw[:i + 1], ["r"] * (i + 1), 2)[0] for i in range(len(raw))]
    flips = lambda xs: sum(a != b for a, b in zip(xs, xs[1:]))
    check("a campaign hovering at its benchmark flips in the raw readings and far less once held (the shape of a real replay)",
          flips(raw) >= 3 and flips(held) < flips(raw), (raw, held))
    check("and a held state only ever follows a state the readings held for two weeks", all(
        held[i] == held[i - 1] or raw[i] == raw[i - 1] == held[i] or held[i] in lifecycle.FORCED for i in range(1, len(held))), (raw, held))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
