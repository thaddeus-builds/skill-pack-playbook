#!/usr/bin/env python3
"""PreToolUse hook for WebSearch and WebFetch: read what is kept before you search.

The first web call of each agent in a session (the main one, and each subagent) is refused once, with the reason shown to the model: the rows of
`docs/research/README.md` and `docs/prior-art/README.md` and the three steps of the research path. The retry goes through. Later calls cost nothing.
The cost is one refused call and the rows, once; a pack with nothing kept says so.

Why a hook and not only a line in CLAUDE.md: CLAUDE.md is context, not enforcement, and the research path was skipped twice with the rule written down
(docs/lessons.md, "Research is kept, not repeated"). The rows are state, which is what a hook is for; the static rule stays in CLAUDE.md.

Fails open: any error, a missing index or an unreadable input lets the call through. Stdlib only. Test: scaffold/tests/test_research_hook.py.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

FOLDERS = ("docs/research", "docs/prior-art")
LINK = re.compile(r"\]\(([\w.-]+\.md)(?:#[^)\s]*)?\)")
ROW_CHARS, TOTAL_CHARS = 280, 3000

STEPS = (
    "Read what is kept before you search (rows below, from {folders}). A row that answers the question is the answer: say its date and stop.\n"
    "Otherwise search, then open the pages: a search summary is a lead, not a source. Tag each claim [documented], [vendor], [academic], [ours] or "
    "[inference], and write what could not be read.\n"
    "Same turn: docs/research/YYYY-MM-DD-topic.md (first line 'Researched YYYY-MM-DD') and one row in docs/research/README.md. "
    "Across packs: python3 tools/research.py PACK... in the playbook.\n"
    "A one-fact lookup needs no file. Retry the call now: this notice comes once per agent."
)


def kept(root: Path) -> list[str]:
    """The index rows (a line that links a .md file of its folder), each cut to ROW_CHARS, all cut to TOTAL_CHARS."""
    rows: list[str] = []
    for folder in FOLDERS:
        index = root / folder / "README.md"
        if not index.is_file():
            continue
        for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
            m = LINK.search(line)
            if m and m.group(1) != "README.md":
                rows.append(f"{folder.split('/')[-1]}: " + " ".join(line.strip().strip("|").split())[:ROW_CHARS])
    out, used = [], 0
    for i, row in enumerate(rows):
        if used + len(row) > TOTAL_CHARS:
            out.append(f"... and {len(rows) - i} more rows in the indexes")
            break
        out.append(row)
        used += len(row)
    return out


def reason(root: Path) -> str:
    rows = kept(root)
    found = [f for f in FOLDERS if (root / f / "README.md").is_file()]
    body = "\n".join(rows) if rows else "Nothing is kept yet" + ("" if found else " (no docs/research/README.md: create it from the playbook's templates/research-index.md)") + "."
    return STEPS.format(folders=" and ".join(f"{f}/README.md" for f in FOLDERS)) + "\n\n" + body


def marker(data: dict) -> Path:
    key = f"{data.get('session_id', '')}-{data.get('agent_id') or 'main'}"
    return Path(tempfile.gettempdir()) / ("research-first-" + re.sub(r"[^A-Za-z0-9_.-]", "_", key))


def main() -> int:
    try:
        data = json.load(sys.stdin)
        if not data.get("session_id"):
            return 0
        mark = marker(data)
        if mark.exists():
            return 0
        mark.touch()
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason(root)}}))
    except Exception:  # noqa: BLE001 - a hook must never stop the work
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
