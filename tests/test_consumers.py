"""tools/consumers.py: the admission rule's count, read from harness checkouts.

Two throwaway harnesses stand in for real ones. `human` is used in production
by both (shared); `copylint` by one; `takes` only by a test (none, listed as
test only); `claimscope` by nobody (`claimscope`). The vendored kit inside a harness is not
read as use, a `scripts_dir = "."` harness keeps its kit at kit/, and a
missing directory is refused.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TOOL = ROOT / "tools" / "consumers.py"


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)


def setup(tmp: Path) -> tuple[Path, Path]:
    acme, flat = tmp / "acme", tmp / "flat"
    write(acme, {
        "harness.toml": '[harness]\nname = "acme"\nscripts_dir = "scripts"\n',
        "scripts/a.py": "from kit import human\n",
        "scripts/b.py": "def f():\n    from kit.copylint import lint\n",
        "scripts/kit/claimscope.py": "from kit import human\n",        # the vendored copy is not use
        "tests/test_t.py": "from kit import takes\n",
    })
    write(flat, {
        "harness.toml": '[harness]\nname = "flat"\nscripts_dir = "."\n',
        "run.py": "import kit.human\n",
        "kit/claimscope.py": "from kit import human\n",
    })
    return acme, flat


def rows(out: str) -> dict[str, dict]:
    return {r["module"]: r for r in json.loads(out)["modules"]}


def test_shared_one_none_and_test_only():
    with _t.tmpdir() as tmp:
        acme, flat = setup(Path(tmp))
        r = run(str(acme), str(flat), "--json")
        assert r.returncode == 0, r.stderr
        m = rows(r.stdout)
        assert (m["human"]["verdict"], m["human"]["prod"]) == ("shared", ["acme", "flat"]), m["human"]
        assert (m["copylint"]["verdict"], m["copylint"]["prod"]) == ("one", ["acme"]), m["copylint"]
        assert (m["takes"]["verdict"], m["takes"]["test_only"]) == ("none", ["acme"]), m["takes"]
        assert m["claimscope"]["verdict"] == "none" and m["claimscope"]["prod"] == [], m["claimscope"]


def test_the_text_report_names_what_to_move_and_what_to_delete():
    with _t.tmpdir() as tmp:
        acme, flat = setup(Path(tmp))
        r = run(str(acme), str(flat))
        assert r.returncode == 0, r.stderr
        assert "none (no production importer):" in r.stdout and "claimscope" in r.stdout, r.stdout
        assert "shared (belong in base): -" in r.stdout, r.stdout     # human is base already


def test_a_missing_harness_is_refused():
    r = run("/no/such/harness")
    assert r.returncode == 2 and "not a directory" in r.stderr, (r.returncode, r.stderr)


def test_it_reads_the_playbooks_own_pack_table():
    from kit.tools import packs
    table = packs.table(ROOT / "kit")
    with _t.tmpdir() as tmp:
        acme = Path(tmp) / "acme"
        write(acme, {"harness.toml": '[harness]\nname = "acme"\n'})
        listed = set(rows(run(str(acme), "--json").stdout))
    want = {m for m, p in table.items() if p != "testkit"}
    assert listed == want, sorted(listed ^ want)


if __name__ == "__main__":
    _t.main(globals())
