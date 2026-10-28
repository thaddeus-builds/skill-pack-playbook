"""The portfolio document: all the creatives at once: how many in each state, how long the performance ones will keep earning, whether the month still reaches
its result if nothing new enters, and how many new creatives the account would need. No database, no file, no clock, no platform: the pack hands over the
creatives' days (the same `Source` the life document reads, wrapped) and the month's result, and prints what `compute()` returns. A warning and a proposal,
never a floor: the exploration wallet is whatever the pacing leaves.

    {month, as_of, horizon_days, states {state: {creatives, spend_7d, conversions_7d, mean_age_days}},
     performance [{creative, label, state, age_days, conv_7d, prev_conv_7d, ratio, daily_now, daily_factor}],
     projection {daily_now, half_life_days, by_week [{week, conversions}]},
     month_view {month, result_left, projected, gap, days_left} | None, history {cohort, matured, yield, median_days_to_mature},
     replenishment {gap, needed_mature, needed_testing, lead_days, enter_within_days, flags} | None, warnings, warning_codes}

The pack adds its own `meta`. The states, the wallets and the history of becoming mature are the life document's (`kit.compute_life`, run on the same creatives, whose
own warnings this document keeps); the trend, the projection and the replenishment are `kit.creative_portfolio`'s.

From the video-ads skill pack (`scripts/compute_portfolio.py`; its cases are this module's test, over a synthetic fixture).

Test: kit/tests/test_compute_portfolio.py.
"""

from __future__ import annotations

import calendar
import re
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from kit import compute_life, creative_portfolio as portfolio
from kit.contract import SkillPackError
from kit.messages import coded, msg


@dataclass
class Source:
    """One reading of a pack's tables.

    life            the creatives' days, as `kit.compute_life.Source` has them (and what that document needs to say their states)
    month           YYYY-MM to look at, or None: the month of the day after the last complete day (None when there is no day)
    result_target   the month's result (conversions), a person's number, or None: then there is no month view and no replenishment
    """
    life: compute_life.Source
    month: str | None = None
    result_target: float | None = None


def _bad(part: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("compute_input_invalid", f"the pack's tables give {part} {problem}", part=part, problem=problem))


