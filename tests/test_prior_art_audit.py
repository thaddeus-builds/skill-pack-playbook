"""templates/prior-art-scan.md, "Auditing a skill pack that already exists", held to what it promises.

Checked, each on a broken copy first, so a check cannot pass by looking at nothing:

  - the template keeps the section, the four verdicts, the sources registry's columns, the front page's parts, the
    coverage test, the spot-check of the heaviest claims and its pointer back at docs/lessons.md. The lesson's own
    wording is not pinned (tests/test_docs_build.py: a lesson is short and says where it was seen; its links resolve).
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
HEADING = "Auditing a skill pack that already exists"
WORDS = ("`adopt`", "`borrow-idea`", "`keep-own`", "`watch`", "docs/prior-art/sources.tsv",
         "id, url, kind, title, author_or_org, published_or_version, accessed, pinned, licence, claim_tag, used_for, note",
         "**Borrow** (at most 12", "**Not surveyed**", "**Could not verify**", "A test holds the coverage",
         "fetch the three heaviest claims yourself", "](../docs/lessons.md)")


def template_problems(text: str) -> list[str]:
    body = section(text, HEADING)
    if not body.strip():
        return [f"## {HEADING}"]
    return [w for w in WORDS if w not in body]



def test_the_template_keeps_the_audit_section():
    text = doc(TEMPLATE)
    assert template_problems(text) == [], template_problems(text)
    for w in WORDS:
        assert template_problems(text.replace(w, "x")) == [w], w
    assert template_problems(text.replace(f"## {HEADING}", "## x")) == [f"## {HEADING}"]



if __name__ == "__main__":
    _t.main(globals())
