"""ROADMAP.md keeps the one roadmap format, so a session on any machine starts
from the file and can search it for what waits on the owner.

The file (templates/ROADMAP.md is the starting point):

    # <Project> roadmap
    Updated: YYYY-MM-DD
    ## Now / ## Waiting on owner / ## Next / (## Milestones) / ## Done / ## Parked / ## Decisions / ## Links

`problems(text)` returns every break of these rules:

  1. the first line is the `# ` title, the second `Updated: YYYY-MM-DD` (a
     real day); then exactly those seven `## ` sections, in that order, with
     an optional `## Milestones` right after Next (other lines, a comment or
     a paragraph, are allowed and not read);
  2. every `- ` item outside Links is `- [ID] YYYY-MM-DD text`: the ID's
     letter names its section (N now, W waiting, X next, D done, P parked,
     R decisions), the ID is unique in the file (never reused: git keeps
     what the file drops), the date a real day not after `Updated`;
  3. Now holds at most one item: one turn per session;
  4. a Waiting row ends `unblocks: <ID>[, <ID>]`, naming rows of the file;
  5. a Done row ends in a reference in parentheses, `(commit abc1234)`,
     `(MR !12)`, `(no ref)`;
  6. a Decisions row quotes the owner's words in double quotes;
  7. a Links item is `name: where`, with no ID;
  8. a Milestones row (letter M) is one integration unit: it ends
     `includes: <ID>[, <ID>]. closes when: <the proof>`, naming rows of the
     file (each in at most one milestone); at most three are open; one whose
     items are all Done is closed and moves to Done as a row of its own (the
     method: docs/operating.md, "Integrate by milestone").

  9. optional, for a roadmap that has grown: a line `Archive: <file>` before the
     first section names a file, next to the roadmap, that holds old Done and
     Parked rows: `# <Project> roadmap archive`, then `## Done` and/or
     `## Parked` with rows in the same form (D and P ids, a Done row ends in a
     reference, a date not after `Updated`). An id is used once across both
     files (never reused), a reference from the live file (`unblocks`,
     `includes`) resolves in either, and a named file that is missing or holds
     another section is a problem. Nothing else moves: Now, Waiting, Next,
     Milestones and Decisions stay in the live file.

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
WITH_MILESTONES = ("Now", "Waiting on owner", "Next", "Milestones", "Done", "Parked", "Decisions", "Links")
LETTER = {"Now": "N", "Waiting on owner": "W", "Next": "X", "Milestones": "M", "Done": "D",
          "Parked": "P", "Decisions": "R"}
MAX_OPEN_MILESTONES = 3
INCLUDES = re.compile(r"includes:\s*([A-Z]\d+(?:\s*,\s*[A-Z]\d+)*)")
CLOSES = re.compile(r"closes when:\s*\S")
ROW = re.compile(r"^\[([A-Z])(\d+)\]\s+(\d{4}-\d{2}-\d{2})\s+(\S.*)$", re.S)
UPDATED = re.compile(r"Updated:\s*(\d{4}-\d{2}-\d{2})")
LINK = re.compile(r"^[^:\[\]]+:\s*\S")
REFERENCE = re.compile(r"\([^()]+\)\s*$")
QUOTE = re.compile(r'"[^"]{3,}"')
UNBLOCKS = re.compile(r"unblocks:\s*([A-Z]\d+(?:\s*,\s*[A-Z]\d+)*)\s*$")
PLACES = ("docs/ROADMAP.md", "ROADMAP.md")
ARCHIVE = re.compile(r"^Archive:\s*(\S+)\s*$", re.M)
ARCHIVED = ("Done", "Parked")


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


def archive_name(text: str) -> str | None:
    """The file the roadmap names as its archive (`Archive: <file>` before the first section), else None."""
    head = text.lstrip("﻿").replace("\r\n", "\n").split("\n## ", 1)[0]
    m = ARCHIVE.search(head)
    return m.group(1) if m else None


def _row(name: str, it: str, updated: date, rows: dict, p: list[str], where: str = "") -> None:
    """One `- ` item of section `name` against the row rules; it joins `rows` (id -> (section, text))."""
    m = ROW.match(it)
    if not m:
        p.append(f"{where}{name}: `{it[:50]}` is not `[ID] YYYY-MM-DD text`")
        return
    letter, num, day, rest = m.groups()
    rid = letter + num
    if letter != LETTER[name]:
        p.append(f"{where}[{rid}] is in {name}, whose ids start with {LETTER[name]}")
    if rid in rows:
        p.append(f"{where}[{rid}] is used twice" + (" (in the roadmap and its archive)" if where else ""))
    rows[rid] = (name, rest)
    d = _day(day)
    if d is None:
        p.append(f"{where}[{rid}]: {day} is not a real day")
    elif d > updated:
        p.append(f"{where}[{rid}] is dated {day}, after Updated {updated}")
    if name == "Done" and not REFERENCE.search(rest):
        p.append(f"{where}[{rid}]: a Done row ends in a reference in parentheses, "
                 f"`(commit abc1234)` or `(no ref)`")
    if name == "Decisions" and not QUOTE.search(rest):
        p.append(f"{where}[{rid}]: a Decisions row quotes the owner's words in double quotes")


def _archive_problems(text: str, updated: date, rows: dict, p: list[str]) -> None:
    """Rule 9 on the archive's text: its Done and Parked rows join `rows`."""
    lines = [x for x in text.lstrip("﻿").replace("\r\n", "\n").split("\n") if x.strip()]
    if not lines or not lines[0].startswith("# "):
        p.append("archive: the first line must be the title, `# <Project> roadmap archive`")
    heads = [x[3:].strip() for x in lines if x.startswith("## ")]
    bad = [h for h in heads if h not in ARCHIVED]
    if bad or len(set(heads)) != len(heads):
        p.append(f"archive: only `## Done` and `## Parked`, each once, are allowed; found: {', '.join(heads) or 'none'}")
        return
    found = sections(text)
    for name in heads:
        for it in found[name]:
            _row(name, it, updated, rows, p, "archive: ")


