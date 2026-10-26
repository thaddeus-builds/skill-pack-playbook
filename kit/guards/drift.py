"""A vendored kit or console is a plain copy nobody edits in place.

kit/tools/vendor.py copies the playbook's kit/ to <skill-pack>/<scripts_dir>/
kit/ and console/ to <skill-pack>/console/, and writes a MANIFEST.sha256 in
each (kit/tools/manifest.py). A fix goes upstream first and is then
re-vendored, so:

  * `check_vendored(dir)`: every file under `dir` matches its
    MANIFEST.sha256 (a changed, added or removed file is named), and its
    VERSION is present, non-empty and covered by the manifest;
  * `check_skill_pack(root)`: the skill pack has a vendored kit, both copies
    (the console when present) pass check_vendored, and the console's
    VERSION equals the kit's: they are vendored together;
  * `behind(root)`: a hint, never a failure. When skill-pack.toml names a
    playbook checkout (`[kit] playbook = "../skill-pack-playbook"`, relative to
    the skill pack or absolute) whose kit/VERSION is more than two minor
    versions ahead of the vendored one, it returns `behind: kit X.Y.Z,
    playbook Z.Y.X`; check_drift() and the generated test_kit_drift.py print it.
    Anything unreadable (no key, no checkout, a version that does not parse)
    gives None.

Test: kit/tests/test_guards.py.
"""

from __future__ import annotations

from pathlib import Path

from kit.guards import skill_pack, report
from kit.tools import manifest


def check_vendored(dir: Path | str) -> list[str]:
    """Every drift of the vendored copy at `dir` from its manifest."""
    d = Path(dir)
    if not d.is_dir():
        return [f"{d}: no vendored copy here"]
    out = [f"{d.name}/: {p}" for p in manifest.check(d)]
    v = d / "VERSION"
    if not (v.is_file() and v.read_text(encoding="utf-8").strip()):
        out.append(f"{d.name}/: no VERSION")
    elif (d / manifest.NAME).is_file() and "VERSION" not in manifest.parse(
            (d / manifest.NAME).read_text(encoding="utf-8")):
        out.append(f"{d.name}/: VERSION is not in {manifest.NAME}")
    return out


def check_skill_pack(root: Path | str | None = None) -> list[str]:
    """The skill pack's vendored kit (and console, when present) match their
    manifests and carry the same VERSION."""
    cfg = skill_pack(root)
    kit_dir = cfg.root / cfg.scripts_dir / "kit"
    console = cfg.root / "console"
    if not kit_dir.is_dir():
        return [f"no vendored kit at {cfg.scripts_dir}/kit/ (run "
                f"kit/tools/vendor.py --skill-pack {cfg.root})"]
    out = check_vendored(kit_dir)
    if console.is_dir():
        out += check_vendored(console)
        kv, cv = kit_dir / "VERSION", console / "VERSION"
        if kv.is_file() and cv.is_file() and (
                kv.read_text(encoding="utf-8").strip()
                != cv.read_text(encoding="utf-8").strip()):
            out.append(f"console/VERSION {cv.read_text().strip()!r} is not "
                       f"the kit's {kv.read_text().strip()!r}: vendor them "
                       f"together")
    return out


BEHIND_MINORS = 2       # more than this many minor versions behind is worth a line


def _version(path: Path) -> tuple[int, int, int] | None:
    try:
        a, b, c = path.read_text(encoding="utf-8").strip().split(".")
        return int(a), int(b), int(c)
    except (OSError, ValueError):
        return None


def behind(root: Path | str | None = None) -> str | None:
    """`behind: kit X.Y.Z, playbook A.B.C` when the playbook named by
    `[kit] playbook` is more than BEHIND_MINORS minor versions ahead of the
    vendored kit (or a major ahead); None otherwise, and never an error."""
    try:
        cfg = skill_pack(root)
    except Exception:           # a hint must not break a guard that has its own errors
        return None
    named = cfg.raw.get("kit", {}).get("playbook") if isinstance(cfg.raw.get("kit"), dict) else None
    if not isinstance(named, str) or not named.strip():
        return None
    mine = _version(cfg.root / cfg.scripts_dir / "kit" / "VERSION")
    theirs = _version((cfg.root / Path(named).expanduser()) / "kit" / "VERSION")
    if not mine or not theirs:
        return None
    if theirs[0] > mine[0] or (theirs[0] == mine[0] and theirs[1] - mine[1] > BEHIND_MINORS):
        return f"behind: kit {'.'.join(map(str, mine))}, playbook {'.'.join(map(str, theirs))}"
    return None


def check_drift(root: Path | str | None = None) -> bool:
    """check_skill_pack() as one kit.testing.check line (and the behind() hint, if any)."""
    if hint := behind(root):
        print(hint)
    return report("drift: the vendored kit and console match their "
                  "manifests", check_skill_pack(root))
