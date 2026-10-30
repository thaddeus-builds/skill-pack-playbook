#!/usr/bin/env python3
"""Where each skill pack's vendored copies stand against this playbook.

    python3 tools/fleet.py status SKILL_PACK... [--json]
    python3 tools/fleet.py diff SKILL_PACK [FILE...]
    python3 tools/fleet.py update SKILL_PACK... [--version X] [--no-tests]
    python3 tools/fleet.py export SKILL_PACK... --out DIR [--remote NAME]
    python3 tools/fleet.py rehearse SKILL_PACK... --out DIR [--remote NAME]

For each skill pack it reads the kit (<scripts_dir>/kit/), the console
(console/) and the Zylos adapter (zylos/), whichever it holds, and compares
each file with the playbook's current copy (kit/, console/, hosts/zylos/):

  * same: equal to the playbook's current file;
  * older: equal to an earlier version of the playbook's file, found in the
    playbook's git history (the kit or adapter VERSION at that commit is
    named: the version in which that content first appeared): re-vendoring brings it up to date and loses nothing;
  * local: in no version the playbook ever had. This is a local change:
    upstream it (a fix here, with its test) or drop it before re-vendoring;
  * missing: the playbook has it and the copy does not (the copy is older);
  * extra: the copy has it and the playbook does not now (removed upstream,
    when history has it; a local file otherwise). A `VERSION` the playbook's
    folder lacks is the stamp vendor.py writes (the console's) and is read for
    the version, never counted as a file.

`edited` lists the files that differ from the copy's own MANIFEST.sha256
(an edit made after vendoring). The verdict per copy is `in sync`,
`behind` (re-vendor) or `local changes` (decide each file first). Phase 1 of
the 2026-10 restructure (docs/history/restructure-2026-10.md, now ROADMAP.md N2):
bring every skill pack to one kit version.

`diff` prints a unified diff, skill pack copy against the playbook's current
file, for each file that is not the same (or only the FILEs named, as
`kit/facts.py`, `console/core.py` or `zylos/lib.js`).

`rehearse` is `update` tried on a clone, for the days before a train: each skill pack's checkout is cloned into `--out` (its `origin` pointed at the
checkout's own remote address, its local branches dropped), the kit is taken as the playbook has it, released or not, and the pack's suite runs. The
checkouts are only read. A pack that refuses to load a new kit file shows up here, not on the train.

`update` brings each skill pack to this playbook's kit in a worktree of its
own, so the pack's checkout is never touched: it asks `git remote show origin`
for the default branch, fetches it, adds `<repo>_worktrees/kit-<version>` on
branch `claude/kit-<version>` cut from `origin/<default>` (the line says which
remote and commit), runs kit/tools/
vendor.py into it, runs the pack's suite (`[skill_pack].test_command` in its
skill-pack.toml, else `python3 tests/run.py`; `--no-tests` skips it), adds one
line under `## [Unreleased]` of its CHANGELOG.md when it has one, and commits
with the from and to versions and the suite result. One line per pack:

  * green: committed, suite passed (or `not run`);
  * red: committed all the same, the failing test files named;
  * refused: the vendor tool said no (nothing is left behind);
  * exists: the worktree or branch is already there (nothing is touched);
  * current: the pack already holds this kit (nothing is left behind).

`--remote NAME` (default `origin`) is the remote the pack's real default branch
is on, for a pack whose `origin` is archived or stale. `update` refuses (nothing
is left behind) when the checkout's own default branch has commits the remote's
does not: that is what a stale remote looks like, and a branch cut from it would
have to be moved by hand (issue #316). It refuses too when another remote of the pack
has commits on that branch the chosen remote's lacks (a pack whose home moved from one
server to another and whose `origin` still names the old one).

`export` writes each pack's default branch on its remote as plain files (`git archive`,
the checkout untouched) into `--out DIR/<folder>`, and says how far the checkout is behind
it. Read `status` and `tools/consumers.py` from those folders: a checkout is often behind
its remote, and the census then describes the checkout, not the pack's main (2026-10-30).

`--version X` names the train being taken and must equal this playbook's
kit/VERSION (the vendor tool copies the checkout it is in). The vendor tool copies
the files as they are, so a checkout whose kit differs from the commit that set
kit/VERSION would label unreleased bytes with the released number: `update`
refuses it (exit 2, the files named) unless `--allow-unreleased`; a playbook git
cannot read is not checked. The commit needs a
git identity: `git config`, or GIT_AUTHOR_* and GIT_COMMITTER_* in the
environment. Exit 0 only when every pack is green or current.

`status` and `diff` are read-only: they write nothing anywhere. Stdlib only;
needs `git` for the history lookups (without history, older and local cannot
be told apart and the report says so). Test: tests/test_fleet.py.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import tomllib
from pathlib import Path

PLAYBOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLAYBOOK))
from kit.testing.run_tests import GIT_LOCAL_ENV  # noqa: E402                the variables that name one repository (a hook or `git rebase --exec` hands them down)
SKIP_DIRS = {"tests", "__pycache__"}
SKIP_FILES = {"MANIFEST.sha256", ".DS_Store"}
# The adapter files a skill pack does not copy (hosts/zylos/README.md), and the
# one it writes itself.
ZYLOS_NOT_COPIED = {"ecosystem.config.cjs.template", "manifest.example.json"}
ZYLOS_OWN = {"manifest.json"}


def files(root: Path, skip: set[str] = frozenset()) -> list[str]:
    """Relative paths under `root`, as vendor.py copies them."""
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if not p.is_file() or SKIP_DIRS & set(rel.parts[:-1]) or p.name in SKIP_FILES \
                or p.suffix == ".pyc" or rel.as_posix() in skip:
            continue
        out.append(rel.as_posix())
    return out


def blob_sha(data: bytes) -> str:
    """The git blob id of `data` (what `git hash-object` prints)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def clean_env(extra: dict | None = None) -> dict:
    """Our environment without the variables that name one repository (GIT_DIR and the rest): every git call here names its folder, and a hook that
    runs this tool would otherwise point them all at the repository that is pushing; plus `extra`."""
    return {**{k: v for k, v in os.environ.items() if k not in GIT_LOCAL_ENV}, **(extra or {})}


