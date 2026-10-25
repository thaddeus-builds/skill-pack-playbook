#!/usr/bin/env python3
"""kit.allocation: the perform wallet's split across campaigns (equal marginal return in bounded steps), on hand-made campaigns. Every number is synthetic.
"""

import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import allocation as al  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

P = al.Params()


def inp(e=0.5, se_e=0.02, roas=4.0, conversions=5000):
    return {"e": e, "se_e": se_e, "roas": roas, "conversions": conversions}


def main() -> int:
    print("[1] the elasticity")
    pts = [(s, 10 * s ** 0.5) for s in range(50, 150)]
    e, se = al.elasticity(pts, P)
    check("revenue = 10 x spend^0.5 gives an elasticity of 0.5 and a tiny error", abs(e - 0.5) < 1e-6 and se < 1e-6, (e, se))
    check("under min_days days with spend: no reading", al.elasticity(pts[:20], P) is None)
    check("no variation in the spend: no reading (the response cannot be seen)", al.elasticity([(100.0, 500.0 + i) for i in range(40)], P) is None)
    e, se = al.shrink(None, 0.5, P)
    check("no reading of its own: the pooled value, held in [0.2, 1], with the prior's sd", (e, se) == (0.5, 0.2), (e, se))
    check("held in the range", al.shrink(None, 1.7, P)[0] == 1.0 and al.shrink(None, 0.0, P)[0] == 0.2)
    pulled, _ = al.shrink((0.9, 0.2), 0.5, P)
    check("a noisy own reading is pulled halfway to the pooled value (equal precision)", abs(pulled - 0.7) < 1e-9, pulled)
    sure, _ = al.shrink((0.9, 0.01), 0.5, P)
    check("a sure own reading stays", sure > 0.89, sure)

    print("[2] equal marginal return")
    items = [{"b": 100.0, "m": 2.5, "e": 0.5, "lo": 0.0, "hi": 1e9}, {"b": 100.0, "m": 1.5, "e": 0.5, "lo": 0.0, "hi": 1e9}]
    lam = al.solve(items, 200.0)
    xs = [al.budget_at(lam, i["b"], i["m"], i["e"]) for i in items]
    check("the level puts the budgets on the total and equalises the marginal returns", abs(sum(xs) - 200) < 1e-6 and abs(2.5 * (xs[0] / 100) ** -0.5 - lam) < 1e-6, (lam, xs))
    check("the better campaign gets more", xs[0] > 100 > xs[1], xs)
    boxed = [{**i, "lo": 90.0, "hi": 110.0} for i in items]
    lam = al.solve(boxed, 200.0)
    xs = [min(max(al.budget_at(lam, i["b"], i["m"], i["e"]), i["lo"]), i["hi"]) for i in boxed]
    check("with a box of plus or minus 10% the budgets stop at the box and still add up", xs == [110.0, 90.0] or all(abs(x - y) < 1e-6 for x, y in zip(xs, [110.0, 90.0])), xs)

    print("[3] the day: evidence, step, cooldown, acceleration")
    arms = [al.Arm("A", 100.0), al.Arm("B", 100.0)]
    moves = al.day(arms, {"A": inp(roas=5.0), "B": inp(roas=3.0)}, 0, P)
    check("two campaigns whose returns differ by a clear margin: the better goes up and the worse down by at most 10%, money conserved",
          len(moves) == 2 and abs(arms[0].budget - 110.0) < 1e-6 and abs(arms[1].budget - 90.0) < 1e-6, moves)
    arms = [al.Arm("A", 100.0), al.Arm("B", 100.0)]
    check("the same difference on little evidence (few conversions): no move", al.day(arms, {"A": inp(roas=5.0, conversions=20), "B": inp(roas=3.0, conversions=20)}, 0, P) == []
          and [a.budget for a in arms] == [100.0, 100.0])
    arms = [al.Arm("A", 100.0), al.Arm("B", 100.0)]
    al.day(arms, {"A": inp(roas=5.0), "B": inp(roas=3.0)}, 0, P)
    check("a campaign that just moved waits out the cooldown", al.day(arms, {"A": inp(roas=5.0), "B": inp(roas=3.0)}, 1, P) == []
          and al.day(arms, {"A": inp(roas=5.0), "B": inp(roas=3.0)}, 3, P) != [])
    arms = [al.Arm("A", 100.0), al.Arm("B", 100.0)]
    caps = []
    for t in range(0, 12, 3):
        got = al.day(arms, {"A": inp(roas=5.0), "B": inp(roas=3.0)}, t, P)
        caps += [m["cap"] for m in got if m["id"] == "A"]
    check("the sign holds: the first moves are 10%, and once it has held three days in a row the step may be 20%", caps[0] == 0.10 and 0.20 in caps, caps)
    arms = [al.Arm("A", 100.0), al.Arm("B", 100.0)]
    caps = []
    for t in range(0, 12, 3):
        got = al.day(arms, {"A": inp(roas=5.0), "B": inp(roas=3.0)}, t, P, fast=False)
        caps += [m["cap"] for m in got if m["id"] == "A"]
    check("with the acceleration off every step is 10%", set(caps) == {0.10}, caps)
    arms = [al.Arm("A", 100.0), al.Arm("B", 100.0)]
    al.day(arms, {"A": inp(roas=5.0), "B": inp(roas=3.0)}, 0, P)
    al.day(arms, {"A": inp(roas=5.0), "B": inp(roas=3.0)}, 3, P)
    streak = arms[0].streak
    al.day(arms, {"A": inp(roas=2.0), "B": inp(roas=6.0)}, 6, P)
    check("the sign flips: the run resets", streak >= 2 and arms[0].streak == 1 and arms[0].side == -1, (streak, arms[0].streak, arms[0].side))
    arms = [al.Arm("A", 100.0)]
    check("one campaign has no one to trade with: no move", al.day(arms, {"A": inp()}, 0, P) == [])
    arms = [al.Arm("A", 100.0), al.Arm("B", 100.0)]
    al.day(arms, {"A": inp(roas=5.0), "B": inp(roas=3.0)}, 0, P)
    check("the sum of the budgets never changes: it is a split, not a raise", abs(sum(a.budget for a in arms) - 200.0) < 1e-6, [a.budget for a in arms])
    check("a campaign with no figures today is left alone", al.day(arms, {"A": inp(roas=5.0)}, 9, P) == [])
    check("a move kept inside the platform's range: a cut below the minimum stops at the minimum, said", al.clip_move(100.0, 60.0, 80.0, None) == (80.0, "min_daily_budget"))
    check("a raise above the maximum stops at the maximum, said", al.clip_move(100.0, 140.0, None, 120.0) == (120.0, "max_daily_budget"))
    check("a budget already under the minimum is not raised by a cut", al.clip_move(70.0, 60.0, 80.0, None) == (70.0, "min_daily_budget"))
    check("inside the range, or with no range known, nothing binds", al.clip_move(100.0, 110.0, 50.0, 200.0) == (110.0, None) and al.clip_move(100.0, 90.0, None, None) == (90.0, None))
    a1 = al.Arm("A", 100.0, last_move=5)
    check("why a campaign is held: no reading, too few, no evidence, cooldown, no counterpart",
          [al.held_reason(a1, None, 6, P), al.held_reason(a1, {}, 6, P), al.held_reason(a1, {"z": 0.2}, 6, P), al.held_reason(a1, {"z": 5.0}, 6, P),
           al.held_reason(al.Arm("B", 100.0), {"z": 5.0}, 6, P)] == ["no_reading", "too_few", "no_evidence", "cooldown", "no_counterpart"])
    check("a proposal is open before the follow days and with no reading",
          al.follow(100.0, 110.0, 110.0, 3, 7) == "open" and al.follow(100.0, 110.0, None, 30, 7) == "open")
    check("taken when the budget moved the proposed way by at least half the distance, else not taken",
          al.follow(100.0, 110.0, 106.0, 8, 7) == "taken" and al.follow(100.0, 110.0, 102.0, 8, 7) == "not_taken" and al.follow(100.0, 110.0, 90.0, 8, 7) == "not_taken"
          and al.follow(100.0, 90.0, 92.0, 8, 7) == "taken")
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
