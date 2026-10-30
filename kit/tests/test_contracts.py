#!/usr/bin/env python3
"""kit.contracts: a contract file's mark, its schema check, write once, read into raw.

  * the schemas in kit/contracts.d are byte for byte the playbook's contracts/; every
    example there is read, and written back out, without a problem;
  * write: the mark is the first line; a document that lacks a required field, has a
    wrong type, enum word or form is refused and nothing is on disk; the same bytes
    again are a no-op, other bytes under an existing name are refused and the file is
    untouched; a TSV takes its optional columns last, only when a row has one;
  * read: a file with another mark, another version, no mark, a missing field, a blank
    required cell or a ragged row is refused and not saved; a valid one is saved to raw
    as it came (the same bytes, a name carrying its hash), twice = one raw file; a field
    the schema does not name is ignored;
  * a pack that takes no `exchange` pack does not get the schemas (kit.tools.packs).
"""

import copy
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import contracts, raw  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.testing.check import check, finish, raises, tmp_dir  # noqa: E402
from kit.tools import packs, vendor  # noqa: E402

PLAYBOOK = _shop.PLAYBOOK
EXAMPLES = PLAYBOOK / "contracts" / "examples"


def code(fn) -> str | None:
    e = raises(fn, SkillPackError)
    return getattr(e.message, "code", None) if e else None


def example(name: str):
    text = (EXAMPLES / name).read_text("utf-8")
    kind, version = text.splitlines()[0][2:].split("/")
    return kind, int(version), text


