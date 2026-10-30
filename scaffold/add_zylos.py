#!/usr/bin/env python3
"""Set a skill pack up to run as a Zylos component: copy the adapter, write the manifest, the SKILL.md keys and the root ecosystem file.

    python3 scaffold/add_zylos.py --skill-pack PATH [--brand openmax] [--port N] [--dry-run]

What hosts/zylos/README.md says a skill pack does by hand, in one command, from what skill-pack.toml already says (name, cli, env prefix,
scripts folder):

  * copies the adapter files (the list is tools/fleet.py's: everything but the adapter's tests and its two templates) into `zylos/`;
  * writes `zylos/manifest.json` when there is none: the example's runtime pins, the CLI link `<brand>-<cli>`, the console on
    127.0.0.1:PORT under `/<cli>`, and no scheduled task (tasks are the skill pack's own prompts: it adds them);
  * adds the Zylos keys to the `SKILL.md` frontmatter when it has none of them (`lifecycle:`, `bin:`, `config:`, `next-steps:`); the file's other
    keys, its body and its line endings stay;
  * writes the root `ecosystem.config.cjs` from the template when there is none;
  * adds Node 22 and `node zylos/lib.js check` to the last job's steps in `.github/workflows/ci.yml`, when the file ends with that list and does not run
    the check yet.

It writes into another repository, so it is built not to leave it half done or broken:

  * every input is checked and every new file is computed before the first byte is written: a port outside 1024 to 65535, a brand or a name the
    adapter's own patterns refuse, a manifest that is not JSON or lacks a field, a folder `zylos/` that is a link, a CLI script that is not there;
  * no write goes through a link: a path that is, or sits under, a link is refused (a `SKILL.md` or `ci.yml` that is a link is left alone and named); a
    folder where a file goes, a file where a folder goes and a read-only target are refused before the first write; and a write that fails after all puts
    back what was written (the bytes and modes of the files, the folders it made);
  * the adapter's own rules are met before anything is written: the `SKILL.md` name is the component's, an `env_prefix` with SECRET, TOKEN, PASSWORD,
    ACCESS_KEY, API_KEY or PRIVATE_KEY in it is refused (every config key would have to be `sensitive`), and the CLI path has only letters, digits, `_`, `.`,
    `-` and `/`;
  * it never overwrites a manifest, a frontmatter that has Zylos keys or an ecosystem file; a skill pack that has them is left as it is, and
    `python3 tools/fleet.py update` keeps the adapter copy current. A file it cannot edit safely (a ci.yml whose steps are not the file's end, written in a style the editor does not read, or indented with a tab; a SKILL.md with
    its own `bin:` or `config:`, a frontmatter that is not plain `key: value` lines, no frontmatter, LF and CRLF mixed) is left alone and named in a line, with what to add by hand;
  * then `node zylos/lib.js check` runs, when node is on PATH, and its verdict is the exit code.

The port is the one thing two skill packs on one host must not share: default 8800 plus a hash of the name, in 8800 to 9799 (a hash has collisions: pass
--port to choose, and keep the ports of one host apart yourself). The brand is the word before the CLI in the linked command (`openmax-seo`); a generic
command name clashes on a host.

Test: scaffold/tests/test_add_zylos.py.
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tomllib
import zlib
from pathlib import Path

PLAYBOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLAYBOOK / "tools"))
import fleet  # noqa: E402

SOURCE = PLAYBOOK / "hosts" / "zylos"
BRAND = "openmax"
CI_CHECK = re.compile(r"^[^#\n]*node\s+(?:\./)?zylos/lib\.js\s+check", re.M)
OWNED_KEYS = ("lifecycle", "bin", "config", "next-steps")
# the adapter's own patterns (hosts/zylos/lib.js, RE), the ones a value of ours has to satisfy
SECRET_KEY = re.compile(r"SECRET|TOKEN|PASSWORD|ACCESS_KEY|API_KEY|PRIVATE_KEY")
NOT_ALIASES = ("uv", "node", "sh", "python", "python3")                  # the adapter's: words a detached command cannot start with to mean the CLI
RELPATH = re.compile(r"[A-Za-z0-9_./-]+")
RE = {"name": r"[a-z0-9][a-z0-9-]*", "bin": r"[a-z0-9]+(-[a-z0-9]+)+", "prefix": r"[A-Z][A-Z0-9]*(_[A-Z0-9]+)*", "env": r"[A-Z][A-Z0-9_]*",
      "basePath": r"/[a-z0-9][a-z0-9-]*", "marker": r"[A-Z][A-Z0-9]*(-[A-Z0-9]+)+", "brand": r"[a-z0-9]+"}


def refuse(text: str) -> SystemExit:
    return SystemExit(f"error: {text}")


def fits(kind: str, value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(RE[kind], value) is not None


def settings(skill_pack: Path) -> dict:
    """name, cli, prefix and the scripts folder of the skill pack, from its skill-pack.toml, each checked against the adapter's patterns."""
    toml = skill_pack / "skill-pack.toml"
    if not toml.is_file():
        raise refuse(f"{toml} is missing: this is not a skill pack")
    try:
        h = tomllib.loads(toml.read_text("utf-8")).get("skill_pack", {})
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as e:
        raise refuse(f"{toml} cannot be read ({e.__class__.__name__})") from None
    if not isinstance(h, dict):
        raise refuse(f"{toml}: [skill_pack] is not a table")
    raw = str(h.get("scripts_dir") or "scripts").replace("\\", "/")
    scripts = posixpath.normpath(raw)
    if raw.startswith("/") or scripts == ".." or scripts.startswith("../"):
        raise refuse(f"skill-pack.toml scripts_dir {raw!r} leaves the skill pack")
    got = {"name": h.get("name"), "cli": h.get("cli"), "prefix": h.get("env_prefix"), "scripts": "" if scripts == "." else scripts}
    missing = [k for k in ("name", "cli", "prefix") if not got[k]]
    if missing:
        raise refuse(f"skill-pack.toml [skill_pack] has no {', '.join(missing)}")
    if not all(isinstance(got[k], str) for k in ("name", "cli", "prefix")):
        raise refuse("skill-pack.toml: name, cli and env_prefix are text")
    for kind, key in (("name", "name"), ("prefix", "prefix")):
        if not fits(kind, str(got[key])):
            raise refuse(f"skill-pack.toml {('env_prefix' if key == 'prefix' else key)} = {got[key]!r} does not fit the adapter's pattern {RE[kind]}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", str(got["cli"])):
        raise refuse(f"skill-pack.toml cli = {got['cli']!r} is not lowercase letters, digits, hyphens and underscores")
    return got


