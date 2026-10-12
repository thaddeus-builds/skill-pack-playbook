"""Set cells in a copy of a client's .xlsx workbook, with the standard
library only, so the client opens their own file with the harness's
numbers in it. The original is never written; the copy is new bytes.

    p = plan(wb, sets, ours)           # what will be set, and what not
    data = apply(src_bytes, p)         # the copy

What it guards:

  * Nothing it does not set changes. A part with no cell to set is copied
    as it is (its sha256 equals the original's, Workbook.parts proves it);
    a sheet that gets cells is edited as text, cell by cell, so its
    namespaces, prefixes and every other element stay byte for byte. The
    workbook part only gains full recalculation on open
    (`calcPr fullCalcOnLoad`), so every formula that reads a set cell
    shows the new value. Shared strings, styles, comments, pivot tables,
    the calculation chain and every other part are not touched: a text is
    written inline (`t="inlineStr"`), a set cell keeps its style.
  * The client's own cells win. A cell holding a formula is never set
    (workbook_patch_formula); a cell holding a value the harness did not
    write there last time (`ours`, the values its previous copy set) is
    never set (workbook_patch_client_value); a cell a merge covers, other
    than the merge's anchor, is never set (workbook_patch_merged); a
    sheet the workbook lacks is listed (workbook_patch_sheet_missing).
    Each is listed in Plan.kept with its ref, never its value. A cell
    already holding the value is left as it is (Plan.same).
  * The same inputs give the same bytes: the parts keep their order and
    compression, every entry gets one fixed time stamp.
  * The workbook is read by kit.workbook first, so an unsafe or broken
    file is refused there (workbook_unsafe, workbook_unreadable). A sheet
    whose cells sit under a namespace prefix (`<x:row>`) is refused,
    coded (workbook_patch_unsupported), never guessed.

Placing a harness's results comes from the client's map
(kit.workbook_map), never from a cell address in code:

  * table_sets(wb, map, table_id, rows, owner): one row per key of the
    table (rows = {key: {field: value}}); each `out` or `both` column the
    owner writes is the table's column with that header, or a new column
    right after the table's header block (its header written too), in the
    map's order; a key the sheet lacks is counted
    (workbook_patch_keys_missing), never added;
  * cell_sets(map, values, owner): each cells.tsv row the owner writes,
    values = {field: value, or a list filling its range in order}; a list
    of another length is listed (workbook_patch_values_length).
Both read the confirmed map only.

Test: kit/tests/test_workbook_patch.py.
"""

from __future__ import annotations

import io
import math
import re
import zipfile
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from kit import workbook_map as wm
from kit.messages import Msg, msg
from kit.workbook import Workbook, _Zip, col_letters, norm, read, ref, \
    split_ref
from kit.workbook_store import keyed_rows, locate

STAMP = (2000, 1, 1, 0, 0, 0)
_ROW = re.compile(r"<row\b[^>]*?\br=\"(\d+)\"[^>]*?(?:/>|>.*?</row>)", re.S)
_CELL = re.compile(r"<c\b[^>]*?\br=\"([A-Z]{1,3}\d+)\"[^>]*?(?:/>|>.*?</c>)",
                   re.S)
_STYLE = re.compile(r"\bs=\"(\d+)\"")


@dataclass(frozen=True)
class Set:
    """One cell to set: a number, a text or a bool (None sets nothing)."""

    sheet: str
    ref: str
    value: object
    field: str = ""


@dataclass
class Plan:
    base_sha: str
    apply: list[Set] = field(default_factory=list)
    same: list[Set] = field(default_factory=list)
    kept: list[dict] = field(default_factory=list)   # {sheet, ref, field, why}

    def written(self) -> list[dict]:
        """What the copy holds from the harness (the next plan's `ours`)."""
        return [{"sheet": s.sheet, "ref": s.ref, "value": s.value}
                for s in self.apply + self.same]


def _text_of(v: object) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return _num(v)
    return str(v)


def _num(v: float) -> str:
    if isinstance(v, bool) or not math.isfinite(float(v)):
        raise ValueError(f"not a finite number: {v!r}")
    return str(int(v)) if float(v).is_integer() and abs(v) < 1e15 \
        else repr(float(v))


