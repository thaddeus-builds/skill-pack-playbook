"""templates/prior-art-scan.md, "A name or a link from the owner" and "Do you need a deep-research tool?", held to what they promise.

Checked, each on a broken copy first, so a check cannot pass by looking at nothing:

  - the quick scan keeps its six steps (what is kept first, facts before words, three searches, one verdict and a
    spike list, written down that turn, the owner asked after) and its budget;
  - the deep-research section keeps its default, the spot-check rule and the three sources the method comes from;
  - docs/lessons.md points at both sections from "Research is kept, not repeated" and says where it was seen.
"""

from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
import _t  # noqa: E402,F401
from test_docs_build import doc, section  # noqa: E402

TEMPLATE = "templates/prior-art-scan.md"
QUICK = "A name or a link from the owner (a quick scan)"
DEEP = "Do you need a deep-research tool?"
LESSON = "Research is kept, not repeated (from the video-ads skill pack, 2026-10-22)"
QUICK_WORDS = ("about 30 tool calls", "**Read what is kept first.**", "**Facts before words, per project.**",
               "three searches at most", "**One verdict per project**", "**spike list**",
               "**Write it down in the same turn,**", "**Ask the owner after, not before:**")
DEEP_WORDS = ("Default no.", "lead list", "fetch the three heaviest claims", "Gemini Deep Research",
              "How we built our multi-agent research system", "Code research projects with async coding agents",
              "the \"LLM Wiki\" idea file")
POINTERS = ("](../templates/prior-art-scan.md#a-name-or-a-link-from-the-owner-a-quick-scan)",
            "](../templates/prior-art-scan.md#do-you-need-a-deep-research-tool)", "*Seen once* (2026-10-26), in the video-ads")


def problems(text: str, heading: str, words: tuple[str, ...]) -> list[str]:
    body = section(text, heading)
    if not body.strip():
        return [f"## {heading}"]
    return [w for w in words if w not in body]


def lesson_problems(lessons: str) -> list[str]:
    body = section(lessons, LESSON)
    return [w for w in POINTERS if w not in body]


def test_the_quick_scan_keeps_its_steps():
    text = doc(TEMPLATE)
    assert problems(text, QUICK, QUICK_WORDS) == [], problems(text, QUICK, QUICK_WORDS)
    for w in QUICK_WORDS:
        assert problems(text.replace(w, "x"), QUICK, QUICK_WORDS) == [w], w
    assert problems(text.replace(f"## {QUICK}", "## x"), QUICK, QUICK_WORDS) == [f"## {QUICK}"]


def test_the_deep_research_section_keeps_its_default_and_sources():
    text = doc(TEMPLATE)
    assert problems(text, DEEP, DEEP_WORDS) == [], problems(text, DEEP, DEEP_WORDS)
    for w in DEEP_WORDS:
        assert problems(text.replace(w, "x"), DEEP, DEEP_WORDS) == [w], w
    assert problems(text.replace(f"## {DEEP}", "## x"), DEEP, DEEP_WORDS) == [f"## {DEEP}"]


def test_the_lesson_points_at_both_sections():
    lessons = doc("docs/lessons.md")
    assert lesson_problems(lessons) == [], lesson_problems(lessons)
    for w in POINTERS:
        assert lesson_problems(lessons.replace(w, "x")) == [w], w


if __name__ == "__main__":
    _t.main(globals())
