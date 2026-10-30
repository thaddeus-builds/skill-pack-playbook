#!/usr/bin/env python3
"""kit/ai.py holds each of its guards, against a loopback fake vendor (no network).

  1. Settings: the task, the key, the protocol, the base URL (https or loopback, no credentials, no query; required for openai), the model (one
     task's own over every task's; none built in) are each refused with a coded message that names the variable; the env chain's file is read.
  2. The two protocols: the request each one sends (path, key header, system, images, schema, effort) and the reply each one is read from (text,
     tokens, stop reason); an image that cannot be read is refused before anything is sent.
  3. Retries: 429 with a retry-after, 5xx and a network fault are retried and the waits are bounded; another 4xx stops at once; the key is in
     no message.
  4. The ledger: every call, a failed one too, appends one line with the prompt's sha256 and length and never its text; the file is 0600.
  5. The cap: a model with no price is refused (or logged with a null cost on request); the daily cap refuses once reached and when the estimate
     would pass it, the run cap likewise, all before a byte is sent; a client's own value may only lower the cap.
  6. ask_json: the schema mode first; a vendor that refuses it, or text that is not one object, is asked once more in words; twice is refused.
  7. count_tokens is Anthropic's alone.
  8. ai.py's msg() calls are closed over its fragment.
  9, 10. Cold reviews: each finding is a case. The second: a 2xx whose body does not arrive and Ctrl-C keep the estimate booked, the lock is on the ledger
     itself, a cut-off error body, huge numbers, a bad price, a damaged ledger, the key in a JSON encoder's forms, `fits` on odd schemas.
"""

import json
import os
import stat
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import ai, config, env, messages  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.testing.check import check, finish, raises, tmp_dir  # noqa: E402

CFG = _shop.use()
DATA = _shop.data_dir()
TASKS = ("review", "translate")
KEY = "sk-test-secret-0123456789"
PRICES = {"fast-1": (1.0, 5.0), "big-1": (10.0, 50.0)}


