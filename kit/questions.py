"""Open questions never hold the plan: what the harness cannot answer yet is recorded with the data that can answer
it and with what the plan does until then. Rule: docs/rules.md, Human-in-the-loop rule 13.

A harness keeps its open questions as rows (any mapping, any store): `id`, `text`, an optional `answer`, an optional
`dropped`, and the two fields this module reads:

  * `by_data`: which data, once the harness holds it, can answer the question without asking anyone. One of the
    harness's own closed list of kinds (its results file, an audience report, an order export, the comments under its
    ads), or `ask_only` (default "ask_only") when only a person can. Never blank;
  * `meanwhile`: what the plan does until the answer is known, an action ("write the template, compile it, make
    nothing"), never a wait. A step that waits for an answer is the fault this rule removes.

and, only when the harness records a read-back, `checked`: the fingerprint of the data the agent last read for it.

What the kit holds (pure: no file, no database, no clock; stdlib only):

  * `problems(questions, sources)`: every unanswered question that breaks the two fields (a missing id, a repeated
    id, a `by_data` outside `sources` and `ask_only`, a blank `meanwhile`, a `meanwhile` that is a bare wait). A harness
    test calls it on its rows; an old row may be loaded and only warned about, as the harness chooses. Errs toward a
    false hit (a `meanwhile` that begins with "wait"): reword it as the action;
  * `groups(questions, sources)`: the questions as a page shows them: `data` (by kind: the data will answer),
    `person` (only a person can), `unnamed` (no data named: the rows `problems` reports), `answered`;
  * `readback(questions, held)`: `held` maps a data kind to a fingerprint of what the harness holds now (a file's
    sha256, an import id). Every unanswered question whose kind is held and whose `checked` is not that fingerprint,
    each with the fingerprint: the harness prompts the agent to read the data and either record the answer or record
    the fingerprint it read. A new version of the data prompts again; `ask_only` is never prompted;
  * `self_test()`: every rule tried on a planted break; returns the rules that missed theirs (empty is sound).

*Seen once:* the video-ads harness (owner decision, 2026-10-13): its client rarely knows such answers, while the
results file the client sends back can answer some of them. Each question there now names the data and the action
meanwhile, and the harness warns once the data it names is held.

Test: kit/tests/test_questions.py.
"""

from __future__ import annotations

import re
from typing import Collection, Iterable, Mapping, Sequence

ASK_ONLY = "ask_only"
# a `meanwhile` that only waits (compared after lowercasing and cutting punctuation); the first word of any other
# text that makes it a wait is in WAIT_FIRST
BARE = frozenset({"", "none", "n a", "na", "tbd", "todo", "pending", "blocked", "on hold", "hold", "unknown",
                  "nothing", "no"})
WAIT_FIRST = ("wait", "waiting", "await", "awaiting", "hold", "blocked")


def _text(x: object) -> str:
    return x.strip() if isinstance(x, str) else ""


def _norm(x: object) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", _text(x).lower()).split())


def _open(q: Mapping) -> bool:
    """Unanswered and not dropped: the questions this module reads."""
    a = q.get("answer")
    return (a is None or (isinstance(a, str) and not a.strip())) and not q.get("dropped")


def _kinds(sources: Collection[str], ask_only: str) -> frozenset[str]:
    if isinstance(sources, str) or not sources:
        raise ValueError("sources: give the harness's closed list of data kinds (a collection of names)")
    bad = [s for s in sources if not _text(s)]
    if bad or not _text(ask_only):
        raise ValueError("sources and ask_only: every kind is a non-blank name")
    return frozenset(sources) | {ask_only}


def waits(meanwhile: object, extra: Iterable[str] = ()) -> bool:
    """True when a `meanwhile` is only a wait: blank, a bare placeholder ("TBD", "none"), or a text that begins by
    waiting or holding (or by one of `extra`, the harness's own words, lowercase)."""
    n = _norm(meanwhile)
    first = n.split(" ", 1)[0] if n else ""
    return n in BARE or first in WAIT_FIRST or any(n == e or n.startswith(e + " ") for e in map(_norm, extra))


def problems(questions: Sequence[Mapping], sources: Collection[str], *, ask_only: str = ASK_ONLY,
             extra_waits: Iterable[str] = ()) -> list[str]:
    """Every break of the rule, one string each, naming the question's id; empty when the rule holds."""
    kinds = _kinds(sources, ask_only)
    out: list[str] = []
    seen: set[str] = set()
    for i, q in enumerate(questions):
        if not isinstance(q, Mapping):
            out.append(f"question #{i + 1}: not a mapping")
            continue
        qid = _text(q.get("id"))
        who = qid or f"question #{i + 1}"
        if not qid:
            out.append(f"{who}: has no id")
        elif qid in seen:
            out.append(f"{who}: the id is used twice")
        seen.add(qid)
        if not _open(q):
            continue
        by = q.get("by_data")
        if not _text(by):
            out.append(f"{who}: names no data that can answer it (by_data; {ask_only} when only a person can)")
        elif by not in kinds:
            out.append(f"{who}: by_data {by!r} is not one of {sorted(kinds)}")
        if not _text(q.get("meanwhile")):
            out.append(f"{who}: says nothing about what the plan does meanwhile")
        elif waits(q.get("meanwhile"), extra_waits):
            out.append(f"{who}: meanwhile only waits (say the action the plan takes until the answer is known)")
    return out


