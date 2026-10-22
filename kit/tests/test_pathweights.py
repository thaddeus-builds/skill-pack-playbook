#!/usr/bin/env python3
"""kit.pathweights: path weights for a skill pack's variants, on SYNTHETIC numbers only (DEMO ids, neutral tags).

  [1] the settings: the defaults, a skill pack's own laid over them, every kind of value refused, the message naming the
      key (an unknown key, not a number, not finite, a bool, a count not whole, a probability or share outside (0, 1),
      close_ratio outside (0, 1], prior_shift_max below 1, twin_ratio not above 1, anything else not above 0), and
      downweight_p not below promising_p
  [2] the statistics against known values: gamma_cdf (closed forms for shapes 1, 2 and 1/2, the recurrence to 7.5, both
      branches; shapes 1e8 and 1e9 against Wilson-Hilferty, and a series cut short raises), p_above, quantile (the
      inverse, closed form at shape 1), tenths (rounded toward a half)
  [3] the partition: every node's numbers are the sum of its leaves' (seeded random partitions, mixed depths), the
      account covers every leaf (a larger total taken, a smaller one refused); the posterior worked by hand, borrowed
      leave-one-out; a leaf with no numbers has its parent's mean; the shift clipped both ways; no rate, no posterior;
      fractional conversions; bad leaves refused (parents as a set among them)
  [4] judge(): every state with its reason, and the close proposal's conditions one at a time (enough spend, enough
      units with settled spend, unlikely to reach close_ratio, down at all), each threshold moved by the settings; warm
      decided by the settings in hand, not the account's own `warm`; a person's close stands over everything
  [5] pick(): cold = the skill pack's coverage order, whole moves, up to two over; warm = the explore share kept, at most
      half a batch per group (a bigger move alone), exclusive keys never both, shared keys together, a fill up to two
      over rather than short (the explore share too, only when nothing within fits), the same data the same batch (keys
      in any order or as a set, in two processes with different PYTHONHASHSEED; another number, another batch); warm
      decided by the settings in hand; bad moves refused
  [6] twins(): flagged only past every threshold, with the known differences; at most three, the largest gap first
  [7] calibration by simulation: every leaf equally good, five rounds, spend pushed to early leaders, two units per made
      leaf: at most 5 in 100 made leaves are ever proposed for closing (the measured rates are printed)
  [8] past_signal(): units the plan did not make (a client's past ads) as a gap signal, never a weight: the pool's own
      rate, P(better) worked by hand (a closed form), strong and weak reads under each threshold, gaps (strong, none of
      ours) and warnings (weak, enough of ours), a cold pool judges nothing, every bad input refused, the same result
      in any order; the result is no input of posteriors(), judge() or pick() (their results and sources); with every
      group equally good the share reading strong or weak is measured (a pointer, not a proof)
"""

import copy
import json
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # ROOT

from kit import pathweights as W  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]


def raises(fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
    except ValueError:
        return True
    return False


def message(fn, *a, **kw) -> str:
    """The ValueError's message, or "" when nothing is refused."""
    try:
        fn(*a, **kw)
    except ValueError as e:
        return str(e)
    return ""


# ---------------------------------------------------------------- [1] settings

def test_settings() -> None:
    print("[1] the settings")
    check("the defaults", W.DEFAULTS == {
        "prior_conv": 2.0, "account_min_conv": 10.0, "min_expected_conv": 3.0, "promising_p": 0.8, "downweight_p": 0.2,
        "close_min_expected_conv": 5.0, "close_min_units": 2, "close_ratio": 0.7, "close_p": 0.1, "batch_size": 5,
        "explore_share": 0.3, "twin_min_conv": 6.0, "twin_min_expected_conv": 2.0, "twin_ratio": 2.0, "twin_p": 0.9,
        "prior_shift_max": 1.5, "past_min_expected_conv": 3.0, "past_warn_units": 3}, W.DEFAULTS)
    check("every setting says what it is", all(isinstance(t, str) and t for _, _, _, t in W.SETTINGS))
    got = W.settings({"batch_size": "4", "close_p": 0.25, "close_min_units": 3.0})
    check("a skill pack's own values are laid over the defaults, typed",
          got["batch_size"] == 4 and isinstance(got["batch_size"], int) and got["close_p"] == 0.25
          and got["close_min_units"] == 3 and isinstance(got["close_min_units"], int)
          and got["twin_p"] == W.DEFAULTS["twin_p"], got)
    check("no override: the defaults", W.settings() == W.DEFAULTS and W.settings({}) == W.DEFAULTS)
    bad = [("no_such_key", 1), ("batch_size", "five"), ("batch_size", 2.5), ("batch_size", 0), ("batch_size", True),
           ("prior_conv", float("nan")), ("prior_conv", float("inf")), ("prior_conv", 0), ("prior_conv", -1),
           ("promising_p", 1.0), ("downweight_p", 0.0), ("close_p", 1.2), ("twin_p", -0.1), ("explore_share", 1),
           ("close_ratio", 0), ("close_ratio", 1.01), ("prior_shift_max", 0.99), ("twin_ratio", 0),
           ("twin_ratio", 0.5), ("twin_ratio", 1), ("account_min_conv", None), ("past_min_expected_conv", 0),
           ("past_warn_units", 0), ("past_warn_units", 1.5)]
    check("every value that is not one is refused, the message naming the key",
          all(k in message(W.setting, k, v) for k, v in bad),
          [(k, v, message(W.setting, k, v)) for k, v in bad if k not in message(W.setting, k, v)])
    check("…and settings() refuses it too, naming the key",
          "close_p" in message(W.settings, {"close_p": 1.5}) and "nope" in message(W.settings, {"nope": 1})
          and "twin_ratio" in message(W.settings, {"twin_ratio": 1}),
          [message(W.settings, o) for o in ({"close_p": 1.5}, {"nope": 1}, {"twin_ratio": 1})])
    crossed = [{"downweight_p": 0.85}, {"promising_p": 0.15}, {"promising_p": 0.3, "downweight_p": 0.4},
               {"promising_p": 0.5, "downweight_p": 0.5}]
    said = [message(W.settings, o) for o in crossed]
    check("settings() keeps downweight_p below promising_p (each fine alone, the pair refused), naming both",
          all("downweight_p" in m and "promising_p" in m for m in said)
          and all(not raises(W.setting, k, v) for o in crossed for k, v in o.items())
          and W.settings({"promising_p": 0.6, "downweight_p": 0.4})["downweight_p"] == 0.4, said)
    check("…and every function taking settings refuses the pair",
          raises(W.judge, None, W.account(70, 10000), made=0, spend=0, settled=0, cfg={"downweight_p": 0.85})
          and raises(W.pick, [], W.account(70, 10000), {"downweight_p": 0.85}))
    check("the edges that are values", W.setting("close_ratio", 1) == 1.0 and W.setting("prior_shift_max", 1) == 1.0
          and W.setting("explore_share", 0.999) == 0.999 and W.setting("twin_ratio", 1.01) == 1.01)


# ---------------------------------------------------------------- [2] statistics

def _p_half(x: float) -> float:
    """P(1/2, x) = erf(sqrt(x))."""
    return math.erf(math.sqrt(x))


def _p_up(a: float, x: float, p_a: float) -> float:
    """P(a + 1, x) = P(a, x) - x^a e^-x / Gamma(a + 1)."""
    return p_a - math.exp(a * math.log(x) - x - math.lgamma(a + 1))


def test_statistics() -> None:
    print("\n[2] the statistics")
    errs = []
    for x in (0.01, 0.1, 0.5, 1.0, 1.9, 2.0, 2.1, 5.0, 10.0, 30.0):     # the series (x < a + 1) and the fraction
        errs.append(abs(W.gamma_cdf(1, x) - (1 - math.exp(-x))))
        errs.append(abs(W.gamma_cdf(2, x) - (1 - math.exp(-x) * (1 + x))))
        errs.append(abs(W.gamma_cdf(0.5, x) - _p_half(x)))
    check("gamma_cdf: the closed forms for shapes 1, 2 and 1/2", max(errs) < 1e-12, max(errs))
    errs = []
    for x in (0.01, 0.5, 2.0, 5.0, 8.0, 10.0, 30.0):
        p = _p_half(x)
        for a in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5):
            p = _p_up(a, x, p)
        errs.append(abs(W.gamma_cdf(7.5, x) - p))
    check("gamma_cdf: shape 7.5 by the recurrence from 1/2", max(errs) < 1e-10, max(errs))
    check("gamma_cdf: 0 at and below 0; the median of Gamma(40) just under 40",
          W.gamma_cdf(3.0, 0) == 0.0 and W.gamma_cdf(3.0, -1.0) == 0.0 and abs(W.gamma_cdf(40.0, 40.0) - 0.5210) < 1e-3)
    check("gamma_cdf refuses a shape that is not above 0", raises(W.gamma_cdf, 0, 1.0) and raises(W.gamma_cdf, -1, 1.0))

    def wilson_hilferty(a: float, x: float) -> float:
        """P(a, x) by the cube-root normal approximation: its error falls like 1 / a, under 1e-6 from a = 1e8."""
        z = ((x / a) ** (1 / 3) - (1 - 1 / (9 * a))) / math.sqrt(1 / (9 * a))
        return 0.5 * math.erfc(-z / math.sqrt(2))
    large = [(1e8, 1e8 - 5000), (1e8, 1e8), (1e8, 1e8 + 5000), (1e8, 1e8 - 30000), (1e9, 1e9 - 15811),
             (1e9, 1e9 + 15811)]
    errs = [abs(W.gamma_cdf(a, x) - wilson_hilferty(a, x)) for a, x in large]
    check("gamma_cdf at shapes 1e8 and 1e9 (a leaf counting clicks): both branches run to convergence, within 1e-5 "
          "of Wilson-Hilferty", max(errs) < 1e-5, errs)
    check("…and so do p_above and quantile there",
          abs(W.p_above(1e8, 1e8, 1.0) - (1 - wilson_hilferty(1e8, 1e8))) < 1e-5
          and abs(W.gamma_cdf(1e8, 1e8 * W.quantile(1e8, 1e8, 0.1)) - 0.1) < 1e-6)   # lgamma(1e8) ~ 2e9: 1e-7
    kept = W._terms
    W._terms = lambda a: 10                         # far too few terms: the series and the fraction stop short
    try:
        said = [message(W.gamma_cdf, 1e8, 1e8), message(W.gamma_cdf, 1e8, 1e8 + 5000)]
    finally:
        W._terms = kept
    check("a series or a continued fraction that does not converge raises, never returns a truncated value",
          "series did not converge" in said[0] and "continued fraction did not converge" in said[1], said)
    check("p_above, Gamma(shape, rate)",
          abs(W.p_above(1, 2, 0.5) - math.exp(-1)) < 1e-12 and abs(W.p_above(2, 100, 0.03) - math.exp(-3) * 4) < 1e-12
          and abs(W.p_above(0.5, 4, 0.25) - (1 - _p_half(1.0))) < 1e-12)
    errs = []
    for q in (0.05, 0.1, 0.5, 0.9, 0.99):
        errs.append(abs(W.quantile(1, 1, q) + math.log(1 - q)))
        errs.append(abs(W.quantile(1, 200, q) + math.log(1 - q) / 200) * 200)
        for a, b in ((0.5, 1.0), (2.0, 400.0), (7.5, 3.0), (52.0, 9000.0)):
            errs.append(abs(W.gamma_cdf(a, b * W.quantile(a, b, q)) - q))
    check("quantile: the closed form at shape 1, and the inverse of gamma_cdf in the rate's units", max(errs) < 1e-9,
          max(errs))
    check("quantile refuses q outside (0, 1)", raises(W.quantile, 2, 1, 0) and raises(W.quantile, 2, 1, 1.0))
    table = ((0.79, 7), (0.8, 8), (0.21, 3), (0.2, 2), (0.5, 5), (0.0, 0), (1.0, 10), (0.999, 9), (0.001, 1),
             (0.55, 5), (0.45, 5), (0.7, 7), (0.3, 3))
    check("tenths: rounded toward a half, so 0.79 reads 7 and 0.21 reads 3",
          all(W.tenths(p) == n for p, n in table), [(p, W.tenths(p), n) for p, n in table if W.tenths(p) != n])


