"""CI minutes are a quota on a private repository: a failure should show before the push, and a stale run should stop.

Checked, each on a broken copy first, so a check cannot pass by looking at nothing:

  - .github/workflows/ci.yml cancels an older run of the same ref and never a run on main;
  - .githooks/pre-push is executable and runs run_all.py from the repository root;
  - CLAUDE.md tells a contributor how to install the hook.
"""

from __future__ import annotations

import os
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
import _t  # noqa: E402,F401
from test_docs_build import doc  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, ".."))
HOOK = ".githooks/pre-push"
INSTALL = "git config core.hooksPath .githooks"


def ci_problems(text: str) -> list[str]:
    out = []
    if not re.search(r"^concurrency:\n  group: ci-\$\{\{ github\.ref \}\}\n  cancel-in-progress: \$\{\{ github\.ref != 'refs/heads/main' \}\}$", text, re.M):
        out.append("ci.yml does not cancel an older run of the same ref, or may cancel one on main")
    return out


def hook_problems(text: str, executable: bool) -> list[str]:
    out = []
    if not executable:
        out.append("the hook is not executable")
    if not text.startswith("#!/bin/sh"):
        out.append("the hook has no shell line")
    if 'cd "$(git rev-parse --show-toplevel)"' not in text:
        out.append("the hook does not start from the repository root")
    if not re.search(r'^exec "\$py" run_all\.py$', text, re.M):
        out.append("the hook does not end by running run_all.py")
    return out


def test_ci_cancels_a_stale_run_and_never_one_on_main():
    ci = doc(".github/workflows/ci.yml")
    assert ci_problems(ci) == [], ci_problems(ci)
    assert ci_problems(ci.replace("cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}", "cancel-in-progress: true"))
    assert ci_problems(ci.replace("concurrency:", "x:"))
    assert ci_problems(ci.replace("group: ci-${{ github.ref }}", "group: ci"))


def test_the_pre_push_hook_runs_every_suite():
    text = doc(HOOK)
    executable = os.access(os.path.join(REPO, HOOK), os.X_OK)
    assert hook_problems(text, executable) == [], hook_problems(text, executable)
    assert hook_problems(text, False)
    assert hook_problems(text.replace("exec \"$py\" run_all.py", "true"), True)
    assert hook_problems(text.replace('cd "$(git rev-parse --show-toplevel)"', "cd /"), True)


def test_the_gitlab_template_cancels_a_stale_pipeline():
    text = doc("templates/gitlab-ci.yml")
    assert re.search(r"^default:\n  interruptible: true$", text, re.M)
    assert not re.search(r"^default:\n  interruptible: true$", text.replace("interruptible: true", "interruptible: false"), re.M)


def test_claude_md_says_how_to_install_the_hook():
    assert INSTALL in doc("CLAUDE.md")
    assert INSTALL in doc(HOOK)


if __name__ == "__main__":
    _t.main(globals())
