"""tools/research.py: one table from the skill packs' research and prior-art indexes.

Throwaway skill packs: one with a research table and a prior-art table, one with a prior-art list and a sentence (dates from file names and from a
`Scan date:` line), one with neither index. A row is any index line that links a file of its folder; `--write` writes the table in full as a TSV.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "research.py"

RESEARCH = """# Research

| File | Question | Date | Answer in one line | Used by |
| --- | --- | --- | --- | --- |
| [fees.md](fees.md) | what does the vendor charge | 2026-10-01 | 3 cents a call, `tab	here` | `pull.py` |
| [limits.md](limits.md) | which rate limits | 2026-10-02 | 10 a second | none |
"""
PRIOR_ART = """# Prior art

| Lens | File | Verdict |
| --- | --- | --- |
| Tools to buy | [2026-10-03-tools.md](2026-10-03-tools.md) | keep ours |
"""
LISTED = """# Prior art

Scans:
- [Law of the market](law.md), read before copy is written
- [Old tools](2026-09-01-old.md)

See also [the index itself](README.md) and [a repeat](law.md).
"""


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)


def packs(tmp: str) -> tuple[Path, Path, Path]:
    a, b, c = (Path(tmp) / n for n in ("a-skill-pack", "b-skill-pack", "c-skill-pack"))
    write(a, {"docs/research/README.md": RESEARCH, "docs/research/fees.md": "# Fees\n", "docs/research/limits.md": "# Limits\n",
              "docs/prior-art/README.md": PRIOR_ART, "docs/prior-art/2026-10-03-tools.md": "# Tools\n"})
    write(b, {"docs/prior-art/README.md": LISTED, "docs/prior-art/law.md": "# Law\n\nScan date: 2026-10-07\n",
              "docs/prior-art/2026-09-01-old.md": "# Old\n"})
    write(c, {"docs/ROADMAP.md": "# c\n"})
    return a, b, c


def table(out: str) -> list[list[str]]:
    return [ln.split("  ") for ln in out.splitlines()]


def test_a_table_row_is_read_by_its_header():
    with _t.tmpdir() as tmp:
        a, b, c = packs(tmp)
        out = tmp + "/out.tsv"
        r = run(str(a), str(b), str(c), "--write", out)
        assert r.returncode == 0, r.stderr
        rows = [ln.split("\t") for ln in Path(out).read_text(encoding="utf-8").splitlines()]
        assert rows[0] == ["pack", "kind", "question", "date", "answer", "file"], rows[0]
        by = {(x[0], x[5]): x for x in rows[1:]}
        assert by[("a-skill-pack", "fees.md")] == ["a-skill-pack", "research", "what does the vendor charge", "2026-10-01",
                                                   "3 cents a call, `tab here`", "fees.md"], by[("a-skill-pack", "fees.md")]
        assert by[("a-skill-pack", "2026-10-03-tools.md")][1:5] == ["prior-art", "Tools to buy", "2026-10-03", "keep ours"]


def test_a_list_or_a_sentence_is_the_question_and_the_date_comes_from_the_file():
    with _t.tmpdir() as tmp:
        a, b, c = packs(tmp)
        out = tmp + "/out.tsv"
        run(str(b), "--write", out)
        rows = {r[5]: r for r in (ln.split("\t") for ln in Path(out).read_text(encoding="utf-8").splitlines()[1:])}
        assert sorted(rows) == ["2026-09-01-old.md", "law.md"], sorted(rows)
        assert rows["law.md"][2:5] == ["Law of the market, read before copy is written", "2026-10-07", ""], rows["law.md"]
        assert rows["2026-09-01-old.md"][3] == "2026-09-01"


def test_the_printed_table_is_one_aligned_table_and_a_pack_with_no_index_is_named():
    with _t.tmpdir() as tmp:
        a, b, c = packs(tmp)
        r = run(str(a), str(b), str(c))
        assert r.returncode == 0, r.stderr
        lines = r.stdout.splitlines()
        assert lines[0].split() [:2] == ["pack", "kind"] and len(lines) == 1 + 2 + 1 + 2, lines
        assert "c-skill-pack" not in r.stdout and "c-skill-pack" in r.stderr, (r.stdout, r.stderr)
        assert not (Path(tmp) / "out.tsv").exists(), "nothing is written unless --write asks"


def test_a_long_cell_is_cut_on_screen_and_whole_in_the_file():
    with _t.tmpdir() as tmp:
        a = Path(tmp) / "a-skill-pack"
        long = "x" * 200
        write(a, {"docs/research/README.md": f"| File | Question | Date | Answer |\n| --- | --- | --- | --- |\n| [q.md](q.md) | {long} | 2026-10-01 | y |\n",
                  "docs/research/q.md": "# Q\n"})
        out = tmp + "/sub/out.tsv"
        r = run(str(a), "--write", out)
        assert long not in r.stdout and "…" in r.stdout
        assert long in Path(out).read_text(encoding="utf-8"), "the file keeps the whole cell, in a folder made for it"


def test_a_missing_folder_is_refused_and_nothing_is_written():
    with _t.tmpdir() as tmp:
        r = run(tmp + "/nope", "--write", tmp + "/out.tsv")
        assert r.returncode == 2 and "not a folder" in r.stderr and not (Path(tmp) / "out.tsv").exists(), (r.returncode, r.stderr)


if __name__ == "__main__":
    _t.main(globals())
