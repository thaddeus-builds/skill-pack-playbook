#!/usr/bin/env python3
"""Claude Code hooks that give every session the bridge's rules, without the session having to remember them.

A session that sends with the OpenMax plugin's own `comm_send` never passes through `kit.bridge`, and it is
that path that forgot the @ and then never read the answer. These hooks sit around it:

  pre-send   (PreToolUse on comm_send)   a message to a GROUP with no `@name` is refused (`no_mention`), as is one whose
                                         @name is no member (`unknown_mention`) or that is the 11th awaited in a day; a DM is not;
  post-send  (PostToolUse on comm_send)  the sent message is written to a pending file (offline, no network);
  turn       (UserPromptSubmit)          each pending request is read from its cursor (`after_seq`), what arrived
  session    (SessionStart)              is handed to the session as untrusted data, each message once;
  end        (SessionEnd)                the session's requests may be read by the next one;
  list, close ID, install-snippet        what is awaited and for how long; stop waiting; the settings to add.

A reply is handed to the session that asked; what comes as several messages is held until 25 seconds pass with nothing
new, then handed over together and marked read.

No background process: the session is reached at the start of a turn and at session start. An idle session has
no turn, so a reply with no @ to us waits for the next one. The pending file lives in the identity's own data
dir (CLAUDE_OPENMAX_DATA_DIR, one per identity, `check_isolation`), under a file lock; a second session on the
same identity that finds it locked skips the read, so a reply is handed over once. A hook never blocks a tool
but for the one case above, never fails the session (exit 0, a log line), and never runs longer than its timeouts.

The reply text is the other side's words: wrapped as untrusted, token shapes removed (`kit.bridge.wrap_untrusted`).
Which messages count (after ours, not ours, and under ours, mentioning us, from the agent we asked, or from a
person) is `_matches`. Test: kit/tests/test_bridge_hooks.py. Design: docs/design/bridge-delivery.md.
"""

from __future__ import annotations

import contextlib
import dataclasses
import fcntl
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

if __name__ == "__main__":                       # run as a script from a hook command: find `kit`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kit import bridge  # noqa: E402

STATE_FILE = "bridge-pending.json"
SEND_TOOL = "mcp__plugin_openmax-channel_openmax__comm_send"
FINAL_AFTER = 24 * 3600          # a request is no longer read after this
DUE_AFTER = 30 * 60              # reported as overdue after this (kept: a late reply still arrives)
POLL_EVERY = 20                  # seconds between reads of one request
QUIET_FOR = 25                   # seconds with nothing new before what has come is handed over (one answer, many messages)
SESSION_IDLE = 1800              # a session that has not run a hook for this long no longer owns its requests
REQUEST_CAP = 10                 # requests awaited per conversation inside FINAL_AFTER; the next is refused
MEMBERS_TTL = 600
MAX_REQUESTS_PER_RUN = 5
MAX_PAGES = 5
HTTP_TIMEOUT = 5.0
NO_MENTION = ("no_mention: a message to a group must @-mention the agent it is for (an ASCII @name); "
              "an agent in a group answers only when it is mentioned. A direct message needs none.")


# --- where things are ----------------------------------------------------------------------------

def data_dir(env=None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("CLAUDE_OPENMAX_DATA_DIR") or Path.home() / ".local" / "share" / "claude-openmax")


def config_path(env=None) -> str:
    env = os.environ if env is None else env
    return env.get("CLAUDE_OPENMAX_CONFIG") or str(Path.home() / ".config" / "claude-openmax" / "config.json")


def _log(env, msg: str) -> None:
    try:
        d = data_dir(env)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "bridge-hooks.log", "a", encoding="utf-8") as fh:
            fh.write(f"{int(time.time())} {msg[:300]}\n")
    except OSError:
        pass


# --- the pending file ----------------------------------------------------------------------------

@contextlib.contextmanager
def _lock(env, wait: bool):
    """The state lock. `wait=False` yields None when another session holds it."""
    d = data_dir(env)
    d.mkdir(parents=True, exist_ok=True)
    fh = open(d / (STATE_FILE + ".lock"), "a+")
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except OSError:
            yield None
            return
        yield True
    finally:
        fh.close()


def load(env=None) -> dict:
    try:
        with open(data_dir(env) / STATE_FILE, encoding="utf-8") as fh:
            st = json.load(fh)
        if isinstance(st, dict):
            st.setdefault("requests", [])
            st.setdefault("types", {})
            st.setdefault("sessions", {})
            st.setdefault("members", {})
            return st
    except (OSError, ValueError):
        pass
    return {"requests": [], "types": {}, "sessions": {}, "members": {}}


