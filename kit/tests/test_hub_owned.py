#!/usr/bin/env python3
"""A key the client's hub confirms (`owner = hub` in the pack's fact_keys.tsv;
kit.registry.FactKeys.hub_owned, kit.facts), seen once in a Meta operator pack
and a client hub, 2026-10-28.

A synthetic DEMO hub (the shop's two keys) and a copy of the fake "shop" skill
pack whose unit_cost is `owner = hub`:

  [1] the registry: no `owner` column = every key the pack's; `owner = hub`
      is listed by hub_owned(); any other word is registry_file_invalid
  [2] with a hub in force the pack reads the hub's value after sync-hub, but
      `set`, `confirm`, `rollback` and the init question of that key are
      refused (fact_hub_owned) while the pack's other key is written as
      before; with no hub the same key is an ordinary one
  [3] a key the hub defines and the pack does not list: with a hub in force
      the refusal names it as the hub's (fact_key_hub_undeclared), with no
      hub it is the plain fact_key_unknown
"""

import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import config, db, facts  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.registry import FactKeys  # noqa: E402
from kit.testing.check import (capture, check, clean_env, finish,  # noqa: E402
                               one_doc, tmp_dir)

SPEC = db.with_human({}, version=1)
ROOT = Path(tmp_dir("hub-owned-"))
HUB = ROOT / "demo-hub"
DEFS = HUB / "hub" / "defs"
DEFS.mkdir(parents=True)
(DEFS / "skill-pack.toml").write_text(
    '[skill_pack]\nname = "demo-hub-hub"\ncli = "hub"\nenv_prefix = "HUB"\n'
    'db_file = "hub.db"\nlanguages = ["en", "zh"]\n'
    'markets = ["US", "CA"]\nhome_env_file = ""\n\n'
    '[ssot]\ndir = "."\nfact_keys = "fact_keys.tsv"\n', encoding="utf-8")
SHOP_KEYS = _shop.SHOP / "ssot" / "fact_keys.tsv"
shutil.copy(SHOP_KEYS, DEFS / "fact_keys.tsv")


def make_pack(name: str, owners: dict[str, str] | None, drop=()) -> Path:
    """A copy of the fake shop; its fact keys with an `owner` column when
    `owners` is given ({key: owner}, the rest `pack`), without the `drop` rows."""
    dest = ROOT / name
    shutil.copytree(_shop.SHOP, dest)
    lines = SHOP_KEYS.read_text(encoding="utf-8").splitlines()
    out = []
    for i, line in enumerate(lines):
        key = line.split("\t")[0]
        if i and key in drop:
            continue
        if owners is not None:
            line += "\t" + ("owner" if i == 0 else owners.get(key, "pack"))
        out.append(line)
    (dest / "ssot" / "fact_keys.tsv").write_text("\n".join(out) + "\n",
                                                 encoding="utf-8")
    return dest


def hub_run(argv, *, stdin=None, tty=None):
    config.use(DEFS)
    env = clean_env(HUB_DATA_DIR=str(HUB / "hub"), HUB_AUTH_ENV_PATHS="none")
    return capture(lambda a: facts.main(a, spec=SPEC, keys=FactKeys(),
                                        thresholds=None),
                   list(argv), env=env, stdin=stdin, tty_answers=tty)


def build_hub() -> None:
    for m in ("US", "CA"):
        rc, out, err = hub_run(["init"], stdin=f"{m}\n\n", tty=[m])
        assert rc == 0, (out, err)
    for key, value in (("unit_cost", "4.2"), ("channel", "web")):
        rc, out, err = hub_run(["set", key, value, "--market", "US",
                                "--source", "owner_call", "--reason", "r"])
        assert rc == 0, (out, err)
        rc, out, err = hub_run(["confirm", key, "--market", "US", "--reason",
                                "r"], tty=[value])
        assert rc == 0, (out, err)


def pack_run(pack: Path, argv, *, hub=True, tty=None, stdin=None, questions=None):
    cfg = config.use(pack)
    extra = {cfg.env("HUB_DIR"): str(HUB)} if hub else {}
    env = clean_env(**{cfg.env("DATA_DIR"): str(pack / "data"),
                       cfg.env("AUTH_ENV_PATHS"): "none", **extra})
    return capture(lambda a: facts.main(a, spec=SPEC, keys=FactKeys(),
                                        thresholds=None,
                                        init_questions=questions),
                   [*argv, "--json"], env=env, tty_answers=tty, stdin=stdin)