def git(playbook: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(playbook), *args], capture_output=True, text=True, env=clean_env())
    return r.stdout if r.returncode == 0 else None


class History:
    """Every blob a playbook path ever had, and the version at that commit."""

    def __init__(self, playbook: Path):
        self.playbook = playbook
        self.ok = git(playbook, "rev-parse", "HEAD") is not None
        self.shallow = (git(playbook, "rev-parse", "--is-shallow-repository") or "").strip() == "true"
        self._blobs: dict[str, dict[str, str]] = {}
        self._versions: dict[tuple[str, str], str] = {}

    def blobs(self, path: str) -> dict[str, str]:
        """{blob id: newest commit that had it} for `path`."""
        if path not in self._blobs:
            out: dict[str, str] = {}
            text = git(self.playbook, "log", "-m", "--format=C %H", "--raw", "--no-abbrev",
                       "--no-renames", "--", path) if self.ok else None
            commit = None
            for line in (text or "").splitlines():
                if line.startswith("C "):
                    commit = line[2:]
                elif line.startswith(":") and commit:
                    new = line.split()[3]
                    if set(new) != {"0"}:
                        out.setdefault(new, commit)
            self._blobs[path] = out
        return self._blobs[path]

    def version(self, commit: str, version_file: str) -> str:
        key = (commit, version_file)
        if key not in self._versions:
            v = git(self.playbook, "show", f"{commit}:{version_file}")
            self._versions[key] = v.strip() if v else "?"
        return self._versions[key]