def default_port(name: str) -> int:
    return 8800 + zlib.crc32(name.encode()) % 1000


def entry_for(skill_pack: Path, s: dict) -> str:
    """The CLI script inside the skill pack: <scripts>/<cli>.py, else <cli>.py at the root, else skill_pack.py."""
    base = f"{s['scripts']}/" if s["scripts"] else ""
    for rel in (f"{base}{s['cli']}.py", f"{s['cli']}.py", "skill_pack.py"):
        if (skill_pack / rel).is_file():
            return rel
    raise refuse(f"no CLI script found for '{s['cli']}' (tried {base}{s['cli']}.py, {s['cli']}.py, skill_pack.py)")


def manifest_for(s: dict, entry: str, brand: str, port: int) -> dict:
    """A manifest that passes `check`: the example's runtime pins, the skill pack's own names, no scheduled task."""
    example = json.loads((SOURCE / "manifest.example.json").read_text("utf-8"))
    p, cli = s["prefix"], s["cli"]
    link = cli.replace("_", "-")
    return {
        "name": s["name"],
        "min_zylos": example["min_zylos"],
        "cli": {"bin": f"{brand}-{link}", "entry": entry, "doctor": ["doctor"]},
        "env": {"prefix": p, "data_dir": f"{p}_DATA_DIR", "files": [f"~/.{cli}.env"]},
        "runtime": example["runtime"],
        "endpoints": [],
        "scope": {"list": ["facts", "list", "--json"], "field": "declared_markets", "declare": "facts init"},
        "reply": {"channel": f"{p}_REPLY_CHANNEL", "endpoint": f"{p}_REPLY_ENDPOINT"},
        "console": {"entry": "console/serve.py", "port": port, "port_key": f"{p}_CONSOLE_PORT", "title_key": f"{p}_CONSOLE_TITLE",
                    "base_path": f"/{link}", "user_header": "X-Remote-User", "users_file": "console.users",
                    "args": ["--relay-verbs", "facts confirm,decisions confirm", "--lang", "en"],
                    "allow_host_key": f"{p}_CONSOLE_ALLOW_HOST"},
        "detach": {"exit_marker": f"{p.replace('_', '')}-EXIT", "alias": cli},
        "tasks": [],
    }


