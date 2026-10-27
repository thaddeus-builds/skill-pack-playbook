"""A snapshot of a client's workspace: one package that restores it.

`make()` packs the workspace of one client (its data dir) into
`<client>-snapshot-<UTC>[-N].tgz` in a folder the caller names, with a
`<same>.manifest.json` beside it. In this order:

  1. the database by SQLite's own backup API from a read-only connection
     (never a file copy: a copy taken mid-write is torn), then
     `PRAGMA integrity_check` and `user_version` on the copy. The live
     database file and its -wal/-shm/-journal files are never copied as
     plain files, whatever `exclude` says;
  2. the rest of the workspace, and, when the workspace sits in a client
     folder (`client_marker` beside it), that folder's `client_dirs`,
     without any path `exclude` matches. `exclude` is the pack's own list
     (fnmatch against the relative posix path or its last name); the kit
     bakes in none, so an empty list packs every file. A pack that keeps
     credentials in the workspace lists them (`.env`, `*.pem`, ...);
  3. the human-tables export, refreshed from the copy (`human_export` is
     the pack's function);
  4. a scan of everything about to be packed: the secret values of the env
     files (`<data_dir>/.env` and `env_files`) and of this process's own
     environment (`env_prefixes`), and token shapes (`SHAPES`; a pack
     extends them with `extra_shapes`). One hit and nothing is written,
     not even a temporary folder; the error names the files, never the
     secret;
  5. MANIFEST.json (pack version, schema version, integrity, the sha256 and
     size of every file, the rows of each human table), then the package
     and its sidecar, both written atomically;
  6. only in `out_dir`: this client's packages beyond the newest `keep`
     are deleted, in order of (timestamp, -N); another client's package or
     any other file is never touched.

The workspace is only read (a reader of a WAL-mode database touches its
-shm index file, which holds no data). `out_dir` must lie outside it. Moving a package
somewhere else (a second disk, a bucket) is the operator's step (rclone,
rsync): the kit holds no credentials and uploads nothing.

Stdlib only; imports base only. Test: kit/tests/test_snapshot.py.
Seen once: the SEO skill pack's S71 built it first (2026-10).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from typing import Callable, Iterable

from kit import atomic, config, dates, env
from kit.contract import SkillPackError
from kit.messages import msg

FORMAT = 1
NAME = re.compile(r"[^A-Za-z0-9._-]+")
SECRET_NAME = re.compile(r"(SECRET|PASS|PASSWORD|TOKEN|KEY|CLIENT_ID)", re.I)
NOT_SECRET = re.compile(r"(_FILE|_URL|_PATH|_DIR|_USER|_HOST|_PORT)$", re.I)
SHAPES: tuple[re.Pattern, ...] = tuple(re.compile(p) for p in (
    rb"shpat_[0-9a-f]{32}", rb"shpss_[0-9a-f]{32}",
    rb"-----BEGIN [A-Z ]*PRIVATE KEY", rb"glpat-[A-Za-z0-9_-]{20}",
    rb"ghp_[A-Za-z0-9]{36}", rb"github_pat_[A-Za-z0-9_]{40,}",
    rb"(?<![A-Za-z0-9/-])sk-[A-Za-z0-9_-]{20,}"))
CHUNK, OVERLAP = 8 << 20, 512
MIN_SECRET = 8
DB_SIDES = ("-wal", "-shm", "-journal")
EXPORT_NAME = "human-export.txt"


class SnapshotError(SkillPackError):
    """A snapshot refused: nothing was written (or, for a prune, nothing was
    deleted). The coded message is args[0]."""


def excluded(rel: str, pats: Iterable[str]) -> bool:
    """A relative path (posix) is out when any pattern matches the whole
    path or its last name."""
    base = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(base, p)
               for p in pats)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _secret(name: str) -> bool:
    return bool(SECRET_NAME.search(name)) and not NOT_SECRET.search(name)


def secret_values(env_files: Iterable[str]) -> list[bytes]:
    """The values of the secret-looking variables of the given env files
    (kit.env.parse: quotes stripped; 8+ characters)."""
    out = []
    for p in env_files:
        for k, v in env.parse(os.path.expanduser(str(p))).items():
            if _secret(k) and len(v) >= MIN_SECRET:
                out.append(v.encode("utf-8"))
    return out


def process_secrets(environ, prefixes: Iterable[str]) -> list[bytes]:
    """The values of the credential variables handed to this process (a
    host that injects them instead of a file): names that start with one of
    `prefixes` and look like a secret."""
    pre = tuple(prefixes)
    if not pre:
        return []
    return [v.encode("utf-8") for k, v in environ.items()
            if k.startswith(pre) and _secret(k) and len(v) >= MIN_SECRET]


def scan(root: str, values: list[bytes],
         shapes: Iterable[re.Pattern] = SHAPES) -> list[str]:
    """The files under `root` holding a secret value or a token shape
    (relative paths, sorted)."""
    shapes = tuple(shapes)
    hits = []
    for r, _, fs in os.walk(root):
        for f in sorted(fs):
            path = os.path.join(r, f)
            tail, found = b"", False
            with open(path, "rb") as fh:
                while not found:
                    block = fh.read(CHUNK)
                    if not block:
                        break
                    data = tail + block
                    found = (any(v in data for v in values)
                             or any(s.search(data) for s in shapes))
                    tail = data[-OVERLAP:]
            if found:
                hits.append(os.path.relpath(path, root))
    return sorted(hits)


def _walk(src: str, pats: list[str], on_file, on_left) -> None:
    """The one walk behind the plan and the copy: `on_file(rel)` for every
    file that goes in, `on_left(rel)` for what is left out (a directory with
    a trailing slash). Symlinks are skipped."""
    for r, dirs, fs in os.walk(src):
        rel_dir = os.path.relpath(r, src).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        keep = []
        for d in sorted(dirs):
            rel = f"{rel_dir}/{d}".lstrip("/")
            if excluded(rel, pats):
                on_left(rel + "/")
            else:
                keep.append(d)
        dirs[:] = keep
        for f in sorted(fs):
            rel = f"{rel_dir}/{f}".lstrip("/")
            if excluded(rel, pats):
                on_left(rel)
            elif not os.path.islink(os.path.join(r, f)):
                on_file(rel)


def client_of(data_dir: str,
              marker: str | None) -> tuple[str, str | None]:
    """(name, client folder or None): the folder that holds `marker` beside
    the workspace names the client, else the workspace's own name does."""
    data_dir = os.path.abspath(data_dir.rstrip("/"))
    folder = os.path.dirname(data_dir)
    if marker and os.path.isfile(os.path.join(folder, marker)):
        base = os.path.basename(folder)
        return NAME.sub("-", base).strip("-") or "client", folder
    return NAME.sub("-", os.path.basename(data_dir)).strip("-") or "client", None


