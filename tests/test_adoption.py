"""tools/adoption.tsv: each known skill pack's adoption level (conformance/INVARIANTS.md,
"Adoption levels"), the level it should reach, and the day the proofs were last run.

The table says where a skill pack stands; the commands in INVARIANTS.md say whether it is
true. This file checks what a test can: the header, a level and a target in L0 to L3 with
the target not below the level, `checked` a day that is not in the future, a next step on
every row that has a distance to cover, one row per pack, and, when the sibling checkouts
are present, that each row names a folder among them (CI has none and skips that check).
Each check is first tried on a planted break, so it cannot pass by reading nothing. The one
calendar read is `today()`, injected into `problems`.
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(HERE).parent
sys.path.insert(0, HERE)
import _t  # noqa: E402

TABLE = ROOT / "tools" / "adoption.tsv"
COLUMNS = ["pack", "level", "target", "checked", "next_step", "note"]
LEVELS = ["L0", "L1", "L2", "L3"]
DAY = re.compile(r"^\d{4}-\d\d-\d\d$")


def today() -> date:
    return datetime.now(timezone.utc).date()


def table(text: str) -> tuple[list[str], list[dict[str, str]]]:
    lines = text.splitlines()
    return lines[0].split("\t"), list(csv.DictReader(lines, delimiter="\t"))


def siblings(root: Path = ROOT) -> Path | None:
    """The folder that holds the skill packs' checkouts: the parent of the main checkout, which
    is not `root.parent` inside a worktree. None when git cannot say."""
    try:
        r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           cwd=root, capture_output=True, text=True)
    except OSError:
        return None
    return Path(r.stdout.strip()).parent.parent if r.returncode == 0 and r.stdout.strip() else None


def problems(header: list[str], rows: list[dict[str, str]], day: date, folder: Path | None) -> list[str]:
    """What the table gets wrong, one line each; [] when every row is sound."""
    if header != COLUMNS:
        return [f"header: {header} is not {COLUMNS}"]
    out = []
    seen: dict[str, int] = {}
    for r in rows:
        pack = (r.get("pack") or "").strip()
        seen[pack] = seen.get(pack, 0) + 1
        level, target = r["level"].strip(), r["target"].strip()
        if not pack or "/" in pack:
            out.append(f"{pack!r}: not a folder name")
        if level not in LEVELS:
            out.append(f"{pack}: level {level!r} is not one of {', '.join(LEVELS)}")
        if target not in LEVELS:
            out.append(f"{pack}: target {target!r} is not one of {', '.join(LEVELS)}")
        if level in LEVELS and target in LEVELS:
            if LEVELS.index(target) < LEVELS.index(level):
                out.append(f"{pack}: target {target} is below level {level}")
            elif level != target and not r["next_step"].strip():
                out.append(f"{pack}: level {level} short of target {target} needs a next_step")
        checked = r["checked"].strip()
        try:
            if not DAY.match(checked):
                raise ValueError
            if date.fromisoformat(checked) > day:
                out.append(f"{pack}: checked {checked} is in the future")
        except ValueError:
            out.append(f"{pack}: checked {checked!r} is not a day (YYYY-MM-DD)")
        if folder is not None and pack and "/" not in pack and not (folder / pack).is_dir():
            out.append(f"{pack}: no such folder among the checkouts in {folder}")
    for pack, n in seen.items():
        if n > 1:
            out.append(f"{pack}: {n} rows")
    if not rows:
        out.append("no rows")
    return out


GOOD = "\t".join(COLUMNS) + "\n" + "\n".join((
    "alpha-skill-pack\tL1\tL3\t2026-10-26\tdrop the pack it does not import\tkit 0.33.1",
    "beta-skill-pack\tL0\tL0\t2026-10-26\t\ta library",
)) + "\n"
DAY0 = date(2026, 10, 26)


def test_the_check_sees_each_break_planted_in_a_small_table():
    assert problems(*table(GOOD), DAY0, None) == [], problems(*table(GOOD), DAY0, None)
    breaks = {
        "header": GOOD.replace("\tnote", "\tnotes"),
        "level 'L4'": GOOD.replace("\tL1\t", "\tL4\t"),
        "level 'l1'": GOOD.replace("\tL1\t", "\tl1\t"),
        "target ''": GOOD.replace("\tL3\t", "\t\t"),
        "target L0 is below level L1": GOOD.replace("\tL1\tL3\t", "\tL1\tL0\t"),
        "needs a next_step": GOOD.replace("drop the pack it does not import", ""),
        "checked '2026/10/26'": GOOD.replace("2026-10-26\tdrop", "2026/10/26\tdrop"),
        "checked '2026-13-40'": GOOD.replace("2026-10-26\tdrop", "2026-13-40\tdrop"),
        "in the future": GOOD.replace("2026-10-26\tdrop", "2026-10-27\tdrop"),
        "2 rows": GOOD + "alpha-skill-pack\tL1\tL1\t2026-10-26\t\t\n",
        "not a folder name": GOOD.replace("beta-skill-pack", "../beta-skill-pack"),
        "no rows": "\t".join(COLUMNS) + "\n",
    }
    for want, text in breaks.items():
        assert text != GOOD, want
        found = problems(*table(text), DAY0, None)
        assert any(want in p for p in found), (want, found)


def test_a_row_names_a_folder_among_the_checkouts_when_there_are_checkouts():
    with _t.tmpdir() as d:
        folder = Path(d)
        (folder / "alpha-skill-pack").mkdir()
        found = problems(*table(GOOD), DAY0, folder)
        assert found == [f"beta-skill-pack: no such folder among the checkouts in {folder}"], found
        (folder / "beta-skill-pack").mkdir()
        assert problems(*table(GOOD), DAY0, folder) == []
        assert problems(*table(GOOD), DAY0, None) == [], "no checkouts: the folder check is skipped"


def test_siblings_is_the_parent_of_the_main_checkout_even_from_a_worktree():
    def git(cwd: Path, *a: str) -> None:
        subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    with _t.tmpdir() as d:
        main = Path(d).resolve() / "playbook"
        main.mkdir()
        git(main, "init", "-q")
        (main / "f").write_text("x")
        git(main, "add", "f")
        git(main, "commit", "-q", "-m", "x")
        wt = main / ".claude" / "worktrees" / "w"
        git(main, "worktree", "add", "-q", str(wt))
        assert siblings(main) == main.parent
        assert siblings(wt) == main.parent, siblings(wt)
    with _t.tmpdir() as d:
        assert siblings(Path(d)) is None, "not a repository"


def test_every_known_skill_pack_has_a_sound_row():
    header, rows = table(TABLE.read_text("utf-8"))
    folder = siblings()
    if folder is not None and not any((folder / r["pack"]).is_dir() for r in rows):
        folder = None                      # no checkouts here (CI): only the table's own shape
    found = problems(header, rows, today(), folder)
    assert found == [], "\n".join(found)


if __name__ == "__main__":
    _t.main(globals())
