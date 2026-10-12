"""tests/_t.py's main: a top-level test_* that main never collected (defined below the `_t.main(globals())` call, or
hidden by a decorator without functools.wraps) fails the file, named, instead of being skipped while the file still
prints `RESULT: N passed` (the video-ads harness: 38 tests in 8 files never ran under its runner)."""

import os
import subprocess
import sys

import _t

HEAD = f"import sys; sys.path.insert(0, {os.path.dirname(os.path.abspath(_t.__file__))!r})\nimport _t\n"


def run(body: str) -> tuple[int, str]:
    with _t.tmpdir() as d:
        f = os.path.join(d, "test_planted.py")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(HEAD + body)
        p = subprocess.run([sys.executable, "-B", f], capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


def test_a_test_below_the_main_call_fails_the_file_by_name():
    code, out = run("def test_a():\n    pass\n\n"
                    "if __name__ == '__main__':\n    _t.main(globals())\n\n"
                    "def test_late():\n    pass\n")
    assert code == 1 and "FAIL test_late: never ran (defined below the call" in out and "RESULT" not in out, out
    assert "FAILED: 1 of 2" in out, out


def test_a_test_a_decorator_hid_fails_too_and_a_clean_file_passes():
    code, out = run("def hide(f):\n    def inner():\n        return f()\n    inner.__module__ = 'elsewhere'\n"
                    "    return inner\n\ndef test_a():\n    pass\n\n@hide\ndef test_hidden():\n    pass\n\n"
                    "if __name__ == '__main__':\n    _t.main(globals())\n")
    assert code == 1 and "decorated away without functools.wraps" in out and "test_hidden" in out, out
    code, out = run("def test_a():\n    pass\n\nif __name__ == '__main__':\n    _t.main(globals())\n")
    assert code == 0 and out.strip().endswith("RESULT: 1 passed"), out


if __name__ == "__main__":
    _t.main(globals())
