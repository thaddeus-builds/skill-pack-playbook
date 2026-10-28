#!/usr/bin/env python3
"""kit.runner: one script runs another and reads its one JSON document.

  * script_cmd: this interpreter, or `uv run` when KIT_RUNNER=uv (every
    script) or KIT_RUNNER=auto (only a script that needs it) and uv is on
    PATH; the `runner` argument stands in for the variable;
  * needs_uv, the rule of auto: dependencies, a requires-python this
    interpreter does not meet, a missing, repeated or unparsable block, an
    unreadable file -> uv; a block with neither -> this interpreter;
  * run_json: a child's document on exit 0; a child's failure document ->
    ChildFailed carrying its error, next and code (and fail() reports the
    child's code); a crash -> its stderr's last line, unclassified; no
    document -> ChildFailed; any_exit keeps a finding document; a hung
    child times out; a failed child's reason, fix commands and code come
    from its stdout document even with noise on stderr.
"""

import os
import stat
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import contract, runner  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.messages import failure  # noqa: E402
from kit.testing.check import (capture, check, finish, one_doc, raises,  # noqa: E402
                               tmp_dir)


def child(d: Path, name: str, body: str) -> Path:
    p = d / name
    p.write_text("import json, sys\n" + body, encoding="utf-8")
    return p


def pep723(d: Path, name: str, block: str | None, newline: str = "\n") -> Path:
    """A script at d/name with `block` (its lines, no `# ` prefix) as its
    PEP 723 block; None = no block."""
    lines = ["#!/usr/bin/env python3"]
    if block is not None:
        lines += ["# /// script", *[("# " + ln).rstrip() for ln in
                                    block.splitlines()], "# ///"]
    lines += ['"""A child."""', "print('{}')"]
    p = d / name
    p.write_bytes((newline.join(lines) + newline).encode())
    return p


