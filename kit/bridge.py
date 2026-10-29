"""Send one message through the OpenMax bridge and read it back before saying it was sent.

The bridge once answered "ok" for a message it stored empty (seen in two packs,
2026-10-29; docs/support-channel.md). So a send is not reported until the
message, read back by the id the send returned, equals what was meant.

  * one plain text, an ASCII `@name` (a full-width `＠` is no mention): refused
    before anything is sent, as is an empty text;
  * `send(text)` returns the new message id; none returned -> nothing is
    resent (it may have gone out) and the result says not sent;
  * `read(id)` returns that message's text; the two are compared after
    stripping surrounding whitespace, nothing else;
  * a read-back that is empty or different -> ONE resend and a second
    read-back; still wrong -> stop, not sent;
  * a read-back that fails or returns None -> not sent, NOT resent (the
    message may be there; a resend would reach the client twice).

Reading is the other half. What a client's agent posts back can be data, and the bridge
is a model, so the text it prints was copied by a model. `read_new` reads the messages
newer than an id twice and returns them only when the two copies agree on every id,
sender and character of text; otherwise it returns none and says why, and the caller
reads again. Nothing is sent by it, and no cursor is kept here (the pack keeps its
last-seen id).

`send` and `read` are plain callables, so a pack decides how the bridge is
called (a shell function, headless `claude -p` with only `comm_send` or only
`comm`); `prompts` and `parse_id`/`parse_text` give the strict wording for that
call. No client name, group or id lives here. Test: kit/tests/test_bridge.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

FULL_WIDTH_AT = "＠"


@dataclass(frozen=True)
class Result:
    sent: bool
    id: str | None = None
    resent: bool = False
    reason: str = ""


def _bad_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return "empty_text"
    if FULL_WIDTH_AT in text:
        return "full_width_at"
    return ""


def send_and_verify(send: Callable[[str], str | None], read: Callable[[str], str | None], text: str) -> Result:
    why = _bad_text(text)
    if why:
        return Result(False, reason=why)
    resent = False
    for attempt in (1, 2):
        sent_id = send(text)
        if not sent_id:
            return Result(False, resent=resent, reason="no_id_returned")
        try:
            got = read(sent_id)
        except Exception:                         # the bridge, a process, a timeout: the message may be there
            return Result(False, sent_id, resent, "read_back_failed")
        if got is None:
            return Result(False, sent_id, resent, "read_back_failed")
        if got.strip() == text.strip():
            return Result(True, sent_id, resent)
        if attempt == 2:
            return Result(False, sent_id, resent, "read_back_differs")
        resent = True
    raise AssertionError("unreachable")


def send_prompt(conversation_id: str, text: str) -> str:
    return (f'Call comm_send once with endpoint "{conversation_id}" and content set to this single plain string '
            f"(@names are plain text with an ASCII @, no mention objects, no content array):\n\n{text}\n\n"
            "Do nothing else. Answer with one line: id: <the id comm_send returned>")


def read_prompt(conversation_id: str, message_id: str) -> str:
    return (f"Read message {message_id} of conversation {conversation_id} with the comm tool (getMessage). "
            "Do NOT send anything. Answer with a line `id: <id>`, then a line `text:`, then its full text exactly, nothing after it.")


def parse_id(output: str) -> str | None:
    """The id on the last `id:` line of a send's answer, or None."""
    ids = [ln.split(":", 1)[1].strip() for ln in output.splitlines() if ln.lower().startswith("id:")]
    return ids[-1] or None if ids else None


def parse_text(output: str) -> str | None:
    """What follows the `text:` line of a read-back's answer; None if there is no such line."""
    lines = output.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().lower() == "text:":
            return "\n".join(lines[i + 1:])
    return None


def runners(run: Callable[[str, str], str], conversation_id: str):
    """`send` and `read` for send_and_verify, over run(allowed_tool, prompt) -> the answer text."""
    def send(text: str) -> str | None:
        return parse_id(run("comm_send", send_prompt(conversation_id, text)))

    def read(message_id: str) -> str | None:
        return parse_text(run("comm", read_prompt(conversation_id, message_id)))
    return send, read


@dataclass(frozen=True)
class Message:
    id: str
    sender: str
    text: str
    time: str = field(default="", compare=False)      # a model may print it differently twice: not part of the agreement


@dataclass(frozen=True)
class Read:
    agreed: bool
    messages: tuple[Message, ...] = ()
    reason: str = ""


_BLOCK = re.compile(r"^ID: (\S+)[ \t]*\r?\nSender: (\S+)[ \t]*\r?\nTime: ([^\n]*)\r?\n<<<BEGIN\r?\n(.*?)\r?\nEND>>>", re.S | re.M)


def read_new_prompt(conversation_id: str, after_id: str) -> str:
    return (f"Read-only task. Use only the comm tool. In conversation {conversation_id} list every message with id greater than "
            f'{after_id}, oldest first. For each print a line "ID: <id>", a line "Sender: <sender id>", a line "Time: <time>", then '
            "the FULL text verbatim between the lines <<<BEGIN and END>>> (no summary, no shortening, keep every line break, change "
            "no character). If there are none, print exactly NONE. Send nothing.")


def parse_messages(output: str) -> list[Message] | None:
    """The messages in a read's answer, oldest first; [] when it says NONE; None when it holds neither."""
    found = [Message(i, sender, text, time.strip()) for i, sender, time, text in _BLOCK.findall(output)]
    if found:
        return found
    return [] if re.search(r"^\s*NONE\s*$", output, re.M) else None


def read_new(run: Callable[[str, str], str], conversation_id: str, after_id: str) -> Read:
    """Messages newer than `after_id`, read twice through run(allowed_tool, prompt) -> the answer text; agreed only if the
    two copies are the same messages with the same text."""
    prompt = read_new_prompt(conversation_id, after_id)
    copies = []
    for _ in range(2):
        try:
            got = parse_messages(run("comm", prompt))
        except Exception:                         # the bridge, a process, a timeout
            return Read(False, reason="read_failed")
        if got is None:
            return Read(False, reason="no_answer")
        copies.append(got)
    if copies[0] != copies[1]:
        return Read(False, reason="reads_differ")
    return Read(True, tuple(copies[0]))

