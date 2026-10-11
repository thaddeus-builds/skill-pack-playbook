"""One human gate per client file: the map of a client's workbook and the
values the agent read from it (kit.workbook_map's values.tsv) are confirmed
together, once per version, never one number at a time.

The flow, with the harness's own verbs around it:

  1. the agent writes the map's files with every new row `proposed` and
     the harness stores them as a staged bundle (no gate: nothing in it is
     read yet);
  2. ask() is the one console ask for that bundle (the `staged=` hook of
     kit.pending), its gate the harness's confirm verb for this version;
  3. that verb calls plan() and then confirm(): one retype at a terminal,
     or one relayed code, bound to exactly what plan() found; the values
     are written as confirmed facts (kit.facts.apply_file);
  4. the harness stores plan()["files"] (the same bundle with every row
     confirmed) as the bundle in force, with confirm()'s record.

What it guards:

  * the ask and the gate cannot disagree: ask()'s `expect` and confirm()'s
    subject are both built from plan()["items"]; the subject's version is
    the bundle in force and every fact's last history id, so a used code is
    stale once the bundle lands or a fact moves;
  * the binding is small whatever the map's size: the staged bundle's
    version and the confirmed one's (hashes of every byte of the files),
    the number of map rows, and every value in full;
  * every value is checked as `facts set` checks it, before the gate
    (kit.facts.plan_file): a value the harness would refuse never reaches
    the owner;
  * nothing is written before the gate passes, and a fact that moved
    meanwhile refuses all of them.

Test: kit/tests/test_file_gate.py.
"""

from __future__ import annotations

import sqlite3

from kit import db, facts, human
from kit import workbook_map as WM
from kit.registry import FactKeys, Thresholds

CONFIRM_WORD = "confirm"            # what a person retypes at a terminal
ENTITY = "workbook_map"
SHOWN = 30                          # map rows an ask shows (the console's)


def plan(con: sqlite3.Connection, files: dict[str, str],
         prev: WM.Map | None, *, keys: FactKeys,
         thresholds: Thresholds | None = None,
         fields: set[str] | None = None) -> dict:
    """What confirming the staged bundle `files` ({file name: text}) over
    `prev` (the bundle in force, or None) would do.

    -> {"staged": its Map, "map": the confirmed Map, "files": the confirmed
    texts, "rows": {row id: content} of the map rows it confirms, "values":
    the values it confirms, "facts": kit.facts.plan_file()'s plan, "items":
    what the gate binds, "version": what the gate's write moves}.
    Refused (coded) when the bundle breaks the map's rules or a value is
    one `facts set` would refuse."""
    staged, probs = WM.parse_texts(files)
    WM.check(staged, fields, keys=set(keys.settable(thresholds)),
             extra=probs)
    yes = WM.texts_confirmed(files)
    new, _ = WM.parse_texts(yes)
    passing = WM.gate_rows(prev, new)
    rows = {k: v for k, v in passing.items() if not k.startswith("value:")}
    values = [v for v in new.values
              if f"value:{v['key']}|{v['market']}" in passing]
    fp = facts.plan_file(con, [(v["market"], v["key"], v["value"])
                               for v in values],
                         keys=keys, thresholds=thresholds)
    items: dict = {"bundle": staged.version, "confirms": new.version,
                   "rows": len(rows)}
    if fp["items"]:
        items["facts"] = fp["items"]
    return {"staged": staged, "map": new, "files": yes, "rows": rows,
            "values": values, "facts": fp, "items": items,
            "version": f"{prev.version if prev else 'none'}|{fp['version']}"}


def subject(verb: list[str], p: dict) -> str:
    """What a relayed code for this plan is bound to."""
    return human.subject(" ".join(verb), "", ENTITY, p["items"],
                         p["version"])


def ask(name: str, p: dict, *, verb: list[str],
        source: str | None = None) -> dict:
    """The staged file for kit.pending's `staged=` hook: one ask, its gate
    `verb` (the harness's confirm verb for this version, plain words) and
    an `expect` that is exactly plan()'s items. Each value is shown in the
    canonical form the gate binds and writes (4.20 is shown 4.2)."""
    return {"name": name, "version": p["staged"].version, "source": source,
            "rows": len(p["rows"]),
            "shown": [[k, v.replace("\t", " | ")]
                      for k, v in sorted(p["rows"].items())][:SHOWN],
            "values": [{"key": v["key"], "market": v["market"],
                        "value": p["facts"]["items"][v["market"]][v["key"]],
                        "cell": v["cell"]} for v in p["values"]],
            "verb": list(verb), "expect": {"items": p["items"]}}


def confirm(spec: db.SchemaSpec, con: sqlite3.Connection, p: dict, *,
            verb: list[str], reason: str | None, code: str | None = None,
            relay_user: str | None = None, relay_at: str | None = None,
            source: str) -> dict:
    """The one gate for the whole file, then its values written confirmed
    (kit.facts.apply_file, `source` on each). -> {"changed_by", "why",
    "rows": every row id it confirmed, "facts": the fact rows written},
    the record the harness keeps with the confirmed bundle. Off a TTY
    without --code: kit.human.CodeRequired, nothing written."""
    why = human.why(reason)
    lines = [f"  {k.split(':', 1)[0]} {k.split(':', 1)[1].replace('|', ' / ')}"
             f": {v.replace(chr(9), ' | ')}"
             for k, v in sorted(p["rows"].items())]
    lines += [f"  value {line}" for line in p["facts"]["lines"]]
    prompt = ("\n".join(lines) + f"\n  type '{CONFIRM_WORD}' to confirm "
              f"these {len(p['rows'])} map row(s) and "
              f"{len(p['values'])} value(s) of bundle "
              f"{p['staged'].version}: ")
    channel = human.confirm(f"`{' '.join(verb)}`", prompt, CONFIRM_WORD,
                            subj=subject(verb, p), code=code)
    why += human.relay_audit(channel, relay_user, relay_at)
    written = facts.apply_file(spec, con, p["facts"], channel=channel,
                               reason=why, source=source) \
        if p["facts"]["rows"] else []
    return {"changed_by": human.changed_by(channel), "why": why,
            "rows": sorted(p["rows"]) + [f"value:{v['key']}|{v['market']}"
                                         for v in p["values"]],
            "facts": written}
