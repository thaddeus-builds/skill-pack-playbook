#!/usr/bin/env python3
"""kit.maturity: the share of a day's final number visible at each age, fitted from restated numbers, on a synthetic world whose lag is known. Every key, day and number is
invented. The world: each day has a Poisson number of orders; each order draws a uniform number and is visible at age a when it is at most F(a), so counts are monotone in
age; values are the orders' worth (unequal, lognormal). The cases are the eight of the brief (#267): the fit recovers the truth and narrows with data; count and value are
fitted apart; a matured estimate's 90 % interval covers the final about nine times in ten; no data gives the prior and says so; shrinkage sits between prior and data; a
day past the window is its own final and a refund is clipped; a drift fires when the lag doubles and a curve goes stale; a window whose interval straddles a threshold is
undecided while the same window matured is decided.
"""

import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import maturity as m, messages  # noqa: E402
from kit.registry import Thresholds  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

W = 7
END = date(2026, 9, 1)


def thresholds() -> dict:
    empty = Path(tmp_dir("maturity-")) / "constants.tsv"
    empty.write_text("\t".join(["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why"]) + "\n", encoding="utf-8")
    return Thresholds(empty).load()


def poisson(rng, lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def world(rng, keys, ndays, tau_c, tau_v, shape=1.0, lam=40.0, ages=range(0, W + 2)):
    """Observation rows of every (key, day) at every age in `ages`, the truth being a lag of tau_c for counts and tau_v for values."""
    obs = []
    for ki in range(keys):
        lam_k = lam * (0.5 + rng.random())
        for di in range(ndays):
            day = END - timedelta(days=di + W + 2)
            orders = [(rng.random(), 40.0 * math.exp(0.5 * rng.gauss(0, 1))) for _ in range(poisson(rng, lam_k))]
            for a in ages:
                fc, fv = m._f(a, tau_c, shape, W), m._f(a, tau_v, shape, W)
                cnt = len(orders) if a >= W else sum(1 for u, _ in orders if u <= fc)
                val = sum(v for _, v in orders) if a >= W else sum(v for u, v in orders if u <= fv)
                obs.append({"key": f"K{ki}", "day": day.isoformat(), "observed_at": (day + timedelta(days=a)).isoformat(), "spend": 10.0, "count": float(cnt), "value": val})
    return obs


def main() -> int:
    _shop.use()
    k = thresholds()
    P = m.params(k)

    print("[1] the curve, by hand")
    c = m.Curve("exp", 1.5, 1.0, 0.0, W, "count", 0, 0, True)
    f0 = (1 - math.exp(-1 / 1.5)) / (1 - math.exp(-8 / 1.5))
    check("F(0) at tau 1.5 and a 7-day window is (1 - e^(-1/1.5)) / (1 - e^(-8/1.5)) = 0.4890; F(6) is 0.9975..., and from the window on it is exactly 1",
          abs(m.share(c, 0)[0] - f0) < 1e-12 and abs(f0 - 0.48898) < 1e-4 and m._f(W, 1.5, 1.0, W) == 1.0 and m._f(W + 5, 1.5, 1.0, W) == 1.0 and 0.99 < m._f(6, 1.5, 1.0, W) < 1.0)
    check("it never falls with age and stays in (0, 1]", all(0 < m._f(a, 1.5, 1.0, W) <= m._f(a + 1, 1.5, 1.0, W) <= 1.0 for a in range(0, 12)))
    wide = m.Curve("exp", 1.5, 1.0, 0.3, W, "count", 0, 0, True)
    lo, hi = m.share(wide, 1)[1], m.share(wide, 1)[2]
    check("a standard error gives an interval around the share (a slower tau is a lower share), none from the window on", lo < m.share(wide, 1)[0] < hi and m.share(wide, W) == (1.0, 1.0, 1.0))
    check("the cold-start tau is read for the window nearest on the log scale: 7 days 1.5, 1 day 1, 28 days 4, 21 days 4", [m.prior_tau(w, k) for w in (7, 1, 28, 21)] == [1.5, 1.0, 4.0, 4.0])

    print("[2] a world with a known lag: the fit finds it, and narrows with data (brief 1, 2)")
    zs_c, zs_v, tc, tv = [], [], None, None
    for seed in range(1, 11):
        obs = world(random.Random(seed), 12, 25, 1.5, 3.0)
        cc, cv = m.fit(obs, W, 1.5, P, "count"), m.fit(obs, W, 3.0, P, "value")
        zs_c.append((cc.tau - 1.5) / cc.se)
        zs_v.append((cv.tau - 3.0) / cv.se)
        tc, tv = tc or cc, tv or cv
    check("ten worlds: the fitted tau is within two standard errors of the truth in at least eight, for counts", sum(abs(z) <= 2.0 for z in zs_c) >= 8, [round(z, 2) for z in zs_c])
    check("and for values, which mature slower and were fitted apart", sum(abs(z) <= 2.0 for z in zs_v) >= 8, [round(z, 2) for z in zs_v])
    check("they differ: the value lag is about twice the count lag, many standard errors apart", tv.tau - tc.tau > 5 * math.hypot(tv.se, tc.se) and 1.2 < tc.tau < 1.8 and 2.5 < tv.tau < 3.5, (tc.tau, tv.tau))
    check("the fit says what it stood on: pairs, ages, not prior-only, the data's first and last day", not tc.prior_only and tc.n_pairs > 1000 and tc.n_ages == 7 and tc.data_from < tc.data_to)
    big = m.fit(world(random.Random(1), 48, 25, 1.5, 3.0), W, 1.5, P, "count")
    check("four times the data narrows the interval by about half", 0.35 < big.se / tc.se < 0.7, (tc.se, big.se))
    check("orders of unequal worth scatter more than the binomial says: a value curve's dispersion is above 1 (1.28 here), a count's near 1",
          1.1 < tv.dispersion < 1.5 and 0.8 < tc.dispersion < 1.2, (tc.dispersion, tv.dispersion))

    print("[3] the matured estimate's 90 % interval covers the true final about nine times in ten (brief 3)")
    hit_c = hit_v = 0
    runs = 200
    for s in range(runs):
        rng = random.Random(10_000 + s)
        obs = world(rng, 8, 20, 1.5, 3.0)
        cc, cv = m.fit(obs, W, 1.5, P, "count"), m.fit(obs, W, 3.0, P, "value")
        orders = [(rng.random(), 40.0 * math.exp(0.5 * rng.gauss(0, 1))) for _ in range(poisson(rng, 40.0))]
        cnt = sum(1 for u, _ in orders if u <= m._f(2, 1.5, 1.0, W))
        val = sum(v for u, v in orders if u <= m._f(2, 3.0, 1.0, W))
        day = date(2026, 9, 20)
        a = m.adjust([{"day": day.isoformat(), "spend": 100.0, "count": float(cnt), "value": val}], (day + timedelta(days=2)).isoformat(), cc, cv, P)[0]
        hit_c += a["count"]["low"] <= len(orders) <= a["count"]["high"]
        hit_v += a["value"]["low"] <= sum(v for _, v in orders) <= a["value"]["high"]
    check(f"a day seen at age 2, 200 runs: the interval covers the true final count between 0.85 and 0.95 of the time", 0.85 <= hit_c / runs <= 0.95, hit_c / runs)
    check("and the true final value", 0.85 <= hit_v / runs <= 0.95, hit_v / runs)

    print("[4] no data, one pair, a prior that is wrong, and few pairs (brief 4, 5)")
    none = m.fit([], W, 1.5, P, "count")
    check("no observation: the curve is the prior, says prior_only, and its interval is wide (+-0.75 on 1.5)", none.prior_only and none.tau == 1.5 and none.se == 0.75 and none.n_pairs == 0)
    check("the wide interval is wide: at age 0 the share runs from under a third to over two thirds", m.share(none, 0)[1] < 0.35 and m.share(none, 0)[2] > 0.65, m.share(none, 0))
    one = [{"key": "K", "day": "2026-08-01", "observed_at": "2026-08-01", "spend": 1.0, "count": 5.0, "value": 5.0}, {"key": "K", "day": "2026-08-01", "observed_at": "2026-08-08", "spend": 1.0, "count": 10.0, "value": 10.0}]
    o = m.fit(one, W, 1.5, P, "count")
    check("one pair is still the prior (under the minimum of 30)", o.prior_only and o.tau == 1.5 and o.n_pairs == 1)
    few_p = m.Params(**{**P.__dict__, "min_pairs": 10, "min_ages": 2})
    obs = world(random.Random(5), 1, 2, 1.5, 3.0)
    thin = m.fit(obs, W, 4.0, few_p, "count")
    free = m.Params(**{**few_p.__dict__, "prior_sd_share": 1e6})                 # a prior with no weight: the data alone
    alone = m.fit(obs, W, 4.0, free, "count")
    check("a few pairs and a prior of 4.0 where the truth is 1.5: the fit is pulled from what the data alone say toward the prior, and stays short of it",
          not thin.prior_only and thin.n_pairs < 30 and alone.tau < 2.0 and alone.tau + 0.05 < thin.tau < 4.0 and thin.se < alone.se, (alone.tau, thin.tau, thin.se, alone.se))
    check("the pull is by precision: the less sure the data, the nearer the prior (a prior held tighter pulls harder)",
          m.fit(obs, W, 4.0, m.Params(**{**few_p.__dict__, "prior_sd_share": 0.1}), "count").tau > thin.tau)
    obs_many = world(random.Random(5), 12, 25, 1.5, 3.0)
    many = m.fit(obs_many, W, 4.0, P, "count")
    alone_many = m.fit(obs_many, W, 4.0, m.Params(**{**P.__dict__, "prior_sd_share": 1e6}), "count")
    check("many pairs: it follows the data and forgets the prior (within 0.01 of the fit with no prior at all)", abs(many.tau - 1.5) < 0.1 and abs(many.tau - alone_many.tau) < 0.01, (many.tau, alone_many.tau))
    check("a prior of 1.5 that was right and many pairs: the same answer, narrower", abs(many.tau - tc.tau) < 0.05 and many.se < tc.se * 1.1)
    check("under the minimum number of distinct ages the fit does not count either", m.fit(world(random.Random(5), 12, 25, 1.5, 3.0, ages=(1, W)), W, 4.0, P, "count").prior_only)

    print("[5] a day past the window, a refund, a bad observation (brief 6)")
    d = date(2026, 8, 1)
    old = m.adjust([{"day": d.isoformat(), "spend": 50.0, "count": 12.0, "value": 480.0}], (d + timedelta(days=W)).isoformat(), tc, tv, P)[0]
    check("a day at the window is its own final: share 1, the estimate is what was seen, no width", old["age"] == W and old["count"]["share"] == 1.0 and old["count"]["estimate"] == 12.0
          and old["count"]["low"] == old["count"]["high"] == 12.0 and old["value"]["low"] == old["value"]["high"] == 480.0, old["count"])
    young = m.adjust([{"day": d.isoformat(), "spend": 50.0, "count": 12.0, "value": 480.0}], d.isoformat(), c, c, P)[0]
    check("a day exported on its own date (age 0) is partial: 12 seen at a share of 0.489 is about 24.5 by the day's end, with a wide interval above and below",
          young["age"] == 0 and abs(young["count"]["estimate"] - 12.0 / f0) < 1e-9 and young["count"]["low"] >= 12.0 and young["count"]["high"] > young["count"]["estimate"] > young["count"]["low"], young["count"])
    refund = world(random.Random(3), 12, 25, 1.5, 3.0)
    for r in refund:
        if r["observed_at"][:10] == (date.fromisoformat(r["day"]) + timedelta(days=W + 1)).isoformat() and random.Random(r["key"] + r["day"]).random() < 0.1:
            r["count"] *= 0.9                                              # a refund: the later number is below an earlier one
    rf = m.fit(refund, W, 1.5, P, "count")
    check("a refund (a final below what was seen earlier) is clipped to a ratio of 1 and counted, and the curve hardly moves", rf.n_clipped > 0 and abs(rf.tau - tc.tau) < 0.1, (rf.n_clipped, rf.tau, tc.tau))
    base = {"key": "K", "day": "2026-08-01", "observed_at": "2026-08-03", "spend": 1.0, "count": 5.0, "value": 5.0}

    def refused(rows, call=None):
        try:
            (call or (lambda: m.fit(rows, W, 1.5, P, "count")))()
        except Exception as e:  # noqa: BLE001
            f = messages.failure(e)
            return f["code"], f["params"].get("where")
        return None, None

    bad = {"a negative count": ({**base, "count": -1.0}, "observations[0]"), "a count that is a word": ({**base, "count": "5"}, "observations[0]"),
           "an observation before its day": ({**base, "observed_at": "2026-07-30"}, "observations[0]"), "a day that is not a day": ({**base, "day": "soon"}, "observations[0]"),
           "a row without its value": ({k_: v for k_, v in base.items() if k_ != "value"}, "observations[0]")}
    got = {name: refused([row]) for name, (row, _) in bad.items()}
    check("each is maturity_bad_observation, naming the row", all(code == "maturity_bad_observation" and where == "observations[0]" for code, where in got.values()), got)
    check("a window or kind that is not understood is refused too", refused([], lambda: m.fit([], 0, 1.5, P, "count"))[0] == "maturity_bad_observation" and refused([], lambda: m.fit([], W, 1.5, P, "price"))[0] == "maturity_bad_observation")
    check("a day handed to adjust before its day, or with a negative number, is refused", refused(None, lambda: m.adjust([{"day": "2026-09-05", "spend": 1.0, "count": 1.0, "value": 1.0}], "2026-09-01", tc, tv, P))[0] == "maturity_bad_observation"
          and refused(None, lambda: m.adjust([{"day": "2026-08-01", "spend": 1.0, "count": -1.0, "value": 1.0}], "2026-09-01", tc, tv, P))[0] == "maturity_bad_observation")

    print("[6] an outage does not decide the curve; a Weibull is kept when it pays")
    outage = world(random.Random(3), 12, 25, 1.5, 3.0)
    gone = random.Random(77)
    for r in outage:
        if 2 <= (date.fromisoformat(r["observed_at"]) - date.fromisoformat(r["day"])).days <= 4 and gone.random() < 0.08:
            r["count"], r["value"] = 0.0, 0.0                                # a tracking outage: some mid-age numbers read zero
    ot = m.fit(outage, W, 1.5, P, "count")
    check("8 % of the mid-age numbers read zero (a tracking outage): the gross outliers are left out and the curve is where it was", abs(ot.tau - m.fit(world(random.Random(3), 12, 25, 1.5, 3.0), W, 1.5, P, "count").tau) < 0.05, ot.tau)
    ex = m.fit(world(random.Random(9), 20, 30, 1.5, 3.0), W, 2.0, P, "count", family="auto")
    wb = m.fit(world(random.Random(9), 20, 30, 2.5, 3.0, shape=2.0), W, 2.0, P, "count", family="auto")
    check("by held-out keys: an exponential world keeps the exponential, a Weibull world of shape 2 keeps the Weibull and finds its shape", ex.family == "exp" and ex.k == 1.0 and wb.family == "weibull" and wb.k == 2.0, (ex.family, ex.k, wb.family, wb.k))

    print("[7] refit, drift and stale (brief 7)")
    t1 = m.fit(world(random.Random(21), 12, 25, 1.5, 3.0), W, 1.5, P, "count", fitted_on="2026-09-01")
    same = m.fit(world(random.Random(22), 12, 25, 1.5, 3.0), W, 1.5, P, "count", fitted_on="2026-09-08")
    doubled = m.fit(world(random.Random(23), 12, 25, 3.0, 3.0), W, 1.5, P, "count", fitted_on="2026-09-08")
    check("two fits of the same lag on different data: no drift", not m.drift(t1, same, P)["drifted"] and abs(m.drift(t1, same, P)["z"]) < 3, m.drift(t1, same, P))
    dd = m.drift(t1, doubled, P)
    check("the lag doubles between two fits: drift fires, many standard errors out", dd["drifted"] and dd["z"] > 10 and dd["tau_new"] > 2 * dd["tau_old"] * 0.9, dd)
    check("a curve that is only a prior cannot show a drift", not m.drift(none, doubled, P)["drifted"] and m.drift(none, doubled, P)["z"] is None)
    check("stale: fitted on 1 September, fresh on the 7th and stale on the 8th (7 days); one with no fit day is stale", not m.stale(t1, "2026-09-07", P) and m.stale(t1, "2026-09-08", P) and m.stale(none, "2026-09-02", P))
    rf2 = m.refit(t1, world(random.Random(24), 12, 25, 3.0, 3.0), P, fitted_on="2026-09-15")
    check("refit takes the old curve as its prior and moves to the new lag; it records its day and leaves the old curve as it was", rf2.fitted_on == "2026-09-15" and rf2.tau > 2.5 and t1.fitted_on == "2026-09-01" and t1.tau < 1.7, (rf2.tau, t1.tau))
    check("a curve survives being stored and read back", m.Curve.from_dict(json.loads(json.dumps(tc.to_dict()))) == tc)
    wins = m.Curve.from_windows({1: 60.0, 7: 100.0, 28: 108.0}, P)
    check("a prior from counts under three attribution windows (unverified against any platform): a curve, still prior-only, with the wide error",
          wins.prior_only and wins.window == 28 and wins.n_pairs == 0 and wins.se > 0 and 0 < m.share(wins, 0)[0] < m.share(wins, 6)[0] <= 1.0, wins)

    print("[8] a window whose interval straddles a threshold is undecided; matured, it is decided (brief 8)")
    cc = m.Curve("exp", 1.5, 1.0, 0.15, W, "count", 600, 7, False, dispersion=1.0)
    cv = m.Curve("exp", 3.0, 1.0, 0.3, W, "value", 600, 7, False, dispersion=1.3)
    as_of = "2026-09-10"
    recent = [{"day": (date.fromisoformat(as_of) - timedelta(days=a)).isoformat(), "spend": 100.0, "count": 6.0, "value": 150.0} for a in (1, 2, 3)]
    adj = m.adjust(recent, as_of, cc, cv, P)
    win = m.summarize(adj, recent[2]["day"], recent[0]["day"], P)
    check("three recent days (ages 1 to 3) seen at 150 a day on 100 spent: a return of 1.5 observed, and an estimate above it with an interval; the window is immature",
          win["return"]["observed"] == 1.5 and win["return"]["estimate"] > 1.5 and win["return"]["low"] < win["return"]["estimate"] < win["return"]["high"] and win["immature"] and win["share"] < 0.9, win["return"])
    check("a benchmark inside the interval: undecided_immature, never a verdict; one under the whole interval is above, one over it is below",
          m.judge(win, win["return"]["estimate"], P) == "undecided_immature" and m.judge(win, win["return"]["low"] * 0.5, P) == "above" and m.judge(win, win["return"]["high"] * 2, P) == "below", win["return"])
    ripe = [{"day": (date.fromisoformat(as_of) - timedelta(days=a)).isoformat(), "spend": 100.0, "count": 6.0, "value": 150.0} for a in (8, 9, 10)]
    rw = m.summarize(m.adjust(ripe, as_of, cc, cv, P), ripe[2]["day"], ripe[0]["day"], P)
    thr = win["return"]["estimate"]
    check("the same window at age 8 to 10: nothing left to arrive, share 1, not immature; it is decided on its return, and the same threshold now says below",
          rw["share"] == 1.0 and not rw["immature"] and rw["return"]["observed"] == rw["return"]["estimate"] == 1.5 and rw["return"]["low"] == rw["return"]["high"] == 1.5
          and m.judge(rw, thr, P) == "below" and m.judge(rw, 1.4, P) == "above", (rw["return"], thr))
    check("the window's arithmetic: spend adds, counts and values add, the return is the value estimate over the spend", abs(win["spend"] - 300.0) < 1e-9 and abs(win["value"]["observed"] - 450.0) < 1e-9
          and abs(win["return"]["estimate"] - win["value"]["estimate"] / 300.0) < 1e-9 and abs(win["value"]["estimate"] - sum(a["value"]["estimate"] for a in adj)) < 1e-9)
    check("the curve's own uncertainty is shared by the days: three days' interval is wider in proportion than one day's, and a sharper curve narrows it",
          (win["value"]["high"] - win["value"]["low"]) / win["value"]["estimate"] > 0.5 * (adj[0]["value"]["high"] - adj[0]["value"]["low"]) / adj[0]["value"]["estimate"]
          and (lambda w: w["value"]["high"] - w["value"]["low"])(m.summarize(m.adjust(recent, as_of, cc, replace_se(cv, 0.05), P), recent[2]["day"], recent[0]["day"], P)) < win["value"]["high"] - win["value"]["low"])
    check("a window with no spend has no return, not a division by zero", m.summarize(m.adjust([{"day": "2026-09-09", "spend": 0.0, "count": 0.0, "value": 0.0}], as_of, cc, cv, P), "2026-09-09", "2026-09-09", P)["return"]["estimate"] is None)
    return finish()


def replace_se(curve, se):
    return m.Curve(**{**curve.to_dict(), "se": se})


if __name__ == "__main__":
    raise SystemExit(main())
