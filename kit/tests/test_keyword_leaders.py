#!/usr/bin/env python3
"""kit.keyword_leaders: the paid-search skill pack's four-week case, then the edges.

W1 A B C; W2 A C D (D enters and is new, B leaves); W3 the table is held but the keyword has no rows (no leaders, no drift: not
"everyone left"); W4 A D E, compared with W2, the previous week with leaders (E enters and is new, C leaves, D is not new).
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import keyword_leaders as kl  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

W1, W2, W3, W4 = "2026-08-23", "2026-08-30", "2026-09-06", "2026-09-13"


def r(week, rank, product, cs=0.3, conv=0.1):
    return {"week": week, "rank": rank, "product": product, "click_share": cs, "conversion_share": conv}


ROWS = [r(W1, 1, "A"), r(W1, 2, "B"), r(W1, 3, "C"), r(W2, 1, "A"), r(W2, 2, "C"), r(W2, 3, "D"), r(W4, 1, "A"), r(W4, 2, "D"), r(W4, 3, "E")]


def main() -> int:
    out = kl.weekly(ROWS, [W1, W2, W3, W4], {"A"}, "widget")
    wk = {w["week"]: w for w in out["weeks"]}
    check("the first week: leaders in rank order, no drift to state", [x["product"] for x in wk[W1]["leaders"]] == ["A", "B", "C"]
          and wk[W1]["entered"] is None and wk[W1]["new_entrants"] is None, wk[W1])
    check("W2: D entered (new), B left", (wk[W2]["entered"], wk[W2]["left"], wk[W2]["new_entrants"]) == (["D"], ["B"], ["D"]), wk[W2])
    check("a week held without the keyword: no leaders and no drift", wk[W3]["leaders"] == [] and wk[W3]["entered"] is None and wk[W3]["left"] is None)
    check("W4 is compared with W2: E entered and is new, C left, D is not new (seen in W2)",
          (wk[W4]["entered"], wk[W4]["left"], wk[W4]["new_entrants"]) == (["E"], ["C"], ["E"]), wk[W4])
    ranks = {p["product"]: p for p in out["products"]}
    check("rank per week, None outside the top 3; first_seen_week", ranks["D"]["ranks"] == {W1: None, W2: 3, W3: None, W4: 2}
          and ranks["D"]["first_seen_week"] == W2 and ranks["A"]["first_seen_week"] == W1, ranks["D"])
    check("ours is marked on the leader and on the product", wk[W1]["leaders"][0]["ours"] and not wk[W1]["leaders"][1]["ours"] and ranks["A"]["ours"])
    check("products are ordered by first week seen, then best rank", [p["product"] for p in out["products"]] == ["A", "B", "C", "D", "E"])
    check("rows given out of order read the same", kl.weekly(list(reversed(ROWS)), [W1, W2, W3, W4], {"A"}, "widget") == out)
    check("rows of a week the table does not hold are ignored", kl.weekly(ROWS + [r("2020-01-05", 1, "Z")], [W1, W2, W3, W4], set())["products"]
          == kl.weekly(ROWS, [W1, W2, W3, W4], set())["products"])
    check("no weeks held, nothing to say", kl.weekly([], [], set(), "k") == {"keyword": "k", "weeks": [], "products": []})
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
