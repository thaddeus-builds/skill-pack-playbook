r"""A page the harness delivers is drawn by the harness: no shipped file hands a person a link to a hosted artifact.

A harness hands people pages, samples and demos (an owner's review page, a client's draft, a design demo). The rule
(docs/rules.md, "A page the harness delivers is drawn by the harness"): each one comes from one of the harness's own
verbs, from the data it holds or a synthetic fixture, so the cloud agent that installs the harness from git can
draw it again and it cannot drift from the code. A link to a page someone published from a chat session is a
convenience for looking at something locally while debugging; it is never the deliverable. This check bans the link
from what ships; that the page really comes from a verb is the harness's own test of its verb.

`check_links(root)` reads the tracked files `git archive` would ship (kit.guards.release asks git: tracked, less the
export-ignore ones; an untracked file is not read until `git add`, and a repository that tracks nothing is a problem;
with no git or no repository the whole tree is read, less dot-directories, never a skip). Every file is read as text
unless it holds a NUL byte (an image, UTF-16) or is over 5 MB, and a symlink is not followed. It returns a problem for
every hosted-artifact link: its path and line, never the link. A link in a file that does not ship (a planning file, a
local note in `[release].internal`) is fine: it never reaches the installed harness.

A line is read after `html.unescape`, `%`-decoding (twice), `\uXXXX` and backslash-slash decoding, so an entity-,
percent-, JSON- or double-escaped slash is a slash; the host may carry a trailing dot or a port, and a link wrapped
across a line break is read as one. What is not read: a link built from parts, and one in a file type that holds no
text. Not read either: the vendored kit (`<scripts_dir>/kit/`) and console (`console/`) when they hold a
MANIFEST.sha256 (the playbook's own bytes, held by the drift guard), and the `[guards.pages]` tables of harness.toml,
which name the hosts it adds.

`[guards.pages]` in harness.toml:

  hosts   more hosts or paths to treat as hosted artifacts, beside HOSTS (a list of plain texts with a dot, at least
          four characters, matched without case)
  allow   {path: reason} or {path: {reason, max}}: a shipped file that may hold such a link, with why (a document
          that names the rule, say), and with `max`, at most that many lines (a link added later in the same file is
          then a problem). A row with no reason, a path that is gone or does not ship, or one that holds no link now
          is a problem (a stale row hides nothing)

The rule prefers a false hit, which an `allow` row answers, to a miss (docs/lessons.md, "A guard's refinement never
costs the recall it had"): any text that spells a host is a hit, in code, a string, a comment or prose. Other hosts
that serve hosted pages are the harness's to add in `hosts`.

`self_test()` plants each form and returns the ones the check missed.

Test: kit/tests/test_page_links.py.
"""

from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.parse import unquote

from kit.guards import harness, read, section
from kit.guards import release as _release

HOSTS = ("claude.ai/artifact", "claude.ai/code/artifact", "claude.ai/public/artifacts")
MAX_BYTES = 5_000_000
SKIP_DIRS = ("node_modules", "__pycache__")
PAGES_TABLE = re.compile(r"^\[guards\.pages[^\]\n]*\][^\n]*\n(?:(?!\[)[^\n]*\n?)*", re.M)


def _normal(text: str) -> str:
    """The text with its escapes undone and lowercased, line breaks kept, so a hit's line is the file's."""
    for _ in range(2):
        text = unquote(html.unescape(text))
    text = re.sub(r"\\u00([0-9a-f]{2})", lambda m: chr(int(m.group(1), 16)), text, flags=re.I)
    return re.sub(r"\\+/", "/", text).lower()


def _pattern(hosts) -> re.Pattern:
    def one(h: str) -> str:
        first, *rest = [p for p in h.strip().lower().split("/") if p]
        return r"[ \t]*/+[ \t]*\n?[ \t]*".join([re.escape(first) + r"\.?(?::\d+)?", *map(re.escape, rest)])
    parts = [one(h) for h in hosts if h.strip("/ ")]
    return re.compile("|".join(parts)) if parts else re.compile(r"(?!x)x")


def hits(text: str, hosts=HOSTS) -> list[int]:
    """The 1-based lines of `text` where a hosted-artifact link starts (a link wrapped across lines: its first)."""
    norm = _normal(text)
    return sorted({norm.count("\n", 0, m.start()) + 1 for m in _pattern(hosts).finditer(norm)})


def settings(cfg) -> tuple[tuple[str, ...], dict, list[str]]:
    """(hosts, allow {path: (reason, max or None)}, problems with the config itself)."""
    g = section(cfg, "guards", "pages")
    bad: list[str] = []
    raw = g.get("hosts", [])
    hosts = [h for h in (raw if isinstance(raw, list) else []) if isinstance(h, str)]
    if not isinstance(raw, list) or len(hosts) != len(raw):
        bad.append("[guards.pages].hosts: a list of host texts")
    for h in hosts[:]:
        if "." not in h or len(h.strip("/ ")) < 4:
            bad.append(f"[guards.pages].hosts {h!r}: a host has a dot and at least four characters (a shorter text "
                       f"would match nearly every line)")
            hosts.remove(h)
    rows = g.get("allow", {})
    allow: dict = {}
    if not isinstance(rows, dict):
        bad.append("[guards.pages].allow: a table {path = reason}")
        rows = {}
    for path, v in rows.items():
        key = str(path).strip().removeprefix("./")
        reason, cap = (v.get("reason"), v.get("max")) if isinstance(v, dict) else (v, None)
        if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 1):
            bad.append(f"[guards.pages].allow {path!r}: max is a whole number of lines, at least 1")
            cap = None
        allow[key] = (reason, cap)
    return (*HOSTS, *hosts), allow, bad


