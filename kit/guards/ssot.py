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
write_skip ([<scripts_dir>/kit]), writers ({path: reason}), write_calls
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
with the word `ssot` (SSOT, cfg.ssot, ssot_dir), or a name bound to such
an expression in the same scope, an enclosing one, or (as a module-level
name) in another scanned module it imports. A path goes through `/`,
f-strings, IfExp and the calls that build or list paths (PATH_CALLS,
PATH_METHODS: Path(), os.path.join, str, sorted, .with_suffix, .glob,
…); any other call's value is data, so what is read from an ssot file is
not a path under it. Reading ssot is never a hit, nor copying from it,
nor writing a row's own file elsewhere. A path the code builds out of
sight (a parameter, a function's return) is not seen: the rule catches
the plain case, not every case.

The code is every .py under `write_code` (default: the whole harness),
`write_skip` left out (default: the vendored kit), and never a test
(a `tests` folder, test_*.py, *_test.py, conftest.py), a hidden folder,
__pycache__ or node_modules. `writers` = {path or folder: reason} is the
builder's own tools that may write ssot (a registry editor run in the
builder's checkout): each needs its reason, and an entry that writes
nothing under ssot any more is itself a problem, so the list stays
true. A file that does not parse is a problem: what the rule cannot
read is never a pass. `writes_self_test()` scans a planted module with
every write form and the reads beside them.

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
              "min", "max", "glob", "iglob")
# methods whose value is still a path when the receiver or an argument is
PATH_METHODS = ("with_suffix", "with_name", "with_stem", "joinpath",
                "relative_to", "resolve", "absolute", "expanduser", "glob",
                "rglob", "iterdir", "as_posix", "replace", "format", "join",
                "strip", "rstrip", "lstrip", "removesuffix", "removeprefix",
                "get", "items", "keys", "values")
# kit.atomic's writers (any module's function of that name): the path first
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


def _bindings(nodes) -> list[tuple[ast.AST, ast.AST]]:
    """(target, value) for every binding among `nodes`; a tuple target
    against a tuple value of the same length is paired."""
    out: list[tuple[ast.AST, ast.AST]] = []

    def bind(target: ast.AST, value: ast.AST) -> None:
        if isinstance(target, (ast.Tuple, ast.List)):
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


class _Writes:
    """The writes under the ssot dir in one module."""

    def __init__(self, d: str, known: set[str], calls: tuple[str, ...]):
        self.d = _segments(d)
        self.known = known              # module-level ssot names elsewhere
        self.calls = set(ATOMIC) | set(calls)
        self.alias: dict[str, str] = {}
        self.attrs: set[str] = set()    # tainted attribute targets: "self.p"
        self.attr_names: set[str] = set()                         # "p"
        self.hits: list[WriteHit] = []
        self.module: set[str] = set()   # its module-level ssot names
        self.imported: set[str] = set()     # names any `from x import` takes

    # -- what an expression names --

    def tainted(self, node: ast.AST, names: set[str]) -> bool:
        """Whether `node` is a path under the ssot dir. A call keeps a path
        only when it builds or lists paths (PATH_CALLS, PATH_METHODS) or is
        named for ssot: what is read from an ssot file is data, not a path
        under it."""
        if isinstance(node, ast.Constant):
            return isinstance(node.value, str) and _ssot_text(node.value,
                                                              self.d)
        if isinstance(node, ast.Name):
            return node.id in names or _ssot_word(node.id)
        if isinstance(node, ast.Attribute):
            return (_ssot_word(node.attr)
                    or (node.attr in self.attr_names
                        and ast.unparse(node) in self.attrs)
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

    def qual(self, func: ast.AST) -> str:
        parts: list[str] = []
        while isinstance(func, ast.Attribute):
            parts.insert(0, func.attr)
            func = func.value
        if not isinstance(func, ast.Name):
            return ""
        return ".".join([self.alias.get(func.id, func.id), *parts])

    # -- the scopes --

    def run(self, tree: ast.Module) -> list[WriteHit]:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in MODULES:
                        self.alias[a.asname or a.name] = a.name
            elif isinstance(node, ast.ImportFrom):
                self.imported |= {a.name for a in node.names}
                for a in node.names:
                    if not node.level and node.module in MODULES:
                        self.alias[a.asname or a.name] = \
                            f"{node.module}.{a.name}"
                    elif a.name in self.calls:
                        self.alias[a.asname or a.name] = a.name
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
                local |= {a.asname or a.name for a in n.names
                          if a.name in self.known}
        pairs = _bindings(own)
        while True:
            names = (outer - bound) | local
            grow = set()
            for target, value in pairs:
                if not self.tainted(value, names):
                    continue
                if isinstance(target, ast.Name):
                    grow.add(target.id)
                elif isinstance(target, ast.Attribute):
                    self.attrs.add(ast.unparse(target))
                    self.attr_names.add(target.attr)
            if grow <= local:
                break
            local |= grow
        names = (outer - bound) | local
        for n in own:
            if isinstance(n, ast.Call):
                self.call(n, names)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.Lambda)):
                self.scope(n, names)
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
            flags = arg(1, "flags")
            if flags is None or any(o in ast.unparse(flags) for o in OS_FLAGS):
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


