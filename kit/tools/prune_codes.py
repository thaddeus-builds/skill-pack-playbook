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
  * the scan must be trustworthy or nothing is deleted (exit 2): a source that matches no file (a mistyped folder would make every code look unemitted), a
    source file that cannot be read or does not parse (a byte-order mark or a coding cookie too: the kit's own scan reads plain UTF-8), or a `msg()` call
    whose code is not a literal is refused. Folders named `venv`, `node_modules` and `site-packages` are not read (nothing in them emits the pack's
    codes). A registry file that is a link or leads outside the pack is skipped. Each file is written whole to a new file beside it (a name nobody
    chose, so a link left at a guessable name is never written through), given the old file's mode, and renamed over the original, its line endings
    kept; another name for the same file (a hard link) keeps the old content. Two runs at once end the same as one;
  * `--dry-run` lists what would go and changes nothing.

A code that is emitted only by a call this scan cannot read (a code built at run time) would be pruned: `msg()` takes its code as a literal
for exactly this reason (`check_registry_closed` refuses a call that is not one).

Test: kit/tests/test_prune_codes.py.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import config, messages  # noqa: E402


SKIP_DIRS = frozenset({"venv", "node_modules", "site-packages"})


class Refused(Exception):
    """The scan cannot be trusted, so nothing is deleted; the message says why."""


def sources_read(root: Path, sources: list[str]) -> list[Path]:
    """The .py files the sources name. A glob that matches no file is refused (a mistyped folder would otherwise read nothing and so find every code
    unemitted), and so is a root whose own name holds a glob character that is not escaped."""
    found: list[Path] = []
    for s in sources:
        hits = sorted(Path(p) for p in glob.glob(str(Path(glob.escape(str(root))) / s), recursive=True)
                      if p.endswith(".py") and Path(p).is_file() and not SKIP_DIRS & set(Path(p).relative_to(root).parts))
        if not hits:
            raise Refused(f"the source {s!r} matches no .py file under {root}: nothing is pruned (a mistyped folder would make every code look unemitted)")
        found += hits
    return sorted(set(found))


def unemitted(root: Path, sources: list[str]) -> dict[str, list[str]]:
    """{registry file: [codes]} of the skill pack's own codes that no msg() call in `sources` emits. The pack must be bound (kit.config.use).
    Refused when a source matches nothing, a source file does not parse, or a call passes a code that is not a literal: any of those means the scan
    did not see every emitter."""
    import ast
    reg = messages.registry()
    files = sources_read(root, sources)
    for f in files:
        try:
            ast.parse(f.read_text(encoding="utf-8"), str(f))
        except (SyntaxError, UnicodeDecodeError, ValueError, RecursionError, MemoryError, OSError) as e:       # ValueError: a null byte
            raise Refused(f"{f} cannot be read as Python ({e.__class__.__name__}): its codes would look unemitted; nothing is pruned") from None
    calls = messages.msg_calls(files, root)
    loose = [where for where, c, _ in calls if c is None]
    if loose:
        raise Refused(f"{loose[0]}: a msg() call whose code is not a string literal ({len(loose)} such call(s)); nothing is pruned")
    emitted = {c for _, c, _ in calls}
    kit_dir = messages.KIT_DIR.resolve()
    root_real = root.resolve()
    out: dict[str, list[str]] = {}
    for code, row in sorted(reg.items()):
        path = Path(row["file"])
        real = path.resolve()
        # the kit's own registry files are never listed, whatever a row says of its origin; nor a file that is a link or leads outside the pack:
        # this tool deletes lines, and the kit's closure test owns the kit's
        if row.get("origin") == "kit" or code in emitted or real.is_relative_to(kit_dir):
            continue
        if path.is_symlink() or not real.is_relative_to(root_real):
            continue
        out.setdefault(row["file"], []).append(code)
    return out


def write_whole(path: Path, data: bytes) -> None:
    """`data` becomes the whole of `path`: written to a new file beside it, given the old file's mode, and renamed over it."""
    mode = path.stat().st_mode & 0o7777
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".prune-tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def prune(root: Path, sources: list[str], *, dry_run: bool = False) -> dict[str, list[str]]:
    """Remove the unemitted codes from their registry files; {file: [codes removed]}. A fragment left with only its header is deleted. Each file is
    written whole to a temporary name and renamed over the original, with its line endings kept."""
    found = unemitted(root, sources)
    if dry_run:
        return found
    for file, codes in found.items():
        path = Path(file)
        gone = set(codes)
        try:
            raw = path.read_bytes().decode("utf-8")
        except FileNotFoundError:                                       # another run took the fragment out first
            continue
        eol = "\r\n" if "\r\n" in raw else "\n"
        lines = raw.replace("\r\n", "\n").split("\n")
        kept = [ln for i, ln in enumerate(lines) if i == 0 or ln.split("\t")[0].strip() not in gone]
        body = [ln for ln in kept[1:] if ln.strip()]
        try:
            if not body and path.parent.name == messages.SKILL_PACK_FRAGMENTS and kept[0].split("\t")[0].strip() == "code":
                path.unlink(missing_ok=True)
            else:
                write_whole(path, eol.join(kept).encode("utf-8"))
        except OSError as e:
            raise Refused(f"{path} cannot be written ({e.strerror}); files before it are done, run again once it can") from None
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
    try:
        found = prune(root, sources, dry_run=a.dry_run)
    except Refused as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for file, codes in sorted(found.items()):
        print(f"  {'would remove' if a.dry_run else 'removed'} {len(codes):>3} from {Path(file).relative_to(root)}: {', '.join(codes)}")
    n = sum(len(c) for c in found.values())
    print(f"{'would remove' if a.dry_run else 'removed'} {n} unemitted code(s) from {len(found)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
