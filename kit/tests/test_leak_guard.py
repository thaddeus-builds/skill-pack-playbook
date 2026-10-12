#!/usr/bin/env python3
"""kit/tools/leak_guard.py and pre-push.sample, on throwaway repositories
and a SYNTHETIC term list:

  * a term in an added line, in a path, or only in a commit message is a
    hit; case and whitespace do not hide it; a removed line and a clean
    commit pass; the output names the term's line and list, never the
    term;
  * the pre-push stdin: only what is pushed, a deletion adds nothing, a
    new branch is what no remote has; --tree reads the working tree;
  * the lists: `[guards.leak] terms` (a glob, `~`) and
    `<PREFIX>_CLIENT_TERMS` are both read, `--terms` replaces them;
    fail closed: none configured, a named list missing, a glob matching
    nothing, an empty list, an empty or bad pattern all refuse (exit 2);
  * the hook, installed as the sample says: a push holding a term is
    refused, a clean one goes through, a push with no list is refused.
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402
from kit.tools import leak_guard  # noqa: E402

TOOLS = _shop.KIT / "tools"
# Widgetco on line 2, the regex on line 3. Synthetic: no client's term.
TERMS = "# synthetic terms\nWidgetco\nre:\\bqq-\\d{3}\\b\n"
SECRET_WORDS = ("widgetco", "widg etco", "qq-")
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
       "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"]


def git(d, *args, env=None) -> str:
    return subprocess.run([*GIT, *args], cwd=d, capture_output=True,
                          text=True, check=True, env=env).stdout.strip()


def commit(d: Path, files: dict, message: str) -> str:
    for name, text in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            p.unlink()
        else:
            p.write_text(text, encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", message)
    return git(d, "rev-parse", "HEAD")


def repo(toml: str = "") -> tuple[Path, Path, str]:
    """(a repo with one clean commit, its term list outside it, the sha)."""
    d = Path(tmp_dir("leak-"))
    r = d / "r"
    r.mkdir()
    git(r, "init", "-q")
    terms = d / "lists" / "client_terms.txt"
    terms.parent.mkdir()
    terms.write_text(TERMS, encoding="utf-8")
    files = {"a.md": "nothing here\n"}
    if toml:
        files["harness.toml"] = toml
    return r, terms, commit(r, files, "start")


def run(r: Path, *argv: str, stdin: str = "", environ=None
        ) -> tuple[int, list[str], str]:
    """(exit, stdout lines, stderr) of the guard run in repo r."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = leak_guard.main(list(argv), stdin=stdin, cwd=r,
                               environ=environ or {})
    return code, out.getvalue().splitlines(), err.getvalue()


def leaks(*texts: str) -> bool:
    """True when any output names a term itself (a path holding one aside:
    that is where the hit is)."""
    body = "\n".join(texts).lower().replace("docs/widgetco.txt", "")
    return any(w in body for w in SECRET_WORDS)


def hits(lines: list[str]) -> list[str]:
    return sorted(x.split(" ", 1)[1] for x in lines)


