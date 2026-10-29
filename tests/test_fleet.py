"""tools/fleet.py: where a skill pack's vendored copies stand against the playbook.

A throwaway git repository stands in for the playbook (CI checks out one
commit, so the real history is not there): kit 0.1.0, then 0.2.0. A skill pack
vendored at 0.1.0 is behind; a file in no version of the playbook is local;
the copy's own manifest names an edit made after vendoring. The console copy
carries the VERSION stamp vendor.py writes (the playbook's console/ has none):
it is read for the version and is never a local file.

`update` is tried on a skill pack cloned from a bare repository whose default
branch is `trunk`, against a throwaway playbook that carries the real kit/tools:
green, red, refused by the vendor tool, worktree exists, already current, and
the pack's own checkout untouched.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FLEET = ROOT / "tools" / "fleet.py"


def sh(cwd: Path, *args: str) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def vendor(src: Path, dest: Path, stamp: str | None = None) -> None:
    """A plain copy with its MANIFEST.sha256, as kit/tools/vendor.py writes it; `stamp` is the
    VERSION it adds to a copy whose source has none (the console)."""
    lines = []
    for p in sorted(src.rglob("*")):
        if p.is_file() and "tests" not in p.relative_to(src).parts:
            rel = p.relative_to(src).as_posix()
            write(dest, {rel: p.read_text()})
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}")
    if stamp:
        write(dest, {"VERSION": stamp + "\n"})
        lines.append(f"{hashlib.sha256((stamp + chr(10)).encode()).hexdigest()}  VERSION")
    (dest / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")


def fleet(playbook: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(FLEET), "--playbook", str(playbook), *args],
                          capture_output=True, text=True)


def setup(tmp: Path) -> tuple[Path, Path]:
    pb, h = tmp / "playbook", tmp / "acme"
    write(pb, {"kit/VERSION": "0.1.0\n", "kit/a.py": "A = 1\n", "kit/gone.py": "G = 1\n",
               "kit/tests/test_a.py": "t\n", "console/core.py": "C = 1\n"})
    sh(pb, "git", "init", "-q")
    sh(pb, "git", "add", "-A")
    sh(pb, "git", "commit", "-qm", "0.1.0")
    write(h, {"skill-pack.toml": '[skill_pack]\nname = "acme"\nscripts_dir = "scripts"\n'})
    vendor(pb / "kit", h / "scripts" / "kit")
    vendor(pb / "console", h / "console", stamp="0.1.0")
    (pb / "kit" / "gone.py").unlink()
    write(pb, {"kit/VERSION": "0.2.0\n", "kit/a.py": "A = 2\n", "kit/b.py": "B = 1\n"})
    sh(pb, "git", "add", "-A")
    sh(pb, "git", "commit", "-qm", "0.2.0")
    return pb, h


def test_a_copy_vendored_earlier_is_behind_and_loses_nothing():
    with _t.tmpdir() as tmp:
        pb, h = setup(Path(tmp))
        r = fleet(pb, "status", str(h), "--json")
        assert r.returncode == 0, r.stderr
        [doc] = json.loads(r.stdout)["skill_packs"]
        kit, console = doc["copies"]
        assert doc["name"] == "acme" and doc["history"] == "ok", doc
        assert (kit["version"], kit["playbook_version"]) == ("0.1.0", "0.2.0"), kit
        states = {f["file"]: f["state"] for f in kit["files"]}
        assert states == {"VERSION": "older", "a.py": "older", "b.py": "missing", "gone.py": "extra"}, states
        assert "as the playbook had it from kit 0.1.0" in next(f["note"] for f in kit["files"] if f["file"] == "a.py")
        assert kit["verdict"].startswith("behind") and kit["edited"] == [], kit
        # the console copy differs only by its VERSION stamp, which the playbook's console/ never has
        assert (console["part"], console["version"], console["playbook_version"]) == ("console", "0.1.0", "0.2.0"), console
        assert console["files"] == [] and console["edited"] == [], console
        assert console["verdict"].startswith("behind"), console
        assert "extra    VERSION" not in r.stdout and "local changes" not in fleet(pb, "status", str(h)).stdout


def test_a_change_no_playbook_version_had_is_local_and_named():
    with _t.tmpdir() as tmp:
        pb, h = setup(Path(tmp))
        (h / "scripts" / "kit" / "a.py").write_text("A = 'forked'\n")
        write(h, {"scripts/kit/mine.py": "M = 1\n"})
        r = fleet(pb, "status", str(h))
        assert r.returncode == 0, r.stderr
        assert "local changes in 2 file(s)" in r.stdout, r.stdout
        assert "local    a.py" in r.stdout and "extra    mine.py" in r.stdout, r.stdout
        assert "edited after vendoring: a.py, mine.py" in r.stdout, r.stdout


def test_a_file_the_playbook_changed_without_a_version_bump_is_unreleased_not_local():
    """#321: a pack on the released version, the playbook's main moved on in a file: that is not the pack's edit."""
    with _t.tmpdir() as tmp:
        pb, h = setup(Path(tmp))
        kit = h / "scripts" / "kit"
        subprocess.run(["rm", "-rf", str(kit)], check=True)
        vendor(pb / "kit", kit)
        write(pb, {"kit/a.py": "A = 3\n"})
        sh(pb, "git", "add", "-A")
        sh(pb, "git", "commit", "-qm", "a change on main, no bump")
        r = fleet(pb, "status", str(h), "--json")
        [copy] = [c for c in json.loads(r.stdout)["skill_packs"][0]["copies"] if c["part"] == "kit"]
        assert [(f["file"], f["state"]) for f in copy["files"]] == [("a.py", "older")], copy
        assert "unreleased" in copy["files"][0]["note"] and "local changes" not in copy["verdict"], copy
        assert copy["verdict"].startswith("same version") and "unreleased" in copy["verdict"], copy
        write(h, {"scripts/kit/a.py": "A = 'forked'\n"})
        r = fleet(pb, "status", str(h), "--json")
        [copy] = [c for c in json.loads(r.stdout)["skill_packs"][0]["copies"] if c["part"] == "kit"]
        assert copy["verdict"].startswith("local changes in 1"), "a real edit is still local"


