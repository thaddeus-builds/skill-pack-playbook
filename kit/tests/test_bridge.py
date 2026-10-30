#!/usr/bin/env python3
"""kit.bridge: a message is reported sent only when its read-back equals it.

  * equal read-back -> sent with the id; surrounding whitespace is ignored;
  * empty or different read-back -> one resend, then sent=True with resent=True;
    wrong twice -> not sent, two sends only;
  * no id returned -> not sent, no resend; read-back failing or None -> not sent, no resend;
  * a full-width ＠ or an empty text is refused before any send;
  * the prompts name only the tool for the step and the parsers read the strict answers;
  * a read-back reads the id the send returned, not the newest message;
  * REST (against a local fake server): a token is exchanged for the org, the typed body is sent, the
    read-back is by id; an empty stored message is resent once; an expired token is exchanged again once;
    a failed send is never resent; the api key is in no result, reason or repr;
  * wait_for_reply: a message under ours, one that mentions us, or one from an asked agent is a reply; our own,
    an older one, a stranger's unrelated one and a message with no link are not; a quiet group ends in
    "timeout" at the limit; reads that keep failing end in "unreadable"; the sent message is the anchor
    and "us" is its sender; next_round stops at three and wants a reason;
  * a group message with no mention is refused (`no_mention`), before any send; a DM is not; the headless path
    wants an ASCII @name in the text, REST wants member ids to mention; a mid-word @ (an address) is no mention;
  * an id that is not a member of the group is refused (`unknown_mention`), a member list that cannot be read
    refuses nothing, an @ is compared with display names that have spaces;
  * check_isolation names a missing, world-readable or key-less config, a wrong organization, a data dir
    shared by two configs, and one config used with two data dirs.
"""

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import bridge  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402


class Fake:
    """A bridge whose stored text per send is scripted; also holds a stranger's newer message."""
    def __init__(self, stored, send_ids=None):
        self.stored, self.sent, self.reads = list(stored), [], []
        self.ids = list(send_ids) if send_ids is not None else None
        self.db = {}

    def send(self, text):
        self.sent.append(text)
        if self.ids is not None:
            if not self.ids:
                return None
            i = self.ids.pop(0)
        else:
            i = f"DEMO-{len(self.sent)}"
        self.db[i] = self.stored.pop(0) if self.stored else text
        return i

    def read(self, i):
        self.reads.append(i)
        return self.db[i]


KEY = "DEMO-secret-key-not-real"
M = ["DEMO-member"]          # who a REST message mentions