def test_auto() -> None:
    print("\n[3] needs_uv and KIT_RUNNER=auto")
    d = Path(tmp_dir("pep723-"))
    major, minor = sys.version_info[:2]
    here = f"{major}.{minor}"
    ahead = f"{major}.{minor + 1}"
    behind = f"{major}.{minor - 1}"
    plain = pep723(d, "plain.py", f'requires-python = ">={behind}"\n'
                   "dependencies = []")
    rows = {
        "no dependencies, requires-python met": (plain, False),
        "a block with no requires-python and no dependencies": (
            pep723(d, "norequires.py", "dependencies = []"), False),
        "dependencies": (pep723(d, "deps.py", f'requires-python = ">={behind}"'
                                '\ndependencies = ["requests>=2"]'), True),
        "dependencies on several lines": (pep723(
            d, "deps2.py", 'dependencies = [\n  "requests>=2",\n  "yaml",\n]'),
            True),
        "requires-python above this interpreter": (pep723(
            d, "ahead.py", f'requires-python = ">={ahead}"'), True),
        "requires-python with an upper bound this interpreter is under": (
            pep723(d, "range.py", f'requires-python = ">={behind},<{ahead}"'),
            False),
        "requires-python with an upper bound this interpreter is over": (
            pep723(d, "over.py", f'requires-python = ">={behind},<{here}"'),
            True),
        "requires-python `>` and `<=` met": (pep723(
            d, "gt.py", f'requires-python = ">{behind}.0, <={ahead}"'), False),
        "requires-python written as three numbers": (pep723(
            d, "triple.py", f'requires-python = ">={behind}.0"'), False),
        "requires-python in a form that is not read (`==`)": (pep723(
            d, "eq.py", f'requires-python = "=={here}.*"'), True),
        "requires-python in a form that is not read (`~=`)": (pep723(
            d, "compat.py", f'requires-python = "~={behind}"'), True),
        "requires-python that is no version": (pep723(
            d, "junk.py", 'requires-python = "recent"'), True),
        "requires-python that is not a string": (pep723(
            d, "num.py", "requires-python = 3.12"), True),
        "no block at all (uv would read the project's dependencies)": (
            pep723(d, "bare.py", None), True),
        "a block that is not TOML": (pep723(d, "broken.py", "this is = = no"),
                                     True),
        "two script blocks": (_two_blocks(d), True),
        "a block that is never closed": (_unclosed(d), True),
        "only a block of another type": (_other_type(d), True),
        "a file that is not there": (d / "nope.py", True),
        "a file that is not UTF-8": (_not_utf8(d), True),
        "CRLF line ends": (pep723(d, "crlf.py", f'requires-python = '
                                  f'">={behind}"', "\r\n"), False),
    }
    for label, (path, want) in rows.items():
        check(f"needs_uv {'is' if want else 'is not'} true: {label}",
              runner.needs_uv(path) is want, runner.needs_uv(path))
    check("needs_uv takes a str as well as a Path",
          runner.needs_uv(str(plain)) is False)

    fake_bin = Path(tmp_dir("bin-"))
    uv = fake_bin / "uv"
    uv.write_text("#!/bin/sh\nexit 0\n")
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    nodeps, deps = plain, d / "deps.py"
    interp = lambda t, a=(): [sys.executable, str(t), *a]  # noqa: E731
    via_uv = lambda t, a=(): [str(uv), "run", str(t), *a]  # noqa: E731
    saved = {k: os.environ.get(k) for k in ("PATH", "KIT_RUNNER")}

    def cmd(target, mode=None, *, path=str(fake_bin), arg=None):
        if mode is None:
            os.environ.pop("KIT_RUNNER", None)
        else:
            os.environ["KIT_RUNNER"] = mode
        os.environ["PATH"] = path
        return (runner.script_cmd(target, ["--json"]) if arg is None
                else runner.script_cmd(target, ["--json"], runner=arg))

    try:
        check("KIT_RUNNER=auto: a script with nothing to install runs under "
              "this interpreter, though uv is on PATH",
              cmd(nodeps, "auto") == interp(nodeps, ["--json"]))
        check("KIT_RUNNER=auto: a script with dependencies runs under uv",
              cmd(deps, "auto") == via_uv(deps, ["--json"]))
        check("KIT_RUNNER=auto: a script whose requires-python is ahead runs "
              "under uv",
              cmd(d / "ahead.py", "auto") == via_uv(d / "ahead.py", ["--json"]))
        check("KIT_RUNNER=auto: a script with no block runs under uv",
              cmd(d / "bare.py", "auto") == via_uv(d / "bare.py", ["--json"]))
        check("KIT_RUNNER=auto: a script that cannot be read runs under uv",
              cmd(d / "nope.py", "auto") == via_uv(d / "nope.py", ["--json"]))
        check("KIT_RUNNER=auto without uv: this interpreter, as uv mode does",
              cmd(deps, "auto", path=str(d)) == interp(deps, ["--json"])
              and cmd(deps, "uv", path=str(d)) == interp(deps, ["--json"]))
        check("KIT_RUNNER=auto: a str target routes the same",
              cmd(str(deps), "auto") == via_uv(str(deps), ["--json"]))
        check("unset: this interpreter for every script, uv on PATH or not",
              cmd(deps) == interp(deps, ["--json"])
              and cmd(nodeps) == interp(nodeps, ["--json"]))
        check("KIT_RUNNER=uv: uv for every script, the one with nothing to "
              "install too (unchanged)",
              cmd(nodeps, "uv") == via_uv(nodeps, ["--json"])
              and cmd(deps, "uv") == via_uv(deps, ["--json"]))
        check("any other KIT_RUNNER word: this interpreter (unchanged)",
              cmd(deps, "pip") == interp(deps, ["--json"])
              and cmd(deps, "AUTO") == interp(deps, ["--json"])
              and cmd(deps, "") == interp(deps, ["--json"]))
        check("the runner argument stands in for the variable: auto with "
              "KIT_RUNNER unset",
              cmd(deps, None, arg="auto") == via_uv(deps, ["--json"])
              and cmd(nodeps, None, arg="auto") == interp(nodeps, ["--json"]))
        check("the runner argument wins over KIT_RUNNER, both ways",
              cmd(nodeps, "uv", arg="auto") == interp(nodeps, ["--json"])
              and cmd(nodeps, "auto", arg="uv") == via_uv(nodeps, ["--json"])
              and cmd(deps, "uv", arg="pip") == interp(deps, ["--json"]))
        check("the runner argument without uv: this interpreter",
              cmd(deps, None, path=str(d), arg="auto") == interp(deps, ["--json"]))
        check("the argv shape is the one uv mode always had",
              cmd(deps, "auto")[:3] == [str(uv), "run", str(deps)])
        check("RUNNERS: the two words that mean something",
              runner.RUNNERS == ("uv", "auto"))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return None


def _two_blocks(d: Path) -> Path:
    p = d / "two.py"
    p.write_text("# /// script\n# dependencies = []\n# ///\n\n"
                 "# /// script\n# dependencies = []\n# ///\nprint('{}')\n")
    return p


def _unclosed(d: Path) -> Path:
    p = d / "unclosed.py"
    p.write_text("# /// script\n# dependencies = []\nprint('{}')\n")
    return p


def _other_type(d: Path) -> Path:
    p = d / "other.py"
    p.write_text("# /// tool\n# x = 1\n# ///\nprint('{}')\n")
    return p


def _not_utf8(d: Path) -> Path:
    p = d / "latin.py"
    p.write_bytes(b"# /// script\n# dependencies = []\n# ///\n# caf\xe9\n")
    return p


