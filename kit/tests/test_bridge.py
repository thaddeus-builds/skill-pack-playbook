#!/usr/bin/env python3
"""kit.bridge: a message is reported sent only when its read-back equals it.

  * equal read-back -> sent with the id; surrounding whitespace is ignored;
  * empty or different read-back -> one resend, then sent=True with resent=True;
    wrong twice -> not sent, two sends only;
  * no id returned -> not sent, no resend; read-back failing or None -> not sent, no resend;
  * a full-width ＠ or an empty text is refused before any send;
  * the prompts name only the tool for the step and the parsers read the strict answers;
  * a read-back reads the id the send returned, not the newest message.
"""

import sys
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
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
