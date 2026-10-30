#!/usr/bin/env python3
"""kit.bridge_hooks: every session gets the bridge's rules, and the reply reaches the session that asked.

Against a local fake server (kit/tests/test_bridge.py), with the pending file in a temp data dir:

  * pre-send: a message with no @name to a GROUP is refused (`no_mention`); an @name, a DM, an unknown
    conversation and a server that is down are let through; a conversation's kind is read once;
  * post-send: the sent id is written to the pending file whatever wraps it; none, nothing; twice, one row;
  * turn / session: what came after our message from the agent we asked, from a person, from a reply under
    ours or a mention is handed over ONCE, wrapped as untrusted with secrets removed; our own and a stranger's
    are not; a reply behind 300 unrelated messages is found; a reply after the request is overdue still comes;
    a session started later gets it; a second session that finds the lock held reads nothing;
  * a request past its final deadline is dropped; a read is not repeated inside POLL_EVERY;
  * stage 2: an @name that is no member (`unknown_mention`), the 11th awaited request in a conversation
    (`request_cap`), a reply handed only to the session that asked until it ends or goes quiet, an answer in
    several messages held until a 25-second lull and handed over together, marked read, stored without secrets;
  * the command line: JSON in, JSON out, exit 0 whatever fails; list, close, install-snippet.
"""

import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit import bridge, bridge_hooks as h  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402
from test_bridge import KEY, FakeServer, write_config  # noqa: E402

GROUP_TEXT = "@DEMO-agent please confirm the DEMO time zone"
h.QUIET_FOR = 0               # the quiet period has its own test; the rest read what is there at once


def setup(d, srv):
    env = {"CLAUDE_OPENMAX_CONFIG": write_config(d, "h.json", srv.url), "CLAUDE_OPENMAX_DATA_DIR": os.path.join(d, "data")}
    return env


def sent_event(msg_id, text=GROUP_TEXT, resp=None):
    return {"tool_name": h.SEND_TOOL, "tool_input": {"endpoint": "DEMO-conv", "content": text},
            "tool_response": resp if resp is not None else {"messageId": msg_id}}


def pre_tests():
    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        env = setup(d, srv)
        ev = lambda text, ep="DEMO-conv": {"tool_name": h.SEND_TOOL, "tool_input": {"endpoint": ep, "content": text}}  # noqa: E731
        out = h.pre_send(ev("hello there"), env)
        check("pre-send: a group message with no @name is refused with the no_mention words",
              out and out["hookSpecificOutput"]["permissionDecision"] == "deny"
              and "no_mention" in out["hookSpecificOutput"]["permissionDecisionReason"], out)
        check("pre-send: an @name goes through", h.pre_send(ev(GROUP_TEXT), env) is None)
        n = len(srv.log)
        check("pre-send: the conversation kind was read once and is remembered",
              h.pre_send(ev("hello again"), env) is not None and len([x for x in srv.log[n:] if "/messages" not in x[0]]) == 0, srv.log[n:])
        check("pre-send: an endpoint with a reply suffix is the same conversation",
              h.pre_send(ev("no mention", "DEMO-conv|reply:7"), env) is not None)
        srv.conv_type = "DM"
        env2 = setup(d, srv)
        env2["CLAUDE_OPENMAX_DATA_DIR"] = os.path.join(d, "data2")
        check("pre-send: a DM needs no mention", h.pre_send(ev("hello there"), env2) is None)
        srv.close()
        env3 = {"CLAUDE_OPENMAX_CONFIG": write_config(d, "dead.json", "http://127.0.0.1:9"), "CLAUDE_OPENMAX_DATA_DIR": os.path.join(d, "data3")}
        check("pre-send: a server that is down -> let through, never block", h.pre_send(ev("hello"), env3) is None)
        check("pre-send: no config at all -> let through",
              h.pre_send(ev("hello"), {"CLAUDE_OPENMAX_CONFIG": os.path.join(d, "none.json"), "CLAUDE_OPENMAX_DATA_DIR": os.path.join(d, "d4")}) is None)
        check("pre-send: not a send we understand -> let through", h.pre_send({"tool_input": {}}, env3) is None)


