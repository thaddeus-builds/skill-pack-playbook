"""Contract files: the mark, the schema check, a file written once, a file read into raw.

A contract (contracts/README.md in the playbook) is a versioned file. Its first line
names it (`# ads.results/1`); the rest is one JSON document or, for the two contracts
that were in use before, a TSV (a header line, then one line per row). Its schema is
`contracts.d/<name>-<version>.schema.json`, a copy of the playbook's contracts/
(a test holds the two equal).

  * `write(kind, version, body, out)` renders the mark and the body, reads the result
    back through the check a reader makes, and only then writes it to `out`, once: the
    same bytes again are a no-op, other bytes under that name are refused
    (exchange_would_overwrite) and the file on disk is untouched. A document that does
    not fit its schema never reaches the disk. Without a hub there is only `out`
    (`add_out_arg` is the --out flag); the hub's exchange folder comes with the hub.
  * `read(path, kind, version, source)` refuses a file whose first line is another mark
    (exchange_mark_wrong) or another version (exchange_version_unknown), or whose body
    does not fit the schema (exchange_invalid, with the problems), and otherwise saves
    the bytes as they came into raw/<source>/ (kit.raw: raw only grows) and returns the
    Document. A file that is refused is not saved.
  * The check is the schema's keywords only (type, properties, required, items, enum,
    pattern, minLength, maxLength, minItems, maxItems, minimum, maximum, $ref into $defs).
    A field the schema does not name is not looked at: a consumer ignores what it does not
    know. The rules across rows and fields (`x-rules`) stay with the pack's own reader.
  * A JSON document is the object as written. A TSV document is a list of rows, each
    {column: value}: a `number` cell is a float, any other cell its text, a blank cell
    None (unknown, never 0). Columns the schema does not name are kept as text.

Stdlib only; the one thing it imports from the kit is raw, contract and messages (base).

Test: kit/tests/test_contracts.py.
"""

from __future__ import annotations

import dataclasses
import errno
import functools
import hashlib
import json
import math
import os
import re
import secrets
from pathlib import Path
from typing import Any

from kit import raw
from kit.contract import SkillPackError
from kit.messages import msg

SCHEMAS = Path(__file__).resolve().parent / "contracts.d"
MARK = re.compile(r"^#\s*([a-z][a-z0-9_.-]*)/([0-9]+)\s*$")
SHOWN = 8                       # problems an error names; the count says the rest


@dataclasses.dataclass(frozen=True)
class Document:
    kind: str
    version: int
    body: Any                    # JSON: the object; TSV: [{column: float | text | None}]
    columns: tuple[str, ...]     # TSV: the header; JSON: ()
    sha256: str
    raw: Path | None = None      # where read() saved it


def mark(kind: str, version: int) -> str:
    return f"# {kind}/{version}"


def add_out_arg(parser) -> None:
    """The `--out PATH` flag of a verb that writes a contract file."""
    parser.add_argument("--out", metavar="PATH",
                        help="write the contract file here; a file is written once")


@functools.lru_cache(maxsize=None)
def schema(kind: str, version: int) -> dict:
    """The schema of `kind`/`version`; exchange_schema_unknown when this kit has none."""
    try:
        return json.loads((SCHEMAS / f"{kind}-{version}.schema.json").read_text("utf-8"))
    except (OSError, ValueError):
        raise SkillPackError(msg(
            "exchange_schema_unknown",
            f"No schema for {kind}/{version}: the contract is not in this kit",
            kind=kind, version=version)) from None


# ---- the check ---------------------------------------------------------------------


def _is(value: Any, t: str) -> bool:
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if t == "integer":
        return isinstance(value, int) or (math.isfinite(value) and value == int(value))
    return t == "number" and math.isfinite(value)


def _rx(pattern: str) -> str:
    """ECMA's `$` ends the text; Python's also matches before a final newline."""
    return pattern[:-1] + r"\Z" if pattern.endswith("$") and not pattern.endswith("\\$") else pattern


def _resolve(node: dict, root: dict) -> dict:
    ref = node.get("$ref")
    return root.get("$defs", {}).get(ref.rsplit("/", 1)[-1], {}) if ref else node