def _equal(cell, v: object) -> bool:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return cell.number is not None and abs(cell.number - float(v)) < 1e-9
    if isinstance(v, bool):
        return cell.kind == "b" and cell.text in (("1", "TRUE") if v
                                                  else ("0", "FALSE"))
    return (cell.text or "") == str(v)


def _keep(p: Plan, s: Set, why: Msg) -> None:
    p.kept.append({"sheet": s.sheet, "ref": s.ref, "field": s.field,
                   "why": why})


def plan(wb: Workbook, sets: list[Set], ours: list[dict] | None = None
         ) -> Plan:
    """What apply() will set in `wb`, what is already so, and what is kept
    as the client has it (module doc). `ours`: Plan.written() of the
    previous copy."""
    mine = {(norm(o["sheet"]), o["ref"]): o["value"] for o in ours or []}
    p = Plan(base_sha=wb.sha256)
    for s in sets:
        if s.value is None:
            continue
        sh = wb.sheet(s.sheet)
        if sh is None:
            _keep(p, s, msg("workbook_patch_sheet_missing",
                            f"the workbook has no sheet {s.sheet!r}",
                            sheet=s.sheet))
            continue
        r, c = split_ref(s.ref)
        if sh.anchor_of(r, c):
            _keep(p, s, msg("workbook_patch_merged",
                            f"{s.sheet}!{s.ref} is covered by a merge: not "
                            f"set", sheet=s.sheet, ref=s.ref))
            continue
        cell = sh.at(r, c)
        if cell is not None and cell.formula is not None:
            _keep(p, s, msg("workbook_patch_formula",
                            f"{s.sheet}!{s.ref} holds a formula: not set",
                            sheet=s.sheet, ref=s.ref))
            continue
        if cell is not None and (cell.text or "") != "":
            if _equal(cell, s.value):
                p.same.append(s)
                continue
            prev = mine.get((norm(s.sheet), s.ref))
            if prev is None or not _equal(cell, prev):
                _keep(p, s, msg("workbook_patch_client_value",
                                f"{s.sheet}!{s.ref} holds a value the "
                                f"client entered: not set", sheet=s.sheet,
                                ref=s.ref))
                continue
        p.apply.append(s)
    return p


# ---- the copy --------------------------------------------------------------

def _parts(z: _Zip) -> tuple[str, dict[str, str]]:
    """(workbook part, {sheet name: worksheet part})."""
    root = z.rels("") if z.has("_rels/.rels") else {}
    wb_part = next((t for typ, t in root.values()
                    if typ.endswith("/officeDocument")), "xl/workbook.xml")
    rels = z.rels(wb_part)
    out = {}
    el = z.xml(wb_part)
    for s in el.iter():
        if s.tag.rsplit("}", 1)[-1] != "sheet":
            continue
        rid = next((v for k, v in s.attrib.items()
                    if k.rsplit("}", 1)[-1] == "id"), "")
        typ, target = rels.get(rid, ("", ""))
        if typ.endswith("/worksheet"):
            out[s.get("name") or ""] = target
    return wb_part, out


def _cell_xml(ref_: str, v: object, style: str | None) -> str:
    s = f' s="{style}"' if style else ""
    if isinstance(v, bool):
        return f'<c r="{ref_}"{s} t="b"><v>{int(v)}</v></c>'
    if isinstance(v, (int, float)):
        return f'<c r="{ref_}"{s}><v>{_num(v)}</v></c>'
    t = escape(str(v))
    return (f'<c r="{ref_}"{s} t="inlineStr"><is><t xml:space="preserve">'
            f'{t}</t></is></c>')


def _unsupported(part: str, why: str) -> Exception:
    from kit.contract import HarnessError
    return HarnessError(msg("workbook_patch_unsupported",
                            f"{part}: {why}; the copy is not written",
                            part=part, reason=why))


def _merge(body: str, pattern: re.Pattern, todo: dict[int, object],
           key, new, edit) -> str:
    """`body` with the items of `todo` (position -> payload) set: an
    element of `pattern` at that position is replaced by edit(match,
    payload), a missing one is inserted by new(position, payload) in
    order; everything between the elements stays as it is."""
    out, pos = [], 0
    for m in pattern.finditer(body):
        k = key(m)
        out.append(body[pos:m.start()])
        for x in sorted(t for t in todo if t < k):
            out.append(new(x, todo.pop(x)))
        out.append(edit(m, todo.pop(k)) if k in todo else m.group(0))
        pos = m.end()
    out.append(body[pos:])
    for x in sorted(todo):
        out.append(new(x, todo.pop(x)))
    return "".join(out)


