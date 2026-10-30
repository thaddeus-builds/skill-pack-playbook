"""A skill pack's own model calls: one small client for the small closed steps whose answer the pack's code can check, with the vendor, the
key, the model and the money all set outside the code. Stdlib only (urllib).

Written from two clients that two skill packs built apart and that came out the same shape (a pack that judges evidence in video scripts, a pack
that classifies pages): settings from the host's env, no model built in, a price row per model, a log line for every call, a daily cap that
refuses before anything is sent, the key never printed or logged, retries on 429, 5xx and network faults. Nothing in it knows either pack.

    s = settings("review", TASKS)                      the task's route from <PREFIX>_AI_* (the env chain, files included), or a refusal that names the variable
    r = ask(s, system, text, images=(), schema=None, effort=None, prices=P, ledger=L, budget=B)
    j = ask_json(s, system, text, schema, ...)         the same, for one JSON object: the schema mode where the vendor has it, else "ask again once"
    count_tokens(s, system, text)                      Anthropic's free count; no other vendor's
    prices_from_rows(rows)                             {model: (input, output) USD per million tokens} from a pack's TSV rows
    Ledger(path)  .append(entry) .rows() .spent(day) .usage(day)         the call log, one JSON line a call, append-only
    Budget(daily_usd, run_usd=None)                    the two caps the pack resolved (a client's value may only lower: `lowered`)

Variables, with the pack's `env_prefix` P:

    P_AI_API_KEY               the secret: never printed, never logged, replaced by <key> in every error
    P_AI_PROTOCOL              anthropic (Messages API) | openai (chat completions); default anthropic
    P_AI_BASE_URL              the vendor's address: https, or a loopback host. No vendor is built in, as no model is: the pack may pass `default_base`
    P_AI_MODEL                 the model of every task; P_AI_MODEL_<TASK> one task's own. No model is built in: a task with none refuses and names the variable
    P_AI_DAILY_CAP_USD         read by `env_cap()` for the pack to combine with its own number; the kit never applies it by itself

What it guards:

  * Nothing is sent when a setting is missing or bad, when the model has no price, or when a cap would be passed; each refusal is coded and names
    the variable or the file to change. The base URL is https (or a loopback host, for a gateway or a test) and holds no credentials.
  * A model with no price is refused by default (`unpriced="refuse"`): the cap could not count it. A pack that wants the call anyway says
    `unpriced="log"`; the call is then logged with a null cost, counted as nothing, and `usage()` says how many calls were unpriced.
  * The daily cap counts the priced cost in the ledger for the UTC day. A call is refused before it is sent once the day's cost has reached the
    cap, or when the day's cost plus this call's estimate (the prompt counted high, the answer at `max_tokens`) would pass it; `run_usd` is the same
    for one run. The cap is counted from the log, never kept as a counter a crash could leave behind.
  * Every call, a failed one too, appends one line: time, task, model, protocol, host, status, tokens, cost (null when unpriced: never guessed),
    milliseconds, attempts, the prompt's sha256 and length (the text is not kept) and the images' sha256. The file is 0600.
  * 429, 5xx and network faults are retried (`BACKOFF_S`, a `retry-after` honoured up to `MAX_RETRY_AFTER_S`); any other 4xx stops at once. The
    key is replaced in every message that leaves this module.
  * `ask_json` asks for the schema mode where the protocol has one; a vendor that refuses it (HTTP 400) or answers with text that is not one JSON
    object is asked once more, with the instruction in words. The model judges, the code verifies: what the object means is the pack's check.

Test: kit/tests/test_ai.py (a loopback fake server; no network).
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping

from kit import config as _config
from kit import dates as _dates
from kit import env as _env
from kit.contract import SkillPackError
from kit.messages import msg

PROTOCOLS = ("anthropic", "openai")
ANTHROPIC_VERSION = "2023-06-01"
LOOPBACK = ("localhost", "127.0.0.1", "::1")
BACKOFF_S = (1.0, 2.0, 4.0)            # waits before the 2nd, 3rd and 4th try: at most four tries a call
MAX_RETRY_AFTER_S = 30.0
TIMEOUT_S = 120.0
UNPRICED = ("refuse", "log")
_IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}


def _fail(m, *next_: str) -> SkillPackError:
    return SkillPackError(m, list(next_))


@dataclass(frozen=True)
class Settings:
    key: str = field(repr=False)
    base_url: str
    protocol: str
    model: str
    task: str

    @property
    def host(self) -> str:
        return urllib.parse.urlsplit(self.base_url).netloc


@dataclass
class Reply:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    model: str
    ms: int
    cost_usd: float | None = None
    attempts: int = 1
    task: str = ""
    stop_reason: str | None = None


@dataclass(frozen=True)
class Budget:
    daily_usd: float
    run_usd: float | None = None


def redact(text, key: str | None = None) -> str:
    """`text` with the API key replaced: the one given, else the configured one (a message that leaves this module never holds it)."""
    s = str(text)
    try:
        k = key if key is not None else _get(_name("API_KEY"))
    except Exception:                      # nothing bound: there is no configured key to hide
        k = key
    return s.replace(k, "<key>") if k else s


# ---------------- settings ----------------

def _name(suffix: str) -> str:
    return _config.config().env(f"AI_{suffix}")


def _get(name: str) -> str | None:
    try:
        return _env.chain().get(name)
    except Exception:                      # no bound skill pack (a tool run outside one): the process env is all there is
        return os.environ.get(name)


def settings(task: str, tasks: Iterable[str], *, default_base: str | None = None, get: Callable[[str], str | None] | None = None) -> Settings:
    """The route of `task` from the env chain (files included: a command that did not load them would see no key and stay silently off), or a
    refusal that names the variable to set. `tasks` is the pack's closed list of task names; `default_base` is the address a pack that has one vendor
    in mind may name for a host that sets none."""
    tasks = tuple(tasks)
    get = get or _get
    if task not in tasks:
        raise _fail(msg("ai_config_invalid", f"unknown AI task {task!r} (tasks: {', '.join(tasks)}); nothing was sent", var="task",
                        detail=f"one of {', '.join(tasks)}"))
    key_var = _name("API_KEY")
    key = (get(key_var) or "").strip()
    if not key:
        raise _fail(msg("ai_config_missing", f"set {key_var} in the host's .env (the vendor's API key); nothing was sent", var=key_var),
                    f"add {key_var}=… to the host's .env")
    proto_var = _name("PROTOCOL")
    protocol = (get(proto_var) or "anthropic").strip().lower()
    if protocol not in PROTOCOLS:
        raise _fail(msg("ai_config_invalid", f"{proto_var} is {' or '.join(PROTOCOLS)} (got {protocol!r}); nothing was sent", var=proto_var,
                        detail=f"one of {', '.join(PROTOCOLS)}"))
    base_var = _name("BASE_URL")
    base = (get(base_var) or default_base or "").strip()
    if not base:
        raise _fail(msg("ai_config_missing", f"set {base_var} (the vendor's address): no vendor is built in; nothing was sent", var=base_var),
                    f"add {base_var}=https://… to the host's .env")
    base = base.rstrip("/")
    u = urllib.parse.urlsplit(base)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query:
        raise _fail(msg("ai_config_invalid", f"{base_var} is a plain http(s) URL without credentials or a query; nothing was sent", var=base_var,
                        detail="a plain http(s) URL"))
    if u.scheme == "http" and u.hostname not in LOOPBACK:
        raise _fail(msg("ai_config_invalid", f"{base_var} must be https (the key would travel in the clear); nothing was sent", var=base_var,
                        detail="https, or a loopback host"))
    own, every = _name(f"MODEL_{task.upper()}"), _name("MODEL")
    model = (get(own) or get(every) or "").strip()
    if not model:
        raise _fail(msg("ai_config_missing", f"set {own} (this task) or {every} (every task): no model is built in; nothing was sent", var=own),
                    f"add {own}=<model name> or {every}=<model name> to the host's .env")
    return Settings(key=key, base_url=base, protocol=protocol, model=model, task=task)


def env_cap(*, get: Callable[[str], str | None] | None = None) -> float | None:
    """`P_AI_DAILY_CAP_USD` as a number of dollars above 0, None when unset; a bad value is refused. The pack decides whether it may raise its own
    cap or only lower it (`lowered`)."""
    var = _name("DAILY_CAP_USD")
    raw = (get or _get)(var)
    if raw in (None, ""):
        return None
    try:
        v = float(raw)
    except ValueError:
        v = float("nan")
    if not (v > 0 and v != float("inf")):
        raise _fail(msg("ai_config_invalid", f"{var} is a number of US dollars above 0", var=var, detail="a number above 0"))
    return v


def lowered(base: float, own: float | None) -> float:
    """The cap a client's own value may only lower, never raise: `base` when `own` is None or higher."""
    return base if own is None or own >= base else own


