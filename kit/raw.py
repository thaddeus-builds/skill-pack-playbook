"""The append-only raw store: raw only grows.

Everything a skill pack pulls or imports lands here first, under
`<DATA_DIR>/raw/<source>/<name>` (the root is `kit.paths.raw_dir()`: `<P>_RAW`
when set), and ingest rebuilds the DB from it. The
rule this module holds is the lesson of a rebuild that shrank 3,072 rows
to 329: a raw file is written once and never replaced, so the DB can
always be rebuilt from everything ever pulled.

  * write-once: saving the same name with identical bytes is a no-op;
    with different bytes it is SkillPackError(raw_would_overwrite) and the
    file on disk is untouched;
  * atomic and race-safe: the bytes go to a temp sibling, then a hard link
    claims the name (it fails if the name exists, so two concurrent writers
    can never both win); the temp is removed either way. A filesystem
    without hard links falls back to an exists-check + os.replace;
  * `import_file` copies an external export (a CSV the owner downloaded…)
    in under a content-hash name `<stem>.<sha256[:12]><suffix>`, so
    importing the same file twice leaves one raw file;
  * names are single path components: no separator, no leading dot (temp
    files start with one and `listing()` never shows them);
  * a client hub's exchange folder holds the same discipline between skill
    packs: `exchange_write` puts one document at
    `<hub>/exchange/<contract>/<producer>/<date>.json` and refuses a name
    that is taken, identical bytes or not; `exchange_list` lists a
    contract's documents by producer and date. A reader imports what it
    reads into its own raw. The folder and the names are all this module
    knows: what a contract carries is not its concern.

Test: kit/tests/test_raw.py.
"""

from __future__ import annotations

import datetime
import errno
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, NamedTuple

from kit import paths
from kit.contract import SkillPackError
from kit.messages import msg

RAW = paths.RAW


def _plain(name: str) -> str:
    if (not isinstance(name, str) or not name or name in (".", "..")
            or name.startswith(".") or "/" in name or "\\" in name
            or "\0" in name):
        raise SkillPackError(msg(
            "raw_bad_name",
            f"{name!r} is not a plain file or folder name (no path separator,"
            f" no leading dot, not empty)", name=str(name)))
    return name


def raw_dir(source: str) -> Path:
    """<paths.raw_dir()>/<source>/ (created); <DATA_DIR>/raw unless <P>_RAW is set."""
    d = paths.raw_dir() / _plain(source)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _same(path: Path, data: bytes) -> bool:
    try:
        return path.read_bytes() == data
    except OSError:
        return False


def _refuse(source: str, name: str) -> SkillPackError:
    return SkillPackError(msg(
        "raw_would_overwrite",
        f"raw/{source}/{name} already holds different bytes; a raw file is "
        f"written once and never replaced — save the new data under a new "
        f"name. Nothing was written", source=source, name=name))


