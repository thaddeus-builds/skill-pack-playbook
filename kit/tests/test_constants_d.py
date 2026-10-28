#!/usr/bin/env python3
"""The engines' default rows (kit/constants.d/<module>.tsv) stay true to the engines that read them.

  1. Each file is named for a kit module, and a row's `reads` names only modules of that module's own pack (a skill pack that
     took `creative` and not `ads-core` loads its rows without the other's).
  2. Every `reads` target exists: `module.Class.field` is a field of that dataclass, `module.function.arg` a parameter of that
     function, `module.function` a function whose source names the row (it reads `k["<name>"]`). A name no engine reads is
     refused, so a row cannot outlive its engine.
  3. Every parameter of an engine's `Params` that has no default in code is read by a row, or is listed below as derived from
     the pack's own tables (its inputs ship with the compute that derives it, not before).
  4. Where the engine has its own default, the row says the same: the kit has one answer to "what is the engines' default".
  5. A pack's rows load alone, and a name is defined once across the kit.
"""

import dataclasses
import importlib
import inspect
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import registry  # noqa: E402
from kit.registry import Thresholds, read_tsv  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402
from kit.tools import packs  # noqa: E402

KIT = Path(__file__).resolve().parents[1]
FILES = registry.kit_defaults()
TABLE = packs.table(KIT)
COLUMNS = ["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why", "reads"]

# Params fields the pack derives from its own tables; the rows that feed that derivation ship with the compute that does it.
DERIVED = {
    ("creative_life", "reach_impressions"): "from the account's reach history",
    ("creative_life", "reach_floor"): "a share of reach_impressions",
    ("creative_life", "doubt_spend"): "from the account's cost per conversion",
    ("creative_life", "weak_signal"): "a percentile of the account's hook rates",
}
# Engines whose parameters are a dataclass `Params`.
ENGINES = ("lifecycle", "allocation", "creative_life", "creative_demand", "wallets")


def rows() -> list[tuple[Path, dict]]:
    return [(f, r) for f in FILES for r in read_tsv(f, COLUMNS, id_col="name")]


def resolve(reads: str, name: str):
    """(kind, default or None): what `module.X.y` points at, or an error string."""
    parts = reads.split(".")
    mod = importlib.import_module("kit." + parts[0])
    if len(parts) == 2:
        fn = getattr(mod, parts[1], None)
        if not callable(fn):
            return "missing", f"{reads}: no such function"
        return ("literal", None) if f'"{name}"' in inspect.getsource(fn) else ("missing", f"{reads} never names {name}")
    if len(parts) != 3:
        return "missing", f"{reads}: not module.Class.field, module.function.arg or module.function"
    obj = getattr(mod, parts[1], None)
    if dataclasses.is_dataclass(obj):
        f = {f.name: f for f in dataclasses.fields(obj)}.get(parts[2])
        if f is None:
            return "missing", f"{reads}: {parts[1]} has no field {parts[2]}"
        return "field", None if f.default is dataclasses.MISSING else f.default
    if callable(obj):
        p = inspect.signature(obj).parameters.get(parts[2])
        if p is None:
            return "missing", f"{reads}: {parts[1]}() has no parameter {parts[2]}"
        return "arg", None if p.default is inspect.Parameter.empty else p.default
    return "missing", f"{reads}: no such class or function"


def test_files() -> None:
    print("[1] files and their packs")
    check("the kit ships default rows", len(FILES) >= 8, FILES)
    stems = [f.stem for f in FILES]
    check("each file is named for a kit module", all(s in TABLE for s in stems), [s for s in stems if s not in TABLE])
    check("packs.module_of puts each file in its module's pack",
          all(packs.module_of(f"constants.d/{s}.tsv", set(TABLE)) == s for s in stems))
    bad = []
    for f, r in rows():
        for target in r["reads"].split():
            if TABLE.get(target.split(".")[0]) != TABLE[f.stem]:
                bad.append(f"{r['name']}: {target} is in pack {TABLE.get(target.split('.')[0])}, the file is {TABLE[f.stem]}")
    check("a row reads only modules of its own pack", not bad, bad)


def test_reads() -> None:
    print("[2] every row is read by an engine")
    bad, seen = [], {}
    for f, r in rows():
        if not r["reads"].strip():
            bad.append(f"{r['name']}: no `reads`")
        for target in r["reads"].split():
            kind, detail = resolve(target, r["name"])
            if kind == "missing":
                bad.append(f"{r['name']}: {detail}")
            seen.setdefault(target, []).append(r["name"])
    check("every `reads` target exists and a row is not left without its engine", not bad, bad)
    twice = {t: n for t, n in seen.items() if len(n) > 1 and t.count(".") == 2}
    check("a parameter is fed by one row", not twice, twice)


def test_params_covered() -> None:
    print("[3] every engine parameter has a row or is derived")
    read = {t for _, r in rows() for t in r["reads"].split()}
    missing = []
    for e in ENGINES:
        cls = getattr(importlib.import_module("kit." + e), "Params")
        for f in dataclasses.fields(cls):
            if f.default is dataclasses.MISSING and f"{e}.Params.{f.name}" not in read and (e, f.name) not in DERIVED:
                missing.append(f"{e}.Params.{f.name}")
    check("no engine parameter without a default in code is left without a row", not missing, missing)
    stale = [f"{e}.{n}" for (e, n) in DERIVED if f"{e}.Params.{n}" in read]
    check("a derived parameter is not also a row", not stale, stale)


def test_same_default() -> None:
    print("[4] a row agrees with the engine's own default")
    diff = []
    for _, r in rows():
        for target in r["reads"].split():
            kind, default = resolve(target, r["name"])
            if kind in ("field", "arg") and default is not None and float(r["default"]) != float(default):
                diff.append(f"{r['name']} = {r['default']} but {target} defaults to {default}")
    check("every row's default equals the default in code where there is one", not diff, diff)


def test_load_alone() -> None:
    print("[5] a pack's rows load alone")
    empty = Path(tmp_dir("constants-d-")) / "constants.tsv"
    empty.write_text("\t".join(["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why"]) + "\n",
                     encoding="utf-8")
    problems = []
    for pack in sorted(set(TABLE.values())):
        mine = [f for f in FILES if TABLE[f.stem] == pack]
        if mine:
            try:
                Thresholds(empty, defaults=mine)
            except Exception as e:  # noqa: BLE001
                problems.append(f"{pack}: {e}")
    check("each pack's default files load without any other pack's", not problems, problems)
    names = [r["name"] for _, r in rows()]
    check("a name is defined once across the kit", len(names) == len(set(names)))
    th = Thresholds(empty)
    check("a skill pack with an empty file gets every engine default",
          set(names) <= set(th.names()) and all(th.origin(n) == "kit" for n in names))


def main() -> int:
    _shop.use()
    for fn in (test_files, test_reads, test_params_covered, test_same_default, test_load_alone):
        fn()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
