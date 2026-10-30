"""A per-client pattern store: what one client's past outputs taught, kept as abstract rows in that client's own
database, and read back as shrunk rates with their counts. Design and rules for any skill pack: docs/pattern-store.md.

A pattern is context x ICP archetype x playbook: three groups whose fields the skill pack names (`Shape`), every value an
id of a closed vocabulary the skill pack passes (or null: not observed, or not counted). An evidence row holds the counts of
the items (ads, posts, emails) that had exactly one pattern vector: `n`, the independent families they come from, and,
for a source with outcomes, how they ranked. What the kit guards:

  * a row is closed: `validate()` never raises and returns the problems, naming the field and never the value. It
    refuses free text (any string outside its vocabulary or token pattern, a trailing newline included), an unknown or
    missing key, a value of the wrong type (a bool is no count), a bad outcome sum, an outcome on a presence-only
    source, and an id that does not recompute (`row_id()`: the first 16 hex of the sha256 of the row without its id,
    as canonical JSON);
  * sources are never pooled: each row names one source of the skill pack's `Shape` (any number of them), and a source
    without outcomes (competitors, say) carries counts only, never good or bad;
  * a coded field counts only when two independent coders agree at the floor (`agreement()`, `meets_floor()`: 0.70 by
    default, read from the counts, never from a rounded rate);
  * a rate never travels without its counts: `shrink()` is empirical Bayes (beta-binomial) toward the cells' own mean
    (anchored off 0 and 1), the prior worth `lo` to `hi` tests (method-of-moments kappa, clipped), with an interval
    (Beta quantiles) and competition ranks (1, 2, 2, 4), never a single winner; a field with fewer than two labelled
    cells gets counts only, with the reason;
  * the store only grows: `TABLES` (kit.db's format; the skill pack passes them as extra human tables with `APPEND_ONLY`,
    so kit.db's triggers refuse an UPDATE, a DELETE and an INSERT over a key), a row retracted by appending a reason,
    an export superseding the live rows it no longer makes (`plan()`, `apply()`), a retraction by hand kept until a
    reinstatement lifts it.

The vocabularies, the sources, which fields are judgement (mapped by the agent) and how a skill pack reads its outputs are
the skill pack's; this module only validates, groups, stores and shrinks. Stdlib only; nothing here reads the clock (the
caller passes `now`). Test: kit/tests/test_patternstore.py.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

GROUPS = ("context", "icp", "play")
OUTCOMES = ("win", "mid", "lose", "thin")      # the last one: ranked items too thin to read, and every unlabelled item
FLOOR = 0.70                                   # two coders' agreement under which a coded field is null for every item
PRIOR_TESTS = (5.0, 10.0)                      # what the prior is worth, in tests (lo, hi)
INTERVAL = (0.10, 0.90)                        # the shrunk rate's interval: these quantiles of its Beta
SEQ_MAX = 16
SUPERSEDED = "superseded"                      # the export's own retraction reason, never one given by hand
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
SCHEMA = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}/[0-9]{1,4}")
ROW_ID = re.compile(r"[0-9a-f]{16}")
FAMILY = re.compile(r"f_[0-9a-f]{10}")
PERIOD = re.compile(r"(\d{4}-(?:0[1-9]|1[0-2]))/(\d{4}-(?:0[1-9]|1[0-2]))")
BASE_KEYS = ("schema", "id", "source", "period", "label_rule", *GROUPS, "n", "families")


# ---------------------------------------------------------------- the shape a skill pack declares

@dataclass(frozen=True)
class Seq:
    """A sequence field's vocabulary: null, or 1 to `max` ids of `ids`, no id twice in a row (beats, steps)."""
    ids: tuple[str, ...]
    max: int = SEQ_MAX


@dataclass(frozen=True)
class Source:
    """One source of evidence. `label_rules`: the rules a row of it may carry; `outcomes`: False for presence only
    (counts, never good or bad); `unlabelled`: its rules under which every item is the last outcome; `extra`: scalar
    fields only its rows carry, each non-null and in its vocabulary."""
    name: str
    label_rules: tuple[str, ...]
    outcomes: bool = True
    unlabelled: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()


