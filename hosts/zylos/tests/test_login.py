"""zylos/bin/login.js, the console's form login (it replaces Caddy's basic_auth):
the password hash, the session cookie, forward_auth's answers, the form's
fields (what lets a browser save it), the redirect rule, the throttle, the
Origin check, the file modes, and `lib.js passwd`.

Each test starts the real service on a unix socket in a temp dir and talks to
it as Caddy and a browser would.

Run: python3 hosts/zylos/tests/test_login.py
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402
from _host import ADAPTER, NODE, Host  # noqa: E402

LOGIN = os.path.join(ADAPTER, "bin", "login.js")
PW = "correct horse battery"

SERVER = """
const l = require(process.argv[1]);
const [sock, users, keyf, base] = process.argv.slice(2);
l.listen({ sock, usersFile: users, keyFile: keyf, setupFile: users + '.setup', base: base === undefined ? '/seo' : base, title: 'Shop', userHeader: 'X-Remote-User' })
  .on('listening', () => console.log('up'));
"""


class Conn(http.client.HTTPConnection):
    def __init__(self, sock):
        super().__init__("localhost")
        self.sock = None
        self._path = sock

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(self._path)


class Svc:
    """A running login service with one user, alice."""

    def __init__(self, user_line=True, base="/seo", sock_dir=None):
        self.base = base
        self.dir = tempfile.mkdtemp(prefix="login ")
        self.sock = os.path.join(sock_dir or self.dir, "auth.sock")
        self.users = os.path.join(self.dir, "console.users")
        self.key = os.path.join(self.dir, "session.key")
        if user_line:
            self.set("alice", PW)
        self.proc = None
        self.start()

    def start(self):
        self.proc = subprocess.Popen([NODE, "-e", SERVER, LOGIN, self.sock, self.users, self.key, self.base],
                                     stdout=subprocess.PIPE, text=True)
        assert self.proc.stdout.readline().strip() == "up"

    def stop(self):
        self.proc.terminate()
        self.proc.wait(10)

    def link(self, user="alice", now=None):
        code = ("const l=require(process.argv[1]);console.log(l.makeSetupToken(process.argv[2],process.argv[3]" + (f",{now}" if now else "") + ").token)")
        r = subprocess.run([NODE, "-e", code, LOGIN, self.users + ".setup", user], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    def set(self, name, pw):
        r = subprocess.run([NODE, "-e", "require(process.argv[1]).setPassword(process.argv[2], process.argv[3], process.argv[4])",
                            LOGIN, self.users, name, pw], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    def req(self, method, path, body=None, headers=None):
        c = Conn(self.sock)
        h = {"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.7", **(headers or {})}
        if body is not None:
            h["Content-Type"] = "application/x-www-form-urlencoded"
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read().decode()
        c.close()
        return r, data

    def login(self, user="alice", pw=PW, nxt="/seo/", headers=None, ip="203.0.113.7"):
        from urllib.parse import urlencode
        h = {"X-Forwarded-For": ip, **(headers or {})}
        return self.req("POST", "/login", urlencode({"username": user, "password": pw, "next": nxt}), h)

    def cookie(self, r):
        sc = r.getheader("Set-Cookie") or ""
        return sc.split(";")[0] if sc else ""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.stop()


def test_passwords_are_scrypt_and_a_bcrypt_line_cannot_sign_in():
    code = ("const l=require(process.argv[1]);const h=l.hashPassword('hunter2hunter2');"
            "console.log(JSON.stringify([h, l.verifyPassword('hunter2hunter2',h), l.verifyPassword('hunter2hunter3',h),"
            "l.verifyPassword('x','$2a$10$abcdefghijklmnopqrstuuabcdefghijklmnopqrstuvwxyz0123'), l.verifyPassword('x','')]))")
    h, good, bad, bcrypt, empty = json.loads(subprocess.run([NODE, "-e", code, LOGIN], capture_output=True, text=True).stdout)
    assert re.fullmatch(r"scrypt\$15\$8\$1\$[\w-]+\$[\w-]+", h) and good and not bad and not bcrypt and not empty, h
    with Svc(user_line=False) as s:
        with open(s.users, "w") as fh:
            fh.write("bob $2a$10$abcdefghijklmnopqrstuuabcdefghijklmnopqrstuvwxyz0123\n")
        r, body = s.login("bob", "anything")
        assert r.status == 401 and "Wrong username or password" in body and not s.cookie(r)
        stale = subprocess.run([NODE, "-e", "console.log(JSON.stringify(require(process.argv[1]).staleUsers(process.argv[2])))",
                                LOGIN, s.users], capture_output=True, text=True).stdout
        assert json.loads(stale) == ["bob"], stale


def test_the_form_is_one_a_browser_can_save():
    with Svc() as s:
        r, body = s.req("GET", "/login?next=%2Fseo%2Fmaterials")
        assert r.status == 200 and r.getheader("Cache-Control") == "no-store"
        assert 'method="post"' in body and 'action="/seo/login"' in body
        assert re.search(r'<input[^>]*name="username"[^>]*autocomplete="username"', body)
        assert re.search(r'<input[^>]*type="password"[^>]*autocomplete="current-password"', body)
        assert 'name="next" value="/seo/materials"' in body
        assert "Content-Security-Policy" in dict(r.getheaders()) and "form-action 'self'" in r.getheader("Content-Security-Policy")
        rz, bz = s.req("GET", "/login", headers={"Accept-Language": "zh-CN,zh;q=0.9"})
        assert "用户名" in bz and 'lang="zh"' in bz


def test_a_good_login_sets_a_private_cookie_and_forward_auth_names_the_user():
    with Svc() as s:
        r, _ = s.login(nxt="/seo/materials?lang=zh")
        sc = r.getheader("Set-Cookie")
        assert r.status == 303 and r.getheader("Location") == "/seo/materials?lang=zh", (r.status, r.getheader("Location"))
        for part in ("HttpOnly", "SameSite=Lax", "Secure", "Path=/seo", "Max-Age=1209600"):
            assert part in sc, (part, sc)
        ck = s.cookie(r)
        a, _ = s.req("GET", "/_auth", headers={"Cookie": ck})
        assert a.status == 200 and a.getheader("X-Remote-User") == "alice"
        # no cookie: a page request goes to the form with the page to come back to; a POST gets 401
        for sent in ("/seo/plan?x=1", "/plan?x=1"):          # Caddy may send the path with or without the prefix
            n, _ = s.req("GET", "/_auth", headers={"X-Forwarded-Uri": sent, "X-Forwarded-Method": "GET"})
            assert n.status == 302 and n.getheader("Location") == "/seo/login?next=%2Fseo%2Fplan%3Fx%3D1", (sent, n.getheader("Location"))
        p, _ = s.req("GET", "/_auth", headers={"X-Forwarded-Method": "POST"})
        assert p.status == 401 and not p.getheader("X-Remote-User")
        # over plain http the cookie is not marked Secure (a test on localhost still works)
        h, _ = s.login(headers={"X-Forwarded-Proto": "http"})
        assert "Secure" not in h.getheader("Set-Cookie")


def test_a_wrong_password_or_unknown_user_is_the_same_401():
    with Svc() as s:
        for user, pw in [("alice", "wrong password!"), ("nobody", PW), ("", ""), ("alice", "")]:
            r, body = s.login(user, pw)
            assert r.status == 401 and "Wrong username or password" in body and not s.cookie(r), (user, r.status)


def test_a_forged_tampered_or_old_cookie_is_refused():
    with Svc() as s:
        ck = s.cookie(s.login()[0])
        name, val = ck.split("=", 1)
        parts = val.split(".")
        for label, bad in [("mac cut", ".".join(parts[:3]) + "." + parts[3][:-2] + "AA"),
                           ("other user", "Ym9i." + ".".join(parts[1:])),
                           ("later expiry", parts[0] + ".9999999999." + ".".join(parts[2:])),
                           ("garbage", "x.y.z.w"), ("empty", "")]:
            a, _ = s.req("GET", "/_auth", headers={"Cookie": f"{name}={bad}"})
            assert a.status == 302, (label, a.status)
        # an expired token: made with a clock a month back
        code = ("const l=require(process.argv[1]);const k=l.loadKey(process.argv[2]);const u=l.readUsers(process.argv[3]);"
                "const t=l.makeToken(k,'alice',u.get('alice'),Date.now()-30*86400e3);"
                "console.log(JSON.stringify([l.checkToken(k,u,t), l.checkToken(k,u,t,Date.now()-30*86400e3)]))")
        old, fresh = json.loads(subprocess.run([NODE, "-e", code, LOGIN, s.key, s.users], capture_output=True, text=True).stdout)
        assert old is None and fresh == "alice"


def test_a_new_password_or_a_removed_user_ends_the_sessions_at_once():
    with Svc() as s:
        s.set("bob", PW)
        ca, cb = s.cookie(s.login()[0]), s.cookie(s.login("bob")[0])
        assert s.req("GET", "/_auth", headers={"Cookie": ca})[0].status == 200
        s.set("alice", "a different password")
        assert s.req("GET", "/_auth", headers={"Cookie": ca})[0].status == 302, "a new password ends the old sessions"
        assert s.req("GET", "/_auth", headers={"Cookie": cb})[0].status == 200, "another person is not affected"
        r = subprocess.run([NODE, "-e", "require(process.argv[1]).setPassword(process.argv[2], 'bob', null)", LOGIN, s.users])
        assert r.returncode == 0
        assert s.req("GET", "/_auth", headers={"Cookie": cb})[0].status == 302, "a removed person is out"


def test_next_stays_under_the_base():
    with Svc() as s:
        for nxt in ["//evil.example.com/x", "https://evil.example.com/", "/other", "/seo/../x", "\\\\evil", "/seo/login", "/seo/logout",
                    "/seo/x\r\nSet-Cookie: a=b", "", "javascript:alert(1)"]:
            r, _ = s.login(nxt=nxt, ip=f"198.51.100.{abs(hash(nxt)) % 200}")
            loc = r.getheader("Location")
            assert r.status == 303 and loc in ("/seo/", "/seo/../x"), (nxt, loc)
            assert "\n" not in (loc or ""), nxt
        r, body = s.req("GET", "/login?next=//evil.example.com")
        assert 'name="next" value="/seo/"' in body


def test_a_site_root_console_cannot_be_used_as_an_open_redirect():
    with Svc(base="") as s:
        for i, nxt in enumerate(["/\t/evil.example.com", "/ /evil.example.com", "/\x0b/evil.example.com", "//evil.example.com", "/\\evil.example.com",
                                 "/%09/evil.example.com"]):
            r, _ = s.login(nxt=nxt, ip=f"198.51.100.{i}")
            loc = r.getheader("Location")
            assert r.status == 303 and (loc == "/" or loc == "/%09/evil.example.com"), (nxt, loc)   # %09 stays text: browsers do not decode a Location
        r, _ = s.login(nxt="/materials?lang=zh")
        assert r.getheader("Location") == "/materials?lang=zh" and "Path=/;" in r.getheader("Set-Cookie")


def test_a_hash_scrypt_would_throw_on_is_a_refusal_not_a_crash():
    with Svc() as s:
        with open(s.users, "a") as fh:
            fh.write("bob scrypt$20$16$4$QUJDRA$QUJDRA\n")      # over the memory bound
            fh.write("carl scrypt$15$8$1$QUJDRA$QUJDRA\n")      # a valid shape, a wrong key
        for u in ("bob", "carl"):
            assert s.login(u, PW)[0].status == 401, u
        assert s.login()[0].status == 303, "and the service still answers"


def test_the_service_makes_its_directory_private_and_leaves_the_umask_alone():
    d = tempfile.mkdtemp(prefix="login ")
    sub = os.path.join(d, "a", "b")
    with Svc(sock_dir=sub) as s:
        assert stat.S_IMODE(os.stat(sub).st_mode) == 0o700 and stat.S_IMODE(os.stat(s.sock).st_mode) == 0o600
    lax = os.path.join(d, "lax")
    os.mkdir(lax, 0o755)
    with Svc(sock_dir=lax):
        assert stat.S_IMODE(os.stat(lax).st_mode) == 0o700, "a lax directory is tightened"
    code = ("const l=require(process.argv[1]);const before=process.umask();"
            "const s=l.listen({sock:process.argv[2],usersFile:process.argv[3],keyFile:process.argv[4],base:'/x'});"
            "console.log(before.toString(8), process.umask().toString(8));s.close();")
    r = subprocess.run([NODE, "-e", code, LOGIN, os.path.join(d, "u", "s.sock"), os.path.join(d, "users"), os.path.join(d, "key")],
                       capture_output=True, text=True)
    before, after = r.stdout.split()
    assert before == after, (r.stdout, r.stderr)             # the console this process starts inherits the umask
    link = os.path.join(d, "link")
    os.symlink(d, link)
    r2 = subprocess.run([NODE, "-e", "try{require(process.argv[1]).listen({sock:process.argv[2],usersFile:'x',keyFile:'y',base:''})}catch(e){console.log('refused')}",
                         LOGIN, os.path.join(link, "s.sock")], capture_output=True, text=True)
    assert "refused" in r2.stdout, (r2.stdout, r2.stderr)    # a symlinked directory is not ours to trust


def test_a_one_time_link_lets_a_person_set_their_own_password():
    from urllib.parse import urlencode
    with Svc(user_line=False) as s:
        tok = s.link("newperson")
        assert len(tok) >= 40 and tok not in open(s.users + ".setup").read(), "only a hash of the token is kept"
        r, body = s.req("GET", f"/setup?token={tok}")
        assert r.status == 200 and 'autocomplete="new-password"' in body and "newperson" in body and 'name="token"' in body
        assert stat.S_IMODE(os.stat(s.users + ".setup").st_mode) == 0o600
        # a typo does not burn the link
        bad = s.req("POST", "/setup", urlencode({"token": tok, "password": "short", "password2": "short"}))[0]
        diff = s.req("POST", "/setup", urlencode({"token": tok, "password": PW, "password2": PW + "x"}))[0]
        assert bad.status == 400 and diff.status == 400
        ok = s.req("POST", "/setup", urlencode({"token": tok, "username": "x", "password": PW, "password2": PW}))[0]
        assert ok.status == 303 and ok.getheader("Location") == "/seo/" and "HttpOnly" in ok.getheader("Set-Cookie")
        a, _ = s.req("GET", "/_auth", headers={"Cookie": s.cookie(ok)})
        assert a.status == 200 and a.getheader("X-Remote-User") == "newperson", "signed in as the link's user, not the form's"
        assert s.login("newperson", PW)[0].status == 303, "and the password works at the login form"
        # once only
        again = s.req("POST", "/setup", urlencode({"token": tok, "password": "another password", "password2": "another password"}))[0]
        gone = s.req("GET", f"/setup?token={tok}")[0]
        assert again.status == 410 and gone.status == 410
        assert s.login("newperson", "another password")[0].status == 401


def test_a_setup_link_expires_is_replaced_by_a_newer_one_and_guessing_is_throttled():
    with Svc(user_line=False) as s:
        old = s.link("amy", now=int(time.time() * 1000) - 31 * 60_000)
        assert s.req("GET", f"/setup?token={old}")[0].status == 410, "30 minutes"
        first = s.link("amy")
        second = s.link("amy")
        assert s.req("GET", f"/setup?token={first}")[0].status == 410, "a newer link replaces the older one"
        assert s.req("GET", f"/setup?token={second}")[0].status == 200
        assert s.req("GET", "/setup")[0].status == 410 and s.req("GET", "/setup?token=%00")[0].status == 410
        for i in range(6):
            s.req("GET", f"/setup?token=guess{i}", headers={"X-Forwarded-For": "198.51.100.200"})
        assert s.req("GET", f"/setup?token={second}", headers={"X-Forwarded-For": "198.51.100.200"})[0].status == 429
        assert s.req("POST", "/setup", "token=x&password=aaaaaaaaaaaa&password2=aaaaaaaaaaaa",
                     {"Origin": "https://evil.example.com", "Host": "agent.example.com"})[0].status == 403


def test_passwd_link_needs_no_terminal_and_prints_the_public_address():
    with Host() as host:
        host.configure({"SHOP_CONSOLE_ALLOW_HOST": "agent.example.com"})
        lib = os.path.join(host.adapter, "lib.js")
        r = host.node(lib, "passwd", "alice", "--link")
        assert r.returncode == 0 and "https://agent.example.com/shop/setup?token=" in r.stdout and "works once" in r.stdout, (r.stdout, r.stderr)
        tok = r.stdout.strip().split("token=")[1].strip()
        assert not os.path.exists(os.path.join(host.data, "console.users")), "nothing is created until the person sets a password"
        saved = open(os.path.join(host.data, "console", "setup-tokens.json")).read()
        assert tok not in saved and "alice" in saved
        assert host.node(lib, "passwd", "--remove", "alice", "--link").returncode == 2
        assert host.node(lib, "passwd", "a b", "--link").returncode == 1


def test_five_wrong_passwords_lock_that_user_and_that_address():
    with Svc() as s:
        for i in range(5):
            assert s.login(pw=f"wrong password {i}")[0].status == 401
        r, body = s.login()                       # the right password, now refused
        assert r.status == 429 and "Too many tries" in body and not s.cookie(r)
        r2, _ = s.login(user="alice", ip="198.51.100.9")
        assert r2.status == 429, "the user is locked wherever it comes from"
        r3, _ = s.login(user="carol", pw="x", ip="203.0.113.7")
        assert r3.status == 429, "the address is locked whoever it tries"
        # a visitor from elsewhere with a good login, for a user nobody attacked
        s.set("bob", PW)
        assert s.login("bob", ip="198.51.100.77")[0].status == 303


def test_a_post_from_another_origin_is_refused():
    with Svc() as s:
        r, _ = s.login(headers={"Origin": "https://evil.example.com", "Host": "agent.example.com"})
        assert r.status == 403 and not s.cookie(r)
        ok, _ = s.login(headers={"Origin": "https://agent.example.com", "Host": "agent.example.com"})
        assert ok.status == 303
        out, _ = s.req("POST", "/logout", "", {"Origin": "https://evil.example.com", "Host": "agent.example.com"})
        assert out.status == 403


def test_logout_clears_the_cookie():
    with Svc() as s:
        r, body = s.req("GET", "/logout")
        assert r.status == 200 and 'method="post"' in body and 'action="/seo/logout"' in body
        o, _ = s.req("POST", "/logout", "")
        sc = o.getheader("Set-Cookie")
        assert o.status == 200 and "Max-Age=0" in sc and "Path=/seo" in sc


def test_other_paths_and_big_bodies_are_not_served():
    with Svc() as s:
        assert s.req("GET", "/")[0].status == 404 and s.req("GET", "/seo/")[0].status == 404
        assert s.req("POST", "/_auth", "")[0].status == 404
        c = Conn(s.sock)
        try:
            c.request("POST", "/login", body="username=a&password=" + "x" * 100000,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
            status = c.getresponse().status
        except (ConnectionError, http.client.HTTPException, OSError):
            status = 413                           # the server closed on us while we were still sending
        assert status == 413, "an oversized login body is refused, not read"
        assert s.req("GET", "/login")[0].status == 200, "and the service is still up"


def test_the_socket_and_the_key_are_private_and_sessions_survive_a_restart():
    with Svc() as s:
        for f in (s.sock, s.key, s.users):
            assert stat.S_IMODE(os.stat(f).st_mode) == 0o600, (f, oct(os.stat(f).st_mode))
        ck = s.cookie(s.login()[0])
        s.stop()
        s.start()
        a, _ = s.req("GET", "/_auth", headers={"Cookie": ck})
        assert a.status == 200 and a.getheader("X-Remote-User") == "alice", "the key is kept in a file, so a restart keeps sessions"


def test_passwd_needs_a_terminal_and_validates():
    with Host() as host:
        host.configure({})
        lib = os.path.join(host.adapter, "lib.js")
        users = os.path.join(host.data, "console.users")
        r = host.node(lib, "passwd", "alice")                   # no tty under the test
        assert r.returncode == 2 and "needs a terminal" in r.stderr and not os.path.exists(users), r.stderr
        assert host.node(lib, "passwd").returncode == 2
        assert host.node(lib, "passwd", "--remove", "ghost").returncode == 1
        bad = host.node("-e", "try{require(process.argv[1]).setPassword(process.argv[2],'a b','x'.repeat(12))}catch(e){console.log(e.message)}",
                        os.path.join(host.adapter, "bin", "login.js"), users)
        assert "not a user name" in bad.stdout, bad.stdout
        short = host.node("-e", "try{require(process.argv[1]).setPassword(process.argv[2],'amy','short')}catch(e){console.log(e.message)}",
                          os.path.join(host.adapter, "bin", "login.js"), users)
        assert "at least 10" in short.stdout, short.stdout


def test_passwd_at_a_real_terminal_writes_a_scrypt_line_without_echo():
    import pty
    import select
    with Host() as host:
        host.configure({})
        lib = os.path.join(host.adapter, "lib.js")
        users = os.path.join(host.data, "console.users")
        pid, fd = pty.fork()
        if pid == 0:
            os.environ.update(host.env())
            os.execv(NODE, [NODE, lib, "passwd", "alice"])
        out = b""
        sent = 0
        deadline = time.time() + 20
        while time.time() < deadline:                    # answer each prompt when it appears
            ready, _, _ = select.select([fd], [], [], 0.5)
            if not ready:
                continue
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            out += data
            if b"min 10 characters" in out and sent == 0:
                os.write(fd, (PW + "\r").encode())
                sent = 1
            elif b"again:" in out and sent == 1:
                os.write(fd, (PW + "\r").encode())
                sent = 2
            elif b"end now" in out:
                break
        _, status = os.waitpid(pid, 0)
        text = out.decode(errors="replace")
        assert os.WEXITSTATUS(status) == 0 and "alice added" in text, text
        assert PW not in text, "the password was echoed"
        line = open(users).read().strip()
        assert line.startswith("alice scrypt$") and PW not in line and stat.S_IMODE(os.stat(users).st_mode) == 0o600, line


if __name__ == "__main__":
    _t.main(globals())
