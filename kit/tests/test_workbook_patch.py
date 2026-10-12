#!/usr/bin/env python3
"""The workbook patch (kit/workbook_patch.py), on the SYNTHETIC influencer
tracker of _workbooks.py:

  1. The copy: a number, a text (escaped), a bool, a new cell in the
     middle of a row, a new row, a new column; re-read, every cell the
     patch did not set is as it was, the set ones hold their values, a set
     cell keeps its style; every part but the edited sheet and the
     workbook part is byte for byte the original's; the workbook part asks
     for full recalculation on open; the dimension grows; the same inputs
     give the same bytes, in the original part order.
  2. The client's cells win: a formula, a value the client entered, a
     merged cell and a missing sheet are kept and listed by ref (never by
     value); a cell already holding the value is `same`; a value the
     harness wrote last time (`ours`) may be replaced.
  3. table_sets: the owner's out and both columns of a table by key, a new
     column after the header block with its header; a key the sheet lacks
     is counted, never added; another harness's columns and unconfirmed
     rows are not written.
  4. cells.tsv (kit/workbook_map.py): its shape and rules (a cell written
     twice, a bad range, an unknown field), a map without it keeps its
     version, confirmed() / pending() / confirmed_rows() carry it;
     cell_sets fills a range in order and lists a list of another length.
  5. A sheet under a namespace prefix is refused, coded; apply() refuses a
     plan made on another file.
  6. workbook_patch.py's msg() calls are closed over its fragment.
"""

import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
import _workbooks as X  # noqa: E402
from kit import messages, workbook as W, workbook_map as WM  # noqa: E402
from kit import workbook_patch as P  # noqa: E402
from kit.contract import HarnessError  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

BASE = X.im(1)
SH = "Creators"


def cells(data: bytes) -> dict:
    wb = W.read(data)
    return {(s.name, c.ref): (c.kind, c.text, c.number, c.num_fmt, c.formula)
            for s in wb.sheets for c in s.cells.values()}


def test_copy() -> None:
    print("[1] the copy")
    wb = W.read(BASE)
    sets = [P.Set(SH, "P17", 12.5), P.Set(SH, "P18", "a & <b>"),
            P.Set(SH, "P19", True), P.Set(SH, "Q40", 7),
            P.Set(SH, "I18", "added in the middle"),
            P.Set(SH, "G19", 15100)]
    p = P.plan(wb, sets)
    check("plan: every cell is empty or ours, so all are set",
          len(p.apply) == 5 and [k["ref"] for k in p.kept] == ["G19"],
          (p.apply, p.kept))
    out = P.apply(BASE, p)
    before, after = cells(BASE), cells(out)
    setr = {(SH, s.ref) for s in p.apply}
    check("every cell the patch did not set is as it was",
          all(after.get(k) == v for k, v in before.items() if k not in setr),
          [k for k, v in before.items() if k not in setr
           and after.get(k) != v][:5])
    check("the set cells hold their values (number, escaped text, bool)",
          after[(SH, "P17")][2] == 12.5 and after[(SH, "P18")][1]
          == "a & <b>" and after[(SH, "P19")][0] == "b"
          and after[(SH, "Q40")][2] == 7.0
          and after[(SH, "I18")][1] == "added in the middle",
          [after.get((SH, r)) for r in ("P17", "P18", "P19", "Q40", "I18")])
    w0, w1 = W.read(BASE), W.read(out)
    changed = sorted(n for n in w0.parts if w0.parts[n] != w1.parts.get(n))
    check("only the edited sheet and the workbook part changed; every "
          "other part byte for byte", changed == ["xl/workbook.xml",
                                                  "xl/worksheets/sheet2.xml"]
          and set(w0.parts) == set(w1.parts), changed)
    with zipfile.ZipFile(BytesIO(out)) as z:
        wbx = z.read("xl/workbook.xml").decode()
        sx = z.read("xl/worksheets/sheet2.xml").decode()
        order = [i.filename for i in z.infolist()]
    with zipfile.ZipFile(BytesIO(BASE)) as z:
        order0 = [i.filename for i in z.infolist()]
    check("full recalculation on open", 'fullCalcOnLoad="1"' in wbx, wbx)
    check("the dimension grows to the new cells",
          w1.sheet(SH).dimension.endswith(":Q40"), w1.sheet(SH).dimension)
    check("the same inputs give the same bytes, in the original order",
          P.apply(BASE, P.plan(wb, sets)) == out and order == order0)
    check("a text is written inline: shared strings untouched",
          't="inlineStr"' in sx and "a &amp; &lt;b&gt;" in sx)
    with zipfile.ZipFile(BytesIO(BASE)) as z:
        x0 = z.read("xl/worksheets/sheet3.xml").decode()
    styled = next(m for m in re.finditer(
        r'<c r="([A-Z]+\d+)" s="([1-9]\d*)"[^>]*>(?:(?!</c>).)*</c>', x0)
        if "<f" not in m.group(0))
    sh3, r3 = W.read(BASE).sheets[2], styled.group(1)
    cell = sh3.at(*W.split_ref(r3))
    g = P.plan(wb, [P.Set(sh3.name, r3, 42)], ours=[
        {"sheet": sh3.name, "ref": r3, "value": cell.number
         if cell.number is not None else cell.text}])
    with zipfile.ZipFile(BytesIO(P.apply(BASE, g))) as z:
        x1 = z.read("xl/worksheets/sheet3.xml").decode()
    check("a set cell keeps its style (s=) and its row stays in place",
          f'<c r="{r3}" s="{styled.group(2)}"><v>42</v></c>' in x1, r3)