class FakeServer:
    """A local stand-in for the OpenMax HTTP API. `store_empty` messages are kept without text; `expire` makes
    the first authed call answer 401; `fail_send` answers 500 to a send."""
    def __init__(self, store_empty=0, expire=False, fail_send=False):
        self.store_empty, self.expire, self.fail_send = store_empty, expire, fail_send
        self.msgs, self.log, self.exchanges, self.tokens = {}, [], 0, ["tok-1", "tok-2"]
        self.conv_type = "GROUP"
        self.members = [{"member_id": "ME", "display_name": "DEMO-me", "kind": "agent"},
                        {"member_id": "AGENT", "display_name": "DEMO-agent", "kind": "agent"},
                        {"member_id": "DEMO-member", "display_name": "Demo Member", "kind": "human"}]
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, obj):
                raw = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _blocked(self):
                if self.headers.get("User-Agent", "").startswith("Python-urllib"):
                    self._reply(403, {"error": "error code: 1010"})     # what the real edge does
                    return True

            def do_POST(self):
                if self._blocked():
                    return
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                auth = self.headers.get("Authorization", "")
                if self.path == "/auth/agent/token":
                    if auth != f"Bearer {KEY}" or body.get("org_id") != "DEMO-org":
                        return self._reply(401, {"error": "no"})
                    outer.exchanges += 1
                    return self._reply(200, {"data": {"access_token": outer.tokens[min(outer.exchanges, 2) - 1]}})
                outer.log.append((self.path, body, auth))
                if self.path.endswith("/read"):
                    return self._reply(200, {"data": {}})
                if outer.expire and auth == "Bearer tok-1":
                    return self._reply(401, {"error": "expired"})
                if outer.fail_send:
                    return self._reply(500, {"error": "boom"})
                mid = f"M{len(outer.msgs) + 1}"
                text = body["content"]["body"]["text"]
                if outer.store_empty > 0:
                    outer.store_empty -= 1
                    text = ""
                outer.msgs[mid] = {"id": mid, "seq": len(outer.msgs) + 1, "sender_id": "ME",
                                   "mentions": [{"mentioned_id": x["member_id"], "is_mention_all": False} for x in body.get("mentions", [])],
                                   "content": {"content_type": "text", "body": {"text": text}}}
                self._reply(200, {"data": {"id": mid}})

            def do_GET(self):
                if self._blocked():
                    return
                outer.log.append((self.path, None, self.headers.get("Authorization", "")))
                bare, _, query = self.path.partition("?")
                if bare.endswith("/members"):
                    return self._reply(200, {"data": outer.members})
                if not bare.endswith("/messages") and "/messages/" not in bare and "/conversations/" in bare:
                    return self._reply(200, {"data": {"id": bare.rsplit("/", 1)[1], "type": outer.conv_type}})
                if bare.endswith("/messages"):
                    q = dict(x.split("=") for x in query.split("&") if "=" in x)
                    rows = sorted(outer.msgs.values(), key=lambda m: m["seq"])
                    if "after_seq" in q:                          # ascending after a cursor, paged
                        rows = [m for m in rows if m["seq"] > int(q["after_seq"])][: int(q.get("limit", 100))]
                        return self._reply(200, {"data": rows})
                    return self._reply(200, {"data": rows[::-1]})  # newest first, as the real list is
                mid = self.path.rsplit("/", 1)[1]
                if mid in outer.msgs:
                    m = outer.msgs[mid]                       # the real shape: content beside the message
                    return self._reply(200, {"data": {"message": {"id": m["id"], "seq": m["seq"], "sender_id": m["sender_id"],
                                                                  "type": "AGENT_TEXT", "mentions": m.get("mentions", [])},
                                                      "content": m["content"]}})
                self._reply(404, {"error": "none"})
        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def add(self, sender, text, parent_id=None, mentions=()):
        """A message from someone else, as the real list shows it: content a plain string, mentions by id."""
        mid = f"M{len(self.msgs) + 1}"
        m = {"id": mid, "seq": len(self.msgs) + 1, "sender_id": sender, "content": text}
        if parent_id:
            m["parent_id"] = parent_id
        if mentions:
            m["mentions"] = [{"mentioned_id": x, "is_mention_all": False} for x in mentions]
        self.msgs[mid] = m
        return mid

    def close(self):
        self.httpd.shutdown()


def write_config(dirpath, name, url, key=KEY, org="DEMO-org", mode=0o600):
    path = os.path.join(dirpath, name)
    with open(path, "w") as fh:
        json.dump({"server": {"bff_url": url}, "agent": {"api_key": key}, "orgs": {org: {}}}, fh)
    os.chmod(path, mode)
    return path


