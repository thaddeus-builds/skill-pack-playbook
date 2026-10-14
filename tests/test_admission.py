"""The admission rule (CLAUDE.md, docs/kit-and-tools.md), as checks that fail when it is broken.

  * `base` is what makes a write safe and checkable. Its modules are pinned below: adding one is
    a visible edit to this list, made on purpose, once two harnesses import the module.
  * every pack in kit/ other than base and testkit names who imports it: a ROADMAP Links line
    `pack <name>: <harness> ...`, or a Parked row for it with a `Review on` day.
  * code with no importer lives in _parked/<pack>/: each folder has a Parked row and a README
    line; none of its modules is also in kit/; nothing outside _parked/ imports one (the AST,
    not the words, so a doc check that names a module is not an import); vendor.py copies none
    of it; and a Review-on day is within 120 days of its row.
Each check is first tried on a broken input, so it cannot pass by reading nothing.
"""

from __future__ import annotations

import ast
import datetime
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import _t  # noqa: E402
from kit.guards import roadmap  # noqa: E402
from kit.tools import packs, vendor  # noqa: E402

BASE = (
    "__init__ config contract dates messages paths db schema_base human market registry raw facts decisions "
    "pending queue execute write_guard cli verbs doctor env auth runner stories single_instance atomic"
).split()
ROADMAP = open(os.path.join(ROOT, "ROADMAP.md"), encoding="utf-8").read()
PARKED = os.path.join(ROOT, "_parked")
REVIEW_ON = re.compile(r"Review on (\d{4}-\d{2}-\d{2})")
ROW_DATE = re.compile(r"^\[P\d+\]\s+(\d{4}-\d{2}-\d{2})")
SKIP = {".git", "_parked", "node_modules", "__pycache__"}


KIT = Path(ROOT) / "kit"


def table() -> dict[str, str]:
    return packs.table(KIT)


def pack_problems(pack_names: list[str], text: str) -> list[str]:
    """Packs (other than base and testkit) with neither a Links line `pack <name>:` nor a Parked row that names them
    with a Review-on day."""
    secs = roadmap.sections(text)
    links = " \n".join(secs.get("Links", []))
    parked = secs.get("Parked", [])
    out = []
    for name in pack_names:
        has_link = re.search(rf"^pack {re.escape(name)}:\s*\S", links, re.M) is not None
        has_row = any(f"pack `{name}`" in r and REVIEW_ON.search(r) for r in parked)
        if not (has_link or has_row):
            out.append(name)
    return out


def parked_dirs() -> list[str]:
    return sorted(d for d in os.listdir(PARKED) if os.path.isdir(os.path.join(PARKED, d))) if os.path.isdir(PARKED) else []


def parked_modules(pack: str) -> list[str]:
    """Top-level module names in _parked/<pack>/ (not tests, not message-code fragments)."""
    d = os.path.join(PARKED, pack)
    return sorted(f[:-3] for f in os.listdir(d) if f.endswith(".py"))