def test_a_copy_equal_to_the_playbook_is_in_sync():
    with _t.tmpdir() as tmp:
        pb, h = setup(Path(tmp))
        kit = h / "scripts" / "kit"
        subprocess.run(["rm", "-rf", str(kit)], check=True)
        vendor(pb / "kit", kit)
        vendor(pb / "console", h / "console", stamp="0.2.0")
        r = fleet(pb, "status", str(h), "--json")
        for copy in json.loads(r.stdout)["skill_packs"][0]["copies"]:
            assert copy["verdict"] == "in sync" and copy["files"] == [], copy


def test_a_file_that_only_a_merge_commit_ever_had_is_older_not_local():
    """Seen 2026-10-30: nine packs on kit 0.44.0 were all called `local` in README.md, VERSION and packs.tsv, because
    the playbook had resolved a conflict in a merge commit and `git log --raw` shows no diff for a merge."""
    with _t.tmpdir() as tmp:
        pb, h = setup(Path(tmp))
        sh(pb, "git", "checkout", "-q", "-b", "side")
        write(pb, {"kit/a.py": "A = 'side'\n"})
        sh(pb, "git", "commit", "-qam", "side")
        sh(pb, "git", "checkout", "-q", "-")
        write(pb, {"kit/a.py": "A = 'main'\n"})
        sh(pb, "git", "commit", "-qam", "main")
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        merged = subprocess.run(["git", "merge", "-q", "side"], cwd=pb, capture_output=True, env=env)
        assert merged.returncode != 0, "the merge must conflict, or the test proves nothing"
        write(pb, {"kit/a.py": "A = 'resolved'\n"})
        sh(pb, "git", "add", "-A")
        sh(pb, "git", "commit", "-qm", "merge side")
        write(pb, {"kit/a.py": "A = 3\n"})
        sh(pb, "git", "commit", "-qam", "moved on")
        write(h, {"scripts/kit/a.py": "A = 'resolved'\n"})
        r = fleet(pb, "status", str(h), "--json")
        [copy] = [c for c in json.loads(r.stdout)["skill_packs"][0]["copies"] if c["part"] == "kit"]
        assert ("a.py", "older") in [(f["file"], f["state"]) for f in copy["files"]], copy
        assert "local changes" not in copy["verdict"], copy


