#!/usr/bin/env python3
"""kit/bridge_cli.py: the bridge over REST as a command line, against the local fake server of test_bridge.py.

  * members lists names, ids and kinds; the pack's targets file names the conversation, nothing else is needed;
  * send needs a mention in a group (`no_mention`, exit 4, nothing stored); --to is resolved through the member
    list by display name or id, an unknown name is `unknown_mention` (exit 4); a direct message needs none;
  * the text comes from a file or stdin and arrives unchanged, a backtick, a quote and a dollar sign included
    (the case that a shell turned into "only run , do not add --publish"); it cannot be given as an argument;
  * --wait returns the agent's reply (exit 0, printed as untrusted data, secrets removed); no reply in time is
    exit 3 with the sent id; `wait` and `read` pick up later;
  * the hook's request cap applies: the 11th awaited request in a conversation is refused with exit 4, nothing sent;
  * a missing or loose config is refused before any call (`isolation`, exit 4), a server that is down is exit 5,
    no targets file or no text file is exit 2; no output holds the api key;
  * `status` says {delivered, seen_by, replies} for a sent message: the members who put a reaction on it (our own
    left out), found however much was said since; `wait` and `send --wait` carry the same `seen_by`, so a timeout says
    whether anyone looked; a message that is not there is exit 5;
  * `watch` prints one line per new message from anyone but us, keeps the last seq in a state file, pages past 100
    messages, starts after the newest when it has no cursor, says so when it does not know who we are, warns once
    after 10 failed reads in a row (and when they work again) and names a refused token at once;
  * a reply that is a file lists its attachments in read and wait, and `download` saves it unchanged with its
    sha256 (exit 5 for a message that is not there or has no file);
  * it runs as a script (the `kit` path is found from the file) and as `main(argv, urlopen=)`.
"""

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from kit import bridge_cli, bridge_hooks  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402
from test_bridge import KEY, FakeServer, write_config  # noqa: E402

TEXT = "please run `date` and \"echo hi\" with $HOME, do not add --publish\nsecond line"


def run(argv, stdin="", **kw):
    out, err = io.StringIO(), io.StringIO()
    code = bridge_cli.main(argv, stdin=io.StringIO(stdin), stdout=out, stderr=err, **kw)
    return code, out.getvalue(), err.getvalue()


def setup(d, srv, dm=False, name="T", file="targets.json"):
    cfg = write_config(d, "c.json", srv.url)
    tf = os.path.join(d, file)
    with open(tf, "w") as fh:
        json.dump({name: {"config": cfg, "data_dir": os.path.join(d, "data"), "org_id": "DEMO-org",
                          "conversation_id": "DEMO-conv", "dm": dm}}, fh)
    txt = os.path.join(d, "msg.txt")
    Path(txt).write_text(TEXT, encoding="utf-8")
    return tf, txt


