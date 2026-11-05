#!/usr/bin/env python3
"""The machine's clients root and each client's folder, by one rule (docs/clients.md).

    python3 scaffold/clients.py where [--set DIR]
    python3 scaffold/clients.py list [--json]
    python3 scaffold/clients.py new CLIENT --title T --term TERM [--term TERM ...]
    python3 scaffold/clients.py check [CLIENT...] [--json]
    python3 scaffold/clients.py relink CLIENT [--dry-run]
    python3 scaffold/clients.py source CLIENT FILE_OR_URL --from client|platform|meeting|chat|ask|digest
                                      --title T [--date YYYY-MM-DD] [--kind K] [--read-by PACKS] [--note N]

The root holds one folder per client. Each machine names its root once: `CLIENTS_DIR` in the environment, else the
one line of `~/.config/openmax/clients_dir` (`where --set DIR` writes it). Neither set: the tool stops and says so;
it never guesses from the working directory or a default path, so two machines never disagree silently.

A client's folder (docs/clients.md; the people's layers came from issue #479, the hub's `new_hub.py`):

    <client>/README.md            the client's card for a person: who, which packs, where things are
             intake/              what a person reads to recall the client and edits to correct the agent:
                                  brief.md, decisions.md, open-questions.md
             sources/             what the client or a platform gave us, kept as received: INDEX.tsv (one row an
                                  item, ids EV-001 up, never reused) and inbox/<YYYY-MM-DD>-<from>/ (the files);
                                  a chat log, a meeting's notes, a video, a picture, a link, a file an agent
                                  pulled through a platform API (`api-agent`): each one row
             reports/             what the packs made for people to read
             .machine/            what tools own: the hub or workspace, pack data, connections (0700), and
                                  links.tsv, the links this machine needs into the folder

`new` lays out a folder for a client that has material and no pack yet (a pack's workspace or the hub, made later by
`new_client.py` or `new_hub.py`, goes under `.machine/`): the card, the three intake files and `meetings/`,
`sources/` with its README and INDEX header, `reports/`, and `.machine/` (0700) with `client_terms.txt`, which takes
the client's names from `--term` (at least one: a client with no term list is one a repository can leak). It
refuses a folder that exists.

`check` holds each rule (one problem a line, exit 1 on any): the card and the three intake files exist; `.machine/`
holds a `client_terms.txt` (the client's names, one a line: the playbook's pre-push hook and every pack's leak guard
read it, so a name never reaches a repository; seen once, 2026-11-05: a client's name in the playbook's docs); INDEX.tsv
has the header, unique ids and a row for every file under inbox/, and every row's file exists (a `link` row's path
is its URL); no `.env` or connections outside `.machine/`; `.machine/connections` is 0700; every links.tsv row
names a target inside the folder. `relink` makes the links.tsv links on this machine: a correct link stays, a wrong
link is replaced, a real file or folder in the way is reported and never touched (seen once: a client folder's hand-written
relink.sh, 2026-11-05). `source` copies a file into today's inbox (never moves or renames the original) or records
a URL, and appends its INDEX row with the next id and the file's sha256; the same bytes again are refused and the
earlier id named. A file already under inbox/ with no row (seen once: eight in one client's) gets its row in place, never
a copy, and bytes listed before are named in `duplicate_of`.

Stdlib only. Test: scaffold/tests/test_clients.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from datetime import date
from pathlib import Path

CONFIG = Path("~/.config/openmax/clients_dir")
INDEX_HEADER = ("id", "date", "source", "kind", "title", "path", "bytes", "files", "sha256", "read_by",
                "duplicate_of", "note")
SOURCES = ("client", "platform", "meeting", "chat", "api-agent", "ask", "digest")   # api-agent: an agent pulled it through a platform API
INTAKE = ("brief.md", "decisions.md", "open-questions.md")
LINKS_HEADER = ("path", "target", "note")
ID_RE = re.compile(r"EV-(\d{3,})")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
URL_RE = re.compile(r"https?://\S+")
SECRETISH = (".env", "connections")


class Stop(Exception):
    """A refusal: one line, exit 2."""


def root(explicit: str | None = None) -> Path:
    """The clients root: --root, else CLIENTS_DIR, else the config file; never a guess."""
    raw = explicit or os.environ.get("CLIENTS_DIR", "").strip()
    if not raw:
        cfg = CONFIG.expanduser()
        raw = cfg.read_text("utf-8").strip() if cfg.is_file() else ""
    if not raw:
        raise Stop(f"no clients root on this machine: set CLIENTS_DIR, or run `clients.py where --set DIR` "
                   f"(writes {CONFIG})")
    r = Path(raw).expanduser()
    if not r.is_dir():
        raise Stop(f"the clients root {r} is not a folder: make it, or name another")
    return r.resolve()


def clients(r: Path) -> list[Path]:
    return sorted(p for p in r.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


def folder(r: Path, name: str) -> Path:
    if not NAME_RE.fullmatch(name):
        raise Stop(f"{name!r} is not a client name (a-z, 0-9, _ and -)")
    p = r / name
    if not p.is_dir():
        raise Stop(f"no client {name!r} under {r}")
    return p


# ---- the sources index ---------------------------------------------------------------------

def read_index(p: Path) -> tuple[list[str], list[dict]]:
    lines = p.read_text("utf-8").splitlines()
    head = lines[0].split("\t") if lines else []
    return head, [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln.strip()]


def digest(p: Path) -> tuple[str, int, int]:
    """sha256, bytes, files; a folder's hash is the hash of its files' hashes in path order."""
    if p.is_file():
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest(), p.stat().st_size, 1
    parts, size, n = [], 0, 0
    for q in sorted(x for x in p.rglob("*") if x.is_file() and x.name != ".DS_Store"):
        d, b, _ = digest(q)
        parts.append(f"{q.relative_to(p).as_posix()}:{d}")
        size, n = size + b, n + 1
    return hashlib.sha256("\n".join(parts).encode()).hexdigest(), size, n


def next_id(rows: list[dict]) -> str:
    seen = [int(m.group(1)) for r in rows if (m := ID_RE.fullmatch(r.get("id", "")))]
    return f"EV-{(max(seen) + 1) if seen else 1:03d}"


def add_source(c: Path, item: str, *, source: str, title: str, day: str, kind: str | None = None,
               read_by: str = "", note: str = "") -> dict:
    if source not in SOURCES:
        raise Stop(f"--from {source!r}: one of {', '.join(SOURCES)}")
    if not title.strip() or "\t" in title + note or "\n" in title + note:
        raise Stop("--title is one line of text with no tab")
    idx = c / "sources" / "INDEX.tsv"
    if not idx.is_file():
        raise Stop(f"{idx} is missing: this folder is not laid out yet (clients.py check {c.name})")
    _, rows = read_index(idx)
    rid = next_id(rows)
    if URL_RE.fullmatch(item):
        if any(r.get("path") == item for r in rows):
            raise Stop(f"{item} is already {next(r['id'] for r in rows if r.get('path') == item)}")
        row = {"id": rid, "date": day, "source": source, "kind": kind or "link", "title": title, "path": item,
               "bytes": "", "files": "", "sha256": "", "read_by": read_by, "duplicate_of": "", "note": note}
    else:
        src = Path(item).expanduser()
        if not src.exists():
            raise Stop(f"{src} does not exist")
        sha, size, n = digest(src)
        same = [r["id"] for r in rows if r.get("sha256") == sha]
        inbox = (c / "sources" / "inbox").resolve()
        if inbox in src.resolve().parents:
            # already kept but never listed: the row only, in place; the same bytes listed before are named
            dest = src.resolve()
            if any(r.get("path") == dest.relative_to(inbox.parent).as_posix() for r in rows):
                raise Stop(f"{src.name} is already listed")
        else:
            if same:
                raise Stop(f"{src.name}: the same bytes are already {same[0]}; nothing copied")
            dest_dir = c / "sources" / "inbox" / f"{day}-{source}"
            dest = dest_dir / src.name
            if dest.exists():
                raise Stop(f"{dest} exists with other bytes: rename the original first, never the kept copy")
            dest_dir.mkdir(parents=True, exist_ok=True)
            (shutil.copytree if src.is_dir() else shutil.copy2)(src, dest)
            dest, same = dest.resolve(), []
        row = {"id": rid, "date": day, "source": source, "kind": kind or ("folder" if src.is_dir() else "file"),
               "title": title, "path": dest.relative_to(inbox.parent).as_posix(), "bytes": str(size),
               "files": str(n), "sha256": sha, "read_by": read_by, "duplicate_of": same[0] if same else "",
               "note": note}
    with idx.open("a", encoding="utf-8") as f:
        f.write("\t".join(row[k] for k in INDEX_HEADER) + "\n")
    return row


# ---- links this machine needs ----------------------------------------------------------------

def read_links(c: Path) -> list[dict]:
    p = c / ".machine" / "links.tsv"
    if not p.is_file():
        return []
    head, rows = read_index(p)
    return rows if tuple(head) == LINKS_HEADER else [{"path": "", "target": "", "note": "bad header"}]


def relink(c: Path, dry: bool = False) -> list[str]:
    out = []
    for r in read_links(c):
        where = Path(os.path.expanduser(r["path"]))
        if not where.is_absolute():
            where = c / where
        target = (c / r["target"]).resolve() if not Path(r["target"]).is_absolute() else Path(r["target"])
        if where.is_symlink():
            if where.resolve() == target:                   # where it leads, however it is written
                out.append(f"ok      {where}")
                continue
            if not dry:
                where.unlink()
        elif where.exists():
            out.append(f"SKIP    {where} is a real file or folder: move it into {c} by hand first")
            continue
        # a link inside the client folder is written relative, so the folder still works after a move
        inside = c.resolve() in where.parent.resolve().parents or where.parent.resolve() == c.resolve()
        to = os.path.relpath(target, where.parent.resolve()) if inside else str(target)
        if not dry:
            where.parent.mkdir(parents=True, exist_ok=True)
            where.symlink_to(to)
        out.append(f"linked  {where} -> {to}")
    return out


# ---- a new client's folder -------------------------------------------------------------------

CARD = """# {title}