def rest_tests(t: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        cfg = write_config(d, "a.json", srv.url)
        tg = bridge.Target(cfg, os.path.join(d, "data-a"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(tg, t, mentions=M)
        posts = [x for x in srv.log if x[1] is not None]
        sent_body = posts[0][1]
        check("REST: sent, read back by id, no resend", r.sent and r.id == "M1" and not r.resent, r)
        check("REST: the typed body, a fresh client id, the exchanged token",
              sent_body["type"] == "AGENT_TEXT" and sent_body["content"]["body"]["text"] == t
              and sent_body["client_msg_id"] and posts[0][2] == "Bearer tok-1" and srv.exchanges == 1, srv.log)
        check("REST: a User-Agent of its own (the edge refuses Python's default)", all(x for x in [srv.exchanges >= 1]) and r.sent)
        check("REST: the read-back asks for the id the send returned", [x for x in srv.log if "/messages/" in x[0]][-1][0].endswith("/messages/M1"), srv.log)
        check("REST: the key is in no result, reason or repr",
              KEY not in repr(r) and KEY not in repr(bridge.load_credentials(cfg, "DEMO-org")))
        srv.close()

        srv = FakeServer(store_empty=1)
        tg = bridge.Target(write_config(d, "b.json", srv.url), os.path.join(d, "data-b"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(tg, t, mentions=M)
        sends = [x for x in srv.log if x[1] is not None]
        check("REST: a message stored empty -> one resend with a new client id, then sent",
              r.sent and r.resent and len(sends) == 2 and sends[0][1]["client_msg_id"] != sends[1][1]["client_msg_id"], (r, srv.log))
        srv.close()

        srv = FakeServer(expire=True)
        tg = bridge.Target(write_config(d, "c.json", srv.url), os.path.join(d, "data-c"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(tg, t, mentions=M)
        check("REST: an expired token is exchanged again once, not a resend", r.sent and not r.resent and srv.exchanges == 2, (r, srv.exchanges))
        srv.close()

        srv = FakeServer(fail_send=True)
        tg = bridge.Target(write_config(d, "e.json", srv.url), os.path.join(d, "data-e"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(tg, t, mentions=M)
        sends = [x for x in srv.log if x[1] is not None]
        check("REST: a failed send is not sent, not resent, and says the status",
              not r.sent and r.reason.startswith("no_id_returned") and "HTTP 500" in r.reason and len(sends) == 1, (r, srv.log))
        check("REST: no key in a failure reason", KEY not in r.reason)
        srv.close()

        srv = FakeServer()
        cfg = write_config(d, "f.json", srv.url)
        send, read = bridge.rest_runners(bridge.load_credentials(cfg, "DEMO-org"), "DEMO-conv", mentions=["DEMO-member"])
        send("@DEMO-agent hi")
        check("REST: mentions go as member objects at the top level",
              [x for x in srv.log if x[1] is not None][0][1]["mentions"] == [{"type": "member", "member_id": "DEMO-member"}], srv.log)
        srv.close()

        down = bridge.Target(write_config(d, "g.json", "http://127.0.0.1:9"), os.path.join(d, "data-g"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(down, t, mentions=M)
        check("REST: a server that is not there -> not sent, no key shown", not r.sent and KEY not in r.reason, r)

        a = bridge.Target(write_config(d, "h1.json", "https://api.example.test"), os.path.join(d, "dh1"), "C1", "DEMO-org")
        bad = bridge.send_to(bridge.Target(a.config, a.data_dir, "C1", "OTHER-org"), t, mentions=M)
        check("send_to: refuses before any call when the isolation check fails", not bad.sent and bad.reason.startswith("isolation:"), bad)


def mention_tests(t: str) -> None:
    calls = []
    f = Fake([])
    def send(x):
        calls.append(x)
        return f.send(x)
    r = bridge.send_and_verify(send, f.read, "please confirm the DEMO time zone")
    check("a group message with no mention is refused before any send", not r.sent and r.reason == "no_mention" and not calls, r)
    for ok in ("@DEMO-agent hi", "hi @DEMO-agent", "@E-commercial Bot hi", "@\u5ba2\u670d hi"):
        f = Fake([ok])
        check(f"an ASCII @name counts as a mention: {ok[:14]!r}", bridge.send_and_verify(f.send, f.read, ok).sent)
    for no in ("mail me" + "@" + "demo", "a @ b", "email@"):
        f = Fake([no])
        r = bridge.send_and_verify(f.send, f.read, no)
        check(f"not a mention: {no!r}", r.reason == "no_mention", r)
    f = Fake(["hello"])
    check("a DM needs no mention", bridge.send_and_verify(f.send, f.read, "hello", dm=True).sent)
    f = Fake(["hello"])
    check("mention_ok=True (REST sent mention objects) lets a plain text through",
          bridge.send_and_verify(f.send, f.read, "hello", mention_ok=True).sent)
    f = Fake(["@DEMO-agent hi"])
    check("mention_ok=False refuses even a text with an @ (REST has no conversion)",
          bridge.send_and_verify(f.send, f.read, "@DEMO-agent hi", mention_ok=False).reason == "no_mention")
    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        cfg = write_config(d, "m.json", srv.url)
        tg = bridge.Target(cfg, os.path.join(d, "dm"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(tg, "@DEMO-agent " + t)
        check("send_to: a group message without member ids to mention is refused, nothing sent",
              not r.sent and r.reason == "no_mention" and not [x for x in srv.log if x[1] is not None] and srv.exchanges == 0, (r, srv.log))
        r = bridge.send_to(tg, t, mentions=M)
        check("send_to: with member ids it is sent and they ride as mention objects",
              r.sent and [x for x in srv.log if x[1] is not None][0][1]["mentions"] == [{"type": "member", "member_id": "DEMO-member"}], (r, srv.log))
        dmt = bridge.Target(cfg, os.path.join(d, "dm"), "DEMO-dm", "DEMO-org", dm=True)
        r = bridge.send_to(dmt, "hello, no mention here")
        check("send_to: a DM target is sent with no mention", r.sent, r)
        srv.close()

def unknown_tests(t: str) -> None:
    members = [{"member_id": "A1", "display_name": "E-commercial Bot"}, {"member_id": "H1", "display_name": "Lizzy Liu"}]
    for text, bad in (("@E-commercial Bot please check", False), ("@e-commercial bot please", False), ("@Lizzy Liu hi", False),
                      ("@Nobody hi", True), ("@E-commercial Bot and @Nobody", False), ("@E-commercial and so on", True), ("@all hi", False), ("@everyone hi", False),
                      ("no at here", False), ("@ alone", True)):
        check(f"unknown_mentions: {text!r} -> {bad}", bridge.unknown_mentions(text, members) is bad)
    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        cfg = write_config(d, "u.json", srv.url)
        tg = bridge.Target(cfg, os.path.join(d, "du"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(tg, t, mentions=["WRONG-id"])
        check("send_to: an id that is no member of the group is refused, nothing sent",
              not r.sent and r.reason == "unknown_mention: WRONG-id" and not [x for x in srv.log if x[1] is not None], (r, srv.log))
        srv.members = []
        check("send_to: a member list that cannot be read refuses nothing", bridge.send_to(tg, t, mentions=["WRONG-id"]).sent)
        srv.close()


def reply_tests(t: str) -> None:
    A = bridge.Anchor("S1", 10, "ME")
    ok = lambda **k: {"seq": 11, "sender_id": "AGENT", **k}      # noqa: E731

    for name, m, want in (
        ("under our message", ok(id="a", parent_id="S1", content="x"), True),
        ("mentions us", ok(id="a", mentions=[{"mentioned_id": "ME"}], content="x"), True),
        ("our own", ok(id="a", sender_id="ME", parent_id="S1"), False),
        ("older than ours", ok(id="a", seq=9, parent_id="S1"), False),
        ("a stranger's, unrelated", ok(id="a", content="x", mentions=[{"mentioned_id": "SOMEONE"}]), False),
        ("under another message", ok(id="a", parent_id="S0"), False),
    ):
        w = bridge.wait_for_reply(lambda m=m: [m], A, timeout=0, poll=1)
        check(f"reply? {name} -> {want}", (w.state == "replied") == want, w)

    w = bridge.wait_for_reply(lambda: [ok(id="a", content="no link")], A, from_ids=["AGENT"], timeout=0)
    check("reply? an asked agent's message with no mention or parent counts", w.state == "replied", w)

    msgs = [ok(id="b", seq=13, parent_id="S1", content={"body": {"text": "second"}}), ok(id="a", parent_id="S1", content="first")]
    w = bridge.wait_for_reply(lambda: msgs, A, timeout=0)
    check("replies come oldest first, text from a string or a typed body",
          [r.text for r in w.replies] == ["first", "second"] and w.replies[0].seq == 11, w)

    clock = [0.0]
    sleeps = []
    def sleep(n):
        sleeps.append(n)
        clock[0] += n
    polls = []
    def fetch():
        polls.append(clock[0])
        return [ok(id="a", parent_id="S1", content="late")] if len(polls) == 3 else []
    w = bridge.wait_for_reply(fetch, A, timeout=100, poll=10, sleep=sleep, clock=lambda: clock[0])
    check("waits and polls until a reply comes", w.state == "replied" and sleeps == [10, 10], (w, sleeps))

    clock[0], sleeps[:] = 0.0, []
    w = bridge.wait_for_reply(lambda: [], A, timeout=25, poll=10, sleep=sleep, clock=lambda: clock[0])
    check("a quiet group -> timeout at the limit, never past it", w.state == "timeout" and sum(sleeps) <= 25, (w, sleeps))

    def down():
        raise OSError("net")
    w = bridge.wait_for_reply(down, A, timeout=100, poll=0, sleep=lambda n: None)
    check("reads that keep failing -> unreadable, with the kind and no more", w.state == "unreadable" and w.reason == "OSError", w)
    flaky = iter([OSError("x"), [ok(id="a", parent_id="S1", content="back")]])
    def once():
        v = next(flaky)
        if isinstance(v, Exception):
            raise v
        return v
    check("one failed read is tried again", bridge.wait_for_reply(once, A, timeout=100, poll=0, sleep=lambda n: None).state == "replied")

    check("next_round: the second request is allowed with a reason", bridge.next_round(1, "the amounts are missing") == bridge.Round(True, 2))
    check("next_round: the fourth is refused", bridge.next_round(3, "still missing").reason == "round_limit")
    check("next_round: no reason, no round", bridge.next_round(1, "  ").reason == "no_reason" and not bridge.next_round(1, "").allowed)

    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        cfg = write_config(d, "w.json", srv.url)
        tg = bridge.Target(cfg, os.path.join(d, "dw"), "DEMO-conv", "DEMO-org")
        sent = bridge.send_to(tg, t, mentions=M)
        srv.add("OTHER", "not for us")
        srv.add("AGENT", "here are the numbers", mentions=["ME"])
        w = bridge.wait_for_reply_to(tg, sent.id, timeout=0)
        check("REST: the anchor is the sent message, we are its sender, the reply is found and the stranger's is not",
              w.state == "replied" and [r.text for r in w.replies] == ["here are the numbers"], w)
        check("REST: the key is in no wait result", KEY not in repr(w))
        w = bridge.wait_for_reply_to(tg, "NOPE", timeout=0)
        check("REST: a sent id that cannot be read -> unreadable, says anchor", w.state == "unreadable" and w.reason.startswith("anchor"), w)
        srv.close()
        bad = bridge.wait_for_reply_to(bridge.Target(os.path.join(d, "none.json"), "x", "C", "DEMO-org"), "S", timeout=0)
        check("REST: isolation is checked before any call", bad.state == "unreadable" and bad.reason.startswith("isolation"), bad)


def isolation_tests() -> None:
    with tempfile.TemporaryDirectory() as d:
        a = write_config(d, "a.json", "https://api.example.test")
        b = write_config(d, "b.json", "https://api.example.test")
        da, db = os.path.join(d, "da"), os.path.join(d, "db")
        ok = [bridge.Target(a, da, "C1", "DEMO-org"), bridge.Target(b, db, "C2", "DEMO-org")]
        check("isolation: two configs, two data dirs -> no problem", bridge.check_isolation(ok) == [], bridge.check_isolation(ok))
        two_convs = [bridge.Target(a, da, "C1", "DEMO-org"), bridge.Target(a, da, "C2", "DEMO-org")]
        check("isolation: one config, two conversations, one data dir -> no problem", bridge.check_isolation(two_convs) == [])
        shared = [bridge.Target(a, da, "C1", "DEMO-org"), bridge.Target(b, da, "C2", "DEMO-org")]
        check("isolation: a data dir shared by two configs", any(p.startswith("data_dir_shared") for p in bridge.check_isolation(shared)))
        split = [bridge.Target(a, da, "C1", "DEMO-org"), bridge.Target(a, db, "C2", "DEMO-org")]
        check("isolation: one config with two data dirs", any(p.startswith("data_dir_differs") for p in bridge.check_isolation(split)))
        check("isolation: a missing config", any(p.startswith("config_missing") for p in
              bridge.check_isolation([bridge.Target(os.path.join(d, "nope.json"), da, "C", "DEMO-org")])))
        loose = write_config(d, "loose.json", "https://api.example.test", mode=0o644)
        check("isolation: a world-readable config", any(p.startswith("config_mode") for p in
              bridge.check_isolation([bridge.Target(loose, da, "C", "DEMO-org")])))
        nokey = write_config(d, "nokey.json", "https://api.example.test", key="")
        check("isolation: a config with no key", any(p.startswith("no_api_key") for p in
              bridge.check_isolation([bridge.Target(nokey, da, "C", "DEMO-org")])))
        check("isolation: an organization the config does not hold", any(p.startswith("org_not_in_config") for p in
              bridge.check_isolation([bridge.Target(a, da, "C", "OTHER-org")])))
        check("isolation: no data dir named", any(p.startswith("no_data_dir") for p in
              bridge.check_isolation([bridge.Target(a, "", "C", "DEMO-org")])))
        check("isolation: no problem line shows the key", all(KEY not in p for p in bridge.check_isolation(shared + split)))


def main() -> int:
    t = "@DEMO-support please confirm the DEMO account time zone"
    f = Fake([t])
    r = bridge.send_and_verify(f.send, f.read, t)
    check("equal read-back -> sent", r.sent and r.id == "DEMO-1" and not r.resent and len(f.sent) == 1, r)
    f = Fake([t + "\n"])
    check("whitespace around is ignored", bridge.send_and_verify(f.send, f.read, t).sent)

    f = Fake(["", t])
    r = bridge.send_and_verify(f.send, f.read, t)
    check("an empty stored message -> one resend, then sent and said resent",
          r.sent and r.resent and r.id == "DEMO-2" and len(f.sent) == 2, r)
    f = Fake(["other", "other"])
    r = bridge.send_and_verify(f.send, f.read, t)
    check("wrong twice -> not sent, two sends only",
          not r.sent and r.reason == "read_back_differs" and len(f.sent) == 2, r)
    f = Fake(["", ""])
    check("empty twice -> not sent", not bridge.send_and_verify(f.send, f.read, t).sent)

    f = Fake([t], send_ids=[])
    r = bridge.send_and_verify(f.send, f.read, t)
    check("no id returned -> not sent, not resent", not r.sent and r.reason == "no_id_returned" and len(f.sent) == 1, r)

    def boom(i):
        raise TimeoutError("bridge")
    f = Fake([t])
    r = bridge.send_and_verify(f.send, boom, t)
    check("a read-back that fails -> not sent and NOT resent", not r.sent and r.reason == "read_back_failed" and len(f.sent) == 1, r)
    r = bridge.send_and_verify(f.send, lambda i: None, t)
    check("a read-back of None -> not sent and not resent", not r.sent and len(f.sent) == 2 and r.reason == "read_back_failed", r)

    for bad, why in (("＠DEMO-support hi", "full_width_at"), ("   ", "empty_text"), ("", "empty_text")):
        f = Fake([bad])
        r = bridge.send_and_verify(f.send, f.read, bad)
        check(f"refused before sending: {why}", not r.sent and r.reason == why and not f.sent, r)

    f = Fake([t])
    bridge.send_and_verify(f.send, f.read, t)
    check("the read-back reads the id the send returned", f.reads == ["DEMO-1"], f.reads)

    check("send prompt: ASCII @, the conversation, the text",
          "DEMO-conv" in bridge.send_prompt("DEMO-conv", t) and t in bridge.send_prompt("DEMO-conv", t))
    check("parse_id takes the last id line", bridge.parse_id("working\nid: A1\nid: B2") == "B2")
    check("parse_id: none -> None", bridge.parse_id("sent it") is None and bridge.parse_id("id:  ") is None)
    check("parse_text: after the text line, many lines kept",
          bridge.parse_text("id: B2\ntext:\nline one\nline two") == "line one\nline two")
    check("parse_text: no text line -> None", bridge.parse_text("id: B2") is None)

    calls = []

    def run(tool, prompt):
        calls.append(tool)
        return "id: X1" if tool == "comm_send" else "id: X1\ntext:\n" + t
    s, rd = bridge.runners(run, "DEMO-conv")
    r = bridge.send_and_verify(s, rd, t)
    check("runners: send with comm_send only, read with comm only",
          r.sent and calls == ["comm_send", "comm"], (r, calls))
    rest_tests(t)
    mention_tests(t)
    unknown_tests(t)
    reply_tests(t)
    isolation_tests()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
