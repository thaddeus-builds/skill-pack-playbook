#!/usr/bin/env python3
"""kit.search_terms: triage, harvest and negatives on the paid-search skill pack's planted cases.

  * the two-gate case (12 clicks and profitable is `profit` under a 10-click gate and `weak` under a single 20-click one), every bucket
    on its boundary, float noise on a line;
  * harvest: a profitable term with enough clicks and no exact keyword; the bid is the term's own cost per click floored to the cent;
  * negatives: waste only, and never a term that has an order anywhere in the account;
  * negative phrases: two-word phrases before single words, a root needs enough characters, a family enough members, the group's
    own vocabulary and any converting word are never roots, every member must have no order;
  * a product reference against the catalog and the group's advertised products.
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import search_terms as st  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

K = {"significance_clicks": 10, "sig_spend_mult": 2, "click_threshold_min": 20, "marginal_band_top": 0.55, "high_cos_bleed": 0.80,
     "negate_protect_orders": 1, "negative_phrase_min_root_chars": 4, "negative_phrase_min_family_size": 2}
BE, CPA = 0.40, 4.0


def main() -> int:
    print("[1] classify")
    check("12 clicks, profitable: profit under the 10-click gate, weak under a single 20-click gate",
          st.classify(12, 4.0, 1, 10.0, BE, None, K) == "profit" and st.classify(12, 4.0, 1, 10.0, BE, None, {**K, "significance_clicks": 20}) == "weak")
    cases = [("on the break-even line", (12, 4.0, 1, 10.0), "profit"),
             ("a hair over the line from float noise still profit", (12, 4.0000001, 1, 10.0), "profit"),
             ("just over: margin", (12, 4.5, 1, 10.0), "margin"),
             ("on the margin band's top", (12, 5.5, 1, 10.0), "margin"),
             ("over the band: loss", (12, 6.0, 1, 10.0), "loss"),
             ("at the bleed line: heavy loss", (12, 8.0, 1, 10.0), "heavy_loss"),
             ("an order and no sales: infinitely over", (12, 3.0, 1, 0.0), "heavy_loss"),
             ("not judged by clicks (5) or spend (< 2 x 4.0): weak", (5, 7.9, 1, 10.0), "weak"),
             ("not judged by clicks but by spend (>= 2 x break-even cost per order)", (5, 8.0, 1, 10.0), "heavy_loss"),
             ("no order below the click floor: weak", (19, 9.0, 0, 0.0), "weak"),
             ("no order at the click floor: waste", (20, 9.0, 0, 0.0), "waste")]
    for label, (c, s, o, sa), want in cases:
        got = st.classify(c, s, o, sa, BE, CPA, K)
        check(f"{label}: {want}", got == want, got)
    check("no break-even cost per order: only clicks judge", st.classify(5, 100.0, 1, 10.0, BE, None, K) == "weak")
    check("six buckets, every one reachable", set(st.BUCKETS) == {st.classify(*a, BE, CPA, K) for a in
          ((12, 4.0, 1, 10.0), (12, 5.0, 1, 10.0), (12, 6.0, 1, 10.0), (12, 8.0, 1, 10.0), (20, 9.0, 0, 0.0), (1, 1.0, 0, 0.0))})

    print("[2] harvest")
    check("a profit term with enough clicks and no exact keyword is a candidate", st.harvest_candidate("profit", 20, False, K))
    check("not with too few clicks, not with an exact keyword there, not another bucket",
          not st.harvest_candidate("profit", 19, False, K) and not st.harvest_candidate("profit", 20, True, K)
          and not st.harvest_candidate("margin", 99, False, K))
    h = st.harvest_bid(30, 20.0, 100.0, 0.40)
    check("the bid is the cost per click floored to the cent (0.6666 gives 0.66); the break-even cost per click is cos x sales / clicks",
          h["bid"] == 0.66 and abs(h["breakeven_cpc"] - 40.0 / 30) < 1e-9, h)
    check("a cent boundary does not slip (0.29 stays 0.29)", st.harvest_bid(100, 29.0, 100.0, 0.4)["bid"] == 0.29)
    check("no clicks, no break-even: None", st.harvest_bid(0, 1.0, 1.0, 0.4) == {"bid": None, "breakeven_cpc": None}
          and st.harvest_bid(5, 1.0, 1.0, None)["breakeven_cpc"] is None)

    print("[3] negate")
    check("a waste term with no order in the account is negated", st.negate_exact("waste", 0, K))
    check("an order anywhere in the account protects it", not st.negate_exact("waste", 1, K))
    check("only waste", not st.negate_exact("weak", 0, K) and not st.negate_exact("loss", 0, K))

    print("[4] negative phrases")
    check("tokens: lower case words and digits", st.tokens("Waterproof Band-Aid 3pk!") == ["waterproof", "band", "aid", "3pk"] and st.tokens(None) == [])
    check("a phrase is words side by side in order", st.has_phrase("cheap waterproof bandage", ["waterproof", "bandage"])
          and not st.has_phrase("waterproof cheap bandage", ["waterproof", "bandage"]) and not st.has_phrase("x", []))
    core = {"kindle", "a"}
    check("core: equal, or a long core word inside or around; a short core word swallows nothing",
          st.is_core("kindle", core, 4) and st.is_core("kindlecase", core, 4) and st.is_core("kind", core, 4)
          and not st.is_core("alpha", core, 4) and st.is_core("a", core, 4))
    check("converting words: the words of terms with an order", st.converting_words({"waterproof bandages": 2, "free stuff": 0}) == {"waterproof", "bandages"})
    terms = ["free coupon code", "free coupon", "free sample", "cheap sticker", "kindle free"]
    fams = st.family_candidates(terms, {"kindle"}, K)
    check("two-word phrases first and they claim their members; then single words over what is left",
          fams == [("free coupon", ["free coupon", "free coupon code"]), ("free", ["free sample", "kindle free"])], fams)
    check("a family needs enough members and a root enough characters", st.family_candidates(["ab cd", "ab ef"], set(), K) == []
          and st.family_candidates(["free x", "free y"], set(), {**K, "negative_phrase_min_family_size": 3}) == [])
    rows = {"free coupon code": (12, 0), "free coupon": (10, 0), "cheap sticker": (30, 0), "cheap stickers pack": (1, 1)}
    out = st.negative_phrase(rows, set(), set(), K)
    check("the family fires with its summed clicks when every member has no order", out == [{"root": "free coupon", "members": ["free coupon", "free coupon code"], "clicks": 22}], out)
    check("one member with an order stops the family", st.negative_phrase({**rows, "free coupon": (10, 1)}, set(), set(), K) == [])
    check("a family under the click floor does not fire", st.negative_phrase({"free coupon code": (5, 0), "free coupon": (5, 0)}, set(), set(), K) == [])
    check("a root with a converting word is never a candidate", st.negative_phrase(rows, set(), {"coupon"}, K) == [])
    own_voc = st.negative_phrase(rows, {"coupon"}, set(), K)
    check("the group's own vocabulary is never a root: the phrase with it is dropped and the single word left over stands",
          [o["root"] for o in own_voc] == ["free"], own_voc)
    check("and a core word that is the whole family leaves nothing", st.negative_phrase({"coupon a": (30, 0), "coupon b": (30, 0)}, {"coupon"}, set(), K) == [])

    print("[5] target class")
    own = {"B0OWN1", "B0OWN2"}
    check("not ours: a competitor", st.target_class("b0rival", own, set()) == "competitor")
    check("ours and advertised alone in its group: self cannibalization", st.target_class("B0OWN1", own, {"B0OWN1"}) == "self_cannibalization")
    check("ours and advertised with others: ambiguous", st.target_class("B0OWN1", own, {"B0OWN1", "B0OWN2"}) == "ambiguous")
    check("ours and not advertised there: cross promotion", st.target_class("B0OWN2", own, {"B0OWN1"}) == "cross_promotion")
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
