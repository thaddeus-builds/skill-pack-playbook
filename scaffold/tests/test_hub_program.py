#!/usr/bin/env python3
"""scaffold/hub/: a client hub's own facts program, as new_hub.py binds it.

  [1] `new --markets DE,DK` writes hub/bin/hub (executable, parses),
      hub/defs/skill-pack.toml (cli hub, prefix HUB, the markets) and
      hub/defs/fact_keys.tsv (the shared keys, read by the kit's strict
      registry); `--markets` omitted = no partition; hub/hub.db,
      hub/backups and hub/.env git-ignored, hub/defs and hub/bin not
  [2] the hub's CLAUDE.md: under 4 KB, says how to start (doctor, pending
      --hub for the hub and each pack, bin/ask, chat answers only for words
      and choices, intake, check_intake.py), names every gate verb as never
      the agent's; add-pack rewrites it with the pack
  [3] `bin/hub hub …` runs the kit's verbs over <hub>/hub/hub.db: verbs
      (facts confirm gated), facts init piped (the declaration pending),
      pending --hub (ids and gate verbs start with `hub`), a relayed code
      confirms (changed_by @relay), set + confirm a shared key; the store is
      <hub>/hub/hub.db; doctor --strict is healthy (the data dir is not
      inside the definitions)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PLAYBOOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLAYBOOK))
sys.path.insert(0, str(PLAYBOOK / "scaffold"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull

from kit import registry  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402
import new_hub  # noqa: E402
from test_new_hub import fake_pack  # noqa: E402

HUB_PY = PLAYBOOK / "scaffold" / "new_hub.py"
RELAY = ["--relay-user", "web:owner", "--relay-at", "2026-10-22T10:00:00Z"]


def env(**extra: str) -> dict:
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(("HUB_", "DEMOA_", "KIT_"))}
    return {**e, "HUB_PYTHON": sys.executable, "DEMOA_PYTHON": sys.executable,
            **extra}


def hub_cli(hub: Path, *argv: str, stdin: str = "", **extra: str):
    r = subprocess.run([str(hub / "bin" / "hub"), "hub", *argv], input=stdin,
                       capture_output=True, text=True, timeout=120,
                       env=env(**extra))
    try:
        doc = json.loads(r.stdout) if "--json" in argv else None
    except json.JSONDecodeError:
        doc = None
    return r.returncode, doc, r.stdout + r.stderr


def ignored(hub: Path, rel: str) -> bool:
    return subprocess.run(["git", "-C", str(hub), "check-ignore", "-q", rel],
                          capture_output=True).returncode == 0


def main() -> int:
    root = Path(tmp_dir("hub-program-")).resolve()
    hub = root / "demo-hub"

    print("[1] new --markets: the hub's facts program, bound")
    r = subprocess.run([sys.executable, str(HUB_PY), "new", "--hub", str(hub),
                        "--title", "Demo Hub", "--markets", "DE,DK"],
                       capture_output=True, text=True, timeout=120, env=env())
    check("written", r.returncode == 0 and hub.is_dir(), r.stdout + r.stderr)
    w = hub / "hub" / "bin" / "hub"
    check("hub/bin/hub is executable and parses",
          os.access(w, os.X_OK) and subprocess.run(
              ["sh", "-n", str(w)], capture_output=True).returncode == 0)
    toml = (hub / "hub" / "defs" / "skill-pack.toml").read_text(encoding="utf-8")
    check("its skill-pack.toml: cli hub, prefix HUB, the markets",
          'cli = "hub"' in toml and 'env_prefix = "HUB"' in toml
          and 'markets = ["DE", "DK"]' in toml, toml)
    rows = registry.read_tsv(hub / "hub" / "defs" / "fact_keys.tsv",
                             ["key", "group", "type", "unit", "min", "max",
                              "label_en", "label_zh", "why"], id_col="key")
    check("its fact_keys.tsv: the shared keys, strict TSV (the markets "
          "enter through the market door, not a row)",
          [x["key"] for x in rows] == ["currency", "npr_roas",
                                       "avg_order_value",
                                       "npr_includes_creator_fee",
                                       "incremental_source",
                                       "incremental_factor"], rows)
    flat = root / "flat-hub"
    subprocess.run([sys.executable, str(HUB_PY), "new", "--hub", str(flat),
                    "--title", "Flat"], capture_output=True, timeout=120,
                   env=env())
    check("--markets omitted: no partition",
          "markets = []" in (flat / "hub" / "defs" / "skill-pack.toml")
          .read_text(encoding="utf-8"))
    subprocess.run(["git", "init", "-q", str(hub)], capture_output=True)
    check("hub/hub.db, hub/backups, hub/.env git-ignored; hub/defs and "
          "hub/bin versioned",
          ignored(hub, "hub/hub.db") and ignored(hub, "hub/backups/x.db")
          and ignored(hub, "hub/.env")
          and not ignored(hub, "hub/defs/fact_keys.tsv")
          and not ignored(hub, "hub/bin/hub"))

    print("[2] the hub's CLAUDE.md")
    brief = (hub / "CLAUDE.md").read_text(encoding="utf-8")
    check("under 4 KB", len(brief.encode("utf-8")) < 4096,
          len(brief.encode("utf-8")))
    for want in ("`bin/hub hub doctor`", "`bin/hub <cli> doctor`",
                 "`bin/hub hub pending --hub --json`",
                 "`bin/hub <cli> pending --hub --json`", "`bin/ask add FILE`",
                 "bin/ask chat ID", "only for words and choices",
                 "intake/inbox/<YYYY-MM-DD>-<source>/", "intake/INDEX.tsv",
                 "check_intake.py", "--transcript FILE",
                 "facts sync-hub", "Never run a gate verb yourself",
                 "`hub facts confirm, facts restore`"):
        check(f"it says {want}", want in brief, brief)
    pa = fake_pack("demoa")
    r = subprocess.run([sys.executable, str(HUB_PY), "add-pack", "--hub",
                        str(hub), "--skill-pack", str(pa), "--market", "DE"],
                       capture_output=True, text=True, timeout=120, env=env())
    brief = (hub / "CLAUDE.md").read_text(encoding="utf-8")
    check("add-pack rewrites it: the pack folder by its name, its market, "
          "its gate verbs, --packs demoa-de",
          r.returncode == 0 and "packs: `demoa-de` (DE)" in brief
          and "`demoa-de facts confirm, facts restore, decisions confirm, "
          "queue approve`" in brief and "--packs demoa-de" in brief,
          r.stdout + r.stderr + brief)

    print("[3] bin/hub hub …: the kit's facts verbs over <hub>/hub/hub.db")
    rc, doc, out = hub_cli(hub, "verbs", "--json")
    kinds = {" ".join(v["words"]): v["kind"] for v in (doc or {}).get("verbs", [])}
    check("verbs: the hub's cli, facts confirm gated, facts set human, "
          "pending read",
          rc == 0 and doc["cli"] == "hub" and kinds.get("facts confirm")
          == "gated" and kinds.get("facts set") == "human"
          and kinds.get("pending") == "read", out)
    check("the store is <hub>/hub/hub.db, made by `new` (no first write "
          "needed)", (hub / "hub" / "hub.db").is_file()
          and not (hub / "hub" / "defs" / "hub.db").exists())
    rc, doc, out = hub_cli(hub, "facts", "list", "--json")
    check("facts list answers (no no_db) and both markets' declarations "
          "are pending, none confirmed",
          rc == 0 and doc["pending_markets"] == ["DE", "DK"]
          and doc["declared_markets"] == []
          and all(f["is_assumption"] == 1 for f in doc["facts"])
          and [f["key"] for f in doc["facts"]] == ["market_declared"] * 2, out)
    rc, doc, out = hub_cli(hub, "facts", "init", "--json",
                           stdin="DE\n\n\n\n\n\n\n\n")
    check("a second facts init (piped) changes nothing: DE stays pending",
          rc == 0 and doc["declaration"] == "pending"
          and doc["written"] == [], out)
    rc, doc, out = hub_cli(hub, "pending", "--hub", "--json")
    a = (doc or {}).get("asks", [{}])[0]
    check("pending --hub: the ask id and gate verb start with `hub`",
          rc == 0 and a["id"].startswith("hub-market-de-")
          and a["gate"]["verb"] == ["hub", "facts", "confirm",
                                    "market_declared"], out)
    sec = {"HUB_CONFIRM_CODE_SECRET": "s3cret"}
    cmd = ["facts", "confirm", "market_declared", "--market", "DE",
           "--reason", "owner", "--json"]
    rc, doc, out = hub_cli(hub, *cmd, **sec)
    code = ((doc or {}).get("params") or {}).get("confirm_code")
    check("a confirm off a terminal is a relay challenge",
          rc == 2 and doc["code"] == "confirm_code_required" and code, out)
    rc, doc, out = hub_cli(hub, *cmd, "--code", code, *RELAY, **sec)
    check("the relayed code confirms it, @relay",
          rc == 0 and doc["changed_by"].endswith("@relay"), out)
    rc, doc, out = hub_cli(hub, "facts", "set", "currency", "HKD", "--market",
                           "DE", "--source", "owner_call", "--reason", "owner",
                           "--json")
    check("a shared key set at the hub is pending",
          rc == 0 and doc["change"] == "new", out)
    cmd = ["facts", "confirm", "currency", "--market", "DE", "--reason",
           "owner", "--json"]
    rc, doc, out = hub_cli(hub, *cmd, **sec)
    code = ((doc or {}).get("params") or {}).get("confirm_code")
    rc, doc, out = hub_cli(hub, *cmd, "--code", code, *RELAY, **sec)
    check("… and confirmed through the gate",
          rc == 0 and doc["confirmed"][0]["is_assumption"] == 0, out)
    rc, doc, out = hub_cli(hub, "doctor", "--strict", "--json")
    check("doctor --strict warns while DK's declaration waits for a person",
          rc != 0 and not doc["healthy"], out)
    cmd = ["facts", "confirm", "market_declared", "--market", "DK",
           "--reason", "owner", "--json"]
    rc, doc, out = hub_cli(hub, *cmd, **sec)
    code = ((doc or {}).get("params") or {}).get("confirm_code")
    rc, doc, out = hub_cli(hub, *cmd, "--code", code, *RELAY, **sec)
    rc, doc, out = hub_cli(hub, "doctor", "--strict", "--json")
    codes = [c["message_code"]["code"] for c in (doc or {}).get("checks", [])]
    check("doctor --strict is healthy (the data dir is outside the "
          "definitions folder)",
          rc == 0 and doc["healthy"] and "doctor_inside_repo" not in codes,
          out)
    print("[4] init-facts: a hub that has no store")
    r = subprocess.run([sys.executable, str(HUB_PY), "init-facts", "--hub",
                        str(hub)], capture_output=True, text=True, timeout=120,
                       env=env())
    check("refused on a hub with a hub.db, which is left as it was",
          r.returncode == 2 and "exists" in r.stderr, r.stdout + r.stderr)
    for old_hub in (hub, flat):
        db_file = old_hub / "hub" / "hub.db"
        for p in db_file.parent.glob("hub.db*"):
            p.unlink()
        r = subprocess.run([sys.executable, str(HUB_PY), "init-facts", "--hub",
                            str(old_hub)], capture_output=True, text=True,
                           timeout=120, env=env())
        rc, doc, out = hub_cli(old_hub, "facts", "list", "--json")
        check(f"{old_hub.name}: made again, facts list answers",
              r.returncode == 0 and db_file.is_file() and rc == 0, r.stdout
              + r.stderr + out)
    check("… the markets' declarations pending again, the flat hub has none "
          "to declare", hub_cli(hub, "facts", "list", "--json")[1]
          ["pending_markets"] == ["DE", "DK"]
          and hub_cli(flat, "facts", "list", "--json")[1]["facts"] == [])
    r = subprocess.run([sys.executable, str(HUB_PY), "init-facts", "--hub",
                        str(root / "nothing")], capture_output=True, text=True,
                       timeout=120, env=env())
    check("refused on a folder that is not a hub", r.returncode == 2
          and "not a hub" in r.stderr, r.stdout + r.stderr)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
