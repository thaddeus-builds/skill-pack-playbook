"""A skill pack's own model calls: one small client for the small closed steps whose answer the pack's code can check, with the vendor, the
key, the model and the money all set outside the code. Stdlib only (urllib).

Written from two clients that two skill packs built apart and that came out the same shape (a pack that judges evidence in video scripts, a pack
that classifies pages): settings from the host's env, no model built in, a price row per model, a log line for every call, a daily cap that
refuses before anything is sent, the key never printed or logged, retries on 429, 5xx and network faults. Nothing in it knows either pack.

    s = settings("review", TASKS)                      the task's route from <PREFIX>_AI_* (the env chain, files included), or a refusal that names the variable
    r = ask(s, system, text, images=(), schema=None, effort=None, prices=P, ledger=L, budget=B)
    j = ask_json(s, system, text, schema, ...)         the same, for one JSON object that fits the schema's required keys and types
    count_tokens(s, system, text)                      Anthropic's free count; no other vendor's
    prices_from_rows(rows)                             {model: (input, output) USD per million tokens} from a pack's TSV rows
    Ledger(path)  .spent(day) .usage(day) .rows()      the call log, one JSON line per event, append-only; a call reserves its estimate before it is sent
    Budget(daily_usd, run_usd=None)                    the two caps the pack resolved (a client's value may only lower: `lowered`); one Budget is one run

Variables, with the pack's `env_prefix` P:

    P_AI_API_KEY               the secret, printable ASCII: never printed, never logged, replaced by <key> in every error
    P_AI_PROTOCOL              anthropic (Messages API) | openai (chat completions); default anthropic
    P_AI_BASE_URL              the vendor's address: https, or a loopback host. No vendor is built in, as no model is: the pack may pass `default_base`
    P_AI_MODEL                 the model of every task; P_AI_MODEL_<TASK> one task's own. No model is built in: a task with none refuses and names the variable
    P_AI_DAILY_CAP_USD         read by `env_cap()` for the pack to combine with its own number; the kit never applies it by itself

What it guards (each is a test in kit/tests/test_ai.py; the last review of it was a cold one, and every finding is a case there):

  * Nothing is sent when a setting is missing or bad, when the model has no price, when `max_tokens` is not a whole number of at least 1, when the
    ledger cannot be appended to, or when a cap would be passed; each refusal is coded and names the variable or the file to change. The base URL is
    https (or a loopback host, for a gateway or a test), holds no credentials, no query, no fragment and a real port.
  * The key goes to the host in the base URL and nowhere else: a redirect is never followed (a 3xx is an error), a loopback call does not go through a
    proxy, and a key that is not printable ASCII is refused (it could not be sent as a header and would leak through the exception).
  * A model with no price is refused by default (`unpriced="refuse"`): the cap could not count it. A pack that wants the call anyway says
    `unpriced="log"`; the call is then logged with a null cost, counted as nothing, and `usage()` says how many calls were unpriced.
  * The cap is counted from the ledger for the UTC day, and holds under threads and processes: before it sends, a call takes a file lock, checks the
    day's cost plus its estimate (the prompt counted high, the answer at `max_tokens`) and writes a reservation of that estimate; the reply settles it. A
    reservation nobody settled (a crash) keeps counting. `run_usd` is per `Budget` object, so one object is one run, not one call.
  * A reply that was billed is booked as billed: a refusal or a cut-off carries its usage, a priced model whose reply has none is booked at the estimate.
    A number that is not finite, or a token count below 0, is never believed: a price is refused, a count is treated as unknown.
  * Every call, a failed one too, ends in one ledger line: time, task, model, protocol, host, status, tokens, cost (null when unpriced: never guessed),
    milliseconds, attempts, the prompt's sha256 and length (the text is not kept) and the images' sha256. The file is 0600.
  * 429, 5xx and a refused or dropped connection are retried (`BACKOFF_S`, a finite `retry-after` between 0 and `MAX_RETRY_AFTER_S` honoured); any other
    4xx stops at once, and a read timeout is not retried (the vendor may be working on, and billing, the first request). The key is replaced in every
    message that leaves this module, before a text is cut.
  * `ask_json` asks for the schema mode where the protocol has one; a vendor that refuses it (HTTP 400) or answers with text that is not one JSON
    object is asked once more, with the instruction in words; a reply that stopped on a refusal or the token limit is not asked again. The object must
    carry the schema's required keys with the right basic types. What it means is the pack's check: the model judges, the code verifies.

Test: kit/tests/test_ai.py (a loopback fake server; no network).
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import math
import mimetypes
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping

from kit import config as _config
from kit import dates as _dates
from kit import env as _env
from kit.contract import SkillPackError
from kit.messages import msg

try:
    import fcntl
except ImportError:                      # no POSIX file locks: one process at a time is all that is promised
    fcntl = None

PROTOCOLS = ("anthropic", "openai")
ANTHROPIC_VERSION = "2023-06-01"
LOOPBACK = ("localhost", "127.0.0.1", "::1")
BACKOFF_S = (1.0, 2.0, 4.0)            # waits before the 2nd, 3rd and 4th try: at most four tries a call
MAX_RETRY_AFTER_S = 30.0
TIMEOUT_S = 120.0
MAX_TOKENS_LIMIT = 1_000_000
UNPRICED = ("refuse", "log")
STOPPED = "it stopped with"
_IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _fail(m, *next_: str) -> SkillPackError:
    return SkillPackError(m, list(next_))


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


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


class Budget:
    """The two caps one run works under. `daily_usd` is the day's, counted from the ledger; `run_usd` (or None) is this object's own: what its calls have
    reserved or spent, so one Budget is one run. Both are finite and above 0."""

    def __init__(self, daily_usd: float, run_usd: float | None = None):
        for name, v in (("daily_usd", daily_usd), ("run_usd", run_usd)):
            if v is not None and not (_finite(v) and v > 0):
                raise ValueError(f"Budget {name} is a finite number of dollars above 0, not {v!r}")
        self.daily_usd, self.run_usd, self.used_usd = float(daily_usd), None if run_usd is None else float(run_usd), 0.0
        self._lock = threading.Lock()

    def charge(self, est: float) -> None:
        with self._lock:
            self.used_usd += est

    def settle(self, est: float, actual: float) -> None:
        with self._lock:
            self.used_usd = max(0.0, self.used_usd + actual - est)


def redact(text, key: str | None = None) -> str:
    """`text` with the API key replaced: the one given, else the configured one (a message that leaves this module never holds it)."""
    s = str(text)
    try:
        k = key if key is not None else _get(_name("API_KEY"))
    except Exception:                      # nothing bound: there is no configured key to hide
        k = key
    if not k:
        return s
    for form in {k, k.encode("unicode_escape").decode("ascii"), repr(k)[1:-1]}:        # the key as typed and as an exception message escapes it
        s = s.replace(form, "<key>")
    return s


# ---------------- settings ----------------

def _name(suffix: str) -> str:
    try:
        return _config.config().env(f"AI_{suffix}")
    except _config.ConfigError:
        raise _fail(msg("aicall_config_invalid", "no skill pack is bound, so the variable names (the pack's env_prefix) are unknown; nothing was sent",
                        var="skill-pack.toml", detail="a bound skill pack")) from None


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
        raise _fail(msg("aicall_config_invalid", f"unknown AI task {task!r} (tasks: {', '.join(tasks)}); nothing was sent", var="task",
                        detail=f"one of {', '.join(tasks)}"))
    key_var = _name("API_KEY")
    key = (get(key_var) or "").strip()
    if not key:
        raise _fail(msg("aicall_config_missing", f"set {key_var} in the host's .env (the vendor's API key); nothing was sent", var=key_var),
                    f"add {key_var}=… to the host's .env")
    if not (key.isascii() and key.isprintable() and " " not in key):
        raise _fail(msg("aicall_config_invalid", f"{key_var} holds a character that cannot be sent in a header; nothing was sent", var=key_var,
                        detail="printable ASCII with no space"))
    proto_var = _name("PROTOCOL")
    protocol = (get(proto_var) or "anthropic").strip().lower()
    if protocol not in PROTOCOLS:
        raise _fail(msg("aicall_config_invalid", f"{proto_var} is {' or '.join(PROTOCOLS)} (got {protocol!r}); nothing was sent", var=proto_var,
                        detail=f"one of {', '.join(PROTOCOLS)}"))
    base_var = _name("BASE_URL")
    base = (get(base_var) or default_base or "").strip()
    if not base:
        raise _fail(msg("aicall_config_missing", f"set {base_var} (the vendor's address): no vendor is built in; nothing was sent", var=base_var),
                    f"add {base_var}=https://… to the host's .env")
    base = base.rstrip("/")
    bad_url = _fail(msg("aicall_config_invalid", f"{base_var} is a plain http(s) URL without credentials, a query or a fragment; nothing was sent",
                        var=base_var, detail="a plain http(s) URL"))
    try:
        u = urllib.parse.urlsplit(base)
        port = u.port                                               # raises on a port that is not one
    except ValueError:
        raise bad_url from None
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment or "#" in base or "?" in base:
        raise bad_url
    if port is not None and not 0 < port < 65536:
        raise bad_url
    if u.scheme == "http" and u.hostname not in LOOPBACK:
        raise _fail(msg("aicall_config_invalid", f"{base_var} must be https (the key would travel in the clear); nothing was sent", var=base_var,
                        detail="https, or a loopback host"))
    own, every = _name(f"MODEL_{task.upper()}"), _name("MODEL")
    model = (get(own) or get(every) or "").strip()
    if not model:
        raise _fail(msg("aicall_config_missing", f"set {own} (this task) or {every} (every task): no model is built in; nothing was sent", var=own),
                    f"add {own}=<model name> or {every}=<model name> to the host's .env")
    return Settings(key=key, base_url=base, protocol=protocol, model=model, task=task)


def env_cap(*, get: Callable[[str], str | None] | None = None) -> float | None:
    """`P_AI_DAILY_CAP_USD` as a finite number of dollars above 0, None when unset; a bad value is refused. The pack decides whether it may raise its own
    cap or only lower it (`lowered`)."""
    var = _name("DAILY_CAP_USD")
    raw = (get or _get)(var)
    if raw in (None, ""):
        return None
    try:
        v = float(raw)
    except ValueError:
        v = float("nan")
    if not (_finite(v) and v > 0):
        raise _fail(msg("aicall_config_invalid", f"{var} is a number of US dollars above 0", var=var, detail="a number above 0"))
    return v


def lowered(base: float, own: float | None) -> float:
    """The cap a client's own value may only lower, never raise: `base` when `own` is None, not a finite number or higher."""
    return base if own is None or not _finite(own) or own >= base else own


