#!/usr/bin/env python3
"""A client hub's confirmed facts, copied into a skill pack (kit.facts
sync-hub, apply_hub_copy, doctor_hub, hub_conflicts; kit.pending's conflict
ask; kit.registry.definition_diffs; kit.guards.hub_keys).

A synthetic DEMO hub (markets US, CA, MX; the shop's two keys, defined as
the shop defines them) is built with the kit's own facts verb and gate (the
KIT_TTY seam), then the fake "shop" skill pack (markets US, CA) syncs:

  [1] the first sync: a declaration copied (the door opens: the facts of
      that market copy too), a value the pack confirmed alike is `same`, a
      market the pack does not keep is skipped, a hand-written hub row (its
      last history no gated confirm) is refused; each copy confirmed with
      source hub:<hub>@<id>#<digest16>, changed_by <user>@hub, history
      action hub_copy; one hub_copies row per outcome; the hub's bytes
      (database and WAL, a live writer holding it open) unchanged, and a
      row only in that WAL seen
  [2] a rerun changes nothing; a person's unconfirm of a copy is never
      undone by the same hub version (`kept`); hub_copies refuses UPDATE
      and DELETE
  [3] the hub moves: doctor names the stale copy with both versions
      (fact_hub_copy_stale); the next sync never overwrites the pack's
      confirmed value (`conflict`), doctor is current again, and pending
      makes it ONE choose ask (hub's value or the own) gated by facts
      confirm --value; choosing the hub's value closes it
  [4] a key defined otherwise at the hub is skipped and named by doctor;
      no hub named = no doctor line and a coded refusal of sync-hub; a
      missing hub store is coded too
  [5] definition_diffs (type, unit, bounds as numbers, shared labels; why
      ignored) and the guard kit.guards.hub_keys.check a pack's test calls
"""

import hashlib
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import config, db, doctor, facts, human, pending  # noqa: E402
from kit.guards import hub_keys  # noqa: E402
from kit.registry import FactKeys, definition_diffs  # noqa: E402
from kit.testing.check import (capture, check, clean_env, finish,  # noqa: E402
                               one_doc, tmp_dir)

SPEC = db.with_human({}, version=1)
USER = human.changed_by("tty").rsplit("@", 1)[0]
SHOP_KEYS = _shop.SHOP / "ssot" / "fact_keys.tsv"

HUB = Path(tmp_dir("hubs-")) / "demo-hub"
DEFS = HUB / "hub" / "defs"
DEFS.mkdir(parents=True)
(DEFS / "skill-pack.toml").write_text(
    '[skill_pack]\nname = "demo-hub-hub"\ncli = "hub"\nenv_prefix = "HUB"\n'
    'db_file = "hub.db"\nlanguages = ["en", "zh"]\n'
    'markets = ["US", "CA", "MX"]\nhome_env_file = ""\n\n'
    '[ssot]\ndir = "."\nfact_keys = "fact_keys.tsv"\n', encoding="utf-8")
shutil.copy(SHOP_KEYS, DEFS / "fact_keys.tsv")
HUB_DB = HUB / "hub" / "hub.db"


# ---- the two sides -----------------------------------------------------------

def as_hub() -> dict:
    config.use(DEFS)
    return clean_env(HUB_DATA_DIR=str(HUB / "hub"),
                     HUB_AUTH_ENV_PATHS="none")


def hub_run(argv, *, stdin=None, tty=None):
    env = as_hub()
    rc, out, err = capture(
        lambda a: facts.main(a, spec=SPEC, keys=FactKeys(), thresholds=None),
        list(argv), env=env, stdin=stdin, tty_answers=tty)
    return rc, out, err


def hub_confirm(key, market, value, *, new=False):
    """A person at the hub's terminal confirms (and with `new` types)."""
    argv = ["confirm", key, "--market", market, "--reason", "owner"]
    if new:
        argv += ["--value", value]
    return hub_run(argv, tty=[value])


PACK = None


def as_pack(hub_env: bool = True) -> dict:
    cfg = _shop.use()
    extra = {cfg.env("HUB_DIR"): str(HUB)} if hub_env else {}
    return clean_env(**{cfg.env("DATA_DIR"): str(PACK),
                        cfg.env("AUTH_ENV_PATHS"): "none", **extra})


def pack_run(argv, *, tty=None, hub_env=True):
    env = as_pack(hub_env)
    return capture(lambda a: facts.main(a, spec=SPEC, keys=FactKeys(),
                                        thresholds=None),
                   list(argv), env=env, tty_answers=tty)


