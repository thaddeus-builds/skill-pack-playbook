#!/usr/bin/env python3
"""Make one client's hub, and add each skill pack that serves the client.

    python3 scaffold/new_hub.py new --hub ../workspaces/northwind \\
        --title "Northwind Tea" [--markets HK,TW] [--lang en|zh] \\
        [--language "Traditional Chinese"] [--console-home DIR] [--dry-run]
    python3 scaffold/new_hub.py add-pack --hub ../workspaces/northwind \\
        --skill-pack ../acme-skill-pack [--folder acme] [--link DIR] \\
        [--language "…"] [--dry-run]

One client is served by several skill packs. The hub is the client's folder
(a git repository; its content git-ignored): one CLIENT.md, one intake, one
owner console, and one folder per pack. What `new` writes, under <hub>/:

  * CLIENT.md: who the client is (`<<fill: …>>` rows), the pack table and
    the port table; client_terms.txt (0600), the leak-guard list, seeded
    with the title;
  * intake/README.md, intake/INDEX.tsv (its header) and intake/inbox/: the
    one intake every pack reads;
  * hub.json: what the generated files are made from (title, port, the
    console's code, the hub program, the markets, each pack's CLI word,
    env prefix, folder, gate verbs);
  * bin/hub: `bin/hub <cli> <args…>` runs that pack's own wrapper
    `<folder>/bin/<cli>` with `<PREFIX>_HUB_DIR` = the hub (where the
    pack's `facts sync-hub` and doctor find the hub's facts), the
    environment passed through; `bin/hub hub <args…>` runs the hub's own;
  * hub/: the hub's own facts, the kit's facts and pending verbs run from
    scaffold/hub/hub.py: hub/bin/hub (its wrapper), hub/defs/skill-pack.toml
    (cli `hub`, env prefix `HUB`, the --markets, default none) and
    hub/defs/fact_keys.tsv, seeded with the keys a client's packs share
    (currency, avg_order_value, incremental_factor, incremental_source,
    npr_includes_creator_fee, npr_roas; a market enters through the kit's
    market door, `facts init`). The store hub/hub.db is made by the first
    write. The console relays `hub facts confirm` before every pack's verbs;
  * CLAUDE.md: the brief of the agent working at the hub;
  * bin/console, bin/ask: the ONE console of this client (CONSOLE_DIR =
    <hub>/console), run from --console-home (default: this playbook's
    console/); it relays `<cli> <verb…>` through bin/hub. Each start makes
    a fresh random <PREFIX>_CONFIRM_CODE_SECRET for every pack and keeps it
    in the console's own process env only (bin/hub and the pack wrapper
    inherit it): never written to a file, never printed;
  * .claude/settings.json: permissions.deny for every gate verb of every
    pack (through bin/hub and through the pack's wrapper) and for hand
    edits under each pack's workspace/, console/ and hub/;
  * .claude/launch.json: the console as a preview; .gitignore.

Its port is the first from 8770 upward that is not bound now and that no
sibling under the same workspaces root (the hub's parent) names: a port
row in a sibling's CLIENT.md, or a port in a sibling's .claude/launch.json
or in one a folder deeper (a per-pack client workspace,
<root>/<pack-clients>/<client>/.claude/launch.json).

`add-pack` adds one pack: with --link DIR it links an existing client
workspace of that pack (a relative symlink; the folder is never written);
without, it writes the pack folder from new_client.py's files() WITHOUT its
own console (no bin/console, bin/ask or launch.json; the brief points at
the hub's console and intake). Then it rewrites hub.json, bin/hub,
bin/console (relay verbs: `hub facts confirm`, then each pack's gated
verbs ending in confirm, approve or answer, as `<cli> facts confirm,<cli>
decisions confirm,<cli> queue approve`), CLAUDE.md, adds the pack's deny rules to .claude/settings.json
(rules already there are kept), and appends the pack's row to CLIENT.md
(and a port row for a linked workspace's own console) and its folder to
.gitignore.

`new` refuses a hub folder that exists and is not empty, a folder name that
is not a client id, a market that is not a plain word, and a path the
console's --relay-cmd could not carry (white space, quotes, `$`, `\\`).
`add-pack` refuses a folder that is not a hub, a pack (name, CLI word,
prefix or folder) already in it or the hub's own (`hub`, `HUB`), a folder
that exists, and a --link without that pack's bin/<cli>. Refusals exit 2
with one line; `--dry-run` lists what would be written.

Test: scaffold/tests/test_new_hub.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import new_client  # noqa: E402
from new_client import CLIENT_RE, RELAYED, Refused  # noqa: E402

PLAYBOOK = Path(__file__).resolve().parents[1]
PORT_FROM, PORT_TO = 8770, 8870
PORT_ROW = re.compile(r"^\|\s*:?(\d{2,5})\s*\|", re.M)
CLI_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}")
PREFIX_RE = re.compile(r"[A-Z][A-Z0-9_]{0,31}")
UNSAFE_PATH = re.compile(r"[\s'\"\\$`]")
PACK_HEADER = "| Pack | CLI | Folder | Relayed by the console |"
PORT_HEADER = "| Port | What |"
INDEX_HEADER = ("id\tdate\tsource\tkind\ttitle\tpath\tbytes\tfiles\tsha256\t"
                "read_by\tduplicate_of\tnote\n")
BASE_DENY = ["Edit(./hub/**)", "Write(./hub/**)",
             "Edit(./console/**)", "Write(./console/**)"]
HUB_HOME = PLAYBOOK / "scaffold" / "hub"          # the hub's own facts program
HUB = {"name": "hub", "cli": "hub", "prefix": "HUB", "folder": "hub",
       "gates": ["facts confirm", "facts restore"], "relay": ["facts confirm"]}
MARKET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,15}")
# The keys a client's packs share, defined as the packs that hold them define
# them: a pack copies a hub fact only when type, unit, bounds and labels match.
HUB_KEY_ROWS = [
    ("currency", "required", "choice:HKD|TWD|EUR|USD", "", "", "",
     "reporting currency of the market", "該市場的報表幣別",
     "every money amount every pack reads is in this currency"),
    ("npr_roas", "required", "number", "x ROAS", "0.1", "50",
     "NPR: minimum profitable ROAS", "NPR：最低獲利 ROAS",
     "break-even ROAS: every call on spend is above or below it"),
    ("avg_order_value", "optional", "number", "currency", "0", "",
     "average order value", "客單價",
     "minimum spends are judged as multiples of it"),
    ("npr_includes_creator_fee", "optional", "choice:yes|no", "", "", "",
     "does NPR already count creator fees", "NPR 是否已含達人費用",
     "when no, creator fees are added to spend before comparing with NPR"),
    ("incremental_source", "optional",
     "choice:none|meta_modeled|lift_study|holdout", "", "", "",
     "where an incremental factor comes from", "增量係數的來源",
     "the evidence level every incremental call names"),
    ("incremental_factor", "optional", "number", "ratio", "0", "2",
     "incremental share of attributed sales", "歸因成交中的增量比例",
     "the share of attributed sales counted as incremental"),
]
HUB_KEYS_HEADER = ("key", "group", "type", "unit", "min", "max", "label_en",
                   "label_zh", "why")


# --- ports ---------------------------------------------------------------

def port_bound(port: int) -> bool:
    """Is something listening on (or holding) 127.0.0.1:port now?"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def _launch_ports(path: Path) -> set[int]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return {int(c["port"]) for c in doc.get("configurations", [])
                if isinstance(c, dict) and str(c.get("port", "")).isdigit()}
    except (OSError, ValueError, AttributeError):
        return set()