def _env_prefixes() -> tuple[str, ...]:
    try:
        return (config.config().env_prefix + "_",)
    except config.ConfigError:
        return ()


def make(*, data_dir: str, db_path: str, out_dir: str, keep: int,
         pack_version: str, schema_version: int,
         human_export: Callable[[sqlite3.Connection],
                                tuple[str, dict]] | None = None,
         exclude: Iterable[str] = (),
         env_files: Iterable[str] = (),
         env_prefixes: Iterable[str] | None = None,
         extra_shapes: Iterable[re.Pattern] = (),
         client_marker: str | None = "client.env",
         client_dirs: Iterable[str] = ("content", "reports"),
         dry_run: bool = False,
         now: datetime | None = None) -> dict:
    """The snapshot (module docstring); raises SnapshotError.

    `human_export(conn)` -> (text, {table: rows}), `conn` a row_factory=Row
    connection to the COPY; None = no export file, human_rows {}.
    `exclude`: the pack's own patterns (empty = nothing left out). The live
    database and its journal files are always left out of the file copy.
    `env_files`: more env files whose secret values must not appear
    (`<data_dir>/.env` is always read). `env_prefixes`: prefixes of the
    process-env variables whose values count as secrets (None = the bound
    skill pack's `<ENV_PREFIX>_`). `now`: aware datetime (default
    kit.dates.now()). dry_run lists what would be packed and writes nothing.
    """
    data_dir = os.path.abspath(data_dir.rstrip("/"))
    out_dir = os.path.abspath(out_dir)
    db_path = os.path.abspath(db_path)
    if out_dir == data_dir or out_dir.startswith(data_dir + os.sep):
        raise SnapshotError(msg(
            "snapshot_out_inside",
            f"{out_dir} is inside the workspace: a package there would be "
            f"packed into the next one; name a folder outside it",
            out=out_dir))
    if keep < 1:
        raise SnapshotError(msg(
            "snapshot_keep_invalid",
            f"keep {keep}: keep at least one package", keep=keep))
    pats = list(exclude)
    if db_path.startswith(data_dir + os.sep):       # the live DB: its own path
        rel_db = os.path.relpath(db_path, data_dir).replace(os.sep, "/")
        pats += [rel_db + s for s in ("", *DB_SIDES)]
    name, folder = client_of(data_dir, client_marker)
    client_dirs = tuple(client_dirs)
    t = (now or dates.now()).astimezone(timezone.utc)
    stamp = t.strftime("%Y%m%dT%H%M%SZ")
    plan_in: list[str] = []
    left: list[str] = []
    _walk(data_dir, pats, plan_in.append, left.append)
    for d in (client_dirs if folder else ()):
        if os.path.isdir(os.path.join(folder, d)):
            _walk(os.path.join(folder, d), pats, plan_in.append, left.append)
    db_exists = os.path.exists(db_path)
    base = {"client": name, "workspace": data_dir, "out": out_dir,
            "keep": keep, "dry_run": dry_run,
            "would_pack": len(plan_in) + (1 if db_exists else 0),
            "left_out": sorted(left)[:50], "left_out_count": len(left)}
    if not db_exists:
        raise SnapshotError(msg("no_db", f"No database at {db_path}",
                                path=db_path))
    if dry_run:
        return base
    shapes = (*SHAPES, *extra_shapes)
    prefixes = _env_prefixes() if env_prefixes is None else tuple(env_prefixes)
    db_name = os.path.basename(db_path)
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".snapshot-") as tmp:
        ws = os.path.join(tmp, "workspace")
        os.makedirs(ws)
        kept: list[str] = []
        left = []

        def copy(src: str, dst: str, p: list[str]) -> None:
            def one(rel: str) -> None:
                os.makedirs(os.path.dirname(os.path.join(dst, rel)),
                            exist_ok=True)
                shutil.copy2(os.path.join(src, rel), os.path.join(dst, rel))
                kept.append(rel)
            _walk(src, p, one, left.append)

        copy(data_dir, ws, pats)
        copy_db = os.path.join(ws, db_name)
        src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        dst = sqlite3.connect(copy_db)
        rows: dict = {}
        text = None
        try:
            src.backup(dst)
            integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
            user_version = dst.execute("PRAGMA user_version").fetchone()[0]
            if integrity == "ok" and human_export is not None:
                dst.row_factory = sqlite3.Row
                text, rows = human_export(dst)
        finally:
            src.close()
            dst.close()
        for side in DB_SIDES:       # reading a WAL-mode copy leaves a -shm
            try:
                p = copy_db + side
                if side == "-shm" or os.path.getsize(p) == 0:
                    os.remove(p)
            except FileNotFoundError:
                pass
        if integrity != "ok":
            raise SnapshotError(msg(
                "snapshot_integrity",
                f"the copy of the database fails PRAGMA integrity_check "
                f"({integrity[:120]}): no package written",
                detail=integrity[:120]))
        if text is not None:
            with atomic.open_atomic(os.path.join(ws, EXPORT_NAME)) as f:
                f.write(text)
        if folder:
            for d in client_dirs:
                if os.path.isdir(os.path.join(folder, d)):
                    copy(os.path.join(folder, d), os.path.join(tmp, d), pats)
        values = (secret_values([os.path.join(data_dir, ".env"), *env_files])
                  + process_secrets(os.environ, prefixes))
        hits = scan(tmp, values, shapes)
        if hits:
            raise SnapshotError(msg(
                "snapshot_secret_found",
                f"{len(hits)} file(s) hold a secret value or a token "
                f"({', '.join(hits[:5])}): no package written; remove it "
                f"from the file, or list the file in the pack's exclude "
                f"patterns", n=len(hits), files="|".join(hits[:20])))
        files = {}
        for r, _, fs in os.walk(tmp):
            for f in sorted(fs):
                p = os.path.join(r, f)
                files[os.path.relpath(p, tmp).replace(os.sep, "/")] = {
                    "bytes": os.path.getsize(p), "sha256": sha256(p)}
        manifest = {
            "format": FORMAT, "client": name, "created_at": stamp,
            "pack_version": pack_version, "schema_version": schema_version,
            "user_version": user_version, "integrity": integrity,
            "db_file": f"workspace/{db_name}",
            "db_sha256": files[f"workspace/{db_name}"]["sha256"],
            "human_rows": rows, "files": dict(sorted(files.items())),
            "left_out": sorted(left)[:200]}
        atomic.write_json_atomic(os.path.join(tmp, "MANIFEST.json"),
                                 manifest, indent=2)
        stem, n = f"{name}-snapshot-{stamp}", 1
        while os.path.exists(os.path.join(out_dir, stem + ".tgz")):
            n += 1
            stem = f"{name}-snapshot-{stamp}-{n}"
        pkg = os.path.join(out_dir, stem + ".tgz")
        part = f"{pkg}.{os.getpid()}.tmp"
        try:
            with tarfile.open(part, "w:gz") as tf:
                for entry in sorted(os.listdir(tmp)):
                    tf.add(os.path.join(tmp, entry), arcname=entry)
            os.replace(part, pkg)
        finally:
            if os.path.exists(part):
                os.remove(part)
    side = os.path.join(out_dir, stem + ".manifest.json")
    atomic.write_json_atomic(side, {
        **manifest, "package": os.path.basename(pkg),
        "package_bytes": os.path.getsize(pkg), "package_sha256": sha256(pkg)},
        indent=2)
    mine, pruned = prune(out_dir, name, keep)
    return {**base, "package": pkg, "manifest": side,
            "bytes": os.path.getsize(pkg), "sha256": sha256(pkg),
            "files": len(files), "user_version": user_version,
            "integrity": integrity, "human_rows": rows,
            "kept": [f for f in mine if f not in pruned], "pruned": pruned,
            "secrets_checked": True}


def prune(out_dir: str, name: str, keep: int) -> tuple[list[str], list[str]]:
    """Delete this client's packages in `out_dir` beyond the newest `keep`
    (with their sidecar manifests): (all of this client's, the deleted).
    Ordered by (timestamp, -N): `...Z.tgz` is older than `...Z-2.tgz`, which
    a plain string sort gets wrong. Another client's package and any other
    file are never touched."""
    pat = re.compile(re.escape(name)
                     + r"-snapshot-(\d{8}T\d{6}Z)(?:-(\d+))?\.tgz")
    mine = sorted((f for f in os.listdir(out_dir) if pat.fullmatch(f)),
                  key=lambda f: (pat.fullmatch(f).group(1),
                                 int(pat.fullmatch(f).group(2) or 1)))
    pruned = mine[:-keep] if len(mine) > keep else []
    for f in pruned:
        os.remove(os.path.join(out_dir, f))
        try:
            os.remove(os.path.join(out_dir, f[:-4] + ".manifest.json"))
        except FileNotFoundError:
            pass
    return mine, pruned