class Vendor:
    """A fake vendor on a loopback port: scripted answers in order, every request kept."""

    def __init__(self, script):
        self.script, self.seen = list(script), []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("content-length") or 0)
                outer.seen.append({"method": self.command, "path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": json.loads(self.rfile.read(n) or b"{}")})
                status, body, extra = outer.script.pop(0) if outer.script else (200, outer.ok(), {})
                if isinstance(body, tuple) and body[0] == "slow":
                    time.sleep(body[1])
                    body = outer.ok()
                short = isinstance(body, tuple) and body[0] == "short"
                raw = body[1] if short else body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                for k, v in extra.items():
                    self.send_header(k, v)
                self.send_header("content-length", str(len(raw) + (50 if short else 0)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except OSError:
                    pass

            do_GET = do_POST                 # a redirect that is followed comes back as a GET: it must show up in `seen`

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @staticmethod
    def ok(text="hello", tin=100, tout=20, proto="anthropic"):
        if proto == "anthropic":
            return {"content": [{"type": "text", "text": text}], "usage": {"input_tokens": tin, "output_tokens": tout}, "stop_reason": "end_turn"}
        return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": {"prompt_tokens": tin, "completion_tokens": tout}}

    def close(self):
        self.httpd.shutdown()


def route(vendor, protocol="anthropic", model="fast-1", task="review"):
    return ai.Settings(key=KEY, base_url=vendor.url, protocol=protocol, model=model, task=task)


def no_sleep(log):
    return lambda s: log.append(s)


def refusal(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except SkillPackError as e:
        return e
    return None


def code_of(e):
    return getattr(e.message, "code", None) if e else None


def vars_set(**kw):
    for k in [k for k in os.environ if k.startswith("SHOP_AI_")]:
        del os.environ[k]
    for k, v in kw.items():
        os.environ[f"SHOP_AI_{k}"] = v


print("[1] settings")
vars_set()
e = refusal(ai.settings, "review", TASKS)
check("no key: refused, naming SHOP_AI_API_KEY", code_of(e) == "aicall_config_missing" and "SHOP_AI_API_KEY" in str(e.message), e)
vars_set(API_KEY=KEY, BASE_URL="https://vendor.example.com")
e = refusal(ai.settings, "review", TASKS)
check("a key and no model: refused, naming the task's variable and the shared one", code_of(e) == "aicall_config_missing" and "SHOP_AI_MODEL_REVIEW" in str(e.message) and "SHOP_AI_MODEL" in str(e.message), e)
vars_set(API_KEY=KEY, MODEL="fast-1")
e = refusal(ai.settings, "review", TASKS)
check("no vendor is built in: with no base URL and no default, refused, naming SHOP_AI_BASE_URL", code_of(e) == "aicall_config_missing" and "SHOP_AI_BASE_URL" in str(e.message), e)
s = ai.settings("review", TASKS, default_base="https://vendor.example.com/")
check("a pack's default_base serves a host that sets none; anthropic is the protocol by default; the shared model", (s.protocol, s.base_url, s.model) == ("anthropic", "https://vendor.example.com", "fast-1"), s)
check("the key is not in repr(settings)", KEY not in repr(s))
vars_set(API_KEY=KEY, MODEL="fast-1", MODEL_TRANSLATE="big-1", BASE_URL="https://vendor.example.com")
check("a task's own model wins over the shared one", ai.settings("translate", TASKS).model == "big-1" and ai.settings("review", TASKS).model == "fast-1")
check("an unknown task is refused and the closed list named", code_of(refusal(ai.settings, "nope", TASKS)) == "aicall_config_invalid" and "review, translate" in str(refusal(ai.settings, "nope", TASKS).message))
bad = {"a protocol it does not know": dict(PROTOCOL="grpc", BASE_URL="https://vendor.example.com"), "openai with no base URL": dict(PROTOCOL="openai"), "plain http to a real host": dict(BASE_URL="http://api.example.com"),
       "credentials in the URL": dict(BASE_URL="https://" + "u:p" + "@vendor.example.com"), "a query in the URL": dict(BASE_URL="https://api.example.com/?k=1"),
       "not a URL": dict(BASE_URL="ftp://x")}
for label, extra in bad.items():
    vars_set(API_KEY=KEY, MODEL="fast-1", **extra)
    e = refusal(ai.settings, "review", TASKS)
    check(f"{label}: refused as aicall_config_invalid or missing, nothing sent", code_of(e) in ("aicall_config_invalid", "aicall_config_missing"), (label, e))
vars_set(API_KEY=KEY, MODEL="fast-1", BASE_URL="http://localhost:1234/v1/")
check("http to a loopback host is allowed and the trailing slash goes", ai.settings("review", TASKS).base_url == "http://localhost:1234/v1")
d = Path(tmp_dir("ai-env-"))
(d / ".env").write_text(f"SHOP_AI_API_KEY={KEY}\nSHOP_AI_MODEL=fast-1\n", encoding="utf-8")
vars_set()
os.environ["SHOP_DATA_DIR"] = str(d)
(d / ".env").write_text(f"SHOP_AI_API_KEY={KEY}\nSHOP_AI_MODEL=fast-1\nSHOP_AI_BASE_URL=https://vendor.example.com\n", encoding="utf-8")
os.environ.pop("SHOP_AUTH_ENV_PATHS", None)
env._clear()
check("the key and the model are read from the env chain's file when the process env has none", ai.settings("review", TASKS).model == "fast-1")
os.environ["SHOP_AUTH_ENV_PATHS"] = "none"
DATA = _shop.data_dir()
env._clear()
vars_set(DAILY_CAP_USD="2.5")
check("the env cap is a number above 0, or None when unset", ai.env_cap() == 2.5)
for badcap in ("0", "-1", "abc", "inf"):
    vars_set(DAILY_CAP_USD=badcap)
    check(f"SHOP_AI_DAILY_CAP_USD={badcap} is refused", code_of(refusal(ai.env_cap)) == "aicall_config_invalid")
vars_set()
check("unset: None", ai.env_cap() is None)
check("a client's own value may only lower a cap", (ai.lowered(5.0, 2.0), ai.lowered(5.0, 9.0), ai.lowered(5.0, None)) == (2.0, 5.0, 5.0))

print("[2] the two protocols")
v = Vendor([])
schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
img = Path(tmp_dir("ai-img-")) / "f.png"
img.write_bytes(b"\x89PNG-bytes")
r = ai.ask(route(v), "SYS", "ask", [img], schema=schema, effort="low", prices=PRICES)
q = v.seen[0]
check("anthropic: /v1/messages, x-api-key, system on top, the image then the text, schema and effort under output_config",
      q["path"] == "/v1/messages" and q["headers"]["x-api-key"] == KEY and q["body"]["system"] == "SYS"
      and [c["type"] for c in q["body"]["messages"][0]["content"]] == ["image", "text"]
      and q["body"]["output_config"] == {"format": {"type": "json_schema", "schema": schema}, "effort": "low"}, q)
check("the reply is read: text, tokens, stop reason, cost from the price row", (r.text, r.input_tokens, r.output_tokens, r.stop_reason, r.cost_usd) == ("hello", 100, 20, "end_turn", 0.0002), r)
v.close()
v = Vendor([(200, Vendor.ok(proto="openai"), {})])
r = ai.ask(route(v, "openai"), "SYS", "ask", [img], schema=schema, effort="low", prices=PRICES)
q = v.seen[0]
check("openai: /v1/chat/completions, a bearer header, the system as a message, the image as a data URL, response_format, and no effort",
      q["path"] == "/v1/chat/completions" and q["headers"]["authorization"] == f"Bearer {KEY}" and q["body"]["messages"][0] == {"role": "system", "content": "SYS"}
      and q["body"]["messages"][1]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
      and q["body"]["response_format"]["type"] == "json_schema" and "effort" not in json.dumps(q["body"]) and "output_config" not in q["body"], q)
check("its reply is read from choices and usage", (r.text, r.input_tokens, r.output_tokens, r.stop_reason) == ("hello", 100, 20, "stop"), r)
v.close()
v = Vendor([])
txt = Path(tmp_dir("ai-img-")) / "x.txt"
txt.write_text("not an image")
e = refusal(ai.ask, route(v), "S", "t", [txt], prices=PRICES)
e2 = refusal(ai.ask, route(v), "S", "t", [txt.with_name("gone.png")], prices=PRICES)
check("a file that is not an image, and one that is gone, are refused before a byte is sent", code_of(e) == "aicall_image_unreadable" and code_of(e2) == "aicall_image_unreadable" and not v.seen, (e, e2, v.seen))
for label, doc in (("a body that is not an object", [1]), ("no content", {"usage": {}}), ("empty text", Vendor.ok(text=" ")),
                   ("a refusal", {**Vendor.ok(), "stop_reason": "refusal"}), ("a cut-off answer", {**Vendor.ok(), "stop_reason": "max_tokens"})):
    v.script = [(200, doc, {})]
    check(f"{label}: aicall_bad_answer", code_of(refusal(ai.ask, route(v), "S", "t", prices=PRICES)) == "aicall_bad_answer", label)
v.script = [(200, b"not json", {})]
check("a 200 that is not JSON: aicall_bad_answer", code_of(refusal(ai.ask, route(v), "S", "t", prices=PRICES)) == "aicall_bad_answer")
v.close()

print("[3] retries and the key")
waits = []
v = Vendor([(429, {"error": "slow down"}, {"retry-after": "7"}), (503, {"error": "busy"}, {}), (200, Vendor.ok(), {})])
r = ai.ask(route(v), "S", "t", prices=PRICES, sleep=no_sleep(waits))
check("429 with retry-after, then 503, then 200: three attempts, the waits are the retry-after and the first back-off", r.attempts == 3 and waits == [7.0, ai.BACKOFF_S[1]], (r.attempts, waits))
v.close()
waits = []
v = Vendor([(429, {}, {"retry-after": "9999"}), (200, Vendor.ok(), {})])
ai.ask(route(v), "S", "t", prices=PRICES, sleep=no_sleep(waits))
check("a retry-after is bounded", waits == [ai.MAX_RETRY_AFTER_S], waits)
v.close()
waits = []
v = Vendor([(500, {"error": f"echo {KEY}"}, {})] * 4)
e = refusal(ai.ask, route(v), "S", "t", prices=PRICES, sleep=no_sleep(waits))
check("5xx four times: four tries, the last answer is the error, the key replaced in it", code_of(e) == "aicall_http_error" and len(v.seen) == 4 and len(waits) == 3 and KEY not in str(e.message) and "<key>" in str(e.message), (e, len(v.seen)))
v.close()
v = Vendor([(400, {"error": "bad"}, {})])
e = refusal(ai.ask, route(v), "S", "t", prices=PRICES, sleep=no_sleep([]))
check("another 4xx stops at once: one try", code_of(e) == "aicall_http_error" and len(v.seen) == 1, len(v.seen))
v.close()
dead = ai.Settings(key=KEY, base_url="http://127.0.0.1:1", protocol="anthropic", model="fast-1", task="review")
waits = []
e = refusal(ai.ask, dead, "S", "t", prices=PRICES, sleep=no_sleep(waits), timeout=2)
check("a network fault is retried and then named, without the key", code_of(e) == "aicall_network_error" and len(waits) == 3 and KEY not in str(e.message), (e, waits))

print("[4] the ledger")
led = Ledger = ai.Ledger(DATA / "ai_calls.jsonl")
v = Vendor([(200, Vendor.ok(tin=1000, tout=100), {}), (400, {"error": "no"}, {})])
ai.ask(route(v), "SYSTEM-SECRET-TEXT", "USER-SECRET-TEXT", [img], prices=PRICES, ledger=led)
refusal(ai.ask, route(v), "SYSTEM-SECRET-TEXT", "USER-SECRET-TEXT", prices=PRICES, ledger=led)
rows = led.rows()
raw = led.path.read_text(encoding="utf-8")
check("two calls, one failed: two lines, the first ok with its cost, the second with the status and a null cost",
      len(rows) == 2 and rows[0]["status"] == "ok" and rows[0]["cost_usd"] == 0.0015 and rows[1]["status"] == "http_400" and rows[1]["cost_usd"] is None, rows)
check("the prompt's sha256 and length are kept, its text is not, nor the key", "SECRET-TEXT" not in raw and KEY not in raw and len(rows[0]["prompt_sha256"]) == 64
      and rows[0]["prompt_chars"] == len("SYSTEM-SECRET-TEXT") + len("USER-SECRET-TEXT") and len(rows[0]["images"][0]) == 64, rows[0])
check("the log is 0600", stat.S_IMODE(os.stat(led.path).st_mode) == 0o600, oct(os.stat(led.path).st_mode))
u = led.usage()
check("usage sums the day: two calls, one failed, the priced cost", (u["calls"], u["failed"], u["cost_usd"], u["unpriced_calls"]) == (2, 1, 0.0015, 0), u)
check("spent() counts the day's priced cost; another day counts none", led.spent() == 0.0015 and led.spent("2000-01-01") == 0.0)
v.close()

print("[5] the cap")
led2 = ai.Ledger(DATA / "ai2.jsonl")
v = Vendor([])
e = refusal(ai.ask, route(v, model="mystery"), "S", "t", prices=PRICES, ledger=led2)
check("a model with no price is refused before sending", code_of(e) == "aicall_model_unpriced" and not v.seen and not led2.rows(), (e, v.seen))
r = ai.ask(route(v, model="mystery"), "S", "t", prices=PRICES, ledger=led2, unpriced="log")
u = led2.usage()
check("unpriced='log' sends, logs a null cost, counts nothing, and usage says one call had no price", r.cost_usd is None and led2.rows()[0]["cost_usd"] is None and u["unpriced_calls"] == 1 and u["cost_usd"] == 0.0, u)
e = refusal(ai.ask, route(v, model="mystery"), "S", "t", prices=PRICES, ledger=led2, unpriced="log", budget=ai.Budget(1.0))
check("a cap cannot count an unpriced model, even with unpriced='log'", code_of(e) == "aicall_model_unpriced")
check("a budget needs its ledger", raises(lambda: ai.ask(route(v), "S", "t", prices=PRICES, budget=ai.Budget(1.0)), ValueError))
check("unpriced is 'refuse' or 'log'", raises(lambda: ai.ask(route(v), "S", "t", prices=PRICES, unpriced="maybe"), ValueError))
v.close()
v = Vendor([])
led3 = ai.Ledger(DATA / "ai3.jsonl")
led3.append({"at": ai.today() + "T01:00:00+00:00", "model": "fast-1", "status": "ok", "cost_usd": 0.0100})
n = len(v.seen)
e = refusal(ai.ask, route(v), "S", "t", prices=PRICES, ledger=led3, budget=ai.Budget(0.0100))
check("the day's cost has reached the cap: refused before a byte is sent", code_of(e) == "aicall_daily_cap_exceeded" and len(v.seen) == n, (e, len(v.seen)))
e = refusal(ai.ask, route(v), "S" * 4000, "t" * 4000, max_tokens=4000, prices=PRICES, ledger=led3, budget=ai.Budget(0.0200))
check("under the cap but the estimate would pass it: refused before sending", code_of(e) == "aicall_daily_cap_exceeded" and len(v.seen) == n, e)
e = refusal(ai.ask, route(v), "S" * 4000, "t" * 4000, max_tokens=4000, prices=PRICES, ledger=led3, budget=ai.Budget(100.0, run_usd=0.001))
check("the run cap is checked against the estimate alone", code_of(e) == "aicall_run_cap_exceeded" and len(v.seen) == n, e)
r = ai.ask(route(v), "S", "t", max_tokens=10, prices=PRICES, ledger=led3, budget=ai.Budget(1.0, run_usd=1.0))
check("within both caps the call goes out", r.text == "hello" and len(v.seen) == n + 1)
check("the estimate counts the prompt high and the answer at its cap", ai.estimate(route(v), "x" * 40, "y" * 40, 1000, PRICES)[1] == round(((20 + 8 * 2) * 1.0 + 1000 * 5.0) / 1e6, 6)
      and ai.tokens_in_text("你好") == 2 + 8 and ai.tokens_in_text("abcd") == 1 + 8)
v.close()
check("prices_from_rows keeps a priced row, leaves a blank one out, refuses a bad number",
      ai.prices_from_rows([{"model": "a", "input_per_mtok_usd": "1", "output_per_mtok_usd": "2"}, {"model": "b", "input_per_mtok_usd": "", "output_per_mtok_usd": "2"}]) == {"a": (1.0, 2.0)}
      and code_of(refusal(ai.prices_from_rows, [{"model": "c", "input_per_mtok_usd": "x", "output_per_mtok_usd": "1"}])) == "aicall_config_invalid"
      and code_of(refusal(ai.prices_from_rows, [{"model": "c", "input_per_mtok_usd": "-1", "output_per_mtok_usd": "1"}])) == "aicall_config_invalid")

print("[6] ask_json")
v = Vendor([(200, Vendor.ok(text='{"ok": true}'), {})])
obj, r = ai.ask_json(route(v), "S", "t", schema, prices=PRICES)
check("the schema mode first, one call, the object returned", obj == {"ok": True} and len(v.seen) == 1 and "output_config" in v.seen[0]["body"])
v.close()
v = Vendor([(400, {"error": "response_format unsupported"}, {}), (200, Vendor.ok(text='```json\n{"ok": false}\n```'), {})])
obj, r = ai.ask_json(route(v), "S", "t", schema, prices=PRICES)
check("a vendor that refuses the schema mode (400) is asked once more in words, and a fenced object is unwrapped",
      obj == {"ok": False} and len(v.seen) == 2 and "output_config" not in v.seen[1]["body"] and v.seen[1]["body"]["system"].endswith("no code fence."), v.seen)
v.close()
v = Vendor([(200, Vendor.ok(text="I think so"), {}), (200, Vendor.ok(text="[1, 2]"), {})])
e = refusal(ai.ask_json, route(v), "S", "t", schema, prices=PRICES)
check("text that is not one object twice is refused as aicall_json_invalid", code_of(e) == "aicall_json_invalid" and len(v.seen) == 2, (e, len(v.seen)))
v.close()
v = Vendor([(401, {"error": "unauthorised"}, {})])
e = refusal(ai.ask_json, route(v), "S", "t", schema, prices=PRICES)
check("another HTTP error is not retried as 'words'", code_of(e) == "aicall_http_error" and len(v.seen) == 1, (e, len(v.seen)))
v.close()
check("unwrap_json: strict, a fence is unwrapped, a list or a string is not an object",
      ai.unwrap_json('{"a": 1}') == {"a": 1} and ai.unwrap_json('```\n{"a": 1}\n```') == {"a": 1} and ai.unwrap_json("[1]") is None and ai.unwrap_json("x") is None)

print("[7] count_tokens")
v = Vendor([(200, {"input_tokens": 42}, {})])
n = ai.count_tokens(route(v), "S", "t")
check("anthropic: the count comes from /v1/messages/count_tokens and the body carries no max_tokens", n == 42 and v.seen[0]["path"] == "/v1/messages/count_tokens" and "max_tokens" not in v.seen[0]["body"], v.seen)
e = refusal(ai.count_tokens, route(v, "openai"), "S", "t")
check("another protocol is refused before sending", code_of(e) == "aicall_config_invalid" and len(v.seen) == 1)
v.close()


print("[9] found by a cold review")
# --- the key goes nowhere else
v2 = Vendor([])
v = Vendor([(302, {}, {"Location": v2.url + "/elsewhere"})])
e = refusal(ai.ask, route(v), "S", "t", prices=PRICES, sleep=no_sleep([]))
check("a redirect is not followed: the other host sees nothing, the answer is an HTTP error", code_of(e) == "aicall_http_error" and not v2.seen and len(v.seen) == 1, (e, v2.seen))
v.close()
v2.close()
vars_set(API_KEY="sk-bad\nkey", MODEL="fast-1", BASE_URL="https://vendor.example.com")
check("a key with a control character is refused when the settings are read", code_of(refusal(ai.settings, "review", TASKS)) == "aicall_config_invalid")
vars_set()
v = Vendor([])
bad_key = ai.Settings(key="sk-bad\nkey", base_url=v.url, protocol="anthropic", model="fast-1", task="review")
led9 = ai.Ledger(DATA / "ai9.jsonl")
e = refusal(ai.ask, bad_key, "S", "t", prices=PRICES, ledger=led9, sleep=no_sleep([]))
check("and if one gets through anyway, the failure is coded, ledgered, and the key is not in it", code_of(e) == "aicall_network_error" and "sk-bad" not in str(e.message)
      and led9.rows() and led9.rows()[-1]["status"] == "network" and not v.seen, (e, led9.rows()))
v.close()
v = Vendor([(200, {"input_tokens": "x", "echo": KEY}, {})])
e = refusal(ai.count_tokens, route(v), "S", "t")
check("count_tokens does not print a reply body that echoes the key", code_of(e) == "aicall_http_error" and KEY not in str(e.message), e)
v.close()
v = Vendor([(400, {"error": "x" * 370 + KEY + "tail"}, {})])
e = refusal(ai.ask, route(v), "S", "t", prices=PRICES, sleep=no_sleep([]))
check("a key across the 400-character cut leaves no prefix of itself: redaction comes first", code_of(e) == "aicall_http_error" and KEY[:10] not in str(e.message), str(e.message)[-120:])
v.close()
proxy = Vendor([])
no_proxy = {k: os.environ.pop(k, None) for k in ("NO_PROXY", "no_proxy")}                  # a NO_PROXY that names 127.0.0.1 would pass this check by itself
os.environ["HTTP_PROXY"] = os.environ["http_proxy"] = proxy.url
v = Vendor([])
try:
    ai.ask(route(v), "S", "t", prices=PRICES)
finally:
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("http_proxy", None)
    os.environ.update({k: x for k, x in no_proxy.items() if x is not None})
check("a loopback call does not go through a proxy", len(v.seen) == 1 and not proxy.seen, (len(v.seen), proxy.seen))
v.close()
proxy.close()

# --- the cap
led = ai.Ledger(DATA / "ai_race.jsonl")
v = Vendor([(200, ("slow", 0.5), {})] * 2)                         # the two sent calls stay in flight while the other six are turned away: a quick settle would free room
out = []
bud = ai.Budget(0.005)
def one():
    try:
        ai.ask(route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=led, budget=bud)
        out.append("sent")
    except SkillPackError as e:
        out.append(code_of(e))
ts = [threading.Thread(target=one) for _ in range(8)]
[x.start() for x in ts]
[x.join() for x in ts]
check("eight threads at once against a cap that admits two: two requests go out, six are refused", len(v.seen) == 2 and out.count("sent") == 2 and out.count("aicall_daily_cap_exceeded") == 6,
      (len(v.seen), out))
check("the log holds a reservation and a settlement per sent call, and the day's spend is counted once", led.spent() == 0.0004 and len(led.rows()) == 4, (led.spent(), len(led.rows())))
v.close()
led = ai.Ledger(DATA / "ai_procs.jsonl")
script = ("import sys, time\nsys.path.insert(0, %r); sys.path.insert(0, %r)\nimport _shop\n_shop.use()\nfrom kit import ai\n"
          "from kit.contract import SkillPackError\nled = ai.Ledger(sys.argv[1])\nbud = ai.Budget(0.005)\n"
          "time.sleep(max(0.0, float(sys.argv[2]) - time.time()))\n"
          "try:\n    led.reserve({'at': ai.today() + 'T00:00:00+00:00', 'model': 'm'}, 0.002, bud)\n    print('ok')\nexcept SkillPackError:\n    print('refused')\n"
          % (str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parent)))
import subprocess  # noqa: E402
start = time.time() + 2.0
procs = [subprocess.Popen([sys.executable, "-c", script, str(led.path), str(start)], stdout=subprocess.PIPE, text=True) for _ in range(8)]
outs = [p.communicate()[0].strip() for p in procs]
check("eight processes at once against a cap that admits two: two reserve, six are refused (the file lock holds across processes)", outs.count("ok") == 2 and outs.count("refused") == 6, outs)
led = ai.Ledger(DATA / "ai_crash.jsonl")
bud = ai.Budget(0.003)
led.reserve({"at": ai.today() + "T00:00:00+00:00", "model": "fast-1"}, 0.0025, bud)           # a call that reserved and never settled (a crash)
check("a reservation nobody settled keeps counting at its estimate", abs(led.spent() - 0.0025) < 1e-9 and code_of(refusal(ai.check_budget, led.spent(), 0.002, ai.Budget(0.003))) == "aicall_daily_cap_exceeded")
v = Vendor([])
bud = ai.Budget(100.0, run_usd=0.005)
led = ai.Ledger(DATA / "ai_run.jsonl")
v.script = [(200, Vendor.ok(tin=18, tout=400), {})] * 3
res = [code_of(refusal(ai.ask, route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=led, budget=bud)) for _ in range(3)]
check("the run cap is the run's: two calls that cost what they were estimated use it up, the third is refused", res == [None, None, "aicall_run_cap_exceeded"] and len(v.seen) == 2, (res, len(v.seen)))
v.close()
v = Vendor([(200, {**Vendor.ok(text="no", tin=1000, tout=500), "stop_reason": "refusal"}, {})])
led = ai.Ledger(DATA / "ai_billed.jsonl")
e = refusal(ai.ask, route(v), "S", "t", prices=PRICES, ledger=led)
check("a refusal that was billed is booked as billed", code_of(e) == "aicall_bad_answer" and led.rows()[0]["cost_usd"] == 0.0035 and led.spent() == 0.0035, led.rows())
v.close()
v = Vendor([(200, {**Vendor.ok(text="cut", tin=10, tout=10), "stop_reason": "max_tokens"}, {}), (200, Vendor.ok(text='{"ok": true}'), {})])
e = refusal(ai.ask_json, route(v), "S", "t", schema, prices=PRICES)
check("ask_json does not ask again after a refusal or a cut-off (it was paid for once)", code_of(e) == "aicall_bad_answer" and len(v.seen) == 1, (e, len(v.seen)))
v.close()
check("a price that is infinite or not a number is refused", all(code_of(refusal(ai.prices_from_rows, [{"model": "a", "input_per_mtok_usd": x, "output_per_mtok_usd": "1"}])) == "aicall_config_invalid" for x in ("inf", "1e999", "nan", "-0.5")))
v = Vendor([(200, {**Vendor.ok(), "usage": {"input_tokens": -10**9, "output_tokens": 5}}, {})])
led = ai.Ledger(DATA / "ai_neg.jsonl")
r = ai.ask(route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=led)
check("a negative token count is unknown, never a negative cost; a priced model with no usable usage is booked at its estimate",
      r.cost_usd == 0.002018 and led.rows()[0].get("cost_estimated") is True and led.spent() == 0.002018, (r.cost_usd, led.rows()))
v.close()
v = Vendor([])
for label, bad_mt in (("zero", 0), ("None", None), ("a huge number", 10 ** 400), ("a bool", True), ("a float", 1.5)):
    check(f"max_tokens {label} is refused before anything is sent", raises(lambda: ai.ask(route(v), "S", "t", max_tokens=bad_mt, prices=PRICES), ValueError) is not None and not v.seen)
check("a Budget needs finite caps above 0, and lowered ignores a cap that is not a number",
      all(raises(lambda x=x: ai.Budget(x), ValueError) is not None for x in (float("nan"), 0, -1, float("inf"))) and ai.lowered(5.0, float("nan")) == 5.0)
v.close()
v = Vendor([])
(DATA / "adir").mkdir(exist_ok=True)
e = refusal(ai.ask, route(v), "S", "t", prices=PRICES, ledger=ai.Ledger(DATA / "adir"))
check("a ledger that cannot be appended to is refused before sending", code_of(e) == "aicall_config_invalid" and not v.seen, (e, v.seen))
v.close()
led = ai.Ledger(DATA / "ai_mixed.jsonl")
led.path.write_text('{"at": "' + ai.today() + 'T01:00:00+00:00", "cost_usd": 0.001, "status": "ok", "model": "m"}\n{"at": "nonsense", "cost_usd": 9}\n{"cut off\n[1]\n{"at": "'
                    + ai.today() + 'T02:00:00+00:00", "cost_usd": NaN}\n', encoding="utf-8")
check("a ledger with a bad day, a cut-off line, a non-object and a NaN cost still counts only the good line, and usage says how many lines it could not read (2)",
      led.spent() == 0.001 and led.usage()["unreadable_lines"] == 2, (led.spent(), led.usage()))

# --- retries
waits = []
v = Vendor([(429, {}, {"retry-after": "-5"}), (429, {}, {"retry-after": "nan"}), (200, Vendor.ok(), {})])
r = ai.ask(route(v), "S", "t", prices=PRICES, sleep=no_sleep(waits))
check("a negative or NaN retry-after is ignored: the back-off is used", r.attempts == 3 and waits == [ai.BACKOFF_S[0], ai.BACKOFF_S[1]], (r.attempts, waits))
v.close()
led = ai.Ledger(DATA / "ai_short.jsonl")
v = Vendor([(200, ("short", b'{"content": [{"type": "te'), {})] * 4)
e = refusal(ai.ask, route(v), "S", "t", prices=PRICES, ledger=led, sleep=no_sleep([]))
check("a 2xx reply cut short is a coded fault and a ledger line, not a raw exception, and it is not sent again (the vendor answered, so it may have billed it)",
      code_of(e) == "aicall_network_error" and len(v.seen) == 1 and led.rows() and led.rows()[-1]["status"] == "cut_off", (e, led.rows(), len(v.seen)))
v.close()
led = ai.Ledger(DATA / "ai_slow.jsonl")
v = Vendor([(200, ("slow", 1.0), {})])
bud = ai.Budget(1.0)
e = refusal(ai.ask, route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=led, budget=bud, timeout=0.3, sleep=no_sleep([]))
time.sleep(0.9)
check("a read timeout is not retried (the vendor may be billing the first request) and its estimate stays booked", code_of(e) == "aicall_network_error"
      and len(v.seen) == 1 and led.rows()[-1]["status"] == "timeout" and led.spent() == 0.002018, (e, len(v.seen), led.rows()))
v.close()

# --- ask_json
v = Vendor([(200, Vendor.ok(text="{}"), {}), (200, Vendor.ok(text='{"other": 1}'), {})])
e = refusal(ai.ask_json, route(v), "S", "t", {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}, prices=PRICES)
check("an object without the schema's required key is not accepted, twice", code_of(e) == "aicall_json_invalid" and len(v.seen) == 2, (e, len(v.seen)))
v.close()
v = Vendor([(200, Vendor.ok(text='{"ok": "yes"}'), {}), (200, Vendor.ok(text='{"ok": true}'), {})])
obj, _ = ai.ask_json(route(v), "S", "t", {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}, prices=PRICES)
check("a property of the wrong basic type is asked again, and the fitting answer is returned", obj == {"ok": True} and len(v.seen) == 2)
v.close()
v = Vendor([(500, {"error": "HTTP 400 in the text of a server error"}, {})] * 4)
e = refusal(ai.ask_json, route(v), "S", "t", schema, prices=PRICES, sleep=no_sleep([]))
check("the schema mode is given up on a 400 status, not on the words 'HTTP 400' in a 500's body", code_of(e) == "aicall_http_error" and len(v.seen) == 4, (e, len(v.seen)))
v.close()
check("unwrap_json: text nested past the parser's limit is not an object, not a crash", ai.unwrap_json("[" * 200000 + "]" * 200000) is None)

# --- settings
vars_set(API_KEY=KEY, MODEL="fast-1")
for label, base in (("an unclosed IPv6 bracket", "http://[::1"), ("a fragment", "https://vendor.example.com#x"), ("a port that is not one", "https://vendor.example.com:99999"),
                    ("a port that is not a number", "https://vendor.example.com:abc")):
    vars_set(API_KEY=KEY, MODEL="fast-1", BASE_URL=base)
    check(f"{label}: coded, not a raw exception", code_of(refusal(ai.settings, "review", TASKS)) == "aicall_config_invalid", label)
vars_set()
from unittest import mock  # noqa: E402
with mock.patch.object(config, "config", side_effect=config.ConfigError("none bound")):
    check("with no skill pack bound the refusal is coded and says so", code_of(refusal(ai.env_cap)) == "aicall_config_invalid")
check("a price row error names the model", "x-model" in str(refusal(ai.prices_from_rows, [{"model": "x-model", "input_per_mtok_usd": "nope", "output_per_mtok_usd": "1"}]).message))

print("[10] found by the second cold review")
import urllib.error  # noqa: E402
from unittest import mock  # noqa: E402

# --- a 2xx whose body does not arrive: possibly billed, never sent again
led = ai.Ledger(DATA / "ai_cut.jsonl")
v = Vendor([(200, ("short", b'{"content": [{"type": "te'), {})] * 4)
bud = ai.Budget(1.0)
e = refusal(ai.ask, route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=led, budget=bud, sleep=no_sleep([]))
est = ai.estimate(route(v), "S", "t", 400, PRICES)[1]
check("a 2xx cut short: one try, the line says cut_off, and the estimate stays booked in the ledger and in the Budget",
      code_of(e) == "aicall_network_error" and len(v.seen) == 1 and led.rows()[-1]["status"] == "cut_off" and led.spent() == round(est, 6) and abs(bud.used_usd - est) < 1e-9
      and "IncompleteRead" in str(e.message), (e, len(v.seen), led.rows()[-1:], bud.used_usd))
v.close()
for code in (503, 429):
    v = Vendor([(code, ("short", b'{"error": "ov'), {})] * 4)
    e = refusal(ai.ask, route(v), "S", "t", prices=PRICES, sleep=no_sleep([]))
    check(f"a {code} whose body is cut short is still the {code}: tried four times, coded, not a raw exception",
          code_of(e) == "aicall_http_error" and e.message.params.get("status") == code and len(v.seen) == 4, (e, len(v.seen)))
    v.close()
v = Vendor([(200, b"not json", {})])
led = ai.Ledger(DATA / "ai_notjson.jsonl")
bud = ai.Budget(1.0)
e = refusal(ai.ask, route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=led, budget=bud, sleep=no_sleep([]))
check("a 200 that is not JSON is booked at the estimate (it was billed)", code_of(e) == "aicall_bad_answer" and led.rows()[-1]["status"] == "bad_reply" and led.spent() == round(est, 6)
      and abs(bud.used_usd - est) < 1e-9, (led.rows()[-1:], bud.used_usd))
v.close()


class ConnectTimeout:
    def open(self, *a, **kw):
        raise urllib.error.URLError(TimeoutError("connect timed out"))


led = ai.Ledger(DATA / "ai_connect.jsonl")
bud = ai.Budget(1.0)
with mock.patch.object(ai, "_opener", return_value=ConnectTimeout()):
    e = refusal(ai.ask, route(Vendor([])), "S", "t", max_tokens=400, prices=PRICES, ledger=led, budget=bud, sleep=no_sleep([]))
check("a connection that times out is not retried and keeps its estimate booked", code_of(e) == "aicall_network_error" and led.rows()[-1]["status"] == "timeout"
      and led.rows()[-1]["attempts"] == 1 and led.spent() == round(est, 6), led.rows()[-1:])


def ctrl_c(_seconds):
    raise KeyboardInterrupt


v = Vendor([(503, {}, {})])
led = ai.Ledger(DATA / "ai_int.jsonl")
bud = ai.Budget(1.0)
try:
    ai.ask(route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=led, budget=bud, sleep=ctrl_c)
    got = None
except KeyboardInterrupt:
    got = "interrupted"
check("Ctrl-C in a back-off wait is raised as it was; the line says 'interrupted', the estimate stays booked and usage counts it as failed",
      got == "interrupted" and led.rows()[-1]["status"] == "interrupted" and led.spent() == round(est, 6) and led.usage()["failed"] == 1 and abs(bud.used_usd - est) < 1e-9, (got, led.rows()[-1:]))
v.close()

# --- what the Budget holds
v = Vendor([(200, Vendor.ok(tin=18, tout=40), {}), (400, {"error": "x"}, {})])
bud = ai.Budget(1.0, run_usd=1.0)
ai.ask(route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=ai.Ledger(DATA / "ai_used.jsonl"), budget=bud)
check("after a reply the Budget holds what it cost, not the estimate", abs(bud.used_usd - 0.000218) < 1e-9, bud.used_usd)
bud = ai.Budget(1.0, run_usd=1.0)
refusal(ai.ask, route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=ai.Ledger(DATA / "ai_used2.jsonl"), budget=bud)
check("after a call that was not billed (HTTP 400) it holds nothing", bud.used_usd == 0.0, bud.used_usd)
v.close()

# --- the lock is on the ledger itself
base = ai.Ledger(DATA / "ai_lockid.jsonl")
base.check_writable()
(DATA / "ai_lockid_sym.jsonl").symlink_to(base.path)
os.link(base.path, DATA / "ai_lockid_hard.jsonl")
here = os.getcwd()
os.chdir(DATA)
rel = ai.Ledger("ai_lockid.jsonl")
os.chdir(here)
check("a relative ledger path is made absolute when the Ledger is made: a later chdir does not move it", rel.path.is_absolute() and os.path.samefile(rel.path, base.path))
for label, other in (("a symlink", ai.Ledger(DATA / "ai_lockid_sym.jsonl")), ("a hard link", ai.Ledger(DATA / "ai_lockid_hard.jsonl")), ("a relative path", rel)):
    done = threading.Event()

    def go(other=other, done=done):
        other.reserve({"at": ai.today() + "T00:00:00+00:00", "model": "m"}, 0.001, ai.Budget(1.0))
        done.set()

    with base._locked():
        t = threading.Thread(target=go)
        t.start()
        time.sleep(0.3)
        blocked = not done.is_set()
    t.join(10)
    check(f"{label} to the ledger takes the same lock: a reservation waits for the holder", blocked and done.is_set(), (blocked, done.is_set()))
check("and there is no lock file beside the ledger", not list(DATA.glob("*.lock")), list(DATA.glob("*.lock")))
if os.geteuid() != 0:
    ro = Path(tmp_dir("ai-ro-"))
    led_ro = ai.Ledger(ro / "calls.jsonl")
    led_ro.check_writable()
    os.chmod(ro, 0o555)
    v = Vendor([])
    try:
        r = ai.ask(route(v), "S", "t", max_tokens=10, prices=PRICES, ledger=led_ro, budget=ai.Budget(1.0))
    finally:
        os.chmod(ro, 0o755)
    check("a ledger file that can be written in a folder that cannot: the call is made and booked (no lock file to create)", r.text == "hello" and r.booked and len(led_ro.rows()) == 2, led_ro.rows())
    v.close()
a, b = ai.Ledger(DATA / "ai_shared_a.jsonl"), ai.Ledger(DATA / "ai_shared_b.jsonl")
wins = []
for _ in range(15):
    bud, got = ai.Budget(100.0, run_usd=0.005), []

    def go(l, bud=bud, got=got):
        try:
            l.reserve({"at": ai.today() + "T00:00:00+00:00", "model": "m"}, 0.002, bud)
            got.append(1)
        except SkillPackError:
            got.append(0)

    ts = [threading.Thread(target=go, args=(a if i % 2 else b,)) for i in range(8)]
    [x.start() for x in ts]
    [x.join() for x in ts]
    wins.append(sum(got))
check("one Budget over two ledger files: exactly two of eight calls reserve, in each of 15 rounds", set(wins) == {2}, wins)
day = ai.today()
led = ai.Ledger(DATA / "ai_midnight.jsonl")
led.append({"at": "2000-01-01T10:00:00+00:00", "cost_usd": 0.0099, "status": "ok", "model": "m"})
e = refusal(led.reserve, {"at": "2000-01-01T23:59:59+00:00", "model": "m"}, 0.001, ai.Budget(0.01))
check("a reservation counts against the day it is stamped with, not the day the lock was taken", code_of(e) == "aicall_daily_cap_exceeded" and led.reserve({"at": day + "T00:00:00+00:00", "model": "m"}, 0.001, ai.Budget(0.01)))

# --- a damaged ledger
led = ai.Ledger(DATA / "ai_cutline.jsonl")
led.path.write_text('{"at": "' + day + 'T01:00:00+00:00", "cost_usd": 0.004, "status": "ok", "model": "m"}\n{"at": "' + day + 'T02:00', encoding="utf-8")
led.reserve({"at": day + "T03:00:00+00:00", "model": "m"}, 0.004, ai.Budget(0.01))
e = refusal(led.reserve, {"at": day + "T04:00:00+00:00", "model": "m"}, 0.004, ai.Budget(0.01))
check("a ledger whose last line was cut off: the next reservation starts a line of its own and counts, so the one after it is refused",
      code_of(e) == "aicall_daily_cap_exceeded" and led.spent() == 0.008 and led.usage()["unreadable_lines"] == 1, (e, led.spent(), led.usage()["unreadable_lines"]))
led.path.write_bytes(b'{"at": "' + day.encode() + b'T01:00:00+00:00", "cost_usd": 0.001, "status": "ok", "model": "m"}\n{"note": "\xe4\xb8')
check("a multibyte character cut mid-write is one unreadable line, not an exception", led.spent() == 0.001 and led.usage()["unreadable_lines"] == 1, led.usage())
good = '{"at": "' + day + 'T01:00:00+00:00", "cost_usd": 0.001, "status": "ok", "model": "m"}\n'
led.path.write_text(good + "[" * 200000 + "\n" + '{"at": "' + day + 'T02:00:00+00:00", "cost_usd": -5, "status": "ok", "model": "m"}\n'
                    + '{"at": "' + day + 'T03:00:00+00:00", "cost_usd": 1' + "0" * 400 + ', "status": "ok", "model": "m"}\n', encoding="utf-8")
check("a line nested past the parser's limit is unreadable; a negative cost and a 400-digit cost count nothing; nothing raises",
      led.spent() == 0.001 and led.usage()["unreadable_lines"] == 1 and led.usage()["cost_usd"] == 0.001, (led.spent(), led.usage()))
check("the ledger refuses to write a NaN", raises(lambda: led.append({"cost_usd": float("nan")}), ValueError) is not None)


class Flaky(ai.Ledger):
    """A ledger that takes the reservation and then cannot write the settling line (the disk filled up)."""

    def append(self, entry):
        if entry.get("status") != "reserved":
            raise OSError(28, "No space left on device")
        super().append(entry)


class Racy(ai.Ledger):
    """A ledger that could be appended to a moment ago and cannot be when the reservation is made."""

    def reserve(self, *a, **kw):
        raise OSError(13, "Permission denied")


v = Vendor([])
e = refusal(ai.ask, route(v), "S", "t", max_tokens=10, prices=PRICES, ledger=Racy(DATA / "ai_racy.jsonl"), budget=ai.Budget(1.0))
check("a ledger that fails when the reservation is made: refused as a coded line, nothing sent", code_of(e) == "aicall_config_invalid" and not v.seen and "cannot be appended to" in str(e.message), e)
fl = Flaky(DATA / "ai_flaky.jsonl")
r = ai.ask(route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=fl, budget=ai.Budget(1.0))
check("a paid reply whose ledger line cannot be written is still returned, marked unbooked, and its reservation keeps counting", r.text == "hello" and r.booked is False and fl.spent() == round(est, 6), (r.booked, fl.spent()))
v.script = [(400, {"error": "x"}, {})]
e = refusal(ai.ask, route(v), "S", "t", prices=PRICES, ledger=Flaky(DATA / "ai_flaky2.jsonl"))
check("and a failed call still raises its own coded error, not the disk's", code_of(e) == "aicall_http_error", e)
v.close()

# --- numbers
v = Vendor([(200, {**Vendor.ok(), "usage": {"input_tokens": 10 ** 400, "output_tokens": 5}}, {})])
led = ai.Ledger(DATA / "ai_huge.jsonl")
r = ai.ask(route(v), "S", "t", max_tokens=400, prices=PRICES, ledger=led, budget=ai.Budget(1.0))
check("a usage count of 10**400 is unknown: the call is booked at its estimate, nothing overflows", r.cost_usd == round(est, 6) and led.rows()[-1].get("cost_estimated") is True, (r.cost_usd, led.rows()[-1:]))
v.close()
sch = {"type": "object", "required": ["n"], "properties": {"n": {"type": "number"}}}
v = Vendor([(200, Vendor.ok(text='{"n": ' + "9" * 400 + "}"), {}), (200, Vendor.ok(text='{"n": 1}'), {})])
obj, _ = ai.ask_json(route(v), "S", "t", sch, prices=PRICES)
check("a 400-digit number for a number property does not fit: asked again, the fitting answer is returned", obj == {"n": 1} and len(v.seen) == 2, (obj, len(v.seen)))
v.close()
v = Vendor([])
for label, bad in (("negative", (-1.0, 5.0)), ("NaN", (float("nan"), 1.0)), ("a string", ("1", "5")), ("three numbers", (1.0, 2.0, 3.0)), ("infinite", (1.0, float("inf"))), ("huge", (10 ** 400, 1.0))):
    check(f"a price passed to ask that is {label}: ValueError before anything is sent", raises(lambda b=bad: ai.ask(route(v), "S", "t", prices={"fast-1": b}), ValueError) is not None and not v.seen, label)
check("a bool is not a count, a number or a price; a count past a trillion is unknown", ai._count(True) is None and not ai._finite(True) and ai.cost_usd(PRICES, "fast-1", True, True) is None
      and ai._count(10 ** 13) is None and ai._count(10 ** 12) == 10 ** 12 and not ai._finite(10 ** 400))
v.close()

# --- what can go wrong in the request
v = Vendor([])
waits = []
for label, odd in (("a set", {"type": "object", "properties": {"x": {1, 2}}}), ("a NaN", {"type": "object", "default": float("nan")})):
    e = refusal(ai.ask, route(v), "S", "t", schema=odd, prices=PRICES, sleep=no_sleep(waits))
    check(f"a schema holding {label} is refused before sending: coded, no request, no retries", code_of(e) == "aicall_config_invalid" and not v.seen and not waits, (e, v.seen, waits))
r = ai.ask(route(v), "S", "a\ud800b", prices=PRICES)
check("a lone surrogate in the prompt is sent (escaped) and hashed, not a UnicodeEncodeError", r.text == "hello" and len(v.seen) == 1)
led = ai.Ledger(DATA / "ai_imgcap.jsonl")
e = refusal(ai.ask, route(v), "S", "t", [img, img, img], max_tokens=10, prices=PRICES, ledger=led, budget=ai.Budget(0.003))
r = ai.ask(route(v), "S", "t", max_tokens=10, prices=PRICES, ledger=led, budget=ai.Budget(0.003))
check("an image counts in the estimate: three of them pass a cap the text alone fits under only if the cap allows them", code_of(e) == "aicall_daily_cap_exceeded" and r.text == "hello", e)
v.close()

# --- the key in the forms an encoder writes
k = 'sk-a/b"c\\d'
forms = [k, json.dumps(k)[1:-1], json.dumps(k)[1:-1].replace("/", "\\/"), k.replace("/", "\\/")]
check("redact hides the key as typed and as a JSON encoder writes it (quotes, backslashes, PHP's escaped slash)", all(ai.redact("x " + f + " y", k) == "x <key> y" for f in forms), [ai.redact("x " + f + " y", k) for f in forms])
v = Vendor([(400, b'{"error": "bad key ' + forms[2].encode() + b'"}', {})])                      # on the wire as written, not escaped a second time
odd_key = ai.Settings(key=k, base_url=v.url, protocol="anthropic", model="fast-1", task="review")
e = refusal(ai.ask, odd_key, "S", "t", prices=PRICES, sleep=no_sleep([]))
check("a 400 body that echoes the key the way PHP writes it does not leak it", code_of(e) == "aicall_http_error" and "sk-a" not in str(e.message), str(e.message))
v.close()

# --- fits
check("fits: a schema that is not well formed constrains nothing, and does not raise",
      all(ai.fits({"a": 1}, sc) is True for sc in ({"required": 3}, {"required": "ok"}, {"required": [3]}, {"type": {"a": 1}}, [1, 2], None, {"properties": {"a": []}}, {"properties": []})))
one = lambda t: {"properties": {"a": {"type": t}}}  # noqa: E731
check("fits: a list of types accepts a value of one it knows; a name it does not know is not a match, and a list of unknown names constrains nothing",
      ai.fits({"a": "x"}, one(["foo", "integer"])) is False and ai.fits({"a": 2}, one(["foo", "integer"])) is True and ai.fits({"a": "x"}, one(["foo"])) is True)
check("fits: 1.0 is an integer; 1.5, true, NaN and a 400-digit int are not; NaN and true are not numbers either",
      ai.fits({"a": 1.0}, one("integer")) and not any(ai.fits({"a": x}, one("integer")) for x in (1.5, True, float("nan"), 10 ** 400)) and not any(ai.fits({"a": x}, one("number")) for x in (True, float("nan"), 10 ** 400)))
check("fits: nested objects and the items of an array are checked", not ai.fits({"a": {"b": 1}}, {"properties": {"a": {"type": "object", "required": ["c"]}}})
      and not ai.fits({"a": [1, "x"]}, {"properties": {"a": {"type": "array", "items": {"type": "integer"}}}}) and ai.fits({"a": [1, 2]}, {"properties": {"a": {"type": "array", "items": {"type": "integer"}}}}))


print("[8] messages")
codes = {ln.split("\t")[0] for ln in (Path(ai.__file__).parent / "message_codes.d" / "ai.tsv").read_text(encoding="utf-8").splitlines()[1:]}
used = {c for _, c, _ in messages.msg_calls([Path(ai.__file__)], Path(ai.__file__).parent) if c}
check("every msg() code in ai.py is in kit/message_codes.d/ai.tsv and none there is unused", used == codes, (used ^ codes))

finish()
