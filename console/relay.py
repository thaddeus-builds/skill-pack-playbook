"""Runs a skill pack's own human gate for one click of the console.

A skill pack that wants a human in the loop answers a first call with a challenge
(a one-time code bound to exactly what it would write) and accepts the same call
again with that code. `run()` is the console's side of that exchange:

    1 ask     <cmd> <verb…> [--market=M] [--value=V] --reason=R --json
                                                         stdin /dev/null
    2 read    the skill pack's one JSON document (stdout only)
    3 check   the payload the code is bound to is what the human was shown
    4 answer  the same call + --code=C --relay-user=web:U --relay-at=T

The skill pack's challenge is `{"code": "confirm_code_required", "params":
{"confirm_code": C}, "subject": {…}}`; its answers carry text in `error`,
`message` or `result` (a string). A document that is not the challenge is the
final answer: the skill pack's exit code says whether it worked, which is also how
an idempotent "already confirmed" ends the exchange at step 1. After step 4 a
failure counts as a refusal only when the skill pack said so in a document with
`error` or `message`; a crash, garbage or silence is `gate_unsure`, because the
skill pack may have written before it stopped.

What this module guarantees, and the tests hold it to:

  * `run()` never raises for a skill pack problem: every failure is a dict with a
    `code` from `core.CODES` (`gate_unavailable`, `gate_refused`, `gate_changed`,
    `gate_unsure`, `gate_timeout`) and one plain line of text.
  * Nothing runs unless the ask has a well-formed gate whose verb starts with one
    of the operator's allowed verbs and the answer is one `core.check_value`
    accepts. The command is the operator's, never the ask's; a "no" never runs.
  * No shell. Every argument is its own list item, and everything the console
    adds is one `--name=value` element (`--value`, `--reason`, and on the second
    call `--code`, `--relay-user`, `--relay-at`), so nothing the human types and
    no code the skill pack issues, even one starting with `-`, can be read as
    another option or become another command. A gate's `market` (one plain
    word, checked when the ask was added) becomes `--market=M`, so a skill pack
    with several markets is told which one; the subject it binds still has to
    match what was shown.
  * The code is sent only when the subject matches what was shown
    (`core.matches`: everything the ask names is in it exactly, an extra item
    is not allowed, only the skill pack's own envelope may say more); a mismatch
    is `gate_changed` and the second call never happens. The code appears in no
    result, exception or log line (a skill pack that echoes it back has it
    scrubbed), and the skill pack never sees the console's own secret
    (`CONSOLE_SECRET`).
  * A skill pack that hangs is killed with everything it started, on either call.

`fetch()` is the other thing the console asks of the skill pack: a page. It
runs `<cmd> <verb…> --lang=L --json` the same way (no shell, no stdin, no
terminal, the console's secret withheld, killed on a timeout) and returns the
one JSON object it prints. A page verb is read-only by contract; the console
cannot enforce that, but it can and does ignore everything but the document.

Only this module in the console starts a process.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import unicodedata

import core

CHALLENGE = "confirm_code_required"
MAX_MESSAGE, MAX_REASON = 300, 200
_BIDI = frozenset("‎‏؜‪‫‬‭‮"
                  "⁦⁧⁨⁩")

log = logging.getLogger("console.relay")

UNAVAILABLE = "This answer cannot be sent to the skill pack from this console."
UNSENDABLE = "That answer is not one the skill pack can be given; nothing was written."
NO_NEVER = "A no is never sent to the skill pack; nothing was written."
WHO = "The console cannot tell the skill pack who is answering; nothing was written."
UNREADABLE = "The skill pack answered in a way the console could not read; nothing was written."
BAD_CHALLENGE = "The skill pack asked for a confirmation the console could not read; nothing was written."
ASKED_AGAIN = "The skill pack asked for a code again instead of answering; nothing was written."
LATE = "The skill pack did not answer in time. It may have written before it stopped; ask the agent to check."


class _Timeout(Exception):
    pass


def run(ask: dict, value: str, *, cmd: list[str], verbs: list[list[str]],
        user: str, reason: str, timeout: float = 60.0,
        env: dict | None = None) -> dict:
    """Send one answer through the skill pack's gate.

    -> {"ok": bool, "code": None | "gate_refused" | "gate_changed" |
        "gate_unsure" | "gate_timeout" | "gate_unavailable", "message": one line
        of at most 300 characters, "verb": the ask's verb}

    `cmd` is the skill pack command (argv), `verbs` the allowed verb prefixes (word
    lists), `user` the human's name (the skill pack is told `web:<user>`), `reason`
    is cleaned to one line of at most 200 characters, `timeout` applies to each
    of the two calls, `env` is the child's environment (default: ours).
    """
    verb = _verb(ask, verbs)
    if verb is None:
        return _out(False, "gate_unavailable", UNAVAILABLE, [])

    def fail(code, message):
        return _out(False, code, message, verb)

    if not (isinstance(cmd, list) and cmd
            and all(isinstance(w, str) and _sendable(w) for w in cmd)):
        return fail("gate_unavailable", UNAVAILABLE)
    norm, err = core.check_value(ask, value) if isinstance(value, str) else (None, True)
    if err or not _sendable(norm):
        return fail("gate_refused", UNSENDABLE)
    if not core.gate_runs(ask, norm):
        return fail("gate_refused", NO_NEVER)
    if not (isinstance(user, str) and core.TOKEN_RE.fullmatch(user)):
        return fail("gate_refused", WHO)

    argv = cmd + verb
    market = ask["gate"].get("market")
    if market is not None:
        argv.append(f"--market={market}")
    if ask["gate"].get("value_arg", False):
        argv.append(f"--value={norm}")
    argv += ["--reason=" + _plain(reason or "")[:MAX_REASON], "--json"]

    try:
        status, out = _exec(argv, timeout, env, 1)
    except _Timeout:
        return fail("gate_timeout", core.CODES["gate_timeout"])
    except OSError:
        return fail("gate_unavailable", "The skill pack command could not be started.")
    doc = _parse(out)
    if doc is None:
        return fail("gate_refused", UNREADABLE)
    if not _is_challenge(doc):
        return _answer(status, doc, verb, None)

    secret = _code_of(doc)
    if secret is None:
        return fail("gate_refused", BAD_CHALLENGE)
    if not core.matches(core.expect_for(ask, norm), doc.get("subject")):
        return fail("gate_changed", core.CODES["gate_changed"])

    argv += [f"--code={secret}", f"--relay-user=web:{user}",
             f"--relay-at={core.now()}"]
    try:
        status, out = _exec(argv, timeout, env, 2)
    except _Timeout:
        return fail("gate_timeout", LATE)
    except OSError:
        return fail("gate_unavailable", "The skill pack command could not be started.")
    doc = _parse(out)
    if _is_challenge(doc):
        return fail("gate_refused", ASKED_AGAIN)
    if doc is None or (status != 0 and not _says(doc)):
        return fail("gate_unsure", core.CODES["gate_unsure"])
    return _answer(status, doc, verb, secret)


MAX_PAGE = 1 << 20          # a page document bigger than this is not one


def fetch(cmd: list[str], verb: list[str], *, lang: str = "en", timeout: float = 30.0,
          env: dict | None = None) -> dict:
    """Ask the skill pack for one page (or the tab counts).

    -> {"ok": True, "doc": the JSON object} or {"ok": False, "code":
       "page_unavailable" | "gate_timeout", "message": one plain line}

    Never raises for a skill pack problem. Only an object counts as a document;
    a non-zero exit is a failure even with a document, and its `error` or
    `message` (cleaned, at most 300 characters) is what the person is told."""
    if not (isinstance(cmd, list) and cmd and all(isinstance(w, str) and _sendable(w) for w in cmd)
            and isinstance(verb, list) and verb and all(isinstance(w, str) and _sendable(w) for w in verb)):
        return _fetch_fail(UNAVAILABLE)
    argv = cmd + verb + [f"--lang={lang}", "--json"]
    try:
        status, out = _exec(argv, timeout, env, 1)
    except _Timeout:
        return {"ok": False, "code": "gate_timeout", "message": core.CODES["gate_timeout"]}
    except OSError:
        return _fetch_fail("The skill pack command could not be started.")
    doc = _parse(out) if len(out) <= MAX_PAGE else None
    if status != 0:
        said = next((v for k in ("error", "message", "result") if isinstance(doc, dict)
                     and isinstance(v := doc.get(k), str) and v.strip()), "")
        return _fetch_fail(_plain(said)[:MAX_MESSAGE] or core.CODES["page_unavailable"])
    if not isinstance(doc, dict):
        return _fetch_fail("The skill pack answered in a way the console could not read.")
    return {"ok": True, "doc": doc}


def _fetch_fail(message: str) -> dict:
    return {"ok": False, "code": "page_unavailable", "message": message}


# ------------------------------------------------------------ checking --

def _verb(ask, verbs) -> list[str] | None:
    """The gate's verb (a copy) if the ask carries a well-formed gate and the verb
    starts with an allowed prefix, else None."""
    gate = ask.get("gate") if isinstance(ask, dict) else None
    if not (isinstance(gate, dict) and ask.get("step") in core.STEPS):
        return None
    verb, expect = gate.get("verb"), gate.get("expect")
    if not (isinstance(verb, list) and 1 <= len(verb) <= core.LIMITS["verb"]
            and all(isinstance(w, str) and core.TOKEN_RE.fullmatch(w) for w in verb)
            and isinstance(expect, dict) and expect
            and isinstance(gate.get("value_arg", False), bool)
            and (gate.get("market") is None
                 or (isinstance(gate.get("market"), str)
                     and core.TOKEN_RE.fullmatch(gate["market"])))):
        return None
    if not any(isinstance(p, list) and p and verb[:len(p)] == p
               for p in verbs or []):
        return None
    return list(verb)


def _sendable(text: str) -> bool:
    """Can this be one argument of a child process (no NUL, encodable)?"""
    try:
        os.fsencode(text)
    except UnicodeError:
        return False
    return "\x00" not in text


def _plain(text) -> str:
    """One line of visible characters: control characters, direction marks and
    every kind of line break become single spaces."""
    text = "".join(" " if unicodedata.category(c) in ("Cc", "Cs") or c in _BIDI
                   else c for c in str(text))
    return " ".join(text.split())


def _is_challenge(doc) -> bool:
    return isinstance(doc, dict) and doc.get("code") == CHALLENGE


def _says(doc) -> bool:
    """Did the skill pack put words in its answer (`error` or `message`)? A crash,
    garbage or an empty stdout has none."""
    return isinstance(doc, dict) and any(
        isinstance(v := doc.get(k), str) and v.strip() for k in ("error", "message"))


def _code_of(doc: dict) -> str | None:
    """The one-time code of a challenge, if it is one that can be sent back."""
    params = doc.get("params")
    c = params.get("confirm_code") if isinstance(params, dict) else None
    ok = (isinstance(c, str) and 0 < len(c) <= 200 and c.isprintable()
          and not any(ch.isspace() for ch in c))
    return c if ok else None


# ------------------------------------------------------------- running --

def _exec(argv: list[str], timeout: float, env: dict | None, n: int) -> tuple[int, bytes]:
    """(exit status, stdout). The child gets no stdin; on a timeout it and
    everything it started are killed."""
    env = dict(os.environ if env is None else env)
    env.pop("CONSOLE_SECRET", None)
    log.debug("relay call %d: %s", n, _shown(argv))
    # start_new_session: no controlling terminal, so a skill pack gate that reads
    # /dev/tty can only be satisfied by a person at the operator's terminal,
    # never by the web click; and the child leads its own process group, which
    # a timeout kills whole
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(proc)
        raise _Timeout from None
    except BaseException:
        _kill(proc)
        raise
    log.debug("relay call %d: exit %s, %d bytes out, %d bytes err",
              n, proc.returncode, len(out), len(err))
    return proc.returncode, out


def _kill(proc: subprocess.Popen) -> None:
    # a wrapper such as `uv run` has a child of its own: signal the whole group
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (AttributeError, OSError):
        proc.kill()
    proc.wait()
    for pipe in (proc.stdout, proc.stderr):
        pipe.close()


def _shown(argv: list[str]) -> list[str]:
    return ["--code=***" if w.startswith("--code=") else w for w in argv]


# ------------------------------------------------------------- reading --

def _parse(raw: bytes):
    """The skill pack's document: all of stdout if it is one JSON document, else its
    last line (a skill pack may print a banner first). A dict or a list, or None."""
    text = raw.decode("utf-8", "replace").strip()
    for candidate in (text, text.rsplit("\n", 1)[-1].strip()):
        try:
            doc = json.loads(candidate)
        except (ValueError, RecursionError):
            continue
        if isinstance(doc, (dict, list)):
            return doc
    return None


def _answer(status: int, doc, verb: list[str], secret: str | None) -> dict:
    ok = status == 0
    keys = ("message", "result", "error") if ok else ("error", "message", "result")
    text = next((v for k in keys
                 if isinstance(doc, dict) and isinstance(v := doc.get(k), str)
                 and v.strip()), "")
    if secret:
        text = text.replace(secret, "***")
    text = _plain(text)
    if len(text) > MAX_MESSAGE:
        text = text[:MAX_MESSAGE - 1].rstrip() + "…"
    if not ok:
        return _out(False, "gate_refused", text or core.CODES["gate_refused"], verb)
    return _out(True, None, text, verb)


def _out(ok: bool, code: str | None, message: str, verb: list[str]) -> dict:
    return {"ok": ok, "code": code, "message": message, "verb": list(verb)}
