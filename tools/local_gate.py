#!/usr/bin/env python3
"""The local gate every skill pack merges through: the suite runs here, not on a forge whose minutes may be unpaid (R49).

    python3 tools/local_gate.py status SKILL_PACK...
    python3 tools/local_gate.py install SKILL_PACK...
    python3 tools/local_gate.py run SKILL_PACK [--fresh] [--remote NAME]

`status` says, for each pack, the suite it runs (`[skill_pack].test_command` in skill-pack.toml, else `python3 tests/run.py`),
whether this clone refuses a push whose suite fails (a pre-push hook plus `git config skillpack.prepush-tests`), and which CI
workflows start by themselves (a `pull_request`, `push` or `schedule` trigger): with GitHub unpaid each of them fails in two
seconds and checks nothing (docs/lessons.md, "A pipeline that fails with zero steps").

`install` sets this clone up: the kit's `pre-push.sample` (the pack's vendored copy) becomes the hook when there is none, and
`skillpack.prepush-tests` is set to the pack's suite. It never replaces a hook that is already there and never touches a
tracked file; the setting is the clone's own, so run it once on each machine.

`run` is the check before a merge: the current commit with the remote's default branch merged in (a throwaway worktree; the
checkout is not touched), the pack's suite on that result, and with `--fresh` a second run on a fresh clone of the default
branch, which shows what main lacks (run it after the merge to check main itself). The last line is `GATE: green` or `GATE: red (why)`; the exit code is 0 only
for green.

Stdlib only, Python 3.11+. Test: tests/test_local_gate.py.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("fleet", HERE / "fleet.py")
fleet = importlib.util.module_from_spec(_spec)
sys.modules["fleet"] = fleet
_spec.loader.exec_module(fleet)

SETTING = "skillpack.prepush-tests"
AUTO_TRIGGER = re.compile(r"^\s{2}(pull_request|pull_request_target|push|schedule):", re.M)
SAMPLE_PATHS = ("scripts/kit/tools/pre-push.sample", "kit/tools/pre-push.sample")


def git(pack: Path, *args: str) -> subprocess.CompletedProcess:
    return fleet.run(pack, "git", *args, env=fleet.git_env(pack))


def suite_text(pack: Path) -> str:
    """The suite as a line to store: the default's interpreter is written `python3`, not this machine's path."""
    cmd = fleet.suite_command(pack)
    return shlex.join(["python3" if c == sys.executable else c for c in cmd])


def auto_workflows(pack: Path) -> list[str]:
    """The workflow files that start without a click."""
    out = []
    for f in sorted((pack / ".github" / "workflows").glob("*.y*ml")):
        text = f.read_text("utf-8", "replace")
        on = text.split("\non:\n", 1)[1].split("\n\n", 1)[0] if "\non:\n" in text else ""
        if AUTO_TRIGGER.search(on) or re.search(r"^on:\s*\[?.*\b(push|pull_request|schedule)\b", text, re.M):
            out.append(f.name)
    return out


def hook_file(pack: Path) -> Path | None:
    """The pre-push hook git will run in this clone, or None."""
    path = git(pack, "config", "--get", "core.hooksPath").stdout.strip()
    if path:
        base = Path(path) if Path(path).is_absolute() else pack / path
    else:
        common = git(pack, "rev-parse", "--git-common-dir").stdout.strip()
        base = (pack / common if not Path(common).is_absolute() else Path(common)) / "hooks"
    hook = base / "pre-push"
    return hook if hook.is_file() else None


def status(pack: Path) -> dict:
    hook = hook_file(pack)
    setting = git(pack, "config", "--get", SETTING).stdout.strip()
    own_suite = "skill-pack.toml" in {p.name for p in pack.iterdir()} and bool(
        fleet.read_toml(pack / "skill-pack.toml").get("skill_pack", {}).get("test_command"))
    auto = auto_workflows(pack)
    gated = bool(hook and setting)
    return {"pack": pack.name, "suite": suite_text(pack), "suite_declared": own_suite, "hook": str(hook) if hook else None,
            "setting": setting or None, "auto_ci": auto, "gated": gated}


def render(doc: dict) -> str:
    out = [f"{doc['pack']}: {'gated' if doc['gated'] else 'NOT gated'}",
           f"  suite       {doc['suite']}" + ("" if doc["suite_declared"] else "   (default; declare [skill_pack].test_command)"),
           f"  hook        {doc['hook'] or 'none'}",
           f"  {SETTING}  {doc['setting'] or 'unset'}",
           f"  auto CI     {', '.join(doc['auto_ci']) or 'none'}"]
    return "\n".join(out)


def install(pack: Path) -> tuple[bool, str]:
    if hook_file(pack) is None:
        sample = next((pack / p for p in SAMPLE_PATHS if (pack / p).is_file()), None)
        if sample is None:
            return False, "no vendored kit/tools/pre-push.sample to install as the hook"
        common = git(pack, "rev-parse", "--git-common-dir").stdout.strip()
        hooks = (pack / common if not Path(common).is_absolute() else Path(common)) / "hooks"
        if git(pack, "config", "--get", "core.hooksPath").stdout.strip():
            return False, "core.hooksPath is set but holds no pre-push hook: add one there, install changes nothing"
        hooks.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sample, hooks / "pre-push")
        (hooks / "pre-push").chmod(0o755)
    r = git(pack, "config", SETTING, suite_text(pack))
    if r.returncode != 0:
        return False, fleet.first_line(r)
    return True, f"hook ok, {SETTING} = {suite_text(pack)}"


RESULT_LINE = re.compile(r"^RESULT: \d+ passed$", re.M)


def run_suite(cwd: Path) -> tuple[int, str]:
    """Exit code and the line that sums the run up. A suite that exits 0 without printing `RESULT: N passed` stopped early or
    ran nothing, so it is red (the same rule as the packs' CI jobs)."""
    r = fleet.run(cwd, *fleet.suite_command(cwd), env=None)
    out = r.stdout + r.stderr
    found = RESULT_LINE.findall(out)
    if r.returncode == 0 and not found:
        return 1, "no `RESULT: N passed` line"
    lines = [ln for ln in out.splitlines() if ln.startswith("RESULT:")]
    return r.returncode, lines[-1] if lines else (out.strip().splitlines() or [f"exit {r.returncode}"])[-1]


def gate(pack: Path, fresh: bool, remote: str = "origin") -> tuple[bool, str]:
    branch = fleet.default_branch(pack, remote)
    if not branch:
        return False, f"cannot tell {remote}'s default branch"
    f = git(pack, "fetch", "-q", remote, branch)
    if f.returncode != 0:
        return False, f"fetch failed: {fleet.first_line(f)}"
    with tempfile.TemporaryDirectory(prefix="gate-") as tmp:
        work = Path(tmp) / "merged"
        w = git(pack, "worktree", "add", "--detach", str(work), "HEAD")
        if w.returncode != 0:
            return False, f"worktree failed: {fleet.first_line(w)}"
        try:
            m = fleet.run(work, "git", "-c", "user.name=gate", "-c", "user.email=gate@localhost", "merge", "--no-edit", f"{remote}/{branch}")
            if m.returncode != 0:
                return False, f"HEAD does not merge with {remote}/{branch}: {fleet.first_line(m)}"
            code, last = run_suite(work)
            print(f"merged with {remote}/{branch}: {last}")
            if code != 0:
                return False, f"the suite failed on the merge result ({last})"
        finally:
            git(pack, "worktree", "remove", "--force", str(work))
        if fresh:
            address = fleet.remote_address(pack, remote)
            if not address:
                return False, f"{remote} has no address to clone"
            clone = Path(tmp) / "fresh"
            c = fleet.run(Path(tmp), "git", "clone", "-q", "--branch", branch, address, str(clone), env=fleet.git_env(pack))
            if c.returncode != 0:
                return False, f"fresh clone failed: {fleet.first_line(c)}"
            code, last = run_suite(clone)
            print(f"fresh clone of {branch}: {last}")
            if code != 0:
                return False, f"the suite failed on a fresh clone of {branch} ({last})"
    return True, ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").add_argument("skill_pack", nargs="+")
    sub.add_parser("install").add_argument("skill_pack", nargs="+")
    r = sub.add_parser("run")
    r.add_argument("skill_pack")
    r.add_argument("--fresh", action="store_true", help="also run the suite on a fresh clone of the default branch")
    r.add_argument("--remote", default="origin")
    args = ap.parse_args(argv)
    packs = [Path(p).expanduser().resolve() for p in (args.skill_pack if isinstance(args.skill_pack, list) else [args.skill_pack])]
    for p in packs:
        if not (p / ".git").exists():
            print(f"error: {p} is not a git checkout", file=sys.stderr)
            return 2
    if args.cmd == "status":
        docs = [status(p) for p in packs]
        print("\n\n".join(render(d) for d in docs))
        return 0 if all(d["gated"] and not d["auto_ci"] for d in docs) else 1
    if args.cmd == "install":
        results = [(p, *install(p)) for p in packs]
        for p, ok, text in results:
            print(f"{p.name}: {'ok' if ok else 'refused'}: {text}")
        return 0 if all(ok for _, ok, _ in results) else 1
    ok, why = gate(packs[0], args.fresh, args.remote)
    print("GATE: green" if ok else f"GATE: red ({why})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