def named_ports(root: Path) -> set[int]:
    """Every port a sibling under the workspaces root names: port rows of
    its CLIENT.md, its .claude/launch.json, and those one folder deeper."""
    ports: set[int] = set()
    try:
        siblings = sorted(d for d in root.iterdir() if d.is_dir())
    except OSError:
        return ports
    for d in siblings:
        try:
            ports |= {int(p) for p in PORT_ROW.findall(
                (d / "CLIENT.md").read_text(encoding="utf-8"))}
        except OSError:
            pass
        for lj in (d / ".claude" / "launch.json",
                   *d.glob("*/.claude/launch.json")):
            ports |= _launch_ports(lj)
    return ports


def choose_port(root: Path, bound=port_bound) -> int:
    taken = named_ports(root)
    for p in range(PORT_FROM, PORT_TO):
        if p not in taken and not bound(p):
            return p
    raise Refused(f"no free port in {PORT_FROM}-{PORT_TO - 1} under {root}")


# --- generated files -----------------------------------------------------

def sh_dq(text: str) -> str:
    """`text` safe inside a double-quoted sh string."""
    return re.sub(r'([\\"$`])', r"\\\1", text)


def relay_list(h: dict) -> list[str]:
    """The console's relay verbs: the hub's own first, then each pack's."""
    return [f"{p['cli']} {v}" for p in (HUB, *h["packs"]) for v in p["relay"]]