def _edit_row(row_xml: str, r: int, cells: dict[int, object]) -> str:
    """A <row> with `cells` (col -> value) set, in column order; a set
    cell keeps its style."""
    if row_xml.endswith("/>"):
        head, body = row_xml[:-2].rstrip() + ">", ""
    else:
        cut = row_xml.index(">") + 1
        head, body = row_xml[:cut], row_xml[cut:-len("</row>")]

    def edit(m, v):
        st = _STYLE.search(m.group(0)[:m.group(0).index(">")])
        return _cell_xml(m.group(1), v, st.group(1) if st else None)
    body = _merge(body, _CELL, dict(cells),
                  lambda m: split_ref(m.group(1))[1],
                  lambda k, v: _cell_xml(ref(r, k), v, None), edit)
    return _spans(head, cells) + body + "</row>"


def _spans(head: str, cells: dict[int, object]) -> str:
    m = re.search(r'\bspans="(\d+):(\d+)"', head)
    if not m:
        return head
    lo, hi = int(m.group(1)), int(m.group(2))
    lo, hi = min([lo, *cells]), max([hi, *cells])
    return head[:m.start()] + f'spans="{lo}:{hi}"' + head[m.end():]


def _edit_sheet(xml: str, part: str, sets: list[Set]) -> str:
    if re.search(r"<\w+:sheetData\b", xml):
        raise _unsupported(part, "its cells sit under a namespace prefix")
    by_row: dict[int, dict[int, object]] = {}
    for s in sets:
        r, c = split_ref(s.ref)
        by_row.setdefault(r, {})[c] = s.value
    m = re.search(r"<sheetData\s*/>", xml)
    if m:
        xml = xml[:m.start()] + "<sheetData></sheetData>" + xml[m.end():]
    a = xml.index("<sheetData")
    a = xml.index(">", a) + 1
    b = xml.index("</sheetData>", a)
    data = _merge(xml[a:b], _ROW, by_row, lambda m: int(m.group(1)),
                  lambda k, v: _edit_row(f'<row r="{k}"/>', k, v),
                  lambda m, v: _edit_row(m.group(0), int(m.group(1)), v))
    xml = xml[:a] + data + xml[b:]
    return _dimension(xml, sets)


def _dimension(xml: str, sets: list[Set]) -> str:
    m = re.search(r'<dimension\s+ref="([A-Z]+\d+)(?::([A-Z]+\d+))?"', xml)
    if not m:
        return xml
    r1, c1 = split_ref(m.group(1))
    r2, c2 = split_ref(m.group(2) or m.group(1))
    for s in sets:
        r, c = split_ref(s.ref)
        r1, c1, r2, c2 = min(r1, r), min(c1, c), max(r2, r), max(c2, c)
    new = f'<dimension ref="{ref(r1, c1)}:{ref(r2, c2)}"'
    return xml[:m.start()] + new + xml[m.end():]


_AFTER_CALC = ("oleSize", "customWorkbookViews", "pivotCaches", "smartTagPr",
               "smartTagTypes", "webPublishing", "fileRecoveryPr",
               "webPublishObjects", "extLst")


def _full_calc(xml: str) -> str:
    m = re.search(r"<calcPr\b[^>]*?/?>", xml)
    if m:
        tag = m.group(0)
        if "fullCalcOnLoad=" in tag:
            tag = re.sub(r'fullCalcOnLoad="[^"]*"', 'fullCalcOnLoad="1"', tag)
        else:
            end = -2 if tag.endswith("/>") else -1
            tag = tag[:end].rstrip() + ' fullCalcOnLoad="1"' + tag[end:]
        return xml[:m.start()] + tag + xml[m.end():]
    at = min((xml.index(f"<{t}") for t in _AFTER_CALC if f"<{t}" in xml),
             default=xml.rindex("</workbook>"))
    return xml[:at] + '<calcPr fullCalcOnLoad="1"/>' + xml[at:]


