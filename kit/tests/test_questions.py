#!/usr/bin/env python3
"""kit.questions: an open question never holds the plan, on SYNTHETIC rows only (neutral kinds and words).

  [0] the rules, each on its planted break; the sound rows pass; an answered or dropped question needs neither field
  [1] problems(): the id (missing, repeated), by_data (missing, blank, outside the harness's kinds; ask_only allowed,
      also when the harness lists it), meanwhile (missing, blank, placeholder, a wait in any case or punctuation, the
      harness's own wait words), non-mapping rows, a bad list of kinds refused; nothing is mutated
  [2] groups(): data by kind, person, unnamed, answered; a dropped question in none; the order given
  [3] readback(): data held prompts once per version of it, an answered question never, ask_only never, a blank
      fingerprint is no data, another key name; nothing is mutated
"""

import copy
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import questions as Q  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

KINDS = ("results_file", "order_export")


def row(**over) -> dict:
    base = {"id": "Q1", "text": "t", "by_data": "results_file", "meanwhile": "write the template and make nothing"}
    return {k: v for k, v in {**base, **over}.items() if v is not None}


def raises(fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
    except ValueError:
        return True
    return False


def test_rules() -> None:
    print("\n[0] the rules, each on its planted break")
    check("self_test: every rule catches its plant, the sound rows pass", Q.self_test() == [], Q.self_test())
    for what, (rows, words) in Q.PLANTED.items():
        got = Q.problems(rows, Q._SOURCES)
        check(f"planted: {what}", any(words in g for g in got), got)
    check("a question answered needs neither field", Q.problems([row(by_data=None, meanwhile=None, answer="x")], KINDS) == [])
    check("a question dropped needs neither field", Q.problems([row(by_data=None, meanwhile=None, dropped=True)], KINDS) == [])
    check("a blank answer is not an answer", len(Q.problems([row(by_data=None, answer="  ")], KINDS)) == 1)
    check("a number as the answer is an answer", Q.problems([row(by_data=None, meanwhile=None, answer=0)], KINDS) == [])


def test_problems() -> None:
    print("\n[1] problems()")
    p = lambda *rows, **kw: Q.problems(list(rows), KINDS, **kw)  # noqa: E731
    check("sound row", p(row()) == [])
    check("the problem names the id", p(row(id="Q7", by_data=None))[0].startswith("Q7:"))
    check("repeated id", p(row(), row()) == ["Q1: the id is used twice"], p(row(), row()))
    check("no id", p(row(id=None))[0].startswith("question #1: has no id"))
    check("by_data outside the kinds names the kinds", "'gossip'" in p(row(by_data="gossip"))[0]
          and "order_export" in p(row(by_data="gossip"))[0])
    check("ask_only is always allowed", p(row(by_data="ask_only")) == [])
    check("a harness may list ask_only itself", Q.problems([row(by_data="ask_only")], (*KINDS, "ask_only")) == [])
    check("another word for ask_only", Q.problems([row(by_data="person")], KINDS, ask_only="person") == []
          and len(Q.problems([row(by_data="ask_only")], KINDS, ask_only="person")) == 1)
    check("by_data blank", len(p(row(by_data=" "))) == 1)
    check("by_data not a string", len(p(row(by_data=3))) == 1)
    for text in ("TBD", "tbd.", "N/A", "None", "pending", "wait", "Waiting for the client", "wait-and-see", "Hold the batch",
                 "Blocked on Q4", "await the leaflet", "WAIT: nothing to do", "Pending client", "On hold until client replies",
                 "Nothing to do until answer", "None yet", "stay idle", "pause the batch", "stop until answered", "defer",
                 "to be decided", "TBA", "later", "等待客户回复", "待定", "无", "暂停出片"):
        check(f"a wait: {text!r}", len(p(row(meanwhile=text))) == 1, p(row(meanwhile=text)))
    for text in ("write the template, compile it, make nothing", "use the last stated value", "make the batch on the "
                 "known rows; the template waits for the leaflet", "先写模板，不出片", "waiter note: cover the lower band",
                 "无需等客户，先写模板"):
        check(f"an action: {text!r}", p(row(meanwhile=text)) == [], p(row(meanwhile=text)))
    check("a Chinese extra wait word is a prefix", len(p(row(meanwhile="静候客户回复"), extra_waits=("静候",))) == 1
          and p(row(meanwhile="先写模板"), extra_waits=("静候",)) == [])
    check("the harness's own wait words", len(p(row(meanwhile="stand by for the client"), extra_waits=("stand by",))) == 1
          and p(row(meanwhile="stand by for the client")) == [])
    check("an extra wait word is not matched inside a word", p(row(meanwhile="standby tool built"), extra_waits=("stand",)) == [])
    check("a row that is not a mapping", p("Q1")[0] == "question #1: not a mapping")
    check("several breaks in one row are all named", len(p(row(by_data="gossip", meanwhile="TBD"))) == 2)
    for bad in ("results_file", [], (), [""], [None], iter(()), [3]):
        check(f"the kinds {bad!r} are refused", raises(Q.problems, [row()], bad))
    check("the kinds may be an iterator of names", Q.problems([row()], iter(KINDS)) == [])
    check("a whole-number id is an id; two the same are one", Q.problems([row(id=1), row(id=2)], KINDS) == []
          and Q.problems([row(id=1), row(id="1")], KINDS) == ["1: the id is used twice"])
    check("an id that is a bool, a list or None is no id", all("has no id" in Q.problems([row(id=x)], KINDS)[0]
                                                               for x in (True, ["Q1"], None)))
    for odd in (["results_file"], {"a": 1}, 3, None):
        check(f"by_data {odd!r} is a problem, not a crash", len(Q.problems([row(by_data=odd)], KINDS)) == 1)
    check("a blank ask_only is refused", raises(Q.problems, [row()], KINDS, ask_only=" "))
    rows = [row(), row(id="Q2", by_data="gossip")]
    before = copy.deepcopy(rows)
    Q.problems(rows, KINDS), Q.groups(rows, KINDS), Q.readback(rows, {"results_file": "x"})
    check("nothing is mutated", rows == before)


def test_groups() -> None:
    print("\n[2] groups()")
    rows = [row(id="Q3"), row(id="Q1", by_data="order_export"), row(id="Q2", by_data="ask_only"), row(id="Q4", by_data="x"),
            row(id="Q5", by_data=None), row(id="Q6", answer="done"), row(id="Q7", dropped=True), row(id="Q8", by_data="results_file")]
    g = Q.groups(rows, KINDS)
    check("data by kind, in the order given", g["data"] == {"results_file": ["Q3", "Q8"], "order_export": ["Q1"]}, g)
    check("person", g["person"] == ["Q2"], g)
    check("unnamed holds the unknown and the missing kind", g["unnamed"] == ["Q4", "Q5"], g)
    check("answered", g["answered"] == ["Q6"], g)
    check("a dropped question is in none", "Q7" not in str(g), g)
    check("an empty list", Q.groups([], KINDS) == {"data": {}, "person": [], "unnamed": [], "answered": []})
    check("a bad list of kinds is refused", raises(Q.groups, rows, "results_file"))
    odd = Q.groups([row(id="Q1", by_data=["results_file"]), row(id="Q2", by_data={"a": 1}), row(id=7, by_data="results_file"),
                    row(id=None, answer="x")], KINDS)
    check("an odd by_data is unnamed, not a crash; a whole-number id is text; no id is blank",
          odd == {"data": {"results_file": ["7"]}, "person": [], "unnamed": ["Q1", "Q2"], "answered": [""]}, odd)
    ids = [r["id"] for r in rows if r["id"] not in ("Q7",)]
    flat = [i for i in (*sum(g["data"].values(), []), *g["person"], *g["unnamed"], *g["answered"])]
    check("every question that is not dropped sits in exactly one group", sorted(flat) == sorted(ids), flat)


def test_readback() -> None:
    print("\n[3] readback()")
    rows = [row(id="Q1"), row(id="Q2", by_data="order_export"), row(id="Q3", by_data="ask_only"), row(id="Q4", answer="yes"),
            row(id="Q5", checked="aaa"), row(id="Q6", checked="old")]
    held = {"results_file": "aaa", "order_export": "bbb", "ask_only": "zzz"}
    got = Q.readback(rows, held)
    check("data held prompts the questions it can answer, once read ones not", [g["id"] for g in got] == ["Q1", "Q2", "Q6"], got)
    check("each carries its kind and the fingerprint", got[1] == {"id": "Q2", "by_data": "order_export", "held": "bbb"}, got)
    check("a new version of the data prompts again", [g["id"] for g in Q.readback(rows, {"results_file": "ccc"})] == ["Q1", "Q5", "Q6"])
    check("no data held, no prompt", Q.readback(rows, {}) == [])
    check("a blank fingerprint is no data", Q.readback(rows, {"results_file": " ", "order_export": ""}) == [])
    check("ask_only is never prompted, whatever is held under it", all(g["id"] != "Q3" for g in got))
    check("an answered question is never prompted", all(g["id"] != "Q4" for g in got))
    check("another key for the read record", [g["id"] for g in Q.readback([row(read="aaa")], held, key="read")] == [])
    check("recording the fingerprint read stops the prompt",
          Q.readback([{**rows[0], "checked": got[0]["held"]}], held) == [])
    check("not a mapping is skipped", Q.readback(["Q1", None], held) == [])
    check("no data held at all (None) prompts nothing", Q.readback(rows, None) == [])
    check("held that is not a mapping is refused", raises(Q.readback, rows, ["results_file"]) and raises(Q.readback, rows, "x"))
    check("a whole-number import id is a fingerprint, equal to its text",
          Q.readback([row(id="Q1")], {"results_file": 123}) == [{"id": "Q1", "by_data": "results_file", "held": "123"}]
          and Q.readback([row(id="Q1", checked=123)], {"results_file": "123"}) == []
          and Q.readback([row(id="Q1", checked="123")], {"results_file": 123}) == [])
    check("a bool or a list is no fingerprint", Q.readback([row()], {"results_file": True}) == []
          and Q.readback([row()], {"results_file": ["x"]}) == [])
    check("an odd by_data is skipped, not a crash", Q.readback([row(by_data=["results_file"])], held) == [])


if __name__ == "__main__":
    test_rules()
    test_problems()
    test_groups()
    test_readback()
    raise SystemExit(finish())
