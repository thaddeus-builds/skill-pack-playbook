"""Proven and unproven: which wallet a precise target (or a creative) spends from, decided by its own settled days, no database, no
platform.

"The explore wallet is to see whether selling can be proved; the perform wallet is to optimise only what is already proved."

  * `tally()`: clicks, orders, order days, spend and sales of some settled day rows (`Day`);
  * `proves()`: at least `min_orders` orders on at least `min_order_days` distinct days, never on a search that is the brand's own
    (it proves nothing about the market). There is no click minimum: clicks gate only the losing side;
  * `loss_verdict()`: over the last weeks, `lost` (at least `click_min` clicks and no order), `kept` (an order, or fewer clicks:
    hysteresis, it keeps its status) or `undetermined` (no order in the days on hand and the daily table misses some of them);
    days a target did not serve carry no clicks, so no stock history is needed;
  * `move()`: the wallet move that follows, `to_perform`, `to_explore` or None; `wallet()` names the wallet of a verdict.

A caller passes the rows already filtered to settled days (`kit.ledger.is_settled`); this module never reads a clock.

From the paid-search skill pack (`certainty`: its tests are the second set here) and the video-ads skill pack (a creative is
proven when it is `mature`, which is the same wallet rule: `wallet(True)`).

Test: kit/tests/test_proof.py.
"""

from __future__ import annotations

from typing import NamedTuple

PERFORM, EXPLORE = "perform", "explore"
LOST, KEPT, UNDETERMINED = "lost", "kept", "undetermined"


class Day(NamedTuple):
    """One settled row of one day of one precise target (an exact keyword, a single named product): the caller decides what is
    precise and passes only its rows."""
    date: str
    clicks: int = 0
    spend: float = 0.0
    orders: int = 0
    sales: float = 0.0


def tally(days) -> dict:
    """clicks / orders / order_days / spend / sales of some day rows."""
    days = list(days)
    return {"clicks": sum(d.clicks for d in days), "orders": sum(d.orders for d in days),
            "order_days": len({d.date for d in days if d.orders}), "spend": sum(d.spend for d in days),
            "sales": sum(d.sales for d in days)}


def proves(t: dict, min_orders: int, min_order_days: int, own_brand: bool = False) -> bool:
    return not own_brand and t["orders"] >= min_orders and t["order_days"] >= min_order_days


def loss_verdict(t: dict, covered: bool, click_min: int) -> str:
    if t["orders"]:
        return KEPT
    if not covered:
        return UNDETERMINED
    return LOST if t["clicks"] >= click_min else KEPT


def wallet(proven: bool) -> str:
    return PERFORM if proven else EXPLORE


def move(current: str, proof: dict, recent: dict, covered: bool, k: dict, own_brand: bool = False) -> str | None:
    """`to_perform` for an explore target whose `proof` tally proves; `to_explore` for a perform target whose `recent` tally is
    `lost`; None otherwise. `k` holds `min_orders`, `min_order_days` and `click_min`."""
    if current == EXPLORE and proves(proof, k["min_orders"], k["min_order_days"], own_brand):
        return "to_perform"
    if current == PERFORM and loss_verdict(recent, covered, k["click_min"]) == LOST:
        return "to_explore"
    return None