def test_a_pack_the_skill_pack_does_not_take_is_not_missing():
    """Seen 2026-10-30: sdr and ecommerce-seo took four kit packs and were told 80 of 84 files were missing or changed."""
    real = ROOT / "kit" / "tools" / "packs.py"
    with _t.tmpdir() as tmp:
        pb, h = setup(Path(tmp))
        write(pb, {"kit/tools/packs.py": real.read_text(),
                   "kit/packs.tsv": "module\tpack\tnote\na\tbase\tx\nb\textra\ty\n"})
        sh(pb, "git", "add", "-A")
        sh(pb, "git", "commit", "-qm", "a table of packs")

        def states(toml: str) -> dict:
            write(h, {"skill-pack.toml": '[skill_pack]\nname = "acme"\nscripts_dir = "scripts"\n' + toml})
            [kit] = [c for c in json.loads(fleet(pb, "status", str(h), "--json").stdout)["skill_packs"][0]["copies"] if c["part"] == "kit"]
            return {f["file"]: f["state"] for f in kit["files"]}
        assert states("[kit]\npacks = []\n").get("b.py") is None, "b.py belongs to `extra`, which this pack does not take"
        assert states("[kit]\npacks = [\"extra\"]\n").get("b.py") == "missing"
        assert states("").get("b.py") == "missing", "no `[kit] packs` means every pack"
        assert states("[kit]\npacks = [\"nonesuch\"]\n").get("b.py") == "missing", "a toml the tool cannot read is not guessed at"


def test_diff_shows_the_skill_pack_copy_against_the_playbook():
    with _t.tmpdir() as tmp:
        pb, h = setup(Path(tmp))
        r = fleet(pb, "diff", str(h), "kit/a.py")
        assert r.returncode == 0, r.stderr
        assert "--- skill_pack/kit/a.py" in r.stdout and "+++ playbook/kit/a.py" in r.stdout, r.stdout
        assert "-A = 1" in r.stdout and "+A = 2" in r.stdout and "b.py" not in r.stdout, r.stdout
        assert "kit/b.py" in fleet(pb, "diff", str(h)).stdout


def test_without_history_it_says_so():
    with _t.tmpdir() as tmp:
        pb, h = setup(Path(tmp))
        subprocess.run(["rm", "-rf", str(pb / ".git")], check=True)
        doc = json.loads(fleet(pb, "status", str(h), "--json").stdout)["skill_packs"][0]
        assert doc["history"].startswith("none"), doc
        assert fleet(pb, "status", str(Path(tmp) / "nowhere")).returncode == 2


# ---------------------------------------------------------------- update

IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
PASS = "print('RESULT: 1 passed')\n"
FAIL = "import sys\nprint('FAIL   0.1s  test_money.py        exit 1')\nsys.exit(1)\n"
LOG = "# Changelog\n\n## [Unreleased]\n\n### Changed\n- a\n\n## [1.0.0] - 2026-01-01\n"


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                       env={**os.environ, **IDENTITY})
    return r.stdout.strip()


def train(tmp: Path, version: str) -> Path:
    """A playbook holding the real kit (without its tests) at `version`."""
    pb = tmp / "playbook"
    if not pb.exists():
        shutil.copytree(ROOT / "kit", pb / "kit", ignore=shutil.ignore_patterns("tests", "__pycache__"))
    (pb / "kit" / "VERSION").write_text(version + "\n")
    return pb


def make_pack(tmp: Path, toml: str = "", suite: str = PASS, extra: dict | None = None) -> tuple[Path, Path]:
    """A pack vendored at kit 0.1.0, cloned from a bare origin whose default branch is
    `trunk`, left on another branch; the playbook is then moved on to 0.2.0."""
    origin, pack = tmp / "origin.git", tmp / "work" / "acme"
    git(tmp, "init", "-q", "--bare", "-b", "trunk", str(origin))
    git(tmp, "clone", "-q", str(origin), str(pack))
    git(pack, "checkout", "-q", "-b", "trunk")
    write(pack, {"skill-pack.toml": '[skill_pack]\nname = "acme"\n', "CHANGELOG.md": LOG,
                 "tests/run.py": suite, **(extra or {})})
    old = train(tmp, "0.1.0")
    subprocess.run([sys.executable, str(old / "kit" / "tools" / "vendor.py"), "--skill-pack", str(pack)],
                   check=True, capture_output=True)
    with open(pack / "skill-pack.toml", "a") as f:        # after the first vendoring: it may be one the tool refuses
        f.write(toml)
    git(pack, "add", "-A")
    git(pack, "commit", "-qm", "start")
    git(pack, "push", "-q", "origin", "trunk")
    git(pack, "checkout", "-q", "-b", "feature")      # someone's branch: update must leave it alone
    return train(tmp, "0.2.0"), pack