@dataclass(frozen=True)
class Shape:
    """The skill pack's row: its schema id, the fields of each group, its sources, the fields never null
    ("context.category"), and the outcome labels (the last one is the thin/unlabelled one)."""
    schema: str
    context: tuple[str, ...]
    icp: tuple[str, ...]
    play: tuple[str, ...]
    sources: tuple[Source, ...]
    required: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = OUTCOMES

    def fields(self, group: str) -> tuple[str, ...]:
        return getattr(self, group)

    def source(self, name: object) -> Source | None:
        return next((s for s in self.sources if s.name == name), None)

    def keys(self, src: Source | None) -> set[str]:
        """The exact key set of a row of `src`."""
        return set(BASE_KEYS) | (set(self.outcomes) if src is None or src.outcomes else set()) \
            | set(src.extra if src else ())


def _token(x: object) -> bool:
    return isinstance(x, str) and TOKEN.fullmatch(x) is not None


def _ids(v: object) -> list:
    """The ids a vocabulary entry holds (a collection, a {key: collection} or a Seq), flat."""
    if isinstance(v, Seq):
        return list(v.ids)
    if isinstance(v, Mapping):
        return list(v) + [i for vals in v.values() for i in (vals if isinstance(vals, (list, tuple, set, frozenset))
                                                             else [vals])]
    return list(v) if isinstance(v, (list, tuple, set, frozenset)) else [v]


_COLL = (list, tuple, set, frozenset)


def _vocab_kind(v: object) -> bool:
    """A vocabulary entry of a kind validate() reads, with at least one id: a collection, {key: collection}, or Seq."""
    if isinstance(v, Seq):
        return isinstance(v.ids, _COLL) and len(v.ids) > 0 and _count(v.max) and v.max >= 1
    if isinstance(v, Mapping):
        return len(v) > 0 and all(isinstance(x, _COLL) and len(x) > 0 for x in v.values())
    return isinstance(v, _COLL) and len(v) > 0


def shape_problems(shape: Shape, vocab: Mapping[str, Any]) -> list[str]:
    """What is wrong with a skill pack's shape and vocabularies (empty: sound). Run it once, in the skill pack's own test: a
    field named twice, a field or extra with no vocabulary, an id that is not a token (a sentence is no id), a source
    named twice or with no label rule, a vocabulary that is not a non-empty list, set, {key: list} or Seq (a bare
    string is not one), an extra that shadows a row key, a `required` path that is no field, fewer than two
    outcomes."""
    p: list[str] = []
    if not (isinstance(shape.schema, str) and SCHEMA.fullmatch(shape.schema)):
        p.append("schema: a token and a version, like acme.pattern_evidence/1")
    names = [f for g in GROUPS for f in shape.fields(g)] + [e for s in shape.sources for e in s.extra]
    p += [f"field {f}: named twice (groups and extras share one vocabulary)" for f in sorted({x for x in names
                                                                                               if names.count(x) > 1})]
    for f in dict.fromkeys(names):
        if not _token(f):
            p.append("a field name is not a token")
        elif f not in vocab:
            p.append(f"field {f}: no vocabulary")
        elif not _vocab_kind(vocab[f]):
            p.append(f"field {f}: a vocabulary is a list, tuple, set, {{key: list}} or Seq of at least one id "
                     "(never a bare string), a Seq's max at least 1")
        elif not all(_token(i) for i in _ids(vocab[f])):
            p.append(f"field {f}: a vocabulary id is not a token")
    shadow = set(BASE_KEYS) | set(shape.outcomes)
    p += [f"source {s.name}: extra {e} shadows a row key" for s in shape.sources for e in s.extra if e in shadow]
    srcs = [s.name for s in shape.sources]
    if not srcs:
        p.append("sources: none")
    p += [f"source {s}: named twice" for s in sorted({x for x in srcs if srcs.count(x) > 1})]
    for s in shape.sources:
        if not _token(s.name) or not s.label_rules or not all(_token(r) for r in s.label_rules) \
                or not set(s.unlabelled) <= set(s.label_rules):
            p.append(f"source {s.name}: a token name, label rules as tokens, unlabelled rules among them")
    paths = {f"{g}.{f}" for g in GROUPS for f in shape.fields(g)}
    p += [f"required {r}: not a field path" for r in shape.required if r not in paths]
    if len(shape.outcomes) < 2 or not all(_token(o) for o in shape.outcomes) or set(shape.outcomes) & set(BASE_KEYS):
        p.append("outcomes: two or more tokens, none a row key")
    return p