def main() -> int:
    _shop.use()
    d = Path(tmp_dir("children-"))

    print("[1] script_cmd")
    os.environ.pop("KIT_RUNNER", None)
    check("default: this interpreter",
          runner.script_cmd(d / "x.py", ["--json"])
          == [sys.executable, str(d / "x.py"), "--json"])
    fake_bin = Path(tmp_dir("bin-"))
    uv = fake_bin / "uv"
    uv.write_text("#!/bin/sh\nexit 0\n")
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    saved_path = os.environ["PATH"]
    os.environ["PATH"] = str(fake_bin)
    try:
        check("uv on PATH but KIT_RUNNER unset: still this interpreter",
              runner.script_cmd("x.py", [])[0] == sys.executable)
        os.environ["KIT_RUNNER"] = "uv"
        check("KIT_RUNNER=uv: uv run <script>",
              runner.script_cmd("x.py", ["a"]) == [str(uv), "run", "x.py", "a"])
        os.environ["PATH"] = str(d)
        check("KIT_RUNNER=uv without uv: this interpreter",
              runner.script_cmd("x.py", [])[0] == sys.executable)
    finally:
        os.environ["PATH"] = saved_path
        os.environ.pop("KIT_RUNNER", None)

    print("\n[2] run_json")
    ok = child(d, "ok.py", "print(json.dumps({'args': sys.argv[1:]}))\n")
    check("exit 0: the child's document",
          runner.run_json(ok, ["--json"]) == {"args": ["--json"]})
    failing = child(d, "failing.py", (
        "print(json.dumps({'error': 'No price on file for A', 'next': "
        "['shop prices set A'], 'code': 'shop_price_missing', 'params': "
        "{'sku': 'A'}}))\nsys.exit(2)\n"))
    e = raises(lambda: runner.run_json(failing, []), runner.ChildFailed)
    check("a failure document -> ChildFailed(error, next, code)",
          e is not None and str(e) == "No price on file for A"
          and e.next == ["shop prices set A"]
          and e.code == {"code": "shop_price_missing", "params": {"sku": "A"}})
    check("ChildFailed is a SkillPackError carrying the child's code",
          isinstance(e, SkillPackError) and failure(e) == e.code)
    rc, out, _ = capture(lambda a: contract.fail(e, cmd=["shop", "q"],
                                                 as_json=True), [])
    check("fail() relays the child's error, next and code",
          rc == 2 and one_doc(out) == {"error": "No price on file for A",
                                       "next": ["shop prices set A"],
                                       **e.code}, out)
    noisy = child(d, "noisy.py", (
        "print('Installed 3 packages in 4ms', file=sys.stderr)\n"
        "print(json.dumps({'error': 'approve needs a person', 'next': "
        "['shop queue approve 1'], 'code': 'confirm_needs_human', 'params': "
        "{'what': 'approve'}}))\n"
        "print('uv: done', file=sys.stderr)\nsys.exit(1)\n"))
    e = raises(lambda: runner.run_json(noisy, []), runner.ChildFailed)
    check("a failed child is read from its document on stdout, whatever "
          "stderr holds (its reason, next and code, not stderr's last line)",
          e is not None and str(e) == "approve needs a person"
          and e.next == ["shop queue approve 1"]
          and e.code == {"code": "confirm_needs_human",
                         "params": {"what": "approve"}}, e)
    quiet_fail = child(d, "quiet_fail.py", (
        "print(json.dumps({'error': 'no store', 'next': []}))\n"
        "sys.exit(1)\n"))
    e = raises(lambda: runner.run_json(quiet_fail, [], any_exit=True),
               runner.ChildFailed)
    check("a failure document with no code: its error, code None "
          "(relayed: unclassified_error)",
          e is not None and str(e) == "no store" and e.code is None
          and failure(e)["code"] == "unclassified_error", e)
    crash = child(d, "crash.py", "raise RuntimeError('kaboom')\n")
    e = raises(lambda: runner.run_json(crash, []), runner.ChildFailed)
    check("a crash: stderr's last line, no next, unclassified",
          str(e) == "RuntimeError: kaboom" and e.next == [] and e.code is None
          and failure(e)["code"] == "unclassified_error", e)
    silent = child(d, "silent.py", "print('not json')\n")
    e = raises(lambda: runner.run_json(silent, []), runner.ChildFailed)
    check("exit 0 without a JSON document: ChildFailed",
          e is not None and "printed no JSON document" in str(e), e)
    finding = child(d, "finding.py",
                    "print(json.dumps({'stories': []}))\nsys.exit(1)\n")
    check("any_exit: a document without error is the output, whatever the "
          "exit", runner.run_json(finding, [], any_exit=True) == {"stories": []})
    check("… without any_exit it is a failure",
          raises(lambda: runner.run_json(finding, []), runner.ChildFailed)
          is not None)
    check("any_exit: an error document still raises",
          raises(lambda: runner.run_json(failing, [], any_exit=True),
                 runner.ChildFailed) is not None)
    hung = child(d, "hung.py", "import time; time.sleep(30)\n")
    e = raises(lambda: runner.run_json(hung, [], timeout=0.5),
               runner.ChildFailed)
    check("a hung child times out as ChildFailed",
          e is not None and "timed out" in str(e), e)
    os.environ["SHOP_SEEN"] = "yes"
    env_child = child(d, "env.py", "import os\n"
                      "print(json.dumps(os.environ.get('SHOP_SEEN')))\n")
    check("the child inherits this process's env",
          runner.run_json(env_child, []) == "yes")
    del os.environ["SHOP_SEEN"]
    test_auto()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
