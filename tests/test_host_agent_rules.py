"""What the host agent may do on Zylos, and what a refusal means (issue #370), held to the two files that say it.

`hosts/zylos/README.md` has the section, and it names the refusal, the console inbox as the gate and the
pseudo-terminal as the thing never done; `templates/install-checklist.md` says in its Rules line that a refusal is
a stop. Each check is first tried on a copy with the words taken out, so it cannot pass by looking at nothing.
"""

from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import _t  # noqa: E402

SECTION = "## What the host agent may do, and what a refusal means"
README_WORDS = ("confirm_needs_human", "console inbox", "pseudo-terminal", "A refusal is a stop")
CHECKLIST_WORDS = ("a refusal", "is a stop", "pseudo-terminal")


def read(rel: str) -> str:
    with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
        return fh.read()


def section_of(text: str) -> str:
    """The section's body, up to the next `## ` heading; "" when there is none."""
    if SECTION not in text:
        return ""
    body = text.split(SECTION, 1)[1]
    return body.split("\n## ", 1)[0]


def problems(readme: str, checklist: str) -> list[str]:
    out = []
    body = section_of(readme)
    if not body:
        return [f"hosts/zylos/README.md has no section {SECTION!r}"]
    out += [f"the section does not say {w!r}" for w in README_WORDS if w not in body]
    rules = next((ln for ln in checklist.splitlines() if ln.startswith("Rules:")), "")
    out += [f"templates/install-checklist.md Rules line does not say {w!r}" for w in CHECKLIST_WORDS if w not in rules]
    return out


def test_the_check_refuses_each_word_taken_out():
    readme, checklist = read("hosts/zylos/README.md"), read("templates/install-checklist.md")
    assert not problems(readme, checklist), problems(readme, checklist)
    assert problems(readme.replace(SECTION, "## Something else"), checklist)
    for w in README_WORDS:
        assert problems(readme.replace(w, "x" * len(w)), checklist), w
    for w in CHECKLIST_WORDS:
        assert problems(readme, checklist.replace(w, "x" * len(w))), w


def test_the_guidance_is_there():
    got = problems(read("hosts/zylos/README.md"), read("templates/install-checklist.md"))
    assert got == [], got


if __name__ == "__main__":
    _t.main(globals())
