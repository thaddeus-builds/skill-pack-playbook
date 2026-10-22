#!/usr/bin/env python3
"""The workbook map (kit/workbook_map.py): two SYNTHETIC clients' maps,
the three rules, and the shape.

  1. Both maps (the influencer tracker and Lumi Haircare Nordics) hold, and
     load() reads one from a folder.
  2. Rule one: an outgoing column has one owner. A second row that writes
     the same column (another skill pack, or the same one twice) is refused;
     the same header in another table, or read by many rows, is not.
  3. Rule two: every field id is one of the skill pack's vocabulary (when it
     gives one).
  4. Rule three: what the owner has not confirmed is listed by pending()
     and never reaches a projection: confirmed() drops it, and a proposed
     table drops its columns with it.
  5. The shape: the files' columns, closed values, unique table ids, known
     tables, an owner for out and both, a reason for a field with no
     place, key and market headers with a column row, the search box and
     the stop; check() raises one coded refusal with the count.
  6. workbook_map.py's msg() calls are closed over its fragment.
  7. values.tsv (a value read from a cell, one gate with the map): its
     shape and rules, a map without it keeps its version, load() reads it
     when it is there; texts_confirmed() turns a staged bundle's proposed
     rows confirmed and nothing else; gate_rows() is exactly what a bundle
     confirms that the one in force did not.
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
import _workbooks as X  # noqa: E402
from kit import messages, workbook_map as WM  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402


def codes(tables: str, columns: str, fields=X.FIELDS) -> list[str]:
    m, probs = WM.parse(tables, columns)
    return sorted(p.code for p in (probs or WM.problems(m, fields)))


def test_maps() -> None:
    print("[1] both maps hold")
    check("the influencer tracker's map",
          codes(X.IM_TABLES, X.IM_COLUMNS) == [])
    check("Lumi Haircare Nordics' map",
          codes(X.LUMI_TABLES, X.LUMI_COLUMNS) == [])
    d = Path(tmp_dir("map-"))
    (d / "tables.tsv").write_text("﻿" + X.IM_TABLES, encoding="utf-8")
    (d / "columns.tsv").write_text(X.IM_COLUMNS, encoding="utf-8")
    m = WM.load(d)
    check("load() reads a folder (a BOM is no header)",
          len(m.tables) == 5 and m.table("q1")["key"] ==
          "Month + KOL + Coupon" and len(m.version) == 16, m.version)
    check("the version is the content's", WM.load(d).version == m.version
          and WM.parse(X.LUMI_TABLES, X.LUMI_COLUMNS)[0].version != m.version)


def test_one_owner() -> None:
    print("\n[2] rule one: an outgoing column has one owner")
    other = X.IM_COLUMNS + \
        "roster\tData Login\troster.flag.data_login\tout\tskill-pack-b\tbool\t" \
        "proposed\t\n"
    check("a second skill pack writing the same column is refused",
          codes(X.IM_TABLES, other) == ["workbook_map_two_owners"],
          codes(X.IM_TABLES, other))
    twice = X.IM_COLUMNS + \
        "roster\tdata  login\troster.flag.data_login\tboth\tskill-pack-a\tbool" \
        "\tconfirmed\t\n"
    check("the same skill pack twice is refused too (headers compared "
          "normalized)", codes(X.IM_TABLES, twice) ==
          ["workbook_map_two_owners"], codes(X.IM_TABLES, twice))
    alias = X.IM_TABLES + \
        "roster_again\tim\tCreators\tName\trows 1-30\t\tOriginal Code\tTW\t" \
        "-\tproposed\tthe same block under another id\n"
    cols = X.IM_COLUMNS + \
        "roster_again\tOriginal Code\t-\tin\t\tcode\tproposed\t\n" \
        "roster_again\tData Login\troster.flag.data_login\tout\tskill-pack-b\t" \
        "bool\tproposed\t\n"
    check("the same block under another table id is the same column",
          codes(alias, cols) == ["workbook_map_two_owners"],
          codes(alias, cols))
    reads = X.IM_COLUMNS + \
        "roster\tData Login\troster.flag.data_login\tin\t\tbool\tproposed\t\n"
    check("a column read by more rows is fine",
          codes(X.IM_TABLES, reads) == [])
    lumi = WM.parse(X.LUMI_TABLES, X.LUMI_COLUMNS)[0]
    check("the same header out in three sheets is three columns",
          sum(1 for c in lumi.columns if c["header"] == "Status"
              and c["direction"] == "both") == 3
          and WM.problems(lumi, X.FIELDS) == [])


def test_fields() -> None:
    print("\n[3] rule two: every field is the skill pack's")
    bad = X.IM_COLUMNS.replace("roster.ads_code", "roster.adds_code")
    check("an unknown field id is refused",
          codes(X.IM_TABLES, bad) == ["workbook_map_field_unknown"],
          codes(X.IM_TABLES, bad))
    check("without a vocabulary no field is judged",
          codes(X.IM_TABLES, bad, None) == [])
    check("'-' is no field: kept in the store, projected nowhere",
          any(c["field"] == "-" for c in
              WM.parse(X.IM_TABLES, X.IM_COLUMNS)[0].columns))


def test_pending() -> None:
    print("\n[4] rule three: only what the owner confirmed is read")
    m = WM.parse(X.IM_TABLES, X.IM_COLUMNS)[0]
    p = WM.pending(m)
    check("pending() lists the proposed table and column rows",
          {(r["file"], r["table_id"], r["header"]) for r in p} == {
              ("tables.tsv", "label_counts", ""),
              ("columns.tsv", "label_counts", "Counts (Q1)"),
              ("columns.tsv", "roster", "Assets uploaded")}, p)
    check("an outgoing column waiting on the owner is listed as such",
          any(r["header"] == "Assets uploaded" and r["direction"] == "out"
              for r in p))
    c = WM.confirmed(m)
    check("confirmed() drops the proposed rows",
          c.table("label_counts") is None
          and not any(r["header"] == "Assets uploaded" for r in c.columns)
          and any(r["header"] == "Data Login" for r in c.columns))
    t = X.IM_TABLES.replace("roster\tconfirmed", "roster\tproposed", 1)
    c = WM.confirmed(WM.parse(t, X.IM_COLUMNS)[0])
    check("a proposed table drops its confirmed columns with it",
          c.table("roster") is None
          and not any(r["table_id"] == "roster" for r in c.columns))
    check("every row of a fully confirmed map is read",
          WM.pending(WM.parse(X.LUMI_TABLES, X.LUMI_COLUMNS)[0]) == [])


def test_shape() -> None:
    print("\n[5] the shape")
    head = X.IM_TABLES.splitlines()[0]
    chead = X.IM_COLUMNS.splitlines()[0]
    cases = [
        ("the files' columns", "x\ty\n", X.IM_COLUMNS,
         ["workbook_map_columns"]),
        ("an empty file", "", X.IM_COLUMNS, ["workbook_map_columns"]),
        ("a closed direction", X.IM_TABLES, X.IM_COLUMNS.replace(
            "\tboth\tskill-pack-b", "\tsideways\tskill-pack-b"),
         ["workbook_map_bad_value"]),
        ("a closed status", X.IM_TABLES.replace("\tconfirmed\tthe label",
                                                "\tmaybe\tthe label"),
         X.IM_COLUMNS, ["workbook_map_bad_value"]),
        ("a closed type", X.IM_TABLES, X.IM_COLUMNS.replace(
            "money:EUR", "money:euro", 1), ["workbook_map_bad_value"]),
        ("a unique table id", X.IM_TABLES + X.IM_TABLES.splitlines()[1]
         + "\n", X.IM_COLUMNS, ["workbook_map_table_duplicate"]),
        ("a known table", X.IM_TABLES, X.IM_COLUMNS +
         "ghost\tX\t-\tin\t\ttext\tproposed\t\n",
         ["workbook_map_table_unknown"]),
        ("an owner for out", X.IM_TABLES, X.IM_COLUMNS.replace(
            "\tout\tskill-pack-a", "\tout\t"), ["workbook_map_owner_missing"]),
        ("a reason for no place", X.IM_TABLES, X.IM_COLUMNS.replace(
            "this workbook keeps no payments", ""),
         ["workbook_map_no_place_reason"]),
        ("a key header with a column row", X.IM_TABLES.replace(
            "Month + KOL + Coupon", "Month + KOL + Voucher"), X.IM_COLUMNS,
         ["workbook_map_key_unknown"]),
        ("an @market header with a column row", X.IM_TABLES.replace(
            "Coupon\tTW", "Coupon\t@Region"), X.IM_COLUMNS,
         ["workbook_map_key_unknown"]),
        ("a search box", X.IM_TABLES.replace("rows 1-30", "first rows"),
         X.IM_COLUMNS, ["workbook_map_bad_value"]),
        ("a stop", X.IM_TABLES.replace("QUICK SUMMARY", "blank:x"),
         X.IM_COLUMNS, ["workbook_map_bad_value"]),
        ("a sheet and an anchor", X.IM_TABLES.replace("\tCalendar\tEvent",
                                                      "\t\t"),
         X.IM_COLUMNS, ["workbook_map_bad_value", "workbook_map_bad_value"]),
        ("a table id", head + "\n-\tim\tS\tA\t\t\t\t\t-\tproposed\t\n",
         chead + "\n", ["workbook_map_bad_value"]),
        ("a header", X.IM_TABLES, X.IM_COLUMNS +
         "roster\t\t-\tin\t\ttext\tproposed\t\n", ["workbook_map_bad_value"]),
    ]
    for label, t, c, want in cases:
        got = codes(t, c)
        check(label, got == want, got)
    check("search boxes: rows, cols, default",
          (WM.search_box("rows 2-30 cols B-F"), WM.search_box(""),
           WM.search_box("rows 30 - 2")) == ((2, 30, 2, 6), (1, 50, 1, 16384),
                                             (2, 30, 1, 16384)))
    check("type_ok: money needs a currency code",
          WM.type_ok("money:DKK") and not WM.type_ok("money")
          and WM.type_ok("md_range"))
    d = Path(tmp_dir("map-"))
    (d / "tables.tsv").write_text(X.IM_TABLES, encoding="utf-8")
    try:
        WM.load(d)
        code = None
    except SkillPackError as e:
        code = e.message.code
    check("a missing file: workbook_map_missing",
          code == "workbook_map_missing", code)
    (d / "columns.tsv").write_text(X.IM_COLUMNS.replace(
        "\tout\tskill-pack-a", "\tout\t") + "ghost\tX\t-\tin\t\ttext\tproposed"
        "\t\n", encoding="utf-8")
    try:
        WM.load(d)
        e = None
    except SkillPackError as err:
        e = err
    check("check() raises one coded refusal with the count and each problem",
          e is not None and e.message.code == "workbook_map_refused"
          and e.message.params["count"] == 2
          and messages.code(e.message)["params"]["problems"]["code"]
          == "joined", e and messages.code(e.message))


def test_closure() -> None:
    print("\n[6] workbook_map.py's codes are closed over its fragment")
    reg = messages.registry()
    own = {c: r for c, r in reg.items() if Path(r["file"]).name ==
           "workbook_map.tsv"}
    check("the fragment holds workbook_map_* codes only",
          own and all(c.startswith("workbook_map_") for c in own),
          sorted(own))
    probs = messages.check_registry_closed(_shop.KIT, ["workbook_map.py"],
                                           own, strict_kit=True)
    check("every msg() is registered and every code emitted", probs == [],
          probs)


VALUES = ("key\tmarket\tvalue\tsheet\tcell\tstatus\tnote\n"
          "eur_rate\tTW\t38\tBudget\tF14\tproposed\tF14 = F13*38 (SYNTHETIC)\n"
          "roas_target\tTW\t5.09\tBudget\tF32:Q32\tproposed\t\n")


def test_values() -> None:
    print("\n[7] values.tsv: the values the file states, one gate with the map")
    base, _ = WM.parse(X.IM_TABLES, X.IM_COLUMNS)
    m, probs = WM.parse(X.IM_TABLES, X.IM_COLUMNS, VALUES)
    check("a map with values holds; its version covers values.tsv, and a map "
          "without one keeps the version it had (old bundles stay named)",
          probs == [] and WM.problems(m, X.FIELDS, {"eur_rate", "roas_target"})
          == [] and m.version != base.version and base.version ==
          WM.version_of(X.IM_TABLES, X.IM_COLUMNS)
          and [v["cell"] for v in m.values] == ["F14", "F32:Q32"], probs)
    bad = VALUES + ("eur_rate\tTW\t40\tBudget\tF15\tproposed\t\n"
                    "fx\tTW\t1\tBudget\tF14:\tmaybe\t\n"
                    "\tTW\t\t\tZZZZ1\tproposed\t\n")
    m2, _ = WM.parse(X.IM_TABLES, X.IM_COLUMNS, bad)
    got = sorted(p.code for p in WM.problems(m2, X.FIELDS,
                                             {"eur_rate", "roas_target"}))
    check("values: a key stated twice, a key that is no fact key, a cell that "
          "is no cell, a closed status, the required texts",
          got == sorted(["workbook_map_value_duplicate",
                         "workbook_map_value_key_unknown",
                         "workbook_map_bad_value", "workbook_map_bad_value",
                         "workbook_map_bad_value", "workbook_map_bad_value",
                         "workbook_map_bad_value", "workbook_map_bad_value"]),
          got)
    check("without a key set, any key is shape-checked only",
          "workbook_map_value_key_unknown" not in
          {p.code for p in WM.problems(m2, X.FIELDS)})
    d = Path(tmp_dir("map-values-"))
    (d / "tables.tsv").write_text(X.IM_TABLES, encoding="utf-8")
    (d / "columns.tsv").write_text(X.IM_COLUMNS, encoding="utf-8")
    check("load() without values.tsv: no values", WM.load(d).values == []
          and WM.load(d).version == base.version)
    (d / "values.tsv").write_text(VALUES, encoding="utf-8")
    check("load() with values.tsv: the values, the bundle's version",
          len(WM.load(d).values) == 2 and WM.load(d).version == m.version)
    check("pending() lists proposed values; confirmed() keeps none of them",
          [p["header"] for p in WM.pending(m) if p["file"] == "values.tsv"]
          == ["eur_rate [TW]", "roas_target [TW]"]
          and WM.confirmed(m).values == [])

    files = WM.texts(d)
    yes = WM.texts_confirmed(files)
    m3, probs3 = WM.parse_texts(yes)
    check("texts_confirmed(): every row confirmed, nothing else changed",
          probs3 == [] and WM.pending(m3) == []
          and all(yes[n].replace("confirmed", "proposed") ==
                  files[n].replace("confirmed", "proposed") for n in files)
          and m3.version != m.version, WM.pending(m3)[:3])
    rows = WM.gate_rows(None, m3)
    check("gate_rows() from nothing: every row of the bundle, values as "
          "value:<key>|<market>",
          len(rows) == len(m3.tables) + len(m3.columns) + 2
          and rows["value:eur_rate|TW"] == "eur_rate\tTW\t38\tBudget\tF14",
          len(rows))
    again = WM.parse_texts(WM.texts_confirmed(
        {**files, "values.tsv": VALUES.replace("\t38\t", "\t39\t")}))[0]
    check("gate_rows() against the bundle in force: only what changed (a "
          "new rate is one row to pass)",
          WM.gate_rows(m3, again) == {
              "value:eur_rate|TW": "eur_rate\tTW\t39\tBudget\tF14"},
          WM.gate_rows(m3, again))
    check("a confirmed map has nothing new to pass",
          WM.gate_rows(m3, m3) == {})


def main() -> int:
    _shop.use()
    for fn in (test_maps, test_one_owner, test_fields, test_pending,
               test_shape, test_closure, test_values):
        fn()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
