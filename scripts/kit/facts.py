"""The client facts verb, `<cli> facts init|list|get|set|confirm|unconfirm|
history|rollback|restore|sync-hub`: the one sanctioned writer of
client_facts.

Ported from the reference skill pack's scripts/facts.py. What it guards:

  * Trust lives in the data. `init`, `set` and `rollback` write PENDING
    values (is_assumption = 1). Only `confirm` raises trust, through the
    human gate (kit.human.confirm): a person retypes the value at the
    terminal, or a relayed code comes back that is bound to the subject
    {key: value} with version = the key's last history id. The confirm
    itself appends a history row, which moves that version, so a code
    works once. `unconfirm` lowers trust and needs no gate. There is no
    bypass flag.
  * A client's own confirmation is theirs (`confirm --for-client NAME`,
    kit.human.client_name): bound into the code's subject, recorded as
    `client:<name>` with the operator who passed the gate in the reason;
    no other path writes a `client:` author.
  * A confirmation belongs to the value that was confirmed. A `set` (or
    `rollback`) never replaces a confirmed value: it is refused, naming
    `unconfirm` (lower trust, recorded) and `confirm --value` (a person's
    new value). A `set` that changes a pending value keeps it pending. A same-value `set` writes
    no history and does not bump updated_at.
  * A value is checked where it is typed (kit.registry.FactKeys, and
    Thresholds for `threshold_<name>` keys): only registered keys, within
    their numeric bounds and choices. It is stored in its canonical form
    (4.20 becomes 4.2), and that form is what the person retypes.
  * The market door. `init` is the only verb that writes a market
    declaration (`market_declared`). The declaration is pending unless a
    person retypes the market at a terminal. Every other write needs a
    confirmed declaration (kit.market.require_declared), and a market is
    never defaulted: an omitted --market resolves to the one market that
    is declared or waiting for confirmation, and nothing else.
  * One write path. Every write runs inside db.keep_human_rows and
    appends a client_facts_history row that records its action (init,
    set, confirm, unconfirm, rollback, restore), the stated --reason and
    the derived changed_by. Inside that write transaction, `confirm`
    checks again that the fact has not moved since the person was asked
    (fact_changed_meanwhile), and `restore` checks again that its diff
    has not changed (fact_restore_moved).
  * `init` collects and validates every answer before it writes the
    first row, so an abort leaves nothing behind. It never overwrites a
    value already on disk.
  * `restore` replays a backup (a SQLite copy, a kit human-table backup
    or a SQL dump) additively into the human tables, and only after a
    person at a terminal types the number of changes. It is TTY only; a
    relayed code never unlocks it.
  * The read verbs (list, get, history) never create the database. Under
    --json every verb prints exactly one document, refusals and usage
    errors included.

Readers for skill pack code: confirmed(), effective(), pending().

A client file's values, one gate with the file (plan_file, apply_file):
the values the agent read from a client's file (kit.workbook_map's
values.tsv) are confirmed by the same human gate as the rest of that file,
not one by one. plan_file() checks each (market, key, value) exactly as
`set` would (a registered key, its bounds and canonical form, a confirmed
market declaration; never the declaration itself) BEFORE any gate runs,
and returns the items the skill pack puts in that gate's subject and the
version every write to those facts moves. apply_file() writes them
confirmed, with the gate's channel as changed_by and history action
`confirm`, after checking again that none of them moved meanwhile. It is
a write that raises trust: only a skill pack verb that has just passed
kit.human.confirm() for a subject holding plan["items"] and
plan["version"] calls it, as `confirm` calls its own write.

A client hub's facts, confirmed once there (`facts sync-hub [--hub DIR]`,
apply_hub_copy, doctor_hub, hub_conflicts): when several skill packs serve
one client, the facts they share (the markets, the currency, break-even
ROAS, …) are confirmed at the client's hub (scaffold/new_hub.py), whose
store `<hub>/hub/hub.db` is the kit's own client_facts with its gate and
history. sync-hub reads it as one in-memory snapshot (hub_snapshot: the
backup API over a `mode=ro` connection, never `immutable=1` on a live WAL
file, never a write), takes the confirmed rows of the keys this skill
pack's fact_keys.tsv declares (and the market declarations of its own
markets) and, for each whose last hub history row is a `confirm` a person
signed: `same` (confirmed alike here), `conflict` (confirmed otherwise
here: never overwritten; `pending` makes it one ask), `copied` (absent or
pending here: written confirmed, source `hub:<hub>@<history id>#<digest16>`,
changed_by `<user>@hub`, history action `hub_copy`) or `kept` (that hub
version was applied before: a person's later step here stands). Each but
`kept` appends a row to the append-only `hub_copies`. A hub row that did not
come from the gate is refused; a key defined otherwise at the hub
(kit.registry.definition_diffs), a market this skill pack does not keep and
a value it refuses are skipped. The hub is never written. doctor's `hub`
check (with `<P>_HUB_DIR` set, as the hub's bin/hub sets it) names every
copy that lags the hub's current version (`fact_hub_copy_stale`) and every
declared, confirmed hub fact never copied (`fact_hub_copy_missing`). A
skill pack without markets serves one hub market per workspace
(`<P>_HUB_MARKET`, exported by the hub's bin/hub): that market's facts land
in its "_" (declarations never: it has no market door); hub_copies keeps
the pack's "_", and the hub row is named by hub_history_id and a digest
over the hub's own market. Nothing refreshes on its own: a person decides.
A key the pack lists with `owner = hub` in fact_keys.tsv (registry.FactKeys,
its definition still alike the hub's) is read here like any other, but
`set`, `confirm`, `rollback` and the init question refuse it while a hub is
in force (`fact_hub_owned`): it is confirmed at the hub and copied. Run with
no hub, it is an ordinary key. A key the hub defines and the pack does not
list is named as the hub's when `set` refuses it (`fact_key_hub_undeclared`).

Deviations from the reference and from the SPEC, each deliberate:
  * No klass, no value_type: the kit's client_facts has neither (a key's
    group lives in the FactKeys registry), so `--klass` is gone, and with
    it fact_confirm_needs_klass / fact_klass_fixed. `confirm --value` on
    a key with no row just creates it, confirmed.
  * The history row carries `action` in its own column; `reason` is the
    plain --reason (the reference encoded "<action>: <why>" in reason).
  * A pending declaration does not open the door (kit.market counts only
    confirmed ones): after a piped `init`, `set` is refused
    (market_not_onboarded) until a person confirms the declaration with
    `facts confirm market_declared`, over the TTY or a relayed code.
    Confirming or unconfirming the declaration itself does not need the
    door.
  * A missing or blank --reason / --source is a coded refusal
    (reason_required, fact_source_required), not an argparse usage error.
    Every usage error is coded too (fact_usage, exit 2), so --json keeps
    its one document.
  * Refusals exit 2 (kit.contract), not 1. The wizard's prompts go to
    stderr and are read from stdin without builtins.input. The wizard's
    questions are the skill pack's `init_questions` ([{"key", "prompt"?}],
    checked against the registry when main() starts), not keys a
    source project hard-coded.
  * An answer that `init` finds on disk is compared in canonical form, so
    retyping 4.20 over a stored 4.2 keeps it. An invalid answer is asked
    again, up to 3 times, just like a new key's answer.
  * The races the reference left open are closed:
    fact_changed_meanwhile, fact_restore_moved, and a re-check in init.
  * A SQL dump is loaded with ATTACH disabled (setlimit), so a hostile
    dump cannot write files through ATTACH DATABASE.

Test: kit/tests/test_facts.py; the hub copy: kit/tests/test_hub_facts.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from kit import contract, dates, db, human, market, registry, schema_base
from kit.config import ConfigError, config
from kit.config import load as load_config
from kit.contract import SkillPackError
from kit.market import MARKET_KEY
from kit.messages import Msg, coded, msg
from kit.registry import FACT_PREFIX, KEY_RE, FactKeys, Thresholds

FACTS, HISTORY = "client_facts", "client_facts_history"
READS = frozenset({"list", "get", "history"})
ACTIONS = ("init", "set", "confirm", "unconfirm", "rollback", "restore",
           "hub_copy")
COPIES = "hub_copies"
# A client hub's layout (scaffold/new_hub.py): <hub>/hub/hub.db is the hub's
# own facts store, <hub>/hub/defs/ its definitions (a skill-pack.toml whose
# [ssot].fact_keys names its key file). The hub's name is its folder's: the
# client id.
HUB_DATA, HUB_DEFS, HUB_DB = "hub", "defs", "hub.db"
GATE_CHANNELS = ("tty", "relay")    # what kit.human.confirm returns
# (current table, its history, required in a backup). A backup taken
# before the decisions store held rows simply has none to replay.
RESTORED = ((FACTS, HISTORY, True), ("decisions", "decisions_history", False))
MAX_ATTEMPTS = 3            # re-asks in init before it gives up
SOURCE_TTY = "owner_interview"      # init's default provenance at a terminal
SOURCE_PIPED = "agent_interview"    # ... and piped: nobody was interviewed
SQLITE_MAGIC = b"SQLite format 3\x00"
QUESTION_KEYS = frozenset({"key", "prompt"})


def _cols(table: str) -> tuple[str, ...]:
    """A human table's columns, minus a history table's local id."""
    return tuple(c for c in schema_base.HUMAN[table]["columns"] if c != "id")


FACT_COLS = tuple(schema_base.HUMAN[FACTS]["columns"])
HIST_COLS = tuple(schema_base.HUMAN[HISTORY]["columns"])


# ---- small SQL helpers -----------------------------------------------------

def _has(con: sqlite3.Connection | None, table: str) -> bool:
    return con is not None and con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone() is not None


def _dicts(cur: sqlite3.Cursor) -> list[dict]:
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def _fetch(con: sqlite3.Connection, m: str, key: str) -> dict | None:
    rows = _dicts(con.execute(
        f"SELECT {', '.join(FACT_COLS)} FROM {FACTS} WHERE market=? AND key=?",
        (m, key)))
    return rows[0] if rows else None


def _last_id(con: sqlite3.Connection, m: str, key: str) -> int:
    """The version a confirm binds: the key's last history id (0 = none).
    Every write to the fact appends a row, so every write moves it."""
    return con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {HISTORY} "
                       f"WHERE market=? AND key=?", (m, key)).fetchone()[0]


def _log(con: sqlite3.Connection, m: str, key: str, action: str,
         old: str | None, new: str | None, is_assumption: int,
         source: str | None, reason: str, by: str, at: str) -> None:
    con.execute(
        f"INSERT INTO {HISTORY} (market, key, action, old_value, new_value, "
        f"is_assumption, source, reason, changed_by, at) "
        f"VALUES (?,?,?,?,?,?,?,?,?,?)",
        (m, key, action, old, new, is_assumption, source, reason, by, at))


# ---- one run of the verb ---------------------------------------------------

@dataclass
class _Run:
    spec: db.SchemaSpec
    keys: FactKeys
    thresholds: Thresholds | None
    questions: list[tuple[str, str]]
    cmd: list[str]
    args: argparse.Namespace
    con: sqlite3.Connection


def _cli() -> str:
    return config().cli


def _say(text: str) -> None:
    """The wizard and the restore diff talk on stderr when stdout is the
    one JSON document."""
    print(text, file=sys.stderr, flush=True)


def _done(run: _Run, note: Msg, doc: dict, nxt: list[str] = ()) -> dict | None:
    """--json: the one document (`note` as a coded `message`); text: the
    note and any next command on stdout."""
    if run.args.json:
        out = {**doc, **coded("message", note)}
        if nxt:
            out["next"] = list(nxt)
        return out
    print(note)
    for c in nxt:
        print(f"next: {c}")
    return None


def _not_found(key: str, m: str) -> SkillPackError:
    return SkillPackError(msg("fact_not_found",
                            f"no fact {key!r} for market {m!r}",
                            key=key, market=m))


def _market(run: _Run, explicit: str | None, *, door: bool) -> str:
    """The market a verb acts on. Explicit: validated, and for a write
    (`door`) confirmed-declared. Omitted: the one market declared or
    waiting for its confirmation, never a default; then, for a write,
    it must be confirmed-declared too (market_not_onboarded says how)."""
    con = run.con
    if explicit:
        m = market.validate(explicit)
    else:
        ms = market.declared(con, include_pending=True)
        if not ms:
            return market.resolve(con, None, cmd=run.cmd)  # market_none_declared
        if len(ms) > 1:
            raise SkillPackError(msg(
                "fact_market_ambiguous",
                f"{len(ms)} markets are declared or waiting for "
                f"confirmation ({', '.join(ms)}) — pass --market to say "
                f"which.", markets=ms),
                [shlex.join([*run.cmd, "--market", x]) for x in ms])
        m = ms[0]
    if door:
        market.require_declared(con, m)
    return m


def _key_shape(key: str) -> None:
    if not KEY_RE.match(key):
        raise SkillPackError(msg(
            "fact_key_malformed",
            f"key {key!r} must be snake_case ^[a-z][a-z0-9_]*$ and carry no "
            f"units (e.g. unit_cost, not cost_4_2)", key=key))


def _settable(run: _Run, key: str) -> None:
    """A key `set` (and so `rollback`) may write, else its coded refusal:
    fact_key_malformed, or FactKeys' fact_key_unknown."""
    _key_shape(key)
    if key not in run.keys.settable(run.thresholds):
        _validate(run, key, "")                                # raises
    _hub_owned(run, key)