def hub_files(h: dict, hub: Path) -> dict[str, tuple[str, int]]:
    """The files new and add-pack both (re)write, wholly from hub.json."""
    packs, home = h["packs"], f'"${{HUB_CONSOLE_HOME:-{h["console_home"]}}}"'
    clis = " ".join(p["cli"] for p in packs) or "none yet (scaffold/new_hub.py add-pack)"
    arms = '  hub) shift; exec "$root/hub/bin/hub" "$@" ;;\n' + "".join(
        f'  {p["cli"]}) shift; {p["prefix"]}_HUB_DIR="$root"; export {p["prefix"]}_HUB_DIR\n'
        f'    exec "$root/{p["folder"]}/bin/{p["cli"]}" "$@" ;;\n' for p in packs)
    dispatch = f"""#!/bin/sh
# {h['title']}'s hub: `bin/hub <cli> <args…>` runs that pack's own wrapper
# (<folder>/bin/<cli>) with this environment, the console's confirm-code
# secrets included, and <PREFIX>_HUB_DIR = this hub (the pack's `facts
# sync-hub` and doctor read the hub's facts there); `bin/hub hub …` runs the
# hub's own facts (hub/bin/hub). Written from hub.json by the playbook's
# scaffold/new_hub.py; `new_hub.py add-pack` rewrites it.
root="$(cd "$(dirname "$0")/.." && pwd)"
case "${{1:-}}" in
{arms}  *) echo "bin/hub: usage: bin/hub <cli> <args…>; <cli> is hub or one of: {clis}" >&2; exit 2 ;;
esac
"""
    secrets = "".join(f'{p["prefix"]}_CONFIRM_CODE_SECRET="$(openssl rand -hex 32)"\n'
                      f'export {p["prefix"]}_CONFIRM_CODE_SECRET\n' for p in (HUB, *packs))
    relay = f' \\\n  --relay-cmd "$root/bin/hub" --relay-verbs "{",".join(relay_list(h))}"'
    console = f"""#!/bin/sh
# {h['title']}'s console: the asks of every pack of this client on one page,
# log in ./console. A click on a gated ask runs `bin/hub <cli> <verb…>` with
# a relayed one-time code. Each pack's <PREFIX>_CONFIRM_CODE_SECRET is made
# fresh at each start and kept only in this process's env (bin/hub and the
# pack's wrapper inherit it): never in a file, never printed.
set -e
{new_client.python_check("HUB", "bin/console")}root="$(cd "$(dirname "$0")/.." && pwd)"
{secrets}export CONSOLE_DIR="$root/console"
mkdir -p "$CONSOLE_DIR" && chmod 700 "$CONSOLE_DIR"
exec "$py" {home}/serve.py --dir "$CONSOLE_DIR" --title "{sh_dq(h['title'])}" \\
  --lang {h['lang']} --port "${{HUB_CONSOLE_PORT:-{h['port']}}}"{relay} "$@"
"""
    ask = f"""#!/bin/sh
# The agent's side of {h['title']}'s console (ask.py), pinned to ./console.
{new_client.python_check("HUB", "bin/ask")}root="$(cd "$(dirname "$0")/.." && pwd)"
export CONSOLE_DIR="$root/console"
exec "$py" {home}/ask.py "$@"
"""
    launch = json.dumps({"version": "0.0.1", "configurations": [{
        "name": f"{h['client']}-hub-console", "runtimeExecutable": "/bin/sh",
        "runtimeArgs": [str(hub / "bin" / "console")], "port": h["port"]}]},
        indent=2) + "\n"
    return {"hub.json": (json.dumps(h, indent=2, ensure_ascii=False) + "\n", 0o644),
            "bin/hub": (dispatch, 0o755), "bin/console": (console, 0o755),
            "bin/ask": (ask, 0o755), ".claude/launch.json": (launch, 0o644),
            "CLAUDE.md": (hub_brief_md(h), 0o644)}


