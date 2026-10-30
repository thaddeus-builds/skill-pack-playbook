#!/usr/bin/env python3
"""kit/tools/prune_codes.py removes exactly the skill pack's own message codes that nothing emits.

  1. A throwaway pack (the kit's fake one) with three planted codes: one unemitted in its main registry, one unemitted in a fragment that also holds
     an emitted code, and a fragment whose every code is unemitted. --dry-run lists the three and changes nothing.
  2. A real run removes those three rows and no other: the emitted codes stay, the main file keeps its header, the half-used fragment keeps its
     emitted code, the all-unemitted fragment is deleted, and the kit's own codes are untouched whether emitted or not.
  3. Afterwards the registry still loads, `check_registry_closed` has no "registered but no msg() call emits it" line, and a second run finds nothing.
  4. A code emitted only in a file outside the sources is pruned (the sources are the claim), and the same code stays when the sources name that file.
  5. A scan it cannot trust deletes nothing: a source that matches no file, a file that does not parse, a call with no literal code, a root whose name
     holds glob characters (read, not mistaken for no sources), a registry file that is a link (not written through), CRLF kept, no temporary left.
  6. (the second cold review) The temporary file has a name nobody chose, so a link or a folder at a guessable name is harmless; the mode is kept; two runs
     at once end the same as one; a folder named like a source, a dangling link, an unreadable file, a null byte and a nested expression are refused or
     ignored cleanly; `venv/` is not read; a main registry with every row unemitted keeps its header; a link inside the pack and a fragment folder that
     leads outside are skipped; a folder that cannot take the new file is a line, not a traceback.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import config, messages  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402
from kit.tools import prune_codes  # noqa: E402

HEADER = "code\tparams\tmeaning_en\tmeaning_zh\n"


def row(code):
    return f"{code}\t\tmeaning of {code}\t{code} 的意思\n"


def make():
    """A copy of the fake pack with planted registries and a script that emits two of its codes."""
    root = Path(tmp_dir("prune-")) / "shop"
    shutil.copytree(_shop.SHOP, root, ignore=shutil.ignore_patterns("__pycache__"))
    ssot = root / "ssot"
    main = ssot / "message_codes.tsv"
    main.write_text(main.read_text(encoding="utf-8").rstrip("\n") + "\n" + row("old_main_code"), encoding="utf-8")
    frag = ssot / "message_codes.d"
    frag.mkdir(exist_ok=True)
    (frag / "half.tsv").write_text(HEADER + row("kept_in_half") + row("old_half_code"), encoding="utf-8")
    (frag / "dead.tsv").write_text(HEADER + row("old_dead_one") + row("old_dead_two"), encoding="utf-8")
    scripts = root / config.use(root).scripts_dir
    (scripts / "emits.py").write_text('from kit.messages import msg\n\ndef f():\n    return msg("kept_in_half", "x")\n', encoding="utf-8")
    return root


def emitted_in(root):
    cfg = config.use(root)
    return messages.check_registry_closed(root, [f"{cfg.scripts_dir}/emits.py"], messages.registry())


root = make()
cfg = config.use(root)
main = root / "ssot" / "message_codes.tsv"
before = {p: p.read_text(encoding="utf-8") for p in [main, *(root / "ssot" / "message_codes.d").glob("*.tsv")]}
sources = [f"{cfg.scripts_dir}/emits.py"]
mains_codes = [ln.split("\t")[0] for ln in main.read_text(encoding="utf-8").splitlines()[1:] if ln.strip()]

print("[1] --dry-run")
found = prune_codes.prune(root, sources, dry_run=True)
mine = {Path(f).name: c for f, c in found.items()}
check("the three planted files are listed with their unemitted codes (the main file's other codes are unemitted too, in this fake pack)",
      mine.get("dead.tsv") == ["old_dead_one", "old_dead_two"] and mine.get("half.tsv") == ["old_half_code"] and "old_main_code" in mine.get("message_codes.tsv", []), mine)
check("a dry run changes nothing", all(p.read_text(encoding="utf-8") == t for p, t in before.items()) and (root / "ssot" / "message_codes.d" / "dead.tsv").is_file())

print("[2] a real run")
# the fake pack's own main registry codes are emitted by its scripts; give the sources the whole scripts folder so only the planted ones are unemitted
sources = [f"{cfg.scripts_dir}/**/*.py"]
found = prune_codes.prune(root, sources)
mine = {Path(f).name: c for f, c in found.items()}
check("exactly the three planted codes are removed, from three files", mine == {"dead.tsv": ["old_dead_one", "old_dead_two"], "half.tsv": ["old_half_code"], "message_codes.tsv": ["old_main_code"]}, mine)
check("the all-unemitted fragment is deleted", not (root / "ssot" / "message_codes.d" / "dead.tsv").exists())
check("the half-used fragment keeps its header and its emitted code only",
      (root / "ssot" / "message_codes.d" / "half.tsv").read_text(encoding="utf-8") == HEADER + row("kept_in_half"))
after_main = main.read_text(encoding="utf-8")
check("the main registry keeps its header and every other row", after_main.split("\n")[0] == "\t".join(["code", "params", "meaning_en", "meaning_zh"]) and "old_main_code" not in after_main
      and all(c in after_main for c in mains_codes if c != "old_main_code"), after_main[:200])
check("the kit's own codes are untouched", all(c in messages.registry() for c in ("unclassified_error",)) and messages.registry()["unclassified_error"]["origin"] == "kit")

print("[3] afterwards")
config.use(root)
reg = messages.registry()
check("the registry still loads and no longer holds the three", all(c not in reg for c in ("old_main_code", "old_half_code", "old_dead_one", "old_dead_two")) and "kept_in_half" in reg)
probs = [p for p in messages.check_registry_closed(root, sources, reg) if "registered but no msg() call emits it" in p]
check("no 'registered but no msg() call emits it' line is left", probs == [], probs[:3])
check("a second run finds nothing", prune_codes.prune(root, sources) == {})

print("[4] the sources are the claim, and the default reads the whole pack")
root2 = make()
config.use(root2)
other = root2 / "elsewhere"
other.mkdir()
(other / "late.py").write_text('from kit.messages import msg\n\ndef g():\n    return msg("old_half_code", "x")\n', encoding="utf-8")
cfg2 = config.config()
s_in = [f"{cfg2.scripts_dir}/**/*.py", "elsewhere/*.py"]
check("a code emitted in a file the sources name stays", "old_half_code" not in {c for cs in prune_codes.unemitted(root2, s_in).values() for c in cs})
check("the default (every .py under the root) keeps a code emitted outside the scripts folder", "old_half_code" not in {c for cs in prune_codes.unemitted(root2, ["**/*.py"]).values() for c in cs})
check("the same code is pruned when the sources leave that file out", "old_half_code" in {c for cs in prune_codes.unemitted(root2, [f"{cfg2.scripts_dir}/**/*.py"]).values() for c in cs})

print("[5] a scan it cannot trust deletes nothing")


def snapshot(r):
    return {p: p.read_bytes() for p in sorted((r / "ssot").rglob("*.tsv"))}


root3 = make()
cfg3 = config.use(root3)
snap = snapshot(root3)
for label, srcs in (("a source that matches nothing", [f"{cfg3.scripts_dir}/**/*.py", "nosuch/*.py"]), ("only a mistyped folder", ["scirpts/**/*.py"]), ("a bare folder name", [cfg3.scripts_dir])):
    try:
        prune_codes.prune(root3, srcs)
        refused = None
    except prune_codes.Refused as e:
        refused = str(e)
    check(f"{label}: refused, and no registry file changed", refused is not None and snapshot(root3) == snap, refused)
(root3 / cfg3.scripts_dir / "broken.py").write_text("def (:\n", encoding="utf-8")
try:
    prune_codes.prune(root3, [f"{cfg3.scripts_dir}/**/*.py"])
    refused = None
except prune_codes.Refused as e:
    refused = str(e)
check("a source file that does not parse: refused (its codes would look unemitted), nothing changed", refused is not None and "cannot be read as Python" in refused and snapshot(root3) == snap, refused)
(root3 / cfg3.scripts_dir / "broken.py").write_text('from kit.messages import msg\n\ndef f(c):\n    return msg(c, "x")\n', encoding="utf-8")
try:
    prune_codes.prune(root3, [f"{cfg3.scripts_dir}/**/*.py"])
    refused = None
except prune_codes.Refused as e:
    refused = str(e)
check("a msg() call whose code is not a literal: refused, nothing changed", refused is not None and "not a string literal" in refused and snapshot(root3) == snap, refused)
check("the command line says so and exits 2", prune_codes.main(["--root", str(root3), "--sources", "nosuch/*.py", "--dry-run"]) == 2)
(root3 / cfg3.scripts_dir / "broken.py").unlink()

root4 = make()
cfg4 = config.use(root4)
moved = root4.parent / "br[1]x"
shutil.copytree(root4, moved)
config.use(moved)
found = prune_codes.unemitted(moved, [f"{cfg4.scripts_dir}/**/*.py"])
check("a root whose own name holds glob characters is read (its scripts are found, so an emitted code is not pruned)", "kept_in_half" not in {c for cs in found.values() for c in cs} and found, found)

root5 = make()
cfg5 = config.use(root5)
dead = root5 / "ssot" / "message_codes.d" / "dead.tsv"
outside = Path(tmp_dir("prune-outside-")) / "other.tsv"
outside.write_text(HEADER + row("other_packs_code"), encoding="utf-8")
dead.unlink()
dead.symlink_to(outside)
config.use(root5)
before_outside = outside.read_bytes()
prune_codes.prune(root5, [f"{cfg5.scripts_dir}/**/*.py"])
check("a registry file that is a link is not written through: the file it points at is untouched", outside.read_bytes() == before_outside and dead.is_symlink())

root6 = make()
cfg6 = config.use(root6)
half = root6 / "ssot" / "message_codes.d" / "half.tsv"
half.write_bytes((HEADER + row("kept_in_half") + row("old_half_code")).replace("\n", "\r\n").encode("utf-8"))
config.use(root6)
prune_codes.prune(root6, [f"{cfg6.scripts_dir}/**/*.py"])
check("CRLF line endings are kept, the unemitted row is gone, no temporary file is left",
      half.read_bytes() == (HEADER + row("kept_in_half")).replace("\n", "\r\n").encode("utf-8") and not list((root6 / "ssot").rglob("*.prune-tmp")), half.read_bytes())

print("[6] found by the second cold review")


def refused(fn):
    try:
        fn()
    except prune_codes.Refused as e:
        return str(e)
    return None


def all_sources(r):
    return [f"{config.use(r).scripts_dir}/**/*.py"]


root7 = make()
srcs = all_sources(root7)
half = root7 / "ssot" / "message_codes.d" / "half.tsv"
victim = Path(tmp_dir("prune-victim-")) / "victim.txt"
victim.write_text("do not touch\n", encoding="utf-8")
(half.parent / "half.tsv.prune-tmp").symlink_to(victim)                     # the name the first version wrote to
(half.parent / "dead.tsv.prune-tmp").mkdir()                                # and a folder at another
half.chmod(0o640)
ino = half.stat().st_ino
prune_codes.prune(root7, srcs)
check("a link left at the old temporary name is not written through, and a folder at one does not stop the run", victim.read_text(encoding="utf-8") == "do not touch\n"
      and half.read_text(encoding="utf-8") == HEADER + row("kept_in_half") and not half.is_symlink() and (half.parent / "half.tsv.prune-tmp").is_symlink(), half.read_text(encoding="utf-8"))
check("the file's mode is kept and the new content is a new file renamed over the old one", (half.stat().st_mode & 0o777) == 0o640 and half.stat().st_ino != ino, oct(half.stat().st_mode))

start_script = ("import sys, time\nsys.path.insert(0, %r)\nfrom kit.tools import prune_codes\ntime.sleep(max(0.0, float(sys.argv[2]) - time.time()))\n"
                "raise SystemExit(prune_codes.main(['--root', sys.argv[1], '--sources', %r]))\n")
bad_runs = []
for _ in range(6):
    r8 = make()
    scripts = f"{config.use(r8).scripts_dir}/**/*.py"
    begin = time.time() + 1.5
    ps = [subprocess.Popen([sys.executable, "-c", start_script % (str(Path(__file__).resolve().parents[2]), scripts), str(r8), str(begin)], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True) for _ in range(3)]
    outs = [(p.communicate(), p.returncode) for p in ps]
    final = {q.name: q.read_text(encoding="utf-8") for q in sorted((r8 / "ssot").rglob("*.tsv"))}
    bad_runs += [o for o in outs if o[1] != 0 or "Traceback" in o[0][1]]
    bad_runs += [] if "old_main_code" not in final.get("message_codes.tsv", "") and "dead.tsv" not in final and "old_half_code" not in final.get("half.tsv", "") else ["state"]
check("three runs at once, six times: every one exits 0 without a traceback and the registries end as after one run", not bad_runs, bad_runs[:2])

root9 = make()
cfg9 = config.use(root9)
scripts9 = root9 / cfg9.scripts_dir
snap9 = {q: q.read_bytes() for q in sorted((root9 / "ssot").rglob("*.tsv"))}
(scripts9 / "folder.py").mkdir()
(scripts9 / "dangling.py").symlink_to(root9 / "nowhere.py")
check("a folder named x.py and a link to nothing are not sources: the run goes on", refused(lambda: prune_codes.prune(root9, all_sources(root9), dry_run=True)) is None)
(scripts9 / "folder.py").rmdir()
(scripts9 / "dangling.py").unlink()
(scripts9 / "nul.py").write_bytes(b"x = 1\x00\n")
why = refused(lambda: prune_codes.prune(root9, all_sources(root9)))
check("a source with a null byte: refused with a line, nothing deleted", why is not None and "cannot be read as Python" in why and {q: q.read_bytes() for q in snap9} == snap9, why)
(scripts9 / "nul.py").write_text("x = " + "+".join(["1"] * 200000) + "\n", encoding="utf-8")
why = refused(lambda: prune_codes.prune(root9, all_sources(root9)))
check("a source nested past the parser's limit: refused with a line, not a traceback", why is not None and "cannot be read as Python" in why, why)
(scripts9 / "nul.py").unlink()
if os.geteuid() != 0:
    (scripts9 / "locked.py").write_text("x = 1\n", encoding="utf-8")
    (scripts9 / "locked.py").chmod(0)
    why = refused(lambda: prune_codes.prune(root9, all_sources(root9)))
    (scripts9 / "locked.py").chmod(0o644)
    check("a source that cannot be read: refused with a line, nothing deleted", why is not None and "cannot be read as Python" in why and {q: q.read_bytes() for q in snap9} == snap9, why)
(scripts9 / "locked.py").unlink(missing_ok=True)
venv = root9 / "venv" / "lib"
venv.mkdir(parents=True)
(venv / "template.py").write_text("def (:\n", encoding="utf-8")
check("a venv/ folder is not read: its files cannot refuse the run", refused(lambda: prune_codes.prune(root9, ["**/*.py"], dry_run=True)) is None)

root10 = make()
cfg10 = config.use(root10)
prune_codes.prune(root10, [f"{cfg10.scripts_dir}/emits.py"])
main10 = root10 / "ssot" / "message_codes.tsv"
config.use(root10)
check("a main registry whose every row is unemitted keeps its header (it is not deleted) and the registry still loads, with the code that is emitted",
      main10.is_file() and main10.read_text(encoding="utf-8").split("\n")[0].startswith("code\t") and not [ln for ln in main10.read_text(encoding="utf-8").splitlines()[1:] if ln.strip()]
      and "kept_in_half" in messages.registry(), main10.read_text(encoding="utf-8")[:200])

root11 = make()
cfg11 = config.use(root11)
frag = root11 / "ssot" / "message_codes.d"
real_half = root11 / "ssot" / "half-real.tsv"
(frag / "half.tsv").rename(real_half)
(frag / "half.tsv").symlink_to(real_half)
before_real = real_half.read_bytes()
prune_codes.prune(root11, [f"{cfg11.scripts_dir}/**/*.py"])
check("a fragment that is a link to a file inside the pack is skipped: the link and the file are untouched", (frag / "half.tsv").is_symlink() and real_half.read_bytes() == before_real)

root12 = make()
cfg12 = config.use(root12)
outside_dir = Path(tmp_dir("prune-outside-dir-")) / "message_codes.d"
shutil.copytree(root12 / "ssot" / "message_codes.d", outside_dir)
shutil.rmtree(root12 / "ssot" / "message_codes.d")
(root12 / "ssot" / "message_codes.d").symlink_to(outside_dir)
before_out = {q.name: q.read_bytes() for q in outside_dir.glob("*.tsv")}
config.use(root12)
prune_codes.prune(root12, [f"{cfg12.scripts_dir}/**/*.py"])
check("a fragment folder that leads outside the pack is skipped: nothing in it changed", {q.name: q.read_bytes() for q in outside_dir.glob("*.tsv")} == before_out and before_out, sorted(before_out))

if os.geteuid() != 0:
    root13 = make()
    cfg13 = config.use(root13)
    frag13 = root13 / "ssot" / "message_codes.d"
    frag13.chmod(0o555)
    try:
        why = refused(lambda: prune_codes.prune(root13, [f"{cfg13.scripts_dir}/**/*.py"]))
    finally:
        frag13.chmod(0o755)
    check("a fragment folder that cannot take a new file: a line that says so, not a traceback, and no temporary file left", why is not None and "cannot be written" in why
          and not list(frag13.glob("*.prune-tmp")), why)

finish()
