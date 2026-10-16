#!/usr/bin/env python3
"""The roadmap format (kit/guards/roadmap.py).

  [0] self_test: a sound roadmap passes and every planted break is caught;
      each break is also planted here, one by one, on the sound text
  [1] the shipped template, its placeholders filled as the scaffolder fills
      them, passes, so a skill pack that starts from it starts green
  [2] a skill pack's file: docs/ROADMAP.md or ROADMAP.md is found, two of them
      or none is a problem, [guards.roadmap] file is honoured, a broken file
      is reported with its name
  [3] edge cases: CRLF, a byte order mark, blank sections, a comment under
      Updated, a Waiting row that unblocks several rows, an empty file
"""

import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit.guards import roadmap  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

TEMPLATE = _shop.PLAYBOOK / "templates" / "ROADMAP.md"


def filled() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    return text.replace("{{name}}", "acme-skill-pack").replace("{{today}}", "2026-10-01")


def test_rules() -> None:
    print("\n[0] the rules, each on its planted break")
    check("self_test: every rule catches its plant, the sound roadmap passes",
          roadmap.self_test() == [], roadmap.self_test())
    for what, (text, needle) in roadmap.PLANTED.items():
        got = roadmap.problems(text)
        check(f"caught: {what}", any(needle in x for x in got), got)
    broken = roadmap.SOUND.replace("[X1] 2026-10-01 doctor", "[X1] 2026-10-01 doctor\n- [X1] 2099-01-01 again")
    got = roadmap.problems(broken)
    check("every break is listed, not only the first",
          any("used twice" in x for x in got) and any("after Updated" in x for x in got), got)


def test_template() -> None:
    print("\n[1] the template")
    text = TEMPLATE.read_text(encoding="utf-8")
    check("its placeholders are {{name}} and {{today}} only",
          set(re.findall(r"\{\{(\w+)\}\}", text)) == {"name", "today"})
    check("filled, it passes its own check", roadmap.problems(filled()) == [], roadmap.problems(filled()))
    check("one example row in each section",
          all(len(v) == (2 if k == "Links" else 1) for k, v in roadmap.sections(filled()).items()),
          roadmap.sections(filled()))


def skill_pack_at(root: Path) -> Path:
    root.mkdir(parents=True)
    shutil.copy(_shop.SHOP / "skill-pack.toml", root / "skill-pack.toml")
    return root


def test_skill_pack_file() -> None:
    print("\n[2] a skill pack's file")
    root = skill_pack_at(Path(tmp_dir()) / "h")
    got = roadmap.check_roadmap(root)
    check("no roadmap is reported, by its default home",
          len(got) == 1 and got[0].startswith("docs/ROADMAP.md does not exist"), got)
    (root / "docs").mkdir()
    (root / "docs" / "ROADMAP.md").write_text(filled(), encoding="utf-8")
    check("docs/ROADMAP.md is found and clean", roadmap.check_roadmap(root) == [], roadmap.check_roadmap(root))
    (root / "ROADMAP.md").write_text(filled(), encoding="utf-8")
    got = roadmap.check_roadmap(root)
    check("two roadmaps are one too many", any("two roadmaps" in x for x in got), got)
    (root / "docs" / "ROADMAP.md").unlink()
    check("ROADMAP.md at the root is found and clean", roadmap.check_roadmap(root) == [], roadmap.check_roadmap(root))
    (root / "ROADMAP.md").write_text(filled().replace("## Parked", "## Later"), encoding="utf-8")
    got = roadmap.check_roadmap(root)
    check("a broken file is reported with its name",
          len(got) == 1 and got[0].startswith("ROADMAP.md: the sections"), got)
    with open(root / "skill-pack.toml", "a", encoding="utf-8") as f:
        f.write('\n[guards.roadmap]\nfile = "plan/ROADMAP.md"\n')
    (root / "plan").mkdir()
    (root / "plan" / "ROADMAP.md").write_text(filled(), encoding="utf-8")
    check("[guards.roadmap] file is honoured (the broken root file is not read)",
          roadmap.check_roadmap(root) == [], roadmap.check_roadmap(root))
    check("check_file on a path that is not there", roadmap.check_file(root / "nope.md") != [])


def test_edges() -> None:
    print("\n[3] edge cases")
    sound = roadmap.SOUND
    check("CRLF and a byte order mark are read",
          roadmap.problems("﻿" + sound.replace("\n", "\r\n")) == [])
    blank = "# P roadmap\nUpdated: 2026-10-01\n" + "".join(f"## {s}\n" for s in roadmap.SECTIONS)
    check("blank sections are fine", roadmap.problems(blank) == [], roadmap.problems(blank))
    check("a Waiting row may unblock one row or several",
          roadmap.problems(sound.replace("unblocks: X1, N1", "unblocks: X1")) == []
          and roadmap.problems(sound.replace("unblocks: X1, N1", "unblocks: X1,N1 ,D1")) == [])
    check("an empty file and a title alone are refused, not a crash",
          roadmap.problems("") != [] and roadmap.problems("# P roadmap\n") != [])
    prose = sound.replace("## Next\n", "## Next\nIn the order it will be done.\n")
    check("a line that is not an item is not read", roadmap.problems(prose) == [], roadmap.problems(prose))


def main() -> None:
    test_rules()
    test_template()
    test_skill_pack_file()
    test_edges()


if __name__ == "__main__":
    main()
    raise SystemExit(finish())