BRIEF_MAX = 4096


def hub_brief_md(h: dict) -> str:
    """The brief of the agent working at the hub (under BRIEF_MAX bytes)."""
    packs = h["packs"]
    clis = ", ".join(f"`{p['cli']}`" for p in packs) or "none yet"
    gates = "; ".join(f"`{p['cli']} {', '.join(p['gates']) or 'none'}`"
                      for p in (HUB, *packs))
    packs_arg = ",".join(p["cli"] for p in packs) or "<cli>,…"
    text = f"""# {h['title']}: the client hub

You work at this client's hub: one console, one intake and one facts store for
every pack that serves the client (packs: {clis}; `CLIENT.md` says who the client
is). `bin/hub <cli> <args…>` runs a pack; `bin/hub hub <args…>` runs the hub's own
facts. Never edit `hub/`, `console/` or a pack's `workspace/` by hand.

## Start

1. `bin/hub hub doctor`, then `bin/hub <cli> doctor` for each pack. A warning names
   its fix; `fact_hub_copy_stale` means `bin/hub <cli> facts sync-hub`.
2. What waits on the owner: `bin/hub hub pending --hub --json` first, then
   `bin/hub <cli> pending --hub --json` for each pack. One cap of 10 open asks for
   the owner across all of them; the hub's own asks first.
3. Post asks through `bin/ask add FILE` (write `recommend.because` in each), read
   them back with `bin/ask answers --since SEQ`, close each with `bin/ask applied`.

## Facts

A fact every pack shares (the markets, currency, break-even ROAS `npr_roas`, …) is
confirmed once, here: `bin/hub hub facts set KEY VALUE --market M --source S
--reason R` makes it pending and the console asks the owner. Each pack then copies
the confirmed value with `bin/hub <cli> facts sync-hub`: it never overwrites a value
a pack confirmed itself (that is a conflict, and the pack's `pending` makes it one
ask) and never refreshes on its own.

## Chat answers

If the owner answers in chat, record their words with `bin/ask chat ID --value=V
--quote="their words" --source="chat <date> <time>"`, only for words and choices.
A number, a confirmation or an approval needs the owner's click on the console.

## Intake

New material lands in `intake/inbox/<YYYY-MM-DD>-<source>/` and gets its
`intake/INDEX.tsv` row at once (`intake/README.md`). Check a meeting's intake with
`python3 {PLAYBOOK / 'build' / 'check_intake.py'} intake/*.json --packs {packs_arg}
--transcript FILE`.

## Never

Never run a gate verb yourself: {gates}. They are the owner's, through the console.
"""
    if len(text.encode("utf-8")) > BRIEF_MAX:
        raise Refused(f"the hub's CLAUDE.md would be {len(text.encode())} bytes "
                      f"(at most {BRIEF_MAX}): too many packs for one brief")
    return text


