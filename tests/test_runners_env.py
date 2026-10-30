"""The playbook's three standalone test runners (tests/run.py, console/tests/run.py, hosts/zylos/tests/run.py) hand a test file an environment without the
variables that name a repository (GIT_DIR, GIT_INDEX_FILE ...): a pre-push hook gives them to its children, and a test's own `git init` would then act on the
checkout that was pushing. The list is what `git rev-parse --local-env-vars` says together with a fallback copy of the kit's list (`kit.testing.run_tests.GIT_LOCAL_ENV`; each runner
stands alone, console/tests/test_runner.py copies one into a sandbox, so it cannot import it); a git that cannot be asked (none on PATH) must not turn the
filter off, which is what the first version of the three did (found by the second cold review). The copies are kept equal to the kit's list here.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kit.testing import run_tests  # noqa: E402

RUNNERS = ("tests/run.py", "console/tests/run.py", "hosts/zylos/tests/run.py")
LOCAL = {"GIT_DIR": "/nowhere/.git", "GIT_INDEX_FILE": "/nowhere/index", "GIT_WORK_TREE": "/nowhere", "GIT_PREFIX": "x/", "GIT_COMMON_DIR": "/nowhere/.git",
         "GIT_CONFIG_PARAMETERS": "'core.abbrev=9'"}


def load(rel: str, git_cannot_be_asked: bool = False):
    spec = importlib.util.spec_from_file_location("runner_" + rel.replace("/", "_").replace(".", "_"), ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    if git_cannot_be_asked:
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("git")):
            spec.loader.exec_module(mod)
    else:
        spec.loader.exec_module(mod)
    return mod


def test_each_runner_filters_the_kits_list_even_when_git_cannot_be_asked():
    for rel in RUNNERS:
        for broken in (False, True):
            names = load(rel, broken).GIT_LOCAL
            assert set(run_tests.GIT_LOCAL_ENV) <= names, (rel, broken, sorted(set(run_tests.GIT_LOCAL_ENV) - names))


def test_a_test_file_run_by_each_runner_does_not_see_them():
    with _t.tmpdir() as tmp:
        f = Path(tmp) / "test_env.py"
        f.write_text("import os\nleft = [k for k in %r if k in os.environ]\nassert not left, left\nassert os.environ.get('GIT_AUTHOR_NAME') == 'kept'\n"
                     "print('RESULT: 1 passed')\n" % sorted(LOCAL))
        for rel in RUNNERS:
            for broken in (False, True):
                with mock.patch.dict(os.environ, {**LOCAL, "GIT_AUTHOR_NAME": "kept"}):
                    runner = load(rel, broken)
                    r = runner.run_one(str(f))
                assert r["ok"], (rel, broken, r)


def test_the_fallback_copies_are_the_kits_list():
    """`GIT_LOCAL_ENV` says the playbook's other runners take the list from it; each keeps a copy, and a copy that drifts fails here."""
    for rel in RUNNERS:
        assert tuple(load(rel).GIT_LOCAL_FALLBACK) == tuple(run_tests.GIT_LOCAL_ENV), rel


if __name__ == "__main__":
    _t.main(globals())
