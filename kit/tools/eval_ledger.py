#!/usr/bin/env python3
"""Where an eval agent's turns and tool output went: learning the skill pack, or using it.

    python3 kit/tools/eval_ledger.py TRANSCRIPT.jsonl... --cli NAME [--cli NAME]
                                     [--pack PATH_PART]... [--json]

An eval run leaves a transcript, one JSON object per line (the format of
Claude Code's session files and of `claude -p --output-format stream-json`:
`type` is `assistant` or `user`, `message.content` holds `tool_use` and
`tool_result` blocks, `message.usage` the tokens). This tool sorts every
tool call into one kind and adds up, per kind, the calls and the bytes the
tool handed back to the model:

  help     the skill pack's own verb with `--help` or `-h`
  verb     the skill pack's own verb, run
  docs     a read of the skill pack's prose: SKILL.md, or a `.md` file under
           a `--pack` path
  source   a read of any other file under a `--pack` path: its code, its
           registries
  explore  `ls`, `find`, `tree`, `pwd`, `stat`, and the Glob and Grep tools
  other    the rest: the agent's own scripts, its edits, its messages, a read
           of the client's files

`learning` is help + docs + source: what the agent spent finding out how
the skill pack works before and while using it. A share of tool output
that stays high after SKILL.md or the help changed says the text still
does not answer what the agent needed; `first_verb_call` (the number of
calls before the first verb ran) is the same question asked of the start.

A Bash command is split at `;`, `&&`, `||`, `|` and newlines. It is a `verb`
when one of its parts runs the skill pack's entry without `--help`/`-h`,
`help` when every part that names the entry asks for help, a read when it
starts with a reader (cat, head, tail, sed, less, more, grep, rg, awk, nl,
wc) and names a file under a `--pack` path or a SKILL.md, `explore` when it
starts with a listing command, else `other`. A Read tool call is a read of
its `file_path`. `--cli` is the entry's name as the agent types it
(`./bin/shop`, `shop`, `shop.py`: any leading path, an optional `.py`).
`--pack` is a part of a path that marks the skill pack's own folder
(`skill_pack/`, `.claude/skills/<name>/`); a relative path the agent reads
after a `cd` into the skill pack is only seen if a `--pack` names its first
folder (`scripts/`). The command is read as text: an entry behind a
variable (`$S plan add`) or inside a script the agent wrote is `other`.

Tokens are summed once per model call. A session file writes one line per
content block, each carrying the whole call's usage, so summing lines
counts a call two or three times (seen once, in an eval of 30 runs: the
reported totals were 1.8 to 2.6 times the real ones, and the factor
differed by model). Calls are told apart by `message.id`; a line without
one counts as its own call.

The tool reads only the files it is given and writes nothing. A line that
is not a JSON object is skipped and counted (`unreadable_lines`). Exit 0
with the ledger, 2 on usage.

Stdlib only; runs without a bound skill pack.

Test: kit/tests/test_eval_ledger.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KINDS = ("help", "verb", "docs", "source", "explore", "other")
LEARNING = ("help", "docs", "source")
TOKENS = ("input_tokens", "cache_read_input_tokens",
          "cache_creation_input_tokens", "output_tokens")
READERS = {"cat", "head", "tail", "sed", "less", "more", "grep", "rg",
           "awk", "nl", "wc"}
LISTERS = {"ls", "find", "tree", "pwd", "stat"}
SPLIT = re.compile(r"\|\||&&|[;|\n]")
HELP = re.compile(r"(?:^|\s)(?:--help|-h)(?=\s|$)")
ASSIGN = re.compile(r"^(?:\w+=\S*\s*)+")


def entry_pattern(clis: list[str]) -> re.Pattern:
    """A command part that runs one of the entries: any leading path, an optional `.py`."""
    names = "|".join(re.escape(c.rsplit("/", 1)[-1].removesuffix(".py")) for c in clis)
    return re.compile(r"(?:^|[\s(`/])(?:%s)(?:\.py)?(?=\s|$)" % names)


def read_kind(path: str, packs: list[str]) -> str:
    """docs, source or other for a file the agent read."""
    if path.rsplit("/", 1)[-1] == "SKILL.md":
        return "docs"
    if any(p in path for p in packs):
        return "docs" if path.endswith(".md") else "source"
    return "other"


def bash_kind(command: str, entry: re.Pattern, packs: list[str]) -> str:
    # a part's leading `NAME=value` words set variables; what follows them is the command
    parts = [ASSIGN.sub("", p.strip()) for p in SPLIT.split(command)]
    parts = [p for p in parts if p]
    named = [p for p in parts if entry.search(p)]
    if named:
        return "help" if all(HELP.search(p) for p in named) else "verb"
    for part in parts:
        words = part.split()
        program = words[0].rsplit("/", 1)[-1]
        if program in ("cd", "export"):
            continue
        if program in READERS:
            kinds = {read_kind(w, packs) for w in words[1:]} - {"other"}
            if kinds:
                return "docs" if kinds == {"docs"} else "source"
        if program in LISTERS:
            return "explore"
        break
    return "other"


def classify(name: str, tool_input: dict, entry: re.Pattern, packs: list[str]) -> str:
    """The kind of one tool call."""
    if name == "Bash":
        return bash_kind(str(tool_input.get("command", "")), entry, packs)
    if name == "Read":
        return read_kind(str(tool_input.get("file_path", "")), packs)
    if name in ("Glob", "Grep", "LS"):
        return "explore"
    return "other"


def result_bytes(content) -> int:
    """The bytes a tool_result handed back: its text, or its blocks' text."""
    if isinstance(content, str):
        return len(content.encode("utf-8"))
    if isinstance(content, list):
        return sum(result_bytes(b.get("text", "")) if isinstance(b, dict) else 0
                   for b in content)
    return 0


