"""The skill pack's own routes in the console's Caddy block (manifest console.routes, 0.7.3).

Seen once, 2026-11-05: a skill pack kept a second console in the block by hand, between
the BEGIN/END lines; post-upgrade found the block outdated, wrote the adapter's own in its
place and reloaded Caddy, and the second console's route was gone on every host. Now the
adapter writes the routes itself, behind the same login, on every rewrite: post-upgrade over
an old block, the copy put back after uninstall + add, a route added in a release. Nothing is
ever written outside the BEGIN/END lines.

Run: python3 hosts/zylos/tests/test_routes.py
"""

from __future__ import annotations

import copy
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402
from _host import Host, example  # noqa: E402

BEGIN, END = "# BEGIN zylos-component:shop-harness", "# END zylos-component:shop-harness"
ROUTE = {"path": "/shop/ops", "port": 8768, "port_key": "SHOP_OPS_PORT"}
SITES = "agent.test {\n    respond / 200\n}\nother.test {\n    handle_path /ops/* {\n        reverse_proxy 127.0.0.1:1\n    }\n}\n"
# A block as the skill pack wrote it by hand before 0.7.3: the adapter's old basic_auth block
# with the pack's own route added before END.
OLD_WITH_ROUTE = (f"{BEGIN}\nredir /shop /shop/ permanent\nhandle_path /shop/* {{\n"
                  "    basic_auth {\n        import /x/console.users\n    }\n    reverse_proxy 127.0.0.1:8767\n}\n"
                  "redir /shop/ops /shop/ops/ permanent\nhandle_path /shop/ops/* {\n    reverse_proxy 127.0.0.1:8768\n}\n"
                  f"{END}\n")


def with_routes(*routes) -> dict:
    m = copy.deepcopy(example())
    m["console"]["routes"] = list(routes) or [ROUTE]
    return m


def indent(block: str, pad: str = "    ") -> str:
    return "".join(pad + ln if ln.strip() else ln for ln in block.splitlines(keepends=True))


def fake_caddy(host, sites: str) -> str:
    """A Caddyfile, users, a fake caddy (validate passes) and pm2 that log their calls."""
    host.write(os.path.join(host.data, "console.users"), "alice scrypt$x\n")
    cf = os.path.join(host.zylos, "http", "Caddyfile")
    host.write(cf, sites)
    host.write(os.path.join(host.zylos, "bin", "caddy"),
               f"#!/bin/sh\n[ \"$1\" = validate ] && echo \"$3\" >> '{host.home}/caddy.log'\nexit 0\n", mode=0o755)
    host.write(os.path.join(host.bin, "pm2"), f"#!/bin/sh\necho \"$*\" >> '{host.home}/pm2.log'\nexit 0\n", mode=0o755)
    return cf


def block_of(text: str) -> str:
    lines = text.splitlines()
    a = next(i for i, ln in enumerate(lines) if ln.strip() == BEGIN)
    b = next(i for i, ln in enumerate(lines) if ln.strip() == END)
    return "\n".join(ln.strip() for ln in lines[a:b + 1])


def outside(text: str) -> tuple[str, str]:
    """What is before BEGIN and after END."""
    lines = text.splitlines(keepends=True)
    a = next(i for i, ln in enumerate(lines) if ln.strip() == BEGIN)
    b = next(i for i, ln in enumerate(lines) if ln.strip() == END)
    return "".join(lines[:a]), "".join(lines[b + 1:])


def has_route(block: str, port: str = "8768") -> bool:
    lines = block.splitlines()
    return ("redir /shop/ops /shop/ops/ permanent" in lines and "handle_path /ops/* {" in lines
            and f"reverse_proxy 127.0.0.1:{port} {{" in lines and "basic_auth {" not in lines)


def caddy(host, **extra) -> str:
    r = host.node(os.path.join(host.adapter, "lib.js"), "caddy", **extra)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_post_upgrade_over_an_old_block_that_holds_the_route_keeps_it():
    with Host(with_routes(), scheduler=False) as host:
        cf = fake_caddy(host, "agent.test {\n    respond / 200\n" + indent(OLD_WITH_ROUTE) + "}\n")
        r = host.hook("post-upgrade.js", SHOP_ZYLOS_HOOK_SKIP_UV="1")
        text = open(cf).read()
        assert r.returncode == 0 and "wrote the form-login Caddy block" in r.stdout and "still uses basic_auth" in r.stdout, r.stdout
        assert text.count(BEGIN) == 1 and has_route(block_of(text)), text
        saved = [ln.strip() for ln in open(os.path.join(host.data, "caddy-block.saved")).read().splitlines()]
        assert saved == [ln.strip() for ln in OLD_WITH_ROUTE.splitlines()], ("the old block kept", saved)
        again = host.hook("post-upgrade.js", SHOP_ZYLOS_HOOK_SKIP_UV="1")
        assert open(cf).read() == text and "Caddy block" not in again.stdout, ("idempotent", again.stdout)


def test_a_current_block_without_a_route_the_release_added_is_written_again():
    with Host(scheduler=False) as host:
        plain = caddy(host)                          # this release's block, before the route was in the manifest
    with Host(with_routes(), scheduler=False) as host:
        cf = fake_caddy(host, "agent.test {\n    respond / 200\n" + indent(plain) + "}\n")
        r = host.hook("post-upgrade.js", SHOP_ZYLOS_HOOK_SKIP_UV="1")
        text = open(cf).read()
        assert r.returncode == 0 and "lacks the route /shop/ops (manifest console.routes)" in r.stdout, r.stdout
        assert has_route(block_of(text)), text