def problems(m: dict) -> list[str]:
    """What in a manifest of ours the adapter's patterns would refuse, before it is written."""
    out = []
    for label, kind, value in (("name", "name", m["name"]), ("cli.bin", "bin", m["cli"]["bin"]), ("env.prefix", "prefix", m["env"]["prefix"]),
                               ("env.data_dir", "env", m["env"]["data_dir"]), ("console.base_path", "basePath", m["console"]["base_path"]),
                               ("detach.exit_marker", "marker", m["detach"]["exit_marker"])):
        if not fits(kind, value):
            out.append(f"{label} = {value!r} does not fit {RE[kind]}")
    alias = m["detach"]["alias"]
    if not fits("name", alias) or alias in NOT_ALIASES:
        out.append(f"detach.alias = {alias!r} (the CLI word) is not a lowercase word of letters, digits and hyphens that the adapter accepts (not {', '.join(NOT_ALIASES)}); "
                   f"write the manifest by hand")
    if SECRET_KEY.search(m["env"]["prefix"]):
        out.append(f"env.prefix {m['env']['prefix']!r} contains a word the adapter reads as a secret (SECRET, TOKEN, PASSWORD, ACCESS_KEY, API_KEY, PRIVATE_KEY), so every "
                   f"config key we write would have to be `sensitive: true`; write the manifest and the SKILL.md keys by hand")
    if not RELPATH.fullmatch(m["cli"]["entry"]) or any(seg in ("", ".", "..") for seg in m["cli"]["entry"].split("/")):
        out.append(f"cli.entry = {m['cli']['entry']!r} is not a path of letters, digits, `_`, `.`, `-` and `/` inside the skill pack")
    return out


def config_keys(m: dict) -> list[tuple[str, str, str | None]]:
    """(name, description, default) of every key the adapter reads, from the manifest: the reply keys, the console's, what the tasks require, the defaults."""
    c, d = m["console"], m.get("defaults") or {}
    named = [(m["reply"]["channel"], "where the scheduled tasks report (a Zylos channel, e.g. lark); read by zylos/ only"),
             (m["reply"]["endpoint"], "the endpoint on that channel (e.g. the owner's chat id); read by zylos/ only"),
             (c["port_key"], f"the console's port on 127.0.0.1 (default {c['port']}); read by zylos/ only"),
             (c["title_key"], "the console's page title; read by zylos/ only"),
             (c["allow_host_key"], "the host's public domain, which the console answers to behind Caddy; read by zylos/ only")]
    named += [(k, "required by a scheduled task; read by zylos/ only") for t in m.get("tasks", []) for k in t.get("requires", [])]
    named += [(k, "has a default in the manifest; read by zylos/ only") for k in d if k != "_comment"]
    out, seen = [], set()
    for name, why in named:
        if name and name not in seen:
            seen.add(name)
            out.append((name, why, str(d[name]["value"]) if isinstance(d.get(name), dict) and "value" in d[name] else None))
    return out


def frontmatter_keys(m: dict, s: dict) -> str:
    """The Zylos keys of the SKILL.md frontmatter, as hosts/zylos/README.md lays them out. Everything the adapter's check compares comes from the manifest
    (the one that exists, if there is one), not from the toml."""
    cli = s["cli"]
    lines = [
        "# Zylos adapter (zylos/README.md); other hosts ignore the keys below.",
        f'next-steps: "Give post-install a 10-minute command timeout and relay its output to the owner. Then run `{cli} {m["scope"]["declare"]}` '
        f'with the owner, and set {m["reply"]["channel"]} / {m["reply"]["endpoint"]} through configure."',
        "bin:",
        f"  {m['cli']['bin']}: zylos/bin/cli.js",
        "lifecycle:",
        "  npm: false",
        "  hooks:",
        "    configure: zylos/hooks/configure.js",
        "    post-install: zylos/hooks/post-install.js",
        "    post-upgrade: zylos/hooks/post-upgrade.js",
        "    pre-uninstall: zylos/hooks/pre-uninstall.js",
        "  service:",
        f"    name: zylos-{m['name']}",
        "    entry: zylos/bin/console.js",
        "    type: pm2",
        "config:",
        "  required: []",
        "  optional:",
    ]
    for name, why, default in config_keys(m):
        lines += [f"    - name: {name}", f"      description: {why}"]
        if SECRET_KEY.search(name):
            lines.append("      sensitive: true")
        if default is not None:
            lines.append(f"      default: {default}")
    return "\n".join(lines)