def save(state: dict, env=None) -> None:
    d = data_dir(env)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{STATE_FILE}.tmp-{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)
    os.replace(tmp, d / STATE_FILE)


# --- the API (read only, short timeouts) ---------------------------------------------------------

def _org_of(env, hint: str = "") -> str:
    cfg = bridge._read_config(os.path.expanduser(config_path(env)))
    orgs = [o for o, v in (cfg.get("orgs") or {}).items() if not isinstance(v, dict) or v.get("enabled", True)]
    return hint if hint in orgs else (orgs[0] if orgs else "")


def _authed(env, org_id: str, urlopen):
    creds = bridge.load_credentials(config_path(env), org_id)
    return bridge._client(creds, urlopen, HTTP_TIMEOUT), creds.prefix


def _conversation_type(state, env, org_id, conv, urlopen) -> str:
    """GROUP, DM, ...; remembered (a conversation's kind does not change). '' when it cannot be read."""
    if conv in state["types"]:
        return state["types"][conv]
    try:
        authed, prefix = _authed(env, org_id, urlopen)
        d = bridge._unwrap(authed("GET", f"{prefix}/conversations/{conv}"))
        d = d.get("conversation", d) if isinstance(d, dict) else {}
        kind = str(d.get("type") or "").upper()
    except Exception as e:
        _log(env, f"conversation type unreadable: {type(e).__name__}")
        return ""
    if kind:
        state["types"][conv] = kind
    return kind


def _members(state, env, org_id, conv, urlopen, now) -> list:
    """The group's members, remembered for MEMBERS_TTL; [] when they cannot be read (then nothing is refused)."""
    hit = state["members"].get(conv)
    if hit and now - hit["at"] < MEMBERS_TTL:
        return hit["members"]
    try:
        authed, prefix = _authed(env, org_id, urlopen)
        d = bridge._unwrap(authed("GET", f"{prefix}/conversations/{conv}/members"))
    except Exception as e:
        _log(env, f"members unreadable: {type(e).__name__}")
        return []
    members = [{"member_id": m.get("member_id"), "display_name": m.get("display_name")}
               for m in (d if isinstance(d, list) else []) if isinstance(m, dict)]
    if members:
        state["members"][conv] = {"at": now, "members": members}
    return members


# --- the hooks -----------------------------------------------------------------------------------

def _endpoint_conversation(endpoint: str) -> str:
    rest = (endpoint or "").strip()
    if rest.startswith("[COCO") and "]/" in rest:
        rest = rest.split("]/", 1)[1]
    return rest.split("|")[0].strip()


def pre_send(event: dict, env=None, urlopen=urllib.request.urlopen, now=None) -> dict | None:
    """The hook's answer: a refusal (a dict for Claude Code), or None to let the call through. Refuses only a
    message to a conversation known to be a GROUP that has no @name, whose @name is no member, or that would be
    the REQUEST_CAP+1st awaited there; anything unknown is let through."""
    inp = event.get("tool_input") or {}
    text, conv = inp.get("content"), _endpoint_conversation(str(inp.get("endpoint") or ""))
    if not isinstance(text, str) or not conv:
        return None
    now = time.time() if now is None else now
    deny = lambda why: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",   # noqa: E731
                                                "permissionDecisionReason": why}}
    try:
        state = load(env)                         # no lock held over the network read: what is read is written once
        org = _org_of(env, str(inp.get("orgId") or ""))
        known = conv in state["types"]
        kind = _conversation_type(state, env, org, conv, urlopen)
        members = None
        if kind == "GROUP" and bridge._AT_NAME.search(text):
            members = _members(state, env, org, conv, urlopen, now)
        if (kind and not known) or members is not None:
            with _lock(env, wait=True):
                fresh = load(env)
                fresh["types"].update(state["types"])
                fresh["members"].update(state["members"])
                save(fresh, env)
    except Exception as e:
        _log(env, f"pre-send unchecked: {type(e).__name__}")
        return None
    if kind != "GROUP":
        return None
    open_here = [r for r in state["requests"] if r["conversation_id"] == conv and now < r["final"]]
    if len(open_here) >= REQUEST_CAP:
        return deny(f"request_cap: {len(open_here)} requests are still awaited in this conversation (at most {REQUEST_CAP} "
                    "in 24 hours). Close the finished ones (`bridge_hooks.py list`, `close ID`) or ask the owner.")
    if not bridge._AT_NAME.search(text):
        return deny(NO_MENTION)
    if members and bridge.unknown_mentions(text, members):
        return deny("unknown_mention: the @name after the @ is not a member of this group, so it would wake no one. "
                    "Members: " + ", ".join(str(m.get("display_name")) for m in members))
    return None


