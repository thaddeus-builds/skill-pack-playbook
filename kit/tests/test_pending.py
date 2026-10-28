#!/usr/bin/env python3
"""`<cli> pending` (kit/pending.py) turns every row waiting on a human into
one valid console ask, on the fake "shop" skill pack.

  1. A read verb: no DB = no_db, nothing created; nothing waiting = no asks.
  2. Every pending fact (number / choice / date / threshold), decision
     (number / choice / text / sha256) and queue item becomes exactly one
     ask of the right step, with evidence from the skill pack's own rows
     (source "skill pack …"), recommend.because left null and flagged; the
     console refuses them as they are and, once the agent writes
     `because`, `console/ask.py add --dry-run` accepts every one.
  3. The gate block is what the kit's gate binds: every gated ask,
     answered through console/relay.py (in a child process, against a
     skill pack command that runs kit.facts / kit.decisions / kit.queue),
     passes relay's subject check and writes exactly that row, @relay
     (a provided value other than the recommendation too).
  4. Several markets declared or waiting: each fact or decision gate names
     its market (the relay passes --market=M) and a relayed confirm writes
     it. No gate where the relayed call could not reach the row, each with
     a coded warning: a verb word the console cannot send, a binding longer
     than the console holds.
  5. Ask ids are stable while nothing moves and new when the value does;
     pending.tsv is closed over pending.py.
  7. A derived fact (`derived=`): the skill pack names the facts it worked out
     and why; each is one `confirm` ask whatever its registry type (the value
     shown, not typed), recommending yes with the skill pack's own because (so
     the console takes it as it is), gated on the value shown; the group's
     asks can be answered together; a key not named is drawn as before.
  6. Hub mode (--hub): every ask id and every gate verb starts with the cli
     word and every group with the skill pack's name; the console takes them,
     a relayed confirm through a hub dispatcher (`<hub> <cli> <verb…>`)
     writes the row, and a verb one word past the console's limit gets no
     gate (pending_gate_too_many_words).
"""

import copy
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import db, decisions, facts, messages, pending  # noqa: E402
from kit import queue as q  # noqa: E402
from kit.registry import DecisionRegistry, FactKeys, Thresholds  # noqa: E402
from kit.testing.check import (capture, check, clean_env, finish,  # noqa: E402
                               one_doc, tmp_dir)
from kit.testing.sandbox import sandbox_env  # noqa: E402

CFG = _shop.use()
DATA = _shop.data_dir()
DB = DATA / CFG.db_file
SECRET = CFG.env("CONFIRM_CODE_SECRET")
CONSOLE = _shop.PLAYBOOK / "console"
SPEC = db.with_human({}, version=1)
SHA = "ab" * 32

FIX = Path(tmp_dir("pending-fixtures-"))
(FIX / "fact_keys.tsv").write_text(
    "key\tgroup\ttype\tunit\tmin\tmax\tlabel_en\tlabel_zh\twhy\n"
    "unit_cost\tcost\tnumber\tUSD\t0\t50\tUnit cost\t单位成本\tmargin\n"
    "channel\tprofile\tchoice:web|store\t\t\t\tChannel\t渠道\trouting\n"
    "launch_date\tprofile\tdate\t\t\t\tLaunch date\t上线日期\tage\n"
    "ad_account\tprofile\ttext\t\t\t\tAd account\t广告账户\treports\n"
    "account_currency\tprofile\tchoice:USD|HKD\t\t\t\tCurrency\t币种\treports\n"
    "reference_return\tcost\tnumber\tx\t0\t100\tReference return\t参考回报\tbenchmark\n"
    "break_even\tcost\tnumber\tx\t0\t100\tBreak-even return\t盈亏平衡回报\tstop rule\n",
    encoding="utf-8")
(FIX / "constants.tsv").write_text(
    "name\tdefault\tunit\tmin\tmax\tgroup\tlabel_en\tlabel_zh\texplain\twhy\n"
    "max_step\t0.2\tratio\t0\t1\tpacing\tMax step\t最大步长\tsize\tsafety\n",
    encoding="utf-8")
