#!/usr/bin/env python3
"""kit/tools/leak_guard.py and pre-push.sample, on throwaway repositories
and a SYNTHETIC term list:

  * a term in an added line, in a path (a non-ASCII one, a binary or an
    empty file too), or only in a commit message is a hit; case,
    whitespace, full-width and zero-width spellings do not hide it; a
    removed line and a clean commit pass; no output line holds the term,
    not even as a path; an added line that reads like a diff header is
    still read;
  * the pre-push stdin: only what is pushed, a deletion adds nothing, a
    new branch is what no remote has; --tree reads the working tree;
  * the lists: `[guards.leak] terms` (a glob, `~`) and
    `<PREFIX>_CLIENT_TERMS` are both read, `--terms` replaces them;
    fail closed: none configured, a named list missing (alone or beside
    one that exists), a glob matching nothing, an empty list, a bad
    pattern or one matching the empty string all refuse (exit 2);
  * the hook, installed as the sample says: a push holding a term is
    refused, a clean one goes through, a push with no list is refused.
"""

import contextlib
import io
import os
import re
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
# Widgetco on line 2, the regex on line 3, a CJK name on line 4. Synthetic:
# no client's term.
TERMS = "# synthetic terms\nWidgetco\nre:\\bqq-\\d{3}\\b\n示例公司\n"
SECRET_WORDS = ("widgetco", "widg etco", "qq-", "示例公司", "示例 公司")
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
    """True when any output line holds a term, in any spelling the guard
    reads as the term."""
    body = leak_guard.norm("\n".join(texts)).lower()
    return any(w in body for w in SECRET_WORDS)


def hits(lines: list[str]) -> list[str]:
    """The hit lines, each commit's short sha written <sha>, sorted."""
    return sorted(re.sub(r"\b[0-9a-f]{10}\b", "<sha>", x) for x in lines)