def hub_facts_files(h: dict) -> dict[str, tuple[str, int]]:
    """The hub's own facts program, bound: hub/bin/hub (its wrapper),
    hub/defs/skill-pack.toml and hub/defs/fact_keys.tsv. Written by `new`
    only: from then on the definitions are the hub's."""
    wrapper = f"""#!/bin/sh
# {h['title']}'s hub facts: the playbook's scaffold/hub/hub.py over ./hub.db
# (HUB_DATA_DIR = this folder; the definitions in ./defs). HUB_HOME points
# at another copy of the program; HUB_PYTHON names the interpreter.
{new_client.python_check("HUB", "hub/bin/hub")}here="$(cd "$(dirname "$0")/.." && pwd)"
export KIT_SKILL_PACK_ROOT="$here/defs" HUB_DATA_DIR="$here"
exec "$py" "${{HUB_HOME:-{h['hub_home']}}}/hub.py" "$@"
"""
    markets = ", ".join(json.dumps(m) for m in h["markets"])
    toml = f"""# {h['title']}'s hub facts (scaffold/hub/hub.py), written by scaffold/new_hub.py.
# A market enters through the kit's door, `bin/hub hub facts init`; a person
# confirms its declaration on the console.
[skill_pack]
name = "{h['client']}-hub"
cli = "hub"
env_prefix = "HUB"
db_file = "hub.db"
languages = ["en", "zh"]
markets = [{markets}]
home_env_file = ""

[ssot]
dir = "."
fact_keys = "fact_keys.tsv"

[contract]
no_db_next = ["facts init"]
"""
    keys = "".join("\t".join(r) + "\n" for r in (HUB_KEYS_HEADER, *HUB_KEY_ROWS))
    return {"hub/bin/hub": (wrapper, 0o755),
            "hub/defs/skill-pack.toml": (toml, 0o644),
            "hub/defs/fact_keys.tsv": (keys, 0o644)}


def deny_rules(h: dict, hub: Path) -> list[str]:
    deny = list(BASE_DENY)
    for p in (HUB, *h["packs"]):
        cli, f = p["cli"], p["folder"]
        for g in p["gates"]:
            for cmd in (f"./bin/hub {cli}", f"bin/hub {cli}",
                        f"{hub}/bin/hub {cli}", f"./{f}/bin/{cli}",
                        f"{f}/bin/{cli}", f"{hub}/{f}/bin/{cli}"):
                deny.append(f"Bash({cmd} {g}:*)")
        if p is not HUB:
            deny += [f"Edit(./{f}/workspace/**)", f"Write(./{f}/workspace/**)",
                     f"Read(./{f}/workspace/.env)"]
    return deny


def settings(h: dict, hub: Path, old: str | None) -> str:
    """The settings with every deny rule of the hub; whatever was there is kept."""
    doc = json.loads(old) if old else {}
    perms = doc.setdefault("permissions", {})
    deny = perms.setdefault("deny", [])
    deny += [d for d in deny_rules(h, hub) if d not in deny]
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def client_md(h: dict) -> str:
    fill = "<<fill: {}>>".format
    return f"""# {h['title']}

| | |
|---|---|
| Client id | `{h['client']}` |
| Brand | {fill("who the client is and what it sells")} |
| Markets | {fill("the markets, each reported separately")} |
| Contact | {fill("the client's people and what each runs")} |
| Our side | {fill("who serves this client")} |
| Contract | {fill("what is paid for; what may be written")} |
| Decision rule | {fill("in the client's words")} |

This folder is the client's hub: one console for the asks of every pack
(`bin/console`, one cap of 10 open), one intake (`intake/`), and one folder
per pack. `bin/hub <cli> <args…>` runs that pack's own wrapper. Packs are
added with the playbook's `scaffold/new_hub.py add-pack`, never by hand.
The client's own details (roster, fees, codes) stay in the pack folders and
`hub/`, never in git.

## Packs

{PACK_HEADER}
|---|---|---|---|

## Ports

{PORT_HEADER}
|---|---|
| {h['port']} | this hub's console (`bin/console`) |
"""


INTAKE_README = """# intake: everything the client or a platform gave us, and what we made of it

One place per client, shared by every pack. `INDEX.tsv` lists each item once: id (never reused), date, source
(`client`, `platform`, `meeting`, `ask`, `digest`), kind, title, path, size, file count, sha256 (a directory's digest
is the hash of its files' hashes; left empty above 500 MB), which packs read it, `duplicate_of`, a note.

Rules:
1. **New material lands in `inbox/<YYYY-MM-DD>-<source>/` first** and gets an INDEX row at once. Raw files are never
   renamed, edited or removed (the packs' stores identify files by their bytes).
2. **A value is read from intake into a pack only through that pack's own door** (`bin/hub <cli> import …`, then the
   human gate). The INDEX is a map, not a source of numbers.
3. Intake content is never in git; only this README and `INDEX.tsv` are (and the hub's `CLIENT.md`).
"""