位置:`$CLIENTS_DIR/{name}`(规矩见 playbook 的 `docs/clients.md`)。

| 想做什么 | 去哪里 |
|---|---|
| 回顾客户是谁、定了什么、还有什么没定 | `intake/`:`brief.md`、`decisions.md`、`open-questions.md`、`meetings/<日期>/` |
| 看客户和平台给过的原始资料(聊天记录、链接、视频、图片、文件) | `sources/`(总账 `sources/INDEX.tsv`,原样不改不删) |
| 看我们做出来的报表和页面 | `reports/` |
| 工具、数据库、连接和密钥 | `.machine/`(平时不用打开) |

客户的名字、金额只留在这个文件夹,不进代码仓库(名字写在 `.machine/client_terms.txt`)。
"""
INTAKE_TEXT = {"brief.md": "# {title}: brief\n\n(who, the goal, the limits, the plan in force)\n",
               "decisions.md": "# {title}: decisions\n\n(a mirror: the record that counts is the pack's decision rows)\n",
               "open-questions.md": "# {title}: open questions\n"}
SOURCES_TEXT = """# sources: what the client or a platform gave us, kept as received

One row an item in `INDEX.tsv` (docs/clients.md): `clients.py source {name} FILE_OR_URL --from F --title T`.
Files land in `inbox/<YYYY-MM-DD>-<from>/` and are never renamed, edited or removed.
"""


def new(r: Path, name: str, title: str, terms: list[str]) -> Path:
    if not NAME_RE.fullmatch(name):
        raise Stop(f"{name!r} is not a client name (a-z, 0-9, _ and -)")
    terms = [t.strip() for t in terms if t.strip()]
    if not terms:
        raise Stop("--term: at least one of the client's names, so the leak guard can keep it out of a repository")
    if not title.strip() or "\n" in title:
        raise Stop("--title is one line")
    c = r / name
    if c.exists():
        raise Stop(f"{c} exists: check it with `clients.py check {name}` instead")
    for d in ("intake/meetings", "sources/inbox", "reports"):
        (c / d).mkdir(parents=True)
    (c / ".machine").mkdir(mode=0o700)
    (c / "README.md").write_text(CARD.format(title=title, name=name), "utf-8")
    for f, text in INTAKE_TEXT.items():
        (c / "intake" / f).write_text(text.format(title=title), "utf-8")
    (c / "sources" / "README.md").write_text(SOURCES_TEXT.format(name=name), "utf-8")
    (c / "sources" / "INDEX.tsv").write_text("\t".join(INDEX_HEADER) + "\n", "utf-8")
    t = c / ".machine" / "client_terms.txt"
    t.write_text("".join(f"{x}\n" for x in terms), "utf-8")
    t.chmod(0o600)
    return c


# ---- the rules -------------------------------------------------------------------------------

def check(c: Path) -> list[str]:
    bad = []
    say = lambda what: bad.append(f"{c.name}: {what}")  # noqa: E731
    if not (c / "README.md").is_file():
        say("README.md (the client's card) is missing")
    for f in INTAKE:
        if not (c / "intake" / f).is_file():
            say(f"intake/{f} is missing")
    idx = c / "sources" / "INDEX.tsv"
    if not idx.is_file():
        say("sources/INDEX.tsv is missing")
    else:
        head, rows = read_index(idx)
        if tuple(head) != INDEX_HEADER:
            say(f"sources/INDEX.tsv header is not {' '.join(INDEX_HEADER)}")
        ids = [r.get("id", "") for r in rows]
        for i in sorted({i for i in ids if ids.count(i) > 1}):
            say(f"sources/INDEX.tsv: {i} is used twice")
        listed = set()
        for r in rows:
            p = r.get("path", "")
            if r.get("source") not in SOURCES:
                say(f"sources/INDEX.tsv {r.get('id')}: source {r.get('source')!r} is not one of {', '.join(SOURCES)}")
            if URL_RE.fullmatch(p):
                continue
            listed.add(p)
            if not (c / "sources" / p).exists():
                say(f"sources/INDEX.tsv {r.get('id')}: {p} does not exist")
        inbox = c / "sources" / "inbox"
        if inbox.is_dir():
            for day in sorted(x for x in inbox.iterdir() if x.is_dir()):
                for item in sorted(day.iterdir()):
                    rel = item.relative_to(c / "sources").as_posix()
                    covered = rel in listed or day.relative_to(c / "sources").as_posix() in listed
                    if item.name != ".DS_Store" and not covered:
                        say(f"sources/{rel} has no INDEX row (clients.py source, or add the row)")
    for top, dirs, files in os.walk(c):                      # links are not followed: they lead into .machine/
        here = Path(top)
        if here == c:
            dirs[:] = [d for d in dirs if d != ".machine"]
        for n in dirs + files:
            if n in SECRETISH:
                say(f"{(here / n).relative_to(c)}: a secret's place is under .machine/")
    if (c / ".machine").is_dir() and not any((c / ".machine").rglob("client_terms.txt")):
        say(".machine/ has no client_terms.txt: the leak guard cannot keep this client's names out of a repository")
    conn = c / ".machine" / "connections"
    if conn.is_dir() and stat.S_IMODE(conn.stat().st_mode) & 0o077:
        say(".machine/connections is readable by others: chmod 700")
    for r in read_links(c):
        t = r.get("target", "")
        if not t or Path(t).is_absolute() or ".." in Path(t).parts:
            say(f".machine/links.tsv: target {t!r} must be a path inside the client folder")
        elif not (c / t).exists():
            say(f".machine/links.tsv: target {t} does not exist")
    return bad


# ---- the command line ------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="clients.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", help="the clients root for this run (else CLIENTS_DIR, else the config file)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("where", help="print this machine's clients root, or --set it")
    w.add_argument("--set", metavar="DIR")
    sub.add_parser("list", help="the clients under the root").add_argument("--json", action="store_true")
    nw = sub.add_parser("new", help="lay out a folder for a new client")
    nw.add_argument("name")
    nw.add_argument("--title", required=True)
    nw.add_argument("--term", action="append", default=[], help="one of the client's names (repeat)")
    ck = sub.add_parser("check", help="each client's folder against the rules")
    ck.add_argument("names", nargs="*")
    ck.add_argument("--json", action="store_true")
    rl = sub.add_parser("relink", help="make .machine/links.tsv's links on this machine")
    rl.add_argument("name")
    rl.add_argument("--dry-run", action="store_true")
    so = sub.add_parser("source", help="keep a file or a link the client or a platform gave us")
    so.add_argument("name")
    so.add_argument("item")
    so.add_argument("--from", dest="source", required=True, choices=SOURCES)
    so.add_argument("--title", required=True)
    so.add_argument("--date", default=date.today().isoformat())
    so.add_argument("--kind")
    so.add_argument("--read-by", default="")
    so.add_argument("--note", default="")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "where":
            if a.set:
                d = Path(a.set).expanduser().resolve()
                if not d.is_dir():
                    raise Stop(f"{d} is not a folder")
                cfg = CONFIG.expanduser()
                cfg.parent.mkdir(parents=True, exist_ok=True)
                cfg.write_text(f"{d}\n", "utf-8")
                print(f"clients root: {d} (written to {cfg}; CLIENTS_DIR, when set, still wins)")
                return 0
            print(root(a.root))
            return 0
        r = root(a.root)
        if a.cmd == "list":
            names = [p.name for p in clients(r)]
            print(json.dumps({"root": str(r), "clients": names}) if a.json else "\n".join(names) or "(none)")
            return 0
        if a.cmd == "new":
            c = new(r, a.name, a.title, a.term)
            print(f"made {c}; next: put meetings in intake/meetings/<date>/, everything else with `source`")
            return 0
        if a.cmd == "check":
            todo = [folder(r, n) for n in a.names] if a.names else clients(r)
            bad = [x for c in todo for x in check(c)]
            if a.json:
                print(json.dumps({"root": str(r), "checked": [c.name for c in todo], "problems": bad}))
            else:
                print("\n".join(bad) if bad else f"ok: {len(todo)} client folder(s) under {r}")
            return 1 if bad else 0
        if a.cmd == "relink":
            lines = relink(folder(r, a.name), a.dry_run)
            print("\n".join(lines) if lines else "no .machine/links.tsv rows")
            return 1 if any(x.startswith("SKIP") for x in lines) else 0
        if a.cmd == "source":
            row = add_source(folder(r, a.name), a.item, source=a.source, title=a.title, day=a.date, kind=a.kind,
                             read_by=a.read_by, note=a.note)
            print(f"{row['id']}  {row['path']}")
            return 0
    except Stop as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
