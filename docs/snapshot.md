# Snapshot: pack a client's workspace so it can be restored

A skill pack keeps a client's state in a data dir: a SQLite file with the human tables, raw files, reports. If the disk goes, so does the client. `kit/snapshot.py` (pack `ops`, `[kit] packs = ["ops"]`) packs one client's workspace into one `<client>-snapshot-<UTC>[-N].tgz` with a `<same>.manifest.json` beside it. The pack adds a verb that calls `snapshot.make()`; the kit writes no verb and no schedule.

*Seen once:* the SEO skill pack built it first (its S71, `seo db snapshot`, 2026-10) and is the worked example. This module is that code with the SEO names taken out.

## What you give it

```python
snapshot.make(data_dir=..., db_path=..., out_dir=..., keep=7,
              pack_version="1.4.0", schema_version=29,
              human_export=my_export,            # conn -> (text, {table: rows}); None = no export
              exclude=[".env", ".env.*", "*.pem", "*.key", ".DS_Store", ".git"],
              env_files=["~/.vendor.env"])       # more files whose secret values must not leak
```

- **`exclude` is the pack's own registry** (a TSV the pack reads), fnmatch on the relative posix path or its last name. The kit's default is empty: nothing is left out except the live database and its `-wal`, `-shm`, `-journal` files, which are replaced by the backup copy. A pack that keeps credentials in the workspace lists them.
- **`env_prefixes`** (default: the bound skill pack's `<ENV_PREFIX>_`): process-env variables with these prefixes whose names look like a secret count as secret values. Add token shapes the kit does not know with `extra_shapes`.
- **`client_marker` / `client_dirs`** (default `client.env`, `content`, `reports`): when the workspace sits in a client folder holding that marker, those folders of the client folder are packed too.
- **`now`** is injected for tests; the default is `kit.dates.now()`.

It raises `SnapshotError` (a `SkillPackError`, so a verb that renders failures through `kit.contract.fail` exits 2 with a coded document): `snapshot_out_inside`, `snapshot_keep_invalid`, `snapshot_integrity`, `snapshot_secret_found`, and the base `no_db`. Every refusal happens before anything is written.

## What it guarantees

1. The database is copied with SQLite's backup API from a read-only connection (a file copy mid-write is torn), then `PRAGMA integrity_check` and `user_version` are read from the copy.
2. Everything about to be packed is scanned for the secret values of the env files and the process env, and for token shapes. One hit: nothing is written, not even a temporary folder, and the error names the files, never the secret.
3. `MANIFEST.json` holds the sha256 and size of every file, the pack and schema versions, the integrity result and the human-table row counts. The sidecar adds the package's own sha256.
4. The package and sidecar are written atomically. The workspace is only read (a reader of a WAL database touches its `-shm` index, which holds no data). `out_dir` must be outside the workspace.
5. `keep` prunes only this client's packages in `out_dir`, ordered by (timestamp, `-N`): `...Z-2.tgz` is newer than `...Z.tgz`. Another client's package, or any other file, is never touched.

## The operator's step

A package is a file in a folder on the same machine. **Keeping a copy elsewhere is the operator's step** (`rclone`, `rsync`, a disk): the kit holds no credentials for it and uploads nothing. Schedule the verb and the copy together, and restore on a fresh machine by unpacking the package, putting `workspace/` where the data dir is, and running the pack's doctor.

Test: [kit/tests/test_snapshot.py](../kit/tests/test_snapshot.py).
