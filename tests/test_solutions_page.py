"""tools/solutions_page.py: which skill packs a kind of client needs, as one page.

The real docs/solutions.md and docs/portfolio.md are parsed and held to their own tables and diagram (a row for
every solution, a pack for every name a layer cell gives, an arrow for every arrow drawn); a small document pins the
grammar and each refusal. The page is the one overview_page.py makes, held here to the same: no network, the data
inside it, nothing that closes the script early.
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
TOOL = ROOT / "tools" / "solutions_page.py"
sys.path.insert(0, str(ROOT / "tools"))
import solutions_page as sp  # noqa: E402

FENCE = "`" * 3
SOL = f"""# Solutions

Intro.

## The solutions

| Solution | For | Operators | Truth | Makers |
| --- | --- | --- | --- | --- |
| **A. Shops** | a shop | `ops1` (a note), `ops2`; `extra` when wanted | `facts`, messaging | `maker` (with the kit's `compliance`) |
| **B. Sellers** | a seller | `ops3` | `facts` | — |

A client may need two solutions. Shops plus sellers is A plus B.

## How they work together

{FENCE}mermaid
flowchart LR
    subgraph truth["Truth"]
      F["facts<br/>facts/1"]
      M["messaging (maker)<br/>messages/1"]
    end
    subgraph makers["Makers"]
      K["maker<br/>makes"]
    end
    subgraph ops["Operators"]
      O1["ops1<br/>runs"]
    end
    F --> K
    M -- "messages/1: what to say" --> K
    K -- "ads.creatives/1" --> O1
{FENCE}

## Starting a client

1. Make the hub.
2. Add packs in this order:
   1. the first operator;
   2. the measurement.
3. One inbox.

## What each solution still lacks (2026-10-23)

| Solution | Missing |
| --- | --- |
| A | the thing |
| B | another thing |
"""
PORT = """| Repository | CLI | Layer and role | State |
| --- | --- | --- | --- |
| ops1-skill-pack | `o1` | Operator, paid push, X | scaffold |
| facts-harness | `f` | Truth: facts | x |
"""


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)


def data_of(html: str) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1))


def refused(text: str, portfolio: str = PORT) -> str:
    try:
        sp.parse(text, portfolio)
    except sp.Refused as e:
        return str(e)
    raise AssertionError("expected a refusal")


def test_the_real_tables_are_drawn_whole():
    text = (ROOT / "docs" / "solutions.md").read_text("utf-8")
    port = (ROOT / "docs" / "portfolio.md").read_text("utf-8")
    d = sp.parse(text, port)
    rows = re.findall(r"^\| \*\*([A-Z])\. ", text, re.M)
    assert [g["id"] for g in d["groups"]] == rows, "a solution of the table is not on the page"
    drawn = re.search(FENCE + r"mermaid\n(.*?)" + FENCE, text, re.S).group(1)
    assert len(d["edges"]) == len(re.findall(r"-->", drawn)), "an arrow of the diagram is missing from the page"
    ids = {n["id"] for n in d["nodes"]}
    assert all(set(g["members"]) <= ids and g["members"] and g["lead"] for g in d["groups"])
    assert {e[k] for e in d["edges"] for k in ("from", "to")} <= ids
    assert {n["lane"] for n in d["nodes"]} <= {la["id"] for la in d["lanes"]}
    assert all(e["contract"] for e in d["edges"]), "an arrow says no document"
    assert all(g.get("lacks") for g in d["groups"]) and d["lacks_title"].startswith("What each solution still lacks")
    table = next(t for t in sp.tables(text) if t["header"][:2] == ["Solution", "For"])
    packs = set(re.findall(r"`([a-z][\w-]*)`", sp.without_notes(" ".join(" ".join(r[2:]) for r in table["rows"]))))
    assert packs <= {n["name"] for n in d["nodes"]}, packs - {n["name"] for n in d["nodes"]}
    assert d["start"]["more"]["title"] == "Starting a client" and d["start"]["lead"].startswith("A client may need two solutions")


def test_the_grammar_on_a_small_document():
    d = sp.parse(SOL, PORT)
    by = {n["name"]: n for n in d["nodes"]}
    assert [(la["id"], la["title"]) for la in d["lanes"]] == [("L1", "Truth"), ("L2", "Makers"), ("L3", "Operators")]
    assert "compliance" not in by, "a pack named inside brackets is a note"
    assert set(by) == {"facts", "messaging (maker)", "maker", "ops1", "ops2", "extra", "ops3"}, set(by)
    assert by["ops2"]["lane"] == "L3" and by["ops1"]["id"] == "O1", "a pack the diagram draws keeps its own id"
    assert by["ops1"]["desc"] == "paid push, X" and by["facts"]["desc"] == "facts", "the layer word is said by the column"
    assert by["maker"]["desc"] == "makes" and by["ops2"]["desc"] == "", by
    a, b = d["groups"]
    assert (a["id"], a["title"], a["lead"]) == ("A", "Shops", "a shop"), a
    assert a["members"] == ["O1", "ops2", "extra", "F", "M", "K"], a["members"]
    assert a["cells"]["L1"] == "facts, messaging" and a["cells"]["L3"].startswith("ops1 (a note), ops2; extra when wanted"), a["cells"]
    assert b["members"] == ["ops3", "F"] and "L2" not in b["cells"], b
    assert (a["lacks"], b["lacks"], d["lacks_title"]) == ("the thing", "another thing", "What each solution still lacks (2026-10-23)")
    assert [e["contract"] for e in d["edges"]] == ["facts/1", "messages/1", "ads.creatives/1"], "an arrow with no label takes its pack's document"
    assert d["start"]["lead"] == "A client may need two solutions. Shops plus sellers is A plus B."
    assert d["start"]["more"]["items"] == ["Make the hub.", "Add packs in this order: the first operator; the measurement", "One inbox."]


def test_what_the_tables_cannot_say_is_refused():
    assert "no solutions table" in refused(SOL.replace("| Solution | For |", "| Kind | For |"))
    assert 'layer "Makers"' in refused(SOL.replace('subgraph makers["Makers"]', 'subgraph makers["Builders"]'))
    assert "in two layers" in refused(SOL.replace("| `ops3` |", "| `ops3` |").replace("| `facts` | — |", "| `facts` | `ops1` |"))
    assert "lists it in" in refused(SOL.replace("`ops1` (a note)", "`maker` (a note)").replace("`maker` (with", "`ops1` (with"))
    assert "6 cells where the header has 5" in refused(SOL.replace("| `ops3` |", "| `ops3` | `x` |"))
    assert 'must start "A. "' in refused(SOL.replace("**A. Shops**", "**Shops**"))
    assert "lists no pack" in refused(SOL.replace("| `ops3` | `facts` | — |", "| — | — | — |"))
    assert "once each" in refused(SOL.replace("**B. Sellers**", "**A. Sellers**"))
    assert "no mermaid" in refused(SOL.replace("mermaid", "text"))
    assert "outside every column" in refused(SOL.replace("    F --> K\n", '    Z["alone<br/>x"]\n    F --> K\n'))
    assert "not understood" in refused(SOL.replace("    F --> K\n", "    F ==> K\n"))


def test_the_page_is_one_file_with_no_network_and_its_data_inside():
    with _t.tmpdir() as tmp:
        doc, port, out = Path(tmp) / "s.md", Path(tmp) / "p.md", Path(tmp) / "x" / "page.html"
        doc.write_text(SOL.replace("a seller", "a seller</script><b>x & y"))
        port.write_text(PORT)
        r = run("--doc", str(doc), "--portfolio", str(port), "--out", str(out))
        assert r.returncode == 0, r.stderr
        html = out.read_text("utf-8")
        assert html.count("</script>") == 2, "the data or the script closed early"
        d = data_of(html)
        assert d == sp.parse(doc.read_text("utf-8"), PORT) and d["groups"][1]["lead"] == "a seller</script><b>x & y"
        assert "default-src 'none'" in html
        assert not re.search(r"""(?:src|href|action)\s*=\s*["']?(?:https?:)?//""", html), "the page asks the network for something"
        again = Path(tmp) / "again.html"
        run("--doc", str(doc), "--portfolio", str(port), "--out", str(again))
        assert again.read_bytes() == out.read_bytes(), "same documents, different bytes"


def test_a_refusal_exits_one_and_names_why_on_stderr():
    with _t.tmpdir() as tmp:
        doc, out = Path(tmp) / "s.md", Path(tmp) / "p.html"
        doc.write_text(SOL.replace("**A. Shops**", "**Shops**"))
        r = run("--doc", str(doc), "--out", str(out))
        assert r.returncode == 1 and r.stderr.startswith("solutions_page: ") and not out.exists(), (r.returncode, r.stderr)
        doc.write_text(SOL)
        r = run("--doc", str(doc), "--portfolio", str(Path(tmp) / "none.md"), "--out", str(out))
        assert r.returncode == 1 and "no such file" in r.stderr and not out.exists(), r.stderr


if __name__ == "__main__":
    _t.main(globals())