def main() -> int:
    _shop.use()
    data = _shop.data_dir()
    out = Path(tmp_dir("contracts-"))

    print("[1] the schemas and the examples")
    here = {p.name: p.read_bytes() for p in contracts.SCHEMAS.glob("*.schema.json")}
    there = {p.name: p.read_bytes() for p in (PLAYBOOK / "contracts").glob("*.schema.json")}
    check("kit/contracts.d holds the playbook's contracts/ schemas, byte for byte",
          here == there and len(here) == 14,
          sorted(set(here) ^ set(there)) or [n for n in here if here[n] != there.get(n)])
    examples = sorted(EXAMPLES.iterdir())
    check("an example for each of the fourteen", len(examples) == 14, examples)
    bad = []
    for f in examples:
        kind, version, text = example(f.name)
        try:
            doc = contracts.read(f, kind, version, "ex")
            again = contracts.write(kind, version, doc.body, out / f.name)
            back = contracts.read(again, kind, version, "ex-back")
            if back.body != doc.body or doc.raw.read_bytes() != f.read_bytes():
                bad.append(f"{f.name}: differs after a round trip")
        except SkillPackError as e:
            bad.append(f"{f.name}: {e.message}")
    check("each example is read as it is, and written back out it reads the same", not bad, bad)

    print("\n[2] write: the first line, the check, once")
    kind, version, text = example("catalog-1.example.json")
    body = json.loads(text.split("\n", 1)[1])
    p = contracts.write(kind, version, body, out / "x" / "catalog.json")
    check("the first line is the mark; the body is the JSON; the folder is made",
          p.read_text("utf-8").splitlines()[0] == "# catalog/1"
          and json.loads(p.read_text("utf-8").split("\n", 1)[1]) == body, p)
    st, before = p.stat(), p.read_bytes()
    again = contracts.write(kind, version, body, p)
    check("the same bytes again: a no-op (same inode and mtime)",
          again == p and (p.stat().st_ino, p.stat().st_mtime_ns) == (st.st_ino, st.st_mtime_ns))
    changed = copy.deepcopy(body)
    changed["products"][0]["price"] = 300
    c = code(lambda: contracts.write(kind, version, changed, p))
    check("other bytes under that name: exchange_would_overwrite, the file untouched",
          c == "exchange_would_overwrite" and p.read_bytes() == before, c)
    check("no temp file is left", sorted(x.name for x in p.parent.iterdir()) == ["catalog.json"])

    def refused(mutate, label, expect="exchange_invalid"):
        doc = copy.deepcopy(body)
        mutate(doc)
        target = out / f"refused-{abs(hash(label))}.json"
        c = code(lambda: contracts.write(kind, version, doc, target))
        check(f"{label}: {expect}, nothing written", c == expect and not target.exists(), c)

    refused(lambda d: d["products"][0].pop("sku"), "a required field missing")
    refused(lambda d: d.pop("products"), "the list missing")
    refused(lambda d: d["products"][0].update(price="299"), "a number given as text")
    refused(lambda d: d["products"][0].update(availability="soon"), "a word outside an enum")
    refused(lambda d: d["products"][0].update(currency="hkd"), "a form the pattern refuses")
    refused(lambda d: d["products"][0].update(currency="HKD\n"), "a pattern's $ is the end of the text")
    refused(lambda d: d["products"][0]["promotions"][0].update(starts_on="2026-11-1"), "a day in the wrong form")
    refused(lambda d: d["products"][0].update(price=float("nan")), "NaN is not JSON")
    refused(lambda d: d.update(produced_at="2026-10-23T08:00:00"), "a time without its zone")
    doc = copy.deepcopy(body)
    doc["something_new"] = {"a": 1}
    doc["products"][0]["colour"] = "red"
    check("a field the schema does not name is written and read: it is ignored, not refused",
          contracts.read(contracts.write(kind, version, doc, out / "extra.json"), kind, version, "extra").body == doc)
    check("a kind this kit has no schema for: exchange_schema_unknown",
          code(lambda: contracts.write("nope", 1, {}, out / "n.json")) == "exchange_schema_unknown"
          and code(lambda: contracts.write("catalog", 2, {}, out / "n.json")) == "exchange_schema_unknown")

    print("\n[3] a TSV contract")
    kind, version, text = example("ads.results-1.example.tsv")
    doc = contracts.parse(text.encode(), kind, version)
    check("rows: a number cell is a float, a flag its text, a blank cell None",
          doc.body[0]["spend_cny"] == 1200.5 and doc.body[0]["settled"] == "1"
          and doc.body[1]["conversions"] is None and doc.body[1]["fission"] is None
          and doc.columns[0] == "creative_code" and doc.columns[-3:] == ("fission", "scored_at", "stage_reason"), doc.columns)
    required_only = [{k: v for k, v in r.items() if k in contracts.schema(kind, version)["x-columns"]} for r in doc.body]
    p = contracts.write(kind, version, required_only, out / "results.tsv")
    check("optional columns are written last, and only when a row has one",
          p.read_text("utf-8").splitlines()[1].split("\t") == list(contracts.schema(kind, version)["x-columns"]))
    withopt = [dict(required_only[0], fission=0.5, scored_at="2026-10-20T06:05:00+08:00"), required_only[1]]
    p2 = contracts.write(kind, version, withopt, out / "results-opt.tsv")
    check("... fission and scored_at appear once a row has them",
          p2.read_text("utf-8").splitlines()[1].split("\t")[-2:] == ["fission", "scored_at"])

    def tsv_refused(edit, label):
        lines = text.splitlines()
        edit(lines)
        c = code(lambda: contracts.parse(("\n".join(lines) + "\n").encode(), kind, version, "r.tsv"))
        check(f"{label}: exchange_invalid", c == "exchange_invalid", c)

    def cell(line, column, value):
        head = text.splitlines()[1].split("\t")
        cells = line.split("\t")
        cells[head.index(column)] = value
        return "\t".join(cells)
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "creative_code", "")), "a blank required cell")
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "settled", "yes")), "a flag that is not 0 or 1")
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "spend_cny", "lots")), "a count that is not a number")
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "spend_cny", "-3")), "a count below 0")
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "spend_cny", "nan")), "a count that is not finite")
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "date_from", "2026-10-1")), "a day in the wrong form")
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "fission", "1.5")), "a score above 1")
    tsv_refused(lambda ls: ls.__setitem__(2, ls[2] + "\textra"), "a ragged row")
    tsv_refused(lambda ls: ls.__setitem__(1, ls[1].replace("nk\t", "")), "a header without a column the schema needs")
    row = dict(required_only[0], spend_cny="12\t3")
    check("a cell with a tab is not written",
          code(lambda: contracts.write(kind, version, [row], out / "tab.tsv")) == "exchange_invalid"
          and not (out / "tab.tsv").exists())
    check("a column the schema does not have is not written either",
          code(lambda: contracts.write(kind, version, [dict(required_only[0], mood="x")], out / "mood.tsv"))
          == "exchange_invalid")
    wide = text.replace("\tstage_reason\n", "\tstage_reason\tnew_column\n").replace("\tconverted\n", "\tconverted\tnew\n") \
        .replace("\t\n", "\t\tnew\n", 1)
    check("a TSV with a column of a later version in it is read, the column kept as text",
          contracts.parse(wide.encode(), kind, version).body[0].get("new_column") == "new")

    print("\n[3b] ads.results/2: the same file with the money in the row's own currency")
    k1, v1, t1 = kind, version, text
    kind, version, text = example("ads.results-2.example.tsv")
    doc2 = contracts.parse(text.encode(), kind, version)
    s1, s2 = contracts.schema(k1, v1), contracts.schema(kind, version)
    names = {"spend_cny": "spend", "gmv_cny": "gmv", "net_gmv_cny": "net_gmv", "cpa_cny": "cpa"}
    check("the second version is the first with the four money columns renamed and `currency` after `restated`, nothing else moved",
          [names.get(c, c) for c in s1["x-columns"]] == [c for c in s2["x-columns"] if c != "currency"]
          and s2["x-columns"][s2["x-columns"].index("restated") + 1] == "currency" and "currency" in s2["required"]
          and set(s2["required"]) == {*s1["required"], "currency"}, s2["x-columns"])
    check("no column of the second version still says CNY", not [c for c in s2["x-columns"] if "cny" in c.lower()] and "currency" in s2["properties"])
    check("a row reads its currency and its money as numbers", doc2.body[0]["currency"] == "CNY" and doc2.body[0]["spend"] == 1200.5 and doc2.body[1]["cpa"] is None, doc2.body[0])
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "currency", "")), "a row without its currency")
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "currency", "cny")), "a currency in lower case")
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "currency", "RMB1")), "a currency of four letters")
    tsv_refused(lambda ls: ls.__setitem__(2, cell(ls[2], "spend", "-3")), "a spend below 0")
    usd = [dict(r, currency=c) for r, c in zip(doc2.body, ("USD", "HKD"))]
    check("a file may hold rows of more than one currency, and is written and read back as given",
          [r["currency"] for r in contracts.read(contracts.write(kind, version, usd, out / "multi.tsv"), kind, version, "multi").body] == ["USD", "HKD"])
    check("the first version's example is not read as the second, nor the second as the first",
          code(lambda: contracts.parse(t1.encode(), kind, version)) == "exchange_version_unknown" and code(lambda: contracts.parse(text.encode(), k1, v1)) == "exchange_version_unknown")

    print("\n[4] read: refused files are not saved, a valid one is saved as it came")
    cat = out / "x" / "catalog.json"
    kind, version = "catalog", 1
    raw_before = raw.listing("in")

    def put(name: str, content: str) -> Path:
        f = out / name
        f.write_text(content, encoding="utf-8")
        return f
    good = cat.read_text("utf-8")
    cases = {
        "a file with no mark": (good.split("\n", 1)[1], "exchange_mark_wrong"),
        "another contract's mark": (good.replace("# catalog/1", "# truth/1", 1), "exchange_mark_wrong"),
        "the old project's mark": (good.replace("# catalog/1", "# ccatalog/1", 1), "exchange_mark_wrong"),
        "another version": (good.replace("# catalog/1", "# catalog/2", 1), "exchange_version_unknown"),
        "an empty file": ("", "exchange_mark_wrong"),
        "a mark and nothing else": ("# catalog/1\n", "exchange_invalid"),
        "a body that is not JSON": ("# catalog/1\n{oops", "exchange_invalid"),
        "a missing field": (good.replace('"sku"', '"skew"'), "exchange_invalid"),
    }
    for label, (content, expect) in cases.items():
        c = code(lambda: contracts.read(put("r.json", content), kind, version, "in"))
        check(f"{label}: {expect}", c == expect, c)
    check("... and none of them is in raw", raw.listing("in") == raw_before, raw.listing("in"))
    check("not a UTF-8 file: exchange_unreadable",
          code(lambda: contracts.parse(b"\xff\xfe\x00", kind, version)) == "exchange_unreadable")
    check("a file that is not there: exchange_unreadable",
          code(lambda: contracts.read(out / "nothing.json", kind, version, "in")) == "exchange_unreadable")
    e = raises(lambda: contracts.parse(("# catalog/1\n" + json.dumps({"producer": "p"})).encode(), kind, version), SkillPackError)
    check("the error names the problems (the first line of them in params.detail)",
          e is not None and "products: missing" in e.message.params["detail"] and "produced_at" in e.message.params["detail"],
          e and e.message.params)

    r1 = contracts.read(cat, kind, version, "in")
    check("a valid file is saved to raw/<source>/ with the bytes it came in, under a name that carries its hash",
          r1.raw == data / "raw" / "in" / f"catalog-1.{r1.sha256[:12]}.json" and r1.raw.read_bytes() == cat.read_bytes()
          and r1.body["products"][0]["sku"] == "DEMO-LAMP", r1.raw)
    r2 = contracts.read(cat, kind, version, "in")
    check("read twice = one raw file", r2.raw == r1.raw and len(raw.listing("in")) == 1)
    tsv = contracts.read(out / "results.tsv", "ads.results", 1, "in")
    check("a TSV is saved as .tsv", tsv.raw.suffix == ".tsv" and tsv.raw.read_bytes() == (out / "results.tsv").read_bytes())

    print("\n[5] packs")
    kit = _shop.KIT
    table = packs.table(kit)
    known = set(table)
    check("contracts is a module of the exchange pack, and imports only base",
          table["contracts"] == "exchange"
          and all(table[m] in ("base", "exchange") for m in packs.imports((kit / "contracts.py").read_text("utf-8"), known)))
    taken = lambda *names: set(vendor.kit_files(kit, set(names)))          # noqa: E731
    check("its schemas travel with the exchange pack and with no other",
          packs.module_of("contracts.d/catalog-1.schema.json", known) == "contracts"
          and packs.module_of("message_codes.d/contracts.tsv", known) == "contracts"
          and "contracts.d/catalog-1.schema.json" in taken("base", "testkit", "exchange")
          and "contracts.py" in taken("base", "testkit", "exchange")
          and not [f for f in taken("base", "testkit") if "contracts" in f])
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
