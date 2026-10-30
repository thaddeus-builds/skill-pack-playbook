#!/usr/bin/env python3
"""kit/tools/eval_ledger.py: where an eval agent's turns and tool output went.

  [1] a Bash command's kind: the entry run (any leading path, `.py`, after
      `cd ... &&`) is a verb, asked only for help is help; a read of the
      skill pack is docs (prose) or source (the rest); SKILL.md anywhere is
      docs; a listing is explore; the client's files, the agent's own
      scripts and an entry behind a variable are other
  [2] the other tools: Read by its path, Glob and Grep explore, the rest other
  [3] tokens once per model call: lines sharing a message id are one call,
      a line without an id is its own
  [4] the bytes each tool_result handed back go to its call's kind (string
      or block content); a result with no known call is other; the learning
      share and the first verb's call number
  [5] several transcripts: summed, the first verb's call the median; a line
      that is not a JSON object is skipped and counted, a blank one is not
  [6] the CLI: the text ledger, --json one document, exit 2 without --cli
      or on a file it cannot read
"""

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from kit.testing.check import capture, check, finish, one_doc, tmp_dir  # noqa: E402
from kit.tools import eval_ledger as el  # noqa: E402

PACKS = ["skill_pack/", "scripts/"]
ENTRY = el.entry_pattern(["shop"])


def bash(command: str) -> str:
    return el.classify("Bash", {"command": command}, ENTRY, PACKS)


def call(i: int, name: str, inp: dict, msg_id: str = "", usage: dict | None = None) -> str:
    msg = {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": name,
                                             "input": inp}]}
    if msg_id:
        msg["id"] = msg_id
    if usage is not None:
        msg["usage"] = usage
    return json.dumps({"type": "assistant", "message": msg})


def result(i: int, content) -> str:
    return json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": f"t{i}", "content": content}]}})


USAGE = {"input_tokens": 3, "cache_read_input_tokens": 1000,
         "cache_creation_input_tokens": 50, "output_tokens": 20}

RUN = [
    call(1, "Read", {"file_path": "/w/skill_pack/SKILL.md"}, "m1", USAGE),
    call(2, "Bash", {"command": "./shop plan add --help"}, "m1", USAGE),
    result(1, "x" * 300),
    result(2, [{"type": "text", "text": "y" * 100}]),
    call(3, "Bash", {"command": "./shop compute status --json"}, "m2", USAGE),
    result(3, "z" * 200),
    call(4, "Bash", {"command": "python3 -c 'print(1)'"}, "", USAGE),
    result(4, "ok"),
    result(99, "orphan"),
]