# ---------------- prices, the ledger, the cap ----------------

def prices_from_rows(rows: Iterable[Mapping[str, str]]) -> dict[str, tuple[float, float]]:
    """{model: (input, output)} USD per million tokens, from TSV rows with `model`, `input_per_mtok_usd` and `output_per_mtok_usd`. A row with
    either price blank is left out (an unknown price is never zero); a number that is not finite, or below 0, is refused."""
    out: dict[str, tuple[float, float]] = {}
    for r in rows:
        model, pin, pout = (r.get("model") or "").strip(), (r.get("input_per_mtok_usd") or "").strip(), (r.get("output_per_mtok_usd") or "").strip()
        if not model or not pin or not pout:
            continue
        try:
            a, b = float(pin), float(pout)
        except ValueError:
            a = b = -1.0
        if not (_finite(a) and _finite(b) and a >= 0 and b >= 0):
            raise _fail(msg("aicall_config_invalid", f"the price row of {model} holds a number that is not a finite price (USD per million tokens, 0 or more)",
                            var="model prices", detail=f"{model}: a finite number 0 or more"))
        out[model] = (a, b)
    return out


def _count(v) -> int | None:
    """A token count: a whole number of 0 or more, else None (unknown)."""
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def cost_usd(prices: Mapping[str, tuple[float, float]] | None, model: str, tokens_in, tokens_out) -> float | None:
    """The cost of one call, or None when the model has no price or a token count is missing or not a count (never a guess)."""
    p = (prices or {}).get(model)
    tin, tout = _count(tokens_in), _count(tokens_out)
    if p is None or tin is None or tout is None:
        return None
    return round((tin * p[0] + tout * p[1]) / 1_000_000, 6)