# ---------------------------------------------------------------- [3] the partition

def rand_leaves(seed: int) -> list[dict]:
    """Leaves under one to three levels of DEMO keys (mixed depths), some with no numbers, fractional conversions."""
    rng = random.Random(seed)
    out = []
    for i in range(rng.randint(5, 30)):
        depth = rng.randint(0, 3)
        parents = [f"DEMO-{'abc'[d]}{rng.randint(1, 3)}" for d in range(depth)]
        made = rng.random() < 0.7
        out.append({"id": f"DEMO-L{i:02d}", "parents": parents,
                    "conv": round(rng.uniform(0, 12), 2) if made else 0.0,
                    "spend": round(rng.uniform(100, 3000), 2) if made else 0.0})
    return out


def test_partition() -> None:
    print("\n[3] the partition")
    bad = []
    for seed in range(40):
        leaves = rand_leaves(seed)
        got = W.posteriors(leaves)
        for key, n in got["nodes"].items():
            under = [x for x in leaves if tuple(x["parents"][:len(key)]) == key]
            kids = [k for k in got["nodes"] if len(k) == len(key) + 1 and k[:-1] == key]
            direct = [x for x in leaves if tuple(x["parents"]) == key]
            if not (math.isclose(n["conv"], sum(x["conv"] for x in under), abs_tol=1e-9)
                    and math.isclose(n["spend"], sum(x["spend"] for x in under), abs_tol=1e-9)
                    and n["leaves"] == len(under)
                    and math.isclose(n["conv"], sum(got["nodes"][k]["conv"] for k in kids)
                                     + sum(x["conv"] for x in direct), abs_tol=1e-9)
                    and math.isclose(n["spend"], sum(got["nodes"][k]["spend"] for k in kids)
                                     + sum(x["spend"] for x in direct), abs_tol=1e-9)):
                bad.append((seed, key))
        acct = got["account"]
        if not (math.isclose(acct["conv"], sum(x["conv"] for x in leaves), abs_tol=1e-9)
                and math.isclose(acct["spend"], sum(x["spend"] for x in leaves), abs_tol=1e-9)):
            bad.append((seed, "account"))
        if acct["rate"] and not math.isclose(acct["post"][0] / acct["post"][1], acct["rate"], rel_tol=1e-12):
            bad.append((seed, "account mean"))
    check("every node's numbers are its leaves' and its children's sums; the account's are all of them (40 seeds)",
          not bad, bad[:5])

    leaves = [{"id": "DEMO-1", "parents": ["DEMO-a", "DEMO-x"], "conv": 4.5, "spend": 1500},
              {"id": "DEMO-2", "parents": ["DEMO-a", "DEMO-x"], "conv": 11.2, "spend": 2500},
              {"id": "DEMO-3", "parents": ["DEMO-a", "DEMO-y"], "conv": 9, "spend": 1000},
              {"id": "DEMO-4", "parents": ["DEMO-b"], "conv": 3, "spend": 1000},
              {"id": "DEMO-5", "parents": [], "conv": 0, "spend": 0}]
    got = W.posteriors(leaves)
    a0, y, s = 2.0, 27.7, 6000.0
    rate = y / s
    acct = (a0 + y, a0 / rate + s)

    def loo(post, yy, ss):
        return (post[0] - yy) / (post[1] - ss)
    pa = (a0 + 24.7, a0 / loo(acct, 24.7, 5000) + 5000)
    px = (a0 + 15.7, a0 / loo(pa, 15.7, 4000) + 4000)
    p1 = (a0 + 4.5, a0 / loo(px, 4.5, 1500) + 1500)
    pb = (a0 + 3, a0 / loo(acct, 3, 1000) + 1000)
    p4 = (a0 + 3, a0 / loo(pb, 3, 1000) + 1000)
    close = all(math.isclose(u, v, rel_tol=1e-12) for u, v in zip(
        (*got["account"]["post"], *got["nodes"][("DEMO-a",)]["post"], *got["nodes"][("DEMO-a", "DEMO-x")]["post"],
         *got["leaves"]["DEMO-1"], *got["nodes"][("DEMO-b",)]["post"], *got["leaves"]["DEMO-4"]),
        (*acct, *pa, *px, *p1, *pb, *p4)))
    check("the posterior worked by hand: each level borrowed from its parent, leave-one-out, worth prior_conv",
          close and got["account"]["rate"] == rate and got["account"]["warm"], got)
    p5 = got["leaves"]["DEMO-5"]
    check("a leaf with no numbers has its parent's mean (here the account's), worth prior_conv",
          math.isclose(p5[0] / p5[1], rate, rel_tol=1e-12) and p5[0] == a0)
    one = W.posteriors([{"id": "DEMO-1", "parents": ["DEMO-a"], "conv": 12, "spend": 3000}])
    n = one["nodes"][("DEMO-a",)]["post"]
    check("a node that holds all the account's numbers borrows the account's rate",
          math.isclose(n[1], a0 / (12 / 3000) + 3000, rel_tol=1e-12))
    big = W.posteriors(leaves, total=(40.0, 9000.0))
    check("a larger account total (units on no leaf) is taken, and moves every prior",
          big["account"]["conv"] == 40.0 and big["account"]["rate"] == 40 / 9000
          and big["leaves"]["DEMO-1"] != got["leaves"]["DEMO-1"])
    check("an account total smaller than the leaves' sums is refused",
          raises(W.posteriors, leaves, total=(20.0, 9000.0)) and raises(W.posteriors, leaves, total=(40.0, 5000.0)))

    def leaf1(shift, cfg=None):
        return W.posteriors([{**leaves[0], "shift": shift}, *leaves[1:]], cfg)["leaves"]["DEMO-1"]
    base = got["leaves"]["DEMO-1"]
    m0 = loo(px, 4.5, 1500)
    ok = True
    for k, used in ((1.3, 1.3), (3.0, 1.5), (0.2, 1 / 1.5), (1.0, 1.0)):
        p = leaf1(k)
        ok = ok and math.isclose(p[1], a0 / (m0 * used) + 1500, rel_tol=1e-12) and p[0] == base[0]
    check("the shift moves the leaf's prior mean, clipped to [1 / prior_shift_max, prior_shift_max]", ok)
    check("prior_shift_max 1: the shift moves nothing", leaf1(3.0, {"prior_shift_max": 1}) == base)
    check("…and only the leaf's own prior: its nodes are untouched",
          W.posteriors([{**leaves[0], "shift": 1.4}, *leaves[1:]])["nodes"] == got["nodes"])
    cold = W.posteriors([{"id": "DEMO-1", "parents": ["DEMO-a"], "conv": 0, "spend": 500}])
    check("no account rate: every posterior is None, the account not warm",
          cold["account"]["rate"] is None and cold["account"]["post"] is None and not cold["account"]["warm"]
          and cold["leaves"] == {"DEMO-1": None} and cold["nodes"][("DEMO-a",)]["post"] is None)
    thin = W.posteriors([{"id": "DEMO-1", "parents": [], "conv": 9.5, "spend": 500}])
    check("a rate under account_min_conv: posteriors, but not warm",
          thin["account"]["rate"] == 9.5 / 500 and not thin["account"]["warm"] and thin["leaves"]["DEMO-1"] is not None
          and W.account(10, 500)["warm"] and not W.account(10, 500, {"account_min_conv": 11})["warm"])
    frac = W.posteriors([{"id": "DEMO-1", "parents": ["DEMO-a"], "conv": 2.75, "spend": 900},
                         {"id": "DEMO-2", "parents": ["DEMO-a"], "conv": 8.25, "spend": 900}])
    check("parents in a tuple are a list's",
          W.posteriors([{**x, "parents": tuple(x["parents"])} for x in leaves]) == got)
    check("fractional conversions are numbers like any other", frac["account"]["conv"] == 11.0
          and frac["leaves"]["DEMO-1"][0] == 4.75)
    wrong = [[{"id": "DEMO-1", "parents": [], "conv": -1, "spend": 10}],
             [{"id": "DEMO-1", "parents": [], "conv": float("nan"), "spend": 10}],
             [{"id": "DEMO-1", "parents": [], "conv": True, "spend": 10}],
             [{"id": "DEMO-1", "parents": [], "conv": 1, "spend": None}],
             [{"id": "DEMO-1", "parents": "DEMO-a", "conv": 1, "spend": 10}],
             [{"id": "DEMO-1", "parents": [""], "conv": 1, "spend": 10}],
             [{"id": "DEMO-1", "parents": {"DEMO-a", "DEMO-b"}, "conv": 1, "spend": 10}],
             [{"id": "DEMO-1", "parents": frozenset({"DEMO-a"}), "conv": 1, "spend": 10}],
             [{"id": "DEMO-1", "parents": [], "conv": 1, "spend": 10, "shift": 0}],
             [{"id": "", "parents": [], "conv": 1, "spend": 10}],
             [{"id": "DEMO-1", "conv": 1, "spend": 10}, {"id": "DEMO-1", "conv": 1, "spend": 10}]]
    check("a bad leaf is refused: negative, not finite, a bool, missing, parents not a list of keys (a set has no "
          "order), a zero shift, no id, an id twice", all(raises(W.posteriors, x) for x in wrong),
          [i for i, x in enumerate(wrong) if not raises(W.posteriors, x)])


