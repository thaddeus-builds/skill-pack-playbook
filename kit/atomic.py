"""Atomic writes for source-of-truth files.

A raw puller output IS the source of truth (ingest reads it back), so a
half-written file must never be observable: a crash, a full disk or a
SIGKILL mid-write would otherwise leave a truncated file that the next
ingest reads as real data. Write a temp sibling, flush it to disk
(fsync, so a power loss cannot leave a renamed-but-empty file), then
`os.replace` it over the target (atomic on one filesystem). On any error
the temp file is removed and the target is untouched; a temp left by a
killed writer is never in the way of the next write.

The folder is not created unless asked (`makedirs=True`): a typo in a path
must not build a tree. A pack that writes into a folder that may not exist
yet (a raw-data tree by source and date) passes it instead of a `makedirs`
line before every call.

The temp name is unique per call (pid + random), so two writers of the
same path never share a temp file; it is created with the process umask
like a plain open() would.

Stdlib-only, no config: pullers import it.

Test: kit/tests/test_atomic.py.
"""

from __future__ import annotations

import json
import os
import secrets
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Iterator


def _tmp_for(path: str | os.PathLike) -> str:
    return f"{os.fspath(path)}.{os.getpid()}.{secrets.token_hex(4)}.tmp"


@contextmanager
def _open_tmp(path: str | os.PathLike, mode: str, makedirs: bool = False) -> Iterator[IO]:
    if makedirs:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = _tmp_for(path)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with (open(fd, mode, encoding="utf-8") if "b" not in mode
              else open(fd, mode)) as f:
            yield f
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass
        raise
    os.replace(tmp, path)


@contextmanager
def open_atomic(path: str | os.PathLike, *, makedirs: bool = False) -> Iterator[IO[str]]:
    """Text-write `path` (utf-8) so a reader never sees a partial file.

    `makedirs=True` creates the missing parent folders first."""
    with _open_tmp(path, "w", makedirs) as f:
        yield f


def write_json_atomic(path: str | os.PathLike, obj: Any, *,
                      indent: int | None = None, makedirs: bool = False) -> None:
    """Serialize `obj` to `path` (ensure_ascii=False) atomically."""
    with open_atomic(path, makedirs=makedirs) as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)


def write_text_atomic(path: str | os.PathLike, text: str, *,
                      makedirs: bool = False) -> None:
    """Write `text` (utf-8) to `path` atomically."""
    with open_atomic(path, makedirs=makedirs) as f:
        f.write(text)


def write_bytes_atomic(path: str | os.PathLike, data: bytes, *,
                       makedirs: bool = False) -> None:
    """Write `data` to `path` atomically."""
    with _open_tmp(path, "wb", makedirs) as f:
        f.write(data)


def is_temp(path: str | os.PathLike) -> bool:
    """True for a temp sibling this module writes (a crash can leave one)."""
    return Path(path).name.endswith(".tmp")