def _validate(run: _Run, key: str, raw: str) -> str:
    """FactKeys.validate, with one more word on an unknown key: with a hub
    in force, a key the hub defines is named as the hub's (a pack lists it
    with `owner = hub`), where plain "nothing reads it" sends nobody
    anywhere."""
    try:
        return run.keys.validate(key, raw, thresholds=run.thresholds)
    except SkillPackError as e:
        if getattr(e.message, "code", None) != "fact_key_unknown":
            raise
        hint = _hub_key_hint(key)
        if hint is None:
            raise
        raise hint from None


def _hub_key_hint(key: str) -> SkillPackError | None:
    try:
        hub = hub_dir()
        if hub is None:
            return None
        theirs = hub_keys_path(hub)
        if key not in {r["key"] for r in registry.read_tsv(theirs, ["key"])}:
            return None
    except SkillPackError:
        return None
    return SkillPackError(msg(
        "fact_key_hub_undeclared", f"{key!r} is a fact of the hub {hub.name}, "
        f"which this skill pack does not list. Add its row to fact_keys.tsv "
        f"as the hub defines it ({theirs}), with owner = hub", key=key,
        hub=hub.name, file=str(theirs)),
        [f"{_cli()} facts sync-hub"])


def _hub_blocked(run: _Run, key: str) -> bool:
    """True when `key` is the hub's to confirm and a hub is in force."""
    return key in run.keys.hub_owned() and hub_dir() is not None


def _hub_owned(run: _Run, key: str) -> None:
    """Refuse to write a key the pack lists as `owner = hub` while a hub is
    in force (`<P>_HUB_DIR`): it is confirmed once at the hub and copied by
    `facts sync-hub`. With no hub it is an ordinary key, so a skill pack
    run on its own still works."""
    if key not in run.keys.hub_owned():
        return
    hub = hub_dir()
    if hub is None:
        return
    raise SkillPackError(msg(
        "fact_hub_owned", f"{key} is confirmed at the hub {hub.name}, not "
        f"here: set it there, then copy it with `{_cli()} facts sync-hub`",
        key=key, hub=hub.name),
        [f"{hub}/bin/hub hub facts set {key} VALUE --market M --source S "
         f"--reason R", f"{_cli()} facts sync-hub"])


def _stored(run: _Run, key: str, raw: str) -> str:
    """The canonical value to store, after every check a write makes."""
    _key_shape(key)
    _hub_owned(run, key)
    return _validate(run, key, raw)


def _labels(run: _Run, key: str) -> dict:
    """{group, unit, label_<lang>…} of a key from its registry row (the
    fact key registry, or the thresholds one for threshold_<name>)."""
    row = run.keys.row(key)
    if row is None and run.thresholds is not None \
            and key.startswith(FACT_PREFIX):
        row = run.thresholds.row(key[len(FACT_PREFIX):])
    row = row or {}
    return {"group": row.get("group") or None, "unit": row.get("unit") or None,
            **{f"label_{lang}": row.get(f"label_{lang}") or None
               for lang in config().languages}}


def _apply_set(con: sqlite3.Connection, m: str, key: str, stored: str,
               source: str, by: str, reason: str, action: str
               ) -> tuple[str, Msg]:
    """The ungated write of a pending value; the caller holds the
    transaction and has checked the key, value and market. Returns
    (change, note): change = new | changed | source | none."""
    existing = _fetch(con, m, key)
    at = human.now()
    if existing is None:
        con.execute(f"INSERT INTO {FACTS} (market, key, value, is_assumption, "
                    f"source, updated_at, changed_by) VALUES (?,?,?,1,?,?,?)",
                    (m, key, stored, source, at, by))
        _log(con, m, key, action, None, stored, 1, source, reason, by, at)
        return "new", msg(
            "fact_set_new", f"set {key} [{m}] = {stored} (new, pending until "
            f"a human confirms it)", key=key, market=m, value=stored)
    if existing["value"] != stored and not existing["is_assumption"]:
        # A value a person confirmed is never replaced by an ungated write:
        # the confirmed number would vanish from the table every rule reads.
        # Lowering trust is its own recorded step; a new value is a person's.
        cli = _cli()
        raise SkillPackError(msg(
            "fact_set_confirmed", f"{key} [{m}] = {existing['value']} was "
            f"confirmed by a person; {action} does not replace it with "
            f"{stored}. Nothing was written", key=key, market=m,
            value=existing["value"], new=stored, action=action),
            [shlex.join([cli, "facts", "unconfirm", key, "--market", m]),
             shlex.join([cli, "facts", "confirm", key, "--market", m,
                         "--value", stored])])
    if existing["value"] != stored:
        # A confirmation belongs to the value confirmed: a new value is
        # pending again, or a placeholder would inherit the confirmation.
        con.execute(f"UPDATE {FACTS} SET value=?, is_assumption=1, source=?, "
                    f"updated_at=?, changed_by=? WHERE market=? AND key=?",
                    (stored, source, at, by, m, key))
        _log(con, m, key, action, existing["value"], stored, 1, source, reason,
             by, at)
        return "changed", msg(
            "fact_set_changed", f"set {key} [{m}]: {existing['value']} → "
            f"{stored} (pending until a human confirms it)", key=key,
            market=m, old=existing["value"], new=stored)
    # Same value: no history row, no updated_at bump; only a new source.
    change = "none"
    if existing["source"] != source:
        con.execute(f"UPDATE {FACTS} SET source=? WHERE market=? AND key=?",
                    (source, m, key))
        change = "source"
    return change, msg(
        "fact_set_unchanged", f"set {key} [{m}]: value unchanged ({stored}); "
        f"no history row", key=key, market=m, value=stored)


# ---- read verbs ------------------------------------------------------------