def post_tests():
    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        env = setup(d, srv)
        h.post_send(sent_event("111"), env, now=1000)
        h.post_send(sent_event("111"), env, now=1001)
        h.post_send(sent_event("", resp={"content": [{"type": "text", "text": '{"messageId":"222"}'}]}), env, now=1002)
        h.post_send(sent_event("", resp="done, no id here"), env, now=1003)
        rows = h.load(env)["requests"]
        check("post-send: ids are found in a dict and in text blocks, a repeat is one row, no id is none",
              [r["id"] for r in rows] == ["111", "222"], rows)
        check("post-send: nothing is read from the network", not srv.log and srv.exchanges == 0)
        check("post-send: the pending file is 0600", oct(os.stat(Path(env["CLAUDE_OPENMAX_DATA_DIR"]) / h.STATE_FILE).st_mode & 0o777) == "0o600")
        srv.close()


def deliver_tests():
    t0 = 1_000_000.0
    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        env = setup(d, srv)
        tg = bridge.Target(env["CLAUDE_OPENMAX_CONFIG"], env["CLAUDE_OPENMAX_DATA_DIR"], "DEMO-conv", "DEMO-org")
        sent = bridge.send_to(tg, GROUP_TEXT, mentions=["AGENT"])
        h.post_send(sent_event(sent.id), env, now=t0)
        check("turn: nothing new -> nothing handed over", h.deliver(env, now=t0 + 30) == "")

        srv.add("STRANGER", "something else entirely")
        srv.add("AGENT", "started, backing up. token glpat-ASFsO6V8AwzwdzLA7bniN286 was used")
        mid = srv.add("PERSON", "can you see the messages above?")
        srv.msgs[mid]["sender_type"] = "HUMAN"
        srv.add("THIRD", "FYI", parent_id=sent.id)
        srv.add("ME", "our own later message")
        out = h.deliver(env, now=t0 + 60)
        check("turn: the asked agent (no mention, no parent), a person and a reply under ours are handed over",
              "backing up" in out and "can you see" in out and "FYI" in out, out)
        check("turn: a stranger's message and our own are not", "something else entirely" not in out and "our own later" not in out, out)
        check("turn: wrapped as untrusted data, with the rule about requests", "untrusted" in out and "not instructions" in out, out)
        check("turn: the pasted token is removed from what is quoted", "glpat-" not in out and "[removed: secret]" in out, out)
        check("turn: the key is nowhere in it", KEY not in out)
        check("turn: each message is handed over once", h.deliver(env, now=t0 + 120) == "")

        reads = len(srv.log)
        srv.add("AGENT", "step 2 done")
        check("turn: a read is not repeated inside the poll interval", h.deliver(env, now=t0 + 125) == "" and len(srv.log) == reads)
        out = h.deliver(env, now=t0 + 200)
        check("turn: the next message comes at the next read, alone", "step 2 done" in out and "backing up" not in out, out)

        for i in range(300):
            srv.add("NOISE", f"unrelated {i}")
        srv.add("AGENT", "the real result")
        out = h.deliver(env, now=t0 + 400)
        check("turn: a reply behind 300 unrelated messages is found", "the real result" in out and "unrelated" not in out, out)

        srv.add("AGENT", "late news")
        out = h.deliver(env, now=t0 + h.DUE_AFTER + 5000)
        check("turn: a reply after the request is overdue still comes", "late news" in out, out)
        check("list: it shows overdue, and how many were delivered", "overdue" in h.awaiting(env, now=t0 + h.DUE_AFTER + 5000)[0], h.awaiting(env, now=t0 + h.DUE_AFTER + 5000))

        env_b = dict(env)                       # a session that starts later: same identity, same data dir
        srv.add("AGENT", "while you were away")
        check("session B: a reply that came after session A ended is handed over before its first turn",
              "while you were away" in h.deliver(env_b, now=t0 + h.DUE_AFTER + 6000, force=True))

        srv.add("AGENT", "contended")
        with h._lock(env, wait=True):
            check("two sessions: one that finds the lock held reads nothing", h.deliver(env_b, now=t0 + h.DUE_AFTER + 7000) == "")
        check("two sessions: the other gets it once the lock is free", "contended" in h.deliver(env_b, now=t0 + h.DUE_AFTER + 7100))

        check("a request past its final deadline is dropped", h.deliver(env, now=t0 + h.FINAL_AFTER + 10) == "" and h.load(env)["requests"] == [])
        srv.close()

        down = {"CLAUDE_OPENMAX_CONFIG": write_config(d, "down.json", "http://127.0.0.1:9"), "CLAUDE_OPENMAX_DATA_DIR": os.path.join(d, "dd")}
        h.post_send(sent_event("999"), down, now=t0)
        check("turn: a server that is down -> nothing, no error, the request stays", h.deliver(down, now=t0 + 60) == "" and len(h.load(down)["requests"]) == 1)