def _sent_id(response) -> str:
    """The message id in a comm_send result, whatever the wrapping (a dict, a list of text blocks, a string)."""
    blob = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
    m = re.search(r'messageId\\*"?\s*[:=]\s*\\*"?([0-9A-Za-z_-]+)', blob)
    return m.group(1) if m else ""


def post_send(event: dict, env=None, now=None) -> None:
    """Write the sent message to the pending file. Offline: the anchor is read at the first turn."""
    inp = event.get("tool_input") or {}
    sent, conv = _sent_id(event.get("tool_response")), _endpoint_conversation(str(inp.get("endpoint") or ""))
    if not sent or not conv:
        return
    now = time.time() if now is None else now
    org = _org_of(env, str(inp.get("orgId") or ""))
    with _lock(env, wait=True):
        state = load(env)
        if any(r["id"] == sent and r["conversation_id"] == conv for r in state["requests"]):
            return
        state["requests"].append({"id": sent, "conversation_id": conv, "org_id": org, "asked_at": now,
                                  "due": now + DUE_AFTER, "final": now + FINAL_AFTER, "cursor": None,
                                  "anchor": None, "last_poll": 0, "delivered": 0,
                                  "session_id": str(event.get("session_id") or ""), "held": [], "held_at": 0})
        if event.get("session_id"):
            state["sessions"][str(event["session_id"])] = now
        save(state, env)


def _matches(m: dict, req: dict) -> str:
    """'' when the message is not for us; else why it is: reply, mention, asked or person."""
    a = req["anchor"]
    if m.get("sender_id") == a["sender_id"]:
        return ""
    if str(m.get("parent_id") or "") == req["id"]:
        return "reply"
    if a["sender_id"] in {x.get("mentioned_id") for x in (m.get("mentions") or []) if isinstance(x, dict)}:
        return "mention"
    if m.get("sender_id") in a["asked"]:
        return "asked"
    if str(m.get("sender_type") or "").upper() == "HUMAN":
        return "person"
    return ""


_LABEL = {"reply": "a reply to your message", "mention": "mentions you", "asked": "the agent you asked",
          "person": "a person in the group (to read)"}


def _read_request(req: dict, state, env, urlopen, now: float) -> list:
    """New matching messages for one request, advancing its cursor past everything read."""
    authed, prefix = _authed(env, req["org_id"], urlopen)
    base = f"{prefix}/conversations/{req['conversation_id']}/messages"
    if not req["anchor"]:
        d = bridge._unwrap(authed("GET", f"{base}/{req['id']}"))
        msg = d.get("message") if isinstance(d, dict) else None
        if not isinstance(msg, dict) or not isinstance(msg.get("seq"), int):
            raise bridge.RestError("the sent message cannot be read")
        req["anchor"] = {"seq": msg["seq"], "sender_id": str(msg.get("sender_id")),
                         "asked": [x.get("mentioned_id") for x in (msg.get("mentions") or []) if isinstance(x, dict)]}
        req["cursor"] = msg["seq"]
    out = []
    for _ in range(MAX_PAGES):
        page = bridge._unwrap(authed("GET", f"{base}?after_seq={req['cursor']}&limit=100"))
        page = page if isinstance(page, list) else []
        for m in sorted((x for x in page if isinstance(x.get("seq"), int)), key=lambda x: x["seq"]):
            why = _matches(m, req)
            if why:
                out.append(bridge.Reply(str(m.get("id")), m["seq"], str(m.get("sender_id")),
                                        bridge._text_of(m.get("content")), _LABEL[why]))
            req["cursor"] = max(req["cursor"], m["seq"])
        if len(page) < 100:
            break
    held = req.get("held", []) + [dataclasses.asdict(r) | {"text": bridge.redact_secrets(r.text)} for r in out]
    if out:
        req["held_at"] = now
    if not held or now - req.get("held_at", 0) < QUIET_FOR:     # one answer often comes as several messages: wait for the lull
        req["held"] = held
        return []
    req["held"] = []
    replies = [bridge.Reply(**x) for x in held]
    try:                                                          # best effort: what was handed over is marked read
        authed("POST", f"{prefix}/conversations/{req['conversation_id']}/read", {"read_until_seq": max(r.seq for r in replies)})
    except Exception as e:
        _log(env, f"mark-read failed: {type(e).__name__}")
    return replies


