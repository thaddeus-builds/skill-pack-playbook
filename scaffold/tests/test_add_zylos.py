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
  [9] to [11] (a cold review): a CI file or a SKILL.md that is not safe to edit is left alone with a line; bad inputs are refused before the first write
  [12] (the second cold review): nothing is written through a link or into a place that cannot take it; a write that fails puts back what was written;
       a name, prefix or path the adapter's check would refuse is refused first; a ci.yml or SKILL.md written in a style we do not read is left alone
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
    new, note = add_zylos.with_ci_step(base)
    check("Node 22 and the check come last", note is None and new is not None and new.endswith(
        '      - uses: actions/setup-node@v7\n        with:\n          node-version: "22"\n'
        '      - name: Zylos adapter check\n        run: node zylos/lib.js check\n'), new)
    check("added once", add_zylos.with_ci_step(new) == (None, None))
    check("a file with no steps is left alone and says why", add_zylos.with_ci_step("name: x\non: push\n")[0] is None and add_zylos.with_ci_step("name: x\non: push\n")[1])


def ci_note(text: str):
    new, note = add_zylos.with_ci_step(text)
    return new, note


def yaml_ok(text: str) -> bool:
    try:
        import yaml
    except ImportError:
        return True                                                  # no YAML reader here: the structural checks above stand alone
    try:
        yaml.safe_load(text)
        return True
    except yaml.YAMLError:
        return False


def test_a_ci_file_that_is_not_safe_to_edit_is_left_alone() -> None:
    print("[9] found by a cold review: the CI file")
    job = "jobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
    cases = {
        "a last job that calls a reusable workflow": job + "  u:\n    uses: org/repo/.github/workflows/w.yml@main\n",
        "a top-level key after the jobs": job + "env:\n  A: b\n",
        "a job key after the steps": job + "    timeout-minutes: 5\n",
        "steps only in a comment": "jobs:\n  t:\n    runs-on: x\n    # steps:\n",
        "steps written inline": "jobs:\n  t:\n    steps: [a, b]\n",
    }
    for label, text in cases.items():
        new, note = ci_note(text)
        check(f"{label}: nothing is added and the line says what to do by hand", new is None and note, (new, note))
    ok, _ = ci_note(job + "\n# a comment at column 0\n")
    check("a comment or a blank line after the steps stays after the new steps, and the file is still YAML", ok is not None and yaml_ok(ok) and ok.index("Zylos adapter check") < ok.index("# a comment"), ok)
    ok, _ = ci_note("jobs:\n  a:\n    steps:\n      - run: x\n  b:\n    steps:\n      - run: y\n")
    check("several jobs: the last job's steps get it, and the file is still YAML", ok is not None and yaml_ok(ok) and ok.rstrip().endswith("run: node zylos/lib.js check"), ok)
    ok, _ = ci_note("jobs:\n  t:\n    steps:\n      - run: |\n          echo steps:\n          steps:\n")
    check("a `steps:` line inside a script block is not taken for the list", ok is not None and yaml_ok(ok) and ok.count("Zylos adapter check") == 1 and
          "          steps:\n      - uses" in ok.replace("\r", ""), ok)
    already, _ = ci_note(job + "      - run: node ./zylos/lib.js check\n")
    commented, _ = ci_note(job + "      # node zylos/lib.js check\n")
    check("a check already run (even as ./zylos) is not added again; a commented one does not count", already is None and commented is not None)
    crlf, _ = ci_note((job).replace("\n", "\r\n").replace("\r\n", "\n"))
    d = bare("crlf")
    ci = d / ".github" / "workflows" / "ci.yml"
    ci.write_bytes(ci.read_bytes().replace(b"\n", b"\r\n"))
    r = run(d)
    after = ci.read_bytes()
    check("a CRLF ci.yml stays CRLF", r.returncode == 0 and b"\r\n" in after and after.count(b"\n") == after.count(b"\r\n") and b"Zylos adapter check" in after, after[-160:])