def groups(questions: Sequence[Mapping], sources: Collection[str], *, ask_only: str = ASK_ONLY) -> dict:
    """The questions as a page shows them, ids in the order given. `data` maps each kind in `sources` that has any to
    its unanswered questions; `person` is `ask_only`; `unnamed` has no valid kind; `answered` holds the answered
    ones (a dropped question is in none)."""
    kinds = _kinds(sources, ask_only)
    out: dict = {"data": {}, "person": [], "unnamed": [], "answered": []}
    for q in questions:
        if not isinstance(q, Mapping) or q.get("dropped"):
            continue
        qid = _text(q.get("id"))
        if not _open(q):
            out["answered"].append(qid)
        elif q.get("by_data") == ask_only:
            out["person"].append(qid)
        elif q.get("by_data") in kinds:
            out["data"].setdefault(q["by_data"], []).append(qid)
        else:
            out["unnamed"].append(qid)
    return out


def readback(questions: Sequence[Mapping], held: Mapping[str, str], *, key: str = "checked",
             ask_only: str = ASK_ONLY) -> list[dict]:
    """The unanswered questions the data now held can answer and the agent has not read it for: `{id, by_data,
    held}`, in the order given. `held` maps a kind to a fingerprint of the data (a blank one means no data of that
    kind); a question whose `key` equals that fingerprint was read already."""
    out = []
    for q in questions:
        if not isinstance(q, Mapping) or not _open(q):
            continue
        by = q.get("by_data")
        fp = _text(held.get(by)) if isinstance(by, str) and by != ask_only else ""
        if fp and _text(q.get(key)) != fp:
            out.append({"id": _text(q.get("id")), "by_data": by, "held": fp})
    return out


# ---- the rules, each tried on a planted break ---------------------------------------------------------------------

_SOURCES = ("results_file", "order_export")
_SOUND = [{"id": "Q1", "text": "t", "by_data": "results_file", "meanwhile": "write the template, make nothing"},
          {"id": "Q2", "text": "t", "by_data": ASK_ONLY, "meanwhile": "use the owner's last stated value"},
          {"id": "Q3", "text": "t", "answer": "yes"}]


def _plant(**over) -> list[dict]:
    """The sound rows with the first one changed (a value None removes the field)."""
    row = {k: v for k, v in {**_SOUND[0], **over}.items() if v is not None}
    return [row, *_SOUND[1:]]


PLANTED = {
    "a question with no id": [{**_SOUND[0], "id": ""}],
    "a repeated id": [*_SOUND, dict(_SOUND[1])],
    "no by_data": _plant(by_data=None),
    "a by_data outside the harness's kinds": _plant(by_data="gossip"),
    "no meanwhile": _plant(meanwhile=None),
    "a blank meanwhile": _plant(meanwhile="  "),
    "a bare placeholder meanwhile": _plant(meanwhile="TBD"),
    "a meanwhile that waits": _plant(meanwhile="Wait for the client to answer"),
    "a meanwhile that holds": _plant(meanwhile="hold the batch"),
}


def self_test() -> list[str]:
    """The rules that missed their planted break, or let the sound rows fail; empty is sound."""
    missed = []
    if problems(_SOUND, _SOURCES):
        missed.append("the sound rows fail")
    for what, rows in PLANTED.items():
        if not problems(rows, _SOURCES):
            missed.append(what)
    if problems(_plant(by_data=None, meanwhile=None, answer="done"), _SOURCES):
        missed.append("an answered question needs neither field")
    if problems(_plant(by_data=None, meanwhile=None, dropped=True), _SOURCES):
        missed.append("a dropped question needs neither field")
    if readback(_SOUND, {"results_file": "sha1"}) != [{"id": "Q1", "by_data": "results_file", "held": "sha1"}]:
        missed.append("readback: data now held prompts the question it can answer")
    if readback(_plant(checked="sha1"), {"results_file": "sha1"}):
        missed.append("readback: data already read does not prompt again")
    if not readback(_plant(checked="sha1"), {"results_file": "sha2"}):
        missed.append("readback: a new version of the data prompts again")
    if readback(_SOUND, {ASK_ONLY: "x"}):
        missed.append("readback: ask_only is never prompted")
    return missed
