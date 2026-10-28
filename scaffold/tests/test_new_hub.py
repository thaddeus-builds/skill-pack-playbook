#!/usr/bin/env python3
"""scaffold/new_hub.py: one client's hub, and the packs that serve it.

  [1] `new --dry-run` lists the files and writes nothing
  [2] `new`: CLIENT.md (fill rows, an empty pack table, the console's port
      row), intake/README.md, INDEX.tsv header, inbox/, client_terms.txt
      0600, hub.json; bin/hub, bin/console, bin/ask executable and parsing;
      no `{{`; launch.json and bin/console on the chosen port; a console
      with no pack yet relays only the hub's own `hub facts confirm`
      exchange/README.md and exchange/.gitkeep; a document written there by
      kit.raw.exchange_write is listed, and the folder has no stray
  [3] `add-pack` writes a pack folder from new_client.py's files() with no
      console of its own (no bin/console, bin/ask, launch.json), its brief
      pointing at the hub's console, ask and intake; `bin/hub <cli> …`
      runs that pack's wrapper on its workspace, argv and env passed through
  [4] `add-pack --link` links an existing client workspace (relative
      symlink, never written) and records its old console port
  [5] the relay verb list is `<cli> facts confirm,<cli> decisions
      confirm,<cli> queue approve` per pack, through bin/hub; the deny list
      holds every gate verb of every pack (through bin/hub and through the
      pack wrapper) and hand edits, not a human verb; a rule added by hand
      stays; each console start puts a fresh secret per pack in the
      console's env only, written to no file
  [6] .gitignore: content, console log, hub data, client terms and every
      pack folder ignored; CLIENT.md, intake README/INDEX, exchange README
      and .gitkeep, bin/, hub.json and .claude/ are not; an exchange
      document is
  [7] refusals, exit 2 with one line, the hub untouched: `new` on a
      non-empty folder, a bad id, a path the relay cannot carry; `add-pack`
      of a pack already present, to a non-hub, onto an existing folder, a
      --link with no bin/<cli>
  [8] the port: the first from 8770 that is not bound and no sibling hub's
      CLIENT.md or launch.json (or a per-pack workspace's, one deeper)
      names; a second hub in the same root gets another port
"""

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PLAYBOOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLAYBOOK))
sys.path.insert(0, str(PLAYBOOK / "scaffold"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull

from kit import config, raw  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402
import new_hub  # noqa: E402

HUB_PY = PLAYBOOK / "scaffold" / "new_hub.py"
CLIENT_PY = PLAYBOOK / "scaffold" / "new_client.py"
GATED = {"demoa": ["facts confirm", "facts restore", "decisions confirm", "queue approve"],
         "demob": ["facts confirm", "facts init", "decisions confirm", "queue approve",
                   "execute apply"]}
ENTRY = """import json, os, sys
P = {prefix!r}
if sys.argv[1:] == ["verbs", "--json"]:
    print(json.dumps({verbs}))
else:
    print(json.dumps({{"data_dir": os.environ.get(P + "_DATA_DIR"), "argv": sys.argv[1:],
                      "secret": os.environ.get(P + "_CONFIRM_CODE_SECRET"),
                      "hub_dir": os.environ.get(P + "_HUB_DIR"),
                      "hub_market": os.environ.get(P + "_HUB_MARKET"),
                      "hub_cli": os.environ.get(P + "_HUB_CLI")}}))
"""
SERVE = """import json, os, sys
print(json.dumps({"argv": sys.argv[1:], "console_dir": os.environ.get("CONSOLE_DIR"),
                  "secrets": {k: v for k, v in os.environ.items()
                              if k.endswith("_CONFIRM_CODE_SECRET")}}))
"""


def fake_pack(cli: str) -> Path:
    prefix = cli.upper()
    verbs = {"skill_pack": f"{cli}-skill-pack", "cli": cli, "verbs": [
        {"words": ["status"], "kind": "read"},
        {"words": ["facts", "set"], "kind": "human"}] + [
        {"words": g.split(), "kind": "gated"} for g in GATED[cli]]}
    h = Path(tmp_dir(f"fake-{cli}-")) / f"{cli}-skill-pack"
    (h / "scripts").mkdir(parents=True)
    (h / "skill-pack.toml").write_text(
        f'[skill_pack]\nname = "{cli}-skill-pack"\ncli = "{cli}"\n'
        f'env_prefix = "{prefix}"\nscripts_dir = "scripts"\n', encoding="utf-8")
    (h / "scripts" / f"{cli}.py").write_text(
        ENTRY.format(prefix=prefix, verbs=json.dumps(verbs)), encoding="utf-8")
    return h


def clean_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("DEMOA_", "DEMOB_", "HUB_"))}
    return {**env, "DEMOA_PYTHON": sys.executable, "DEMOB_PYTHON": sys.executable,
            "HUB_PYTHON": sys.executable, **extra}