def problems(text: str, archive: str | None = None) -> list[str]:
    """Every break of the format in `text`; [] when it holds. `archive` is the text of the file the roadmap
    names with `Archive:` (rule 9); without it an archive is taken as empty."""
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
    if heads not in (SECTIONS, WITH_MILESTONES):
        return p + [f"the sections must be exactly, in order: "
                    f"{', '.join(SECTIONS)} (with Milestones allowed after Next); "
                    f"found: {', '.join(heads) or 'none'}"]
    found = sections(text)
    rows: dict[str, tuple[str, str]] = {}            # id -> (section, text)
    for name in heads:
        for it in found[name]:
            if name == "Links":
                if not LINK.match(it):
                    p.append(f"Links: `{it[:50]}` is not `name: where`")
                continue
            _row(name, it, updated, rows, p)
    if archive is not None:
        _archive_problems(archive, updated, rows, p)
    if len(found["Now"]) > 1:
        p.append("Now holds more than one item: one turn per session")
    p += _milestones(rows)
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


def _milestones(rows: dict[str, tuple[str, str]]) -> list[str]:
    """Rule 8 on the rows read so far."""
    out: list[str] = []
    mine = {rid: rest for rid, (name, rest) in rows.items() if name == "Milestones"}
    if len(mine) > MAX_OPEN_MILESTONES:
        out.append(f"Milestones holds {len(mine)} rows; at most {MAX_OPEN_MILESTONES} are open at once")
    owner: dict[str, str] = {}
    for rid, rest in mine.items():
        m = INCLUDES.search(rest)
        if not m:
            out.append(f"[{rid}]: a Milestones row names its items, `includes: <ID>[, <ID>]`")
            continue
        if not CLOSES.search(rest):
            out.append(f"[{rid}]: a Milestones row says its proof, `closes when: <the proof>`")
        ids = re.split(r"\s*,\s*", m.group(1))
        out += [f"[{rid}] includes {t}, which is not a row of this file" for t in ids if t not in rows]
        for t in ids:
            if t in rows and rows[t][0] not in ("Next", "Done"):
                out.append(f"[{rid}] includes {t}, which is in {rows[t][0]}: a milestone holds Next and Done rows")
            if t in owner and owner[t] != rid:
                out.append(f"{t} is in two milestones, {owner[t]} and {rid}")
            owner.setdefault(t, rid)
        if ids and all(t in rows and rows[t][0] == "Done" for t in ids):
            out.append(f"[{rid}] is closed (every item is Done): remove it and record it as a Done row")
    return out


def check_file(path: Path | str, name: str | None = None) -> list[str]:
    """problems() of one file, each prefixed with `name` (default: the
    file's name)."""
    path = Path(path)
    name = name or path.name
    if not path.is_file():
        return [f"{name} does not exist: the project keeps its state in one "
                f"roadmap (templates/ROADMAP.md)"]
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = archive_name(text)
    archive = None
    if rel:
        target = path.parent / rel
        if Path(rel).is_absolute() or ".." in Path(rel).parts or not target.is_file():
            return [f"{name}: Archive: {rel} is not a file next to the roadmap (a name, not a path outside its folder)"]
        archive = target.read_text(encoding="utf-8", errors="replace")
    return [f"{name}: {x}" for x in problems(text, archive)]


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

