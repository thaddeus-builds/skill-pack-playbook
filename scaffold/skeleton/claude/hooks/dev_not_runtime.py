#!/usr/bin/env python3
"""PreToolUse hook for the scheduling tools: development is not runtime (the playbook's R44).

This checkout is the development machine. It runs the skill pack's steps by hand, while debugging. A recurring step is a verb of the skill pack;
its cadence is declared in the pack (the host adapter's task list) and the runtime, the client's agent, schedules it. So a scheduled task or
cron job created here whose prompt runs this skill pack ({{cli}}, {{name}}, or a script under tools/) is refused, with that reason shown to the model.
A task that runs nothing of the pack (a reminder, a watcher of the team's own inbox) goes through.

Why a hook: seen once, 2026-11-05, a session created a daily task on the development machine that ran a pack's tools/ script against a client's
folder; the owner had it removed the same day ("我们这里只是开发环境 并非 runtime 生产环境"). A line in CLAUDE.md did not stop it.

Fails open: any error or unreadable input lets the call through. Stdlib only. Test: scaffold/tests/test_dev_runtime_hook.py.
"""

from __future__ import annotations

import json
import re
import sys

CLI, NAME = "{{cli}}", "{{name}}"
RUNS_PACK = re.compile(rf"(?<![\w.-])(?:{re.escape(CLI)}|{re.escape(NAME)})(?![\w-])|(?<![\w.-])tools/")
REASON = ("Development is not runtime (R44): this machine runs {cli}'s steps by hand only. A recurring step is a verb of the skill pack; "
          "declare its cadence in the pack (the host adapter's task list) and let the runtime, the client's agent, schedule it. "
          "To debug, run the verb by hand now. The prompt named: {hit}.")


def strings(value) -> list[str]:
    """Every string inside the tool input (prompts may sit in any field)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def main() -> int:
    try:
        data = json.load(sys.stdin)
        hit = next((m.group(0) for s in strings(data.get("tool_input") or {}) for m in [RUNS_PACK.search(s)] if m), None)
        if hit:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": REASON.format(cli=CLI, hit=hit)}}))
    except Exception:  # noqa: BLE001 - a hook must never stop the work
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