# ---------------------------------------------------------------- [4] judge

# the rest of the account: 40 conversions at 0.005; the leaf judged is DEMO-T, under DEMO-a / DEMO-a1
BASE = [{"id": "DEMO-L1", "parents": ["DEMO-b", "DEMO-b1"], "units": [(2000, 10), (2000, 10)]},
        {"id": "DEMO-L2", "parents": ["DEMO-b", "DEMO-b1"], "units": [(2000, 10)]},
        {"id": "DEMO-L3", "parents": ["DEMO-a", "DEMO-a1"], "units": [(2000, 10)]}]


def state(units, cfg=None, base=BASE, closed=False) -> dict:
    """judge() of DEMO-T made by one unit per entry of `units` ((spend, conv) settled, or None: none yet)."""
    leaves = []
    for x in base + [{"id": "DEMO-T", "parents": ["DEMO-a", "DEMO-a1"], "units": units}]:
        got = [u for u in x["units"] if u is not None]
        leaves.append({"id": x["id"], "parents": x["parents"], "conv": sum(c for _, c in got),
                       "spend": sum(s for s, _ in got), "settled": sum(1 for s, _ in got if s > 0),
                       "made": len(x["units"])})
    pw = W.posteriors(leaves, cfg)
    t = leaves[-1]
    return W.judge(pw["leaves"]["DEMO-T"], pw["account"], made=t["made"], spend=t["spend"], settled=t["settled"],
                   closed=closed, cfg=cfg)


