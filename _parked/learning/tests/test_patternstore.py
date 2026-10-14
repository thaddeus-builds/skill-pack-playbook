#!/usr/bin/env python3
"""kit.patternstore: a per-client pattern store, on a SYNTHETIC harness (a coffee shop's short videos).

  [1] the shape and its vocabularies: sound, and each kind of fault found (a vocabulary of the wrong kind or empty,
      an extra that shadows a row key)
  [2] the row: group() pools items into rows that validate, deterministic, the id recomputes, a presence source has
      no outcome, family ids are hashed
  [3] validate() refuses free text, a trailing newline, unknown or missing keys, wrong types, bad sums, an outcome on a
      presence row, a wrong label rule, a bad mapping or sequence, a null required field, a wrong id; it never raises,
      and a problem never quotes the value
  [4] two coders: agreement from the counts, null-null not compared, one-sided against, the floor from the counts
      (6996 of 10000 is under 0.70), the agreed values only
  [5] the Beta distribution: known CDFs and quantiles, the edges
  [6] the shrinkage: mu anchored off the edges (an all-win or all-lose field keeps an interval), kappa by the method
      of moments (checked by hand), clipped to [lo, hi], no spread = hi, a rate with its counts and interval,
      competition ranks (the prior ranks nothing), fewer than two labelled cells = counts only with the reason, bad
      cells refused
  [7] the store in kit.db: append-only (triggers refuse UPDATE and DELETE), an export twice adds nothing, a changed
      export supersedes (every live record of an id), a source not read keeps its rows, a retraction by hand stays out
      until lifted and out of the all-scopes union, a duplicate id inserted once, a row whose id does not recompute
      refused
"""

import contextlib
import io
import json
import math
import sqlite3
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import db  # noqa: E402
from kit import patternstore as P  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

OWN, OURS, COMP = "own_past", "ours_tested", "competitor_presence"
SHAPE = P.Shape(
    schema="acme.pattern_evidence/1",
    context=("category", "channel", "price_band"),
    icp=("persona", "objection"),
    play=("hook", "length", "steps", "traits"),
    sources=(P.Source(OWN, ("rank_v1",), extra=("spend_share",)),
             P.Source(OURS, ("rank_v1", "unlabelled"), unlabelled=("unlabelled",)),
             P.Source(COMP, ("presence",), outcomes=False)),
    required=("context.category", "context.channel"))
VOCAB = {
    "category": ("coffee_beans", "tea"), "channel": ("feed_video", "search"), "price_band": ("p_lo", "p_hi"),
    "persona": ("commuter", "home_brewer", "gift_buyer"), "objection": ("price", "taste_risk", "other"),
    "hook": ("question", "demo", "testimonial"), "length": ("s0_15", "s15_30", "s30_60"),
    "steps": P.Seq(("problem", "demo", "offer", "cta"), max=4),
    "traits": {"tone": ("calm", "upbeat"), "voice": ("human", "synthetic")},
    "spend_share": ("share_lo", "share_hi"),
}


def item(source, family, outcome=None, label_rule="rank_v1", persona=None, hook="demo", steps=None, traits=None,
         period="2026-01/2026-03"):
    return {"source": source, "period": period, "label_rule": label_rule,
            "context": {"category": "coffee_beans", "channel": "feed_video", "price_band": None},
            "icp": {"persona": persona, "objection": None},
            "play": {"hook": hook, "length": "s15_30", "steps": steps, "traits": traits or {}},
            "family": family, "outcome": outcome}


def items():
    return [item(OWN, "fam-a", "win", persona="commuter"), item(OWN, "fam-a", "lose", persona="commuter"),
            item(OWN, "fam-b", "win", persona="commuter"), item(OWN, "fam-c", "thin", hook="question"),
            item(OURS, "formula-1", "thin", label_rule="unlabelled", steps=["problem", "demo", "cta"]),
            item(COMP, "a competitor's phrase", None, label_rule="presence", traits={"tone": "upbeat"}),
            item(COMP, "another phrase", None, label_rule="presence", traits={"tone": "upbeat"})]


