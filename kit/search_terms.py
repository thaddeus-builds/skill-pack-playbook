"""Search-term triage, harvest and negatives, the rules alone: no database, no platform, no clock.

  * `classify()`: a term's window sums into one of six buckets. *Judged* means clicks >= `significance_clicks`, or spend >=
    `sig_spend_mult` x the break-even cost per order. No order: `waste` at `click_threshold_min` clicks, else `weak`. An order but
    not judged: `weak`. Judged: cost of sales (spend over sales, rounded so float noise cannot move a term on a line) at or under
    the break-even is `profit`, up to `marginal_band_top` `margin`, under `high_cos_bleed` `loss`, else `heavy_loss`;
  * `harvest_candidate()`, `harvest_bid()`: a `profit` term with enough clicks and no exact keyword in its group is proposed as a
    new exact keyword, bid at its own cost per click floored to the cent, beside the break-even cost per click;
  * `negate_exact()`: a `waste` term is negated, unless it has `negate_protect_orders` orders anywhere in the account;
  * `negative_phrase()`: root-word families within one group's terms, two-word phrases first and then single words of at least
    `negative_phrase_min_root_chars` characters, a family of at least `negative_phrase_min_family_size` terms whose summed clicks
    reach `click_threshold_min` and none of whose members has an order; the group's own keyword vocabulary (`is_core`) and any word
    that has converted anywhere in the account (`converting_words`) are never roots. A candidate only: a person glances at it;
  * `target_class()`: a product reference against our catalog and the group's advertised products.

Thresholds arrive as a dict `k`. From the paid-search skill pack (`compute_triage`, `compute_actions_triage`; its golden cases
are the test).

Test: kit/tests/test_search_terms.py.
"""

from __future__ import annotations

import math
import re

BUCKETS = ("profit", "margin", "loss", "heavy_loss", "waste", "weak")
_WORD = re.compile(r"[a-z0-9]+")


def classify(clicks: int, spend: float, orders: int, sales: float, be_cos: float, be_cpa: float | None, k: dict) -> str:
    if not orders:
        return "waste" if clicks >= k["click_threshold_min"] else "weak"
    judged = clicks >= k["significance_clicks"] or (be_cpa is not None and spend >= k["sig_spend_mult"] * be_cpa)
    if not judged:
        return "weak"
    cos = round(spend / sales, 6) if sales else float("inf")
    if cos <= round(be_cos, 6):
        return "profit"
    if cos <= k["marginal_band_top"]:
        return "margin"
    if cos < k["high_cos_bleed"]:
        return "loss"
    return "heavy_loss"


def harvest_candidate(bucket: str, clicks: int, has_exact: bool, k: dict) -> bool:
    return bucket == "profit" and clicks >= k["click_threshold_min"] and not has_exact


def harvest_bid(clicks: int, spend: float, sales: float, be_cos: float | None) -> dict:
    """{bid, breakeven_cpc}: None where the clicks, the spend or the break-even are missing."""
    cpc = spend / clicks if clicks else None
    bid = (math.floor(round(cpc * 100, 6)) / 100 or None) if cpc else None
    return {"bid": bid, "breakeven_cpc": be_cos * sales / clicks if clicks and be_cos is not None else None}


def negate_exact(bucket: str, account_orders: int, k: dict) -> bool:
    return bucket == "waste" and account_orders < k["negate_protect_orders"]


def tokens(text: str | None) -> list[str]:
    return _WORD.findall((text or "").lower())


def has_phrase(text: str, root: list[str]) -> bool:
    """`root`'s words appear in `text`'s, in order and side by side: what a phrase negative of `root` blocks."""
    toks, n = tokens(text), len(root)
    return bool(n) and any(toks[i:i + n] == root for i in range(len(toks) - n + 1))


def is_core(word: str, core: set[str], min_root_chars: int) -> bool:
    """A candidate root is core if it equals one of the group's own keyword words or, for a core word long enough to mean
    something alone, contains it or sits inside it (so the brand and its compounds are never roots)."""
    long_c = {c for c in core if len(c) >= min_root_chars}
    return word in core or any(word in c or c in word for c in long_c)


def converting_words(account_orders: dict[str, int]) -> set[str]:
    """Every word of a search term that has an order anywhere in the account: the honest stand-in for "not off-product"."""
    out: set[str] = set()
    for term, orders in account_orders.items():
        if orders:
            out.update(tokens(term))
    return out


def family_candidates(terms: list[str], core: set[str], k: dict) -> list[tuple[str, list[str]]]:
    """[(root, [member terms])] within one group's terms; each term ends in at most one family; deterministic."""
    mn, size = k["negative_phrase_min_root_chars"], k["negative_phrase_min_family_size"]
    toks = {t: tokens(t) for t in terms}
    claimed: set[str] = set()
    out: list[tuple[str, list[str]]] = []

    def try_root(root: str, member) -> None:
        members = [t for t in terms if t not in claimed and member(t)]
        if len(members) >= size:
            out.append((root, sorted(members)))
            claimed.update(members)

    for root in sorted({f"{a} {b}" for t in terms for a, b in zip(toks[t], toks[t][1:])
                        if not is_core(a, core, mn) and not is_core(b, core, mn)}):
        a, b = root.split(" ", 1)
        try_root(root, lambda t, a=a, b=b: any(x == a and y == b for x, y in zip(toks[t], toks[t][1:])))
    for root in sorted({w for t in terms for w in toks[t] if len(w) >= mn and not is_core(w, core, mn)}):
        try_root(root, lambda t, root=root: root in toks[t])
    return out


def negative_phrase(rows: dict[str, tuple[int, int]], core: set[str], converting: set[str], k: dict) -> list[dict]:
    """`rows` {term: (clicks, orders)} of one group. [{root, members, clicks}] for each family that fires."""
    out = []
    for root, members in family_candidates(sorted(rows), core, k):
        if any(w in converting for w in root.split()):
            continue
        clicks = sum(rows[m][0] for m in members)
        if clicks >= k["click_threshold_min"] and all(rows[m][1] == 0 for m in members):
            out.append({"root": root, "members": members, "clicks": clicks})
    return out


def target_class(ref: str, own: set[str], advertised: set[str]) -> str:
    """competitor / ambiguous / self_cannibalization / cross_promotion of a product reference against our catalog and the
    products a group advertises."""
    ref = ref.upper()
    if ref not in own:
        return "competitor"
    if ref in advertised:
        return "ambiguous" if len(advertised) > 1 else "self_cannibalization"
    return "cross_promotion"
