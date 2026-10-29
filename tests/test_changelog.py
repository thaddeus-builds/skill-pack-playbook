"""CHANGELOG.md names every kit version and stays in order.

A skill pack re-vendors the kit and reads this file to learn what changed, so a
`kit/VERSION` bump without an entry is a defect. Checked: `## [Unreleased]` first,
then one `## [X.Y.Z] - DATE` per release, versions strictly descending, dates never
increasing, the newest heading equal to `kit/VERSION`, and the Zylos host version
named in the file. From 0.45.0 on, each version also says what a skill pack has to do:
a line `- Skill packs: nothing`, `- Skill packs: mechanical (...)` or `- Skill packs:
judgement (...)`, so a pack's own session can act on it without asking (mechanical is
one command, `python3 tools/fleet.py update`; judgement is the pack's call).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
HEAD = re.compile(r"^## \[([^\]]+)\](?: - (\d{4}-\d\d-\d\d))?", re.M)


def read(path: str) -> str:
    return open(os.path.join(ROOT, path), encoding="utf-8").read().strip()


def releases() -> list[tuple[str, str]]:
    return [(n, d) for n, d in HEAD.findall(LOG) if n != "Unreleased"]


def key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


FIRST_WITH_TODO = (0, 45, 0)
TODO = re.compile(r"^- Skill packs: (nothing|mechanical \(.+\)|judgement \(.+\))$", re.M)


def todo_problems(log: str) -> list[str]:
    """The versions from 0.45.0 on whose section has no (or a malformed) `- Skill packs:` line."""
    out = []
    parts = re.split(r"^## \[([^\]]+)\].*$", log, flags=re.M)
    for name, body in zip(parts[1::2], parts[2::2]):
        if re.fullmatch(r"\d+\.\d+\.\d+", name) and key(name) >= FIRST_WITH_TODO and not TODO.search(body):
            out.append(f"{name}: no line '- Skill packs: nothing | mechanical (...) | judgement (...)'")
    return out


def test_every_version_from_0_45_0_says_what_a_skill_pack_does():
    assert todo_problems(LOG) == [], todo_problems(LOG)
    good = "## [0.45.0] - 2026-11-01\n- x\n- Skill packs: mechanical (python3 tools/fleet.py update)\n"
    assert todo_problems(good) == []
    for label, bad in (("missing", "## [0.45.0] - 2026-11-01\n- x\n"),
                       ("no kind", "## [0.45.0] - 2026-11-01\n- Skill packs: soon\n"),
                       ("no detail", "## [0.45.0] - 2026-11-01\n- Skill packs: judgement\n"),
                       ("the newest of two", good + "## [0.46.0] - 2026-11-02\n- y\n")):
        assert todo_problems(bad), label
    assert todo_problems("## [0.44.0] - 2026-10-26\n- old entry, before the rule\n") == []
    assert todo_problems("## [Unreleased]\n- not yet a version\n") == []


def test_shape():
    names = [n for n, _ in HEAD.findall(LOG)]
    assert names[:1] == ["Unreleased"], names[:2]
    rel = releases()
    assert rel and all(re.fullmatch(r"\d+\.\d+\.\d+", n) and d for n, d in rel), rel[:3]
    versions = [key(n) for n, _ in rel]
    assert versions == sorted(set(versions), reverse=True), [n for n, _ in rel]
    dates = [d for _, d in rel]
    assert dates == sorted(dates, reverse=True), dates


def test_kit_version_has_its_entry():
    newest = releases()[0][0]
    assert read("kit/VERSION") == newest, (
        f"kit/VERSION is {read('kit/VERSION')} but the newest CHANGELOG entry is "
        f"{newest}: a version bump needs its entry (CLAUDE.md)")


def test_host_version_is_named():
    host = read("hosts/zylos/VERSION")
    assert f"hosts/zylos` {host}" in LOG, f"hosts/zylos {host} is not named in CHANGELOG.md"


def _git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                          cwd=cwd, capture_output=True, text=True, env=env)


def _two_branches(attributes: str | None) -> tuple[str, str]:
    """A repository where `a` and `b` each add an entry (two lines) at the top of [Unreleased]; returns its path and the folder to clean."""
    root = tempfile.mkdtemp(prefix="changelog-union-")
    assert _git(root, "init", "-q", "-b", "main").returncode == 0
    base = "## [Unreleased]\n\n### Kit\n- old\n- Skill packs: nothing\n"
    if attributes is not None:
        open(os.path.join(root, ".gitattributes"), "w", encoding="utf-8").write(attributes)
    open(os.path.join(root, "CHANGELOG.md"), "w", encoding="utf-8").write(base)
    _git(root, "add", "-A"), _git(root, "commit", "-qm", "base")
    for name in ("a", "b"):
        _git(root, "switch", "-q", "-c", name, "main")
        open(os.path.join(root, "CHANGELOG.md"), "w", encoding="utf-8").write(
            base.replace("### Kit\n", f"### Kit\n- entry {name}\n- Skill packs: judgement ({name})\n"))
        _git(root, "commit", "-qam", name)
    return root, root


def test_two_pull_requests_adding_entries_at_the_top_do_not_conflict():
    attributes = open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8").read()
    assert re.search(r"^CHANGELOG\.md\s+merge=union\s*$", attributes, re.M), attributes
    pairs = ("- entry a\n- Skill packs: judgement (a)\n", "- entry b\n- Skill packs: judgement (b)\n")
    for how in ("merge", "rebase"):
        root, tmp = _two_branches(attributes)
        try:
            _git(root, "switch", "-q", "b")
            r = _git(root, "merge", "-q", "a") if how == "merge" else _git(root, "rebase", "a")
            log = open(os.path.join(root, "CHANGELOG.md"), encoding="utf-8").read()
            assert r.returncode == 0, (how, r.stdout, r.stderr)
            assert all(p in log for p in pairs) and "- old\n- Skill packs: nothing\n" in log, (how, log)
            assert not re.search(r"^(<<<<<<<|=======|>>>>>>>)", log, re.M), (how, log)
            assert todo_problems(log.replace("## [Unreleased]", "## [0.99.0] - 2099-01-01")) == [], (how, log)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    root, tmp = _two_branches(None)   # the premise: without the setting the same merge is a conflict
    try:
        _git(root, "switch", "-q", "b")
        assert _git(root, "merge", "-q", "a").returncode != 0, "no conflict without the file: the test proves nothing"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    _t.main(globals())
