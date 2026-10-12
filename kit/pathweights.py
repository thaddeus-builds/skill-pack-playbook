"""Path weights: which of a harness's variants do better than its own account, what to make next, and which a person
may close. Design and rules for any harness: docs/path-weights.md.

A harness that makes variants (ads, posts, emails) and gets back, per variant, its spend and its conversions lays what
it makes out as a partition: every unit (one variant) sits on exactly one leaf (a path), and every leaf under its
ancestors (any depth: a direction, then a template, then one value per variable, say). What the kit guards:

  * exact statistics, stdlib only: `gamma_cdf()` (the regularized lower incomplete gamma), `p_above()`, `quantile()`;
    `tenths()` reads a probability as "about n times in 10", rounded toward a half, so 0.79 reads 7 and 0.21 reads 3
    and a number shown never crosses the 0.8 or 0.2 line its state was judged on;
  * `posteriors()`: a leaf's rate (conversions per unit of spend) is a Gamma-Poisson posterior on its settled numbers
    (fractional conversions allowed: the Poisson kernel is then a quasi-likelihood, and the mean stays right). Its
    prior is borrowed down the partition, leave-one-out: account -> each level -> the leaf, every level's prior mean
    its parent's posterior mean with the level's own numbers taken out (nothing counts twice), worth `prior_conv`
    conversions; an optional per-leaf factor moves the leaf's prior mean, clipped to [1 / prior_shift_max,
    prior_shift_max]. A node's numbers are the sum of its children's, and the account covers every leaf;
  * `judge()`: five states, each with its reason (REASONS). Only settled numbers count, so a leaf the platform starved
    stays testing, never down. A down leaf is proposed for closing when its settled spend would buy
    close_min_expected_conv at the account rate, close_min_units of its units have settled spend and P(rate >=
    close_ratio x the account rate) is at most close_p. A close is never decided here: a person confirms it, and the
    harness records it (and passes `closed=True` from then on);
  * `pick()`: the next batch, over the moves the harness built (what a move makes is the harness's). With no warm
    account, the harness's coverage order; once warm, batched top-two Thompson draws, at least explore_share of the
    batch from moves not known yet, at most half a batch per group (one move bigger than that stands alone), two moves
    that share an exclusive key never both (a key one move holds `shared` fits beside another's `shared`, never beside
    an `exclusive`), a fill up to two over rather than short, and a seed from the data: the same data, the same batch;
  * `twins()`: units of one group with the same tags whose settled rates differ by twin_ratio with probability twin_p,
    past two count thresholds; at most three, the largest gap first, with what is known to differ. A clue, never proof;
  * every threshold is in DEFAULTS (SETTINGS says what each is); `settings()` lays a harness's or a client's own values
    over them and refuses one that is not a value of that threshold (`setting()`, ValueError).

The platform does not randomise delivery: "better than the account" is a statement about these numbers, never a cause.
What a leaf is, what a move makes, where the numbers come from, who closes and how a person sees it are the harness's.
Pure: no file, no database, no clock; the same input gives the same output. Stdlib only.
Test: kit/tests/test_pathweights.py.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Iterable, Mapping, Sequence

Post = tuple[float, float]                      # a Gamma posterior on a rate: (shape alpha, rate beta), mean a / b

# (key, default, type, what it is): a harness lays its own (or a client's) over these with settings()
SETTINGS = (
    ("prior_conv", 2.0, float, "a prior is worth this many conversions at its parent's rate"),
    ("account_min_conv", 10.0, float, "settled conversions the account needs before anything is judged"),
    ("min_expected_conv", 3.0, float, "a leaf is judged once its settled spend buys this many at the account rate"),
    ("promising_p", 0.8, float, "P(better than the account) at or above which a leaf is promising"),
    ("downweight_p", 0.2, float, "P(better than the account) at or below which a leaf is down"),
    ("close_min_expected_conv", 5.0, float,
     "settled spend, in conversions at the account rate, before a close is proposed"),
    ("close_min_units", 2, int, "units with settled spend a leaf needs before a close is proposed"),
    ("close_ratio", 0.7, float, "a close asks whether the leaf reaches this share of the account rate"),
    ("close_p", 0.1, float, "P(rate >= close_ratio x account rate) at or below which a close is proposed"),
    ("batch_size", 5, int, "units in a next batch"),
    ("explore_share", 0.3, float, "the least share of a batch kept for moves not known yet"),
    ("twin_min_conv", 6.0, float, "settled conversions a group of same-tag units needs before it is compared"),
    ("twin_min_expected_conv", 2.0, float,
     "settled spend, in conversions at the account rate, each compared unit needs"),
    ("twin_ratio", 2.0, float, "how many times better the best twin must be"),
    ("twin_p", 0.9, float, "the probability of that ratio before twins are flagged"),
    ("prior_shift_max", 1.5, float, "the most a leaf's factor moves its prior mean (and 1 / it, the least)"),
)
DEFAULTS: dict[str, float | int] = {k: d for k, d, _, _ in SETTINGS}
TYPES = {k: t for k, _, t, _ in SETTINGS}
STATES = ("untested", "testing", "promising", "down", "closed")
REASONS = {                                     # reason -> the state it gives
    "not_made": "untested",                     # no unit made on it
    "account_thin": "testing",                  # the account has fewer than account_min_conv settled conversions
    "no_settled_numbers": "testing",            # made, no settled spend yet
    "spend_thin": "testing",                    # its settled spend buys under min_expected_conv at the account rate
    "no_difference_yet": "testing",             # judged, between the two lines
    "likely_better": "promising",
    "likely_worse": "down",
    "closed_by_person": "closed",
}
KINDS = ("known", "unknown")                    # a move known to be good (a promising leaf's neighbour), or not yet
INTERVAL = (0.1, 0.9)                           # judge()'s band: these quantiles of the posterior
TOP_TWO = 0.5                                   # how often a top-two draw takes the runner-up
TWIN_PRIOR = 0.5                                # twins are compared under a weak prior: they must speak for themselves
DRAWS = 4000
TWINS_MAX = 3
_SLACK = 1e-9                                   # 0.3 x 10 is 3, not 3.0000000000000004


# ---------------------------------------------------------------- settings

def setting(key: str, value: object) -> float | int:
    """The typed value of one threshold, or ValueError saying what is wrong: an unknown key, a value that is not a
    finite number (a bool is none), a count that is not whole, a probability or share not strictly between 0 and 1,
    a close_ratio not in (0, 1], a prior_shift_max below 1 (1: the factor moves nothing), anything else not above 0."""
    if key not in DEFAULTS:
        raise ValueError(f"no setting {key!r} (the settings: {', '.join(DEFAULTS)})")
    whole = TYPES[key] is int
    if isinstance(value, bool):
        raise ValueError(f"{key}: not a number")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key}: not a {'whole number' if whole else 'number'}") from None
    if not math.isfinite(v):
        raise ValueError(f"{key}: not a finite number")
    if whole:
        if v != int(v):
            raise ValueError(f"{key}: not a whole number")
        v = int(v)
    if key.endswith("_p") or key == "explore_share":
        if not 0 < v < 1:
            raise ValueError(f"{key}: a probability or a share is between 0 and 1")
    elif key == "close_ratio":
        if not 0 < v <= 1:
            raise ValueError(f"{key}: a share of the account's rate, above 0 and at most 1")
    elif key == "prior_shift_max":
        if v < 1:
            raise ValueError(f"{key}: at least 1 (1 means the factor moves nothing)")
    elif v <= 0:
        raise ValueError(f"{key}: must be above 0")
    return v


def settings(over: Mapping[str, object] | None = None) -> dict:
    """DEFAULTS with `over` laid on them, every value of `over` checked by setting() (ValueError on the first bad one).
    Every function here takes its thresholds this way."""
    return {**DEFAULTS, **{k: setting(k, v) for k, v in (over or {}).items()}}


# ---------------------------------------------------------------- statistics

def _gser(a: float, x: float) -> float:
    s = term = 1.0 / a
    ap = a
    for _ in range(10000):
        ap += 1
        term *= x / ap
        s += term
        if abs(term) < abs(s) * 1e-15:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a: float, x: float) -> float:
    tiny = 1e-300
    b = x + 1 - a
    c, d = 1 / tiny, 1 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        h *= d * c
        if abs(d * c - 1) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def gamma_cdf(a: float, x: float) -> float:
    """The regularized lower incomplete gamma P(a, x) = P(X <= x) for X ~ Gamma(shape a, rate 1): the series below
    a + 1, the continued fraction above. 0 for x <= 0; ValueError for a shape that is not above 0."""
    if not a > 0:
        raise ValueError("a gamma's shape is above 0")
    if x <= 0:
        return 0.0
    return _gser(a, x) if x < a + 1 else 1 - _gcf(a, x)


def p_above(alpha: float, beta: float, r: float) -> float:
    """P(lambda > r) for lambda ~ Gamma(shape alpha, rate beta)."""
    return 1.0 - gamma_cdf(alpha, beta * r)


def quantile(alpha: float, beta: float, q: float) -> float:
    """The q-quantile of Gamma(shape alpha, rate beta), in the rate's units: bisection to double precision."""
    if not 0 < q < 1:
        raise ValueError("a quantile is strictly between 0 and 1")
    lo, hi = 0.0, (alpha + 10 * math.sqrt(alpha) + 10) / beta
    for _ in range(64):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if gamma_cdf(alpha, beta * mid) < q else (lo, mid)
    return (lo + hi) / 2


