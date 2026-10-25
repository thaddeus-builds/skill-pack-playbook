"""The split of the perform wallet across campaigns: the rules alone, no database, no platform.

Equal marginal return, in bounded steps (the KKT condition of a concave allocation, water-filling with a box): money moves from a
campaign whose marginal return is under the common level to one above it, by at most `step` a day (`fast_step` when the sign has
held `fast_days` days and the evidence separates), only when the evidence excludes zero, and not again before the cooldown. Every
number is a field of `Params`. Nothing here writes: the output is a proposal and its replay.

From the video-ads skill pack (`allocation`).

Test: kit/tests/test_allocation.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Params:
    step: float = 0.10
    fast_step: float = 0.20
    fast_days: int = 3
    cooldown_days: int = 3
    min_days: int = 30
    evidence_z: float = 1.64
    e_min: float = 0.2
    e_max: float = 1.0
    prior_sd: float = 0.2


@dataclass
class Arm:
    """One campaign's state in the loop: its budget, the days since its last move, and the run of days its marginal return has been on one side of the level."""
    id: str
    budget: float
    last_move: int | None = None
    streak: int = 0
    side: int = 0
    moves: list = field(default_factory=list)


def elasticity(points: list[tuple[float, float]], p: Params) -> tuple[float, float] | None:
    """(e, standard error) of log revenue on log spend over the days (spend, revenue) with both above 0; None under `min_days` such days or with no spread in the
    spend (the response to a budget cannot be seen without variation)."""
    xs = [(math.log(s), math.log(r)) for s, r in points if s > 0 and r > 0]
    n = len(xs)
    if n < p.min_days:
        return None
    mx, my = sum(x for x, _ in xs) / n, sum(y for _, y in xs) / n
    sxx = sum((x - mx) ** 2 for x, _ in xs)
    if sxx < 1e-6:
        return None
    b = sum((x - mx) * (y - my) for x, y in xs) / sxx
    resid = sum((y - (my + b * (x - mx))) ** 2 for x, y in xs) / max(n - 2, 1)
    return b, math.sqrt(resid / sxx)


def shrink(own: tuple[float, float] | None, pooled: float, p: Params) -> tuple[float, float]:
    """The elasticity pulled toward the pooled value by precision (the prior's sd is `prior_sd`), held between `e_min` and `e_max`: (e, its standard error).
    No reading of its own gives the pooled value and the prior's sd."""
    if own is None:
        return min(max(pooled, p.e_min), p.e_max), p.prior_sd
    e, se = own
    w_own, w_pool = 1 / max(se, 1e-6) ** 2, 1 / p.prior_sd ** 2
    e = (w_own * e + w_pool * pooled) / (w_own + w_pool)
    return min(max(e, p.e_min), p.e_max), math.sqrt(1 / (w_own + w_pool))


def marginal(e: float, se_e: float, roas: float, conversions: float) -> tuple[float, float]:
    """(marginal return, its standard error): e x the average return, the relative error of both parts added in quadrature (the average's from the conversions
    it stands on, Poisson)."""
    m = e * roas
    rel = math.sqrt((se_e / max(e, 1e-6)) ** 2 + 1 / max(conversions, 1.0))
    return m, m * rel


def budget_at(level: float, b: float, m: float, e: float) -> float:
    """The budget at which a campaign's marginal return falls to `level`, on revenue = a x^e calibrated at its budget b, where it is m: x = b (m / level)^(1/(1-e))."""
    return b * (m / level) ** (1 / (1 - e)) if level > 0 else float("inf")