def today() -> str:
    return _dates.today().isoformat()


class Ledger:
    """The call log: one JSON line per event, append-only, 0600. The day's spend is counted from it, so a crash cannot leave a counter wrong, and it
    holds across threads and processes because a call reserves its estimate under a file lock before it is sent (`reserve`) and the reply settles it
    (a line with the same `id`). A reservation no line settled keeps counting at its estimate."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self._tlock = threading.Lock()

    @contextlib.contextmanager
    def _locked(self):
        with self._tlock:
            if fcntl is None:
                yield
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self.path) + ".lock", os.O_WRONLY | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                os.close(fd)

    def check_writable(self) -> None:
        """Refuse before sending when a line could not be appended afterwards: a call that is billed and cannot be booked is never repeated for free."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            os.close(os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600))
        except OSError as e:
            raise _fail(msg("aicall_config_invalid", f"{self.path}: the call log cannot be appended to ({e.strerror}); nothing was sent", var="call log",
                            detail="a file this process can append to")) from None

    def append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (json.dumps(entry, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode())
        finally:
            os.close(fd)

    def reserve(self, entry: dict, est_usd: float, budget: Budget) -> str:
        """Under the file lock: check the day's cost and the run's against this call's estimate, and write a reservation of the estimate. Returns the
        id the settling line carries. Refuses (coded) when a cap would be passed; nothing is written then."""
        with self._locked():
            check_budget(self.spent(), est_usd, budget)
            rid = uuid.uuid4().hex
            self.append({**entry, "id": rid, "status": "reserved", "cost_usd": est_usd, "input_tokens": None, "output_tokens": None})
            budget.charge(est_usd)
            return rid

    def rows(self) -> list[dict]:
        """The lines of the log; a line that is cut off or not an object (a crash mid-write) is left out, and `usage()` counts it."""
        return self._read()[0]

    def _read(self) -> tuple[list[dict], int]:
        if not self.path.is_file():
            return [], 0
        rows, bad = [], 0
        for ln in self.path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                r = json.loads(ln)
            except (ValueError, RecursionError):
                bad += 1
                continue
            if isinstance(r, dict):
                rows.append(r)
            else:
                bad += 1
        return rows, bad

    @staticmethod
    def _settled(rows: list[dict]) -> list[dict]:
        """One row per call: the settling line where there is one, else the reservation. A line with no `id` stands for itself."""
        final: dict[str, dict] = {}
        out: list[dict] = []
        for r in rows:
            rid = r.get("id")
            if not isinstance(rid, str):
                out.append(r)
            elif r.get("status") != "reserved" or rid not in final:
                final[rid] = r
        return out + list(final.values())

    def spent(self, day: str | None = None) -> float:
        day = day or today()
        total = 0.0
        for r in self._settled(self._read()[0]):
            at, c = r.get("at"), r.get("cost_usd")
            if isinstance(at, str) and _DAY.match(at) and at[:10] == day and _finite(c) and c > 0:
                total += c
        return round(total, 6)

    def usage(self, day: str | None = None) -> dict:
        """Totals for the UTC `day`: calls, failed calls, tokens, priced cost and the calls that had no price, per model and together; `unreadable_lines`
        counts lines of the log that could not be read."""
        day = day or today()
        rows, bad = self._read()
        per: dict[str, dict] = {}
        for r in (r for r in self._settled(rows) if isinstance(r.get("at"), str) and r["at"][:10] == day):
            m = per.setdefault(r.get("model", ""), {"calls": 0, "failed": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "unpriced_calls": 0})
            m["calls"] += 1
            m["failed"] += r.get("status") not in ("ok", "reserved")
            m["input_tokens"] += _count(r.get("input_tokens")) or 0
            m["output_tokens"] += _count(r.get("output_tokens")) or 0
            m["unpriced_calls"] += r.get("status") == "ok" and r.get("cost_usd") is None
            c = r.get("cost_usd")
            m["cost_usd"] = round(m["cost_usd"] + (c if _finite(c) and c > 0 else 0.0), 6)
        total = lambda k: sum(m[k] for m in per.values())  # noqa: E731
        return {"day": day, "calls": total("calls"), "failed": total("failed"), "input_tokens": total("input_tokens"),
                "output_tokens": total("output_tokens"), "cost_usd": round(total("cost_usd"), 6), "unpriced_calls": total("unpriced_calls"),
                "models": per, "log": str(self.path), "unreadable_lines": bad}


def tokens_in_text(text: str) -> int:
    """A count of a prompt's tokens that errs high for prose: 4 ASCII characters a token, one token for every other character (CJK is about that); the
    real count comes back in the reply. It does not see images, and dense text (code, base64) can have more tokens than this."""
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return -(-ascii_chars // 4) + (len(text) - ascii_chars) + 8


def estimate(s: Settings, system: str, text: str, max_tokens: int, prices: Mapping[str, tuple[float, float]] | None) -> tuple[int, float | None]:
    """(input tokens, USD) of one call: the prompt counted high, the answer at its cap; the USD is None for a model with no price."""
    tin = tokens_in_text(system) + tokens_in_text(text)
    return tin, cost_usd(prices, s.model, tin, max_tokens)


def check_budget(spent: float, est_usd: float | None, budget: Budget) -> None:
    """Refuse before sending: this run's reserved and spent cost plus the estimate against the run cap, and the day's cost (reached, or with the
    estimate) against the daily cap."""
    est = est_usd or 0.0
    if budget.run_usd is not None and budget.used_usd + est > budget.run_usd:
        raise _fail(msg("aicall_run_cap_exceeded", f"this run has used ${budget.used_usd:.4f} and this call is estimated at ${est:.4f}, over the run cap "
                        f"${budget.run_usd:.2f}; nothing was sent", estimated_usd=f"{budget.used_usd + est:.4f}", cap_usd=f"{budget.run_usd:.2f}"),
                    "do fewer calls in one run, or use a cheaper model")
    if spent >= budget.daily_usd or spent + est > budget.daily_usd:
        raise _fail(msg("aicall_daily_cap_exceeded", f"today's AI calls cost ${spent:.4f}, this one about ${est:.4f} more; the daily cap is "
                        f"${budget.daily_usd:.2f}; nothing was sent", spent_usd=f"{spent:.4f}", estimated_usd=f"{est:.4f}",
                        cap_usd=f"{budget.daily_usd:.2f}"), "wait for tomorrow (UTC), or a person raises the cap")


# ---------------- the protocols ----------------

def _image(path) -> tuple[str, str, str]:
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as e:
        raise _fail(msg("aicall_image_unreadable", f"{p}: cannot read the image ({e.strerror}); nothing was sent", path=str(p))) from None
    mime = _IMAGE_TYPES.get(p.suffix.lower()) or mimetypes.guess_type(str(p))[0]
    if not mime or not mime.startswith("image/"):
        raise _fail(msg("aicall_image_unreadable", f"{p}: not an image file; nothing was sent", path=str(p)))
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


def usage_of(s: Settings, doc) -> tuple[int | None, int | None]:
    """(input tokens, output tokens) a reply reports, each a count or None; never raises (a billed reply that cannot be parsed still has a usage)."""
    u = doc.get("usage") if isinstance(doc, dict) and isinstance(doc.get("usage"), dict) else {}
    if s.protocol == "anthropic":
        return _count(u.get("input_tokens")), _count(u.get("output_tokens"))
    return _count(u.get("prompt_tokens")), _count(u.get("completion_tokens"))


def parse_response(s: Settings, doc) -> tuple[str, int | None, int | None, str | None]:
    """(text, input tokens, output tokens, stop reason) of a reply, or aicall_bad_answer."""
    def bad(detail):
        return _fail(msg("aicall_bad_answer", f"the {s.protocol} reply is not what the protocol says: {detail}", detail=detail))
    if not isinstance(doc, dict):
        raise bad("not a JSON object")
    try:
        if s.protocol == "anthropic":
            text = "".join(b.get("text", "") for b in doc["content"] if isinstance(b, dict) and b.get("type") == "text")
            stop = doc.get("stop_reason")
        else:
            ch = doc["choices"][0]
            text = ch["message"]["content"]
            stop = ch.get("finish_reason")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise bad("no content in it") from None
    if not isinstance(text, str) or not text.strip():
        raise bad("the content is not text")
    if stop in ("refusal", "max_tokens", "length", "content_filter"):
        raise bad(f"{STOPPED} {stop}")
    tin, tout = usage_of(s, doc)
    return text, tin, tout, stop if isinstance(stop, str) else None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """The key goes to the host in the base URL and nowhere else: a 3xx is an answer to report, never a place to follow (urllib would resend the
    key headers to the new address)."""

    def redirect_request(self, *a, **kw):
        return None


def _opener(host: str | None) -> urllib.request.OpenerDirector:
    handlers: list = [_NoRedirect()]
    if host in LOOPBACK:                 # a gateway on this machine is not reached through a proxy (the key would travel to it in the clear)
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def _once(s: Settings, url: str, headers: dict, body: dict, timeout: float):
    """(status, doc, retry_after) of one HTTP try. Status 0 is a network fault (retried), -1 a read timeout (not retried: the vendor may be working on
    the request and billing it); doc is then the fault, redacted. Nothing escapes: any other failure is a network fault."""
    try:
        r = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
        with _opener(urllib.parse.urlsplit(url).hostname).open(r, timeout=timeout) as resp:
            raw = resp.read()
        try:
            return 200, json.loads(raw), None
        except (ValueError, RecursionError):
            return 200, None, None
    except urllib.error.HTTPError as e:
        detail = redact(e.read().decode(errors="replace"), s.key)[:400]          # redacted first, then cut: a key across the cut would leave its prefix
        ra = e.headers.get("retry-after") if e.headers else None
        try:
            ra = float(ra) if ra else None
        except ValueError:
            ra = None
        ra = min(ra, MAX_RETRY_AFTER_S) if ra is not None and math.isfinite(ra) and ra >= 0 else None
        return e.code, detail, ra
    except TimeoutError:
        return -1, "the read timed out", None
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), TimeoutError):
            return -1, "the connection timed out", None
        return 0, redact(str(getattr(e, "reason", e)), s.key)[:200], None
    except Exception as e:               # IncompleteRead, BadStatusLine, InvalidURL, a header the key cannot be sent in...
        return 0, redact(f"{type(e).__name__}: {e}", s.key)[:200], None


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
    """One call: refused before anything is sent when the model has no price (`unpriced="refuse"`), `max_tokens` is not a whole number of 1 or more,
    the ledger cannot be appended to or a cap would be passed; retried on 429, 5xx and refused or dropped connections; ledgered whatever happens. A
    cap needs a ledger and a price for the model."""
    if unpriced not in UNPRICED:
        raise ValueError(f"unpriced is one of {', '.join(UNPRICED)}, not {unpriced!r}")
    if not (isinstance(max_tokens, int) and not isinstance(max_tokens, bool) and 1 <= max_tokens <= MAX_TOKENS_LIMIT):
        raise ValueError(f"max_tokens is a whole number from 1 to {MAX_TOKENS_LIMIT}, not {max_tokens!r}")
    if budget is not None and ledger is None:
        raise ValueError("a budget needs the ledger it is counted from")
    images = list(images)
    known = s.model in (prices or {})
    if not known and (unpriced == "refuse" or budget is not None):
        raise _fail(msg("aicall_model_unpriced", f"{s.model}: no price, so the cap could not count it; nothing was sent", model=s.model),
                    "add the model's list price to the pack's ai_prices.tsv, or use a priced model")
    url, headers, body = build_request(s, system, text, images, max_tokens, schema, effort)
    entry = {"at": _dates.now().isoformat(timespec="seconds"), "task": s.task, "model": s.model, "protocol": s.protocol,
             "host": s.host, "prompt_sha256": hashlib.sha256((system + "\n" + text).encode()).hexdigest(), "prompt_chars": len(system) + len(text),
             "images": [_image(p)[2] for p in images]}
    est = estimate(s, system, text, max_tokens, prices)[1] or 0.0
    rid = None
    if ledger is not None:
        ledger.check_writable()
        if budget is not None:
            rid = ledger.reserve(entry, est, budget)
    status, doc, attempts, ms = _send(s, url, headers, body, timeout, sleep)
    entry.update(ms=ms, attempts=attempts, id=rid)

    def settle(row: dict, actual: float) -> None:
        if ledger is not None:
            ledger.append(row)
        if budget is not None and rid is not None:
            budget.settle(est, actual)

    def fail(err: SkillPackError, why: str, tin=None, tout=None, billed: float = 0.0) -> SkillPackError:
        settle({**entry, "status": why, "input_tokens": tin, "output_tokens": tout, "cost_usd": billed or None}, billed)
        return err

    if status <= 0:
        why = "timeout" if status == -1 else "network"
        raise fail(_fail(msg("aicall_network_error", f"{s.host}: {'no answer' if status == 0 else 'timed out'} after {attempts} "
                             f"{'try' if attempts == 1 else 'tries'} ({doc}); is the base URL right?", detail=str(doc), host=s.host)), why,
                   billed=est if status == -1 and budget is not None else 0.0)          # a timed-out request may still be billed: its estimate stays booked
    if status != 200:
        raise fail(_fail(msg("aicall_http_error", f"{s.host} answered HTTP {status}: {doc}", status=status, detail=str(doc), host=s.host)), f"http_{status}")
    if doc is None:
        raise fail(_fail(msg("aicall_bad_answer", f"{s.host} answered 200 with a body that is not JSON", detail="not JSON")), "bad_reply",
                   billed=est if budget is not None else 0.0)
    try:
        out, tin, tout, stop = parse_response(s, doc)
    except SkillPackError as e:
        tin, tout = usage_of(s, doc)                                    # the reply was billed even though it is unusable: book what it says it used
        c = cost_usd(prices, s.model, tin, tout)
        raise fail(e, "bad_reply", tin, tout, billed=c if c is not None else (est if known else 0.0)) from None
    c = cost_usd(prices, s.model, tin, tout)
    if c is None and known:                                             # a priced model whose reply has no usable usage: booked at the estimate
        c = est
        entry["cost_estimated"] = True
    settle({**entry, "status": "ok", "input_tokens": tin, "output_tokens": tout, "cost_usd": c}, c or 0.0)
    return Reply(text=out, input_tokens=tin, output_tokens=tout, model=s.model, ms=ms, cost_usd=c, attempts=attempts, task=s.task, stop_reason=stop)