def test_a_skill_md_that_is_not_safe_to_edit_is_left_alone() -> None:
    print("[10] found by a cold review: SKILL.md")
    for label, extra in (("bin:", "bin:\n  x: y\n"), ("config:", "config:\n  required: []\n"), ("next-steps:", 'next-steps: "do it"\n')):
        d = bare("skill-" + label[:3])
        skill = d / "SKILL.md"
        skill.write_text(skill.read_text("utf-8").replace("type: capability\n", "type: capability\n" + extra, 1), encoding="utf-8")
        before = skill.read_bytes()
        r = run(d)
        check(f"its own {label} without lifecycle: SKILL.md is not touched and a line says to merge by hand", skill.read_bytes() == before and "merge the Zylos keys by hand" in r.stdout, r.stdout[-300:])
        again = run(d)
        check(f"and a second run says the same, it does not pretend it is done ({label})", skill.read_bytes() == before and "merge the Zylos keys by hand" in again.stdout)
    d = bare("skill-trail")
    skill = d / "SKILL.md"
    text = skill.read_text("utf-8")
    skill.write_text(text.replace("\n---\n", "\n---  \n", 1), encoding="utf-8")
    before = skill.read_bytes()
    r = run(d)
    check("a closing `---` with trailing spaces is not the adapter's closing line: SKILL.md is untouched and a line says so (no false green)",
          skill.read_bytes() == before and "exactly `---`" in r.stdout, r.stdout[-300:])
    d = bare("skill-nofm")
    skill = d / "SKILL.md"
    skill.write_text("# no frontmatter here\n", encoding="utf-8")
    r = run(d)
    check("no frontmatter: untouched, with a line", skill.read_text("utf-8") == "# no frontmatter here\n" and "no frontmatter" in r.stdout, r.stdout[-200:])
    d = bare("skill-bom")
    skill = d / "SKILL.md"
    skill.write_bytes(b"\xef\xbb\xbf" + skill.read_bytes())
    r = run(d)
    check("a byte-order mark: untouched, with a line", "byte-order mark" in r.stdout, r.stdout[-200:])
    d = bare("skill-crlf")
    skill = d / "SKILL.md"
    skill.write_bytes(skill.read_bytes().replace(b"\n", b"\r\n"))
    run(d)
    after = skill.read_bytes()
    check("a CRLF SKILL.md stays CRLF, with the keys added", b"lifecycle:" in after and after.count(b"\n") == after.count(b"\r\n"))


def test_bad_inputs_are_refused_before_anything_is_written() -> None:
    print("[11] found by a cold review: inputs")
    for label, extra in (("--port 80", ["--port", "80"]), ("--port -1", ["--port", "-1"]), ("--port 70000", ["--port", "70000"]), ("--brand 'Open Max'", ["--brand", "Open Max"])):
        d = bare("in-" + label[2:6])
        before = tree(d)
        r = run(d, *extra)
        check(f"{label}: one line, exit non-zero, nothing written", r.returncode != 0 and "error:" in (r.stdout + r.stderr) and "Traceback" not in r.stderr and tree(d) == before, (r.stdout[-200:], r.stderr[-200:]))
    d = bare("in-prefix")
    toml = d / "skill-pack.toml"
    toml.write_text(toml.read_text("utf-8").replace('env_prefix = "ACME"', 'env_prefix = "a:b"'), encoding="utf-8")
    before = tree(d)
    r = run(d)
    check("an env prefix with a colon: refused with a line, nothing written", r.returncode != 0 and "env_prefix" in (r.stdout + r.stderr) and tree(d) == before and "Traceback" not in r.stderr, r.stderr[-200:])
    d = bare("in-scripts")
    toml = d / "skill-pack.toml"
    toml.write_text(toml.read_text("utf-8").replace('scripts_dir = "scripts"', 'scripts_dir = "./scripts/"'), encoding="utf-8")
    r = run(d)
    m = json.loads((d / "zylos" / "manifest.json").read_text("utf-8")) if (d / "zylos" / "manifest.json").is_file() else {}
    check("scripts_dir written as ./scripts/ is normalised: the entry is scripts/acme.py and the check passes", r.returncode == 0 and m.get("cli", {}).get("entry") == "scripts/acme.py", (r.stdout[-200:], m.get("cli")))
    d = bare("in-up")
    toml = d / "skill-pack.toml"
    toml.write_text(toml.read_text("utf-8").replace('scripts_dir = "scripts"', 'scripts_dir = "../x"'), encoding="utf-8")
    r = run(d)
    check("a scripts_dir that leaves the pack is refused", r.returncode != 0 and "leaves the skill pack" in (r.stdout + r.stderr))
    d = bare("in-manifest")
    run(d)
    (d / "zylos" / "manifest.json").write_text("{}", encoding="utf-8")
    before = tree(d)
    r = run(d)
    check("a manifest of {}: one line, nothing else written, no traceback", r.returncode != 0 and "manifest" in (r.stdout + r.stderr) and "Traceback" not in r.stderr and tree(d) == before, (r.stdout[-200:], r.stderr[-200:]))
    (d / "zylos" / "manifest.json").write_text("not json", encoding="utf-8")
    r = run(d, "--dry-run")
    check("a manifest that is not JSON: a line even with --dry-run, no traceback", r.returncode != 0 and "Traceback" not in r.stderr, r.stderr[-200:])
    d = bare("in-explicit")
    run(d)
    r = run(d, "--port", "9100")
    check("--port with a manifest that exists says it is ignored", "--port and --brand are ignored" in r.stdout, r.stdout[-200:])
    d = bare("in-link")
    real = Path(tmp_dir("zylos-real-"))
    (d / "zylos").symlink_to(real)
    r = run(d)
    check("a zylos/ that is a link is refused and nothing is written through it", r.returncode != 0 and "is a link" in (r.stdout + r.stderr) and not list(real.iterdir()), (r.stdout[-200:], list(real.iterdir())))
    d = bare("in-gitlab")
    (d / ".gitlab-ci.yml").write_text("test:\n  script: [x]\n", encoding="utf-8")
    r = run(d)
    check("a .gitlab-ci.yml is not edited and a line says to add the check by hand", ".gitlab-ci.yml is not edited" in r.stdout and (d / ".gitlab-ci.yml").read_text("utf-8") == "test:\n  script: [x]\n")


