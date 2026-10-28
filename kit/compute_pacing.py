"""The pacing document: what the next day may spend and how that money divides between the performance and exploration wallets, as one `--json`
document. No database, no file, no clock, no platform: the pack reads its own tables into a `Source` (below) and prints what `compute()` returns.

    {month, inputs {spend {value, source}, result {value, source}}, last_day, plan {kit.pacing.plan's, or None}, wallets_now {explore, perform, other:
     the creatives' last 7 days' spend by the wallet that pays them}, efficiency {conversions_per_money, performance_creatives, conversions_7d, spend_7d},
     creative_wallets {creative id: the wallet that pays it, or None} (what `kit.compute_demand` reads), ad_groups {count, wallets, by_reason} (None when the pack gave no ad groups), warnings, warning_codes}

The pack adds its own `meta` (the sources it read and how fresh they are). Read-only: it proposes, a person changes a budget.

The month's money and result are a person's numbers: the pack reads them where it keeps them (a confirmed decision, a command line) and hands them over with
where they came from. The shape of a week comes from the account's own weekdays (flat until each weekday has `pacing_min_weeks` weeks; the event days of
`Source.event_days` are left out of them). The wallets: an ad group is judged on its own days (`kit.wallets`, the `adgroup_*` rows) and pays a creative from
its wallet only as far as the creative's own wallet allows (`wallets.pay`); a creative with no known group keeps the wallet of its own state. The efficiency
is the performance creatives' conversions per unit of money over their last 7 days, read only from `pacing_min_conversions` conversions.

From the video-ads skill pack (`scripts/compute_pacing.py`; its cases are this module's test, over a synthetic fixture).

Test: kit/tests/test_compute_pacing.py.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from kit import pacing, wallets
from kit.contract import SkillPackError
from kit.messages import coded, msg

WALLETS = ("perform", "explore")
CREATIVE_KEYS = ("wallet", "group", "spend7", "conv7")


@dataclass
class Source:
    """One planning run of a pack's tables. Days are ISO dates, money in the account's currency.

    month            YYYY-MM to plan, or None: the month of the day after the last complete day
    spend_target     the month's money, a person's number, or None (nothing is planned); `spend_source` says where it came from (`given`, `decision`, ...)
    result_target    the month's result (conversions), or None; `result_source` likewise
    day              the day to plan (a day of `month`), or None: the day after the last complete day
    daily_spend      {day: spend} of the account's complete, unblocked days; the last of them is the last complete day
    daily_conv       {day: conversions} of the same days
    creatives        {creative id: {wallet, group, spend7, conv7}}: `wallet` the wallet its own state pays from (`perform`, `explore`, or None for a
                     creative parked or ended), `group` its ad group's id or None, and its spend and conversions over its last 7 counted days
    groups           {ad group id: {days: {day: (spend, conversions)}, active}}: the ad groups of the creatives, `active` whether the platform says
                     they still deliver; {} = no ad group reading, and the creatives' own wallets pay
    event_days       {date} the account's event days (`kit.event_days`), or None
    warnings         coded messages the pack's own reading raised, kept in the document
    """
    daily_spend: dict
    daily_conv: dict
    creatives: dict
    month: str | None = None
    spend_target: float | None = None
    spend_source: str | None = None
    result_target: float | None = None
    result_source: str | None = None
    day: str | None = None
    groups: dict = field(default_factory=dict)
    event_days: set | None = None
    warnings: list = field(default_factory=list)


def _bad(part: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("compute_input_invalid", f"the pack's tables give {part} {problem}", part=part, problem=problem))


def _day(part: str, value) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise _bad(part, f"{value!r}, which is not a day (YYYY-MM-DD)") from None


def _number(part: str, value, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _bad(part, f"{value!r}, which is not a number")


def check(src: Source) -> None:
    """Refuse a `Source` the rules cannot read, naming the part (`compute_input_invalid`)."""
    if src.month is not None and not (isinstance(src.month, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", src.month)):
        raise _bad("month", f"{src.month!r}, which is not a month (YYYY-MM)")
    if src.day is not None:
        d = _day("day", src.day)
        if src.month is not None and d.strftime("%Y-%m") != src.month:
            raise _bad("day", f"{src.day}, which is not a day of {src.month}")
    _number("spend_target", src.spend_target, True)
    _number("result_target", src.result_target, True)
    for name in ("daily_spend", "daily_conv"):
        for day, v in getattr(src, name).items():
            _day(f"{name}[{day}]", day)
            _number(f"{name}[{day}]", v)
    for cid, c in src.creatives.items():
        absent = [x for x in CREATIVE_KEYS if not isinstance(c, dict) or x not in c]
        if absent:
            raise _bad(f"creatives[{cid}]", f"without {', '.join(absent)}")
        if c["wallet"] is not None and c["wallet"] not in WALLETS:
            raise _bad(f"creatives[{cid}].wallet", f"{c['wallet']!r}, which is not perform, explore or None")
        _number(f"creatives[{cid}].spend7", c["spend7"])
        _number(f"creatives[{cid}].conv7", c["conv7"])
        if c["group"] is not None and src.groups and c["group"] not in src.groups:
            raise _bad(f"creatives[{cid}].group", f"{c['group']!r}, which is not among the ad groups")
    for g, x in src.groups.items():
        if not isinstance(x, dict) or "days" not in x or "active" not in x:
            raise _bad(f"groups[{g}]", "without days and active")
        for day, v in x["days"].items():
            _day(f"groups[{g}].days[{day}]", day)
            if not isinstance(v, (tuple, list)) or len(v) != 2:
                raise _bad(f"groups[{g}].days[{day}]", "that is not (spend, conversions)")
    if src.event_days is not None and not all(isinstance(d, date) for d in src.event_days):
        raise _bad("event_days", "that are not all days (datetime.date)")


def group_params(k: dict) -> wallets.Params:
    """`kit.wallets`' parameters from the thresholds in effect (the `adgroup_*` rows)."""
    return wallets.Params(int(k["adgroup_learning_days"]), int(k["adgroup_window_days"]), k["adgroup_judge_spend"],
                          k["adgroup_min_conversions"], int(k["adgroup_end_idle_days"]))