def unwrap_json(text: str):
    """The JSON object in a reply: strict, but a fenced block is unwrapped. None when it is not one object."""
    t = text.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", t, re.S)
    try:
        v = json.loads(m.group(1) if m else t)
    except (ValueError, RecursionError):
        return None
    return v if isinstance(v, dict) else None


_TYPES = {"string": str, "boolean": bool, "object": dict, "array": list, "null": type(None)}


def fits(obj: dict, schema: dict) -> bool:
    """Does `obj` carry the schema's `required` keys, and do the properties it lists have the right basic type (string, number, integer, boolean,
    array, object, null)? Nothing more: the pack's check says what the values mean."""
    for k in schema.get("required", []) or []:
        if k not in obj:
            return False
    for k, spec in (schema.get("properties") or {}).items():
        if k not in obj or not isinstance(spec, dict):
            continue
        t, v = spec.get("type"), obj[k]
        for one in (t if isinstance(t, list) else [t]):
            if one not in _TYPES and one not in ("number", "integer"):
                break                                                   # no type given, or one this check does not know: not its business
            if one == "number" and _finite(v):
                break
            if one == "integer" and isinstance(v, int) and not isinstance(v, bool):
                break
            if one in _TYPES and isinstance(v, _TYPES[one]):
                break
        else:
            return False
    return True