GITIGNORE = """# The client's content, the console log and the hub's data: never versioned.
# new_hub.py add-pack appends each pack folder (a local folder or link).
/client_terms.txt
/console/
/hub/*
!/hub/bin/
!/hub/defs/
/intake/*
!/intake/README.md
!/intake/INDEX.tsv
!/intake/inbox/
/intake/inbox/*
!/intake/inbox/.gitkeep
.DS_Store
__pycache__/
"""


def append_row(text: str, header: str, row: str) -> str | None:
    """`text` with `row` added at the end of the table under `header`, or
    None when that table is not there (CLIENT.md was edited by hand)."""
    lines = text.split("\n")
    if header not in lines:
        return None
    i = lines.index(header) + 1
    while i < len(lines) and lines[i].startswith("|"):
        i += 1
    lines.insert(i, row)
    return "\n".join(lines)


# --- a pack's folder -----------------------------------------------------

def hub_brief(text: str, cli: str, port: int) -> str:
    """The client brief (templates/client/CLAUDE.md) for a pack folder in a
    hub: the console, ask and intake are the hub's, one folder up."""
    swaps = [
        (r"(?m)^\| `workspace/intake/` \|.*$",
         "| `../intake/` | the client's intake, one for every pack of this client "
         "(`../intake/README.md`): new material lands in `../intake/inbox/<date>-<source>/` "
         "with an `INDEX.tsv` row. Read the compact facts file first, never the raw transcript |"),
        (r"(?m)^\| `workspace/console/` \|.*$",
         "| `../console/` | the hub's console log: one console for every pack of this client "
         f"(`../bin/console`, http://127.0.0.1:{port}/) |"),
        (r"(?<![.\w])\./bin/(console|ask)\b", r"../bin/\1"),
    ]
    for pattern, new in swaps:
        text, n = re.subn(pattern, lambda m, new=new: m.expand(new), text)
        if not n:
            raise Refused(f"templates/client/CLAUDE.md no longer has {pattern!r}: "
                          f"update hub_brief() in scaffold/new_hub.py")
    head, sep, rest = text.partition("\n\n")
    note = (f"this folder is the `{cli}` pack of a client hub: `..` holds the client "
            f"(`../CLIENT.md`), its one console and its one intake. the console's asks of "
            f"every pack share one cap of 10 open, and a click runs the gate through "
            f"`../bin/hub {cli} …`, which runs `./bin/{cli}`.")
    return head + sep + note + "\n\n" + rest


def pack_folder(h: dict, n: dict, a, gates: list[str], relay: list[str]) -> dict:
    ns = argparse.Namespace(skill_pack=a.skill_pack, title=h["title"],
                            client=h["client"], clients=a.hub, port=h["port"],
                            lang=h["lang"], language=a.language or h["language"])
    out = new_client.files(ns, n, gates, relay)
    for rel in ("bin/console", "bin/ask", ".claude/launch.json"):
        del out[rel]
    brief, mode = out["CLAUDE.md"]
    out["CLAUDE.md"] = (hub_brief(brief, n["cli"], h["port"]), mode)
    return out


def default_folder(name: str) -> str:
    return re.sub(r"-(skill-pack|harness)$", "", name)


# --- verbs ---------------------------------------------------------------

def write(base: Path, out: dict[str, tuple[str, int]]) -> None:
    for rel, (text, mode) in out.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        p.chmod(mode)


