#!/usr/bin/env python3
"""scaffold/add_zylos.py: a skill pack set up to run as a Zylos component by one command.

  [1] a new skill pack has the adapter by default and `node zylos/lib.js check` passes in it; --no-zylos leaves all of it out
  [2] on a pack without it: the adapter files are exactly the ones tools/fleet.py compares (no tests/, no template), a manifest from the
      toml's names, the SKILL.md keys, the ecosystem file and the CI step; a second run changes nothing
  [3] what the skill pack owns is never overwritten (its manifest with a task added, its ecosystem file, a SKILL.md that has Zylos keys); a
      copied adapter file that was edited is put back
  [4] --dry-run names the changes and writes nothing
  [5] the verdict is the check's: a SKILL.md whose name differs from the manifest's makes the run exit 1
  [6] the port is stable per name, in 8800 to 9799, different for different names, and --port wins
  [7] a folder with no skill-pack.toml, and a pack with no CLI script, are refused with one line
  [8] the CI step: Node 22 and the check as the last steps; nothing added twice or to a file with no steps
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PLAYBOOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLAYBOOK))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

from kit.testing.check import check, finish, tmp_dir  # noqa: E402

sys.path.insert(0, str(PLAYBOOK / "scaffold"))
sys.path.insert(0, str(PLAYBOOK / "tools"))
import add_zylos  # noqa: E402
import fleet  # noqa: E402

SCAFFOLD = PLAYBOOK / "scaffold" / "new_skill_pack.py"
ENV = {k: v for k, v in os.environ.items() if k != "KIT_SKILL_PACK_ROOT" and not k.startswith("ACME_")}
HAS_NODE = shutil.which("node") is not None
EXPECTED = fleet.files(add_zylos.SOURCE, fleet.ZYLOS_NOT_COPIED | fleet.ZYLOS_OWN)


def scaffold(d: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCAFFOLD), "--dir", str(d), "--name", "acme-skill-pack", "--cli", "acme",
                           "--prefix", "ACME", *extra], capture_output=True, text=True, timeout=300, env=ENV)


def run(d: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(add_zylos.__file__), "--skill-pack", str(d), *extra],
                          capture_output=True, text=True, timeout=120, env=ENV)


def tree(d: Path) -> dict[str, bytes]:
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file() and ".git" not in p.parts}


def bare(label: str, *extra: str) -> Path:
    d = Path(tmp_dir(f"zylos-{label}-")) / "acme-skill-pack"
    r = scaffold(d, "--no-zylos", *extra)
    assert r.returncode == 0, r.stderr
    return d


def test_the_scaffold_sets_it_up_by_default() -> None:
    print("[1] new_skill_pack.py")
    d = Path(tmp_dir("zylos-new-")) / "acme-skill-pack"
    r = scaffold(d)
    check("a new skill pack has the adapter, the manifest, the ecosystem file and the SKILL.md keys",
          r.returncode == 0 and (d / "zylos" / "lib.js").is_file() and (d / "zylos" / "manifest.json").is_file()
          and (d / "ecosystem.config.cjs").is_file() and "lifecycle:" in (d / "SKILL.md").read_text("utf-8"), (r.stdout[-300:], r.stderr))
    if HAS_NODE:
        code, out = add_zylos.check(d)
        check("`node zylos/lib.js check` passes in it", code == 0 and out.endswith("check: ok"), out)
    n = bare("off")
    check("--no-zylos leaves it all out", not (n / "zylos").exists() and not (n / "ecosystem.config.cjs").exists()
          and "lifecycle:" not in (n / "SKILL.md").read_text("utf-8"), sorted(tree(n))[:5])


def test_adding_to_an_existing_pack_and_running_twice() -> None:
    print("[2] a pack without it")
    d = bare("add")
    r = run(d)
    got = sorted(k.removeprefix("zylos/") for k in tree(d) if k.startswith("zylos/") and k != "zylos/manifest.json")
    check("the copied files are the ones fleet.py compares: nothing from tests/, no template",
          r.returncode == 0 and got == sorted(EXPECTED) and not any("tests" in g or "template" in g or "example" in g for g in got),
          (r.stdout[-300:], r.stderr, got))
    m = json.loads((d / "zylos" / "manifest.json").read_text("utf-8"))
    check("the manifest carries the toml's names and no scheduled task",
          m["name"] == "acme-skill-pack" and m["cli"]["bin"] == "openmax-acme" and m["cli"]["entry"] == "scripts/acme.py"
          and m["env"]["prefix"] == "ACME" and m["tasks"] == [] and m["console"]["base_path"] == "/acme", m)
    ci = (d / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    check("the CI file ends with Node 22 and the check",
          ci.rstrip().endswith('- uses: actions/setup-node@v7\n        with:\n          node-version: "22"\n'
                               '      - name: Zylos adapter check\n        run: node zylos/lib.js check'), ci[-300:])
    before = tree(d)
    again = run(d)
    check("a second run changes nothing", again.returncode == 0 and "nothing to do" in again.stdout and tree(d) == before,
          (again.stdout[-200:], [k for k in tree(d) if tree(d)[k] != before.get(k)]))


def test_what_the_skill_pack_owns_is_not_overwritten() -> None:
    print("[3] its own files")
    d = bare("own")
    run(d)
    mf = d / "zylos" / "manifest.json"
    m = json.loads(mf.read_text("utf-8"))
    m["tasks"].append({"name": "acme-hourly", "cron": "5 * * * *", "miss_threshold": 14400, "requires": [],
                       "prompt": "Hourly: run {cli} compute daily. Exit 0: call done, report nothing. Otherwise send the owner the error lines, then call done."})
    mf.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    eco = d / "ecosystem.config.cjs"
    eco.write_text(eco.read_text("utf-8") + "// the pack's own line\n", encoding="utf-8")
    skill = d / "SKILL.md"
    skill.write_text(skill.read_text("utf-8").replace("next-steps:", "next-steps (edited):", 1), encoding="utf-8")
    (d / "zylos" / "lib.js").write_text("// edited\n", encoding="utf-8")
    keep = {k: v for k, v in tree(d).items() if k != "zylos/lib.js"}
    r = run(d)
    after = tree(d)
    check("the manifest, the ecosystem file and the SKILL.md keys keep their bytes", r.returncode in (0, 1)
          and all(after[k] == v for k, v in keep.items()), [k for k, v in keep.items() if after.get(k) != v])
    check("an edited copy of the adapter is put back", after["zylos/lib.js"] == (add_zylos.SOURCE / "lib.js").read_bytes())


def test_dry_run_and_the_verdict() -> None:
    print("[4] --dry-run, [5] the check's verdict")
    d = bare("dry")
    before = tree(d)
    r = run(d, "--dry-run")
    check("--dry-run names the changes and writes nothing",
          r.returncode == 0 and "would write  zylos/lib.js" in r.stdout and tree(d) == before, (r.stdout[-200:], r.stderr))
    if HAS_NODE:
        run(d)
        skill = d / "SKILL.md"
        skill.write_text(skill.read_text("utf-8").replace("name: acme-skill-pack", "name: other-skill-pack", 1), encoding="utf-8")
        bad = run(d)
        check("a SKILL.md whose name differs from the manifest's makes the run exit 1 and names it",
              bad.returncode == 1 and "name" in bad.stdout + bad.stderr, (bad.returncode, bad.stdout[-300:]))


def test_the_port() -> None:
    print("[6] the port")
    ports = {add_zylos.default_port(n) for n in ("acme-skill-pack", "beta-skill-pack", "gamma-skill-pack", "delta-skill-pack")}
    check("in 8800 to 9799, stable, and different for different names",
          all(8800 <= p <= 9799 for p in ports) and len(ports) > 1 and add_zylos.default_port("acme-skill-pack") == add_zylos.default_port("acme-skill-pack"),
          ports)
    d = bare("port")
    run(d, "--port", "9123", "--brand", "coco")
    m = json.loads((d / "zylos" / "manifest.json").read_text("utf-8"))
    check("--port and --brand win", m["console"]["port"] == 9123 and m["cli"]["bin"] == "coco-acme", m["console"])


def test_refusals() -> None:
    print("[7] refusals")
    empty = Path(tmp_dir("zylos-empty-"))
    r = run(empty)
    check("a folder with no skill-pack.toml: one line, no traceback", r.returncode != 0 and "not a skill pack" in r.stderr
          and "Traceback" not in r.stderr, r.stderr[-300:])
    d = bare("noentry")
    (d / "scripts" / "acme.py").unlink()
    r = run(d)
    check("a pack with no CLI script: one line", r.returncode != 0 and "no CLI script" in r.stderr and "Traceback" not in r.stderr, r.stderr[-300:])
    check("and nothing was written", not (d / "zylos").exists())


def test_the_ci_step() -> None:
    print("[8] the CI step")
    base = "jobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: echo hi\n"
    new = add_zylos.with_ci_step(base)
    check("Node 22 and the check come last", new is not None and new.endswith(
        '      - uses: actions/setup-node@v7\n        with:\n          node-version: "22"\n'
        '      - name: Zylos adapter check\n        run: node zylos/lib.js check\n'), new)
    check("added once", add_zylos.with_ci_step(new) is None)
    check("a file with no steps is left alone", add_zylos.with_ci_step("name: x\non: push\n") is None)


if __name__ == "__main__":
    for fn in (test_the_scaffold_sets_it_up_by_default, test_adding_to_an_existing_pack_and_running_twice,
               test_what_the_skill_pack_owns_is_not_overwritten, test_dry_run_and_the_verdict, test_the_port, test_refusals,
               test_the_ci_step):
        fn()
    raise SystemExit(finish())
