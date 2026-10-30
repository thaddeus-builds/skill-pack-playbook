#!/usr/bin/env python3
"""kit.testing.run_tests: the gate every other test relies on.

The gate is run over throwaway tests dirs of planted files, in its own
process with a TMPDIR we then inspect:

  * a clean file passes, in both RESULT conventions (`N passed` and
    `N passed, 0 failed`), and the run leaves the caller's TMPDIR empty;
  * a file without a RESULT line fails; `0 passed` fails; `M failed` > 0
    fails even with exit 0; a non-zero exit fails; a timeout fails;
  * a file that leaks into its TMPDIR fails and is named; uv's lock is
    not a leak; a sandbox from check.tmp_dir() is not a leak;
  * the last RESULT line counts; one bad file fails the run; the filter
    is a substring (several = any); no match fails;
  * check.finish() and check.run_functions() files pass through the gate;
    a test_* defined below the run_functions() call fails its file, named;
  * a file's own `# kit-timeout: S` is its budget: a slow file with a
    larger one passes under a short default, a file past a smaller one is
    killed; `--timeout S` sets the run's default, and a bad one fails;
  * every file sees KIT_TEST_RUN=1;
  * no file inherits a variable that names a repository (GIT_DIR, GIT_INDEX_FILE ...): a pre-push hook hands them down, and a test's throwaway `git init` would
    then act on the checkout that was pushing; the list is git's own (`git rev-parse --local-env-vars`).
"""

import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit.testing import run_tests  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

ROOT = str(_shop.PLAYBOOK)


def gate(files: dict[str, str], *args: str, timeout_s: float = 60
         ) -> tuple[int, str, list[str]]:
    """Run the gate over {name: body}: (exit, output, what it left in the
    TMPDIR it was given). The gate starts unmarked: KIT_TEST_RUN, which
    importing check set here, is not passed on."""
    d = Path(tmp_dir("gate-"))
    (d / "tests").mkdir()
    for name, body in files.items():
        (d / "tests" / name).write_text(body, encoding="utf-8")
    tmp = d / "tmp"
    tmp.mkdir()
    shim = ("import sys; sys.path.insert(0, %r)\n"
            "from kit.testing import run_tests\n"
            "sys.exit(run_tests.main(%r, root=%r, timeout_s=%r))\n"
            % (ROOT, list(args), str(d), timeout_s))
    env = {k: v for k, v in os.environ.items() if k != "KIT_TEST_RUN"}
    p = subprocess.run([sys.executable, "-B", "-c", shim], capture_output=True,
                       text=True, env={**env, "TMPDIR": str(tmp)})
    return p.returncode, p.stdout + p.stderr, sorted(os.listdir(tmp))


def _planted(body: str) -> Path:
    f = Path(tmp_dir("budget-")) / "test_b.py"
    f.write_text(body, encoding="utf-8")
    return f


def parse(text):
    return run_tests.parse_result(text)


PASS = "print('  PASS  x')\nprint('RESULT: 1 passed')\n"
PASS_OLD = "print('  PASS  x')\nprint('RESULT: 1 passed, 0 failed')\n"
LEAK = "import tempfile; tempfile.mkdtemp()\n" + PASS
UV_LOCK = ("import os, tempfile\nopen(os.path.join(tempfile.gettempdir(), "
           "'uv-0a1b.lock'), 'w').close()\n" + PASS)
HEADER = "import os, sys; sys.path.insert(0, %r)\n" % ROOT
HELPER = (HEADER + "from kit.testing.check import check, finish, tmp_dir\n"
          "d = tmp_dir(prefix='sandbox-')\n"
          "open(os.path.join(d, 't.db'), 'w').close()\n"
          "check('sandbox made', os.path.isdir(d))\n"
          "raise SystemExit(finish())\n")
FUNCS = (HEADER + "from kit.testing.check import run_functions\n"
         "def test_one():\n    assert 1 + 1 == 2\n"
         "def test_two():\n    assert 'a'.upper() == 'A'\n"
         "raise SystemExit(run_functions(globals()))\n")
