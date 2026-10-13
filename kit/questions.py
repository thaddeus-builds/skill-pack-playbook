"""Open questions never hold the plan: what the harness cannot answer yet is recorded with the data that can answer
it and with what the plan does until then. Rule: docs/rules.md, Human-in-the-loop rule 13.

A harness keeps its open questions as rows (any mapping, any store): `id`, `text`, an optional `answer`, an optional
`dropped`, and the two fields this module reads:

  * `by_data`: which data, once the harness holds it, can answer the question without asking anyone. One of the
    harness's own closed list of kinds (its results file, an audience report, an order export, the comments under its
    ads), or `ask_only` (the default name; a harness may rename it) when only a person can. Never blank and never
    defaulted: a question that names nothing is a problem;
  * `meanwhile`: what the plan does until the answer is known, an action ("write the template, compile it, make
    nothing"), never a wait. A step that waits for an answer is the fault this rule removes.

and, only when the harness records a read-back, `checked`: the fingerprint of the data the agent last read for it.

What the kit holds (pure: no file, no database, no clock; stdlib only):

  * `problems(questions, sources)`: every unanswered question that breaks the two fields (a missing or repeated id, a
    `by_data` outside `sources` and `ask_only`, a blank `meanwhile`, a `meanwhile` that is a bare wait). A harness test
    calls it on its rows; whether an old row is refused or only warned about is the harness's. The wait test is a floor,
    not a proof: it catches the obvious waits (English, plus a few Chinese; `extra_waits` adds a harness's own words)
    and errs toward a false hit ("Hold on: write the template" is refused: reword it as the action);
  * `groups(questions, sources)`: the questions as a page shows them: `data` (by kind: the data will answer),
    `person` (only a person can), `unnamed` (no data named: the rows `problems` reports), `answered`;
  * `readback(questions, held)`: `held` maps a data kind to a fingerprint of what the harness holds now (a file's
    sha256, an import id). Every unanswered question whose kind is held and whose `checked` is not that fingerprint,
    each with the fingerprint: the harness prompts the agent to read the data and either record the answer or record
    the fingerprint it read. A new version of the data prompts again; `ask_only` is never prompted;
  * `self_test()`: every rule tried on a planted break; returns the rules that missed theirs (empty is sound).

*Seen once:* the video-ads harness (docs/rules.md, rule 13, says how).

Test: kit/tests/test_questions.py.
"""

from __future__ import annotations

import re
from typing import Collection, Iterable, Mapping, Sequence

ASK_ONLY = "ask_only"
# a `meanwhile` that only waits (compared after lowercasing and cutting punctuation): the whole text is one of BARE, or
# it begins with a word of WAIT_FIRST or a phrase of WAIT_PHRASES
BARE = frozenset({"", "none", "n a", "na", "tbd", "tba", "todo", "pending", "blocked", "on hold", "hold", "unknown",
                  "nothing", "no", "later", "无", "暂无", "待定"})
WAIT_FIRST = ("wait", "waiting", "await", "awaiting", "hold", "blocked", "pending", "idle", "pause", "paused",
              "defer", "deferred", "postpone", "postponed", "stop", "later", "tba", "tbd")
WAIT_PHRASES = ("on hold", "to be decided", "to be determined", "nothing to do", "none yet", "stay idle", "do nothing",
                "no action", "等待", "暂停", "暂缓", "等客户")


def _text(x: object) -> str:
    return x.strip() if isinstance(x, str) else ""


def _norm(x: object) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", _text(x).lower()).split())


def _id(x: object) -> str:
    """A question's id as text: a non-blank string, or a whole number (not a bool) written out; else ""."""
    if isinstance(x, bool):
        return ""
    return str(x) if isinstance(x, int) else _text(x)


def _fp(x: object) -> str:
    """A fingerprint as text (a hash string, or a whole-number import id); "" is no data."""
    return _id(x)


def _open(q: Mapping) -> bool:
    """Open: no answer (None or blank text; any other value, 0 and False included, is an answer) and not dropped (any
    truthy `dropped`)."""
    a = q.get("answer")
    return (a is None or (isinstance(a, str) and not a.strip())) and not q.get("dropped")


def _kinds(sources: Collection[str], ask_only: str) -> frozenset[str]:
    if isinstance(sources, str):
        raise ValueError("sources: give the harness's closed list of data kinds (a collection of names)")
    sources = tuple(sources)
    if not sources or not all(isinstance(s, str) and s.strip() for s in sources) or not _text(ask_only):
        raise ValueError("sources and ask_only: a closed list of data kinds, every kind a non-blank name")
    return frozenset(sources) | {ask_only}