def ledger(lines, clis: list[str], packs: list[str]) -> dict:
    """The ledger of one transcript, from its lines."""
    entry = entry_pattern(clis)
    kinds = {k: {"calls": 0, "result_bytes": 0} for k in KINDS}
    by_id: dict[str, str] = {}
    usage: dict[str, dict] = {}
    unreadable = calls = 0
    first_verb = None
    for n, line in enumerate(lines):
        try:
            row = json.loads(line)
        except ValueError:
            row = None
        if not isinstance(row, dict):
            unreadable += line.strip() != ""
            continue
        msg = row.get("message") if isinstance(row.get("message"), dict) else {}
        blocks = msg.get("content") if isinstance(msg.get("content"), list) else []
        if row.get("type") == "assistant":
            if isinstance(msg.get("usage"), dict):
                usage[str(msg.get("id") or f"line-{n}")] = msg["usage"]
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    kind = classify(str(b.get("name", "")), b.get("input") or {}, entry, packs)
                    by_id[str(b.get("id"))] = kind
                    kinds[kind]["calls"] += 1
                    calls += 1
                    if kind == "verb" and first_verb is None:
                        first_verb = calls
        elif row.get("type") == "user":
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    kind = by_id.get(str(b.get("tool_use_id")), "other")
                    kinds[kind]["result_bytes"] += result_bytes(b.get("content"))
    return summary(kinds, calls, len(usage), first_verb, unreadable,
                   {t: sum(int(u.get(t) or 0) for u in usage.values()) for t in TOKENS})


def summary(kinds: dict, calls: int, model_calls: int, first_verb, unreadable: int,
            tokens: dict) -> dict:
    total = sum(k["result_bytes"] for k in kinds.values())
    learned = sum(kinds[k]["result_bytes"] for k in LEARNING)
    return {"model_calls": model_calls, "tool_calls": calls,
            "first_verb_call": first_verb, "tokens": tokens, "kinds": kinds,
            "result_bytes": total,
            "learning_calls": sum(kinds[k]["calls"] for k in LEARNING),
            "learning_share": round(learned / total, 3) if total else None,
            "unreadable_lines": unreadable}


def combine(runs: list[dict]) -> dict:
    """The ledger of several transcripts together (first_verb_call: the median)."""
    kinds = {k: {f: sum(r["kinds"][k][f] for r in runs) for f in ("calls", "result_bytes")}
             for k in KINDS}
    firsts = sorted(r["first_verb_call"] for r in runs if r["first_verb_call"] is not None)
    median = firsts[len(firsts) // 2] if firsts else None
    return summary(kinds, sum(r["tool_calls"] for r in runs),
                   sum(r["model_calls"] for r in runs), median,
                   sum(r["unreadable_lines"] for r in runs),
                   {t: sum(r["tokens"][t] for r in runs) for t in TOKENS})


def text(runs: list[tuple[str, dict]], total: dict) -> str:
    out = []
    for path, r in runs:
        share = "-" if r["learning_share"] is None else f"{r['learning_share']:.0%}"
        out.append(f"{path}: {r['model_calls']} model calls, {r['tool_calls']} tool calls, "
                   f"learning {share} of tool output, first verb at call {r['first_verb_call']}")
    out.append(f"\n{'kind':8} {'calls':>6} {'KB':>8} {'share':>6}")
    for k in KINDS:
        v = total["kinds"][k]
        share = v["result_bytes"] / total["result_bytes"] if total["result_bytes"] else 0
        out.append(f"{k:8} {v['calls']:6} {v['result_bytes'] / 1024:8.0f} {share:6.0%}")
    t = total["tokens"]
    out.append(f"\ntokens, once per model call: input {t['input_tokens']}, cache read "
               f"{t['cache_read_input_tokens']}, cache write {t['cache_creation_input_tokens']}, "
               f"output {t['output_tokens']}")
    if total["unreadable_lines"]:
        out.append(f"skipped {total['unreadable_lines']} line(s) that were not a JSON object")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eval_ledger.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("transcripts", nargs="+", type=Path)
    ap.add_argument("--cli", action="append", required=True,
                    help="the skill pack's entry as the agent types it; repeat for each name")
    ap.add_argument("--pack", action="append", default=[],
                    help="a part of a path that marks the skill pack's folder; repeatable")
    ap.add_argument("--json", action="store_true", help="one JSON document on stdout")
    args = ap.parse_args(argv)
    runs = []
    for path in args.transcripts:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            ap.error(f"cannot read {path}: {e.strerror}")
        runs.append((str(path), ledger(lines, args.cli, args.pack)))
    total = combine([r for _, r in runs])
    if args.json:
        print(json.dumps({"transcripts": [{"path": p, **r} for p, r in runs],
                          "total": total}, ensure_ascii=False, indent=1))
    else:
        print(text(runs, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