def apply(src: bytes, p: Plan) -> bytes:
    """The copy of `src` with p.apply set (module doc); `src` must be the
    file p was planned on."""
    wb = read(src)
    if wb.sha256 != p.base_sha:
        raise ValueError("apply(): the plan was made on another file")
    z = _Zip(src, "<base>")
    wb_part, sheets = _parts(z)
    edits: dict[str, list[Set]] = {}
    for s in p.apply:
        edits.setdefault(sheets[s.sheet], []).append(s)
    new: dict[str, bytes] = {}
    for part, sets in edits.items():
        new[part] = _edit_sheet(z.bytes(part).decode("utf-8"), part,
                                sets).encode("utf-8")
    if edits:
        new[wb_part] = _full_calc(z.bytes(wb_part).decode("utf-8")
                                  ).encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(src)) as zin, \
            zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            data = new.get(info.filename)
            if data is None:
                data = zin.read(info.filename)
            ni = zipfile.ZipInfo(info.filename, date_time=STAMP)
            ni.compress_type = info.compress_type
            ni.external_attr = info.external_attr
            zout.writestr(ni, data)
    return out.getvalue()


# ---- placing a harness's results by the map --------------------------------

def table_sets(wb: Workbook, m: wm.Map, table_id: str,
               rows: dict[str, dict], owner: str
               ) -> tuple[list[Set], list[Msg]]:
    """The cells of `rows` ({key: {field: value}}) in the table `table_id`
    for the columns `owner` writes (module doc), and the issues."""
    m = wm.confirmed(m)
    spec = m.table(table_id)
    issues: list = []
    if spec is None:
        return [], [msg("workbook_patch_table_unknown",
                        f"{table_id} is not a confirmed table of the map",
                        table_id=table_id)]
    cols = m.columns_of(table_id)
    loc = locate(wb, spec, cols, issues)
    if loc is None:
        return [], [m_ for _, _, m_ in issues]
    outs = [c for c in cols if c["direction"] in ("out", "both")
            and c["owner"] == owner]
    sheet = loc.sheet.name
    place: dict[str, int] = {}
    nxt = max(c.col for c in loc.columns) + 1
    sets: list[Set] = []
    for c in outs:
        hit = next((k.col for k in loc.columns
                    if norm(k.path) == norm(c["header"])
                    or norm(k.header) == norm(c["header"])), None)
        if hit is None:
            hit, nxt = nxt, nxt + 1
            sets.append(Set(sheet, ref(loc.header_row, hit), c["header"],
                            c["field"]))
        place[c["field"]] = hit
    seen = set()
    for key, occ, r, _ in keyed_rows(loc, issues):
        vals = rows.get(key)
        if occ != 1 or vals is None:
            continue
        seen.add(key)
        for f, col in place.items():
            if f in vals and vals[f] is not None:
                sets.append(Set(sheet, ref(r, col), vals[f], f))
    out: list[Msg] = []
    gone = [k for k in rows if k not in seen]
    if gone:
        out.append(msg("workbook_patch_keys_missing",
                       f"{table_id}: {len(gone)} key(s) the harness has "
                       f"are not rows of the sheet; not added",
                       table_id=table_id, count=len(gone)))
    return sets, out


def cell_sets(m: wm.Map, values: dict, owner: str
              ) -> tuple[list[Set], list[Msg]]:
    """The cells of each confirmed cells.tsv row `owner` writes, from
    `values` ({field: value or [values]})."""
    sets: list[Set] = []
    out: list[Msg] = []
    for c in wm.confirmed(m).cells:
        if c["owner"] != owner or c["field"] not in values:
            continue
        spots = wm.cells_of(c["cell"])
        v = values[c["field"]]
        vs = list(v) if isinstance(v, (list, tuple)) else [v]
        if len(vs) != len(spots):
            out.append(msg("workbook_patch_values_length",
                           f"{c['field']}: {len(vs)} value(s) for the "
                           f"{len(spots)} cell(s) of {c['sheet']} "
                           f"{c['cell']}; not set", field=c["field"],
                           values=len(vs), cells=len(spots),
                           sheet=c["sheet"], cell=c["cell"]))
            continue
        for (r, k), x in zip(spots, vs):
            sets.append(Set(c["sheet"], f"{col_letters(k)}{r}", x,
                            c["field"]))
    return sets, out