KEYS = FactKeys(FIX / "fact_keys.tsv")
TH = Thresholds(FIX / "constants.tsv")
IDS = {"product": r"SKU-[A-Z0-9]+", "campaign": r"[0-9]+"}
REG = DecisionRegistry(entity_ids=IDS)

# the skill pack command console/relay.py runs: `<cmd> facts|decisions|queue …`
SKILL_PACK = r'''
import os, sys
sys.path.insert(0, os.environ["PLAYBOOK"])
from pathlib import Path
from kit import db, decisions, facts, queue
from kit.registry import DecisionRegistry, FactKeys, Thresholds
fix = Path(os.environ["FIX"])
spec = db.with_human({}, version=1)
group, argv = sys.argv[1], sys.argv[2:]
if group == "facts":
    rc = facts.main(argv, spec=spec, keys=FactKeys(fix / "fact_keys.tsv"),
                    thresholds=Thresholds(fix / "constants.tsv"))
elif group == "decisions":
    rc = decisions.main(argv, spec=spec, registry=DecisionRegistry(
        entity_ids={"product": r"SKU-[A-Z0-9]+", "campaign": r"[0-9]+"}))
else:
    rc = queue.main(argv, spec=spec, snapshot=lambda m: {},
                    validate=lambda c, p: None, ttl_hours=lambda c, m: 24)
raise SystemExit(rc)
'''

RELAY = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
import core, relay
cfg = json.loads(sys.argv[2])
ask, errs = core.validate_ask(cfg["ask"])
assert not errs, errs
print(json.dumps(relay.run(ask, cfg["value"], cmd=cfg["cmd"], verbs=cfg["verbs"],
                           user="alice", reason="owner answered",
                           timeout=60.0, env=cfg["env"])))