FUNCS_BAD = FUNCS.replace("== 'A'", "== 'B'")
FUNCS_WRAPPED = (HEADER + "from kit.testing.check import run_functions\n"
                 "def plain(f):\n    def inner():\n        return f()\n"
                 "    inner.__module__ = 'elsewhere'\n    return inner\n"
                 "def test_one():\n    assert True\n"
                 "@plain\ndef test_hidden():\n    assert True\n"
                 "raise SystemExit(run_functions(globals()))\n")
FUNCS_LATE = (FUNCS.replace("raise SystemExit", "if __name__ == '__main__':\n"
                             "    raise SystemExit")
              + "\n\ndef test_appended_later():\n    assert False\n")
SLOW_OWN = "# kit-timeout: 30\nimport time; time.sleep(2)\n" + PASS
SLOW_OVER = "# kit-timeout: 1\nimport time; time.sleep(30)\n" + PASS
SLOW_IN_TEXT = ('"""\n# kit-timeout: 30\n"""\nimport time; time.sleep(30)\n'
                + PASS)
MARKER = ("import os\nprint(os.environ.get('KIT_TEST_RUN'))\n"
          "assert os.environ.get('KIT_TEST_RUN') == '1'\n" + PASS)
GREEN_LIE = "print('RESULT: 3 passed, 2 failed')\n"     # exit 0
ZERO = "print('RESULT: 0 passed')\n"
NO_LINE = "print('did some work')\n"
EXIT_1 = "print('RESULT: 4 passed')\nraise SystemExit(1)\n"
SLOW = "import time; time.sleep(30)\n" + PASS
LAST_WINS_BAD = "print('RESULT: 5 passed')\nprint('RESULT: 1 passed, 1 failed')\n"
LAST_WINS_OK = "print('RESULT: 1 passed, 1 failed')\nprint('RESULT: 5 passed')\n"


