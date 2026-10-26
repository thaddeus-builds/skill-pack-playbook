"""tools/overview_page.py: the overview's diagram as one page.

The page is made from docs/overview.md, so the real document is parsed here and held to the diagram
(one arrow in the page for every arrow drawn); a small document pins the grammar and each refusal. The page
itself is held to what lets a colleague open a downloaded copy: no network, the data inside it, nothing
that closes the script early, and a script that clears the columns it builds before it builds them.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "overview_page.py"
sys.path.insert(0, str(ROOT / "tools"))
import overview_page as op  # noqa: E402

FENCE = "`" * 3
SMALL = f"""Follow one example: a shop runs a sale. Each arrow is a document.

1. **Makers** make things.
2. **`checker`** checks them.

{FENCE}mermaid
flowchart LR
    subgraph MK["1 · Makers"]
      direction TB
      A["alpha<br/>makes things"]
      B["beta<br/>makes more"]
    end
    C["2 · checker<br/>checks them"]
    A -- "doc/1: why it moves" --> C
    C --> B
{FENCE}
"""


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)


def make(text: str, tmp: str) -> Path:
    p = Path(tmp) / "doc.md"
    p.write_text(text)
    return p


def data_of(html: str) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1))


def refused(text: str) -> str:
    try:
        op.parse(text)
    except op.Refused as e:
        return str(e)
    raise AssertionError("expected a refusal")


def test_the_real_overview_is_drawn_whole():
    text = (ROOT / "docs" / "overview.md").read_text("utf-8")
    d = op.parse(text)
    drawn = re.search(FENCE + r"mermaid\n(.*?)" + FENCE, text, re.S).group(1)
    assert len(d["edges"]) == len(re.findall(r"-->", drawn)), "an arrow of the diagram is missing from the page"
    ids = {n["id"] for n in d["nodes"]}
    assert ids >= {e["from"] for e in d["edges"]} | {e["to"] for e in d["edges"]}
    assert [la["n"] for la in d["lanes"]] == list(range(1, len(d["lanes"]) + 1))
    assert all(la["step"] and la["text"] and la["title"] for la in d["lanes"]), d["lanes"]
    assert {n["lane"] for n in d["nodes"]} == {la["id"] for la in d["lanes"]}, "a column with no pack, or a pack in none"


def test_the_grammar_on_a_small_document():
    d = op.parse(SMALL)
    assert d["start"]["title"] == "A shop runs a sale"
    assert [(la["n"], la["title"], la["step"]) for la in d["lanes"]] == [(1, "Makers", "Makers"), (2, "Checker", "Checker")], d["lanes"]
    by = {n["id"]: n for n in d["nodes"]}
    assert by["A"]["desc"] == "makes things" and by["C"]["name"] == "checker" and by["C"]["lane"] == "L2", by
    assert d["edges"] == [{"from": "A", "to": "C", "contract": "doc/1", "why": "why it moves"},
                          {"from": "C", "to": "B", "contract": "", "why": ""}], d["edges"]


def test_what_the_diagram_cannot_say_is_refused_with_its_line():
    assert "not understood" in refused(SMALL.replace("    C --> B\n", "    C ==> B\n"))
    msg = refused(SMALL.replace("C --> B", "C --> Z"))
    assert "Z" in msg and "no pack" in msg, msg
    assert "2 steps and the diagram 3" in refused(SMALL.replace("    C[", "    D[\"3 · third<br/>x\"]\n    C["))
    assert "2 steps and the diagram 1" in refused(SMALL.replace("    C[\"2 · checker<br/>checks them\"]\n", "").replace("    C --> B\n", "").replace("-> C", "-> B"))
    assert "no \"N · \"" in refused(SMALL.replace('"1 · Makers"', '"Makers"'))
    assert "no \"N · \"" in refused(SMALL.replace('"2 · checker', '"checker'))
    assert "drawn twice" in refused(SMALL.replace('"2 · checker', '"1 · checker'))
    assert "drawn twice" in refused(SMALL.replace('    B["beta', '    A["beta'))
    assert "numbered 2 where 1" in refused(SMALL.replace("1. **Makers**", "2. **Makers**"))
    assert "no mermaid" in refused("nothing here\n")
    bad = SMALL.replace("    C --> B\n", "    C ==> B\n")
    n = int(re.search(r"line (\d+)", refused(bad)).group(1))
    assert bad.split("\n")[n - 1].strip() == "C ==> B", "the line number is not the document's line"


def test_the_page_is_one_file_with_no_network_and_its_data_inside():
    with _t.tmpdir() as tmp:
        out = Path(tmp) / "sub" / "page.html"
        r = run("--doc", str(ROOT / "docs" / "overview.md"), "--out", str(out))
        assert r.returncode == 0, r.stderr
        html = out.read_text("utf-8")
        assert data_of(html) == op.parse((ROOT / "docs" / "overview.md").read_text("utf-8"))
        assert "default-src 'none'" in html, "no policy that refuses every request"
        assert not re.search(r"""(?:src|href|action)\s*=\s*["']?(?:https?:)?//""", html), "the page asks the network for something"
        assert "@import" not in html and "url(http" not in html
        assert 'name="viewport"' in html and "prefers-color-scheme: dark" in html and "max-width:860px" in html
        again = Path(tmp) / "again.html"
        run("--doc", str(ROOT / "docs" / "overview.md"), "--out", str(again))
        assert again.read_bytes() == out.read_bytes(), "same document, different bytes"


def test_a_word_in_the_diagram_cannot_close_the_script():
    with _t.tmpdir() as tmp:
        doc = make(SMALL.replace("makes things", "x</script><b>y & z"), tmp)
        out = Path(tmp) / "p.html"
        assert run("--doc", str(doc), "--out", str(out)).returncode == 0
        html = out.read_text("utf-8")
        assert html.count("</script>") == 2, "the data or the script closed early"
        assert {n["id"]: n for n in data_of(html)["nodes"]}["A"]["desc"] == "x</script><b>y & z"


def test_the_script_clears_its_columns_before_building_them():
    # seen once, 2026-10-26: a browser's "save page" kept the built columns, and the saved copy showed every one twice
    js = (ROOT / "tools" / "overview_page.html").read_text("utf-8")
    clear = js.index("lanesEl.replaceChildren()")
    assert clear < js.index("DATA.lanes.forEach"), "the columns are built before they are cleared"
    assert "stepsEl.replaceChildren()" in js and "svg.replaceChildren()" in js and ".chip').forEach(c => c.remove())" in js


def test_a_refusal_exits_one_and_names_the_line_on_stderr():
    with _t.tmpdir() as tmp:
        doc = make(SMALL.replace("C --> B", "C --> Z"), tmp)
        out = Path(tmp) / "p.html"
        r = run("--doc", str(doc), "--out", str(out))
        assert r.returncode == 1 and r.stderr.startswith("overview_page: line "), (r.returncode, r.stderr)
        assert not out.exists(), "a page written from a document that was refused"
        assert run("--doc", str(Path(tmp) / "none.md"), "--out", str(out)).returncode == 1


if __name__ == "__main__":
    _t.main(globals())
