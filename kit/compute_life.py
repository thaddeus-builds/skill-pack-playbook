"""The life document: the state of every creative, its reason, what it waits for and its wallet, as one `--json` document. No database, no file, no
clock, no platform: the pack reads its own tables into a `Source` (below) and prints what `compute()` returns.

    {as_of, counts {creatives, days}, params {name: {value, source, n}}, rows [{creative, label, state, wallet, group, accounts, entities, since, reason,
     moves [{date, from, to, reason, read, message, message_code}], waiting, totals, signal, blocked_now, review_due, last_day, spend7, conv7}],
     summary {<state>: count}, by_entity {<entity>: {<state>: count}}, wallets {explore, perform, other: spend of the last 7 days}, window_days,
     warnings, warning_codes}

The pack adds its own `meta` (the sources it read and how fresh they are). The rules are `kit.creative_life`'s: seven states, moved a day at a time over a
creative's complete, unblocked days. Every run replays everything from the days, so the same days say the same thing whatever day it runs.

  * `Source`: what the pack's adapter hands over; `check()` refuses a missing or ill-shaped part with `compute_input_invalid`, naming it;
  * `derive()`: the thresholds that are rules over the account's own history (the reach a creative needs to have found its people, the doubt line, the
    weak-signal cut), each with a cold start when the history is short, and each saying which it used (`source`: `rule`, `cold_start`, `unknown`,
    `history_insufficient`, `constant`). A short history is a coded warning, never a guess; a doubt line that cannot be derived switches the
    spend-without-conversion check off;
  * `compute()`: the replay of every creative, optionally only one state, one creative, one entity or one account.

One document reads one set of creatives and derives its thresholds from them: a pack that reads two sources (two platforms' tables) calls it once for
each, as their histories differ. A row's `spend7` and `conv7` (the last 7 counted days, not rounded: they are fed forward) are what `kit.compute_pacing` reads to size the performance wallet.

From the video-ads skill pack (`scripts/compute_life.py`, `_lib/life_data.py` `derive` and `pad_off_tail`, `_lib/life_view.py`; its cases are this
module's test, over a synthetic fixture).

Test: kit/tests/test_compute_life.py.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from kit import creative_life as life
from kit.contract import SkillPackError
from kit.messages import coded, msg

INF = float("inf")
ORDER = ("mature", "declining", "doubt", "learning", "testing", "parked", "ended")
CREATIVE_KEYS = ("days",)


@dataclass
class Source:
    """One reading of a pack's tables. Days are ISO dates, money in the account's currency.

    creatives   {creative id: {days, label, group, accounts, entities, off, overrides}}: `days` the creative's `creative_life.Day`s, oldest first, one
                per date (a day the platform did not deliver on is simply absent); the rest are optional: `label` how the pack names it (default: the
                id), `group` its ad group's id (echoed, for `kit.compute_pacing`), `accounts` and `entities` where it ran (echoed, for the filters and
                `by_entity`), `off` whether the platform says it no longer runs (its days after the last delivery up to `until` are blocked: off),
                `overrides` a person's dated word [(date, state)]
    until       the last day to read (the pack has already cut its days there), or None: each creative's own last day
    warnings    coded messages the pack's own reading raised, kept in the document
    read_cost   a function `window (the last 7 counted `Day`s) -> (cost, low, high) | None`: the 7-day cost per conversion of a mature creative's window read on what its unsettled
                days will come to, as the pack builds it from `kit.maturity` (this module cannot import it: another pack), or None: every window as seen (`kit.creative_life`)
    """
    creatives: dict
    until: str | None = None
    warnings: list = field(default_factory=list)
    read_cost: object = None


def _bad(part: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("compute_input_invalid", f"the pack's tables give {part} {problem}", part=part, problem=problem))


def _day(part: str, value) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise _bad(part, f"{value!r}, which is not a day (YYYY-MM-DD)") from None


def check(src: Source) -> None:
    """Refuse a `Source` the rules cannot read, naming the part (`compute_input_invalid`)."""
    if src.read_cost is not None and not callable(src.read_cost):
        raise _bad("read_cost", f"{src.read_cost!r}, which is not a function or None")
    if src.until is not None:
        _day("until", src.until)
    for cid, c in src.creatives.items():
        absent = [x for x in CREATIVE_KEYS if not isinstance(c, dict) or x not in c]
        if absent:
            raise _bad(f"creatives[{cid}]", f"without {', '.join(absent)}")
        part, seen = f"creatives[{cid}].days", None
        if not isinstance(c["days"], (list, tuple)):
            raise _bad(part, "that is not a list of days")
        for d in c["days"]:
            if not isinstance(d, life.Day):
                raise _bad(part, f"{d!r}, which is not a kit.creative_life.Day")
            _day(part, d.date)
            if seen is not None and d.date <= seen:
                raise _bad(part, f"that are not oldest first, one per date ({d.date} after {seen})")
            seen = d.date
        for date_, state in c.get("overrides", ()):
            _day(f"creatives[{cid}].overrides", date_)
            if state not in life.STATES:
                raise _bad(f"creatives[{cid}].overrides", f"{state!r}, which is not a state")


def _quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def derive(creatives: dict[str, list[life.Day]], k: dict, label: str = "") -> tuple[life.Params, dict, list]:
    """(Params, {threshold: {value, source, n}}, warnings): the thresholds of the account's history. `k` holds the thresholds in effect (the `life_*`
    rows)."""
    need = int(k["life_history_min_creatives"])
    prov: dict[str, dict] = {}
    warnings: list = []
    counted = {c: [d for d in days if d.complete] for c, days in creatives.items()}

    first_conv_impr = []
    for days in counted.values():
        cum_i = cum_c = 0.0
        for d in days:
            cum_i += d.impressions
            cum_c += d.conversions
            if cum_c >= 1:
                first_conv_impr.append(cum_i)
                break
    if len(first_conv_impr) >= need:
        reach = min(max(_quantile(first_conv_impr, 0.75), k["life_reach_min"]), k["life_reach_max"])
        prov["reach_impressions"] = {"value": reach, "source": "rule", "n": len(first_conv_impr)}
    else:
        reach = k["life_reach_cold"]
        prov["reach_impressions"] = {"value": reach, "source": "cold_start", "n": len(first_conv_impr)}
        warnings.append(msg("life_history_insufficient", f"{label}reach_impressions: {len(first_conv_impr)} creatives that converted, {need} needed: "
                            f"the cold start {reach:g} is used", name=f"{label}reach_impressions", have=len(first_conv_impr), need=need))

    costs = []
    for days in counted.values():
        conv = sum(d.conversions for d in days)
        if conv >= 5:
            costs.append(sum(d.spend for d in days) / conv)
    if len(costs) >= max(3, need // 2):
        doubt = k["life_doubt_multiple"] * _quantile(costs, 0.5)
        prov["doubt_spend"] = {"value": doubt, "source": "rule", "n": len(costs)}
    else:
        doubt = INF
        prov["doubt_spend"] = {"value": None, "source": "unknown", "n": len(costs)}
        warnings.append(msg("life_doubt_unknown", f"{label}doubt_spend: {len(costs)} creatives with 5 or more conversions, {max(3, need // 2)} needed: "
                            "the spend-without-conversion check is off (the slow check still runs)", have=len(costs), need=max(3, need // 2)))

    sigs = [life.signal(days) for days in counted.values() if sum(d.impressions for d in days) >= reach]
    sigs = [s for s in sigs if s is not None]
    if len(sigs) >= need:
        weak = _quantile(sigs, k["life_weak_percentile"] / 100)
        prov["weak_signal"] = {"value": weak, "source": "rule", "n": len(sigs)}
    else:
        weak = None
        prov["weak_signal"] = {"value": None, "source": "history_insufficient", "n": len(sigs)}
    p = life.Params(reach_impressions=reach, reach_floor=reach * k["life_reach_floor_share"], reach_days=int(k["life_reach_days"]),
                    learning_conversions=k["life_learning_conversions"], doubt_spend=doubt, doubt_extension=k["life_doubt_extension"],
                    learning_max_days=int(k["life_learning_max_days"]), weak_signal=weak, decline_rise=k["life_decline_rise"],
                    decline_drop=k["life_decline_drop"], decline_days=int(k["life_decline_days"]), recover_days=int(k["life_recover_days"]),
                    end_spend_share=k["life_end_spend_share"], end_idle_days=int(k["life_end_idle_days"]),
                    park_review_days=int(k["life_park_review_days"]), min_conversions_for_cost=k["life_min_conversions_for_cost"])
    for name in ("reach_floor", "reach_days", "learning_conversions", "doubt_extension", "learning_max_days", "decline_rise", "decline_drop",
                 "decline_days", "recover_days", "end_spend_share", "end_idle_days", "park_review_days"):
        prov.setdefault(name, {"value": getattr(p, name), "source": "constant", "n": None})
    return p, prov, warnings


def pad_off_tail(days: list[life.Day], off: bool, through: str) -> list[life.Day]:
    """The days after a switched-off creative's last delivery up to `through` are `blocked: off`: a blocked day stops every clock, so a creative the
    platform no longer runs does not age toward `ended` on days it could not have spent."""
    if not days or not off:
        return list(days)
    last, end = date.fromisoformat(days[-1].date), date.fromisoformat(through)
    return list(days) + [life.Day(date=(last + timedelta(days=i)).isoformat(), blocked="off") for i in range(1, (end - last).days + 1)]


def compute(src: Source, k: dict, *, state: str | None = None, creative: str | None = None, entity: str | None = None,
            account: str | None = None) -> dict:
    """The document for every creative of `src`, optionally only one `state`, one `creative` (its id or label), one `entity` or one `account`."""
    check(src)
    if state is not None and state not in life.STATES:
        raise _bad("state", f"{state!r}, which is not a state")
    warnings = list(src.warnings)
    if not src.creatives:
        warnings.append(msg("life_no_creatives", "no creative has a day to read"))
        p, prov = None, {}
    else:
        p, prov, derived = derive({cid: c["days"] for cid, c in src.creatives.items()}, k)
        warnings += derived
    rows = []
    for cid, c in src.creatives.items():
        label = c.get("label") or cid
        if creative and creative not in (cid, label):
            continue
        days = pad_off_tail(c["days"], bool(c.get("off")), src.until or c["days"][-1].date) if c["days"] else []
        lf = life.replay(days, p, list(c.get("overrides", ())), src.read_cost)
        if state and lf.state != state:
            continue
        accounts, entities = sorted(c.get("accounts", ())), sorted(c.get("entities", ()))
        if (entity and entity not in entities) or (account and account not in accounts):
            continue
        moves = [{"date": m.date, "from": m.frm, "to": m.to, "reason": m.reason, "read": m.read,
                  **coded("message", msg("life_move", f"{label}: {m.frm} -> {m.to} ({m.reason})", creative=label, frm=m.frm, to=m.to, reason=m.reason))}
                 for m in lf.moves]
        counted = [d for d in days if d.complete and not d.blocked]
        rows.append({"creative": cid, "label": label, "state": lf.state, "wallet": life.WALLET[lf.state], "group": c.get("group"),
                     "accounts": accounts, "entities": entities, "since": lf.since, "reason": lf.moves[-1].reason if lf.moves else None,
                     "moves": moves, "waiting": lf.waiting, "totals": lf.totals, "signal": life.signal(counted), "blocked_now": lf.blocked_now,
                     "review_due": lf.review_due, "last_day": counted[-1].date if counted else None,
                     "spend7": sum(d.spend for d in counted[-life.WINDOW:]), "conv7": sum(d.conversions for d in counted[-life.WINDOW:])})
    rows.sort(key=lambda r: (ORDER.index(r["state"]), -r["totals"].get("spend", 0), r["creative"]))
    wallets = {"explore": 0.0, "perform": 0.0, "other": 0.0}
    for r in rows:
        wallets[r["wallet"] or "other"] += r["spend7"]
    return {"as_of": max((r["last_day"] for r in rows if r["last_day"]), default=None),
            "counts": {"creatives": len(src.creatives), "days": sum(len(c["days"]) for c in src.creatives.values())},
            "params": prov, "rows": rows, "summary": dict(Counter(r["state"] for r in rows)),
            "by_entity": {e: dict(Counter(r["state"] for r in rows if e in r["entities"])) for e in sorted({e for r in rows for e in r["entities"]})},
            "wallets": {n: round(v, 2) for n, v in wallets.items()}, "window_days": life.WINDOW, **coded("warnings", warnings)}