def test_client_wins() -> None:
    print("\n[2] the client's cells win")
    wb = W.read(BASE)
    sets = [P.Set(SH, "H17", 1), P.Set(SH, "G17", 1),
            P.Set(SH, "B15", "x"), P.Set("Nope", "A1", 1),
            P.Set(SH, "L17", "nano01")]
    p = P.plan(wb, sets)
    why = {k["ref"]: k["why"].code for k in p.kept}
    check("a formula, a client value, a merged cell, a missing sheet: kept",
          why == {"H17": "workbook_patch_formula",
                  "G17": "workbook_patch_client_value",
                  "B15": "workbook_patch_merged",
                  "A1": "workbook_patch_sheet_missing"}, why)
    check("kept rows carry a ref, never the cell's value",
          all("15000" not in str(k) for k in p.kept))
    check("a cell already holding the value is `same`, not set",
          [s.ref for s in p.same] == ["L17"] and not p.apply)
    q = P.plan(wb, [P.Set(SH, "G17", 99)],
               ours=[{"sheet": SH, "ref": "G17", "value": 15000}])
    check("a value the harness wrote last time may be replaced",
          [s.ref for s in q.apply] == ["G17"] and not q.kept, q)
    check("written() is what the next plan's ours needs",
          q.written() == [{"sheet": SH, "ref": "G17", "value": 99}])


MAP_EXTRA = ("roster\tHarness stage\troster.stage\tout\tharness-a\ttext\t"
             "confirmed\t\nroster\tHarness note\troster.note_out\tout\t"
             "harness-a\ttext\tproposed\t\nroster\tOther\troster.other\tout\t"
             "harness-b\ttext\tconfirmed\t\n")


def test_table() -> None:
    print("\n[3] table_sets")
    m, probs = WM.parse(X.IM_TABLES, X.IM_COLUMNS + MAP_EXTRA)
    wb = W.read(BASE)
    rows = {"nano01": {"roster.stage": "scale",
                       "roster.flag.data_login": True,
                       "roster.note_out": "x", "roster.other": "y"},
            "nano04": {"roster.stage": "lift"},
            "nano99": {"roster.stage": "conv"}}
    sets, issues = P.table_sets(wb, m, "roster", rows, "harness-a")
    got = {(s.ref, s.value) for s in sets}
    check("the owner's new column after the block, with its header",
          ("P16", "Harness stage") in got and ("P17", "scale") in got
          and ("P20", "lift") in got, sorted(got))
    check("a both column the owner writes: its own column (Data Login)",
          ("N17", True) in got, sorted(got))
    check("an unconfirmed row and another harness's column are not written",
          not any(v in ("x", "y") for _, v in got)
          and not any(r.startswith("Q") for r, _ in got), sorted(got))
    check("a key the sheet lacks is counted, never added",
          [i.code for i in issues] == ["workbook_patch_keys_missing"]
          and issues[0].params["count"] == 1, issues)
    p = P.plan(wb, sets)
    check("… and the plan keeps the client's Data Login (FALSE)",
          [k["ref"] for k in p.kept] == ["N17"], p.kept)


