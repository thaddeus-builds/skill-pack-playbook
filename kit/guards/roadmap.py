"""ROADMAP.md keeps the one roadmap format, so a session on any machine starts
from the file and can search it for what waits on the owner.

The file (templates/ROADMAP.md is the starting point):

    # <Project> roadmap
    Updated: YYYY-MM-DD
    ## Now / ## Waiting on owner / ## Next / ## Done / ## Parked / ## Decisions / ## Links

`problems(text)` returns every break of these rules:

  1. the first line is the `# ` title, the second `Updated: YYYY-MM-DD` (a
     real day); then exactly those seven `## ` sections, in that order (other
     lines, a comment or a paragraph, are allowed and not read);
  2. every `- ` item outside Links is `- [ID] YYYY-MM-DD text`: the ID's
     letter names its section (N now, W waiting, X next, D done, P parked,
     R decisions), the ID is unique in the file (never reused: git keeps
     what the file drops), the date a real day not after `Updated`;
  3. Now holds at most one item: one turn per session;
  4. a Waiting row ends `unblocks: <ID>[, <ID>]`, naming rows of the file;
  5. a Done row ends in a reference in parentheses, `(commit abc1234)`,
     `(MR !12)`, `(no ref)`;
  6. a Decisions row quotes the owner's words in double quotes;
  7. a Links item is `name: where`, with no ID.

`check_file(path)` checks one file (a missing one is a problem);
`check_roadmap(root)` checks a skill pack's: skill-pack.toml `[guards.roadmap]
file`, else whichever of `docs/ROADMAP.md` and `ROADMAP.md` exists (both is
a problem: one home). `self_test()` plants each break and returns the rules
that missed theirs.

Paid for: the video-ads skill pack has kept its roadmap in this format, held
by its own test, since 2026-10-01, and a second skill pack adopted it; before,
one roadmap was prose in its own layout, another a memory note that did not
travel to the next machine, and neither could be searched for what waited
on the owner.

Test: kit/tests/test_roadmap.py.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from kit.guards import skill_pack, section

SECTIONS = ("Now", "Waiting on owner", "Next", "Done", "Parked", "Decisions", "Links")
LETTER = {"Now": "N", "Waiting on owner": "W", "Next": "X", "Done": "D",
          "Parked": "P", "Decisions": "R"}
ROW = re.compile(r"^\[([A-Z])(\d+)\]\s+(\d{4}-\d{2}-\d{2})\s+(\S.*)$", re.S)
UPDATED = re.compile(r"Updated:\s*(\d{4}-\d{2}-\d{2})")
LINK = re.compile(r"^[^:\[\]]+:\s*\S")
REFERENCE = re.compile(r"\([^()]+\)\s*$")
QUOTE = re.compile(r'"[^"]{3,}"')
UNBLOCKS = re.compile(r"unblocks:\s*([A-Z]\d+(?:\s*,\s*[A-Z]\d+)*)\s*$")
PLACES = ("docs/ROADMAP.md", "ROADMAP.md")


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def sections(text: str) -> dict[str, list[str]]:
    """{section: its `- ` items, the marker stripped}, in file order."""
    out: dict[str, list[str]] = {}
    name = None
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            out[name] = []
        elif name is not None and line.startswith("- "):
            out[name].append(line[2:].strip())
    return out


def problems(text: str) -> list[str]:
    """Every break of the format in `text`; [] when it holds."""
    text = text.lstrip("﻿").replace("\r\n", "\n")
    lines = [x for x in text.split("\n") if x.strip()]
    p: list[str] = []
    if not lines or not lines[0].startswith("# "):
        p.append("the first line must be the title, `# <Project> roadmap`")
    m = UPDATED.fullmatch(lines[1].strip()) if len(lines) > 1 else None
    updated = _day(m.group(1)) if m else None
    if updated is None:
        return p + ["the second line must be `Updated: YYYY-MM-DD`, a real day"]
    heads = tuple(x[3:].strip() for x in lines if x.startswith("## "))
    if heads != SECTIONS:
        return p + [f"the sections must be exactly, in order: "
                    f"{', '.join(SECTIONS)}; found: {', '.join(heads) or 'none'}"]
    found = sections(text)
    rows: dict[str, tuple[str, str]] = {}            # id -> (section, text)
    for name in SECTIONS:
        for it in found[name]:
            if name == "Links":
                if not LINK.match(it):
                    p.append(f"Links: `{it[:50]}` is not `name: where`")
                continue
            m = ROW.match(it)
            if not m:
                p.append(f"{name}: `{it[:50]}` is not `[ID] YYYY-MM-DD text`")
                continue
            letter, num, day, rest = m.groups()
            rid = letter + num
            if letter != LETTER[name]:
                p.append(f"[{rid}] is in {name}, whose ids start with {LETTER[name]}")
            if rid in rows:
                p.append(f"[{rid}] is used twice")
            rows[rid] = (name, rest)
            d = _day(day)
            if d is None:
                p.append(f"[{rid}]: {day} is not a real day")
            elif d > updated:
                p.append(f"[{rid}] is dated {day}, after Updated {updated}")
            if name == "Done" and not REFERENCE.search(rest):
                p.append(f"[{rid}]: a Done row ends in a reference in parentheses, "
                         f"`(commit abc1234)` or `(no ref)`")
            if name == "Decisions" and not QUOTE.search(rest):
                p.append(f"[{rid}]: a Decisions row quotes the owner's words in double quotes")
    if len(found["Now"]) > 1:
        p.append("Now holds more than one item: one turn per session")
    for rid, (name, rest) in rows.items():
        if name != "Waiting on owner":
            continue
        m = UNBLOCKS.search(rest)
        if not m:
            p.append(f"[{rid}]: a Waiting row ends `unblocks: <ID>[, <ID>]`")
            continue
        p += [f"[{rid}] unblocks {t}, which is not a row of this file"
              for t in re.split(r"\s*,\s*", m.group(1)) if t not in rows]
    return p


def check_file(path: Path | str, name: str | None = None) -> list[str]:
    """problems() of one file, each prefixed with `name` (default: the
    file's name)."""
    path = Path(path)
    name = name or path.name
    if not path.is_file():
        return [f"{name} does not exist: the project keeps its state in one "
                f"roadmap (templates/ROADMAP.md)"]
    return [f"{name}: {x}" for x in problems(path.read_text(encoding="utf-8", errors="replace"))]


def where(root: Path | str | None = None) -> tuple[Path, str, list[str]]:
    """The skill pack's roadmap as (path, its name under the root, problems):
    `[guards.roadmap] file`, else the one of PLACES that exists (the first
    when neither does); two of them is a problem."""
    cfg = skill_pack(root)
    base = Path(root) if root is not None else cfg.root
    rel = section(cfg, "guards", "roadmap").get("file")
    if rel:
        return base / str(rel), str(rel), []
    have = [r for r in PLACES if (base / r).is_file()]
    rel = have[0] if have else PLACES[0]
    if len(have) > 1:
        return base / rel, rel, [f"two roadmaps, {' and '.join(have)}: keep one "
                                 f"(or name it in [guards.roadmap] file)"]
    return base / rel, rel, []


def check_roadmap(root: Path | str | None = None) -> list[str]:
    path, rel, p = where(root)
    return p + check_file(path, rel)


SOUND = """# Demo roadmap
Updated: 2026-10-01
<!-- a comment is not read -->
## Now
- [N1] 2026-10-01 write the first-run example
## Waiting on owner
- [W1] 2026-09-30 confirm the rule list. unblocks: X1, N1
## Next
- [X1] 2026-10-01 doctor as the first call
## Done
- [D1] 2026-09-30 merged the tracking layer (commit abc1234)
## Parked
- [P1] 2026-09-30 no budget rules
## Decisions
- [R1] 2026-09-30 "skip the portfolio management" (chat)
## Links
- repository: the demo repository
"""

# a break -> (the planted text, a word its problem must hold)
PLANTED = {
    "no title": (SOUND.replace("# Demo roadmap", "Demo roadmap"), "title"),
    "no Updated": (SOUND.replace("Updated: 2026-10-01\n", ""), "Updated"),
    "an unreal Updated": (SOUND.replace("Updated: 2026-10-01", "Updated: 2026-13-01"), "Updated"),
    "a section missing": (SOUND.replace("## Parked\n- [P1] 2026-09-30 no budget rules\n", ""), "sections"),
    "sections out of order": (SOUND.replace("## Done", "## Zed").replace("## Parked", "## Done")
                              .replace("## Zed", "## Parked"), "sections"),
    "a section renamed": (SOUND.replace("## Next", "## Soon"), "sections"),
    "two Now items": (SOUND.replace("## Waiting", "- [N2] 2026-10-01 another\n## Waiting"), "one turn"),
    "a row with no date": (SOUND.replace("[X1] 2026-10-01", "[X1]"), "is not `[ID]"),
    "a row with no id": (SOUND.replace("- [X1] 2026-10-01", "- 2026-10-01"), "is not `[ID]"),
    "an unreal date": (SOUND.replace("[X1] 2026-10-01", "[X1] 2026-02-30"), "not a real day"),
    "a date after Updated": (SOUND.replace("[X1] 2026-10-01", "[X1] 2026-10-02"), "after Updated"),
    "a wrong letter": (SOUND.replace("[X1] 2026-10-01 doctor", "[D9] 2026-10-01 doctor"), "whose ids start"),
    "a duplicate id": (SOUND.replace("[P1] 2026-09-30", "[D1] 2026-09-30"), "used twice"),
    "a waiting row with no unblocks": (SOUND.replace(" unblocks: X1, N1", ""), "unblocks:"),
    "an unblocks that is no row": (SOUND.replace("X1, N1", "X1, X9"), "not a row"),
    "an unblocks with no id": (SOUND.replace("unblocks: X1, N1", "unblocks: —"), "unblocks:"),
    "a done row with no reference": (SOUND.replace(" (commit abc1234)", ""), "reference"),
    "a decision with no quotation": (SOUND.replace('"skip the portfolio management"',
                                                   "skip the portfolio management"), "quotes"),
    "a link with no where": (SOUND.replace("repository: the demo repository", "repository"), "name: where"),
}


def self_test() -> list[str]:
    """[] when the sound roadmap passes and every planted break is caught."""
    out = [f"a sound roadmap is refused: {problems(SOUND)}"] if problems(SOUND) else []
    for what, (text, needle) in PLANTED.items():
        got = problems(text)
        if text == SOUND or not any(needle in x for x in got):
            out.append(f"the roadmap rule misses: {what} (got {got})")
    return out