def cmd_new(a) -> int:
    hub = a.hub.expanduser().resolve()
    if not CLIENT_RE.fullmatch(hub.name):
        raise Refused(f"{hub.name!r}: a hub folder is named for the client id: "
                      f"lower-case letters, digits, '.', '_' and '-' only")
    if UNSAFE_PATH.search(str(hub)):
        raise Refused(f"{hub}: white space, quotes, '$' or '\\' in the path; "
                      f"the console's --relay-cmd cannot carry them")
    if hub.exists() and (not hub.is_dir() or any(hub.iterdir())):
        raise Refused(f"{hub} exists and is not empty")
    markets = [m.strip() for m in (a.markets or "").split(",") if m.strip()]
    bad = [m for m in markets if not MARKET_RE.fullmatch(m)]
    if bad or len(set(markets)) != len(markets):
        raise Refused(f"--markets {a.markets!r}: plain words (letters, digits, "
                      f"'_', '-'), each once")
    home = (a.console_home or PLAYBOOK / "console").expanduser().resolve()
    if not ((home / "serve.py").is_file() and (home / "ask.py").is_file()):
        raise Refused(f"{home} has no serve.py and ask.py: not a console")
    h = {"client": hub.name, "title": a.title, "lang": a.lang,
         "language": a.language, "port": choose_port(hub.parent),
         "console_home": str(home), "hub_home": str(HUB_HOME),
         "markets": markets, "packs": []}
    out = hub_files(h, hub) | hub_facts_files(h)
    out |= {"CLIENT.md": (client_md(h), 0o644),
            "client_terms.txt": (f"# leak-guard terms for {h['client']}: one per line, "
                                 f"'#' a comment, 're:' a regular expression\n"
                                 f"{a.title}\n", 0o600),
            "intake/README.md": (INTAKE_README, 0o644),
            "intake/INDEX.tsv": (INDEX_HEADER, 0o644),
            "intake/inbox/.gitkeep": ("", 0o644),
            ".gitignore": (GITIGNORE, 0o644),
            ".claude/settings.json": (settings(h, hub, None), 0o644)}
    for rel in sorted(out):
        print(("would write " if a.dry_run else "write ") + str(hub / rel))
    print(f"console port: {h['port']}")
    if a.dry_run:
        return 0
    write(hub, out)
    print(f"next: fill the `<<fill: …>>` in {hub / 'CLIENT.md'}, `git init` the hub, "
          f"then `python3 {Path(__file__).resolve()} add-pack --hub {hub} --skill-pack DIR` "
          f"for each pack that serves the client")
    return 0


