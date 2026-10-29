#!/usr/bin/env python3
"""kit.export_results: the `ads.results/2` rows (and the first version, for one release) from the report's current rows and the creatives' days, over the hand-made account of test_compute_demand (invented DEMO
ids, invented numbers). The cases are the video-ads skill pack's `export results`: one row per current report row, in the contract's columns, sorted by key; a creative's
stage from the life document; a fission score only for a creative that has earned a verdict, against the account's proven ones; blank is unknown, never 0; the rows pass
the playbook's schema and are written once; a part the file cannot be written from is refused by name.
"""

import json
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
import test_compute_demand as base  # noqa: E402
from kit import compute_life as cl, contracts, export_results as er, messages  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

AT = "2026-10-29T08:00:00Z"
SCHEMA = contracts.schema(er.KIND, er.VERSION)


def row(code, nk, frm="2026-09-01", to="2026-09-30", **kw):
    r = {"creative_code": code, "platform": "meta", "account": "ACC-1", "ref_kind": "ad_id", "ref_value": f"ad-{code}", "unit_id": "", "placement": "", "date_from": frm,
         "date_to": to, "nk": nk, "exported_at": "2026-10-20T06:00:00+08:00", "complete": True, "settled": True, "restated": False,
         "currency": "CNY", "spend": 600.0, "impressions": 12000.0, "clicks": 240.0, "conversions": 90.0, "gmv": 5400.5, "ctr": 0.02, "roi": 9.0}
    r.update(kw)
    return r


def refused(src, k, at=AT):
    try:
        er.compute(src, k, at=at)
    except Exception as e:  # noqa: BLE001
        f = messages.failure(e)
        return f["code"], f["params"].get("part")
    return None, None


def refused_v(src, k, version, at=AT):
    try:
        er.compute(src, k, at=at, version=version)
    except Exception as e:  # noqa: BLE001
        f = messages.failure(e)
        return f["code"], f["params"].get("part")
    return None, None