CELLS = ("field\tsheet\tcell\towner\tstatus\tnote\n"
         "roster.month_spend\tCreators\tQ3:S3\tharness-a\tconfirmed\t\n"
         "roster.total\tCreators\tQ5\tharness-a\tconfirmed\t\n"
         "roster.later\tCreators\tQ6\tharness-a\tproposed\t\n")


def test_cells() -> None:
    print("\n[4] cells.tsv")
    plain, _ = WM.parse(X.IM_TABLES, X.IM_COLUMNS)
    m, probs = WM.parse(X.IM_TABLES, X.IM_COLUMNS, None, CELLS)
    check("a map without cells.tsv keeps its version", plain.version
          == WM.version_of(X.IM_TABLES, X.IM_COLUMNS) != m.version)
    fields = X.FIELDS | {"roster.month_spend", "roster.total",
                         "roster.later"}
    check("the cells rows hold", not probs and WM.problems(m, fields) == [],
          WM.problems(m, fields))
    bad, _ = WM.parse(X.IM_TABLES, X.IM_COLUMNS, None, CELLS +
                      "roster.total\tCreators\tR3\tharness-b\tconfirmed\t\n"
                      "x.y\tCreators\tA1:B2\tharness-a\tconfirmed\t\n"
                      "roster.unknown\tCreators\tZ9\t\tconfirmed\t\n")
    codes = sorted(p.code for p in WM.problems(bad, fields))
    check("a cell written twice, a range that is not a line, an unknown "
          "field, no owner", codes == sorted([
              "workbook_map_cell_twice", "workbook_map_bad_value",
              "workbook_map_field_unknown", "workbook_map_field_unknown",
              "workbook_map_bad_value"]), codes)
    check("confirmed() keeps the confirmed cells, pending() lists the rest",
          [c["field"] for c in WM.confirmed(m).cells] == [
              "roster.month_spend", "roster.total"]
          and [x["header"] for x in WM.pending(m)
               if x["file"] == WM.CELLS_FILE] == ["Creators!Q6"])
    check("confirmed_rows() carries them (the file gate binds them)",
          "cell:Creators!Q3:S3" in WM.confirmed_rows(m))
    sets, issues = P.cell_sets(m, {"roster.month_spend": [1, 2, 3],
                                   "roster.total": [1, 2],
                                   "roster.later": 9}, "harness-a")
    check("a range filled in order; a list of another length is listed",
          [(s.ref, s.value) for s in sets] == [("Q3", 1), ("R3", 2),
                                               ("S3", 3)]
          and [i.code for i in issues] == ["workbook_patch_values_length"],
          (sets, issues))
    folder = Path(_shop.tmp_dir("patch-map-"))
    for name, text in ((WM.TABLES_FILE, X.IM_TABLES),
                       (WM.COLUMNS_FILE, X.IM_COLUMNS),
                       (WM.CELLS_FILE, CELLS)):
        (folder / name).write_text(text, encoding="utf-8")
    check("load() reads cells.tsv when it is there",
          len(WM.load(folder).cells) == 3)


def test_refusals() -> None:
    print("\n[5] refusals")
    try:
        P._edit_sheet('<x:worksheet xmlns:x="m"><x:sheetData/></x:worksheet>',
                      "xl/worksheets/sheet9.xml", [P.Set("S", "A1", 1)])
        code = None
    except HarnessError as e:
        code = e.message.code if hasattr(e, "message") else \
            messages.code(e.args[0])["code"]
    check("a sheet under a namespace prefix is refused, coded",
          code == "workbook_patch_unsupported", code)
    p = P.plan(W.read(X.lumi()), [])
    try:
        P.apply(BASE, p)
        ok = False
    except ValueError:
        ok = True
    check("apply() refuses a plan made on another file", ok)


def test_closure() -> None:
    print("\n[6] workbook_patch.py's codes are closed over its fragment")
    reg = messages.registry()
    own = {c: r for c, r in reg.items() if Path(r["file"]).name ==
           "workbook_patch.tsv"}
    check("the fragment holds workbook_patch_* codes only",
          own and all(c.startswith("workbook_patch_") for c in own),
          sorted(own))
    probs = messages.check_registry_closed(_shop.KIT, ["workbook_patch.py"],
                                           own, strict_kit=True)
    check("every msg() is registered and every code emitted", probs == [],
          probs)


if __name__ == "__main__":
    _shop.use()
    test_copy()
    test_client_wins()
    test_table()
    test_cells()
    test_refusals()
    test_closure()
    raise SystemExit(finish())
