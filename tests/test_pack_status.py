"""tools/pack_status.tsv: every kit pack but base and testkit is `shared` (two or more skill
packs import it from their main branches, counted on a day by tools/consumers.py) or
`incubating` (born before its second importer, with the day by which it must have two).

The rule (CLAUDE.md, "Keep it small"): a pack may be born before its second importer, but
not for good. This file fails the day after an incubating pack's `until`, and on a pack
with no row, a row with no pack, a `shared` row with fewer than two importers, a bad date
or a bad status. Each check is first tried on a planted break, so it cannot pass by reading
nothing. The one calendar read is `today()`, injected into `problems` so the checks on the
planted table are fixed.
"""

from __future__ import annotations

import csv
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(HERE).parent
sys.path.insert(0, HERE)
sys.path.insert(0, str(ROOT))
import _t  # noqa: E402
from kit.tools import packs  # noqa: E402

TABLE = ROOT / "tools" / "pack_status.tsv"
COLUMNS = ["pack", "status", "since", "until", "consumers", "counted", "note"]
STATUSES = {"shared", "incubating"}
NEVER = set(packs.ALWAYS)                     # base and testkit: every skill pack takes them
DAY = re.compile(r"^\d{4}-\d\d-\d\d$")
MIN_SHARED = 2


def today() -> date:
    return datetime.now(timezone.utc).date()


def read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    header = rows[0].keys() if rows else path.read_text("utf-8").splitlines()[0].split("\t")
    return list(header), rows


def kit_packs() -> set[str]:
    return set(packs.table(ROOT / "kit").values()) - NEVER


def problems(header: list[str], rows: list[dict[str, str]], known: set[str], day: date,
             skill_packs: set[str] | None = None) -> list[str]:
    """What the table gets wrong, one line each; [] when every pack is accounted for. With `skill_packs` (the rows of
    tools/adoption.tsv), a consumer that is not one of them is a typo or a skill pack nobody tracks."""
    out = []
    if header != COLUMNS:
        return [f"header: {header} is not {COLUMNS}"]
    seen: dict[str, int] = {}
    for r in rows:
        pack = (r.get("pack") or "").strip()
        seen[pack] = seen.get(pack, 0) + 1
        if pack not in known:
            out.append(f"{pack}: not a kit pack (kit/packs.tsv), or one every skill pack takes")
            continue
        status = r["status"].strip()
        if status not in STATUSES:
            out.append(f"{pack}: status {status!r} is not shared or incubating")
            continue
        for col in ("since", "counted"):
            if not DAY.match(r[col].strip()):
                out.append(f"{pack}: {col} {r[col]!r} is not a day (YYYY-MM-DD)")
        names = [n for n in r["consumers"].split(",") if n.strip()]
        if len(set(names)) != len(names):
            out.append(f"{pack}: a consumer is named twice")
        for n in names:
            if skill_packs is not None and n not in skill_packs:
                out.append(f"{pack}: consumer {n} is not a row of tools/adoption.tsv")
        until = r["until"].strip()
        if status == "shared":
            if len(set(names)) < MIN_SHARED:
                out.append(f"{pack}: shared needs {MIN_SHARED} importers counted, has {len(set(names))}")
            if until:
                out.append(f"{pack}: a shared pack has no until")
        else:
            if not DAY.match(until):
                out.append(f"{pack}: incubating needs an until day (YYYY-MM-DD)")
            elif date.fromisoformat(until) < day:
                out.append(f"{pack}: incubating until {until}, which has passed: extend it with a reason, "
                           f"mark it shared with the importers tools/consumers.py counted, or move the pack "
                           f"back into the skill pack it came from")
    for pack, n in seen.items():
        if n > 1 and pack in known:
            out.append(f"{pack}: {n} rows")
    for pack in sorted(known - set(seen)):
        out.append(f"{pack}: no row; a new pack starts incubating, with an until day")
    return out


def table(text: str) -> tuple[list[str], list[dict[str, str]]]:
    lines = text.splitlines()
    rows = list(csv.DictReader(lines, delimiter="\t"))
    return lines[0].split("\t"), rows


GOOD = "\t".join(COLUMNS) + "\n" + "\n".join((
    "alpha\tshared\t2026-10-05\t\ta-skill-pack,b-skill-pack\t2026-10-26\t",
    "beta\tincubating\t2026-10-24\t2026-12-31\t\t2026-10-26\tborn for the next skill pack",
)) + "\n"
KNOWN = {"alpha", "beta"}
DAY0 = date(2026, 10, 26)


def test_the_check_sees_each_break_planted_in_a_small_table():
    assert problems(*table(GOOD), KNOWN, DAY0) == [], problems(*table(GOOD), KNOWN, DAY0)
    assert problems(*table(GOOD), KNOWN, DAY0, {"a-skill-pack", "b-skill-pack"}) == []
    assert any("not a row of tools/adoption.tsv" in p for p in problems(*table(GOOD), KNOWN, DAY0, {"a-skill-pack"}))
    breaks = {
        "header": GOOD.replace("\tnote", "\tnotes"),
        "not a kit pack": GOOD.replace("alpha\t", "gamma\t"),
        "status 'kept'": GOOD.replace("\tshared\t", "\tkept\t"),
        "since '2026/10/05'": GOOD.replace("2026-10-05", "2026/10/05"),
        "named twice": GOOD.replace("a-skill-pack,b-skill-pack", "a-skill-pack,a-skill-pack"),
        "shared needs 2 importers": GOOD.replace("a-skill-pack,b-skill-pack", "a-skill-pack"),
        "a shared pack has no until": GOOD.replace("2026-10-05\t\t", "2026-10-05\t2026-12-31\t"),
        "incubating needs an until": GOOD.replace("\t2026-12-31\t", "\t\t"),
        "which has passed": GOOD.replace("2026-12-31", "2026-10-25"),
        "2 rows": GOOD + "beta\tincubating\t2026-10-24\t2026-12-31\t\t2026-10-26\t\n",
        "no row": GOOD.replace("beta\tincubating\t2026-10-24\t2026-12-31\t\t2026-10-26\tborn for the next skill pack\n", ""),
    }
    for want, text in breaks.items():
        assert text != GOOD, want
        found = problems(*table(text), KNOWN, DAY0)
        assert any(want in p for p in found), (want, found)
    assert problems(*table(GOOD), KNOWN, date(2027, 1, 1)) == [
        "beta: incubating until 2026-12-31, which has passed: extend it with a reason, mark it shared with the "
        "importers tools/consumers.py counted, or move the pack back into the skill pack it came from"]
    assert problems(*table(GOOD), KNOWN | {"gamma"}, DAY0) == ["gamma: no row; a new pack starts incubating, with an until day"]


def test_every_kit_pack_is_shared_or_incubating_and_no_incubation_has_run_out():
    header, rows = read(TABLE)
    known = kit_packs()
    assert known, "kit/packs.tsv names no pack besides base and testkit"
    adoption = {ln.split("\t")[0] for ln in (ROOT / "tools" / "adoption.tsv").read_text("utf-8").splitlines()[1:]}
    found = problems(header, rows, known, today(), adoption)
    assert found == [], "\n".join(found)


if __name__ == "__main__":
    _t.main(globals())