def stage2_tests():
    t0 = 2_000_000.0
    ev = lambda text: {"tool_name": h.SEND_TOOL, "tool_input": {"endpoint": "DEMO-conv", "content": text}}  # noqa: E731
    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        env = setup(d, srv)
        deny = lambda text, now=t0: (h.pre_send(ev(text), env, now=now) or {}).get("hookSpecificOutput", {}).get("permissionDecisionReason", "")  # noqa: E731
        check("pre-send: an @name that is no member is refused as unknown_mention", deny("@Nobody hi").startswith("unknown_mention"), deny("@Nobody hi"))
        check("pre-send: a member's name, any case, goes through", deny("@demo-agent hi") == "")
        check("pre-send: one good @ among strays goes through", deny("@DEMO-agent and @Nobody") == "")
        check("pre-send: @all goes through", deny("@all hi") == "")
        srv.members = []
        env_m = dict(env, CLAUDE_OPENMAX_DATA_DIR=os.path.join(d, "dm"))
        check("pre-send: a member list that cannot be read refuses nothing",
              h.pre_send(ev("@Nobody hi"), env_m, now=t0) is None)

        for i in range(h.REQUEST_CAP):
            h.post_send(sent_event(f"R{i}"), env, now=t0 + i)
        check("pre-send: the 11th awaited request in a conversation is refused as request_cap",
              deny("@DEMO-agent one more", now=t0 + 20).startswith("request_cap"), deny("@DEMO-agent one more", now=t0 + 20))
        h.close("R0", env)
        check("pre-send: closing one makes room", deny("@DEMO-agent one more", now=t0 + 20) == "")
        check("pre-send: the cap is per day: after the final deadline it is gone",
              deny("@DEMO-agent one more", now=t0 + h.FINAL_AFTER + 100) == "")
        srv.close()

    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        env = setup(d, srv)
        tg = bridge.Target(env["CLAUDE_OPENMAX_CONFIG"], env["CLAUDE_OPENMAX_DATA_DIR"], "DEMO-conv", "DEMO-org")
        sent = bridge.send_to(tg, GROUP_TEXT, mentions=["AGENT"])
        h.post_send(dict(sent_event(sent.id), session_id="A"), env, now=t0)
        srv.add("AGENT", "the answer")
        check("sessions: another live session is not handed A's reply", h.deliver(env, now=t0 + 60, session_id="B") == "")
        check("sessions: the session that asked is", "the answer" in h.deliver(env, now=t0 + 90, session_id="A"))
        srv.add("AGENT", "and more")
        check("sessions: B still gets nothing while A is alive", h.deliver(env, now=t0 + 150, session_id="B") == "")
        h.end_session({"session_id": "A"}, env)
        check("sessions: when A has ended, the next session gets it before its first turn",
              "and more" in h.deliver(env, now=t0 + 200, session_id="B", force=True))
        srv.add("AGENT", "later still")
        h.post_send(dict(sent_event("X9"), session_id="C"), env, now=t0 + 300)
        check("sessions: a session silent for SESSION_IDLE no longer owns its requests",
              "later still" in h.deliver(env, now=t0 + 300 + h.SESSION_IDLE + 100, session_id="B", force=True))
        srv.close()

    h.QUIET_FOR = 25
    try:
        with tempfile.TemporaryDirectory() as d:
            srv = FakeServer()
            env = setup(d, srv)
            tg = bridge.Target(env["CLAUDE_OPENMAX_CONFIG"], env["CLAUDE_OPENMAX_DATA_DIR"], "DEMO-conv", "DEMO-org")
            sent = bridge.send_to(tg, GROUP_TEXT, mentions=["AGENT"])
            h.post_send(sent_event(sent.id), env, now=t0)
            srv.add("AGENT", "part one, started")
            first = h.deliver(env, now=t0 + 20)
            srv.add("AGENT", "part two")
            srv.add("AGENT", "part three, done")
            second = h.deliver(env, now=t0 + 40)
            third = h.deliver(env, now=t0 + 60)
            out = h.deliver(env, now=t0 + 80)
            check("quiet period: nothing is handed over while the answer is still arriving", first == second == third == "", (first, second, third))
            check("quiet period: after the lull all three come together, once",
                  all(x in out for x in ("part one", "part two", "part three")) and out.count("--- seq") == 3, out)
            check("quiet period: nothing again afterwards", h.deliver(env, now=t0 + 120) == "")
            reads = [x for x in srv.log if x[0].endswith("/read")]
            check("mark-read: what was handed over is marked read up to its last message",
                  len(reads) == 1 and reads[0][1]["read_until_seq"] == 4, reads)
            check("quiet period: a held reply is kept in the file without a token",
                  "glpat-" not in json.dumps(h.load(env)))
            srv.add("AGENT", "late token glpat-ASFsO6V8AwzwdzLA7bniN286")
            h.deliver(env, now=t0 + 140)
            check("a message held for the lull is stored with its secret removed", "glpat-" not in json.dumps(h.load(env)), h.load(env))
            srv.close()
    finally:
        h.QUIET_FOR = 0