def test_judge() -> None:
    print("\n[4] judge(): the states and the close proposal")
    check("every reason gives a state", set(W.REASONS.values()) == set(W.STATES))
    p = state([])
    check("untested: nothing made", (p["state"], p["why"]) == ("untested", "not_made") and "p_better" not in p, p)
    p = state([(1000, 15), (1000, 15)])
    check("promising: likely better than the account",
          (p["state"], p["why"]) == ("promising", "likely_better") and p["p_better"] >= 0.8
          and p["expected"] == round(2000 * 70 / 10000, 3) and p["lo"] < p["rate"] < p["hi"], p)
    thin = [{**x, "units": [(s, c / 10) for s, c in x["units"]]} for x in BASE]
    p = state([(1000, 0.5), (1000, 0.4)], base=thin)
    check("testing, account_thin: the account has too few conversions, whatever the leaf shows",
          (p["state"], p["why"]) == ("testing", "account_thin") and "p_better" not in p, p)
    p = state([None, None], base=thin)
    check("testing, no_settled_numbers: made, nothing settled (cold)",
          (p["state"], p["why"]) == ("testing", "no_settled_numbers"), p)
    p = state([None])
    check("testing, no_settled_numbers: a warm account, nothing settled here",
          (p["state"], p["why"]) == ("testing", "no_settled_numbers"), p)
    p = state([(300, 0)])
    check("testing, spend_thin: its spend buys fewer than min_expected_conv at the account rate",
          (p["state"], p["why"]) == ("testing", "spend_thin") and p["expected"] < 3, p)
    p = state([(1000, 5), (1000, 5)])
    check("testing, no_difference_yet: between the lines",
          (p["state"], p["why"]) == ("testing", "no_difference_yet") and 0.2 < p["p_better"] < 0.8, p)
    p = state([(1000, 0.5), (1000, 0.5)])
    check("down: likely worse", (p["state"], p["why"]) == ("down", "likely_worse") and p["p_better"] <= 0.2, p)
    check("closed: a person's close stands over everything",
          state([(1000, 0.5), (1000, 0.5)], closed=True) == {"state": "closed", "why": "closed_by_person",
                                                              "propose_close": False}
          and state([], closed=True)["state"] == "closed")

    p = state([(1000, 0.5), (1000, 0.5)])
    check("a close is proposed when every condition holds", p["propose_close"] is True and p["expected"] >= 5
          and p["p_reaches"] <= 0.1, p)
    p = state([(2000, 1.0)])
    check("…not with one unit (close_min_units), whatever its numbers",
          p["state"] == "down" and p["p_reaches"] <= 0.1 and p["expected"] >= 5 and p["propose_close"] is False, p)
    p = state([(2000, 1.0), None])
    check("…not when the second unit has no settled numbers yet", p["propose_close"] is False, p)
    p = state([(450, 0), (450, 0)])
    check("…not when its spend buys fewer than close_min_expected_conv",
          p["state"] == "down" and p["p_reaches"] <= 0.1 and 3 <= p["expected"] < 5 and p["propose_close"] is False, p)
    p = state([(600, 1.5), (600, 1.5)])
    check("…not while reaching close_ratio of the account is still plausible (close_p)",
          p["state"] == "down" and p["expected"] >= 5 and p["p_reaches"] > 0.1 and p["propose_close"] is False, p)
    check("…and a skill pack's own close_p moves it", state([(600, 1.5), (600, 1.5)], {"close_p": 0.5})["propose_close"])
    p = state([(3000, 15), (3000, 15)])
    check("…never when not down, however much was spent", p["state"] == "testing" and p["propose_close"] is False, p)
    moved = [({"close_min_units": 3}, "units"), ({"close_min_expected_conv": 50.0}, "spend"),
             ({"close_ratio": 0.1}, "ratio"), ({"downweight_p": 0.0001}, "down"),
             ({"account_min_conv": 1000.0}, "warm"), ({"min_expected_conv": 100.0}, "judged")]
    check("each threshold moves with the settings passed in",
          all(not state([(1000, 0.5), (1000, 0.5)], cfg)["propose_close"] for cfg, _ in moved),
          [w for cfg, w in moved if state([(1000, 0.5), (1000, 0.5)], cfg)["propose_close"]])
    check("…and so do the states", state([(1000, 15), (1000, 15)], {"promising_p": 0.99999})["state"] == "testing"
          and state([(1000, 15), (1000, 15)], {"min_expected_conv": 50.0})["why"] == "spend_thin")
    two = [{"id": "DEMO-L1", "conv": 0, "spend": 1500}, {"id": "DEMO-L2", "conv": 15, "spend": 1500}]
    pw = W.posteriors(two)                          # built with the defaults: 15 conversions, warm
    strict = {"account_min_conv": 40.0}

    def l1(acct, cfg=None):
        return W.judge(pw["leaves"]["DEMO-L1"], acct, made=2, spend=1500, settled=2, cfg=cfg)
    p, q = l1(pw["account"], strict), l1(pw["account"])
    check("warm is decided by the settings judge() is given, not by the account's own `warm`: an account built "
          "with the defaults, judged with a higher account_min_conv, is thin",
          pw["account"]["warm"] and (p["state"], p["why"], p["propose_close"]) == ("testing", "account_thin", False)
          and (q["state"], q["why"], q["propose_close"]) == ("down", "likely_worse", True), (p, q))
    cold = {**pw["account"], "warm": False}         # what account(15, 3000, strict) says under its own settings
    p = l1(cold)
    check("…and one built with a higher account_min_conv, judged with the defaults, is judged",
          not W.account(15, 3000, strict)["warm"] and (p["state"], p["why"]) == ("down", "likely_worse")
          and l1(W.account(15, 3000, strict))["state"] == "down", p)
    check("…no rate is never warm, and a bad account is refused",
          l1({"conv": 15.0, "spend": 0.0, "rate": None, "warm": True})["why"] == "account_thin"
          and raises(l1, {"conv": None, "spend": 3000.0, "rate": 0.005}) and raises(l1, "warm"))
    acct = W.account(70, 10000)
    check("judge refuses what cannot be: more settled than made, a warm judgement with no posterior",
          raises(W.judge, (3, 400), acct, made=1, spend=100, settled=2)
          and raises(W.judge, None, acct, made=1, spend=100, settled=1)
          and raises(W.judge, (3, 400), acct, made=1, spend=-1, settled=1))


# ---------------------------------------------------------------- [5] pick

WARM = W.account(70, 10000)
COLD = W.account(4, 10000)


def mv(i, group, n=1, kind="unknown", post=None, **kw) -> dict:
    return {"id": f"DEMO-m{i}", "group": group, "n": n, "kind": kind, "post": post, **kw}


def moves_mix() -> list[dict]:
    """Known-good moves on two strong leaves, unknown ones on four groups (one of three units)."""
    return [mv(1, "DEMO-g1", 2, "known", (32.0, 2000.0), note="a"), mv(2, "DEMO-g1", 1, "known", (30.0, 2100.0)),
            mv(3, "DEMO-g2", 1, "unknown", (12.0, 1800.0)), mv(4, "DEMO-g3", 3, "unknown", None),
            mv(5, "DEMO-g4", 1, "unknown", (6.0, 1500.0)), mv(6, "DEMO-g2", 2, "unknown", (9.0, 1400.0)),
            mv(7, "DEMO-g5", 1, "known", (25.0, 2500.0))]


def per_group(plan) -> dict:
    out: dict[str, int] = {}
    for b in plan["batch"]:
        out[b["group"]] = out.get(b["group"], 0) + b["n"]
    return out


