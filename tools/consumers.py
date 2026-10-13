#!/usr/bin/env python3
"""Who imports which kit module, counted from the harnesses' own code.

    python3 tools/consumers.py HARNESS... [--json]

The admission rule (CLAUDE.md, docs/kit-and-tools.md) is a count: a module
moves to `base` once two harnesses import it from code merged to their main
branches, and a module nobody imports is a candidate for deletion. This is
the count, read from the checkouts you name, not from a hand-kept table.

For each harness it reads `harness.toml` for `scripts_dir`, finds the vendored
kit at `<scripts_dir>/kit/` (or `kit/` when `scripts_dir = "."`), and lists
every kit module that the harness's own Python code imports, lazy imports
included (`kit.tools.packs.harness_imports`, the same scan `vendor.py` uses to
refuse removing a module a harness needs). A file under a `tests` folder or
named `test_*` counts as a test, never as use.

Per kit module it prints the pack, the harnesses that use it in production,
the harnesses that only test it, and a verdict:

  * `shared`  two or more harnesses use it in production: it belongs in `base`;
  * `one`     one harness uses it: it stays in its pack;
  * `none`    no harness uses it in production: a candidate for deletion.

The summary lines list the packs other than `base`: `base` is what the scaffold
skeleton runs, so a `base` module no harness imports by name is still in use.

Read what it reads: a checkout of each harness's main branch. An unmerged
branch is not use (RESTRUCTURE.md, decision 4); a harness that keeps its own
copy of a module counts for nothing here. Read-only. Stdlib only.
Test: tests/test_consumers.py.
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


def is_test(rel: str) -> bool:
    parts = rel.split("/")
    return "tests" in parts[:-1] or parts[-1].startswith("test_")


def kit_dest(harness: Path) -> Path:
    try:
        h = tomllib.loads((harness / "harness.toml").read_text("utf-8")).get("harness", {})
    except (OSError, tomllib.TOMLDecodeError):
        h = {}
    scripts = harness / str(h.get("scripts_dir") or "scripts")
    return (scripts / "kit").resolve() if scripts.resolve() != harness.resolve() \
        else (harness / "kit").resolve()


def scan(harness: Path, known: set[str]) -> dict[str, dict[str, int]]:
    """{module: {"prod": n files, "test": n files}} for one harness checkout."""
    out: dict[str, dict[str, int]] = {}
    found = packs.harness_imports(harness.resolve(), kit_dest(harness), known)
    for module, files in found.items():
        row = out.setdefault(module, {"prod": 0, "test": 0})
        for f in files:
            row["test" if is_test(f) else "prod"] += 1
    return out


def report(harnesses: list[Path], kit: Path = PLAYBOOK / "kit") -> list[dict]:
    table = packs.table(kit)
    known = set(table)
    per = {h.name: scan(h, known) for h in harnesses}
    rows = []
    for module in sorted(table, key=lambda m: (table[m], m)):
        if table[module] == "testkit":
            continue
        prod = sorted(n for n, s in per.items() if s.get(module, {}).get("prod"))
        test = sorted(n for n, s in per.items() if s.get(module, {}).get("test") and n not in prod)
        rows.append({"module": module, "pack": table[module], "prod": prod, "test_only": test,
                     "verdict": "shared" if len(prod) >= 2 else "one" if prod else "none"})
    return rows


def render(rows: list[dict], harnesses: list[str]) -> str:
    out = [f"harnesses read: {', '.join(harnesses)}", ""]
    out.append(f"{'module':<18}{'pack':<12}{'verdict':<8}production / test only")
    for r in rows:
        out.append(f"{r['module']:<18}{r['pack']:<12}{r['verdict']:<8}"
                   f"{', '.join(r['prod']) or '-'} / {', '.join(r['test_only']) or '-'}")
    for verdict, hint in (("shared", "belong in base"), ("none", "no production importer")):
        names = [r["module"] for r in rows if r["verdict"] == verdict and r["pack"] != "base"]
        out += ["", f"{verdict} ({hint}): {', '.join(names) or '-'}"]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("harness", nargs="+")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    harnesses = [Path(h).expanduser() for h in args.harness]
    for h in harnesses:
        if not h.is_dir():
            print(f"error: {h} is not a directory", file=sys.stderr)
            return 2
    rows = report(harnesses)
    if args.json:
        print(json.dumps({"harnesses": [h.name for h in harnesses], "modules": rows}, indent=2))
    else:
        print(render(rows, [h.name for h in harnesses]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