def update(pb: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(FLEET), "--playbook", str(pb), "update", *args],
                          capture_output=True, text=True, env={**os.environ, **IDENTITY})


def drop(pack: Path) -> None:
    git(pack, "worktree", "remove", "--force", str(pack.parent / "acme_worktrees" / "kit-0.2.0"))
    git(pack, "branch", "-D", "claude/kit-0.2.0")


def test_update_commits_the_new_kit_in_a_worktree_beside_the_pack():
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))
        head = git(pack, "rev-parse", "HEAD")
        r = update(pb, str(pack))
        assert r.returncode == 0, r.stdout + r.stderr
        work = pack.parent / "acme_worktrees" / "kit-0.2.0"
        assert r.stdout.startswith("acme: green  kit 0.1.0 -> 0.2.0, suite green;"), r.stdout
        assert (work / "scripts" / "kit" / "VERSION").read_text().strip() == "0.2.0"
        assert git(work, "branch", "--show-current") == "claude/kit-0.2.0"
        assert git(work, "rev-parse", "HEAD~1") == git(pack, "rev-parse", "origin/trunk"), "cut from the default branch"
        assert git(work, "status", "--porcelain") == "", "everything is committed"
        msg = git(work, "log", "-1", "--format=%B")
        assert "0.1.0 -> 0.2.0" in msg and "Suite: green" in msg, msg
        log = (work / "CHANGELOG.md").read_text()
        assert log.index("### Changed\n- Re-vendored the playbook kit 0.1.0 -> 0.2.0") < log.index("- a\n"), log
        assert "suite green" in log and log.count("Re-vendored") == 1
        assert (git(pack, "rev-parse", "HEAD"), git(pack, "branch", "--show-current"), git(pack, "status", "--porcelain")) \
            == (head, "feature", ""), "the pack's own checkout is untouched"
        assert (pack / "scripts" / "kit" / "VERSION").read_text().strip() == "0.1.0"


def real_remote(pack: Path, tmp: Path) -> str:
    """The pack's real trunk moves on a second remote, `github`; `origin` is left as it was (archived, stale). Returns the new commit."""
    git(pack, "checkout", "-q", "trunk")
    (pack / "NOTES.md").write_text("work done after origin was archived\n")
    git(pack, "add", "-A")
    git(pack, "commit", "-qm", "real work")
    git(tmp, "init", "-q", "--bare", "-b", "trunk", str(tmp / "github.git"))
    git(pack, "remote", "add", "github", str(tmp / "github.git"))
    git(pack, "push", "-q", "github", "trunk")
    new = git(pack, "rev-parse", "HEAD")
    git(pack, "checkout", "-q", "feature")
    return new


def test_update_says_which_remote_and_commit_it_cut_from():
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))
        r = update(pb, str(pack))
        short = git(pack, "rev-parse", "--short", "origin/trunk")
        assert r.returncode == 0 and f"cut from origin/trunk at {short}" in r.stdout, r.stdout + r.stderr


