"""zylos/bin/login.js, the console's sign-in by a one-time link (0.8.0, the owner's R41): the
link's shape (28 letters a chat app leaves alone, 2 of them a check), a cut-short link told
apart from a used or expired one, a GET that never spends it (a chat app's link preview fetches
it), the POST that spends it once, a newer link in place of an older, the throttle, the 90-day
cookie on the base path, a 0.7.x line still a valid stamp, `signout` and `remove` ending
sessions at once, the /login and /setup pages that now only say what to do, forward_auth's
answers, the Origin check, the file modes, and kit.guards.asks over every page drawn.

Each test starts the real service on a unix socket in a temp dir and talks to it as Caddy and a
browser would.

Run: python3 hosts/zylos/tests/test_login.py
"""

from __future__ import annotations

import hashlib
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

ROOT = os.path.dirname(os.path.dirname(ADAPTER))      # the playbook: the test may import the kit, the adapter never does
LOGIN = os.path.join(ADAPTER, "bin", "login.js")
ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"
DAYS90 = 90 * 86400
INCOMPLETE_ZH = "这个链接不完整，可能在转发时被截断了。请让发给你的人重新发一个。"
DEAD_ZH = "这个链接已经用过或已过期，请重新要一个。"

SERVER = """
const l = require(process.argv[1]);
const [sock, users, keyf, links, base, allow] = process.argv.slice(2);
l.listen({ sock, usersFile: users, keyFile: keyf, linksFile: links, base, title: 'Shop', userHeader: 'X-Remote-User',
           allowHosts: allow ? allow.split(',') : [] })
  .on('listening', () => console.log('up'));
"""


