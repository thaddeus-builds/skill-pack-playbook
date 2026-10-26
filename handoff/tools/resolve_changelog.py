"""Resolve a CHANGELOG.md conflict where both sides added lines under the same heading:
keep the newer side's lines (theirs, the commit being replayed) above the older side's (ours),
so the newest change stays first. Exits 1 if the conflict is not of that shape."""
import re
import sys
from pathlib import Path

p = Path("CHANGELOG.md")
s = p.read_text()
m = re.search(r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n", s, re.S)
if not m:
    print("no conflict block", file=sys.stderr)
    sys.exit(1)
ours, theirs = m.group(1), m.group(2)
if not all(l.startswith("- ") for l in (ours + theirs).splitlines() if l.strip()):
    print("conflict is not two sets of list lines:", repr(ours[:80]), repr(theirs[:80]), file=sys.stderr)
    sys.exit(1)
s = s[:m.start()] + theirs + ours + s[m.end():]
assert "<<<<<<<" not in s and ">>>>>>>" not in s
p.write_text(s)
print("resolved: kept", len(theirs.splitlines()), "+", len(ours.splitlines()), "lines")