def run(script: Path, *argv: str) -> tuple[int, str, str]:
    r = subprocess.run([sys.executable, str(script), *argv], capture_output=True,
                       text=True, timeout=120, env=clean_env())
    return r.returncode, r.stdout, r.stderr


def snapshot(d: Path) -> dict:
    return {str(p.relative_to(d)): (p.read_bytes() if p.is_file() and not p.is_symlink()
                                    else os.readlink(p) if p.is_symlink() else None)
            for p in sorted(d.rglob("*"))}


def texts(d: Path) -> dict:
    return {str(p.relative_to(d)): p.read_text(encoding="utf-8")
            for p in d.rglob("*") if p.is_file() and not p.is_symlink()
            and ".git" not in p.relative_to(d).parts
            and not p.name.startswith("hub.db")}       # the store `new` makes


def main() -> int:
    root = Path(tmp_dir("workspaces-")).resolve()
    home = Path(tmp_dir("console-home-")).resolve()
    (home / "serve.py").write_text(SERVE, encoding="utf-8")
    (home / "ask.py").write_text(
        'import os; print(os.environ.get("CONSOLE_DIR"))\n', encoding="utf-8")
    pa, pb = fake_pack("demoa"), fake_pack("demob")
    hub = root / "northwind"
    new = ["new", "--hub", str(hub), "--title", "Northwind Tea", "--lang", "zh",
           "--language", "Traditional Chinese", "--console-home", str(home)]

    print("[1] new --dry-run")
    rc, out, err = run(HUB_PY, *new, "--dry-run")
    check("lists the files, writes nothing", rc == 0 and "would write" in out
          and "bin/hub" in out and not hub.exists(), out + err)

    print("[2] new")
    rc, out, err = run(HUB_PY, *new)
    check("written", rc == 0 and hub.is_dir(), out + err)
    t = texts(hub)
    port = json.loads(t["hub.json"])["port"]
    for b in ("bin/hub", "bin/console", "bin/ask"):
        check(f"{b} is executable", os.access(hub / b, os.X_OK))
        r = subprocess.run(["sh", "-n", str(hub / b)], capture_output=True, text=True)
        check(f"{b} parses (sh -n)", r.returncode == 0, r.stderr)
    check("no `{{` left anywhere", not any("{{" in v for v in t.values()),
          [k for k, v in t.items() if "{{" in v])
    cm = t["CLIENT.md"]
    check("CLIENT.md: fill rows, a pack table, the console's port row",
          cm.count("<<fill:") >= 5 and new_hub.PACK_HEADER in cm
          and f"| {port} | this hub's console (`bin/console`) |" in cm, cm)
    check("intake: README, INDEX.tsv header, inbox/",
          "inbox/<YYYY-MM-DD>-<source>/" in t["intake/README.md"]
          and t["intake/INDEX.tsv"].startswith("id\tdate\tsource\t")
          and (hub / "intake" / "inbox" / ".gitkeep").is_file())
    check("exchange: a README that says write once, and a .gitkeep",
          "A producer writes a file once" in t["exchange/README.md"]
          and "exchange_write" in t["exchange/README.md"]
          and (hub / "exchange" / ".gitkeep").is_file())
    config.use(PLAYBOOK / "kit" / "tests" / "fake_skill_pack")     # a pack binds the kit like this
    doc = raw.exchange_write(hub, "ads.results/1", "demoa", "2026-10-23", b"{}")
    check("a pack writes there with the kit; the folder lists it and has no stray",
          raw.exchange_scan(hub)[0] == raw.exchange_list(hub, "ads.results/1")
          and [d.path for d in raw.exchange_list(hub, "ads.results/1")] == [doc]
          and raw.exchange_scan(hub)[1] == [])
    check("client_terms.txt is 0600 and names the client",
          stat.S_IMODE((hub / "client_terms.txt").stat().st_mode) == 0o600
          and "Northwind Tea" in t["client_terms.txt"])
    launch = json.loads(t[".claude/launch.json"])["configurations"][0]
    check("launch.json and bin/console use the chosen port (from 8770)",
          port >= 8770 and launch["port"] == port
          and launch["runtimeArgs"] == [str(hub / "bin" / "console")]
          and f'--port "${{HUB_CONSOLE_PORT:-{port}}}"' in t["bin/console"], (port, launch))
    r = subprocess.run([str(hub / "bin" / "console")], capture_output=True, text=True,
                       timeout=60, env=clean_env())
    doc = json.loads(r.stdout or "{}")
    argv = doc.get("argv", [])
    check("a console with no pack yet runs and relays only the hub's own "
          "facts confirm, with its secret",
          r.returncode == 0 and "--relay-verbs" in argv
          and argv[argv.index("--relay-verbs") + 1] == "hub facts confirm"
          and doc.get("console_dir") == str(hub / "console")
          and set(doc.get("secrets") or {}) == {"HUB_CONFIRM_CODE_SECRET"},
          r.stdout + r.stderr)
    r = subprocess.run([str(hub / "bin" / "ask")], capture_output=True, text=True,
                       timeout=60, env=clean_env())
    check("bin/ask is pinned to the hub's console/",
          r.stdout.strip() == str(hub / "console"), r.stdout + r.stderr)

    print("[3] add-pack (a folder written here)")
    rc, out, err = run(HUB_PY, "add-pack", "--hub", str(hub), "--skill-pack", str(pa))
    pf = hub / "demoa"
    check("written", rc == 0 and pf.is_dir() and not pf.is_symlink(), out + err)
    check("the pack folder has its wrapper, brief and deny list, no console of its own",
          os.access(pf / "bin" / "demoa", os.X_OK) and (pf / "CLAUDE.md").is_file()
          and (pf / ".claude" / "settings.json").is_file()
          and not any((pf / x).exists() for x in
                      ("bin/console", "bin/ask", ".claude/launch.json")),
          sorted(str(p.relative_to(pf)) for p in pf.rglob("*")))
    brief = (pf / "CLAUDE.md").read_text(encoding="utf-8")
    check("its brief points at the hub's console, ask and intake, on the hub's port",
          "./bin/console" not in brief.replace("../bin/console", "")
          and "./bin/ask" not in brief.replace("../bin/ask", "")
          and "`../bin/console`" in brief and "`../bin/ask add FILE`" in brief
          and f"http://127.0.0.1:{port}/" in brief and "`../intake/`" in brief
          and "`workspace/intake/`" not in brief and "`../bin/hub demoa …`" in brief
          and "Traditional Chinese" in brief and "{{" not in brief, brief)
    check("its workspace/ is 0700",
          stat.S_IMODE((pf / "workspace").stat().st_mode) == 0o700)
    r = subprocess.run([str(hub / "bin" / "hub"), "demoa", "status", "--json"],
                       capture_output=True, text=True, timeout=60,
                       env=clean_env(DEMOA_CONFIRM_CODE_SECRET="s3"))
    doc = json.loads(r.stdout or "{}")
    check("bin/hub demoa … runs demoa/bin/demoa on its workspace, argv and env passed",
          os.path.realpath(doc.get("data_dir") or "") == str((pf / "workspace").resolve())
          and doc.get("argv") == ["status", "--json"] and doc.get("secret") == "s3",
          r.stdout + r.stderr)
    check("… with DEMOA_HUB_DIR = the hub (sync-hub and doctor read it)",
          os.path.realpath(doc.get("hub_dir") or "") == str(hub.resolve()), doc)
    r = subprocess.run([str(hub / "bin" / "hub"), "nope"], capture_output=True,
                       text=True, timeout=60, env=clean_env())
    check("bin/hub with an unknown CLI word: exit 2, names the packs",
          r.returncode == 2 and "demoa" in r.stderr, r.stderr)
    cm = (hub / "CLIENT.md").read_text(encoding="utf-8")
    check("CLIENT.md gets the pack's row",
          "| demoa-skill-pack | `demoa` | `demoa/` | `facts confirm`, "
          "`decisions confirm`, `queue approve` |" in cm, cm)
    # a rule the owner added by hand between two add-packs
    sp = hub / ".claude" / "settings.json"
    s = json.loads(sp.read_text(encoding="utf-8"))
    s["permissions"]["allow"] = ["Bash(git status)"]
    s["permissions"]["deny"].append("Bash(rm -rf:*)")
    sp.write_text(json.dumps(s), encoding="utf-8")

    print("[4] add-pack --link (an existing client workspace)")
    clients = root / "demob-skill-pack"
    rc, out, err = run(CLIENT_PY, "--skill-pack", str(pb), "--clients", str(clients),
                       "--client", "northwind", "--title", "Northwind", "--port", "8799")
    existing = clients / "northwind"
    check("an existing workspace made by new_client.py", rc == 0, out + err)
    before = snapshot(existing)
    rc, out, err = run(HUB_PY, "add-pack", "--hub", str(hub), "--skill-pack", str(pb),
                       "--folder", "demob", "--link", str(existing))
    link = hub / "demob"
    check("linked with a relative symlink", rc == 0 and link.is_symlink()
          and not os.path.isabs(os.readlink(link))
          and link.resolve() == existing.resolve(), out + err)
    check("the linked workspace is not written", snapshot(existing) == before)
    cm = (hub / "CLIENT.md").read_text(encoding="utf-8")
    check("CLIENT.md: the pack's row names the link; its old console port is a port row",
          "| demob-skill-pack | `demob` | `demob/` → `../demob-skill-pack/northwind` |" in cm
          and re.search(r"^\| 8799 \| `demob`: the linked workspace's own console", cm, re.M),
          cm)
    r = subprocess.run([str(hub / "bin" / "hub"), "demob", "status"], capture_output=True,
                       text=True, timeout=60, env=clean_env())
    doc = json.loads(r.stdout or "{}")
    check("bin/hub demob … runs the linked wrapper",
          os.path.realpath(doc.get("data_dir") or "")
          == str((existing / "workspace").resolve()), r.stdout + r.stderr)

    print("[5] the console's relay verbs, the deny list, the secrets")
    t = texts(hub)
    want = ("hub facts confirm,"
            "demoa facts confirm,demoa decisions confirm,demoa queue approve,"
            "demob facts confirm,demob decisions confirm,demob queue approve")
    check("the console relays every pack's confirm / approve verbs through bin/hub",
          f'--relay-cmd "$root/bin/hub" --relay-verbs "{want}"' in t["bin/console"],
          t["bin/console"])
    deny = json.loads(t[".claude/settings.json"])["permissions"]["deny"]
    missing = [f"Bash({c} {g}:*)" for cli in GATED for g in GATED[cli]
               for c in (f"./bin/hub {cli}", f"bin/hub {cli}", f"{hub}/bin/hub {cli}",
                         f"./{cli}/bin/{cli}", f"{cli}/bin/{cli}")
               if f"Bash({c} {g}:*)" not in deny]
    check("every gate verb of every pack is denied, through bin/hub and the wrapper",
          not missing, missing)
    check("execute apply and facts restore are denied but not relayed",
          "demob execute apply" not in t["bin/console"]
          and "demoa facts restore" not in t["bin/console"]
          and "Bash(bin/hub demob execute apply:*)" in deny)
    check("a human verb is not denied", not any("facts set" in d for d in deny), deny)
    check("hand edits under each pack's workspace, console/ and hub/ are denied",
          {"Edit(./demoa/workspace/**)", "Write(./demob/workspace/**)",
           "Read(./demob/workspace/.env)", "Edit(./hub/**)", "Write(./console/**)"}
          <= set(deny), deny)
    s = json.loads(t[".claude/settings.json"])
    check("rules added by hand stay", s["permissions"].get("allow") == ["Bash(git status)"]
          and "Bash(rm -rf:*)" in deny and len(deny) == len(set(deny)), s)
    runs = []
    for _ in range(2):
        r = subprocess.run([str(hub / "bin" / "console")], capture_output=True,
                           text=True, timeout=60, env=clean_env())
        runs.append(json.loads(r.stdout or "{}"))
    sec = [d.get("secrets", {}) for d in runs]
    hexes = [v for s_ in sec for v in s_.values()]
    check("each start: one fresh 64-hex secret per pack, in the console's env",
          all(set(s_) == {"HUB_CONFIRM_CODE_SECRET", "DEMOA_CONFIRM_CODE_SECRET",
                          "DEMOB_CONFIRM_CODE_SECRET"} for s_ in sec)
          and all(re.fullmatch(r"[0-9a-f]{64}", v) for v in hexes)
          and len(set(hexes)) == 6, sec)
    on_disk = [p for p in hub.rglob("*") if p.is_file()
               and any(v.encode() in p.read_bytes() for v in hexes)]
    on_disk += [p for p in existing.rglob("*") if p.is_file()
                and any(v.encode() in p.read_bytes() for v in hexes)]
    check("no secret is written to any file", not on_disk and ".env" not in t["bin/console"],
          on_disk)
    argv = runs[0].get("argv", [])
    check("the console runs with --relay-cmd <hub>/bin/hub and the verb list",
          argv[argv.index("--relay-cmd") + 1] == str(hub / "bin" / "hub")
          and argv[argv.index("--relay-verbs") + 1] == want
          and argv[argv.index("--title") + 1] == "Northwind Tea"
          and argv[argv.index("--lang") + 1] == "zh", argv)

    print("[6] .gitignore")
    subprocess.run(["git", "init", "-q", str(hub)], check=True, capture_output=True)

    def ignored(rel: str) -> bool:
        return subprocess.run(["git", "-C", str(hub), "check-ignore", "-q", rel],
                              capture_output=True).returncode == 0
    yes = ["client_terms.txt", "console/events.jsonl", "hub/hub.db", "demoa", "demob",
           "demoa/workspace/x.db", "intake/inbox/2026-10-22-client/brief.pdf",
           "intake/2026-10-22.json", "intake/numbers.tsv", "intake/questions.tsv",
           "exchange/ads.results/1/demoa/2026-10-23.json"]
    no = ["CLIENT.md", "hub.json", "bin/hub", "bin/console", ".claude/settings.json",
          ".claude/launch.json", "intake/README.md", "intake/INDEX.tsv",
          "intake/inbox/.gitkeep", "exchange/README.md", "exchange/.gitkeep", ".gitignore"]
    check("content, console log, hub data, terms and pack folders are ignored",
          all(ignored(x) for x in yes), [x for x in yes if not ignored(x)])
    check("CLIENT.md, intake and exchange README, bin/, hub.json, .claude/ are tracked",
          not any(ignored(x) for x in no), [x for x in no if ignored(x)])

    print("[7] refusals")
    hub_before = snapshot(hub)
    other = Path(tmp_dir("not-a-hub-"))
    (pf_existing := hub / "taken").mkdir()
    bare = Path(tmp_dir("bare-"))
    for script, argv, what in (
            (HUB_PY, new, "not empty"),
            (HUB_PY, ["new", "--hub", str(root / "Bad Id"), "--title", "x"], "client id"),
            (HUB_PY, ["new", "--hub", str(root / "with space" / "acme"), "--title", "x"],
             "white space"),
            (HUB_PY, ["add-pack", "--hub", str(hub), "--skill-pack", str(pa)], "already"),
            (HUB_PY, ["add-pack", "--hub", str(hub), "--skill-pack", str(pa),
                      "--folder", "other"], "already"),
            (HUB_PY, ["add-pack", "--hub", str(other), "--skill-pack", str(pa)],
             "not a hub"),
            (HUB_PY, ["add-pack", "--hub", str(hub), "--skill-pack", str(fake_pack("demoa").parent / "demoa-skill-pack"),
                      "--folder", "taken"], "already"),
            (HUB_PY, ["add-pack", "--hub", str(hub), "--skill-pack", str(bare)],
             "no skill-pack.toml")):
        rc, out, err = run(script, *argv)
        check(f"refused, exit 2: {what}", rc == 2 and what in err
              and len(err.strip().splitlines()) == 1, (rc, err))
    pc = fake_pack("demob").parent / "demob-skill-pack"
    (pc / "skill-pack.toml").write_text(
        '[skill_pack]\nname = "democ-skill-pack"\ncli = "democ"\n'
        'env_prefix = "DEMOC"\nscripts_dir = "scripts"\n', encoding="utf-8")
    rc, out, err = run(HUB_PY, "add-pack", "--hub", str(hub), "--skill-pack", str(pc),
                       "--folder", "taken")
    check("refused, exit 2: a folder that exists", rc == 2 and "exists" in err, err)
    rc, out, err = run(HUB_PY, "add-pack", "--hub", str(hub), "--skill-pack", str(pc),
                       "--link", str(existing))
    check("refused, exit 2: a --link with no bin/<cli>", rc == 2 and "no bin/democ" in err,
          err)
    ph = fake_pack("demob").parent / "demob-skill-pack"
    for name, cli, prefix in (("hub", "hubx", "HUBX"), ("hubby", "hub", "HUBY"),
                              ("hubz", "hubz", "HUB")):
        (ph / "skill-pack.toml").write_text(
            f'[skill_pack]\nname = "{name}"\ncli = "{cli}"\n'
            f'env_prefix = "{prefix}"\nscripts_dir = "scripts"\n', encoding="utf-8")
        (ph / "scripts" / f"{cli}.py").write_text(
            ENTRY.format(prefix=prefix, verbs=json.dumps({"verbs": []})), encoding="utf-8")
        rc, out, err = run(HUB_PY, "add-pack", "--hub", str(hub), "--skill-pack", str(ph),
                           "--folder", f"f-{cli}")
        check(f"refused, exit 2: a pack taking the hub's own {name}/{cli}/{prefix}",
              rc == 2 and "the hub's own" in err, err)
    rc, out, err = run(HUB_PY, "new", "--hub", str(root / "mk"), "--title", "x",
                       "--markets", "HK,H K")
    check("refused, exit 2: a market that is not a plain word",
          rc == 2 and "--markets" in err and not (root / "mk").exists(), err)
    rc, out, err = run(HUB_PY, "new", "--hub", str(root / "cu"), "--title", "x",
                       "--currencies", "USD,euro")
    check("refused, exit 2: a currency that is not an ISO code",
          rc == 2 and "--currencies" in err and not (root / "cu").exists(), err)
    rc, out, err = run(HUB_PY, "new", "--hub", str(root / "cu2"), "--title", "x")
    keys = (root / "cu2" / "hub" / "defs" / "fact_keys.tsv").read_text(encoding="utf-8")
    check("without --currencies, currency is text: no client's list is built in",
          rc == 0 and "currency\trequired\ttext\t" in keys, err or keys[:200])
    rc, out, err = run(HUB_PY, "new", "--hub", str(root / "cu3"), "--title", "x",
                       "--currencies", "USD,EUR")
    keys = (root / "cu3" / "hub" / "defs" / "fact_keys.tsv").read_text(encoding="utf-8")
    check("--currencies USD,EUR makes currency choice:USD|EUR",
          rc == 0 and "currency\trequired\tchoice:USD|EUR\t" in keys, err or keys[:200])
    pf_existing.rmdir()
    check("a refused add-pack changed nothing in the hub", snapshot(hub) == hub_before)

    print("[8] the port")
    r8 = Path(tmp_dir("ports-"))
    (r8 / "alpha").mkdir()
    (r8 / "alpha" / "CLIENT.md").write_text(
        "## Ports\n\n| Port | What |\n|---|---|\n| 8770 | console |\n", encoding="utf-8")
    (r8 / "beta-skill-pack" / "c1" / ".claude").mkdir(parents=True)
    (r8 / "beta-skill-pack" / "c1" / ".claude" / "launch.json").write_text(
        json.dumps({"configurations": [{"port": 8771}]}), encoding="utf-8")
    (r8 / "gamma" / ".claude").mkdir(parents=True)
    (r8 / "gamma" / ".claude" / "launch.json").write_text(
        json.dumps({"configurations": [{"port": 8773}]}), encoding="utf-8")
    never = lambda p: False  # noqa: E731
    check("a port a sibling's CLIENT.md, launch.json or per-pack launch.json names is skipped",
          new_hub.named_ports(r8) == {8770, 8771, 8773}
          and new_hub.choose_port(r8, bound=never) == 8772)
    check("a port bound now is skipped",
          new_hub.choose_port(r8, bound=lambda p: p == 8772) == 8774)
    check("an empty root starts at 8770", new_hub.choose_port(Path(tmp_dir("e-")),
                                                              bound=never) == 8770)
    try:
        new_hub.choose_port(r8, bound=lambda p: True)
        check("no free port is refused", False)
    except new_hub.Refused as e:
        check("no free port is refused", "no free port" in str(e), e)
    rc, out, err = run(HUB_PY, "new", "--hub", str(root / "second"), "--title", "Second",
                       "--console-home", str(home))
    p2 = json.loads((root / "second" / "hub.json").read_text(encoding="utf-8"))["port"] \
        if rc == 0 else None
    check("a second hub in the same root takes another port, not the per-pack 8799",
          rc == 0 and p2 not in (port, 8799) and p2 >= 8770, (rc, p2, port, err))

    print("[9] a pack without markets, once per hub market")
    mh = root / "teahouse"
    rc, out, err = run(HUB_PY, "new", "--hub", str(mh), "--title", "Tea", "--markets", "NL,SE",
                       "--console-home", str(home))
    pm = fake_pack("demoa")
    for argv, what in ((["--skill-pack", str(pm)], "--market"),
                       (["--skill-pack", str(pm), "--market", "XX"], "not one of the hub's")):
        rc, out, err = run(HUB_PY, "add-pack", "--hub", str(mh), *argv)
        check(f"refused, exit 2: {what}", rc == 2 and what in err, err)
    own = fake_pack("demob")
    (own / "skill-pack.toml").write_text(
        (own / "skill-pack.toml").read_text(encoding="utf-8") + 'markets = ["NL"]\n',
        encoding="utf-8")
    rc, out, err = run(HUB_PY, "add-pack", "--hub", str(mh), "--skill-pack", str(own),
                       "--market", "NL")
    check("refused, exit 2: --market for a pack with its own markets",
          rc == 2 and "keeps its own markets" in err, err)
    for m in ("NL", "SE"):
        rc, out, err = run(HUB_PY, "add-pack", "--hub", str(mh), "--skill-pack", str(pm),
                           "--market", m)
        check(f"add-pack --market {m}: a folder of its own", rc == 0
              and (mh / f"demoa-{m.lower()}" / "bin" / "demoa").is_file(), out + err)
    rc, out, err = run(HUB_PY, "add-pack", "--hub", str(mh), "--skill-pack", str(pm),
                       "--market", "NL", "--folder", "other")
    check("refused, exit 2: the same pack for a market it already serves",
          rc == 2 and "already" in err, err)
    hj = json.loads((mh / "hub.json").read_text(encoding="utf-8"))
    check("hub.json records each folder's market and dispatch name",
          [(p_["folder"], p_["market"], p_["word"]) for p_ in hj["packs"]]
          == [("demoa-nl", "NL", "demoa-nl"), ("demoa-se", "SE", "demoa-se")], hj["packs"])
    for m in ("NL", "SE"):
        r = subprocess.run([str(mh / "bin" / "hub"), f"demoa-{m.lower()}", "status"],
                           capture_output=True, text=True, timeout=60, env=clean_env())
        doc = json.loads(r.stdout or "{}")
        check(f"bin/hub demoa-{m.lower()} runs that folder with DEMOA_HUB_MARKET={m} and "
              f"DEMOA_HUB_CLI=demoa-{m.lower()}",
              os.path.realpath(doc.get("data_dir") or "")
              == str((mh / f"demoa-{m.lower()}" / "workspace").resolve())
              and doc.get("hub_market") == m and doc.get("hub_cli") == f"demoa-{m.lower()}",
              r.stdout + r.stderr)
    t = texts(mh)
    check("the console relays each folder's verbs under its name, one secret per prefix",
          "demoa-nl facts confirm,demoa-nl decisions confirm" in t["bin/console"]
          and "demoa-se queue approve" in t["bin/console"]
          and t["bin/console"].count("DEMOA_CONFIRM_CODE_SECRET=") == 1, t["bin/console"])
    deny = json.loads(t[".claude/settings.json"])["permissions"]["deny"]
    check("the deny list holds each folder's gate verbs through bin/hub and its wrapper",
          {"Bash(./bin/hub demoa-nl facts confirm:*)", "Bash(bin/hub demoa-se queue approve:*)",
           "Bash(./demoa-se/bin/demoa facts confirm:*)"} <= set(deny), deny)
    check("the pack folder's brief runs its gate through ../bin/hub demoa-nl",
          "`../bin/hub demoa-nl …`" in t["demoa-nl/CLAUDE.md"])
    r = subprocess.run([str(mh / "bin" / "hub"), "demoa", "status"], capture_output=True,
                       text=True, timeout=60, env=clean_env())
    check("the bare cli word is no dispatch name then", r.returncode == 2, r.stderr)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
