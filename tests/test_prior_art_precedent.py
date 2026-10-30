"""templates/prior-art-scan.md, "A design question from the owner (a precedent scan)", held to what it promises.

Checked, each on a broken copy first, so a check cannot pass by looking at nothing:

  - the section keeps its six steps (the index first, in the pack and its siblings; four lenses, four searches at most; three things per
    source, what does not transfer included; one verdict that names what it changes; what could not be read; written down that turn) and
    its seen-once;
  - "When to scan" lists the owner's design question as a trigger, and the quick scan reads the siblings' indexes too.
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
PRECEDENT = "A design question from the owner (a precedent scan)"
QUICK = "A name or a link from the owner (a quick scan)"
WORDS = ("four searches in one turn", "**Read what is kept first, in this pack and its siblings:**", "`python3 tools/research.py`",
         "four at most", "**Per source, write three things:**", "what does not transfer and why", "**[ours]**",
         "**One verdict, and what it changes:**", "**[inference]**", "**Say what could not be read:**",
         "**Write it down in the same turn,**", "docs/research/", "*Seen once, in the adcut skill pack (2026-10-30):*")
TRIGGER = "The owner asks how others design something"


def problems(text: str, heading: str, words: tuple[str, ...]) -> list[str]:
    body = section(text, heading)
    if not body.strip():
        return [f"## {heading}"]
    return [w for w in words if w not in body]


def test_the_precedent_scan_keeps_its_steps():
    text = doc(TEMPLATE)
    assert problems(text, PRECEDENT, WORDS) == [], problems(text, PRECEDENT, WORDS)
    for w in WORDS:
        assert problems(text.replace(w, "x"), PRECEDENT, WORDS) == [w], w
    assert problems(text.replace(f"## {PRECEDENT}", "## x"), PRECEDENT, WORDS) == [f"## {PRECEDENT}"]


def test_the_owners_design_question_is_a_trigger_and_the_quick_scan_reads_the_siblings():
    text = doc(TEMPLATE)
    assert TRIGGER in section(text, "When to scan"), "the trigger row"
    assert TRIGGER not in section(text.replace(TRIGGER, "x"), "When to scan")
    assert "tools/research.py" in section(text, QUICK)
    assert "tools/research.py" not in section(text.replace("`python3 tools/research.py` over the sibling skill packs (the same", "x (the same"), QUICK)


if __name__ == "__main__":
    _t.main(globals())