def waits(meanwhile: object, extra: Iterable[str] = ()) -> bool:
    """True when a `meanwhile` is only a wait: blank, a bare placeholder ("TBD", "none"), or a text that begins by
    waiting, holding, pausing or deferring (BARE, WAIT_FIRST, WAIT_PHRASES), or by one of `extra`, the harness's own
    words. A word is matched whole ("waiter" is no wait); an `extra` or phrase in Chinese, which has no spaces, is
    matched as a prefix."""
    n = _norm(meanwhile)
    first = n.split(" ", 1)[0] if n else ""
    if n in BARE or first in WAIT_FIRST:
        return True
    for e in (*WAIT_PHRASES, *map(_norm, extra)):
        if e and (n == e or n.startswith(e + " ") or (not e.isascii() and n.startswith(e))):
            return True
    return False


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
        qid = _id(q.get("id"))
        who = qid or f"question #{i + 1}"
        if not qid:
            out.append(f"{who}: has no id (a non-blank string or a whole number)")
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
    """The questions as a page shows them, ids in the order given (an id is text; a question with none is listed as
    ""). `data` maps each kind in `sources` that has any to its unanswered questions; `person` is `ask_only`;
    `unnamed` has no valid kind (the rows `problems` reports); `answered` holds the answered ones (a dropped question
    is in none)."""
    kinds = _kinds(sources, ask_only)
    out: dict = {"data": {}, "person": [], "unnamed": [], "answered": []}
    for q in questions:
        if not isinstance(q, Mapping) or q.get("dropped"):
            continue
        qid, by = _id(q.get("id")), q.get("by_data")
        if not _open(q):
            out["answered"].append(qid)
        elif isinstance(by, str) and by == ask_only:
            out["person"].append(qid)
        elif isinstance(by, str) and by in kinds:
            out["data"].setdefault(by, []).append(qid)
        else:
            out["unnamed"].append(qid)
    return out


def readback(questions: Sequence[Mapping], held: Mapping[str, str | int] | None, *, key: str = "checked",
             ask_only: str = ASK_ONLY) -> list[dict]:
    """The unanswered questions the data now held can answer and the agent has not read it for: `{id, by_data,
    held}`, in the order given. `held` maps a kind to a fingerprint of the data (a hash string or a whole-number
    import id; blank, None or no entry means no data of that kind; None for `held` means none held); a question whose
    `key` equals that fingerprint (as text) was read already."""
    if held is None:
        held = {}
    if not isinstance(held, Mapping):
        raise ValueError("held: a mapping {kind: fingerprint}")
    out = []
    for q in questions:
        if not isinstance(q, Mapping) or not _open(q):
            continue
        by = q.get("by_data")
        fp = _fp(held.get(by)) if isinstance(by, str) and by != ask_only else ""
        if fp and _fp(q.get(key)) != fp:
            out.append({"id": _id(q.get("id")), "by_data": by, "held": fp})
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


# what is broken -> (the rows, the words the problem must say)
PLANTED = {
    "a question with no id": ([{**_SOUND[0], "id": ""}], "has no id"),
    "a repeated id": ([*_SOUND, dict(_SOUND[1])], "used twice"),
    "no by_data": (_plant(by_data=None), "names no data"),
    "a by_data outside the harness's kinds": (_plant(by_data="gossip"), "is not one of"),
    "no meanwhile": (_plant(meanwhile=None), "says nothing"),
    "a blank meanwhile": (_plant(meanwhile="  "), "says nothing"),
    "a bare placeholder meanwhile": (_plant(meanwhile="TBD"), "only waits"),
    "a meanwhile that waits": (_plant(meanwhile="Wait for the client to answer"), "only waits"),
    "a meanwhile that holds": (_plant(meanwhile="hold the batch"), "only waits"),
    "a meanwhile that pauses": (_plant(meanwhile="Pause until answered"), "only waits"),
    "a meanwhile that waits, in Chinese": (_plant(meanwhile="等待客户回复"), "only waits"),
}


def self_test() -> list[str]:
    """The rules that missed their planted break (the break not reported, or reported as another), or that let the
    sound rows fail; empty is sound."""
    missed = []
    if problems(_SOUND, _SOURCES):
        missed.append("the sound rows fail")
    for what, (rows, words) in PLANTED.items():
        if not any(words in p for p in problems(rows, _SOURCES)):
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
