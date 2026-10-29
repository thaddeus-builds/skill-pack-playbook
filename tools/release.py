#!/usr/bin/env python3
"""The release train as one command (docs/maintaining.md, "The release train"; issue #222).

    python3 tools/release.py X.Y.Z [--date YYYY-MM-DD] [--urgent "why"] [--dry-run] [--root DIR]

Sets `kit/VERSION`, turns `## [Unreleased]` into `## [X.Y.Z] - DATE` (a new empty `## [Unreleased]` above it), regenerates
`kit/MANIFEST.sha256` and runs `tests/test_changelog.py`. It commits nothing: read `git diff`, then commit, then run
`python3 tools/fleet.py update PACK...` from that commit.

It refuses, so that the train cannot be started wrongly:
  - an `[Unreleased]` with no entry, or an entry without its own `- Skill packs: nothing | mechanical (...) | judgement (...)` line
    right after it (`nothing` may carry a parenthesis saying why) (the train would otherwise ship a version a pack's session cannot act on);
  - a version that is not above `kit/VERSION`, or one the CHANGELOG already has (a release note is never rewritten);
  - a train less than 7 days after the last one, unless `--urgent "why"` is given and the bump is a patch;
  - a date earlier than the last release's.
It prints what the entries ask of a skill pack (nothing / mechanical / judgement, counted) for the pull request.

Stdlib only, Python 3.11+. Test: tests/test_release.py.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

sys.dont_write_bytecode = True

HEAD = re.compile(r"^## \[([^\]]+)\](?: - (\d{4}-\d\d-\d\d))?", re.M)
SKILL = re.compile(r"^- Skill packs: (nothing(?: \(.+\))?|mechanical \(.+\)|judgement \(.+\))$")
UNRELEASED = "## [Unreleased]\n"


class Refused(Exception):
    """The train cannot start; the message says what to change."""


def key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def unreleased(log: str) -> str:
    m = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[|\Z)", log, re.M | re.S)
    if not m:
        raise Refused("CHANGELOG.md has no `## [Unreleased]` heading")
    return m.group(1)


def entry_problems(body: str) -> list[str]:
    """Every entry (a top-level bullet that is not a Skill packs line) is followed at once by its own Skill packs line."""
    out, entry = [], None
    for line in body.splitlines():
        if not line.startswith("- "):
            continue
        if line.startswith("- Skill packs:"):
            if entry is None:
                out.append(f"a Skill packs line with no entry before it: {line[:70]!r}")
            elif not SKILL.match(line):
                out.append(f"malformed Skill packs line after {entry[:50]!r}: {line[:70]!r}")
            entry = None
        else:
            if entry is not None:
                out.append(f"no Skill packs line after {entry[:70]!r}")
            entry = line
    if entry is not None:
        out.append(f"no Skill packs line after {entry[:70]!r}")
    return out


def asks(body: str) -> dict[str, int]:
    kinds = {"nothing": 0, "mechanical": 0, "judgement": 0}
    for line in body.splitlines():
        m = SKILL.match(line)
        if m:
            kinds[m.group(1).split(" ")[0]] += 1
    return kinds


def check(log: str, current: str, version: str, day: date, urgent: str | None) -> dict[str, int]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise Refused(f"{version!r} is not X.Y.Z")
    if key(version) <= key(current):
        raise Refused(f"{version} is not above kit/VERSION {current}")
    heads = [(n, d) for n, d in HEAD.findall(log) if n != "Unreleased"]
    if any(n == version for n, _ in heads):
        raise Refused(f"the CHANGELOG already has {version}: a release note is never rewritten")
    body = unreleased(log)
    if not any(line.startswith("- ") and not line.startswith("- Skill packs:") for line in body.splitlines()):
        raise Refused("[Unreleased] has no entry: nothing to release")
    problems = entry_problems(body)
    if problems:
        raise Refused("[Unreleased] is not ready:\n  " + "\n  ".join(problems))
    last = datetime.strptime(heads[0][1], "%Y-%m-%d").date() if heads and heads[0][1] else None
    if last:
        if day < last:
            raise Refused(f"the date {day} is earlier than the last release's {last}")
        if (day - last).days < 7:
            cur, new = key(current), key(version)
            if not urgent:
                raise Refused(f"the last train ran on {last}, {(day - last).days} day(s) ago: at most weekly; "
                              "an urgent patch says why with --urgent \"...\"")
            if new[:2] != cur[:2]:
                raise Refused("an urgent train in between is a patch (X.Y.Z+1); a minor or a major waits for the train day")
    return asks(body)


def release(root: Path, version: str, day: date, urgent: str | None = None, dry_run: bool = False) -> dict:
    log_path, ver_path = root / "CHANGELOG.md", root / "kit" / "VERSION"
    log = log_path.read_text("utf-8")
    current = ver_path.read_text("utf-8").strip()
    kinds = check(log, current, version, day, urgent)
    done = {"version": version, "previous": current, "date": day.isoformat(), "asks": kinds, "written": not dry_run}
    if dry_run:
        return done
    log_path.write_text(log.replace(UNRELEASED, f"{UNRELEASED}\n## [{version}] - {day.isoformat()}\n", 1), "utf-8")
    ver_path.write_text(version + "\n", "utf-8")
    subprocess.run([sys.executable, str(root / "kit" / "tools" / "manifest.py"), str(root / "kit")], check=True, capture_output=True)
    gate = root / "tests" / "test_changelog.py"
    if gate.is_file():
        r = subprocess.run([sys.executable, str(gate)], capture_output=True, text=True, cwd=root)
        done["changelog_test"] = "ok" if r.returncode == 0 else (r.stdout + r.stderr)[-600:]
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Start the release train: version, CHANGELOG heading, manifest.")
    ap.add_argument("version")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--urgent", help="why a train runs less than 7 days after the last one (a patch only)")
    ap.add_argument("--dry-run", action="store_true", help="check and report, write nothing")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    a = ap.parse_args(argv)
    try:
        r = release(a.root, a.version, date.fromisoformat(a.date), a.urgent, a.dry_run)
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    k = r["asks"]
    print(f"{'would release' if a.dry_run else 'released'} {r['previous']} -> {r['version']} on {r['date']}: "
          f"{k['judgement']} judgement, {k['mechanical']} mechanical, {k['nothing']} nothing")
    if r.get("changelog_test") not in (None, "ok"):
        print(f"tests/test_changelog.py FAILED:\n{r['changelog_test']}", file=sys.stderr)
        return 1
    if not a.dry_run:
        print("next: read `git diff`, commit, then `python3 tools/fleet.py update PACK...` from that commit; "
              "after the merge, look at every open pull request's CHANGELOG entry (docs/maintaining.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
