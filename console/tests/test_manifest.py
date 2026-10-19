"""manifest.py, and what the agent's side does with it: a skill pack declares its relay verbs and its
open-ask budget once, and `ask.py add` refuses (at registration, not at the owner's click) a gate whose verb
the console would not run. Each check has its refused input next to its accepted one, so none passes by
refusing everything.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import _t  # noqa: E402
import core  # noqa: E402
import manifest  # noqa: E402
from test_ask_cli import mk_ask, ok, put, refused  # noqa: E402

GOOD = {"version": 1, "cmd": ["uv", "run", "pack.py"], "relay_verbs": [["facts", "confirm"], ["queue", "approve"]],
        "max_open": 14, "counts": ["console", "counts"],
        "pages": [{"name": "space", "title": {"en": "Space", "zh": "空间"}, "order": 20, "verb": ["console", "page", "space"],
                   "blocking": True},
                  {"name": "evidence", "title": "Evidence", "verb": ["console", "page", "evidence"]}]}


def bad(doc, word):
    try:
        manifest.parse(doc)
    except manifest.ManifestError as e:
        assert word in str(e), (word, str(e))
        return
    raise AssertionError(f"accepted: {doc}")


def with_(**over):
    d = {**GOOD, **over}
    return {k: v for k, v in d.items() if v is not None}


def test_a_good_manifest_is_read_whole_with_its_defaults_filled():
    m = manifest.parse(GOOD)
    assert m["cmd"] == ["uv", "run", "pack.py"] and m["relay_verbs"] == [["facts", "confirm"], ["queue", "approve"]]
    assert m["max_open"] == 14 and m["counts"] == ["console", "counts"]
    p = m["pages"]
    assert p[0]["title"] == {"en": "Space", "zh": "空间"} and p[0]["blocking"] is True and p[0]["order"] == 20
    assert p[1]["title"] == {"en": "Evidence", "zh": "Evidence"} and p[1]["order"] == 100 and p[1]["blocking"] is False
    empty = manifest.parse({"version": 1})                               # a manifest may declare nothing at all
    assert empty == {"version": 1, "cmd": [], "relay_verbs": [], "max_open": core.MAX_OPEN, "counts": None, "pages": []}
    assert manifest.limit(None) == core.MAX_OPEN and manifest.limit(m) == 14


def test_the_manifest_refuses_what_it_cannot_read_and_says_which_key():
    bad("x", "JSON object")
    bad({}, "version")
    bad({"version": 2}, "version")
    bad({"version": True}, "version")
    bad(with_(colour="red"), "colour")                                   # a typo surfaces
    bad(with_(cmd="uv run"), "cmd")
    bad(with_(cmd=[]), "cmd")                                            # pages and verbs need a command to run
    bad(with_(relay_verbs=[["-x"]]), "relay_verbs[0]")                   # a verb word that is a flag
    bad(with_(relay_verbs=[[]]), "relay_verbs[0]")
    bad(with_(relay_verbs=[["a"] * 7]), "relay_verbs[0]")
    bad(with_(relay_verbs="facts confirm"), "relay_verbs")
    for n in (0, 101, True, "10", 1.5):
        bad(with_(max_open=n), "max_open")
    manifest.parse(with_(max_open=1))
    manifest.parse(with_(max_open=100))
    bad(with_(counts=["-c"]), "counts")
    bad(with_(pages=[]), "counts")                                       # a counts verb with no tab to number
    bad({"version": 1, "cmd": ["x"], "counts": ["a", "b"]}, "counts")


def test_a_page_must_be_named_once_and_not_after_the_consoles_own_pages():
    page = GOOD["pages"][0]
    for name in ("Space", "1space", "sp ace", "sp-ace", "", "x" * 25, None, 7, "épace"):
        bad(with_(pages=[{**page, "name": name}]), "name")
    for name in ("waiting", "history", "poll", "act", "answer", "static"):
        bad(with_(pages=[{**page, "name": name}]), "taken by the console")
    bad(with_(pages=[page, page]), "used twice")
    manifest.parse(with_(pages=[{**page, "name": "a1_b"}]))
    for key, val in (("title", ""), ("title", {"zh": "空间"}), ("title", {"en": "x", "fr": "y"}), ("title", "x" * 41),
                     ("order", -1), ("order", True), ("order", 1.5), ("blocking", "yes"), ("verb", None), ("verb", ["--x"]),
                     ("colour", 1)):
        bad(with_(pages=[{**page, key: val}]), "pages[0]")
    bad(with_(pages=[{**page, "name": f"p{i}"} for i in range(13)]), "at most 12")
    bad(with_(pages=["space"]), "pages[0]")


def test_the_tabs_are_in_order_with_the_builtin_pages_among_them():
    tabs = manifest.nav(manifest.parse(GOOD))
    assert [t["name"] for t in tabs] == ["waiting", "space", "evidence", "history"]      # 10, 20, 100, 1000
    assert tabs[0]["title"] is None and tabs[1]["blocking"] is True and tabs[2]["blocking"] is False
    first = manifest.parse(with_(pages=[{**GOOD["pages"][0], "order": 0}, {**GOOD["pages"][1], "order": 1000}]))
    assert [t["name"] for t in manifest.nav(first)] == ["space", "waiting", "evidence", "history"]   # a tie by name
    assert [t["name"] for t in manifest.nav(None)] == ["waiting", "history"]


def test_load_names_the_file_when_it_is_missing_not_json_or_wrong():
    with _t.tmpdir() as d:
        for path, word in ((os.path.join(d, "none.json"), "cannot read"), (put(d, "a.json", "{nope"), "not valid JSON"),
                           (put(d, "b.json", {"version": 3}), "version")):
            try:
                manifest.load(path)
            except manifest.ManifestError as e:
                assert path in str(e) and word in str(e), str(e)
            else:
                raise AssertionError(path)
        assert manifest.load(put(d, "ok.json", GOOD))["max_open"] == 14


def test_an_ask_whose_gate_verb_the_manifest_does_not_allow_is_refused_when_it_is_added():
    gate = lambda *v: {"verb": list(v), "expect": {"verb": " ".join(v[:2])}}          # noqa: E731
    with _t.tmpdir() as d:
        m = put(d, "m.json", GOOD)
        wrong = mk_ask("g1", "approve", gate=gate("pay", "invoice"))
        right = mk_ask("g2", "approve", gate=gate("queue", "approve", "n7"))              # a prefix match, word for word
        doc = refused("invalid_ask", "--manifest", m, "add", "-", d=d, stdin=json.dumps([wrong, right]))
        errs = doc["params"]["errors"]
        assert [(e["ask"], e["field"], e["code"]) for e in errs] == [("g1", "gate.verb", "not_allowed")], errs
        assert "pay invoice" in errs[0]["message"] and "facts confirm, queue approve" in errs[0]["message"]
        assert ok("list", "--status", "all", d=d)["asks"] == []                       # all or nothing: g2 was not posted either
        assert ok("--manifest", m, "add", "-", d=d, stdin=json.dumps(right))["posted"] == ["g2"]
        near = mk_ask("g3", "approve", gate=gate("queue", "appr"))                       # words, not characters
        refused("invalid_ask", "--manifest", m, "add", "-", d=d, stdin=json.dumps(near))
        refused("invalid_ask", "--manifest", m, "add", "-", d=d,
                stdin=json.dumps(mk_ask("g4", "approve", gate=gate("queue"))))           # a shorter verb than the prefix
        assert ok("add", "--dry-run", "-", d=d, stdin=json.dumps(wrong))["posted"] == ["g1"]   # no manifest, no check (as before)


def test_the_manifest_comes_from_the_flag_or_the_environment_and_a_bad_one_is_a_refusal_not_a_pass():
    wrong = mk_ask("g1", "approve", gate={"verb": ["pay", "invoice"], "expect": {"verb": "pay invoice"}})
    with _t.tmpdir() as d:
        m = put(d, "m.json", GOOD)
        refused("invalid_ask", "add", "--dry-run", "-", d=d, env={"CONSOLE_MANIFEST": m}, stdin=json.dumps(wrong))
        refused("bad_request", "--manifest", os.path.join(d, "gone.json"), "add", "-", d=d, stdin=json.dumps(wrong))
        refused("bad_request", "add", "-", d=d, env={"CONSOLE_MANIFEST": put(d, "bad.json", {"version": 9})},
                stdin=json.dumps(wrong))                                                  # never read as "no manifest"
        assert ok("--manifest", m, "schema")["max_open"] == 14 and ok("schema")["max_open"] == core.MAX_OPEN


def test_the_manifest_sets_the_open_ask_budget_and_the_flag_can_only_lower_it():
    asks = lambda n: json.dumps([mk_ask(f"a{i}") for i in range(n)])                      # noqa: E731
    with _t.tmpdir() as d:
        m = put(d, "m.json", GOOD)                                                        # max_open 14
        doc = ok("--manifest", m, "add", "-", d=d, stdin=asks(14))
        assert doc["budget"] == 14 and doc["open"] == 14
        over = refused("over_budget", "--manifest", m, "add", "-", d=d, stdin=json.dumps(mk_ask("fifteenth")))
        assert over["params"]["max"] == 14
    with _t.tmpdir() as d:
        m = put(d, "m.json", GOOD)
        assert ok("--manifest", m, "add", "--max-open", "50", "--dry-run", "-", d=d, stdin=asks(1))["budget"] == 14
        assert ok("--manifest", m, "add", "--max-open", "3", "--dry-run", "-", d=d, stdin=asks(1))["budget"] == 3
        refused("over_budget", "--manifest", m, "add", "--max-open", "3", "-", d=d, stdin=asks(4))
    with _t.tmpdir() as d:                                                                 # without one: ten, as it always was
        refused("over_budget", "add", "-", d=d, stdin=asks(core.MAX_OPEN + 1))


if __name__ == "__main__":
    _t.main(globals())