def cmd_list(run: _Run) -> dict | None:
    a, con = run.args, run.con
    if a.thresholds:
        return _thresholds(run)
    where, params = [], []
    if a.market:
        where.append("market=?")
        params.append(market.validate(a.market))
    if a.pending:
        where.append("is_assumption=1")
    sql = f"SELECT {', '.join(FACT_COLS)} FROM {FACTS}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    rows = _dicts(con.execute(sql + " ORDER BY market, key", params))
    declared = market.declared(con)
    waiting = [m for m in market.declared(con, include_pending=True)
               if m not in declared]
    if a.json:
        return {"declared_markets": declared, "pending_markets": waiting,
                "facts": [{**r, **_labels(run, r["key"])} for r in rows],
                "settable_keys": list(run.keys.settable(run.thresholds))}
    print("declared market(s): " + (", ".join(declared) or
                                    f"none — run `{_cli()} facts init`"))
    if waiting:
        print("waiting for a human to confirm the declaration: "
              + ", ".join(waiting))
    print(f"{len(rows)} fact(s)" + (" [pending only]" if a.pending else ""))
    for r in rows:
        mark = "*" if r["is_assumption"] else " "
        print(f" {mark} {r['market']:<4} {r['key']:<32} {r['value']!s:<20} "
              f"src={r['source']} updated={r['updated_at']}")
    print(f"(* = pending: not in effect until a human confirms it, "
          f"`{_cli()} facts confirm <key> --market <M>`)")
    return None


def _thresholds(run: _Run) -> dict | None:
    """Every overridable threshold per market: default, the market's
    threshold_<name> fact (confirmed or pending) and the value in effect."""
    a, con = run.args, run.con
    ms = ([market.validate(a.market)] if a.market
          else market.declared(con, include_pending=True))
    rows = ([r for m in ms for r in run.thresholds.listing(con, m)]
            if run.thresholds is not None else [])
    if a.json:
        return {"thresholds": rows}
    print(f"{len(rows)} threshold(s) for {', '.join(ms) or 'no market'}")
    for r in rows:
        mark = "*" if r["is_assumption"] else " "
        client = "—" if r["value"] is None else r["value"]
        print(f" {mark} {r['market']:<4} {r['name']:<32} "
              f"default={r['default']:<8g} client={client!s:<8} "
              f"effective={r['effective']:g} ({r['in_effect']})")
    print(f"(* = pending: not in effect until `{_cli()} facts confirm "
          f"threshold_<name> --market <M>`)")
    return None


def cmd_get(run: _Run) -> dict | None:
    # Reads validate the market but skip the door: a row under a market
    # whose declaration is pending must stay visible.
    m = _market(run, run.args.market, door=False)
    row = _fetch(run.con, m, run.args.key)
    if row is None:
        raise _not_found(run.args.key, m)
    if run.args.json:
        return row
    for c in FACT_COLS:
        print(f"{c:<14} {row[c]}")
    return None


def cmd_history(run: _Run) -> dict | None:
    a = run.args
    m = _market(run, a.market, door=False)
    sql = f"SELECT {', '.join(HIST_COLS)} FROM {HISTORY} WHERE market=?"
    params: list[Any] = [m]
    if a.key:
        sql += " AND key=?"
        params.append(a.key)
    # `at`, then id: a restore appends older rows after newer ones.
    rows = _dicts(run.con.execute(sql + " ORDER BY at, id", params))
    if a.json:
        return {"market": m, "key": a.key, "history": rows}
    print(f"{len(rows)} history row(s) for {a.key or 'every key'} [{m}]")
    for r in rows:
        print(f"  #{r['id']:<4} {r['at']}  {r['key']:<24} {r['action']:<9} "
              f"{r['old_value']!s:<16} → {r['new_value']!s:<16} "
              f"by={r['changed_by']}  {r['reason']}")
    return None


# ---- write verbs -----------------------------------------------------------

def cmd_set(run: _Run) -> dict | None:
    a = run.args
    reason = human.why(a.reason)
    source = (a.source or "").strip()
    if not source:
        raise SkillPackError(msg(
            "fact_source_required",
            "--source is required: where the value came from (e.g. "
            "owner_interview_<YYYY-MM-DD>), not who typed it; history's "
            "changed_by says who"))
    stored = _stored(run, a.key, a.value)
    m = _market(run, a.market, door=True)
    with db.keep_human_rows(run.spec, run.con):
        change, note = _apply_set(run.con, m, a.key, stored, source,
                                  human.changed_by("cli"), reason, "set")
        row = _fetch(run.con, m, a.key)
    return _done(run, note, {"set": [row], "change": change})


def _state(row: dict | None) -> tuple | None:
    return None if row is None else (row["value"], row["is_assumption"])


def cmd_confirm(run: _Run) -> dict | None:
    """Pending → confirmed, a human act: the value retyped at the terminal,
    or the relayed --code bound to {key: value} at the key's last history
    id. `--value V` confirms the human's own value instead (validated like
    `set`, and the challenge binds V). The market declaration is confirmed
    here too (`confirm market_declared`), without the door it opens.
    `--for-client NAME`: the client's own confirmation, passed through the
    operator's channel: the name is in the code's subject (an operator's
    code never passes for it, nor back), history and the row record
    `client:<name>`, a typed value's source is `client:<name> <date>`, and
    the reason keeps who passed the gate (` [operator=…]`)."""
    a, con = run.args, run.con
    reason = human.why(a.reason)
    client = human.client_name(a.for_client)
    _hub_owned(run, a.key)
    typed = None if a.value is None else _stored(run, a.key, a.value)
    m = _market(run, a.market, door=a.key != MARKET_KEY)
    existing = _fetch(con, m, a.key)
    if existing is None and typed is None:
        raise _not_found(a.key, m)
    old = existing["value"] if existing else None
    value = old if typed is None else typed
    if typed is None and old is not None and run.thresholds is not None \
            and a.key.startswith(FACT_PREFIX):  # its bound may have moved
        run.thresholds.validate(a.key, str(old))    # refuses; keeps `old`
    if existing is not None and old == value and not existing["is_assumption"]:
        return _done(run, msg(
            "fact_already_confirmed", f"{a.key} [{m}] = {value}: already "
            f"confirmed", key=a.key, market=m, value=value),
            {"confirmed": [], "already_confirmed": [existing]})
    last = _last_id(con, m, a.key)
    was = "" if old in (None, value) else f" (replacing {old})"
    channel = human.confirm(
        f"`{_cli()} facts confirm`",
        human.client_prompt(client)
        + f"{a.key} [{m}] = {value}{was} — retype the value to confirm it: ",
        value, code=a.code,
        subj=human.subject("facts confirm", m, "fact", {a.key: value}, last,
                           client))
    reason += (human.relay_audit(channel, a.relay_user, a.relay_at)
               + human.client_audit(channel, client))
    by = human.changed_by(channel, client)
    with db.keep_human_rows(run.spec, con):
        if (_last_id(con, m, a.key) != last
                or _state(_fetch(con, m, a.key)) != _state(existing)):
            raise SkillPackError(msg(
                "fact_changed_meanwhile",
                f"{a.key} [{m}] changed while the human was being asked; "
                f"the confirmation no longer matches it. Nothing was "
                f"written.", key=a.key, market=m),
                [shlex.join([_cli(), "facts", "get", a.key, "--market", m])])
        at = human.now()
        if existing is None:
            source = human.typed_source(client)
            con.execute(f"INSERT INTO {FACTS} (market, key, value, "
                        f"is_assumption, source, updated_at, changed_by) "
                        f"VALUES (?,?,?,0,?,?,?)",
                        (m, a.key, value, source, at, by))
        elif old != value:
            source = human.typed_source(client)
            con.execute(f"UPDATE {FACTS} SET value=?, is_assumption=0, "
                        f"source=?, updated_at=?, changed_by=? "
                        f"WHERE market=? AND key=?",
                        (value, source, at, by, m, a.key))
        else:
            source = existing["source"]
            con.execute(f"UPDATE {FACTS} SET is_assumption=0, changed_by=? "
                        f"WHERE market=? AND key=?", (by, m, a.key))
        _log(con, m, a.key, "confirm", old, value, 0, source, reason, by, at)
        row = _fetch(con, m, a.key)
    return _done(run, msg(
        "fact_confirmed", f"confirmed {a.key} [{m}] = {value}"
        + (f" (was {old})" if old not in (None, value) else ""),
        key=a.key, market=m, value=value, was=old),
        {"confirmed": [row], "changed_by": by, "reason": reason})


# ---- a client file's values, confirmed with the file -----------------------

def plan_file(con: sqlite3.Connection,
              values: list[tuple[str, str, str]], *, keys: FactKeys,
              thresholds: Thresholds | None = None) -> dict:
    """The facts a client file states, checked before its one gate.

    `values` are (market, key, raw value). -> {"items": {market: {key:
    value}} (canonical values: what the gate binds and shows),
    "version": the facts' last history ids joined (every write moves it),
    "rows": [{market, key, value, old, state, last}], "lines": one line
    per value for the gate's prompt}. Refused (coded) at the first value
    `set` would refuse, or the market declaration itself."""
    rows, items, lines = [], {}, []
    for m, key, raw in values:
        m = market.validate(m)
        if key == MARKET_KEY:
            raise SkillPackError(msg(
                "fact_file_declaration",
                f"a client file cannot declare a market ({MARKET_KEY} "
                f"[{m}]); `facts init` does", market=m))
        _key_shape(key)
        if key not in keys.settable(thresholds):
            keys.validate(key, "", thresholds=thresholds)       # raises
        value = keys.validate(key, raw, thresholds=thresholds)
        market.require_declared(con, m)
        if key in items.get(m, {}):
            raise SkillPackError(msg(
                "fact_file_twice", f"{key} [{m}] is stated twice",
                key=key, market=m))
        existing = _fetch(con, m, key)
        old = existing["value"] if existing else None
        rows.append({"market": m, "key": key, "value": value, "old": old,
                     "state": _state(existing),
                     "last": _last_id(con, m, key)})
        items.setdefault(m, {})[key] = value
        was = "" if old in (None, value) else f" (replacing {old})"
        lines.append(f"{key} [{m}] = {value}{was}")
    version = ",".join(f"{r['market']}:{r['key']}:{r['last']}" for r in rows)
    return {"items": items, "version": version, "rows": rows,
            "lines": lines}


