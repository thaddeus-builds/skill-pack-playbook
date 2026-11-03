#!/usr/bin/env python3
"""Close the lessons nobody saw twice (X40, the owner's C10 of docs/design/consolidation-2026-11.md, R29): an open issue
labelled `seen-once` with no activity for 90 days is closed as not planned, with a comment naming this rule. A second
sighting is a comment or an edit (it moves `updatedAt`), or the label taken off once a second pack has paid for it
(then it is the playbook's work and this tool never sees it).

    python3 tools/seen_once.py list [--from FILE] [--today YYYY-MM-DD]    the issues due, one per line (exit 0)
    python3 tools/seen_once.py close [--from FILE] [--today YYYY-MM-DD]   close each one due (gh issue close, with the comment)

`--from FILE` reads the JSON `gh issue list --label seen-once --state open --json number,title,updatedAt,labels` prints;
without it the tool runs that command. Needs `gh` only without `--from` and for `close`. Test: tests/test_seen_once.py.
"""
import argparse, json, subprocess, sys
from datetime import date, datetime

LABEL = "seen-once"
DAYS = 90
FIELDS = "number,title,updatedAt,labels"
COMMENT = ("Closed by the playbook's rule for lessons seen once (docs/maintaining.md, the loop): {days} days with no second sighting "
           "since {last}. Reopen it, or file a new issue, the day a second skill pack meets the same thing.")


def due(issues, today: date, days: int = DAYS):
    """The issues still labelled seen-once whose last activity is at least `days` days before `today`, oldest first."""
    out = []
    for i in issues:
        names = {(l.get("name") if isinstance(l, dict) else l) for l in i.get("labels", [])}
        last = datetime.fromisoformat(i["updatedAt"].replace("Z", "+00:00")).date()
        if LABEL in names and (today - last).days >= days:
            out.append({**i, "last": last.isoformat()})
    return sorted(out, key=lambda i: (i["last"], i["number"]))


def load(path):
    if path:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    r = subprocess.run(["gh", "issue", "list", "--label", LABEL, "--state", "open", "--limit", "500", "--json", FIELDS],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"gh issue list: {r.stderr.strip()}")
    return json.loads(r.stdout)


def main(argv=None):
    ap = argparse.ArgumentParser(description="List or close the seen-once issues with no second sighting in 90 days.")
    ap.add_argument("what", choices=("list", "close"))
    ap.add_argument("--from", dest="src", help="the JSON of gh issue list (default: run it)")
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args(argv)
    found = due(load(a.src), date.fromisoformat(a.today))
    for i in found:
        print(f"#{i['number']}\t{i['last']}\t{i['title']}")
        if a.what == "close":
            r = subprocess.run(["gh", "issue", "close", str(i["number"]), "--reason", "not planned",
                                "--comment", COMMENT.format(days=DAYS, last=i["last"])], capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(f"gh issue close {i['number']}: {r.stderr.strip()}")
    print(f"{len(found)} due", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