def compute(src: Source, k: dict) -> dict:
    """The document for one planning run. `k` is the thresholds in effect (`Thresholds.load()`): the `pacing_*` and `adgroup_*` rows."""
    check(src)
    warnings = list(src.warnings)
    spend = {d: v for d, v in src.daily_spend.items()}
    conv = {d: src.daily_conv.get(d, 0.0) for d in spend}
    last = date.fromisoformat(max(spend)) if spend else None
    month = src.month or ((last + timedelta(days=1)).strftime("%Y-%m") if last else None)
    verdict: dict[str, tuple[str, str]] = {}
    if src.groups and last:
        p = group_params(k)
        verdict = {g: wallets.judge({d: (float(x[0]), float(x[1])) for d, x in v["days"].items()}, bool(v["active"]), last.isoformat(), p)
                   for g, v in src.groups.items()}
    paid = {}
    for cid, c in src.creatives.items():
        g = verdict.get(c["group"]) if c["group"] is not None else None
        paid[cid] = wallets.pay(c["wallet"], g[0]) if g is not None else c["wallet"]
    by_wallet = {"explore": 0.0, "perform": 0.0, "other": 0.0}
    for cid, c in src.creatives.items():
        by_wallet[paid[cid] or "other"] += c["spend7"]
    perform = [c for cid, c in src.creatives.items() if paid[cid] == "perform"]
    p_spend, p_conv = sum(c["spend7"] for c in perform), sum(c["conv7"] for c in perform)
    efficiency = p_conv / p_spend if p_spend > 0 and p_conv >= k["pacing_min_conversions"] else None
    doc = {"month": month,
           "inputs": {"spend": {"value": src.spend_target, "source": src.spend_source}, "result": {"value": src.result_target, "source": src.result_source}},
           "last_day": last.isoformat() if last else None, "plan": None,
           "wallets_now": {n: round(v, 2) for n, v in by_wallet.items()},
           "efficiency": {"conversions_per_money": efficiency, "performance_creatives": len(perform), "conversions_7d": p_conv, "spend_7d": round(p_spend, 2)},
           "creative_wallets": paid,
           "ad_groups": ({"count": len(verdict), "wallets": dict(Counter(w for w, _ in verdict.values())), "by_reason": dict(Counter(r for _, r in verdict.values()))}
                         if src.groups else None)}
    if last is None:
        warnings.append(msg("pacing_no_data", "no complete day to plan from", month=""))
    elif src.spend_target is None:
        warnings.append(msg("pacing_no_target", f"{month}: no spend target for the month: nothing to plan", month=month))
    else:
        day = date.fromisoformat(src.day) if src.day else None
        if day is not None and day.strftime("%Y-%m") != month:
            raise _bad("day", f"{src.day}, which is not a day of {month}")
        plan = pacing.plan(month, src.spend_target, src.result_target, spend, conv, last, efficiency, int(k["pacing_history_weeks"]),
                           int(k["pacing_min_weeks"]), day, explore_min_share=k["pacing_explore_min_share"],
                           explore_max_share=k["pacing_explore_max_share"], event_days=src.event_days)
        doc["plan"] = plan
        if "flat" in plan["flags"]:
            warnings.append(msg("pacing_flat", f"the weekday weights need {int(k['pacing_min_weeks'])} weeks of each weekday, {plan['weekday_weeks']} found: "
                                "every day weighs the same", have=plan["weekday_weeks"], need=int(k["pacing_min_weeks"])))
        if "no_performance" in plan["flags"] and src.result_target is not None:
            warnings.append(msg("pacing_no_performance", f"{month}: no performance creative has enough conversions to read an efficiency from: all of the money "
                                "is exploration", month=month))
        if "shortfall" in plan["flags"]:
            warnings.append(msg("pacing_shortfall", f"{month}: the result still to reach needs about {plan['perform_need_total']} at today's efficiency and "
                                f"{plan['money_left']} is left", month=month, need=plan["perform_need_total"], left=plan["money_left"]))
        if "result_met" in plan["flags"]:
            warnings.append(msg("pacing_result_met", f"{month}: the result target is already met", month=month))
        if plan["days_left"] == 0:
            warnings.append(msg("pacing_no_days_left", f"{month}: no day is left to plan", month=month))
    doc.update(coded("warnings", warnings))
    return doc
