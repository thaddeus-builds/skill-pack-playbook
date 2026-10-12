"""The ssot index — the one list of registries and owner files — and the
owner-file lint.

`check_index(root)` returns every problem of these rules:

  * the index (`[ssot].index`, default <ssot dir>/index.tsv) has exactly
    the configured header (default `file owner reader test id_column
    purpose`); one row per file; every <ssot dir>/**.tsv has a row (a
    message-code fragment, <ssot dir>/message_codes.d/*.tsv, is covered by
    the `[ssot].message_codes` row);
  * each row's file exists (`path:SYMBOL` = a code-held registry: the file
    assigns SYMBOL); the owner kind is owner | agent | registry; every
    reader and test path exists and a test is named; a TSV's id column
    (`a+b` for a compound key) is one of its header columns; the purpose
    is set;
  * every ssot TSV has one column count (a stray tab is caught here, not
    by an agent reading a shifted column); ids are unique and non-empty;
  * an owner file (kind owner) holds business meaning only: no issue ref
    `#12`, no `<cli> <verb>` command (`[guards.ssot].cli_verbs` = the verb
    words, when the CLI word is also a business word), no `--flag`, no
    file name (`x.py`, `x.tsv`, …) or `_lib`, no table name (the kit's
    human tables and `[guards.ssot].table_prefixes`), no number written
    right after a threshold name (the number lives in
    `[ssot].constants`). Engineering detail goes to the same id's
    `.agent.tsv` row. `held` lists the owner cells still allowed to fail;
    an entry that no longer fails is itself a problem, so the list only
    shrinks;
  * an `X.agent.tsv` whose owner sibling `X.tsv` exists carries the same
    ids (agent rows whose status is `proposed` or `asked` aside: the owner
    has not adopted them yet; an `asked` row's `ask` reference is the
    trail check's, kit.testing.suites.trail_problems); an agent file with
    no owner sibling is agent-only;
  * ids are never deleted: every id an owner or agent file held at git
    HEAD is still there (retire a row, never delete or renumber it);
    skipped per file when git or the file at HEAD is absent;
  * no ssot text uses a banned term (`[guards.ssot].banned_terms`,
    {banned: preferred}).

Parameters, all optional, in harness.toml `[guards.ssot]`:
index_columns {file, owner, reader, test, id, purpose -> header name},
owner_kinds, cli_verbs, none ("—"), table_prefixes, file_exts, held
[[file, id, column]…], banned_terms, status_column ("status"),
proposed_statuses (["proposed", "asked"]: the statuses of a row the
owner has not adopted yet); for check_writes, write_code (["."]),
write_skip ({folder: reason}; the vendored <scripts_dir>/kit is
always left out, with no row), writers ({path: reason}), write_calls
([]).

Deviations (SPEC §guards): these parameters live in [guards.ssot], not
[ssot], because kit.config requires every [ssot] value to be a path
string; `[ssot].index` may name the index. "Lists every file in ssot/"
is every ssot TSV (as the reference did): README.md and other prose are
not registries.

A reader cell of — (or empty) marks a planning file: kit.guards.release
keeps it out of a release. The reader column, not the owner kind,
decides what ships.

ssot/ is the builder's (docs/rules.md, "Registries: one place per
value"): what a client sets or decides through its agent goes to that
client's own database, never into an edit of ssot/. `check_writes(root)`
returns, as `path:line` and never what is written, every call in the
harness's code that writes under the ssot dir, by AST: Path
write_text / write_bytes / touch / unlink / mkdir / rmdir / rename /
replace, `open` (builtin, Path, io, codecs, gzip, bz2, lzma, os) with a
write mode (a mode that is not a literal counts as one), os.replace /
rename / remove / unlink / mkdir / makedirs / link / symlink / truncate,
shutil.copy / copy2 / copyfile / copytree / copymode / copystat (the
destination) / move / rmtree, kit.atomic's open_atomic /
write_json_atomic / write_bytes_atomic, and the harness's own helpers
named in `write_calls` (the path is their first argument). A path is
under the ssot dir when its expression holds a string with the dir as
path segments ("ssot", "ssot/x.tsv", f"{root}/ssot/x"), an identifier
with the word `ssot` (SSOT, cfg.ssot, ssot_dir) unless the name is bound
only to data (a call that builds no path and reads one under ssot:
`ssot_rows = read_tsv(SSOT / name)`),
or a name bound to such an expression: in the same scope (a name bound
only by plain assignments in the scope's own statements holds what the
last one above the line put in it; under a branch, loop, try, augmented
assignment or comprehension any binding counts), an enclosing one, a
class body or a method (`self.p`, keyed by the class and matched in any
class linked to it by inheritance in the module, a base, a subclass or
a mixin beside it; in any class when a base is out of sight; any other
attribute by its text), or another
scanned module's top level, imported by name (`from m import NAME`, a
re-export followed) or reached through the module (`m.NAME`). A path goes
through `/`, f-strings, IfExp and the calls that build or list paths
(PATH_CALLS, PATH_METHODS: Path(), os.path.join, os.walk's dirpath, str,
sorted,
.with_suffix, .glob, …); any other call's value is data, so what is read
from an ssot file is not a path under it, and a path's words (`.name`,
`.stem`, `.suffix`) are not a path either. os.open writes unless its
flags are the literal 0 or O_RDONLY with no writing flag. Reading ssot
is never a hit, nor copying from it, nor writing a row's own file
elsewhere. A path the code builds out of sight (a parameter, a
function's return) is not seen: the rule catches the plain case, not
every case.

The code is every .py under `write_code` (default: the whole harness;
each entry must find code), never the vendored kit, a test (a `tests`
folder, test_*.py, *_test.py, conftest.py), a hidden folder,
__pycache__, node_modules, a virtualenv (a folder with pyvenv.cfg) or
site-packages. `write_skip` = {folder: reason} leaves out more, each row
with its reason, a row whose folder is gone being a problem. `writers` =
{path or folder: reason} is the builder's own tools that may write ssot
(a registry editor run in the builder's checkout): each needs its
reason, and an entry that writes nothing under ssot any more is itself a
problem, so the list stays true. A file that does not parse (read as
bytes, so a BOM or coding cookie holds) or is too deeply nested to read
is a problem: what the rule cannot read is never a pass.
`writes_self_test()` scans a planted module with every write form and
the reads beside them, and each form the rule once read wrong.

Test: kit/tests/test_guards.py.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from kit.config import HarnessConfig
from kit.guards import (NONE, SKIP_DIRS, harness, paths, read, report,
                        section, strs, tsv)

ORDER = ("file", "owner", "reader", "test", "id", "purpose")
COLUMNS = {"file": "file", "owner": "owner", "reader": "reader",
           "test": "test", "id": "id_column", "purpose": "purpose"}
KINDS = ("owner", "agent", "registry")
# The kit's own human tables with a compound name (a bare English word such
# as `decisions` is prose, not a table name).
HUMAN_TABLES = ("client_facts", "client_facts_history", "decisions_history",
                "action_queue", "action_effects")
FILE_EXTS = ("py", "tsv", "json", "toml", "sh")
# An agent row the owner has not adopted yet: the agent's idea, or one sent
# to the console and not answered (templates/ssot/README.md, the trail).
PROPOSED = ("proposed", "asked")


@dataclass(frozen=True)
class Rules:
    """Everything the ssot guard reads from one harness.toml."""
    root: Path
    ssot_dir: str
    index: str
    columns: dict
    kinds: tuple[str, ...]
    none: str
    cli: str
    cli_verbs: tuple[str, ...]
    table_prefixes: tuple[str, ...]
    file_exts: tuple[str, ...]
    held: frozenset
    banned: dict
    status_column: str
    proposed: tuple[str, ...]
    constants: str | None
    message_codes: str | None = None


def rules(root: Path | str | None = None,
          cfg: HarnessConfig | None = None) -> Rules:
    cfg = cfg or harness(root)
    g = section(cfg, "guards", "ssot")
    ssot_dir = cfg.ssot.get("dir", "ssot").strip("/")
    constants = cfg.ssot.get("constants")
    return Rules(
        root=cfg.root, ssot_dir=ssot_dir,
        index=cfg.ssot.get("index", f"{ssot_dir}/index.tsv"),
        columns={**COLUMNS, **dict(g.get("index_columns", {}))},
        kinds=tuple(g.get("owner_kinds", KINDS)),
        none=str(g.get("none", NONE)), cli=cfg.cli,
        cli_verbs=tuple(g.get("cli_verbs", ())),
        table_prefixes=tuple(g.get("table_prefixes", ())),
        file_exts=tuple(g.get("file_exts", FILE_EXTS)),
        held=frozenset(tuple(h) for h in g.get("held", ())),
        banned=dict(g.get("banned_terms", {})),
        status_column=str(g.get("status_column", "status")),
        proposed=tuple(g.get("proposed_statuses", PROPOSED)),
        constants=constants,
        message_codes=(cfg.ssot.get("message_codes") or "").strip("/")
        or None)


def _is_none(cell: str, r: Rules) -> bool:
    return cell.strip() in ("", r.none, NONE)


def index_rows(r: Rules) -> tuple[list[str], list[dict[str, str]]]:
    """(header, rows keyed by the logical names file/owner/reader/test/id/
    purpose); ([], []) when there is no index."""
    path = r.root / r.index
    if not path.is_file():
        return [], []
    table = tsv(path)
    if not table:
        return [], []
    head = [c.strip() for c in table[0]]
    pos = {k: head.index(r.columns[k]) for k in ORDER
           if r.columns[k] in head}
    rows = []
    for row in table[1:]:
        cells = [c.strip() for c in row]
        rows.append({k: cells[i] if i < len(cells) else ""
                     for k, i in pos.items()})
    return head, rows


def planning_files(r: Rules) -> set[str]:
    """Index rows with no reader: planning files, never shipped."""
    return {row["file"] for row in index_rows(r)[1]
            if _is_none(row.get("reader", ""), r)}


def read_files(r: Rules) -> set[str]:
    """Files the index names a reader for (a `path:SYMBOL` row = its path):
    they ship."""
    return {row["file"].partition(":")[0] for row in index_rows(r)[1]
            if not _is_none(row.get("reader", ""), r)}


def owner_files(r: Rules) -> set[str]:
    return {row["file"] for row in index_rows(r)[1]
            if row.get("owner") == "owner"}


def thresholds(r: Rules) -> set[str]:
    """The registered threshold names: the first column of [ssot].constants."""
    if not r.constants or not (r.root / r.constants).is_file():
        return set()
    return {row[0].strip() for row in tsv(r.root / r.constants)[1:]
            if row and row[0].strip()}


def lint(text: str, r: Rules, names: set[str] | None = None) -> list[str]:
    """The engineering tokens an owner cell must not carry."""
    names = thresholds(r) if names is None else names
    hits = []
    hits += re.findall(r"#\d+", text)
    verb = ("|".join(map(re.escape, r.cli_verbs)) if r.cli_verbs
            else r"[a-z][\w-]*")
    hits += re.findall(rf"\b{re.escape(r.cli)}(?:\.py)?[ \t]+(?:{verb})\b",
                       text)
    hits += re.findall(r"(?<![\w-])--[a-z][\w-]*", text)
    if r.file_exts:
        exts = "|".join(map(re.escape, r.file_exts))
        hits += re.findall(rf"\w*\.(?:{exts})\b", text)
    hits += re.findall(r"\b_lib\b", text)
    if r.table_prefixes:
        pre = "|".join(map(re.escape, r.table_prefixes))
        hits += [t for t in re.findall(rf"\b(?:{pre})[a-z0-9_]+", text)
                 if t not in names]
    hits += [t for t in HUMAN_TABLES if re.search(rf"\b{t}\b", text)]
    for name in sorted(names):
        hits += re.findall(
            rf"\b{re.escape(name)}\s*[(（]?\s*[=:：]?\s*\d[\d.,]*", text)
    return hits


def lint_file(rel: str, r: Rules, held: frozenset | set = frozenset()
              ) -> tuple[dict[str, list[str]], set]:
    """({"<file> <row id> <column>": hits} outside `held`, the `held`
    (file, id, column) cells that were hit) for the owner file `rel`,
    every column but the id."""
    names = thresholds(r)
    table = tsv(r.root / rel)
    flagged: dict[str, list[str]] = {}
    held_hit: set = set()
    if not table:
        return flagged, held_hit
    for row in table[1:]:
        for col, cell in zip(table[0][1:], row[1:]):
            hits = lint(cell, r, names)
            if not hits:
                continue
            key = (rel, row[0].strip(), col.strip())
            if key in held:
                held_hit.add(key)
            else:
                flagged[" ".join(key)] = hits
    return flagged, held_hit


def _ids(table: list[list[str]], id_cols: list[str]) -> list[tuple] | None:
    """The id of every row (a tuple over the id columns), None when a
    column is missing from the header."""
    head = [c.strip() for c in table[0]]
    if not all(c in head for c in id_cols):
        return None
    pos = [head.index(c) for c in id_cols]
    return [tuple(row[i].strip() if i < len(row) else "" for i in pos)
            for row in table[1:]]


def _show(ids: set[tuple]) -> list[str]:
    return sorted("+".join(i) for i in ids)


def _head_table(root: Path, rel: str) -> list[list[str]] | None:
    """The TSV as git HEAD holds it; None without git, a HEAD or the file."""
    try:
        res = subprocess.run(["git", "-C", str(root), "show", f"HEAD:./{rel}"],
                             capture_output=True, text=True,
                             stdin=subprocess.DEVNULL)
    except OSError:
        return None
    if res.returncode != 0:
        return None
    rows = [line.rstrip("\r").split("\t") for line in res.stdout.split("\n")]
    rows = [row for row in rows if any(c.strip() for c in row)]
    return rows or None


def check_index(root: Path | str | None = None) -> list[str]:
    """Every problem of the ssot index and owner-file rules (module
    docstring); empty = the rules hold."""
    r = rules(root)
    out: list[str] = []
    want = [r.columns[k] for k in ORDER]
    head, rows = index_rows(r)
    if not head:
        return [f"{r.index}: missing or empty (the one list of registries "
                f"and owner files)"]
    if head != want:
        out.append(f"{r.index}: header is {head}, expected {want}")
    if not set(want) <= set(head):
        return out

    files = [row["file"] for row in rows]
    dup = sorted({f for f in files if files.count(f) > 1})
    if dup:
        out.append(f"{r.index}: more than one row for {dup}")
    ssot = r.root / r.ssot_dir
    tsvs = sorted(p.relative_to(r.root).as_posix() for p in ssot.rglob("*.tsv")
                  ) if ssot.is_dir() else []
    # message-code fragments (kit.messages.harness_files) are rows of the
    # [ssot].message_codes registry: its index row covers them
    frag_dir = f"{r.ssot_dir}/message_codes.d/"
    covered = {t for t in tsvs if t.startswith(frag_dir)} \
        if r.message_codes in files else set()
    unlisted = sorted(set(tsvs) - set(files) - covered)
    if unlisted:
        out.append(f"{r.index}: does not list {unlisted}")

    id_of: dict[str, list[str]] = {}
    for row in rows:
        f = row["file"]
        path, _, symbol = f.partition(":")
        exists = (r.root / path).is_file()
        if exists and symbol:
            exists = re.search(rf"^{re.escape(symbol)}\s*[:=]",
                               read(r.root / path), re.M) is not None
        if not exists:
            out.append(f"{r.index} row {f}: the file does not exist")
        if row["owner"] not in r.kinds:
            out.append(f"{r.index} row {f}: owner is {row['owner']!r}, not "
                       f"one of {list(r.kinds)}")
        missing = [p for p in paths(row["reader"]) + paths(row["test"])
                   if p != r.none and not (r.root / p).is_file()]
        if missing:
            out.append(f"{r.index} row {f}: reader/test paths do not exist: "
                       f"{missing}")
        if not [p for p in paths(row["test"]) if p != r.none]:
            out.append(f"{r.index} row {f}: names no test")
        if not row["purpose"].strip():
            out.append(f"{r.index} row {f}: purpose is empty")
        if f.endswith(".tsv") and exists:
            cols = [c.strip() for c in (tsv(r.root / f) or [[]])[0]]
            id_cols = [c.strip() for c in row["id"].split("+")]
            if not row["id"].strip() or not all(c in cols for c in id_cols):
                out.append(f"{r.index} row {f}: id column {row['id']!r} is "
                           f"not a column of {cols}")
            else:
                id_of[f] = id_cols

    # every TSV: one column count; ids unique and non-empty
    for rel in tsvs:
        table = tsv(r.root / rel)
        widths = sorted({len(row) for row in table})
        if len(widths) > 1:
            bad = [n + 1 for n, row in enumerate(table)
                   if len(row) != len(table[0])]
            out.append(f"{rel}: rows of different widths {widths} (lines "
                       f"{bad[:10]} differ from the header)")
    for rel, cols in sorted(id_of.items()):
        ids = _ids(tsv(r.root / rel), cols) or []
        empty = sum(1 for i in ids if not all(i))
        if empty:
            out.append(f"{rel}: {empty} row(s) with an empty id "
                       f"({'+'.join(cols)})")
        dups = sorted({"+".join(i) for i in ids if ids.count(i) > 1})
        if dups:
            out.append(f"{rel}: duplicate id(s) {dups}")

    # owner / agent siblings carry the same ids
    kind = {row["file"]: row["owner"] for row in rows}
    for f, k in sorted(kind.items()):
        if k != "agent" or not f.endswith(".agent.tsv"):
            continue
        owner = f.removesuffix(".agent.tsv") + ".tsv"
        if owner not in kind and (r.root / owner).is_file():
            out.append(f"{f}: its owner sibling {owner} is not in the index")
            continue
        if f not in id_of or owner not in id_of:    # an agent-only file
            continue
        agent_t, owner_t = tsv(r.root / f), tsv(r.root / owner)
        head_a = [c.strip() for c in agent_t[0]]
        st = head_a.index(r.status_column) if r.status_column in head_a \
            else None
        agent_ids = {i for i, row in zip(_ids(agent_t, id_of[f]) or [],
                                         agent_t[1:])
                     if st is None or st >= len(row)
                     or row[st].strip() not in r.proposed}
        owner_ids = set(_ids(owner_t, id_of[owner]) or [])
        if agent_ids != owner_ids:
            out.append(f"{f}: ids differ from {owner}: only in the agent "
                       f"file {_show(agent_ids - owner_ids)}, only in the "
                       f"owner file {_show(owner_ids - agent_ids)}")

    # owner files: business meaning only (+ the held ratchet)
    flagged: dict[str, list[str]] = {}
    held_hit: set = set()
    for f, k in sorted(kind.items()):
        if k == "owner" and f.endswith(".tsv") and (r.root / f).is_file():
            got, hit = lint_file(f, r, r.held)
            flagged.update(got)
            held_hit |= hit
    for cell, hits in sorted(flagged.items()):
        out.append(f"owner file {cell}: engineering tokens {hits} (keep "
                   f"business meaning here; the detail goes to .agent.tsv)")
    for h in sorted(r.held - held_hit):
        out.append(f"held {list(h)} no longer fails the lint: drop it from "
                   f"[guards.ssot].held")

    # ids are retired, never deleted
    for f, k in sorted(kind.items()):
        if k not in ("owner", "agent") or f not in id_of:
            continue
        old = _head_table(r.root, f)
        if old is None:
            continue
        before = set(_ids(old, id_of[f]) or [])
        now = set(_ids(tsv(r.root / f), id_of[f]) or [])
        gone = sorted("+".join(i) for i in before - now)
        if gone:
            out.append(f"{f}: id(s) {gone} were at git HEAD and are gone: "
                       f"retire a row (mark it retired), never delete or "
                       f"renumber it")

    # banned terms
    if r.banned and ssot.is_dir():
        for p in sorted(ssot.rglob("*")):
            if p.suffix in (".tsv", ".md") and p.is_file():
                text = read(p)
                for bad, good in sorted(r.banned.items()):
                    if bad in text:
                        out.append(f"{p.relative_to(r.root).as_posix()}: "
                                   f"says {bad!r}; the term is {good!r}")
    return out


def check_ssot(root: Path | str | None = None) -> bool:
    """check_index() as one kit.testing.check line."""
    return report("ssot: the index, owner files and ids keep their rules",
                  check_index(root))


# ---- writes: ssot/ is the builder's, a client's value goes to its database ---

# Path methods that write their receiver
PATH_WRITES = ("write_text", "write_bytes", "touch", "unlink", "mkdir",
               "rmdir", "symlink_to", "hardlink_to")
# open-like functions: (path, mode) at args 0 and 1
OPENERS = ("open", "io.open", "codecs.open", "gzip.open", "bz2.open",
           "lzma.open")
OS_FLAGS = ("O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC")
# function -> the argument positions (and keywords) that name a written path
WRITES_AT = {
    "os.replace": ((0, 1), ("src", "dst")),
    "os.rename": ((0, 1), ("src", "dst")),
    "os.renames": ((0, 1), ("old", "new")),
    "os.remove": ((0,), ("path",)), "os.unlink": ((0,), ("path",)),
    "os.rmdir": ((0,), ("path",)), "os.removedirs": ((0,), ("name",)),
    "os.mkdir": ((0,), ("path",)), "os.makedirs": ((0,), ("name",)),
    "os.link": ((1,), ("dst",)), "os.symlink": ((1,), ("dst",)),
    "os.truncate": ((0,), ("path",)),
    "shutil.copy": ((1,), ("dst",)), "shutil.copy2": ((1,), ("dst",)),
    "shutil.copyfile": ((1,), ("dst",)), "shutil.copytree": ((1,), ("dst",)),
    "shutil.copymode": ((1,), ("dst",)), "shutil.copystat": ((1,), ("dst",)),
    "shutil.move": ((0, 1), ("src", "dst")), "shutil.rmtree": ((0,), ("path",)),
}
# calls whose value is still a path when an argument is one: by name, or
# (os.path.join, pathlib.Path, glob.glob) by their module's
PATH_CALLS = ("Path", "PurePath", "PosixPath", "PurePosixPath", "join",
              "abspath", "realpath", "normpath", "expanduser", "dirname",
              "fspath", "str", "sorted", "list", "tuple", "set", "frozenset",
              "reversed", "enumerate", "zip", "iter", "next", "filter", "map",
              "min", "max", "glob", "iglob", "walk", "scandir")
# methods whose value is still a path when the receiver or an argument is
PATH_METHODS = ("with_suffix", "with_name", "with_stem", "joinpath",
                "relative_to", "resolve", "absolute", "expanduser", "glob",
                "rglob", "iterdir", "as_posix", "replace", "format", "join",
                "strip", "rstrip", "lstrip", "removesuffix", "removeprefix",
                "get", "items", "keys", "values")
# kit.atomic's writers (any module's function of that name): the path first
# a path's attributes that are words of it (a name, a suffix), not a path
FILENAME_ATTRS = ("name", "stem", "suffix", "suffixes", "parts", "anchor",
                  "drive")
ATOMIC = ("open_atomic", "write_json_atomic", "write_bytes_atomic")
MODULES = ("os", "io", "codecs", "gzip", "bz2", "lzma", "shutil")
WriteHit = tuple[int, str]          # (line, what: the call and its path)


def _segments(text: str) -> list[str]:
    return [p for p in text.replace("\\", "/").split("/") if p not in ("",
                                                                       ".")]


def _ssot_text(text: str, d: list[str]) -> bool:
    """A string that names the ssot dir as path segments."""
    parts, n = _segments(text), len(d)
    return any(parts[i:i + n] == d for i in range(len(parts) - n + 1))


def _ssot_word(name: str) -> bool:
    """An identifier with the word ssot (SSOT, ssot_dir, cfg.ssot)."""
    return "ssot" in name.lower().split("_")


def _own(scope: ast.AST):
    """The nodes of one scope: nested functions and lambdas left out (they
    are scopes of their own); class bodies and comprehensions kept."""
    todo = list(ast.iter_child_nodes(scope))
    while todo:
        node = todo.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.Lambda)):
            todo.extend(ast.iter_child_nodes(node))


def _is_walk(node: ast.AST) -> bool:
    """os.walk(...) (or a bare walk(...)): (dirpath, dirnames, filenames),
    of which only dirpath is a path."""
    f = node.func if isinstance(node, ast.Call) else None
    return (isinstance(f, ast.Attribute) and f.attr == "walk"
            and isinstance(f.value, ast.Name) and f.value.id == "os") or (
        isinstance(f, ast.Name) and f.id == "walk")


def _bindings(nodes) -> list[tuple[ast.AST, ast.AST]]:
    """(target, value) for every binding among `nodes`; a tuple target
    against a tuple value of the same length is paired."""
    out: list[tuple[ast.AST, ast.AST]] = []

    def bind(target: ast.AST, value: ast.AST) -> None:
        if isinstance(target, (ast.Tuple, ast.List)):
            if _is_walk(value) and len(target.elts) == 3:
                bind(target.elts[0], value)     # dirpath; the rest are names
                return
            if isinstance(value, (ast.Tuple, ast.List)) \
                    and len(value.elts) == len(target.elts):
                for t, v in zip(target.elts, value.elts):
                    bind(t, v)
            else:
                for t in target.elts:
                    bind(t, value)
        elif isinstance(target, ast.Starred):
            bind(target.value, value)
        else:
            out.append((target, value))

    for n in nodes:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                bind(t, n.value)
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)) and n.value:
            bind(n.target, n.value)
        elif isinstance(n, ast.NamedExpr):
            bind(n.target, n.value)
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            bind(n.target, n.iter)
        elif isinstance(n, ast.withitem) and n.optional_vars is not None:
            bind(n.optional_vars, n.context_expr)
    return out


def _bound_names(nodes) -> set[str]:
    """Every name a scope binds (so it shadows an outer one)."""
    out: set[str] = set()
    for n in nodes:
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store,
                                                           ast.Del)):
            out.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                            ast.ClassDef)):
            out.add(n.name)
    return out


def _is_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) or (isinstance(node, ast.Await)
                                          and isinstance(node.value, ast.Call))


def _module_keys(rel: str) -> set[str]:
    """The dotted names a file is imported by: every tail of its path
    (`scripts/_lib/paths.py` -> `paths`, `_lib.paths`,
    `scripts._lib.paths`); a package's `__init__.py` is the package."""
    parts = rel.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return {".".join(parts[i:]) for i in range(len(parts))}