SOUND_MILESTONES = SOUND.replace("## Done", """## Milestones
- [M1] 2026-10-01 the first run works end to end. includes: X1, D1. closes when: the doctor and the example pass on a fresh checkout
## Done""")

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
    "milestones out of place": (SOUND_MILESTONES.replace("## Done", "## Zed", 1).replace("## Parked", "## Done")
                                .replace("## Zed", "## Parked"), "sections"),
    "a milestone with no items": (SOUND_MILESTONES.replace("includes: X1, D1. ", ""), "includes:"),
    "a milestone with no proof": (SOUND_MILESTONES.replace("closes when: the doctor and the example pass on a fresh checkout",
                                                           "closes when:"), "closes when"),
    "a milestone item that is no row": (SOUND_MILESTONES.replace("X1, D1", "X1, X9"), "not a row of this file"),
    "a milestone item in Parked": (SOUND_MILESTONES.replace("X1, D1", "X1, P1"), "holds Next and Done"),
    "an item in two milestones": (SOUND_MILESTONES.replace("## Done", "- [M2] 2026-10-01 another. includes: X1. closes when: it runs\n## Done"),
                                  "in two milestones"),
    "four open milestones": (SOUND_MILESTONES
                             .replace("- [X1] 2026-10-01 doctor as the first call",
                                      "- [X1] 2026-10-01 doctor as the first call\n- [X2] 2026-10-01 b\n"
                                      "- [X3] 2026-10-01 c\n- [X4] 2026-10-01 d")
                             .replace("## Done", "- [M2] 2026-10-01 b. includes: X2. closes when: b\n"
                                      "- [M3] 2026-10-01 c. includes: X3. closes when: c\n"
                                      "- [M4] 2026-10-01 d. includes: X4. closes when: d\n## Done"), "at most"),
    "a closed milestone left open": (SOUND_MILESTONES.replace("X1, D1", "D1"), "is closed"),
}


ARCHIVE_TEXT = """# Demo roadmap archive
## Done
- [D0] 2026-09-01 the first merge (commit 0000000)
## Parked
- [P0] 2026-09-01 an old idea
"""
WITH_ARCHIVE = SOUND.replace("Updated: 2026-10-01\n", "Updated: 2026-10-01\nArchive: ROADMAP-ARCHIVE.md\n")
WITH_ARCHIVE = WITH_ARCHIVE.replace("unblocks: X1, N1", "unblocks: X1, N1, D0")

# a break of rule 9 -> (the archive's text, a word its problem must hold)
PLANTED_ARCHIVE = {
    "an id in both files": (ARCHIVE_TEXT.replace("[D0]", "[D1]"), "roadmap and its archive"),
    "a Done row with no reference": (ARCHIVE_TEXT.replace(" (commit 0000000)", ""), "reference"),
    "a row in the wrong section": (ARCHIVE_TEXT.replace("[P0]", "[D5]"), "whose ids start"),
    "a section the archive may not hold": (ARCHIVE_TEXT + "## Next\n- [X5] 2026-09-01 x\n", "only `## Done`"),
    "an unreal date": (ARCHIVE_TEXT.replace("2026-09-01 the first", "2026-02-30 the first"), "not a real day"),
    "a date after Updated": (ARCHIVE_TEXT.replace("2026-09-01 the first", "2026-11-01 the first"), "after Updated"),
    "no title": (ARCHIVE_TEXT.replace("# Demo roadmap archive", "Demo"), "title"),
}


def self_test() -> list[str]:
    """[] when the sound roadmap passes and every planted break is caught."""
    out = [f"a sound roadmap is refused: {problems(SOUND)}"] if problems(SOUND) else []
    if problems(SOUND_MILESTONES):
        out.append(f"a sound roadmap with milestones is refused: {problems(SOUND_MILESTONES)}")
    for what, (text, needle) in PLANTED.items():
        got = problems(text)
        if text == SOUND or not any(needle in x for x in got):
            out.append(f"the roadmap rule misses: {what} (got {got})")
    if problems(WITH_ARCHIVE, ARCHIVE_TEXT):
        out.append(f"a sound roadmap with its archive is refused: {problems(WITH_ARCHIVE, ARCHIVE_TEXT)}")
    if not any("not a row of this file" in x for x in problems(WITH_ARCHIVE, "# Demo roadmap archive\n")):
        out.append("a reference to a row the archive does not hold is accepted")
    for what, (archive, needle) in PLANTED_ARCHIVE.items():
        got = problems(WITH_ARCHIVE, archive)
        if archive == ARCHIVE_TEXT or not any(needle in x for x in got):
            out.append(f"the archive rule misses: {what} (got {got})")
    return out
