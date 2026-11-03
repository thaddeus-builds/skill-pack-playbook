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
  * messages/1 (the customer-insight card as a file): its x-rules across fields hold on the example and
    fail on each way of breaking them (a dropped row said, an id in `insights` that the matrix lacks, a
    pending scope with a sayable fact ...), and its claims_scope is a record kit.claimscope.confirmed()
    accepts once confirmed_on is left out and calls a draft after an edit;
  * a pack that takes no `exchange` pack does not get the schemas (kit.tools.packs).
"""

import copy
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import claimscope, contracts, raw  # noqa: E402
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


def undeclared(node, schema: dict, root: dict | None = None, where: str = "$") -> list[str]:
    """Every key of the JSON `node` that its schema does not declare. A reader ignores such a key (that is rule 2),
    so the schema's own check never sees it; for an example it means the schema lost a property the example shows."""
    root = root or schema
    if "$ref" in schema:
        schema = root.get("$defs", {}).get(schema["$ref"].rsplit("/", 1)[-1], {})
    out: list[str] = []
    if isinstance(node, dict):
        props = schema.get("properties", {})
        for k, v in node.items():
            if k not in props:
                out.append(f"{where}.{k}")
            else:
                out += undeclared(v, props[k], root, f"{where}.{k}")
    elif isinstance(node, list) and isinstance(schema.get("items"), dict):
        for i, v in enumerate(node):
            out += undeclared(v, schema["items"], root, f"{where}[{i}]")
    return out


def declared_paths(schema: dict, root: dict | None = None, where: str = "$") -> set[str]:
    """Every property path of a schema (arrays as []), to show that an example uses all of them."""
    root = root or schema
    if "$ref" in schema:
        schema = root.get("$defs", {}).get(schema["$ref"].rsplit("/", 1)[-1], {})
    out: set[str] = set()
    for k, sub in schema.get("properties", {}).items():
        out.add(f"{where}.{k}")
        out |= declared_paths(sub, root, f"{where}.{k}")
    if isinstance(schema.get("items"), dict):
        out |= declared_paths(schema["items"], root, f"{where}[]")
    return out


def used_paths(node, where: str = "$") -> set[str]:
    out: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(f"{where}.{k}")
            out |= used_paths(v, f"{where}.{k}")
    elif isinstance(node, list):
        for v in node:
            out |= used_paths(v, f"{where}[]")
    return out


def walk_schema(node: dict, path: str = ""):
    """Every schema node under `node` with its path (`properties` and `$defs` are maps of schemas)."""
    yield path, node
    for key in ("properties", "$defs"):
        for name, sub in (node.get(key) or {}).items():
            yield from walk_schema(sub, f"{path}/{key}/{name}")
    if isinstance(node.get("items"), dict):
        yield from walk_schema(node["items"], f"{path}/items")