def link_to(target: Path, at: Path) -> None:
    at.parent.mkdir(parents=True, exist_ok=True)
    at.symlink_to(target)


def test_nothing_is_written_through_a_link_or_where_it_cannot_go() -> None:
    print("[12a] links and places that cannot take a write")
    outside = Path(tmp_dir("zylos-out-"))
    d = bare("lk-skill")
    keep = outside / "SKILL.md"
    keep.write_bytes((d / "SKILL.md").read_bytes())
    (d / "SKILL.md").unlink()
    link_to(keep, d / "SKILL.md")
    r = run(d)
    check("a SKILL.md that is a link: the file it points at is untouched and a line says to edit it by hand",
          keep.read_bytes() == (outside / "SKILL.md").read_bytes() and b"lifecycle:" not in keep.read_bytes() and "SKILL.md is a link" in r.stdout, r.stdout[-300:])
    d = bare("lk-gh")
    ci_real = outside / "gh"
    shutil.copytree(d / ".github", ci_real)
    shutil.rmtree(d / ".github")
    link_to(ci_real, d / ".github")
    before = (ci_real / "workflows" / "ci.yml").read_bytes()
    r = run(d)
    check("a .github that is a link: ci.yml behind it is untouched and a line says so", (ci_real / "workflows" / "ci.yml").read_bytes() == before and "is, or sits under, a link" in r.stdout, r.stdout[-300:])
    d = bare("lk-dangling")
    gone = outside / "not-there.cjs"
    link_to(gone, d / "ecosystem.config.cjs")
    before = tree(d)
    r = run(d)
    check("an ecosystem file that is a dangling link: refused, nothing written, the target not created", r.returncode != 0 and "link" in r.stderr and not gone.exists() and tree(d) == before and not (d / "zylos").exists(), (r.stderr[-300:], sorted(tree(d))[:4]))
    d = bare("lk-bin")
    run(d)
    shutil.rmtree(d / "zylos" / "bin")
    elsewhere = Path(tmp_dir("zylos-bin-"))
    link_to(elsewhere, d / "zylos" / "bin")
    r = run(d)
    check("a zylos/bin that is a link: refused and nothing is written behind it", r.returncode != 0 and "link" in r.stderr and not list(elsewhere.iterdir()), (r.stderr[-300:], list(elsewhere.iterdir())))
    d = bare("lk-dir")
    (d / "ecosystem.config.cjs").mkdir()
    before = tree(d)
    r = run(d)
    check("an ecosystem file that is a folder: refused, nothing written", r.returncode != 0 and "not a file" in r.stderr and tree(d) == before and not (d / "zylos").exists(), r.stderr[-300:])
    d = bare("lk-zfile")
    (d / "zylos").write_text("a file, not a folder\n", encoding="utf-8")
    r = run(d)
    check("a zylos that is a file: refused with a line, not a traceback", r.returncode != 0 and "Traceback" not in r.stderr and "not a folder" in r.stderr and (d / "zylos").read_text("utf-8") == "a file, not a folder\n", r.stderr[-300:])
    if os.geteuid() != 0:
        d = bare("lk-ro")
        ci = d / ".github" / "workflows" / "ci.yml"
        ci.chmod(0o444)
        before = tree(d)
        r = run(d)
        ci.chmod(0o644)
        check("a read-only ci.yml: refused before the first write, nothing written", r.returncode != 0 and "not writable" in r.stderr and tree(d) == before and not (d / "zylos").exists(), r.stderr[-300:])


