"""Research is kept, not repeated: what a skill pack looked up is a file with a row in an index, so the next session reads the row before it searches.

Two folders, each with a `README.md` that lists its files (docs/lessons.md, "Research is kept, not repeated"; templates/research-index.md and
templates/prior-art-index.md are the starting points):

  docs/research/    one file per question; the index is a table, one row per file: question, date, answer in one line, where it is used.
                    Each file says `Researched YYYY-MM-DD` and tags its claims `[documented]`, `[vendor]`, `[academic]`, `[ours]` or `[inference]`
  docs/prior-art/   one dated scan per lens (`YYYY-MM-DD-name.md`, or a `Scan date:` line); the README is the front page and links every file

`problems(root)` returns every break of these rules; a folder that does not exist is not read (nothing is kept yet), one that does exist needs its README:

  1. the README links every `.md` file of its folder, and every same-folder `.md` link of the README is a file (a file with no row, or a row with
     no file, fails here)
  2. a research table row (a table line with a link) states a day
  3. a research file states `Researched YYYY-MM-DD` (a real day) and tags at least one claim
  4. a prior-art file's day is in its name or on a `Scan date:` line

Only the same folder is read: a link with a path (`../x.md`, `sub/y.md`) is not a row. Other files (`sources.tsv`, data) are not read.
`check_research(root)` is `problems`; `self_test()` plants each break and returns the ones the check missed.

Paid for: one skill pack held its research folder with a test of its own (2026-10-22); another moved its scan from `docs/research/` to `docs/prior-art/`
and back because two places were named, and the same vendors were researched again in other skill packs that kept no index.

Test: kit/tests/test_research.py.
"""

from __future__ import annotations

import re
import tempfile
from datetime import date
from pathlib import Path

from kit.guards import read

RESEARCH = "docs/research"
PRIOR_ART = "docs/prior-art"
INDEX = "README.md"
LINK = re.compile(r"\]\(([\w.-]+\.md)(?:#[^)\s]*)?\)")
DAY = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
RESEARCHED = re.compile(r"\bResearched (\d{4}-\d{2}-\d{2})\b")
SCANNED = re.compile(r"^(?:Scan date|Researched):?\s*\**\s*(\d{4}-\d{2}-\d{2})", re.M | re.I)
NAMED = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
TAG = re.compile(r"\[(?:documented|vendor|academic|ours|inference)\b")


def _real(day: str) -> bool:
    try:
        date.fromisoformat(day)
    except ValueError:
        return False
    return True


def listed(index: str) -> list[str]:
    """The files a README links (same folder, in order, each once)."""
    out: list[str] = []
    for name in LINK.findall(index):
        if name != INDEX and name not in out:
            out.append(name)
    return out


def rows(index: str) -> list[tuple[str, str]]:
    """(file, line) for each table line of a research README that links a file."""
    out = []
    for ln in index.splitlines():
        m = LINK.search(ln) if ln.lstrip().startswith("|") else None
        if m:
            out.append((m.group(1), ln))
    return out


def _folder(root: Path, rel: str, kind: str) -> list[str]:
    d = root / rel
    if not d.is_dir():
        return []
    out: list[str] = []
    files = sorted(p.name for p in d.glob("*.md") if p.name != INDEX)
    index = d / INDEX
    if not index.is_file():
        return [f"{rel}/: no {INDEX}; the index lists every file here (templates/{'research' if kind == 'research' else 'prior-art'}-index.md)"]
    text = read(index)
    links = listed(text)
    out += [f"{rel}/{f}: not in {rel}/{INDEX}" for f in files if f not in links]
    out += [f"{rel}/{INDEX}: lists {n}, which is not a file" for n in links if n not in files]
    if kind == "research":
        out += [f"{rel}/{INDEX}: the row for {n} states no day" for n, ln in rows(text) if not DAY.search(ln)]
    for f in files:
        body = read(d / f)
        if kind == "research":
            m = RESEARCHED.search(body)
            if not m or not _real(m.group(1)):
                out.append(f"{rel}/{f}: no `Researched YYYY-MM-DD` line (a real day)")
            if not TAG.search(body):
                out.append(f"{rel}/{f}: no claim tagged [documented], [vendor], [academic], [ours] or [inference]")
        else:
            m = NAMED.match(f) or SCANNED.search(body)
            if not m or not _real(m.group(1)):
                out.append(f"{rel}/{f}: no day in its name (YYYY-MM-DD-name.md) or on a `Scan date:` line")
    return out


