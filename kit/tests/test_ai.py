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
"""

import json
import os
import stat
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
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
                outer.seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": json.loads(self.rfile.read(n) or b"{}")})
                status, body, extra = outer.script.pop(0) if outer.script else (200, outer.ok(), {})
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                for k, v in extra.items():
                    self.send_header(k, v)
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
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

print("[8] messages")
codes = {ln.split("\t")[0] for ln in (Path(ai.__file__).parent / "message_codes.d" / "ai.tsv").read_text(encoding="utf-8").splitlines()[1:]}
used = {c for _, c, _ in messages.msg_calls([Path(ai.__file__)], Path(ai.__file__).parent) if c}
check("every msg() code in ai.py is in kit/message_codes.d/ai.tsv and none there is unused", used == codes, (used ^ codes))

finish()