def node(code, *args):
    r = subprocess.run([NODE, "-e", code, LOGIN, *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


class Conn(http.client.HTTPConnection):
    def __init__(self, sock):
        super().__init__("localhost")
        self.sock = None
        self._path = sock

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(self._path)


class Svc:
    """A running sign-in service; its users and links files may be a host's own."""

    def __init__(self, base="/seo", sock_dir=None, allow="", users=None, links=None):
        self.base = base
        self.allow = allow
        self.dir = tempfile.mkdtemp(prefix="login ")
        self.sock = os.path.join(sock_dir or self.dir, "auth.sock")
        self.users = users or os.path.join(self.dir, "console.users")
        self.links = links or os.path.join(self.dir, "console", "sign-in-links.json")
        self.key = os.path.join(self.dir, "session.key")
        self.proc = None
        self.start()

    def start(self):
        self.proc = subprocess.Popen([NODE, "-e", SERVER, LOGIN, self.sock, self.users, self.key, self.links, self.base, self.allow],
                                     stdout=subprocess.PIPE, text=True)
        assert self.proc.stdout.readline().strip() == "up"

    def stop(self):
        self.proc.terminate()
        self.proc.wait(10)

    def link(self, user="alice", now=None):
        return node("const l=require(process.argv[1]);console.log(l.makeLink(process.argv[2],process.argv[3]"
                    + (f",{now}" if now else "") + ").token)", self.links, user).strip()

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

    def sign_in(self, token, headers=None):
        return self.req("POST", f"/in/{token}", "", headers)

    def cookie(self, r):
        sc = r.getheader("Set-Cookie") or ""
        return sc.split(";")[0] if sc else ""

    def who(self, cookie):
        a, _ = self.req("GET", "/_auth", headers={"Cookie": cookie})
        return a.getheader("X-Remote-User") if a.status == 200 else None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.stop()


def check_of(body: str) -> str:
    d = hashlib.sha256(body.encode()).digest()
    return ALPHABET[d[0] & 31] + ALPHABET[d[1] & 31]


def test_the_link_is_28_letters_from_the_alphabet_with_a_check():
    tokens = json.loads(node("const l=require(process.argv[1]);console.log(JSON.stringify(Array.from({length:300},()=>l.newLinkToken())))"))
    assert len(set(tokens)) == 300
    for t in tokens:
        assert len(t) == 28 and set(t) <= set(ALPHABET) and t[26:] == check_of(t[:26]), t
    assert not set("lo01-_?#") & set(ALPHABET) and len(ALPHABET) == 32, "26 letters of 5 bits: 130 bits"
    seen = set("".join(tokens))
    assert seen == set(ALPHABET), ("every letter is used", sorted(set(ALPHABET) - seen))
    t = tokens[0]
    bad_check = t[:26] + next(c + d for c in ALPHABET for d in ALPHABET if c + d != t[26:])
    cases = {"whole": t, "cut short": t[:27], "one longer": t + "a", "a wrong check": bad_check,
             "an l": t[:5] + "l" + t[6:], "a 0": "0" + t[1:], "empty": ""}
    got = json.loads(node("const l=require(process.argv[1]);const c=JSON.parse(process.argv[2]);"
                          "console.log(JSON.stringify(Object.fromEntries(Object.entries(c).map(([k,v])=>[k,l.linkShape(v)]))))",
                          json.dumps(cases)))
    assert got == {k: k == "whole" for k in cases}, got


def test_a_get_shows_the_name_and_one_button_and_never_spends_the_link():
    with Svc() as s:
        tok = s.link("newperson")
        for method in ("GET", "HEAD", "GET", "GET"):           # a link preview, then the person, then a reload
            r, body = s.req(method, f"/in/{tok}")
            assert r.status == 200 and not r.getheader("Set-Cookie"), (method, r.status)
        assert "newperson" in body and body.count("<form") == 1 and body.count("<button") == 1 and "<input" not in body
        assert re.search(rf'<form method="post" action="/seo/in/{tok}" data-no="[^"]+">', body), body
        assert "Content-Security-Policy" in dict(r.getheaders()) and r.getheader("Cache-Control") == "no-store"
        assert not os.path.exists(s.users), "nothing is written by a GET"
        _, zh = s.req("GET", f"/in/{tok}", headers={"Accept-Language": "zh-CN,zh;q=0.9"})
        assert ">登录</button>" in zh and 'lang="zh"' in zh
        ok, _ = s.sign_in(tok)
        assert ok.status == 303, "the link still works after every GET"


def test_the_post_spends_the_link_once_and_sets_a_90_day_cookie_on_the_base_path():
    with Svc() as s:
        tok = s.link("newperson")
        t0 = int(time.time())
        r, _ = s.sign_in(tok)
        sc = r.getheader("Set-Cookie")
        assert r.status == 303 and r.getheader("Location") == "/seo/", (r.status, r.getheader("Location"))
        for part in ("HttpOnly", "SameSite=Lax", "Secure", "Path=/seo;", f"Max-Age={DAYS90}"):
            assert part in sc, (part, sc)
        exp = int(s.cookie(r).split("=", 1)[1].split(".")[1])
        assert abs(exp - (t0 + DAYS90)) < 60, "the cookie itself says 90 days too"
        assert s.who(s.cookie(r)) == "newperson"
        line = open(s.users).read()
        assert re.fullmatch(r"newperson link\$[\w-]{20,}\n", line) and stat.S_IMODE(os.stat(s.users).st_mode) == 0o600, line
        again, body = s.sign_in(tok)
        assert again.status == 410 and not again.getheader("Set-Cookie") and "used or has expired" in body
        assert s.req("GET", f"/in/{tok}")[0].status == 410, "once only"
        # over plain http the cookie is not marked Secure (a test on localhost still works)
        h, _ = s.sign_in(s.link("other"), headers={"X-Forwarded-Proto": "http"})
        assert h.status == 303 and "Secure" not in h.getheader("Set-Cookie")


def test_a_cut_short_link_is_incomplete_not_used_or_expired():
    with Svc() as s:
        tok = s.link()
        old = s.link("amy", now=int(time.time() * 1000) - 31 * 60_000)
        zh = {"Accept-Language": "zh-CN,zh;q=0.9"}
        for label, path in [("cut short", f"/in/{tok[:20]}"), ("one letter lost", f"/in/{tok[:-1]}"),
                            ("a wrong check", f"/in/{tok[:26]}{'a' if tok[26] != 'a' else 'b'}{tok[27]}"),
                            ("no token", "/in/"), ("the 0.7 shape", "/in/" + "A" * 20 + "-_" + "b" * 21)]:
            r, body = s.req("GET", path, headers=zh)
            assert r.status == 400 and INCOMPLETE_ZH in body and DEAD_ZH not in body, (label, r.status, body)
            p, _ = s.req("POST", path, "")
            assert p.status == 400 and not p.getheader("Set-Cookie"), label
        _, en = s.req("GET", f"/in/{tok[:20]}")
        assert "This link is incomplete" in en and "cut off when it was forwarded" in en
        r, body = s.req("GET", f"/in/{old}", headers=zh)
        assert r.status == 410 and DEAD_ZH in body and INCOMPLETE_ZH not in body, "30 minutes, then expired"
        assert s.sign_in(old)[0].status == 410
        s.sign_in(tok)
        r, body = s.req("GET", f"/in/{tok}", headers=zh)
        assert r.status == 410 and DEAD_ZH in body, "used"
        fresh = s.link("bea")
        assert s.req("GET", f"/in/{fresh.upper()}/")[0].status == 200, "a chat app's capitals or trailing slash do not break it"


def test_a_newer_link_replaces_the_older_and_only_a_hash_is_kept():
    with Svc() as s:
        first, second, bob = s.link("amy"), s.link("amy"), s.link("bob")
        saved = open(s.links).read()
        assert all(t not in saved for t in (first, second, bob)) and "amy" in saved, "only a hash of the token is kept"
        assert stat.S_IMODE(os.stat(s.links).st_mode) == 0o600
        assert s.req("GET", f"/in/{first}")[0].status == 410, "a newer link replaces the older one"
        assert s.req("GET", f"/in/{second}")[0].status == 200 and s.req("GET", f"/in/{bob}")[0].status == 200, "another name's link stays"


def test_wrong_tokens_are_throttled_per_address():
    with Svc() as s:
        good = s.link()
        guesses = json.loads(node("const l=require(process.argv[1]);console.log(JSON.stringify(Array.from({length:6},()=>l.newLinkToken())))"))
        for g in guesses[:5]:                                 # whole tokens nobody made: guesses
            assert s.req("GET", f"/in/{g}", headers={"X-Forwarded-For": "198.51.100.200"})[0].status == 410
        r, body = s.req("GET", f"/in/{good}", headers={"X-Forwarded-For": "198.51.100.200"})
        assert r.status == 429 and "Too many tries" in body, "that address waits, even with a good link"
        assert s.sign_in(good, headers={"X-Forwarded-For": "198.51.100.200"})[0].status == 429, "the POST too"
        for i in range(8):                                    # a cut-short link tried again and again is no guess
            s.req("GET", f"/in/{good[:20]}", headers={"X-Forwarded-For": "198.51.100.201"})
        assert s.req("GET", f"/in/{good}", headers={"X-Forwarded-For": "198.51.100.201"})[0].status == 200
        assert s.sign_in(good, headers={"X-Forwarded-For": "198.51.100.9"})[0].status == 303, "another address signs in"


def test_a_second_device_does_not_sign_the_first_one_out():
    with Svc() as s:
        a = s.cookie(s.sign_in(s.link())[0])
        b = s.cookie(s.sign_in(s.link())[0])
        assert s.who(a) == "alice" and s.who(b) == "alice"


def test_a_0_7_line_is_still_a_valid_stamp():
    """A host upgrading from 0.7.x keeps its `scrypt$` lines (and any bcrypt line from before): the cookie
    a 0.7 login set still works until it expires, and a link sign-in leaves the line as it was."""
    with Svc() as s:
        scrypt = "scrypt$15$8$1$QUJDRA$QUJDRA"
        bcrypt = "$2a$10$abcdefghijklmnopqrstuuabcdefghijklmnopqrstuvwxyz0123"
        os.makedirs(os.path.dirname(s.users), exist_ok=True)
        with open(s.users, "w") as fh:
            fh.write(f"# kept\nalice {scrypt}\nbob {bcrypt}\n")
        old = node("const l=require(process.argv[1]);console.log(l.makeToken(l.loadKey(process.argv[2]),'alice',process.argv[3]))", s.key, scrypt).strip()
        name = s.cookie(s.sign_in(s.link("carl"))[0]).split("=")[0]
        assert s.who(f"{name}={old}") == "alice", "a 0.7.x cookie keeps working"
        for who in ("alice", "bob"):
            assert s.who(s.cookie(s.sign_in(s.link(who))[0])) == who, who
        lines = open(s.users).read().splitlines()
        assert lines[:3] == ["# kept", f"alice {scrypt}", f"bob {bcrypt}"] and lines[3].startswith("carl link$"), lines
        assert s.who(f"{name}={old}") == "alice", "and still after alice signed in by a link"


def test_signout_and_remove_end_every_session_at_once():
    with Host() as host:
        host.configure({"SHOP_CONSOLE_ALLOW_HOST": "agent.example.com"})
        lib = os.path.join(host.adapter, "lib.js")
        users = os.path.join(host.data, "console.users")
        links = os.path.join(host.data, "console", "sign-in-links.json")

        def link(name):
            r = host.node(lib, "link", name)
            assert r.returncode == 0, r.stderr
            return r.stdout.strip().split("/shop/in/")[1].strip()

        with Svc(base="/shop", users=users, links=links) as s:
            a1, a2, b = (s.cookie(s.sign_in(link(n))[0]) for n in ("alice", "alice", "bob"))
            assert [s.who(c) for c in (a1, a2, b)] == ["alice", "alice", "bob"]
            pending = link("alice")
            r = host.node(lib, "signout", "alice")
            assert r.returncode == 0 and "signed out on every device" in r.stdout, (r.stdout, r.stderr)
            assert s.who(a1) is None and s.who(a2) is None, "every device of alice"
            assert s.who(b) == "bob", "another person is not affected"
            assert s.req("GET", f"/in/{pending}")[0].status == 410, "an unused link of alice is dropped too"
            a3 = s.cookie(s.sign_in(link("alice"))[0])
            assert s.who(a3) == "alice", "a new link signs her in again"
            r = host.node(lib, "remove", "bob")
            assert r.returncode == 0 and "removed" in r.stdout, r.stderr
            assert s.who(b) is None and "bob" not in open(users).read()
            assert s.who(a3) == "alice"
            assert host.node(lib, "signout", "ghost").returncode == 1 and host.node(lib, "remove", "ghost").returncode == 1


def test_link_needs_no_terminal_and_prints_the_public_address():
    with Host() as host:
        host.configure({"SHOP_CONSOLE_ALLOW_HOST": "agent.example.com"})
        lib = os.path.join(host.adapter, "lib.js")
        r = host.node(lib, "link", "alice")
        url = r.stdout.strip().splitlines()[-1]
        assert r.returncode == 0 and "works once" in r.stdout and re.fullmatch(re.escape("https://agent.example.com/shop/in/") + "[a-z2-9]{28}", url), (r.stdout, r.stderr)
        assert not os.path.exists(os.path.join(host.data, "console.users")), "nothing is created until the person signs in"
        saved = open(os.path.join(host.data, "console", "sign-in-links.json")).read()
        assert url.rsplit("/", 1)[1] not in saved and "alice" in saved
        for args, code in [(["link"], 2), (["link", "-x"], 2), (["link", "a", "b"], 2), (["link", "a b"], 1),
                           (["signout"], 2), (["remove"], 2), (["frobnicate"], 2)]:
            assert host.node(lib, *args).returncode == code, args
        old = host.node(lib, "passwd", "alice", "--link")
        assert old.returncode == 2 and "link NAME" in old.stderr, "passwd is gone and says what replaced it"


def test_link_skips_a_loopback_host_for_the_public_one():
    """Issue #485: the first allowed host may be the machine's own (localhost); the link names the public one."""
    for allow, want in (("localhost,seo.example.com", "https://seo.example.com/shop/in/"),
                        ("127.0.0.1:8766 [::1]:8766 seo.example.com:8443", "https://seo.example.com:8443/shop/in/"),
                        ("localhost", "<the console's public address>/shop/in/"),
                        ("localhost.example.com", "https://localhost.example.com/shop/in/")):
        with Host() as host:
            host.configure({"SHOP_CONSOLE_ALLOW_HOST": allow})
            r = host.node(os.path.join(host.adapter, "lib.js"), "link", "alice")
            assert r.returncode == 0 and want in r.stdout, (allow, r.stdout, r.stderr)
            assert ("needs the console's public name" in r.stdout) == want.startswith("<"), (allow, r.stdout)


def test_login_and_setup_only_say_what_to_do():
    from urllib.parse import urlencode
    with Svc() as s:
        r, body = s.req("GET", "/login")
        assert r.status == 200 and "<form" not in body and "<input" not in body and "ask the agent for a sign-in link" in body
        _, zh = s.req("GET", "/login", headers={"Accept-Language": "zh"})
        assert "登录链接" in zh and 'lang="zh"' in zh
        p, _ = s.req("POST", "/login", urlencode({"username": "alice", "password": "correct horse battery", "next": "/seo/"}))
        assert p.status == 410 and not p.getheader("Set-Cookie"), "a saved 0.7 password form checks nothing"
        for method, path, body in [("GET", "/setup?token=" + "A" * 43, None), ("POST", "/setup", "token=x&password=aaaaaaaaaaaa&password2=aaaaaaaaaaaa")]:
            r, text = s.req(method, path, body)
            assert r.status == 410 and "older version" in text and not r.getheader("Set-Cookie"), (method, r.status)
        _, zh = s.req("GET", "/setup?token=x", headers={"Accept-Language": "zh"})
        assert "旧版本" in zh


def test_forward_auth_answers_and_a_forged_or_old_cookie_is_refused():
    with Svc() as s:
        r, _ = s.sign_in(s.link())
        ck = s.cookie(r)
        a, _ = s.req("GET", "/_auth", headers={"Cookie": ck})
        assert a.status == 200 and a.getheader("X-Remote-User") == "alice"
        n, _ = s.req("GET", "/_auth", headers={"X-Forwarded-Uri": "/seo/plan?x=1", "X-Forwarded-Method": "GET"})
        assert n.status == 302 and n.getheader("Location") == "/seo/login", n.getheader("Location")
        p, _ = s.req("GET", "/_auth", headers={"X-Forwarded-Method": "POST"})
        assert p.status == 401 and not p.getheader("X-Remote-User")
        name, val = ck.split("=", 1)
        parts = val.split(".")
        for label, bad in [("mac cut", ".".join(parts[:3]) + "." + parts[3][:-2] + "AA"),
                           ("other user", "Ym9i." + ".".join(parts[1:])),
                           ("later expiry", parts[0] + ".9999999999." + ".".join(parts[2:])),
                           ("garbage", "x.y.z.w"), ("empty", "")]:
            assert s.req("GET", "/_auth", headers={"Cookie": f"{name}={bad}"})[0].status == 302, label
        code = ("const l=require(process.argv[1]);const k=l.loadKey(process.argv[2]);const u=l.readUsers(process.argv[3]);"
                "const back=Date.now()-91*86400e3;const t=l.makeToken(k,'alice',u.get('alice'),back);"
                "console.log(JSON.stringify([l.checkToken(k,u,t), l.checkToken(k,u,t,back)]))")
        old, fresh = json.loads(node(code, s.key, s.users))
        assert old is None and fresh == "alice", "91 days old: expired"


def test_a_post_from_another_origin_is_refused_and_spends_nothing():
    with Svc() as s:
        tok = s.link()
        r, _ = s.sign_in(tok, headers={"Origin": "https://evil.example.com", "Host": "agent.example.com"})
        assert r.status == 403 and not s.cookie(r)
        ok, _ = s.sign_in(tok, headers={"Origin": "https://agent.example.com", "Host": "agent.example.com"})
        assert ok.status == 303, "the refused POST did not spend the link"
        out, _ = s.req("POST", "/logout", "", {"Origin": "https://evil.example.com", "Host": "agent.example.com"})
        assert out.status == 403


def test_behind_a_platform_entry_that_rewrites_host_the_public_origin_passes():
    """Issue #488: Host and X-Forwarded-Host both arrive as localhost; the console's own public name is the allow list."""
    behind = {"Host": "localhost", "X-Forwarded-Host": "localhost"}
    with Svc(allow="seo.example.com,LOCALHOST") as s:
        for evil in ("https://evil.example.com", "https://seo.example.com.evil.example.com", "https://seo.example.com:8443", "null"):
            r, _ = s.sign_in(s.link(), headers={"Origin": evil, **behind})
            assert r.status == 403 and not s.cookie(r), evil
        r, _ = s.sign_in(s.link(), headers={"Origin": "https://SEO.example.com", **behind})
        assert r.status == 303 and s.cookie(r), "a sign-in on the public domain works behind the entry"
    with Svc() as s:
        assert s.sign_in(s.link(), headers={"Origin": "https://seo.example.com", **behind})[0].status == 403, \
            "with no allow list, as before: only the host the request names"


def test_a_site_root_console_signs_in_at_the_root():
    with Svc(base="") as s:
        tok = s.link()
        _, body = s.req("GET", f"/in/{tok}")
        assert f'action="/in/{tok}"' in body
        r, _ = s.sign_in(tok)
        assert r.status == 303 and r.getheader("Location") == "/" and "Path=/;" in r.getheader("Set-Cookie")


def test_logout_clears_the_cookie():
    with Svc() as s:
        r, body = s.req("GET", "/logout")
        assert r.status == 200 and 'method="post"' in body and 'action="/seo/logout"' in body
        o, body = s.req("POST", "/logout", "")
        sc = o.getheader("Set-Cookie")
        assert o.status == 200 and "Max-Age=0" in sc and "Path=/seo" in sc and 'href="/seo/login"' in body


def test_other_paths_and_big_bodies_are_not_served():
    with Svc() as s:
        assert s.req("GET", "/")[0].status == 404 and s.req("GET", "/seo/")[0].status == 404
        assert s.req("POST", "/_auth", "")[0].status == 404 and s.req("GET", "/in")[0].status == 404
        tok = s.link()
        c = Conn(s.sock)
        try:
            c.request("POST", f"/in/{tok}", body="x" * 100000, headers={"Content-Type": "application/x-www-form-urlencoded"})
            status = c.getresponse().status
        except (ConnectionError, http.client.HTTPException, OSError):
            status = 413                           # the server closed on us while we were still sending
        assert status == 413, "an oversized body is refused, not read"
        assert s.sign_in(tok)[0].status == 303, "and the link was not spent; the service is still up"


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
    before, after = node(code, os.path.join(d, "u", "s.sock"), os.path.join(d, "users"), os.path.join(d, "key")).split()
    assert before == after                                # the console this process starts inherits the umask
    link = os.path.join(d, "link")
    os.symlink(d, link)
    out = node("try{require(process.argv[1]).listen({sock:process.argv[2],usersFile:'x',keyFile:'y',base:''})}catch(e){console.log('refused')}",
               os.path.join(link, "s.sock"))
    assert "refused" in out                               # a symlinked directory is not ours to trust


def test_the_socket_and_the_key_are_private_and_sessions_survive_a_restart():
    with Svc() as s:
        ck = s.cookie(s.sign_in(s.link())[0])
        for f in (s.sock, s.key, s.users, s.links):
            assert stat.S_IMODE(os.stat(f).st_mode) == 0o600, (f, oct(os.stat(f).st_mode))
        s.stop()
        s.start()
        assert s.who(ck) == "alice", "the key is kept in a file, so a restart keeps sessions"


def test_every_page_the_service_draws_passes_the_asks_guard():
    """D67, kit.guards.asks: each POST form on these pages says why it offers no "no" (signing in and
    signing out are not asks). Every page pages() can draw, in both languages, and the ones served."""
    sys.path.insert(0, ROOT)
    from kit.guards import asks
    drawn = json.loads(node(
        "const l=require(process.argv[1]);const out={};"
        "for(const lang of ['en','zh']){const P=l.pages(lang,'Shop','/seo');"
        "for(const [k,f] of Object.entries(P))out[`${lang} ${k}`]=f(l.newLinkToken(),'alice');}"
        "console.log(JSON.stringify(out))"))
    assert {k.split()[1] for k in drawn} >= {"login", "link", "incomplete", "dead", "old", "wait", "refused", "logout", "gone"}, drawn.keys()
    for where, html in drawn.items():
        assert not asks.problems(html, where), asks.problems(html, where)
    forms = sum(html.count('<form method="post"') for html in drawn.values())
    assert forms == 4, ("the link and the logout pages, twice: the check saw them", forms)
    with Svc() as s:
        tok = s.link()
        served = [s.req("GET", p)[1] for p in ("/login", f"/in/{tok}", f"/in/{tok[:9]}", "/setup", "/logout", "/nope")]
        served.append(s.req("POST", "/logout", "")[1])
        for html in served:
            assert not asks.problems(html, "served"), asks.problems(html, "served")
        assert any("data-no=" in h for h in served)
    assert asks.problems('<form method="post" action="/seo/in/x"><button>Sign in</button></form>'), "the guard bites without data-no"


if __name__ == "__main__":
    _t.main(globals())