def _readable(path: Path) -> str | None:
    """The file's text, or None for a symlink, a file over MAX_BYTES, or one with a NUL byte."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    return None if b"\0" in raw else raw.decode("utf-8", errors="replace")


def _vendored(root: Path, rel: str) -> bool:
    return (root / rel / "MANIFEST.sha256").is_file()


def files(root: Path, cfg) -> tuple[list[str], list[str]]:
    """(the files to read, problems). Shipped files (the whole tree with no git, less dot-directories), less the
    vendored kit and console and the symlinks."""
    got = _release.shipped(root)
    problems: list[str] = []
    if got is not None:
        tracked, ships = got
        if not tracked:
            problems.append("git tracks no file here: `git add` the harness's files (an untracked file is not read)")
        names = sorted(ships)
    else:
        names = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
            names += [str((Path(dirpath) / f).relative_to(root)) for f in sorted(filenames)]
    skip = [d for d in (f"{cfg.scripts_dir}/kit", "console") if _vendored(root, d)]
    return [f for f in names if not _release.under(f, skip)], problems


def check_links(root: Path | str | None = None) -> list[str]:
    """Every hosted-artifact link in a file the harness ships, outside the `allow` rows; [] when the rule holds."""
    cfg = harness(root)
    base = Path(root) if root is not None else cfg.root
    hosts, allow, out = settings(cfg)
    names, more = files(base, cfg)
    out += more
    found: dict[str, list[int]] = {}
    for rel in names:
        text = _readable(base / rel)
        if text is None:
            continue
        if rel == "harness.toml":
            text = PAGES_TABLE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
        lines = hits(text, hosts)
        if lines:
            found[rel] = lines
    for rel, lines in found.items():
        reason, cap = allow.get(rel, (None, None))
        if rel in allow and (cap is None or len(lines) <= cap):
            continue
        if rel in allow:
            out.append(f"{rel}: {len(lines)} lines hold a link, [guards.pages].allow lets {cap} (lines {lines})")
            continue
        out += [f"{rel}:{n}: a link to a hosted artifact ships; the page is drawn by a verb of this harness "
                f"(allow it in [guards.pages].allow with its reason, or keep the link in a file that does not "
                f"ship)" for n in lines]
    for rel, (why, _) in sorted(allow.items()):
        if not isinstance(why, str) or not why.strip():
            out.append(f"[guards.pages].allow {rel!r}: give its reason (why this shipped file may hold such a link)")
        elif not (base / rel).is_file():
            out.append(f"[guards.pages].allow {rel!r}: is gone: drop the row")
        elif rel not in found:
            out.append(f"[guards.pages].allow {rel!r}: holds no such link, or does not ship: drop the row")
    return out


# ---- the rule, each form on a plant ---------------------------------------------------------------------------

H = "claude" + ".ai"                    # spelled apart so no file here is itself a link
PLANTED = {
    "a markdown link": f"See [the page](https://{H}/artifact/AbC123) for the draft.\n",
    "a bare host": f"draft: {H}/artifact/AbC123\n",
    "a code-session link": f"print('open https://{H}/code/artifact/0f1e2d3c-aaaa')\n",
    "a public share": f"url = 'https://{H}/public/artifacts/abc'\n",
    "capitals": f"HTTPS://{H.upper()}/ARTIFACT/ABC\n",
    "www and http": f"http://www.{H}/artifact/abc\n",
    "a trailing dot": f"{H}./artifact/abc\n",
    "a port": f"{H}:443/artifact/abc\n",
    "json-escaped slashes": '{"link": "https:\\/\\/' + H + '\\/artifact\\/abc"}\n',
    "double-escaped slashes": '{"link": "' + H + '\\\\/artifact\\\\/abc"}\n',
    "a json unicode slash": H + "\\u002fartifact\\u002fabc\n",
    "percent-encoded": "redirect?to=https%3A%2F%2F" + H + "%2Fartifact%2Fabc\n",
    "double percent-encoded": H + "%252Fartifact%252Fabc\n",
    "a percent-encoded letter": H + "/%61rtifact/abc\n",
    "an html entity slash": H + "&#47;artifact&#x2F;abc\n",
    "a named entity slash": H + "&sol;artifact&sol;abc\n",
    "a doubled slash": H + "//artifact/abc\n",
    "wrapped across a line": H + "/\nartifact/abc\n",
    "on a later line": f"# a page\n\nsome words\nthe sample: {H}/artifact/abc\n",
}
SOUND = (f"The page is written by `site build` to the review folder.\n"
         f"Read the docs at https://{H}/docs/overview.\n"
         "An artifact is a build output here; the cloud agent installs from git.\n")


def self_test() -> list[str]:
    """The forms the check missed, or "the sound text fails"; empty is sound."""
    missed = [what for what, text in PLANTED.items() if not hits(text)]
    if hits(SOUND):
        missed.append("the sound text fails")
    if hits(PLANTED["on a later line"]) != [4] or hits("a\r\nb\r\n" + H + "/artifact/x") != [3]:
        missed.append("the line of a hit")
    if hits("see example.test/page/abc", hosts=(*HOSTS, "example.test/page")) != [1]:
        missed.append("a host the harness adds")
    if hits("see example.test/page/abc"):
        missed.append("a host nobody added is no hit")
    return missed
