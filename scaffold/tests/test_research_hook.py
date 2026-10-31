#!/usr/bin/env python3
"""scaffold/skeleton/claude/hooks/research_first.py: read what is kept before the first web search of each agent.

Run as Claude Code runs it: the hook input on stdin, the answer on stdout, a private TMPDIR for its once-per-agent markers.

  1. The first WebSearch of a session is refused once with `hookSpecificOutput.permissionDecision` deny; the reason holds the rows of both indexes and
     the steps; the retry, and every later call, goes through with no output.
  2. A subagent (`agent_id`) and another session each get their own one refusal.
  3. A pack with no index is told to create it; an index of a hundred rows is cut, with the count left over.
  4. It fails open: empty input, malformed input, no session id.
  5. The project folder is `CLAUDE_PROJECT_DIR` when set, else the input's `cwd`.
  6. The settings file the scaffold writes matches WebSearch and WebFetch and runs this file; the scaffold maps both files into `.claude/`.
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

import new_skill_pack  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

SKELETON = PLAYBOOK / "scaffold" / "skeleton" / "claude"
HOOK = SKELETON / "hooks" / "research_first.py"


def run(stdin: str, tmp: Path, project: Path | None = None, **env: str) -> tuple[int, str]:
    e = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    e["TMPDIR"] = str(tmp)
    if project:
        e["CLAUDE_PROJECT_DIR"] = str(project)
    e.update(env)
    r = subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, env=e)
    return r.returncode, r.stdout


def call(tmp: Path, project: Path, session: str = "s1", **extra) -> tuple[int, str]:
    return run(json.dumps({"session_id": session, "hook_event_name": "PreToolUse", "tool_name": "WebSearch", **extra}), tmp, project)


def make_pack(root: Path, rows: int = 2) -> Path:
    (root / "docs/research").mkdir(parents=True)
    (root / "docs/prior-art").mkdir(parents=True)
    table = "| File | Question | Date | Answer |\n| --- | --- | --- | --- |\n"
    table += "".join(f"| [q{i}.md](q{i}.md) | question number {i} | 2026-10-0{i % 9 + 1} | answer {i} |\n" for i in range(rows))
    (root / "docs/research/README.md").write_text("# Research\n\n" + table)
    (root / "docs/prior-art/README.md").write_text("# Prior art\n\n- [Old tools](2026-09-01-old.md), keep ours\n")
    return root


def main() -> int:
    work = Path(tmp_dir("rhook-"))

    print("[1] refused once, then through")
    pack, tmp = make_pack(work / "p1"), work / "t1"
    tmp.mkdir()
    code, out = call(tmp, pack)
    doc = json.loads(out) if out else {}
    h = doc.get("hookSpecificOutput", {})
    why = h.get("permissionDecisionReason", "")
    check("exit 0 and one JSON document", code == 0 and bool(doc), out[:200])
    check("the shape Claude Code reads", h.get("hookEventName") == "PreToolUse" and h.get("permissionDecision") == "deny", h)
    check("the reason holds the research row and the prior-art row", "question number 1" in why and "Old tools" in why, why[:400])
    check("the reason holds the steps", "Researched YYYY-MM-DD" in why and "Retry" in why)
    check("the reason is short", len(why) < 3600, len(why))
    code, out = call(tmp, pack)
    check("the retry goes through with no output", code == 0 and out == "", out[:200])
    code, out = call(tmp, pack)
    check("so does every later call", code == 0 and out == "")

    print("[2] each agent, each session")
    code, out = call(tmp, pack, agent_id="sub-1")
    check("a subagent is refused once", '"deny"' in out)
    code, out = call(tmp, pack, agent_id="sub-1")
    check("and then goes through", out == "")
    code, out = call(tmp, pack, session="s2")
    check("another session is refused once", '"deny"' in out)

    print("[3] no index, many rows")
    bare, tmp3 = work / "p3", work / "t3"
    bare.mkdir(), tmp3.mkdir()
    code, out = call(tmp3, bare)
    why = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    check("a pack with nothing kept is told to create the index", "Nothing is kept yet" in why and "research-index.md" in why, why[-300:])
    big, tmp4 = make_pack(work / "p4", rows=100), work / "t4"
    tmp4.mkdir()
    code, out = call(tmp4, big)
    why = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    check("a hundred rows are cut and the rest counted", "more rows in the indexes" in why and len(why) < 4000, len(why))

    print("[4] fails open")
    tmp5 = work / "t5"
    tmp5.mkdir()
    check("empty input passes", run("", tmp5, pack) == (0, ""))
    check("malformed input passes", run("{not json", tmp5, pack) == (0, ""))
    check("no session id passes", run(json.dumps({"tool_name": "WebSearch"}), tmp5, pack) == (0, ""))
    check("the marker folder is not created by a failure", not any(tmp5.iterdir()), list(tmp5.iterdir()))

    print("[5] the project folder")
    tmp6, elsewhere = work / "t6", work / "elsewhere"
    tmp6.mkdir(), elsewhere.mkdir()
    code, out = run(json.dumps({"session_id": "s9", "cwd": str(pack)}), tmp6)
    check("without CLAUDE_PROJECT_DIR the input's cwd is read", "question number 1" in out, out[:200])
    code, out = run(json.dumps({"session_id": "s10", "cwd": str(elsewhere)}), tmp6, pack)
    check("CLAUDE_PROJECT_DIR wins over cwd", "question number 1" in out, out[:200])

    print("[6] the settings and the scaffold")
    s = json.loads((SKELETON / "settings.json").read_text())
    group = s["hooks"]["PreToolUse"][0]
    hook = group["hooks"][0]
    check("matches WebSearch and WebFetch", set(group["matcher"].split("|")) == {"WebSearch", "WebFetch"}, group["matcher"])
    check("runs this file from the project folder", hook["type"] == "command" and hook["args"] == ["${CLAUDE_PROJECT_DIR}/.claude/hooks/research_first.py"], hook)
    t = new_skill_pack.SKELETON_TARGETS
    check("the scaffold maps both files into .claude/", t.get("claude/settings.json") == ".claude/settings.json"
          and t.get("claude/hooks/research_first.py") == ".claude/hooks/research_first.py", t)
    check("no placeholder is left in either", "{{" not in HOOK.read_text() and "{{" not in (SKELETON / "settings.json").read_text())
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