def problems(root: Path | str) -> list[str]:
    root = Path(root)
    return _folder(root, RESEARCH, "research") + _folder(root, PRIOR_ART, "prior-art")


def check_research(root: Path | str) -> list[str]:
    return problems(root)


SOUND = {
    "docs/research/README.md": "# Research\n\n| File | Question | Date | Answer | Used by |\n| --- | --- | --- | --- | --- |\n"
                               "| [fees.md](fees.md) | what does it cost | 2026-10-01 | per call | `pull.py` |\n",
    "docs/research/fees.md": "# Fees\n\n- 3 cents a call [documented].\n\nResearched 2026-10-01. Kinds of claim: documented, vendor.\n",
    "docs/prior-art/README.md": "# Prior art\n\n- [2026-10-02-tools.md](2026-10-02-tools.md)\n",
    "docs/prior-art/2026-10-02-tools.md": "# Tools\n",
}

# a break -> ({file: its new text, or None to delete it}, a word its problem must hold)
FEES = SOUND["docs/research/fees.md"]
PLANTED = {
    "a research file with no row": ({"docs/research/more.md": "# More\n\nResearched 2026-10-01. [ours]\n"}, "not in docs/research/README.md"),
    "a row with no file": ({"docs/research/fees.md": None}, "which is not a file"),
    "a research README that is missing": ({"docs/research/README.md": None}, "no README.md"),
    "a row with no day": ({"docs/research/README.md": SOUND["docs/research/README.md"].replace("2026-10-01", "last week")}, "states no day"),
    "a file with no Researched day": ({"docs/research/fees.md": "# Fees\n\n3 cents [documented].\n"}, "Researched"),
    "a file with an unreal day": ({"docs/research/fees.md": FEES.replace("2026-10-01", "2026-13-01")}, "Researched"),
    "a file with no tagged claim": ({"docs/research/fees.md": "# Fees\n\n3 cents.\n\nResearched 2026-10-01.\n"}, "no claim tagged"),
    "a prior-art file with no row": ({"docs/prior-art/2026-10-03-law.md": "# Law\n"}, "not in docs/prior-art/README.md"),
    "a prior-art file with no day": ({"docs/prior-art/tools.md": "# Tools\n",
                                      "docs/prior-art/README.md": SOUND["docs/prior-art/README.md"] + "- [tools.md](tools.md)\n"},
                                     "no day in its name"),
    "a prior-art README that is missing": ({"docs/prior-art/README.md": None}, "no README.md"),
}


def _write(root: Path, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        p = root / rel
        if text is None:
            p.unlink(missing_ok=True)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def self_test() -> list[str]:
    """[] when the sound folders pass and every planted break is caught."""
    out: list[str] = []
    with tempfile.TemporaryDirectory(prefix="research-") as d:
        _write(Path(d), SOUND)
        if problems(d):
            out.append(f"sound research folders are refused: {problems(d)}")
        if problems(Path(d) / "nowhere"):
            out.append("a skill pack with neither folder is refused")
    for what, (files, needle) in PLANTED.items():
        with tempfile.TemporaryDirectory(prefix="research-") as d:
            _write(Path(d), SOUND)
            _write(Path(d), files)
            got = problems(d)
            if not any(needle in x for x in got):
                out.append(f"the research rule misses: {what} (got {got})")
    return out