def test_uninstall_then_post_install_keeps_the_route():
    with Host(with_routes(), scheduler=False) as host:
        block = caddy(host)
        assert has_route(block_of(block)), block
        cf = fake_caddy(host, "agent.test {\n    respond / 200\n" + indent(block) + "}\n")
        r = host.hook("pre-uninstall.js", ZYLOS_COMPONENT=host.name, ZYLOS_DATA_DIR=host.data)
        assert r.returncode == 0 and "kept a copy of the Caddy block" in r.stdout, r.stdout + r.stderr
        a, b = outside(open(cf).read())
        host.write(cf, a + b)                        # what `zylos uninstall` does: the block goes, by its BEGIN/END lines
        r = host.hook("post-install.js", SHOP_ZYLOS_HOOK_SKIP_UV="1")
        text = open(cf).read()
        assert r.returncode == 0 and "restored the Caddy block" in r.stdout, r.stdout
        assert block_of(text) == block_of(block) and has_route(block_of(text)), text


def test_a_saved_copy_without_the_route_is_not_put_back_as_it_was():
    with Host(scheduler=False) as host:
        plain = caddy(host)
    with Host(with_routes(), scheduler=False) as host:
        cf = fake_caddy(host, SITES)
        host.write(os.path.join(host.data, "caddy-block.saved"), plain)
        r = host.hook("post-install.js", SHOP_ZYLOS_HOOK_SKIP_UV="1")
        text = open(cf).read()
        assert r.returncode == 0 and "wrote the form-login Caddy block" in r.stdout and "lacks the route" in r.stdout, r.stdout
        assert text.count(BEGIN) == 1 and has_route(block_of(text)), text


def test_nothing_is_written_outside_the_markers():
    """The host's own route at the same sub-path in another site stays as it was; the block's
    lines are all between BEGIN and END, and the file outside them is byte for byte the same."""
    for label, sites in [("an old block in the file", "agent.test {\n    respond / 200\n" + indent(OLD_WITH_ROUTE) + "}\n"
                          + SITES.split("}\n", 1)[1]),
                         ("the block put back", SITES)]:
        with Host(with_routes(), scheduler=False) as host:
            cf = fake_caddy(host, sites)
            if label == "the block put back":
                host.write(os.path.join(host.data, "caddy-block.saved"), OLD_WITH_ROUTE)
                before = (sites.split("}\n", 1)[0], "}\n" + sites.split("}\n", 1)[1])
            else:
                before = outside(sites)
            r = host.hook("post-install.js", SHOP_ZYLOS_HOOK_SKIP_UV="1")
            text = open(cf).read()
            assert r.returncode == 0 and text.count(BEGIN) == 1, (label, r.stdout)
            assert outside(text) == before, (label, outside(text), before)
            assert "handle_path /ops/* {\n        reverse_proxy 127.0.0.1:1\n    }" in outside(text)[1], (label, "the host's own route untouched")
        with Host(with_routes(), scheduler=False) as host:
            out = caddy(host)
            lines = out.rstrip("\n").splitlines()
            assert lines[0] == BEGIN and lines[-1] == END, ("the printed block is all inside the markers", out)


def test_the_login_guards_the_route():
    with Host(with_routes(ROUTE, {"path": "/shop/files", "socket": "files/files.sock"}), scheduler=False) as host:
        out = caddy(host)
        sock = host.lib("console.log(JSON.stringify(h.AUTH_SOCK))")
        lines = [ln.strip() for ln in out.splitlines()]
        at = lines.index
        drop, login, ask, ops, files, console = (at(s) for s in (
            "request_header -X-Remote-User", "handle @login {", f"forward_auth unix/{sock} {{",
            "handle_path /ops/* {", "handle_path /files/* {", "reverse_proxy 127.0.0.1:8767 {"))
        assert drop < login < ask < ops < console and ask < files < console, "after forward_auth, as the console"
        assert lines[login + 2] == "}" and lines[ask - 1] == "handle {", "outside @login: never an unguarded route"
        assert lines[ops:ops + 5] == ["handle_path /ops/* {", "reverse_proxy 127.0.0.1:8768 {", "header_up -Cookie", "}", "}"], lines[ops:ops + 5]
        assert lines[files + 1] == f"reverse_proxy unix/{os.path.join(host.data, 'files', 'files.sock')} {{", lines[files + 1]
        assert lines[files + 2] == "header_up -Cookie", "the session cookie is the login's business"
        # the console's handle_path holds the whole guarded part: the route is not a sibling of it
        depth, inside = 0, []
        for ln in lines:
            if ln.startswith("handle_path /shop/* {"):
                depth = 1
                continue
            if depth:
                inside.append(ln)
                depth += ln.count("{") - ln.count("}")
        assert "handle_path /ops/* {" in inside and "handle_path /files/* {" in inside, inside
        assert lines.index("redir /shop/ops /shop/ops/ permanent") < lines.index("handle_path /shop/* {")
        host.configure({"SHOP_OPS_PORT": "9555"})
        assert "reverse_proxy 127.0.0.1:9555 {" in caddy(host), "port_key overrides the route's port"


def test_without_routes_the_block_is_the_snippet_as_it_was():
    with Host(scheduler=False) as host:
        out = caddy(host)
        assert "<ROUTE" not in out and "\n\n" not in out.strip() and out.count("redir ") == 1 and out.count("handle_path ") == 1, out
        assert not re.search(r"^\s*$", out.rstrip("\n"), re.M), "no blank line where the slots were"


if __name__ == "__main__":
    _t.main(globals())
