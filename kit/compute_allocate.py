"""The allocation document: the split of the performance wallet across a pack's campaigns as the mechanism of `kit.allocation` would have made it, day by day,
over the last days (a replay), and with `propose` tomorrow's moves from the campaigns' actual budgets. No database, no file, no clock, no platform: the pack
reads its own tables into a `Source` (below) and prints what `compute()` returns. Nothing here writes: a proposal is a sentence with its evidence, and a
person changes a budget. A replay cannot say what the moves would have earned: there is no counterfactual in the data.

The wallet is the campaigns in a performance state (earning, steady, lagging, declining, fatigued; unjudged, learning and setup are exploration; blocked and
ended spend nothing) on each day, and its money is held constant: only the split moves. Each campaign starts at its mean spend of the 7 days before the replay;
its marginal return is the shrunk elasticity of its own days times its recent return; a move needs the evidence to exclude zero, respects a cooldown and, after
the sign has held `fast_days` days, may be `fast_step` instead of `step`. The same run with the acceleration off is given beside it. The evidence bar is not a
guess: the replay is run at each bar of a grid, and the bar used is the lowest at which at most `allocation_flip_target` of the moves are undone within a week
(and `allocation_calibration_min_moves` were made); with none that qualifies, the base value of `allocation_evidence_z` stands. It is recomputed on every run.

    {as_of, currency, days, params {step, fast_step, fast_days, cooldown_days, min_days, evidence_z {value, source calibrated|base, base, grid [...]},
     elasticity, prior_sd}, campaigns [{campaign, name, start, end, actual_spend_start, actual_spend_end, path, moves, stats, states}],
     summary {campaigns, moves, fast_moves, flips, campaigns_moved}, without_acceleration {summary}, warnings, warning_codes,
     proposal {day, currency, moves [{campaign, name, from, to, change, cap, fast, z, level, marginal {value, se, low, high}, binding, doubt, budget_basis}],
     held [{campaign, name, why}], limits, unallocated, followed {taken, not_taken, open, recorded, items}}  (with `propose`)}

The pack adds its own `meta`. `Source.states` is what the campaign document says over the weeks (`kit.compute_campaign.timeline`): a series of dated states per campaign.

From the video-ads skill pack (`scripts/compute_allocate.py`; its cases are this module's test, over a synthetic fixture).

Test: kit/tests/test_compute_allocate.py.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from kit import allocation, lifecycle
from kit.contract import SkillPackError
from kit.messages import coded, msg

PERFORMANCE = ("earning", "steady", "lagging", "declining", "fatigued")
GRID = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
CAMPAIGN_KEYS = ("name", "status", "budget", "group_budget")


@dataclass
class Source:
    """One reading day of a pack's tables. Days are ISO dates, money in the account's currency.

    as_of            the last complete day (None: the tables hold none yet, and the document is refused)
    currency         the account's currency, or None
    campaigns        {campaign id: {name, status, budget, group_budget}}, as `kit.compute_campaign.Source.campaigns` has them: `status` is
                     `lifecycle.ACTIVE`, another word or None, `budget` the campaign's own daily budget or None, `group_budget` the sum of its ad groups'
    days             {campaign id: {day: (spend, revenue, conversions, impressions, clicks)}}, the days it spent (as `compute_campaign.Source.days`)
    states           {campaign id: {checkpoint day: the campaign's state}} (`lifecycle.STATES`): the state on a day is the latest checkpoint's at or before it,
                     the first for a day before them
    budget_history   {campaign id: [the daily budgets the platform's record shows]}: one value only says no budget change was ever seen
    limits           {"min": the platform's lowest daily budget, "max": its highest}, a side None when unknown
    records          [{day, moves: [{campaign, from, to}]}]: the advice recorded earlier, oldest first, whose fate the proposal reports
    warnings         coded messages the pack's own reading raised, kept in the document
    """
    as_of: str | None
    currency: str | None
    campaigns: dict
    days: dict
    states: dict
    budget_history: dict = field(default_factory=dict)
    limits: dict = field(default_factory=dict)
    records: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _bad(part: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("compute_input_invalid", f"the pack's tables give {part} {problem}", part=part, problem=problem))


def _day(part: str, value) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise _bad(part, f"{value!r}, which is not a day (YYYY-MM-DD)") from None


def check(src: Source) -> None:
    """Refuse a `Source` the rules cannot read, naming the part (`compute_input_invalid`)."""
    if src.as_of is None:
        raise _bad("as_of", "none: no complete day to judge")
    _day("as_of", src.as_of)
    for cid, c in src.campaigns.items():
        absent = [x for x in CAMPAIGN_KEYS if not isinstance(c, dict) or x not in c]
        if absent:
            raise _bad(f"campaigns[{cid}]", f"without {', '.join(absent)}")
    for cid, ds in src.days.items():
        for day, x in ds.items():
            _day(f"days[{cid}]", day)
            if not isinstance(x, (tuple, list)) or len(x) != 5:
                raise _bad(f"days[{cid}][{day}]", "that is not (spend, revenue, conversions, impressions, clicks)")
    for cid, series in src.states.items():
        for day, state in series.items():
            _day(f"states[{cid}]", day)
            if state not in lifecycle.STATES:
                raise _bad(f"states[{cid}][{day}]", f"{state!r}, which is not a state")
    for side, v in src.limits.items():
        if side not in ("min", "max") or (v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)))):
            raise _bad("limits", "that are not {min, max} numbers or None")
    for i, r in enumerate(src.records):
        if not isinstance(r, dict) or "day" not in r or not all(isinstance(m, dict) and {"campaign", "from", "to"} <= set(m) for m in r.get("moves", ())):
            raise _bad(f"records[{i}]", "that is not {day, moves [{campaign, from, to}]}")
        _day(f"records[{i}]", r["day"])


def calibrated_z(grid: list[dict], k: dict) -> float | None:
    """The evidence bar the replay's own record picks (a fixed rule, recomputed on every run): the lowest bar at which at most `allocation_flip_target` of the moves
    are reversed within a week and at least `allocation_calibration_min_moves` moves were made (a bar that moves nothing proves nothing). None when no bar
    qualifies: the base value stands."""
    for g in grid:
        if g["moves"] >= k["allocation_calibration_min_moves"] and g["flip_share"] is not None and g["flip_share"] <= k["allocation_flip_target"]:
            return g["evidence_z"]
    return None


def params(k: dict, step: float | None = None, fast_step: float | None = None, fast_days: int | None = None,
           weekly_step_cap: float | None = None) -> allocation.Params:
    """`kit.allocation`'s parameters from the thresholds in effect; a run may replace the step, the faster step and the days the sign must hold."""
    return allocation.Params(
        step=step if step is not None else k["allocation_step"], fast_step=fast_step if fast_step is not None else k["allocation_step_fast"],
        fast_days=int(fast_days if fast_days is not None else k["allocation_fast_days"]), cooldown_days=int(k["allocation_cooldown_days"]),
        min_days=int(k["allocation_min_days"]), evidence_z=k["allocation_evidence_z"], e_min=k["allocation_elasticity_min"],
        e_max=k["allocation_elasticity_max"], prior_sd=k["allocation_prior_sd"], weekly_step_cap=weekly_step_cap)


def _inputs(arms: dict, days: dict, state_at, d: str, p: allocation.Params, window: int) -> dict:
    """The readings of day `d` for the arms in the performance wallet: {id: {e, se_e, roas, conversions, own_reading}} from the days before `d`; `own_reading`
    says the elasticity had a reading of its own (else it is the pooled value)."""
    end = date.fromisoformat(d) - timedelta(days=1)
    inputs, pool = {}, []
    for cid in arms:
        if state_at(cid, d) not in PERFORMANCE:
            continue
        hist = [(x[0], x[1]) for dd, x in days[cid].items() if date.fromisoformat(dd) <= end]
        own = allocation.elasticity(hist, p)
        if own:
            pool.append(own[0])
        recent = [x for dd, x in days[cid].items() if end - timedelta(days=window - 1) <= date.fromisoformat(dd) <= end]
        spend, rev, conv = sum(x[0] for x in recent), sum(x[1] for x in recent), sum(x[2] for x in recent)
        if spend <= 0 or rev <= 0:
            continue
        inputs[cid] = {"own": own, "roas": rev / spend, "conversions": conv}
    pooled = sorted(pool)[len(pool) // 2] if pool else 0.5
    for i in inputs.values():
        i["own_reading"] = i["own"] is not None
        i["e"], i["se_e"] = allocation.shrink(i.pop("own"), pooled, p)
    return inputs


def _run(ids, days, state_at, dates, p: allocation.Params, window: int, fast: bool) -> dict:
    """The loop over `dates` for the campaigns `ids`: {id: Arm}, the budget path, the starting budgets."""
    first = date.fromisoformat(dates[0])
    start = {}
    for cid in ids:
        spent = [days[cid].get((first - timedelta(days=i)).isoformat(), (0.0,))[0] for i in range(1, 8)]
        start[cid] = sum(spent) / 7
    arms = {cid: allocation.Arm(cid, start[cid]) for cid in ids if start[cid] > 0}
    path = {cid: [] for cid in arms}
    for t, d in enumerate(dates):
        inputs = _inputs(arms, days, state_at, d, p, window)
        allocation.day(list(arms.values()), inputs, t, p, fast)
        for cid, arm in arms.items():
            path[cid].append({"day": d, "budget": round(arm.budget, 2)})
    return {"arms": arms, "path": path, "start": start}


def _stats(arm: allocation.Arm) -> dict:
    mv = arm.moves
    flips = sum(1 for a, b in zip(mv, mv[1:]) if (a["to"] > a["from"]) != (b["to"] > b["from"]) and b["day"] - a["day"] <= 7)
    return {"moves": len(mv), "fast_moves": sum(1 for m in mv if m["cap"] > mv[0]["cap"]) if mv and len({m["cap"] for m in mv}) > 1 else 0, "flips": flips}


def _summary(res: dict) -> dict:
    st = [_stats(a) for a in res["arms"].values()]
    return {"campaigns": len(st), "moves": sum(s["moves"] for s in st), "fast_moves": sum(s["fast_moves"] for s in st), "flips": sum(s["flips"] for s in st),
            "campaigns_moved": sum(1 for s in st if s["moves"])}


def _propose(res: dict, src: Source, days: dict, state_at, end: date, t: int, p: allocation.Params, window: int, follow_days: int) -> dict:
    """Tomorrow's moves: the loop's own state (streaks, cooldowns) carried to the next day, but the budgets reset to what the campaigns really have now, so a move is
    from a real budget. Each move has its marginal return with an interval, the doubt behind it and the platform's range applied; a campaign in the wallet with
    no move says why. What was advised before is read back from the record."""
    day = (end + timedelta(days=1)).isoformat()
    limits = {"min": src.limits.get("min"), "max": src.limits.get("max")}
    names = {cid: c.get("name") for cid, c in src.campaigns.items()}
    live, held, basis = {}, [], {}
    for cid, arm in res["arms"].items():
        if state_at(cid, day) not in PERFORMANCE:
            continue
        st = src.campaigns.get(cid) or {}
        budget, basis[cid] = (st.get("budget") or 0.0), "campaign"
        if budget <= 0:
            budget, basis[cid] = (st.get("group_budget") or 0.0), "ad sets"
        if st.get("status") not in (None, lifecycle.ACTIVE):
            held.append({"campaign": cid, "name": names.get(cid), "why": "not_delivering"})
        elif budget <= 0:
            held.append({"campaign": cid, "name": names.get(cid), "why": "budget_unknown"})
        else:
            scale = budget / arm.budget if arm.budget > 0 else 1.0        # the replayed moves, at the real budget's scale, for the weekly cap
            live[cid] = allocation.Arm(cid, budget, arm.last_move, arm.streak, arm.side,
                                       [{**m, "from": m["from"] * scale, "to": m["to"] * scale} for m in arm.moves])
    inputs = _inputs(live, days, state_at, day, p, window)
    start = {cid: a.budget for cid, a in live.items()}
    moved = {m["id"]: m for m in allocation.day(list(live.values()), inputs, t, p, True)}
    moves, unallocated = [], 0.0
    for cid, a in live.items():
        m = moved.get(cid)
        if m is None:
            held.append({"campaign": cid, "name": names.get(cid), "why": allocation.held_reason(a, inputs.get(cid), t, p)})
            continue
        to, binding = allocation.clip_move(start[cid], m["to"], limits.get("min"), limits.get("max"))
        unallocated += m["to"] - to if m["to"] > start[cid] else to - m["to"]
        if abs(to - start[cid]) / start[cid] < 0.005:
            held.append({"campaign": cid, "name": names.get(cid), "why": "limit", "binding": binding})
            continue
        i = inputs[cid]
        doubt = ["no_counterfactual"] + ([] if i["own_reading"] else ["elasticity_pooled"]) + (["budget_from_ad_sets"] if basis[cid] == "ad sets" else []) \
            + ([] if len({v for v in src.budget_history.get(cid, [])}) > 1 else ["no_budget_change_seen"])
        moves.append({"campaign": cid, "name": names.get(cid), "from": round(start[cid], 2), "to": round(to, 2), "change": round(to / start[cid] - 1, 4), "cap": m["cap"],
                      "fast": m["cap"] > p.step, "z": m["z"], "level": m["level"],
                      "marginal": {"value": round(i["m"], 3), "se": round(i["se"], 3), "low": round(i["m"] - p.evidence_z * i["se"], 3),
                                   "high": round(i["m"] + p.evidence_z * i["se"], 3)},
                      "binding": binding, "doubt": doubt, "budget_basis": basis[cid]})
    taken = []
    for r in src.records:
        if r["day"] >= day:
            continue
        age = (date.fromisoformat(day) - date.fromisoformat(r["day"])).days
        for mv in r["moves"]:
            st = src.campaigns.get(mv["campaign"]) or {}
            now = (st.get("budget") or st.get("group_budget") or None)
            taken.append({"day": r["day"], "campaign": mv["campaign"], "from": mv["from"], "to": mv["to"], "now": now,
                          "result": allocation.follow(mv["from"], mv["to"], now, age, follow_days)})
    count = {k: sum(1 for x in taken if x["result"] == k) for k in ("taken", "not_taken", "open")}
    return {"day": day, "currency": src.currency, "moves": sorted(moves, key=lambda m: -abs(m["to"] - m["from"])), "held": held, "limits": limits,
            "unallocated": round(unallocated, 2), "followed": {**count, "recorded": len(taken), "items": taken[-20:]}}


def compute(src: Source, k: dict, *, days: int = 56, propose: bool = False, step: float | None = None, fast_step: float | None = None,
            fast_days: int | None = None, weekly_step_cap: float | None = None) -> dict:
    """The document: the replay of the last `days` days, and with `propose` tomorrow's moves. `k` is the thresholds in effect (`Thresholds.load()`): the
    `allocation_*` rows and `campaign_window_days`. `step`, `fast_step` and `fast_days` replace the thresholds for this run; `weekly_step_cap` caps the
    compounded change of a campaign's budget over 7 days."""
    check(src)
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise _bad("days", f"{days!r}, which is not a number of days of 1 or more")
    p = params(k, step, fast_step, fast_days, weekly_step_cap)
    series = {cid: sorted(s.items()) for cid, s in src.states.items()}

    def state_at(cid: str, d: str) -> str | None:
        got = None
        for day_, st in series.get(cid, ()):
            if day_ <= d:
                got = st
        return got if got is not None else (series[cid][0][1] if series.get(cid) else None)

    end = date.fromisoformat(src.as_of)
    dates = [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    ids = sorted(c for c in src.days if any(state_at(c, d) in PERFORMANCE for d in dates))
    window = int(k["campaign_window_days"])
    grid, runs = [], {}
    for z in GRID:                                              # the evidence bar is calibrated, not guessed: the replay at each bar on the same days
        q = allocation.Params(**{**p.__dict__, "evidence_z": z})
        runs[z] = _run(ids, src.days, state_at, dates, q, window, True)
        s = _summary(runs[z])
        grid.append({"evidence_z": z, "moves": s["moves"], "fast_moves": s["fast_moves"], "flips": s["flips"],
                     "flip_share": round(s["flips"] / s["moves"], 3) if s["moves"] else None})
    chosen = calibrated_z(grid, k)
    base = float(k["allocation_evidence_z"])
    z_used, source = (chosen, "calibrated") if chosen is not None else (base, "base")
    p = allocation.Params(**{**p.__dict__, "evidence_z": z_used})
    main = runs[z_used] if z_used in runs else _run(ids, src.days, state_at, dates, p, window, True)
    plain = _run(ids, src.days, state_at, dates, p, window, False)
    rows = []
    for cid, arm in main["arms"].items():
        path = main["path"][cid]
        spend_start = sum(src.days[cid].get((date.fromisoformat(dates[0]) - timedelta(days=i)).isoformat(), (0.0,))[0] for i in range(1, 8)) / 7
        spend_end = sum(src.days[cid].get((end - timedelta(days=i)).isoformat(), (0.0,))[0] for i in range(7)) / 7
        rows.append({"campaign": cid, "name": (src.campaigns.get(cid) or {}).get("name"), "start": round(main["start"][cid], 2), "end": round(arm.budget, 2),
                     "actual_spend_start": round(spend_start, 2), "actual_spend_end": round(spend_end, 2),
                     "path": path[::7] + ([path[-1]] if (len(path) - 1) % 7 else []), "moves": arm.moves, "stats": _stats(arm),
                     "states": {d: state_at(cid, d) for d in (dates[0], dates[-1])}})
    rows.sort(key=lambda r: (-r["start"], r["campaign"]))
    warnings = list(src.warnings)
    warnings += [msg("campaign_thresholds_draft", "the campaign_* thresholds are drafts the owner has not confirmed yet: read the states as a proposal, not a verdict",
                     names=sorted(n for n in k if n.startswith("campaign_"))),
                 msg("allocate_replay_only", "a replay: it shows what the rule does, not what the moves would have earned (the data has no counterfactual)")]
    if propose:
        warnings.append(msg("allocate_proposal_draft", "a proposal, not an instruction: the allocation_* thresholds are drafts the owner has not confirmed, and the "
                            "evidence is a day-to-day relationship, not the effect of a budget change"))
    out = {"as_of": src.as_of, "currency": src.currency, "days": days,
           "params": {"step": p.step, "fast_step": p.fast_step, "fast_days": p.fast_days, "cooldown_days": p.cooldown_days, "min_days": p.min_days,
                      "evidence_z": {"value": p.evidence_z, "source": source, "base": base, "grid": grid}, "elasticity": [p.e_min, p.e_max], "prior_sd": p.prior_sd},
           "campaigns": rows, "summary": _summary(main), "without_acceleration": {"summary": _summary(plain)}, **coded("warnings", warnings)}
    if propose:
        out["proposal"] = _propose(main, src, src.days, state_at, end, len(dates), p, window, int(k["allocation_follow_days"]))
    return out