def main() -> int:
    print("[1] a range: added lines, paths and messages")
    r, terms, base = repo()
    commit(r, {"a.md": "nothing here\nmade by WIDGET co\nticket QQ-123 open\n",
               "docs/widgetco.txt": "x\n"}, "fix\n\nfor widgetco")
    code, lines, err = run(r, "--terms", str(terms), "--range",
                           f"{base}..HEAD")
    check("a term in an added line, a path and the message: refused (exit 1)",
          code == 1 and hits(lines) == sorted([
              "<sha> (commit message):3: term on line 2 of list 1",
              "<sha> a.md:2: term on line 2 of list 1",
              "<sha> a.md:3: term on line 3 of list 1",
              "a file path in commit <sha>: term on line 2 of list 1"]),
          lines)
    check("no output line holds the term, not even the path that holds it",
          not leaks(*lines, err), (lines, err))
    r, terms, base = repo()
    commit(r, {"资料/示例公司/说明.md": "one\nWidgetco here\n",
               "x/示例公司.bin": "\0\1binary", "y/示例公司-empty.txt": ""},
           "cjk")
    code, lines, err = run(r, "--terms", str(terms), "--range",
                           f"{base}..HEAD")
    check("a CJK term in a non-ASCII path (a text, a binary and an empty "
          "file) is found, and the path is not printed",
          code == 1 and hits(lines) == sorted(
              ["a file path in commit <sha>: term on line 4 of list 1"] * 3
              + ["<sha> (a file whose path holds a term):2: term on line 2 "
                 "of list 1"]) and not leaks(*lines, err), lines)
    r, terms, base = repo()
    git(r, "checkout", "-q", "-b", "side")
    commit(r, {"a.md": "side\n"}, "side")
    git(r, "checkout", "-q", "-")
    commit(r, {"a.md": "main\n"}, "main")
    subprocess.run([*GIT, "merge", "-q", "side"], cwd=r, capture_output=True)
    commit(r, {"a.md": "resolved for qq-555\n"}, "merge side")
    code, lines, _ = run(r, "--terms", str(terms), "--range", f"{base}..HEAD")
    check("a merge's own resolution line is read (a combined diff)",
          code == 1 and hits(lines) == ["<sha> a.md:1: term on line 3 of "
                                        "list 1"], lines)
    check("a path git quotes even with core.quotePath off is read back",
          leak_guard._unquote('"b/\\347\\244\\272 \\"x\\".md"')
          == 'b/示 "x".md' and leak_guard._unquote("b/a b.md\t") == "b/a b.md")
    r, terms, base = repo()
    commit(r, {"f.md": "ok\n++ widgetco\n+++ b/qq-123\n"}, "diff-like")
    code, lines, _ = run(r, "--terms", str(terms), "--range", f"{base}..HEAD")
    check("an added line that reads like a diff header is still read",
          code == 1 and hits(lines) == ["<sha> f.md:2: term on line 2 of "
                                        "list 1", "<sha> f.md:3: term on line"
                                        " 3 of list 1"], lines)
    r, terms, base = repo()
    commit(r, {"g.md": "ＷＩＤＧＥＴＣＯ\nWidg\u200betco\nqq\u2011123 no\n"},
           "evasions")
    code, lines, _ = run(r, "--terms", str(terms), "--range", f"{base}..HEAD")
    check("full-width and zero-width spellings are the same term",
          code == 1 and hits(lines) == ["<sha> g.md:1: term on line 2 of "
                                        "list 1", "<sha> g.md:2: term on line"
                                        " 2 of list 1"], lines)
    wide = Path(tmp_dir("leak-wide-")) / "t.txt"
    wide.write_text("ｑｑ\u200b－１２３\n", encoding="utf-8")
    commit(r, {"h.md": "qq-123\n"}, "h")
    code, lines, _ = run(r, "--terms", str(wide), "--range", "HEAD~1..HEAD")
    check("a term written full-width in the list is normalised too",
          code == 1 and hits(lines) == ["<sha> h.md:1: term on line 1 of "
                                        "list 1"], lines)

    r, terms, base = repo()
    commit(r, {"b.md": "a clean line\n"}, "ship it for Widgetco")
    code, lines, err = run(r, "--terms", str(terms), "--range",
                           f"{base}..HEAD")
    check("a term only in the commit message: refused",
          code == 1 and hits(lines)
          == ["<sha> (commit message):1: term on line 2 of list 1"]
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
          code == 1 and hits(lines) == ["<sha> c.md:1: term on line 3 of "
                                        "list 1"], lines)
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
    held = commit(r, {"old.md": "Widgetco, already on the remote\n"}, "old")
    git(r, "update-ref", "refs/remotes/origin/main", held)
    head = commit(r, {"new.md": "clean\n"}, "new")
    check("a new branch: not the commits a remote already has",
          run(r, "--terms", str(terms),
              stdin=f"refs/heads/z {head} refs/heads/z {zero}\n")[:2]
          == (0, []))
    r, terms, _ = repo()
    check("--tree: a clean tree passes",
          run(r, "--terms", str(terms), "--tree")[:2] == (0, []))
    commit(r, {"d.md": "one\nWidg etco\n"}, "d")
    check("--tree: a term with a space inside is still found",
          run(r, "--terms", str(terms), "--tree")[:2]
          == (1, ["d.md:2: term on line 2 of list 1"]))
    commit(r, {"widgetco/e.md": "qq-321\n"}, "e")
    code, lines, _ = run(r, "--terms", str(terms), "--tree")
    check("--tree: a path holding a term is not printed",
          code == 1 and sorted(lines)[:3] == [
              "(a tracked file whose path holds a term):1: term on line 3 of "
              "list 1", "a tracked file path: term on line 2 of list 1",
              "d.md:2: term on line 2 of list 1"] and not leaks(*lines),
          lines)

    print("\n[3] where the lists are, and fail closed")
    toml = ('[harness]\nname = "acme"\ncli = "acme"\nenv_prefix = "ACME"\n'
            '[guards.leak]\nterms = ["../lists/*.txt", "~/no-such-dir/*.txt"]\n')
    r, terms, base = repo(toml)
    head = commit(r, {"e.md": "Widgetco\n"}, "e")
    rng = f"{base}..HEAD"
    code, lines, _ = run(r, "--range", rng)
    check("[guards.leak] terms: a glob from the top level; one matching "
          "nothing adds nothing", code == 1 and hits(lines)
          == ["<sha> e.md:1: term on line 2 of list 1"], lines)
    extra = terms.parent / "more.txt"
    extra.write_text("# more\n\nre:e\\.md\n", encoding="utf-8")
    code, lines, _ = run(r, "--range", rng)
    check("… every match of the glob is a list, in sorted order",
          code == 1 and hits(lines) == [
              "<sha> (a file whose path holds a term):1: term on line 2 of "
              "list 1", "a file path in commit <sha>: term on line 3 of list "
              "2"], lines)
    extra.unlink()
    other = Path(tmp_dir("leak-env-")) / "terms.txt"
    other.write_text("re:^Widgetco$\n", encoding="utf-8")
    code, lines, _ = run(r, "--range", rng,
                         environ={"ACME_CLIENT_TERMS": f"{other}{os.pathsep}"})
    check("<PREFIX>_CLIENT_TERMS is read after harness.toml's lists",
          code == 1 and hits(lines) == ["<sha> e.md:1: term on line 1 of "
                                        "list 2", "<sha> e.md:1: term on line"
                                        " 2 of list 1"], lines)
    code, lines, _ = run(r, "--range", rng, "--terms", str(other))
    check("--terms replaces the configured lists",
          code == 1 and hits(lines) == ["<sha> e.md:1: term on line 1 of "
                                        "list 1"], lines)
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
    refused("a named list missing beside one that exists", "--terms",
            str(terms), "--terms", str(terms.parent / "gone.txt"))
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
    for empties in ("re:a*", "re:x?", "re:^", "re:(?:)"):
        empty.write_text(f"Widgetco\n{empties}\n", encoding="utf-8")
        refused(f"{empties!r} matches the empty string", "--terms", str(empty))
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
