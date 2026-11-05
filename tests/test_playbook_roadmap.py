"""The playbook's own ROADMAP.md keeps the one roadmap format every skill pack's does
(kit.guards.roadmap; templates/ROADMAP.md), so a session on any machine starts from
it. Each check is first tried on a break planted in this very file, so it cannot pass
by reading nothing."""

from __future__ import annotations

import os
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import _t  # noqa: E402
from kit.guards import roadmap  # noqa: E402

PATH = os.path.join(ROOT, "ROADMAP.md")
TEXT = open(PATH, encoding="utf-8").read()


def test_the_check_refuses_this_roadmap_broken():
    wait = re.search(r"unblocks: [A-Z]\d+", TEXT).group(0)        # whichever row the first wait unblocks today
    for old, new in (("## Next\n", "## Soon\n"),                 # a section renamed
                     (wait, "unblocks: X99"),                     # a wait that unblocks no row
                     (" (no ref)", ""),                   # a Done row with no reference
                     ('"yes, after turn 2"', "yes, after turn 2")):   # a decision not quoted
        broken = TEXT.replace(old, new, 1)
        assert broken != TEXT and roadmap.problems(broken), old


def test_the_playbook_roadmap_keeps_the_format():
    assert roadmap.check_file(PATH) == [], roadmap.check_file(PATH)


def test_no_decision_on_the_default_branch_was_edited():
    # R44: the R rows are the one record of the owner's decisions (rule 10 of kit.guards.roadmap)
    assert roadmap.decisions_kept(ROOT, "ROADMAP.md") == [], roadmap.decisions_kept(ROOT, "ROADMAP.md")


if __name__ == "__main__":
    _t.main(globals())