def _check(node: dict, value: Any, root: dict, where: str, out: list[str]) -> None:
    """Append to `out` each way `value` breaks `node` (and the schema it $refs)."""
    if "$ref" in node:
        target = root.get("$defs", {}).get(node["$ref"].rsplit("/", 1)[-1])
        if target is None:
            out.append(f"{where}: the schema's {node['$ref']} is not defined")
        else:
            _check(target, value, root, where, out)
    types = node.get("type")
    if types is not None:
        types = [types] if isinstance(types, str) else types
        if not any(_is(value, t) for t in types):
            out.append(f"{where}: {json.dumps(value, ensure_ascii=False)[:40]} is not {' or '.join(types)}")
            return
    if "enum" in node and not any(value == e and type(value) is type(e) for e in node["enum"]):
        out.append(f"{where}: {json.dumps(value, ensure_ascii=False)[:40]} is not one of {', '.join(map(str, node['enum']))}")
    if isinstance(value, str):
        if "pattern" in node and not re.search(_rx(node["pattern"]), value):
            out.append(f"{where}: {value[:40]!r} is not in the form the schema asks for")
        if len(value) < node.get("minLength", 0):
            out.append(f"{where}: is shorter than {node['minLength']}")
        if len(value) > node.get("maxLength", len(value)):
            out.append(f"{where}: is longer than {node['maxLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < node.get("minimum", value):
            out.append(f"{where}: {value} is below {node['minimum']}")
        if value > node.get("maximum", value):
            out.append(f"{where}: {value} is above {node['maximum']}")
    if isinstance(value, dict):
        for key in node.get("required", ()):
            if key not in value:
                out.append(f"{where}.{key}: missing")
        for key, sub in node.get("properties", {}).items():
            if key in value:
                _check(sub, value[key], root, f"{where}.{key}", out)
    if isinstance(value, list):
        if len(value) < node.get("minItems", 0):
            out.append(f"{where}: has fewer than {node['minItems']} items")
        if len(value) > node.get("maxItems", len(value)):
            out.append(f"{where}: has more than {node['maxItems']} items")
        if isinstance(node.get("items"), dict):
            for i, item in enumerate(value):
                _check(node["items"], item, root, f"{where}[{i}]", out)


def problems(kind: str, version: int, body: Any) -> list[str]:
    """Why a JSON `body` does not fit the schema of `kind`/`version` ([] when it does)."""
    root = schema(kind, version)
    out: list[str] = []
    _check(root, body, root, "$", out)
    return out


# ---- parsing a file -----------------------------------------------------------------


def _invalid(name: str, kind: str, found: list[str]) -> SkillPackError:
    more = f" (and {len(found) - SHOWN} more)" if len(found) > SHOWN else ""
    return SkillPackError(msg(
        "exchange_invalid", f"{name} is not a valid {kind}: {'; '.join(found[:SHOWN])}{more}",
        file=name, kind=kind, detail="; ".join(found[:SHOWN]) + more))


def _tsv(root: dict, lines: list[tuple[int, str]]) -> tuple[tuple[str, ...], list[dict], list[str]]:
    found: list[str] = []
    if not lines:
        return (), [], ["no header line after the mark"]
    header = tuple(c.strip() for c in lines[0][1].split("\t"))
    if len(set(header)) != len(header):
        found.append("the header names a column twice")
    missing = [c for c in root.get("x-columns", ()) if c not in header]
    if missing:
        found.append(f"the header lacks {', '.join(missing)}")
    props, needed = root.get("properties", {}), set(root.get("required", ()))
    rows = []
    for n, line in lines[1:]:
        cells = line.split("\t")
        if len(cells) != len(header):
            found.append(f"line {n}: {len(cells)} cells, the header has {len(header)}")
            continue
        row: dict[str, Any] = {}
        for column, cell in zip(header, (c.strip() for c in cells)):
            sub = props.get(column)
            if cell == "":
                row[column] = None
                if column in needed:
                    found.append(f"line {n}: {column} is blank")
            elif sub is None:
                row[column] = cell
            elif _resolve(sub, root).get("type") == "number":
                try:
                    row[column] = float(cell)
                except ValueError:
                    row[column] = cell
                _check(sub, row[column], root, f"line {n}: {column}", found)
            else:
                row[column] = cell
                _check(sub, cell, root, f"line {n}: {column}", found)
        rows.append(row)
    return header, rows, found


def parse(data: bytes, kind: str, version: int, name: str = "the file") -> Document:
    """The Document in `data`, or the SkillPackError that says what is wrong with it."""
    root = schema(kind, version)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise SkillPackError(msg("exchange_unreadable", f"{name} cannot be read: not a UTF-8 text file",
                                 file=name, detail="not a UTF-8 text file")) from None
    first, _, rest = text.lstrip("﻿").partition("\n")
    m = MARK.match(first.strip())
    if not m or m.group(1) != kind:
        raise SkillPackError(msg(
            "exchange_mark_wrong", f"{name}: its first line is not {mark(kind, version)} ({first.strip()[:40]!r})",
            file=name, expected=mark(kind, version), found=first.strip()[:40]))
    if int(m.group(2)) != version:
        raise SkillPackError(msg(
            "exchange_version_unknown", f"{name} is {kind} version {m.group(2)}; this reader knows version {version} only",
            file=name, kind=kind, found=m.group(2), knows=version))
    sha = hashlib.sha256(data).hexdigest()
    if root.get("x-format") == "tsv":
        lines = [(n, x) for n, x in enumerate(rest.splitlines(), start=2) if x.strip()]
        columns, body, found = _tsv(root, lines)
    else:
        columns, found = (), []

        def no_constant(c):
            raise ValueError(f"{c} is not JSON")
        try:
            body = json.loads(rest, parse_constant=no_constant)
        except ValueError as e:
            body, found = None, [f"the body is not JSON ({str(e)[:60]})"]
        if not found:
            found = problems(kind, version, body)
    if found:
        raise _invalid(name, kind, found)
    return Document(kind, version, body, columns, sha)


# ---- writing and reading ------------------------------------------------------------


def _cell(column: str, v: Any, found: list[str]) -> str:
    s = "" if v is None else repr(v) if isinstance(v, float) else str(v)
    if isinstance(v, bool) or any(c in s for c in "\t\r\n"):
        found.append(f"{column} {s!r} is a flag or holds a tab or a line break; a cell is text or a decimal")
    return s


def render(kind: str, version: int, body: Any) -> bytes:
    """The bytes of the file for `body`: its mark, then the JSON or the TSV. Not yet checked."""
    root = schema(kind, version)
    if root.get("x-format") != "tsv":
        try:
            doc = json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as e:
            raise _invalid("the document", kind, [f"not JSON ({str(e)[:60]})"]) from None
        return f"{mark(kind, version)}\n{doc}\n".encode("utf-8")
    props, base = root.get("properties", {}), list(root.get("x-columns", ()))
    rows = list(body) if isinstance(body, (list, tuple)) else []
    if not rows or not all(isinstance(r, dict) for r in rows):
        raise _invalid("the document", kind, ["a TSV contract takes a list of rows, each a dict"])
    extra = [c for c in props if c not in base and any(r.get(c) not in (None, "") for r in rows)]
    found = [f"{c} is not a column of the schema" for c in sorted({k for r in rows for k in r} - set(props))]
    cols = base + extra
    lines = ["\t".join(cols)] + ["\t".join(_cell(c, r.get(c), found) for c in cols) for r in rows]
    if found:
        raise _invalid("the document", kind, found)
    return (mark(kind, version) + "\n" + "\n".join(lines) + "\n").encode("utf-8")


def _same(path: Path, data: bytes) -> bool:
    try:
        return path.read_bytes() == data
    except OSError:
        return False


def _claim(path: Path, data: bytes) -> None:
    """Write `data` to `path` if the name is free (or already holds these bytes). Whole or not at all."""
    def refuse():
        return SkillPackError(msg(
            "exchange_would_overwrite",
            f"{path} already holds different bytes; a contract file is written once and never replaced "
            f"— write the new one under a new name. Nothing was written", path=str(path)))
    if path.exists():
        if _same(path, data):
            return
        raise refuse()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    try:
        with open(tmp, "xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, path)                  # claims the name, or fails if it is taken
        except FileExistsError:
            if not _same(path, data):
                raise refuse() from None
        except OSError as e:
            if e.errno not in (errno.EPERM, errno.ENOTSUP, errno.EXDEV, errno.EMLINK, errno.EOPNOTSUPP):
                raise
            if path.exists():                   # no hard links here: best effort
                if not _same(path, data):
                    raise refuse() from None
            else:
                os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass


def write(kind: str, version: int, body: Any, out: Path | str) -> Path:
    """Write `body` as the contract file `out`, once. Checked as a reader would check it before a byte is written."""
    out = Path(out).expanduser()
    data = render(kind, version, body)
    parse(data, kind, version, out.name)
    _claim(out, data)
    return out


def read(path: Path | str, kind: str, version: int, source: str) -> Document:
    """The contract file `path`, checked, and saved as it came into raw/<source>/ (the name carries its hash)."""
    path = Path(path).expanduser()
    try:
        data = path.read_bytes()
    except OSError as e:
        raise SkillPackError(msg("exchange_unreadable", f"{path.name} cannot be read: {e.strerror or 'unreadable'}",
                                 file=path.name, detail=e.strerror or "unreadable")) from None
    doc = parse(data, kind, version, path.name)
    ext = "tsv" if schema(kind, version).get("x-format") == "tsv" else "json"
    saved = raw.save(source, f"{kind}-{version}.{doc.sha256[:12]}.{ext}", data)
    return dataclasses.replace(doc, raw=saved)