def tenths(p: float) -> int:
    """P as "about n times in 10", rounded toward a half: 0.79 reads 7 (not promising at 0.8) and 0.21 reads 3 (not down
    at 0.2), so a number shown never crosses the line its state was judged on."""
    return math.floor(10 * p + _SLACK) if p >= 0.5 else math.ceil(10 * p - _SLACK)


# ---------------------------------------------------------------- inputs

def _amount(x: object, what: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0:
        raise ValueError(f"{what}: a finite number at least 0")
    return float(x)


def _count(x: object, what: str) -> int:
    if isinstance(x, bool) or not isinstance(x, int) or x < 0:
        raise ValueError(f"{what}: a whole number at least 0")
    return x


def _post(p: object, what: str) -> Post | None:
    if p is None:
        return None
    if not (isinstance(p, (list, tuple)) and len(p) == 2
            and all(not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in p)):
        raise ValueError(f"{what}: a posterior is (alpha, beta), both finite and above 0, or None")
    return float(p[0]), float(p[1])


def _keys(x: object, what: str) -> tuple[str, ...]:
    if isinstance(x, str) or not isinstance(x, (list, tuple, set, frozenset)) \
            or not all(isinstance(k, str) and k for k in x):
        raise ValueError(f"{what}: a list of non-empty strings")
    return tuple(x)


def _ids(items: Sequence[Mapping], what: str) -> None:
    seen: set[str] = set()
    for it in items:
        i = it.get("id") if isinstance(it, Mapping) else None
        if not (isinstance(i, str) and i):
            raise ValueError(f"{what}: every one has an id, a non-empty string")
        if i in seen:
            raise ValueError(f"{what}: the id {i!r} is given twice")
        seen.add(i)


# ---------------------------------------------------------------- the account and the partition

def account(conv: float, spend: float, cfg: Mapping | None = None) -> dict:
    """{conv, spend, rate, warm}: the account's settled conversions and spend, its rate (conv / spend; None with no
    spend or no conversion) and whether it is warm (a rate, and at least account_min_conv conversions): below that
    nothing is judged and the next batch goes by coverage."""
    cfg = settings(cfg)
    y, s = _amount(conv, "the account's conversions"), _amount(spend, "the account's spend")
    rate = y / s if s > 0 and y > 0 else None
    return {"conv": y, "spend": s, "rate": rate, "warm": rate is not None and y >= cfg["account_min_conv"]}


def _without(post: Post, y: float, s: float) -> float:
    """The parent's posterior mean with the child's own numbers taken out (leave-one-out); the whole mean when the
    child is all of it."""
    a, b = post
    return (a - y) / (b - s) if a - y > 0 and b - s > 0 else a / b


def posteriors(leaves: Iterable[Mapping], cfg: Mapping | None = None,
               total: tuple[float, float] | None = None) -> dict:
    """{account, nodes, leaves} for a partition. A leaf is {id, parents, conv, spend, shift?}: `parents` its ancestors'
    keys from the top (strings, any depth, none = directly under the account), `conv` and `spend` its settled numbers
    (the sum of its units'), `shift` an optional factor on its prior mean (1 = none; clipped to [1 / prior_shift_max,
    prior_shift_max]). `total` is the account's (conv, spend) when it holds more than the leaves (units on no leaf);
    it is never less (ValueError).

    `account`: account()'s dict plus `post`, the account's own Gamma(prior_conv + Y, prior_conv / rate + S).
    `nodes`: {tuple of keys from the top: {conv, spend, leaves, post}}, the sums of the leaves under it and its
    posterior (prior_conv + y, prior_conv / m + s), m its parent's posterior mean leave-one-out. `leaves`: {id:
    posterior}, the same from its deepest node, m times the clipped shift. With no account rate every post is None."""
    cfg = settings(cfg)
    ls = []
    for x in leaves:
        if not isinstance(x, Mapping):
            raise ValueError("a leaf is a mapping")
        shift = x.get("shift", 1.0)
        if isinstance(shift, bool) or not isinstance(shift, (int, float)) or not math.isfinite(shift) or shift <= 0:
            raise ValueError(f"leaf {x.get('id')!r}: shift is a finite number above 0")
        ls.append({"id": x.get("id"), "parents": _keys(x.get("parents", ()), f"leaf {x.get('id')!r}: parents"),
                   "conv": _amount(x.get("conv"), f"leaf {x.get('id')!r}: conv"),
                   "spend": _amount(x.get("spend"), f"leaf {x.get('id')!r}: spend"), "shift": float(shift)})
    _ids(ls, "a leaf")
    nodes: dict[tuple[str, ...], dict] = {}
    for x in ls:
        for d in range(1, len(x["parents"]) + 1):
            n = nodes.setdefault(x["parents"][:d], {"conv": 0.0, "spend": 0.0, "leaves": 0, "post": None})
            n["conv"] += x["conv"]
            n["spend"] += x["spend"]
            n["leaves"] += 1
    y = math.fsum(x["conv"] for x in ls)
    s = math.fsum(x["spend"] for x in ls)
    if total is not None:
        ty, ts = _amount(total[0], "the account's conversions"), _amount(total[1], "the account's spend")
        if ty < y * (1 - 1e-9) - 1e-9 or ts < s * (1 - 1e-9) - 1e-9:
            raise ValueError("the account holds every leaf: its conversions and spend are at least the leaves' sums")
        y, s = ty, ts
    acct = {**account(y, s, cfg), "post": None}
    a0, rate = cfg["prior_conv"], acct["rate"]
    posts: dict[str, Post | None] = {x["id"]: None for x in ls}
    if rate:
        acct["post"] = (a0 + y, a0 / rate + s)
        for key in sorted(nodes, key=len):                                  # a parent before its children
            n = nodes[key]
            up = nodes[key[:-1]]["post"] if len(key) > 1 else acct["post"]
            n["post"] = (a0 + n["conv"], a0 / _without(up, n["conv"], n["spend"]) + n["spend"])
        hi = max(1.0, cfg["prior_shift_max"])
        for x in ls:
            up = nodes[x["parents"]]["post"] if x["parents"] else acct["post"]
            m = _without(up, x["conv"], x["spend"]) * min(hi, max(1 / hi, x["shift"]))
            posts[x["id"]] = (a0 + x["conv"], a0 / m + x["spend"])
    return {"account": acct, "nodes": nodes, "leaves": posts}


# ---------------------------------------------------------------- the state of a leaf (or a node)

def judge(post: Post | None, acct: Mapping, *, made: int, spend: float, settled: int, closed: bool = False,
          cfg: Mapping | None = None) -> dict:
    """{state, why, propose_close} of a leaf (a node is judged by the same rule; whether a node's proposal is shown is
    the harness's): `post` its posterior (posteriors()), `acct` the account (account() or posteriors()["account"]),
    `made` its units made, `spend` its settled spend, `settled` its units with settled spend, `closed` a person's close
    standing on it. Once judged it also carries `rate` (the posterior mean), `lo` and `hi` (INTERVAL), `expected` (the
    settled spend in conversions at the account rate, 3 places) and `p_better` (P(rate > the account's), 4 places); a
    down one `p_reaches` (P(rate >= close_ratio x the account's), 4 places). The state is decided on the rounded numbers
    it returns, so what is shown never contradicts it. `propose_close` is only ever a proposal."""
    cfg = settings(cfg)
    made, settled, spend = _count(made, "made"), _count(settled, "settled"), _amount(spend, "spend")
    if settled > made:
        raise ValueError("settled: at most the units made")

    def out(why: str, **nums) -> dict:
        return {"state": REASONS[why], "why": why, "propose_close": False, **nums}
    if closed:
        return out("closed_by_person")
    if made == 0:
        return out("not_made")
    if not acct.get("warm"):
        return out("account_thin" if spend > 0 else "no_settled_numbers")
    if spend <= 0:
        return out("no_settled_numbers")
    post = _post(post, "post")
    if post is None:
        raise ValueError("a warm account judges a leaf with settled spend on its posterior: post is None")
    a, b = post
    rate = acct["rate"]
    nums = {"rate": a / b, "lo": quantile(a, b, INTERVAL[0]), "hi": quantile(a, b, INTERVAL[1]),
            "expected": round(spend * rate, 3), "p_better": round(p_above(a, b, rate), 4)}
    if nums["expected"] < cfg["min_expected_conv"]:
        return out("spend_thin", **nums)
    if nums["p_better"] >= cfg["promising_p"]:
        return out("likely_better", **nums)
    if nums["p_better"] <= cfg["downweight_p"]:
        nums["p_reaches"] = round(p_above(a, b, cfg["close_ratio"] * rate), 4)
        got = out("likely_worse", **nums)
        got["propose_close"] = (nums["expected"] >= cfg["close_min_expected_conv"]
                                and settled >= cfg["close_min_units"] and nums["p_reaches"] <= cfg["close_p"])
        return got
    return out("no_difference_yet", **nums)


# ---------------------------------------------------------------- the next batch

def _seed(data: object) -> int:
    """A seed from the data: the first 12 hex of the sha256 of its canonical JSON."""
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12], 16)


