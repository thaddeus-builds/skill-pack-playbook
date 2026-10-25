"""The wallet of an ad group: the rules alone, no database, no platform.

The learning stage belongs to the ad group (the unit above the creative and below the campaign that has its own budget), so the
day's money is split by the ad group: one past learning and judged spends from the *perform* wallet, a new batch's group (still
learning) or one with too little evidence spends from *explore*, one that is stopped or never spent spends nothing. The group has
delivered `learning_days` and its window holds the judging spend and conversions. A group can only hold money back: a creative
that has not earned a verdict (its own wallet is explore) is paid from explore even in a judged group, a creative that is parked
or ended is paid by nobody, and a creative with no known group keeps the wallet of its own state.

From the video-ads skill pack (`adgroup`).

Test: kit/tests/test_wallets.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class Params:
    learning_days: int
    window_days: int
    judge_spend: float
    min_conversions: float
    end_idle_days: int


def judge(days: dict[str, tuple[float, float]], active: bool, as_of: str, p: Params) -> tuple[str, str]:
    """(wallet, reason) of one ad group on `as_of`: `days` = {YYYY-MM-DD: (spend, conversions)} of its complete days, `active` whether the platform
    still says it delivers. wallet is `perform`, `explore` or `none`."""
    end = date.fromisoformat(as_of)
    spent = sorted(d for d, (s, _) in days.items() if s > 0 and d <= as_of)
    if not spent:
        return ("explore", "no_spend_yet") if active else ("none", "never_ran")
    last, first = date.fromisoformat(spent[-1]), date.fromisoformat(spent[0])
    if not active and (end - last).days >= p.end_idle_days:
        return "none", "stopped_idle"
    if (end - first).days + 1 < p.learning_days:
        return "explore", "learning"
    lo = end - timedelta(days=p.window_days - 1)
    spend = conv = 0.0
    for d, (s, c) in days.items():
        if lo <= date.fromisoformat(d) <= end:
            spend += s
            conv += c
    if spend < p.judge_spend or conv < p.min_conversions:
        return "explore", "unjudged"
    return "perform", "judged"


def pay(own: str | None, group: str) -> str | None:
    """The wallet that pays a creative: `own` is its own state's wallet (a creative's lifecycle gives it), `group` its ad group's ("perform", "explore" or "none")."""
    if own is None or group == "none":
        return None
    return "explore" if group == "explore" else own
