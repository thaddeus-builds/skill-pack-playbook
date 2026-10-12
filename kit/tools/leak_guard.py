#!/usr/bin/env python3
"""Leak guard: refuse a push that adds a client term.

    python3 kit/tools/leak_guard.py               as a pre-push hook: the commits about to be pushed (stdin)
    python3 kit/tools/leak_guard.py --range A..B  the commits of a range
    python3 kit/tools/leak_guard.py --tree        every file git tracks, as it is in the working tree
    … --terms PATH [--terms PATH …]               these term lists instead of the configured ones

A commit is read whole: every added line, every path it adds or changes,
and its message. A term matches case-insensitively and ignoring
whitespace (a plain term is also found with spaces inside it).

The term lists are client data, so they live OUTSIDE the repository
(one term per line, `#` starts a comment, `re:` starts a regular
expression). Where they are, in harness.toml at the repository's top
level (a path or glob each; `~` expands; a relative one is from the top
level, which differs in a worktree, so prefer `~/` or an absolute path):

    [guards.leak]
    terms = ["~/work/workspaces/acme-harness/*/data/client_terms.txt"]

and `<PREFIX>_CLIENT_TERMS` (`[harness].env_prefix`), more paths or globs
separated by `:`. Both are read; `--terms` replaces them. Fail closed:
no list configured, a named list missing, a list that cannot be read,
holds no term or an empty or bad pattern refuses, and so does a git
error. A glob that matches nothing adds nothing.

A hit prints where it is and the term's place (`term on line N of list
K`, the lists in the order above, a glob's matches sorted), never the
term, the line or a list's path, so the output itself leaks nothing.
Exit 0: no hit; 1: a hit; 2: refused for want of a usable list or git.

Install, once per clone: kit/tools/pre-push.sample (its header says how).
Seen in the video-ads harness, whose own guard this generalises (one list
per client workspace, several clients beside one harness).

Stdlib only; runs without a bound harness.

Test: kit/tests/test_leak_guard.py.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from pathlib import Path

ZERO = re.compile(r"^0+$")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
WS = re.compile(r"\s+")
GLOB = re.compile(r"[*?\[]")
ENV_NAME = "CLIENT_TERMS"            # <PREFIX>_CLIENT_TERMS


class Refusal(Exception):
    """No usable term list, or git failed: the guard refuses (exit 2)."""


Terms = list[tuple[str, re.Pattern]]          # (place, pattern)


def git(*args: str, cwd: str | os.PathLike | None = None) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=cwd)
    if r.returncode != 0:
        raise Refusal(f"git {args[0]} failed ({r.returncode})")
    return r.stdout


def _harness_toml(root: Path) -> dict:
    path = root / "harness.toml"
    if not path.is_file():
        return {}
    try:
        import tomllib
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except ImportError:
        raise Refusal("harness.toml needs Python 3.11 or newer to read"
                      ) from None
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise Refusal(f"harness.toml cannot be read "
                      f"({type(e).__name__})") from None


def configured(root: Path, environ: dict[str, str]
               ) -> list[tuple[str, str]]:
    """(source, path or glob) of every configured list, in order:
    `[guards.leak] terms`, then `<PREFIX>_CLIENT_TERMS`."""
    raw = _harness_toml(root)
    specs = []
    terms = raw.get("guards", {}).get("leak", {}).get("terms", [])
    if not (isinstance(terms, list)
            and all(isinstance(t, str) and t.strip() for t in terms)):
        raise Refusal("[guards.leak] terms must be a list of paths")
    specs += [(f"[guards.leak] terms #{i}", t)
              for i, t in enumerate(terms, 1)]
    prefix = raw.get("harness", {}).get("env_prefix")
    if isinstance(prefix, str) and prefix:
        var = f"{prefix}_{ENV_NAME}"
        parts = [p for p in environ.get(var, "").split(os.pathsep)
                 if p.strip()]
        specs += [(f"{var} #{i}", p) for i, p in enumerate(parts, 1)]
    return specs


def resolve(specs: list[tuple[str, str]], base: Path) -> list[Path]:
    """The list files, in order, each once. A named file that is missing
    refuses; a glob may match nothing."""
    out: list[Path] = []
    for source, spec in specs:
        p = Path(spec.strip()).expanduser()
        if not p.is_absolute():
            p = base / p
        if GLOB.search(str(p)):
            found = [Path(x) for x in sorted(glob.glob(str(p)))
                     if Path(x).is_file()]
        else:
            if not p.is_file():
                raise Refusal(f"the term list of {source} is missing")
            found = [p]
        out += [f for f in found if f.resolve() not in
                {g.resolve() for g in out}]
    return out


def load_terms(paths: list[Path]) -> Terms:
    """(place, pattern) per term. A plain term is matched with its
    whitespace removed against text with its whitespace removed; a `re:`
    term against the text both as it is and without whitespace."""
    out: Terms = []
    for k, path in enumerate(paths, 1):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as e:
            raise Refusal(f"term list {k} cannot be read "
                          f"({type(e).__name__})") from None
        for n, raw in enumerate(text.splitlines(), 1):
            t = raw.strip()
            if not t or t.startswith("#"):
                continue
            place = f"line {n} of list {k}"
            body = t[3:] if t.startswith("re:") else re.escape(WS.sub("", t))
            if not body.strip():
                raise Refusal(f"term on {place} is an empty pattern")
            try:
                out.append((place, re.compile(body, re.I)))
            except re.error:
                raise Refusal(f"term on {place} is not a valid regular "
                              f"expression") from None
    if not out:
        raise Refusal("the term lists hold no term")
    return out


def scan(text: str, terms: Terms) -> list[str]:
    """The place of every term found in one line of text."""
    squeezed = WS.sub("", text)
    return [place for place, pat in terms
            if pat.search(squeezed) or pat.search(text)]


def scan_commit(sha: str, terms: Terms, cwd=None) -> list[str]:
    hits = []
    short = sha[:10]
    message = git("log", "-1", "--format=%B", sha, cwd=cwd)
    for k, line in enumerate(message.splitlines(), 1):
        hits += [f"{short} (commit message):{k}: term on {p}"
                 for p in scan(line, terms)]
    diff = git("show", "--format=", "--unified=0", "--no-color",
               "--no-ext-diff", "--no-renames", sha, cwd=cwd)
    path, lineno = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = (None if line[4:] == "/dev/null"
                    else line[4:].removeprefix("b/"))
            if path:
                hits += [f"{short} {path} (its path): term on {p}"
                         for p in scan(path, terms)]
            continue
        if line.startswith("--- ") or line.startswith("diff --git"):
            continue
        m = HUNK.match(line)
        if m:
            lineno = int(m.group(1))
            continue
        if path and line.startswith("+"):
            hits += [f"{short} {path}:{lineno}: term on {p}"
                     for p in scan(line[1:], terms)]
            lineno += 1
    return hits


def scan_range(rng: str, terms: Terms, cwd=None) -> list[str]:
    hits = []
    for sha in git("rev-list", "--reverse", rng, cwd=cwd).split():
        hits += scan_commit(sha, terms, cwd)
    return hits


def scan_push(stdin: str, terms: Terms, cwd=None) -> list[str]:
    """pre-push stdin: `<local ref> <local sha> <remote ref> <remote sha>`
    per ref pushed. A deletion adds nothing; a new branch is what no
    remote has yet."""
    hits = []
    for line in stdin.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        local, remote = parts[1], parts[3]
        if ZERO.match(local):
            continue
        if ZERO.match(remote):
            shas = git("rev-list", "--reverse", local, "--not", "--remotes",
                       cwd=cwd).split()
        else:
            shas = git("rev-list", "--reverse", f"{remote}..{local}",
                       cwd=cwd).split()
        for sha in shas:
            hits += scan_commit(sha, terms, cwd)
    return hits


def scan_tree(terms: Terms, cwd=None) -> list[str]:
    root = Path(git("rev-parse", "--show-toplevel", cwd=cwd).strip())
    hits = []
    for f in sorted(x for x in git("ls-files", "-z", cwd=cwd).split("\0")
                    if x):
        hits += [f"{f} (its path): term on {p}" for p in scan(f, terms)]
        try:
            data = (root / f).read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for k, line in enumerate(text.splitlines(), 1):
            hits += [f"{f}:{k}: term on {p}" for p in scan(line, terms)]
    return hits


def main(argv: list[str] | None = None, *, stdin: str | None = None,
         cwd: str | os.PathLike | None = None,
         environ: dict[str, str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="leak_guard", description=__doc__.split("\n\n")[0])
    ap.add_argument("hook_args", nargs="*",
                    help="a pre-push hook's remote name and url (ignored)")
    ap.add_argument("--terms", action="append", default=[],
                    help="a term list (path or glob; repeatable); replaces "
                         "the configured ones")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--tree", action="store_true",
                      help="scan every tracked file in the working tree")
    mode.add_argument("--range",
                      help="scan the commits of A..B (added lines, paths "
                           "and messages)")
    a = ap.parse_args(argv)
    environ = os.environ if environ is None else environ
    try:
        top = Path(git("rev-parse", "--show-toplevel", cwd=cwd).strip())
        if a.terms:
            specs = [(f"--terms #{i}", t) for i, t in enumerate(a.terms, 1)]
            base = Path(cwd or os.getcwd())
        else:
            specs, base = configured(top, environ), top
        if not specs:
            raise Refusal("no term list configured: set [guards.leak] terms "
                          "in harness.toml or <PREFIX>_CLIENT_TERMS, or pass "
                          "--terms")
        paths = resolve(specs, base)
        if not paths:
            raise Refusal("no configured term list exists")
        terms = load_terms(paths)
        if a.tree:
            hits, what = scan_tree(terms, cwd), "tracked files"
        elif a.range:
            hits, what = scan_range(a.range, terms, cwd), "commits of the range"
        else:
            text = sys.stdin.read() if stdin is None else stdin
            hits, what = scan_push(text, terms, cwd), "commits to push"
    except Refusal as e:
        print(f"leak_guard: {e}; refusing", file=sys.stderr)
        return 2
    for h in hits:
        print(h)
    print(f"leak_guard: {len(hits)} hit(s) in {what} ({len(terms)} terms, "
          f"{len(paths)} list(s))", file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