def apply_file(spec: db.SchemaSpec, con: sqlite3.Connection, plan: dict, *,
               channel: str, reason: str, source: str,
               client: str | None = None) -> list[dict]:
    """Write plan_file()'s values confirmed, after the skill pack's gate
    passed for a subject holding plan["items"] and plan["version"]
    (`channel` is what kit.human.confirm returned). A value already
    confirmed as it is writes nothing. -> the rows written. Refused,
    nothing written, if any of the facts moved since the plan
    (fact_changed_meanwhile)."""
    if channel not in ("tty", "relay"):        # what a gate returns
        raise ValueError(f"apply_file: channel {channel!r} is no gate's "
                         f"(tty or relay)")
    by = human.changed_by(channel, client)
    reason = human.why(reason)
    out = []
    with db.keep_human_rows(spec, con):
        for r in plan["rows"]:
            m, key = r["market"], r["key"]
            if (_last_id(con, m, key) != r["last"]
                    or _state(_fetch(con, m, key)) != r["state"]):
                raise SkillPackError(msg(
                    "fact_changed_meanwhile",
                    f"{key} [{m}] changed while the human was being asked; "
                    f"the confirmation no longer matches it. Nothing was "
                    f"written.", key=key, market=m),
                    [shlex.join([_cli(), "facts", "get", key, "--market",
                                 m])])
        for r in plan["rows"]:
            m, key, value, old = r["market"], r["key"], r["value"], r["old"]
            if r["state"] == (value, 0):
                continue
            at = human.now()
            if r["state"] is None:
                con.execute(f"INSERT INTO {FACTS} (market, key, value, "
                            f"is_assumption, source, updated_at, changed_by) "
                            f"VALUES (?,?,?,0,?,?,?)",
                            (m, key, value, source, at, by))
            else:
                con.execute(f"UPDATE {FACTS} SET value=?, is_assumption=0, "
                            f"source=?, updated_at=?, changed_by=? "
                            f"WHERE market=? AND key=?",
                            (value, source, at, by, m, key))
            _log(con, m, key, "confirm", old, value, 0, source, reason, by,
                 at)
            out.append(_fetch(con, m, key))
    return out


def cmd_unconfirm(run: _Run) -> dict | None:
    """Confirmed → pending. Lowering trust needs no human: anyone (an
    agent included) may say a number is in doubt; history records who and
    why, and only `confirm` puts it back in effect."""
    a, con = run.args, run.con
    reason = human.why(a.reason)
    m = _market(run, a.market, door=a.key != MARKET_KEY)
    with db.keep_human_rows(run.spec, con):
        existing = _fetch(con, m, a.key)
        if existing is None:
            raise _not_found(a.key, m)
        if existing["is_assumption"]:
            return _done(run, msg(
                "fact_already_pending", f"{a.key} [{m}] = "
                f"{existing['value']}: already pending", key=a.key, market=m,
                value=existing["value"]), {"unconfirmed": [], "fact": existing})
        by, at = human.changed_by("cli"), human.now()
        con.execute(f"UPDATE {FACTS} SET is_assumption=1, changed_by=? "
                    f"WHERE market=? AND key=?", (by, m, a.key))
        _log(con, m, a.key, "unconfirm", existing["value"], existing["value"],
             1, existing["source"], reason, by, at)
        row = _fetch(con, m, a.key)
    return _done(run, msg(
        "fact_unconfirmed", f"{a.key} [{m}] = {row['value']} is pending again "
        f"(a human re-confirms it with `{_cli()} facts confirm`)",
        key=a.key, market=m, value=row["value"]), {"unconfirmed": [row]})


def cmd_rollback(run: _Run) -> dict | None:
    """The value one of the key's history rows wrote, back as a PENDING
    value (source rollback_to_<id>_<date>): `set`'s own checks and write,
    so it drives nothing until a human confirms it. A history row of
    another key or market is refused."""
    a, con = run.args, run.con
    reason = human.why(a.reason)
    _settable(run, a.key)
    m = _market(run, a.market, door=True)
    with db.keep_human_rows(run.spec, con):
        rows = _dicts(con.execute(f"SELECT {', '.join(HIST_COLS)} FROM "
                                  f"{HISTORY} WHERE id=?", (a.to,)))
        if not rows:
            raise SkillPackError(
                msg("fact_history_not_found", f"no history row #{a.to}",
                    id=a.to),
                [shlex.join([_cli(), "facts", "history", a.key,
                             "--market", m])])
        h = rows[0]
        if (h["key"], h["market"]) != (a.key, m):
            raise SkillPackError(msg(
                "fact_history_other",
                f"history row #{a.to} is {h['key']} [{h['market']}], not "
                f"{a.key} [{m}]. Nothing was written.", id=a.to, key=a.key,
                market=m, row_key=h["key"], row_market=h["market"]))
        if h["new_value"] is None:
            raise SkillPackError(msg(
                "fact_history_no_value", f"history row #{a.to} wrote no "
                f"value. Nothing was written.", id=a.to))
        stored = _stored(run, a.key, h["new_value"])
        existing = _fetch(con, m, a.key)
        if existing is None:
            raise _not_found(a.key, m)
        if existing["value"] == stored:
            return _done(run, msg(
                "fact_rollback_nothing", f"{a.key} [{m}] is already {stored} "
                f"(history row #{a.to}); nothing written", key=a.key,
                market=m, value=stored, id=a.to),
                {"rolled_back": [], "fact": existing})
        _apply_set(con, m, a.key, stored,
                   f"rollback_to_{a.to}_{dates.today().isoformat()}",
                   human.changed_by("cli"), reason, "rollback")
        row = _fetch(con, m, a.key)
    return _done(run, msg(
        "fact_rolled_back", f"rolled {a.key} [{m}] back: {existing['value']} → "
        f"{stored} (history row #{a.to}), pending until a human confirms it",
        key=a.key, market=m, old=existing["value"], new=stored, id=a.to),
        {"rolled_back": [row]},
        [f"{_cli()} facts confirm {a.key} --market {m} --reason <why>"])


# ---- init: the onboarding wizard -------------------------------------------

def _ask(prompt: str) -> str:
    """One answer from stdin (never builtins.input: the prompt goes to
    stderr, so --json keeps stdout for the one document). End of input
    and Ctrl-C abort cleanly: nothing has been written yet."""
    print(prompt, end="", file=sys.stderr, flush=True)
    try:
        line = sys.stdin.readline() if sys.stdin is not None else ""
    except KeyboardInterrupt:
        raise SkillPackError(msg("fact_init_interrupted",
                               "init aborted at the keyboard. Nothing was "
                               "written.")) from None
    if not line:
        raise SkillPackError(msg("fact_init_eof",
                               "init aborted: no answer for the last question "
                               "(end of input). Nothing was written."))
    answer = line.rstrip("\r\n")
    try:
        piped = not sys.stdin.isatty()
    except (AttributeError, ValueError):
        piped = True
    if piped:
        # Nothing echoes a pipe: show which answer went to which question.
        print(f"  → {answer}", file=sys.stderr, flush=True)
    return answer


def _ask_market(con: sqlite3.Connection) -> str:
    markets = config().markets
    have = market.declared(con, include_pending=True)
    if have:
        _say(f"already declared in this DB: {', '.join(have)}")
    for _ in range(MAX_ATTEMPTS):
        raw = _ask(f"market (one of {', '.join(markets)}): ")
        if not raw.strip():
            raise SkillPackError(msg("fact_init_no_market",
                                   "init aborted: no market given. Nothing "
                                   "was written."))
        try:
            return market.validate(raw)
        except SkillPackError as e:
            _say(f"  {e} — try again.")
    raise SkillPackError(msg(
        "fact_init_bad_market", f"init aborted: no valid market after "
        f"{MAX_ATTEMPTS} attempts. Nothing was written.",
        attempts=MAX_ATTEMPTS, markets=list(markets)))


def _would_overwrite(key: str, m: str, current: str, typed: str
                     ) -> SkillPackError:
    return SkillPackError(msg(
        "fact_init_would_overwrite",
        f"{key} is already {current!r} for market {m}; refusing to overwrite "
        f"it with {typed!r}. Nothing was written. To change it deliberately, "
        f"use `{_cli()} facts set`.", key=key, market=m, current=current,
        typed=typed),
        [shlex.join([_cli(), "facts", "set", key, typed, "--market", m])
         + " --source <where the value came from> --reason <why>"])


def _ask_value(run: _Run, m: str, key: str, prompt: str,
               current: dict | None) -> str | None:
    """The canonical answer for one question, or None to leave the key
    as it is. A blank answer skips; an invalid one is asked again. The
    one place init could hurt trust is a question whose answer is on
    disk: the same value (in canonical form) keeps it, a different one is
    refused, since correcting a value is `set`'s job."""
    shown = None if current is None else current["value"]
    hint = "enter to skip" if current is None else f"{shown}; enter keeps it"
    for _ in range(MAX_ATTEMPTS):
        raw = _ask(f"{prompt} [{hint}]: ").strip()
        if not raw:
            return None
        try:
            stored = _validate(run, key, raw)
        except SkillPackError as e:
            _say(f"  {e} — try again.")
            continue
        if current is None:
            return stored
        if stored == shown:
            return None
        raise _would_overwrite(key, m, shown, stored)
    raise SkillPackError(msg(
        "fact_init_bad_answer", f"init aborted: no valid answer for {key} "
        f"after {MAX_ATTEMPTS} attempts. Nothing was written.", key=key,
        attempts=MAX_ATTEMPTS))