def _move(m: object) -> dict:
    if not isinstance(m, Mapping):
        raise ValueError("a move is a mapping")
    what = f"move {m.get('id')!r}"
    if not (isinstance(m.get("group"), str) and m["group"]):
        raise ValueError(f"{what}: group is a non-empty string")
    n = m.get("n")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(f"{what}: n is a whole number at least 1 (the units it makes)")
    if m.get("kind") not in KINDS:
        raise ValueError(f"{what}: kind is one of {', '.join(KINDS)}")
    return {"id": m.get("id"), "group": m["group"], "n": n, "kind": m["kind"], "post": _post(m.get("post"), what),
            "exclusive": _keys(m.get("exclusive", ()), f"{what}: exclusive"),
            "shared": _keys(m.get("shared", ()), f"{what}: shared")}


def pick(moves: Sequence[Mapping], acct: Mapping, cfg: Mapping | None = None, seed: int | None = None) -> dict:
    """{mode, batch, n, moves, left}: the next batch of about batch_size units, drawn from `moves` the harness built. A
    move is {id, group, n, kind, post, exclusive?, shared?, ...}: `n` the units it makes, `kind` known or unknown,
    `post` the posterior it is drawn on (None: the account's own rate, worth prior_conv), `exclusive` and `shared` keys
    (two moves never both hold one key when either holds it exclusive); any other key rides along into the batch.

    Cold (the account not warm): mode `coverage`, the moves in the order given (the harness's coverage order), each
    taken whole while the batch is short, so it may run up to two over. Warm: mode `weights`, first at least
    explore_share of the batch from unknown moves (plain Thompson draws), then batched top-two Thompson over all (each
    draw takes the leader, or, TOP_TWO of the time, the best of a fresh draw over the others); a move up to two over is
    taken rather than leaving the batch short. Always: a group takes at most half a batch, rounded down (at least 1),
    and one move bigger than that only into a group with nothing else, then standing alone. The draws are seeded by
    `seed`, else by the moves and the account, so the same data gives the same batch. Each batch entry is its move
    without `post`, with `basis` (coverage or weights) and, warm, `p_better` (its post against the account's rate)."""
    cfg = settings(cfg)
    if not isinstance(moves, Sequence) or isinstance(moves, (str, bytes)):
        raise ValueError("moves: a list")
    ms = [_move(m) for m in moves]
    _ids(ms, "a move")
    k = cfg["batch_size"]
    cap = max(1, k // 2)
    picked: list[dict] = []
    chosen: list[int] = []
    per_group: dict[str, int] = {}
    held_x: set[str] = set()
    held_s: set[str] = set()

    def total() -> int:
        return sum(x["n"] for x in picked)

    def fits(i: int, limit: int) -> bool:
        m = ms[i]
        if set(m["exclusive"]) & (held_x | held_s) or set(m["shared"]) & held_x:
            return False
        return per_group.get(m["group"], 0) + m["n"] <= max(cap, m["n"]) and total() + m["n"] <= limit

    def take(i: int, why: dict) -> None:
        m = ms[i]
        picked.append({**{x: y for x, y in moves[i].items() if x != "post"}, **why})
        chosen.append(i)
        per_group[m["group"]] = per_group.get(m["group"], 0) + m["n"]
        held_x.update(m["exclusive"])
        held_s.update(m["shared"])

    def done(mode: str) -> dict:
        return {"mode": mode, "batch": picked, "n": total(), "moves": len(ms), "left": len(ms) - len(picked)}

    if not acct.get("warm"):
        for i in range(len(ms)):
            if total() >= k:
                break
            if fits(i, k + 2):
                take(i, {"basis": "coverage"})
        return done("coverage")

    rate, a0 = acct["rate"], cfg["prior_conv"]
    rng = random.Random(seed if seed is not None else _seed(
        [[[m["id"], m["group"], m["kind"], m["n"], m["post"], m["exclusive"], m["shared"]] for m in ms],
         acct["conv"], acct["spend"]]))

    def post_of(i: int) -> Post:
        return ms[i]["post"] or (a0, a0 / rate)

    def draw(i: int) -> float:
        a, b = post_of(i)
        return rng.gammavariate(a, 1 / b)

    def weight(i: int) -> dict:
        return {"basis": "weights", "p_better": round(p_above(*post_of(i), rate), 4)}

    pool = list(range(len(ms)))
    explore = math.ceil(cfg["explore_share"] * k - _SLACK)
    while sum(ms[i]["n"] for i in chosen if ms[i]["kind"] == "unknown") < explore:
        cands = [i for i in pool if ms[i]["kind"] == "unknown" and fits(i, k + 2)]
        if not cands:
            break
        d = {i: draw(i) for i in cands}
        i = max(cands, key=lambda j: d[j])
        pool.remove(i)
        take(i, weight(i))
    while total() < k:
        cands = [i for i in pool if fits(i, k)] or [i for i in pool if fits(i, k + 2)]   # rather two over than short
        if not cands:
            break
        d = {i: draw(i) for i in cands}
        lead = max(cands, key=lambda j: d[j])
        if len(cands) > 1 and rng.random() >= 1 - TOP_TWO:
            rest = [i for i in cands if i != lead]
            again = {i: draw(i) for i in rest}
            lead = max(rest, key=lambda j: again[j])
        pool.remove(lead)
        take(lead, weight(lead))
    return done("weights")


# ---------------------------------------------------------------- same tags, very different numbers

def twins(units: Iterable[Mapping], acct: Mapping, cfg: Mapping | None = None) -> list[dict]:
    """Units of one group with the same tags whose settled rates differ a lot: at most TWINS_MAX, the largest gap first.
    A unit is {id, group, tags, conv, spend, known?}: `group` the leaf (or any key the harness compares within), `tags`
    {name: value} on every dimension the harness records, `conv` and `spend` its settled numbers, `known` {name: value}
    of what else is known about it (when and how it was made). A group of same-tag units is compared when its settled
    conversions reach twin_min_conv, among its units whose settled spend buys at least twin_min_expected_conv at the
    account rate (two of them at least); it is flagged when P(best rate / worst rate >= twin_ratio) under a weak prior
    (TWIN_PRIOR conversions at the account rate) is at least twin_p (DRAWS seeded draws). Each twin: {group, tags, high,
    low, high_rate, low_rate, ratio (None when the low one has no conversion), p, differences: [{what, high, low}] of
    `known`}. A twin is a clue (a dimension nobody records, or the two were bought differently), never proof; no
    account rate, none."""
    cfg = settings(cfg)
    rate = acct.get("rate")
    us = []
    for u in units:
        if not isinstance(u, Mapping):
            raise ValueError("a unit is a mapping")
        what = f"unit {u.get('id')!r}"
        tags, known = u.get("tags"), u.get("known", {})
        if not (isinstance(tags, Mapping) and all(isinstance(k, str) and isinstance(v, str) for k, v in tags.items())):
            raise ValueError(f"{what}: tags are {{name: value}}, strings")
        if not isinstance(known, Mapping):
            raise ValueError(f"{what}: known is a mapping")
        if not (isinstance(u.get("group"), str) and u["group"]):
            raise ValueError(f"{what}: group is a non-empty string")
        us.append({"id": u.get("id"), "group": u["group"], "tags": dict(tags), "known": dict(known),
                   "conv": _amount(u.get("conv"), f"{what}: conv"), "spend": _amount(u.get("spend"), f"{what}: spend")})
    _ids(us, "a unit")
    if not rate:
        return []
    groups: dict[tuple, list[dict]] = {}
    for u in us:
        groups.setdefault((u["group"], tuple(sorted(u["tags"].items()))), []).append(u)
    out = []
    for (group, tags), cs in sorted(groups.items()):
        cs = [u for u in cs if u["spend"] > 0]
        if len(cs) < 2 or math.fsum(u["conv"] for u in cs) < cfg["twin_min_conv"]:
            continue
        cs = [u for u in cs if u["spend"] * rate >= cfg["twin_min_expected_conv"]]
        if len(cs) < 2:
            continue
        post = {u["id"]: (TWIN_PRIOR + u["conv"], TWIN_PRIOR / rate + u["spend"]) for u in cs}
        hi = max(cs, key=lambda u: (post[u["id"]][0] / post[u["id"]][1], u["id"]))
        lo = min(cs, key=lambda u: (post[u["id"]][0] / post[u["id"]][1], u["id"]))
        rng = random.Random(int(hashlib.sha256(f"{hi['id']}|{lo['id']}".encode()).hexdigest()[:12], 16))
        (ah, bh), (al, bl) = post[hi["id"]], post[lo["id"]]
        hit = sum(1 for _ in range(DRAWS)
                  if (b := rng.gammavariate(al, 1 / bl)) > 0 and rng.gammavariate(ah, 1 / bh) / b >= cfg["twin_ratio"])
        p = hit / DRAWS
        if p < cfg["twin_p"]:
            continue
        rh, rl = hi["conv"] / hi["spend"], lo["conv"] / lo["spend"]
        names = list(hi["known"]) + [k for k in lo["known"] if k not in hi["known"]]
        diffs = [{"what": k, "high": hi["known"].get(k), "low": lo["known"].get(k)}
                 for k in names if hi["known"].get(k) != lo["known"].get(k)]
        out.append({"group": group, "tags": dict(tags), "high": hi["id"], "low": lo["id"], "high_rate": rh,
                    "low_rate": rl, "ratio": round(rh / rl, 2) if rl > 0 else None, "p": round(p, 4),
                    "differences": diffs})
    out.sort(key=lambda t: (-(t["ratio"] if t["ratio"] is not None else math.inf), t["group"],
                            sorted(t["tags"].items())))
    return out[:TWINS_MAX]