class _Writes:
    """The writes under the ssot dir in one module."""

    def __init__(self, d: str, known: dict[str, set[str]],
                 calls: tuple[str, ...], rel: str = ""):
        self.d = _segments(d)
        self.known = known      # scanned module -> its module-level ssot names
        self.pkg = rel.split("/")[:-1]
        self.calls = set(ATOMIC) | set(calls)
        self.alias: dict[str, str] = {}
        self.mods: dict[str, str] = {}      # local name -> scanned module
        self.attrs: set[tuple[str | None, str]] = set()  # (class, "self.p")
        self.attr_names: set[str] = set()                         # "p"
        self.methods: dict[int, str] = {}   # id(method) -> its class
        self.bases: dict[str, list[str]] = {}   # class -> its bases' names
        self.cls: str | None = None         # the class of the method scanned
        self.data: set[str] = set()     # names bound only to data (a read)
        self.flow: dict[str, list[tuple[int, bool]]] | None = None
        self.hits: list[WriteHit] = []
        self.module: set[str] = set()   # its module-level ssot names

    # -- what an expression names --

    def tainted(self, node: ast.AST, names: set[str]) -> bool:
        """Whether `node` is a path under the ssot dir. A call keeps a path
        only when it builds or lists paths (PATH_CALLS, PATH_METHODS) or is
        named for ssot: what is read from an ssot file is data, not a path
        under it. A name holds what its last binding above the line put in
        it; the word ssot makes a path of a name only when the name is not
        bound to data (`ssot_rows = read_tsv(...)` is rows)."""
        if isinstance(node, ast.Constant):
            return isinstance(node.value, str) and _ssot_text(node.value,
                                                              self.d)
        if isinstance(node, ast.Name):
            word = node.id not in self.data and _ssot_word(node.id)
            if self.flow and node.id in self.flow:
                before = [t for line, t in self.flow[node.id]
                          if line < node.lineno]
                if before:
                    return before[-1] or word
            return node.id in names or word
        if isinstance(node, ast.Attribute):
            if node.attr in FILENAME_ATTRS:     # a path's words, not a path
                return False
            if _ssot_word(node.attr):
                return True
            mod = self.module_of(node.value)
            if mod is not None:
                return (node.attr in self.known.get(mod, ())
                        or (None, ast.unparse(node)) in self.attrs)
            return ((node.attr in self.attr_names and self.attr_hit(node))
                    or self.tainted(node.value, names))
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else \
                f.id if isinstance(f, ast.Name) else ""
            if _ssot_word(name):
                return True
            args = [*node.args, *(k.value for k in node.keywords)]
            if isinstance(f, ast.Attribute) and name in PATH_METHODS:
                args.append(f.value)
            else:
                q = self.qual(f)
                if not ((isinstance(f, ast.Name) and name in PATH_CALLS)
                        or (q.rpartition(".")[2] in PATH_CALLS
                            and q.split(".")[0] in ("os", "pathlib",
                                                    "glob"))):
                    return False
            return any(self.tainted(a, names) for a in args)
        if isinstance(node, ast.IfExp):
            return self.tainted(node.body, names) or self.tainted(
                node.orelse, names)
        if isinstance(node, (ast.Compare, ast.UnaryOp, ast.Lambda)):
            return False
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return self.tainted(node.elt, names)
        if isinstance(node, ast.DictComp):
            return self.tainted(node.key, names) or self.tainted(node.value,
                                                                 names)
        return any(self.tainted(c, names) for c in ast.iter_child_nodes(node))

    def builds_path(self, call: ast.Call) -> bool:
        """A call whose value is a path (Path(), .resolve(), os.path.join,
        one named for ssot), not data read from a file."""
        f = call.func
        name = f.attr if isinstance(f, ast.Attribute) else \
            f.id if isinstance(f, ast.Name) else ""
        q = self.qual(f)
        return (_ssot_word(name)
                or (isinstance(f, ast.Attribute) and name in PATH_METHODS)
                or (isinstance(f, ast.Name) and name in PATH_CALLS)
                or (q.rpartition(".")[2] in PATH_CALLS
                    and q.split(".")[0] in ("os", "pathlib", "glob")))

    def is_data(self, value: ast.AST, names: set[str]) -> bool:
        """A value that is data: a call that builds no path and reads one
        under ssot (`read_tsv(SSOT / name)` is rows). A call given no ssot
        path (`find_dir(root)`, `locate()`) may return the dir itself, so a
        name with the word ssot bound to it stays a path."""
        call = value.value if isinstance(value, ast.Await) else value
        if not isinstance(call, ast.Call) or self.builds_path(call):
            return False
        args = [*call.args, *(k.value for k in call.keywords)]
        return any(not isinstance(a, ast.Constant) and self.tainted(a, names)
                   for a in args)

    def attr_key(self, node: ast.Attribute) -> str | None:
        """The class an attribute is keyed by: the method's own for
        `self.x` / `cls.x`, none for any other."""
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        return self.cls if isinstance(root, ast.Name) and root.id in (
            "self", "cls") else None

    def attr_hit(self, node: ast.Attribute) -> bool:
        """`self.x` set to an ssot path in a class related to this one by
        inheritance in this module (a base, a subclass, a mixin beside it),
        or in any class when a base is out of sight; any other attribute by
        its text."""
        text, key = ast.unparse(node), self.attr_key(node)
        if (None, text) in self.attrs:
            return True
        if key is None:
            return any(t == text for _, t in self.attrs)
        family = self.family(key)
        return any(t == text and (c is None or c in family or family is None)
                   for c, t in self.attrs)

    def family(self, cls: str) -> set[str] | None:
        """The classes of this module linked to `cls` by inheritance either
        way; None when one of them has a base out of sight."""
        links: dict[str, set[str]] = {}
        for c, bs in self.bases.items():
            for b in bs:
                links.setdefault(c, set()).add(b)
                links.setdefault(b, set()).add(c)
        seen, todo = set(), [cls]
        while todo:
            c = todo.pop()
            if c in seen:
                continue
            seen.add(c)
            if c not in self.bases:             # a base defined elsewhere
                return None
            todo += links.get(c, ())
        return seen

    def qual(self, func: ast.AST) -> str:
        parts: list[str] = []
        while isinstance(func, ast.Attribute):
            parts.insert(0, func.attr)
            func = func.value
        if not isinstance(func, ast.Name):
            return ""
        return ".".join([self.alias.get(func.id, func.id), *parts])

    def module_of(self, node: ast.AST) -> str | None:
        """The scanned module `node` names (`paths`, `_lib.paths`), if any."""
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.insert(0, node.attr)
            node = node.value
        if not isinstance(node, ast.Name) or node.id not in self.mods:
            return None
        mod = ".".join([self.mods[node.id], *parts])
        return mod if mod in self.known else None

    def source(self, node: ast.ImportFrom) -> str:
        """The module a `from … import` reads, a relative one resolved
        against this file's folder."""
        if not node.level:
            return node.module or ""
        up = node.level - 1
        base = self.pkg[:len(self.pkg) - up] if up <= len(self.pkg) else []
        return ".".join([*base, *([node.module] if node.module else [])])

    # -- the scopes --

    def run(self, tree: ast.Module) -> list[WriteHit]:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in MODULES:
                        self.alias[a.asname or a.name] = a.name
                    if a.asname:
                        self.mods[a.asname] = a.name
                    else:                       # `import a.b` binds a
                        top = a.name.split(".")[0]
                        self.mods[top] = top
            elif isinstance(node, ast.ImportFrom):
                src = self.source(node)
                for a in node.names:
                    local = a.asname or a.name
                    if not node.level and node.module in MODULES:
                        self.alias[local] = f"{node.module}.{a.name}"
                    elif a.name in self.calls:
                        self.alias[local] = a.name
                    if f"{src}.{a.name}".strip(".") in self.known:
                        self.mods[local] = f"{src}.{a.name}".strip(".")
            elif isinstance(node, ast.ClassDef):
                self.bases[node.name] = [
                    b.id if isinstance(b, ast.Name) else ast.unparse(b)
                    for b in node.bases if not (isinstance(b, ast.Name)
                                                and b.id == "object")]
                for s in node.body:
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.methods[id(s)] = node.name
        before = None
        while before != self.attrs:          # attributes cross methods
            before = set(self.attrs)
            self.hits = []
            self.module = self.scope(tree, set(), top=True)
        return sorted(set(self.hits))

    def scope(self, node: ast.AST, outer: set[str], top: bool = False
              ) -> set[str]:
        """Scan one scope; the names tainted in it (its module-level ones
        when `top`)."""
        own = list(_own(node))
        bound = _bound_names(own)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda)):
            a = node.args
            bound |= {x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs,
                                      a.vararg, a.kwarg) if x is not None}
        local: set[str] = set()
        for n in own:                        # imported from a scanned module
            if isinstance(n, ast.ImportFrom):
                ssot_names = self.known.get(self.source(n), ())
                local |= {a.asname or a.name for a in n.names
                          if a.name in ssot_names}
        pairs = _bindings(own)
        in_class = {id(t): c.name for c in own if isinstance(c, ast.ClassDef)
                    for s in c.body if isinstance(s, (ast.Assign,
                                                      ast.AnnAssign))
                    for t in (s.targets if isinstance(s, ast.Assign)
                              else [s.target]) if isinstance(t, ast.Name)}
        values: dict[str, list[ast.AST]] = {}
        for t, v in pairs:
            if isinstance(t, ast.Name):
                values.setdefault(t.id, []).append(v)
        # a name every binding of which is a plain assignment in the scope's
        # own statements (no branch, loop, try, with, augmented assignment,
        # comprehension or class body): there the last one above holds
        body = getattr(node, "body", [])
        top = {id(n) for st in (body if isinstance(body, list) else [])
               if isinstance(st, (ast.Assign, ast.AnnAssign))
               for t in (st.targets if isinstance(st, ast.Assign)
                         else [st.target])
               for n in ast.walk(t) if isinstance(n, ast.Name)}
        targets: dict[str, list[ast.Name]] = {}
        for n in own:
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                targets.setdefault(n.id, []).append(n)
        other = {(a.asname or a.name).split(".")[0] for n in own
                 if isinstance(n, (ast.Import, ast.ImportFrom))
                 for a in n.names} | {
            n.name for n in own if isinstance(
                n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        straight = {k for k, ts in targets.items()
                    if k not in other and all(id(t) in top for t in ts)}
        saved, outer_data = (self.data, self.flow), self.data - bound
        self.flow = None
        cls_local: dict[str, set[str]] = {}     # a class body's ssot names
        while True:
            before = sum(len(v) for v in cls_local.values())
            names = (outer - bound) | local
            self.data = outer_data | {
                k for k, vs in values.items()
                if all(self.is_data(v, names) for v in vs)}
            grow = set()
            for target, value in pairs:
                c = in_class.get(id(target)) if isinstance(
                    target, ast.Name) else None
                if not self.tainted(value, names | cls_local.get(c, set())):
                    continue
                if c is not None:
                    n = target.id
                    cls_local.setdefault(c, set()).add(n)
                    self.attrs |= {(c, f"self.{n}"), (c, f"cls.{n}"),
                                   (c, f"{c}.{n}"), (None, f"{c}.{n}")}
                    self.attr_names.add(n)
                elif isinstance(target, ast.Name):
                    grow.add(target.id)
                elif isinstance(target, ast.Attribute):
                    self.attrs.add((self.attr_key(target),
                                    ast.unparse(target)))
                    self.attr_names.add(target.attr)
            if grow <= local and before == sum(len(v) for v in
                                               cls_local.values()):
                break
            local |= grow
        names = (outer - bound) | local
        self.flow = {}
        for t, v in pairs:
            if isinstance(t, ast.Name) and t.id in straight:
                self.flow.setdefault(t.id, []).append(
                    (t.lineno, self.tainted(v, names)))
        for k in self.flow:
            self.flow[k].sort(key=lambda x: x[0])
        for n in own:
            if isinstance(n, ast.Call):
                self.call(n, names)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.Lambda)):
                cls = self.cls
                self.cls = self.methods.get(id(n), cls)
                self.scope(n, names)
                self.cls = cls
        self.data, self.flow = saved
        return local if top else names

    # -- the writes --

    def _hit(self, node: ast.Call, what: str, target: ast.AST) -> None:
        shown = ast.unparse(target)
        shown = shown if len(shown) <= 60 else shown[:57] + "..."
        self.hits.append((node.lineno, f"{what} {shown}"))

    def call(self, node: ast.Call, names: set[str]) -> None:
        f, q = node.func, self.qual(node.func)
        args, kw = node.args, {k.arg: k.value for k in node.keywords if k.arg}

        def arg(i: int, name: str) -> ast.AST | None:
            return args[i] if len(args) > i else kw.get(name)

        def check(what: str, *targets: ast.AST | None) -> None:
            for t in targets:
                if t is not None and self.tainted(t, names):
                    self._hit(node, what, t)
                    return

        if q in OPENERS or (isinstance(f, ast.Name) and f.id == "open"):
            if _write_mode(arg(1, "mode")):
                check(f"{q or 'open'}(…, write)", arg(0, "file"))
        elif q == "os.open":
            if not _read_flags(arg(1, "flags")):
                check("os.open(…, write)", arg(0, "path"))
        elif q in WRITES_AT:
            at, keys = WRITES_AT[q]
            check(q, *(arg(i, k) for i, k in zip(at, keys)))
        elif q.rpartition(".")[2] in self.calls:
            check(q.rpartition(".")[2], arg(0, "path"))
        elif isinstance(f, ast.Attribute):
            if f.attr in PATH_WRITES:
                check(f".{f.attr}()", f.value)
            elif f.attr in ("rename", "replace") and len(args) == 1 \
                    and not node.keywords:      # Path's; str.replace takes 2
                check(f".{f.attr}()", f.value, args[0])
            elif f.attr == "open" and _write_mode(arg(0, "mode")):
                check(".open(write)", f.value)