def test_pick() -> None:
    print("\n[5] pick(): the next batch")
    cold = [mv(1, "DEMO-g1", 3), mv(2, "DEMO-g1", 1), mv(3, "DEMO-g2", 1), mv(4, "DEMO-g3", 3), mv(5, "DEMO-g4", 1)]
    plan = W.pick(cold, COLD)
    check("cold: coverage, the moves in the order given, whole, up to two over",
          plan["mode"] == "coverage" and [b["id"] for b in plan["batch"]] == ["DEMO-m1", "DEMO-m3", "DEMO-m4"]
          and plan["n"] == 7 and all(b["basis"] == "coverage" for b in plan["batch"]) and plan["left"] == 2, plan)
    plan = W.pick(cold[1:], COLD, {"batch_size": 4})
    check("cold: a group takes at most half a batch; the batch stops once full",
          [b["id"] for b in plan["batch"]] == ["DEMO-m2", "DEMO-m3", "DEMO-m4"] and plan["n"] == 5, plan)
    plan = W.pick([mv(1, "DEMO-g1", 1, exclusive=["DEMO-k"]), mv(2, "DEMO-g2", 1, exclusive=["DEMO-k"]),
                   mv(3, "DEMO-g3", 1, shared=["DEMO-k"]), mv(4, "DEMO-g4", 1, shared=["DEMO-j"]),
                   mv(5, "DEMO-g5", 1, shared=["DEMO-j"])], COLD)
    check("cold: an exclusive key never twice nor beside a shared one; two shared ones together",
          [b["id"] for b in plan["batch"]] == ["DEMO-m1", "DEMO-m4", "DEMO-m5"], plan)

    ms = moves_mix()
    plan = W.pick(ms, WARM)
    check("warm: weights; each entry its move without post, with basis and p_better against the account rate",
          plan["mode"] == "weights" and all(b["basis"] == "weights" and "post" not in b for b in plan["batch"])
          and all(b["p_better"] == round(W.p_above(*(m["post"] or (2.0, 2.0 / 0.007)), 0.007), 4)
                  for b in plan["batch"] for m in ms if m["id"] == b["id"])
          and plan["n"] == sum(b["n"] for b in plan["batch"]) and plan["moves"] == 7
          and plan["left"] == 7 - len(plan["batch"]), plan)
    check("…and any other key of a move rides along", all(b.get("note") == "a" for b in plan["batch"]
                                                          if b["id"] == "DEMO-m1"))
    broken = []
    for k in range(3, 11):
        for share in (0.1, 0.2, 0.3, 0.5, 0.7):
            for shift in range(8):
                m2 = copy.deepcopy(ms)
                m2[0]["post"] = (32.0 + shift, 2000.0)
                plan = W.pick(m2, WARM, {"batch_size": k, "explore_share": share})
                unknown = sum(b["n"] for b in plan["batch"] if b["kind"] == "unknown")
                if unknown < min(math.ceil(share * k - 1e-9), 7):
                    broken.append(("share", k, share, shift, unknown))
                for g, v in per_group(plan).items():
                    mine = [b for b in plan["batch"] if b["group"] == g]
                    if v > max(1, k // 2) and len(mine) != 1:          # over half a batch: one move alone
                        broken.append(("group", k, share, shift, g, v))
                if plan["n"] > k + 2:
                    broken.append(("over", k, share, shift, plan["n"]))
    check("warm: at least explore_share of the batch is unknown, a group at most half a batch (a bigger move alone), "
          "never more than two over (k 3..10, five shares, eight numbers each)", not broken, broken[:5])
    strong = [mv(10 * i + j, f"DEMO-g{i}", 1, "known", (40.0, 2000.0)) for i in range(1, 5) for j in range(2)]
    strong.append(mv(99, "DEMO-g9", 3, "unknown", (2.0, 2.0 / 0.007)))
    seen = [sum(b["n"] for b in W.pick(strong, WARM, {"batch_size": k})["batch"] if b["kind"] == "unknown")
            for k in (4, 5, 6, 8)]
    check("the explore share keeps the one unknown move even when the draws favour the known ones",
          seen == [3] * 4, seen)
    excl = [mv(1, "DEMO-g1", 1, "known", (40.0, 2000.0), exclusive=["DEMO-card"]),
            mv(2, "DEMO-g2", 1, "known", (40.0, 2000.0), exclusive=["DEMO-card"]),
            mv(3, "DEMO-g3", 1, "known", (40.0, 2000.0), shared=["DEMO-card"]),
            mv(4, "DEMO-g4", 1, "known", (40.0, 2000.0), shared=["DEMO-card"]),
            mv(5, "DEMO-g5", 1, "unknown", None), mv(6, "DEMO-g6", 1, "unknown", None),
            mv(7, "DEMO-g7", 1, "unknown", None)]
    bad, both_shared = [], 0
    for s in range(60):
        b = {x["id"] for x in W.pick(excl, WARM, seed=s)["batch"]}
        if {"DEMO-m1", "DEMO-m2"} <= b or (b & {"DEMO-m1", "DEMO-m2"} and b & {"DEMO-m3", "DEMO-m4"}):
            bad.append((s, sorted(b)))
        both_shared += {"DEMO-m3", "DEMO-m4"} <= b
    check("warm: moves sharing an exclusive key never both, an exclusive never beside a shared (60 seeds)",
          not bad, bad)
    check("…while two shared ones fit together", both_shared > 0, both_shared)
    plan = W.pick([mv(1, "DEMO-g1", 3), mv(2, "DEMO-g2", 3)], WARM)
    check("a fill up to two over rather than short", plan["n"] == 6 and len(plan["batch"]) == 2, plan)
    big = mv(3, "DEMO-g3", 6, "unknown", (60.0, 6000.0))
    known = [mv(4, "DEMO-g4", 1, "known"), mv(5, "DEMO-g5", 1, "known"), mv(6, "DEMO-g6", 1, "known")]
    fill = [mv(1, "DEMO-g1", 1, "unknown", (2.0, 500.0)), mv(2, "DEMO-g2", 1, "unknown", (2.0, 500.0)), big, *known]
    sizes, took_big = set(), 0
    for s in range(200):
        plan = W.pick(fill, WARM, seed=s)
        sizes.add(plan["n"])
        took_big += any(b["id"] == "DEMO-m3" for b in plan["batch"])
    check("the explore share draws among the unknown moves within the batch first: smaller ones that fill it exactly "
          "beat a first try two over (200 seeds)", sizes == {5} and took_big == 0, (sizes, took_big))
    plan = W.pick([big, *known], WARM)
    check("…and takes one up to two over only when no unknown move fits within",
          [b["id"] for b in plan["batch"]] == ["DEMO-m3"] and plan["n"] == 6, plan)
    plan = W.pick([mv(1, "DEMO-g1", 3), mv(2, "DEMO-g2", 5)], WARM)
    check("…never three over: short then", plan["n"] in (3, 5) and len(plan["batch"]) == 1, plan)
    plan = W.pick([mv(1, "DEMO-g1", 4), mv(2, "DEMO-g1", 1), mv(3, "DEMO-g2", 1)], WARM)
    g1 = [b for b in plan["batch"] if b["group"] == "DEMO-g1"]
    check("a move bigger than half a batch only into an empty group, then alone",
          len(g1) == 1 and per_group(plan)["DEMO-g1"] in (1, 4), plan)
    a = W.pick(ms, WARM)
    check("the same data gives the same batch (a copy, a JSON round trip, a given seed)",
          W.pick(copy.deepcopy(ms), WARM) == a and W.pick(json.loads(json.dumps(ms)), json.loads(json.dumps(WARM))) == a
          and W.pick(ms, WARM, seed=7) == W.pick(ms, WARM, seed=7))
    batches = set()
    for extra in range(30):
        m2 = copy.deepcopy(ms)
        m2[2]["post"] = (12.0 + extra / 10, 1800.0)
        batches.add(json.dumps([b["id"] for b in W.pick(m2, WARM)["batch"]]))
    check("…and another number can give another batch (the seed comes from the data)", len(batches) > 1, batches)
    keyed = [mv(i, f"DEMO-g{i}", 1, "unknown" if i % 2 else "known", None) for i in range(9)]
    keyed[0]["exclusive"] = ["DEMO-k-alpha", "DEMO-k-beta", "DEMO-k-gamma", "DEMO-k-delta"]
    keyed[3]["shared"] = ["DEMO-t-a", "DEMO-t-b", "DEMO-t-c"]
    turned = copy.deepcopy(keyed)
    turned[0]["exclusive"] = turned[0]["exclusive"][::-1] + ["DEMO-k-beta"]
    turned[3]["shared"] = set(turned[3]["shared"])
    ids = [b["id"] for b in W.pick(keyed, WARM)["batch"]]
    check("a move's keys in another order, twice over or as a set: the same batch",
          [b["id"] for b in W.pick(turned, WARM)["batch"]] == ids, ids)
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); from kit import pathweights as W; "
            "ms = [{'id': f'DEMO-m{i}', 'group': f'DEMO-g{i}', 'n': 1, 'kind': 'unknown' if i % 2 else 'known', "
            "'post': None} for i in range(9)]; "
            "ms[0]['exclusive'] = {'DEMO-k-alpha', 'DEMO-k-beta', 'DEMO-k-gamma', 'DEMO-k-delta'}; "
            "ms[3]['shared'] = frozenset({'DEMO-t-a', 'DEMO-t-b', 'DEMO-t-c'}); "
            "print(json.dumps([b['id'] for b in W.pick(ms, W.account(70, 10000))['batch']]))")
    runs = {}
    for hs in ("1", "2", "3", "4"):
        got = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT)], capture_output=True, text=True,
                             env={**os.environ, "PYTHONHASHSEED": hs}, timeout=60)
        runs[hs] = got.stdout.strip() if got.returncode == 0 else got.stderr.strip()[-300:]
    check("…in any process: keys given as sets, four PYTHONHASHSEED values, one batch",
          len(set(runs.values())) == 1 and json.loads(runs["1"]) == ids, runs)
    thin = W.account(15, 3000)                      # warm under the defaults
    check("pick() decides warm by the settings it is given: coverage under a higher account_min_conv",
          W.pick(ms, thin)["mode"] == "weights" and W.pick(ms, thin, {"account_min_conv": 40.0})["mode"] == "coverage"
          and W.pick(ms, W.account(15, 3000, {"account_min_conv": 40.0}))["mode"] == "weights")
    wrong = [[mv(1, "DEMO-g1"), mv(1, "DEMO-g2")], [mv(1, "DEMO-g1", 0)], [mv(1, "DEMO-g1", True)],
             [mv(1, "DEMO-g1", 1, "maybe")], [mv(1, "", 1)], [mv(1, "DEMO-g1", 1, post=(0, 1))],
             [mv(1, "DEMO-g1", 1, post=(1, 2, 3))], [mv(1, "DEMO-g1", 1, exclusive="DEMO-k")],
             [mv(1, "DEMO-g1", 1, shared=["DEMO-k", ""])], [mv(1, "DEMO-g1", 1, shared={"DEMO-k": 1})],
             [{**mv(1, "DEMO-g1"), "id": None}]]
    check("a bad move is refused: an id twice, n not a whole number from 1, an unknown kind, no group, "
          "a bad posterior, keys not a list, no id", all(raises(W.pick, x, WARM) for x in wrong),
          [i for i, x in enumerate(wrong) if not raises(W.pick, x, WARM)])