'''


def PEND(argv, registry=REG):
    return pending.main(argv, spec=SPEC, keys=KEYS, registry=registry,
                        thresholds=TH)


def env() -> dict:
    return clean_env(**{CFG.env("DATA_DIR"): str(DATA),
                        CFG.env("AUTH_ENV_PATHS"): "none"})


def pend(registry=REG, *flags: str) -> dict:
    rc, out, err = capture(lambda a: PEND(a, registry), ["--json", *flags],
                           env=env())
    assert rc == 0, (rc, out, err)
    return one_doc(out)


def fset(*argv):
    rc, out, err = capture(lambda a: facts.main(a, spec=SPEC, keys=KEYS,
                                                thresholds=TH),
                           ["set", *argv, "--source", "agent_2026-09-28",
                            "--reason", "from the invoice", "--json"],
                           env=env())
    assert rc == 0, (argv, out, err)


def dset(*argv, registry=REG):
    rc, out, err = capture(lambda a: decisions.main(a, spec=SPEC,
                                                    registry=registry),
                           ["set", *argv, "--source", "agent_2026-09-28",
                            "--reason", "proposed", "--json"], env=env())
    assert rc == 0, (argv, out, err)


def queue_add(*props):
    with closing(db.connect(SPEC)) as c:
        return q.add(SPEC, c, {"meta": {}, "proposals": list(props)},
                     lambda con, p: None)


def prop(target, payload, **kw):
    return {"kind": "restock", "market": "US", "target_ref": target,
            "payload": payload, "basis": "b1", "evidence": {"stock": 2},
            "expected": {"effect": f"{target} gets {payload.get('units')} "
                                   f"more units"}, **kw}


def filled(asks: list[dict]) -> list[dict]:
    return [{**a, "recommend": {**a["recommend"],
                                "because": "the skill pack's own numbers"}}
            for a in asks]


def console_add(asks: list[dict]) -> dict:
    d = Path(tmp_dir("console-"))
    f = d / "asks.json"
    f.write_text(json.dumps(asks, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(CONSOLE / "ask.py"), "--dir",
                        str(d / "log"), "add", str(f), "--dry-run"],
                       capture_output=True, text=True, timeout=60,
                       env={**sandbox_env(DATA),
                            "PYTHONDONTWRITEBYTECODE": "1"})
    return one_doc(r.stdout) or {"stdout": r.stdout, "stderr": r.stderr}


# a client hub's dispatcher: `hub <cli> <verb…>` runs that pack's command
HUB = r'''
import os, runpy, sys
assert sys.argv[1] == os.environ["HUB_CLI"], sys.argv
sys.argv = [os.environ["HUB_PACK"], *sys.argv[2:]]
runpy.run_path(os.environ["HUB_PACK"], run_name="__main__")
'''


def relay(ask: dict, value: str, hub: bool = False) -> dict:
    d = Path(tmp_dir("skill-pack-"))
    script = d / "shop_skill_pack.py"
    script.write_text(SKILL_PACK, encoding="utf-8")
    cmd, verbs = [sys.executable, str(script)], [["facts", "confirm"],
                                                 ["decisions", "confirm"],
                                                 ["queue", "approve"]]
    extra = {}
    if hub:
        (d / "hub.py").write_text(HUB, encoding="utf-8")
        cmd = [sys.executable, str(d / "hub.py")]
        verbs = [[CFG.cli, *v] for v in verbs]
        extra = {"HUB_CLI": CFG.cli, "HUB_PACK": str(script)}
    child_env = sandbox_env(DATA, PLAYBOOK=str(_shop.PLAYBOOK), FIX=str(FIX),
                            PYTHONDONTWRITEBYTECODE="1",
                            **{SECRET: "s3cret"}, **extra)
    cfg = json.dumps({"ask": ask, "value": value, "cmd": cmd,
                      "verbs": verbs, "env": child_env})
    r = subprocess.run([sys.executable, "-c", RELAY, str(CONSOLE), cfg],
                       env=child_env, capture_output=True, text=True,
                       timeout=180)
    return one_doc(r.stdout) or {"stdout": r.stdout, "stderr": r.stderr}


def fact_row(key, market="US"):
    with closing(sqlite3.connect(DB)) as c:
        return c.execute("SELECT value, is_assumption, changed_by FROM "
                         "client_facts WHERE market=? AND key=?",
                         (market, key)).fetchone()


def queue_status(i: int) -> str:
    with closing(sqlite3.connect(DB)) as c:
        return q.fetch(c, i)["status"]


def by_ref(doc: dict) -> dict:
    """ask by a readable handle: fact:<key>, decision:<eid>:<key>, queue:<id>."""
    out = {}
    for a, b in zip(doc["asks"], doc["about"]):
        r = b["ref"]
        h = (f"fact:{r['key']}" if b["table"] == "client_facts" else
             f"decision:{r['entity_id']}:{r['key']}"
             if b["table"] == "decisions" else f"queue:{r['id']}")
        out[h] = (a, b)
    return out


def wcodes(doc: dict) -> list[str]:
    return [w["code"] for w in doc["warning_codes"]]


# ---- 1 ---------------------------------------------------------------------

def test_read_only() -> None:
    print("[1] a read verb")
    rc, out, _ = capture(PEND, ["--json"], env=env())
    check("no DB: no_db, exit 2, nothing created",
          rc == 2 and one_doc(out)["code"] == "no_db" and not DB.exists(),
          out)
    db.connect(SPEC).close()
    with closing(sqlite3.connect(DB)) as c:
        c.execute("INSERT INTO client_facts (market, key, value, "
                  "is_assumption, source, updated_at, changed_by) VALUES "
                  "('US', 'market_declared', 'US', 0, 't', "
                  "'2026-09-22', 't@tty')")
        c.commit()
    d = pend()
    check("nothing waiting: no asks, the coded summary, no warnings",
          d["asks"] == [] and d["about"] == [] and d["warnings"] == []
          and d["message_code"]["code"] == "pending_summary", d)
    rc, out, _ = capture(PEND, ["--market", "XX", "--json"], env=env())
    check("--market outside the closed set: market_not_a_market",
          rc == 2 and one_doc(out)["code"] == "market_not_a_market", out)


# ---- 2 + 3 -------------------------------------------------------------------

def test_asks_and_relay() -> None:
    print("[2] one valid console ask per pending row")
    fset("unit_cost", "4.20")
    fset("channel", "web")
    fset("launch_date", "2026-01-15")
    fset("threshold_max_step", "0.3")
    dset("product", "SKU-1", "floor_price", "2.50")
    dset("product", "SKU-1", "stage", "live")
    dset("product", "SKU-2", "note", "hand wash only")
    dset("product", "SKU-3", "artwork", SHA)
    rep = queue_add(prop("SKU-1", {"units": 40}))
    qid = rep["queued"][0]
    mtime = DB.stat().st_mtime_ns
    doc = pend()
    asks, about = doc["asks"], doc["about"]
    refs = by_ref(doc)
    check("nine asks: 4 facts, 4 decisions, 1 queue item, in that order",
          len(asks) == 9 and [b["table"] for b in about] ==
          ["client_facts"] * 4 + ["decisions"] * 4 + ["action_queue"]
          and doc["message_code"]["params"] == {"facts": 4, "decisions": 4,
                                                "queue": 1}, about)
    check("pending opened the DB read-only (the file is unchanged)",
          DB.stat().st_mtime_ns == mtime)
    steps = {h: a["step"] for h, (a, _) in refs.items()}
    check("steps by value kind: number/date/threshold provide, choice "
          "choose, text provide, sha256 confirm, queue approve",
          steps == {"fact:unit_cost": "provide", "fact:channel": "choose",
                    "fact:launch_date": "provide",
                    "fact:threshold_max_step": "provide",
                    "decision:SKU-1:floor_price": "provide",
                    "decision:SKU-1:stage": "choose",
                    "decision:SKU-2:note": "provide",
                    "decision:SKU-3:artwork": "confirm",
                    f"queue:{qid}": "approve"}, steps)
    uc = refs["fact:unit_cost"][0]
    check("a number fact: input number with the registry's bounds and "
          "unit; recommend = the pending value",
          uc["input"] == {"type": "number", "min": 0, "max": 50,
                          "unit": "USD"}
          and uc["recommend"] == {"value": "4.2", "because": None}, uc)
    check("a threshold fact: the thresholds registry's bounds",
          refs["fact:threshold_max_step"][0]["input"] ==
          {"type": "number", "min": 0, "max": 1, "unit": "ratio"},
          refs["fact:threshold_max_step"][0])
    check("a choice: its options", [o["value"] for o in
                                    refs["fact:channel"][0]["options"]] ==
          ["web", "store"])
    qa = refs[f"queue:{qid}"][0]
    check("the queue ask: approve, effect from expected, the payload and "
          "evidence as tables", qa["effect"].endswith("SKU-1 gets 40 more "
                                                     "units")
          and qa["evidence"][0]["table"]["rows"] == [["units", "40"]]
          and qa["recommend"] == {"value": "yes", "because": None}, qa)
    sources = [e.get("source") or e["table"]["caption"]
               for a in asks for e in a["evidence"]]
    check("every evidence item is sourced from the skill pack",
          sources and all("skill_pack" in s for s in sources), sources)
    check("every ask is flagged: recommend.because null, about.fill, the "
          "coded pending_fill_because warning; the texts coded",
          all(a["recommend"]["because"] is None for a in asks)
          and all(b["fill"] == ["recommend.because"] for b in about)
          and wcodes(doc) == ["pending_fill_because"]
          and all(b["title_code"]["code"].startswith("pending_title_")
                  and b["why_code"] and b["if_no_code"] for b in about)
          and about[-1]["effect_code"]["code"] == "pending_effect_queue",
          doc["warning_codes"])
    check("every ask is gated here (one market declared)",
          all(b["gate"] for b in about) and all("gate" in a for a in asks))
    got = console_add(asks[:1])
    check("as emitted, the console refuses an ask (because is required)",
          got.get("ok") is False and got.get("code") == "invalid_ask"
          and any(e["field"] == "recommend.because"
                  for e in got["params"]["errors"]), got)
    got = console_add(filled(asks))
    check("with because written: console/ask.py add --dry-run accepts all "
          "nine", got.get("ok") is True and len(got.get("posted", [])) == 9,
          got)

    print("[3] each gate passes console/relay.py's subject check")
    bad = copy.deepcopy(filled([refs[f"queue:{qid}"][0]])[0])
    items = bad["gate"]["expect"]["items"]
    bad["gate"]["expect"]["items"] = {
        k: [*v[:3], '{"units":41}', v[4]] for k, v in items.items()}
    got = relay(bad, "yes")
    check("control: an expect that is not what the gate binds is "
          "gate_changed, nothing written",
          got.get("code") == "gate_changed" and queue_status(qid) ==
          "pending", got)
    answers = {"fact:unit_cost": "4.5", "fact:channel": "web",
               "fact:launch_date": "2026-01-15",
               "fact:threshold_max_step": "0.3",
               "decision:SKU-1:floor_price": "2.50",
               "decision:SKU-1:stage": "live",
               "decision:SKU-2:note": "hand wash only",
               "decision:SKU-3:artwork": "yes", f"queue:{qid}": "yes"}
    for h, value in answers.items():
        ask = filled([refs[h][0]])[0]
        got = relay(ask, value)
        check(f"{h} answered {value!r}: ok through the kit's gate",
              got.get("ok") is True and got.get("code") is None, got)
    check("the facts confirmed @relay, the provided value (4.5, not the "
          "recommended 4.2) is the one written",
          fact_row("unit_cost")[:2] == ("4.5", 0)
          and fact_row("unit_cost")[2].endswith("@relay")
          and fact_row("channel")[:2] == ("web", 0)
          and fact_row("threshold_max_step")[:2] == ("0.3", 0),
          [fact_row(k) for k in ("unit_cost", "channel")])
    with closing(sqlite3.connect(DB)) as c:
        st = c.execute("SELECT entity_id, key, status, confirmed_value FROM "
                       "decisions ORDER BY entity_id, key").fetchall()
        qr = q.fetch(c, qid)
    check("the decisions confirmed", all(s[2] == "confirmed" for s in st)
          and ("SKU-1", "floor_price", "confirmed", "2.5") in st, st)
    check("the queue item approved @relay", qr["status"] == "approved"
          and qr["decided_by"].endswith("@relay"), qr)
    check("nothing is waiting any more", pend()["asks"] == [])


# ---- 4 ---------------------------------------------------------------------

def test_no_gate() -> None:
    print("[4] no gate where the relayed call cannot reach the row")
    capture(lambda a: facts.main(a, spec=SPEC, keys=KEYS, thresholds=TH),
            ["unconfirm", "unit_cost", "--reason", "new invoice"], env=env())
    fset("unit_cost", "5")          # a confirmed value is never set over
    dset("product", "SKU-1", "floor_price", "3")
    with closing(sqlite3.connect(DB)) as c:        # a second market waits
        c.execute("INSERT INTO client_facts (market, key, value, "
                  "is_assumption, source, updated_at, changed_by) VALUES "
                  "('CA', 'market_declared', 'CA', 1, 'agent', "
                  "'2026-09-28', 'a@cli')")
        c.commit()
    doc = pend()
    refs = by_ref(doc)
    decl, fact = doc["asks"][0], refs["fact:unit_cost"][0]
    check("two markets declared or waiting: the CA declaration (listed "
          "first) and the US fact keep their gates, each naming its market "
          "(the relay passes --market=M), and no ambiguity warning",
          doc["about"][0]["ref"] == {"key": "market_declared"}
          and doc["about"][0]["market"] == "CA" and doc["about"][0]["gate"]
          and decl["gate"]["market"] == "CA"
          and fact["gate"]["market"] == "US"
          and fact["gate"]["expect"]["market"] == "US"
          and "pending_gate_market_ambiguous" not in wcodes(doc),
          (decl.get("gate"), fact.get("gate"), doc["warning_codes"]))
    check("the decision (only US confirmed) keeps its gate, with no market "
          "word (one market can take decisions)",
          "market" not in refs["decision:SKU-1:floor_price"][0]["gate"])
    got = console_add(filled(doc["asks"]))
    check("the market-naming asks are valid console asks",
          got.get("ok") is True, got)
    got = relay(filled([fact])[0], "5")
    check("relayed with --market=US, the US fact is confirmed while two "
          "markets are declared", got.get("ok") is True
          and fact_row("unit_cost")[:2] == ("5", 0), (got, fact_row("unit_cost")))
    capture(lambda a: facts.main(a, spec=SPEC, keys=KEYS, thresholds=TH),
            ["unconfirm", "unit_cost", "--market", "US", "--reason",
             "back to pending for the next checks"], env=env())

    loose = DecisionRegistry()
    dset("product", "SKU 9", "note", "fragile", registry=loose)
    doc = pend(loose)
    a, b = by_ref(doc)["decision:SKU 9:note"]
    check("an entity id the console cannot send as a verb word: no gate, "
          "pending_gate_bad_word", "gate" not in a and not b["gate"]
          and "pending_gate_bad_word" in wcodes(doc)
          and a["id"].startswith("decision-us-product-sku-9-note-"), a)
    rep = queue_add(prop("SKU-8", {"units": 1, "note": "x" * 2100}))
    doc = pend()
    a, b = by_ref(doc)[f"queue:{rep['queued'][0]}"]
    check("a binding longer than the console's expect limit: no gate, "
          "pending_gate_too_long", "gate" not in a
          and "pending_gate_too_long" in wcodes(doc), doc["warning_codes"])
    got = console_add(filled([a]))
    check("that ask is still valid (evidence cells clipped)",
          got.get("ok") is True, got)


# ---- 5 ---------------------------------------------------------------------

def test_ids_and_closure() -> None:
    print("[5] stable ids; closure")
    first = [a["id"] for a in pend()["asks"]]
    check("the same rows: the same ids", [a["id"] for a in pend()["asks"]]
          == first)
    fset("unit_cost", "6", "--market", "US")
    again = by_ref(pend())["fact:unit_cost"][0]["id"]
    check("a new pending value: a new id (an answered id is never reused)",
          again not in first and again.startswith("fact-us-unit_cost-"),
          again)
    rc, out, _ = capture(PEND, [], env=env())
    check("text mode: one line per ask and the summary",
          rc == 0 and "fact-us-unit_cost-" in out and "ask(s) waiting" in out,
          out)
    reg = messages.registry()
    own = {c: r for c, r in reg.items()
           if Path(r["file"]).name == "pending.tsv"}
    probs = messages.check_registry_closed(_shop.KIT, ["pending.py"], own,
                                           strict_kit=True)
    check("every msg() in pending.py is literal and registered; every "
          "pending.tsv code is emitted", probs == [], probs)


# ---- 6 ---------------------------------------------------------------------

def staged_file(words: int):
    return lambda con: [{"name": "plan.xlsx", "version": "v1", "rows": 1,
                         "shown": [["r1", "unit cost"]], "values": [],
                         "source": "raw/plan.xlsx",
                         "verb": ["workbook", "confirm", *["w"] * (words - 2)],
                         "expect": {"items": {"plan.xlsx": "v1"}}}]


def test_hub() -> None:
    print("[6] hub mode: one console for several skill packs")
    plain, doc = pend(), pend(REG, "--hub")
    cli, name = CFG.cli, CFG.name
    check("the same asks, in the same order, each id the plain one with the "
          "cli word first", len(doc["asks"]) == len(plain["asks"]) > 3
          and doc["hub"] is True and plain["hub"] is False
          and all(h["id"] == f"{cli}-{p['id']}" for h, p in
                  zip(doc["asks"], plain["asks"]))
          and [b["id"] for b in doc["about"]] == [a["id"] for a in doc["asks"]],
          [a["id"] for a in doc["asks"]])
    gated = [(h, p) for h, p in zip(doc["asks"], plain["asks"]) if "gate" in p]
    check("every gate verb starts with the cli word, the rest of the gate "
          "unchanged", gated and all(
              h["gate"]["verb"] == [cli, *p["gate"]["verb"]]
              and h["gate"]["expect"] == p["gate"]["expect"] for h, p in gated),
          [h["gate"]["verb"] for h, _ in gated])
    check("every group names the skill pack",
          all(h["group"] == f"{name} · {p['group']}"[:60]
              for h, p in zip(doc["asks"], plain["asks"])),
          [a["group"] for a in doc["asks"]])
    got = console_add(filled(doc["asks"]))
    check("the console takes every hub ask (ids, verbs of one word more)",
          got.get("ok") is True and len(got.get("posted", [])) ==
          len(doc["asks"]), got)
    fact = next(a for a in doc["asks"] if a["kind"] == "fact"
                and a["gate"]["verb"][1:3] == ["facts", "confirm"])
    key = fact["gate"]["verb"][3]
    value = fact["recommend"]["value"]
    got = relay(filled([fact])[0], value, hub=True)
    check("relayed through the hub's dispatcher (<hub> <cli> facts confirm "
          "KEY), the fact is confirmed @relay", got.get("ok") is True
          and fact_row(key)[1] == 0 and fact_row(key)[2].endswith("@relay"),
          (got, fact_row(key)))
    got = relay(filled([fact])[0], value)
    check("control: the hub ask is refused by a console whose verbs are a "
          "skill pack's own (no cli word)", got.get("code") ==
          "gate_unavailable", got)

    def staged(words, *flags):
        rc, out, _ = capture(lambda a: pending.main(
            a, spec=SPEC, keys=KEYS, registry=REG, thresholds=TH,
            staged=staged_file(words)), ["--json", *flags], env=env())
        d = one_doc(out)
        return next((a, b) for a, b in zip(d["asks"], d["about"])
                    if b["table"] == "workbook_map"), d
    (a, b), d = staged(6, "--hub")
    check("a staged file's verb of 6 words: 7 with the cli word, gated",
          b["gate"] and a["gate"]["verb"][0] == cli
          and len(a["gate"]["verb"]) == pending.LIMITS["verb"], a.get("gate"))
    (a, b), d = staged(7, "--hub")
    check("one word more: no gate, pending_gate_too_many_words",
          "gate" not in a and not b["gate"]
          and "pending_gate_too_many_words" in wcodes(d), d["warning_codes"])
    (a, b), _ = staged(7)
    check("the same 7-word verb without --hub keeps its gate",
          b["gate"] and len(a["gate"]["verb"]) == 7, a.get("gate"))


# ---- 7 ---------------------------------------------------------------------

def pend_derived(derived) -> dict:
    rc, out, err = capture(lambda a: pending.main(
        a, spec=SPEC, keys=KEYS, registry=REG, thresholds=TH, derived=derived),
        ["--json"], env=env())
    assert rc == 0, (rc, out, err)
    return one_doc(out)


def refused_derived(derived):
    try:
        with closing(db.connect(SPEC, read_only=True)) as con:
            pending.asks(con, keys=KEYS, registry=REG, thresholds=TH,
                         derived=derived)
    except Exception as e:  # noqa: BLE001
        return messages.failure(e)
    return None


def test_derived() -> None:
    print("[7] a derived fact is one confirm ask the skill pack has argued")
    src = "derived: report export, 2026-09-01..2026-09-30"
    def derive(k, v, source=src):
        rc, out, err = capture(lambda a: facts.main(a, spec=SPEC, keys=KEYS,
                                                    thresholds=TH),
                               ["set", k, v, "--market", "US", "--source",
                                source, "--reason", "worked out from the "
                                "export", "--json"], env=env())
        assert rc == 0, (k, out, err)
    for k, v in (("ad_account", "ACC-1"), ("account_currency", "HKD"),
                 ("reference_return", "2.4"), ("break_even", "1.8")):
        derive(k, v, src if k != "break_even" else "agent_2026-09-28")
    because = {"ad_account": "the id every row of the export carries",
               "account_currency": "all 412 rows are in HKD",
               "reference_return": "spend-weighted return of the last 30 days"}
    plain = by_ref(pend())
    doc = pend_derived({**because, ("CA", "break_even"): "not for US"})
    refs = by_ref(doc)
    mine = {k: refs[f"fact:{k}"] for k in because}
    check("before the hook: a text and a number fact are typed (provide), a "
          "choice is chosen, each waiting for the agent's because",
          [plain[f"fact:{k}"][0]["step"] for k in because] ==
          ["provide", "choose", "provide"]
          and all(plain[f"fact:{k}"][1]["fill"] == ["recommend.because"]
                  for k in because))
    check("named in derived=, each is a confirm ask: the value is shown, not "
          "typed (no input, no options)",
          all(a["step"] == "confirm" and "input" not in a
              and "options" not in a for a, _ in mine.values()),
          {k: a["step"] for k, (a, _) in mine.items()})
    check("it recommends yes with the skill pack's own because, so nothing is "
          "left for the agent to fill", all(
              a["recommend"] == {"value": "yes", "because": because[k]}
              and b["fill"] == [] for k, (a, b) in mine.items()),
          {k: a["recommend"] for k, (a, _) in mine.items()})
    check("the source and the window stay in the text the owner reads", all(
        src in a["why"] and any(e.get("value") == src for e in a["evidence"])
        for a, _ in mine.values()), mine["ad_account"][0]["why"])
    check("the gate binds the value shown, not a typed one",
          all(a["gate"]["expect"]["items"] == {k: v}
              and not a["gate"].get("value_arg")
              for (k, v), (a, _) in zip((("ad_account", "ACC-1"),
                                         ("account_currency", "HKD"),
                                         ("reference_return", "2.4")),
                                        mine.values())),
          [a["gate"] for a, _ in mine.values()])
    check("they are one group, which the console's answer-all button needs: "
          "every ask suggests, none approves, every gate is a confirm",
          len({a["group"] for a, _ in mine.values()}) == 1
          and all(a["recommend"] and a["step"] != "approve"
                  and a["gate"]["verb"][:2] == ["facts", "confirm"]
                  for a, _ in mine.values()))
    be, be_b = refs["fact:break_even"]
    check("a key not named for this market (the CA pair) is drawn as before: "
          "typed, and still waiting for the agent",
          be["step"] == "provide" and be["recommend"]["because"] is None
          and be_b["fill"] == ["recommend.because"])
    unfilled = sum(1 for b in doc["about"] if b["fill"])
    check("the fill warning counts only the asks that still need it",
          [w["params"]["count"] for w in doc["warning_codes"]
           if w["code"] == "pending_fill_because"] == [unfilled]
          and unfilled == len(doc["asks"]) - 3, (unfilled, len(doc["asks"])))
    got = console_add([a for a, _ in mine.values()])
    check("the console takes the derived asks as they are, with no agent step",
          got.get("ok") is True, got)
    got = console_add([be])
    check("and still refuses the one that waits for a because",
          got.get("ok") is not True, got)
    rel = relay(mine["account_currency"][0], "yes")
    check("answering yes through the gate confirms exactly the value shown",
          rel.get("ok") is True and fact_row("account_currency")[:2] ==
          ("HKD", 0), (rel, fact_row("account_currency")))
    derive("reference_return", "2.9")
    now = by_ref(pend_derived(because))["fact:reference_return"][0]
    check("a changed value is a new question: another id, the new value, "
          "still a confirm ask a person must answer",
          now["id"] != mine["reference_return"][0]["id"]
          and now["step"] == "confirm" and "2.9" in now["title"]
          and fact_row("reference_return")[:2] == ("2.9", 1), now["title"])
    only = refused_derived({"account_currency": because["account_currency"]})
    check("a confirmed fact named in derived= is just not asked again",
          only is None)
    long_ = pend_derived({"ad_account": "  a  " + "word " * 80})
    c = by_ref(long_)["fact:ad_account"][0]["recommend"]["because"]
    check("a long because is clipped to the console's limit, spaces "
          "collapsed", len(c) == 200 and c.startswith("a word") and "  " not in c, c)
    bad = {"an empty because": {"ad_account": " "},
           "a because that is not text": {"ad_account": 3},
           "a key that is a number": {7: "x"},
           "a pair with an empty market": {("", "ad_account"): "x"}}
    got = {n: refused_derived(d) for n, d in bad.items()}
    check("a hook the skill pack wrote wrongly is refused by name "
          "(pending_derived_invalid)", all(
              f and f["code"] == "pending_derived_invalid" for f in got.values())
          and "ad_account" in got["an empty because"]["params"]["key"], got)


test_read_only()
test_asks_and_relay()
test_no_gate()
test_ids_and_closure()
test_hub()
test_derived()
raise SystemExit(finish())