def cmd_init(run: _Run) -> dict | None:
    """The one door through which a market enters the DB: its declaration
    (`market_declared`, pending unless a human retypes the market at a
    terminal), then the skill pack's init questions, as pending facts.
    Collect-all-then-write: every answer is read and validated before the
    first row is written, in one transaction."""
    cfg, con = config(), run.con
    _say(f"{cfg.cli} facts init — onboarding. Answers are read from stdin, "
         f"one per line; end of input aborts without writing anything.")
    partitioned = bool(cfg.markets)
    m = _ask_market(con) if partitioned else market.PSEUDO
    answers: dict[str, str] = {}
    asked = [q for q in run.questions if not _hub_blocked(run, q[0])]
    n = len(asked)
    for i, (key, prompt) in enumerate(asked, 1):
        v = _ask_value(run, m, key, f"[{i}/{n} {key}] {prompt}",
                       _fetch(con, m, key))
        if v is not None:
            answers[key] = v
    at_tty = human.stdin_is_tty()
    default = (f"{SOURCE_TTY if at_tty else SOURCE_PIPED}_"
               f"{dates.today().isoformat()}")
    source = _ask(f"provenance source [{default}]: ").strip() or default

    # The declaration: a human at a terminal retypes the market to confirm
    # it (the gate, TTY only); a piped run leaves it pending. Asked before
    # the write phase, so no prompt interrupts the transaction.
    decl = _fetch(con, m, MARKET_KEY) if partitioned else None
    unconfirmed = partitioned and (decl is None or bool(decl["is_assumption"]))
    confirm_now = False
    if unconfirmed and at_tty:
        try:
            human.require_human(
                f"`{cfg.cli} facts init` (the market declaration)",
                f"retype the market ({m}) to confirm the declaration: ", m)
            confirm_now = True
        except human.Refused as e:
            _say(f"  {e}")

    # -- write phase: no prompt from here on --
    reason = f"onboarding ({cfg.cli} facts init)"
    by = human.changed_by("cli")
    written: list[dict] = []
    notes: list[Msg] = []
    with db.keep_human_rows(run.spec, con):
        if partitioned:
            if _fetch(con, m, MARKET_KEY) is None:
                change, note = _apply_set(con, m, MARKET_KEY, m, source, by,
                                          reason, "init")
                written.append({"key": MARKET_KEY, "value": m,
                                "change": change})
                notes.append(note)
            row = _fetch(con, m, MARKET_KEY)
            if confirm_now and row["is_assumption"]:
                tty_by, at = human.changed_by("tty"), human.now()
                con.execute(f"UPDATE {FACTS} SET is_assumption=0, "
                            f"changed_by=? WHERE market=? AND key=?",
                            (tty_by, m, MARKET_KEY))
                _log(con, m, MARKET_KEY, "confirm", m, m, 0, row["source"],
                     "market declared at onboarding", tty_by, at)
        for key, stored in answers.items():
            cur = _fetch(con, m, key)
            if cur is not None:       # written since it was asked
                if cur["value"] == stored:
                    continue
                raise _would_overwrite(key, m, cur["value"], stored)
            change, note = _apply_set(con, m, key, stored, source, by, reason,
                                      "init")
            written.append({"key": key, "value": stored, "change": change})
            notes.append(note)
        decl = _fetch(con, m, MARKET_KEY) if partitioned else None
    state = ("none" if decl is None
             else "pending" if decl["is_assumption"] else "confirmed")
    recorded = sum(1 for w in written if w["key"] != MARKET_KEY)
    kept = [k for k, _ in asked if k not in answers]
    nxt = ([f"{cfg.cli} facts confirm {MARKET_KEY} --market {m} "
            f"--reason <why>"] if state == "pending" else [])
    note = msg("fact_init_done",
               f"market {m}: onboarding done, {recorded} fact(s) recorded; "
               f"the declaration is {state}"
               + (" (a human confirms it)" if state == "pending" else ""),
               market=m, recorded=recorded, declaration=state)
    if not run.args.json:
        for n_ in notes:
            print(f"  {n_}")
        for k in kept:
            print(f"  {k}: left as-is")
    return _done(run, note, {"market": m, "declaration": state,
                             "written": written, "kept": kept}, nxt)


# ---- restore: replay a backup ----------------------------------------------

def _load_backup(path: str) -> sqlite3.Connection:
    """A SQLite file (opened read-only) or a SQL dump (loaded into memory,
    ATTACH disabled). Either must hold both client_facts tables in the
    kit's columns; the decisions pair is optional."""
    p = Path(path)
    if not p.is_file():
        raise SkillPackError(msg("fact_backup_missing", f"no such file: {path}",
                               path=str(path)))
    con = None
    try:
        with open(p, "rb") as f:
            is_sqlite = f.read(16) == SQLITE_MAGIC
        if is_sqlite:
            con = sqlite3.connect(p.absolute().as_uri() + "?mode=ro", uri=True)
        else:
            text = p.read_text(encoding="utf-8")
            con = sqlite3.connect(":memory:")
            con.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            con.executescript(text)
        for table, hist, required in RESTORED:
            if required or _has(con, table):
                for t in (table, hist):
                    con.execute(f"SELECT {', '.join(_cols(t))} FROM {t} "
                                f"LIMIT 0")
    except (sqlite3.Error, UnicodeDecodeError, OSError) as e:
        if con is not None:
            con.close()
        raise SkillPackError(msg(
            "fact_backup_unusable", f"{path} is not a usable backup (a SQLite "
            f"file or a SQL dump holding the human tables): {e}",
            path=str(path), detail=str(e))) from None
    return con


def _plan(con: sqlite3.Connection, src: sqlite3.Connection, table: str,
          hist: str) -> tuple[list, list]:
    """([(current row | None, backup row)] that differ, [history rows the
    DB lacks]) for one human table and its history (rows as tuples in
    _cols order; history matched as a multiset, ids aside)."""
    if not _has(src, table):
        return [], []
    cols, hcols = _cols(table), _cols(hist)
    pk = [cols.index(c) for c in schema_base.HUMAN[table]["pk"]]

    def ident(r: tuple) -> tuple:
        return tuple(r[i] for i in pk)

    order = ", ".join(cols[i] for i in pk)
    backup = src.execute(f"SELECT {', '.join(cols)} FROM {table} "
                         f"ORDER BY {order}").fetchall()
    backup_hist = src.execute(f"SELECT {', '.join(hcols)} FROM {hist} "
                              f"ORDER BY id").fetchall()
    current = {ident(r): r for r in con.execute(
        f"SELECT {', '.join(cols)} FROM {table}").fetchall()}
    have = Counter(con.execute(f"SELECT {', '.join(hcols)} FROM {hist}"
                               ).fetchall())
    missing = []
    for r in backup_hist:
        if have[r]:
            have[r] -= 1
        else:
            missing.append(r)
    changes = [(current.get(ident(r)), r) for r in backup
               if current.get(ident(r)) != r]
    return changes, missing


def _plans(run: _Run, src: sqlite3.Connection) -> list[tuple]:
    return [(t, h, *_plan(run.con, src, t, h)) for t, h, _req in RESTORED
            if t in run.spec.human_tables and h in run.spec.human_tables]


def _trusted(table: str, row: dict) -> bool:
    return (row.get("is_assumption") == 0 if table == FACTS
            else row.get("status") == "confirmed")


def _show(plans: list[tuple], path: str, out) -> None:
    print(f"restore from {path}:", file=out)
    for table, _hist, changes, missing in plans:
        cols = _cols(table)
        pk = schema_base.HUMAN[table]["pk"]
        for old, new in changes:
            r = dict(zip(cols, new))
            name = " ".join(str(r[c]) for c in pk)
            state = " (confirmed)" if _trusted(table, r) else ""
            if old is None:
                print(f"  + {name} = {r['value']!r}{state}", file=out)
            else:
                was = dict(zip(cols, old))["value"]
                print(f"  ~ {name}: {was!r} → {r['value']!r}{state} "
                      f"(src={r.get('source')})", file=out)
        if table == FACTS or changes or missing:
            print(f"  {table}: {len(changes)} row(s) to add/change, "
                  f"{len(missing)} history row(s) to append", file=out)