# ---------------------------------------------------------------- [6] twins

def twin_units(groups, rest=True) -> tuple[list[dict], dict]:
    """Twin groups [(group, [(spend, conv, known)...])], every unit tagged {dim_a: a1, dim_b: b1}; the rest of the
    account (four units at 0.01) in DEMO-rest with tags of its own."""
    us, n = [], 0
    for g, members in groups:
        for spend, conv, known in members:
            n += 1
            us.append({"id": f"DEMO-{n:04d}", "group": g, "tags": {"dim_a": "a1", "dim_b": "b1"}, "conv": conv,
                       "spend": spend, "known": known})
    for i in range(4 if rest else 0):
        n += 1
        us.append({"id": f"DEMO-{n:04d}", "group": "DEMO-rest", "tags": {"dim_a": "a1", "dim_b": f"b{i + 2}"},
                   "conv": 30, "spend": 3000})
    return us, W.account(sum(u["conv"] for u in us), sum(u["spend"] for u in us))


def test_twins() -> None:
    print("\n[6] twins()")
    g = ("DEMO-g1", [(1000, 20, {"batch": "g1", "made_on": "2026-09-01", "length": 30}),
                     (1000, 2, {"batch": "g2", "made_on": "2026-09-01", "length": 45})])
    us, acct = twin_units([g])
    t = W.twins(us, acct)
    check("a pair past every threshold is flagged, with what is known to differ",
          len(t) == 1 and (t[0]["high"], t[0]["low"], t[0]["group"]) == ("DEMO-0001", "DEMO-0002", "DEMO-g1")
          and t[0]["ratio"] == 10.0 and t[0]["p"] >= 0.9 and t[0]["high_rate"] == 0.02 and t[0]["low_rate"] == 0.002
          and t[0]["tags"] == {"dim_a": "a1", "dim_b": "b1"}
          and t[0]["differences"] == [{"what": "batch", "high": "g1", "low": "g2"},
                                      {"what": "length", "high": 30, "low": 45}], t)
    low = ("DEMO-g1", [(1000, 5, {}), (1000, 0.5, {})])
    check("a group under twin_min_conv is not compared; a skill pack's own thresholds move it",
          W.twins(*twin_units([low])) == []
          and len(W.twins(*twin_units([low]), {"twin_min_conv": 5.0, "twin_p": 0.5})) == 1)
    third = ("DEMO-g1", [(1000, 20, {}), (1000, 15, {}), (100, 0, {})])
    got = W.twins(*twin_units([third]), {"twin_min_expected_conv": 0.5, "twin_p": 0.5})
    check("a unit whose spend buys fewer than twin_min_expected_conv is not compared",
          W.twins(*twin_units([third])) == [] and got and got[0]["low"] == "DEMO-0003" and got[0]["ratio"] is None, got)
    check("one unit left to compare: none", W.twins(*twin_units([("DEMO-g1", [(1000, 20, {}), (150, 0, {})])])) == [])
    near = ("DEMO-g1", [(1000, 8, {}), (1000, 5, {})])
    check("a gap the numbers do not make likely enough (twin_ratio, twin_p)", W.twins(*twin_units([near])) == []
          and W.twins(*twin_units([near]), {"twin_ratio": 1.1, "twin_p": 0.6}) != [])
    us, acct = twin_units([g])
    us[1]["tags"] = {"dim_a": "a1", "dim_b": "b2"}
    check("units whose tags differ are no twins", W.twins(us, acct) == [])
    us, _ = twin_units([g])
    check("no account rate: none", W.twins(us, W.account(0, 0)) == [])
    groups = [(f"DEMO-g{i}", [(1000, 30, {}), (1000, c, {})]) for i, c in ((1, 2), (2, 6), (3, 1), (4, 3), (5, 10))]
    t = W.twins(*twin_units(groups))
    check("at most three, the largest gap first", [x["group"] for x in t] == ["DEMO-g3", "DEMO-g1", "DEMO-g4"]
          and [x["ratio"] for x in t] == [30.0, 15.0, 10.0], t)
    check("…and the same twins again (the draws are seeded by the pair)", W.twins(*twin_units(groups)) == t)
    zero = [("DEMO-g1", [(1000, 30, {}), (1000, 2, {})]), ("DEMO-g2", [(1000, 30, {}), (1000, 0, {})])]
    t = W.twins(*twin_units(zero))
    check("a low twin with no conversion has no ratio and comes first", [x["ratio"] for x in t] == [None, 15.0], t)
    check("a bad unit is refused", raises(W.twins, [{"id": "DEMO-1", "group": "g", "tags": {"a": 1}, "conv": 1,
                                                    "spend": 1}], acct)
          and raises(W.twins, [{"id": "DEMO-1", "group": "g", "tags": {}, "conv": -1, "spend": 1}], acct))


# ---------------------------------------------------------------- [7] calibration by simulation

def _poisson(rng: random.Random, mu: float) -> int:
    if mu <= 0:
        return 0
    if mu > 40:
        return max(0, int(round(rng.gauss(mu, math.sqrt(mu)))))
    lim, k, p = math.exp(-mu), 0, 1.0
    while True:
        p *= rng.random()
        if p <= lim:
            return k
        k += 1


def _sim_leaves(rng: random.Random) -> list[dict]:
    """Three directions, one template each (six, three and three leaves), two to four leaves made on each."""
    out = []
    for top, size in (("DEMO-a", 6), ("DEMO-b", 3), ("DEMO-c", 3)):
        for j in sorted(rng.sample(range(size), min(size, rng.randint(2, 4)))):
            out.append({"id": f"{top}-{j}", "parents": [top, f"{top}1"], "units": 2})
    return out


def simulate(worlds: int, *, rounds: int = 5, rate: float = 1 / 200, budget: float = 8000.0, floor: float = 0.2,
             push: float = 1.0, fractional: bool = False) -> tuple[int, int]:
    """(leaves ever proposed for closing within `rounds`, leaves made) over seeded worlds where every leaf has the same
    true rate. Each round's budget goes to the made leaves in proportion to (posterior mean)^push, `floor` of it split
    evenly (a platform pushing spend to early leaders); a leaf's share is split evenly over its two units; conversions
    are Poisson at the true rate (fractional: half-units, Poisson(2 mu) / 2, the same mean)."""
    proposed = made = 0
    for s in range(worlds):
        rng = random.Random(1000 + s)
        leaves = _sim_leaves(rng)
        units = {x["id"]: [[0.0, 0.0] for _ in range(x["units"])] for x in leaves}
        mean = {x["id"]: rate for x in leaves}
        ever: set[str] = set()
        for _ in range(rounds):
            weight = {i: mean[i] ** push for i in mean}
            tot = sum(weight.values())
            for x in leaves:
                share = (1 - floor) * weight[x["id"]] / tot + floor / len(leaves)
                for u in units[x["id"]]:
                    spend = budget * share / len(units[x["id"]])
                    u[0] += spend
                    u[1] += _poisson(rng, 2 * spend * rate) / 2 if fractional else _poisson(rng, spend * rate)
            pw = W.posteriors([{"id": x["id"], "parents": x["parents"], "conv": sum(c for _, c in units[x["id"]]),
                                "spend": sum(sp for sp, _ in units[x["id"]])} for x in leaves])
            for x in leaves:
                us = units[x["id"]]
                j = W.judge(pw["leaves"][x["id"]], pw["account"], made=len(us), spend=sum(sp for sp, _ in us),
                            settled=sum(1 for sp, _ in us if sp > 0))
                if j["propose_close"]:
                    ever.add(x["id"])
                post = pw["leaves"][x["id"]]
                if post is not None:
                    mean[x["id"]] = post[0] / post[1]
        proposed += len(ever)
        made += len(leaves)
    return proposed, made


