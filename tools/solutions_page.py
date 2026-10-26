#!/usr/bin/env python3
"""Which skill packs a kind of client needs, as one page: pick the kind, and its packs light up.

    python3 tools/solutions_page.py --out PATH [--doc docs/solutions.md] [--portfolio docs/portfolio.md]

Reads the solutions table of docs/solutions.md (one row per kind of client, one column per layer),
its mermaid diagram (the documents the packs hand each other) and, for what each pack is, the
repository table of docs/portfolio.md; writes one self-contained page, the same as tools/overview_page.py
makes (that tool's template, `parse_diagram` and `render`). A person picks one kind of client, or two (a brand
that also sells on Amazon is two), and the packs that solution needs light up and the others fade, with what
the table says of each layer and what the solution still lacks. A click on a pack draws the documents it
reads and hands on.

The page is made from the tables, so the two cannot disagree. A pack is a name in backticks in a layer's cell,
not one inside brackets (a note: "with the kit's `compliance`"), plus a bare name the diagram draws
("messaging"). A layer the table has and the diagram has not, a pack the diagram draws in another layer than
the table puts it in, or one pack in two layers is refused, never guessed.

Read-only. Stdlib only. Test: tests/test_solutions_page.py.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import overview_page as op  # noqa: E402

Refused = op.Refused
PLAYBOOK = op.PLAYBOOK
HEADING = "Which packs does a client need?"
SUB = ("Pick the kind of client. The packs its solution needs light up and the others fade; a client may need two, "
       "so pick two if so. Click a pack to see which documents it reads and hands on.")
FOOTER = ("Drawn from the tables of docs/solutions.md (and what each pack is, from docs/portfolio.md) by "
          "tools/solutions_page.py, so the page and the tables cannot disagree. The documents between packs are the ones "
          "that page draws for solution A, of which the others are subsets.")
EMPTY = {"", "-", "—"}


def tables(text: str) -> list[dict]:
    """Every markdown table: {heading, header: [cells], rows: [[cells]], end: line index after it}."""
    lines, out, heading, i = text.split("\n"), [], "", 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"#{1,6} ", line):
            heading = line.lstrip("#").strip()
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            cells = lambda s: [c.strip() for c in s.strip().strip("|").split("|")]
            header, rows, j = cells(line), [], i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append(cells(lines[j]))
                j += 1
            out.append({"heading": heading, "header": header, "rows": rows, "end": j})
            i = j
            continue
        i += 1
    return out


def without_notes(s: str) -> str:
    """The cell without anything in brackets (a note, not a pack), brackets inside brackets too."""
    prev = None
    while prev != s:
        prev, s = s, re.sub(r"\([^()]*\)", "", s)
    return s


def pack_names(cell: str, known: list[str]) -> list[str]:
    s = without_notes(cell)
    names = re.findall(r"`([^`]+)`", s)
    names += [k for k in known if re.search(rf"(?:^|[,;]\s*){re.escape(k)}\b", s)]
    return list(dict.fromkeys(names))


def roles(portfolio: str) -> dict[str, str]:
    """{pack: its layer and role} from the repository table of portfolio.md; a pack is its repository's name
    without the "-skill-pack" or "-harness" it ends with."""
    out: dict[str, str] = {}
    for t in tables(portfolio):
        if t["header"][:1] == ["Repository"] and len(t["header"]) >= 3:
            for r in t["rows"]:
                name = re.sub(r"(-skill-pack|-harness)$", "", op.plain(r[0]))
                out[name] = op.plain(r[2])
    return out


def starting(text: str) -> dict | None:
    """The numbered steps of the section "Starting a client", the nested ones folded into their step."""
    m = re.search(r"^## (Starting a client)\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return None
    items: list[list] = []
    for line in m.group(2).split("\n"):
        if (g := re.match(r"\d+\. (.*)$", line)):
            items.append([op.plain(g.group(1)), []])
        elif (g := re.match(r"\s+\d+\. (.*)$", line)) and items:
            items[-1][1].append(op.plain(g.group(1)).rstrip(";."))
    return {"title": m.group(1),
            "items": [a.rstrip(":") + (": " + "; ".join(b) if b else "") for a, b in items]} if items else None


def parse(text: str, portfolio: str = "") -> dict:
    fence = op.FENCE.search(text)
    if not fence:
        raise Refused("no mermaid diagram in the document")
    lanes, nodes, edges = op.parse_diagram(fence.group(1), text[:fence.start()].count("\n") + 2, numbered=False)
    lane_of = {lanes[n]["title"].lower(): f"L{n}" for n in lanes}
    packs = {v["name"].split(" (")[0]: v for v in nodes.values()}            # the diagram's packs by name
    for e in edges:                                    # an arrow with no label carries the document its pack is drawn with
        if not e["contract"] and re.fullmatch(r"[\w.]+/\d+", nodes[e["from"]]["desc"]):
            e["contract"] = nodes[e["from"]]["desc"]
    for v in nodes.values():
        v["lane"] = f"L{v['lane']}"

    ts = tables(text)
    sol = next((t for t in ts if t["header"][:2] == ["Solution", "For"]), None)
    if not sol:
        raise Refused('no solutions table (a table whose columns start "Solution", "For")')
    layers = sol["header"][2:]
    for c in layers:
        if c.lower() not in lane_of:
            raise Refused(f'the table has a layer "{c}" and the diagram draws none: it draws {sorted(lane_of)}')
    what = roles(portfolio)
    groups, seen = [], {}
    for r in sol["rows"]:
        if len(r) != len(sol["header"]):
            raise Refused(f"a row of the solutions table has {len(r)} cells where the header has {len(sol['header'])}: {r[:1]}")
        m = re.match(r"([A-Z])\. (.*)$", op.plain(r[0]))
        if not m:
            raise Refused(f'a solution is named "{op.plain(r[0])}": it must start "A. ", "B. " ...')
        cells, members = {}, []
        for col, cell in zip(layers, r[2:]):
            lane = lane_of[col.lower()]
            if op.plain(cell) not in EMPTY:
                cells[lane] = op.plain(cell)
            for name in pack_names(cell, list(packs)):
                if name in seen and seen[name] != lane:
                    raise Refused(f"pack {name} is in two layers: {seen[name]} and {lane}")
                seen[name] = lane
                if name not in packs:
                    packs[name] = {"id": name, "name": name, "desc": "", "lane": lane}
                    nodes[name] = packs[name]
                elif packs[name]["lane"] != lane:
                    raise Refused(f"the diagram draws {name} in {packs[name]['lane']} and solution {m.group(1)} lists it in {lane}")
                members.append(packs[name]["id"])
        if not members:
            raise Refused(f"solution {m.group(1)} lists no pack")
        groups.append({"id": m.group(1), "title": m.group(2), "lead": op.plain(r[1]), "cells": cells,
                       "members": list(dict.fromkeys(members))})
    if not groups or len({g["id"] for g in groups}) != len(groups):
        raise Refused("the solutions are lettered A, B, C ... once each")
    for name, v in packs.items():
        title = lanes[int(v["lane"][1:])]["title"]
        role = re.sub(rf"^({title}|{title.rstrip('s')})[,:] ", "", what.get(name, ""))    # the column already says the layer
        v["desc"] = role or v["desc"]

    lacks = next((t for t in ts if t["header"][:1] == ["Solution"] and t["header"][:2] != ["Solution", "For"]), None)
    lacks_title = ""
    if lacks:
        lacks_title = lacks["heading"]
        by = {op.plain(r[0]): op.plain(r[1]) for r in lacks["rows"] if len(r) >= 2}
        for g in groups:
            g["lacks"] = by.get(g["id"], "")
    after = text.split("\n")[sol["end"]:]
    note = next((ln.strip() for ln in after if ln.strip()), "")
    note = op.plain(note) if note and not note.startswith(("#", "|")) else ""
    start = {"title": "Pick the kind of client", "lead": note or "Pick the kind of client.",
             "items": [f"{g['id']} · {g['title']}: {g['lead']}" for g in groups]}
    if (s := starting(text)):
        start["more"] = s
    order = {n: i for i, n in enumerate(sorted(lanes))}
    out_lanes = [{"id": f"L{n}", "n": n, "title": lanes[n]["title"]} for n in sorted(lanes)]
    out_nodes = sorted(nodes.values(), key=lambda v: (order[int(v["lane"][1:])], 0))
    return {"heading": HEADING, "sub": SUB, "footer": FOOTER, "start": start, "lacks_title": lacks_title,
            "lanes": out_lanes, "nodes": out_nodes, "edges": edges, "groups": groups}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Which skill packs a kind of client needs, as one page.")
    ap.add_argument("--doc", default=str(PLAYBOOK / "docs" / "solutions.md"), help="the document with the solutions table")
    ap.add_argument("--portfolio", default=None, help="the portfolio, for what each pack is (default: docs/portfolio.md if it exists)")
    ap.add_argument("--out", required=True, help="the HTML file to write (replaced if it exists)")
    a = ap.parse_args(argv)
    try:
        pf = Path(a.portfolio) if a.portfolio else PLAYBOOK / "docs" / "portfolio.md"
        if a.portfolio and not pf.is_file():
            raise Refused(f"no such file: {pf}")
        data = parse(Path(a.doc).read_text("utf-8"), pf.read_text("utf-8") if pf.is_file() else "")
        html = op.render(data)
    except (Refused, OSError) as e:
        print(f"solutions_page: {e}", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, "utf-8")
    print(f"wrote {out} ({len(data['groups'])} solutions, {len(data['nodes'])} packs, {len(data['edges'])} documents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