def cmd_restore(run: _Run) -> dict | None:
    """Replay a backup into the human tables (client_facts, and the
    decisions store when the backup has it). Additive by construction:
    a current row is inserted or set to the backup's row, never deleted;
    history rows the DB lacks are inserted verbatim (their changed_by, at
    and reason), and each row the backup changes gets one `restore`
    history row of its own. TTY only: a human types the number of
    changes. A second run finds nothing to do."""
    a, con = run.args, run.con
    why = human.why(a.reason)
    src = _load_backup(a.src)
    try:
        plans = _plans(run, src)
        _show(plans, a.src, sys.stderr if a.json else sys.stdout)
        total = sum(len(c) + len(mi) for *_x, c, mi in plans)
        if not total:
            return _done(run, msg(
                "fact_restore_nothing", f"nothing to restore — this DB already "
                f"holds everything in {a.src}.", path=a.src), {"restored": {}})
        human.require_human(f"`{_cli()} facts restore`",
                            f"type the number of changes ({total}) to apply "
                            f"them: ", str(total))
        by, now = human.changed_by("tty"), human.now()
        with db.keep_human_rows(run.spec, con):
            if _plans(run, src) != plans:
                raise SkillPackError(msg(
                    "fact_restore_moved", f"the database changed while the "
                    f"restore from {a.src} was being confirmed. Nothing was "
                    f"written.", path=a.src))
            for table, hist, changes, missing in plans:
                cols, hcols = _cols(table), _cols(hist)
                pk = schema_base.HUMAN[table]["pk"]
                rest = [c for c in cols if c not in pk]
                for r in missing:
                    con.execute(f"INSERT INTO {hist} ({', '.join(hcols)}) "
                                f"VALUES ({', '.join('?' * len(hcols))})", r)
                for old, new in changes:
                    n = dict(zip(cols, new))
                    if old is None:
                        con.execute(f"INSERT INTO {table} ({', '.join(cols)}) "
                                    f"VALUES ({', '.join('?' * len(cols))})",
                                    new)
                    else:
                        con.execute(
                            f"UPDATE {table} SET "
                            + ", ".join(f"{c}=?" for c in rest) + " WHERE "
                            + " AND ".join(f"{c}=?" for c in pk),
                            (*(n[c] for c in rest), *(n[c] for c in pk)))
                    h = {c: n[c] for c in hcols if c in n}
                    h.update(action="restore", reason=why, changed_by=by,
                             at=now, new_value=n["value"],
                             old_value=None if old is None
                             else dict(zip(cols, old))["value"])
                    con.execute(f"INSERT INTO {hist} ({', '.join(h)}) VALUES "
                                f"({', '.join('?' * len(h))})",
                                tuple(h.values()))
    finally:
        src.close()
    tables = {t: {"rows": len(c), "history": len(mi)}
              for t, _h, c, mi in plans if c or mi}
    return _done(run, msg(
        "fact_restored", "restored: " + "; ".join(
            f"{t} {v['rows']} row(s), {v['history']} history row(s) appended"
            for t, v in tables.items()) + ".", tables=tables),
        {"restored": tables})


# ---- a client hub's confirmed facts, copied --------------------------------

def hub_db_path(hub: Path | str) -> Path:
    return Path(hub) / HUB_DATA / HUB_DB


def hub_keys_path(hub: Path | str) -> Path:
    """The hub's fact key file, as its own skill-pack.toml declares it
    (read, never bound). Refused (fact_hub_unreadable) without one."""
    defs = Path(hub) / HUB_DATA / HUB_DEFS
    try:
        p = load_config(defs).ssot_path("fact_keys")
    except ConfigError as e:
        p, detail = None, str(e)
    else:
        detail = "it declares no [ssot].fact_keys"
    if p is None:
        raise SkillPackError(msg(
            "fact_hub_defs_unreadable", f"the hub's definitions {defs} "
            f"cannot be read: {detail}", path=str(defs), detail=detail))
    return p


def hub_dir(explicit: str | None = None) -> Path | None:
    """The client hub: `explicit` (--hub, resolved), else `<P>_HUB_DIR`
    (absolute; the hub's bin/hub exports it), else None."""
    if explicit is not None and explicit.strip():
        return Path(explicit).expanduser().resolve()
    var = config().env("HUB_DIR")
    raw = os.environ.get(var, "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise SkillPackError(msg(
            "fact_hub_not_absolute", f"{var}={raw} is a relative path; the "
            f"hub is named by an absolute one, never the current directory",
            var=var, value=raw))
    return p


def hub_snapshot(hub: Path | str) -> sqlite3.Connection:
    """The hub's facts store as one in-memory copy, read through SQLite's
    backup API from a `mode=ro` connection. The hub is a live WAL
    database: `immutable=1` would read it as if no writer existed (a
    half-applied WAL, a stale page), so a plain read-only connection is
    used and SQLite may touch its -shm; the database file itself is never
    written. The copy is one consistent snapshot (a current row and its
    history from the same moment), the hub's read lock is held only for
    the copy, and every later step reads the copy, so no code path here
    can write the hub. Refused (coded): no hub database, or one without
    the kit's client_facts tables."""
    path = hub_db_path(hub)
    if not path.is_file():
        raise SkillPackError(msg(
            "fact_hub_missing", f"no hub facts store at {path}: the hub has "
            f"confirmed nothing yet, or {hub} is not a client hub",
            hub=str(hub), path=str(path)),
            [f"{Path(hub) / 'bin' / 'hub'} hub facts list"])
    mem = sqlite3.connect(":memory:")
    try:
        src = sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)
        try:
            src.backup(mem)
        finally:
            src.close()
        for t in (FACTS, HISTORY):
            mem.execute(f"SELECT {', '.join(_cols(t))} FROM {t} LIMIT 0")
    except sqlite3.Error as e:
        mem.close()
        raise SkillPackError(msg(
            "fact_hub_unreadable", f"the hub facts store {path} cannot be "
            f"read as the kit's client facts: {e}", path=str(path),
            detail=str(e))) from None
    return mem


def _signed(by: str | None) -> bool:
    """A history row a person signed through the gate: `<user>@tty|relay`
    (kit.human.changed_by), or a client's own confirmation (`client:…`)."""
    by = str(by or "")
    return by.startswith(human.CLIENT) or (
        "@" in by and by.rsplit("@", 1)[1] in GATE_CHANNELS)


def hub_rows(snap: sqlite3.Connection, keys: set[str] | frozenset[str]
             ) -> list[dict]:
    """The hub's confirmed facts of `keys`, declarations first: {market,
    key, value, history_id (the fact's last history id: its version),
    action, changed_by, gated}. `gated`: that last history row is a
    `confirm` of this very value that a person signed (tty, relay or a
    client's own); anything else (a hand edit, a restore, an ungated
    write) is not the hub's confirmation."""
    out = []
    for m, key, value in snap.execute(
            f"SELECT market, key, value FROM {FACTS} WHERE is_assumption=0 "
            f"ORDER BY key != ?, market, key", (MARKET_KEY,)).fetchall():
        if key not in keys:
            continue
        h = snap.execute(
            f"SELECT id, action, new_value, is_assumption, changed_by FROM "
            f"{HISTORY} WHERE market=? AND key=? ORDER BY id DESC LIMIT 1",
            (m, key)).fetchone()
        gated = (h is not None and h[1] == "confirm" and h[2] == value
                 and h[3] == 0 and _signed(h[4]))
        out.append({"market": m, "key": key, "value": value,
                    "history_id": h[0] if h else 0,
                    "action": h[1] if h else None,
                    "changed_by": h[4] if h else None, "gated": gated})
    return out


