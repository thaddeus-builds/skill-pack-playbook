#!/usr/bin/env python3
"""kit.auction_pressure: the paid-search skill pack's four-week case and its verdict table.

W33 is the baseline; W34 the cost per click is up and our share down at the same bid (heating); W35 our bid and share are up (bought);
W36 the cost per click is down at the same bid (cooling). The first week has no verdict and says why; a week with no day of ours has no
number; the share is weighted by impressions and days without one are left out and counted.
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import auction_pressure as ap  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

DAYS = {"2026-08-11": (100, 10, 10.0, 20.0, 1.00), "2026-08-18": (100, 10, 13.0, 10.0, 1.00),
        "2026-08-25": (100, 10, 13.0, 15.0, 1.30), "2026-09-01": (100, 10, 9.0, 15.0, 1.30)}
WEEKS = ["2026-W33", "2026-W34", "2026-W35", "2026-W36", "2026-W37"]


def main() -> int:
    print("[1] weekly")
    days = [{"date": d, "impressions": i, "clicks": c, "cost": cost, "share": s, "bid": b} for d, (i, c, cost, s, b) in DAYS.items()]
    wk = {w["week"]: w for w in ap.weekly(days, WEEKS, 0.1)}
    check("W33: cost per click = cost over clicks, share and bid as read", (wk["2026-W33"]["cpc"], wk["2026-W33"]["share"], wk["2026-W33"]["bid"]) == (1.0, 20.0, 1.0), wk["2026-W33"])
    check("the first week has no verdict and says why", wk["2026-W33"]["verdict"] is None and wk["2026-W33"]["reason"] == "no_prior_week")
    check("CPC up and share down at the same bid: heating", wk["2026-W34"]["verdict"] == "heating", wk["2026-W34"])
    check("bid up and share up: bought", wk["2026-W35"]["verdict"] == "bought", wk["2026-W35"])
    check("CPC down at the same bid: cooling", wk["2026-W36"]["verdict"] == "cooling", wk["2026-W36"])
    check("a week with no day of ours has no number and no verdict (missing input)", wk["2026-W37"]["impressions"] == 0
          and wk["2026-W37"]["verdict"] is None and wk["2026-W37"]["reason"] == "missing_input", wk["2026-W37"])
    two = ap.weekly([{"date": "2026-08-10", "impressions": 100, "clicks": 2, "cost": 2.0, "share": 10.0, "bid": 1.0},
                     {"date": "2026-08-11", "impressions": 300, "clicks": 2, "cost": 2.0, "share": 30.0, "bid": 2.0},
                     {"date": "2026-08-12", "impressions": 500, "clicks": 0, "cost": 0.0, "share": None, "bid": None}], ["2026-W33"], 0.1)[0]
    check("share and bid are weighted by impressions; a day with no share is left out and counted",
          two["share"] == 25.0 and two["bid"] == 1.75 and two["share_days"] == 2 and two["impressions"] == 900, two)
    check("days outside the weeks asked for are not read", ap.weekly(days, ["2026-W40"], 0.1)[0]["impressions"] == 0)

    print("[2] verdict")
    flat = {"cpc": 1.0, "share": 10.0, "bid": 1.0}
    check("inside the move threshold: flat", ap.verdict(flat, {"cpc": 1.05, "share": 9.6, "bid": 1.0}, 0.1) == ("flat", None))
    check("a missing number: no verdict, missing_input", ap.verdict(flat, {**flat, "share": None}, 0.1) == (None, "missing_input"))
    check("a previous number of 0 cannot be compared", ap.verdict({**flat, "cpc": 0}, flat, 0.1) == (None, "missing_input"))
    check("CPC up with the share also up: unclear, not cooling", ap.verdict(flat, {"cpc": 1.5, "share": 15.0, "bid": 1.0}, 0.1) == (None, "unclear"))
    check("bid raised without a share gain: unclear", ap.verdict(flat, {"cpc": 1.0, "share": 10.0, "bid": 1.5}, 0.1) == (None, "unclear"))
    check("bid cut: unclear whatever else moved", ap.verdict(flat, {"cpc": 0.5, "share": 10.0, "bid": 0.5}, 0.1) == (None, "unclear"))
    check("share up alone at the same bid: cooling", ap.verdict(flat, {"cpc": 1.0, "share": 12.0, "bid": 1.0}, 0.1) == ("cooling", None))
    check("the threshold is a fraction: exactly 10% counts as a move", ap.verdict(flat, {"cpc": 1.1, "share": 9.0, "bid": 1.0}, 0.1)[0] == "heating")
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