def cmd_add_pack(a) -> int:
    hub = a.hub = a.hub.expanduser().resolve()
    a.skill_pack = a.skill_pack.expanduser().resolve()
    try:
        h = json.loads((hub / "hub.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refused(f"{hub} is not a hub (no readable hub.json): make one with "
                      f"`new_hub.py new`")
    if hub == a.skill_pack or a.skill_pack in hub.parents:
        raise Refused(f"{hub} is inside the skill pack: client data never lives "
                      f"in the skill pack checkout")
    n = new_client.skill_pack_names(a.skill_pack)
    if not CLI_RE.fullmatch(n["cli"]) or not PREFIX_RE.fullmatch(n["prefix"]):
        raise Refused(f"{n['name']}: cli {n['cli']!r} or env_prefix {n['prefix']!r} "
                      f"is not a plain word")
    folder = a.folder or default_folder(n["name"])
    if not CLIENT_RE.fullmatch(folder):
        raise Refused(f"--folder {folder!r}: lower-case letters, digits, '.', '_' "
                      f"and '-' only")
    for p in (HUB, *h["packs"]):
        for key, mine in (("name", n["name"]), ("cli", n["cli"]),
                          ("prefix", n["prefix"]), ("folder", folder)):
            if p[key] == mine and p is HUB:
                raise Refused(f"{key} {mine!r} is the hub's own (its facts "
                              f"program): name the pack otherwise")
            if p[key] == mine:
                raise Refused(f"pack {p['name']} is already in this hub "
                              f"(same {key}: {mine})")
    dest = hub / folder
    if dest.exists() or dest.is_symlink():
        raise Refused(f"{dest} exists: name another --folder")
    link = None
    if a.link:
        link = a.link.expanduser().resolve()
        if not os.access(link / "bin" / n["cli"], os.X_OK):
            raise Refused(f"--link {link}: no bin/{n['cli']} there, not a client "
                          f"workspace of {n['name']}")
        if link == hub or hub in link.parents:
            raise Refused(f"--link {link} is inside the hub")
    gates = new_client.gate_verbs(a.skill_pack, n)
    relay = [g for g in gates if g.split()[-1] in RELAYED]
    h["packs"].append({"name": n["name"], "cli": n["cli"], "prefix": n["prefix"],
                       "folder": folder, "skill_pack": str(a.skill_pack),
                       "link": str(link) if link else None,
                       "gates": gates, "relay": relay})
    out = hub_files(h, hub)
    sp = hub / ".claude" / "settings.json"
    out[".claude/settings.json"] = (settings(h, hub, sp.read_text(encoding="utf-8")
                                             if sp.is_file() else None), 0o644)
    gi = (hub / ".gitignore").read_text(encoding="utf-8") if (hub / ".gitignore").is_file() else ""
    if f"/{folder}" not in gi.splitlines():
        out[".gitignore"] = (gi + ("" if gi.endswith("\n") or not gi else "\n")
                             + f"/{folder}\n", 0o644)
    where = f"`{folder}/` → `{os.path.relpath(link, hub)}`" if link else f"`{folder}/`"
    rows = [(PACK_HEADER, f"| {n['name']} | `{n['cli']}` | {where} | "
                          f"{', '.join(f'`{v}`' for v in relay) or 'none'} |")]
    if link:
        rows += [(PORT_HEADER, f"| {p} | `{n['cli']}`: the linked workspace's own console "
                               f"(`{folder}/bin/console`), before this hub |")
                 for p in sorted(_launch_ports(link / ".claude" / "launch.json"))]
    cm = hub / "CLIENT.md"
    text, missing = (cm.read_text(encoding="utf-8") if cm.is_file() else ""), []
    for header, row in rows:
        new = append_row(text, header, row)
        if new is None:
            missing.append(row)
        else:
            text = new
    if cm.is_file():
        out["CLIENT.md"] = (text, 0o644)
    pack = {} if link else pack_folder(h, n, a, gates, relay)
    for rel in sorted(out):
        print(("would write " if a.dry_run else "write ") + str(hub / rel))
    if link:
        print(("would link " if a.dry_run else "link ") + f"{dest} -> {link}")
    for rel in sorted(pack):
        print(("would write " if a.dry_run else "write ") + str(dest / rel))
    if a.dry_run:
        return 0
    if link:
        os.symlink(os.path.relpath(link, hub), dest)
    else:
        write(dest, pack)
        (dest / "workspace").mkdir(exist_ok=True)
        (dest / "workspace").chmod(stat.S_IRWXU)
    write(hub, out)
    for row in missing:
        print(f"add to {cm}: {row}")
    print(f"next: `{hub / 'bin' / 'hub'} {n['cli']} doctor --strict`; restart "
          f"{hub / 'bin' / 'console'} so it relays {n['cli']}'s verbs")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="verb", required=True)
    new = sub.add_parser("new", help="make a hub folder")
    new.add_argument("--hub", required=True, type=Path,
                     help="the hub folder, named for the client id, under the workspaces root")
    new.add_argument("--title", required=True)
    new.add_argument("--markets", default="",
                     help="the client's markets, comma-separated (e.g. HK,TW); "
                          "default none: the hub keeps no market partition")
    new.add_argument("--lang", choices=("en", "zh"), default="en",
                     help="the console's language")
    new.add_argument("--language", default="the client's language",
                     help="the language the agent talks to the client in")
    new.add_argument("--console-home", type=Path,
                     help="the console's code (serve.py, ask.py); default: this playbook's console/")
    new.add_argument("--dry-run", action="store_true")
    add = sub.add_parser("add-pack", help="add a skill pack to a hub")
    add.add_argument("--hub", required=True, type=Path)
    add.add_argument("--skill-pack", required=True, type=Path)
    add.add_argument("--folder", help="the pack's folder in the hub (default: its "
                                      "name without -skill-pack)")
    add.add_argument("--link", type=Path,
                     help="an existing client workspace of this pack, linked, not written")
    add.add_argument("--language", help="default: the hub's")
    add.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        return cmd_new(a) if a.verb == "new" else cmd_add_pack(a)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
