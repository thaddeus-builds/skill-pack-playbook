"""The demand document: how many creatives to ask the creative maker for. The request follows the exploration money of the pacing plan: what a verdict costs is
measured from the creatives' own history, how long a verdict takes and how long a request takes to reach a first spend are measured too, and the request is the
number of unknown creatives the exploration money of the days they will spend in can still carry to a verdict, in whole batches, inside the platform's hard
limits. No database, no file, no clock, no platform: the pack hands over the creatives' days (the same `Source` the life document reads), the pacing document's
plan and which wallet pays each creative, the earlier requests and the platform's range, and prints what `compute()` returns. A proposal, never a write.

    {month, demand {explore_next_7_days, unit_cost, basis, n, batches [{size, daily_budget}], batch_size, capacity, money, committed, binding, constraints,
     verdicts, wins, win_rate, days_to_verdict, days_basis, lead_days, lead_basis, in_production, lost, fade_weekly, diagnostic {flag, need, ...} | None,
     limits {min, max}} | None, warnings, warning_codes}

`demand` is None when the pacing plan is (no spend target for the month: nothing to ask for). The pack adds its own `meta`. The creatives' moves and states are the life
document's (`kit.compute_life`, run on the same creatives, whose own warnings this document keeps); the rules are `kit.creative_demand`'s. `kit.compute_review` takes
the `demand` block as it is.

From the video-ads skill pack (`scripts/compute_pacing.py` `_demand`, the `creative_demand` of its pacing document; its cases are this module's test, over a
synthetic fixture).

Test: kit/tests/test_compute_demand.py.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from kit import compute_life, creative_demand as demand
from kit.contract import SkillPackError
from kit.messages import coded, msg

WALLETS = ("perform", "explore")


@dataclass
class Source:
    """One reading of a pack's tables.

    life       the creatives' days, as `kit.compute_life.Source` has them
    plan       the `plan` of the pacing document (`kit.compute_pacing`): the exploration money by day, the day planned and its performance money; None without one
    paid       {creative id: the wallet that pays it today (`perform`, `explore` or None)}: the pacing document's `creative_wallets`, which says what its ad group
               allows; a creative not named keeps the wallet of its own state
    groups     {ad group id: {days: {day: (spend, conversions)}, active}} as for the pacing document: the first day an ad group spent is when a request reached it
    requests   [{date, n, batches}]: the creatives asked for earlier, oldest first, the pack's own record of them
    limits     {"min": an ad group's lowest daily budget, "max": its highest}, a side None when unknown
    warnings   coded messages the pack's own reading raised, kept in the document
    """
    life: compute_life.Source
    plan: dict | None
    paid: dict = field(default_factory=dict)
    groups: dict = field(default_factory=dict)
    requests: list = field(default_factory=list)
    limits: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def _bad(part: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("compute_input_invalid", f"the pack's tables give {part} {problem}", part=part, problem=problem))


def check(src: Source) -> None:
    """Refuse a `Source` the rules cannot read, naming the part (`compute_input_invalid`)."""
    compute_life.check(src.life)
    if src.plan is not None:
        if not isinstance(src.plan, dict) or not isinstance(src.plan.get("days"), list) or "day" not in src.plan or "month" not in src.plan:
            raise _bad("plan", "that is not the plan of the pacing document (month, day, days)")
        for r in src.plan["days"]:
            if not isinstance(r, dict) or not {"day", "explore"} <= set(r):
                raise _bad("plan", "whose days are not {day, explore}")
    for cid, w in src.paid.items():
        if w is not None and w not in WALLETS:
            raise _bad(f"paid[{cid}]", f"{w!r}, which is not perform, explore or None")
    for g, x in src.groups.items():
        if not isinstance(x, dict) or "days" not in x:
            raise _bad(f"groups[{g}]", "without days")
    for i, r in enumerate(src.requests):
        if not isinstance(r, dict) or not {"date", "n", "batches"} <= set(r):
            raise _bad(f"requests[{i}]", "that is not {date, n, batches}")
    for side, v in src.limits.items():
        if side not in ("min", "max") or (v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)))):
            raise _bad("limits", "that are not {min, max} numbers or None")


def params(k: dict) -> demand.Params:
    """`kit.creative_demand`'s parameters from the thresholds in effect (the `demand_*` rows, and the days a creative may stay in learning)."""
    return demand.Params(int(k["demand_batch_size"]), int(k["demand_min_batch"]), int(k["demand_min_verdicts"]), int(k["demand_max_batches"]),
                         int(k["demand_lead_days"]), int(k["demand_weeks"]), k["demand_prior_verdicts"], k["demand_lost_factor"], int(k["life_learning_max_days"]))


def compute(src: Source, k: dict) -> dict:
    """The document. `k` is the thresholds in effect: the `demand_*` rows and the `life_*` rows the life document reads."""
    check(src)
    life = compute_life.compute(src.life, k)
    warnings = list(src.warnings) + list(life["warnings"])
    if src.plan is None or not life["as_of"]:
        return {"month": None if src.plan is None else src.plan["month"], "demand": None, **coded("warnings", warnings)}
    plan, rows, month = src.plan, life["rows"], src.plan["month"]
    p = params(k)
    last = date.fromisoformat(life["as_of"])
    moves = {r["creative"]: r["moves"] for r in rows}
    days = {cid: c["days"] for cid, c in src.life.creatives.items()}
    iso, lo = last.isoformat(), (last - timedelta(weeks=p.weeks)).isoformat()
    unit = life["params"]["doubt_spend"]["value"]
    paid = {r["creative"]: src.paid.get(r["creative"], r["wallet"]) for r in rows}
    vs = demand.verdicts(moves, days)
    est = demand.estimate(vs, demand.explore_spend(moves, days, lo, iso), unit, iso, p)
    starts = [min(d for d, x in g["days"].items() if x[0] > 0) for g in src.groups.values() if any(x[0] > 0 for x in g["days"].values())]
    pipe = demand.pipeline(src.requests, starts, iso, p)
    explore = [(r["day"], r["explore"]) for r in plan["days"]]
    t = date.fromisoformat(plan["day"]["day"]) if plan["day"] else last + timedelta(days=1)
    limits = {"min": src.limits.get("min"), "max": src.limits.get("max")}
    spent = [r["totals"].get("spend", 0.0) for r in rows if r["state"] in demand.EXPLORE and paid[r["creative"]] == "explore"]
    req = demand.request(est["cost"], est["days"], pipe["lead"], explore, t, spent, pipe["in_production"], est["verdicts"], limits, p)
    proven = [r["spend7"] / 7 for r in rows if paid[r["creative"]] == "perform" and r["spend7"] > 0]
    fade = demand.fade(moves, lo, iso)
    diag = demand.diagnose(plan["day"]["perform"] if plan["day"] else None, sum(proven) / len(proven) if proven else None, len(proven), fade or 0.0,
                           pipe["lead"], est["days"], est["win_rate"], req["capacity"])
    block = {"explore_next_7_days": round(sum(m for _, m in explore[:7]), 2), "unit_cost": None if est["cost"] is None else round(est["cost"], 2), "basis": est["basis"],
             "n": None if est["cost"] is None else req["n"], "batches": req["batches"], "batch_size": p.batch_size, "capacity": req["capacity"], "money": req["money"],
             "committed": req["committed"], "binding": req["binding"], "constraints": req["constraints"], "verdicts": est["verdicts"], "wins": est["wins"],
             "win_rate": None if est["win_rate"] is None else round(est["win_rate"], 3), "days_to_verdict": est["days"], "days_basis": est["days_basis"],
             "lead_days": pipe["lead"], "lead_basis": pipe["lead_basis"], "in_production": round(pipe["in_production"], 2), "lost": round(pipe["lost"], 2),
             "fade_weekly": None if fade is None else round(fade, 4), "diagnostic": diag, "limits": limits}
    if est["cost"] is None:
        warnings.append(msg("pacing_demand_unknown", f"{month}: what it takes to judge one creative (doubt_spend) is not known yet: no number of creatives to ask for", month=month))
    if req["binding"] in ("min_daily_budget", "max_daily_budget"):
        warnings.append(msg("pacing_limit_binds", f"{month}: the platform's {req['binding']} bound the request", month=month, limit=req["binding"]))
    if diag and diag["flag"] == "money_limited":
        warnings.append(msg("pacing_money_limited", f"{month}: the proven creatives will fade and the exploration money can carry {req['capacity']} new ones to a verdict, "
                            f"{diag['need']} are needed: raise the exploration share or accept a lower result", month=month, need=diag["need"], capacity=req["capacity"]))
    elif diag and diag["flag"]:
        warnings.append(msg("pacing_surplus", f"{month}: the exploration money can carry {req['capacity']} new creatives to a verdict and {diag['need']} are needed to replace the "
                            "fading ones: the rest explores new directions", month=month, need=diag["need"], capacity=req["capacity"]))
    return {"month": month, "demand": block, **coded("warnings", warnings)}