def main() -> int:
    print("[1] a range: added lines, paths and messages")
    r, terms, base = repo()
    commit(r, {"a.md": "nothing here\nmade by WIDGET co\nticket QQ-123 open\n",
               "docs/widgetco.txt": "x\n"}, "fix\n\nfor widgetco")
    code, lines, err = run(r, "--terms", str(terms), "--range",
                           f"{base}..HEAD")
    check("a term in an added line, a path and the message: refused (exit 1)",
          code == 1 and hits(lines) == sorted([
              "(commit message):3: term on line 2 of list 1",
              "a.md:2: term on line 2 of list 1",
              "a.md:3: term on line 3 of list 1",
              "docs/widgetco.txt (its path): term on line 2 of list 1"]),
          lines)
    check("the output names the term's line and list, never the term",
          not leaks(*lines, err), (lines, err))

    r, terms, base = repo()
    commit(r, {"b.md": "a clean line\n"}, "ship it for Widgetco")
    code, lines, err = run(r, "--terms", str(terms), "--range",
                           f"{base}..HEAD")
    check("a term only in the commit message: refused",
          code == 1 and hits(lines)
          == ["(commit message):1: term on line 2 of list 1"]
          and not leaks(*lines, err), (lines, err))

    r, terms, base = repo()
    commit(r, {"b.md": "Widgetco\n"}, "add")
    mid = git(r, "rev-parse", "HEAD")
    commit(r, {"b.md": "gone\n"}, "remove it")
    code, lines, err = run(r, "--terms", str(terms), "--range", f"{mid}..HEAD")
    check("a removed line is not a hit; a clean commit passes (exit 0)",
          (code, lines) == (0, []) and "0 hit(s)" in err, (code, lines, err))

    print("\n[2] the pre-push stdin and --tree")
    r, terms, base = repo()
    head = commit(r, {"c.md": "qq-777\n"}, "c")
    zero = "0" * 40
    code, lines, _ = run(r, "--terms", str(terms), "origin", "url",
                         stdin=f"refs/heads/x {head} refs/heads/x {base}\n")
    check("only what is pushed is read",
          code == 1 and hits(lines) == ["c.md:1: term on line 3 of list 1"],
          lines)
    check("nothing new: passes",
          run(r, "--terms", str(terms),
              stdin=f"refs/heads/x {head} refs/heads/x {head}\n")[:2]
          == (0, []))
    check("a deletion adds nothing",
          run(r, "--terms", str(terms),
              stdin=f"(delete) {zero} refs/heads/x {head}\n")[:2] == (0, []))
    check("a new branch: every commit no remote has",
          run(r, "--terms", str(terms),
              stdin=f"refs/heads/y {head} refs/heads/y {zero}\n")[0] == 1)
    r, terms, _ = repo()
    check("--tree: a clean tree passes",
          run(r, "--terms", str(terms), "--tree")[:2] == (0, []))
    commit(r, {"d.md": "one\nWidg etco\n"}, "d")
    check("--tree: a term with a space inside is still found",
          run(r, "--terms", str(terms), "--tree")[:2]
          == (1, ["d.md:2: term on line 2 of list 1"]))

    print("\n[3] where the lists are, and fail closed")
    toml = ('[harness]\nname = "acme"\ncli = "acme"\nenv_prefix = "ACME"\n'
            '[guards.leak]\nterms = ["../lists/*.txt", "~/no-such-dir/*.txt"]\n')
    r, terms, base = repo(toml)
    head = commit(r, {"e.md": "Widgetco\n"}, "e")
    rng = f"{base}..HEAD"
    code, lines, _ = run(r, "--range", rng)
    check("[guards.leak] terms: a glob from the top level; one matching "
          "nothing adds nothing", code == 1 and hits(lines)
          == ["e.md:1: term on line 2 of list 1"], lines)
    extra = terms.parent / "more.txt"
    extra.write_text("# more\n\nre:e\\.md\n", encoding="utf-8")
    code, lines, _ = run(r, "--range", rng)
    check("… every match of the glob is a list, in sorted order",
          code == 1 and hits(lines) == ["e.md (its path): term on line 3 of "
                                        "list 2", "e.md:1: term on line 2 of "
                                        "list 1"], lines)
    extra.unlink()
    other = Path(tmp_dir("leak-env-")) / "terms.txt"
    other.write_text("re:^Widgetco$\n", encoding="utf-8")
    code, lines, _ = run(r, "--range", rng,
                         environ={"ACME_CLIENT_TERMS": f"{other}{os.pathsep}"})
    check("<PREFIX>_CLIENT_TERMS is read after harness.toml's lists",
          code == 1 and hits(lines) == ["e.md:1: term on line 1 of list 2",
                                        "e.md:1: term on line 2 of list 1"],
          lines)
    code, lines, _ = run(r, "--range", rng, "--terms", str(other))
    check("--terms replaces the configured lists",
          code == 1 and hits(lines) == ["e.md:1: term on line 1 of list 1"],
          lines)
    home = Path(tmp_dir("leak-home-"))
    shutil.copy(terms, home / "t.txt")
    saved = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        code, lines, _ = run(r, "--range", rng, "--terms", "~/t.txt")
    finally:
        os.environ["HOME"] = saved
    check("~ expands", code == 1 and len(lines) == 1, lines)

    def refused(why: str, *argv: str, repo_dir=r, environ=None) -> None:
        code, lines, err = run(repo_dir, "--range", rng, *argv,
                               environ=environ)
        check(f"refused (exit 2): {why}",
              code == 2 and lines == [] and "refusing" in err
              and not leaks(err), (code, lines, err))

    bare, _, _ = repo()
    refused("no harness.toml and no --terms", repo_dir=bare)
    refused("a named list that is missing", "--terms",
            str(terms.parent / "gone.txt"))
    refused("<PREFIX>_CLIENT_TERMS naming a missing list",
            environ={"ACME_CLIENT_TERMS": str(terms.parent / "gone.txt")})
    refused("a glob that matches nothing anywhere", "--terms",
            str(terms.parent / "*.none"))
    empty = terms.parent / "empty.txt"
    empty.write_text("# only a comment\n\n", encoding="utf-8")
    refused("a list that holds no term", "--terms", str(empty))
    empty.write_text("re:\n", encoding="utf-8")
    refused("an empty pattern (it would match everything)", "--terms",
            str(empty))
    empty.write_text("re:(widgetco\n", encoding="utf-8")
    refused("a bad regular expression, its text not echoed", "--terms",
            str(empty))
    bad, _, _ = repo('[harness]\nenv_prefix = "ACME"\n[guards.leak]\n'
                     'terms = "one.txt"\n')
    refused("[guards.leak] terms that is not a list", repo_dir=bad)
    code, _, err = run(r, "--terms", str(terms), "--range", "nope..HEAD")
    check("a git error refuses (exit 2)", code == 2 and "refusing" in err,
          err)

    print("\n[4] the hook, installed as the sample says")
    d = Path(tmp_dir("leak-push-"))
    remote = d / "remote.git"
    subprocess.run([*GIT, "init", "-q", "--bare", str(remote)], check=True)
    r = d / "acme"
    r.mkdir()
    git(r, "init", "-q")
    (r / "scripts" / "kit").mkdir(parents=True)
    shutil.copytree(TOOLS, r / "scripts" / "kit" / "tools",
                    ignore=shutil.ignore_patterns("__pycache__"))
    lists = d / "workspaces" / "client-a" / "data"
    lists.mkdir(parents=True)
    (lists / "client_terms.txt").write_text(TERMS, encoding="utf-8")
    commit(r, {"harness.toml": (
        '[harness]\nname = "acme"\ncli = "acme"\nenv_prefix = "ACME"\n'
        f'[guards.leak]\nterms = ["{d}/workspaces/*/data/client_terms.txt"]\n'),
        "a.md": "clean\n"}, "start")
    git(r, "remote", "add", "origin", str(remote))
    hooks = Path(r / git(r, "rev-parse", "--git-common-dir")) / "hooks"
    hooks.mkdir(exist_ok=True)
    subprocess.run(["install", "-m", "755",
                    str(r / "scripts/kit/tools/pre-push.sample"),
                    str(hooks / "pre-push")], check=True)
    env = {**os.environ,
           "PATH": f"{Path(sys.executable).parent}{os.pathsep}"
                   f"{os.environ.get('PATH', '')}"}
    hooked = ["git", "-c", f"core.hooksPath={hooks}"]

    def push(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([*hooked, "push", "-q", "origin", *args], cwd=r,
                              capture_output=True, text=True, env=env)
    p = push("HEAD:refs/heads/main")
    check("a clean push goes through", p.returncode == 0, p.stderr)
    commit(r, {"b.md": "nothing\n"}, "for WidgetCo")
    p = push("HEAD:refs/heads/main")
    check("a push whose message holds a term is refused, the term not shown",
          p.returncode != 0 and "term on line 2 of list 1" in p.stdout + p.stderr
          and not leaks(p.stdout, p.stderr), p.stdout + p.stderr)
    shutil.rmtree(d / "workspaces")
    git(r, "commit", "-q", "--amend", "-m", "clean now")
    p = push("HEAD:refs/heads/main")
    check("with no term list the push is refused",
          p.returncode != 0 and "refusing" in p.stderr, p.stderr)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