def cli_tests():
    def run(verb, event, env):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            rc = h.main([verb], stdin=io.StringIO(json.dumps(event)), stdout=out, env=env)
        finally:
            sys.stderr = old
        return rc, out.getvalue()

    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        env = setup(d, srv)
        rc, out = run("pre-send", {"tool_input": {"endpoint": "DEMO-conv", "content": "no mention"}}, env)
        check("cli: pre-send prints the refusal as JSON and exits 0", rc == 0 and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny", out)
        tg = bridge.Target(env["CLAUDE_OPENMAX_CONFIG"], env["CLAUDE_OPENMAX_DATA_DIR"], "DEMO-conv", "DEMO-org")
        sent = bridge.send_to(tg, GROUP_TEXT, mentions=["AGENT"])
        rc, out = run("post-send", sent_event(sent.id), env)
        check("cli: post-send prints nothing and exits 0", rc == 0 and out == "")
        srv.add("AGENT", "here you go")
        rc, out = run("turn", {"prompt": "next"}, env)
        ctx = json.loads(out)["hookSpecificOutput"]
        check("cli: turn hands the reply over as additionalContext for UserPromptSubmit",
              ctx["hookEventName"] == "UserPromptSubmit" and "here you go" in ctx["additionalContext"], out)
        srv.add("AGENT", "and this")
        rc, out = run("session", {}, env)
        ctx = json.loads(out)["hookSpecificOutput"]
        check("cli: session hands over what is new and lists what is still awaited",
              ctx["hookEventName"] == "SessionStart" and "and this" in ctx["additionalContext"] and "still awaited" in ctx["additionalContext"], out)
        rc, out = run("list", {}, env)
        check("cli: list names the request", sent.id in out, out)
        rc, out = run("close", {}, env)
        out2 = io.StringIO()
        h.main(["close", sent.id], stdout=out2, env=env)
        check("cli: close stops the wait", out2.getvalue().strip() == "closed" and h.load(env)["requests"] == [])
        broken = {"CLAUDE_OPENMAX_CONFIG": os.path.join(d, "missing.json"), "CLAUDE_OPENMAX_DATA_DIR": os.path.join(d, "x")}
        for verb in ("pre-send", "post-send", "turn", "session"):
            rc, out = run(verb, {"tool_input": {"endpoint": "C", "content": "x"}, "tool_response": {"messageId": "1"}}, broken)
            check(f"cli: {verb} with a broken setup exits 0 and does not refuse", rc == 0 and "deny" not in out)
        rc, out = run("pre-send", {}, env)
        check("cli: an empty event is no error", rc == 0)
        snip = json.loads(run("install-snippet", {}, env)[1])["hooks"]
        check("cli: install-snippet names the five hooks with this file's absolute path",
              set(snip) == {"PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionStart", "SessionEnd"}
              and snip["PreToolUse"][0]["matcher"] == h.SEND_TOOL and str(Path(h.__file__).resolve()) in snip["PreToolUse"][0]["hooks"][0]["command"], snip)
        srv.close()


def main() -> int:
    pre_tests()
    post_tests()
    deliver_tests()
    stage2_tests()
    cli_tests()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
