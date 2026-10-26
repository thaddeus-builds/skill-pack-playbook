#!/usr/bin/env python3
"""The overview's diagram as one page a person can click through.

    python3 tools/overview_page.py --out PATH [--doc docs/overview.md]

Reads the first mermaid flowchart of the overview and the numbered list just above it (one
step per column), and writes one self-contained HTML file: no network request, the data
inside it, light and dark, readable at phone width. Every arrow is one document one pack hands
to another. By default nothing is drawn between the packs; a person picks a step, or a pack,
and sees only that pack's arrows, numbered, with the same numbers in a list beneath.

The page is made from the diagram, so the two cannot disagree. A line of the diagram this
reads does not understand, an arrow to a pack that is not drawn, a column with no step in the
list, or a list with a step too many is refused with the line named, never drawn without it.

The diagram's grammar is the overview's: `subgraph ID["N · title"]` ... `end`, a pack as
`ID["name<br/>what it does"]`, an arrow as `A -- "document/1: why" --> B`, and a pack outside
every subgraph as `ID["N · name<br/>what it does"]`, which is a column of its own.

The page builds its columns when it opens, and a browser's "save page" keeps what it built:
the script clears them first, so a saved copy shows one set, not two (seen once, 2026-10-26).

Read-only. Stdlib only. Test: tests/test_overview_page.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PLAYBOOK = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).with_name("overview_page.html")
FENCE = re.compile(r"```mermaid\n(.*?)```", re.S)
SUBGRAPH = re.compile(r'subgraph (\w+)\["(.*)"\]$')
NODE = re.compile(r'(\w+)\["(.*)"\]$')
EDGE = re.compile(r'(\w+) -- "(.*)" --> (\w+)$|(\w+) --> (\w+)$')
NUMBERED = re.compile(r"(\d+)\. (.*)$")
SKIP = re.compile(r"(flowchart\b.*|graph\b.*|direction\b.*|%%.*)$")


class Refused(Exception):
    pass


def plain(s: str) -> str:
    return s.replace("**", "").replace("`", "")


def numbered_title(text: str, what: str) -> tuple[int, str]:
    m = re.match(r"(\d+) · (.*)$", text)
    if not m:
        raise Refused(f'{what} "{text}" has no "N · " in front: the number is its column')
    return int(m.group(1)), m.group(2)


def steps_above(before: str) -> tuple[list[tuple[str, str]], str]:
    """The numbered list closest above the diagram: [(short name, sentence)], and the example it
    introduces (the paragraph above it, "Follow one example: ..."), or "" when there is none."""
    lines = before.rstrip().split("\n")
    run: list[str] = []
    i = len(lines) - 1
    while i >= 0 and (not lines[i].strip() or NUMBERED.match(lines[i])):
        if lines[i].strip():
            run.append(lines[i])
        i -= 1
    run.reverse()
    items = []
    for k, line in enumerate(run, 1):
        m = NUMBERED.match(line)
        if int(m.group(1)) != k:
            raise Refused(f"the list above the diagram is numbered {m.group(1)} where {k} comes")
        bold = re.search(r"\*\*(.+?)\*\*", m.group(2))
        short = plain(bold.group(1)) if bold else plain(m.group(2)).split(" ")[0]
        items.append((short[:1].upper() + short[1:], plain(m.group(2))))
    example = ""
    for j in range(i, max(i - 4, -1), -1):
        m = re.search(r"Follow one example: (.*?)\.(?: |$)", lines[j])
        if m:
            example = m.group(1)[:1].upper() + m.group(1)[1:]
            break
    return items, example


def parse(text: str) -> dict:
    """{title, lanes: [{id, n, title, step, text}], nodes: [{id, name, desc, lane}], edges: [...]}."""
    m = FENCE.search(text)
    if not m:
        raise Refused("no mermaid diagram in the document")
    steps, example = steps_above(text[:m.start()])
    nodes: dict[str, dict] = {}
    lanes: dict[int, dict] = {}
    edges: list[dict] = []
    cur = None
    first = text[:m.start()].count("\n") + 2          # the diagram's first line, for messages
    for off, raw in enumerate(m.group(1).split("\n")):
        line, where = raw.strip(), first + off
        if not line or SKIP.match(line):
            continue
        if line == "end":
            cur = None
            continue
        if (g := SUBGRAPH.match(line)):
            n, title = numbered_title(g.group(2), "column")
            if n in lanes:
                raise Refused(f"line {where}: column {n} is drawn twice")
            lanes[n] = {"id": g.group(1), "n": n, "title": title}
            cur = n
            continue
        if (g := NODE.match(line)):
            name, _, desc = g.group(2).partition("<br/>")
            lane = cur
            if lane is None:                           # outside every subgraph: a column of its own
                lane, name = numbered_title(name, f'pack {g.group(1)}')
                if lane in lanes:
                    raise Refused(f"line {where}: column {lane} is drawn twice")
                lanes[lane] = {"id": g.group(1) + "_col", "n": lane, "title": ""}
            if g.group(1) in nodes:
                raise Refused(f"line {where}: pack {g.group(1)} is drawn twice")
            nodes[g.group(1)] = {"id": g.group(1), "name": name, "desc": desc, "lane": lane}
            continue
        if (g := EDGE.match(line)):
            a, label, b = (g.group(1), g.group(2), g.group(3)) if g.group(1) else (g.group(4), "", g.group(5))
            contract, _, why = label.partition(": ")
            edges.append({"from": a, "to": b, "contract": contract, "why": why, "line": where})
            continue
        raise Refused(f"line {where} of the diagram is not understood: {line!r}")
    for e in edges:
        for end in (e["from"], e["to"]):
            if end not in nodes:
                raise Refused(f"line {e['line']}: the arrow names {end}, which no pack in the diagram is")
        del e["line"]
    order = sorted(lanes)
    if order != list(range(1, len(order) + 1)) or not order:
        raise Refused(f"the columns are numbered {order}: they must run 1, 2, 3 ... with none missing")
    if len(steps) != len(order):
        raise Refused(f"the list above the diagram has {len(steps)} steps and the diagram {len(order)} columns")
    empty = [n for n in order if not any(v["lane"] == n for v in nodes.values())]
    if empty:
        raise Refused(f"column {empty[0]} has no pack")
    out_lanes = []
    for n in order:
        short, sentence = steps[n - 1]
        out_lanes.append({"id": f"L{n}", "n": n, "title": lanes[n]["title"] or short, "step": short, "text": sentence})
    for v in nodes.values():
        v["lane"] = f"L{v['lane']}"
    return {"title": example or "The example", "lanes": out_lanes, "nodes": list(nodes.values()), "edges": edges}


def render(data: dict) -> str:
    page = TEMPLATE.read_text("utf-8")
    if page.count("__DATA__") != 1:
        raise Refused("the page template must hold __DATA__ once")
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")     # never a closing tag inside the data
    return page.replace("__DATA__", blob)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The overview's diagram as a page a person can click through.")
    ap.add_argument("--doc", default=str(PLAYBOOK / "docs" / "overview.md"), help="the document holding the diagram")
    ap.add_argument("--out", required=True, help="the HTML file to write (replaced if it exists)")
    a = ap.parse_args(argv)
    try:
        data = parse(Path(a.doc).read_text("utf-8"))
        html = render(data)
    except (Refused, OSError) as e:
        print(f"overview_page: {e}", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, "utf-8")
    print(f"wrote {out} ({len(data['nodes'])} packs, {len(data['edges'])} documents, {len(data['lanes'])} steps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
