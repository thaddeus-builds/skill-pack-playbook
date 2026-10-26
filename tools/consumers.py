#!/usr/bin/env python3
"""Which kit modules the skill packs import: the count behind "two skill packs
import it" (move to base) and "no skill pack imports it" (delete), CLAUDE.md.

    python3 tools/consumers.py SKILL_PACK... [--json]

For each skill pack it reads the Python files of its own code (not the
vendored kit, not hidden folders, not any tests/ folder: a test's import is not a use) and lists the kit modules
they import, lazy imports included. A module nobody imports directly but
another module that is imported pulls in is `via` that module. Modules of the
`testkit` pack are left out: every skill pack's tests reach them.

Only merged code counts (docs/history/restructure-2026-10.md, decision 4): point it at a checkout of
the skill pack's main branch, not a feature branch. A skill pack that does not
vendor the kit has no imports to count and says so.

Read-only. Stdlib only. Test: tests/test_consumers.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

PLAYBOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLAYBOOK))
from kit.tools import packs  # noqa: E402

KIT = PLAYBOOK / "kit"


def scripts_dir(skill_pack: Path) -> str:
    try:
        raw = tomllib.loads((skill_pack / "skill-pack.toml").read_text("utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return "scripts"
    return str(raw.get("skill_pack", {}).get("scripts_dir") or "scripts")


def own_imports(sp: Path, dest: Path, known: set[str]) -> dict[str, list[str]]:
    """{kit module: [files]} for the skill pack's production code: not the vendored kit, hidden
    folders, virtual environments or any tests/ folder (a test's import is not a use)."""
    out: dict[str, list[str]] = {}
    for p in sorted(sp.rglob("*.py")):
        rel = p.relative_to(sp)
        if (packs.SKIP_DIRS | {"tests"}) & set(rel.parts) or any(x.startswith(".") for x in rel.parts[:-1]) \
                or dest == p or dest in p.parents:
            continue
        try:
            found = packs.imports(p.read_text("utf-8"), known)
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        for m in found:
            out.setdefault(m, []).append(rel.as_posix())
    return out


def reached(direct: set[str], kit_imports: dict[str, set[str]]) -> dict[str, str]:
    """{module: the directly imported module that pulls it in} for the rest of the closure."""
    out: dict[str, str] = {}
    for root in sorted(direct):
        todo = list(kit_imports.get(root, ()))
        while todo:
            m = todo.pop()
            if m in direct or m in out:
                continue
            out[m] = root
            todo.extend(kit_imports.get(m, ()))
    return out


def report(skill_packs: list[Path]) -> dict:
    table = packs.table(KIT)
    known = set(table)
    kit_imports = {m: packs.imports((KIT / (m.replace(".", "/") + ".py")).read_text("utf-8"), known) - {m}
                   for m in known}
    per: dict[str, dict] = {}
    for sp in skill_packs:
        dest = sp / scripts_dir(sp) / "kit"
        direct = own_imports(sp, dest, known)
        per[sp.name] = {"vendors_the_kit": dest.is_dir(),
                        "direct": {m: len(fs) for m, fs in sorted(direct.items())},
                        "via": reached(set(direct), kit_imports)}
    modules = {}
    for m in sorted(known):
        if table[m] == "testkit":
            continue
        modules[m] = {"pack": table[m],
                      "direct": [n for n, d in per.items() if m in d["direct"]],
                      "via": {n: d["via"][m] for n, d in per.items() if m in d["via"]}}
    return {"skill_packs": per, "modules": modules}


def render(doc: dict) -> str:
    out = []
    for name, d in doc["skill_packs"].items():
        out.append(f"{name}: {'vendors the kit' if d['vendors_the_kit'] else 'does not vendor the kit'}, "
                   f"{len(d['direct'])} kit module(s) imported directly")
    out.append("")
    out.append(f"{'module':<18}{'pack':<12}imported by")
    for m, d in doc["modules"].items():
        who = ", ".join(d["direct"]) or ""
        via = ", ".join(f"{n} via {r}" for n, r in d["via"].items())
        out.append(f"{m:<18}{d['pack']:<12}{'; '.join(x for x in (who, via) if x) or 'no one'}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Which kit modules the skill packs import.")
    ap.add_argument("skill_pack", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    missing = [str(p) for p in a.skill_pack if not p.is_dir()]
    if missing:
        print("not a folder: " + ", ".join(missing), file=sys.stderr)
        return 2
    doc = report([p.resolve() for p in a.skill_pack])
    print(json.dumps(doc, indent=2) if a.json else render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