def imports_of(path: str) -> set[str]:
    """Names under `kit` that a Python file imports: `from kit import x` -> x, `import kit.x` / `from kit.x import y` -> x."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except (SyntaxError, UnicodeDecodeError):
        return set()
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[1] for a in n.names if a.name.startswith("kit.")}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            if n.module == "kit":
                out |= {a.name for a in n.names}
            elif n.module.startswith("kit."):
                out.add(n.module.split(".")[1])
    return out


def py_files() -> list[str]:
    out = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP]
        out += [os.path.join(dp, f) for f in fn if f.endswith(".py")]
    return out


def test_base_is_the_pinned_list():
    base = sorted(m for m, p in table().items() if p == "base")
    assert base == sorted(BASE), (f"base changed: added {sorted(set(base) - set(BASE))}, removed "
                                  f"{sorted(set(BASE) - set(base))}. A module moves to base once two harnesses import "
                                  "it from code merged to their main branches (python3 tools/consumers.py); edit BASE "
                                  "here then, and say which two in the pull request")
    assert sorted(set(BASE) | {"x"}) != base                      # the check sees a module that is not there


def test_every_pack_names_who_imports_it_or_is_reviewed_by_a_day():
    named = sorted(set(table().values()) - set(packs.ALWAYS))
    assert pack_problems(named, ROADMAP) == [], pack_problems(named, ROADMAP)
    assert pack_problems(["nobody"], ROADMAP) == ["nobody"]
    assert pack_problems(["nobody"], ROADMAP.replace("## Links\n", "## Links\n- pack nobody: video-ads imports it\n")) == []
    row = "## Parked\n- [P9] 2026-10-14 pack `nobody` stays. Review on 2027-01-13\n"
    assert pack_problems(["nobody"], ROADMAP.replace("## Parked\n", row)) == []
    assert pack_problems(["nobody"], ROADMAP.replace("## Parked\n", row.replace("Review on", "Later on"))) == ["nobody"]


def test_parked_code_is_set_aside_and_imported_by_nothing():
    kit_modules = set(packs.modules(KIT))
    readme = open(os.path.join(PARKED, "README.md"), encoding="utf-8").read()
    parked_rows = roadmap.sections(ROADMAP).get("Parked", [])
    mods = {}
    for pack in parked_dirs():
        assert f"`{pack}/`" in readme, f"_parked/README.md does not list {pack}/"
        assert any(f"_parked/{pack}/" in r and REVIEW_ON.search(r) for r in parked_rows), \
            f"ROADMAP has no Parked row with a Review on day for _parked/{pack}/"
        for m in parked_modules(pack):
            assert m not in kit_modules, f"{m} is in kit/ and in _parked/{pack}/"
            mods[m] = pack
    assert mods, "_parked/ holds no module: delete the folder and this check, or park something"
    bad = [f"{os.path.relpath(f, ROOT)} imports kit.{m} (parked in {mods[m]})"
           for f in py_files() for m in sorted(imports_of(f) & set(mods))]
    assert bad == [], bad
    probe = os.path.join(HERE, "_probe_parked_import.py")      # the scan sees an import it must refuse
    try:
        open(probe, "w").write(f"from kit import {sorted(mods)[0]}\n")
        assert imports_of(probe) == {sorted(mods)[0]}
        open(probe, "w").write("x = 'kit.autonomy'\n")        # a name in a string is not an import
        assert imports_of(probe) == set()
    finally:
        if os.path.exists(probe):
            os.remove(probe)


def test_the_vendor_tool_copies_none_of_it():
    import shutil
    import tempfile
    dest = Path(tempfile.mkdtemp()) / "kit"
    try:
        vendor.sync(KIT, dest, {})
        files = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
        mods = {m for pack in parked_dirs() for m in parked_modules(pack)}
        leaked = sorted(f for f in files if "_parked" in f or f[:-3] in mods)
        assert leaked == [], leaked
        assert "human.py" in files                                # it did copy the kit
    finally:
        shutil.rmtree(dest.parent, ignore_errors=True)


def test_a_review_day_is_near():
    late = []
    for r in roadmap.sections(ROADMAP).get("Parked", []):
        d, m = ROW_DATE.match(r), REVIEW_ON.search(r)
        if m and d and (datetime.date.fromisoformat(m.group(1)) - datetime.date.fromisoformat(d.group(1))).days > 120:
            late.append(r.split(" ", 1)[0])
    assert late == [], f"{late}: a Review on day is more than 120 days after its row"
    far = "- [P9] 2026-10-14 pack `x`. Review on 2028-01-01"
    assert ROW_DATE.match(far[2:]) and (datetime.date(2028, 1, 1) - datetime.date(2026, 10, 14)).days > 120


if __name__ == "__main__":
    _t.main(globals())