def hub_digest(hub: str, m: str, key: str, value: str, history_id: int
               ) -> str:
    """sha256 of the hub fact a copy came from (hub, market, key, value,
    history id), so a copy names the exact confirmation it rests on."""
    doc = {"hub": hub, "market": m, "key": key, "value": value,
           "history_id": history_id}
    return hashlib.sha256(json.dumps(
        doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def hub_market() -> str | None:
    """The one hub market a skill pack without a market partition serves:
    `<P>_HUB_MARKET` (the hub's bin/hub exports it for that pack folder,
    `new_hub.py add-pack --market`), None when unset. A skill pack with
    markets copies each hub market into its own and is refused one
    (fact_hub_market_partitioned)."""
    var = config().env("HUB_MARKET")
    raw = os.environ.get(var, "").strip()
    if not raw:
        return None
    if config().markets:
        raise SkillPackError(msg(
            "fact_hub_market_partitioned", f"{var}={raw}: this skill pack "
            f"keeps its own markets and copies each hub market into its "
            f"own; unset {var}", var=var, value=raw))
    return raw


def _to_pack(m: str, key: str, served: str | None) -> str | None:
    """The market of this skill pack a hub row of market `m` lands in, None
    when it is not this skill pack's: with a served hub market (a skill
    pack without partition), that market's rows land in "_" and its
    declaration does not (no market door there); else the same market,
    as spelled, when this skill pack keeps it."""
    if served is not None:
        return market.PSEUDO if m == served and key != MARKET_KEY else None
    try:
        return m if market.validate(m) == m else None
    except SkillPackError:
        return None


def _unserved(m: str, key: str, served: str | None) -> bool:
    """A hub row this skill pack should hold and cannot: it keeps no market,
    serves none, and the hub's row is of a real market (not a
    declaration)."""
    return (not config().markets and served is None and m != market.PSEUDO
            and key != MARKET_KEY)


def _applied(con: sqlite3.Connection, m: str, key: str, hub: str,
             history_id: int) -> bool:
    """Has this hub version been copied or found the same here before?"""
    return con.execute(
        f"SELECT 1 FROM {COPIES} WHERE market=? AND key=? AND hub=? AND "
        f"hub_history_id=? AND outcome IN ('copied', 'same') LIMIT 1",
        (m, key, hub, history_id)).fetchone() is not None


def apply_hub_copy(spec: db.SchemaSpec, con: sqlite3.Connection, *,
                   keys: FactKeys, hub: str, m: str, key: str, value: str,
                   history_id: int, digest: str) -> str:
    """One confirmed, gated hub fact into this skill pack -> its outcome:

      * `same`      the skill pack's confirmed value is the hub's;
      * `conflict`  the skill pack has its own confirmed, different value:
                    never overwritten (`pending` makes it one ask);
      * `copied`    absent or pending here: written confirmed (source
                    `hub:<hub>@<history_id>#<digest16>`, changed_by
                    `<user>@hub`, history action `hub_copy`);
      * `kept`      absent or pending here, but this hub version was
                    copied (or the same) before: a person's later step here
                    stands, the same version is never copied twice.

    Each outcome but `kept` appends a hub_copies row (one per hub version
    and pack version). No gate: the human act is the hub's own gated
    confirm, which the caller has checked (hub_rows' `gated`) and which
    `history_id` and `digest` name. The value is checked as `set` checks
    it, and every key but the declaration needs the market's door."""
    stored = m if key == MARKET_KEY else _stored_hub(keys, key, value)
    by = human.changed_by("hub")
    with db.keep_human_rows(spec, con):
        if key == MARKET_KEY:
            market.validate(m)
        else:
            market.require_declared(con, m)
        row = _fetch(con, m, key)
        if row is not None and row["is_assumption"] == 0:
            outcome = "same" if row["value"] == stored else "conflict"
        elif _applied(con, m, key, hub, history_id):
            outcome = "kept"
        else:
            outcome, at = "copied", human.now()
            src = f"hub:{hub}@{history_id}#{digest[:16]}"
            if row is None:
                con.execute(f"INSERT INTO {FACTS} (market, key, value, "
                            f"is_assumption, source, updated_at, changed_by) "
                            f"VALUES (?,?,?,0,?,?,?)",
                            (m, key, stored, src, at, by))
            else:
                con.execute(f"UPDATE {FACTS} SET value=?, is_assumption=0, "
                            f"source=?, updated_at=?, changed_by=? "
                            f"WHERE market=? AND key=?",
                            (stored, src, at, by, m, key))
            _log(con, m, key, "hub_copy", row and row["value"], stored, 0,
                 src, f"copied from hub {hub}, its confirm #{history_id}",
                 by, at)
        if outcome != "kept":
            con.execute(
                f"INSERT OR IGNORE INTO {COPIES} (market, key, value, hub, "
                f"hub_history_id, hub_digest, outcome, pack_history_id, "
                f"copied_at, copied_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (m, key, value, hub, history_id, digest, outcome,
                 _last_id(con, m, key), human.now(), by))
    return outcome


def _stored_hub(keys: FactKeys, key: str, value: str) -> str:
    stored = keys.validate(key, value)
    if stored != value:
        raise SkillPackError(msg(
            "fact_hub_value_form", f"the hub's {key} = {value!r} reads as "
            f"{stored!r} here: the two definitions differ", key=key,
            value=value, stored=stored))
    return stored


def _hub_scope(keys: FactKeys, hub: Path) -> tuple[set[str], dict]:
    """(the keys this skill pack declares, {key: definition differences
    with the hub's})."""
    return (set(keys.keys()) | {MARKET_KEY},
            registry.definition_diffs(keys.path, hub_keys_path(hub)))


def cmd_sync_hub(run: _Run) -> dict | None:
    """Copy the hub's confirmed facts of the keys this skill pack declares
    (apply_hub_copy, one outcome each), declarations first. Reported and
    not written: a hub fact whose last history row is no gated confirm
    (`refused`), and one of a market this skill pack does not keep, a key
    the two define differently, or a value this skill pack refuses
    (`skipped`). Never writes the hub."""
    hub = hub_dir(run.args.hub)
    if hub is None:
        raise SkillPackError(msg(
            "fact_hub_none", f"no hub named: pass --hub DIR or set "
            f"{config().env('HUB_DIR')} (the hub's bin/hub sets it)",
            var=config().env("HUB_DIR")))
    name = hub.name
    served = hub_market()
    snap = hub_snapshot(hub)
    try:
        keys, diffs = _hub_scope(run.keys, hub)
        rows = hub_rows(snap, keys)
    finally:
        snap.close()
    results: list[dict] = []
    for r in rows:
        m, key, value, hid = r["market"], r["key"], r["value"], r["history_id"]
        pm = _to_pack(m, key, served)
        item = {"market": m, "key": key, "value": value,
                "hub_history_id": hid}
        if pm is not None and pm != m:
            item["pack_market"] = pm
        note = None
        if pm is None and _unserved(m, key, served):
            item["outcome"] = "skipped"
            note = msg("fact_hub_skipped", f"{key} [{m}]: not copied (this "
                       f"skill pack keeps no market and serves no hub market: "
                       f"set {config().env('HUB_MARKET')}, as the hub's "
                       f"bin/hub does for a folder added with --market)",
                       key=key, market=m, reason="no_hub_market")
        elif pm is None:
            item["outcome"] = "skipped"
            note = msg("fact_hub_skipped", f"{key} [{m}]: not copied "
                       f"(market {m} is not one this skill pack serves)",
                       key=key, market=m, reason="market")
        elif key in diffs:
            item["outcome"] = "skipped"
            note = msg("fact_hub_skipped", f"{key} [{m}]: not copied (its "
                       f"definition here differs from the hub's: "
                       f"{'; '.join(diffs[key])})", key=key, market=m,
                       reason="definition")
        elif not r["gated"]:
            item["outcome"] = "refused"
            note = msg("fact_hub_ungated", f"{key} [{m}]: the hub's value "
                       f"{value} did not come from its gate (last history "
                       f"#{hid}: {r['action']} by {r['changed_by']}); not "
                       f"copied", key=key, market=m, history_id=hid,
                       action=r["action"], by=r["changed_by"])
        else:
            try:
                item["outcome"] = apply_hub_copy(
                    run.spec, run.con, keys=run.keys, hub=name, m=pm,
                    key=key, value=value, history_id=hid,
                    digest=hub_digest(name, m, key, value, hid))
            except SkillPackError as e:
                item["outcome"] = "skipped"
                note = msg("fact_hub_skipped", f"{key} [{m}]: not copied "
                           f"({e.message})", key=key, market=m,
                           reason=getattr(e.message, "code", None) or "")
            if item["outcome"] == "conflict":
                mine = _fetch(run.con, pm, key)["value"]
                item["pack_value"] = mine
                note = msg("fact_hub_conflict", f"{key} [{m}]: the hub "
                           f"confirmed {value}, this skill pack confirmed "
                           f"{mine}; kept, a person chooses (`{_cli()} "
                           f"pending`)", key=key, market=m, value=value,
                           pack_value=mine)
        if note is not None:
            item.update(coded("message", note))
        results.append(item)
    counts = Counter(i["outcome"] for i in results)
    n = {k: counts.get(k, 0) for k in
         ("copied", "same", "conflict", "kept", "refused", "skipped")}
    summary = msg("fact_hub_synced",
                  f"hub {name}: {n['copied']} copied, {n['same']} the same, "
                  f"{n['conflict']} conflict(s), {n['kept']} kept, "
                  f"{n['refused']} refused, {n['skipped']} skipped",
                  hub=name, copied=n["copied"], same=n["same"],
                  conflict=n["conflict"], kept=n["kept"],
                  refused=n["refused"], skipped=n["skipped"])
    if not run.args.json:
        for i in results:
            print(f"  {i['outcome']:<8} {i['key']} [{i['market']}] = "
                  f"{i['value']} (hub #{i['hub_history_id']})"
                  + (f": {i['message']}" if "message" in i else ""))
    nxt = [f"{_cli()} pending"] if n["conflict"] else []
    return _done(run, summary, {"hub": name, "path": str(hub),
                                "results": results, "counts": n}, nxt)


def hub_copied(con: sqlite3.Connection | None, m: str, key: str, hub: str
               ) -> int | None:
    """The newest hub version this skill pack has seen for the fact (any
    outcome), None when none (or no hub_copies table yet)."""
    if not _has(con, COPIES):
        return None
    return con.execute(f"SELECT MAX(hub_history_id) FROM {COPIES} WHERE "
                       f"market=? AND key=? AND hub=?",
                       (m, key, hub)).fetchone()[0]


def hub_conflicts(con: sqlite3.Connection | None, m: str | None = None
                  ) -> list[dict]:
    """The open conflicts with a hub: per (market, key, hub), its newest
    hub_copies row is a `conflict` and this skill pack still holds its own
    confirmed, different value. {market, key, value (this skill pack's),
    hub, hub_value, hub_history_id, source, changed_by, updated_at}."""
    if not _has(con, COPIES) or not _has(con, FACTS):
        return []
    sql = (f"SELECT c.market, c.key, c.hub, c.value, c.hub_history_id FROM "
           f"{COPIES} c WHERE c.copy_id = (SELECT MAX(copy_id) FROM {COPIES} "
           f"d WHERE d.market=c.market AND d.key=c.key AND d.hub=c.hub) AND "
           f"c.outcome='conflict'")
    params: tuple = ()
    if m is not None:
        sql += " AND c.market=?"
        params = (m,)
    out = []
    for cm, key, hub, hv, hid in con.execute(
            sql + " ORDER BY c.market, c.key, c.hub", params).fetchall():
        row = _fetch(con, cm, key)
        if row is None or row["is_assumption"] or row["value"] == hv:
            continue
        out.append({"market": cm, "key": key, "value": row["value"],
                    "hub": hub, "hub_value": hv, "hub_history_id": hid,
                    "source": row["source"], "changed_by": row["changed_by"],
                    "updated_at": row["updated_at"]})
    return out


def doctor_hub(ctx: Any) -> None:
    """kit.doctor's `hub` check: with a hub named (`<P>_HUB_DIR`), each
    gated hub fact of a key this skill pack declares, of a market it
    serves (_to_pack), is checked against hub_copies: never seen is
    `fact_hub_copy_missing` (the key and market), seen at an older version
    `fact_hub_copy_stale` (the key, both versions); the fix is sync-hub.
    A skill pack without markets that serves no hub market has every hub
    row of a market missing. A hub fact that did not come from the hub's
    gate and a key defined otherwise at the hub warn too; ok only when
    every checked fact is copied at its current version. No hub named:
    nothing."""
    hub = hub_dir()
    if hub is None:
        return
    try:
        served = hub_market()
        snap = hub_snapshot(hub)
        try:
            scope, diffs = _hub_scope(FactKeys(), hub)
            rows = hub_rows(snap, scope)
        finally:
            snap.close()
    except SkillPackError as e:
        ctx.warn("hub", e.message, e.next)
        return
    con, name, sync = ctx.con(), hub.name, f"{_cli()} facts sync-hub"
    stale = checked = 0
    for key, diff in sorted(diffs.items()):
        ctx.warn("hub", msg(
            "fact_hub_definition_differs", f"{key} is defined differently "
            f"here and at hub {name}: {'; '.join(diff)}; it is not copied "
            f"until the two agree", key=key, hub=name, diff=diff))
    for r in rows:
        m, key, hid = r["market"], r["key"], r["history_id"]
        pm = _to_pack(m, key, served)
        if key in diffs or (pm is None and not _unserved(m, key, served)):
            continue
        checked += 1
        if not r["gated"]:
            ctx.warn("hub", msg(
                "fact_hub_ungated", f"{key} [{m}]: the hub's value "
                f"{r['value']} did not come from its gate (last history "
                f"#{hid}: {r['action']} by {r['changed_by']}); not copied",
                key=key, market=m, history_id=hid, action=r["action"],
                by=r["changed_by"]))
            continue
        seen = None if pm is None else hub_copied(con, pm, key, name)
        if seen is None:
            stale += 1
            fix = [sync] if pm is not None else [
                f"export {config().env('HUB_MARKET')}=<the hub market this "
                f"folder serves>  # new_hub.py add-pack --market", sync]
            ctx.warn("hub", msg(
                "fact_hub_copy_missing", f"{key} [{m}]: confirmed at the hub, "
                f"never copied here", key=key, market=m), fix)
        elif seen < hid:
            stale += 1
            ctx.warn("hub", msg(
                "fact_hub_copy_stale", f"{key} [{m}]: hub {name} is at "
                f"#{hid}, this skill pack copied #{seen}", key=key,
                market=m, hub=name, hub_version=hid, copied_version=seen),
                [sync])
    if not stale and not diffs:
        ctx.ok("hub", msg("fact_hub_current", f"hub {name}: every confirmed "
                          f"fact this skill pack declares is copied at its "
                          f"current version ({checked} checked)",
                          hub=name, checked=checked))


# ---- the verb --------------------------------------------------------------

class _Parser(argparse.ArgumentParser):
    """argparse whose usage errors are coded refusals (fact_usage, exit 2),
    so --json keeps its one document."""

    def error(self, message: str):
        raise SkillPackError(msg("fact_usage", f"{self.prog}: {message}",
                               detail=message), [f"{self.prog} --help"])


def _parser(cli: str) -> argparse.ArgumentParser:
    p = _Parser(prog=f"{cli} facts",
                description="Client facts: what the client told us, per "
                            "market; pending until a human confirms it.",
                epilog="This verb is the only sanctioned writer of "
                       "client_facts; hand SQL edits are a violation.")
    sub = p.add_subparsers(dest="verb", required=True, metavar="VERB")

    def add(name: str, fn: Callable, text: str, *, key: str | None = "key",
            with_market: bool = True) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=text, description=text)
        if key == "key":
            sp.add_argument("key")
        elif key == "optional":
            sp.add_argument("key", nargs="?")
        if with_market:
            sp.add_argument("--market", help="the market; omit it when "
                            "exactly one is declared (there is no default)")
        contract.add_json_arg(sp)
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init, "onboarding: declare a market and answer the init "
        "questions (answers read from stdin, one per line; all pending)",
        key=None, with_market=False)
    sp = add("list", cmd_list, "every fact (* = pending)", key=None)
    sp.add_argument("--thresholds", action="store_true",
                    help="every overridable threshold: default, the "
                         "market's own value and the value in effect")
    sp.add_argument("--pending", action="store_true",
                    help="only the facts waiting for a human's confirmation")
    add("get", cmd_get, "one fact")
    sp = add("set", cmd_set, "record a value, pending until a human confirms "
             "it (writes history)")
    sp.add_argument("value")
    sp.add_argument("--source", help="where the value came from (required), "
                    "e.g. owner_interview_2026-09-21 — not who typed it")
    sp.add_argument("--reason", help="why (required; kept in history)")
    sp = add("confirm", cmd_confirm, "pending → confirmed: a human retypes "
             "the value at a terminal, or relays back a --code; --value "
             "confirms the human's own value instead")
    sp.add_argument("--value", help="the value the human confirms instead "
                    "of the pending one (validated like `set`)")
    human.add_gate_args(sp, for_client=True)
    sp = add("unconfirm", cmd_unconfirm, "confirmed → pending (anyone, "
             "agents included: it only lowers trust)")
    sp.add_argument("--reason", help="why it is doubted (required)")
    add("history", cmd_history, "the append-only change log (one key, or "
        "every key of the market)", key="optional")
    sp = add("rollback", cmd_rollback, "write the value a history row wrote "
             "back as a pending value (a human then confirms it)")
    sp.add_argument("--to", type=int, required=True, metavar="HISTORY_ID",
                    help="the history row whose value to go back to")
    sp.add_argument("--reason", help="why roll back (required)")
    sp = add("restore", cmd_restore, "replay a backup additively (never "
             "deletes); a human at a terminal confirms the diff",
             key=None, with_market=False)
    sp.add_argument("--from", dest="src", required=True,
                    help="a SQLite file (a copy or a kit backup) or a SQL "
                         "dump")
    sp.add_argument("--reason", help="why restore (required)")
    sp = add("sync-hub", cmd_sync_hub, "copy the client hub's confirmed "
             "facts of the keys this skill pack declares (never over a "
             "value confirmed here; never writes the hub)", key=None,
             with_market=False)
    sp.add_argument("--hub", help="the client hub's folder (default: "
                    "$<PREFIX>_HUB_DIR, which the hub's bin/hub sets)")
    return p