def frontmatter_of(text: str) -> tuple[str, int] | None:
    """(the frontmatter's lines, where its closing `---` starts in text[4:]) or None: it must open with `---` and close on a line that is exactly `---`."""
    if not text.startswith("---\n"):
        return None
    close = re.search(r"^---$", text[4:], re.M)                                      # exactly `---`, as the adapter's own check reads it
    return (text[4:4 + close.start()], close.start()) if close else None


def skill_name(text: str) -> str | None:
    """The `name:` of the frontmatter as the adapter reads it (hosts/zylos/lib.js `topValue` and `unquote`): the text after the colon and any indented lines
    that follow, joined by spaces, quotes taken off, a trailing ` # comment` cut. None when there is no frontmatter or no name."""
    fm = frontmatter_of(text)
    if not fm:
        return None
    lines = fm[0].split("\n")
    at = next((i for i, ln in enumerate(lines) if ln.startswith("name:")), None)
    if at is None:
        return None
    head, rest = lines[at][5:].strip(), []
    for ln in lines[at + 1:]:
        if ln.strip() and not ln[:1].isspace():
            break
        if ln.strip():
            rest.append(ln.strip())
    if re.fullmatch(r"[>|][+-]?", head):
        return " ".join(rest)
    v = " ".join([head, *rest]).strip()
    if len(v) >= 2 and v[0] in "'\"" and v[-1] == v[0]:
        return v[1:-1]
    return re.sub(r"\s+#.*$", "", v)


def with_frontmatter(text: str, keys: str) -> tuple[str | None, str | None]:
    """(text with the Zylos keys at the end of its frontmatter, None), (None, None) when it has them already (`lifecycle:`), or (None, why) when it
    cannot be edited safely: no frontmatter, a closing delimiter not found, a top level that is not plain `key: value` lines, or one of the keys we
    would add is already there on its own."""
    if text.startswith("\ufeff"):
        return None, "SKILL.md starts with a byte-order mark: add the Zylos keys by hand (zylos/README.md, SKILL.md frontmatter)"
    if not text.startswith("---\n"):
        return None, "SKILL.md has no frontmatter: add one with the Zylos keys by hand (zylos/README.md)"
    fm = frontmatter_of(text)
    if not fm:
        return None, "SKILL.md's frontmatter has no closing line that is exactly `---` (the adapter's check reads no other): fix it, or add the Zylos keys by hand"
    head, close = fm
    top = [ln for ln in head.split("\n") if ln.strip() and not ln.startswith((" ", "\t", "#"))]
    keyed = [re.match(r"""^(?:([A-Za-z_][\w-]*)|"([A-Za-z_][\w-]*)"|'([A-Za-z_][\w-]*)')[ \t]*:(?:[ \t]|$)""", ln) for ln in top]
    if not all(keyed):
        return None, "SKILL.md's frontmatter has a top-level line that is not `key: value` (a flow mapping, an explicit `?` key, a list): add the Zylos keys by hand (zylos/README.md)"
    present = {next(g for g in m.groups() if g) for m in keyed}
    if "lifecycle" in present:
        return None, None
    clash = [k for k in OWNED_KEYS if k in present]
    if clash:
        return None, f"SKILL.md has its own {', '.join(f'`{k}:`' for k in clash)} without `lifecycle:`: merge the Zylos keys by hand (zylos/README.md)"
    return "---\n" + head.rstrip("\n") + "\n" + keys + "\n" + text[4 + close:], None


OPENS_BLOCK = re.compile(r"""^(?P<lead> *(?:- +)*)(?P<key>(?:"[^"]*"|'[^']*'|[^\s'"#][^#]*?):[ \t]+)?(?:[!&][^\s]*[ \t]+)*[|>][0-9+-]{0,2}[ \t]*(?:#.*)?$""")


