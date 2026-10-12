#!/usr/bin/env python3
"""Leak guard: refuse a push that adds a client term.

    python3 kit/tools/leak_guard.py               as a pre-push hook: the commits about to be pushed (stdin)
    python3 kit/tools/leak_guard.py --range A..B  the commits of a range
    python3 kit/tools/leak_guard.py --tree        every file git tracks, as it is in the working tree
    … --terms PATH [--terms PATH …]               these term lists instead of the configured ones

A commit is read whole: every added line, every path it adds or changes
(binary and empty files too; a non-ASCII path as it is, never git's
octal escape), and its message. A term matches case-insensitively and
ignoring whitespace (a plain term is also found with spaces inside it),
after both it and the text are NFKC-normalised and stripped of Unicode
format characters (a full-width or zero-width spelling is the same term).

The term lists are client data, so they live OUTSIDE the repository
(one term per line, `#` starts a comment, `re:` starts a regular
expression). Where they are, in harness.toml at the repository's top
level (a path or glob each; `~` expands; a relative one is from the top
level, which differs in a worktree, so prefer `~/` or an absolute path):

    [guards.leak]
    terms = ["~/work/workspaces/acme-harness/*/data/client_terms.txt"]

and `<PREFIX>_CLIENT_TERMS` (`[harness].env_prefix`), more paths or globs
separated by `:`. Both are read; `--terms` replaces them. Fail closed:
no list configured, a named list missing (even beside one that exists),
a list that cannot be read, holds no term, or a pattern that is bad or
matches the empty string refuses, and so does a git error. A glob that
matches nothing adds nothing.

A hit prints where it is and the term's place (`term on line N of list
K`, the lists in the order above, a glob's matches sorted), never the
term, the line or a list's path, so the output itself leaks nothing. A
path that holds a term is never printed either: the hit says "a file
path in commit <sha>" (or "a tracked file path"), and a line hit in that
file names it the same way.
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
import unicodedata
from pathlib import Path

ZERO = re.compile(r"^0+$")
# a hunk header, plain (@@) or combined for a merge (@@@ …): the new side's first line
HUNK = re.compile(r"^(@@+) .*?\+(\d+)(?:,\d+)? \1")
WS = re.compile(r"\s+")
SEP = "\x01"                         # between commits in one `git log` stream
DIFF = ("-p", "--cc", "--unified=0", "--no-color", "--no-ext-diff",
        "--no-renames", "--no-textconv")
GLOB = re.compile(r"[*?\[]")
ENV_NAME = "CLIENT_TERMS"            # <PREFIX>_CLIENT_TERMS


class Refusal(Exception):
    """No usable term list, or git failed: the guard refuses (exit 2)."""


class Terms(list):
    """(place, pattern) per term, and `any`: all of them as one pattern,
    so a line that holds none is passed over in one search."""
    any: re.Pattern | None = None


def git(*args: str, cwd: str | os.PathLike | None = None,
        stdin: str | None = None) -> str:
    """git's output; paths are printed as they are (core.quotePath off)."""
    r = subprocess.run(["git", "-c", "core.quotePath=false", *args],
                       capture_output=True, text=True, input=stdin,
                       encoding="utf-8", errors="replace", cwd=cwd)
    if r.returncode != 0:
        raise Refusal(f"git {args[0]} failed ({r.returncode})")
    return r.stdout


def norm(text: str) -> str:
    """NFKC, without Unicode format characters (zero-width and the like)."""
    return "".join(c for c in unicodedata.normalize("NFKC", text)
                   if unicodedata.category(c) != "Cf")


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
    out = Terms()
    for k, path in enumerate(paths, 1):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as e:
            raise Refusal(f"term list {k} cannot be read "
                          f"({type(e).__name__})") from None
        for n, raw in enumerate(text.splitlines(), 1):
            t = norm(raw).strip()
            if not t or t.startswith("#"):
                continue
            place = f"line {n} of list {k}"
            body = t[3:] if t.startswith("re:") else re.escape(WS.sub("", t))
            try:
                pat = re.compile(body, re.I)
            except re.error:
                raise Refusal(f"term on {place} is not a valid regular "
                              f"expression") from None
            if pat.search(""):
                raise Refusal(f"term on {place} matches the empty string "
                              f"(it would match every line)")
            out.append((place, pat))
    if not out:
        raise Refusal("the term lists hold no term")
    try:
        out.any = re.compile("|".join(f"(?:{p.pattern})" for _, p in out),
                             re.I)
    except re.error:             # a term with its own global flags: one by one
        out.any = None
    return out


def scan(text: str, terms: Terms) -> list[str]:
    """The place of every term found in one line of text."""
    text = norm(text)
    squeezed = WS.sub("", text)
    if terms.any is not None and not (terms.any.search(squeezed)
                                      or terms.any.search(text)):
        return []
    return [place for place, pat in terms
            if pat.search(squeezed) or pat.search(text)]


