#!/usr/bin/env python3
"""What the skill packs already looked up: one table from every pack's two indexes, so a question one pack asked
(a vendor's API, a method, a law) is found before another pack asks it again (docs/lessons.md, "Research is kept, not repeated").

    python3 tools/research.py SKILL_PACK... [--write docs/research-index.tsv]

For each skill pack it reads `docs/research/README.md` (kind `research`) and `docs/prior-art/README.md` (kind `prior-art`) and prints
one table: pack, kind, question, date, answer, file. A row is any line of the index that links a `.md` file of the same folder: in a
table the cells are read by their header (question or lens or topic; date; answer or verdict or covers), in a list or a sentence the
line is the question. A date missing from the index is the file's: `YYYY-MM-DD-` in its name, else its `Researched` or `Scan date`
line. A skill pack with neither index is named on stderr and left out. `--write FILE` also writes the table, in full, as a TSV
(tabs and line breaks inside a cell become spaces).

Only merged work counts: point it at checkouts of the skill packs' main branches. Read-only except for `--write`. Stdlib only.
Test: tests/test_research_tool.py.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FOLDERS = (("research", "docs/research"), ("prior-art", "docs/prior-art"))
COLUMNS = ("pack", "kind", "question", "date", "answer", "file")
LINK = re.compile(r"\[([^\]]*)\]\(([\w.-]+\.md)(?:#[^)\s]*)?\)")
DAY = re.compile(r"(\d{4}-\d{2}-\d{2})")
STATED = re.compile(r"(?:Researched|Scan date:?)\s*\**\s*(\d{4}-\d{2}-\d{2})", re.I)
QUESTION, ANSWER = ("question", "lens", "topic"), ("answer", "verdict", "covers")
SHOWN = 60


def cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def date_of(folder: Path, name: str) -> str:
    m = DAY.match(name)
    if m:
        return m.group(1)
    try:
        m = STATED.search((folder / name).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        m = None
    return m.group(1) if m else ""


def rows(folder: Path, kind: str) -> list[dict]:
    index = folder / "README.md"
    if not index.is_file():
        return []
    out, seen, header = [], set(), []
    for ln in index.read_text(encoding="utf-8", errors="replace").splitlines():
        link = LINK.search(ln)
        piped = ln.lstrip().startswith("|")
        if piped and not link:
            if not re.fullmatch(r"[\s|:-]+", ln):
                header = [c.lower() for c in cells(ln)]
            continue
        if not link or link.group(2) == "README.md" or link.group(2) in seen:
            continue
        seen.add(link.group(2))
        row = {"kind": kind, "question": "", "date": "", "answer": "", "file": link.group(2)}
        if piped:
            vals = cells(ln)
            by = dict(zip(header, vals)) if len(header) == len(vals) else {}
            pick = lambda names: next((by[h] for h in header if h in by and any(n in h for n in names)), "")
            row["question"], row["answer"] = pick(QUESTION), pick(ANSWER)
            m = DAY.search(pick(("date",)))
            row["date"] = m.group(1) if m else ""
            if not (row["question"] or row["answer"]):
                rest = [LINK.sub(r"\1", v) for v in vals if not LINK.search(v)]
                row["question"], row["answer"] = (rest[0] if rest else link.group(1)), " — ".join(rest[1:])
        else:
            row["question"] = LINK.sub(r"\1", re.sub(r"^\s*(?:[-*+]|\d+\.)\s*", "", ln)).strip()
        row["date"] = row["date"] or date_of(folder, row["file"])
        out.append(row)
    return out


def collect(skill_packs: list[Path]) -> tuple[list[dict], list[str]]:
    table, bare = [], []
    for sp in skill_packs:
        found = [dict(r, pack=sp.name) for kind, rel in FOLDERS for r in rows(sp / rel, kind)]
        table += found
        if not any((sp / rel / "README.md").is_file() for _, rel in FOLDERS):
            bare.append(sp.name)
    return table, bare


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def tsv(table: list[dict]) -> str:
    return "\n".join("\t".join(COLUMNS) if r is None else "\t".join(clean(r[c]) for c in COLUMNS)
                     for r in [None, *table]) + "\n"


def render(table: list[dict]) -> str:
    cut = lambda t: t if len(t) <= SHOWN else t[:SHOWN - 1] + "…"
    lines = [[c for c in COLUMNS]] + [[cut(clean(r[c])) for c in COLUMNS] for r in table]
    width = [max(len(l[i]) for l in lines) for i in range(len(COLUMNS))]
    return "\n".join("  ".join(v.ljust(w) for v, w in zip(l, width)).rstrip() for l in lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="One table of what the skill packs already looked up.")
    ap.add_argument("skill_pack", nargs="+", type=Path)
    ap.add_argument("--write", type=Path, metavar="FILE", help="also write the table in full as a TSV")
    a = ap.parse_args(argv)
    missing = [str(p) for p in a.skill_pack if not p.is_dir()]
    if missing:
        print("not a folder: " + ", ".join(missing), file=sys.stderr)
        return 2
    table, bare = collect([p.resolve() for p in a.skill_pack])
    print(render(table))
    if bare:
        print("no docs/research or docs/prior-art index: " + ", ".join(bare), file=sys.stderr)
    if a.write:
        a.write.parent.mkdir(parents=True, exist_ok=True)
        a.write.write_text(tsv(table), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