# ---------------- prices, the ledger, the cap ----------------

def prices_from_rows(rows: Iterable[Mapping[str, str]]) -> dict[str, tuple[float, float]]:
    """{model: (input, output)} USD per million tokens, from TSV rows with `model`, `input_per_mtok_usd` and `output_per_mtok_usd`. A row with
    either price blank is left out (an unknown price is never zero); a number that is not one, or below 0, is refused."""
    out: dict[str, tuple[float, float]] = {}
    for r in rows:
        model, pin, pout = (r.get("model") or "").strip(), (r.get("input_per_mtok_usd") or "").strip(), (r.get("output_per_mtok_usd") or "").strip()
        if not model or not pin or not pout:
            continue
        try:
            a, b = float(pin), float(pout)
        except ValueError:
            a = b = -1.0
        if not (a >= 0 and b >= 0):
            raise _fail(msg("ai_config_invalid", f"the price row of {model} holds a number that is not one (USD per million tokens, 0 or more)",
                            var="model prices", detail=model))
        out[model] = (a, b)
    return out


def cost_usd(prices: Mapping[str, tuple[float, float]] | None, model: str, tokens_in: int | None, tokens_out: int | None) -> float | None:
    """The cost of one call, or None when the model has no price or a token count is missing (never a guess)."""
    p = (prices or {}).get(model)
    if p is None or tokens_in is None or tokens_out is None:
        return None
    return round((tokens_in * p[0] + tokens_out * p[1]) / 1_000_000, 6)