def test_update_refuses_a_stale_remote_and_takes_the_real_one_with_remote():
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))
        real = real_remote(pack, Path(tmp))
        r = update(pb, str(pack))
        assert r.returncode == 1 and "has commits that origin/trunk does not" in r.stdout and "--remote NAME" in r.stdout, r.stdout + r.stderr
        assert not (pack.parent / "acme_worktrees").exists() and git(pack, "branch", "--list", "claude/kit-0.2.0") == "", "nothing is left behind"
        other = Path(tmp) / "other"           # someone pushes to github after the pack last looked: the update has to fetch
        git(Path(tmp), "clone", "-q", str(Path(tmp) / "github.git"), str(other))
        (other / "MORE.md").write_text("pushed since\n")
        git(other, "add", "-A")
        git(other, "commit", "-qm", "pushed since")
        git(other, "push", "-q", "origin", "trunk")
        real = git(other, "rev-parse", "HEAD")
        r = update(pb, str(pack), "--remote", "github")
        work = pack.parent / "acme_worktrees" / "kit-0.2.0"
        assert r.returncode == 0 and "cut from github/trunk at " in r.stdout, r.stdout + r.stderr
        assert git(work, "rev-parse", "HEAD~1") == real, "the re-vendor sits on the real trunk"
        assert (work / "NOTES.md").is_file()


def test_update_refuses_when_another_remote_is_ahead_of_the_one_it_would_cut_from():
    """The migration case (2026-10-30): sdr's `origin` was the old server, 63 commits behind its new one, and the checkout had no local trunk to show it."""
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))
        real_remote(pack, Path(tmp))
        git(pack, "branch", "-f", "trunk", "origin/trunk")      # the checkout itself holds nothing the remotes lack
        r = update(pb, str(pack))
        assert r.returncode == 1 and "the remote github has 1 commit(s) on trunk that origin/trunk does not" in r.stdout, r.stdout + r.stderr
        assert not (pack.parent / "acme_worktrees").exists() and git(pack, "branch", "--list", "claude/kit-0.2.0") == "", "nothing is left behind"
        ok = update(pb, str(pack), "--remote", "github")
        assert ok.returncode == 0 and "cut from github/trunk" in ok.stdout, ok.stdout + ok.stderr


def test_update_with_a_remote_the_pack_does_not_have_is_refused_by_name():
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))
        r = update(pb, str(pack), "--remote", "nowhere")
        assert r.returncode == 1 and "`git remote show nowhere` names no default branch" in r.stdout, r.stdout + r.stderr


def test_update_commits_a_red_suite_and_names_the_failing_files():
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp), suite=FAIL)
        r = update(pb, str(pack))
        assert r.returncode == 1, r.stdout
        assert "acme: red  kit 0.1.0 -> 0.2.0, suite red (test_money.py);" in r.stdout, r.stdout
        work = pack.parent / "acme_worktrees" / "kit-0.2.0"
        assert "Suite: red (test_money.py)" in git(work, "log", "-1", "--format=%B")
        assert "suite red" in (work / "CHANGELOG.md").read_text()


def test_update_honours_test_command_and_no_tests():
    with _t.tmpdir() as tmp:
        py = shlex.quote(sys.executable)
        pb, pack = make_pack(Path(tmp), toml=f'test_command = "{py} tests/fail.py"\n',
                             extra={"tests/fail.py": FAIL})
        r = update(pb, str(pack), "--no-tests")
        assert r.returncode == 0 and "suite not run;" in r.stdout, r.stdout
        drop(pack)
        r = update(pb, str(pack))
        assert r.returncode == 1 and "suite red (test_money.py)" in r.stdout, r.stdout


def test_update_refuses_what_the_vendor_tool_refuses_and_leaves_nothing_behind():
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp), toml='\n[kit]\npacks = ["nonesuch"]\n')
        r = update(pb, str(pack))
        assert r.returncode == 1 and "acme: refused by the vendor tool:" in r.stdout, r.stdout
        assert not (pack.parent / "acme_worktrees" / "kit-0.2.0").exists()
        assert git(pack, "branch", "--list", "claude/kit-*") == ""


def test_update_stops_at_an_existing_worktree_and_at_a_pack_already_current():
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))
        assert update(pb, str(pack)).returncode == 0
        again = update(pb, str(pack))
        assert again.returncode == 1 and "acme: worktree exists:" in again.stdout, again.stdout
        work = pack.parent / "acme_worktrees" / "kit-0.2.0"
        git(work, "push", "-q", "origin", "HEAD:trunk")      # the train reaches the default branch
        drop(pack)
        r = update(pb, str(pack))
        assert r.returncode == 0 and "acme: already holds kit 0.2.0" in r.stdout, r.stdout
        assert not work.exists() and git(pack, "branch", "--list", "claude/kit-*") == ""


