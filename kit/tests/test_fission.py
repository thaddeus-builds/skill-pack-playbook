#!/usr/bin/env python3
"""kit.fission: the fission score, the rules, on planted creatives.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import fission  # noqa: E402
from kit.creative_life import Day  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402


START = date(2026, 8, 1)


def days(rows):
    return [Day((START + timedelta(days=i)).isoformat(), *r) for i, r in enumerate(rows)]


def row(cid, state, reason, spend, conv, delivery, source="report"):
    return {"creative": cid, "label": cid, "source": source, "state": state, "reason": reason,
            "totals": {"spend": spend, "conversions": conv, "delivery_days": delivery}}


def main() -> int:
    print("[1] the numbers")
    s = fission.stats({"spend": 1000.0, "conversions": 20.0, "delivery_days": 10})
    check("cost per conversion 50, 2 conversions a delivery day", s == {"cost": 50.0, "volume": 2.0}, s)
    check("no conversions, no stats", fission.stats({"spend": 100.0, "conversions": 0, "delivery_days": 5}) is None)
    d = days([(100, 1000, 20, 4)] * 20 + [(100, 1000, 20, 1)] * 14)
    r = fission.recent(d, 14)
    check("the recent 14 days only: cost 100 per conversion, 1 a day", r == {"cost": 100.0, "volume": 1.0}, r)
    check("recent days with no conversion: none", fission.recent(days([(100, 1000, 20, 0)] * 5), 14) is None)

    proven = [{"cost": 40.0, "volume": 1.0}, {"cost": 50.0, "volume": 2.0}, {"cost": 60.0, "volume": 3.0}]
    b = fission.benchmark(proven, 3)
    check("the benchmark is the median cost and volume", b == {"cost": 50.0, "volume": 2.0, "n": 3}, b)
    check("under the minimum: no benchmark", fission.benchmark(proven[:2], 3) is None)
    check("the minimum is at least 3", fission.benchmark(proven[:2], 1) is None)

    print("[2] the score")
    at = fission.score({"cost": 50.0, "volume": 2.0}, b)
    check("at the benchmark: 0.5", at["fission"] == 0.5, at)
    check("half the cost and double the volume: 1.0", fission.score({"cost": 25.0, "volume": 4.0}, b)["fission"] == 1.0)
    check("better than that is still 1.0", fission.score({"cost": 5.0, "volume": 40.0}, b)["fission"] == 1.0)
    cheap = fission.score({"cost": 25.0, "volume": 0.2}, b)
    check("cheap but tiny lands low: both must be good", cheap["fission"] < 0.35 and cheap["efficiency"] == 1.0, cheap)
    dear = fission.score({"cost": 200.0, "volume": 8.0}, b)
    check("big but dear lands low too", dear["fission"] < 0.55 and dear["impact"] == 1.0, dear)
    check("nearly nothing earned: near 0", fission.score({"cost": 5000.0, "volume": 0.01}, b)["fission"] <= 0.03)

    half = fission.score({"cost": 50.0, "volume": 2.0}, b, 0.5)
    check("the trend damps a creative that earns half of last week's: 0.5 -> 0.25", half["fission"] == 0.25 and half["trend"] == 0.5, half)
    check("a growing creative is not boosted", fission.score({"cost": 50.0, "volume": 2.0}, b, 3.0)["fission"] == 0.5)
    check("no trend known (no previous week): no damping", fission.score({"cost": 50.0, "volume": 2.0}, b, None)["fission"] == 0.5)

    print("[3] who is scored, and the recent days")
    steady = days([(100, 1000, 20, 2)] * 40)                              # cost 50, 2 a day, all the time
    fading = days([(100, 1000, 20, 4)] * 26 + [(100, 1000, 20, 2)] * 7 + [(100, 1000, 20, 1)] * 7)   # converted a lot, halving
    rows = [row("STEADY", "mature", "learned", 4000, 80, 40), row("FADING", "declining", "worse", 4000, 130, 40),
            row("OTHER", "mature", "learned", 4000, 80, 40),
            row("NEW", "learning", "reach", 100, 1, 3), row("WAIT", "doubt", "slow", 900, 2, 14),
            row("PARK", "parked", "low_reach", 5, 0, 7), row("WEAK", "ended", "weak_creative", 600, 0, 20)]
    days_of = {("report", c): steady for c in ("STEADY", "OTHER")} | {("report", "FADING"): fading}
    out, bench, omitted = fission.scores(rows, days_of, 14, 3)
    check("a benchmark from the three proven creatives' whole lives", bench and bench["n"] == 3, bench)
    check("a steady creative scores near the middle", 0.4 <= out["STEADY"]["fission"] <= 0.7, out["STEADY"])
    check("a fading creative that converted a lot scores lower than the steady one ",
          out["FADING"]["fission"] < out["STEADY"]["fission"] - 0.15 and out["FADING"]["trend"] == 0.5, (out["FADING"]["fission"], out["STEADY"]["fission"]))
    check("a weak creative that spent its extension is 0.0", out["WEAK"]["fission"] == 0.0, out["WEAK"])
    check("testing, learning, doubt and parked are unknown, not 0",
          all(out[c]["fission"] is None for c in ("NEW", "WAIT", "PARK")), {c: out[c]["fission"] for c in ("NEW", "WAIT", "PARK")})
    check("the unscored are counted by state", omitted == {"learning": 1, "doubt": 1, "parked": 1}, omitted)
    out2, bench2, omitted2 = fission.scores(rows[:2], {k: v for k, v in days_of.items() if k[1] in ("STEADY", "FADING")}, 14, 3)
    check("two proven creatives are no benchmark: nothing is scored but the weak zeros",
          bench2 is None and out2["STEADY"]["fission"] is None and out2["FADING"]["fission"] is None, out2)
    dead = {("report", "STEADY"): days([(100, 1000, 20, 2)] * 30 + [(0, 0, 0, 0)] * 14), ("report", "OTHER"): steady,
            ("report", "FADING"): fading}
    out3, _, _ = fission.scores(rows[:3], dead, 14, 3)
    check("no delivery in the recent days: 0.0 (nothing earned lately)", out3["STEADY"]["fission"] == 0.0, out3["STEADY"])

    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
