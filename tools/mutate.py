#!/usr/bin/env python3
"""Break one line of a file on purpose and see whether the tests notice: "a rule nothing enforces is deleted" (CLAUDE.md), made a command.

    python3 tools/mutate.py SOURCE MUTANTS --test "python3 tests/test_x.py" [--timeout 600] [--json]

SOURCE is the file to break. MUTANTS is a text file of breaks, separated by a line `####`; in each, the text to replace and its replacement are
separated by a line `=>>` (the replacement may be empty). For each break the tool writes SOURCE with that text replaced, runs the `--test` command
from the current folder, and puts SOURCE back. A break the test run fails on is CAUGHT; one it passes is SURVIVED, and the rule behind it is not
checked by that test. Exit 0 only when every break was caught.

What it refuses, so that a pass means something:
  - the test command must pass on the unbroken file first (otherwise every break would "fail" for the wrong reason);
  - the text to replace must be in SOURCE exactly once (otherwise it is not clear which place was broken);
  - a Python SOURCE must still compile after the break (a SyntaxError is caught by anything, so it proves nothing): that break is INVALID and fails the run;
  - a break whose test run times out is TIMEOUT, not caught, and fails the run (a hang is not a verdict).
SOURCE is put back byte for byte after every break, and on an exception, Ctrl-C or SIGTERM too.

Stdlib only, Python 3.11+. Test: tests/test_mutate.py.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import signal
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True


class Refused(Exception):
    """The input cannot be run honestly; the message says what to change."""


def parse(text: str) -> list[tuple[str, str]]:
    """[(old, new)] from a mutants file. Each block is `old`, a line `=>>`, `new`; blocks are separated by a line `####`."""
    out = []
    blocks = [b for b in re.split(r"^####[ \t]*$", text.replace("\r\n", "\n"), flags=re.M) if b.strip()]
    for n, block in enumerate(blocks, 1):
        parts = re.split(r"^=>>[ \t]*$", block, flags=re.M)
        if len(parts) != 2:
            raise Refused(f"break {n}: wants one line `=>>` between the text to replace and its replacement, found {len(parts) - 1}")
        old, new = parts[0].strip("\n"), parts[1].strip("\n")
        if not old.strip():
            raise Refused(f"break {n}: the text to replace is empty")
        out.append((old, new))
    if not out:
        raise Refused("the mutants file holds no break")
    return out


def run_test(cmd: list[str], timeout: float) -> tuple[str, str]:
    """('pass' | 'fail' | 'timeout', the tail of its output)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout", ""
    return ("pass" if r.returncode == 0 else "fail"), (r.stdout + r.stderr)[-600:]


def mutate(source: Path, mutants: list[tuple[str, str]], cmd: list[str], timeout: float = 600.0) -> list[dict]:
    """One result per break: {n, old, new, verdict}, verdict one of caught, survived, invalid, timeout. SOURCE is the same bytes afterwards."""
    original = source.read_bytes()
    text = original.decode("utf-8")
    for n, (old, _) in enumerate(mutants, 1):
        if text.count(old) != 1:
            raise Refused(f"break {n}: the text to replace is in {source} {text.count(old)} times, not once: {old[:70]!r}")
    base, tail = run_test(cmd, timeout)
    if base != "pass":
        raise Refused(f"the test command does not pass on the unbroken file ({base}); fix that first.\n{tail}")

    def restore(*_):
        source.write_bytes(original)
        raise KeyboardInterrupt
    old_handlers = {s: signal.signal(s, restore) for s in (signal.SIGTERM, signal.SIGINT)}
    results = []
    try:
        for n, (old, new) in enumerate(mutants, 1):
            broken = text.replace(old, new)
            verdict = None
            if source.suffix == ".py":
                try:
                    compile(broken, str(source), "exec")
                except SyntaxError:
                    verdict = "invalid"
            if verdict is None:
                source.write_text(broken, encoding="utf-8")
                got, _ = run_test(cmd, timeout)
                verdict = {"fail": "caught", "pass": "survived", "timeout": "timeout"}[got]
            results.append({"n": n, "old": old, "new": new, "verdict": verdict})
    finally:
        source.write_bytes(original)
        for s, h in old_handlers.items():
            signal.signal(s, h)
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Break one line of a file on purpose and see whether the tests notice.")
    ap.add_argument("source", type=Path)
    ap.add_argument("mutants", type=Path)
    ap.add_argument("--test", required=True, help='the command that must fail on a break, e.g. "python3 tests/test_x.py"')
    ap.add_argument("--timeout", type=float, default=600.0, help="seconds per test run (default 600)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if not a.source.is_file():
            raise Refused(f"{a.source} is not a file")
        results = mutate(a.source, parse(a.mutants.read_text(encoding="utf-8")), shlex.split(a.test), a.timeout)
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    bad = [r for r in results if r["verdict"] != "caught"]
    if a.json:
        print(json.dumps({"results": results, "not_caught": len(bad)}, indent=2))
    else:
        for r in results:
            print(f"{r['verdict'].upper():9} {r['n']:>3}  {r['old'].splitlines()[0][:80]}")
        print(f"{len(results) - len(bad)} of {len(results)} breaks caught" + (f"; {len(bad)} NOT: {', '.join(str(r['n']) for r in bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
