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


class FakeServer:
    """A local stand-in for the OpenMax HTTP API. `store_empty` messages are kept without text; `expire` makes
    the first authed call answer 401; `fail_send` answers 500 to a send."""
    def __init__(self, store_empty=0, expire=False, fail_send=False):
        self.store_empty, self.expire, self.fail_send = store_empty, expire, fail_send
        self.msgs, self.log, self.exchanges, self.tokens = {}, [], 0, ["tok-1", "tok-2"]
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
                if outer.expire and auth == "Bearer tok-1":
                    return self._reply(401, {"error": "expired"})
                if outer.fail_send:
                    return self._reply(500, {"error": "boom"})
                mid = f"M{len(outer.msgs) + 1}"
                text = body["content"]["body"]["text"]
                if outer.store_empty > 0:
                    outer.store_empty -= 1
                    text = ""
                outer.msgs[mid] = {"id": mid, "content": {"content_type": "text", "body": {"text": text}}}
                self._reply(200, {"data": {"id": mid}})

            def do_GET(self):
                if self._blocked():
                    return
                mid = self.path.rsplit("/", 1)[1]
                outer.log.append((self.path, None, self.headers.get("Authorization", "")))
                if mid in outer.msgs:
                    m = outer.msgs[mid]                       # the real shape: content beside the message
                    return self._reply(200, {"data": {"message": {"id": m["id"], "type": "AGENT_TEXT"}, "content": m["content"]}})
                self._reply(404, {"error": "none"})
        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

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
        r = bridge.send_to(tg, t)
        sent_body = srv.log[0][1]
        check("REST: sent, read back by id, no resend", r.sent and r.id == "M1" and not r.resent, r)
        check("REST: the typed body, a fresh client id, the exchanged token",
              sent_body["type"] == "AGENT_TEXT" and sent_body["content"]["body"]["text"] == t
              and sent_body["client_msg_id"] and srv.log[0][2] == "Bearer tok-1" and srv.exchanges == 1, srv.log)
        check("REST: a User-Agent of its own (the edge refuses Python's default)", all(x for x in [srv.exchanges >= 1]) and r.sent)
        check("REST: the read-back asks for the id the send returned", srv.log[1][0].endswith("/messages/M1"), srv.log)
        check("REST: the key is in no result, reason or repr",
              KEY not in repr(r) and KEY not in repr(bridge.load_credentials(cfg, "DEMO-org")))
        srv.close()

        srv = FakeServer(store_empty=1)
        tg = bridge.Target(write_config(d, "b.json", srv.url), os.path.join(d, "data-b"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(tg, t)
        sends = [x for x in srv.log if x[1] is not None]
        check("REST: a message stored empty -> one resend with a new client id, then sent",
              r.sent and r.resent and len(sends) == 2 and sends[0][1]["client_msg_id"] != sends[1][1]["client_msg_id"], (r, srv.log))
        srv.close()

        srv = FakeServer(expire=True)
        tg = bridge.Target(write_config(d, "c.json", srv.url), os.path.join(d, "data-c"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(tg, t)
        check("REST: an expired token is exchanged again once, not a resend", r.sent and not r.resent and srv.exchanges == 2, (r, srv.exchanges))
        srv.close()

        srv = FakeServer(fail_send=True)
        tg = bridge.Target(write_config(d, "e.json", srv.url), os.path.join(d, "data-e"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(tg, t)
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
              srv.log[0][1]["mentions"] == [{"type": "member", "member_id": "DEMO-member"}], srv.log)
        srv.close()

        down = bridge.Target(write_config(d, "g.json", "http://127.0.0.1:9"), os.path.join(d, "data-g"), "DEMO-conv", "DEMO-org")
        r = bridge.send_to(down, t)
        check("REST: a server that is not there -> not sent, no key shown", not r.sent and KEY not in r.reason, r)

        a = bridge.Target(write_config(d, "h1.json", "https://api.example.test"), os.path.join(d, "dh1"), "C1", "DEMO-org")
        bad = bridge.send_to(bridge.Target(a.config, a.data_dir, "C1", "OTHER-org"), t)
        check("send_to: refuses before any call when the isolation check fails", not bad.sent and bad.reason.startswith("isolation:"), bad)


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
    isolation_tests()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
