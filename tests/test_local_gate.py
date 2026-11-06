"""tools/local_gate.py: the check a skill pack merges through when the forge's CI cannot be paid for (R49).

A throwaway skill pack is cloned from a bare repository. Checked, each against a broken case so a check cannot pass by
looking at nothing:

  - `status` names the suite, whether the clone has the hook and the setting, and each workflow that starts by itself;
  - `install` writes the hook from the pack's vendored sample and the setting, and never replaces a hook that exists;
  - `run` is green on a passing suite, red on a failing one, red when the commit does not merge with main, and `--fresh`
    finds a file that was never committed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tools" / "local_gate.py"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
SAMPLE = (ROOT / "kit" / "tools" / "pre-push.sample").read_text()
RUNNER = 'import sys\nprint("RESULT: 1 passed")\nsys.exit(0)\n'
FAILING = 'import sys\nprint("RESULT: 0 passed")\nsys.exit(1)\n'
NEEDS_UNTRACKED = 'import os, sys\nok = os.path.exists("extra.txt")\nprint("RESULT: 1 passed" if ok else "RESULT: 0 passed")\nsys.exit(0 if ok else 1)\n'


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True, env=ENV).stdout


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def gate(pack: Path, cmd: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GATE), cmd, str(pack), *flags], capture_output=True, text=True, env=ENV)


def make_pack(tmp: Path, runner: str = RUNNER) -> Path:
    """origin.git (default branch `trunk`) and a clone `acme` of it holding a runner, a vendored sample and one workflow."""
    origin, seed, pack = tmp / "origin.git", tmp / "seed", tmp / "acme"
    sh(tmp, "git", "init", "-q", "--bare", "-b", "trunk", str(origin))
    write(seed, {"tests/run.py": runner, "skill-pack.toml": '[skill_pack]\nname = "acme"\n',
                 "scripts/kit/tools/pre-push.sample": SAMPLE,
                 ".github/workflows/ci.yml": "name: ci\n\non:\n  workflow_dispatch:\n\njobs: {}\n"})
    sh(seed, "git", "init", "-q", "-b", "trunk")
    sh(seed, "git", "add", "-A")
    sh(seed, "git", "commit", "-qm", "first")
    sh(seed, "git", "remote", "add", "origin", str(origin))
    sh(seed, "git", "push", "-q", "origin", "trunk")
    sh(tmp, "git", "clone", "-q", str(origin), str(pack))
    return pack


def test_status_names_the_suite_the_hook_and_the_workflows_that_start_by_themselves():
    with _t.tmpdir() as t:
        pack = make_pack(Path(t))
        r = gate(pack, "status")
        assert r.returncode == 1 and "acme: NOT gated" in r.stdout, r.stdout     # no hook yet
        assert "tests/run.py" in r.stdout and "auto CI     none" in r.stdout, r.stdout
        write(pack, {".github/workflows/ci.yml": "name: ci\n\non:\n  pull_request:\n  workflow_dispatch:\n\njobs: {}\n"})
        r = gate(pack, "status")
        assert "auto CI     ci.yml" in r.stdout, r.stdout                          # a trigger that fires without a click is named


def test_install_writes_the_hook_and_the_setting_and_keeps_a_hook_that_is_there():
    with _t.tmpdir() as t:
        pack = make_pack(Path(t))
        r = gate(pack, "install")
        assert r.returncode == 0 and "acme: ok" in r.stdout, r.stdout + r.stderr
        hook = pack / ".git" / "hooks" / "pre-push"
        assert hook.is_file() and os.access(hook, os.X_OK) and hook.read_text() == SAMPLE
        assert sh(pack, "git", "config", "--get", "skillpack.prepush-tests").strip() == "python3 tests/run.py"
        assert gate(pack, "status").returncode == 0                                 # gated, and no workflow starts by itself
        hook.write_text("#!/bin/sh\necho mine\n")
        sh(pack, "git", "config", "--unset", "skillpack.prepush-tests")
        gate(pack, "install")
        assert hook.read_text() == "#!/bin/sh\necho mine\n"                         # the pack's own hook is never replaced
        sample = pack / "scripts" / "kit" / "tools" / "pre-push.sample"
        sample.unlink()
        hook.unlink()
        r = gate(pack, "install")
        assert r.returncode == 1 and "no vendored" in r.stdout, r.stdout            # nothing to install from: said, not guessed


def test_run_is_green_on_a_passing_suite_and_red_on_a_failing_one():
    with _t.tmpdir() as t:
        pack = make_pack(Path(t))
        r = gate(pack, "run")
        assert r.returncode == 0 and r.stdout.strip().endswith("GATE: green"), r.stdout + r.stderr
        assert "RESULT: 1 passed" in r.stdout, r.stdout
        write(pack, {"tests/run.py": FAILING})
        sh(pack, "git", "commit", "-qam", "break")
        r = gate(pack, "run")
        assert r.returncode == 1 and "GATE: red (the suite failed on the merge result" in r.stdout, r.stdout
        assert "worktrees" not in sh(pack, "git", "worktree", "list").replace(str(pack), "")   # the throwaway worktree is gone


def test_run_is_red_when_the_commit_does_not_merge_with_main():
    with _t.tmpdir() as t:
        tmp = Path(t)
        pack = make_pack(tmp)
        other = tmp / "other"
        sh(tmp, "git", "clone", "-q", str(tmp / "origin.git"), str(other))
        write(other, {"tests/run.py": RUNNER + "# theirs\n"})
        sh(other, "git", "commit", "-qam", "theirs")
        sh(other, "git", "push", "-q", "origin", "trunk")
        write(pack, {"tests/run.py": RUNNER + "# mine\n"})
        sh(pack, "git", "commit", "-qam", "mine")
        r = gate(pack, "run")
        assert r.returncode == 1 and "does not merge with origin/trunk" in r.stdout, r.stdout


def test_a_fresh_clone_finds_what_main_lacks():
    with _t.tmpdir() as t:
        pack = make_pack(Path(t), NEEDS_UNTRACKED)
        write(pack, {"extra.txt": "x\n"})                                           # committed here, not pushed
        sh(pack, "git", "add", "extra.txt")
        sh(pack, "git", "commit", "-qm", "add it")
        r = gate(pack, "run")
        assert r.returncode == 0, r.stdout                                          # the merge result has the file
        r = gate(pack, "run", "--fresh")
        assert r.returncode == 1 and "fresh clone of trunk" in r.stdout and "GATE: red (the suite failed on a fresh clone" in r.stdout, r.stdout
        sh(pack, "git", "push", "-q", "origin", "trunk")
        assert gate(pack, "run", "--fresh").returncode == 0                         # once main holds it, the clone passes


if __name__ == "__main__":
    _t.main(globals())
