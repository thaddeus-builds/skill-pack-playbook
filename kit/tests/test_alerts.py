#!/usr/bin/env python3
"""kit.alerts: an entity against its own last 7 settled days, on the paid-search skill pack's golden fixture (20 days, 100 a day,
a 300 spike on the last).

  * spend spike: 300 against a baseline of 100 is 3.0x, over a 1.5x threshold; a return drop when sales stay flat while spend
    triples; a flat entity hits neither;
  * fewer than two settled days, no spend now, no spend in the baseline, too few clicks: no verdict, with a reason;
  * a zero baseline: met, not measured, coded; a measured 3x spike keeps no code; a return `ge` after none is not coded;
  * settled days only, newest first; event days leave the baseline and it refills; the cooldown.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import alerts  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

P = alerts.Point
START = date(2026, 9, 1)


def iso(i):
    return (START + timedelta(days=i)).isoformat()


def golden(spike=300.0, sales=200.0, n=20, clicks=None):
    """Days 0..n-1: spend 100 and sales 200 each, the last day `spike` and `sales`."""
    return [P(iso(i), 100.0 if i < n - 1 else spike, 200.0 if i < n - 1 else sales, clicks) for i in range(n)]


def main() -> int:
    print("[1] settled points")
    daily = golden()
    ok = {iso(i) for i in range(20)} - {iso(19), iso(5)}
    pts = alerts.settled_points(daily, ok)
    check("only settled days, newest first, the judged day plus 7", [p.date for p in pts] == [iso(i) for i in (18, 17, 16, 15, 14, 13, 12, 11)], [p.date for p in pts])

    print("[2] spend and return against the baseline")
    pts = alerts.settled_points(daily, {iso(i) for i in range(20)})
    c = alerts.check(pts, "spend", "ge", 1.5)
    check("spend 300 against 7 settled days of 100: 3.0x, a hit", c["hit"] is True and c["current"] == 300.0 and c["baseline"] == 100.0
          and c["baseline_days"] == 7 and c["current_date"] == iso(19) and c["reason"] is None, c)
    r = alerts.check(pts, "return", "le", 0.5)
    check("sales flat while spend triples: the return falls to 0.67 against 2.0 (0.33x), under 0.5x: a hit", r["hit"] is True
          and abs(r["current"] - 0.666667) < 1e-6 and r["baseline"] == 2.0, r)
    flat = alerts.check(alerts.settled_points(golden(spike=100.0, sales=200.0), {iso(i) for i in range(20)}), "spend", "ge", 1.5)
    check("a flat entity does not hit", flat["hit"] is False and flat["current"] == 100.0, flat)
    check("a baseline is a mean of the days, a return a sum over a sum",
          alerts.check([P("d9", 10.0, 20.0), P("d8", 1.0, 5.0), P("d7", 99.0, 99.0)], "return", "ge", 1.0)["baseline"] == 1.04,
          alerts.check([P("d9", 10.0, 20.0), P("d8", 1.0, 5.0), P("d7", 99.0, 99.0)], "return", "ge", 1.0))
    check("the baseline is at most `baseline_days` days", alerts.check(pts, "spend", "ge", 1.5, baseline_days=3)["baseline_days"] == 3)

    print("[3] no verdict")
    one = alerts.check([P(iso(0), 10.0, 5.0)], "spend", "ge", 1.5)
    check("fewer than 2 settled days: no verdict, a reason, never a crash", one["hit"] is None and one["reason"] == "too_few_settled_days", one)
    zz = alerts.check([P("b", 0.0, 0.0), P("a", 0.0, 0.0)], "spend", "ge", 1.5)
    check("0 against 0 is no level shift", zz["hit"] is None and zz["reason"] == "no_spend_current_day", zz)
    ns = alerts.check([P("b", 0.0, 0.0), P("a", 5.0, 9.0)], "return", "le", 0.5)
    check("no spend today, a return has nothing to divide", ns["hit"] is None and ns["reason"] == "no_spend_current_day", ns)
    nb = alerts.check([P("b", 5.0, 9.0), P("a", 0.0, 0.0)], "return", "le", 0.5)
    check("no spend in the baseline: no return baseline", nb["hit"] is None and nb["reason"] == "no_spend_baseline", nb)
    few = alerts.check([P("b", 300.0, 0.0, 19), P("a", 100.0, 0.0, 40)], "spend", "ge", 1.5, min_clicks=20)
    check("under the click floor on the judged day: no verdict", few["hit"] is None and few["reason"] == "too_few_clicks", few)
    enough = alerts.check([P("b", 300.0, 0.0, 20), P("a", 100.0, 0.0, 40)], "spend", "ge", 1.5, min_clicks=20)
    check("on the click floor: judged", enough["hit"] is True, enough)

    print("[4] a zero baseline is met, not measured")
    z = alerts.check([P("2026-09-20", 50.0, 0.0), P("2026-09-19", 0.0, 0.0), P("2026-09-18", 0.0, 0.0)], "spend", "ge", 1.5)
    check("spend after none in the days before: a hit, coded with its figures", z["hit"] is True and z["baseline"] == 0.0
          and z["reason"] == "spend_from_zero_baseline" and z["reason_params"] == {"spend": 50.0, "date": "2026-09-20", "baseline_days": 2}, z)
    check("a measured 3x spike keeps no code", alerts.check(pts, "spend", "ge", 1.5)["reason"] is None)
    rz = alerts.check([P("2026-09-20", 30.0, 0.0), P("2026-09-19", 10.0, 0.0)], "return", "le", 0.5)
    check("a return of 0 before and now meets `le` without a drop: coded", rz["hit"] is True and rz["reason"] == "return_from_zero_baseline", rz)
    rg = alerts.check([P("2026-09-20", 30.0, 90.0), P("2026-09-19", 10.0, 0.0)], "return", "ge", 1.5)
    check("a return `ge` met by sales after none is not coded", rg["hit"] is True and rg["reason"] is None, rg)
    check("a measured return drop keeps no code", alerts.check(alerts.settled_points(golden(), {iso(i) for i in range(20)}), "return", "le", 0.5)["reason"] is None)

    print("[5] event days")
    pts8 = [P(iso(19 - i), 100.0, 200.0) for i in range(12)]
    kept, dropped = alerts.without_event_days(pts8, lambda d: d in (iso(17), iso(16)))
    check("event days leave the baseline, which refills from older days up to 7", len(kept) == 8 and dropped == [iso(16), iso(17)]
          and all(p.date not in dropped for p in kept) and kept[0].date == iso(19), (len(kept), dropped))
    check("the judged day stays even on an event", alerts.without_event_days(pts8, lambda d: True)[0] == [pts8[0]])
    check("no points, nothing", alerts.without_event_days([], lambda d: True) == ([], []))

    print("[6] bad rules are refused")
    for args in (("revenue", "ge", 1.5), ("spend", "in", 1.5), ("spend", "ge", 0)):
        try:
            alerts.check(pts, *args)
            err = ""
        except ValueError as e:
            err = str(e)
        check(f"refused: {args}", "bad alert rule" in err, err)

    print("[7] the cooldown")
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    check("never fired: not in cooldown", not alerts.in_cooldown(None, 24, now))
    check("fired 10 hours ago, cooldown 24: in", alerts.in_cooldown(now - timedelta(hours=10), 24, now))
    check("fired 23.5 hours ago: an hour of slack for scheduler jitter, out", not alerts.in_cooldown(now - timedelta(hours=23.5), 24, now))
    check("a short cooldown keeps its half: 1 hour, fired 20 minutes ago, in", alerts.in_cooldown(now - timedelta(minutes=20), 1, now))
    check("fired 25 hours ago: out", not alerts.in_cooldown(now - timedelta(hours=25), 24, now))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
