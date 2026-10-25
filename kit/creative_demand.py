"""How many creatives to ask the creative maker for: the rules alone, no database .

The request follows the exploration money. What a verdict costs is measured from the creatives' own history (a flow, so a creative still running counts
through the money it has used), how long a verdict takes and how long a request takes to reach a first spend are measured too, and the request is the number
of unknown creatives the exploration money of the days they will spend in can still carry to a verdict, in whole batches, inside the platform's hard limits.

    verdicts()   the creatives that left the exploration states, with their cost, days and outcome
    estimate()   cost per verdict (mean, shrunk toward the lifecycle's doubt line while few), win rate, days to a verdict
    pipeline()   the requests made earlier that no ad group has started from yet, and the lead time those that did show
    request()    the batches to ask for now, with the daily budget of each and the limit that bound them
    fade()       the share of proven creatives that stop being proven per week
    diagnose()   whether the exploration money can replace what the proven creatives will lose (`money_limited`, `surplus`)

Nothing here reads a clock or a file: the pack gathers the inputs.

From the video-ads skill pack (`demand`).

Test: kit/tests/test_creative_demand.py.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

EXPLORE = ("testing", "learning", "doubt")
LOSS_REASONS = ("low_reach", "no_conversion", "weak_creative")        # a loss; `stopped_unjudged` is a switch-off, not a verdict


@dataclass(frozen=True)
class Params:
    batch_size: int
    min_batch: int
    min_verdicts: int
    max_batches: int
    lead_days: int                  # the draft, used until a request has been seen to reach a first spend
    weeks: int                      # how many weeks of history the flow estimate reads
    prior_verdicts: float           # the doubt line counts as this many verdicts when shrinking the cost
    lost_factor: float              # a request with no first spend after this many lead times is taken as lost
    fallback_days: int              # days to a verdict until one is seen (the lifecycle's learning limit)


@dataclass(frozen=True)
class Verdict:
    creative: str
    date: str
    win: bool
    cost: float                     # spend from its first day to the verdict
    days: int


def verdicts(moves: dict[str, list[dict]], days: dict[str, list]) -> list[Verdict]:
    """The first time each creative left the exploration states. `moves` is {creative: [{date, from, to, reason}]} (compute life's), `days` {creative: [Day]}
    (complete, unblocked days only count). Winning is reaching `mature`; losing is `parked` or `ended` for no reach, no conversion or a weak creative."""
    out = []
    for cid, ms in moves.items():
        for m in ms:
            if m["from"] in EXPLORE and m["to"] not in EXPLORE:
                win = m["to"] == "mature"
                if not win and m["reason"] not in LOSS_REASONS:
                    break                                   # switched off unjudged: no verdict, and it does not come back through here
                ds = [d for d in days.get(cid, []) if d.complete and not d.blocked and d.spend > 0 and d.date <= m["date"]]
                if not ds:
                    break
                out.append(Verdict(cid, m["date"], win, sum(d.spend for d in ds),
                                   max(1, (date.fromisoformat(m["date"]) - date.fromisoformat(ds[0].date)).days)))
                break
    return out


def explore_spend(moves: dict[str, list[dict]], days: dict[str, list], since: str, until: str) -> float:
    """The money spent on creatives while they were still in the exploration states, on the days from `since` to `until`."""
    total = 0.0
    for cid, ds in days.items():
        left = next((m["date"] for m in moves.get(cid, []) if m["from"] in EXPLORE and m["to"] not in EXPLORE), None)
        total += sum(d.spend for d in ds if d.complete and not d.blocked and since <= d.date <= until and (left is None or d.date <= left))
    return total


def fade(moves: dict[str, list[dict]], since: str, until: str) -> float | None:
    """Proven creatives (mature or declining) that went to parked or ended in [since, until], per proven creative-week of that window; None with no proven day."""
    lo, hi = date.fromisoformat(since), date.fromisoformat(until)
    exits, proven_days = 0, 0
    for ms in moves.values():
        entered = next((date.fromisoformat(m["date"]) for m in ms if m["to"] == "mature"), None)
        if entered is None:
            continue
        gone = next((date.fromisoformat(m["date"]) for m in ms if m["from"] in ("mature", "declining") and m["to"] in ("parked", "ended")), None)
        a, b = max(entered, lo), min(gone or hi, hi)
        proven_days += max(0, (b - a).days + 1)
        exits += gone is not None and lo <= gone <= hi
    return exits / (proven_days / 7) if proven_days else None


def estimate(vs: list[Verdict], flow: float, doubt: float | None, as_of: str, p: Params) -> dict:
    """{cost, basis, verdicts, wins, win_rate, days}: `flow` the exploration spend of the last `weeks` weeks. The cost is that spend over the verdicts of the same
    weeks, shrunk toward `doubt` by n/(n + prior_verdicts); with no verdict in the window it is `doubt` alone, with neither it is None."""
    lo = (date.fromisoformat(as_of) - timedelta(weeks=p.weeks)).isoformat()
    recent = [v for v in vs if lo < v.date <= as_of]
    n = len(recent)
    if n and doubt:
        cost, basis = (flow + p.prior_verdicts * doubt) / (n + p.prior_verdicts), "measured"
    elif n:
        cost, basis = flow / n, "measured"
    elif doubt:
        cost, basis = doubt, "doubt_spend"
    else:
        cost, basis = None, None
    wins = sum(v.win for v in vs)
    return {"cost": cost, "basis": basis, "verdicts": len(vs), "recent_verdicts": n, "wins": wins,
            "win_rate": (wins + 1) / (len(vs) + 2) if vs else None,
            "days": statistics.median(v.days for v in vs) if vs else p.fallback_days, "days_basis": "measured" if vs else "draft"}


def pipeline(requests: list[dict], starts: list[str], as_of: str, p: Params) -> dict:
    """Match each requested batch to the earliest ad group whose first spend came on or after the request (`starts`, dates). {in_production: creatives not yet seen,
    lost: creatives of requests with no start after lost_factor lead times, leads: days from request to start of those matched, lead: the median or the draft}.
    `requests` are {date, n, batches} oldest first."""
    free = sorted(starts)
    leads: list[int] = []
    in_production = lost = 0.0
    horizon = p.lost_factor * p.lead_days
    for r in sorted(requests, key=lambda r: r["date"]):
        per = r["n"] / r["batches"] if r["batches"] else 0.0
        for _ in range(r["batches"]):
            i = next((i for i, s in enumerate(free) if s >= r["date"]), None)
            if i is not None:
                leads.append((date.fromisoformat(free.pop(i)) - date.fromisoformat(r["date"])).days)
            elif (date.fromisoformat(as_of) - date.fromisoformat(r["date"])).days > horizon:
                lost += per
            else:
                in_production += per
    return {"in_production": in_production, "lost": lost, "leads": leads,
            "lead": statistics.median(leads) if leads else float(p.lead_days), "lead_basis": "measured" if leads else "draft"}


def batches_of(n: int, p: Params) -> list[int]:
    """`n` creatives as whole batches: as many of `batch_size` as fit, then the remainder as a batch of its own when it reaches `min_batch`."""
    full, rest = divmod(max(n, 0), p.batch_size)
    return [p.batch_size] * full + ([rest] if rest >= p.min_batch else [])


def request(cost: float | None, days: float, lead: float, explore: list[tuple[str, float]], t: date, spent: list[float], promised: float,
            verdict_count: int, limits: dict, p: Params) -> dict:
    """The request on day `t`. `explore` is the plan's exploration money by day (date, money); `spent` the money each creative still in exploration has used so far;
    `promised` the creatives asked for earlier that no ad group has started; `limits` {min, max}: an ad group's daily budget range, either may be None.
    {n, batches [{size, daily_budget}], money, committed, capacity, binding, constraints}."""
    out = {"n": 0, "batches": [], "money": None, "committed": None, "capacity": 0, "binding": None, "constraints": []}
    if not cost:
        out["constraints"].append("cost_unknown")
        return out
    start, end = t + timedelta(days=math.ceil(lead)), t + timedelta(days=math.ceil(lead) + math.ceil(days))
    inside = [m for d, m in explore if start <= date.fromisoformat(d) < end]
    horizon = max(0, (end - start).days)
    if not explore:
        money = 0.0
    elif len(inside) < horizon:                     # the plan stops at the month's end: the rest of the window is spent at the plan's average
        money = sum(inside) + (horizon - len(inside)) * (sum(m for _, m in explore) / len(explore))
        out["constraints"].append("window_extended")
    else:
        money = sum(inside)
    committed = sum(max(cost - s, 0.0) for s in spent) + promised * cost
    out["money"], out["committed"] = round(money, 2), round(committed, 2)
    free = money - committed
    out["capacity"] = max(0, math.floor(free / cost))
    if out["capacity"] == 0:
        out["constraints"].append("money_committed" if committed > 0 and money > 0 else "no_exploration_money")
        return out
    sizes = batches_of(out["capacity"], p)
    if verdict_count < p.min_verdicts:
        sizes = sizes[:1]
        out["constraints"].append("few_verdicts")
    if len(sizes) > p.max_batches:
        sizes = sizes[:p.max_batches]
        out["constraints"].append("max_batches")
    chosen, spend_left, binding = [], free, None
    for s in sizes:
        budget = s * cost / max(days, 1)
        if limits.get("min") and budget < limits["min"]:
            budget, binding = limits["min"], "min_daily_budget"
        if limits.get("max") and budget > limits["max"]:
            budget, binding = limits["max"], "max_daily_budget"
        need = budget * max(days, 1)
        if need > spend_left + 1e-9:
            binding = binding or "exploration_money"
            break
        spend_left -= need
        chosen.append({"size": s, "daily_budget": round(budget, 2)})
    out["batches"], out["n"], out["binding"] = chosen, sum(b["size"] for b in chosen), binding
    if not chosen:
        out["constraints"].append("limit_binds")
    return out


def diagnose(perform_per_day: float | None, mean_daily: float | None, proven: int, fade_weekly: float, lead: float, days: float,
             win_rate: float | None, capacity: int) -> dict | None:
    """Whether the exploration money can replace the proven creatives that will fade by the time a new one is proven. P* is how many proven creatives the performance
    money can feed; `need` the new creatives it takes to make up the shortfall at the win rate. None when it cannot be read (no performance money or no proven creative)."""
    if not perform_per_day or not mean_daily or proven <= 0 or not win_rate:
        return None
    wanted = perform_per_day / mean_daily
    left = proven * max(0.0, 1 - fade_weekly * (lead + days) / 7)
    need = max(0, math.ceil(max(0.0, wanted - left) / win_rate))
    flag = "money_limited" if need > capacity else ("surplus" if need < capacity else None)
    return {"wanted_proven": round(wanted, 2), "proven_then": round(left, 2), "need": need, "flag": flag}
