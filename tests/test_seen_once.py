"""tools/seen_once.py: a seen-once issue is due 90 days after its last activity and not a day before; an issue without the
label, or one touched again (a second sighting moves updatedAt), is never due; the list is read from gh's JSON, no network."""
import json, os, subprocess, sys, tempfile
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t
import seen_once as s

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "seen_once.py")
ISSUES = [
    {"number": 3, "title": "old lesson", "updatedAt": "2026-08-01T10:00:00Z", "labels": [{"name": "seen-once"}]},
    {"number": 4, "title": "exactly ninety days", "updatedAt": "2026-08-05T23:00:00Z", "labels": [{"name": "seen-once"}, {"name": "kit"}]},
    {"number": 5, "title": "eighty-nine days", "updatedAt": "2026-08-06T00:00:00Z", "labels": [{"name": "seen-once"}]},
    {"number": 6, "title": "old but a second pack saw it (label off)", "updatedAt": "2026-07-01T00:00:00Z", "labels": [{"name": "kit"}]},
]
TODAY = date(2026, 11, 3)


def test_due_after_ninety_days_and_not_before():
    assert [i["number"] for i in s.due(ISSUES, TODAY)] == [3, 4]


def test_a_second_sighting_keeps_it_open():
    touched = [dict(ISSUES[0], updatedAt="2026-10-30T09:00:00Z")]
    assert s.due(touched, TODAY) == []


def test_the_list_reads_gh_json_and_names_the_last_day():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(ISSUES, f)
    try:
        r = subprocess.run([sys.executable, TOOL, "list", "--from", f.name, "--today", "2026-11-03"], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(f.name)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["#3\t2026-08-01\told lesson", "#4\t2026-08-05\texactly ninety days"] and "2 due" in r.stderr


if __name__ == "__main__":
    _t.main(globals())