def messages_problems(doc: dict) -> list[str]:
    """The rules of messages/1's x-rules that one document can show and no schema keyword says (the schema's own
    check is contracts.problems)."""
    out: list[str] = []
    scope = doc.get("claims_scope") or {}
    pending = scope.get("status") == "pending"
    new_style = "matrix" in doc or "card_version" in doc
    insights = [i.get("insight_id") for i in doc.get("insights") or []]
    if len(set(insights)) != len(insights):
        out.append("an insight_id is listed twice in insights")
    if pending and insights:
        out.append("a pending scope with a row in insights")
    if new_style and "status" not in scope:
        out.append("a document with a matrix or a card_version has no claims_scope.status")
    if scope.get("status") == "confirmed" and new_style:
        for k in ("confirmed_by", "confirmed_at", "content_sha"):
            if k not in scope:
                out.append(f"claims_scope.status is confirmed and {k} is missing")
    if scope.get("status") in (None, "confirmed") and "content_sha" in scope \
            and not claimscope.confirmed({k: v for k, v in scope.items() if k != "confirmed_on"}):
        out.append("claims_scope does not read as confirmed through kit.claimscope.confirmed (without confirmed_on)")
    if scope.get("confirmed_on") and scope.get("confirmed_at") and scope["confirmed_on"] != scope["confirmed_at"][:10]:
        out.append("confirmed_on is not the day part of confirmed_at")
    if str(scope.get("confirmed_by", "")).endswith("@auto") and scope.get("status") == "confirmed":
        out.append("a scope confirmed by an automatic mode is written as confirmed")
    m = doc.get("matrix")
    if m is None:
        return out
    segs, jobs, moments = m.get("segments") or [], m.get("jobs") or [], m.get("moments") or []
    for label, items in (("segments", segs), ("jobs", jobs), ("moments", moments)):
        ids = [x.get("id") for x in items]
        if len(set(ids)) != len(ids):
            out.append(f"an id is listed twice in matrix.{label}")
    rows = m.get("rows") or []
    ids = [r.get("insight_id") for r in rows]
    if len(set(ids)) != len(ids):
        out.append("an insight_id is listed twice in matrix.rows")
    for i in insights:
        if i not in ids:
            out.append(f"{i} is in insights and not in matrix.rows")
    seg = {s["id"]: s for s in segs}
    refs = {"segment_id": seg, "job_id": {j["id"]: j for j in jobs}, "moment_id": {x["id"]: x for x in moments}}
    said = {i["insight_id"]: i for i in doc.get("insights") or []}
    sayable = set()
    for r in rows:
        ident, state = r.get("insight_id"), r.get("state")
        for key, known in refs.items():
            if r.get(key) is not None and r[key] not in known:
                out.append(f"{ident}: {key} {r[key]} is not in the matrix")
        if r.get("may_say"):
            sayable.add(ident)
            if state != "live":
                out.append(f"{ident}: may_say on a row that is {state}")
            if r.get("segment_id") is None:
                out.append(f"{ident}: may_say on a row that names no segment")
            elif (seg.get(r["segment_id"]) or {}).get("hold"):
                out.append(f"{ident}: may_say on a row of a held segment")
            if not r.get("say_count"):
                out.append(f"{ident}: may_say on a row with no fact (say_count 0)")
            if pending:
                out.append(f"{ident}: may_say under a pending scope")
        if state == "dropped" and ident in said:
            out.append(f"{ident}: a dropped row is in insights")
        if ident in said:
            if r.get("pain") is not None and r["pain"] != said[ident]["pain"]:
                out.append(f"{ident}: pain differs between insights and the matrix")
            name = (seg.get(r.get("segment_id")) or {}).get("name")
            if name is not None and name != said[ident]["segment"]:
                out.append(f"{ident}: the segment's name differs between insights and the matrix")
    if sayable != set(insights):
        out.append(f"insights and the rows with may_say differ: {sorted(sayable ^ set(insights))}")
    by_id = {r.get("insight_id"): r for r in rows}
    for o in m.get("objections") or []:
        stray = [x for x in o.get("rows") or [] if x not in ids]
        if stray:
            out.append(f"objection {o['value']} names rows the matrix lacks: {stray}")
        if o["value"] not in ids:
            out.append(f"objection value {o['value']} is not a row id")
        elif by_id[o["value"]].get("objection") not in (None, o.get("text")):
            out.append(f"objection {o['value']}: the text is not the wording of its row")
        if o.get("rows") and o["value"] not in o["rows"]:
            out.append(f"objection {o['value']} is not among its own rows")
    return out


def messages_continuity(older: dict, newer: dict) -> list[str]:
    """What two documents of one product and market must keep (x-rules: an insight_id is never reused or renumbered,
    a dropped row stays listed): every id the older one listed is in the newer one's matrix."""
    listed = lambda d: {r["insight_id"] for r in (d.get("matrix") or {}).get("rows", [])} | \
        {i["insight_id"] for i in d.get("insights") or []}                                   # noqa: E731
    new_ids = {r["insight_id"] for r in (newer.get("matrix") or {}).get("rows", [])}
    out = [f"{i} was listed and is gone" for i in sorted(listed(older) - new_ids)]
    old_rows = {r["insight_id"]: r for r in (older.get("matrix") or {}).get("rows", [])}
    for r in (newer.get("matrix") or {}).get("rows", []):
        was = old_rows.get(r["insight_id"])
        if was and was.get("state") == "dropped" and r.get("state") == "live" and was.get("pain") != r.get("pain"):
            out.append(f"{r['insight_id']} was dropped and is now another live row")
    return out