def solve(items: list[dict], total: float) -> float:
    """The common level lambda (bisection) at which the campaigns' budgets, each clipped to its box [lo, hi], add up to `total`. Each item has b, m, e, lo, hi;
    returns the level (the sum may stay off `total` when the boxes cannot reach it: the boxes win)."""
    lo, hi = 1e-9, max(i["m"] for i in items) * 1e6
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        got = sum(min(max(budget_at(mid, i["b"], i["m"], i["e"]), i["lo"]), i["hi"]) for i in items)
        if got > total:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def day(arms: list[Arm], inputs: dict, today: int, p: Params, fast: bool = True) -> list[dict]:
    """One day's decision over the arms of the performance wallet. `inputs[id]` = {e, se_e, roas, conversions}; returns the moves made today
    [{id, from, to, level, z, cap}] and updates the arms (budget, last_move, streak).

    1. the level lambda_u without the boxes (the equal-marginal point) and each campaign's z = (m - lambda_u)/se: the evidence;
    2. a campaign with no evidence (|z| under `evidence_z`) keeps its budget and its run is reset; one with evidence extends its run on its side;
    3. a campaign in its cooldown keeps its budget; the others move to the box solution over their own total, the box being `step` (or `fast_step` after
       `fast_days` days on one side, when `fast`) either way."""
    live = [a for a in arms if a.id in inputs and a.budget > 0]
    if len(live) < 2:
        return []
    for a in live:
        i = inputs[a.id]
        i["m"], i["se"] = marginal(i["e"], i["se_e"], i["roas"], i["conversions"])
        i["b"] = a.budget
    wide = [{"b": a.budget, "m": inputs[a.id]["m"], "e": inputs[a.id]["e"], "lo": a.budget * 0.2, "hi": a.budget * 5} for a in live]
    lam_u = solve(wide, sum(a.budget for a in live))
    movers = []
    for a in live:
        i = inputs[a.id]
        z = (i["m"] - lam_u) / max(i["se"], 1e-9)
        side = 0 if abs(z) < p.evidence_z else (1 if z > 0 else -1)
        a.streak = a.streak + 1 if side and side == a.side else (1 if side else 0)
        a.side = side
        i["z"] = z
        cooling = a.last_move is not None and today - a.last_move < p.cooldown_days
        if side and not cooling:
            movers.append(a)
    if len(movers) < 2:
        return []
    items = []
    for a in movers:
        cap = p.fast_step if (fast and a.streak >= p.fast_days) else p.step
        i = inputs[a.id]
        items.append({"a": a, "b": a.budget, "m": i["m"], "e": i["e"], "lo": a.budget * (1 - cap), "hi": a.budget * (1 + cap), "cap": cap})
    level = solve(items, sum(a.budget for a in movers))
    out = []
    for it in items:
        a = it["a"]
        new = min(max(budget_at(level, it["b"], it["m"], it["e"]), it["lo"]), it["hi"])
        if abs(new - a.budget) / a.budget < 0.005:
            continue
        move = {"id": a.id, "from": round(a.budget, 2), "to": round(new, 2), "level": round(level, 3), "z": round(inputs[a.id]["z"], 2), "cap": it["cap"]}
        a.moves.append({**move, "day": today})
        a.budget, a.last_move = new, today
        out.append(move)
    return out


def clip_move(frm: float, to: float, lo: float | None, hi: float | None) -> tuple[float, str | None]:
    """(budget, binding): a proposed budget kept inside the platform's range [lo, hi] (either may be None: no limit known), and which end held it back."""
    if lo is not None and to < lo:
        return min(lo, frm), "min_daily_budget"
    if hi is not None and to > hi:
        return max(hi, frm), "max_daily_budget"
    return to, None


def held_reason(arm: Arm, i: dict | None, today: int, p: Params) -> str:
    """Why a campaign in the performance wallet gets no move today: `no_reading` (no return to read), `too_few` (fewer than two campaigns to move money between),
    `no_evidence` (its marginal return is not apart from the common level), `cooldown` (it moved lately), `no_counterpart` (the evidence is there but nothing to move
    the money to or from)."""
    if i is None:
        return "no_reading"
    if "z" not in i:
        return "too_few"
    if abs(i["z"]) < p.evidence_z:
        return "no_evidence"
    if arm.last_move is not None and today - arm.last_move < p.cooldown_days:
        return "cooldown"
    return "no_counterpart"


def follow(frm: float, to: float, now: float | None, age_days: int, follow_days: int) -> str:
    """What became of a recorded proposal `frm` -> `to`, `age_days` later when the budget reads `now`: `open` before `follow_days` have passed or with no reading,
    `taken` when the budget moved the proposed way by at least half the proposed distance, else `not_taken`."""
    if now is None or age_days < follow_days:
        return "open"
    want = to - frm
    return "taken" if want and (now - frm) * want > 0 and abs(now - frm) >= abs(want) / 2 else "not_taken"
