"""How one skill pack script runs another, and reads its one JSON document.

`script_cmd` is the argv that runs a script: this interpreter
(`sys.executable`), or `uv run <script>` by KIT_RUNNER (or the `runner`
argument, which wins over it):

  unset, or any other word   this interpreter
  uv                         `uv run <script>` for every script (a skill pack
                             whose scripts all declare PEP 723 dependencies)
  auto                       `uv run <script>` only for a script that needs
                             it (`needs_uv`), this interpreter for the rest:
                             a second interpreter start is not paid for a
                             script with nothing to install, and a host
                             without uv still runs every such verb

uv missing = this interpreter, as a direct run would be, in both modes.

`needs_uv(script)` is the rule `auto` applies: true when the script's PEP 723
block lists dependencies or asks for a Python this interpreter is not (only
`>=`, `>`, `<=`, `<` over dotted numbers are read: any other form, an
unparsable or repeated block, an unreadable file, is true: uv decides); true
too for a script with no block at all, since `uv run` would take its
dependencies from the project; a block with no dependencies and no
requires-python is false.

`run_json` is how a verb snapshots another verb's `--json` (a queue
snapshotting a compute, a story check running a read verb): a failed
child printed its one failure document on stdout (kit.contract.fail), so
that is where its reason, fix commands and message code are; stderr
holds only notices or a crash's traceback. A failure is `ChildFailed`, a
SkillPackError that keeps the child's own code (messages.relayed), so the
parent's fail() reports the child's reason, not a generic one.

Test: kit/tests/test_runner.py.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from kit.contract import SkillPackError

RUNNER_ENV = "KIT_RUNNER"
RUNNERS = ("uv", "auto")      # the values that mean something; any other = this interpreter

# PEP 723's reference pattern (a block: `# /// script` ... `# ///`, every line between a comment)
_BLOCK = re.compile(r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$")
_CLAUSE = re.compile(r"(>=|<=|>|<)\s*(\d+(?:\.\d+){0,2})")


def _python_met(spec: str) -> bool:
    """Whether this interpreter meets a requires-python made of `>=`, `>`,
    `<=` and `<` clauses over dotted numbers (empty meets any). Any other
    form is not decided here: False."""
    if not spec.strip():
        return True
    here = tuple(sys.version_info[:3])
    for clause in spec.split(","):
        m = _CLAUSE.fullmatch(clause.strip())
        if m is None:
            return False
        want = tuple(int(n) for n in m.group(2).split("."))
        want += (0,) * (3 - len(want))
        ok = {">=": here >= want, ">": here > want,
              "<=": here <= want, "<": here < want}[m.group(1)]
        if not ok:
            return False
    return True


def needs_uv(script: Path | str) -> bool:
    """Whether `uv run` has something to do for `script` that this
    interpreter cannot (the rule of KIT_RUNNER=auto; see the module
    docstring). Any failure to read or parse it is True."""
    try:
        text = Path(script).read_text(encoding="utf-8")
        blocks = [m for m in _BLOCK.finditer(text) if m.group("type") == "script"]
        if len(blocks) != 1:
            return True            # none: dependencies may come from the project; two: invalid
        meta = tomllib.loads("".join(
            ln[2:] if ln.startswith("# ") else ln[1:]
            for ln in blocks[0].group("content").splitlines(keepends=True)))
        return bool(meta.get("dependencies")) or not _python_met(
            str(meta.get("requires-python", "")))
    except Exception:
        return True


def script_cmd(target: Path | str, args: list[str], *,
               runner: str | None = None) -> list[str]:
    """The argv that runs the script at `target` with `args`. `runner`
    (`uv`, `auto`, or any other word for this interpreter) stands in for
    KIT_RUNNER when it is not None."""
    mode = os.environ.get(RUNNER_ENV) if runner is None else runner
    uv = (shutil.which("uv")
          if mode == "uv" or (mode == "auto" and needs_uv(target)) else None)
    return ([uv, "run", str(target), *args] if uv
            else [sys.executable, str(target), *args])


class ChildFailed(SkillPackError):
    """A child script failed. str() = its failure document's `error`;
    `next` = its fix commands; `code` = its {code, params}. A child that
    died without a document (a crash): stderr's last line, [] and None."""

    def __init__(self, error: str, next: list[str], code: dict | None):
        try:
            from kit.messages import relayed
            message = relayed(code, error)
        except Exception:        # no bound skill pack: keep the plain text
            message = error
        super().__init__(message, next)
        self.code = code


def run_json(target: Path | str, args: list[str], *, any_exit: bool = False,
             timeout: float | None = None) -> dict | list:
    """The one JSON document the script at `target` prints for `args` (its
    `--json` among them), run as script_cmd runs it, with this process's
    env. A non-zero exit raises ChildFailed with the child's own failure
    document. `any_exit`: a document without `error` is the child's output
    whatever its exit (an exit code that flags a finding the document
    carries); no JSON document raises ChildFailed even on exit 0."""
    try:
        r = subprocess.run(script_cmd(target, args), capture_output=True,
                           text=True, env=os.environ, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise ChildFailed(f"{Path(target).name} timed out after {timeout}s",
                          [], None) from None
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = None
    if r.returncode == 0 and not any_exit and doc is not None:
        return doc
    if doc is not None and any_exit and (r.returncode == 0 or not (
            isinstance(doc, dict) and "error" in doc)):
        return doc
    if isinstance(doc, dict) and "error" in doc:
        code = ({"code": doc["code"], "params": doc.get("params") or {}}
                if doc.get("code") else None)
        raise ChildFailed(str(doc["error"]), list(doc.get("next") or []),
                          code)
    last = (r.stderr.strip().splitlines()
            or [f"{Path(target).name} printed no JSON document "
                f"(exit {r.returncode})"])[-1]
    raise ChildFailed(last, [], None)