def test_calibration() -> None:
    print("\n[7] calibration: every leaf equally good, five rounds, spend pushed to early leaders")
    t0 = time.time()
    out = {}
    for name, kw, n in (("proportional", {}, 400), ("pushed (mean squared)", {"push": 2.0}, 200),
                        ("fractional conversions", {"fractional": True}, 200)):
        got, made = simulate(n, **kw)
        out[name] = (got, made, got / made)
        print(f"  calibration, {name}: {got} of {made} leaves ever proposed for closing in 5 rounds = "
              f"{100 * got / made:.2f}%")
    print(f"  calibration took {time.time() - t0:.1f} s")
    for name, (got, made, r) in out.items():
        check(f"{name}: at most 5 in 100 made leaves ever proposed for closing ({100 * r:.2f}% of {made})",
              made >= 1000 and r <= 0.05, (got, made, r))


# ---------------------------------------------------------------- [8] the past: a gap signal, never a weight

def erlang_above(n: int, rate: float, r: float) -> float:
    """P(lambda > r) for lambda ~ Gamma(n, rate), n whole: e^-x * sum_{k<n} x^k / k!, x = rate * r."""
    x = rate * r
    return math.exp(-x) * sum(x ** k / math.factorial(k) for k in range(n))


PAST = [("DEMO-p1", 1000, 10), ("DEMO-p2", 1000, 12), ("DEMO-p3", 1000, 2), ("DEMO-p4", 1000, 3),
        ("DEMO-p5", 1000, 5), ("DEMO-p6", 1000, 8), ("DEMO-p7", 0, 0)]
PAST_GROUPS = {"DEMO-g1": {"units": ["DEMO-p1", "DEMO-p2"], "ours": 0}, "DEMO-g2": {"units": ["DEMO-p3", "DEMO-p4"], "ours": 3},
               "DEMO-g3": {"units": ["DEMO-p5", "DEMO-p6", "DEMO-p7"]}}


def past_units(rows=PAST) -> list[dict]:
    return [{"id": i, "spend": sp, "conv": cv} for i, sp, cv in rows]


def by_key(out: dict) -> dict:
    return {g["key"]: g for g in out["groups"]}


def test_past() -> None:
    print("\n[8] past_signal(): a gap signal, never a weight")
    # the plan's results are taken first, before past_signal has ever run in this process, so state it leaves behind shows
    leaves = [{"id": "DEMO-l1", "parents": ["DEMO-d1"], "conv": 6, "spend": 1000},
              {"id": "DEMO-l2", "parents": ["DEMO-d1"], "conv": 4, "spend": 1000},
              {"id": "DEMO-l3", "parents": ["DEMO-d2"], "conv": 1, "spend": 1000}]
    acct = W.account(11, 3000)
    moves = [{"id": "DEMO-m1", "group": "DEMO-d1", "n": 2, "kind": "unknown", "post": None},
             {"id": "DEMO-m2", "group": "DEMO-d2", "n": 2, "kind": "known", "post": (4.0, 1000.0)},
             {"id": "DEMO-m3", "group": "DEMO-d3", "n": 2, "kind": "unknown", "post": None}]

    def plan_results() -> str:
        pw = W.posteriors(leaves)
        j = W.judge(pw["leaves"]["DEMO-l3"], pw["account"], made=2, spend=1000, settled=2)
        return repr([pw, j, W.pick(moves, acct, seed=7), W.twins([], acct), acct])
    base = plan_results()
    out = W.past_signal(past_units(), PAST_GROUPS)
    R = 40 / 6000
    check("the pool: units with spend, their spend and conversions, their own rate",
          out["pool"] == {"units": 6, "spend": 6000.0, "conv": 40.0, "rate": R}, out["pool"])
    g = by_key(out)
    check("the groups, the largest by conversions first (a unit with no spend counts nowhere)",
          [x["key"] for x in out["groups"]] == ["DEMO-g1", "DEMO-g3", "DEMO-g2"] and g["DEMO-g3"]["units"] == 2
          and g["DEMO-g1"]["conv"] == 22.0 and g["DEMO-g1"]["spend"] == 2000.0, out["groups"])
    # prior_conv 2 at the pool's rate: Gamma(2 + y, 2 / R + s); whole shapes here, so the closed form
    worked = {k: erlang_above(2 + int(g[k]["conv"]), 2 / R + g[k]["spend"], R) for k in g}
    check("P(better than the pool) against the closed form (whole shapes)",
          all(abs(g[k]["p_better"] - worked[k]) < 1e-4 for k in g), (worked, {k: g[k]["p_better"] for k in g}))
    check("its rate over the pool's, what its spend buys at the pool's rate",
          g["DEMO-g1"]["vs_pool"] == round(0.011 / R, 2) and g["DEMO-g1"]["expected"] == round(2000 * R, 2)
          and g["DEMO-g1"]["rate"] == 0.011, g["DEMO-g1"])
    check("strong, none, weak", (g["DEMO-g1"]["reads"], g["DEMO-g3"]["reads"], g["DEMO-g2"]["reads"]) == (
        "strong", None, "weak"), {k: (g[k]["p_better"], g[k]["reads"]) for k in g})
    check("top: up to three units by conversions", g["DEMO-g1"]["top"] == ["DEMO-p2", "DEMO-p1"], g["DEMO-g1"])
    check("a gap is a strong group with none of ours; a warning a weak one with enough of ours",
          out["gaps"] == ["DEMO-g1"] and out["warnings"] == ["DEMO-g2"], (out["gaps"], out["warnings"]))
    check("ours defaults to 0", g["DEMO-g3"]["ours"] == 0)
    check("a strong group the plan has a unit on is no gap", W.past_signal(past_units(), {
        **PAST_GROUPS, "DEMO-g1": {"units": ["DEMO-p1", "DEMO-p2"], "ours": 1}})["gaps"] == [])
    check("a weak group with fewer of ours than past_warn_units is no warning",
          W.past_signal(past_units(), {**PAST_GROUPS, "DEMO-g2": {"units": ["DEMO-p3", "DEMO-p4"], "ours": 2}})[
              "warnings"] == [] and W.past_signal(past_units(), PAST_GROUPS, {"past_warn_units": 2})["warnings"] == [
              "DEMO-g2"])
    # thresholds
    check("a group speaks once its spend buys past_min_expected_conv at the pool's rate (13.33 here)",
          not by_key(W.past_signal(past_units(), PAST_GROUPS, {"past_min_expected_conv": 14}))["DEMO-g1"]["speaks"]
          and by_key(W.past_signal(past_units(), PAST_GROUPS, {"past_min_expected_conv": 13}))["DEMO-g1"]["speaks"])
    quiet = W.past_signal(past_units(), PAST_GROUPS, {"past_min_expected_conv": 14})
    check("a group that does not speak reads nothing: no gap, no warning",
          all(x["reads"] is None for x in quiet["groups"]) and quiet["gaps"] == [] and quiet["warnings"] == [])
    check("promising_p and downweight_p move the reads",
          by_key(W.past_signal(past_units(), PAST_GROUPS, {"promising_p": 0.99, "downweight_p": 0.001}))["DEMO-g1"][
              "reads"] is None
          and by_key(W.past_signal(past_units(), PAST_GROUPS, {"promising_p": 0.99, "downweight_p": 0.001}))[
              "DEMO-g2"]["reads"] is None)
    check("prior_conv moves P(better): a heavier prior pulls a group toward the pool",
          by_key(W.past_signal(past_units(), PAST_GROUPS, {"prior_conv": 50}))["DEMO-g1"]["p_better"]
          < g["DEMO-g1"]["p_better"])
    # a cold pool judges nothing
    for what, rows in (("no conversion", [("DEMO-p1", 1000, 0), ("DEMO-p2", 1000, 0)]), ("no spend", [("DEMO-p1", 0, 0)]),
                       ("no units", [])):
        cold = W.past_signal(past_units(rows), {"DEMO-g1": {"units": [r[0] for r in rows]}} if rows else {})
        check(f"{what}: no pool rate, nothing judged", cold["pool"]["rate"] is None and cold["groups"] == []
              and cold["gaps"] == [] and cold["warnings"] == [], cold)
    check("a group with no unit with spend is listed with no rate", by_key(W.past_signal(past_units(), {
        "DEMO-g9": {"units": ["DEMO-p7"]}, "DEMO-g1": PAST_GROUPS["DEMO-g1"]}))["DEMO-g9"]["vs_pool"] is None)
    whole = W.past_signal(past_units(), {"DEMO-all": {"units": [r[0] for r in PAST]}})
    check("a group that is the whole pool reads about even (the pool includes it): never strong or weak, vs_pool 1",
          by_key(whole)["DEMO-all"]["reads"] is None and by_key(whole)["DEMO-all"]["vs_pool"] == 1.0
          and 0.4 < by_key(whole)["DEMO-all"]["p_better"] < 0.6, whole["groups"])
    allrows = [x for r in (W.past_signal(past_units(), PAST_GROUPS, {"promising_p": p / 1000, "downweight_p": 0.001})
                           for p in range(500, 999, 7)) for x in r["groups"]]
    check("what is shown decides the read: no row shows a p_better at or above promising_p without reading strong "
          "(when it speaks), none shows expected under the bar and speaks",
          all((x["reads"] == "strong") == (x["speaks"] and x["p_better"] >= p / 1000)
              for p in range(500, 999, 7) for x in W.past_signal(past_units(), PAST_GROUPS, {
                  "promising_p": p / 1000, "downweight_p": 0.001})["groups"])
          and all(x["speaks"] == (x["expected"] >= 3.0) for x in allrows))
    check("a total too large for a float is a ValueError", raises(W.past_signal, [
        {"id": "DEMO-a", "spend": 1e308, "conv": 1}, {"id": "DEMO-b", "spend": 1e308, "conv": 1}], {}))
    check("an absurdly large unit beside a normal one is a ValueError, not a crash", raises(W.past_signal, [
        {"id": "DEMO-a", "spend": 1e300, "conv": 1e290}, {"id": "DEMO-b", "spend": 1000, "conv": 5}],
        {"DEMO-g": {"units": ["DEMO-a", "DEMO-b"]}}))
    check("a unit may sit in several groups", len(W.past_signal(past_units(), {
        "DEMO-a": {"units": ["DEMO-p1"]}, "DEMO-b": {"units": ["DEMO-p1", "DEMO-p2"]}})["groups"]) == 2)
    # bad input
    bad_groups = [{"": {"units": ["DEMO-p1"]}}, {"DEMO-g": {"units": "DEMO-p1"}}, {"DEMO-g": {"units": ["DEMO-p1", "DEMO-p1"]}},
                  {"DEMO-g": {"units": ["DEMO-nope"]}}, {"DEMO-g": {"units": [1]}}, {"DEMO-g": {"units": [["DEMO-p1"]]}},
                  {"DEMO-g": {}}, {"DEMO-g": ["DEMO-p1"]}, {"DEMO-g": {"units": ["DEMO-p1"], "ours": -1}},
                  {"DEMO-g": {"units": ["DEMO-p1"], "ours": True}}, {"DEMO-g": {"units": ["DEMO-p1"], "ours": 1.5}},
                  ["DEMO-g"], None]
    check("every bad group is refused", all(raises(W.past_signal, past_units(), x) for x in bad_groups),
          [x for x in bad_groups if not raises(W.past_signal, past_units(), x)])
    bad_units = [[{"id": "DEMO-p1", "spend": -1, "conv": 1}], [{"id": "DEMO-p1", "spend": 1, "conv": -1}],
                 [{"id": "DEMO-p1", "spend": float("nan"), "conv": 1}], [{"id": "DEMO-p1", "spend": "1", "conv": 1}],
                 [{"id": "DEMO-p1", "spend": True, "conv": 1}], [{"spend": 1, "conv": 1}],
                 [{"id": "DEMO-p1", "spend": 1}], ["DEMO-p1"],
                 [{"id": "DEMO-p1", "spend": 1, "conv": 1}, {"id": "DEMO-p1", "spend": 1, "conv": 1}]]
    check("every bad unit is refused", all(raises(W.past_signal, x, {}) for x in bad_units),
          [x for x in bad_units if not raises(W.past_signal, x, {})])
    check("a bad setting is refused naming the key", "past_warn_units" in message(
        W.past_signal, past_units(), PAST_GROUPS, {"past_warn_units": 0}))
    check("fractional conversions are fine", W.past_signal(past_units([("DEMO-p1", 1000, 10.5), ("DEMO-p2", 1000, 3.25)]), {
        "DEMO-g": {"units": ["DEMO-p1"]}})["pool"]["conv"] == 13.75)
    # determinism and purity
    before_u, before_g = copy.deepcopy(past_units()), copy.deepcopy(PAST_GROUPS)
    rng = random.Random(5)
    shuffled = past_units()
    rng.shuffle(shuffled)
    regroup = {k: {**v, "units": list(reversed(v["units"]))} for k, v in reversed(list(PAST_GROUPS.items()))}
    check("the same result in any order of units, groups and a group's units", W.past_signal(shuffled, regroup) == out
          and W.past_signal(past_units(), {k: {**v, "units": set(v["units"])} for k, v in PAST_GROUPS.items()}) == out)
    check("nothing is mutated", past_units() == before_u and PAST_GROUPS == before_g)
    # never a weight
    W.past_signal(past_units(), PAST_GROUPS)
    check("the plan's posteriors, judgements and next batch are the same before and after the past is read",
          plan_results() == base)
    W.past_signal(past_units(), {})
    W.past_signal(past_units([("DEMO-p1", 1000, 0)]), {})
    check("…and after every kind of call (a cold pool, no groups), so no state is left behind", plan_results() == base)
    check("its result carries nothing a leaf, a move or the account takes (no post, shift, state, parents, warm)",
          not {"post", "shift", "state", "parents", "warm", "reason"} & {k for x in out["groups"] for k in x}
          and not {"post", "shift", "state", "parents", "warm"} & set(out["pool"]) & set(out))
    import inspect
    named = [fn for fn in ("posteriors", "judge", "pick", "twins", "account", "p_above", "gamma_cdf", "quantile", "tenths",
                           "_warm", "_move", "_without", "_post", "settings", "setting")
             if "past_signal" in inspect.getsource(getattr(W, fn))]
    check("no function that weighs, judges or picks names past_signal", named == [], named)
    import ast
    called = {n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "") for n in ast.walk(
        ast.parse(inspect.getsource(W.past_signal))) if isinstance(n, ast.Call)}
    check("past_signal itself calls none of them", not called & {"posteriors", "judge", "pick", "twins", "account"}, called)
    tree = ast.parse(inspect.getsource(W.past_signal))
    check("past_signal writes no module state (no global statement)",
          not [n for n in ast.walk(tree) if isinstance(n, ast.Global)])


