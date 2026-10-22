"""tools/consumers.py: which kit modules a skill pack's own code imports.

Two throwaway skill packs: one imports `facts` and a lazy `takes`, one only `facts`; neither
imports `queue` directly, but `facts` is the vendored kit's own and pulls in what it imports.
The vendored kit and a tests/ folder are not read; a skill pack with no vendored kit says so.
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
TOOL = ROOT / "tools" / "consumers.py"


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)


def test_direct_lazy_and_pulled_in_modules_are_told_apart():
    with _t.tmpdir() as tmp:
        a, b, c = (Path(tmp) / n for n in ("a", "b", "c"))
        write(a, {"scripts/kit/__init__.py": "", "scripts/kit/facts.py": "from kit import db\n",
                  "scripts/run.py": "from kit import facts\ndef f():\n    from kit.takes import plan\n",
                  "scripts/kit/ignored.py": "from kit import consent\n",
                  "tests/test_x.py": "from kit import consent\n", ".hidden/x.py": "from kit import consent\n"})
        write(b, {"scripts/kit/__init__.py": "", "scripts/run.py": "from kit import facts\n"})
        write(c, {"scripts/run.py": "import json\n"})
        r = run(str(a), str(b), str(c), "--json")
        assert r.returncode == 0, r.stderr
        doc = json.loads(r.stdout)
        sp, mods = doc["skill_packs"], doc["modules"]
        assert sp["a"]["direct"] == {"facts": 1, "takes": 1} and sp["a"]["vendors_the_kit"], sp["a"]
        assert sp["b"]["direct"] == {"facts": 1} and sp["c"]["vendors_the_kit"] is False, sp
        assert mods["facts"]["direct"] == ["a", "b"] and mods["facts"]["pack"] == "base", mods["facts"]
        assert mods["takes"]["direct"] == ["a"] and mods["takes"]["pack"] == "generation", mods["takes"]
        assert mods["consent"]["direct"] == [] and mods["consent"]["via"] == {}, mods["consent"]
        assert mods["db"]["direct"] == [] and mods["db"]["via"] == {"a": "facts", "b": "facts"}, mods["db"]
        assert not any(m.startswith(("guards.", "testing.", "tools.")) for m in mods), "testkit is left out"


def test_the_table_names_what_nobody_imports():
    with _t.tmpdir() as tmp:
        a = Path(tmp) / "a"
        write(a, {"scripts/run.py": "from kit import takes\n"})
        r = run(str(a))
        assert r.returncode == 0, r.stderr
        assert "a: does not vendor the kit, 1 kit module(s)" in r.stdout, r.stdout
        assert any(l.startswith("takes") and l.rstrip().endswith("a") for l in r.stdout.splitlines()), r.stdout
        assert any(l.startswith("consent") and l.rstrip().endswith("no one") for l in r.stdout.splitlines()), r.stdout


def test_a_missing_folder_is_refused():
    r = run("/nowhere/at/all")
    assert r.returncode == 2 and "not a folder" in r.stderr, (r.returncode, r.stderr)


if __name__ == "__main__":
    _t.main(globals())