def sender_stored(srv):
    return [m["content"]["body"]["text"] for m in srv.msgs.values() if m["sender_id"] == "ME"]


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        srv = FakeServer()
        tf, txt = setup(d, srv)
        base = ["--targets", tf]
        outputs = []

        code, out, err = run(["members", "T", *base])
        outputs += [out, err]
        check("members: exit 0, one line per member with name, id and kind",
              code == 0 and "DEMO-agent\tAGENT\tagent" in out and "Demo Member\tDEMO-member\thuman" in out, (code, out, err))
        code, out, _ = run(["members", "T", *base, "--json"])
        doc = json.loads(out)
        check("members --json: one document", code == 0 and doc["ok"] is True and len(doc["members"]) == 3, doc)

        code, out, err = run(["send", "T", *base, "--file", txt])
        outputs += [out, err]
        check("send to a group with no --to: no_mention, exit 4, nothing stored",
              code == 4 and "no_mention" in err and not srv.msgs, (code, err, srv.msgs))
        code, out, err = run(["send", "T", *base, "--file", txt, "--to", "Nobody"])
        check("an unknown --to: unknown_mention, exit 4, nothing stored",
              code == 4 and "unknown_mention" in err and not srv.msgs, (code, err))

        code, out, err = run(["send", "T", *base, "--file", txt, "--to", "demo-AGENT"])
        outputs += [out, err]
        check("send --to a display name (case ignored): sent, exit 0, the id printed",
              code == 0 and out.startswith("sent M1"), (code, out, err))
        check("the text arrives unchanged: backtick, quotes, dollar sign, two lines", sender_stored(srv) == [TEXT], sender_stored(srv))
        check("the agent is mentioned by its member id", srv.msgs["M1"]["mentions"][0]["mentioned_id"] == "AGENT", srv.msgs["M1"])

        code, out, _ = run(["send", "T", *base, "--file", "-", "--to", "AGENT", "--json"], stdin=TEXT + "!")
        doc = json.loads(out)
        check("the text from stdin and --to a member id; --json says sent", code == 0 and doc["sent"] and doc["id"] == "M2"
              and sender_stored(srv)[-1] == TEXT + "!", (code, doc))
        code, _, err = run(["send", "T", *base, "--to", "AGENT", "hello"])
        check("the text cannot be given as an argument: usage, exit 2", code == 2 and len(srv.msgs) == 2, (code, err))
        code, _, err = run(["send", "T", *base, "--file", os.path.join(d, "none.txt"), "--to", "AGENT"])
        check("a text file that is not there: exit 2", code == 2 and len(srv.msgs) == 2, (code, err))

        # --wait: the reply arrives while the command sleeps
        clock = [0.0]

        def sleep(n):
            clock[0] += n
            if not srv.late:
                srv.late.append(srv.add("AGENT", "numbers: 42 and glpat-AAAAAAAAAAAAAAAAAAAAAA"))
        srv.late = []
        code, out, err = run(["send", "T", *base, "--file", txt, "--to", "AGENT", "--wait", "100", "--poll", "10"],
                             sleep=sleep, clock=lambda: clock[0])
        outputs += [out, err]
        check("send --wait: the reply is printed, exit 0", code == 0 and "numbers: 42" in out and "sent M" in out, (code, out, err))
        check("the reply is marked untrusted and a token shape is removed",
              "untrusted data" in out and "from DEMO-agent" in out and "[removed: secret]" in out and "glpat-" not in out, out)

        code, out, _ = run(["send", "T", *base, "--file", txt, "--to", "AGENT", "--wait", "0", "--json"])
        doc = json.loads(out)
        sent_id = doc["id"]
        check("send --wait: no reply in time is exit 3 with the sent id (and ok: the message is sent)",
              code == 3 and doc["wait"]["state"] == "timeout" and doc["ok"] is True and sent_id, (code, doc))
        srv.add("AGENT", "late answer")
        code, out, _ = run(["wait", "T", sent_id, *base, "--from", "DEMO-agent", "--wait", "0"])
        check("wait picks up the late reply later, exit 0", code == 0 and "late answer" in out, (code, out))
        code, out, _ = run(["wait", "T", sent_id, *base, "--from", "Nobody", "--wait", "0"])
        check("wait --from an unknown name: exit 4", code == 4, (code, out))

        code, out, _ = run(["read", "T", *base, "--after-seq", "0", "--json"])
        doc = json.loads(out)
        seqs = [r["seq"] for r in doc["replies"]]
        check("read: the messages after a seq, oldest first, with the sender's name, untrusted",
              code == 0 and seqs == sorted(seqs) and len(seqs) == len(srv.msgs) and doc["untrusted"] is True
              and doc["next_after_seq"] == seqs[-1] and doc["replies"][0]["from"] == "DEMO-me", doc)
        check("read: a token shape in a message is removed", all("glpat-" not in r["text"] for r in doc["replies"]))
        code, out, _ = run(["read", "T", *base, "--after-seq", str(seqs[-1])])
        check("read: nothing newer", code == 0 and out.startswith("nothing new"), out)
        code, out, _ = run(["read", "T", *base, "--limit", "2"])
        check("read with no cursor: the last messages, oldest first",
              code == 0 and out.index(f"seq {seqs[-2]},") < out.index(f"seq {seqs[-1]},"), out)

        # a reply that is a file (issue #368): listed by read, saved by download
        raw = b"day,spend\r\n2026-10-01,10.50\r\n`x` \xff\xfe\r\n"
        fid = srv.add("AGENT", None, files={"report.csv": raw}, mentions=["ME"])
        code, out, _ = run(["read", "T", *base, "--after-seq", str(seqs[-1]), "--json"])
        doc = json.loads(out)
        check("read: a file reply lists its attachment (file name, artifact id) and has no text",
              code == 0 and doc["replies"][0]["text"] == "" and doc["replies"][0]["attachments"]
              == [{"file_name": "report.csv", "artifact_id": f"ART-{fid}-0"}], doc)
        code, out, _ = run(["read", "T", *base, "--after-seq", str(seqs[-1])])
        check("read: shown as an attached file to read, not as an empty message", "(attached file: report.csv)" in out and "(empty)" not in out, out)
        saved = os.path.join(d, "files")
        code, out, err = run(["download", "T", fid, *base, "--dir", saved, "--json"])
        doc = json.loads(out)
        got = doc["files"][0] if code == 0 else {}
        check("download: the file is saved exactly as stored, with its path, size and sha256, exit 0",
              code == 0 and open(got["path"], "rb").read() == raw and got["size"] == len(raw)
              and got["sha256"] == hashlib.sha256(raw).hexdigest() and os.path.dirname(got["path"]) == saved
              and doc["untrusted"] is True, (code, doc, err))
        code, out, _ = run(["download", "T", fid, *base, "--dir", saved])
        check("download: the text form says where, and that a file is data to read and never to run",
              code == 0 and "saved " in out and "never run them" in out, out)
        code, _, err = run(["download", "T", "M1", *base, "--dir", saved])
        check("download: a message with no file is exit 5, message_not_found", code == 5 and "message_not_found" in err, (code, err))
        code, _, err = run(["download", "T", "M999", *base, "--dir", saved])
        check("download: a message that is not there is exit 5", code == 5, (code, err))
        outputs.append(err)

        # the request cap, from the pending file the hooks keep
        env = {"CLAUDE_OPENMAX_DATA_DIR": os.path.join(d, "data")}
        now = time.time()
        rec = lambda i, conv="DEMO-conv": {"id": f"R{i}", "conversation_id": conv, "final": now + 3600}  # noqa: E731
        bridge_hooks.save({"requests": [rec(i) for i in range(bridge_hooks.REQUEST_CAP - 1)]}, env)
        before = len(srv.msgs)
        code, _, err = run(["send", "T", *base, "--file", txt, "--to", "AGENT"])
        check("one request below the cap: sent", code == 0 and len(srv.msgs) == before + 1, (code, err))
        bridge_hooks.save({"requests": [rec(i) for i in range(bridge_hooks.REQUEST_CAP)]}, env)
        code, _, err = run(["send", "T", *base, "--file", txt, "--to", "AGENT"])
        check("the 11th awaited request in a conversation: request_cap, exit 4, nothing sent",
              code == 4 and "request_cap" in err and len(srv.msgs) == before + 1, (code, err))
        bridge_hooks.save({"requests": [rec(i, "OTHER") for i in range(bridge_hooks.REQUEST_CAP)]}, env)
        code, _, err = run(["send", "T", *base, "--file", txt, "--to", "AGENT"])
        check("requests awaited in another conversation do not count", code == 0, (code, err))

        # isolation, usage, a server that is down
        os.chmod(os.path.join(d, "c.json"), 0o644)
        code, _, err = run(["members", "T", *base])
        check("a world-readable config: isolation, exit 4, before any call", code == 4 and err.startswith("isolation"), (code, err))
        os.chmod(os.path.join(d, "c.json"), 0o600)
        code, _, err = run(["members", "T"], env={})
        check("no targets file given: exit 2", code == 2 and "BRIDGE_TARGETS" in err, (code, err))
        code, _, err = run(["members", "T"], env={"BRIDGE_TARGETS": tf})
        check("the targets file from BRIDGE_TARGETS", code == 0, (code, err))
        code, _, err = run(["members", "Other", *base])
        check("a target not in the file: exit 2", code == 2 and "'Other'" in err, (code, err))

        # a direct message needs no --to
        dtf, _ = setup(d, srv, dm=True, name="D", file="dm-targets.json")
        code, out, err = run(["send", "D", "--targets", dtf, "--file", txt])
        check("a direct-message target needs no --to", code == 0 and out.startswith("sent"), (code, out, err))

        # as a script: the kit path is found from the file; the text from stdin reaches the server unchanged
        n = len(srv.msgs)
        p = subprocess.run([sys.executable, str(ROOT / "kit" / "bridge_cli.py"), "send", "T", *base, "--file", "-", "--to", "AGENT"],
                           input=TEXT, capture_output=True, text=True, cwd=d, env={**os.environ, "PYTHONPATH": ""})
        check("run as a script: sent, the backtick text unchanged", p.returncode == 0 and len(srv.msgs) == n + 1
              and sender_stored(srv)[-1] == TEXT, (p.returncode, p.stderr))
        check("the file declares itself a PEP 723 script", (ROOT / "kit" / "bridge_cli.py").read_text().split("\n")[1:5]
              == ["# /// script", '# requires-python = ">=3.11"', "# dependencies = []", "# ///"])

        check("no output of any verb holds the api key", all(KEY not in o for o in outputs) and KEY not in p.stdout + p.stderr)

        # a read that fails in transit is asked again; a send that was posted but could not be read back says so and is never repeated
        import urllib.error
        import urllib.request
        from kit import bridge as bridge_mod
        bridge_mod.READ_BACKOFF = 0.0
        real = urllib.request.urlopen
        dropped = {"get": 0, "post": 0}

        def drop_first_get(req, timeout=None):
            if req.get_method() == "GET" and dropped["get"] < 1:
                dropped["get"] += 1
                raise urllib.error.URLError(ConnectionResetError("dropped"))
            return real(req, timeout=timeout)

        code, out, err = run(["members", "T", *base], urlopen=drop_first_get)
        check("a read that is dropped once is asked again and answers", code == 0 and dropped["get"] == 1 and "DEMO-agent" in out, (code, dropped, err))

        def drop_readback(req, timeout=None):
            if req.get_method() == "GET" and "/messages/M" in req.full_url:
                raise urllib.error.URLError(ConnectionResetError("dropped"))
            return real(req, timeout=timeout)

        n = len(srv.msgs)
        code, out, err = run(["send", "T", *base, "--file", txt, "--to", "AGENT", "--json"], urlopen=drop_readback)
        doc = json.loads(out)
        check("a send whose read-back keeps failing: exit 5, posted true with its id, stored once, told not to send again",
              code == 5 and doc["posted"] is True and doc["id"] in srv.msgs and len(srv.msgs) == n + 1 and "do not send it again" in doc["reason"],
              (code, doc, len(srv.msgs) - n))
        code, out, err = run(["send", "T", *base, "--file", txt, "--to", "AGENT"], urlopen=drop_readback)
        check("the text form says it too, on stderr", code == 5 and "posted as" in err and "do not send it again" in err, (code, err))

        def drop_post(req, timeout=None):
            if req.get_method() == "POST" and req.full_url.endswith("/messages"):
                dropped["post"] += 1
                raise urllib.error.URLError(ConnectionResetError("dropped"))
            return real(req, timeout=timeout)

        n = len(srv.msgs)
        code, out, err = run(["send", "T", *base, "--file", txt, "--to", "AGENT", "--json"], urlopen=drop_post)
        doc = json.loads(out)
        check("a send that fails in transit is NOT asked again (it could post twice): one POST, exit 5, no posted flag",
              code == 5 and dropped["post"] == 1 and len(srv.msgs) == n and "posted" not in doc, (code, dropped, doc))

        # reactions: `seen_by` in status and in wait
        srv.msgs["M1"]["reactions"] = [
            {"code": "eyes", "unicode_fallback": "\U0001F440", "count": 2, "reacted_by_me": True, "reactor_ids": ["AGENT", "ME"]},
            {"code": "thumbsup", "count": 1, "reacted_by_me": False}]
        code, out, err = run(["status", "T", "M1", *base, "--json"])
        doc = json.loads(out)
        check("status: delivered, seen_by names the other member and the code (ours left out; a count with no id is someone)",
              code == 0 and doc["delivered"] is True and doc["seen_by"] == [
                  {"member_id": "AGENT", "from": "DEMO-agent", "code": "eyes"},
                  {"member_id": "", "from": "someone", "code": "thumbsup"}] and "replies" in doc, (code, doc, err))
        code, out, _ = run(["status", "T", "M1", *base])
        check("status text: who saw it", code == 0 and out.startswith("delivered M1: seen by DEMO-agent (eyes), someone (thumbsup)"), out)
        code, out, _ = run(["status", "T", "M999", *base, "--json"])
        doc = json.loads(out)
        check("status: a message that is not there is exit 5, delivered false, message_not_found",
              code == 5 and doc["delivered"] is False and doc["reason"].startswith("message_not_found"), (code, doc))
        for i in range(120):                                        # M1 is now far outside the newest 100
            srv.add("DEMO-member", f"chatter {i}")
        code, out, _ = run(["status", "T", "M1", *base, "--json"])
        doc = json.loads(out)
        check("status finds an old message however much was said since", code == 0 and doc["seen_by"][0]["member_id"] == "AGENT", (code, doc))
        code, out, _ = run(["send", "T", *base, "--file", txt, "--to", "AGENT", "--wait", "0", "--json"])
        sid = json.loads(out)["id"]
        code, out, _ = run(["wait", "T", sid, *base, "--from", "DEMO-agent", "--wait", "0", "--json"])
        check("wait: nobody looked yet: timeout with an empty seen_by", code == 3 and json.loads(out)["wait"]["seen_by"] == [], out)
        srv.msgs[sid]["reactions"] = [{"code": "eyes", "count": 1, "reacted_by_me": False, "reactor_ids": ["AGENT"]}]
        code, out, _ = run(["wait", "T", sid, *base, "--from", "DEMO-agent", "--wait", "0", "--json"])
        doc = json.loads(out)["wait"]
        check("wait: seen but not answered: timeout, seen_by has the member and eyes",
              code == 3 and doc["state"] == "timeout" and doc["seen_by"] == [{"member_id": "AGENT", "from": "DEMO-agent", "code": "eyes"}], (code, doc))
        code, out, _ = run(["wait", "T", sid, *base, "--from", "DEMO-agent", "--wait", "0"])
        check("wait text: no reply yet, and seen by", "no reply yet" in out and "seen by DEMO-agent (eyes)" in out, out)
        check("the reaction is read only: nothing in the code posts one",
              not any("reaction" in (x[0] or "") for x in srv.log))

        # watch, on a server of its own
        wsrv = FakeServer()
        wtf, _ = setup(d, wsrv, name="W", file="watch-targets.json")
        wbase = ["--targets", wtf]
        state = os.path.join(d, "state", "seq.txt")
        wsrv.add("DEMO-member", "first\nline two with glpat-AAAAAAAAAAAAAAAAAAAAAA")
        wsrv.add("ME", "my own words")
        wsrv.add("AGENT", "x" * 450)
        wsrv.add("AGENT", None, files={"a.csv": b"1", "b\n.pdf": b"2"})
        code, out, err = run(["watch", "W", *wbase, "--after-seq", "0", "--self", "DEMO-me", "--once", "--state", state])
        lines = out.splitlines()
        check("watch --once: a line per message from others, none for ours, id, seq, sender name",
              code == 0 and len(lines) == 3 and lines[0].startswith("NEW id=M1 seq=1 from=Demo Member files=-: first line two with")
              and lines[1].startswith("NEW id=M3 seq=3 from=DEMO-agent files=-: xxx"), (code, out, err))
        check("watch: the text is cut at 400 characters, on one line, a token shape removed",
              lines[1].endswith("x" * 400) and "x" * 401 not in lines[1] and "glpat-" not in lines[0] and "[removed: secret]" in lines[0], lines)
        check("watch: the state file holds the last seq (ours counted), made with its folder", open(state).read().strip() == "4")
        check("watch: a file message is a line with its names (a line break in a name is gone) and no text",
              lines[2] == "NEW id=M4 seq=4 from=DEMO-agent files=a.csv,b.pdf:", lines)
        code, out, _ = run(["watch", "W", *wbase, "--self", "DEMO-me", "--once", "--state", state])
        check("watch: a second pass from the state file prints nothing and repeats nothing", code == 0 and out == "", out)
        wsrv.add("AGENT", "later")
        code, out, _ = run(["watch", "W", *wbase, "--self", "DEMO-me", "--once", "--state", state, "--after-seq", "0"])
        check("watch: the state file wins over --after-seq; only the new message", out.splitlines() == ["NEW id=M5 seq=5 from=DEMO-agent files=-: later"], out)
        code, out, _ = run(["watch", "W", *wbase, "--self", "DEMO-me", "--once"])
        check("watch with no cursor: starts after the newest message now and prints none of the old", code == 0 and out == "WATCHER: started after seq 5\n", out)
        code, out, _ = run(["watch", "W", *wbase, "--self", "DEMO-me", "--once", "--json", "--after-seq", "4"])
        check("watch --json: one document per line",
              json.loads(out) == {"event": "message", "id": "M5", "seq": 5, "sender_id": "AGENT", "from": "DEMO-agent", "text": "later", "files": []}, out)
        for i in range(150):
            wsrv.add("AGENT", f"bulk {i}")
        code, out, _ = run(["watch", "W", *wbase, "--self", "DEMO-me", "--once", "--after-seq", "5"])
        check("watch pages past 100 messages: all 150, in order", len(out.splitlines()) == 150 and out.splitlines()[-1].endswith("bulk 149"), len(out.splitlines()))
        code, out, _ = run(["watch", "W", *wbase, "--once", "--after-seq", "153"])
        check("watch with no --self says so, and prints our own messages too",
              out.splitlines()[0].startswith("WATCHER: no --self") and len(out.splitlines()) == 1 + 2, out)
        with open(wtf) as fh:
            wcfg = json.load(fh)
        wcfg["W"]["self"] = "ME"
        with open(wtf, "w") as fh:
            json.dump(wcfg, fh)
        code, out, _ = run(["watch", "W", *wbase, "--once", "--after-seq", "1"])
        check("watch: \"self\" in the target's entry stands for --self", "my own words" not in out and "WATCHER" not in out and "x" * 400 in out, out[:200])

        # a long failure: one WATCHER line at the 10th failed read, one when reads work again
        down = {"on": True}

        def flaky(req, timeout=None):
            if down["on"] and req.get_method() == "GET" and "/members" not in req.full_url:
                raise urllib.error.URLError(ConnectionResetError("dropped"))
            return real(req, timeout=timeout)

        naps = []

        def nap(n):
            naps.append(n)
            if len(naps) == 12:
                down["on"] = False
            if len(naps) == 14:
                raise KeyboardInterrupt
        code, out, err = run(["watch", "W", *wbase, "--after-seq", "150", "--poll", "7"], urlopen=flaky, sleep=nap)
        warn = [ln for ln in out.splitlines() if ln.startswith("WATCHER")]
        check("watch: 10 failed reads in a row print one WATCHER line, recovery one more, then it follows on; polls at --poll",
              code == 0 and len([w for w in warn if "10 reads in a row" in w]) == 1 and warn[-1] == "WATCHER: reads work again"
              and set(naps) == {7.0}, (code, out, naps))

        def no_token(req, timeout=None):
            if req.full_url.endswith("/auth/agent/token"):
                raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)
            return real(req, timeout=timeout)
        naps.clear()
        code, out, err = run(["watch", "W", *wbase, "--once", "--after-seq", "1"], urlopen=no_token)
        check("watch: a token exchange that fails says so at once and names the api key; exit 5 for --once",
              code == 5 and "token exchange failed" in out and "api key" in out and out.count("WATCHER") == 1, (code, out))
        check("watch prints no api key", KEY not in out)
        wsrv.close()
        wsrv.httpd.server_close()

        srv.close()
        srv.httpd.server_close()
        code, _, err = run(["members", "T", *base])
        check("a server that is down: exit 5", code == 5, (code, err))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