def _outside_blocks(lines: list[str]) -> list[bool]:
    """For each line: is it outside a block scalar (`key: |`, `- run: >-`)? A line inside one is text, whatever it looks like."""
    out: list[bool] = []
    block = None                                                       # the column the lines of the open block must be indented past
    for ln in lines:
        if block is not None and (not ln.strip() or len(ln) - len(ln.lstrip(" ")) > block):
            out.append(False)
            continue
        block = None
        out.append(True)
        m = OPENS_BLOCK.match(ln)
        if m and not ln.lstrip().startswith("#"):
            block = len(m["lead"]) if m["key"] else len(ln) - len(ln.lstrip(" "))
    return out


def with_ci_step(text: str) -> tuple[str | None, str | None]:
    """(text of a GitHub workflow with Node 22 and the check as the last steps, None), (None, None) when it runs the check already, or (None, why) when
    its steps are not the end of the file: a job with none, a key after them (even at the items' own indent), steps written inline, a tab."""
    if CI_CHECK.search(text):
        return None, None
    lines = text.split("\n")
    plain = _outside_blocks(lines)
    if any("\t" in ln[:len(ln) - len(ln.lstrip())] for ln, p in zip(lines, plain) if p):
        return None, "ci.yml indents with a tab"
    at = [i for i, ln in enumerate(lines) if plain[i] and re.match(r"^ {0,6}steps:[ \t]*$", ln)]
    if not at:
        return None, "ci.yml has no `steps:` list to add to (a job that calls a reusable workflow, or steps written inline)"
    i = at[-1]
    steps_indent = len(lines[i]) - len(lines[i].lstrip(" "))
    after = range(i + 1, len(lines))
    content = [j for j in after if lines[j].strip() and plain[j] and not lines[j].lstrip().startswith("#")]
    if not content:
        return None, "ci.yml's last `steps:` list is empty"
    first = lines[content[0]]
    item = len(first) - len(first.lstrip(" "))
    if not first.lstrip().startswith("- ") or item < steps_indent:
        return None, "ci.yml's last `steps:` is not followed by a list"
    for j in content:
        ind = len(lines[j]) - len(lines[j].lstrip(" "))
        if ind < item or (ind == item and not lines[j].lstrip().startswith("-")):
            return None, "ci.yml has more after its last `steps:` list (a job key or a top-level key)"
    # the new steps go after the last line that is part of the list: a script block's lines count, a comment between items or after them does not
    last = max(j for j in after if lines[j].strip() and (not plain[j] or not lines[j].lstrip().startswith("#")))
    pad = " " * item
    lines[last + 1:last + 1] = [
        f"{pad}- uses: actions/setup-node@v7", f"{pad}  with:", f'{pad}    node-version: "22"', f"{pad}- name: Zylos adapter check",
        f"{pad}  run: node zylos/lib.js check"]
    return "\n".join(lines), None


class Unreadable(Exception):
    """A file this tool will not edit; the message finishes the sentence "<file> ...", the caller says what to do by hand."""


def _read(path: Path) -> tuple[str, bool]:
    """(text with LF line endings, whether the file used CRLF). A file that is not UTF-8, or mixes LF and CRLF (rewriting it would change lines we do not
    own), is Unreadable."""
    try:
        raw = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise Unreadable("is not UTF-8") from None
    except OSError as e:
        raise Unreadable(f"cannot be read ({e.strerror})") from None
    crlf = "\r\n" in raw
    if crlf and re.search(r"(?<!\r)\n", raw):
        raise Unreadable("mixes LF and CRLF line endings")
    return raw.replace("\r\n", "\n"), crlf


