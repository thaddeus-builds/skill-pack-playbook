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
  * it runs as a script (the `kit` path is found from the file) and as `main(argv, urlopen=)`.
"""

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

        srv.close()
        srv.httpd.server_close()
        code, _, err = run(["members", "T", *base])
        check("a server that is down: exit 5", code == 5, (code, err))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
