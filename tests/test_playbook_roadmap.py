"""The playbook's own ROADMAP.md keeps the one roadmap format every harness's does
(kit.guards.roadmap; templates/ROADMAP.md), so a session on any machine starts from
it. Each check is first tried on a break planted in this very file, so it cannot pass
by reading nothing."""

from __future__ import annotations

import datetime
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


REVIEW_ON = re.compile(r"Review on (\d{4}-\d{2}-\d{2})")


def overdue(text: str, today: datetime.date) -> list[str]:
    """Parked rows whose `Review on DAY` has passed: the code they name has no importer
    and the day to revive it, delete it, or move the day (with the owner's words) is here."""
    rows = roadmap.sections(text).get("Parked", [])
    return [row.split(" ", 2)[0] for row in rows
            if (m := REVIEW_ON.search(row)) and datetime.date.fromisoformat(m.group(1)) < today]


def test_parked_code_is_revived_deleted_or_re_decided_by_its_day():
    parked = roadmap.sections(TEXT).get("Parked", [])
    assert any(REVIEW_ON.search(r) for r in parked), "no Parked row has a Review on day"
    late = overdue(TEXT, datetime.date.today())
    assert late == [], (f"{late}: the day has passed. Run python3 tools/consumers.py on the harness "
                        "checkouts; revive the code (docs/kit-and-tools.md), delete it, or move the day "
                        "with the owner's words quoted in Decisions")


def test_the_overdue_check_sees_a_day_that_has_passed():
    on_the_day, after = datetime.date(2027, 1, 13), datetime.date(2027, 1, 14)
    assert overdue(TEXT, on_the_day) == [] and overdue(TEXT, after), overdue(TEXT, after)


def test_the_check_refuses_this_roadmap_broken():
    for old, new in (("## Next\n", "## Soon\n"),                 # a section renamed
                     ("unblocks: X1", "unblocks: X99"),           # a wait that unblocks no row
                     (" (commit 8e13e16)", ""),                   # a Done row with no reference
                     ('"yes, after turn 2"', "yes, after turn 2")):   # a decision not quoted
        broken = TEXT.replace(old, new, 1)
        assert broken != TEXT and roadmap.problems(broken), old


def test_the_playbook_roadmap_keeps_the_format():
    assert roadmap.check_file(PATH) == [], roadmap.check_file(PATH)


if __name__ == "__main__":
    _t.main(globals())
