#!/usr/bin/env python3
"""kit.guards.pages: a page the harness delivers is drawn by the harness, so no shipped file links to a hosted artifact.
On SYNTHETIC files only (neutral names, a made-up artifact id).

  [0] the rule on its planted forms: a markdown link, a bare host, a code-session link, a public share, capitals,
      JSON-escaped and percent-encoded slashes; the sound text and look-alike hosts are no hit
  [1] a harness on disk (git): a link in a shipped skill, readme, script, page or template is reported by path and line
      and never by the link; the same link in an export-ignore (internal) file, in the vendored kit or in the console is
      not; a harness with no git is read whole; a file type that is not text is not read
  [2] [guards.pages]: allow (with its reason, passing; no reason, a path that is gone, a file that holds no link now,
      a file that does not ship: each a problem), hosts (a host the harness adds)
  [3] the day-one suite runs the rule (suites.page_links)
"""

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
LINK = "https://claude.ai/artifact/DEMO-abc123"
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
    write(root, "README.md", "# Readme\nDocs: https://claude.ai/docs/overview\n")
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
    for text in ("https://claude.ai/docs", "claude.ai/new", "an artifact is a build output", "see artifact/abc at example.test"):
        check(f"no hit: {text!r}", pages.hits(text) == [], text)
    check("a path that only begins with a host is a hit (a false hit over a miss)", pages.hits("claude.ai/artifacts-x") == [1])
    check("two hits on two lines", pages.hits(f"{LINK}\nx\n{LINK}") == [1, 3])


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
                             ("ssot/links.tsv", f"a\t{LINK}\n", "ssot/links.tsv:1")):
        r = build()
        put(r, rel, text)
        got = pages.check_links(r)
        check(f"a link in {rel} is reported by path and line", len(got) == 1 and got[0].startswith(where + ":"), got)
        check(f"…never by the link itself", all("DEMO-abc123" not in g and "claude.ai/artifact" not in g for g in got), got)
    if HAS_GIT:
        r = build()
        put(r, "notes/local.md", f"scratch {LINK}\n")
        put(r, "CLAUDE.md", f"internal {LINK}\n")
        check("a link in an export-ignore (internal) file is fine: it never ships", pages.check_links(r) == [],
              pages.check_links(r))
        r = build()
        put(r, "scripts/kit/guards/pages.py", f"HOSTS = ('claude.ai/artifact', '{LINK}')\n")
        put(r, "console/README.md", f"{LINK}\n")
        check("the vendored kit and the console are not read", pages.check_links(r) == [], pages.check_links(r))
        r = build()
        put(r, "scripts/other/README.md", f"{LINK}\n")
        check("…but another folder under scripts/ is", len(pages.check_links(r)) == 1)
        r = build()
        put(r, "logo.png", f"{LINK}\n")
        check("a file that is not text is not read", pages.check_links(r) == [])
    else:
        check("skipped: the export-ignore cases (no git)", True)
    r = build(repo=False)
    write(r, "notes/local.md", f"scratch {LINK}\n")
    check("with no repository the whole tree is read (never a silent pass)", len(pages.check_links(r)) == 1
          and pages.check_links(r)[0].startswith("notes/local.md:1:"), pages.check_links(r))
    write(r, "notes/local.md", "scratch\n")
    write(r, "scripts/kit/x.md", LINK)
    write(r, ".git-not/x", "x")
    check("…less the vendored kit", pages.check_links(r) == [], pages.check_links(r))


def test_config() -> None:
    print("\n[2] [guards.pages]")
    ok = '[guards.pages.allow]\n"docs/rule.md" = "the page that names the rule"\n'
    r = build(ok)
    put(r, "docs/rule.md", f"The rule bans links like {LINK}\n")
    check("an allowed file with its reason passes", pages.check_links(r) == [], pages.check_links(r))
    put(r, "docs/other.md", f"{LINK}\n")
    check("…and only that file", len(pages.check_links(r)) == 1 and pages.check_links(r)[0].startswith("docs/other.md:1:"))
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