def rows():
    out = []
    for r in P.group(items(), SHAPE):
        if r["source"] == OWN:
            r = P.with_id({**r, "spend_share": "share_hi"})
        out.append(r)
    return out


def own_row():
    return next(r for r in rows() if r["source"] == OWN and r["n"] == 3)


def problems_of(row, **change):
    """validate() of `row` changed by `change` (a dotted key reaches into a group), the id recomputed unless given."""
    r = json.loads(json.dumps(row))
    for k, v in change.items():
        if "__" in k:
            g, f = k.split("__")
            r[g][f] = v
        elif v is KeyError:
            r.pop(k, None)
        else:
            r[k] = v
    if "id" not in change:
        try:
            r["id"] = P.row_id(r)
        except (TypeError, ValueError):
            pass
    return P.validate(r, SHAPE, VOCAB)


def has(problems, words):
    return any(words in p for p in problems)


def main() -> int:
    print("[1] the shape and its vocabularies")
    check("the synthetic shape is sound", P.shape_problems(SHAPE, VOCAB) == [], P.shape_problems(SHAPE, VOCAB))
    bad_shape = P.Shape(schema="no version", context=("category", "hook"), icp=("persona",), play=("hook",),
                        sources=(P.Source(OWN, ("rank_v1",)), P.Source(OWN, ()), P.Source("x y", ("a",))),
                        required=("context.nowhere",), outcomes=("win",))
    got = P.shape_problems(bad_shape, {**VOCAB, "persona": ("commuter", "a person who buys coffee")})
    for words in ("schema:", "field hook: named twice", "field persona: a vocabulary id is not a token",
                  "source own_past: named twice", "source x y:", "required context.nowhere", "outcomes:"):
        check(f"shape fault found: {words}", has(got, words), got)
    check("a field with no vocabulary is found",
          has(P.shape_problems(SHAPE, {k: v for k, v in VOCAB.items() if k != "hook"}), "field hook: no vocabulary"))
    for label, entry in (("a bare string", "question"), ("an empty list", ()), ("a number", 7),
                         ("a Seq with max 0", P.Seq(("demo",), max=0)), ("an empty Seq", P.Seq(())),
                         ("a mapping to a bare string", {"tone": "calm"}), ("an empty mapping", {})):
        got = P.shape_problems(SHAPE, {**VOCAB, "hook": entry})
        check(f"a vocabulary that is {label} is refused", has(got, "field hook: a vocabulary is"), got)
    for extra in ("n", "win", "play", "families"):
        shadow = P.Shape(schema=SHAPE.schema, context=SHAPE.context, icp=SHAPE.icp, play=SHAPE.play,
                         sources=(P.Source(OWN, ("rank_v1",), extra=(extra,)),))
        got = P.shape_problems(shadow, {**VOCAB, extra: ("x",)})
        check(f"an extra may not shadow a row key: {extra}", has(got, f"extra {extra} shadows a row key"), got)

    print("\n[2] the row")
    rs = rows()
    check("every grouped row validates", all(P.validate(r, SHAPE, VOCAB) == [] for r in rs),
          [P.validate(r, SHAPE, VOCAB) for r in rs])
    check("items with one vector pool into one row (3 own items, 2 families)",
          own_row()["n"] == 3 and len(own_row()["families"]) == 2 and (own_row()["win"], own_row()["lose"]) == (2, 1))
    check("the same items make the same rows, in the shape's source order", [r["id"] for r in P.group(items(), SHAPE)]
          == [r["id"] for r in P.group(list(reversed(items())), SHAPE)]
          and [r["source"] for r in rs] == [OWN, OWN, OURS, COMP])
    comp = next(r for r in rs if r["source"] == COMP)
    check("a presence row carries counts, never an outcome",
          comp["n"] == 2 and not set(SHAPE.outcomes) & set(comp), comp)
    check("family ids are hashed, never stored", all(P.FAMILY.fullmatch(f) for f in comp["families"])
          and "phrase" not in json.dumps(rs) and P.family_token(COMP, "x") != P.family_token(OWN, "x"))
    r = own_row()
    check("the id is the first 16 hex of the sha256 of the canonical row without it",
          r["id"] == P.row_id(r) and P.ROW_ID.fullmatch(r["id"]) and list(P.with_id(r))[0] == "id"
          and P.row_id({**r, "id": "x"}) == r["id"])
    check("canonical JSON: sorted keys, no spaces, UTF-8 as is",
          P.canonical({"b": 1, "a": "é"}) == '{"a":"é","b":1}')
    unl = next(x for x in rs if x["source"] == OURS)
    lone = "\ud800"
    try:
        odd_rows = P.group([item(OWN, "fam" + lone, "win"), {**item(OWN, "fam-z", "win"), "icp": {"persona": lone,
                                                                                              "objection": None}}],
                           SHAPE)
        crashed = None
    except Exception as e:      # noqa: BLE001 - the point is that nothing escapes
        odd_rows, crashed = [], e
    check("a lone surrogate never crashes group() or family_token()",
          crashed is None and len(odd_rows) == 2 and P.FAMILY.fullmatch(P.family_token(OWN, lone)), crashed)
    sur = next((r for r in odd_rows if r["icp"]["persona"] == lone), None)
    sur_p = P.validate(P.with_id({**sur, "spend_share": "share_hi"}), SHAPE, VOCAB) if sur else ["missing"]
    check("validate() refuses the row that carries it, without a crash",
          has(sur_p, "id: not canonical JSON") and has(sur_p, "icp.persona"), sur_p)
    check("an unlabelled row counts every item as the last outcome", unl["thin"] == unl["n"] == 1)

    print("\n[3] validate() refuses")
    secret = "Our customer said the beans taste burnt"
    cases = [
        ("free text in a scalar field", dict(icp__persona=secret), "icp.persona: not in its vocabulary"),
        ("a trailing newline in an id", dict(play__hook="demo\n"), "play.hook: not in its vocabulary"),
        ("a trailing newline in the period", dict(period="2026-01/2026-03\n"), "period:"),
        ("a period that runs backwards", dict(period="2026-03/2026-01"), "period:"),
        ("an unknown key", dict(note=secret), "unknown 1"),
        ("a missing key", dict(spend_share=KeyError), "missing spend_share"),
        ("an unknown key inside a group", dict(context__brand=secret), "context: keys not exactly"),
        ("a bool as a count", dict(n=True), "n: an int"),
        ("n of 0", dict(n=0), "n: an int"),
        ("outcomes that do not sum to n", dict(win=3), "not n"),
        ("a negative outcome", dict(mid=-1), "ints of at least 0"),
        ("a label rule the source does not take", dict(label_rule="presence"), "label_rule:"),
        ("a source the shape does not have", dict(source="partner_ads"), "source:"),
        ("another schema", dict(schema="acme.pattern_evidence/2"), "schema:"),
        ("a null required field", dict(context__channel=None), "context.channel: never null"),
        ("a mapping value outside its list", dict(play__traits={"tone": "angry"}), "play.traits:"),
        ("a mapping key outside its list", dict(play__traits={"mood": "calm"}), "play.traits:"),
        ("a mapping that is null", dict(play__traits=None), "play.traits: an object"),
        ("a step twice in a row", dict(play__steps=["demo", "demo"]), "play.steps:"),
        ("too many steps", dict(play__steps=["problem", "demo", "offer", "cta", "offer"]), "play.steps:"),
        ("an empty step list", dict(play__steps=[]), "play.steps:"),
        ("steps as a string", dict(play__steps="problem>demo"), "play.steps:"),
        ("families unsorted", dict(families=["f_ffffffffff", "f_0000000000"]), "families:"),
        ("more families than items", dict(n=1, win=1, lose=0, families=["f_0000000000", "f_1111111111"]), "families:"),
        ("a family that is not a token", dict(families=["fam-a"]), "families:"),
        ("an extra field that is null", dict(spend_share=None), "spend_share: never null"),
        ("an extra field outside its list", dict(spend_share=secret), "spend_share: not in its vocabulary"),
        ("a wrong id", dict(id="0" * 16), "id: not the first 16 hex"),
        ("an id with a newline", dict(id=P.row_id(own_row()) + "\n"), "id: not the first 16 hex"),
        ("a value JSON cannot hold", dict(icp__objection=float("nan")), "id: not canonical JSON"),
    ]
    every = []
    for label, change, words in cases:
        got = problems_of(own_row(), **change)
        every += got
        check(f"refused: {label}", has(got, words), got)
    check("a problem never quotes the value", not any(secret in p or "burnt" in p for p in every))
    comp_bad = problems_of(comp, win=0, lose=0, mid=0, thin=2)
    check("refused: an outcome on a presence row", has(comp_bad, "unknown 4"), comp_bad)
    unl_bad = problems_of(unl, thin=0, win=1)
    check("refused: an unlabelled row with a label", has(unl_bad, "an unlabelled row counts every item"), unl_bad)
    odd = [P.validate(x, SHAPE, VOCAB) for x in (None, [], "row", {"id": {1, 2}})]
    check("never raises on what is not a row", all(odd), odd)
    weird = [P.validate(own_row(), SHAPE, v) for v in ({}, {**VOCAB, "hook": 7}, {**VOCAB, "traits": 7},
                                                       {**VOCAB, "steps": None}, None)]
    check("never raises on an odd vocabulary, and says so", all(weird), weird)
    nested = P.validate(P.with_id({**own_row(), "play": {**own_row()["play"], "traits": {"tone": "calm"}}}), SHAPE,
                        {**VOCAB, "traits": {"tone": 7}})
    check("a mapping vocabulary with an odd list: a problem, not a crash", has(nested, "play.traits:"), nested)
    check("a set in a row is a problem, not a crash", has(problems_of(own_row(), icp__objection={1}), "icp.objection"))

    print("\n[4] two coders")
    a = {"v1": {"persona": "commuter", "objection": "price"}, "v2": {"persona": "commuter", "objection": None},
         "v3": {"persona": "gift_buyer", "objection": None}, "v4": {"persona": None, "objection": None}}
    b = {"v1": {"persona": "commuter", "objection": "taste_risk"}, "v2": {"persona": "commuter", "objection": None},
         "v3": {"persona": "home_brewer"}}
    st = P.agreement(a, b)
    check("compared: an item either coded; null-null is not compared",
          st["persona"]["compared"] == 3 and st["objection"]["compared"] == 1, st)
    check("agreed: equal values only", st["persona"]["agreed"] == 2 and st["objection"]["agreed"] == 0, st)
    one = P.agreement({"v1": {"hook": "demo"}}, {})
    check("an item one coder left out counts against", one["hook"] == {"compared": 1, "agreed": 0, "agree": 0.0}, one)
    check("the floor reads the counts: 6996 of 10000 is under 0.70, 7000 is not",
          not P.meets_floor({"compared": 10000, "agreed": 6996}) and P.meets_floor({"compared": 10000, "agreed": 7000})
          and P.meets_floor({"compared": 10, "agreed": 7}) and not P.meets_floor({"compared": 3, "agreed": 2}))
    check("none compared is not counted", not P.meets_floor({"compared": 0, "agreed": 0}))
    check("counted(): only the fields at the floor", P.counted(st) == [] and P.counted(st, floor=0.6) == ["persona"])
    check("agreed_values(): both gave the same non-null value",
          P.agreed_values(a, b, ["persona", "objection"]) == {"v1": {"persona": "commuter"},
                                                              "v2": {"persona": "commuter"}})

    print("\n[5] the Beta distribution")
    check("I_x(1, 1) = x", all(abs(P.betainc(1, 1, x) - x) < 1e-12 for x in (0.1, 0.5, 0.9)))
    check("I_x(2, 1) = x^2 and I_x(1, 3) = 1 - (1 - x)^3",
          abs(P.betainc(2, 1, 0.3) - 0.09) < 1e-12 and abs(P.betainc(1, 3, 0.2) - (1 - 0.8 ** 3)) < 1e-12)
    check("I_0.5(a, a) = 0.5", all(abs(P.betainc(a_, a_, 0.5) - 0.5) < 1e-10 for a_ in (0.5, 3, 40)))
    check("quantiles invert the CDF", abs(P.beta_quantile(0.25, 2, 1) - 0.5) < 1e-12
          and abs(P.betainc(4.2, 7.9, P.beta_quantile(0.9, 4.2, 7.9)) - 0.9) < 1e-10)
    check("the edges: a = 0 at 0, b = 0 at 1, x outside [0, 1]",
          P.beta_quantile(0.5, 0, 2) == 0.0 and P.beta_quantile(0.5, 2, 0) == 1.0
          and P.betainc(2, 2, -1) == 0.0 and P.betainc(2, 2, 2) == 1.0)

    print("\n[6] the shrinkage")
    pr = P.prior([(1, 10), (5, 10), (3, 10)])
    mu = (9 + 0.5) / (30 + 1)
    ss = sum((w - 10 * mu) ** 2 / 10 for w in (1, 5, 3))
    rho = (ss / (mu * (1 - mu)) - 2) / (30 - 300 / 30 - 2)
    check("mu is the pooled rate anchored off the edges: (sum w + 0.5) / (N + 1)", abs(pr["mu"] - mu) < 1e-12, pr)
    check("kappa by the method of moments, inside [5, 10]: kept",
          5 < (1 - rho) / rho < 10 and abs(pr["kappa"] - (1 - rho) / rho) < 1e-9 and pr["clipped"] is None, pr)
    lo = P.prior([(0, 10), (10, 10), (1, 10), (9, 10)])
    check("a wide spread clips to lo", lo["kappa"] == 5.0 and lo["clipped"] == "min" and lo["kappa_moments"] < 5, lo)
    flat = P.prior([(5, 10), (5, 10), (5, 10)])
    check("a spread within chance is the most shrinkage, hi", flat["kappa"] == 10.0 and flat["clipped"] == "max")
    check("no labelled item: no prior", P.prior([(0, 0)]) is None and P.prior([]) is None
          and P.prior_reason([(0, 0)]) == "no_labelled")
    check("the owner's range is the default: 5 to 10 tests", P.PRIOR_TESTS == (5.0, 10.0)
          and P.prior([(5, 10), (5, 10)], lo=2, hi=4)["kappa"] == 4)
    for side, cells in (("all-win", [(4, 4), (6, 6), (3, 3)]), ("all-lose", [(0, 4), (0, 6), (0, 3)])):
        sh = P.shrink(cells)
        widths = [c["interval"][1] - c["interval"][0] for c in sh["cells"]]
        check(f"an {side} field keeps a real interval (mu anchored off the edge)",
              0 < sh["prior"]["mu"] < 1 and all(w > 0.01 for w in widths)
              and all(0 < c["shrunk"] < 1 for c in sh["cells"]), sh)
    s = P.shrunk(5, 10, pr)
    want = (5 + pr["kappa"] * mu) / (10 + pr["kappa"])
    check("a shrunk rate sits between the raw rate and mu, with its counts",
          abs(s["shrunk"] - round(want, 4)) < 1e-12 and mu < s["shrunk"] < 0.5 and (s["count"], s["of"], s["raw"])
          == (5, 10, 0.5), s)
    check("its interval holds it", s["interval"][0] < s["shrunk"] < s["interval"][1], s)
    check("ranks: ties share, the next skips (1, 2, 2, 4)", P.ranks([0.5, 0.3, 0.3, 0.1, None]) == [1, 2, 2, 4, None])
    sh = P.shrink([(1, 10), (5, 10), (3, 10), (0, 0)])
    check("shrink(): every labelled cell has a rate and a rank, an empty one none",
          [c and c["rank"] for c in sh["cells"]] == [3, 1, 2, None] and sh["prior"]["cells"] == 3
          and sh["reason"] is None, sh)
    check("the prior ranks nothing", not any("rank" in k for k in pr), pr)
    one = P.shrink([(3, 7), (0, 0)])
    check("one labelled cell: no prior, no shrunk rate, counts only with the reason",
          P.prior([(3, 7), (0, 0)]) is None and P.prior_reason([(3, 7)]) == "one_cell"
          and one == {"prior": None, "reason": P.NO_PRIOR["one_cell"], "cells": [None, None]}, one)
    check("shrink() with no labelled item: no rates, the reason",
          P.shrink([(0, 0), (0, 0)]) == {"prior": None, "reason": P.NO_PRIOR["no_labelled"], "cells": [None, None]})
    for bad in ([(3, 2)], [(-1, 2)], [(True, 2)], [(1.5, 2)]):
        try:
            P.prior(bad)
            ok = False
        except ValueError:
            ok = True
        check(f"a bad cell is refused: {bad}", ok)
    try:
        P.prior([(1, 2)], lo=10, hi=5)
        ok = False
    except ValueError:
        ok = True
    check("lo above hi is refused", ok)

    print("\n[7] the store in kit.db")
    _shop.use()
    spec = db.with_human({}, version=1, extra_human=P.TABLES, append_only=P.APPEND_ONLY,
                         human_added_later=tuple(P.TABLES))
    path = Path(tmp_dir("patterns-")) / "client.db"
    with contextlib.redirect_stderr(io.StringIO()):
        con = db.connect(spec, path)

    def export(made, read, reinstate=(), scope="proj-a", now="2026-10-12T00:00:00Z"):
        live, kept = P.state(con, scope)
        p = P.plan(live, kept, made, read, reinstate)
        with db.keep_human_rows(spec, con):
            P.apply(con, scope, p, now, "agent")
        return p

    first = rows()
    p1 = export(first, {OWN, OURS, COMP})
    check("a first export inserts every row", len(p1["insert"]) == len(first) and not p1["supersede"], p1)
    p2 = export(first, {OWN, OURS, COMP})
    check("the same export again adds nothing", p2["insert"] == [] and p2["already_live"] == len(first), p2)
    changed = [r for r in first if r["source"] != OWN or r["n"] != 3]
    p3 = export(changed, {OWN, OURS})
    check("a row the export no longer makes is superseded", len(p3["supersede"]) == 1 and p3["insert"] == [], p3)
    check("a source not read keeps its rows live",
          p3["unread"] == {} and len(P.live_rows(con, "proj-a")) == len(first) - 1)
    p4 = export([r for r in changed if r["source"] == OWN], {OWN})
    check("a source not read this time: counted, never superseded",
          p4["unread"] == {OURS: 1, COMP: 1} and not p4["supersede"], p4)
    gone = next(r for r in changed if r["source"] == OURS)
    with db.keep_human_rows(spec, con):
        got = P.retract(con, "proj-a", gone["id"], "wrong_numbers", "2026-10-12T01:00:00Z", "agent")
    check("a retraction by hand appends, and the row drops out of the live rows",
          got and got["row_id"] == gone["id"] and gone["id"] not in {r["id"] for r in P.live_rows(con, "proj-a")})
    check("retracting a row that is not live: None", P.retract(con, "proj-a", gone["id"], "wrong_numbers", "t", "a")
          is None)
    try:
        P.retract(con, "proj-a", changed[0]["id"], P.SUPERSEDED, "t", "a")
        ok = False
    except ValueError:
        ok = True
    check("superseded is never a reason given by hand", ok)
    p5 = export(changed, {OWN, OURS, COMP})
    check("a row retracted by hand stays out of the next export", gone["id"] in p5["kept"]
          and gone["id"] not in {r["id"] for r in p5["insert"]}, p5)
    p6 = export(changed, {OWN, OURS, COMP}, reinstate=[gone["id"], "0" * 16])
    check("a reinstatement lifts it, the row comes back as a new record; an unknown id is named",
          [x["row_id"] for x in p6["lift"]] == [gone["id"]] and [r["id"] for r in p6["insert"]] == [gone["id"]]
          and p6["unknown"] == ["0" * 16], p6)
    check("every record stays: retracted ones too", len(P.records(con, "proj-a")) == len(first) + 1)
    export(changed, {OWN, OURS, COMP}, scope="proj-b")
    every = P.live_rows(con)
    check("every scope of the file: a row live under two scopes is one row",
          len(every) == len({r["id"] for r in every}) == len(changed))
    out_b = next(r for r in changed if r["source"] == COMP)
    with db.keep_human_rows(spec, con):
        P.retract(con, "proj-b", out_b["id"], "duplicate", "2026-10-12T02:00:00Z", "agent")
    check("a row retracted by hand in one scope is out of the all-scopes union, though live in another",
          out_b["id"] in {r["id"] for r in P.live_rows(con, "proj-a")}
          and out_b["id"] not in {r["id"] for r in P.live_rows(con)})
    dup = P.plan({}, {}, [changed[0], changed[0], changed[1]], {OWN})
    check("plan(): a row id twice in one export is inserted once, the duplicate counted",
          [r["id"] for r in dup["insert"]] == [changed[0]["id"], changed[1]["id"]] and dup["duplicates"] == 1, dup)
    with db.keep_human_rows(spec, con):     # an earlier build stored one id twice in a scope
        P.apply(con, "proj-c", {"lift": [], "supersede": [], "insert": [changed[0], changed[0]]}, "t0", "agent")
    live_c = P.state(con, "proj-c")[0]
    check("state(): every live record of an id rides along", len(live_c[changed[0]["id"]]["records"]) == 2, live_c)
    p7 = export([], {changed[0]["source"]}, scope="proj-c")
    check("an export supersedes every live record of an id it no longer makes",
          len(p7["supersede"]) == 1 and P.live_rows(con, "proj-c") == []
          and all(r["reason"] == P.SUPERSEDED for r in P.records(con, "proj-c")), P.records(con, "proj-c"))
    with db.keep_human_rows(spec, con):
        P.apply(con, "proj-e", {"lift": [], "supersede": [], "insert": [changed[1], changed[1]]}, "t0", "agent")
        P.retract(con, "proj-e", changed[1]["id"], "wrong_tags", "t1", "agent")
    check("a retraction by hand covers every live record of the id",
          P.live_rows(con, "proj-e") == [] and all(r["reason"] == "wrong_tags" for r in P.records(con, "proj-e")))
    try:
        with db.keep_human_rows(spec, con):
            P.apply(con, "proj-d", {"lift": [], "supersede": [], "insert": [changed[1], {**changed[0], "n": 99}]},
                    "t0", "agent")
        ok = False
    except ValueError:
        ok = True
    check("apply() refuses a row whose id does not recompute, and writes nothing", ok and P.records(con, "proj-d") == [])
    for sql in ("UPDATE pattern_rows SET n = 99", "DELETE FROM pattern_rows",
                "UPDATE pattern_retractions SET reason = 'x'", "DELETE FROM pattern_reinstatements",
                "INSERT OR REPLACE INTO pattern_retractions (record, scope, row_id, reason, retracted_at, retracted_by) "
                "SELECT record, scope, row_id, 'x', retracted_at, retracted_by FROM pattern_retractions LIMIT 1"):
        raw = sqlite3.connect(path)
        try:
            raw.execute(sql)
            raw.commit()
            ok = False
        except sqlite3.DatabaseError:
            ok = True
        finally:
            raw.close()
        check(f"the file's triggers refuse: {sql.split(' (')[0][:48]}", ok)
    con.close()
    bare = sqlite3.connect(":memory:")
    check("a file without the tables reads as empty", P.records(bare) == [] and P.live_rows(bare, "x") == []
          and P.state(bare, "x") == ({}, {}))
    bare.close()
    check("the payload is the row as canonical JSON", all(json.loads(P.canonical(r)) == r for r in every)
          and not any(math.isnan(r["n"]) for r in every))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