def scan_writes(source: str, ssot_dir: str = "ssot",
                known: set[str] | frozenset = frozenset(),
                calls: tuple[str, ...] = ()) -> list[WriteHit]:
    """The writes under `ssot_dir` in one module's source, (line, what);
    `known` = module-level ssot names of other modules it may import."""
    return _Writes(ssot_dir, set(known), calls).run(ast.parse(source))


def _is_test(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    return ("tests" in parts[:-1] or name.startswith("test_")
            or name.endswith("_test.py") or name == "conftest.py")


def write_settings(cfg: HarnessConfig) -> tuple[tuple[str, ...],
                                                tuple[str, ...], dict,
                                                tuple[str, ...]]:
    """(code folders, skipped folders, writers {path: reason}, the
    harness's own write helpers)."""
    g = section(cfg, "guards", "ssot")
    scripts = cfg.scripts_dir.strip("/") or "."
    kit = "kit" if scripts == "." else f"{scripts}/kit"
    writers = g.get("writers", {})
    return (strs(g.get("write_code"), ["."]),
            strs(g.get("write_skip"), [kit]),
            dict(writers) if isinstance(writers, dict) else {},
            strs(g.get("write_calls"), []))


def _under(rel: str, folders) -> str | None:
    """The first of `folders` that `rel` is, or is under."""
    for f in folders:
        f = f.strip("/")
        if f in ("", ".") or rel == f or rel.startswith(f + "/"):
            return f
    return None


def write_files(root: Path, code: tuple[str, ...], skip: tuple[str, ...]
                ) -> list[str]:
    """The .py files the rule reads (harness-relative, sorted)."""
    out: set[str] = set()
    for d in code:
        base = root / d.strip("/") if d.strip("/") not in ("", ".") else root
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(
                n for n in dirnames if not n.startswith(".")
                and n not in SKIP_DIRS and n != "tests")
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                rel = (Path(dirpath) / name).relative_to(root).as_posix()
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
    code, skip, writers, calls = write_settings(cfg)
    out: list[str] = []
    files = write_files(base, code, skip)
    if not files:
        out.append(f"no code to read under {', '.join(code)}: a wrong path "
                   f"is never a pass")
    trees: dict[str, ast.Module] = {}
    hits: dict[str, list[WriteHit]] = {}
    takes: dict[str, set[str]] = {}
    known: set[str] = set()
    for rel in files:
        try:
            trees[rel] = ast.parse(read(base / rel))
        except SyntaxError as e:
            out.append(f"{rel}:{e.lineno}: does not parse, so the ssot write "
                       f"rule cannot read it")
            continue
        w = _Writes(d, set(), calls)
        hits[rel] = w.run(trees[rel])
        known |= w.module
        takes[rel] = w.imported
    for rel, names in takes.items():     # again, with the names it imports
        if names & known:
            hits[rel] = _Writes(d, known, calls).run(trees[rel])
    used: set[str] = set()
    for rel, found in sorted(hits.items()):
        if not found:
            continue
        w = _under(rel, [k for k in writers if k.strip("/") not in ("", ".")])
        if w is not None:
            used.add(w)
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


def writes_self_test() -> list[str]:
    """The write rule tried on a planted module: [] when every write
    under ssot is caught and the reads and other writes beside it are not."""
    got = [n for n, _ in scan_writes(_PLANTED_WRITES)]
    want = [10, 11, 13, 14, 15, 16, 19, 30, 35]
    out = []
    if got != want:
        out.append(f"planted writes: expected lines {want}, the scan found "
                   f"{got}")
    if scan_writes("from paths import CONST\nCONST.write_text('x')\n",
                   known={"CONST"}) == []:
        out.append("a module-level ssot name imported from another module "
                   "is not followed")
    if scan_writes("P = SSOT / 'x.json'\ndef f():\n    P = DATA / 'y.json'\n"
                   "    P.write_text('x')\n") != []:
        out.append("a local name that shadows a module-level ssot one was "
                   "flagged")
    return out


def check_ssot_writes(root: Path | str | None = None) -> bool:
    """writes_self_test() + check_writes() as kit.testing.check lines."""
    ok = report("ssot writes: the rule catches each planted write",
                writes_self_test())
    return report("ssot writes: no harness code writes under ssot/ (a "
                  "client's value goes to its database)",
                  check_writes(root)) and ok