def test_update_takes_only_the_version_the_playbook_is_at():
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))
        r = update(pb, str(pack), "--version", "0.3.0")
        assert r.returncode == 2 and "this playbook is at kit 0.2.0, not 0.3.0" in r.stderr, r.stderr
        assert update(pb, str(pack), "--version", "0.2.0").returncode == 0


def commit_playbook(pb: Path) -> None:
    git(pb, "init", "-q")
    git(pb, "add", "-A")
    git(pb, "commit", "-qm", "0.2.0")


def test_update_refuses_a_kit_that_is_not_the_released_one_and_says_which_files():
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))
        commit_playbook(pb)
        assert update(pb, str(pack)).returncode == 0, "a checkout that is the release is taken"
        drop(pack)
        (pb / "kit" / "zz_unreleased.py").write_text("X = 1\n")                      # a merge after the train, not yet committed
        r = update(pb, str(pack))
        assert r.returncode == 2 and "kit/zz_unreleased.py" in r.stderr and "not in kit 0.2.0" in r.stderr, r.stderr
        assert not (pack.parent / "acme_worktrees" / "kit-0.2.0").exists(), "nothing is left behind"
        git(pb, "add", "-A")
        git(pb, "commit", "-qm", "a merge after the train")
        assert update(pb, str(pack)).returncode == 2, "committed after the train is still not the release"
        (pb / "kit" / "a_changed.py").write_text("X = 2\n")
        assert "a_changed.py" in update(pb, str(pack)).stderr
        assert update(pb, str(pack), "--allow-unreleased").returncode == 0, "the owner may take it on purpose"
        drop(pack)
        (pb / "kit" / "zz_unreleased.py").unlink()
        (pb / "kit" / "a_changed.py").unlink()
        git(pb, "add", "-A")
        git(pb, "commit", "-qm", "back")
        assert update(pb, str(pack)).returncode == 0, "the files gone again, it is the release"


def test_update_does_not_count_the_kit_tests_and_does_not_guess_without_a_checkout():
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))
        commit_playbook(pb)
        (pb / "kit" / "tests").mkdir(exist_ok=True)
        (pb / "kit" / "tests" / "test_new.py").write_text("t\n")                       # a test is not a vendored byte
        r = update(pb, str(pack))
        assert r.returncode == 0, r.stderr
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))                                                # a folder that is no git checkout
        (pb / "kit" / "zz_unreleased.py").write_text("X = 1\n")
        assert update(pb, str(pack)).returncode == 0
    with _t.tmpdir() as tmp:
        pb, pack = make_pack(Path(tmp))                                                # a folder inside someone else's checkout
        git(Path(tmp), "init", "-q")
        git(Path(tmp), "add", "playbook")
        git(Path(tmp), "commit", "-qm", "outer")
        (pb / "kit" / "zz_unreleased.py").write_text("X = 1\n")
        assert update(pb, str(pack)).returncode == 0, "the outer repository's history is not this playbook's release"


def test_the_changelog_line_goes_first_under_unreleased_in_each_shape():
    spec = importlib.util.spec_from_file_location("fleet_tool", FLEET)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    cases = {
        "## [Unreleased]\n\n### Added\n- a\n": "## [Unreleased]\n\n### Added\nL\n- a\n",
        "## [Unreleased]\n\n- a\n## [1.0.0]\n": "## [Unreleased]\n\nL\n- a\n## [1.0.0]\n",
        "## [Unreleased]\n## [1.0.0]\n": "## [Unreleased]\n\nL\n\n## [1.0.0]\n",
        "## [Unreleased]\n": "## [Unreleased]\n\nL\n\n",
    }
    with _t.tmpdir() as tmp:
        f = Path(tmp) / "CHANGELOG.md"
        for before, after in cases.items():
            f.write_text(before)
            assert tool.add_changelog(f, "L\n") and f.read_text() == after, (before, f.read_text())
        f.write_text("# Changelog\n\n## [1.0.0]\n")
        assert not tool.add_changelog(f, "L\n") and f.read_text() == "# Changelog\n\n## [1.0.0]\n"
        assert not tool.add_changelog(Path(tmp) / "none.md", "L\n")


if __name__ == "__main__":
    _t.main(globals())