def _claim(path: Path, data: bytes) -> bool:
    """Write `data` to a temp sibling and claim `path` with it. False when
    the name is taken (also when a concurrent writer won it): nothing of
    ours is left behind and the file at `path` is untouched."""
    tmp = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    try:
        with open(tmp, "xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, path)          # claims the name, or fails if taken
        except FileExistsError:
            return False
        except OSError as e:
            if e.errno not in (errno.EPERM, errno.ENOTSUP, errno.EXDEV,
                               errno.EMLINK, errno.EOPNOTSUPP):
                raise
            if path.exists():           # no hard links here: best effort
                return False
            os.replace(tmp, path)
        return True
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass


def save(source: str, name: str, data: bytes) -> Path:
    """Write `data` as raw/<source>/<name> once; identical re-save = no-op,
    different bytes = raw_would_overwrite. Returns the path."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"raw.save takes bytes, got {type(data).__name__}")
    data = bytes(data)
    path = raw_dir(source) / _plain(name)
    if path.exists() or not _claim(path, data):
        if _same(path, data):
            return path
        raise _refuse(source, name)
    return path


def canonical_json(obj: Any) -> bytes:
    """The bytes save_json writes: sorted keys, compact, utf-8. Equal
    objects give equal bytes, so a re-save of the same data is a no-op."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def save_json(source: str, name: str, obj: Any) -> Path:
    """save() of canonical_json(obj)."""
    return save(source, name, canonical_json(obj))


def listing(source: str) -> list[Path]:
    """The raw files of `source`, sorted by name (temp files never shown)."""
    return sorted(p for p in raw_dir(source).iterdir()
                  if p.is_file() and not p.name.startswith("."))


def import_file(source: str, src: Path | str) -> Path:
    """Copy an external file in under `<stem>.<sha256[:12]><suffix>`;
    importing the same file twice leaves one raw file."""
    src = Path(src).expanduser()
    try:
        if not src.is_file():
            raise OSError
        data = src.read_bytes()
    except OSError:
        raise SkillPackError(msg(
            "raw_import_missing",
            f"Nothing to import: {src} is not a readable file",
            path=str(src))) from None
    digest = hashlib.sha256(data).hexdigest()[:12]
    stem = src.stem.lstrip(".") or "import"
    return save(source, f"{stem}.{digest}{src.suffix}", data)


# ---- the client hub's exchange folder -----------------------------------------

EXCHANGE = "exchange"
CONTRACT_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*/[1-9][0-9]*")
PRODUCER_RE = re.compile(r"[a-z][a-z0-9_-]*")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class Document(NamedTuple):
    """One file in the exchange: who wrote which contract, on which day."""
    contract: str
    producer: str
    date: str
    path: Path


def _exchange(hub: Path | str) -> Path:
    """<hub>/exchange, which must exist (scaffold/new_hub.py makes it)."""
    folder = Path(hub).expanduser().resolve() / EXCHANGE
    if not folder.is_dir():
        raise SkillPackError(msg(
            "exchange_no_folder",
            f"{folder} is not there: this hub was made before the exchange "
            f"folder. Make it (mkdir) in the hub, then write again. Nothing "
            f"was written", folder=str(folder)))
    return folder


def _shaped(what: str, value: Any, pattern: re.Pattern, shape: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise SkillPackError(msg(
            "exchange_bad_name",
            f"{what} `{value}` is not {shape}. Nothing was written",
            what=what, value=str(value), shape=shape))
    return value


def _date(value: datetime.date | str) -> str:
    text = value.isoformat() if isinstance(value, datetime.date) else value
    _shaped("date", text, DATE_RE, "a day as YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        raise SkillPackError(msg(
            "exchange_bad_name",
            f"date `{text}` is not a real day. Nothing was written",
            what="date", value=text, shape="a real day")) from None
    return text


def exchange_write(hub: Path | str, contract: str, producer: str,
                   date: datetime.date | str, data: bytes) -> Path:
    """Write `data` as `<hub>/exchange/<contract>/<producer>/<date>.json`,
    once. `contract` is `name/version` (`ads.results/1`), `producer` the
    writing skill pack's cli word, `date` the day (YYYY-MM-DD). A name that
    is taken is `exchange_exists` whatever the bytes are, also when two
    writers race: the first stays, the second writes nothing. The folders
    under `exchange/` are made as needed; `exchange/` itself must be there.
    Returns the path."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"exchange_write takes bytes, got {type(data).__name__}")
    folder = _exchange(hub)
    _shaped("contract", contract, CONTRACT_RE, "a name and a version, like ads.results/1")
    _shaped("producer", producer, PRODUCER_RE, "a cli word: lower-case letters, digits, - and _")
    day = _date(date)
    target = folder / contract / producer
    path = target / f"{day}.json"

    def taken() -> SkillPackError:
        return SkillPackError(msg(
            "exchange_exists",
            f"exchange/{contract}/{producer}/{day}.json is already there; an "
            f"exchange document is written once and never replaced. Nothing "
            f"was written", contract=contract, producer=producer, date=day,
            path=str(path)))
    if path.exists():
        raise taken()
    target.mkdir(parents=True, exist_ok=True)
    if not _claim(path, bytes(data)):
        raise taken()
    return path


def _documents(contract_dir: Path, contract: str) -> list[Document]:
    out = []
    for prod in sorted(contract_dir.iterdir()):
        if not (prod.is_dir() and PRODUCER_RE.fullmatch(prod.name)):
            continue
        out += [Document(contract, prod.name, f.stem, f)
                for f in sorted(prod.iterdir())
                if f.is_file() and f.suffix == ".json"
                and DATE_RE.fullmatch(f.stem)]
    return out


def exchange_list(hub: Path | str, contract: str) -> list[Document]:
    """Every document of `contract` in the hub's exchange, sorted by
    producer, then date (oldest first). A contract nobody wrote yet is an
    empty list. Files that do not fit the layout, and temp files of a write
    in flight, are not listed."""
    folder = _exchange(hub)
    _shaped("contract", contract, CONTRACT_RE, "a name and a version, like ads.results/1")
    contract_dir = folder / contract
    return _documents(contract_dir, contract) if contract_dir.is_dir() else []


def exchange_scan(hub: Path | str) -> tuple[list[Document], list[str]]:
    """Everything under `<hub>/exchange/`: the documents of every contract
    (as exchange_list gives them) and the paths, relative to it, of what
    does not belong (a file out of place, a folder not named for a contract
    or a producer, a name that is not a day). The folder's README.md and
    dotfiles (`.gitkeep`, a write in flight) are neither. What doctor reads."""
    folder = _exchange(hub)
    docs: list[Document] = []
    strays: list[str] = []
    for top in sorted(folder.iterdir()):
        if top.name.startswith(".") or (top.is_file() and top.name == "README.md"):
            continue
        if not top.is_dir():
            strays.append(top.name)
            continue
        for ver in sorted(top.iterdir()):
            contract = f"{top.name}/{ver.name}"
            if ver.name.startswith("."):
                continue
            if not (ver.is_dir() and CONTRACT_RE.fullmatch(contract)):
                strays.append(contract)
                continue
            docs += _documents(ver, contract)
            for prod in sorted(ver.iterdir()):
                if prod.name.startswith("."):
                    continue
                if not (prod.is_dir() and PRODUCER_RE.fullmatch(prod.name)):
                    strays.append(f"{contract}/{prod.name}")
                    continue
                strays += [f"{contract}/{prod.name}/{f.name}"
                           for f in sorted(prod.iterdir())
                           if not f.name.startswith(".")
                           and not (f.is_file() and f.suffix == ".json"
                                    and DATE_RE.fullmatch(f.stem))]
    return docs, strays