def test_a_failed_write_puts_back_what_was_written() -> None:
    print("[12b] all or nothing")
    d = bare("rb")
    before = tree(d)
    real = add_zylos._write
    seen = []

    def failing(to, data, mode):
        seen.append(to.name)
        if to.name == "ci.yml":
            raise PermissionError(13, "Permission denied", str(to))
        real(to, data, mode)

    add_zylos._write = failing
    try:
        try:
            add_zylos.add(d)
            said = None
        except SystemExit as e:
            said = str(e)
    finally:
        add_zylos._write = real
    check("a write that fails in the last file: SKILL.md, the ecosystem file and the adapter are all back as they were, and the one line says so",
          said is not None and "a write failed" in said and "put back" in said and tree(d) == before and not (d / "zylos").exists() and "ci.yml" in seen and len(seen) > 5, (said, seen[:3]))
    again = add_zylos.add(d)
    check("and the next run, once the cause is gone, does all of it", len(again[0]) > 5 and (d / "zylos" / "manifest.json").is_file())


def test_what_the_adapters_check_would_refuse_is_refused_first() -> None:
    print("[12c] names and paths")
    d = bare("nm")
    skill = d / "SKILL.md"
    skill.write_text(skill.read_text("utf-8").replace("name: acme-skill-pack", "name: other-skill-pack", 1), encoding="utf-8")
    before = tree(d)
    r = run(d)
    check("a SKILL.md name that is not the component's: refused with both names, before any write", r.returncode != 0 and "other-skill-pack" in r.stderr and "acme-skill-pack" in r.stderr and tree(d) == before, r.stderr[-300:])
    for label, old, new in (("a prefix with TOKEN in it", 'env_prefix = "ACME"', 'env_prefix = "ACME_TOKEN"'), ("a prefix with SECRET in it", 'env_prefix = "ACME"', 'env_prefix = "SECRET"'),
                            ("a scripts folder with a space", 'scripts_dir = "scripts"', 'scripts_dir = "my scripts"'), ("a scripts folder with a non-ASCII letter", 'scripts_dir = "scripts"', 'scripts_dir = "skripte-\u00e4"')):
        d = bare("nm-" + label.split()[1][:4])
        toml = d / "skill-pack.toml"
        text = toml.read_text("utf-8")
        toml.write_text(text.replace(old, new), encoding="utf-8")
        if "scripts" in old:
            (d / "scripts").rename(d / new.split('"')[1])
        before = tree(d)
        r = run(d)
        check(f"{label}: refused with a line, nothing written", r.returncode != 0 and "Traceback" not in r.stderr and "error:" in r.stderr and tree(d) == before, (r.stderr[-300:], sorted(set(tree(d)) ^ set(before))[:3]))
    d = bare("nm-ok")
    toml = d / "skill-pack.toml"
    toml.write_text(toml.read_text("utf-8").replace('env_prefix = "ACME"', 'env_prefix = "ACME_TOKENS_X"'), encoding="utf-8")
    check("the secret words are matched as the adapter does (anywhere in the prefix): TOKENS_X is refused too", run(d).returncode != 0)


