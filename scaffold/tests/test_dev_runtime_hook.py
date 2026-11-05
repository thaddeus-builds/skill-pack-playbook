#!/usr/bin/env python3
"""scaffold/skeleton/claude/hooks/dev_not_runtime.py: no standing task on the development machine runs the skill pack (R44).

Run as Claude Code runs it, filled as the scaffolder fills it (the CLI word and the name): the hook input on stdin, the answer on stdout.

  1. A scheduled task whose prompt runs the pack's CLI, names the pack, or runs a script under tools/ is refused with
     `hookSpecificOutput.permissionDecision` deny, and the reason says why and what to do.
  2. A task that runs nothing of the pack goes through with no output, and so does a word that only contains the CLI word.
  3. It fails open: empty input, malformed input, no tool input.
  4. The settings file the scaffold writes runs it for the scheduling tools, and the scaffold maps it into .claude/hooks/.
"""

import json
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
HOOK = SKELETON / "hooks" / "dev_not_runtime.py"


def filled() -> Path:
    path = Path(tmp_dir("devhook-")) / "dev_not_runtime.py"
    text = new_skill_pack.fill(HOOK.read_text(encoding="utf-8"), {"cli": "acme", "name": "acme-skill-pack"}, "hook")
    path.write_text(text, encoding="utf-8")
    return path


def call(hook: Path, stdin: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(hook)], input=stdin, capture_output=True, text=True)
    return r.returncode, r.stdout


def task(prompt: str, tool: str = "mcp__scheduled-tasks__create_scheduled_task") -> str:
    return json.dumps({"session_id": "s1", "hook_event_name": "PreToolUse", "tool_name": tool,
                       "tool_input": {"taskId": "morning", "cronExpression": "0 7 * * *", "prompt": prompt}})


def main() -> int:
    hook = filled()
    print("[1] a task that runs the pack is refused")
    for prompt in ("Every morning run `~/x/acme-skill-pack/bin/acme routine run --json` and report",
                   "cd ~/code/acme-skill-pack && python3 scripts/acme.py pull",
                   "python3 ~/somewhere/tools/run_routine.py --pack ~/client"):
        code, out = call(hook, task(prompt))
        h = (json.loads(out) if out else {}).get("hookSpecificOutput", {})
        check(f"refused: {prompt[:50]}", code == 0 and h.get("hookEventName") == "PreToolUse"
              and h.get("permissionDecision") == "deny", out[:200])
    why = h.get("permissionDecisionReason", "")
    check("the reason says why and what to do", "Development is not runtime" in why and "by hand" in why
          and "runtime" in why and "tools/" in why, why)
    code, out = call(hook, json.dumps({"tool_name": "CronCreate", "tool_input": {"cron": "*/5 * * * *",
                                                                                "prompt": {"steps": ["run acme doctor"]}}}))
    check("a prompt nested anywhere in the input is read", '"deny"' in out, out[:200])

    print("[2] a task that runs nothing of the pack goes through")
    for prompt in ("Check the team inbox and ring the session when a message is new",
                   "Remind me to review the acmeco invoice",
                   "Summarise the mytools/ folder"):
        code, out = call(hook, task(prompt))
        check(f"through: {prompt[:50]}", code == 0 and out == "", out[:200])

    print("[3] fails open")
    for stdin in ("", "not json", json.dumps({"tool_name": "CronCreate"}), json.dumps({"tool_input": None})):
        code, out = call(hook, stdin)
        check(f"through on {stdin[:30]!r}", code == 0 and out == "", out[:200])

    print("[4] the settings and the scaffold")
    s = json.loads((SKELETON / "settings.json").read_text())
    entry = [e for e in s["hooks"]["PreToolUse"] if "dev_not_runtime.py" in json.dumps(e)]
    check("one PreToolUse entry runs it", len(entry) == 1, entry)
    matcher = entry[0]["matcher"].split("|") if entry else []
    check("for the scheduling tools", {"mcp__scheduled-tasks__create_scheduled_task", "mcp__scheduled-tasks__update_scheduled_task",
                                      "CronCreate"} <= set(matcher), matcher)
    check("the scaffold maps it into .claude/hooks/",
          new_skill_pack.SKELETON_TARGETS.get("claude/hooks/dev_not_runtime.py") == ".claude/hooks/dev_not_runtime.py")
    check("filled, no placeholder is left", "{{" not in hook.read_text(encoding="utf-8"))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
