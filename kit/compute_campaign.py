"""The campaign document: what a pack's tables say of every campaign, run through `kit.lifecycle`, as one `--json` document. No database, no
file, no platform: the pack reads its own tables into a `Source` (below) and the pack's verb prints what `compute()` returns.

    {as_of, market, currency, window {from, to, days}, params, kinds {source, n}, hold_weeks,
     campaigns [{campaign, name, type, kind, status, state, raw_state, reason, pending, first_spend, last_spend, budget {daily, basis},
                 window {spend, revenue, roas, conversions, days}, previous {...}, use_share, benchmark {roas, basis, n},
                 creatives {<state>: count}, ctr, proposals [{action, evidence, message_code, ...}]}],
     summary {<state>: count}, warnings, warning_codes}

The pack adds its own `meta` (the sources it read and how fresh they are). A proposal is a sentence with its evidence, never a write.

  * `Source`: what the pack's adapter hands over, for one reading day. `check()` refuses a missing or ill-shaped part with
    `compute_input_invalid`, naming the part, so a pack's adapter finds its own mistake and not a `KeyError` deep in the rules;
  * `read()`: one reading of every campaign on the last complete day, the raw state before the hold;
  * `timeline()`: the readings at each of the last weekly checkpoints, each with its state after `lifecycle.hold` (a state among earning, steady,
    declining, fatigued and unjudged changes only when the new reading has held for `campaign_hold_weeks` readings);
  * `compute()`: the last reading of the timeline, filtered by state or campaign, in the order of `lifecycle.STATES`.

A campaign's kind is read from its name by the pack's own registry (a list of `(pattern, kind)`, the first pattern that matches wins; none matches =
unclassified): a kind is never a rule about one platform. The benchmark a campaign is compared with is the return of the judged campaigns of its kind
(two or more), else of the account's other judged campaigns.

The thresholds are `k`, the dict `Thresholds.load()` returns: the `campaign_*` rows of `constants.d/lifecycle.tsv` and the two creative ones the
creative engine owns. Words that name a platform stay in the pack's adapter; the budget of a campaign that has none of its own is the sum of its ad
groups' (`basis` says which).

From the video-ads skill pack (`scripts/compute_campaign.py`; its cases are this module's test, over a synthetic fixture).

Test: kit/tests/test_compute_campaign.py.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from kit import lifecycle
from kit.contract import SkillPackError
from kit.messages import Msg, coded, msg

CTR_WEEKS = 26                  # the weekly click-through history the fatigue rule reads: half a year
UNCLASSIFIED = "unclassified"
PARAM_FIELDS = ("window_days", "learning_days", "judge_spend", "min_conversions", "earn_margin", "use_share", "decline_drop", "issue_share",
                "end_idle_days", "budget_step", "hold_weeks", "fatigue_good_pct", "fatigue_bad_pct", "fatigue_ctr_drop", "fatigue_min_weeks",
                "fatigue_min_impressions", "fatigue_prior_impressions")
CAMPAIGN_KEYS = ("name", "type", "status", "budget", "group_budget")


@dataclass
class Source:
    """One reading day of a pack's tables. Days are ISO dates, money in the account's currency.

    as_of            the last complete day (None: the tables hold none yet)
    currency         the account's currency, or None
    campaigns        {campaign id: {name, type, status, budget, group_budget}}: `status` is `lifecycle.ACTIVE`, `DISAPPROVED`, another word or None
                     (the export never said); `budget` the campaign's own daily budget or None; `group_budget` the sum of its live ad groups'
    days             {campaign id: {day: (spend, revenue, conversions, impressions, clicks)}}, the days it spent
    ads              {ad id: (campaign id, has_issue)}: `has_issue` is the pack's reading of the platform's status (limited or disapproved)
    ad_spend         {ad id: {day: spend}}
    creative_state   {ad id: the creative's state} (`kit.creative_life`), the ads with none left out
    doubt_spend      the creatives' doubt line (`creative_life.Params.doubt_spend`), None when unknown: then no campaign is judged
    kinds            [(regular expression, kind)] in the order the first match wins; [] = none
    kinds_file       what the pack calls that registry (for the warning and `kinds.source`)
    warnings         coded messages the pack's own reading raised, kept in the document
    """
    as_of: str | None
    currency: str | None
    campaigns: dict
    days: dict
    ads: dict
    ad_spend: dict
    creative_state: dict
    doubt_spend: float | None
    kinds: list = field(default_factory=list)
    kinds_file: str = "campaign kinds"
    warnings: list = field(default_factory=list)


ReadAt = Callable[[str | None], Source]


def _bad(part: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("compute_input_invalid", f"the pack's tables give {part} {problem}", part=part, problem=problem))


def check(src: Source) -> None:
    """Refuse a `Source` the rules cannot read, naming the part (`compute_input_invalid`)."""
    if src.as_of is not None:
        try:
            date.fromisoformat(src.as_of)
        except (TypeError, ValueError):
            raise _bad("as_of", f"{src.as_of!r}, which is not a day (YYYY-MM-DD)") from None
    for cid, c in src.campaigns.items():
        absent = [x for x in CAMPAIGN_KEYS if not isinstance(c, dict) or x not in c]
        if absent:
            raise _bad(f"campaigns[{cid}]", f"without {', '.join(absent)}")
    for cid, ds in src.days.items():
        for day, x in ds.items():
            if not isinstance(x, (tuple, list)) or len(x) != 5:
                raise _bad(f"days[{cid}][{day}]", "that is not (spend, revenue, conversions, impressions, clicks)")
    for ad, v in src.ads.items():
        if not isinstance(v, (tuple, list)) or len(v) != 2:
            raise _bad(f"ads[{ad}]", "that is not (campaign id, has_issue)")
    for kind in src.kinds:
        if not isinstance(kind, (tuple, list)) or len(kind) != 2:
            raise _bad("kinds", "that are not (pattern, kind) pairs")


def compile_kinds(kinds: list, file: str) -> list[tuple[re.Pattern, str]]:
    out = []
    for pattern, kind in kinds:
        try:
            out.append((re.compile(pattern, re.I), kind))
        except re.error as e:
            raise SkillPackError(msg("campaign_kind_pattern_invalid", f"{file}: {pattern!r} is not a regular expression ({e})",
                                     file=file, pattern=pattern)) from None
    return out


def kind_of(name: str | None, kinds: list[tuple[re.Pattern, str]]) -> str:
    for rx, kind in kinds:
        if name and rx.search(name):
            return kind
    return UNCLASSIFIED


def params(k: dict, doubt_spend: float | None) -> lifecycle.Params:
    """The rules' parameters from the thresholds in effect; the judging spend is a multiple of the creatives' doubt line (0 when unknown)."""
    return lifecycle.Params(
        window_days=int(k["campaign_window_days"]), learning_days=int(k["campaign_learning_days"]),
        judge_spend=(doubt_spend or 0.0) * k["campaign_judge_spend_multiple"], min_conversions=k["campaign_min_conversions"],
        earn_margin=k["campaign_earn_margin"], use_share=k["campaign_use_share"], decline_drop=k["campaign_decline_drop"],
        issue_share=k["campaign_issue_share"], end_idle_days=int(k["campaign_end_idle_days"]), budget_step=k["campaign_budget_step"],
        hold_weeks=int(k["campaign_hold_weeks"]), fatigue_good_pct=k["campaign_fatigue_good_pct"], fatigue_bad_pct=k["campaign_fatigue_bad_pct"],
        fatigue_ctr_drop=k["campaign_fatigue_ctr_drop"], fatigue_min_weeks=int(k["campaign_fatigue_min_weeks"]),
        fatigue_min_impressions=k["campaign_fatigue_min_impressions"], fatigue_prior_impressions=k["campaign_fatigue_prior_impressions"])


def proposals(c: dict, v: lifecycle.Verdict, p: lifecycle.Params) -> list[dict]:
    """What a person could do, each with its evidence (never a write)."""
    roas, bench = v.window["roas"], v.benchmark_roas
    out = []

    def add(action: str, m: Msg) -> None:
        out.append({"action": action, "evidence": str(m), **coded("message", m)})
    declining, n = c["creatives"].get("declining", 0), sum(c["creatives"].values())
    if v.state == "earning" and v.reason == "above_benchmark":
        add("raise_budget", msg("campaign_raise_budget",
                                f"raise its budget by a step of {p.budget_step:.0%}: the last {p.window_days} days returned {roas:.2f} "
                                f"against {bench:.2f}" + (f", and it spent {v.use_share:.0%} of its budget" if v.use_share is not None else ""),
                                step=round(p.budget_step, 2), roas=round(roas, 2), benchmark=round(bench, 2)))
    elif v.state == "earning":
        add("ask_creatives", msg("campaign_ask_creatives",
                                 f"it returned {roas:.2f} against {bench:.2f} but spent only {v.use_share:.0%} of its budget: its "
                                 "creatives are the limit, not the money; ask for more",
                                 roas=round(roas, 2), benchmark=round(bench, 2), use=round(v.use_share, 2)))
    elif v.state == "fatigued":
        f = v.ctr or {}
        add("rest_creatives", msg("campaign_rest_creatives",
                                  f"its creatives are wearing out: its relative click-through rate is {f.get('now', 0):.2f} against a peak of "
                                  f"{f.get('peak', 0):.2f}; rest its declining creatives ({declining} of {n}) and ask for new ones",
                                  declining=declining, now=round(f.get("now", 0), 2), peak=round(f.get("peak", 0), 2)))
    elif v.state == "declining":
        add("check_account", msg("campaign_check_account",
                                 f"its return fell from {v.previous['roas']:.2f} to {roas:.2f} with no sign that the creatives wore out: look at the "
                                 "budget, the season and the landing page before asking for new creatives",
                                 roas=round(roas, 2), before=round(v.previous["roas"], 2)))
    elif v.state == "lagging":
        add("check_account", msg("campaign_lagging", f"its return is {roas:.2f} against {bench:.2f} and it did not fall: it never was good or settled low; look at "
                                 "the budget and the audience before asking for creatives; the allocation may lower its budget",
                                 roas=round(roas, 2), benchmark=round(bench, 2)))
    elif v.state == "blocked":
        add("fix_issue", msg("campaign_fix_issue", f"{v.reason.replace('_', ' ')}: name the ads with issues to the person who can fix "
                             "them", reason=v.reason))
    elif v.state == "steady" and c["creatives"].get("mature"):
        add("add_creative", msg("campaign_add_creative", f"{c['creatives']['mature']} mature creative(s) in it: add a new one beside "
                                "them", mature=c["creatives"]["mature"]))
    return out


def _round(d: dict) -> dict:
    return {k: (round(x, 2) if isinstance(x, float) else x) for k, x in d.items()}


def read(src: Source, k: dict, *, market: str) -> dict:
    """One reading of every campaign on the last complete day: the raw state, before the hold."""
    check(src)
    as_of = src.as_of
    if as_of is None:
        raise SkillPackError(msg("campaign_no_data", f"no complete day of {market}'s data: nothing to judge", market=market))
    p = params(k, src.doubt_spend)
    kinds = compile_kinds(src.kinds, src.kinds_file)
    warnings = list(src.warnings)
    if not kinds:
        warnings.append(msg("campaign_kinds_missing", f"{src.kinds_file} is not in the data folder: every campaign is unclassified and is "
                            "compared with the account's return", file=src.kinds_file))
    warnings.append(msg("campaign_thresholds_draft", "the campaign_* thresholds are drafts the owner has not confirmed yet: read the states as a "
                        "proposal, not a verdict", names=sorted(n for n in k if n.startswith("campaign_"))))
    by_camp: dict[str, Counter] = defaultdict(Counter)
    window_start = (date.fromisoformat(as_of) - timedelta(days=p.window_days - 1)).isoformat()
    last7 = (date.fromisoformat(as_of) - timedelta(days=6)).isoformat()
    spend7: dict[str, float] = defaultdict(float)
    issue7: dict[str, float] = defaultdict(float)
    for ad, (camp, has_issue) in src.ads.items():
        st = src.creative_state.get(ad)
        if st:
            by_camp[camp][st] += 1
        for d, s in src.ad_spend.get(ad, {}).items():
            if last7 <= d <= as_of:
                spend7[camp] += s
                if has_issue:
                    issue7[camp] += s
    ids = sorted(set(src.campaigns) | set(src.days))
    per = {cid: lifecycle.weekly_clicks(src.days.get(cid, {}), as_of, CTR_WEEKS) for cid in ids}
    account_weeks = [(sum(per[c][w][0] for c in ids), sum(per[c][w][1] for c in ids)) for w in range(CTR_WEEKS)]
    camps = {}
    for cid in ids:
        st = src.campaigns.get(cid, {})
        budget, basis = (st.get("budget") or 0.0), "campaign"
        if budget <= 0:
            budget, basis = (st.get("group_budget") or 0.0), "ad groups"
        if budget <= 0:
            budget, basis = None, "unknown"
        camps[cid] = lifecycle.Campaign(
            cid, st.get("status"), src.days.get(cid, {}), budget,
            issue_share=(issue7[cid] / spend7[cid]) if spend7.get(cid) else 0.0, basis=basis, ctr=per[cid], ctr_account=account_weeks)
    kind = {cid: kind_of(src.campaigns.get(cid, {}).get("name"), kinds) for cid in ids}
    win = {cid: lifecycle.windows(c.days, as_of, p)[0] for cid, c in camps.items()}

    def benchmark(cid: str) -> tuple[float | None, str, int]:
        judged = [o for o in ids if o != cid and win[o]["spend"] >= p.judge_spend and win[o]["conversions"] >= p.min_conversions
                  and win[o]["roas"] is not None]
        same = [o for o in judged if kind[cid] != UNCLASSIFIED and kind[o] == kind[cid]]
        pool, label = (same, f"kind {kind[cid]}") if len(same) >= 2 else (judged, "the account's other campaigns")
        spend = sum(win[o]["spend"] for o in pool)
        return ((sum(win[o]["revenue"] for o in pool) / spend) if spend > 0 else None), label, len(pool)

    rows = []
    for cid in ids:
        c = camps[cid]
        bench, bbasis, bn = benchmark(cid)
        v = lifecycle.judge(c, as_of, p, bench)
        spent = sorted(d for d, x in c.days.items() if x[0] > 0)
        info = src.campaigns.get(cid, {})
        row = {"campaign": cid, "name": info.get("name"), "type": info.get("type"), "kind": kind[cid], "status": c.status, "state": v.state,
               "reason": v.reason, "first_spend": spent[0] if spent else None, "last_spend": spent[-1] if spent else None,
               "budget": {"daily": c.budget, "basis": c.basis}, "window": _round(v.window), "previous": _round(v.previous),
               "use_share": None if v.use_share is None else round(v.use_share, 4),
               "benchmark": {"roas": None if bench is None else round(bench, 2), "basis": bbasis, "n": bn},
               "creatives": dict(by_camp.get(cid, {})), "ctr": v.ctr}
        row["proposals"] = proposals(row, v, p)
        rows.append(row)
    return {"as_of": as_of, "market": market, "currency": src.currency,
            "window": {"from": window_start, "to": as_of, "days": p.window_days},
            "params": {f: getattr(p, f) for f in PARAM_FIELDS}, "kinds": {"source": src.kinds_file if kinds else None, "n": len(kinds)},
            "campaigns": rows, "summary": dict(Counter(r["state"] for r in rows)), "hold_weeks": p.hold_weeks, **coded("warnings", warnings)}


def checkpoints(as_of: str, weeks: int) -> list[str]:
    """The days a state is read on, oldest first: `weeks` weekly steps back from the last complete day, and that day."""
    end = date.fromisoformat(as_of)
    return [(end - timedelta(days=7 * i)).isoformat() for i in range(weeks, -1, -1)]


def timeline(read_at: ReadAt, k: dict, *, market: str, until: str | None, weeks: int) -> list[dict]:
    """The readings at each of the last `weeks` weekly checkpoints (and the hold's history before them), each with its state after the hold:
    [{day, doc}] oldest first, every doc a `read()` whose campaigns carry `state` (held), `raw_state` and `pending`. `read_at(day)` is the pack's
    adapter: the `Source` of the tables read no further than `day` (None = no limit). A checkpoint with no complete day gives `doc` None: no
    reading, never a guess; the last one is refused (`campaign_no_data`)."""
    last = read(read_at(until), k, market=market)
    hold = last["hold_weeks"]
    docs = []
    for d in checkpoints(last["as_of"], weeks + max(hold, 1) - 1):
        if d == last["as_of"]:
            docs.append((d, last))
            continue
        src = read_at(d)
        docs.append((d, read(src, k, market=market) if src.as_of is not None else None))
    held: dict[str, list] = {}
    out = []
    for d, doc in docs:
        if doc is None:
            out.append({"day": d, "doc": None})
            continue
        for r in doc["campaigns"]:
            h = held.setdefault(r["campaign"], [])
            h.append((r["state"], r["reason"]))
            state, reason, pending = lifecycle.hold([s for s, _ in h], [x for _, x in h], hold)
            r["raw_state"], r["state"], r["reason"], r["pending"] = r["state"], state, reason, pending
            if pending:
                r["proposals"] = []
        doc["summary"] = dict(Counter(r["state"] for r in doc["campaigns"]))
        out.append({"day": d, "doc": doc})
    return out[-(weeks + 1):]


def compute(read_at: ReadAt, k: dict, *, market: str, until: str | None = None, state: str | None = None, campaign: str | None = None) -> dict:
    """The campaigns as the last reading says, each state held, optionally only one state or one campaign (its id or exact name)."""
    doc = timeline(read_at, k, market=market, until=until, weeks=0)[-1]["doc"]
    rows = [r for r in doc["campaigns"] if not (state and r["state"] != state) and not (campaign and campaign not in (r["campaign"], r["name"]))]
    order = {s: i for i, s in enumerate(lifecycle.STATES)}
    rows.sort(key=lambda r: (order[r["state"]], -r["window"]["spend"], r["campaign"]))
    return {**doc, "campaigns": rows, "summary": dict(Counter(r["state"] for r in rows))}
