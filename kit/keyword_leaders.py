"""Who holds the top clicks on a main keyword, week by week, and who just arrived. A weekly reading, no database, no platform.

The source is a table the platform sends weekly and keeps only the top 3 clicked products per term for (`rows`: week, rank, product,
click share, conversion share). Per week the keyword's `leaders` (rank 1 to 3), then against the previous week *that has leaders*:
`entered` and `left` the top 3, and `new_entrants` (entered, and never in the top 3 of an earlier week held). A week the table
holds but where the keyword has no rows has no leaders and no drift: the platform dropped it from the kept terms, which is not
"everyone left". `products` gives each product's rank in every week held (None = not in the top 3 that week) and its
`first_seen_week`, which is the first week *held*, not the first week it ever appeared: a short table cannot say how old a
leader is. Only the top 3 and click share, never a page position.

From the paid-search skill pack (`keyword_leaders`; its cases are the test).

Test: kit/tests/test_keyword_leaders.py.
"""

from __future__ import annotations


def weekly(rows: list[dict], held: list[str], own: set[str], keyword: str = "") -> dict:
    """`rows`: [{week, rank, product, click_share, conversion_share}] of one keyword; `held`: the weeks the table holds, oldest
    first. {keyword, weeks, products}."""
    by_week: dict[str, list[dict]] = {w: [] for w in held}
    for r in sorted(rows, key=lambda r: (r["week"], r["rank"])):
        if r["week"] in by_week:
            by_week[r["week"]].append({"rank": r["rank"], "product": r["product"], "click_share": r.get("click_share"),
                                       "conversion_share": r.get("conversion_share"), "ours": r["product"] in own})
    weeks, seen, prev = [], {}, None
    for w in held:
        leaders = by_week[w]
        ids = [x["product"] for x in leaders]
        entry = {"week": w, "leaders": leaders, "entered": None, "left": None, "new_entrants": None}
        if leaders and prev is not None:
            before = {x["product"] for x in by_week[prev]}
            entry["entered"] = [a for a in ids if a not in before]
            entry["left"] = sorted(before - set(ids))
            entry["new_entrants"] = [a for a in entry["entered"] if a not in seen]
        for a in ids:
            seen.setdefault(a, w)
        if leaders:
            prev = w
        weeks.append(entry)
    ranks = {a: {w: None for w in held} for a in seen}
    for e in weeks:
        for x in e["leaders"]:
            ranks[x["product"]][e["week"]] = x["rank"]
    products = [{"product": a, "ours": a in own, "first_seen_week": seen[a], "ranks": ranks[a]}
                for a in sorted(seen, key=lambda a: (seen[a], min(r for r in ranks[a].values() if r), a))]
    return {"keyword": keyword, "weeks": weeks, "products": products}