def _write_mode(mode: ast.AST | None) -> bool:
    """An open mode that writes; one that is not a literal counts."""
    if mode is None:
        return False
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return any(c in mode.value for c in "wax+")
    return True


def _read_flags(flags: ast.AST | None) -> bool:
    """os.open flags that only read: the literal 0, or O_RDONLY with no
    writing flag beside it. A flags value the scan cannot read counts as a
    write."""
    if flags is None:
        return False
    if isinstance(flags, ast.Constant):
        return flags.value == 0
    s = ast.unparse(flags)
    return "O_RDONLY" in s and not any(o in s for o in OS_FLAGS)


def scan_writes(source: str, ssot_dir: str = "ssot",
                known: dict[str, set[str]] | None = None,
                calls: tuple[str, ...] = (), rel: str = "") -> list[WriteHit]:
    """The writes under `ssot_dir` in one module's source, (line, what);
    `known` = {scanned module: its module-level ssot names}, for the
    modules it may import; `rel` = its harness-relative path (for its
    relative imports)."""
    return _Writes(ssot_dir, dict(known or {}), calls, rel).run(
        ast.parse(source))


def _is_test(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    return ("tests" in parts[:-1] or name.startswith("test_")
            or name.endswith("_test.py") or name == "conftest.py")


def write_settings(cfg: HarnessConfig) -> tuple[tuple[str, ...],
                                                tuple[str, ...], dict, dict,
                                                tuple[str, ...]]:
    """(code folders, skipped folders, the skip rows {path: reason},
    writers {path: reason}, the harness's own write helpers). The vendored
    kit is always skipped; any other skip needs its reason (a list gives
    none, so each of its entries is reported)."""
    g = section(cfg, "guards", "ssot")
    scripts = cfg.scripts_dir.strip("/") or "."
    kit = "kit" if scripts == "." else f"{scripts}/kit"
    writers, skips = g.get("writers", {}), g.get("write_skip", {})
    if isinstance(skips, (list, tuple)):
        skips = {str(k): "" for k in skips}
    skips = dict(skips) if isinstance(skips, dict) else {}
    return (strs(g.get("write_code"), ["."]),
            (kit, *(k for k in skips if k.strip("/") != kit)), skips,
            dict(writers) if isinstance(writers, dict) else {},
            strs(g.get("write_calls"), []))


def _under(rel: str, folders) -> str | None:
    """The first of `folders` that `rel` is, or is under."""
    for f in folders:
        f = f.strip("/")
        if f in ("", ".") or rel == f or rel.startswith(f + "/"):
            return f
    return None


def _third_party(folder: Path) -> bool:
    """A virtualenv or an installed-packages folder: not the harness's."""
    return folder.name == "site-packages" or (folder / "pyvenv.cfg").is_file()


def write_files(root: Path, code: tuple[str, ...], skip: tuple[str, ...]
                ) -> list[str]:
    """The .py files the rule reads (harness-relative, sorted)."""
    out: set[str] = set()
    skip = tuple(s for s in skip if s.strip("/") not in ("", "."))
    for d in code:
        base = root / d.strip("/") if d.strip("/") not in ("", ".") else root
        for dirpath, dirnames, filenames in os.walk(base):
            here = Path(dirpath)
            dirnames[:] = sorted(
                n for n in dirnames if not n.startswith(".")
                and n not in SKIP_DIRS and n != "tests"
                and not _third_party(here / n)
                and _under((here / n).relative_to(root).as_posix(),
                           skip) is None)
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                rel = (here / name).relative_to(root).as_posix()
                if not _is_test(rel) and _under(rel, skip) is None:
                    out.add(rel)
    return sorted(out)


def check_writes(root: Path | str | None = None) -> list[str]:
    """Every call in the harness's code that writes under the ssot dir,
    outside the builder's `writers` (module docstring); empty = ssot/ is
    edited only by the builder."""
    cfg = harness(root)
    base = Path(root) if root is not None else cfg.root
    d = cfg.ssot.get("dir", "ssot").strip("/")
    code, skip, skips, writers, calls = write_settings(cfg)
    out: list[str] = []
    for k, why in sorted(skips.items()):
        if not isinstance(why, str) or not why.strip():
            out.append(f"[guards.ssot].write_skip {k!r}: give its reason "
                       f"(why the ssot write rule may not read it)")
        if not (base / k.strip("/")).exists():
            out.append(f"[guards.ssot].write_skip {k!r}: is gone: drop the "
                       f"row")
    for c in code:
        if not write_files(base, (c,), skip):
            out.append(f"no code to read under {c}: a wrong path is never a "
                       f"pass")
    trees: dict[str, ast.Module] = {}
    for rel in write_files(base, code, skip):
        try:
            trees[rel] = ast.parse((base / rel).read_bytes(), filename=rel)
        except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
            out.append(f"{rel}:{getattr(e, 'lineno', None) or 1}: does not "
                       f"parse, so the ssot write rule cannot read it")
    known: dict[str, set[str]] = {}
    hits: dict[str, list[WriteHit]] = {}
    deep: set[str] = set()
    for _ in range(len(trees) + 1):      # until no module's ssot names grow
        grew = False
        for rel, tree in trees.items():
            if rel in deep:
                continue
            w = _Writes(d, known, calls, rel)
            try:
                hits[rel] = w.run(tree)
            except RecursionError:
                deep.add(rel)
                hits.pop(rel, None)
                out.append(f"{rel}: too deeply nested for the ssot write "
                           f"rule to read (never a pass)")
                continue
            for key in _module_keys(rel):
                if not w.module <= known.get(key, set()):
                    known.setdefault(key, set()).update(w.module)
                    grew = True
        if not grew:
            break
    used: set[str] = set()
    for rel, found in sorted(hits.items()):
        if not found:
            continue
        keys = [k.strip("/") for k in writers if k.strip("/") not in ("", ".")
                and _under(rel, [k]) is not None]
        if keys:
            used.update(keys)
            continue
        out += [f"{rel}:{line}: {what} writes under {d}/ (ssot/ is the "
                f"builder's: a client's own value goes to its database; a "
                f"builder's tool goes in [guards.ssot].writers with its "
                f"reason)" for line, what in found]
    for k, why in sorted(writers.items()):
        if not isinstance(why, str) or not why.strip():
            out.append(f"[guards.ssot].writers {k!r}: give its reason (who "
                       f"runs it, and why it may write {d}/)")
        if k.strip("/") not in used:
            out.append(f"[guards.ssot].writers {k!r}: writes nothing under "
                       f"{d}/ any more (or is gone): drop the row")
    return out


_PLANTED_WRITES = '''import os, shutil
from pathlib import Path
from kit import atomic
from kit.atomic import open_atomic
ROOT = Path(__file__).resolve().parent
SSOT = ROOT / "ssot"
CONST = SSOT / "thresholds.json"
DATA = ROOT / "data"
def f(cfg, rows, out):
    CONST.write_text(rows)
    with open(ROOT / "ssot" / "x.json", "a") as fh:
        fh.write(rows)
    os.replace(out, f"{ROOT}/ssot/y.tsv")
    shutil.copy(DATA / "z.json", SSOT)
    atomic.write_json_atomic(Path(cfg.ssot["thresholds"]), rows)
    with open_atomic(CONST) as fh:
        fh.write(rows)
    for p in SSOT.glob("*.tsv"):
        p.unlink()
    (DATA / "a.json").write_text(rows)
    rows2 = CONST.read_text()
    with open(CONST) as fh:
        fh.read()
    shutil.copy(CONST, DATA / "c.json")
    name = str(CONST).replace(".tsv", ".agent.tsv")
    path = DATA / "own.json"
    path.write_text(name)
    for row in read_tsv(CONST):
        (DATA / row["file"]).write_text(rows)
    os.replace(name, DATA / "d.json")
class Store:
    def __init__(self):
        self.path = SSOT / "s.json"
    def save(self, mode):
        self.path.open(mode).write("x")
'''


# (source, known, a write expected): each a way the rule once read wrong
_WRITE_CASES: tuple[tuple[str, dict, bool], ...] = (
    ("from paths import CONST\nCONST.write_text('x')\n",
     {"paths": {"CONST"}}, True),
    ("from out import CONST\nCONST.write_text('x')\n",
     {"paths": {"CONST"}}, False),
    ("from _lib import paths\npaths.CONST.write_text('x')\n",
     {"_lib.paths": {"CONST"}}, True),
    ("import _lib.paths as p\nopen(p.CONST, 'w')\n",
     {"_lib.paths": {"CONST"}}, True),
    ("P = SSOT / 'x.json'\ndef f():\n    P = DATA / 'y.json'\n"
     "    P.write_text('x')\n", {}, False),
    ("C = Path('ssot') / 'c.json'\nshutil.copy(C, DATA / C.name)\n"
     "for p in Path('ssot').glob('*.tsv'):\n"
     "    (DATA / f'{p.stem}.json').write_text('x')\n", {}, False),
    ("class S:\n    p = Path('ssot/c')\n    def f(self):\n"
     "        self.p.write_text('x')\n", {}, True),
    ("class A:\n    def __init__(self):\n        self.path = Path('ssot/a')\n"
     "class B:\n    def __init__(self):\n        self.path = Path('data/b')\n"
     "    def f(self):\n        self.path.write_text('x')\n", {}, False),
    ("ssot_rows = read_tsv(Path('ssot/c.json'))\nfor row in ssot_rows:\n"
     "    (Path('data') / row['f']).write_text('x')\n", {}, False),
    ("p = Path('ssot/c')\np.read_text()\np = Path('data/c')\n"
     "p.write_text('x')\n", {}, False),
    ("import os\nos.open(Path('ssot/x'), flags)\n", {}, True),
    ("import os\nos.open(Path('ssot/x'), os.O_RDONLY)\n", {}, False),
    ("import os\nfor d, _, fs in os.walk(Path('ssot')):\n    for f in fs:\n"
     "        os.remove(os.path.join(d, f))\n", {}, True),
    ("def save(args, v):\n    if args.default:\n"
     "        path = SSOT / 'constants.json'\n    else:\n"
     "        path = args.client_dir / 'settings.json'\n"
     "    path.write_text(v)\n", {}, True),
    ("p = str(SSOT / 'a')\np += '.tmp'\nopen(p, 'w')\n", {}, True),
    ("p = DATA / 'log'\nfor n in ns:\n    p.write_text(n)\n"
     "    p = SSOT / n\n", {}, True),
    ("p = SSOT / 'a'\nxs = [p.name for p in DATA.iterdir()]\n"
     "p.write_text('')\n", {}, True),
    ("import sys\nssot = Path(sys.argv[1])\n(ssot / 'x.json').write_text('')\n",
     {}, True),
    ("ssot_dir = ROOT / REG\n(ssot_dir / 'x.json').write_text('')\n", {}, True),
    ("class Base:\n    def __init__(self):\n        self.p = SSOT / 'a'\n"
     "class Child(Base):\n    def save(self):\n        self.p.write_text('')\n",
     {}, True),
    ("def a(obj):\n    obj.out = SSOT / 'a'\n"
     "class C:\n    def f(self, obj):\n        obj.out.write_text('')\n",
     {}, True),
    ("store.out = SSOT / 'a'\nclass C:\n    def f(self):\n"
     "        store.out.write_text('')\n", {}, True),
    ("class Base:\n    def save(self):\n        self.path.write_text('x')\n"
     "class Child(Base):\n    def __init__(self):\n"
     "        self.path = SSOT / 'a.json'\n", {}, True),
    ("class Paths:\n    def __init__(self):\n        self.out = SSOT / 'a'\n"
     "class Saver:\n    def save(self):\n        self.out.write_text('')\n"
     "class Store(Paths, Saver):\n    pass\n", {}, True),
    ("def init(self):\n    self.p = SSOT / 'a'\nclass C:\n"
     "    def f(self):\n        self.p.write_text('')\n", {}, True),
    ("def f(root):\n    ssot_dir = find_dir(root)\n"
     "    (ssot_dir / 'x.json').write_text('')\n", {}, True),
    ("for ssot_file in registry_files():\n    ssot_file.unlink()\n", {}, True),
    ("import os, shutil\nfor d, _, fs in os.walk(Path('ssot')):\n"
     "    for f in fs:\n        shutil.copy(os.path.join(d, f), DATA / f)\n",
     {}, False),
    ("import paths\npaths.OUT = SSOT / 'a'\npaths.OUT.write_text('')\n",
     {"paths": {"CONST"}}, True),
    ("class S:\n    DIR = Path('ssot')\n    FILE = DIR / 'a.json'\n"
     "    def f(self):\n        self.FILE.write_text('')\n", {}, True),
)


def writes_self_test() -> list[str]:
    """The write rule tried on a planted module and on each form it once
    read wrong: [] when every write under ssot is caught and the reads and
    other writes beside it are not."""
    got = [n for n, _ in scan_writes(_PLANTED_WRITES)]
    want = [10, 11, 13, 14, 15, 16, 19, 30, 35]
    out = []
    if got != want:
        out.append(f"planted writes: expected lines {want}, the scan found "
                   f"{got}")
    for source, known, write in _WRITE_CASES:
        if bool(scan_writes(source, known=known)) != write:
            out.append(f"{'missed' if write else 'flagged'}: "
                       f"{source.splitlines()[-1].strip()!r} in "
                       f"{source!r}")
    return out


def check_ssot_writes(root: Path | str | None = None) -> bool:
    """writes_self_test() + check_writes() as kit.testing.check lines."""
    ok = report("ssot writes: the rule catches each planted write",
                writes_self_test())
    return report("ssot writes: no harness code writes under ssot/ (a "
                  "client's value goes to its database)",
                  check_writes(root)) and ok