def main() -> int:
    print("[1] the RESULT line")
    check("'N passed' -> (N, 0)", parse("RESULT: 5 passed") == (5, 0))
    check("'N passed, M failed' -> (N, M)",
          parse("RESULT: 5 passed, 2 failed") == (5, 2))
    check("leading indent tolerated", parse("   RESULT: 7 passed") == (7, 0))
    check("no line -> (None, 0)", parse("nothing here") == (None, 0))
    check("the last line counts",
          parse("RESULT: 9 passed\n  PASS b\nRESULT: 2 passed, 1 failed\n")
          == (2, 1))
    check("the runner's own failure summary parses as a failure",
          parse("RESULT: 7 passed, 1 failed (1 of 2 files failed the gate)")
          == (7, 1))

    print("\n[2] clean files pass")
    rc, out, left = gate({"test_ok.py": PASS, "test_old.py": PASS_OLD})
    check("both RESULT conventions pass; summary 'RESULT: 2 passed'",
          rc == 0 and out.rstrip().endswith("RESULT: 2 passed"), out)
    check("the run leaves the caller's TMPDIR as it found it", left == [], left)
    rc, out, _ = gate({"test_helper.py": HELPER})
    check("a sandbox from check.tmp_dir() is gone when the file exits",
          rc == 0, out)
    rc, out, _ = gate({"test_funcs.py": FUNCS})
    check("run_functions(): each test_* function is one check",
          rc == 0 and "RESULT: 2 passed" in out, out)
    rc, out, _ = gate({"test_marker.py": MARKER})
    check("every file runs with KIT_TEST_RUN=1 (a skill pack tells a test by it)",
          rc == 0, out)
    rc, out, _ = gate({"test_uv.py": UV_LOCK})
    check("uv's own lock file is not the test's leak", rc == 0, out)

    print("\n[3] every violation class fails")
    cases = {
        "missing RESULT line": (NO_LINE, "missing 'RESULT: N passed' gate line"),
        "0 passed": (ZERO, "RESULT line reports 0 passed (ran no tests)"),
        "M failed with exit 0": (GREEN_LIE, "RESULT line reports 2 failed"),
        "a non-zero exit": (EXIT_1, "exit 1"),
        "the last RESULT line reports a failure": (
            LAST_WINS_BAD, "RESULT line reports 1 failed"),
        "a failing run_functions() test (exit 1)": (FUNCS_BAD, "exit 1"),
    }
    for label, (body, why) in cases.items():
        rc, out, left = gate({"test_x.py": body})
        check(f"{label}: the gate fails and says why",
              rc == 1 and f"tests/test_x.py: {why}" in out
              and "RESULT: 0 passed, 1 failed" in out and left == [], out)
    rc, out, left = gate({"test_leak.py": LEAK})
    check("a file leaving a temp dir fails, named with the count",
          rc == 1 and "tests/test_leak.py: left 1 temp entry" in out, out)
    check("the leak itself is swept, not left for the next run", left == [],
          left)
    rc, out, left = gate({"test_slow.py": SLOW}, timeout_s=1)
    check("a file past its timeout is killed and fails",
          rc == 1 and "tests/test_slow.py: timed out after 1s" in out
          and left == [], out)
    rc, out, _ = gate({"test_late.py": FUNCS_LATE})
    check("a test_* defined below the run_functions() call fails its file, "
          "named", rc == 1 and "tests/test_late.py: exit 1" in out
          and "test_appended_later: never ran (defined below the call" in out
          and "PASS  test_one" in out, out)
    rc, out, _ = gate({"test_wrapped.py": FUNCS_WRAPPED})
    check("a test a decorator hid from run_functions() fails its file, named "
          "with both causes", rc == 1 and "test_hidden: never ran (defined "
          "below the call, or decorated away without functools.wraps)" in out,
          out)
    rc, out, _ = gate({"test_ok.py": PASS, "test_lie.py": GREEN_LIE})
    check("one bad file fails the whole run; the good one still counts",
          rc == 1 and "RESULT: 1 passed, 1 failed" in out, out)
    rc, out, _ = gate({"test_x.py": LAST_WINS_OK})
    check("a nested failure line followed by the file's own pass line passes",
          rc == 0, out)

    print("\n[4] a file's own budget")
    check("budget(): the file's comment, else the default",
          run_tests.budget(_planted(SLOW_OWN), 5) == 30
          and run_tests.budget(_planted(PASS), 5) == 5)
    check("budget(): a trailing comment after the number is allowed",
          run_tests.budget(_planted("# kit-timeout: 600  # builds videos\n"
                                    + PASS), 5) == 600)
    check("budget(): text in a string is not a comment; 0 is no budget",
          run_tests.budget(_planted(SLOW_IN_TEXT), 5) == 5
          and run_tests.budget(_planted("# kit-timeout: 0\n" + PASS), 5) == 5)
    rc, out, left = gate({"test_own.py": SLOW_OWN, "test_ok.py": PASS},
                         timeout_s=1)
    check("a slow file with its own larger budget passes a 1 s default",
          rc == 0 and out.rstrip().endswith("RESULT: 2 passed"), out)
    rc, out, left = gate({"test_over.py": SLOW_OVER}, timeout_s=60)
    check("a file past its own smaller budget is killed and fails",
          rc == 1 and "tests/test_over.py: timed out after 1s" in out
          and left == [], out)
    rc, out, _ = gate({"test_slow.py": SLOW}, "--timeout", "1")
    check("--timeout S sets the run's default",
          rc == 1 and "tests/test_slow.py: timed out after 1s" in out, out)
    rc, out, _ = gate({"test_own.py": SLOW_OWN}, "--timeout=1")
    check("… and a file's own budget still wins over it", rc == 0, out)
    for bad in ("0", "x", "inf"):
        rc, out, _ = gate({"test_ok.py": PASS}, f"--timeout={bad}")
        check(f"--timeout={bad} is refused, nothing run",
              rc == 1 and "--timeout needs a positive number" in out
              and "test_ok" not in out, out)

    print("\n[5] the filter")
    files = {"test_alpha.py": PASS, "test_beta.py": PASS, "test_gamma.py": ZERO}
    rc, out, _ = gate(files, "alpha")
    check("a substring picks files", rc == 0 and "test_beta" not in out
          and out.rstrip().endswith("RESULT: 1 passed"), out)
    rc, out, _ = gate(files, "alpha", "beta")
    check("several arguments = any of them",
          rc == 0 and out.rstrip().endswith("RESULT: 2 passed"), out)
    rc, out, _ = gate(files, "zzz")
    check("no file matches: the run fails",
          rc == 1 and "FAILED: no tests/test_*.py matches 'zzz'" in out, out)
    rc, out, _ = gate({"helper.py": PASS, "test_a.py": PASS})
    check("only test_*.py files run", rc == 0 and "helper.py" not in out, out)
    print("\n[12] the git variables a test must not inherit")
    local = {"GIT_DIR": "/nowhere/.git", "GIT_INDEX_FILE": "/nowhere/index", "GIT_WORK_TREE": "/nowhere", "GIT_PREFIX": "x/", "GIT_COMMON_DIR": "/nowhere/.git"}
    saved = {k: os.environ.get(k) for k in local}
    os.environ.update(local)
    os.environ["GIT_AUTHOR_NAME"] = "kept"
    try:
        env = run_tests.clean_env({"X": "1"})
        body = ("import os\nleft = [k for k in %r if k in os.environ]\nassert not left, left\nassert os.environ.get('GIT_AUTHOR_NAME') == 'kept'\n" % sorted(local)) + PASS
        rc, out, _ = gate({"test_env.py": body})
    finally:
        os.environ.pop("GIT_AUTHOR_NAME", None)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    check("clean_env has none of them, keeps the rest, and adds what it is given", not [k for k in local if k in env] and env["GIT_AUTHOR_NAME"] == "kept" and env["X"] == "1"
          and env["PYTHONDONTWRITEBYTECODE"] == "1")
    check("a test file run by the gate does not see them (and still sees the author name)", rc == 0 and out.rstrip().endswith("RESULT: 1 passed"), out)
    git = subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True)
    if git.returncode == 0 and git.stdout.split():
        check("every name this git lists is in the list (a newer git that lists more fails here, so the list is kept up)", set(git.stdout.split()) <= set(run_tests.GIT_LOCAL_ENV),
              sorted(set(git.stdout.split()) - set(run_tests.GIT_LOCAL_ENV)))
    sample = (Path(ROOT) / "kit" / "tools" / "pre-push.sample").read_text(encoding="utf-8")
    check("the pre-push sample clears git's own list, not a copy of it", "unset $(git rev-parse --local-env-vars)" in sample, sample[-400:])
    print("\n[13] the pre-push sample, run for real (found by the second cold review: the check above reads the text, it does not run it)")
    top = Path(tmp_dir("hook-")) / "pack"
    (top / "kit" / "tools").mkdir(parents=True)
    (top / "kit" / "tools" / "leak_guard.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    bin_dir = top.parent / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").symlink_to(sys.executable)                       # the sample wants a python3 of 3.11 or newer on PATH; this one is
    seen = top.parent / "hook-env.txt"
    plain = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q"], cwd=top, env=plain, check=True)
    subprocess.run(["git", "config", "skillpack.prepush-tests", f'env > "{seen}"'], cwd=top, env=plain, check=True)
    handed = {"GIT_DIR": str(top / ".git"), "GIT_INDEX_FILE": str(top / ".git" / "index"), "GIT_PREFIX": "", "GIT_COMMON_DIR": str(top / ".git"),
              "GIT_CONFIG_PARAMETERS": "'core.abbrev=9'", "KEEP_ME": "1", "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    hook = subprocess.run(["sh", str(Path(ROOT) / "kit" / "tools" / "pre-push.sample"), "origin", "https://example.com/x.git"], cwd=top, env={**plain, **handed},
                          input="", capture_output=True, text=True)
    got = dict(ln.split("=", 1) for ln in seen.read_text(encoding="utf-8", errors="replace").splitlines() if "=" in ln) if seen.exists() else {}
    check("the hook runs the pack's test command from the top level after the guard passes, and the command still has the rest of the environment",
          hook.returncode == 0 and got.get("KEEP_ME") == "1", (hook.returncode, hook.stderr[-300:], sorted(got)[:5]))
    listed = set(subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True, env=plain).stdout.split()) | set(run_tests.GIT_LOCAL_ENV)
    check("that command sees none of the variables git says name a repository, although the hook was handed them",
          not [k for k in listed if k in got] and all(k in handed for k in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_CONFIG_PARAMETERS")), sorted(k for k in listed if k in got))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