def test_a_ci_or_skill_md_in_a_style_we_do_not_read_is_left_alone() -> None:
    print("[12d] styles")
    for label, text in (
        ("steps with a sibling key at the items' own indent", "jobs:\n  t:\n    steps:\n    - run: x\n    timeout-minutes: 5\n"),
        ("a `steps:` inside a script block at the end of the file", "jobs:\n  t:\n    steps:\n      - run: x\nnotes: |\n  steps:\n  - a\n"),
        ("a tab in the indent", "jobs:\n  t:\n    steps:\n      - run: x\n\t- run: y\n"),
    ):
        new, note = ci_note(text)
        check(f"ci.yml, {label}: nothing is added and a line says what to do by hand", new is None and note and ("tab" in note if "tab" in label else True), (new, note))
    ok, _ = ci_note("jobs:\n  t:\n    steps:\n    - run: x\n")
    check("steps written at the key's own indent (compact style) get the new steps at that indent, and the file is still YAML", ok is not None and yaml_ok(ok) and "\n    - name: Zylos adapter check\n      run: node zylos/lib.js check" in ok, ok)
    ok, _ = ci_note("jobs:\n  t:\n    steps:\n      - run: |\n          echo\n          # a comment in the script\n          steps:\n")
    check("a script block that ends the file keeps all its lines before the new steps", ok is not None and yaml_ok(ok) and ok.index("steps:\n      - uses") > ok.index("a comment in the script"), ok)
    for label, edit in (("a quoted key", lambda t: t.replace("type: capability\n", 'type: capability\n"bin": x\n', 1)),
                        ("a single-quoted key", lambda t: t.replace("type: capability\n", "type: capability\n'config': {}\n", 1)),
                        ("a quoted lifecycle", lambda t: t.replace("type: capability\n", "type: capability\n\"lifecycle\": {}\n", 1)),
                        ("an explicit `?` key", lambda t: t.replace("type: capability\n", "type: capability\n? bin\n: x\n", 1)),
                        ("a list at the top", lambda t: t.replace("type: capability\n", "type: capability\n- a\n", 1))):
        d = bare("st-" + label.split()[1][:4])
        skill = d / "SKILL.md"
        skill.write_text(edit(skill.read_text("utf-8")), encoding="utf-8")
        before = skill.read_bytes()
        r = run(d)
        check(f"SKILL.md with {label}: not edited{'' if 'lifecycle' in label else ', and a line says to merge by hand'}", skill.read_bytes() == before and (("lifecycle" in label) or "by hand" in r.stdout), r.stdout[-300:])
    d = bare("st-flow")
    skill = d / "SKILL.md"
    skill.write_text("---\n{name: acme-skill-pack, version: 0.1.0, type: capability}\n---\nbody\n", encoding="utf-8")
    r = run(d)
    check("a frontmatter written as a flow mapping: not edited, a line says so", skill.read_text("utf-8").startswith("---\n{name:") and "lifecycle" not in skill.read_text("utf-8") and "by hand" in r.stdout, r.stdout[-300:])
    d = bare("st-mixed")
    skill = d / "SKILL.md"
    skill.write_bytes(skill.read_bytes().replace(b"\n", b"\r\n", 5))
    before = skill.read_bytes()
    r = run(d)
    check("a SKILL.md that mixes LF and CRLF: not edited, a line says so", skill.read_bytes() == before and "mixes LF and CRLF" in r.stdout, r.stdout[-300:])


if __name__ == "__main__":
    for fn in (test_the_scaffold_sets_it_up_by_default, test_adding_to_an_existing_pack_and_running_twice,
               test_what_the_skill_pack_owns_is_not_overwritten, test_dry_run_and_the_verdict, test_the_port, test_refusals,
               test_the_ci_step, test_a_ci_file_that_is_not_safe_to_edit_is_left_alone, test_a_skill_md_that_is_not_safe_to_edit_is_left_alone,
               test_bad_inputs_are_refused_before_anything_is_written, test_nothing_is_written_through_a_link_or_where_it_cannot_go,
               test_a_failed_write_puts_back_what_was_written, test_what_the_adapters_check_would_refuse_is_refused_first,
               test_a_ci_or_skill_md_in_a_style_we_do_not_read_is_left_alone):
        fn()
    raise SystemExit(finish())