def _bytes(text: str, crlf: bool) -> bytes:
    return (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")


def link_in(skill_pack: Path, rel: str) -> str | None:
    """The first part of `rel` below the skill pack that is a link (a write there would go where the link points), else None."""
    p = skill_pack
    for part in Path(rel).parts:
        p = p / part
        if p.is_symlink():
            return p.relative_to(skill_pack).as_posix()
    return None


def unwritable(skill_pack: Path, rel: str) -> str | None:
    """Why `rel` cannot be written, or None: it is a folder, a parent of it is a file, or the place is read-only. A pre-flight; `add` still puts back
    what it wrote if a write fails after all."""
    to = skill_pack / rel
    if to.exists() and not to.is_file():
        return f"{rel} exists and is not a file"
    probe = to if to.exists() else to.parent
    while not probe.exists():
        probe = probe.parent
    if not to.exists() and not probe.is_dir():
        return f"{probe.relative_to(skill_pack).as_posix()} is a file, not a folder"
    if not os.access(probe, os.W_OK | (0 if probe.is_file() else os.X_OK)):
        return f"{probe.relative_to(skill_pack).as_posix() if probe != skill_pack else '.'} is not writable"
    return None


def plan(skill_pack: Path, *, brand: str, port: int | None) -> tuple[list[tuple[str, bytes, int | None]], list[str], list[str]]:
    """(the writes as (relative path, content, mode), the notes to print, the lines for what is created or changed). Reads only; refuses (exit 1 with a
    line) before anything is written."""
    s = settings(skill_pack)
    if not fits("brand", brand):
        raise refuse(f"--brand {brand!r} is not lowercase letters and digits")
    if port is not None and not (isinstance(port, int) and 1024 <= port <= 65535):
        raise refuse(f"--port {port!r} is not a port from 1024 to 65535")
    dest = skill_pack / "zylos"
    if dest.is_symlink():
        raise refuse(f"{dest} is a link: it would write outside the skill pack")
    entry = entry_for(skill_pack, s)
    writes: list[tuple[str, bytes, int | None]] = []
    notes: list[str] = []
    mf = dest / "manifest.json"
    if mf.is_file():
        try:
            m = json.loads(mf.read_text("utf-8"))
            m["name"], m["cli"]["bin"], m["console"]["port"]
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise refuse(f"zylos/manifest.json is not a manifest this tool can read ({e.__class__.__name__}): fix it, or delete it to have a new one written") from None
        if port is not None or brand != BRAND:
            notes.append("zylos/manifest.json exists, so --port and --brand are ignored")
    else:
        m = manifest_for(s, entry, brand, port or default_port(s["name"]))
        bad = problems(m)
        if bad:
            raise refuse("the manifest would not pass the adapter's check, nothing was written: " + "; ".join(bad))
        writes.append(("zylos/manifest.json", (json.dumps(m, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), None))
    for rel in fleet.files(SOURCE, fleet.ZYLOS_NOT_COPIED | fleet.ZYLOS_OWN):
        src, to = SOURCE / rel, dest / rel
        if not (to.is_file() and to.read_bytes() == src.read_bytes()):
            writes.append((f"zylos/{rel}", src.read_bytes(), src.stat().st_mode & 0o777))
    skill = skill_pack / "SKILL.md"
    if link_in(skill_pack, "SKILL.md"):
        notes.append("SKILL.md is a link: it is not edited through it; add the Zylos keys to the file it points at by hand (zylos/README.md)")
    elif skill.is_file():
        try:
            text, crlf = _read(skill)
        except Unreadable as e:
            notes.append(f"SKILL.md {e}: add the Zylos keys by hand (zylos/README.md)")
        else:
            named = skill_name(text)
            if named is not None and named != m["name"]:
                raise refuse(f"SKILL.md name is {named!r} but the component's is {m['name']!r}: the adapter's check wants the same name in both; fix one, nothing was written")
            new, note = with_frontmatter(text, frontmatter_keys(m, s))
            if note:
                notes.append(note)
            if new is not None:
                writes.append(("SKILL.md", _bytes(new, crlf), None))
    else:
        notes.append("there is no SKILL.md: the Zylos keys go in its frontmatter once it exists")
    if not (skill_pack / "ecosystem.config.cjs").is_file():
        writes.append(("ecosystem.config.cjs", (SOURCE / "ecosystem.config.cjs.template").read_bytes(), None))
    ci = skill_pack / ".github" / "workflows" / "ci.yml"
    if link_in(skill_pack, ".github/workflows/ci.yml"):
        notes.append(".github/workflows/ci.yml is, or sits under, a link: it is not edited; add Node 22 and `node zylos/lib.js check` by hand")
    elif ci.is_file():
        try:
            text, crlf = _read(ci)
        except Unreadable as e:
            notes.append(f"ci.yml {e}: add Node 22 and `node zylos/lib.js check` by hand")
        else:
            new, note = with_ci_step(text)
            if note:
                notes.append(f"{note}; add Node 22 and `node zylos/lib.js check` by hand")
            if new is not None:
                writes.append((".github/workflows/ci.yml", _bytes(new, crlf), None))
    if (skill_pack / ".gitlab-ci.yml").is_file():
        notes.append(".gitlab-ci.yml is not edited: add `node zylos/lib.js check` to it by hand (Node 22 or newer)")
    for rel, _, _ in writes:
        via = link_in(skill_pack, rel)
        if via:
            raise refuse(f"{rel} is, or sits under, the link {via}: it would write outside its own place in the skill pack; nothing was written")
        why = unwritable(skill_pack, rel)
        if why:
            raise refuse(f"{rel} cannot be written ({why}); nothing was written")
    return writes, notes, [rel for rel, _, _ in writes]


def _write(to: Path, data: bytes, mode: int | None) -> None:
    to.write_bytes(data)
    if mode is not None:
        to.chmod(mode)


def add(skill_pack: Path, *, brand: str = BRAND, port: int | None = None, dry_run: bool = False) -> tuple[list[str], list[str]]:
    """(the files created or changed, the notes): everything is planned before the first write, and a write that fails puts back what was written."""
    writes, notes, done = plan(skill_pack, brand=brand, port=port)
    if dry_run:
        return done, notes
    undo: list[tuple[Path, bytes | None, int]] = []                    # (file, its bytes before or None if it is new, its mode before)
    made: list[Path] = []                                              # folders this run created
    try:
        for rel, data, mode in writes:
            to = skill_pack / rel
            new_dirs, d = [], to.parent
            while not d.exists():
                new_dirs.append(d)
                d = d.parent
            for d in reversed(new_dirs):
                d.mkdir()
                made.append(d)
            undo.append((to, to.read_bytes() if to.is_file() else None, to.stat().st_mode & 0o777 if to.is_file() else 0o644))
            _write(to, data, mode)
    except BaseException as e:                                          # a failed write, or Ctrl-C / SIGTERM halfway: the same way back
        stuck = []
        for to, old, was in reversed(undo):
            try:
                if old is None:
                    to.unlink(missing_ok=True)
                else:
                    to.write_bytes(old)
                    to.chmod(was)
            except OSError:
                stuck.append(to.relative_to(skill_pack).as_posix())
        for d in reversed(made):
            try:
                d.rmdir()
            except OSError:
                pass
        left = f"; these could not be put back, fix them by hand: {', '.join(stuck)}" if stuck else "; what was written before it was put back"
        if not isinstance(e, OSError):
            raise
        raise refuse(f"a write failed ({e.strerror or e.__class__.__name__}: {e.filename}){left}") from None
    return done, notes


def check(skill_pack: Path) -> tuple[int, str]:
    """`node zylos/lib.js check` in the skill pack: (exit code, its output); without node on PATH (0, a line that says the check did not run)."""
    node = shutil.which("node")
    if not node:
        return 0, "note: node is not on PATH, so the adapter's check did not run; run `node zylos/lib.js check` where node is"
    r = subprocess.run([node, "zylos/lib.js", "check"], cwd=skill_pack, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Set a skill pack up to run as a Zylos component.")
    ap.add_argument("--skill-pack", required=True, type=Path)
    ap.add_argument("--brand", default=BRAND, help=f"the word before the CLI in the linked command (default {BRAND})")
    ap.add_argument("--port", type=int, help="the console's port on 127.0.0.1, 1024 to 65535 (default: 8800 plus a hash of the name)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    sp = a.skill_pack.resolve()
    try:
        done, notes = add(sp, brand=a.brand, port=a.port, dry_run=a.dry_run)
    except (OSError, TypeError, AttributeError, KeyError, ValueError) as e:       # an input the tool did not foresee: one line, and nothing half done (add puts back)
        raise refuse(f"{e.__class__.__name__}: {e}") from None
    for line in done:
        print(f"  {'would write' if a.dry_run else 'wrote'}  {line}")
    for line in notes:
        print(f"  note   {line}")
    print(f"zylos: {len(done)} {'would change' if a.dry_run else 'changed'} in {sp.name}" if done else f"zylos: nothing to do in {sp.name}")
    if a.dry_run:
        return 0
    code, out = check(sp)
    if out:
        print(out)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