def main() -> int:
    _shop.use()
    _shop.data_dir()
    k = base.thresholds()
    cr = base.account()
    cr["WIN-0"] = {**cr["WIN-0"], "days": base.days(30, conv=6.0)}              # a stronger winner and a weaker one: the scores differ
    cr["WIN-1"] = {**cr["WIN-1"], "days": base.days(30, conv=1.5)}
    life = cl.Source(cr)
    rows = [row(c, f"nk-{c}-{n}", **({"date_from": "2026-10-01", "date_to": "2026-10-15", "restated": True} if n else {})) for c in cr for n in (0, 1)]
    rows.append(row("GHOST", "nk-ghost"))
    random.Random(7).shuffle(rows)

    print("[1] the rows are the contract's columns, sorted by key")
    doc = er.compute(er.Source(rows, life), k, at=AT)
    out = doc["rows"]
    check("the module's columns are the schema's, in its order, and its optional ones are the schema's too",
          list(er.COLUMNS) == SCHEMA["x-columns"] and set(er.OPTIONAL) == set(SCHEMA["properties"]) - set(SCHEMA["x-columns"]) and set(er.REQUIRED) == set(SCHEMA["required"]), (er.COLUMNS, er.OPTIONAL))
    check("one row per report row, nothing dropped, sorted by creative, then key", len(out) == len(rows) == 21 and doc["counts"] == {"rows": 21, "creatives": 11}
          and [r["creative_code"] for r in out] == sorted(r["creative_code"] for r in rows) and [(r["creative_code"], r["date_from"]) for r in out] == sorted((r["creative_code"], r["date_from"]) for r in rows),
          doc["counts"])
    first = next(r for r in out if r["creative_code"] == "DUD-0")
    check("flags are 1 and 0, a whole number has no point, a decimal keeps it, a count the platform did not give is blank (unknown, never 0)",
          first["complete"] == "1" and first["restated"] == "0" and first["spend"] == "600" and first["gmv"] == "5400.5" and first["currency"] == "CNY" and first["ctr"] == "0.02" and first["plays"] is None
          and first["net_conversions"] is None, first)
    check("the document is plain data and every warning has a code", json.dumps(doc) and len(doc["warnings"]) == len(doc["warning_codes"]))

    print("[2] a creative's stage, and a score only for one that has a verdict")
    lf = {r["creative"]: r for r in cl.compute(life, k)["rows"]}
    st = {r["creative_code"]: (r["stage"], r["stage_reason"], r["fission"], r["scored_at"]) for r in out}
    check("each row's stage is its creative's state in the life document", all(st[c][0] == lf[c]["state"] for c in cr) and st["WIN-0"][0] == "mature" and st["DUD-0"][0] == "parked"
          and st["NEW"][0] == "testing", {c: v[0] for c, v in st.items()})
    check("the reason of the state is the stage_reason", st["DUD-0"][1] == lf["DUD-0"]["reason"] is not None, st["DUD-0"])
    check("a creative with a report row the days do not know has no stage, no score", st["GHOST"] == (None, None, None, None), st["GHOST"])
    check("a creative that has not earned a verdict (parked, testing) is unscored: blank, never 0", st["DUD-0"][2] is None and st["NEW"][2] is None and st["DUD-0"][3] is None, (st["DUD-0"], st["NEW"]))
    score = {c: float(st[c][2]) for c in cr if st[c][2] is not None}
    check("the six winners are scored, between 0 and 1 with two decimals, the stronger above the weaker, and stamped with the time given",
          set(score) == {f"WIN-{i}" for i in range(6)} and all(0 <= v <= 1 for v in score.values()) and score["WIN-0"] > score["WIN-5"] > score["WIN-1"] and st["WIN-0"][3] == AT
          and all(len(st[c][2].split(".")[1]) == 2 for c in score), score)
    check("both rows of a creative carry its score", len({r["fission"] for r in out if r["creative_code"] == "WIN-0"}) == 1)
    check("the summary says how many were scored, when, against which benchmark, and what was left out", doc["scored"] == 6 and doc["scored_at"] == AT and doc["benchmark"]["n"] == 6
          and sum(doc["unscored"].values()) == 4 and len(doc["scores"]) == 6, (doc["scored"], doc["benchmark"], doc["unscored"]))
    check("the scores are kit.fission's own", {s["creative"]: s["fission"] for s in doc["scores"]} == {c: round(v, 2) for c, v in score.items()}, doc["scores"])

    print("[3] the rows pass the playbook's schema and are written once")
    body = [{c: v for c, v in r.items()} for r in out]
    out_dir = Path(tmp_dir("export-results-"))
    path = contracts.write(er.KIND, er.VERSION, body, out_dir / "results.tsv")
    read = contracts.read(path, er.KIND, er.VERSION, "results-test")
    byc = {}
    for r in read.body:
        byc.setdefault(r["creative_code"], r)
    check("a reader gets the rows back: a score as a number with its time, a creative without one blank, the counts as numbers",
          len(read.body) == 21 and byc["WIN-0"]["fission"] == score["WIN-0"] and byc["WIN-0"]["scored_at"] == AT and byc["DUD-0"]["fission"] is None and byc["DUD-0"]["spend"] == 600.0
          and byc["DUD-0"]["plays"] is None and read.columns[-3:] == ("fission", "scored_at", "stage_reason"), (read.columns, byc["WIN-0"]))
    shuffled = list(rows)
    random.Random(99).shuffle(shuffled)
    again = er.compute(er.Source(shuffled, life), k, at=AT)["rows"]
    check("the same rows in another order are the same bytes: writing them again is a no-op", contracts.render(er.KIND, er.VERSION, again) == contracts.render(er.KIND, er.VERSION, out)
          and contracts.write(er.KIND, er.VERSION, again, path) == path)

    print("[4] the facts only, and an account too young for a benchmark")
    facts = er.compute(er.Source(rows), k, at=AT)
    check("without the creatives' days the rows are the facts only: no stage, no score, and the file has no score column", all(r["stage"] is None and r["fission"] is None for r in facts["rows"])
          and facts["scored"] == 0 and facts["scored_at"] is None and facts["benchmark"] is None, facts["counts"])
    kept = er.compute(er.Source([row("WIN-0", "n1", stage="doubt")]), k, at=AT)["rows"][0]
    check("a stage the pack gave is kept when the days are not given", kept["stage"] == "doubt", kept)
    f_path = contracts.write(er.KIND, er.VERSION, facts["rows"], out_dir / "facts.tsv")
    check("the facts-only file has the contract's columns and no optional one", contracts.read(f_path, er.KIND, er.VERSION, "results-test").columns == tuple(SCHEMA["x-columns"]))
    two = {c: v for c, v in cr.items() if c in ("WIN-0", "WIN-1", "DUD-0", "NEW")}
    thin = er.compute(er.Source([row(c, f"n-{c}") for c in two], cl.Source(two)), k, at=AT)
    check("two proven creatives are too few for a benchmark: none is scored, the stage is still given, and the warning says 2 of 3",
          thin["scored"] == 0 and thin["benchmark"] is None and all(r["stage"] for r in thin["rows"]) and [w["code"] for w in thin["warning_codes"]] == ["fission_benchmark_insufficient"]
          and thin["warning_codes"][0]["params"] == {"have": 2, "need": 3}, thin["warning_codes"])
    nothing = er.compute(er.Source([], cl.Source({})), k, at=AT)
    check("no row and no creative: an empty list, no failure", nothing["rows"] == [] and nothing["counts"] == {"rows": 0, "creatives": 0} and nothing["scored"] == 0)

    print("[5] a Source the file cannot be written from is refused, naming the part")
    good = row("WIN-0", "n1")

    def one(**kw):
        return er.Source([{**good, **kw}], life)
    bad = {"a row without its nk": ("rows[0]", er.Source([{x: v for x, v in good.items() if x != "nk"}])),
           "a blank creative code": ("rows[0]", one(creative_code=" ")),
           "a column the contract does not have": ("rows[0]", one(spend_usd=3.0)),
           "a flag that is a word": ("rows[0].settled", one(settled="yes")),
           "a negative count": ("rows[0].clicks", one(clicks=-1.0)),
           "a count that is text": ("rows[0].impressions", one(impressions="12")),
           "a ratio that is infinite": ("rows[0].roi", one(roi=float("inf"))),
           "a day that is not a day": ("rows[0].date_to", one(date_to="30 Sep")),
           "a period that ends before it begins": ("rows[0].date_from", one(date_from="2026-10-02", date_to="2026-10-01")),
           "a time that is a number": ("rows[0].exported_at", one(exported_at=5)),
           "an nk on two rows": ("rows[1].nk", er.Source([good, {**good, "ref_value": "other"}])),
           "rows that are not a list": ("rows", er.Source({"a": 1})),
           "a row that is not a dict": ("rows[0]", er.Source([["x"]])),
           "creatives without days": ("creatives[X]", er.Source([good], cl.Source({"X": {"label": "x"}})))}
    got = {name: refused(s, k) for name, (_, s) in bad.items()}
    check("each is compute_input_invalid, naming its part", all(c == "compute_input_invalid" for c, _ in got.values()) and [p for _, p in got.values()] == [x for x, _ in bad.values()], got)
    check("a time that is not given is refused as the time", refused(er.Source([good]), k, at=" ") == ("compute_input_invalid", "at"))
    miss = [c for c in er.REQUIRED if refused(er.Source([{x: v for x, v in good.items() if x != c}]), k)[1] != "rows[0]"]
    check("every required column is named when it is missing", miss == [], miss)

    print("[6] the currency, and the first version for the release in which a consumer has not moved")
    bare = [{x: v for x, v in r.items() if x != "currency"} for r in rows]
    own = er.compute(er.Source(bare, life, currency="HKD"), k, at=AT)["rows"]
    check("a row with no currency of its own takes the Source's", {r["currency"] for r in own} == {"HKD"} and len(own) == len(rows), {r["currency"] for r in own})
    two = er.compute(er.Source([{**bare[0], "currency": "USD"}, {**bare[1], "nk": "other"}], currency="HKD"), k, at=AT)["rows"]
    check("a row with its own currency keeps it beside one that takes the Source's, so a file may hold more than one", sorted(r["currency"] for r in two) == ["HKD", "USD"], [r["currency"] for r in two])
    check("the file with several currencies passes the schema and is read back as written",
          [r["currency"] for r in contracts.read(contracts.write(er.KIND, er.VERSION, two, out_dir / "multi.tsv"), er.KIND, er.VERSION, "multi").body] == [r["currency"] for r in two])
    nocur = [{x: v for x, v in r.items() if x != "currency"} for r in (good,)]
    check("version 2 without a currency anywhere is refused, naming the row", refused(er.Source(nocur), k) == ("compute_input_invalid", "rows[0]"))
    bad_cur = {"a Source currency in lower case": ("currency", er.Source([good], currency="cny")), "a Source currency that is a number": ("currency", er.Source([good], currency=156)),
               "a Source currency of four letters": ("currency", er.Source([good], currency="RMBB")), "a row currency in lower case": ("rows[0].currency", one(currency="cny")),
               "a row currency that is a word": ("rows[0].currency", one(currency="yuan")), "a blank row currency": ("rows[0]", one(currency=" "))}
    got = {n: refused(s, k) for n, (_, s) in bad_cur.items()}
    check("a currency that is not three capitals is compute_input_invalid, naming its part", all(c == "compute_input_invalid" for c, _ in got.values())
          and [p for _, p in got.values()] == [x for x, _ in bad_cur.values()], got)

    v1 = er.compute(er.Source(rows, life), k, at=AT, version=1)
    S1 = contracts.schema(er.KIND, 1)
    old = {"spend": "spend_cny", "gmv": "gmv_cny", "net_gmv": "net_gmv_cny", "cpa": "cpa_cny"}
    check("version 1 is the first contract's columns exactly: the four money columns named for CNY, no currency", all(list(r) == [*S1["x-columns"], *er.OPTIONAL] for r in v1["rows"])
          and not any("currency" in r for r in v1["rows"]), list(v1["rows"][0]))
    check("... and the same rows as version 2 but for those names and the currency column", [{old.get(c, c): v for c, v in r.items() if c != "currency"} for r in out] == v1["rows"])
    p1 = contracts.write(er.KIND, 1, v1["rows"], out_dir / "results-v1.tsv")
    check("the first version is written and read as ads.results/1", contracts.read(p1, er.KIND, 1, "v1").body[0]["spend_cny"] == 600.0
          and p1.read_text("utf-8").startswith("# ads.results/1\n") and path.read_text("utf-8").startswith("# ads.results/2\n"))
    check("the other counts of the summary do not depend on the version", {x: v1[x] for x in ("counts", "scored", "scored_at", "benchmark", "unscored")}
          == {x: doc[x] for x in ("counts", "scored", "scored_at", "benchmark", "unscored")})
    unknown = er.compute(er.Source([{x: v for x, v in r.items() if x != "currency"} for r in rows], life), k, at=AT, version=1)
    check("a pack that does not know its currency still gets version 1 as before (the file does not say which money it holds)", unknown["rows"] == v1["rows"])
    cny = er.compute(er.Source(bare, currency="CNY"), k, at=AT, version=1)
    check("a ledger that says CNY is written as version 1", len(cny["rows"]) == len(rows) and "spend_cny" in cny["rows"][0])
    foreign = {"a Source in HKD": ("rows[0].currency", er.Source([{x: v for x, v in good.items() if x != "currency"}], currency="HKD")),
               "a row in USD": ("rows[0].currency", one(currency="USD"))}
    got = {n: refused_v(s, k, 1) for n, (_, s) in foreign.items()}
    check("version 1 refuses money that is not CNY rather than naming it CNY", all(c == "compute_input_invalid" for c, _ in got.values())
          and [p for _, p in got.values()] == [x for x, _ in foreign.values()], got)
    check("a version that does not exist is refused as the version", refused_v(er.Source([good]), k, 3) == ("compute_input_invalid", "version")
          and refused_v(er.Source([good]), k, "2") == ("compute_input_invalid", "version"))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
