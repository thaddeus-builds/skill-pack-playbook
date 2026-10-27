#!/usr/bin/env python3
"""kit/snapshot.py holds each of its guards.

  1. The package holds the database (by SQLite's backup, integrity ok, the
     skill pack's user_version), the workspace files, the human export, the
     client folder's content/ and reports/, and a MANIFEST whose sha256 of
     every file matches; the pack's exclude list is honoured and an empty one
     leaves nothing out but the live database and its journal files.
  2. The workspace is only read: its tree hashes the same after (but for
     the WAL index -shm, which any reader of a WAL database touches).
  3. A secret value (from the workspace .env, an extra env file, the process
     env under the pack's prefix) or a token shape (or one the pack adds) in
     anything about to be packed refuses: nothing is left in the output
     folder, not even a temporary one, and the error never holds the secret.
  4. An output folder inside the workspace, keep < 1, a missing database and
     a failing integrity check are refused, coded.
  5. keep prunes only this client's packages (and their sidecars), ordered by
     (timestamp, -N): a same-second `...Z-2.tgz` is newer than `...Z.tgz`.
  6. dry_run writes nothing; a package never overwrites another.
  7. snapshot.py's msg() calls are closed over its fragment.
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import messages, snapshot  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.testing.check import check, finish, raises, tmp_dir  # noqa: E402

CFG = _shop.use()
PASS = "shop-secret-pass-123456"
TOKEN = "shpat_" + "0123456789abcdef" * 2
EXCLUDE = [".env", ".env.*", "*.pem", "*.key", "seo.db-*", ".DS_Store", ".git",
           "backups"]
T0 = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)


def export(conn):
    n = conn.execute("SELECT count(*) AS n FROM facts").fetchone()["n"]
    return f"facts: {n}\n", {"facts": n}


def build(client: bool = True) -> dict:
    """A workspace with a DB in WAL mode, files to pack, files to exclude."""
    root = Path(tmp_dir("snap-"))
    folder = root / "acme"
    data = folder / "data" if client else root / "plain-ws"
    data.mkdir(parents=True)
    if client:
        (folder / "client.env").write_text("NAME=acme\n")
        (folder / "reports").mkdir()
        (folder / "reports" / "r.md").write_text("report")
        (folder / "content").mkdir()
        (folder / "content" / "a.md").write_text("article")
    db = data / "shop.db"
    c = sqlite3.connect(db)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA user_version=7")
    c.execute("CREATE TABLE facts (k TEXT, v TEXT)")
    c.execute("INSERT INTO facts VALUES ('site', 'acme-site-value')")
    c.commit()                       # the connection stays open: -wal exists
    (data / ".env").write_text(f'SHOP_API_PASS="{PASS}"\nSHOP_SHOP=acme.x\n')
    (data / "server.pem").write_text("not for a package")
    (data / "intake").mkdir()
    (data / "intake" / "notes.txt").write_text("client notes")
    (data / "backups").mkdir()
    (data / "backups" / "human-1.db").write_bytes(b"x")
    out = root / "out"
    return {"root": root, "folder": folder, "data": data, "db": db, "out": out,
            "conn": c}


def tree(d: Path) -> dict:
    """Every file's sha256 but the WAL index (-shm): any reader of a WAL
    database touches that shared-memory file, and it holds no data."""
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.rglob("*"))
            if p.is_file() and not p.name.endswith("-shm")}


def kw(w: dict, **over) -> dict:
    return {"data_dir": str(w["data"]), "db_path": str(w["db"]),
            "out_dir": str(w["out"]), "keep": 3, "pack_version": "1.2.3",
            "schema_version": 7, "human_export": export, "now": T0,
            "exclude": EXCLUDE, **over}


def run(w: dict, **over) -> dict:
    return snapshot.make(**kw(w, **over))


def code_of(fn) -> str | None:
    e = raises(fn, SkillPackError)
    return getattr(getattr(e, "message", None), "code", None)


def extract(pkg: str) -> tuple[Path, list[str]]:
    ex = Path(tmp_dir("snap-x-"))
    with tarfile.open(pkg) as tf:
        names = sorted(m.name.lstrip("./") for m in tf.getmembers() if m.isfile())
        if hasattr(tarfile, "data_filter"):
            tf.extractall(ex, filter="data")
        else:
            tf.extractall(ex)
    return ex, names


def test_package() -> None:
    print("[1+2] what is in the package; the workspace is only read")
    w = build()
    before = tree(w["data"])
    doc = run(w)
    check("the workspace is only read: every file is as it was",
          tree(w["data"]) == before)
    ex, names = extract(doc["package"])
    check("the package holds the DB, the export, the manifest, the workspace "
          "files and the client folder's content/ and reports/",
          {"workspace/shop.db", "workspace/human-export.txt", "MANIFEST.json",
           "workspace/intake/notes.txt", "reports/r.md", "content/a.md"}
          <= set(names), names)
    check("no .env, no key, no backups/, no live DB journal in it",
          not [n for n in names if n.endswith((".env", ".pem", "-wal", "-shm"))
               or "backups" in n], names)
    check("the DB in it is the backup, not the live file",
          doc["package"].endswith(".tgz") and
          sqlite3.connect(ex / "workspace" / "shop.db").execute(
              "SELECT v FROM facts").fetchone()[0] == "acme-site-value")
    man = json.loads((ex / "MANIFEST.json").read_text())
    check("integrity ok and user_version carried",
          (man["integrity"], man["user_version"], man["schema_version"],
           man["pack_version"]) == ("ok", 7, 7, "1.2.3"), man)
    bad = [f for f, v in man["files"].items()
           if hashlib.sha256((ex / f).read_bytes()).hexdigest() != v["sha256"]]
    check("every file's sha256 in the manifest matches the file", bad == [], bad)
    check("the database's too", man["db_sha256"]
          == man["files"]["workspace/shop.db"]["sha256"])
    check("the manifest counts the human rows the pack's export returned",
          man["human_rows"] == {"facts": 1}, man["human_rows"])
    side = json.loads(Path(doc["manifest"]).read_text())
    check("a sidecar manifest beside the package names it and its sha256",
          (side["package_sha256"], side["package"])
          == (doc["sha256"], os.path.basename(doc["package"]))
          and hashlib.sha256(Path(doc["package"]).read_bytes()).hexdigest()
          == doc["sha256"])
    check("the client folder names the client; the stamp is the injected UTC "
          "now", os.path.basename(doc["package"])
          == "acme-snapshot-20261027T120000Z.tgz", doc["package"])
    check("the report lists what was left out",
          ".env" in doc["left_out"] and "server.pem" in doc["left_out"]
          and "backups/" in doc["left_out"], doc["left_out"])
    leftovers = sorted(os.listdir(w["out"]))
    check("the output folder holds the package and its sidecar only",
          len(leftovers) == 2, leftovers)


def test_exclude_default() -> None:
    print("\n[1] an empty exclude list leaves nothing out but the live DB")
    w = build(client=False)
    (w["data"] / "backups" / "x").write_text("y")
    (w["data"] / ".env").write_text("SHOP_NAME=acme-shop-name\n")   # no secret
    doc = run(w, exclude=())
    ex, names = extract(doc["package"])
    check("a plain workspace names the client after its folder",
          os.path.basename(doc["package"]).startswith("plain-ws-snapshot-"))
    check(".env, the key and backups/ are packed when the pack lists nothing",
          {"workspace/.env", "workspace/server.pem",
           "workspace/backups/human-1.db"} <= set(names), names)
    check("the live DB file and its -wal/-shm are never packed as plain "
          "files; the one DB in the package is the backup",
          [n for n in names if "shop.db" in n] == ["workspace/shop.db"], names)
    check("the pack's export function is called when given",
          "workspace/human-export.txt" in names, names)
    _, n2 = extract(run(w, exclude=(), human_export=None, now=T0.replace(second=1))["package"])
    check("human_export=None writes no export file and no rows",
          "workspace/human-export.txt" not in n2, n2)


def test_secrets() -> None:
    print("\n[3] a secret refuses and leaves nothing")
    w = build()
    leak = w["data"] / "intake" / "leak.txt"
    leak.write_text(f"the password is {PASS} in plain words")
    e = raises(lambda: run(w), SkillPackError)
    check("a file holding a secret value of the workspace .env: refused, coded",
          e is not None and e.message.code == "snapshot_secret_found",
          e and e.message)
    check("... the error never prints the secret",
          PASS not in str(e) and PASS not in json.dumps(
              messages.code(e.message)))
    check("... nothing is left in the output folder, not even a temporary one",
          not w["out"].exists() or os.listdir(w["out"]) == [],
          os.listdir(w["out"]) if w["out"].exists() else None)
    leak.unlink()
    tok = w["data"] / "intake" / "token.txt"
    tok.write_text(f"token {TOKEN}")
    check("a token shape (Shopify access token): refused",
          code_of(lambda: run(w)) == "snapshot_secret_found")
    tok.unlink()
    pk = w["folder"] / "reports" / "key.txt"
    pk.write_text("-----BEGIN RSA PRIVATE " + "KEY-----\nabc")
    check("... also in the client folder's reports/",
          code_of(lambda: run(w)) == "snapshot_secret_found")
    pk.unlink()
    check("a clean workspace passes (the excluded .env holding the secret is "
          "not scanned as a leak)", run(w)["secrets_checked"])
    other = Path(tmp_dir("envf-")) / "home.env"
    other.write_text("OTHER_API_TOKEN=abcdefgh-12345678\n")
    (w["data"] / "intake" / "n2.txt").write_text("has abcdefgh-12345678 in it")
    check("a secret of an extra env file counts",
          code_of(lambda: run(w, env_files=[str(other)]))
          == "snapshot_secret_found")
    check("... and without that file it is not known to be one",
          run(w, now=T0.replace(second=2))["secrets_checked"])
    (w["data"] / "intake" / "n2.txt").unlink()
    (w["data"] / "intake" / "n3.txt").write_text("proc-secret-value-99")
    os.environ["SHOP_SERVICE_TOKEN"] = "proc-secret-value-99"
    os.environ["ELSEWHERE_TOKEN"] = "other-secret-value-99"
    try:
        check("a secret in the process env under the pack's prefix counts "
              "(the default prefix is the bound skill pack's)",
              code_of(lambda: run(w)) == "snapshot_secret_found")
        check("... an explicit prefix list replaces it",
              run(w, env_prefixes=["ELSEWHERE_"],
                  now=T0.replace(second=3))["secrets_checked"])
        (w["data"] / "intake" / "n3.txt").write_text("other-secret-value-99")
        check("... and names the other prefix",
              code_of(lambda: run(w, env_prefixes=["ELSEWHERE_"]))
              == "snapshot_secret_found")
    finally:
        del os.environ["SHOP_SERVICE_TOKEN"], os.environ["ELSEWHERE_TOKEN"]
    (w["data"] / "intake" / "n3.txt").write_text("acme-ticket-ZZ-0000000001")
    check("a pack's own token shape is refused",
          code_of(lambda: run(w,
                              extra_shapes=[re.compile(rb"acme-ticket-[A-Z]{2}-\d{10}")]))
          == "snapshot_secret_found")


def test_refusals() -> None:
    print("\n[4] refusals")
    w = build()
    check("an output folder inside the workspace: refused",
          code_of(lambda: run(w, out_dir=str(w["data"] / "snaps")))
          == "snapshot_out_inside")
    check("... the workspace itself too",
          code_of(lambda: run(w, out_dir=str(w["data"]))) == "snapshot_out_inside")
    check("keep 0: refused", code_of(lambda: run(w, keep=0)) == "snapshot_keep_invalid")
    check("a workspace with no database: refused, coded (even in a dry run)",
          code_of(lambda: run(w, db_path=str(w["data"] / "none.db"))) == "no_db"
          and code_of(lambda: run(w, db_path=str(w["data"] / "none.db"),
                                  dry_run=True)) == "no_db")
    check("a refusal exits 2 through the contract (it is a SkillPackError)",
          issubclass(snapshot.SnapshotError, SkillPackError))
    check("nothing was written by any of them", not w["out"].exists())
    bad = Path(tmp_dir("snap-bad-")) / "bad.db"
    bad.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100 + b"garbage" * 600)
    wb = build()
    r = raises(lambda: run(wb, db_path=str(bad)), Exception)
    pkgs = [f for f in os.listdir(wb["out"])] if wb["out"].exists() else []
    check("a file that is not a database refuses and leaves nothing in the "
          "output folder", r is not None and pkgs == [], (repr(r), pkgs))
    fake = snapshot.SnapshotError(messages.msg(
        "snapshot_integrity", "x", detail="row 1 missing"))
    check("snapshot_integrity is a registered code",
          fake.message.code == "snapshot_integrity")


def test_keep() -> None:
    print("\n[5] keep prunes only this client's packages, in time order")
    w = build()
    out = w["out"]
    out.mkdir()
    other = out / "someone-else-snapshot-20200101T000000Z.tgz"
    note = out / "README.txt"
    longer = out / "acme-corp-snapshot-20200101T000000Z.tgz"
    for p in (other, note, longer):
        p.write_text("keep me")
    made = [run(w, keep=2, now=T0.replace(minute=i)) for i in range(3)]
    check("three snapshots with keep 2: the oldest is deleted, with its sidecar",
          made[2]["pruned"] == [os.path.basename(made[0]["package"])]
          and not os.path.exists(made[0]["package"])
          and not os.path.exists(made[0]["manifest"]), made[2]["pruned"])
    check("another client's package (a longer name too) and a file that is no "
          "package are never deleted",
          other.exists() and note.exists() and longer.exists())
    check("the kept list is the two newest",
          made[2]["kept"] == [os.path.basename(m["package"]) for m in made[1:]])
    # same second: ...Z, ...Z-2, ...Z-3 sort by N, not by string
    w2 = build()
    same = [run(w2, keep=2) for _ in range(3)]
    names = [os.path.basename(s["package"]) for s in same]
    check("the same second gets -2 and -3, never an overwrite",
          [n.split("Z")[-1] for n in names] == [".tgz", "-2.tgz", "-3.tgz"],
          names)
    check("... and prune treats -2 as newer than the bare name (a string sort "
          "puts '-2.tgz' before '.tgz')",
          same[2]["pruned"] == [names[0]] and same[2]["kept"] == names[1:],
          (same[2]["pruned"], same[2]["kept"]))
    check("prune() alone: keep more than there are deletes nothing",
          snapshot.prune(str(w2["out"]), "acme", 9)[1] == [])


def test_dry_run() -> None:
    print("\n[6] dry run")
    w = build()
    w["out"].mkdir()
    (w["out"] / "x.txt").write_text("x")
    before = sorted(os.listdir(w["out"]))
    doc = run(w, dry_run=True, exclude=EXCLUDE)
    check("a dry run writes nothing", sorted(os.listdir(w["out"])) == before
          and doc["dry_run"] is True and "package" not in doc)
    check("... and lists what would go in and what is left out",
          doc["would_pack"] == 1 + 2 + 1 and ".env" in doc["left_out"]
          and doc["client"] == "acme", doc)


def test_closure() -> None:
    print("\n[7] snapshot.py's msg() calls are closed over its fragment")
    problems = messages.check_registry_closed(
        _shop.PLAYBOOK, ["kit/snapshot.py"], strict_kit=False)
    mine = [p for p in problems if "snapshot" in p and "registered but" not in p]
    check("every msg() call names a registered code with exactly its params",
          mine == [], mine)
    reg = messages.registry()
    check("the four codes are in the kit registry, in English and Chinese",
          all(c in reg and reg[c].get("meaning_en") and reg[c].get("meaning_zh")
              for c in ("snapshot_out_inside", "snapshot_keep_invalid",
                        "snapshot_integrity", "snapshot_secret_found")))


if __name__ == "__main__":
    test_package()
    test_exclude_default()
    test_secrets()
    test_refusals()
    test_keep()
    test_dry_run()
    test_closure()
    raise SystemExit(finish())