def code(out) -> str | None:
    return (one_doc(out) or {}).get("code")


def test_registry() -> None:
    print("[1] the owner column")
    plain = make_pack("plain", None)
    config.use(plain)
    check("no owner column: no key is the hub's", FactKeys().hub_owned() == ())
    owned = make_pack("owned", {"unit_cost": "hub"})
    config.use(owned)
    check("owner = hub is listed", FactKeys().hub_owned() == ("unit_cost",))
    bad = make_pack("bad", {"unit_cost": "both"})
    config.use(bad)
    try:
        FactKeys()
        got = None
    except SkillPackError as e:
        got = getattr(e.message, "code", None)
    check("any other owner is registry_file_invalid",
          got == "registry_file_invalid", got)


def test_hub_in_force() -> None:
    print("[2] a hub-owned key is read here and written at the hub")
    build_hub()
    pack = make_pack("pack", {"unit_cost": "hub"})
    rc, out, err = pack_run(pack, ["init"], stdin="US\n\n", tty=["US"],
                            questions=[{"key": "unit_cost"}])
    check("init asks nothing for the hub's key and does not abort",
          rc == 0, (out, err))
    rc, out, err = pack_run(pack, ["get", "unit_cost", "--market", "US"])
    check("before a copy the key is simply not set here",
          code(out) == "fact_not_found", (rc, out))
    rc, out, err = pack_run(pack, ["sync-hub"])
    doc = one_doc(out) or {}
    check("sync-hub copies the hub's unit_cost into the pack",
          rc == 0 and any(i["key"] == "unit_cost" and i["outcome"] == "copied"
                          for i in doc.get("results", [])), (rc, out, err))
    rc, out, err = pack_run(pack, ["get", "unit_cost", "--market", "US"])
    check("the pack reads the hub's value", rc == 0 and "4.2" in out, out)
    for argv, what in ((["set", "unit_cost", "9", "--market", "US", "--source",
                          "own", "--reason", "r"], "set"),
                       (["confirm", "unit_cost", "--market", "US", "--reason",
                         "r", "--value", "9"], "confirm --value"),
                       (["confirm", "unit_cost", "--market", "US", "--reason",
                         "r"], "confirm"),
                       (["rollback", "unit_cost", "--market", "US", "--to",
                         "1", "--reason", "r"], "rollback")):
        rc, out, err = pack_run(pack, argv, tty=["9"])
        check(f"{what} of the hub's key is refused (fact_hub_owned)",
              rc == 2 and code(out) == "fact_hub_owned", (rc, out, err))
    doc = one_doc(pack_run(pack, ["get", "unit_cost", "--market", "US"])[1])
    check("… and the copied value stands", "4.2" in str(doc), doc)
    pack_run(pack, ["init"], stdin="CA\n\n", tty=["CA"])
    rc, out, err = pack_run(pack, ["set", "channel", "store", "--market", "CA",
                                   "--source", "own", "--reason", "r"])
    check("the pack's own key is written as before", rc == 0, (out, err))
    rc, out, err = pack_run(pack, ["set", "unit_cost", "9", "--market", "CA",
                                   "--source", "own", "--reason", "r"],
                            hub=False)
    check("with no hub the same key is an ordinary one", rc == 0, (rc, out, err))


def test_unknown_hub_key() -> None:
    print("[3] a hub key the pack does not list")
    pack = make_pack("short", {}, drop=("channel",))
    rc, out, err = pack_run(pack, ["init"], stdin="US\n\n", tty=["US"])
    assert rc == 0, (out, err)
    argv = ["set", "channel", "web", "--market", "US", "--source", "own",
            "--reason", "r"]
    rc, out, err = pack_run(pack, argv)
    check("with a hub in force the refusal names the hub",
          rc == 2 and code(out) == "fact_key_hub_undeclared"
          and "owner = hub" in (one_doc(out) or {}).get("error", ""),
          (rc, out, err))
    rc, out, err = pack_run(pack, argv, hub=False)
    check("with no hub it is the plain unknown key",
          rc == 2 and code(out) == "fact_key_unknown", (rc, out, err))
    rc, out, err = pack_run(pack, ["set", "nonsense", "1", "--market", "US",
                                   "--source", "own", "--reason", "r"])
    check("a key the hub does not define stays unknown",
          code(out) == "fact_key_unknown", out)


if __name__ == "__main__":
    test_registry()
    test_hub_in_force()
    test_unknown_hub_key()
    raise SystemExit(finish())
