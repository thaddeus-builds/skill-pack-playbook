#!/usr/bin/env python3
"""One human gate per client file (kit/file_gate.py), on the fake "shop"
harness (markets US/CA) with the SYNTHETIC influencer tracker's map
(kit/tests/_workbooks.py) and one value read from a cell.

  1. plan(): the rows and values a staged bundle confirms over the bundle in
     force, and the small binding (both bundles' versions, the row count,
     every value); a value `facts set` would refuse, a key the harness does
     not have and a market not onboarded are refused before any gate.
  2. ask() is one console ask through kit.pending's `staged=` hook: kind
     file, its gate the harness's verb, `expect` exactly plan()'s items; the
     console accepts it.
  3. confirm() at a terminal: one retype for the whole file; the value is
     written confirmed (changed_by <user>@tty, the file as its source,
     history action confirm).
  4. confirm() relayed: no code = the challenge, nothing written; the code
     for exactly this plan writes the new value @relay; the same code on a
     fresh plan is refused (the fact moved, so the version did).
  5. file_gate.py writes no message of its own (its refusals are facts' and
     workbook_map's codes).
"""

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
import _workbooks as X  # noqa: E402
from kit import db, file_gate, human, pending  # noqa: E402
from kit import workbook_map as WM  # noqa: E402
from kit.registry import FactKeys, Thresholds  # noqa: E402
from kit.testing.check import (capture, check, clean_env, finish,  # noqa: E402
                               raises, tmp_dir)

CFG = _shop.use()
DATA = _shop.data_dir()
DB = DATA / CFG.db_file
SECRET = CFG.env("CONFIRM_CODE_SECRET")
SPEC = db.with_human({}, version=1)
USER = __import__("getpass").getuser()
VERB = ["workbook", "confirm", "v1"]

FIX = Path(tmp_dir("file-gate-fixtures-"))
(FIX / "fact_keys.tsv").write_text(
    "key\tgroup\ttype\tunit\tmin\tmax\tlabel_en\tlabel_zh\twhy\n"
    "unit_cost\tcost\tnumber\tUSD\t0\t50\tUnit cost\t单位成本\tmargin\n",
    encoding="utf-8")
(FIX / "constants.tsv").write_text(
    "name\tdefault\tunit\tmin\tmax\tgroup\tlabel_en\tlabel_zh\texplain\twhy\n"
    "max_step\t0.2\tratio\t0\t1\tpacing\tMax step\t最大步长\tsize\tsafety\n",
    encoding="utf-8")
KEYS = FactKeys(FIX / "fact_keys.tsv")
TH = Thresholds(FIX / "constants.tsv")
VALUES = ("key\tmarket\tvalue\tsheet\tcell\tstatus\tnote\n"
          "unit_cost\tUS\t4.20\tBudget\tF14\tproposed\tF13*38 (SYNTHETIC)\n")


def files(values: str = VALUES) -> dict[str, str]:
    return {"tables.tsv": X.IM_TABLES, "columns.tsv": X.IM_COLUMNS,
            "values.tsv": values}


def env(secret: bool = False) -> dict:
    return clean_env(**{CFG.env("DATA_DIR"): str(DATA),
                        CFG.env("AUTH_ENV_PATHS"): "none",
                        **({SECRET: "s3cret"} if secret else {})})


def con() -> sqlite3.Connection:
    return sqlite3.connect(DB)


def fact(key: str = "unit_cost", market: str = "US"):
    with closing(con()) as c:
        return c.execute("SELECT value, is_assumption, source, changed_by "
                         "FROM client_facts WHERE market=? AND key=?",
                         (market, key)).fetchone()


def ecode(e) -> str | None:
    return getattr(getattr(e, "message", None), "code", None)


def gate(p: dict, *, tty=None, secret=False, code=None) -> tuple:
    """file_gate.confirm(p) as a harness verb would run it: (result, error)."""
    box: dict = {}

    def main(_argv):
        with closing(db.connect(SPEC)) as c:
            try:
                box["out"] = file_gate.confirm(
                    SPEC, c, p, verb=VERB, reason="the owner's yes",
                    code=code, relay_user="web:owner" if code else None,
                    relay_at="2026-10-11T10:00:00Z" if code else None,
                    source="workbook:synthetic Budget!F14")
            except Exception as e:      # noqa: BLE001 (the test reads it)
                box["err"] = e
        return 0
    capture(main, [], env=env(secret), tty_answers=tty)
    return box.get("out"), box.get("err")


def setup() -> None:
    capture(lambda a: db.connect(SPEC).close(), [], env=env())
    with closing(con()) as c:
        c.execute("INSERT INTO client_facts (market, key, value, "
                  "is_assumption, source, updated_at, changed_by) VALUES "
                  "('US', 'market_declared', 'US', 0, 't', '2026-09-22', "
                  "'t@tty')")
        c.commit()