def check(src: Source, horizon: int) -> None:
    """Refuse a `Source` the rules cannot read, naming the part (`compute_input_invalid`)."""
    compute_life.check(src.life)
    if src.month is not None and not (isinstance(src.month, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", src.month)):
        raise _bad("month", f"{src.month!r}, which is not a month (YYYY-MM)")
    if src.result_target is not None and (isinstance(src.result_target, bool) or not isinstance(src.result_target, (int, float))):
        raise _bad("result_target", f"{src.result_target!r}, which is not a number")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 7 <= horizon <= 365:
        raise _bad("horizon", f"{horizon!r}, which is not 7 to 365 days")


def month_days(month: str) -> list[date]:
    y, m = int(month[:4]), int(month[5:7])
    return [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]


def compute(src: Source, k: dict, *, horizon: int = 84) -> dict:
    """The document for the creatives of `src`, projected `horizon` days (7 to 365). `k` is the thresholds in effect: the `life_*` rows the life document reads."""
    check(src, horizon)
    life = compute_life.compute(src.life, k)
    rows = life["rows"]
    warnings = list(life["warnings"])
    counted = {cid: [d for d in c["days"] if d.complete and not d.blocked] for cid, c in src.life.creatives.items()}
    as_of = date.fromisoformat(life["as_of"]) if life["as_of"] else None
    states: dict[str, dict] = {}
    for r in rows:
        st = states.setdefault(r["state"], {"creatives": 0, "spend_7d": 0.0, "conversions_7d": 0.0, "_ages": []})
        last7 = counted[r["creative"]][-compute_life.life.WINDOW:]
        st["creatives"] += 1
        st["spend_7d"] += sum(d.spend for d in last7)
        st["conversions_7d"] += sum(d.conversions for d in last7)
        if as_of and r["since"]:
            st["_ages"].append((as_of - date.fromisoformat(r["since"])).days)
    for st in states.values():
        ages = st.pop("_ages")
        st["spend_7d"], st["conversions_7d"] = round(st["spend_7d"], 2), round(st["conversions_7d"], 2)
        st["mean_age_days"] = round(sum(ages) / len(ages), 1) if ages else None

    perf, items = [], []
    for r in rows:
        if r["wallet"] != "perform":
            continue
        t = portfolio.trend([d.conversions for d in counted[r["creative"]]])
        f = portfolio.daily_factor(t["ratio"])
        now = t["conv_7d"] / 7
        items.append((now, f))
        perf.append({"creative": r["creative"], "label": r["label"], "state": r["state"],
                     "age_days": (as_of - date.fromisoformat(r["since"])).days if as_of and r["since"] else None,
                     "conv_7d": round(t["conv_7d"], 2), "prev_conv_7d": round(t["prev_conv_7d"], 2),
                     "ratio": None if t["ratio"] is None else round(t["ratio"], 3), "daily_now": round(now, 3), "daily_factor": round(f, 4)})
    totals = portfolio.project(items, horizon)
    now_total = sum(d for d, _ in items)
    by_week = [{"week": i + 1, "conversions": round(sum(totals[i * 7:(i + 1) * 7]), 2)} for i in range((horizon + 6) // 7)]
    projection = {"daily_now": round(now_total, 3), "half_life_days": portfolio.half_life(totals, now_total), "by_week": by_week}
    if not items:
        warnings.append(msg("portfolio_no_performance", "no creative is in a performance state: nothing to project"))

    cohort_days = int(k["life_learning_max_days"])
    first_day, mature_day = {}, {}
    for r in rows:
        if counted[r["creative"]]:
            first_day[r["creative"]] = counted[r["creative"]][0].date
            mature_day[r["creative"]] = next((m["date"] for m in r["moves"] if m["to"] == "mature"), None)
    hist = portfolio.history(first_day, mature_day, as_of or date.min, cohort_days)
    month = src.month or ((as_of + timedelta(days=1)).strftime("%Y-%m") if as_of else None)
    month_view = replenishment = None
    if src.result_target is not None and as_of and month:
        left = [d for d in month_days(month) if d > as_of]
        conv_to_date = sum(d.conversions for ds in counted.values() for d in ds if d.date.startswith(month) and date.fromisoformat(d.date) <= as_of)
        result_left = max(0.0, src.result_target - conv_to_date)
        projected = sum(portfolio.project(items, len(left))) if left else 0.0
        gap = result_left - projected
        month_view = {"month": month, "result_left": round(result_left, 2), "projected": round(projected, 2), "gap": round(gap, 2), "days_left": len(left)}
        mature_daily = [sum(d.conversions for d in counted[r["creative"]][-compute_life.life.WINDOW:]) / 7 for r in rows if r["state"] == "mature"]
        need = int(k["life_history_min_creatives"])
        replenishment = portfolio.replenishment(gap, statistics.median(mature_daily) if mature_daily else None, len(left), hist, need)
        if gap > 0:
            warnings.append(msg("portfolio_gap", f"{month}: if nothing new enters, the performance creatives fall about {round(gap, 1)} conversions short of the "
                                "result target", month=month, gap=round(gap, 1)))
            if "history_insufficient" in replenishment["flags"]:
                warnings.append(msg("portfolio_history_insufficient", f"the account's history has {hist['cohort']} creative(s) old enough to read how many become "
                                    f"mature, {need} needed: no number of new creatives is given", have=hist["cohort"], need=need))
            if "too_late" in replenishment["flags"]:
                warnings.append(msg("portfolio_too_late", f"{month}: {len(left)} day(s) left is shorter than the time a new creative takes to become mature: new "
                                    "creatives cannot close the gap this month", month=month, days_left=len(left)))
    return {"month": month, "as_of": as_of.isoformat() if as_of else None, "horizon_days": horizon, "states": states, "performance": perf,
            "projection": projection, "month_view": month_view, "history": {**hist, "yield": None if hist["yield"] is None else round(hist["yield"], 3)},
            "replenishment": replenishment, **coded("warnings", warnings)}