def main() -> int:
    _shop.use()
    data = _shop.data_dir()
    out = Path(tmp_dir("contracts-"))

    print("[1] the schemas and the examples")
    here = {p.name: p.read_bytes() for p in contracts.SCHEMAS.glob("*.schema.json")}
    there = {p.name: p.read_bytes() for p in (PLAYBOOK / "contracts").glob("*.schema.json")}
    check("kit/contracts.d holds the playbook's contracts/ schemas, byte for byte",
          here == there and len(here) == 17,
          sorted(set(here) ^ set(there)) or [n for n in here if here[n] != there.get(n)])
    examples = sorted(EXAMPLES.iterdir())
    check("an example for each of the seventeen", len(examples) == 17, examples)
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

    print("\n[1b] messages/1: the card as a file, and the join keys back to a row")
    kind, version, text = example("messages-1.example.json")
    msg_doc = json.loads(text.split("\n", 1)[1])
    msg_schema = contracts.schema(kind, version)
    check("the example breaks none of the rules across fields", messages_problems(msg_doc) == [], messages_problems(msg_doc))
    check("the example lists a dropped, a held and a nothing-to-say row beside the one that may be said",
          {r["insight_id"]: (r["state"], r["may_say"]) for r in msg_doc["matrix"]["rows"]}
          == {"ins-001": ("live", True), "ins-002": ("dropped", False), "ins-003": ("live", False), "ins-004": ("live", False)}
          and [i["insight_id"] for i in msg_doc["insights"]] == ["ins-001"])
    scope = {k: v for k, v in msg_doc["claims_scope"].items() if k != "confirmed_on"}
    check("its claims_scope, without confirmed_on, is a record the kit's own gate calls confirmed",
          claimscope.confirmed(scope))
    check("... with confirmed_on in it the hash is another (the day is not confirmed content)",
          not claimscope.confirmed(msg_doc["claims_scope"]))
    check("... an edit of the wording, of lexicon_sha, a status of pending or no hash reads as a draft",
          not claimscope.confirmed(dict(scope, scope_text="Dimmable and waterproof."))
          and not claimscope.confirmed(dict(scope, lexicon_sha="0" * 64))
          and not claimscope.confirmed(dict(scope, status="pending"))
          and not claimscope.confirmed({k: v for k, v in scope.items() if k != "content_sha"}))
    check("a scope as the adcut pack wrote it before (none of the confirmation fields) reads as a draft through the kit",
          not claimscope.confirmed({k: v for k, v in scope.items()
                                    if k not in ("status", "confirmed_by", "confirmed_at", "content_sha", "lexicon_sha")}))
    check("every key the example uses is declared by the schema, and the example uses every key the schema declares",
          undeclared(msg_doc, msg_schema) == [] and declared_paths(msg_schema) - used_paths(msg_doc) == set(),
          (undeclared(msg_doc, msg_schema), sorted(declared_paths(msg_schema) - used_paths(msg_doc))))

    def broken(mutate, label, needle):
        d = copy.deepcopy(msg_doc)
        mutate(d)
        found = messages_problems(d)
        check(f"{label}: found", any(needle in f for f in found), found)

    def row(d, ident):
        return next(r for r in d["matrix"]["rows"] if r["insight_id"] == ident)

    def segment(d, ident):
        return next(s for s in d["matrix"]["segments"] if s["id"] == ident)
    broken(lambda d: d["matrix"]["rows"].pop(0), "an id of insights that the matrix lacks", "is in insights and not in matrix.rows")
    broken(lambda d: row(d, "ins-002").update(may_say=True), "a dropped row that may be said", "may_say on a row that is dropped")
    broken(lambda d: d["insights"].append(dict(d["insights"][0], insight_id="ins-002")), "a dropped row in insights", "a dropped row is in insights")
    broken(lambda d: row(d, "ins-003").update(may_say=True), "a row of a held segment that may be said", "held segment")
    broken(lambda d: (row(d, "ins-003").update(may_say=True), row(d, "ins-003").pop("segment_id")), "a row with no segment that may be said", "names no segment")
    broken(lambda d: row(d, "ins-004").update(may_say=True), "a row with no fact that may be said", "no fact (say_count 0)")
    broken(lambda d: d["matrix"]["rows"].append(dict(row(d, "ins-004"))), "an id listed twice in the matrix", "listed twice in matrix.rows")
    broken(lambda d: d["matrix"]["segments"].append(dict(segment(d, "S1"))), "a segment id listed twice", "listed twice in matrix.segments")
    broken(lambda d: row(d, "ins-004").update(segment_id="S9"), "a row naming a segment the matrix lacks", "segment_id S9")
    broken(lambda d: row(d, "ins-001").update(may_say=False), "a row in insights whose matrix row says it may not be said", "differ")
    broken(lambda d: row(d, "ins-001").update(pain="another pain"), "a pain that differs between insights and the matrix", "pain differs")
    broken(lambda d: segment(d, "S1").update(name="another name"), "a segment name that differs between insights and the matrix", "segment's name differs")
    broken(lambda d: d["matrix"]["objections"][0]["rows"].append("ins-099"), "an objection naming a row the matrix lacks", "ins-099")
    broken(lambda d: d["matrix"]["objections"][0].update(text="another wording"), "an objection whose text is not its row's", "not the wording of its row")
    broken(lambda d: d["claims_scope"].update(scope_text="Dimmable and waterproof."), "a scope edited after its confirmation", "does not read as confirmed")
    broken(lambda d: d["claims_scope"].update(lexicon_sha="1" * 64), "a lexicon hash edited after the confirmation", "does not read as confirmed")
    broken(lambda d: d["claims_scope"].update(confirmed_on="2026-10-21"), "a confirmed_on that is not the day of confirmed_at", "day part")
    broken(lambda d: d["claims_scope"].update(status="pending"), "a pending scope with a row in insights", "a pending scope with a row in insights")
    broken(lambda d: (d["claims_scope"].update(status="pending"), d.update(insights=[])), "a pending scope with a row that may be said", "may_say under a pending scope")
    broken(lambda d: d["claims_scope"].pop("status"), "a new-style document without a scope status", "has no claims_scope.status")
    broken(lambda d: d["claims_scope"].pop("confirmed_by"), "a confirmed scope without who confirmed it", "confirmed_by is missing")
    broken(lambda d: d["claims_scope"].update(confirmed_by="bot@auto"), "a scope confirmed by an automatic mode, written as confirmed", "automatic mode")
    check("an insights-only document, without a matrix or card_version, may leave the scope status out (it reads as confirmed)",
          messages_problems({k: v for k, v in msg_doc.items() if k not in ("matrix", "card_version")}
                            | {"claims_scope": {k: v for k, v in msg_doc["claims_scope"].items()
                                                if k not in ("status", "confirmed_by", "confirmed_at", "content_sha", "lexicon_sha")}}) == [])
    draft = copy.deepcopy(msg_doc)
    draft["claims_scope"] = {k: v for k, v in draft["claims_scope"].items()
                             if k not in ("confirmed_by", "confirmed_at", "content_sha", "confirmed_on")} | {"status": "pending"}
    draft["insights"] = []
    for r in draft["matrix"]["rows"]:
        r["may_say"] = False
    check("a pending scope with no sayable row is a valid document, and breaks no rule",
          contracts.problems("messages", 1, draft) == [] and messages_problems(draft) == [], messages_problems(draft))
    later = copy.deepcopy(msg_doc)
    later["matrix"]["rows"].append(dict(row(later, "ins-004"), insight_id="ins-005"))
    check("a later document keeps every id the earlier one listed, and may add more",
          messages_continuity(msg_doc, later) == [] and messages_continuity(msg_doc, msg_doc) == [])
    gone = copy.deepcopy(later)
    gone["matrix"]["rows"] = [r for r in gone["matrix"]["rows"] if r["insight_id"] != "ins-002"]
    check("... a dropped row that vanishes from the next document is found",
          any("ins-002" in f for f in messages_continuity(msg_doc, gone)), messages_continuity(msg_doc, gone))
    reused = copy.deepcopy(later)
    row(reused, "ins-002").update(state="live", pain="a pain of another row")
    check("... a dropped id given to another live row is found",
          any("ins-002" in f for f in messages_continuity(msg_doc, reused)), messages_continuity(msg_doc, reused))

    def refused_by_schema(mutate, label):
        d = copy.deepcopy(msg_doc)
        mutate(d)
        check(f"{label}: refused by the schema", contracts.problems("messages", 1, d) != [])
    refused_by_schema(lambda d: d["claims_scope"].update(status="draft"), "a scope status outside confirmed and pending")
    refused_by_schema(lambda d: d["claims_scope"].update(content_sha="abc"), "a hash that is not 64 hex digits")
    refused_by_schema(lambda d: d["claims_scope"].update(lexicon_sha="A" * 64), "a lexicon hash in capitals")
    refused_by_schema(lambda d: d["claims_scope"].update(confirmed_at="2026-10-20T10:30:00"), "a confirmation time without its zone")
    refused_by_schema(lambda d: d["claims_scope"].update(confirmed_by=""), "an empty confirmed_by")
    refused_by_schema(lambda d: d.update(card_version="7"), "a card_version given as text")
    refused_by_schema(lambda d: d.update(card_version=-1), "a card_version below 0")
    refused_by_schema(lambda d: d["matrix"].pop("rows"), "a matrix without rows")
    refused_by_schema(lambda d: row(d, "ins-001").update(state="held"), "a row state outside live and dropped")
    refused_by_schema(lambda d: row(d, "ins-001").pop("state"), "a matrix row without its state")
    refused_by_schema(lambda d: row(d, "ins-001").update(may_say="yes"), "may_say given as text")
    refused_by_schema(lambda d: row(d, "ins-001").update(say_count=-1), "a say_count below 0")
    refused_by_schema(lambda d: row(d, "ins-001").update(say_count=1.5), "a say_count that is not whole")
    refused_by_schema(lambda d: row(d, "ins-001").update(ours_codes=[""]), "an empty creative code")
    refused_by_schema(lambda d: row(d, "ins-003").update(flags=[{"rule": "IB06"}]), "a flag without its code")
    refused_by_schema(lambda d: d["matrix"]["segments"].append("S3"), "a segment that is not an object")
    refused_by_schema(lambda d: d["matrix"]["jobs"].append("J3"), "a job that is not an object")
    refused_by_schema(lambda d: d["matrix"]["moments"].append("M3"), "a moment that is not an object")
    refused_by_schema(lambda d: d["matrix"]["rows"].append("ins-009"), "a matrix row that is not an object")
    refused_by_schema(lambda d: row(d, "ins-001").update(ours_codes=[7]), "a creative code that is not text")
    refused_by_schema(lambda d: row(d, "ins-003").update(flags=["insight_out_of_bounds"]), "a flag that is not an object")
    refused_by_schema(lambda d: d["matrix"]["objections"].append("none"), "an objection that is not an object")
    refused_by_schema(lambda d: d["matrix"]["objections"][0].update(rows=[7]), "an objection row id that is not text")
    refused_by_schema(lambda d: d["matrix"]["objections"][0].update(rows=[""]), "an empty objection row id")
    refused_by_schema(lambda d: row(d, "ins-001").pop("insight_id"), "a matrix row without its id")
    refused_by_schema(lambda d: d["matrix"]["segments"][0].pop("id"), "a segment without its id")
    refused_by_schema(lambda d: d["matrix"]["moments"][0].pop("id"), "a moment without its id")
    refused_by_schema(lambda d: d["matrix"]["objections"][0].pop("value"), "an objection without its value")
    refused_by_schema(lambda d: d["matrix"]["segments"][0].pop("name"), "a segment without its name")
    refused_by_schema(lambda d: d["matrix"]["jobs"][0].pop("id"), "a job without its id")
    refused_by_schema(lambda d: d["matrix"]["objections"][0].pop("text"), "an objection without its text")
    refused_by_schema(lambda d: d["matrix"]["objections"][0].update(rows="ins-001"), "an objection's rows given as a string")
    refused_by_schema(lambda d: d["insights"][0].update(status=""), "an empty row status")
    refused_by_schema(lambda d: d["insights"][0].update(source=""), "an empty row source")
    loose = [path for path, node in walk_schema(msg_schema)
             if path.rsplit("/", 2)[-2:-1] == ["properties"]
             and (msg_schema["$defs"][node["$ref"].rsplit("/", 1)[1]] if "$ref" in node else node).get("type") == "string"
             and not {"minLength", "pattern"} & set(msg_schema["$defs"][node["$ref"].rsplit("/", 1)[1]] if "$ref" in node else node)]
    check("no string of messages/1 may be empty (an absent key means unknown, never an empty string)", loose == [], loose)
    join_keys = {"ads.creatives": contracts.schema("ads.creatives", 1)["properties"]["insight_id"],
                 "copy.proposals": contracts.schema("copy.proposals", 1)["properties"]["proposals"]["items"]["properties"]["insight_id"]}
    for k, node in join_keys.items():
        check(f"{k}: insight_id is a string of at least one character", node.get("type") == "string" and node.get("minLength") == 1, node)
    old_style = {k: v for k, v in msg_doc.items() if k not in ("card_version", "matrix")}
    old_style["claims_scope"] = {k: v for k, v in old_style["claims_scope"].items()
                                 if k not in ("status", "confirmed_by", "confirmed_at", "content_sha", "lexicon_sha")}
    old_style["insights"] = [{k: v for k, v in msg_doc["insights"][0].items() if k not in ("status", "source")}]
    check("a document as written before 2026-11-03 (none of the new keys) still passes, and a key the schema does not know is ignored",
          contracts.problems("messages", 1, old_style) == [] and messages_problems(old_style) == []
          and contracts.problems("messages", 1, dict(msg_doc, future_key={"a": 1})) == [])

    cre_kind, cre_version, cre_text = example("ads.creatives-1.example.tsv")
    cre = contracts.parse(cre_text.encode(), cre_kind, cre_version)
    cre_schema = contracts.schema(cre_kind, cre_version)
    check("a creative names the row it serves in a last, optional column; a blank cell is unknown",
          cre.columns[-1] == "insight_id" and [r["insight_id"] for r in cre.body] == ["ins-001", "ins-001"]
          and "insight_id" not in cre_schema["x-columns"] and set(cre.columns) == set(cre_schema["properties"]))
    cre_cols = cre_schema["x-columns"]
    six = [{k: v for k, v in r.items() if k in cre_cols} for r in cre.body]

    def header(rows, name):
        return contracts.write(cre_kind, cre_version, rows, out / name).read_text("utf-8").splitlines()[1].split("\t")
    check("... written only when a row has one, and after material_ids when that is there too",
          header(six, "c6.tsv") == cre_cols
          and header([dict(six[0], insight_id="ins-001"), six[1]], "c7.tsv") == cre_cols + ["insight_id"]
          and header([dict(six[0], material_ids="7", insight_id="ins-001"), six[1]], "c8.tsv")
          == cre_cols + ["material_ids", "insight_id"])
    lines = cre_text.splitlines()
    lines[2] = lines[2].rsplit("\t", 1)[0] + "\t"
    check("... a blank insight_id cell reads as unknown (None), not as an id",
          contracts.parse(("\n".join(lines) + "\n").encode(), cre_kind, cre_version).body[0]["insight_id"] is None)
    prop_kind, prop_version, prop_text = example("copy.proposals-1.example.json")
    props = json.loads(prop_text.split("\n", 1)[1])
    prop_schema = contracts.schema(prop_kind, prop_version)
    check("a copy proposal names the row it was written for, and one that does not is as valid as before",
          props["proposals"][0]["insight_id"] == "ins-001" and "insight_id" not in props["proposals"][1]
          and contracts.problems(prop_kind, prop_version, props) == [])
    check("every key the copy-proposal example uses is declared by its schema",
          undeclared(props, prop_schema) == [], undeclared(props, prop_schema))
    props["proposals"][0]["insight_id"] = ""
    check("... a blank insight_id is refused (absent means unknown)", contracts.problems(prop_kind, prop_version, props) != [])
    props["proposals"][0]["insight_id"] = 1
    check("... and so is one that is a number", contracts.problems(prop_kind, prop_version, props) != [])

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
