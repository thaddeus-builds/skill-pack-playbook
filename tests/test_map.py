"""docs/map.html: the picture of the skill packs keeps its colours from tools/adoption.tsv (the `use` column), so it cannot drift from the table.

A tile is `<div class="tile COLOUR"><div class="row"><b>NAME</b>`; its name is the pack's folder name without `-skill-pack`. The legend counts
must equal the table's, the page names no outside host, and docs/portfolio.md links it.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TILE = re.compile(r'<div class="tile (\w+)"><div class="row"><b>([^<]+)</b>')
LEGEND = re.compile(r'<span class="count (\w+)">(\d+)</span>')


def read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def use_by_name(adoption: str) -> dict[str, str]:
    rows = csv.DictReader(adoption.splitlines(), delimiter="\t")
    return {r["pack"].removesuffix("-skill-pack"): r["use"] for r in rows}


def problems(page: str, adoption: str, portfolio: str) -> list[str]:
    want = use_by_name(adoption)
    tiles = {n: c for c, n in TILE.findall(page) if n.isascii()}
    out = [f"tile missing: {n}" for n in sorted(set(want) - set(tiles))]
    out += [f"tile not in the table: {n}" for n in sorted(set(tiles) - set(want))]
    out += [f"{n} is {tiles[n]} on the page, {want[n]} in the table" for n in sorted(set(tiles) & set(want)) if tiles[n] != want[n]]
    counts = {c: int(k) for c, k in LEGEND.findall(page)}
    for use in sorted(set(want.values())):
        if counts.get(use) != sum(1 for v in want.values() if v == use):
            out.append(f"legend count for {use}: {counts.get(use)}")
    if "http" in page:
        out.append("an outside address")
    if "map.html" not in portfolio:
        out.append("docs/portfolio.md does not link the map")
    return out


def test_the_map_agrees_with_the_adoption_table():
    assert problems(read("docs/map.html"), read("tools/adoption.tsv"), read("docs/portfolio.md")) == []


def test_each_break_is_seen():
    page, table, portfolio = read("docs/map.html"), read("tools/adoption.tsv"), read("docs/portfolio.md")
    assert problems(page.replace('<div class="tile earned"><div class="row"><b>adcut<', '<div class="tile built"><div class="row"><b>adcut<'), table, portfolio)
    assert problems(page.replace("<b>meta-ads</b>", "<b>meta-adz</b>"), table, portfolio)
    assert problems(page, table.replace("sdr-skill-pack\t", "sdr2-skill-pack\t", 1), portfolio)
    assert problems(page.replace('<span class="count earned">9<', '<span class="count earned">8<'), table, portfolio)
    assert problems(page + "https://example.com", table, portfolio)
    assert problems(page, table, portfolio.replace("map.html", "x.html"))


if __name__ == "__main__":
    _t.main(globals())
