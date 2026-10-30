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

`send` and `read` are plain callables, so a pack decides how the bridge is
called. Two ways are here:

  * REST (`send_to`, `rest_runners`): the bridge plugin's own HTTP calls, no
    `claude` process, no model call, no connection and no data dir of the
    plugin touched. The api key is read from the plugin's config (0600, outside
    the repo), exchanged for a token held in memory, and never returned, logged
    or put in a reason. design: docs/design/bridge-isolation.md;
  * headless `claude -p` with only `comm_send` or only `comm` (`prompts`,
    `parse_id`/`parse_text`, `runners`), for a machine with no key file.

`check_isolation(targets)` names what would make two bridges share state before
anything is sent. No client name, group or id lives here.
Test: kit/tests/test_bridge.py.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Callable, Iterable

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


# --- isolation: what must differ between two bridges --------------------------------------------

@dataclass(frozen=True)
class Target:
    """One conversation reached through one plugin config. All four come from the pack's config outside the repo."""
    config: str            # the plugin's config file (holds the api key)
    data_dir: str          # CLAUDE_OPENMAX_DATA_DIR of that bridge (token cache, sync cursor)
    conversation_id: str
    org_id: str


def _read_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


def check_isolation(targets: Iterable[Target]) -> list[str]:
    """Problems that would make bridges share state, as `code: where` lines (never a key); [] when none.

    Same config -> one data dir (it is one identity); different configs -> different data dirs;
    each config exists, is 0600, holds an api key and the target's organization.
    """
    targets = list(targets)
    problems: list[str] = []
    dirs_of: dict[str, set[str]] = {}
    for t in targets:
        cfg = os.path.realpath(os.path.expanduser(t.config))
        dirs_of.setdefault(cfg, set()).add(os.path.realpath(os.path.expanduser(t.data_dir)) if t.data_dir else "")
        try:
            mode = os.stat(cfg).st_mode & 0o777
        except OSError:
            problems.append(f"config_missing: {t.config}")
            continue
        if mode & 0o077:
            problems.append(f"config_mode: {t.config} is {oct(mode)}, must be 0600")
        try:
            data = _read_config(cfg)
        except (OSError, ValueError):
            problems.append(f"config_unreadable: {t.config}")
            continue
        if not str((data.get("agent") or {}).get("api_key") or "").strip():
            problems.append(f"no_api_key: {t.config}")
        if t.org_id not in (data.get("orgs") or {}):
            problems.append(f"org_not_in_config: {t.org_id} in {t.config}")
        if not t.data_dir:
            problems.append(f"no_data_dir: {t.config}")
    seen: dict[str, str] = {}
    for cfg, dirs in dirs_of.items():
        if len(dirs) > 1:
            problems.append(f"data_dir_differs: {cfg} is used with {len(dirs)} data dirs")
        for d in dirs - {""}:
            if d in seen and seen[d] != cfg:
                problems.append(f"data_dir_shared: {d} is used by {seen[d]} and {cfg}")
            seen.setdefault(d, cfg)
    return problems


# --- REST: send and read back with the plugin's own HTTP calls -----------------------------------

class RestError(Exception):
    """An HTTP call failed. The text names the status and the step, never a body, a token or a key."""


@dataclass(frozen=True)
class Credentials:
    base_url: str
    org_id: str
    api_key: str = field(repr=False)
    headers: dict = field(default_factory=dict, repr=False)   # Cloudflare Access pair, when the config has one
    prefix: str = "/api/v1"


def load_credentials(config: str, org_id: str) -> Credentials:
    cfg = _read_config(os.path.expanduser(config))
    base = str((cfg.get("server") or {}).get("bff_url") or "").rstrip("/")
    key = str((cfg.get("agent") or {}).get("api_key") or "").strip()
    if not base or not key:
        raise ValueError("the config has no server.bff_url or agent.api_key")
    cf = cfg.get("cf_access") or {}
    headers = ({"CF-Access-Client-Id": cf["client_id"], "CF-Access-Client-Secret": cf["client_secret"]}
               if cf.get("client_id") and cf.get("client_secret") else {})
    return Credentials(base, org_id, key, headers)


def _unwrap(raw):
    return raw["data"] if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw


def rest_runners(creds: Credentials, conversation_id: str, *, mentions: Iterable[str] = (),
                 urlopen=urllib.request.urlopen, timeout: float = 30.0):
    """`send` and `read` for send_and_verify over HTTP. `mentions` are member ids sent as mention objects
    (an @name in the text wakes an agent only with one). `send.last_error` holds why a send returned None."""
    token: list[str] = []
    mention_objs = [{"type": "member", "member_id": m} for m in mentions]

    def call(method, path, body=None, bearer=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(creds.base_url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        for k, v in creds.headers.items():
            req.add_header(k, v)
        req.add_header("Authorization", f"Bearer {bearer}")
        try:
            with urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raise RestError(f"{method} {path.rsplit('/', 1)[0]}: HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise RestError(f"{method} {path.rsplit('/', 1)[0]}: {type(e).__name__}") from None
        try:
            return json.loads(text) if text.strip() else {}
        except ValueError:
            raise RestError(f"{method} {path.rsplit('/', 1)[0]}: not JSON") from None

    def exchange() -> str:
        d = _unwrap(call("POST", "/auth/agent/token", {"org_id": creds.org_id}, creds.api_key))
        tok = d.get("access_token") if isinstance(d, dict) else None
        if not tok:
            raise RestError("token exchange: no access_token")
        token[:] = [tok]
        return tok

    def authed(method, path, body=None):
        try:
            return call(method, path, body, token[0] if token else exchange())
        except RestError as e:
            if "HTTP 401" not in str(e):         # an expired token: one fresh exchange, then once more
                raise
            return call(method, path, body, exchange())

    base = f"{creds.prefix}/conversations/{conversation_id}/messages"

    def send(text: str) -> str | None:
        body = {"client_msg_id": uuid.uuid4().hex, "type": "AGENT_TEXT",
                "content": {"content_type": "text", "body": {"text": text}, "attachments": []}}
        if mention_objs:
            body["mentions"] = mention_objs
        send.last_error = ""
        try:
            d = _unwrap(authed("POST", base, body))
        except RestError as e:
            send.last_error = str(e)
            return None
        if not isinstance(d, dict):
            return None
        mid = d.get("id") or (d.get("message") or {}).get("id") or d.get("message_id")
        return str(mid) if mid else None
    send.last_error = ""

    def read(message_id: str) -> str | None:
        d = _unwrap(authed("GET", f"{base}/{message_id}"))
        msg = d.get("message", d) if isinstance(d, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, dict):
            return None                          # nothing readable: not sent, not resent
        body = content.get("body")
        text = body.get("text") if isinstance(body, dict) else None
        return text if isinstance(text, str) else ""   # a message stored without text is the empty one

    return send, read


def send_to(target: Target, text: str, *, mentions: Iterable[str] = (), urlopen=urllib.request.urlopen) -> Result:
    """Check the isolation, then send `text` to the target over REST and read it back."""
    problems = check_isolation([target])
    if problems:
        return Result(False, reason="isolation: " + problems[0])
    try:
        creds = load_credentials(target.config, target.org_id)
    except (OSError, ValueError) as e:
        return Result(False, reason=f"config: {e}")
    send, read = rest_runners(creds, target.conversation_id, mentions=mentions, urlopen=urlopen)
    result = send_and_verify(send, read, text)
    if not result.sent and result.reason == "no_id_returned" and send.last_error:
        return Result(False, result.id, result.resent, f"no_id_returned: {send.last_error}")
    return result
