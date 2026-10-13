#!/usr/bin/env python3
"""kit.guards.pages: a page the harness delivers is drawn by the harness, so no shipped file links to a hosted artifact.
On SYNTHETIC files only (neutral names, a made-up artifact id).

  [0] the rule on its planted forms: a markdown link, a bare host, a code-session link, a public share, capitals,
      JSON-escaped and percent-encoded slashes; the sound text and look-alike hosts are no hit
  [1] a harness on disk (git): a link in a shipped file of any text type (every extension, none, upper case) is reported
      by path and line and never by the link; the same link in an export-ignore (internal) file is not; the vendored kit
      and the console (only when they hold a MANIFEST.sha256) are not read, a console of the harness's own is; a file
      with a NUL byte, over 5 MB, a symlink, a file deleted from the disk and a directory named like a file are not read
      and do not crash; harness.toml is read outside its [guards.pages] tables; a repository with nothing tracked is a
      problem; a harness with no git is read whole, less .git, virtualenvs and caches
  [2] [guards.pages]: allow (with its reason, passing; with max, a link added later is a problem; no reason, a path that
      is gone, a file that holds no link now, a file that does not ship: each a problem), hosts (a host the harness
      adds; a bad one is a problem), a bad allow table is a problem
  [3] the day-one suite runs the rule (suites.page_links)
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit.guards import pages  # noqa: E402
from kit.testing import suites  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

HAS_GIT = shutil.which("git") is not None
H = pages.H
LINK = f"https://{H}/artifact/DEMO-abc123"
TOML = """
[release]
internal = ["notes", "CLAUDE.md"]
must_ship = ["SKILL.md"]
"""


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=kit test", "-c", "user.email=kit@example.com",
                    "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True)


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def build(extra: str = "", *, repo: bool = True) -> Path:
    """A harness whose files are clean; `extra` is appended to its harness.toml."""
    root = Path(tmp_dir("page-links-")) / "shop"
    shutil.copytree(_shop.SHOP, root, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    toml = root / "harness.toml"
    text = toml.read_text(encoding="utf-8")
    text = re.sub(r"\[release\]\n(?:.*\n)*?(?=\n\[)", "", text)          # the fake shop's own release table
    toml.write_text(text + TOML + extra, encoding="utf-8")
    write(root, "SKILL.md", "# Skill\nThe page is written by `space page`.\n")
    write(root, "README.md", f"# Readme\nDocs: https://{H}/docs/overview\n")
    write(root, "scripts/shop.py", "print('ok')\n")
    write(root, "notes/local.md", "scratch\n")
    write(root, "CLAUDE.md", "# internal\n")
    write(root, ".gitattributes", "/notes export-ignore\n/CLAUDE.md export-ignore\n")
    if repo and HAS_GIT:
        git(root, "init", "-q")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "clean")
    return root


def commit(root: Path) -> None:
    if HAS_GIT and (root / ".git").exists():
        git(root, "add", "-A")
        git(root, "commit", "-qm", "change", "--allow-empty")


def put(root: Path, rel: str, text: str) -> None:
    write(root, rel, text)
    commit(root)


def test_rule() -> None:
    print("[0] the rule on its planted forms")
    check("self_test: every form is caught, the sound text passes", pages.self_test() == [], pages.self_test())
    for what, text in pages.PLANTED.items():
        check(f"planted: {what}", pages.hits(text) != [], text)
    check("the line is named", pages.hits(pages.PLANTED["on a later line"]) == [4])
    for text in (f"https://{H}/docs", f"{H}/new", "an artifact is a build output", "see artifact/abc at example.test"):
        check(f"no hit: {text!r}", pages.hits(text) == [], text)
    check("a path that only begins with a host is a hit (a false hit over a miss)", pages.hits(f"{H}/artifacts-x") == [1])
    check("two hits on two lines", pages.hits(f"{LINK}\nx\n{LINK}") == [1, 3])
    check("the line count is the file's: a form feed or a line separator does not start a line",
          pages.hits(f"a\x0cb\u2028c\n{LINK}") == [2])


def test_harness() -> None:
    print("\n[1] a harness on disk")
    root = build()
    check("the clean harness passes", pages.check_links(root) == [], pages.check_links(root))
    for rel, text, where in (("SKILL.md", f"# Skill\nSee {LINK}\n", "SKILL.md:2"),
                             ("README.md", f"[draft]({LINK})\n", "README.md:1"),
                             ("scripts/shop.py", f"url = '{LINK}'\n", "scripts/shop.py:1"),
                             ("docs/sample.html", f"<a href='{LINK}'>x</a>\n", "docs/sample.html:1"),
                             ("templates/page.md.tmpl.json", f'{{"u": "{LINK.replace("/", chr(92) + "/")}"}}\n',
                              "templates/page.md.tmpl.json:1"),
                             ("Makefile", f"open: ; echo {LINK}\n", "Makefile:1"),
                             ("NOTES.MD", f"{LINK}\n", "NOTES.MD:1"),
                             ("docs/page.j2", f"{{{{ x }}}} {LINK}\n", "docs/page.j2:1"),
                             ("app/page.tsx", f"const u = '{LINK}'\n", "app/page.tsx:1"),
                             ("harness.toml", f"# {LINK}\n", "harness.toml"),
                             ("ssot/links.tsv", f"a\t{LINK}\n", "ssot/links.tsv:1")):
        r = build()
        put(r, rel, (open(r / rel).read() if rel == "harness.toml" else "") + text)
        got = pages.check_links(r)
        check(f"a link in {rel} is reported by path and line", len(got) == 1 and got[0].startswith(where + ":"), got)
        check(f"…never by the link itself", all("DEMO-abc123" not in g and f"{H}/artifact" not in g for g in got), got)
    if HAS_GIT:
        r = build()
        put(r, "notes/local.md", f"scratch {LINK}\n")
        put(r, "CLAUDE.md", f"internal {LINK}\n")
        check("a link in an export-ignore (internal) file is fine: it never ships", pages.check_links(r) == [],
              pages.check_links(r))
        r = build()
        put(r, "scripts/kit/MANIFEST.sha256", "x\n")
        put(r, "scripts/kit/guards/pages.py", f"HOSTS = ('{LINK}',)\n")
        put(r, "console/MANIFEST.sha256", "x\n")
        put(r, "console/README.md", f"{LINK}\n")
        check("a vendored kit and console (each with its MANIFEST.sha256) are not read", pages.check_links(r) == [],
              pages.check_links(r))
        r = build()
        put(r, "scripts/kit/guards/pages.py", f"HOSTS = ('{LINK}',)\n")
        put(r, "console/own.md", f"{LINK}\n")
        check("…but a console or a scripts/kit of the harness's own, with no MANIFEST.sha256, is", len(pages.check_links(r)) == 2,
              pages.check_links(r))
        r = build()
        put(r, "scripts/other/README.md", f"{LINK}\n")
        check("…and another folder under scripts/ is", len(pages.check_links(r)) == 1)
        r = build()
        (r / "logo.bin").write_bytes(b"\x00\x01" + LINK.encode())
        (r / "big.md").write_text(LINK + "\n" + "x" * 5_000_001)
        outside = Path(tmp_dir("outside-")) / "o.md"
        outside.write_text(LINK + "\n")
        os.symlink(str(outside), r / "alias.md")
        (r / "dir.md").mkdir()
        put(r, "dir.md/inner.txt", "no link\n")
        (r / "ghost.md").write_text(f"{LINK}\n")
        commit(r)
        (r / "ghost.md").unlink()
        os.symlink(str(r / "nowhere"), r / "broken.md")
        commit(r)
        check("a file with a NUL byte, one over 5 MB, a symlink, a broken symlink, a file deleted from the disk and a "
              "directory named like a file are not read, and do not crash", pages.check_links(r) == [], pages.check_links(r))
        r = build()
        (r / "u16.txt").write_bytes((LINK + "\n").encode("utf-16"))
        commit(r)
        check("UTF-16 with a byte order mark is decoded and read", len(pages.check_links(r)) == 1, pages.check_links(r))
        r = build()
        (r / "u16.txt").write_bytes((LINK + "\n").encode("utf-16-le"))
        commit(r)
        check("UTF-16 without one (NUL bytes) is not read: the docstring says so", pages.check_links(r) == [])
        r = build(repo=False)
        git(r, "init", "-q")
        check("a repository that tracks nothing is a problem, not a pass", len(pages.check_links(r)) == 1
              and "tracks no file" in pages.check_links(r)[0], pages.check_links(r))
        r = build()
        write(r, "untracked.md", f"{LINK}\n")
        check("an untracked file is not read until `git add` (the docstring says so)", pages.check_links(r) == [])
    else:
        check("skipped: the git cases", True)
    r = build(repo=False)
    write(r, "notes/local.md", f"scratch {LINK}\n")
    check("with no repository the whole tree is read (never a silent pass)", len(pages.check_links(r)) == 1
          and pages.check_links(r)[0].startswith("notes/local.md:1:"), pages.check_links(r))
    write(r, "notes/local.md", "scratch\n")
    write(r, ".venv/lib/x.md", LINK)
    write(r, ".git/x.md", LINK)
    write(r, "node_modules/p/README.md", LINK)
    check("…less .git, virtualenvs and node_modules", pages.check_links(r) == [], pages.check_links(r))
    write(r, ".claude/skills/x/SKILL.md", LINK)
    write(r, ".github/workflow.yml", LINK)
    check("…but other dot-directories (.claude, .github) are read", len(pages.check_links(r)) == 2, pages.check_links(r))
    r = build()
    toml = (r / "harness.toml").read_text()
    put(r, "harness.toml", toml + f'\n[guards.pages]\nhosts = ["example.test/page"]\n\n[other]\nnote = "{LINK}"\n')
    got = pages.check_links(r)
    check("harness.toml is read outside its [guards.pages] tables (a link after them is caught, the host it names is not)",
          len(got) == 1 and got[0].startswith("harness.toml"), got)
    check("a link wrapped across lines is reported at its first line", pages.hits(f"x {H}/\nartifact/abc") == [1])
    check("…also when the next line opens with a comment mark, a quote mark or a bullet",
          all(pages.hits(f"{H}/\n{m} artifact/abc") == [1] for m in ("#", ">", "*", "//", "-")))
    check("a decoded line break (%0A, an entity, \\u000a) moves no line number",
          pages.hits(f"a%0Ab&#10;c\n{LINK}") == [2] and pages.hits(f"a\\u000ab\n{LINK}") == [2])
    import time
    t0 = time.time()
    pages.hits(f"{H}/" + " " * 40000 + "x\n" + (f"{H}/" + " " * 2000 + "\n") * 20)
    check("a long run of spaces after a host does not stall the check (linear)", time.time() - t0 < 2.0, time.time() - t0)
    t = '[guards.pages]\nhosts = ["example.test/page"]\n  [other]\nnote = "x"\n[b]\nk = 1\n'
    check("the [guards.pages] strip keeps the line count and stops at an indented header",
          pages.PAGES_TABLE.sub(lambda m: "\n" * m.group(0).count("\n"), t).count("\n") == t.count("\n")
          and "[other]" in pages.PAGES_TABLE.sub("", t))


def test_config() -> None:
    print("\n[2] [guards.pages]")
    ok = '[guards.pages.allow]\n"docs/rule.md" = "the page that names the rule"\n'
    r = build(ok)
    put(r, "docs/rule.md", f"The rule bans links like {LINK}\n")
    check("an allowed file with its reason passes", pages.check_links(r) == [], pages.check_links(r))
    put(r, "docs/other.md", f"{LINK}\n")
    check("…and only that file", len(pages.check_links(r)) == 1 and pages.check_links(r)[0].startswith("docs/other.md:1:"))
    r = build('[guards.pages.allow."docs/rule.md"]\nreason = "names the rule"\nmax = 1\n')
    put(r, "docs/rule.md", f"{LINK}\n")
    check("an allow row with max passes at max", pages.check_links(r) == [], pages.check_links(r))
    put(r, "docs/rule.md", f"{LINK}\nand again {LINK}\n")
    got = pages.check_links(r)
    check("…and a link added later in the same file is a problem", len(got) == 1 and "lets 1" in got[0], got)
    r = build('[guards.pages.allow."docs/rule.md"]\nreason = "x"\nmax = 0\n')
    put(r, "docs/rule.md", f"{LINK}\n")
    check("a max that is not a whole number of at least 1 is a problem", any("max is a whole number" in g
                                                                              for g in pages.check_links(r)))
    r = build('[guards.pages.allow]\n"./docs/rule.md" = "names the rule"\n')
    put(r, "docs/rule.md", f"{LINK}\n")
    check("an allow path written ./path is read as path", pages.check_links(r) == [], pages.check_links(r))
    r = build('[guards.pages.allow]\n"docs/rule.md" = ""\n')
    put(r, "docs/rule.md", f"{LINK}\n")
    got = pages.check_links(r)
    check("an allow row with no reason is a problem", len(got) == 1 and "give its reason" in got[0], got)
    r = build(ok)
    got = pages.check_links(r)
    check("an allow row whose file is gone is a problem", len(got) == 1 and "is gone" in got[0], got)
    put(r, "docs/rule.md", "no link any more\n")
    got = pages.check_links(r)
    check("an allow row whose file holds no link now is a problem (a stale row hides nothing)",
          len(got) == 1 and "holds no such link" in got[0], got)
    if HAS_GIT:
        r = build('[guards.pages.allow]\n"notes/local.md" = "a note"\n')
        put(r, "notes/local.md", f"{LINK}\n")
        got = pages.check_links(r)
        check("an allow row for a file that does not ship is a problem", len(got) == 1 and "does not ship" in got[0], got)
    r = build('[guards.pages]\nhosts = ["example.test/page"]\n')
    put(r, "README.md", "see https://example.test/page/abc\n")
    check("a host the harness adds", len(pages.check_links(r)) == 1)
    r = build()
    put(r, "README.md", "see https://example.test/page/abc\n")
    check("…is no host until it is added", pages.check_links(r) == [])
    r = build('[guards.pages]\nhosts = ["example.test/page"]\n')
    put(r, "README.md", f"{LINK}\n")
    check("an added host leaves the default hosts in force", len(pages.check_links(r)) == 1)
    for bad in ('hosts = 5', 'hosts = ["a"]', 'hosts = ["abc"]', 'hosts = ["a.b"]', 'hosts = ["example"]', 'hosts = [1]',
                'allow = ["README.md"]', 'allow = "README.md"', 'allow = {"README.md" = {reason = "x", max = true}}'):
        r = build(f"[guards.pages]\n{bad}\n")
        got = pages.check_links(r)
        want = "a table" if bad.startswith("allow = [") or bad.startswith('allow = "') else "[guards.pages]"
        check(f"a bad config ({bad}) is a problem, not a crash or a silent pass",
              len(got) >= 1 and want in got[0], got)


def test_suite() -> None:
    print("\n[3] the day-one suite")
    r = build()
    res = suites.page_links(r)
    check("suites.page_links: the rule's self-test and the harness's check, both clean",
          [p for _, p in res] == [[], []], res)
    put(r, "SKILL.md", f"{LINK}\n")
    res = suites.page_links(r)
    check("…and the harness's check fails on a shipped link", res[0][1] == [] and len(res[1][1]) == 1, res)


if __name__ == "__main__":
    test_rule()
    test_harness()
    test_config()
    test_suite()
    raise SystemExit(finish())
