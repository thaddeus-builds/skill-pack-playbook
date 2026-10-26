#!/usr/bin/env python3
"""kit.guards.research: research is kept, not repeated (docs/research/ and docs/prior-art/ each list their files in a README). On SYNTHETIC folders only.

  [0] self_test: the sound folders pass and every planted break is caught; a skill pack with neither folder passes
  [1] each rule on a folder on disk: a file with no row, a row with no file, a link with a path is no row, a missing README, a row with no
      day, a file with no Researched day (or an unreal one), no tagged claim; a prior-art file takes its day from its name or a Scan date line
  [2] the day-one suite runs the rule (suites.research) and reports each break by file
"""

import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit.guards import research  # noqa: E402
from kit.testing import suites  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

SOUND = research.SOUND


def folder(**changes) -> Path:
    root = Path(tmp_dir("research-"))
    research._write(root, {**SOUND, **changes})
    return root


def has(root: Path, needle: str) -> bool:
    return any(needle in p for p in research.problems(root))


def test_rules() -> None:
    print("\n[0] the rules, each on its planted break")
    check("self_test: every rule catches its plant, the sound folders pass", research.self_test() == [], research.self_test())
    for what, (files, needle) in research.PLANTED.items():
        root = folder(**files)
        check(f"caught: {what}", has(root, needle), research.problems(root))
    check("neither folder: nothing kept yet, nothing to check", research.problems(Path(tmp_dir("research-"))) == [])
    check("a pack with only docs/ and no folder is not read", research.problems(folder(**{k: None for k in SOUND})) == [])


def test_disk() -> None:
    print("\n[1] the rules on a folder on disk")
    root = folder()
    check("the sound folders pass", research.problems(root) == [], research.problems(root))
    (root / "docs/research/README.md").write_text(
        SOUND["docs/research/README.md"] + "| [other](../other.md) | q | 2026-10-01 | a | b |\n"
        "| [sub](sub/y.md) | q | 2026-10-01 | a | b |\n", encoding="utf-8")
    check("a link with a path is no row: not listed, not a missing file", research.problems(root) == [], research.problems(root))
    (root / "docs/research/README.md").write_text(SOUND["docs/research/README.md"] + "\nSee also [fees](fees.md#top) and [the index](README.md).\n", encoding="utf-8")
    check("an anchor on a listed file, and a link to the README itself, are fine", research.problems(root) == [], research.problems(root))
    all_problems = research.problems(folder(**{
        "docs/research/fees.md": "# Fees\n", "docs/research/stray.md": "# Stray\n", "docs/prior-art/2026-10-02-tools.md": None}))
    check("every break is listed, not only the first",
          len(all_problems) >= 4 and any("stray.md" in p for p in all_problems) and any("2026-10-02-tools.md" in p for p in all_problems), all_problems)
    scan = folder(**{"docs/prior-art/lens.md": "# Lens\n\nScan date: 2026-10-05\n",
                     "docs/prior-art/README.md": SOUND["docs/prior-art/README.md"] + "- [lens](lens.md)\n"})
    check("a prior-art file with a `Scan date:` line and no dated name passes", research.problems(scan) == [], research.problems(scan))
    odd = folder(**{"docs/prior-art/2026-02-30-x.md": "# X\n",
                    "docs/prior-art/README.md": SOUND["docs/prior-art/README.md"] + "- [x](2026-02-30-x.md)\n"})
    check("an unreal day in a prior-art name is refused", has(odd, "no day in its name"), research.problems(odd))
    crlf = folder(**{"docs/research/README.md": SOUND["docs/research/README.md"].replace("\n", "\r\n")})
    check("CRLF line ends read the same", research.problems(crlf) == [], research.problems(crlf))
    empty = folder(**{"docs/research/README.md": "# Research\n\n| File | Question | Date | Answer | Used by |\n| --- | --- | --- | --- | --- |\n",
                      "docs/research/fees.md": None})
    check("an index with no row and no file passes (the day-one state)", research.problems(empty) == [], research.problems(empty))


def test_suite() -> None:
    print("\n[2] the day-one suite")
    root = folder()
    res = suites.research(root)
    check("suites.research: green on the sound folders", not [p for _, p in res if p], res)
    research._write(root, {"docs/research/stray.md": "# Stray\n"})
    bad = [p for _, ps in suites.research(root) for p in ps]
    check("…and names the file that has no row", any("docs/research/stray.md" in p for p in bad), bad)


def main() -> int:
    test_rules()
    test_disk()
    test_suite()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