def _unquote(path: str) -> str:
    """A path from a diff header: git still C-quotes one with a tab, a
    newline, a quote or a backslash in it, even with core.quotePath off."""
    path = path.rstrip("\t")        # git ends a header path holding a space with a tab
    if not (len(path) > 1 and path[0] == path[-1] == '"'):
        return path
    raw, i, body = bytearray(), 0, path[1:-1]
    simple = {"t": 9, "n": 10, '"': 34, "\\": 92, "a": 7, "b": 8, "f": 12,
              "r": 13, "v": 11}
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt in "01234567" and re.match(r"[0-7]{3}", body[i + 1:i + 4]):
                raw.append(int(body[i + 1:i + 4], 8))
                i += 4
                continue
            raw.append(simple.get(nxt, ord(nxt)))
            i += 2
            continue
        raw += c.encode("utf-8")
        i += 1
    return raw.decode("utf-8", errors="replace")


def _patch(short: str, patch: str, terms: Terms, hidden: set[str]
           ) -> list[str]:
    """Hits in the added lines of one commit's patch (plain or combined)."""
    hits: list[str] = []
    path, lineno, width = None, 0, 0
    for line in patch.splitlines():
        if line.startswith("diff --"):
            path, width = None, 0            # a file header until its first hunk
            continue
        if not width:
            if line.startswith("+++ "):
                new = _unquote(line[4:])
                path = None if new == "/dev/null" else new.removeprefix("b/")
            m = HUNK.match(line)
            if m and path is not None:
                lineno, width = int(m.group(2)), len(m.group(1)) - 1
            continue
        m = HUNK.match(line)
        if m:
            lineno = int(m.group(2))
            continue
        mark = line[:width]
        if "-" in mark:
            continue                         # a removed line
        if "+" in mark:
            shown = ("(a file whose path holds a term)" if path in hidden
                     else path)
            hits += [f"{short} {shown}:{lineno}: term on {p}"
                     for p in scan(line[width:], terms)]
        lineno += 1
    return hits


def scan_commits(shas: list[str], terms: Terms, cwd=None) -> list[str]:
    """Hits in each commit's message, the paths it adds or changes and its
    added lines: two `git log` runs for all of them, not two per commit."""
    if not shas:
        return []
    given = "".join(s + "\n" for s in shas)
    names = git("log", "--no-walk=unsorted", "--stdin", "-z", "--cc",
                "--name-only", "--no-renames", "--diff-filter=d",
                f"--format={SEP}%H", cwd=cwd, stdin=given)
    paths: dict[str, list[str]] = {}
    for chunk in names.split(SEP)[1:]:
        sha, _, rest = chunk.partition("\0")
        paths[sha] = [n.lstrip("\n") for n in rest.split("\0")
                      if n.lstrip("\n")]
    log = git("log", "--no-walk=unsorted", "--stdin", *DIFF,
              f"--format={SEP}%H%x00%B%x00", cwd=cwd, stdin=given)
    hits: list[str] = []
    for chunk in log.split(SEP)[1:]:
        sha, message, patch = (chunk.split("\0", 2) + ["", ""])[:3]
        short = sha[:10]
        for k, line in enumerate(message.splitlines(), 1):
            hits += [f"{short} (commit message):{k}: term on {p}"
                     for p in scan(line, terms)]
        hidden = set()
        for f in paths.get(sha, []):
            found = scan(f, terms)
            if found:
                hidden.add(f)
                hits += [f"a file path in commit {short}: term on {p}"
                         for p in found]
        hits += _patch(short, patch, terms, hidden)
    return hits


def scan_range(rng: str, terms: Terms, cwd=None) -> list[str]:
    return scan_commits(git("rev-list", "--reverse", rng, cwd=cwd).split(),
                        terms, cwd)


def scan_push(stdin: str, terms: Terms, cwd=None) -> list[str]:
    """pre-push stdin: `<local ref> <local sha> <remote ref> <remote sha>`
    per ref pushed. A deletion adds nothing; a new branch is what no
    remote has yet."""
    shas: list[str] = []
    for line in stdin.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        local, remote = parts[1], parts[3]
        if ZERO.match(local):
            continue
        if ZERO.match(remote):
            new = git("rev-list", "--reverse", local, "--not", "--remotes",
                      cwd=cwd).split()
        else:
            new = git("rev-list", "--reverse", f"{remote}..{local}",
                      cwd=cwd).split()
        shas += [s for s in new if s not in shas]
    return scan_commits(shas, terms, cwd)


def scan_tree(terms: Terms, cwd=None) -> list[str]:
    root = Path(git("rev-parse", "--show-toplevel", cwd=cwd).strip())
    hits = []
    for f in sorted(x for x in git("ls-files", "-z", cwd=cwd).split("\0")
                    if x):
        found = scan(f, terms)
        hits += [f"a tracked file path: term on {p}" for p in found]
        shown = "(a tracked file whose path holds a term)" if found else f
        try:
            data = (root / f).read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for k, line in enumerate(text.splitlines(), 1):
            hits += [f"{shown}:{k}: term on {p}" for p in scan(line, terms)]
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
