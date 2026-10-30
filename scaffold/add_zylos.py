#!/usr/bin/env python3
"""Set a skill pack up to run as a Zylos component: copy the adapter, write the manifest, the SKILL.md keys and the root ecosystem file.

    python3 scaffold/add_zylos.py --skill-pack PATH [--brand openmax] [--port N] [--dry-run]

What hosts/zylos/README.md says a skill pack does by hand, in one command, from what skill-pack.toml already says (name, cli, env prefix,
scripts folder):

  * copies the adapter files (the list is tools/fleet.py's: everything but the adapter's tests and its two templates) into `zylos/`;
  * writes `zylos/manifest.json` when there is none: the example's runtime pins, the CLI link `<brand>-<cli>`, the console on
    127.0.0.1:PORT under `/<cli>`, and no scheduled task (tasks are the skill pack's own prompts: it adds them);
  * adds the Zylos keys to the `SKILL.md` frontmatter when it has none of them (`lifecycle:`); the file's other keys and its body stay;
  * writes the root `ecosystem.config.cjs` from the template when there is none;
  * adds Node 22 and `node zylos/lib.js check` to `.github/workflows/ci.yml` when that file exists and does not run it yet.

It never overwrites a manifest, a frontmatter that has Zylos keys or an ecosystem file: a skill pack that has them is left as it is, and
`python3 tools/fleet.py update` keeps the adapter copy current. Then `node zylos/lib.js check` runs, when node is on PATH, and its verdict is
the exit code.

The port is the one thing two skill packs on one host must not share: default 8800 plus a hash of the name, in 8800 to 9799; pass --port
to choose. The brand is the word before the CLI in the linked command (`openmax-seo`); a generic command name clashes on a host.

Test: scaffold/tests/test_add_zylos.py.
"""

from __future__ import annotations

import argparse
import json
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
CI_STEP = "node zylos/lib.js check"


def settings(skill_pack: Path) -> dict:
    """name, cli, prefix and the scripts folder of the skill pack, from its skill-pack.toml."""
    toml = skill_pack / "skill-pack.toml"
    if not toml.is_file():
        raise SystemExit(f"error: {toml} is missing: this is not a skill pack")
    h = tomllib.loads(toml.read_text("utf-8")).get("skill_pack", {})
    got = {"name": h.get("name"), "cli": h.get("cli"), "prefix": h.get("env_prefix"),
           "scripts": str(h.get("scripts_dir") or "scripts")}
    missing = [k for k in ("name", "cli", "prefix") if not got[k]]
    if missing:
        raise SystemExit(f"error: skill-pack.toml [skill_pack] has no {', '.join(missing)}")
    return got


def default_port(name: str) -> int:
    return 8800 + zlib.crc32(name.encode()) % 1000


def entry_for(skill_pack: Path, s: dict) -> str:
    """The CLI script inside the skill pack: scripts/<cli>.py, else the one file the toml's cli word names at the root."""
    for rel in (f"{s['scripts']}/{s['cli']}.py", f"{s['cli']}.py", "skill_pack.py"):
        if (skill_pack / rel).is_file():
            return rel
    raise SystemExit(f"error: no CLI script found for '{s['cli']}' (tried {s['scripts']}/{s['cli']}.py, {s['cli']}.py, skill_pack.py)")


def manifest_for(s: dict, entry: str, brand: str, port: int) -> dict:
    """A manifest that passes `check`: the example's runtime pins, the skill pack's own names, no scheduled task."""
    example = json.loads((SOURCE / "manifest.example.json").read_text("utf-8"))
    p, cli = s["prefix"], s["cli"]
    return {
        "name": s["name"],
        "min_zylos": example["min_zylos"],
        "cli": {"bin": f"{brand}-{cli}", "entry": entry, "doctor": ["doctor"]},
        "env": {"prefix": p, "data_dir": f"{p}_DATA_DIR", "files": [f"~/.{cli}.env"]},
        "runtime": example["runtime"],
        "endpoints": [],
        "scope": {"list": ["facts", "list", "--json"], "field": "declared_markets", "declare": "facts init"},
        "reply": {"channel": f"{p}_REPLY_CHANNEL", "endpoint": f"{p}_REPLY_ENDPOINT"},
        "console": {"entry": "console/serve.py", "port": port, "port_key": f"{p}_CONSOLE_PORT", "title_key": f"{p}_CONSOLE_TITLE",
                    "base_path": f"/{cli}", "user_header": "X-Remote-User", "users_file": "console.users",
                    "args": ["--relay-verbs", "facts confirm,decisions confirm", "--lang", "en"],
                    "allow_host_key": f"{p}_CONSOLE_ALLOW_HOST"},
        "detach": {"exit_marker": f"{p}-EXIT", "alias": cli},
        "tasks": [],
    }


