"""serve.py with a skill pack's manifest: the pages it registers inside the shared frame, and the buttons on
them that the console relays to the skill pack's own gate. A real console on a free port, a stand-in skill
pack (tests/fake_pages.py: pages from files, the gate from tests/fake_skill_pack.py), driven the way a
browser drives it. Every refusal is paired with the click that is accepted.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import _t  # noqa: E402
import core  # noqa: E402
import frame  # noqa: E402
import i18n  # noqa: E402
from test_serve import Srv, fake_calls, flat, forms_of, gate_on, raw_ask, refused, run_serve, saved, say  # noqa: E402

PAGES = os.path.join(HERE, "fake_pages.py")
BUTTON = {"type": "button", "label": "Confirm delivery", "verb": ["queue", "approve"],
          "expect": {"verb": "queue approve"}, "effect": "Sends 3 clips to the client."}
SPACE = {"count": 3, "blocks": [{"type": "heading", "text": "Next batch"},
                                {"type": "card", "title": "Deliver 3 clips", "blocks": [{"type": "text", "text": "N7"}, BUTTON]}]}
MANIFEST = {"version": 1, "relay_verbs": [["queue", "approve"], ["facts", "confirm"]], "max_open": 14,
            "counts": ["console", "counts"],
            "pages": [{"name": "space", "title": {"en": "Space", "zh": "空间"}, "order": 20, "verb": ["console", "space"],
                       "blocking": True},
                      {"name": "evidence", "title": "Evidence", "order": 30, "verb": ["console", "evidence"]}]}


def write(root, name, doc):
    os.makedirs(os.path.join(root, "pages"), exist_ok=True)
    with open(os.path.join(root, "pages", name + ".json"), "w", encoding="utf-8") as f:
        json.dump(doc, f)


def srv_with(root, manifest=None, mode="ok", pages=None, args=(), env=None, **kw):
    """A console started with a manifest whose command is fake_pages.py; pages are files under `root`/pages."""
    man = {**(manifest or MANIFEST), "cmd": [sys.executable, PAGES]}
    path = os.path.join(root, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(man, f)
    for name, doc in (pages if pages is not None else {"space": SPACE, "evidence": {"blocks": []},
                                                        "counts": {"counts": {"space": 3, "evidence": 5}}}).items():
        write(root, name, doc)
    env = {"FAKE_PAGES_DIR": os.path.join(root, "pages"), "FAKE_PAGES_LOG": os.path.join(root, "pages.log"),
           "FAKE_SKILL_PACK_STATE": os.path.join(root, "fake-state.json"),
           "FAKE_SKILL_PACK_LOG": os.path.join(root, "fake.log"), "FAKE_SKILL_PACK_MODE": mode, **(env or {})}
    return Srv(root, "--manifest", path, *args, env=env, **kw)


def page_calls(root):
    try:
        with open(os.path.join(root, "pages.log")) as f:
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []


def tabs(markup):
    return [(m.group(1), m.group(2), flat(m.group(3))) for m in
            re.finditer(r'<a href="([^"]+)"( aria-current="page")?>(.*?)</a>', re.search(r'<nav class="tabs".*?</nav>', markup, re.S).group(0))]


def act_form(srv, markup=None):
    return next(f for f in forms_of(markup or srv.get("page-space").text) if f.action == "act")


def test_the_pages_a_manifest_declares_join_the_builtin_ones_in_one_top_bar_on_every_page():
    with _t.tmpdir() as root, srv_with(root) as srv:
        srv.agent(raw_ask("confirm", "c1"), raw_ask("confirm", "c2"))
        want = [("./", "Waiting", None), ("page-space", "Space", None), ("page-evidence", "Evidence", None), ("history", "History", None)]
        for path, here in (("", 0), ("page-space", 1), ("page-evidence", 2), ("history", 3)):
            got = tabs(srv.get(path).text)
            assert [g[0] for g in got] == [w[0] for w in want], (path, got)
            assert [i for i, g in enumerate(got) if g[1]] == [here], (path, got)
        got = tabs(srv.get("page-space").text)
        assert got[0][2] == f"{say('nav.waiting')} 5"           # 2 asks + the blocking page's 3
        assert got[1][2] == "Space 3" and got[2][2] == "Evidence 5" and got[3][2] == say("nav.history")
        zh = tabs(srv.get("?lang=zh").text)
        assert zh[1][2] == "空间 3" and zh[0][2] == f"{say('nav.waiting', 'zh')} 5", zh


def test_the_tab_numbers_come_from_one_cached_call_and_a_failing_counts_verb_costs_a_number_not_a_page():
    with _t.tmpdir() as root, srv_with(root) as srv:
        for _ in range(4):
            srv.get("")
            srv.get("history")
        calls = [c for c in page_calls(root) if c[:2] == ["console", "counts"]]
        assert len(calls) == 1, calls                                                      # kept for a few seconds
    with _t.tmpdir() as root, srv_with(root, pages={"space": SPACE, "evidence": {"blocks": []}, "counts": {"__exit": 1, "error": "down"}}) as srv:
        got = tabs(srv.get("").text)
        assert [g[2] for g in got] == [say("nav.waiting"), "Space", "Evidence", say("nav.history")]   # no numbers, still a page
        assert "counts verb failed: down" in srv.log()
    with _t.tmpdir() as root, srv_with(root, pages={"space": SPACE, "evidence": {"blocks": []}, "counts": {"counts": {
            "space": -1, "evidence": True, "nope": 4}}}) as srv:
        assert [g[2] for g in tabs(srv.get("").text)][1:3] == ["Space", "Evidence"]        # a number that is not a count is none


def test_a_page_is_drawn_from_the_skill_packs_document_and_every_other_path_stays_closed():
    with _t.tmpdir() as root, srv_with(root) as srv:
        r = srv.get("page-space")
        assert r.status == 200 and "no-store" in r.headers["Cache-Control"] and "script-src 'self'" in r.headers["Content-Security-Policy"]
        text = flat(r.text)
        assert "Space" in text and "Next batch" in text and "Deliver 3 clips" in text and "Sends 3 clips to the client." in text
        call = next(c for c in page_calls(root) if c[:2] == ["console", "space"])
        assert call == ["console", "space", "--lang=en", "--json"]
        srv.get("page-space?lang=zh")
        assert ["console", "space", "--lang=zh", "--json"] in page_calls(root)
        assert srv.get("page-nothing").status == 404 and srv.get("page-").status == 404 and srv.get("page-history").status == 404
        assert srv.get("page-space/").status == 404
        assert srv.post("page-space", {}).status == 405
        assert 'data-poll="poll"' in r.text                                              # it refreshes with the log like the others


def test_a_page_the_skill_pack_cannot_draw_is_a_page_that_says_so_and_the_console_goes_on():
    with _t.tmpdir() as root, srv_with(root, pages={"space": {"__exit": 1, "error": "The database is locked."},
                                                    "evidence": {"blocks": "not a list"},
                                                    "counts": {"counts": {}}}) as srv:
        r = srv.get("page-space")
        assert r.status == 200 and say("err.page_unavailable") in flat(r.text) and "The database is locked." in flat(r.text)
        assert len(tabs(r.text)) == 4
        e = srv.get("page-evidence")                                                       # a document, but not a page
        assert e.status == 200 and say("page.empty") in flat(e.text) and say("page.bad_blocks", n=1) in flat(e.text)
        os.unlink(os.path.join(root, "pages", "space.json"))                               # no output at all, exit 2
        assert say("err.page_unavailable") in flat(srv.get("page-space").text)
        assert srv.get("").status == 200 and "Traceback" not in srv.log()
        write(root, "space", SPACE)
        assert "Next batch" in flat(srv.get("page-space").text)                            # and it recovers on its own


def test_a_click_on_a_page_button_runs_the_skill_packs_gate_with_the_consoles_words_and_is_logged_signed():
    with _t.tmpdir() as root, srv_with(root, args=("--default-reason", "from the page"), env={"CONSOLE_SECRET": "g" * 32}) as srv:
        markup = srv.get("page-space").text
        form = act_form(srv, markup)
        assert sorted(n for n, *_ in form.items) == ["hash", "page", "token"]
        r = srv.submit(form, "page-space")
        saved(r)
        assert "Confirm delivery" in flat(r.text) and say("result.ok") in flat(r.text)
        calls = fake_calls(root)
        assert [c["run"] for c in calls] == [1, 2], calls
        assert calls[0]["argv"] == ["queue", "approve", "--reason=from the page", "--json"], calls[0]
        assert calls[1]["argv"][-3:] == ["--code=***", "--relay-user=web:alice", calls[1]["argv"][-1]], calls[1]
        assert all(c["stdin_devnull"] and not c["tty"] and not c["console_secret"] for c in calls)
        (ev,) = srv.events("action")
        assert ev["by"] == "web:alice" and ev["id"] == "space" and ev["label"] == "Confirm delivery"
        assert ev["verb"] == ["queue", "approve"] and ev["subject"] == form.value("hash") and ev["gate"]["ok"] is True
        assert core.verify(b"g" * 32, ev) is True
        assert core.verify(b"h" * 32, ev) is False
        assert srv.events("answer") == [] and srv.get("").status == 200                   # an action is not an answer: the fold goes on
        assert core.Store(srv.folder).state()["actions"][0]["seq"] == ev["seq"]


def test_a_forged_click_cannot_name_a_verb_or_a_payload_only_a_button_the_page_still_shows():
    with _t.tmpdir() as root, srv_with(root) as srv:
        form = act_form(srv)
        token = form.value("token")
        h = form.value("hash")
        extra = [("verb", "pay"), ("verb", "invoice"), ("expect", '{"x":1}'), ("value", "yes")]
        r = srv.post("act", [("page", "space"), ("hash", h)] + extra, token=token)
        saved(r)                                                                            # the extras are ignored
        assert [c["argv"][:2] for c in fake_calls(root) if c["run"] == 1] == [["queue", "approve"]]
        for fields, why in (([("page", "space"), ("hash", "0" * 32)], "a hash the page does not show"),
                            ([("page", "nothing"), ("hash", h)], "a page that is not declared"),
                            ([("page", "evidence"), ("hash", h)], "the hash of another page's button"),
                            ([("page", "space")], "no hash")):
            before = len(fake_calls(root))
            r = srv.post("act", fields, token=token)
            assert r.status in (400, 409) and "res bad" in r.text, (why, r.status, flat(r.text)[:200])
            assert len(fake_calls(root)) == before, why                                     # the skill pack was not called
        assert srv.post("act", [("page", "space"), ("hash", h)], token="wrong").status == 403
        assert srv.post("act", [("page", "space"), ("hash", h)], token=None).status == 403
        assert len(srv.events("action")) == 1


def test_a_page_that_changed_since_it_was_drawn_refuses_the_old_button_and_runs_the_new_one():
    with _t.tmpdir() as root, srv_with(root) as srv:
        old = act_form(srv)
        newer = json.loads(json.dumps(SPACE))
        newer["blocks"][1]["blocks"][1].update(verb=["queue", "approve", "batch5"],                          # another payload
                                               expect={"verb": "queue approve", "items": {"batch5": "yes"}})
        write(root, "space", newer)
        r = srv.submit(old, "page-space")
        assert r.status == 409 and say("err.changed") in flat(r.text), (r.status, flat(r.text)[:200])
        assert fake_calls(root) == [] and srv.events("action") == []
        saved(srv.submit(act_form(srv), "page-space"))                                      # the page as it is now
        assert len(srv.events("action")) == 1


def test_a_button_whose_verb_the_manifest_does_not_allow_is_a_sentence_and_a_forged_click_on_it_is_refused():
    pay = {**BUTTON, "label": "Pay", "verb": ["pay", "invoice"], "expect": {"verb": "pay invoice"}}
    with _t.tmpdir() as root, srv_with(root, pages={"space": {"blocks": [pay, BUTTON]}, "evidence": {"blocks": []},
                                                    "counts": {"counts": {}}}) as srv:
        markup = srv.get("page-space").text
        assert [f.value("hash") for f in forms_of(markup) if f.action == "act"] == [
            frame.button_hash("space", frame.clean({"blocks": [BUTTON]})["blocks"][0])]    # one form: the allowed one
        assert say("btn.norelay", label="Pay") in flat(markup)
        h = frame.button_hash("space", frame.clean({"blocks": [pay]})["blocks"][0])
        r = srv.post("act", [("page", "space"), ("hash", h)])
        refused(r, 403, "err.verb_not_allowed")
        assert fake_calls(root) == [] and srv.events("action") == []


def test_a_refusal_by_the_skill_pack_is_shown_in_its_words_and_leaves_no_action_in_the_log():
    with _t.tmpdir() as root, srv_with(root, mode="fail") as srv:
        r = srv.submit(act_form(srv), "page-space")
        assert r.status == 409 and "res bad" in r.text and say("err.gate_refused") in flat(r.text), flat(r.text)[:300]
        assert srv.events("action") == []
    keyed = {**BUTTON, "verb": ["queue", "approve", "batch"], "expect": {"verb": "queue approve", "items": {"batch": "yes"}}}
    with _t.tmpdir() as root, srv_with(root, mode="changed", pages={"space": {"blocks": [keyed]}, "evidence": {"blocks": []},
                                                                    "counts": {"counts": {}}}) as srv:      # it would write something else
        r = srv.submit(act_form(srv), "page-space")
        assert r.status == 409
        assert say("err.gate_changed") in flat(r.text) and [c["run"] for c in fake_calls(root)] == [1]


def test_the_manifest_alone_decides_which_gated_asks_the_console_can_answer():
    with _t.tmpdir() as root, srv_with(root) as srv:
        srv.agent(gate_on("ok1", ["facts", "confirm", "unit_cost"]), raw_ask("confirm", "plain"))
        page = srv.get("").text
        assert "gate.norelay" not in page and say("gate.norelay") not in flat(page)
        f = next(f for f in forms_of(page) if f.action == "answer" and ("id", "hidden", "ok1", False) in map(tuple, f.items))
        saved(srv.submit(f))
        assert srv.events("answer")[0]["gate"]["ok"] is True
        assert say("budget.line", open=1, max=14) in flat(srv.get("").text)      # ok1 was answered, "plain" waits
    with _t.tmpdir() as root, srv_with(root, manifest={**MANIFEST, "relay_verbs": [["queue", "approve"]]}) as srv:
        srv.agent(gate_on("no1", ["facts", "confirm", "unit_cost"], step="approve"))
        assert say("gate.norelay") in flat(srv.get("").text)                                 # drawn only as a decline


def test_the_open_ask_budget_on_the_waiting_page_is_the_manifests():
    with _t.tmpdir() as root, srv_with(root) as srv:
        srv.agent(*[raw_ask("confirm", f"c{i}") for i in range(3)])
        assert say("budget.line", open=3, max=14) in flat(srv.get("").text)
    with _t.tmpdir() as root, srv_with(root, manifest={"version": 1}) as srv:               # a manifest that declares nothing
        srv.agent(raw_ask("confirm", "c1"))
        assert say("budget.line", open=1, max=core.MAX_OPEN) in flat(srv.get("").text)
        assert [g[0] for g in tabs(srv.get("").text)] == ["./", "history"]


def test_the_manifest_is_read_at_start_from_the_flag_or_the_environment_and_a_bad_one_stops_the_console():
    with _t.tmpdir() as root:
        good = os.path.join(root, "m.json")
        with open(good, "w") as f:
            json.dump({"version": 1}, f)
        bad = os.path.join(root, "bad.json")
        with open(bad, "w") as f:
            json.dump({"version": 1, "pages": [{"name": "act", "title": "x", "verb": ["a"]}], "cmd": ["x"]}, f)
        dirflag = ["--dir", os.path.join(root, "d")]
        code, out, err = run_serve(*dirflag, "--manifest", bad)
        assert code == 2 and "taken by the console" in err and "bad.json" in err and out == "", (code, err)
        code, out, err = run_serve(*dirflag, "--manifest", os.path.join(root, "gone.json"))
        assert code == 2 and "cannot read the manifest" in err
        code, out, err = run_serve(*dirflag, env={"CONSOLE_MANIFEST": bad})
        assert code == 2 and "taken by the console" in err                                  # the environment is read too
        code, out, err = run_serve(*dirflag, "--manifest", good, "--relay-cmd", "x", "--relay-verbs", "a b")
        assert code == 2 and "exclude each other" in err
        assert not os.path.exists(os.path.join(root, "d"))                                  # a start that fails leaves nothing behind
        with Srv(root, "--manifest", good) as srv:
            assert srv.get("").status == 200
        with Srv(root, env={"CONSOLE_MANIFEST": good}) as srv:
            assert srv.get("").status == 200


if __name__ == "__main__":
    _t.main(globals())