# ---------------------------------------------------------------- the row

def canonical(obj: Any) -> str:
    """Sorted keys, no spaces, UTF-8 as is, no NaN: the bytes a row id is taken over."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def row_id(row: Mapping) -> str:
    """The first 16 hex of the sha256 of the row without its id, as canonical JSON (raises on a value JSON cannot
    hold; `validate()` turns that into a problem). A lone surrogate is hashed as it is (surrogatepass), never a crash:
    `validate()` refuses the text that is not UTF-8."""
    body = canonical({k: v for k, v in row.items() if k != "id"})
    return hashlib.sha256(body.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def with_id(row: Mapping) -> dict:
    """The row with its id, the id first."""
    return {"id": row_id(row), **{k: v for k, v in row.items() if k != "id"}}


def family_token(source: str, family: str) -> str:
    """`f_` + 10 hex of sha256(source:family): a family counted exactly, whatever its own id looks like (a phrase, a
    file name), and never stored as itself."""
    return "f_" + hashlib.sha256(f"{source}:{family}".encode("utf-8", "surrogatepass")).hexdigest()[:10]


def _count(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _in(x: object, ids: object) -> bool:
    """`x` is a str and one of `ids` (a collection of the vocabulary), whatever `ids` turns out to be."""
    if not isinstance(x, str) or not isinstance(ids, (list, tuple, set, frozenset, Mapping)):
        return False
    try:
        return x in ids
    except TypeError:
        return False


def _field(p: list, path: str, v: object, voc: object, required: bool) -> None:
    if voc is None:
        p.append(f"{path}: no vocabulary for it")
    elif isinstance(voc, Seq):
        if v is None and not required:
            return
        if not (isinstance(v, list) and 1 <= len(v) <= voc.max and all(_in(x, voc.ids) for x in v)
                and all(x != y for x, y in zip(v, v[1:]))):
            p.append(f"{path}: null, or 1-{voc.max} ids of its vocabulary, none twice in a row")
    elif isinstance(voc, Mapping):
        if not isinstance(v, dict):
            p.append(f"{path}: an object of {{key: id}} (empty when none)")
        elif not all(_in(k, voc) and _in(x, voc[k]) for k, x in v.items()) or (required and not v):
            p.append(f"{path}: a key or value not in its vocabulary")
    elif v is None:
        if required:
            p.append(f"{path}: never null")
    elif not _in(v, voc):
        p.append(f"{path}: not in its vocabulary")


def validate(row: object, shape: Shape, vocab: Mapping[str, Any]) -> list[str]:
    """The problems of one evidence row (empty: valid). Never raises. A problem names the field, never the value."""
    try:
        return _validate(row, shape, vocab)
    except Exception as e:                    # a skill pack's odd vocabulary must not crash an export: report it
        return [f"the row could not be checked ({type(e).__name__})"]


def _validate(row: object, shape: Shape, vocab: Mapping[str, Any]) -> list[str]:
    if not isinstance(row, dict):
        return ["the row is not an object"]
    p: list[str] = []
    src = shape.source(row.get("source"))
    if set(row) != shape.keys(src):
        miss, extra = sorted(shape.keys(src) - set(row)), set(row) - shape.keys(src)
        p.append("row: keys" + (f" missing {', '.join(miss)}" if miss else "") + (f" unknown {len(extra)}" if extra else ""))
    if row.get("schema") != shape.schema:
        p.append(f"schema: not {shape.schema}")
    if src is None:
        p.append("source: not one of the shape's sources")
    m = PERIOD.fullmatch(row["period"]) if isinstance(row.get("period"), str) else None
    if not m or m.group(1) > m.group(2):
        p.append("period: not YYYY-MM/YYYY-MM (from <= to)")
    rule = row.get("label_rule")
    if src is not None and not _in(rule, src.label_rules):
        p.append(f"label_rule: not one source {src.name} takes")
    for g in GROUPS:
        obj, want = row.get(g), shape.fields(g)
        if not isinstance(obj, dict):
            p.append(f"{g}: not an object")
            continue
        if set(obj) != set(want):
            p.append(f"{g}: keys not exactly {', '.join(want)}")
        for f in want:
            if f in obj:
                _field(p, f"{g}.{f}", obj[f], vocab.get(f), f"{g}.{f}" in shape.required)
    n = row.get("n")
    if not (_count(n) and n >= 1):
        p.append("n: an int of at least 1")
    fam = row.get("families")
    if not (isinstance(fam, list) and fam and all(isinstance(f, str) and FAMILY.fullmatch(f) for f in fam)
            and fam == sorted(set(fam)) and (not _count(n) or len(fam) <= n)):
        p.append("families: a sorted list of unique family tokens (f_ + 10 hex), at least one, at most n")
    if src is not None and src.outcomes:
        outs = [row.get(k) for k in shape.outcomes]
        if not all(_count(x) and x >= 0 for x in outs):
            p.append(f"{', '.join(shape.outcomes)}: ints of at least 0")
        elif _count(n) and sum(outs) != n:
            p.append(f"{' + '.join(shape.outcomes)}: not n")
        elif rule in src.unlabelled and row.get(shape.outcomes[-1]) != n:
            p.append(f"{shape.outcomes[-1]}: an unlabelled row counts every item as {shape.outcomes[-1]}")
    for e in src.extra if src is not None else ():
        _field(p, e, row.get(e), vocab.get(e), True)
    try:
        canonical(row).encode("utf-8")
        want_id = row_id(row)
    except (TypeError, ValueError, UnicodeEncodeError):
        p.append("id: not canonical JSON (a value JSON cannot hold, mixed key types, or text that is not UTF-8)")
        return p
    if not (isinstance(row.get("id"), str) and ROW_ID.fullmatch(row["id"])) or row["id"] != want_id:
        p.append("id: not the first 16 hex of the sha256 of the row without its id")
    return p


def group(items: Iterable[Mapping], shape: Shape) -> list[dict]:
    """Per-item records -> evidence rows: one row per (source, period, label_rule, context, icp, play), with `n`, the
    family tokens and, for a source with outcomes, the outcome counts. An item is {source, period, label_rule, context,
    icp, play, family (its own id: hashed here), outcome (one of shape.outcomes; ignored on a presence source)}. A
    source's extra fields are the skill pack's: add them, then `with_id()` again. Order: the shape's sources, most items
    first, then the id. Check every row with `validate()` before anything is written."""
    cells: dict[str, dict] = {}
    for a in items:
        vec = {k: a[k] for k in ("source", "period", "label_rule", *GROUPS)}
        c = cells.setdefault(canonical(vec), {"vec": vec, "n": 0, "fams": set(), "out": dict.fromkeys(shape.outcomes, 0)})
        c["n"] += 1
        c["fams"].add(family_token(str(a["source"]), str(a["family"])))
        if a.get("outcome") in c["out"]:
            c["out"][a["outcome"]] += 1
    rows = []
    for c in cells.values():
        src = shape.source(c["vec"]["source"])
        row = {"schema": shape.schema, **c["vec"], "n": c["n"], "families": sorted(c["fams"])}
        if src is None or src.outcomes:
            row.update(c["out"])
        rows.append(with_id(row))
    order = [s.name for s in shape.sources]
    return sorted(rows, key=lambda r: (order.index(r["source"]) if r["source"] in order else len(order), -r["n"], r["id"]))


# ---------------------------------------------------------------- two coders

def agreement(a: Mapping[str, Mapping[str, Any]], b: Mapping[str, Mapping[str, Any]],
              fields: Iterable[str] | None = None) -> dict[str, dict]:
    """{field: {compared, agreed, agree}} of two independent coders' {item: {field: value}}, over every item either
    coded. A field both left null is unsure and not compared; an item one coder left out, or a field only one answered,
    counts against them. `agree` is rounded for display only: `meets_floor()` reads the counts."""
    items = sorted(set(a) | set(b))
    if fields is None:
        fields = sorted({f for side in (a, b) for i in side for f in (side[i] or {})})
    out = {}
    for f in fields:
        compared = agreed = 0
        for i in items:
            va, vb = (a.get(i) or {}).get(f), (b.get(i) or {}).get(f)
            if va is None and vb is None:
                continue
            compared += 1
            agreed += va == vb
        out[f] = {"compared": compared, "agreed": agreed, "agree": round(agreed / compared, 3) if compared else None}
    return out


def meets_floor(stat: Mapping, floor: float = FLOOR) -> bool:
    """Whether a field's agreement reaches the floor, from its counts (6996 of 10000 is under 0.70); none compared is
    not counted."""
    return stat["compared"] > 0 and stat["agreed"] >= floor * stat["compared"] - 1e-9


def counted(stats: Mapping[str, Mapping], floor: float = FLOOR) -> list[str]:
    """The fields that count: their two coders agree at the floor. Every other coded field is null for every item."""
    return [f for f, s in stats.items() if meets_floor(s, floor)]


def agreed_values(a: Mapping[str, Mapping[str, Any]], b: Mapping[str, Mapping[str, Any]],
                  fields: Iterable[str]) -> dict[str, dict]:
    """{item: {field: value}} for the counted `fields` where both coders gave the same non-null value. A disagreement
    is null here; an adjudicated value is the skill pack's to add, and must be one of the two."""
    out: dict[str, dict] = {}
    for i in sorted(set(a) | set(b)):
        for f in fields:
            va, vb = (a.get(i) or {}).get(f), (b.get(i) or {}).get(f)
            if va is not None and va == vb:
                out.setdefault(i, {})[f] = va
    return out


