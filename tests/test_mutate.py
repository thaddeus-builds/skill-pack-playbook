"""tools/mutate.py: break one line of a file on purpose and report whether a test command notices.

Tried on a throwaway module and test: a break the test fails on is caught, one it passes is a survivor and fails the run; the file is put back byte for byte
after every break, on a hang and on SIGTERM too; and what would make a pass meaningless is refused (a test that is red to begin with, a text found twice or
not at all, a break that does not compile, a malformed mutants file).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "mutate.py")
MODULE = "def f(x):\n    return x + 1\n\n\ndef g(x):\n    return x * 2\n"
TEST = ("import sys, time\nsys.dont_write_bytecode = True\nsrc = open('m.py').read()\n"
        "if 'HANG' in src:\n    time.sleep(60)\n"
        "ns = {}\nexec(src, ns)\nassert ns['f'](1) == 2\nprint('RESULT: 1 passed')\n")


def setup(module: str = MODULE) -> str:
    d = tempfile.mkdtemp(prefix="mutate-")
    open(os.path.join(d, "m.py"), "w", encoding="utf-8").write(module)
    open(os.path.join(d, "t.py"), "w", encoding="utf-8").write(TEST)
    return d


def run(d: str, mutants: str, *extra: str, source: str = "m.py", test: str = "t.py"):
    open(os.path.join(d, "mutants.txt"), "w", encoding="utf-8").write(mutants)
    return subprocess.run([sys.executable, TOOL, source, "mutants.txt", "--test", f"{sys.executable} {test}", *extra],
                          cwd=d, capture_output=True, text=True, timeout=120)


def test_a_break_the_test_fails_on_is_caught_and_a_survivor_fails_the_run():
    d = setup()
    try:
        r = run(d, "x + 1\n=>>\nx - 1\n")
        assert r.returncode == 0 and "CAUGHT" in r.stdout and "1 of 1 breaks caught" in r.stdout, (r.stdout, r.stderr)
        r = run(d, "x + 1\n=>>\nx - 1\n####\nx * 2\n=>>\nx * 3\n####\nx + 1\n=>>\n1 + x\n")
        assert r.returncode == 1, (r.stdout, r.stderr)
        verdicts = [line.split()[0] for line in r.stdout.splitlines() if line.split()[:1] in (["CAUGHT"], ["SURVIVED"])]
        assert verdicts == ["CAUGHT", "SURVIVED", "SURVIVED"], r.stdout
        assert "1 of 3 breaks caught; 2 NOT: 2, 3" in r.stdout, r.stdout
        j = json.loads(run(d, "x * 2\n=>>\nx * 3\n", "--json").stdout)
        assert j["not_caught"] == 1 and j["results"][0]["verdict"] == "survived", j
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_the_file_is_the_same_bytes_afterwards_whatever_happened():
    d = setup()
    path = os.path.join(d, "m.py")
    try:
        for mutants in ("x + 1\n=>>\nx - 1\n", "x * 2\n=>>\nx * 3\n", "x + 1\n=>>\nx + 1  # HANG\n", "x +\n=>>\n"):
            run(d, mutants, "--timeout", "2")
            assert open(path, encoding="utf-8").read() == MODULE, mutants
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_a_hang_is_a_timeout_and_a_break_that_does_not_compile_is_invalid_neither_is_caught():
    d = setup()
    try:
        r = run(d, "x + 1\n=>>\nx + 1  # HANG\n", "--timeout", "2")
        assert r.returncode == 1 and "TIMEOUT" in r.stdout and "CAUGHT" not in r.stdout, r.stdout
        r = run(d, "x + 1\n=>>\nx +\n")
        assert r.returncode == 1 and "INVALID" in r.stdout and "CAUGHT" not in r.stdout, r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_what_would_make_a_pass_meaningless_is_refused_with_exit_2():
    d = setup()
    try:
        cases = {
            "a text that is not in the file": ("nowhere\n=>>\nx\n", "not once"),
            "a text found twice": ("return\n=>>\nreturn 0 +\n", "2 times"),
            "no arrow": ("x + 1\n", "wants one line `=>>`"),
            "two arrows": ("x + 1\n=>>\nx\n=>>\ny\n", "found 2"),
            "an empty text to replace": ("=>>\nx\n", "empty"),
            "no break at all": ("\n\n", "no break"),
        }
        for label, (mutants, word) in cases.items():
            r = run(d, mutants)
            assert r.returncode == 2 and word in r.stderr, (label, r.returncode, r.stderr)
        open(os.path.join(d, "m.py"), "w", encoding="utf-8").write(MODULE.replace("x + 1", "x + 2"))
        r = run(d, "x + 2\n=>>\nx - 1\n")
        assert r.returncode == 2 and "does not pass on the unbroken file" in r.stderr, (r.returncode, r.stderr)
        assert run(d, "x\n=>>\ny\n", source="absent.py").returncode == 2
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_a_file_that_is_not_python_is_broken_the_same_way_without_the_compile_check():
    d = setup()
    try:
        open(os.path.join(d, "rule.txt"), "w", encoding="utf-8").write("limit = 5\n")
        open(os.path.join(d, "t2.py"), "w", encoding="utf-8").write(
            "assert open('rule.txt').read() == 'limit = 5\\n'\nprint('RESULT: 1 passed')\n")
        r = run(d, "limit = 5\n=>>\nlimit = (\n", source="rule.txt", test="t2.py")
        assert r.returncode == 0 and "CAUGHT" in r.stdout and "INVALID" not in r.stdout, (r.stdout, r.stderr)
        assert open(os.path.join(d, "rule.txt"), encoding="utf-8").read() == "limit = 5\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_sigterm_and_ctrl_c_put_the_file_back():
    d = setup()
    path = os.path.join(d, "m.py")
    try:
        open(os.path.join(d, "mutants.txt"), "w", encoding="utf-8").write("x + 1\n=>>\nx + 1  # HANG\n")
        for sig in (signal.SIGTERM, signal.SIGINT):
            p = subprocess.Popen([sys.executable, TOOL, "m.py", "mutants.txt", "--test", f"{sys.executable} t.py", "--timeout", "60"],
                                 cwd=d, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            deadline = time.time() + 30
            while "HANG" not in open(path, encoding="utf-8").read():
                assert time.time() < deadline and p.poll() is None, "the break was never written"
                time.sleep(0.05)
            p.send_signal(sig)
            p.communicate(timeout=30)
            assert open(path, encoding="utf-8").read() == MODULE, sig
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    _t.main(globals())