def test_plan() -> dict:
    print("[1] plan(): what one yes confirms, refused before any gate")
    with closing(con()) as c:
        p = file_gate.plan(c, files(), None, keys=KEYS, thresholds=TH,
                           fields=X.FIELDS)
        staged = WM.parse_texts(files())[0]
        n = len(staged.tables) + len(staged.columns)
        check("every map row and the value pass (nothing was in force); the "
              "binding is the two versions, the row count and the value",
              p["items"] == {"bundle": staged.version,
                             "confirms": p["map"].version, "rows": n,
                             "facts": {"US": {"unit_cost": "4.2"}}}
              and p["version"] == "none|US:unit_cost:0"
              and WM.pending(p["map"]) == [], p["items"])
        again = file_gate.plan(c, files(VALUES.replace("4.20", "4.5")),
                               p["map"], keys=KEYS, thresholds=TH)
        check("over the bundle in force: only the changed value passes",
              again["items"]["rows"] == 0 and again["rows"] == {}
              and again["items"]["facts"] == {"US": {"unit_cost": "4.5"}},
              again["items"])
        for vals, code in (
                (VALUES.replace("4.20", "99"), "fact_value_out_of_range"),
                (VALUES.replace("unit_cost", "fx_rate"),
                 "workbook_map_refused"),
                (VALUES.replace("\tUS\t", "\tCA\t"), "market_not_onboarded")):
            e = raises(lambda: file_gate.plan(c, files(vals), None,
                                              keys=KEYS, thresholds=TH))
            check(f"refused before any gate: {code}", ecode(e) == code,
                  (code, e))
    check("plan() wrote nothing", fact() is None)
    return p


def test_ask(p: dict) -> None:
    print("\n[2] ask(): one console ask for the whole file")
    f = file_gate.ask("im-tracker", p, verb=VERB, source="raw/map.x.json")
    check("expect is exactly plan()'s items; the rows shown, the value with "
          "its cell", f["expect"] == {"items": p["items"]}
          and f["values"] == [{"key": "unit_cost", "market": "US",
                               "value": "4.2", "cell": "F14"}]
          and len(f["shown"]) == min(30, p["items"]["rows"]), f["values"])
    with closing(con()) as c:
        doc = pending.asks(c, keys=KEYS, registry=None, thresholds=TH,
                           staged=lambda _c: [f])
    a, about = doc["asks"][0], doc["about"][0]
    check("pending lists it as one file ask, gated by the harness's verb",
          len(doc["asks"]) == 1 and a["kind"] == "file"
          and a["step"] == "confirm" and a["gate"]["verb"] == VERB
          and a["gate"]["expect"] == f["expect"] and about["gate"]
          and doc["message_code"]["code"] == "pending_summary_files", a)
    sys.path.insert(0, str(_shop.PLAYBOOK / "console"))
    import core  # noqa: E402
    filled = {**a, "recommend": {**a["recommend"], "because": "it matches"}}
    got, errs = core.validate_ask(filled)
    check("the console accepts it as it is (evidence within its limits)",
          errs == [], errs)


def test_tty(p: dict) -> dict:
    print("\n[3] confirm() at a terminal: one retype for the file")
    out, err = gate(p, tty=["confirm"])
    check("the value is confirmed @tty, the file its source; every row id "
          "is in the record", err is None and fact() == (
              "4.2", 0, "workbook:synthetic Budget!F14", f"{USER}@tty")
          and out["changed_by"] == f"{USER}@tty"
          and "value:unit_cost|US" in out["rows"]
          and len(out["rows"]) == p["items"]["rows"] + 1, (out, err))
    with closing(con()) as c:
        h = c.execute("SELECT action, new_value, reason FROM "
                      "client_facts_history WHERE key='unit_cost'").fetchall()
    check("history: one confirm, the reason given", h == [
        ("confirm", "4.2", "the owner's yes")], h)
    return p["map"]


def test_relay(in_force) -> None:
    print("\n[4] confirm() relayed: the code binds exactly this plan")
    with closing(con()) as c:
        p = file_gate.plan(c, files(VALUES.replace("4.20", "4.5")), in_force,
                           keys=KEYS, thresholds=TH)
    out, err = gate(p, secret=True)
    check("no code: the challenge (confirm_code_required), nothing written",
          isinstance(err, human.CodeRequired) and fact()[0] == "4.2"
          and err.subject["items"] == json.loads(json.dumps(p["items"])),
          err)
    code = err.confirm_code
    out, err = gate(p, secret=True, code=code)
    check("the code: the new value written @relay, the relay audit in the "
          "reason", err is None and fact()[:2] == ("4.5", 0)
          and fact()[3] == f"{USER}@relay"
          and "[relay user=web:owner" in out["why"], (out, err))
    with closing(con()) as c:
        fresh = file_gate.plan(c, files(VALUES.replace("4.20", "4.6")),
                               in_force, keys=KEYS, thresholds=TH)
    out, err = gate(fresh, secret=True, code=code)
    check("the same code for another plan is refused, nothing written",
          ecode(err) == "confirm_code_mismatch" and fact()[0] == "4.5", err)


def test_closure() -> None:
    print("\n[5] file_gate.py writes no message of its own")
    text = (Path(_shop.KIT) / "file_gate.py").read_text(encoding="utf-8")
    check("no msg() call: its refusals are facts' and workbook_map's",
          "msg(" not in text)


def main() -> int:
    setup()
    p = test_plan()
    test_ask(p)
    in_force = test_tty(p)
    test_relay(in_force)
    test_closure()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
