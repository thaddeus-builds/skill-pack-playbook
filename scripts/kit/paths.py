"""Where a skill pack's data lands: the one resolver for the data dir and DB.

Every verb, ingest, `kit.db.connect()` and `doctor` read their locations
from here, so what doctor reports is what the scripts use.

  * `<P>_DATA_DIR` is required and never defaults to the cwd: agent shells
    reset it, and a wrong one lands credentials and client data in the
    wrong place. Unset -> SkillPackError(data_dir_unset), whose `next` names
    the variable. A relative value is cwd-relative too, so it is refused
    the same way (data_dir_not_absolute). `~` is expanded.
  * `<P>_DB` overrides the DB file; a relative one sits under the data
    dir. Default: `<DATA_DIR>/<db_file>`.
  * `<P>_RAW` overrides the raw store's root (`raw_dir()`, which `kit.raw`
    saves under as `<root>/<source>/<name>`); a relative one sits under the
    data dir. Default: `<DATA_DIR>/raw`. `resolve()` does not list it (its
    output for a pack that never sets `<P>_RAW` stays as it was); doctor
    reports it only when it is set.
  * `inside_repo(p)`: doctor warns when client data lives in the skill pack
    checkout (it would ship in a release or leak into a commit).

Process env only, read at call time (the CLI loads the env chain into
the process env once, at the entry point).

Test: kit/tests/test_paths.py.
"""

from __future__ import annotations

import os
from pathlib import Path

from kit.config import config
from kit.contract import SkillPackError
from kit.messages import msg

RAW = "raw"      # the raw store's folder under the data dir (kit.raw.RAW)


def data_dir() -> Path:
    """The client's data directory (absolute), or SkillPackError."""
    cfg = config()
    var = cfg.env("DATA_DIR")
    value = os.environ.get(var, "").strip()
    if not value:
        raise SkillPackError(
            msg("data_dir_unset",
                f"{var} is not set — set it to the directory that holds this "
                f"client's .env and database. The current directory is never "
                f"used as a default: agent shells reset it, and a wrong one "
                f"lands credentials and data in the wrong place", var=var),
            [f"export {var}=/absolute/path/to/client-data",
             f"{cfg.cli} doctor"])
    p = Path(value).expanduser()
    if not p.is_absolute():
        raise SkillPackError(
            msg("data_dir_not_absolute",
                f"{var}={value} is a relative path — set it to an absolute "
                f"path; the current directory is never used",
                var=var, value=value),
            [f"export {var}=/absolute/path/to/client-data"])
    return p


def db_path() -> Path:
    """`<P>_DB` (relative = under the data dir), else <DATA_DIR>/<db_file>."""
    cfg = config()
    override = os.environ.get(cfg.env("DB"), "").strip()
    if override:
        p = Path(override).expanduser()
        return p if p.is_absolute() else data_dir() / p
    return data_dir() / cfg.db_file


def raw_dir() -> Path:
    """`<P>_RAW` (relative = under the data dir), else <DATA_DIR>/raw."""
    override = os.environ.get(config().env("RAW"), "").strip()
    if override:
        p = Path(override).expanduser()
        return p if p.is_absolute() else data_dir() / p
    return data_dir() / RAW


def resolve() -> dict[str, str | None]:
    """{env var: resolved path or None} for doctor; never raises on unset."""
    cfg = config()
    out: dict[str, str | None] = {}
    for var, fn in ((cfg.env("DATA_DIR"), data_dir),
                    (cfg.env("DB"), db_path)):
        try:
            out[var] = str(fn())
        except SkillPackError:
            out[var] = None
    return out


def inside_repo(p: Path | str) -> bool:
    """True when `p` is the skill pack checkout or anything inside it."""
    root = config().root.resolve()
    q = Path(p).expanduser().resolve()
    return q == root or root in q.parents
