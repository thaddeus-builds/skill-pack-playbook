#!/usr/bin/env python3
"""kit/tools/prune_codes.py removes exactly the skill pack's own message codes that nothing emits.

  1. A throwaway pack (the kit's fake one) with three planted codes: one unemitted in its main registry, one unemitted in a fragment that also holds
     an emitted code, and a fragment whose every code is unemitted. --dry-run lists the three and changes nothing.
  2. A real run removes those three rows and no other: the emitted codes stay, the main file keeps its header, the half-used fragment keeps its
     emitted code, the all-unemitted fragment is deleted, and the kit's own codes are untouched whether emitted or not.
  3. Afterwards the registry still loads, `check_registry_closed` has no "registered but no msg() call emits it" line, and a second run finds nothing.
  4. A code emitted only in a file outside the sources is pruned (the sources are the claim), and the same code stays when the sources name that file.
"""

import shutil
import sys
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

finish()
