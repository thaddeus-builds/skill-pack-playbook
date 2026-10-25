#!/usr/bin/env python3
"""kit.reconcile: two routes' numbers for one platform side by side, on planted numbers.

  * totals sums a route's rows per day and counts the entities;
  * a day is `match` when every metric is within the tolerance of the larger, `differs` with the metrics that are off, `only_a` or `only_b` when a route has no row;
  * different currencies: the spend is not compared (`currency`) and the counts still are;
  * the window is the last N days ending at a day; days neither route has are left out.
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import reconcile  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402


def row(day, spend, imp, clicks, buy):
    return {"date": day, "spend": spend, "impressions": imp, "clicks": clicks, "conversions": buy}


def main() -> int:
    a = reconcile.totals([row("2026-10-01", 100.0, 1000, 10, 2), row("2026-10-01", 50.0, 500, 5, 1), row("2026-10-02", 80.0, 800, 8, 1)])
    check("totals sums per day and counts the ads", a["2026-10-01"] == {"spend": 150.0, "impressions": 1500, "clicks": 15.0, "conversions": 3.0, "ads": 2} and a["2026-10-02"]["ads"] == 1, a)
    b = reconcile.totals([row("2026-10-01", 151.0, 1490, 15, 3), row("2026-10-03", 70.0, 700, 7, 1)])
    days = reconcile.window("2026-10-03", 4)
    check("the window is the last N days ending at a day", days == ["2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03"], days)
    rows = reconcile.compare(a, b, days, 0.02, True)
    by = {r["day"]: r for r in rows}
    check("days neither route has are left out", sorted(by) == ["2026-10-01", "2026-10-02", "2026-10-03"], sorted(by))
    check("within the tolerance of the larger: match (151 against 150, 1490 against 1500)", by["2026-10-01"]["verdict"] == "match" and by["2026-10-01"]["diff"]["spend"] == 1.0, by["2026-10-01"])
    check("a route with no row for the day: only_a or only_b", by["2026-10-02"]["verdict"] == "only_a" and by["2026-10-03"]["verdict"] == "only_b")
    wide = reconcile.compare(a, {"2026-10-01": {"spend": 200.0, "impressions": 1500, "clicks": 15.0, "conversions": 3.0, "ads": 2}}, ["2026-10-01"], 0.02, True)[0]
    check("beyond the tolerance: differs, naming the metric", wide["verdict"] == "differs" and wide["off"] == ["spend"], wide)
    tight = reconcile.compare(a, b, ["2026-10-01"], 0.001, True)[0]
    check("a tighter tolerance calls the same day different", tight["verdict"] == "differs" and "spend" in tight["off"], tight)
    cur = reconcile.compare(a, {"2026-10-01": {"spend": 999.0, "impressions": 1500, "clicks": 15.0, "conversions": 3.0, "ads": 2}}, ["2026-10-01"], 0.02, False)[0]
    check("different currencies: the spend is not compared, the day is `currency`", cur["verdict"] == "currency" and cur["off"] == [], cur)
    cnt = reconcile.compare(a, {"2026-10-01": {"spend": 999.0, "impressions": 1500, "clicks": 40.0, "conversions": 3.0, "ads": 2}}, ["2026-10-01"], 0.02, False)[0]
    check("different currencies: a count that differs is still found", cnt["verdict"] == "differs" and cnt["off"] == ["clicks"], cnt)
    zero = reconcile.compare({"d": {"spend": 0.0, "impressions": 0, "clicks": 0.0, "conversions": 0.0, "ads": 1}}, {"d": {"spend": 0.0, "impressions": 0, "clicks": 0.0, "conversions": 0.0, "ads": 1}}, ["d"], 0.02, True)[0]
    check("two zeros match", zero["verdict"] == "match")
    s = reconcile.summary(rows)
    check("the summary counts the verdicts and sums the days both have", s["days"] == 3 and s["match"] == 1 and s["only_a"] == 1 and s["only_b"] == 1 and s["compared_days"] == 1
          and s["totals"]["spend"] == {"a": 150.0, "b": 151.0}, s)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
