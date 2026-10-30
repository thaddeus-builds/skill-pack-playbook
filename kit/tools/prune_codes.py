#!/usr/bin/env python3
"""Delete the message codes a skill pack registers and nothing emits.

    python3 scripts/kit/tools/prune_codes.py [--root PACK] [--sources GLOB ...] [--dry-run]

Retiring a subsystem leaves its message codes behind, and `messages.check_registry_closed` reports each as "registered but no msg() call
emits it", one line at a time (about 100 across ten fragment files when a subsystem went; issue #136). This removes exactly those rows, and
nothing else:

  * a code is pruned when it is in the skill pack's own registry (its `[ssot].message_codes` file or a fragment under `<ssot dir>/message_codes.d/`)
    and no `msg()` call in the sources emits it; a code of the kit is never touched, and no file inside the kit's folder is (the kit's own closure test
    owns those);
  * a fragment left with only its header is deleted; the pack's main registry file keeps its header;
  * the sources are globs relative to the root, `**` recursive; default: every `.py` file under the root (hidden folders aside), tests included, so a
    pack whose code lives outside its scripts folder is read whole and a code is pruned only when nothing anywhere emits it. Name fewer to prune more;
  * `--dry-run` lists what would go and changes nothing.

A code that is emitted only by a call this scan cannot read (a code built at run time) would be pruned: `msg()` takes its code as a literal
for exactly this reason (`check_registry_closed` refuses a call that is not one).

Test: kit/tests/test_prune_codes.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import config, messages  # noqa: E402


def unemitted(root: Path, sources: list[str]) -> dict[str, list[str]]:
    """{registry file: [codes]} of the skill pack's own codes that no msg() call in `sources` emits. The pack must be bound (kit.config.use)."""
    import glob
    reg = messages.registry()
    files = sorted({Path(p) for s in sources for p in glob.glob(str(root / s), recursive=True) if p.endswith(".py")})
    emitted = {c for _, c, _ in messages.msg_calls(files, root) if c}
    kit_dir = messages.KIT_DIR.resolve()
    out: dict[str, list[str]] = {}
    for code, row in sorted(reg.items()):
        # the kit's own registry files are never listed, whatever a row says of its origin: this tool deletes lines, and the kit's closure test owns those
        if row.get("origin") != "kit" and code not in emitted and not Path(row["file"]).resolve().is_relative_to(kit_dir):
            out.setdefault(row["file"], []).append(code)
    return out


def prune(root: Path, sources: list[str], *, dry_run: bool = False) -> dict[str, list[str]]:
    """Remove the unemitted codes from their registry files; {file: [codes removed]}. A fragment left with only its header is deleted."""
    found = unemitted(root, sources)
    if dry_run:
        return found
    for file, codes in found.items():
        path = Path(file)
        gone = set(codes)
        lines = path.read_text(encoding="utf-8").split("\n")
        kept = [ln for i, ln in enumerate(lines) if i == 0 or ln.split("\t")[0].strip() not in gone]
        body = [ln for ln in kept[1:] if ln.strip()]
        if not body and path.parent.name == messages.SKILL_PACK_FRAGMENTS:
            path.unlink()
        else:
            path.write_text("\n".join(kept), encoding="utf-8")
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Delete the message codes a skill pack registers and nothing emits.")
    ap.add_argument("--root", type=Path, default=None, help="the skill pack (default: the one the kit is vendored in)")
    ap.add_argument("--sources", nargs="*", help="globs of the .py files that may emit, relative to the root")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    cfg = config.use(a.root) if a.root else config.config()
    root = cfg.root
    sources = a.sources or ["**/*.py"]
    found = prune(root, sources, dry_run=a.dry_run)
    for file, codes in sorted(found.items()):
        print(f"  {'would remove' if a.dry_run else 'removed'} {len(codes):>3} from {Path(file).relative_to(root)}: {', '.join(codes)}")
    n = sum(len(c) for c in found.values())
    print(f"{'would remove' if a.dry_run else 'removed'} {n} unemitted code(s) from {len(found)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