def null_past(trials: int = 300, groups: int = 8, per: int = 5, rate: float = 0.01, sigma: float = 0.0
              ) -> tuple[int, int, int]:
    """(strong, weak, groups judged) over seeded pools where every group is equally good: each unit's true rate is
    `rate`, spread log-normally by `sigma` (0: every unit identical, only Poisson noise)."""
    strong = weak = n = 0
    for t in range(trials):
        rng = random.Random(7000 + t)
        us = []
        for i in range(groups * per):
            sp = rng.choice([500, 1000, 2000, 4000])
            mu = sp * rate * (math.exp(rng.gauss(0, sigma) - sigma * sigma / 2) if sigma else 1.0)
            us.append({"id": f"DEMO-{i}", "spend": sp, "conv": _poisson(rng, mu)})
        gs = {f"DEMO-g{j}": {"units": [f"DEMO-{i}" for i in range(j * per, (j + 1) * per)]} for j in range(groups)}
        for x in W.past_signal(us, gs)["groups"]:
            n += 1
            strong += x["reads"] == "strong"
            weak += x["reads"] == "weak"
    return strong, weak, n


def test_past_calibration() -> None:
    print("\n[8b] past_signal(): every group equally good")
    for label, sigma, strong_band, weak_band in (("Poisson noise only", 0.0, (0.14, 0.21), (0.16, 0.25)),
                                                   ("unit rates spread by half a log-unit", 0.5, (0.25, 0.42),
                                                    (0.32, 0.50))):
        strong, weak, n = null_past(sigma=sigma)
        print(f"  {label}: {strong} of {n} groups read strong ({100 * strong / n:.1f}%), {weak} weak "
              f"({100 * weak / n:.1f}%)")
        check(f"{label}: strong in {strong_band}, weak in {weak_band} (the docs quote about 1 in 6 and 1 in 5; with "
              f"spread about a third and 2 in 5): a pointer, never a proof",
              n >= 2000 and strong_band[0] <= strong / n <= strong_band[1] and weak_band[0] <= weak / n <= weak_band[1],
              (strong, weak, n))


def main() -> int:
    test_settings()
    test_statistics()
    test_partition()
    test_judge()
    test_pick()
    test_twins()
    test_calibration()
    test_past()
    test_past_calibration()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