# ---------------------------------------------------------------- the Beta distribution, stdlib only

def _betacf(a: float, b: float, x: float) -> float:
    """The continued fraction of the incomplete beta function (modified Lentz; Numerical Recipes 6.4)."""
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + aa / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-15:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """The regularized incomplete beta function I_x(a, b): the CDF of Beta(a, b) at x (a, b > 0)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def beta_quantile(p: float, a: float, b: float) -> float:
    """The p-quantile of Beta(a, b) by bisection on betainc (to 2^-60). a = 0 is all the mass at 0, b = 0 at 1."""
    if a <= 0.0 or p <= 0.0:
        return 0.0
    if b <= 0.0 or p >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if betainc(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ---------------------------------------------------------------- the shrinkage

def _cells(cells: Iterable[Sequence[int]]) -> list[tuple[int, int]]:
    out = []
    for c in cells:
        w, m = c
        if not (_count(w) and _count(m) and 0 <= w <= m):
            raise ValueError("a cell is (successes, labelled): ints, 0 <= successes <= labelled")
        out.append((w, m))
    return out


MIN_CELLS = 2                                  # a field with fewer labelled non-null cells gets counts only, no rate
NO_PRIOR = {"no_labelled": "no cell has a labelled item",
            "one_cell": f"fewer than {MIN_CELLS} non-null cells have a labelled item: counts only, no shrunk rate"}


def prior_reason(cells: Iterable[Sequence[int]]) -> str | None:
    """Why the cells give no prior (a key of NO_PRIOR), or None when they give one."""
    k = sum(1 for _, m in _cells(cells) if m > 0)
    return "no_labelled" if k == 0 else "one_cell" if k < MIN_CELLS else None


def prior(cells: Iterable[Sequence[int]], lo: float = PRIOR_TESTS[0], hi: float = PRIOR_TESTS[1]) -> dict | None:
    """The field's prior from its non-null cells' (successes, labelled): mu = the pooled rate anchored off the edges,
    (sum w + 0.5) / (N + 1), so an all-win or all-lose field keeps an interval; kappa by the method of moments for the
    beta-binomial (the spread of the cells' raw rates about mu, weighted by labelled, beyond what binomial noise gives:
    E[sum m (p - mu)^2] = mu (1 - mu) [(k - 1) + rho (N - sum m^2 / N - (k - 1))], kappa = (1 - rho) / rho), clipped
    to [lo, hi]. No spread to read (a spread within chance) is the most shrinkage, hi. None, with `prior_reason()`,
    when fewer than MIN_CELLS cells have a labelled item: one cell has no field to be shrunk toward. A null value is
    never a cell here. It ranks nothing."""
    if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and 0 < lo <= hi):
        raise ValueError("the prior is worth lo to hi tests: 0 < lo <= hi")
    cells = [(w, m) for w, m in _cells(cells) if m > 0]
    if prior_reason(cells) is not None:
        return None
    big_n = sum(m for _, m in cells)
    mu = (sum(w for w, _ in cells) + 0.5) / (big_n + 1)
    k, raw = len(cells), None
    ss = sum((w - m * mu) ** 2 / m for w, m in cells)
    denom = big_n - sum(m * m for _, m in cells) / big_n - (k - 1)
    if denom > 0:
        rho = (ss / (mu * (1.0 - mu)) - (k - 1)) / denom
        raw = (1.0 - rho) / rho if rho > 0 else None
    kappa = hi if raw is None else min(max(raw, lo), hi)
    clipped = None if raw is not None and lo <= raw <= hi else ("min" if raw is not None and raw < lo else "max")
    return {"mu": mu, "kappa": kappa, "kappa_moments": raw, "clipped": clipped, "cells": k, "labelled": big_n,
            "count": sum(w for w, _ in cells)}


def shrunk(w: int, m: int, pr: Mapping, interval: Sequence[float] = INTERVAL) -> dict:
    """One cell's shrunk rate (w + kappa mu) / (m + kappa), its interval (quantiles of Beta(w + kappa mu,
    m - w + kappa (1 - mu))), its raw rate and its counts: a rate never travels without them."""
    ((w, m),) = _cells([(w, m)])
    a, b = w + pr["kappa"] * pr["mu"], m - w + pr["kappa"] * (1.0 - pr["mu"])
    return {"shrunk": round(a / (a + b), 4), "interval": [round(beta_quantile(q, a, b), 4) for q in interval],
            "raw": round(w / m, 4) if m else None, "count": w, "of": m}


def ranks(values: Sequence[float | None]) -> list[int | None]:
    """Competition ranks, highest first (1, 2, 2, 4): a tie shares its rank, so nothing is crowned by a rounding;
    None stays None."""
    got = [v for v in values if v is not None]
    return [None if v is None else 1 + sum(1 for o in got if o > v) for v in values]


def shrink(cells: Iterable[Sequence[int]], lo: float = PRIOR_TESTS[0], hi: float = PRIOR_TESTS[1],
           interval: Sequence[float] = INTERVAL) -> dict:
    """{prior, reason, cells}: the prior of one field's non-null (successes, labelled) cells (a null value is not passed:
    it gets no rate and no status) and, per cell in the same order, its shrunk rate with interval, counts and rank (None
    for a cell with no labelled item). With no prior, `reason` says why and no cell has a rate: counts only."""
    cells = _cells(cells)
    pr = prior(cells, lo, hi)
    out = [shrunk(w, m, pr, interval) if pr is not None and m else None for w, m in cells]
    for c, r in zip(out, ranks([c["shrunk"] if c else None for c in out])):
        if c is not None:
            c["rank"] = r
    why = prior_reason(cells)
    return {"prior": pr, "reason": NO_PRIOR[why] if why else None, "cells": out}


# ---------------------------------------------------------------- the store (kit.db's table format)

_T, _I = "TEXT", "INTEGER"
TABLES: dict[str, dict] = {
    "pattern_rows": {
        "columns": {"id": _I, "scope": _T, "row_id": _T, "source": _T, "period": _T, "n": _I, "payload": _T,
                    "recorded_at": _T, "recorded_by": _T},
        "pk": ("id",),
        "not_null": ("scope", "row_id", "source", "period", "n", "payload", "recorded_at", "recorded_by"),
        "doc": "One evidence row of a scope (a project, a product line: the skill pack's word), abstract only, as "
               "canonical JSON under its content id. Live while no pattern_retractions row names it. Append-only.",
        "grain": "evidence row x export",
    },
    "pattern_retractions": {
        "columns": {"record": _I, "scope": _T, "row_id": _T, "reason": _T, "retracted_at": _T, "retracted_by": _T},
        "pk": ("record",),
        "not_null": ("scope", "row_id", "reason", "retracted_at", "retracted_by"),
        "doc": "A pattern_rows record withdrawn (record = its id): `superseded` by an export that no longer makes it, "
               "or a reason given by hand. The row stays. Append-only.",
        "grain": "pattern row",
    },
    "pattern_reinstatements": {
        "columns": {"record": _I, "scope": _T, "row_id": _T, "reinstated_at": _T, "reinstated_by": _T},
        "pk": ("record",),
        "not_null": ("scope", "row_id", "reinstated_at", "reinstated_by"),
        "doc": "A retraction by hand lifted: the next export may make the row live again as a new record; the "
               "retracted record stays retracted. Append-only.",
        "grain": "pattern row",
    },
}
APPEND_ONLY: dict[str, tuple[str, ...]] = {t: ("UPDATE", "DELETE") for t in TABLES}


def _has_tables(con) -> bool:
    got = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return set(TABLES) <= got


def records(con, scope: str | None = None) -> list[dict]:
    """Every pattern_rows record of `scope` (None: every scope), oldest first, with its retraction reason (None: live)
    and whether that retraction was lifted. No tables yet (a read-only open of an older file): none."""
    if not _has_tables(con):
        return []
    sql = ("SELECT p.id, p.scope, p.row_id, p.source, p.n, p.payload, r.reason, s.record IS NOT NULL "
           "FROM pattern_rows p LEFT JOIN pattern_retractions r ON r.record = p.id "
           "LEFT JOIN pattern_reinstatements s ON s.record = p.id")
    got = con.execute(sql + " WHERE p.scope = ? ORDER BY p.id", (scope,)) if scope is not None \
        else con.execute(sql + " ORDER BY p.id")
    keys = ("record", "scope", "row_id", "source", "n", "payload", "reason", "lifted")
    return [dict(zip(keys, r)) for r in got]


def state(con, scope: str, source: str | None = None) -> tuple[dict[str, dict], dict[str, dict]]:
    """({row id: its live record}, {row id: its record kept out}) of `scope`: a row id is kept out of every export while
    a retraction by hand (any reason but `superseded`) names one of its records and no reinstatement lifted it."""
    live: dict[str, dict] = {}
    kept: dict[str, dict] = {}
    for r in records(con, scope):
        if source is not None and r["source"] != source:
            continue
        into = live if r["reason"] is None else kept if _by_hand(r) else None
        if into is not None:                    # every record of the id rides along, so all of them are acted on
            into.setdefault(r["row_id"], {**r, "records": []})["records"].append(r["record"])
    return live, {i: r for i, r in kept.items() if i not in live}


def _by_hand(r: Mapping) -> bool:
    """A record retracted by hand (any reason but `superseded`) and not lifted: its row id stays out."""
    return r["reason"] is not None and r["reason"] != SUPERSEDED and not r["lifted"]


def live_rows(con, scope: str | None = None) -> list[dict]:
    """The live rows of `scope` (None: every scope of this one client's file; a row id live under two scopes is one
    row, and a row id retracted by hand in any scope read, not lifted, is out), as their payloads. A store never holds
    another client's rows: the skill pack opens this client's file only."""
    recs = records(con, scope)
    out_ids = {r["row_id"] for r in recs if _by_hand(r)}
    out: dict[str, dict] = {}
    for r in recs:
        if r["reason"] is None and r["row_id"] not in out_ids:
            out.setdefault(r["row_id"], json.loads(r["payload"]))
    return list(out.values())


def plan(live: Mapping[str, Mapping], kept: Mapping[str, Mapping], rows: Sequence[Mapping], read: Iterable[str],
         reinstate: Iterable[str] = ()) -> dict:
    """What an export does to a scope, from `state()`: `insert` the rows neither live nor kept out; `supersede` the live
    records the export no longer makes, of the sources it `read` (a source not read keeps its rows live: `unread`
    counts them); `lift` the kept-out records `reinstate` names (their rows are then inserted anew); `unknown` the
    `reinstate` ids that name no kept-out row (the skill pack refuses them); `kept` what stays out; `duplicates` the rows
    dropped because an earlier row of this export has the same id (each id is inserted once)."""
    read, kept = set(read), dict(kept)
    lift, unknown = [], []
    for rid in reinstate:
        if rid in kept:
            lift.append(kept.pop(rid))
        else:
            unknown.append(rid)
    once: dict[str, Mapping] = {}
    for r in rows:
        once.setdefault(r["id"], r)
    duplicates, rows = len(rows) - len(once), list(once.values())
    made = set(once)
    unread: dict[str, int] = {}
    for i, x in live.items():
        if i not in made and x["source"] not in read:
            unread[x["source"]] = unread.get(x["source"], 0) + 1
    return {"insert": [r for r in rows if r["id"] not in live and r["id"] not in kept],
            "supersede": [x for i, x in live.items() if i not in made and x["source"] in read],
            "lift": lift, "unknown": unknown, "kept": kept, "unread": unread, "duplicates": duplicates,
            "already_live": sum(1 for r in rows if r["id"] in live)}


def apply(con, scope: str, p: Mapping, now: str, by: str) -> None:
    """Append what `plan()` decided: the reinstatements, the `superseded` retractions (every live record of the id),
    then the new rows. Run it inside the skill pack's write transaction (kit.db.keep_human_rows), after every row passed
    `validate()`. A row whose id does not recompute is refused (ValueError) before anything is written."""
    bad = [r.get("id") for r in p["insert"] if not isinstance(r, Mapping) or r.get("id") != row_id(r)]
    if bad:
        raise ValueError(f"{len(bad)} row(s) whose id is not row_id() of the row: nothing written")
    for x in p["lift"]:
        for rec in x.get("records") or [x["record"]]:
            con.execute("INSERT INTO pattern_reinstatements (record, scope, row_id, reinstated_at, reinstated_by) "
                        "VALUES (?,?,?,?,?)", (rec, scope, x["row_id"], now, by))
    for x in p["supersede"]:
        for rec in x.get("records") or [x["record"]]:
            con.execute("INSERT INTO pattern_retractions (record, scope, row_id, reason, retracted_at, retracted_by) "
                        "VALUES (?,?,?,?,?,?)", (rec, scope, x["row_id"], SUPERSEDED, now, by))
    for r in p["insert"]:
        con.execute("INSERT INTO pattern_rows (scope, row_id, source, period, n, payload, recorded_at, recorded_by) "
                    "VALUES (?,?,?,?,?,?,?,?)", (scope, r["id"], r["source"], r["period"], r["n"], canonical(r), now, by))


def retract(con, scope: str, rid: str, reason: str, now: str, by: str) -> dict | None:
    """Append a retraction by hand of the live row `rid` of `scope` (the reason a token of the skill pack's own list, never
    `superseded`), every live record of it. The row's record (with `records`), or None when no live row has that id.
    Inside the skill pack's transaction."""
    if not _token(reason) or reason == SUPERSEDED:
        raise ValueError(f"a reason given by hand is a token of the skill pack's list, never {SUPERSEDED}")
    got = state(con, scope)[0].get(rid)
    if got is None:
        return None
    for rec in got["records"]:
        con.execute("INSERT INTO pattern_retractions (record, scope, row_id, reason, retracted_at, retracted_by) "
                    "VALUES (?,?,?,?,?,?)", (rec, scope, rid, reason, now, by))
    return got