def deliver(env=None, now=None, urlopen=urllib.request.urlopen, force: bool = False, session_id: str = "") -> str:
    """The text to hand the session: new replies as untrusted data, and a line on what is still awaited.
    '' when there is nothing. Reads at most every POLL_EVERY seconds per request; skips if another session holds the lock.
    A request belongs to the session that sent it: another session reads it only once that one has ended
    (`end_session`) or has run no hook for SESSION_IDLE seconds."""
    now = time.time() if now is None else now
    with _lock(env, wait=False) as got:
        if not got:
            return ""
        state = load(env)
        blocks = []
        kept = [r for r in state["requests"] if now < r["final"]]                   # past its final deadline: dropped
        changed = len(kept) != len(state["requests"])
        state["requests"] = kept
        if session_id:
            state["sessions"][session_id] = now
            changed = True
        for req in state["requests"][:MAX_REQUESTS_PER_RUN]:
            owner = req.get("session_id") or ""
            if owner and session_id and owner != session_id and now - state["sessions"].get(owner, 0) <= SESSION_IDLE:
                continue                                  # another live session sent it: it is that session's reply
            if not force and now - req["last_poll"] < POLL_EVERY:
                continue
            req["last_poll"], changed = now, True
            try:
                replies = _read_request(req, state, env, urlopen, now)
            except Exception as e:
                _log(env, f"read of {req['id']} failed: {type(e).__name__}")
                continue
            if replies:
                req["delivered"] += len(replies)
                blocks.append(bridge.wrap_untrusted(replies, request=f"your message {req['id']}"))
        if changed:
            save(state, env)
    return "\n\n".join(blocks)


def end_session(event: dict, env=None) -> None:
    """The session is over: its requests may be read by the next session that starts."""
    sid = str(event.get("session_id") or "")
    if not sid:
        return
    with _lock(env, wait=True):
        st = load(env)
        st["sessions"][sid] = 0
        save(st, env)


def awaiting(env=None, now=None) -> list[str]:
    """One line per request still awaited, for `list` and for the start of a session."""
    now = time.time() if now is None else now
    out = []
    for r in load(env)["requests"]:
        if now >= r["final"]:
            continue
        age = int((now - r["asked_at"]) // 60)
        state = "overdue" if now > r["due"] else "waiting"
        out.append(f"{r['id']} in {r['conversation_id']}: {state}, {age} min, {r['delivered']} delivered")
    return out


def close(request_id: str, env=None) -> bool:
    with _lock(env, wait=True):
        st = load(env)
        keep = [r for r in st["requests"] if r["id"] != request_id]
        if len(keep) == len(st["requests"]):
            return False
        st["requests"] = keep
        save(st, env)
    return True


def settings_snippet(path: str | None = None) -> dict:
    """The `hooks` block to merge into Claude Code's settings (user level: every session, every project)."""
    me = str(Path(path or __file__).resolve())
    def cmd(verb):
        return {"type": "command", "command": f"python3 {me} {verb}", "timeout": 10}
    return {"hooks": {
        "PreToolUse": [{"matcher": SEND_TOOL, "hooks": [cmd("pre-send")]}],
        "PostToolUse": [{"matcher": SEND_TOOL, "hooks": [cmd("post-send")]}],
        "UserPromptSubmit": [{"hooks": [cmd("turn")]}],
        "SessionStart": [{"hooks": [cmd("session")]}],
        "SessionEnd": [{"hooks": [cmd("end")]}],
    }}


# --- the command line ----------------------------------------------------------------------------

def _context(event_name: str, text: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}}


def main(argv=None, stdin=None, stdout=None, env=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    verb = argv[0] if argv else ""
    try:
        if verb == "install-snippet":
            stdout.write(json.dumps(settings_snippet(), indent=2) + "\n")
        elif verb == "list":
            stdout.write("\n".join(awaiting(env)) + "\n" if awaiting(env) else "nothing awaited\n")
        elif verb == "close" and len(argv) > 1:
            stdout.write("closed\n" if close(argv[1], env) else "not found\n")
        elif verb in ("pre-send", "post-send", "turn", "session", "end"):
            try:
                event = json.loads(stdin.read() or "{}")
            except ValueError:
                event = {}
            if verb == "pre-send":
                answer = pre_send(event, env)
                if answer:
                    stdout.write(json.dumps(answer))
            elif verb == "post-send":
                post_send(event, env)
            elif verb == "end":
                end_session(event, env)
            else:
                text = deliver(env, force=(verb == "session"), session_id=str(event.get("session_id") or ""))
                if verb == "session":
                    aw = awaiting(env)
                    if aw:
                        text = (text + "\n\n" if text else "") + "[OpenMax: requests still awaited]\n" + "\n".join(aw)
                if text:
                    stdout.write(json.dumps(_context("SessionStart" if verb == "session" else "UserPromptSubmit", text)))
        else:
            sys.stderr.write("usage: bridge_hooks.py pre-send|post-send|turn|session|end|list|close ID|install-snippet\n")
            return 2
    except Exception as e:                       # a hook never fails the session
        _log(env, f"{verb} failed: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