JSON_ONLY = "\n\nReply with one JSON object and nothing else: no prose, no code fence."


def ask_json(s: Settings, system: str, text: str, schema: dict, images=(), **kw) -> tuple[dict, Reply]:
    """One JSON object that fits `schema`'s required keys and types, with the reply it came in. The schema mode is tried first; a vendor that refuses it
    (HTTP 400) or answers with text that is not a fitting object is asked once more with the instruction in words; a reply that stopped on a refusal
    or the token limit is not asked again (it was paid for once). The object's meaning is the pack's to check."""
    last: SkillPackError | None = None
    for mode in ("schema", "words"):
        try:
            r = ask(s, system + (JSON_ONLY if mode == "words" else ""), text, images, schema=schema if mode == "schema" else None, **kw)
        except SkillPackError as e:
            code = getattr(e.message, "code", "")
            params = getattr(e.message, "params", {}) or {}
            again = (code == "aicall_http_error" and params.get("status") == 400) or \
                    (code == "aicall_bad_answer" and not str(params.get("detail", "")).startswith(STOPPED))
            if mode == "schema" and again:
                last = e
                continue
            raise
        obj = unwrap_json(r.text)
        if obj is not None and fits(obj, schema):
            return obj, r
        last = _fail(msg("aicall_json_invalid", "the reply is not one JSON object that fits the schema", detail=r.text[:80]))
    raise last or _fail(msg("aicall_json_invalid", "the reply is not one JSON object that fits the schema", detail="none"))


def count_tokens(s: Settings, system: str, text: str, images=(), *, timeout: float = TIMEOUT_S, sleep: Callable[[float], None] = time.sleep) -> int:
    """The input tokens `ask` would send, by Anthropic's `messages/count_tokens` (free; counts against no cap and is not logged). Anthropic protocol only."""
    if s.protocol != "anthropic":
        proto_var = _name("PROTOCOL")
        raise _fail(msg("aicall_config_invalid", f"count_tokens is Anthropic's endpoint; {proto_var} must be anthropic for it; nothing was sent", var=proto_var,
                        detail="anthropic for count_tokens"))
    url, headers, body = build_request(s, system, text, list(images), 1)
    status, doc, _, _ = _send(s, url + "/count_tokens", headers, {k: body[k] for k in ("model", "system", "messages")}, timeout, sleep)
    if status != 200 or not isinstance(doc, dict) or _count(doc.get("input_tokens")) is None:
        shown = redact(str(doc), s.key)[:200]
        raise _fail(msg("aicall_http_error", f"{s.host} count_tokens answered HTTP {status}: {shown}", status=status, detail=shown, host=s.host))
    return doc["input_tokens"]
