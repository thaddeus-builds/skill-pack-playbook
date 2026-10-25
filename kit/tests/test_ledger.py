#!/usr/bin/env python3
"""kit.ledger: settled days, restatement and one currency, on the video-ads skill pack's import scenarios (a platform whose day is
Asia/Shanghai's and whose orders settle in 7 days).

  * a day is partial in a same-day export, complete after, settled 7 days after;
  * a later export with the same numbers adds nothing, unless it finishes a partial day or settles a complete one;
  * different numbers add a row, and the current row is the newest export, not the last import;
  * a row that would count spend twice refuses the whole import (other plan or period of one entity; a blank plan stands for all);
  * two currencies under one owner refuse the import; a retraction brings back what a later import left out.
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import ledger  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

TZ = "Asia/Shanghai"
M = ("spend", "impressions", "conversions")


def row(day, spend=10.0, ref="7001", unit="P1", to=None, **kw):
    return {"platform": "pf", "account": "A", "ref_kind": "material_id", "ref_value": ref, "unit_id": unit, "placement": "",
            "date_from": day, "date_to": to or day, "spend": spend, "impressions": 100, "conversions": 1.0, "owner": "C1", **kw}


def book():
    return ledger.Book(TZ, 7, M)


def raises(fn, exc):
    try:
        fn()
    except exc as e:
        return e
    return None


def main() -> int:
    print("[1] the day")
    check("a same-day export holds a partial day (the 20th at 05:00 UTC is 13:00 in Shanghai)",
          ledger.day_state("2026-09-20T05:00:00Z", "2026-09-20", TZ, 7) == "partial")
    check("the platform's calendar decides: 17:00 UTC on the 20th is already the 21st in Shanghai", ledger.is_complete("2026-09-20T17:00:00Z", "2026-09-20", TZ))
    check("complete the day after, settled seven days after", ledger.day_state("2026-09-21T05:00:00Z", "2026-09-20", TZ, 7) == "complete"
          and ledger.day_state("2026-09-26T05:00:00Z", "2026-09-20", TZ, 7) == "complete"
          and ledger.day_state("2026-09-27T05:00:00Z", "2026-09-20", TZ, 7) == "settled")

    print("[2] restatement: a later export that confirms the same numbers finishes a partial day")
    b = book()
    first = b.add([row("2026-09-20")], "2026-09-20T05:00:00Z")
    check("the first export is new, and its day is partial", first["rows_new"] == 1 and b.current()[0]["state"] == "partial", b.current())
    more = [row("2026-09-20"), row("2026-09-21")]
    nxt = b.add(more, "2026-09-21T05:00:00Z")
    check("the 20th is re-recorded (it is now finished); the 21st is new", nxt["rows_new"] == 2 and nxt["rows_unchanged"] == 0, nxt)
    third = b.add(more, "2026-09-22T05:00:00Z")
    check("the 21st is finished too; the 20th needs nothing", third["rows_new"] == 1 and third["rows_unchanged"] == 1, third)
    fourth = b.add(more, "2026-09-23T05:00:00Z")
    check("nothing more once both are finished", fourth["rows_new"] == 0 and fourth["rows_unchanged"] == 2, fourth)

    print("[3] restatement: the same numbers settle a day once its orders cannot move")
    b = book()
    two = [row("2026-09-20"), row("2026-09-21")]
    check("both days finished, none settled", b.add(two, "2026-09-22T05:00:00Z")["rows_new"] == 2
          and [r["state"] for r in b.current()] == ["complete", "complete"])
    again = b.add(two, "2026-09-24T05:00:00Z")
    check("the same numbers, still too early: nothing", again["rows_new"] == 0 and again["rows_unchanged"] == 2, again)
    late = b.add(two, "2026-09-27T05:00:00Z")
    check("the 20th is 7 days old, the 21st is not: one row", late["rows_new"] == 1 and late["rows_unchanged"] == 1
          and [r["state"] for r in b.current()] == ["settled", "complete"], late)
    last = b.add(two, "2026-09-28T05:00:00Z")
    check("the 21st settles a day later", last["rows_new"] == 1 and [r["state"] for r in b.current()] == ["settled", "settled"], last)
    check("then nothing more to say", b.add(two, "2026-10-05T05:00:00Z")["rows_new"] == 0)

    print("[4] restatement: other numbers, and the newest export wins")
    b = book()
    b.add([row("2026-09-10", spend=10.0)], "2026-09-12T05:00:00Z")
    b.add([row("2026-09-10", spend=12.5)], "2026-09-13T05:00:00Z")
    check("the restated number is the current one", [r["spend"] for r in b.current()] == [12.5], b.current())
    b.add([row("2026-09-10", spend=11.0)], "2026-09-12T08:00:00Z")      # an older export landed later
    check("the current row is the newest by the export's time, not by import order", [r["spend"] for r in b.current()] == [12.5], b.current())

    print("[5] double counting")
    b = book()
    b.add([row("2026-09-10", to="2026-09-12")], "2026-09-15T05:00:00Z")
    e = raises(lambda: b.add([row("2026-09-12", to="2026-09-14")], "2026-09-16T05:00:00Z"), ledger.Overlap)
    check("overlapping periods of one entity in one plan refuse the import", e is not None and e.clash[0]["id"] == "C1", e)
    e = raises(lambda: b.add([row("2026-09-11", unit="")], "2026-09-16T05:00:00Z"), ledger.Overlap)
    check("a blank plan stands for all plans: refused", e is not None)
    check("another plan on other days is fine", b.add([row("2026-09-13", unit="P2")], "2026-09-16T05:00:00Z")["rows_new"] == 1)
    check("another entity on the same days is fine", b.add([row("2026-09-10", ref="8002", owner="C2")], "2026-09-16T05:00:00Z")["rows_new"] == 1)
    n = len(b.imports)
    raises(lambda: b.add([row("2026-09-11")], "2026-09-17T05:00:00Z"), ledger.Overlap)
    check("a refusal changes nothing", len(b.imports) == n)
    e = raises(lambda: b.add([row("2026-09-30"), row("2026-09-30")], "2026-10-01T05:00:00Z"), ValueError)
    check("two rows of one key in a file are refused, not summed", e is not None and "same key" in str(e), e)
    check("the same entity reached by a name in one export and an id in another still double counts",
          raises(lambda: b.add([row("2026-09-11", ref="name-x", ref_kind="name")], "2026-10-02T05:00:00Z"), ledger.Overlap) is not None)

    print("[6] one currency")
    b = book()
    b.add([row("2026-09-10", currency="HKD")], "2026-09-12T05:00:00Z")
    e = raises(lambda: b.add([row("2026-09-11", currency="TWD")], "2026-09-13T05:00:00Z"), ledger.CurrencyMix)
    check("two currencies under one creative: nothing is added", e is not None and e.owners == {"C1": ["HKD", "TWD"]} and len(b.imports) == 1, e)
    check("another creative in another currency is fine", b.add([row("2026-09-11", ref="8002", owner="C2", currency="TWD")], "2026-09-13T05:00:00Z")["rows_new"] == 1)
    check("single_currency on rows: only the owners with two or more", ledger.single_currency(
        [{"owner": "a", "currency": "X"}, {"owner": "a", "currency": "Y"}, {"owner": "b", "currency": "X"}, {"owner": None, "currency": "Z"}]) == {"a": ["X", "Y"]})

    print("[7] retraction")
    b = book()
    one = b.add([row("2026-09-20")], "2026-09-22T05:00:00Z")["import_id"]
    two = b.add([row("2026-09-20")], "2026-09-23T05:00:00Z")
    check("a later export with the same numbers left the row out", two["rows_new"] == 0 and len(b.current()) == 1)
    r = b.retract(one)
    check("retracting the first brings the row back under the later import: that export still says it", r["rows_restored"] == 1
          and [c["import_id"] for c in b.current()] == [2], b.current())
    check("a retracted import is gone from the current set", b.retract(2)["rows_restored"] == 0 and b.current() == [])
    check("retracting twice, or an unknown import, is refused", raises(lambda: b.retract(2), ValueError) is not None and raises(lambda: b.retract(9), ValueError) is not None)

    print("[8] keys and fingerprints")
    check("the key follows the identity fields, not the numbers", ledger.natural_key(row("2026-09-10", spend=1.0)) == ledger.natural_key(row("2026-09-10", spend=9.0))
          and ledger.natural_key(row("2026-09-10")) != ledger.natural_key(row("2026-09-11")))
    check("the fingerprint follows the numbers", ledger.fingerprint(row("d", spend=1.0), M) != ledger.fingerprint(row("d", spend=2.0), M)
          and ledger.fingerprint(row("d"), M) == ledger.fingerprint(row("d", ref="other"), M))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
