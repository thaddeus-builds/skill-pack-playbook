"""A page the harness delivers is drawn by the harness: no shipped file hands a person a link to a hosted artifact.

A harness hands people pages, samples and demos (an owner's review page, a client's draft, a design demo). The rule
(docs/rules.md, "A page the harness delivers is drawn by the harness"): each one comes from one of the harness's own
verbs, from the data it holds or a synthetic fixture, so the cloud agent that installs the harness from git can
draw it again and it cannot drift from the code. A link to a page someone published from a chat session is a
convenience for looking at something locally while debugging; it is never the deliverable.

`check_links(root)` reads what the release ships (`git archive`, as kit.guards.release asks git: tracked files, less
the export-ignore ones; a harness with no git or no repository is read whole, never skipped) and returns a problem for
every hosted-artifact link in a text file: its path and line, never the link. A link in a file that does not ship (a
planning file, a local note in `[release].internal`) is fine: it never reaches the installed harness. The vendored kit
(`<scripts_dir>/kit/`) and console (`console/`) are the playbook's own bytes, held by the drift guard, and are not read;
nor is `harness.toml`, which names the hosts it adds.

`[guards.pages]` in harness.toml:

  hosts   more hosts or paths to treat as hosted artifacts, beside HOSTS (a plain text, matched without case, with
          `/` also read as `\\/` and `%2f`)
  allow   {path: reason}: a shipped file that may hold such a link, with why (a document that names the rule, say). A
          row with no reason, a path that is gone, or one that holds no link now is a problem (a stale row hides
          nothing)

The rule prefers a false hit, which an `allow` row answers, to a miss (docs/lessons.md, "A guard's refinement never
costs the recall it had"): any text that spells a host is a hit, in code, a string, a comment or prose. A link split
across two lines or built from parts is not read; the review reads those.

`self_test()` plants each form and returns the ones the check missed.

Test: kit/tests/test_page_links.py.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from kit.guards import TEXT_EXT, harness, read, section, strs
from kit.guards import release as _release

HOSTS = ("claude.ai/artifact", "claude.ai/code/artifact", "claude.ai/public/artifacts")
EXT = TEXT_EXT + (".svg", ".xml", ".csv", ".rst")


def _pattern(hosts) -> re.Pattern:
    def one(h: str) -> str:
        return r"(?:/|\\/|%2f)".join(re.escape(p) for p in re.split(r"/", h.strip().lower()))
    parts = [one(h) for h in hosts if h.strip()]
    return re.compile("|".join(parts), re.I) if parts else re.compile(r"(?!x)x")


def hits(text: str, hosts=HOSTS) -> list[int]:
    """The 1-based lines of `text` that hold a hosted-artifact link."""
    pat = _pattern(hosts)
    return [i for i, line in enumerate(text.splitlines(), 1) if pat.search(line)]


def settings(cfg) -> tuple[tuple[str, ...], dict]:
    g = section(cfg, "guards", "pages")
    allow = g.get("allow", {})
    return (*HOSTS, *strs(g.get("hosts"))), dict(allow) if isinstance(allow, dict) else {}


def files(root: Path, cfg) -> list[str]:
    """The text files a harness ships (all of them with no git), less the vendored kit and console."""
    got = _release.shipped(root)
    names = sorted(got[1]) if got is not None else sorted(
        str(p.relative_to(root)) for p in _tree(root))
    skip = (f"{cfg.scripts_dir}/kit", "console")
    return [f for f in names if f.endswith(EXT) and f != "harness.toml" and not _release.under(f, skip)
            and (root / f).is_file()]


def _tree(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in (".git", "node_modules", "__pycache__"))
        for f in sorted(filenames):
            yield Path(dirpath) / f


def check_links(root: Path | str | None = None) -> list[str]:
    """Every hosted-artifact link in a file the harness ships, outside the `allow` rows; [] when the rule holds."""
    cfg = harness(root)
    base = Path(root) if root is not None else cfg.root
    hosts, allow = settings(cfg)
    out: list[str] = []
    found: dict[str, list[int]] = {}
    for rel in files(base, cfg):
        lines = hits(read(base / rel), hosts)
        if lines:
            found[rel] = lines
    for rel, lines in found.items():
        if rel not in allow:
            out += [f"{rel}:{n}: a link to a hosted artifact ships; the page is drawn by a verb of this harness "
                    f"(allow it in [guards.pages].allow with its reason, or keep the link in a file that does not "
                    f"ship)" for n in lines]
    for rel, why in sorted(allow.items()):
        if not isinstance(why, str) or not why.strip():
            out.append(f"[guards.pages].allow {rel!r}: give its reason (why this shipped file may hold such a link)")
        elif not (base / rel).is_file():
            out.append(f"[guards.pages].allow {rel!r}: is gone: drop the row")
        elif rel not in found:
            out.append(f"[guards.pages].allow {rel!r}: holds no such link, or does not ship: drop the row")
    return out


# ---- the rule, each form on a plant ---------------------------------------------------------------------------

PLANTED = {
    "a markdown link": "See [the page](https://claude.ai/artifact/AbC123) for the draft.\n",
    "a bare host": "draft: claude.ai/artifact/AbC123\n",
    "a code-session link": "print('open https://claude.ai/code/artifact/0f1e2d3c-aaaa')\n",
    "a public share": "url = 'https://claude.ai/public/artifacts/abc'\n",
    "capitals": "HTTPS://CLAUDE.AI/ARTIFACT/ABC\n",
    "json-escaped slashes": '{"link": "https:\\/\\/claude.ai\\/artifact\\/abc"}\n',
    "percent-encoded": "redirect?to=https%3A%2F%2Fclaude.ai%2Fartifact%2Fabc\n",
    "on a later line": "# a page\n\nsome words\nthe sample: claude.ai/artifact/abc\n",
}
SOUND = ("The page is written by `space page` to the review folder.\n"
         "Read the docs at https://claude.ai/docs/overview.\n"
         "An artifact is a build output here; the cloud agent installs from git.\n")


def self_test() -> list[str]:
    """The forms the check missed, or "the sound text fails"; empty is sound."""
    missed = [what for what, text in PLANTED.items() if not hits(text)]
    if hits(SOUND):
        missed.append("the sound text fails")
    if hits("see example.test/page/abc", hosts=(*HOSTS, "example.test/page")) != [1]:
        missed.append("a host the harness adds")
    if hits("see example.test/page/abc"):
        missed.append("a host nobody added is no hit")
    return missed