def frontmatter_keys(m: dict, s: dict) -> str:
    """The Zylos keys of the SKILL.md frontmatter, as hosts/zylos/README.md lays them out."""
    p, cli = s["prefix"], s["cli"]
    return "\n".join([
        "",
        "# Zylos adapter (zylos/README.md); other hosts ignore the keys below.",
        f'next-steps: "Give post-install a 10-minute command timeout and relay its output to the owner. Then run `{cli} facts init` '
        f'with the owner, and set {p}_REPLY_CHANNEL / {p}_REPLY_ENDPOINT through configure."',
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
        f"    - name: {p}_REPLY_CHANNEL",
        "      description: where the scheduled tasks report (a Zylos channel, e.g. lark); read by zylos/ only",
        f"    - name: {p}_REPLY_ENDPOINT",
        "      description: the endpoint on that channel (e.g. the owner's chat id); read by zylos/ only",
        f"    - name: {p}_CONSOLE_PORT",
        f"      description: the console's port on 127.0.0.1 (default {m['console']['port']}); read by zylos/ only",
        f"    - name: {p}_CONSOLE_TITLE",
        "      description: the console's page title; read by zylos/ only",
        f"    - name: {p}_CONSOLE_ALLOW_HOST",
        "      description: the host's public domain, which the console answers to behind Caddy; read by zylos/ only",
    ])


def with_frontmatter(text: str, keys: str) -> str | None:
    """`text` with the Zylos keys at the end of its frontmatter; None when it has no frontmatter or already has `lifecycle:`."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m or re.search(r"^lifecycle:", m.group(1), re.M):
        return None
    return f"---\n{m.group(1)}{keys}\n---\n" + text[m.end():]


def with_ci_step(text: str) -> str | None:
    """`text` of a GitHub workflow with the check as the last step of its last job; None when it runs it already or has no `steps:`."""
    if CI_STEP in text or "steps:" not in text:
        return None
    lines = text.rstrip("\n").split("\n")
    last = max(i for i, ln in enumerate(lines) if re.match(r"\s+steps:\s*$", ln))
    indent = re.match(r"\s*", lines[last + 1]).group(0) if last + 1 < len(lines) else "      "
    return ("\n".join(lines) + f"\n{indent}- uses: actions/setup-node@v7\n{indent}  with:\n{indent}    node-version: \"22\"\n"
            f"{indent}- name: Zylos adapter check\n{indent}  run: {CI_STEP}\n")


def add(skill_pack: Path, *, brand: str = BRAND, port: int | None = None, dry_run: bool = False) -> list[str]:
    """Do the five things above; return one line for each that changed something."""
    s = settings(skill_pack)
    entry = entry_for(skill_pack, s)
    m = manifest_for(s, entry, brand, port or default_port(s["name"]))
    done: list[str] = []
    dest = skill_pack / "zylos"
    for rel in fleet.files(SOURCE, fleet.ZYLOS_NOT_COPIED | fleet.ZYLOS_OWN):
        src, to = SOURCE / rel, dest / rel
        if to.is_file() and to.read_bytes() == src.read_bytes():
            continue
        done.append(f"zylos/{rel}")
        if not dry_run:
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, to)
            shutil.copymode(src, to)
    mf = dest / "manifest.json"
    if not mf.is_file():
        done.append("zylos/manifest.json")
        if not dry_run:
            mf.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        m = json.loads(mf.read_text("utf-8"))
    skill = skill_pack / "SKILL.md"
    if skill.is_file():
        new = with_frontmatter(skill.read_text("utf-8"), frontmatter_keys(m, s))
        if new is not None:
            done.append("SKILL.md frontmatter")
            if not dry_run:
                skill.write_text(new, encoding="utf-8")
    eco = skill_pack / "ecosystem.config.cjs"
    if not eco.is_file():
        done.append("ecosystem.config.cjs")
        if not dry_run:
            shutil.copyfile(SOURCE / "ecosystem.config.cjs.template", eco)
    ci = skill_pack / ".github" / "workflows" / "ci.yml"
    if ci.is_file():
        new = with_ci_step(ci.read_text("utf-8"))
        if new is not None:
            done.append(".github/workflows/ci.yml")
            if not dry_run:
                ci.write_text(new, encoding="utf-8")
    return done


def check(skill_pack: Path) -> tuple[int, str]:
    """`node zylos/lib.js check` in the skill pack: (exit code, its output); (0, "") without node on PATH."""
    node = shutil.which("node")
    if not node:
        return 0, ""
    r = subprocess.run([node, "zylos/lib.js", "check"], cwd=skill_pack, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Set a skill pack up to run as a Zylos component.")
    ap.add_argument("--skill-pack", required=True, type=Path)
    ap.add_argument("--brand", default=BRAND, help=f"the word before the CLI in the linked command (default {BRAND})")
    ap.add_argument("--port", type=int, help="the console's port on 127.0.0.1 (default: 8800 plus a hash of the name)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    sp = a.skill_pack.resolve()
    done = add(sp, brand=a.brand, port=a.port, dry_run=a.dry_run)
    for line in done:
        print(f"  {'would write' if a.dry_run else 'wrote'}  {line}")
    print(f"zylos: {len(done)} {'would change' if a.dry_run else 'changed'} in {sp.name}" if done else f"zylos: nothing to do in {sp.name}")
    if a.dry_run:
        return 0
    code, out = check(sp)
    if out:
        print(out)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
