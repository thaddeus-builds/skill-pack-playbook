"""A session reads ROADMAP.md and CHANGELOG.md before it starts, so a long row costs
every session its context (review 2026-11, F7; Stage 6). Two caps, each held by a check
that fails when the rule is broken:

  * a ROADMAP row is at most ROW_MAX characters. The rows already longer when the cap
    came are listed in `tools/doc_caps.tsv` with the length they had; such a row may only
    get shorter, and its line goes once it fits. The detail lives in the pull request and
    the issue the row links.
  * a CHANGELOG entry is at most ENTRY_MAX characters, from the first version after
    FIRST_CAPPED on (`[Unreleased]` included). Older entries stay as written.
"""

from __future__ import annotations

import os
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _t  # noqa: E402

ROW_MAX = 400
ENTRY_MAX = 600
FIRST_CAPPED = (0, 51, 0)      # versions after this one are read; 0.51.0 and older stay as written
BASELINE = os.path.join(ROOT, "tools", "doc_caps.tsv")

ROW = re.compile(r"^- \[([A-Z]\d+)\] ", re.M)
HEAD = re.compile(r"^## \[([^\]]+)\]", re.M)


def roadmap_rows(text: str) -> dict[str, int]:
    """id -> length in characters of each `- [ID] ...` item (an item is one line)."""
    return {m.group(1): len(text[m.start():].split("\n", 1)[0]) for m in ROW.finditer(text)}


def baseline(text: str) -> dict[str, int]:
    out = {}
    for line in text.splitlines():
        if line.strip() and not line.startswith("#"):
            rid, n = line.split("\t")[:2]
            out[rid] = int(n)
    return out


def row_problems(rows: dict[str, int], grandfathered: dict[str, int]) -> list[str]:
    p = []
    for rid, n in rows.items():
        cap = max(ROW_MAX, grandfathered.get(rid, 0))
        if n > cap:
            p.append(f"ROADMAP [{rid}] is {n} characters, the cap is {cap}: shorten the row; the detail lives in the pull request or issue it links")
    for rid, n in grandfathered.items():
        if rid not in rows:
            p.append(f"tools/doc_caps.tsv lists [{rid}], which ROADMAP no longer has: delete its line")
        elif rows[rid] <= ROW_MAX:
            p.append(f"tools/doc_caps.tsv lists [{rid}], which now fits in {ROW_MAX}: delete its line")
    return p


def changelog_entries(log: str) -> list[tuple[str, str]]:
    """(version, entry) for every bullet of the sections after FIRST_CAPPED, an entry being a
    column-0 bullet with the indented lines that follow it."""
    out = []
    parts = re.split(r"^## \[([^\]]+)\].*$", log, flags=re.M)
    for name, body in zip(parts[1::2], parts[2::2]):
        if name != "Unreleased":
            if not re.fullmatch(r"\d+\.\d+\.\d+", name) or tuple(map(int, name.split("."))) <= FIRST_CAPPED:
                continue
        entry = None
        for line in body.split("\n"):
            if line.startswith("- "):
                entry and out.append((name, entry))
                entry = line
            elif entry is not None and line.startswith((" ", "\t")) and line.strip():
                entry += "\n" + line
            else:
                entry and out.append((name, entry))
                entry = None
        entry and out.append((name, entry))
    return out


def entry_problems(log: str) -> list[str]:
    return [f"CHANGELOG [{v}] entry is {len(e)} characters, the cap is {ENTRY_MAX}: {e[:60]}..."
            for v, e in changelog_entries(log) if len(e) > ENTRY_MAX]


ROADMAP = open(os.path.join(ROOT, "ROADMAP.md"), encoding="utf-8").read()
CHANGELOG = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()


def test_a_roadmap_row_fits_its_cap():
    got = row_problems(roadmap_rows(ROADMAP), baseline(open(BASELINE, encoding="utf-8").read()))
    assert got == [], "\n".join(got)


def test_the_row_check_refuses_a_long_row_a_grown_row_and_a_stale_line():
    fit = {"X1": 100, "X2": 450}
    assert row_problems(fit, {"X2": 450}) == []
    assert row_problems({"X1": ROW_MAX + 1}, {}), "a new row over the cap"
    assert row_problems({"X2": 451}, {"X2": 450}), "a listed row grown"
    assert row_problems({"X2": 450}, {"X2": 450, "X9": 500}), "a line for a row that is gone"
    assert row_problems({"X2": ROW_MAX}, {"X2": 450}), "a line for a row that now fits"
    assert row_problems({"X2": 449}, {"X2": 450}) == [], "a listed row that got shorter is fine"
    assert roadmap_rows("- [X1] 2026-11-05 abc\n- [D2] x\n") == {"X1": 21, "D2": 8}


def test_a_new_changelog_entry_fits_its_cap():
    got = entry_problems(CHANGELOG)
    assert got == [], "\n".join(got)


def test_the_entry_check_reads_new_entries_only():
    long = "- " + "x" * ENTRY_MAX
    new = f"## [Unreleased]\n\n### Kit\n{long}\n- Skill packs: nothing\n"
    assert entry_problems(new), "an Unreleased entry over the cap"
    assert entry_problems(f"## [0.52.0] - 2026-11-06\n{long}\n"), "a version after the cutoff"
    assert entry_problems(f"## [0.51.0] - 2026-11-05\n{long}\n") == [], "the cutoff version stays as written"
    assert entry_problems(f"## [0.40.0] - 2026-10-01\n{long}\n") == [], "an old entry stays as written"
    assert entry_problems("## [Unreleased]\n- " + "x" * (ENTRY_MAX - 2) + "\n") == []
    wrapped = "## [Unreleased]\n- " + "x" * 300 + "\n  " + "y" * 300 + "\n"
    assert entry_problems(wrapped), "indented lines belong to their entry"
    two = "## [Unreleased]\n- " + "x" * 300 + "\n- " + "y" * 300 + "\n"
    assert entry_problems(two) == [], "two short bullets are two entries"


if __name__ == "__main__":
    _t.main(globals())
