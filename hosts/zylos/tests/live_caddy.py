"""The form login under a REAL Caddy (the other tests cannot: they have none).
Not run by tests/run.py (no `test_` prefix, it needs the caddy binary); a host that
has Caddy runs it once before it trusts a release:

    python3 hosts/zylos/tests/live_caddy.py [--caddy ~/zylos/bin/caddy]

It starts `bin/login.js` on a socket, a stand-in console that echoes the headers it
gets, and Caddy with the block printed from `Caddyfile.snippet` (the real file, its
placeholders filled), on 127.0.0.1:18080 with the admin API off. Then it checks what a
visitor and a spoofing visitor see. Nothing outside a temp dir is touched; the host's
own Caddy is not used or reloaded. Prints `RESULT: N passed` or the first failure.
"""

from __future__ import annotations

import http.client
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlencode

HERE = os.path.dirname(os.path.abspath(__file__))
ADAPTER = os.path.dirname(HERE)
LOGIN = os.path.join(ADAPTER, "bin", "login.js")
SITE_PORT, APP_PORT = 18080, 18081
PW = "correct horse battery"


def find_caddy() -> str:
    args = sys.argv[1:]
    cands = [args[args.index("--caddy") + 1]] if "--caddy" in args else []
    cands += [os.environ.get("CADDY", ""), os.path.expanduser("~/zylos/bin/caddy"), shutil.which("caddy") or ""]
    for c in cands:
        if c and os.path.exists(c):
            return c
    sys.exit("no caddy binary: pass --caddy PATH (this check needs a real one)")


class Echo(http.server.BaseHTTPRequestHandler):
    def do_any(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        body = json.dumps({"path": self.path, "method": self.command,
                           "headers": {k.lower(): v for k, v in self.headers.items()}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_any

    def log_message(self, *a):
        pass


def main() -> None:
    caddy = find_caddy()
    tmp = tempfile.mkdtemp(prefix="zl-live-")
    sock = os.path.join(tmp, "a", "auth.sock")
    users = os.path.join(tmp, "console.users")
    key = os.path.join(tmp, "session.key")
    subprocess.run(["node", "-e", "require(process.argv[1]).setPassword(process.argv[2],'alice',process.argv[3])", LOGIN, users, PW], check=True)
    procs = []
    try:
        srv = subprocess.Popen(["node", "-e", "const l=require(process.argv[1]);l.listen({sock:process.argv[2],usersFile:process.argv[3],keyFile:process.argv[4],"
                                "base:'/seo',title:'Live',userHeader:'X-Remote-User'}).on('listening',()=>console.log('up'))",
                                LOGIN, sock, users, key], stdout=subprocess.PIPE, text=True)
        procs.append(srv)
        assert srv.stdout.readline().strip() == "up", "login service did not start"
        app = http.server.ThreadingHTTPServer(("127.0.0.1", APP_PORT), Echo)
        threading.Thread(target=app.serve_forever, daemon=True).start()
        snippet = open(os.path.join(ADAPTER, "Caddyfile.snippet")).read()
        block = "\n".join(ln for ln in snippet.splitlines() if not ln.startswith("##"))
        for k, v in {"<NAME>": "live", "<BASE_PATH>": "/seo", "<PORT>": str(APP_PORT), "<AUTH_SOCK>": sock,
                     "<USERS_FILE>": users, "<USER_HEADER>": "X-Remote-User"}.items():
            block = block.replace(k, v)
        assert not re.search(r"<[A-Z_]+>", block), block
        cf = os.path.join(tmp, "Caddyfile")
        open(cf, "w").write("{\n    admin off\n    auto_https off\n}\n"
                            f"http://127.0.0.1:{SITE_PORT} {{\n{block}\n}}\n")
        v = subprocess.run([caddy, "validate", "--config", cf, "--adapter", "caddyfile"], capture_output=True, text=True)
        assert v.returncode == 0, f"caddy validate refused the block:\n{v.stderr[-1500:]}"
        cp = subprocess.Popen([caddy, "run", "--config", cf, "--adapter", "caddyfile"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        procs.append(cp)
        for _ in range(100):
            try:
                http.client.HTTPConnection("127.0.0.1", SITE_PORT, timeout=1).request("GET", "/")
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("caddy did not listen")

        def req(method, path, body=None, headers=None):
            c = http.client.HTTPConnection("127.0.0.1", SITE_PORT, timeout=10)
            h = dict(headers or {})
            if body is not None:
                h["Content-Type"] = "application/x-www-form-urlencoded"
            c.request(method, path, body=body, headers=h)
            r = c.getresponse()
            data = r.read().decode()
            c.close()
            return r, data

        n = 0

        def ok(cond, what):
            nonlocal n
            if not cond:
                raise AssertionError(what)
            n += 1
            print(f"  ok  {what}")

        spoof = {"X-Remote-User": "root"}
        r, _ = req("GET", "/seo/materials?lang=zh", headers=spoof)
        loc = r.getheader("Location") or ""
        ok(r.status == 302 and loc.startswith("/seo/login?next="), f"no session: {r.status} to {loc} (a spoofed X-Remote-User does not get in)")
        ok("%2Fseo%2Fmaterials%3Flang%3Dzh" in loc, "the page the visitor wanted is kept under the prefix in next=" + loc)
        r, body = req("GET", "/seo/login")
        ok(r.status == 200 and 'type="password"' in body and 'autocomplete="current-password"' in body, "the form is served through Caddy")
        r, _ = req("POST", "/seo/materials", "x=1", headers=spoof)
        ok(r.status == 401, f"a POST with no session is 401, got {r.status}")
        r, _ = req("GET", "/seo/LOGIN")
        ok(r.status in (404, 302), f"/seo/LOGIN never reaches the console ({r.status})")
        r, _ = req("POST", "/seo/login", urlencode({"username": "alice", "password": "wrong password!", "next": "/seo/"}))
        ok(r.status == 401 and not r.getheader("Set-Cookie"), "a wrong password is 401, no cookie")
        r, _ = req("POST", "/seo/login", urlencode({"username": "alice", "password": PW, "next": "/seo/materials"}))
        sc = r.getheader("Set-Cookie") or ""
        ok(r.status == 303 and r.getheader("Location") == "/seo/materials" and "HttpOnly" in sc and "Path=/seo" in sc, f"login: {r.status}, {sc.split(';')[0][:20]}...")
        cookie = sc.split(";")[0]
        r, body = req("GET", "/seo/materials", headers={"Cookie": cookie, **spoof})
        seen = json.loads(body)
        ok(r.status == 200 and seen["path"] == "/materials" and seen["headers"].get("x-remote-user") == "alice",
           f"the console sees the real user, not the spoofed one: {seen['headers'].get('x-remote-user')}")
        ok("cookie" not in seen["headers"], "the console does not get the session cookie")
        r, body = req("POST", "/seo/plan", "a=1", headers={"Cookie": cookie, "Content-Length": "3"})
        ok(r.status == 200 and json.loads(body)["method"] == "POST", "a POST with a session reaches the console as a POST")
        r, _ = req("GET", "/seo/materials", headers={"Cookie": cookie[:-3] + "AAA"})
        ok(r.status == 302, "a tampered cookie is sent to the form")
        print(f"RESULT: {n} passed")
    finally:
        for p in procs:
            p.terminate()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