def today() -> str:
    return _dates.today().isoformat()


class Ledger:
    """The call log: one JSON line a call, append-only, 0600. The day's spend is the sum of what it holds, so a crash cannot leave a counter wrong."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    def append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n").encode())
        finally:
            os.close(fd)

    def rows(self) -> list[dict]:
        if not self.path.is_file():
            return []
        return [json.loads(ln) for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def spent(self, day: str | None = None) -> float:
        day = day or today()
        return round(sum(r.get("cost_usd") or 0.0 for r in self.rows() if str(r.get("at", ""))[:10] == day), 6)

    def usage(self, day: str | None = None) -> dict:
        """Totals for the UTC `day`: calls, failed calls, tokens, priced cost and the calls that had no price, per model and together."""
        day = day or today()
        per: dict[str, dict] = {}
        for r in (r for r in self.rows() if str(r.get("at", ""))[:10] == day):
            m = per.setdefault(r.get("model", ""), {"calls": 0, "failed": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "unpriced_calls": 0})
            m["calls"] += 1
            m["failed"] += r.get("status") != "ok"
            m["input_tokens"] += r.get("input_tokens") or 0
            m["output_tokens"] += r.get("output_tokens") or 0
            m["unpriced_calls"] += r.get("status") == "ok" and r.get("cost_usd") is None
            m["cost_usd"] = round(m["cost_usd"] + (r.get("cost_usd") or 0.0), 6)
        total = lambda k: sum(m[k] for m in per.values())  # noqa: E731
        return {"day": day, "calls": total("calls"), "failed": total("failed"), "input_tokens": total("input_tokens"),
                "output_tokens": total("output_tokens"), "cost_usd": round(total("cost_usd"), 6), "unpriced_calls": total("unpriced_calls"),
                "models": per, "log": str(self.path)}


def tokens_in_text(text: str) -> int:
    """A high count of a prompt's tokens: 4 ASCII characters a token, one token for every other character (CJK is about that); the real count
    comes back in the reply."""
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return -(-ascii_chars // 4) + (len(text) - ascii_chars) + 8


def estimate(s: Settings, system: str, text: str, max_tokens: int, prices: Mapping[str, tuple[float, float]] | None) -> tuple[int, float | None]:
    """(input tokens, USD) of one call: the prompt counted high, the answer at its cap; the USD is None for a model with no price."""
    tin = tokens_in_text(system) + tokens_in_text(text)
    return tin, cost_usd(prices, s.model, tin, max_tokens)


def check_budget(spent: float, est_usd: float | None, budget: Budget) -> None:
    """Refuse before sending: the run cap against the estimate, the daily cap against what was spent (reached) and what was spent plus the estimate."""
    est = est_usd or 0.0
    if budget.run_usd is not None and est > budget.run_usd:
        raise _fail(msg("ai_run_cap_exceeded", f"estimated ${est:.4f} exceeds the run cap ${budget.run_usd:.2f}; nothing was sent",
                        estimated_usd=f"{est:.4f}", cap_usd=f"{budget.run_usd:.2f}"), "do fewer calls in one run, or use a cheaper model")
    if spent >= budget.daily_usd or spent + est > budget.daily_usd:
        raise _fail(msg("ai_daily_cap_exceeded", f"today's AI calls cost ${spent:.4f}, this one about ${est:.4f} more; the daily cap is "
                        f"${budget.daily_usd:.2f}; nothing was sent", spent_usd=f"{spent:.4f}", estimated_usd=f"{est:.4f}",
                        cap_usd=f"{budget.daily_usd:.2f}"), "wait for tomorrow (UTC), or a person raises the cap")


# ---------------- the protocols ----------------

def _image(path) -> tuple[str, str, str]:
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as e:
        raise _fail(msg("ai_image_unreadable", f"{p}: cannot read the image ({e.strerror}); nothing was sent", path=str(p))) from None
    mime = _IMAGE_TYPES.get(p.suffix.lower()) or mimetypes.guess_type(str(p))[0]
    if not mime or not mime.startswith("image/"):
        raise _fail(msg("ai_image_unreadable", f"{p}: not an image file; nothing was sent", path=str(p)))
    return mime, base64.standard_b64encode(data).decode(), hashlib.sha256(data).hexdigest()


def build_request(s: Settings, system: str, text: str, images, max_tokens: int, schema: dict | None = None,
                  effort: str | None = None) -> tuple[str, dict, dict]:
    """(url, headers, body) of one call. `schema` makes the reply one JSON object of that JSON Schema (anthropic: output_config.format; openai:
    response_format json_schema); `effort` (low|medium|high|xhigh|max) is Anthropic's output_config.effort and is not sent on the openai
    protocol, whose vendors differ on it. No sampling parameter is sent."""
    blobs = [_image(p)[:2] for p in images]
    if s.protocol == "anthropic":
        content = [{"type": "image", "source": {"type": "base64", "media_type": m, "data": d}} for m, d in blobs] + [{"type": "text", "text": text}]
        body = {"model": s.model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": content}]}
        oc = {k: v for k, v in (("format", {"type": "json_schema", "schema": schema} if schema else None), ("effort", effort)) if v}
        if oc:
            body["output_config"] = oc
        url = s.base_url + ("/messages" if s.base_url.endswith("/v1") else "/v1/messages")
        headers = {"x-api-key": s.key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    else:
        content = [{"type": "image_url", "image_url": {"url": f"data:{m};base64,{d}"}} for m, d in blobs] + [{"type": "text", "text": text}]
        body = {"model": s.model, "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema, "strict": True}}
        url = s.base_url + ("/chat/completions" if s.base_url.endswith("/v1") else "/v1/chat/completions")
        headers = {"authorization": f"Bearer {s.key}", "content-type": "application/json"}
    return url, headers, body


def parse_response(s: Settings, doc) -> tuple[str, int | None, int | None, str | None]:
    """(text, input tokens, output tokens, stop reason) of a reply, or ai_bad_answer."""
    def bad(detail):
        return _fail(msg("ai_bad_answer", f"the {s.protocol} reply is not what the protocol says: {detail}", detail=detail))
    if not isinstance(doc, dict):
        raise bad("not a JSON object")
    u = doc.get("usage") if isinstance(doc.get("usage"), dict) else {}
    try:
        if s.protocol == "anthropic":
            text = "".join(b.get("text", "") for b in doc["content"] if isinstance(b, dict) and b.get("type") == "text")
            tin, tout, stop = u.get("input_tokens"), u.get("output_tokens"), doc.get("stop_reason")
        else:
            ch = doc["choices"][0]
            text = ch["message"]["content"]
            tin, tout, stop = u.get("prompt_tokens"), u.get("completion_tokens"), ch.get("finish_reason")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise bad("no content in it") from None
    if not isinstance(text, str) or not text.strip():
        raise bad("the content is not text")
    if stop in ("refusal", "max_tokens", "length", "content_filter"):
        raise bad(f"it stopped with {stop}")
    ints = [t if isinstance(t, int) and not isinstance(t, bool) else None for t in (tin, tout)]
    return text, ints[0], ints[1], stop if isinstance(stop, str) else None


def _once(s: Settings, url: str, headers: dict, body: dict, timeout: float):
    """(status, doc, retry_after) of one HTTP try; status 0 is a network fault (doc = the fault, redacted)."""
    r = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
        try:
            return 200, json.loads(raw), None
        except ValueError:
            return 200, None, None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        ra = e.headers.get("retry-after") if e.headers else None
        try:
            ra = min(float(ra), MAX_RETRY_AFTER_S) if ra else None
        except ValueError:
            ra = None
        return e.code, redact(detail, s.key), ra
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return 0, redact(str(getattr(e, "reason", e)), s.key)[:200], None


def _send(s: Settings, url: str, headers: dict, body: dict, timeout: float, sleep: Callable[[float], None]):
    """(status, doc, attempts, ms): the tries of one call, 429, 5xx and network faults retried."""
    t0 = time.monotonic()
    status, doc, attempts = 0, None, 0
    for attempts in range(1, len(BACKOFF_S) + 2):
        status, doc, retry_after = _once(s, url, headers, body, timeout)
        if status == 200 and doc is not None or not (status in (0, 429) or status >= 500) or attempts > len(BACKOFF_S):
            break
        sleep(retry_after if retry_after is not None else BACKOFF_S[attempts - 1])
    return status, doc, attempts, int((time.monotonic() - t0) * 1000)


# ---------------- the calls ----------------

def ask(s: Settings, system: str, text: str, images=(), *, max_tokens: int = 600, schema: dict | None = None, effort: str | None = None,
        prices: Mapping[str, tuple[float, float]] | None = None, ledger: Ledger | None = None, budget: Budget | None = None,
        unpriced: str = "refuse", timeout: float = TIMEOUT_S, sleep: Callable[[float], None] = time.sleep) -> Reply:
    """One call: refused before anything is sent when the model has no price (`unpriced="refuse"`) or a cap would be passed; retried on 429, 5xx
    and network faults; logged in the ledger whatever happens. A cap needs a ledger and a price for the model."""
    if unpriced not in UNPRICED:
        raise ValueError(f"unpriced is one of {', '.join(UNPRICED)}, not {unpriced!r}")
    images = list(images)
    known = s.model in (prices or {})
    if not known and (unpriced == "refuse" or budget is not None):
        raise _fail(msg("ai_model_unpriced", f"{s.model}: no price, so the cap could not count it; nothing was sent", model=s.model),
                    "add the model's list price to the pack's ai_prices.tsv, or use a priced model")
    url, headers, body = build_request(s, system, text, images, max_tokens, schema, effort)
    if budget is not None:
        if ledger is None:
            raise ValueError("a budget needs the ledger it is counted from")
        check_budget(ledger.spent(), estimate(s, system, text, max_tokens, prices)[1], budget)
    entry = {"at": _dates.now().isoformat(timespec="seconds"), "task": s.task, "model": s.model, "protocol": s.protocol,
             "host": s.host, "prompt_sha256": hashlib.sha256((system + "\n" + text).encode()).hexdigest(), "prompt_chars": len(system) + len(text),
             "images": [_image(p)[2] for p in images]}
    status, doc, attempts, ms = _send(s, url, headers, body, timeout, sleep)
    entry.update(ms=ms, attempts=attempts)

    def fail(err: SkillPackError, why: str) -> SkillPackError:
        if ledger is not None:
            ledger.append({**entry, "status": why, "input_tokens": None, "output_tokens": None, "cost_usd": None})
        return err

    if status == 0:
        raise fail(_fail(msg("ai_network_error", f"{s.host}: no answer after {attempts} tries ({doc}); is the base URL right?", detail=str(doc), host=s.host)),
                   "network")
    if status != 200:
        raise fail(_fail(msg("ai_http_error", f"{s.host} answered HTTP {status}: {doc}", status=status, detail=str(doc), host=s.host)), f"http_{status}")
    if doc is None:
        raise fail(_fail(msg("ai_bad_answer", f"{s.host} answered 200 with a body that is not JSON", detail="not JSON")), "bad_reply")
    try:
        out, tin, tout, stop = parse_response(s, doc)
    except SkillPackError as e:
        raise fail(e, "bad_reply") from None
    c = cost_usd(prices, s.model, tin, tout)
    if ledger is not None:
        ledger.append({**entry, "status": "ok", "input_tokens": tin, "output_tokens": tout, "cost_usd": c})
    return Reply(text=out, input_tokens=tin, output_tokens=tout, model=s.model, ms=ms, cost_usd=c, attempts=attempts, task=s.task, stop_reason=stop)


def unwrap_json(text: str):
    """The JSON object in a reply: strict, but a fenced block is unwrapped. None when it is not one object."""
    t = text.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", t, re.S)
    try:
        v = json.loads(m.group(1) if m else t)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


JSON_ONLY = "\n\nReply with one JSON object and nothing else: no prose, no code fence."


def ask_json(s: Settings, system: str, text: str, schema: dict, images=(), **kw) -> tuple[dict, Reply]:
    """One JSON object that fits `schema`'s shape, with the reply it came in. The schema mode is tried first; a vendor that refuses it (HTTP 400) or
    answers with text that is not one JSON object is asked once more with the instruction in words. The object's meaning is the pack's to check."""
    last: SkillPackError | None = None
    for mode in ("schema", "words"):
        try:
            r = ask(s, system + (JSON_ONLY if mode == "words" else ""), text, images, schema=schema if mode == "schema" else None, **kw)
        except SkillPackError as e:
            code = getattr(e.message, "code", "")
            if mode == "schema" and code in ("ai_http_error", "ai_bad_answer") and (code == "ai_bad_answer" or "HTTP 400" in str(e.message)):
                last = e
                continue
            raise
        obj = unwrap_json(r.text)
        if obj is not None:
            return obj, r
        last = _fail(msg("ai_json_invalid", "the reply is not one JSON object", detail=r.text[:80]))
    raise last or _fail(msg("ai_json_invalid", "the reply is not one JSON object", detail="none"))


def count_tokens(s: Settings, system: str, text: str, images=(), *, timeout: float = TIMEOUT_S, sleep: Callable[[float], None] = time.sleep) -> int:
    """The input tokens `ask` would send, by Anthropic's `messages/count_tokens` (free; counts against no cap and is not logged). Anthropic protocol only."""
    if s.protocol != "anthropic":
        proto_var = _name("PROTOCOL")
        raise _fail(msg("ai_config_invalid", f"count_tokens is Anthropic's endpoint; {proto_var} must be anthropic for it; nothing was sent", var=proto_var,
                        detail="anthropic for count_tokens"))
    url, headers, body = build_request(s, system, text, list(images), 1)
    status, doc, _, _ = _send(s, url + "/count_tokens", headers, {k: body[k] for k in ("model", "system", "messages")}, timeout, sleep)
    if status != 200 or not isinstance(doc, dict) or not isinstance(doc.get("input_tokens"), int):
        raise _fail(msg("ai_http_error", f"{s.host} count_tokens answered HTTP {status}: {doc}", status=status, detail=str(doc), host=s.host))
    return doc["input_tokens"]
