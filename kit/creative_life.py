"""The life of one creative (a campaign's is `kit.lifecycle`): its state, moved forward a day at a time by rule.

The rules alone. This module reads no database and names no platform, market or currency: the pack builds the days and the thresholds, `replay()` walks them. Every number a rule reads is a field of `Params`; nothing is a literal here.

    testing  -> learning   impressions reach `reach_impressions`, or it has a conversion (it found people)
             -> parked     `reach_days` delivery days and still under `reach_floor` impressions (low_reach)
    learning -> mature     `learning_conversions` conversions, or the platform says the learning period is over
             -> doubt      it spent `doubt_spend` with no conversion (no_conversion), or `learning_max_days`
                           delivery days in learning (slow)
    doubt    -> learning   a conversion within the extension (`doubt_extension` x `doubt_spend` more)
             -> ended      the extension spent, none, and its signal is under `weak_signal` (weak_creative)
             -> parked     the extension spent, none (no_conversion)
    mature   -> declining  `decline_days` days in a row of a 7-day cost per conversion `decline_rise` over its best, or a
                           7-day spend `decline_drop` under its peak
    declining-> mature     `recover_days` days in a row without those signs
             -> ended      the 7-day spend under `end_spend_share` of its peak, or `end_idle_days` days without delivery
    testing, learning, doubt -> parked (stopped_unjudged)  switched off for `end_idle_days` days
    parked   -> testing    only a person's override; `park_review_due` says when to look at it again

A day counts only when it is complete and not blocked: a blocked day stops every clock (it is not counted, not judged).
A creative is ended only from a faded mature one or from a doubt with the evidence floor met. An override (a person's
word, dated) sets the state on its day and the rules go on from it the next day.

From the video-ads skill pack (`life`).

Test: kit/tests/test_creative_life.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STATES = ("testing", "learning", "doubt", "mature", "declining", "parked", "ended")
WALLET = {"testing": "explore", "learning": "explore", "doubt": "explore", "mature": "perform", "declining": "perform",
          "parked": None, "ended": None}
WINDOW = 7                      # the days a "recent" read covers


@dataclass(frozen=True)
class Day:
    date: str                   # YYYY-MM-DD, the platform's day
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    conversions: float = 0.0    # the client's conversion event
    plays: int | None = None    # optional: the hook is plays_3s / plays
    plays_3s: int | None = None
    complete: bool = True       # exported after the day ended
    blocked: str | None = None  # a reason the creative could not run: review, off, budget_cap
    platform_learning_over: bool | None = None   # the platform's own flag, when it gives one


@dataclass(frozen=True)
class Params:
    reach_impressions: float
    reach_floor: float
    reach_days: int
    learning_conversions: float
    doubt_spend: float
    doubt_extension: float
    learning_max_days: int
    weak_signal: float | None   # the account's cut under which the hook (else the click rate) is weak; None: not read
    decline_rise: float
    decline_drop: float
    decline_days: int
    recover_days: int
    end_spend_share: float
    end_idle_days: int
    park_review_days: int
    min_conversions_for_cost: float = 3   # a 7-day cost per conversion is read from this many conversions up


@dataclass
class Move:
    date: str
    frm: str
    to: str
    reason: str
    read: dict


@dataclass
class Life:
    state: str = "testing"
    since: str | None = None
    moves: list[Move] = field(default_factory=list)
    waiting: dict = field(default_factory=dict)      # what the current state waits for: {name: [have, need]}
    blocked_now: str | None = None
    review_due: str | None = None
    days_counted: int = 0
    totals: dict = field(default_factory=dict)


def signal(days: list[Day]) -> float | None:
    """The hook (3-second plays over plays) when the days carry plays, else the click rate; None with neither."""
    plays = sum(d.plays or 0 for d in days if d.plays is not None)
    if plays > 0:
        return sum(d.plays_3s or 0 for d in days if d.plays is not None) / plays
    imp = sum(d.impressions for d in days)
    return sum(d.clicks for d in days) / imp if imp else None


def _recent(counted: list[Day]) -> list[Day]:
    return counted[-WINDOW:]


def _cost(window: list[Day], minimum: float) -> float | None:
    conv = sum(d.conversions for d in window)
    return sum(d.spend for d in window) / conv if conv >= minimum else None


def replay(days: list[Day], p: Params, overrides: list[tuple[str, str]] = ()) -> Life:
    """Walk `days` (sorted by date) and return the creative's life. `overrides`: [(date, state)] from confirmed decisions."""
    life = Life(since=days[0].date if days else None)
    over = {d: s for d, s in overrides}
    counted: list[Day] = []                       # complete, unblocked days, in order
    cum = {"impressions": 0.0, "clicks": 0.0, "spend": 0.0, "conversions": 0.0, "delivery_days": 0}
    st = {"entered_delivery": 0, "entered_spend": 0.0, "entered_conv": 0.0, "doubt_spend_at": 0.0, "doubt_conv_at": 0.0,
          "peak_spend7": 0.0, "best_cost7": None, "decline_run": 0, "recover_run": 0, "idle_run": 0, "off_run": 0}

    def enter(to: str, day: str, reason: str, read: dict) -> None:
        life.moves.append(Move(day, life.state, to, reason, read))
        life.state, life.since = to, day
        st["entered_delivery"], st["entered_spend"], st["entered_conv"] = cum["delivery_days"], cum["spend"], cum["conversions"]
        if to == "doubt":
            st["doubt_spend_at"], st["doubt_conv_at"] = cum["spend"], cum["conversions"]
        if to in ("mature", "declining"):
            st["decline_run"] = st["recover_run"] = 0
        if to == "mature" and frm_is_new_peak(life):
            st["peak_spend7"], st["best_cost7"] = 0.0, None

    def frm_is_new_peak(l: Life) -> bool:        # a creative that comes to mature from elsewhere starts its peak afresh
        return bool(l.moves) and l.moves[-1].frm != "declining"

    for day in days:
        if day.date in over and over[day.date] in STATES and over[day.date] != life.state:
            enter(over[day.date], day.date, "override", {})
        if day.blocked:
            life.blocked_now = day.blocked
            if day.blocked == "off" and life.state in ("testing", "learning", "doubt"):
                st["off_run"] += 1
                if st["off_run"] >= p.end_idle_days:
                    enter("parked", day.date, "stopped_unjudged", {"off_days": st["off_run"]})
            continue                              # a blocked day is not counted and not judged
        st["off_run"] = 0
        life.blocked_now = None
        if not day.complete:
            continue
        counted.append(day)
        life.days_counted += 1
        cum["impressions"] += day.impressions
        cum["clicks"] += day.clicks
        cum["spend"] += day.spend
        cum["conversions"] += day.conversions
        delivered = day.spend > 0 or day.impressions > 0
        if delivered:
            cum["delivery_days"] += 1
            st["idle_run"] = 0
        else:
            st["idle_run"] += 1
        if life.state in ("parked", "ended"):
            if life.state == "parked" and life.review_due is None:
                life.review_due = _plus(life.since, p.park_review_days)
            continue
        window = _recent(counted)
        spend7 = sum(d.spend for d in window)
        cost7 = _cost(window, p.min_conversions_for_cost)
        in_state = cum["delivery_days"] - st["entered_delivery"]
        read = {"impressions": cum["impressions"], "conversions": cum["conversions"], "spend": round(cum["spend"], 2)}

        if life.state == "testing":
            if cum["impressions"] >= p.reach_impressions or cum["conversions"] >= 1:
                enter("learning", day.date, "reach" if cum["impressions"] >= p.reach_impressions else "converted", read)
            elif in_state >= p.reach_days and cum["impressions"] < p.reach_floor:
                enter("parked", day.date, "low_reach", {**read, "delivery_days": in_state})
            else:
                life.waiting = {"impressions": [cum["impressions"], p.reach_impressions],
                                "delivery_days_to_park": [in_state, p.reach_days]}
        if life.state == "learning":
            if cum["conversions"] >= p.learning_conversions or day.platform_learning_over:
                enter("mature", day.date, "learned" if cum["conversions"] >= p.learning_conversions else "platform_learned", read)
            elif cum["conversions"] == 0 and cum["spend"] >= p.doubt_spend:
                enter("doubt", day.date, "no_conversion", read)
            elif in_state >= p.learning_max_days:
                enter("doubt", day.date, "slow", {**read, "delivery_days": in_state})
            else:
                life.waiting = {"conversions": [cum["conversions"], p.learning_conversions]}
                if cum["conversions"] == 0 and p.doubt_spend != float("inf"):
                    life.waiting["spend_to_doubt"] = [round(cum["spend"], 2), p.doubt_spend]
        elif life.state == "doubt":
            extension = p.doubt_extension * p.doubt_spend
            more = cum["spend"] - st["doubt_spend_at"]
            if cum["conversions"] > st["doubt_conv_at"]:
                enter("learning", day.date, "converted", read)
            elif more >= extension:
                sig = signal(counted)
                if p.weak_signal is not None and sig is not None and sig <= p.weak_signal:
                    enter("ended", day.date, "weak_creative", {**read, "signal": round(sig, 4)})
                else:
                    enter("parked", day.date, "no_conversion", read)
            else:
                life.waiting = {"extension_spend": [round(more, 2), extension]}
        elif life.state in ("mature", "declining"):
            st["peak_spend7"] = max(st["peak_spend7"], spend7)
            if cost7 is not None and (st["best_cost7"] is None or cost7 < st["best_cost7"]):
                st["best_cost7"] = cost7
            worse = (cost7 is not None and st["best_cost7"] is not None and cost7 >= st["best_cost7"] * (1 + p.decline_rise)) \
                or (st["peak_spend7"] > 0 and spend7 <= st["peak_spend7"] * (1 - p.decline_drop))
            r7 = {"spend7": round(spend7, 2), "cost7": None if cost7 is None else round(cost7, 2),
                  "peak_spend7": round(st["peak_spend7"], 2),
                  "best_cost7": None if st["best_cost7"] is None else round(st["best_cost7"], 2)}
            if life.state == "mature":
                st["decline_run"] = st["decline_run"] + 1 if worse else 0
                if st["decline_run"] >= p.decline_days:
                    enter("declining", day.date, "worse", r7)
                else:
                    life.waiting = {"decline_days": [st["decline_run"], p.decline_days]}
            else:
                st["recover_run"] = st["recover_run"] + 1 if not worse else 0
                if st["peak_spend7"] > 0 and spend7 < st["peak_spend7"] * p.end_spend_share:
                    enter("ended", day.date, "faded", r7)
                elif st["idle_run"] >= p.end_idle_days:
                    enter("ended", day.date, "idle", {"idle_days": st["idle_run"], **r7})
                elif st["recover_run"] >= p.recover_days:
                    enter("mature", day.date, "recovered", r7)
                else:
                    life.waiting = {"recover_days": [st["recover_run"], p.recover_days]}
    life.totals = {"impressions": cum["impressions"], "clicks": cum["clicks"], "spend": round(cum["spend"], 2),
                   "conversions": cum["conversions"], "delivery_days": cum["delivery_days"]}
    if life.state == "parked" and life.review_due is None and life.since:
        life.review_due = _plus(life.since, p.park_review_days)
    if life.state in ("parked", "ended"):
        life.waiting = {}
    return life


def _plus(day: str, n: int) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()