def main() -> int:
    print("[1] a Bash command's kind")
    for command, kind in {
        "./shop facts set a b": "verb",
        "/w/bin/shop compute gap --json": "verb",
        "shop.py ingest": "verb",
        "cd /w && ./shop plan list": "verb",
        "./shop plan --help": "help",
        "shop plan add -h | head -40": "help",
        "./shop plan --help && ./shop plan list": "verb",
        "cat /w/skill_pack/SKILL.md": "docs",
        "sed -n 1,80p skill_pack/docs/onboard.md": "docs",
        "head -50 SKILL.md": "docs",
        "grep -n def scripts/plan.py": "source",
        "cd skill_pack && cat skill_pack/ssot/workflow.tsv": "source",
        "P=/w; cat skill_pack/a.md skill_pack/b.tsv": "source",
        "ls -la /w": "explore",
        "find . -name '*.json'": "explore",
        "cat workspace/intake/company_profile.md": "other",
        "python3 /tmp/compare.py a.json b.json": "other",
        "S=./shop; $S plan add --kind fix": "other",
        "echo shopping": "other",
    }.items():
        check(f"{command!r} is {kind}", bash(command) == kind, bash(command))

    print("[2] the other tools")
    check("Read of the skill pack's prose is docs",
          el.classify("Read", {"file_path": "/w/skill_pack/README.md"}, ENTRY, PACKS) == "docs")
    check("Read of its code is source",
          el.classify("Read", {"file_path": "/w/scripts/plan.py"}, ENTRY, PACKS) == "source")
    check("Read of a client file is other",
          el.classify("Read", {"file_path": "/w/workspace/brief.md"}, ENTRY, PACKS) == "other")
    check("Glob and Grep are explore",
          {el.classify(n, {}, ENTRY, PACKS) for n in ("Glob", "Grep")} == {"explore"})
    check("Write, Edit and any other tool are other",
          {el.classify(n, {}, ENTRY, PACKS) for n in ("Write", "Edit", "Skill")} == {"other"})

    print("[3] tokens once per model call")
    r = el.ledger(RUN, ["shop"], PACKS)
    check("two lines of m1, one of m2 and one without an id are three calls",
          r["model_calls"] == 3, r["model_calls"])
    check("each call's usage counted once",
          r["tokens"] == {"input_tokens": 9, "cache_read_input_tokens": 3000,
                          "cache_creation_input_tokens": 150, "output_tokens": 60}, r["tokens"])

    print("[4] the bytes per kind, the learning share, the first verb")
    k = r["kinds"]
    check("docs 300, help 100, verb 200",
          (k["docs"]["result_bytes"], k["help"]["result_bytes"], k["verb"]["result_bytes"])
          == (300, 100, 200), k)
    check("the agent's own script and the orphan result are other",
          k["other"] == {"calls": 1, "result_bytes": 2 + 6}, k["other"])
    check("four tool calls, two of them learning",
          (r["tool_calls"], r["learning_calls"]) == (4, 2), r)
    check("learning share: 400 of 608 bytes", r["learning_share"] == round(400 / 608, 3),
          r["learning_share"])
    check("the first verb is the third call", r["first_verb_call"] == 3, r["first_verb_call"])
    check("a run with no result has no share",
          el.ledger([call(1, "Bash", {"command": "ls"})], ["shop"], PACKS)["learning_share"]
          is None)

    print("[5] several transcripts, unreadable lines")
    late = el.ledger(RUN[4:] + RUN[:4], ["shop"], PACKS)
    none = el.ledger([call(1, "Bash", {"command": "ls"}), "not json", "[1]", "  "], ["shop"], PACKS)
    check("a line that is not a JSON object is counted, a blank one is not",
          none["unreadable_lines"] == 2, none["unreadable_lines"])
    t = el.combine([r, late, none])
    check("calls and bytes are summed",
          t["tool_calls"] == 9 and t["kinds"]["docs"]["result_bytes"] == 600, t)
    check("the first verb's call is the median of the runs that ran one",
          (late["first_verb_call"], t["first_verb_call"]) == (1, 3), t["first_verb_call"])
    check("unreadable lines are summed", t["unreadable_lines"] == 2)

    print("[6] the CLI")
    d = Path(tmp_dir("ledger-"))
    f = d / "run.jsonl"
    f.write_text("\n".join(RUN) + "\n", encoding="utf-8")
    rc, out, _ = capture(el.main, [str(f), "--cli", "./shop", "--pack", "skill_pack/"])
    check("the text ledger names the run and every kind",
          rc == 0 and "3 model calls, 4 tool calls" in out
          and all(f"\n{kind:8}" in out for kind in el.KINDS), out)
    rc, out, _ = capture(el.main, [str(f), str(f), "--cli", "shop", "--json"])
    doc = one_doc(out)
    check("--json is one document with both runs and their total",
          rc == 0 and doc and len(doc["transcripts"]) == 2
          and doc["total"]["tool_calls"] == 8, out[:300])
    rc, _, err = capture(el.main, [str(f)])
    check("no --cli: exit 2", rc == 2, err)
    rc, _, err = capture(el.main, [str(d / "missing.jsonl"), "--cli", "shop"])
    check("a file it cannot read: exit 2, named", rc == 2 and "missing.jsonl" in err, err)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
