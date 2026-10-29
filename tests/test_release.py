"""tools/release.py: the release train as one command (docs/maintaining.md; issue #222).

Run on a throwaway playbook (kit/VERSION, kit/MANIFEST.sha256 made by the real manifest tool, a CHANGELOG): a train sets the version, moves the
[Unreleased] heading, regenerates the manifest and leaves the previous release note as it was; and each thing that would make the train wrong is refused
and writes nothing (no entry, an entry without its Skill packs line, a version not above the current one or one the CHANGELOG has, a second train inside
a week without a reason, an urgent minor, a date in the past).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "release.py")
LOG = """# Changelog

## [Unreleased]

### Kit
- a new module
- Skill packs: nothing

### Other
- a doc
- Skill packs: judgement (the pack decides)

## [0.2.0] - 2026-10-20

### Kit
- the old note
- Skill packs: nothing
"""


def setup(log: str = LOG) -> str:
    d = tempfile.mkdtemp(prefix="release-")
    os.makedirs(f"{d}/kit/tools")
    shutil.copy(os.path.join(ROOT, "kit", "tools", "manifest.py"), f"{d}/kit/tools/manifest.py")
    open(f"{d}/kit/VERSION", "w").write("0.2.0\n")
    open(f"{d}/kit/x.py", "w").write("X = 1\n")
    open(f"{d}/CHANGELOG.md", "w").write(log)
    subprocess.run([sys.executable, f"{d}/kit/tools/manifest.py", f"{d}/kit"], check=True, capture_output=True)
    return d


def snapshot(d: str) -> dict:
    return {p: open(f"{d}/{p}").read() for p in ("CHANGELOG.md", "kit/VERSION", "kit/MANIFEST.sha256")}


def run(d: str, *args: str):
    return subprocess.run([sys.executable, TOOL, *args, "--root", d], capture_output=True, text=True, timeout=60)


def refused(d: str, why: str, *args: str) -> None:
    before = snapshot(d)
    r = run(d, *args)
    assert r.returncode == 2 and why in r.stderr, (args, r.returncode, r.stderr)
    assert snapshot(d) == before, "a refused train writes nothing"


def test_a_train_sets_the_version_the_heading_and_the_manifest():
    d = setup()
    before = snapshot(d)
    r = run(d, "0.3.0", "--date", "2026-10-28")
    assert r.returncode == 0, r.stderr
    assert "0.2.0 -> 0.3.0" in r.stdout and "1 judgement, 0 mechanical, 1 nothing" in r.stdout, r.stdout
    after = snapshot(d)
    assert after["kit/VERSION"] == "0.3.0\n"
    assert after["CHANGELOG.md"].startswith("# Changelog\n\n## [Unreleased]\n\n## [0.3.0] - 2026-10-28\n\n### Kit\n- a new module"), after["CHANGELOG.md"][:120]
    assert after["CHANGELOG.md"].endswith(before["CHANGELOG.md"].split("## [0.2.0]")[1]), "the previous note is byte for byte"
    assert after["kit/MANIFEST.sha256"] != before["kit/MANIFEST.sha256"], "VERSION is in the manifest"
    check = subprocess.run([sys.executable, f"{d}/kit/tools/manifest.py", "--check", f"{d}/kit"], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr


def test_a_dry_run_reports_and_writes_nothing():
    d = setup()
    before = snapshot(d)
    r = run(d, "0.3.0", "--date", "2026-10-28", "--dry-run")
    assert r.returncode == 0 and "would release" in r.stdout and snapshot(d) == before, r


def test_an_unreleased_that_is_not_ready_is_refused():
    refused(setup(LOG.replace("- a new module\n- Skill packs: nothing\n", "").replace("- a doc\n- Skill packs: judgement (the pack decides)\n", "")),
            "no entry", "0.3.0", "--date", "2026-10-28")
    refused(setup(LOG.replace("- Skill packs: nothing\n\n### Other", "\n### Other")), "no Skill packs line after '- a new module'", "0.3.0", "--date", "2026-10-28")
    refused(setup(LOG.replace("judgement (the pack decides)", "judgement")), "malformed Skill packs line", "0.3.0", "--date", "2026-10-28")
    refused(setup(LOG.replace("- a new module\n", "- a new module\n- another entry\n")), "no Skill packs line after '- a new module'", "0.3.0", "--date", "2026-10-28")


def test_a_version_that_cannot_be_released_is_refused():
    d = setup()
    refused(d, "is not above kit/VERSION", "0.2.0", "--date", "2026-10-28")
    refused(d, "is not above kit/VERSION", "0.1.9", "--date", "2026-10-28")
    refused(d, "is not X.Y.Z", "next", "--date", "2026-10-28")
    d2 = setup(LOG.replace("## [0.2.0]", "## [0.3.0] - 2026-10-21\n\n- x\n- Skill packs: nothing\n\n## [0.2.0]"))
    refused(d2, "never rewritten", "0.3.0", "--date", "2026-10-28")


def test_a_second_train_inside_a_week_needs_a_reason_and_is_a_patch():
    d = setup()
    refused(d, "at most weekly", "0.2.1", "--date", "2026-10-24")
    refused(d, "is a patch", "0.3.0", "--date", "2026-10-24", "--urgent", "a pack is blocked")
    refused(d, "earlier than the last release", "0.2.1", "--date", "2026-10-19")
    r = run(d, "0.2.1", "--date", "2026-10-24", "--urgent", "a pack is blocked")
    assert r.returncode == 0 and open(f"{d}/kit/VERSION").read() == "0.2.1\n", r.stderr


def test_the_real_changelog_is_ready_for_a_train():
    """A dry run on this repository: a train on 2999-01-01 would be accepted, so the entries merged since the last train are all paired."""
    r = subprocess.run([sys.executable, TOOL, "999.0.0", "--date", "2999-01-01", "--dry-run"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr


if __name__ == "__main__":
    _t.main(globals())