def _questions(init_questions: list[dict] | None, keys: FactKeys,
               thresholds: Thresholds | None) -> list[tuple[str, str]]:
    """[(key, prompt)] from the skill pack's init questions, checked once:
    a known dict shape, a settable key, no key twice. The prompt defaults
    to the key's label in the skill pack's first language. A bad list is a
    ValueError: a bug in the skill pack, not a runtime condition."""
    out: list[tuple[str, str]] = []
    settable = keys.settable(thresholds)
    for q in init_questions or []:
        if not isinstance(q, dict) or not set(q) <= QUESTION_KEYS \
                or not isinstance(q.get("key"), str):
            raise ValueError(f"init question {q!r}: a dict with 'key' (and "
                             f"optionally 'prompt')")
        key = q["key"]
        if key not in settable:
            raise ValueError(f"init question {key!r} is not a settable fact "
                             f"key ({', '.join(settable)})")
        if key in (k for k, _ in out):
            raise ValueError(f"init question {key!r} is listed twice")
        prompt = q.get("prompt")
        if prompt is None:
            label = (keys.row(key) or {}).get(f"label_{config().languages[0]}")
            if label is None and thresholds is not None:
                label = (thresholds.row(key[len(FACT_PREFIX):]) or {}).get(
                    f"label_{config().languages[0]}")
            prompt = label or key
        if not isinstance(prompt, str):
            raise ValueError(f"init question {key!r}: prompt must be a str")
        out.append((key, prompt))
    return out


def _check_spec(spec: db.SchemaSpec) -> None:
    missing = [t for t in (FACTS, HISTORY) if t not in spec.human_tables]
    if missing:
        raise ValueError(f"spec lacks the kit's human tables {missing}: "
                         f"build it with kit.db.with_human()")


def main(argv: list[str] | None = None, *, spec: db.SchemaSpec,
         keys: FactKeys, thresholds: Thresholds | None,
         init_questions: list[dict] | None = None) -> int:
    """`<cli> facts VERB …`; returns the exit code (0 ok, 2 a named
    refusal, 1 anything else). `argv` starts at the verb."""
    argv = sys.argv[1:] if argv is None else list(argv)
    _check_spec(spec)
    questions = _questions(init_questions, keys, thresholds)
    cmd = [_cli(), "facts", *argv]
    parser = _parser(_cli())

    def run(argv: list[str]) -> Any:
        args = parser.parse_args(argv)
        if args.verb in READS:
            if (e := contract.missing_db_error()) is not None:
                raise e
            con = db.connect(spec, read_only=True)
        else:
            con = db.connect(spec)
        try:
            return args.fn(_Run(spec, keys, thresholds, questions, cmd, args,
                                con))
        finally:
            con.close()

    return contract.run_main(run, argv, cmd=cmd)


# ---- readers for skill pack code ----------------------------------------------

def effective(con: sqlite3.Connection | None, market: str, key: str
              ) -> tuple[str, bool] | None:
    """(value, confirmed) of the market's fact, None when there is none
    (or no client_facts table). A pending value is returned with False:
    it is what was said, not what is in effect."""
    if not _has(con, FACTS):
        return None
    r = con.execute(f"SELECT value, is_assumption FROM {FACTS} "
                    f"WHERE market=? AND key=?", (market, key)).fetchone()
    return None if r is None else (r[0], not r[1])


def confirmed(con: sqlite3.Connection | None, market: str, key: str
              ) -> str | None:
    """The market's value for `key` when a human confirmed it, else None.
    A pending value that replaced a confirmed one is not in effect."""
    e = effective(con, market, key)
    return e[0] if e is not None and e[1] else None


def pending(con: sqlite3.Connection | None, market: str | None
            ) -> list[dict]:
    """Every fact waiting for a human (is_assumption = 1) for `market`
    (None = every market), market declarations included, as client_facts
    rows ordered by market and key: what `<cli> pending` asks about."""
    if not _has(con, FACTS):
        return []
    sql = f"SELECT {', '.join(FACT_COLS)} FROM {FACTS} WHERE is_assumption=1"
    params: tuple = ()
    if market is not None:
        sql += " AND market=?"
        params = (market,)
    return _dicts(con.execute(sql + " ORDER BY market, key", params))