def sync(*extra):
    rc, out, err = pack_run(["sync-hub", "--json", *extra])
    return rc, one_doc(out) or {}, err


def outcomes(doc) -> dict:
    return {(i["key"], i["market"]): i["outcome"]
            for i in doc.get("results", [])}


def pcon() -> sqlite3.Connection:
    return sqlite3.connect(PACK / "shop.db")


def fact(key, market="US"):
    with closing(pcon()) as c:
        return c.execute("SELECT value, is_assumption, source, changed_by "
                         "FROM client_facts WHERE market=? AND key=?",
                         (market, key)).fetchone()


def copies():
    with closing(pcon()) as c:
        return c.execute("SELECT market, key, value, hub, hub_history_id, "
                         "hub_digest, outcome FROM hub_copies ORDER BY "
                         "copy_id").fetchall()


def hub_id(key, market="US") -> int:
    with closing(sqlite3.connect(HUB_DB)) as c:
        return c.execute("SELECT MAX(id) FROM client_facts_history WHERE "
                         "market=? AND key=?", (market, key)).fetchone()[0]


def hub_bytes() -> dict:
    """The hub's database and WAL (its -shm, SQLite's shared-memory index,
    a reader may touch: the accepted cost of a plain mode=ro open)."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in HUB_DB.parent.glob("hub.db*")
            if not p.name.endswith("-shm")}


def doctor_lines(hub_env=True) -> list[tuple]:
    env = as_pack(hub_env)
    box = {}

    def run(_a):
        box["ctx"] = doctor.collect(spec=SPEC)
        return 0
    capture(run, [], env=env)
    return [(f.level, f.message.code, f.message.params, f.next)
            for f in box["ctx"].findings if f.check == "hub"]


def build_hub() -> None:
    for m in ("US", "CA", "MX"):
        rc, out, err = hub_run(["init"], stdin=f"{m}\n\n", tty=[m])
        assert rc == 0, (out, err)
    for key, value, m in (("unit_cost", "4.2", "US"), ("channel", "web", "US"),
                          ("unit_cost", "3", "MX")):
        rc, out, err = hub_run(["set", key, value, "--market", m, "--source",
                                "owner_call", "--reason", "owner"])
        assert rc == 0, (out, err)
        rc, out, err = hub_confirm(key, m, value)
        assert rc == 0, (out, err)


# ---- 1 -----------------------------------------------------------------------

def test_first_sync() -> None:
    global PACK
    print("[1] the first sync: copied, same, skipped, refused; the hub "
          "untouched")
    build_hub()
    PACK = Path(tmp_dir("shop-hub-"))
    env = as_pack()
    rc, out, err = capture(lambda a: facts.main(a, spec=SPEC, keys=FactKeys(),
                                                thresholds=None),
                           ["init"], env=env, stdin="US\n\n\n\n", tty_answers=["US"])
    check("the pack declared US itself (at its terminal)",
          rc == 0 and fact("market_declared")[1] == 0, (rc, out, err))
    pack_run(["set", "unit_cost", "4.2", "--market", "US", "--source", "own",
              "--reason", "r"])
    pack_run(["confirm", "unit_cost", "--market", "US", "--reason", "r"],
             tty=["4.2"])
    check("… and confirmed unit_cost 4.2 itself", fact("unit_cost")[1] == 0)

    # a live writer: a hand-written, ungated hub row committed in the WAL
    live = sqlite3.connect(HUB_DB, isolation_level=None)
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("PRAGMA wal_autocheckpoint=0")
    live.execute("INSERT INTO client_facts (market, key, value, "
                 "is_assumption, source, updated_at, changed_by) VALUES "
                 "('CA', 'unit_cost', '9', 0, 'hand', 't', 'x@cli')")
    live.execute("INSERT INTO client_facts_history (market, key, action, "
                 "new_value, is_assumption, reason, changed_by, at) VALUES "
                 "('CA', 'unit_cost', 'set', '9', 0, 'hand', 'x@cli', 't')")
    before = hub_bytes()
    rc, doc, err = sync()
    after = hub_bytes()
    live.close()
    got = outcomes(doc)
    check("outcomes: US declared alike = same, CA declaration copied, MX "
          "skipped (not the pack's market), unit_cost US same, channel US "
          "copied, the ungated CA row refused",
          rc == 0 and got == {
              ("market_declared", "US"): "same",
              ("market_declared", "CA"): "copied",
              ("market_declared", "MX"): "skipped",
              ("unit_cost", "US"): "same", ("channel", "US"): "copied",
              ("unit_cost", "CA"): "refused", ("unit_cost", "MX"): "skipped"},
          (got, err))
    check("the summary is coded with every count",
          doc["message_code"]["code"] == "fact_hub_synced"
          and doc["counts"] == {"copied": 2, "same": 2, "conflict": 0,
                                "kept": 0, "refused": 1, "skipped": 2},
          doc.get("counts"))
    refused = [i for i in doc["results"] if i["outcome"] == "refused"][0]
    check("the refusal names the history row that is no gated confirm "
          "(seen in the live WAL)",
          refused["message_code"]["code"] == "fact_hub_ungated"
          and refused["message_code"]["params"]["action"] == "set"
          and refused["message_code"]["params"]["by"] == "x@cli", refused)
    check("the hub's database and WAL bytes are unchanged by the sync "
          "(a live writer holds it open)",
          before == after and "hub.db-wal" in before, (before, after))
    hid = hub_id("channel")
    digest = facts.hub_digest("demo-hub", "US", "channel", "web", hid)
    check("a copy is confirmed with the hub's version and digest as its "
          "source, changed_by <user>@hub",
          fact("channel") == ("web", 0, f"hub:demo-hub@{hid}#{digest[:16]}",
                              f"{USER}@hub")
          and fact("market_declared", "CA")[1:] == (
              0, f"hub:demo-hub@{hub_id('market_declared', 'CA')}#"
              f"{facts.hub_digest('demo-hub', 'CA', 'market_declared', 'CA', hub_id('market_declared', 'CA'))[:16]}",
              f"{USER}@hub"), fact("channel"))
    with closing(pcon()) as c:
        h = c.execute("SELECT action, old_value, new_value, is_assumption, "
                      "changed_by FROM client_facts_history WHERE key="
                      "'channel'").fetchall()
    check("history: one hub_copy row (action in ACTIONS)",
          h == [("hub_copy", None, "web", 0, f"{USER}@hub")]
          and "hub_copy" in facts.ACTIONS, h)
    rows = copies()
    check("hub_copies: one row per copied or same fact, full digest, the "
          "hub's version",
          sorted((r[1], r[0], r[6]) for r in rows) == [
              ("channel", "US", "copied"), ("market_declared", "CA", "copied"),
              ("market_declared", "US", "same"), ("unit_cost", "US", "same")]
          and all(len(r[5]) == 64 and r[3] == "demo-hub" for r in rows)
          and ("US", "channel", "web", "demo-hub", hid, digest, "copied")
          in rows, rows)
    check("the pack's own confirmed unit_cost kept its own source",
          fact("unit_cost")[2] == "own", fact("unit_cost"))
    # the ungated row stays out of the hub (clean up for the later steps)
    with closing(sqlite3.connect(HUB_DB, isolation_level=None)) as c:
        n = c.execute("SELECT count(*) FROM client_facts WHERE market='CA' "
                      "AND key='unit_cost'").fetchone()[0]
    check("(the sync wrote nothing to the hub: the hand row is all there is)",
          n == 1)


# ---- 2 -----------------------------------------------------------------------

def test_once_per_version() -> None:
    print("[2] once per hub version")
    n = len(copies())
    with closing(pcon()) as c:
        h = c.execute("SELECT count(*) FROM client_facts_history").fetchone()
    rc, doc, err = sync()
    with closing(pcon()) as c:
        h2 = c.execute("SELECT count(*) FROM client_facts_history").fetchone()
    check("a rerun: copies found the same, no new history, no new "
          "hub_copies row for an unchanged pack version",
          outcomes(doc)[("channel", "US")] == "same" and h == h2,
          (outcomes(doc), h, h2))
    added = len(copies()) - n
    rc, out, err = pack_run(["unconfirm", "channel", "--market", "US",
                             "--reason", "doubt it"])
    check("a person doubts the copy here (unconfirm)",
          rc == 0 and fact("channel")[1] == 1, out)
    rc, doc, err = sync()
    check("the same hub version does not copy it again: kept, still pending",
          outcomes(doc)[("channel", "US")] == "kept"
          and fact("channel")[1] == 1 and doc["counts"]["kept"] == 1,
          (outcomes(doc), fact("channel")))
    raw = sqlite3.connect(PACK / "shop.db", isolation_level=None)
    errs = []
    for sql in ("UPDATE hub_copies SET outcome='copied'",
                "DELETE FROM hub_copies"):
        try:
            raw.execute(sql)
            errs.append("ok")
        except sqlite3.IntegrityError as e:
            errs.append(str(e)[:16])
    raw.close()
    check("hub_copies is append-only in the file",
          errs == ["refused: UPDATE ", "refused: DELETE "] and added == 0,
          (errs, added))
    pack_run(["confirm", "channel", "--market", "US", "--reason", "ok"],
             tty=["web"])


# ---- 3 -----------------------------------------------------------------------

def test_stale_and_conflict() -> None:
    print("[3] the hub moves: stale, then one conflict ask")
    lines = [x[:2] for x in doctor_lines()]
    check("doctor: current before the hub moves; the hub's hand-written "
          "row is named (fact_hub_ungated)",
          lines == [("warn", "fact_hub_ungated"), ("ok", "fact_hub_current")],
          lines)
    old = hub_id("unit_cost")
    rc, out, err = hub_confirm("unit_cost", "US", "4.5", new=True)
    new = hub_id("unit_cost")
    lines = doctor_lines()
    stale = [x for x in lines if x[1] == "fact_hub_copy_stale"]
    check("doctor: fact_hub_copy_stale names the key and both versions, "
          "the fix is sync-hub",
          rc == 0 and len(stale) == 1 and stale[0][0] == "warn"
          and stale[0][2] == {"key": "unit_cost", "market": "US",
                              "hub": "demo-hub", "hub_version": new,
                              "copied_version": old}
          and stale[0][3] == ["shop facts sync-hub"], lines)
    rc, doc, err = sync()
    item = [i for i in doc["results"] if i["key"] == "unit_cost"
            and i["market"] == "US"][0]
    check("the sync never overwrites the pack's confirmed 4.2: conflict, "
          "coded, next = pending",
          item["outcome"] == "conflict" and item["pack_value"] == "4.2"
          and item["message_code"]["code"] == "fact_hub_conflict"
          and fact("unit_cost")[:2] == ("4.2", 0)
          and doc.get("next") == ["shop pending"], (item, doc))
    lines = [x[:2] for x in doctor_lines()]
    check("doctor is current again (the version was seen)",
          ("ok", "fact_hub_current") in lines
          and ("warn", "fact_hub_copy_stale") not in lines, lines)
    as_pack()
    with closing(db.connect(SPEC, PACK / "shop.db", read_only=True)) as c:
        got = pending.asks(c, keys=FactKeys(), registry=None)
        hub_got = pending.asks(c, keys=FactKeys(), registry=None, hub=True)
    asks = [a for a in got["asks"] if a["id"].startswith("hubfact-")]
    a = asks[0] if asks else {}
    check("pending: ONE choose ask, the hub's value or the own, recommended "
          "the hub's",
          len(asks) == 1 and a["step"] == "choose"
          and [o["value"] for o in a["options"]] == ["4.5", "4.2"]
          and a["recommend"]["value"] == "4.5"
          and a["id"].startswith("hubfact-us-unit_cost-"), asks)
    check("… gated by facts confirm KEY with the chosen value",
          a.get("gate") == {"verb": ["facts", "confirm", "unit_cost"],
                            "value_arg": True,
                            "expect": {"market": "US",
                                       "items": {"unit_cost": "$value"}},
                            "market": "US"}, a.get("gate"))
    hub_ask = [x for x in hub_got["asks"] if "hubfact" in x["id"]]
    check("… in hub mode its id and verb start with the cli word",
          len(hub_ask) == 1 and hub_ask[0]["id"].startswith("shop-hubfact-")
          and hub_ask[0]["gate"]["verb"][0] == "shop", hub_ask)
    rc, out, err = pack_run(["confirm", "unit_cost", "--market", "US",
                             "--value", "4.5", "--reason", "hub's"],
                            tty=["4.5"])
    as_pack()
    with closing(db.connect(SPEC, PACK / "shop.db", read_only=True)) as c:
        left = [x for x in pending.asks(c, keys=FactKeys(), registry=None)
                ["asks"] if x["id"].startswith("hubfact-")]
    check("choosing the hub's value closes the ask", rc == 0 and not left,
          (out, left))
    rc, doc, err = sync()
    check("… and the next sync finds it the same",
          outcomes(doc)[("unit_cost", "US")] == "same", outcomes(doc))


# ---- 4 -----------------------------------------------------------------------

def test_definitions_and_no_hub() -> None:
    print("[4] a key defined otherwise; no hub; no store")
    keys = DEFS / "fact_keys.tsv"
    saved = keys.read_text(encoding="utf-8")
    keys.write_text(saved.replace("\tUSD\t0\t50\t", "\tEUR\t0\t50\t"),
                    encoding="utf-8")
    try:
        rc, doc, err = sync()
        item = [i for i in doc["results"] if i["key"] == "unit_cost"
                and i["market"] == "US"][0]
        check("a key whose unit differs at the hub is skipped, saying why",
              item["outcome"] == "skipped"
              and item["message_code"]["params"]["reason"] == "definition"
              and "unit" in item["message"], item)
        lines = doctor_lines()
        check("doctor names the definition difference",
              any(x[1] == "fact_hub_definition_differs"
                  and x[2]["key"] == "unit_cost" for x in lines), lines)
    finally:
        keys.write_text(saved, encoding="utf-8")
    check("no hub named: doctor says nothing about a hub",
          doctor_lines(hub_env=False) == [], doctor_lines(hub_env=False))
    rc, out, err = pack_run(["sync-hub", "--json"], hub_env=False)
    check("… and sync-hub is a coded refusal naming the variable",
          rc == 2 and one_doc(out)["code"] == "fact_hub_none"
          and one_doc(out)["params"] == {"var": "SHOP_HUB_DIR"}, out)
    empty = Path(tmp_dir("hubs-")) / "other-hub"
    shutil.copytree(DEFS, empty / "hub" / "defs")
    rc, out, err = pack_run(["sync-hub", "--hub", str(empty), "--json"])
    check("a hub with no store yet: fact_hub_missing",
          rc == 2 and one_doc(out)["code"] == "fact_hub_missing", out)


# ---- 5 -----------------------------------------------------------------------

def test_definition_guard() -> None:
    print("[5] definition_diffs and the guard")
    _shop.use()
    d = Path(tmp_dir("defs-"))
    head = "key\tgroup\ttype\tunit\tmin\tmax\tlabel_en\twhy\n"
    (d / "a.tsv").write_text(
        head + "x\tg\tnumber\tUSD\t0\t50\tX\tours\n"
        "y\tg\tchoice:a|b\t\t\t\tY\tours\nz\tg\ttext\t\t\t\tZ\tours\n"
        "only\tg\ttext\t\t\t\tO\tours\n", encoding="utf-8")
    (d / "b.tsv").write_text(
        head + "x\th\tnumber\tUSD\t0.0\t50\tX\ttheirs\n"
        "y\tg\tchoice:b|a\t\t\t\tY\tours\nz\tg\ttext\t\t\t\tZed\tours\n",
        encoding="utf-8")
    diffs = definition_diffs(d / "a.tsv", d / "b.tsv")
    check("bounds compare as numbers, group and why are each file's own; "
          "choice order and a label differ; a key one file lacks is not "
          "compared",
          set(diffs) == {"y", "z"} and diffs["y"][0].startswith("type:")
          and diffs["z"][0].startswith("label_en:"), diffs)
    check("the guard: a pack defining the hub's keys alike has no problem",
          hub_keys.check(HUB, _shop.SHOP) == [],
          hub_keys.check(HUB, _shop.SHOP))
    check("… no hub given checks nothing",
          hub_keys.check(None) == [] and hub_keys.check("") == [])
    keys = DEFS / "fact_keys.tsv"
    saved = keys.read_text(encoding="utf-8")
    keys.write_text(saved.replace("choice:web|store", "choice:web|store|app"),
                    encoding="utf-8")
    try:
        got = hub_keys.check(HUB, _shop.SHOP)
    finally:
        keys.write_text(saved, encoding="utf-8")
    check("… a key defined otherwise is one problem naming it and what "
          "differs", len(got) == 1 and got[0].startswith("channel: type:"),
          got)
    gone = Path(tmp_dir("hubs-")) / "no-defs"
    got = hub_keys.check(gone, _shop.SHOP)
    check("… the hub's definitions missing is a problem too",
          len(got) == 1 and "cannot be read" in got[0], got)


if __name__ == "__main__":
    test_first_sync()
    test_once_per_version()
    test_stale_and_conflict()
    test_definitions_and_no_hub()
    test_definition_guard()
    raise SystemExit(finish())