def read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text("utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def parts(skill_pack: Path, playbook: Path) -> list[dict]:
    """The copies a skill pack can hold: label, playbook dir, copy dir, VERSION file in the playbook."""
    h = read_toml(skill_pack / "skill-pack.toml").get("skill_pack", {})
    scripts = str(h.get("scripts_dir") or "scripts")
    common = {"root": playbook}
    common["skill_pack"] = skill_pack
    return [{**common, **p} for p in (
        {"label": "kit", "src": playbook / "kit", "src_rel": "kit",
         "dest": skill_pack / scripts / "kit", "version_file": "kit/VERSION", "skip": set()},
        {"label": "console", "src": playbook / "console", "src_rel": "console",
         "dest": skill_pack / "console", "version_file": "kit/VERSION", "skip": set()},
        {"label": "zylos", "src": playbook / "hosts" / "zylos", "src_rel": "hosts/zylos",
         "dest": skill_pack / "zylos", "version_file": "hosts/zylos/VERSION",
         "skip": ZYLOS_NOT_COPIED | ZYLOS_OWN},
    )]


NETWORK_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_HTTP_LOW_SPEED_LIMIT": "1", "GIT_HTTP_LOW_SPEED_TIME": "30"}
SSH_COMMAND = "ssh -o ConnectTimeout=20 -o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=4"
REMOTE_SHOW_S, FETCH_S = 60, 300                                    # how long one `git remote show` and one fetch may take before they are given up on


def git_env(cwd: Path | None = None) -> dict[str, str]:
    """What keeps a git call from hanging on a remote that accepts the connection and never answers, or from asking a question nobody is there to
    answer: no prompt, a stall limit for http, and for ssh a connect timeout and keep-alives. A value the caller already set wins, and the ssh command
    is left alone when the caller has one of their own (`GIT_SSH_COMMAND`, `GIT_SSH`, or `core.sshCommand` as `cwd` sees it): theirs may name a key or a port."""
    env = {k: v for k, v in NETWORK_ENV.items() if k not in os.environ}
    if not any(k in os.environ for k in ("GIT_SSH_COMMAND", "GIT_SSH")):
        own = subprocess.run(["git", "config", "--get", "core.sshCommand"], cwd=cwd, capture_output=True, text=True, errors="replace", env=clean_env())
        if not own.stdout.strip():
            env["GIT_SSH_COMMAND"] = SSH_COMMAND
    return env


SECRET_QUERY = re.compile(r"([?&](?:[^=&\s]*(?:token|key|secret|pass|pwd|auth|sig|code|jwt|bearer)[^=&\s]*|t)=)[^&\s]+", re.I)


def hide_credentials(text: str) -> str:
    """`text` (an address, or a line a git error printed) without the user and password of an address, the value of a query parameter that looks like a
    secret (`?token=...`) and the fragment of an address."""
    return SECRET_QUERY.sub(r"\1<hidden>", re.sub(r"(://[^\s#]*)#\S*", r"\1", re.sub(r"(://)[^/\s]*@", r"\1", text)))


def is_network_address(address: str) -> bool:
    """Is `address` a URL or scp-like (`host:path`, `user@host:path`) rather than a path? Git's own rule: a colon before any slash."""
    colon, slash = address.find(":"), address.find("/")
    return "://" in address or (colon > 0 and (slash == -1 or colon < slash))


def remote_address(pack: Path, name: str) -> str | None:
    """The address of the checkout's remote `name`; a relative path is made absolute against the checkout, as git reads it. None when it has none."""
    r = run(pack, "git", "remote", "get-url", name)
    address = r.stdout.strip() if r.returncode == 0 else ""
    if not address or os.path.isabs(address) or is_network_address(address):
        return address or None
    return str((pack / address).resolve())


def inside(out: Path, pack: Path) -> bool:
    """Is `out` the skill pack or a folder inside it? Compared as the file system does (a case-insensitive one, a link), not as text."""
    here = out
    while True:
        try:
            if here.exists() and os.path.samefile(here, pack):
                return True
        except OSError:
            pass
        if here.parent == here:
            return False
        here = here.parent


COPIED_CONFIG = re.compile(r"^(user\.|core\.sshcommand$|credential\.|http\.|url\.)")


def copy_config(pack: Path, dest: Path) -> None:
    """What the checkout's own git configuration gives a command and the clone would lack: who commits (as the checkout sees it, includes and the global
    file too), the ssh command, credential helpers, http settings and address rewrites. Copied into the clone's own config; nothing is printed."""
    for key in ("user.name", "user.email"):
        value = run(pack, "git", "config", "--get", key).stdout.strip()
        if value:
            run(dest, "git", "config", "--local", key, value)
    listed = run(pack, "git", "config", "--local", "-z", "--list").stdout
    for entry in listed.split("\0"):
        key, _, value = entry.partition("\n")
        if COPIED_CONFIG.match(key.lower()) and not key.lower().startswith("user."):
            run(dest, "git", "config", "--local", "--add", key, value)


def rehearse(pack: Path, out: Path, playbook: Path, version: str, remote: str = "origin") -> dict:
    """A trial of `update` before a train, on a clone: the pack's checkout is only read. The clone has the checkout's remotes under the checkout's own
    names (so `update` sees another remote that is ahead, whichever one `remote` names), the remote-tracking refs the checkout recorded, its own default
    branch (so a checkout ahead of its remote is refused as `update` refuses it), and no `HEAD` of a remote inherited from the checkout's current branch.
    Cloned into `out/<folder>`, which must not exist; a trial that cannot start, or is interrupted, leaves no folder behind.
    {pack, state, text} as `update` returns it."""
    name = pack.name

    def refused(text: str) -> dict:
        return {"pack": name, "state": "refused", "text": text}

    address = remote_address(pack, remote)
    if not address:
        return refused(f"the checkout has no remote named {remote}")
    shown = hide_credentials(address)
    dest = out / name
    worktrees = out / f"{name}_worktrees"
    had_worktrees = worktrees.exists()                                  # `update` makes it in the clone's neighbourhood; an interrupted trial must not leave it
    try:
        if out.exists() and not out.is_dir():
            return refused(f"{out} is a file; --out names a folder")
        if dest.exists():
            return refused(f"{dest} exists (two packs with the folder name {name}, or a trial made before); name an --out that has no folder for it")
        out.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return refused(f"cannot use --out {out.name[:60]}: {e.strerror}")

    class Stop(Exception):
        """A step of the setup failed; the message says which and why."""

    def need(r: subprocess.CompletedProcess, what: str) -> None:
        if r.returncode != 0:
            raise Stop(f"{what}: {hide_credentials(first_line(r))}")

    def build() -> None:
        need(run(out, "git", "clone", "-q", "--no-hardlinks", str(pack), str(dest), timeout=FETCH_S), "cannot clone the checkout")
        copy_config(pack, dest)
        branch = default_branch(pack, remote)
        run(dest, "git", "checkout", "-q", "--detach")
        for b in run(dest, "git", "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout.split():
            run(dest, "git", "branch", "-q", "-D", b)
        # the checkout's remotes under its own names; the clone's `origin` (the checkout itself) and the branches it made of the checkout's are dropped
        run(dest, "git", "remote", "remove", "origin")
        for other in run(pack, "git", "remote").stdout.split():
            where = remote_address(pack, other)
            if where:
                need(run(dest, "git", "remote", "add", other, where), f"cannot copy the remote {other}")
        # what `update` looks at, as the checkout has it now: its own default branch, and the remote-tracking refs it recorded (another remote that was
        # ahead when the checkout last looked is ahead here too); nothing else of its local branches
        if branch and run(pack, "git", "rev-parse", "--verify", "-q", f"refs/heads/{branch}").returncode == 0:
            need(run(dest, "git", "fetch", "-q", str(pack), f"+refs/heads/{branch}:refs/heads/{branch}"), f"cannot copy the checkout's {branch}")
        need(run(dest, "git", "fetch", "-q", str(pack), "+refs/remotes/*:refs/remotes/*"), "cannot copy the checkout's remote-tracking refs")
        for other in run(dest, "git", "remote").stdout.split():
            run(dest, "git", "remote", "set-head", other, "-d")
        env = git_env(dest)
        for attempt in range(3):                                       # a remote that drops a connection is tried again
            fetched = run(dest, "git", "fetch", "-q", remote, env=env, timeout=FETCH_S)
            if fetched.returncode == 0:
                return
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        raise Stop(f"cannot fetch {shown}: {hide_credentials(first_line(fetched))}")

    try:
        build()
        return update(dest.resolve(), playbook, version, True, remote)
    except Stop as e:
        shutil.rmtree(dest, ignore_errors=True)
        return refused(str(e))
    except BaseException:                                                # Ctrl-C in the middle of a clone or of the suite must not poison the next trial
        shutil.rmtree(dest, ignore_errors=True)
        if not had_worktrees:
            shutil.rmtree(worktrees, ignore_errors=True)
        raise


def manifest_edits(dest: Path) -> list[str] | None:
    """Files that differ from the copy's own MANIFEST.sha256; None when it has none."""
    m = dest / "MANIFEST.sha256"
    if not m.is_file():
        return None
    want = {}
    for line in m.read_text("utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, _, rel = line.partition("  ")
            want[rel.strip()] = digest.strip()
    have = {rel: hashlib.sha256((dest / rel).read_bytes()).hexdigest()
            for rel in files(dest)}
    return sorted(r for r in set(want) | set(have) if want.get(r) != have.get(r))


def selected(part: dict, want: set[str]) -> set[str]:
    """The playbook files this copy was asked to hold. A skill pack that takes some of the kit's packs (`[kit] packs`)
    never holds the others; those files are not `missing`, they were not asked for (kit/tools/packs.py decides, as vendor.py does)."""
    path = part["src"] / "tools" / "packs.py"
    if part["label"] != "kit" or not path.is_file():
        return want
    try:
        spec = importlib.util.spec_from_file_location("playbook_kit_packs", path)
        packs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(packs)
        table = packs.table(part["src"])
        taken = packs.chosen(part["skill_pack"], part["src"])
    except Exception:                 # a table or a toml this tool cannot read: do not guess, list everything
        return want
    known = set(table)
    return {rel for rel in want if (m := packs.module_of(rel, known)) is None or table.get(m) in taken}


def compare(part: dict, history: History) -> dict | None:
    src, dest = part["src"], part["dest"]
    if not dest.is_dir():
        return None
    want = set(files(src, part["skip"]))
    asked = selected(part, want)
    have = set(files(dest, part["skip"]))
    v, cur = dest / "VERSION", part["root"] / part["version_file"]
    version = v.read_text("utf-8").strip() if v.is_file() else None
    current = cur.read_text("utf-8").strip() if cur.is_file() else None
    rows = []
    for rel in sorted(want | have):
        if rel == "VERSION" and rel not in want:
            continue                  # vendor.py's stamp, written when the playbook's folder has no VERSION (the console)
        path = f"{part['src_rel']}/{rel}"
        if rel not in have:
            if rel in asked or rel not in want:
                rows.append({"file": rel, "state": "missing"})
            continue
        data = (dest / rel).read_bytes()
        if rel in want and (src / rel).read_bytes() == data:
            continue
        commit = history.blobs(path).get(blob_sha(data))
        row = {"file": rel}
        if commit:
            row.update(state="older" if rel in want else "extra",
                       note=f"as the playbook had it from {part['label']} {history.version(commit, part['version_file'])}"
                            f" ({commit[:10]})" + ("" if rel in want else ", removed since"))
            if rel in want and version == current:
                row["note"] = f"as the playbook released it in {part['label']} {version}; its main changed it since with no version bump (unreleased)"
        else:
            row["state"] = "local" if rel in want else "extra"
            if rel not in want:
                row.update(own=True, note="not in the playbook's history: a file of the skill pack's own")
        rows.append(row)
    local = [r["file"] for r in rows if r.pop("own", False) or r["state"] == "local"]
    if not rows and version == current:
        verdict = "in sync"
    elif local:
        verdict = f"local changes in {len(local)} file(s): upstream or drop each, then re-vendor"
    elif version == current:
        verdict = f"same version, but the playbook's main has {len(rows)} file(s) changed since, unreleased: the next train carries them, nothing local is lost"
    else:
        verdict = "behind: re-vendor, nothing local is lost"
    return {"part": part["label"], "dir": str(dest), "version": version, "playbook_version": current,
            "edited": manifest_edits(dest), "files": rows, "verdict": verdict}


def status(skill_pack: Path, playbook: Path, history: History) -> dict:
    h = read_toml(skill_pack / "skill-pack.toml").get("skill_pack", {})
    copies = [c for p in parts(skill_pack, playbook) if (c := compare(p, history))]
    return {"skill_pack": str(skill_pack), "name": h.get("name"), "copies": copies,
            "history": "ok" if history.ok and not history.shallow
            else "shallow: older and local cannot be told apart for old versions" if history.ok
            else "none: older and local cannot be told apart"}


def render(doc: dict) -> str:
    out = [f"{doc['name'] or '?'}  {doc['skill_pack']}"]
    if doc["history"] != "ok":
        out.append(f"  history: {doc['history']}")
    if not doc["copies"]:
        out.append("  no vendored kit, console or zylos/ found")
    for c in doc["copies"]:
        out.append(f"  {c['part']:<8} {c['version'] or 'no VERSION'} (playbook {c['playbook_version']}): {c['verdict']}")
        if c["edited"]:
            out.append(f"           edited after vendoring: {', '.join(c['edited'])}")
        for r in c["files"]:
            out.append(f"           {r['state']:<8} {r['file']}" + (f"  [{r['note']}]" if r.get("note") else ""))
    return "\n".join(out)


def diff(skill_pack: Path, playbook: Path, only: list[str]) -> str:
    out = []
    for p in parts(skill_pack, playbook):
        if not p["dest"].is_dir():
            continue
        for rel in sorted(set(files(p["src"], p["skip"])) | set(files(p["dest"], p["skip"]))):
            name = f"{p['label']}/{rel}"
            if only and name not in only:
                continue
            a = (p["dest"] / rel).read_bytes() if (p["dest"] / rel).is_file() else b""
            b = (p["src"] / rel).read_bytes() if (p["src"] / rel).is_file() else b""
            if a == b:
                continue
            out.extend(difflib.unified_diff(
                a.decode("utf-8", "replace").splitlines(keepends=True),
                b.decode("utf-8", "replace").splitlines(keepends=True),
                fromfile=f"skill_pack/{name}", tofile=f"playbook/{p['src_rel']}/{rel}"))
    return "".join(out)


# ---------------------------------------------------------------- update

CHANGELOG_LINE = "- Re-vendored the playbook kit {old} -> {new} (`tools/fleet.py update`); suite {suite}.\n"
UNRELEASED = re.compile(r"^## \[Unreleased\]", re.I | re.M)


def run(cwd: Path, *cmd: str, env: dict | None = None, timeout: float | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace",
                              env=clean_env(env), timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", f"timed out after {int(timeout or 0)} s")


def first_line(r: subprocess.CompletedProcess) -> str:
    text = (r.stderr.strip() or r.stdout.strip()).splitlines()
    return "; ".join(ln.strip() for ln in text[:3]) or f"exit {r.returncode}"


def default_branch(pack: Path, remote: str = "origin") -> str | None:
    """The branch `git remote show REMOTE` calls HEAD; when that cannot be asked (the server does not answer: git.coco.xyz often
    does not), the one the checkout recorded at its last fetch (refs/remotes/REMOTE/HEAD); None when neither says."""
    r = run(pack, "git", "remote", "show", remote, env=git_env(pack), timeout=REMOTE_SHOW_S)
    m = re.search(r"^\s*HEAD branch:\s*(\S+)", r.stdout, re.M) if r.returncode == 0 else None
    if m and m.group(1) != "(unknown)":
        return m.group(1)
    kept = run(pack, "git", "symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD")
    name = kept.stdout.strip().removeprefix(f"{remote}/") if kept.returncode == 0 else ""
    return name or None


def suite_command(pack: Path) -> list[str]:
    cmd = read_toml(pack / "skill-pack.toml").get("skill_pack", {}).get("test_command")
    return shlex.split(cmd) if isinstance(cmd, str) and cmd.strip() else [sys.executable, "tests/run.py"]


def failing_files(out: str) -> list[str]:
    """The test files a runner's `FAIL ... test_x.py` lines name."""
    seen = []
    for ln in out.splitlines():
        if ln.startswith("FAIL"):
            seen += [f for f in re.findall(r"[\w./-]*test_\w+\.py", ln) if f not in seen]
    return seen


def add_changelog(path: Path, line: str) -> bool:
    """Put `line` first under `## [Unreleased]` (under its first `###` when it has one); False when there is none."""
    if not path.is_file():
        return False
    lines = path.read_text("utf-8").splitlines(keepends=True)
    at = next((i for i, ln in enumerate(lines) if UNRELEASED.match(ln)), None)
    if at is None:
        return False
    i = at + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    nxt = lines[i] if i < len(lines) else ""
    if nxt.startswith("### "):
        at, text = i + 1, line
    else:
        at, text = i, ("\n" if i == at + 1 else "") + line + ("" if nxt.startswith("- ") else "\n")
    lines.insert(at, text)
    path.write_text("".join(lines), "utf-8")
    return True


def unreleased(playbook: Path) -> list[str] | None:
    """The kit files (tests aside) that differ from the commit that last set kit/VERSION, uncommitted edits included; None when git cannot say."""
    top = git(playbook, "rev-parse", "--show-toplevel")
    if top is None or Path(top.strip()).resolve() != playbook.resolve():
        return None                          # not a checkout of its own: nothing to compare with
    commit = (git(playbook, "log", "-1", "--format=%H", "--", "kit/VERSION") or "").strip()
    if not commit:
        return None
    changed = git(playbook, "diff", "--name-only", commit, "--", "kit")
    untracked = git(playbook, "ls-files", "--others", "--exclude-standard", "--", "kit")
    if changed is None or untracked is None:
        return None
    return sorted(f for f in {*changed.splitlines(), *untracked.splitlines()} if f and not f.startswith("kit/tests/") and "__pycache__" not in f)


def other_remote_ahead(pack: Path, base: str, branch: str) -> str | None:
    """A sentence naming a remote of the pack whose `branch` has commits that `base` (remote/branch) lacks; None when none has."""
    for other in run(pack, "git", "remote").stdout.split():
        ahead = run(pack, "git", "rev-list", "--count", f"refs/remotes/{base}..refs/remotes/{other}/{branch}")
        if ahead.returncode == 0 and ahead.stdout.strip() not in ("", "0"):
            return f"the remote {other} has {ahead.stdout.strip()} commit(s) on {branch} that {base} does not"
    return None


def export(pack: Path, out: Path, remote: str = "origin") -> dict:
    """The pack's default branch on `remote`, as plain files in `out/<folder>`: what `status` and tools/consumers.py should read, since a
    checkout is often behind its remote (2026-10-30: meta-ads was 110 commits behind and showed kit 0.41.0 where its main holds 0.47.0).
    The checkout is not touched. {pack, state: exported | refused, text, path}."""
    name = read_toml(pack / "skill-pack.toml").get("skill_pack", {}).get("name") or pack.name
    done = lambda state, text, **more: {"pack": name, "path": str(pack), "state": state, "text": text, **more}
    if run(pack, "git", "rev-parse", "--show-toplevel").returncode != 0:
        return done("refused", "not a git checkout")
    branch = default_branch(pack, remote)
    if not branch:
        return done("refused", f"`git remote show {remote}` names no default branch")
    fetched = run(pack, "git", "fetch", "-q", remote, branch, env=git_env(pack), timeout=FETCH_S)
    base = f"{remote}/{branch}"
    note = f"; fetch failed, this is what was last fetched: {hide_credentials(first_line(fetched))}" if fetched.returncode != 0 else ""
    dest = out / pack.name
    if dest.exists():
        return done("refused", f"{dest} exists; remove it or choose another --out")
    tar = subprocess.run(["git", "-C", str(pack), "archive", "--format=tar", f"refs/remotes/{base}"], capture_output=True, env=clean_env())
    if tar.returncode != 0:
        return done("refused", f"cannot archive {base}: {tar.stderr.decode(errors='replace').strip()[:120]}")
    try:
        dest.mkdir(parents=True)
    except OSError as e:
        return done("refused", f"cannot use --out {out.name[:60]}: {e.strerror}")
    with tarfile.open(fileobj=io.BytesIO(tar.stdout), mode="r:") as tf:
        tf.extractall(dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    sha = run(pack, "git", "rev-parse", "--short", f"refs/remotes/{base}").stdout.strip()
    moved = other_remote_ahead(pack, base, branch)
    behind = run(pack, "git", "rev-list", "--count", f"HEAD..refs/remotes/{base}").stdout.strip()
    text = f"{base} at {sha} -> {dest}" + (f" (the checkout is {behind} commit(s) behind it)" if behind not in ("", "0") else "")
    return done("exported", text + note + (f"; WARNING: {moved}, so this is not the pack's real main: use --remote" if moved else ""), dest=str(dest))


def update(pack: Path, playbook: Path, version: str, tests: bool = True, remote: str = "origin") -> dict:
    """Bring one skill pack to the playbook's kit. {pack, state, text, ...}; see the module docstring."""
    name = read_toml(pack / "skill-pack.toml").get("skill_pack", {}).get("name") or pack.name
    out = {"pack": name, "path": str(pack)}

    def done(state: str, text: str, **more) -> dict:
        return {**out, "state": state, "text": text, **more}

    top = run(pack, "git", "rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != pack:
        return done("refused", "not the top of a git checkout")
    branch = default_branch(pack, remote)
    if not branch:
        return done("refused", f"`git remote show {remote}` names no default branch")
    work = pack.parent / f"{pack.name}_worktrees" / f"kit-{version}"
    new = f"claude/kit-{version}"
    if work.exists() or run(pack, "git", "rev-parse", "--verify", "-q", f"refs/heads/{new}").returncode == 0:
        return done("exists", f"worktree exists: {work} (branch {new}); remove it to start again")
    fetched = run(pack, "git", "fetch", "-q", remote, branch, env=git_env(pack), timeout=FETCH_S)
    if fetched.returncode != 0:
        return done("refused", f"cannot fetch {remote} {branch}: {hide_credentials(first_line(fetched))}")
    base = f"{remote}/{branch}"
    if run(pack, "git", "rev-parse", "--verify", "-q", f"refs/heads/{branch}").returncode == 0 \
            and run(pack, "git", "merge-base", "--is-ancestor", f"refs/heads/{branch}", f"refs/remotes/{base}").returncode != 0:
        return done("refused", f"the checkout's own {branch} has commits that {base} does not: {remote} looks stale or unpushed; "
                    f"push them, or name the remote the real {branch} is on with --remote NAME")
    moved = other_remote_ahead(pack, base, branch)
    if moved:
        return done("refused", f"{moved}: the pack's home may have moved (a migration); name the remote the real {branch} is on with --remote NAME, or reconcile them")
    cut = (run(pack, "git", "rev-parse", "--short", f"refs/remotes/{base}").stdout.strip()) or "?"
    added = run(pack, "git", "worktree", "add", "-q", "--no-track", "-b", new, str(work), f"refs/remotes/{base}")
    if added.returncode != 0:
        return done("refused", f"cannot add the worktree: {first_line(added)}")

    def discard() -> None:
        run(pack, "git", "worktree", "remove", "--force", str(work))
        run(pack, "git", "branch", "-D", new)

    scripts = str(read_toml(work / "skill-pack.toml").get("skill_pack", {}).get("scripts_dir") or "scripts")
    old_file = work / scripts / "kit" / "VERSION"
    old = old_file.read_text("utf-8").strip() if old_file.is_file() else "none"
    vendored = run(work, sys.executable, str(playbook / "kit" / "tools" / "vendor.py"), "--skill-pack", str(work))
    if vendored.returncode != 0:
        discard()
        return done("refused", f"refused by the vendor tool: {first_line(vendored)}")
    run(work, "git", "add", "-A")
    if not run(work, "git", "status", "--porcelain").stdout.strip():
        discard()
        return done("current", f"already holds kit {version}")
    suite, failing = "not run", []
    if tests:
        cmd = suite_command(work)
        if len(cmd) > 1 and cmd[-1] == "tests/run.py" and not (work / "tests" / "run.py").is_file():
            suite = "not run (no tests/run.py)"
        else:
            try:
                r = run(work, *cmd, env={"PYTHONDONTWRITEBYTECODE": "1"})
            except OSError as e:
                r = subprocess.CompletedProcess(cmd, 127, "", str(e))
            failing = failing_files(r.stdout + r.stderr)
            suite = "green" if r.returncode == 0 else \
                "red" + (f" ({', '.join(failing)})" if failing else f" ({first_line(r)})")
    if add_changelog(work / "CHANGELOG.md", CHANGELOG_LINE.format(old=old, new=version, suite=suite.split(" (")[0])):
        run(work, "git", "add", "CHANGELOG.md")
    msg = (f"Re-vendor the playbook kit {old} -> {version}\n\n"
           f"python3 kit/tools/vendor.py --skill-pack, by tools/fleet.py update.\nSuite: {suite}.\n")
    c = run(work, "git", "commit", "-q", "-m", msg)
    if c.returncode != 0:
        return done("refused", f"vendored in {work} but the commit failed: {first_line(c)}", worktree=str(work))
    state = "red" if suite.startswith("red") else "green"
    return done(state, f"{state}  kit {old} -> {version}, suite {suite}; branch {new} in {work}; cut from {base} at {cut}",
                worktree=str(work), branch=new, failing=failing)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--playbook", default=str(PLAYBOOK), help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", help="each copy's version, verdict and differing files")
    s.add_argument("skill_pack", nargs="+")
    s.add_argument("--json", action="store_true")
    d = sub.add_parser("diff", help="unified diffs, skill pack copy against the playbook")
    d.add_argument("skill_pack")
    d.add_argument("file", nargs="*", help="e.g. kit/facts.py; default every differing file")
    e = sub.add_parser("export", help="each skill pack's default branch on its remote as plain files, for status and tools/consumers.py (a checkout is often behind)")
    e.add_argument("skill_pack", nargs="+")
    e.add_argument("--out", required=True, help="a folder; each pack goes to <out>/<its folder name>, which must not exist")
    e.add_argument("--remote", default="origin", help="the remote the pack's real default branch is on (default origin)")
    u = sub.add_parser("update", help="vendor this playbook's kit into a worktree of each skill pack, test, commit")
    u.add_argument("skill_pack", nargs="+")
    u.add_argument("--version", help="the kit version being taken; must equal this playbook's kit/VERSION")
    u.add_argument("--no-tests", action="store_true", help="vendor and commit without running the suite")
    u.add_argument("--remote", default="origin", help="the remote the pack's real default branch is on (default origin)")
    u.add_argument("--allow-unreleased", action="store_true", help="take a kit that differs from the commit that set kit/VERSION (its bytes are not the released ones)")
    r = sub.add_parser("rehearse", help="a trial of update on a clone of each skill pack, before a train: the checkouts are only read")
    r.add_argument("skill_pack", nargs="+")
    r.add_argument("--out", required=True, help="a folder; each pack is cloned to <out>/<its folder name>, which must not exist")
    r.add_argument("--remote", default="origin", help="the remote the pack's real default branch is on (default origin)")
    args = ap.parse_args(argv)
    playbook = Path(args.playbook).resolve()
    skill_packs = [Path(h).expanduser().resolve() for h in
                 (args.skill_pack if args.cmd in ("status", "update", "export", "rehearse") else [args.skill_pack])]
    for h in skill_packs:
        if not h.is_dir():
            print(f"error: {h} is not a directory", file=sys.stderr)
            return 2
    if args.cmd == "update":
        current = (playbook / "kit" / "VERSION").read_text("utf-8").strip()
        if args.version and args.version != current:
            print(f"error: this playbook is at kit {current}, not {args.version}; "
                  f"check out the version to take first", file=sys.stderr)
            return 2
        loose = None if args.allow_unreleased else unreleased(playbook)
        if loose:
            print(f"error: this playbook's kit has {len(loose)} file(s) that are not in kit {current} ({', '.join(loose[:5])}{', ...' if len(loose) > 5 else ''}); "
                  f"update from the commit that set kit/VERSION, or pass --allow-unreleased", file=sys.stderr)
            return 2
        results = [update(h, playbook, current, not args.no_tests, args.remote) for h in skill_packs]
        for r in results:
            print(f"{r['pack']}: {r['text']}")
        return 0 if all(r["state"] in ("green", "current") for r in results) else 1
    if args.cmd == "rehearse":
        out = Path(args.out).expanduser().resolve()
        for h in skill_packs:
            if inside(out, h):
                print(f"error: --out {out} is inside the skill pack {h}: the checkouts are only read; name a folder outside them", file=sys.stderr)
                return 2
        current = (playbook / "kit" / "VERSION").read_text("utf-8").strip()
        results = [rehearse(h, out, playbook, current, args.remote) for h in skill_packs]
        for r in results:
            print(f"{r['pack']}: {r['text']}")
        return 0 if all(r["state"] in ("green", "current") for r in results) else 1
    if args.cmd == "export":
        results = [export(h, Path(args.out).expanduser().resolve(), args.remote) for h in skill_packs]
        for r in results:
            print(f"{r['pack']}: {r['text']}")
        return 0 if all(r["state"] == "exported" for r in results) else 1
    if args.cmd == "diff":
        sys.stdout.write(diff(skill_packs[0], playbook, args.file))
        return 0
    history = History(playbook)
    docs = [status(h, playbook, history) for h in skill_packs]
    if args.json:
        print(json.dumps({"playbook": str(playbook), "skill_packs": docs}, indent=2))
    else:
        print("\n\n".join(render(doc) for doc in docs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
