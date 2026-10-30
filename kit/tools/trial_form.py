#!/usr/bin/env python3
"""A field trial's form: every field filled, frozen before the first publish.

    python3 kit/tools/trial_form.py FORM.md [--json]

A field trial runs an agent with the skill pack against the same agent
without it, on real work, for weeks (templates/evals/field-trial.md). What
it measures, when, and what counts as the same result is written down
before the work starts, in a form (templates/evals/trial-form.md), so the
reading cannot be chosen after the numbers are in. This tool reads a
filled form and says whether it is complete:

- every field of FIELDS is present, once, in order;
- every field has a value: not empty, no `<...>` left from the template,
  no `TODO` or `TBD`;
- `frozen` is a date (YYYY-MM-DD), and `first_publish`, once it is a date,
  is not before it.

A field is one line `- **name**: value`. A value may go on over the lines
below it, until the next field or heading. Text outside fields (headings,
notes, the change log at the end) is not read.

Exit 0 when complete, 1 with the problems listed, 2 on usage.
Stdlib only; runs without a bound skill pack.

Test: kit/tests/test_trial_form.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

FIELDS = (
    "question", "decision", "test_arm", "control_arm", "difference",
    "held_equal", "coaching", "site", "task", "split", "items_per_arm",
    "window", "primary_outcome", "read_at", "guardrails", "same_result",
    "costs", "spend_caps", "judging", "stop_rules", "referee", "frozen",
    "frozen_by", "first_publish",
)
FIELD = re.compile(r"^- \*\*(\w+)\*\*:[ \t]*(.*)$")
BREAK = re.compile(r"^(?:- \*\*\w+\*\*:|#)")
UNFILLED = re.compile(r"<[^>\n]*>|\bTODO\b|\bTBD\b")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read(text: str) -> list[tuple[str, str]]:
    """The fields of a form, in order, each with its value joined over its lines."""
    out: list[tuple[str, str]] = []
    open_field = False
    for line in text.splitlines():
        m = FIELD.match(line)
        if m:
            out.append((m.group(1), m.group(2).strip()))
            open_field = True
        elif BREAK.match(line):
            open_field = False
        elif open_field and line.strip():
            name, value = out[-1]
            out[-1] = (name, f"{value} {line.strip()}".strip())
    return out


def day(value: str) -> date | None:
    if not DAY.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def check(text: str) -> list[str]:
    """The problems of a filled form; empty when it is complete."""
    fields = read(text)
    names = [n for n, _ in fields]
    problems = [f"missing: {n}" for n in FIELDS if n not in names]
    problems += [f"twice: {n}" for n in dict.fromkeys(names) if names.count(n) > 1]
    problems += [f"not a field of the form: {n}" for n in dict.fromkeys(names) if n not in FIELDS]
    known = [n for n in names if n in FIELDS]
    if not problems and known != list(FIELDS):
        problems.append("out of order: the fields follow templates/evals/trial-form.md")
    values = dict(fields)
    for name in FIELDS:
        value = values.get(name)
        if value is None:
            continue
        if not value:
            problems.append(f"empty: {name}")
        elif UNFILLED.search(value):
            problems.append(f"not filled: {name} ({UNFILLED.search(value).group(0)})")
    frozen = day(values.get("frozen", ""))
    if values.get("frozen") and frozen is None and not UNFILLED.search(values["frozen"]):
        problems.append("frozen is not a date (YYYY-MM-DD)")
    published = day(values.get("first_publish", ""))
    if frozen and published and published < frozen:
        problems.append(f"frozen {frozen} after the first publish {published}: "
                        "the reading was chosen with results in sight")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trial_form.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("form", type=Path)
    ap.add_argument("--json", action="store_true", help="one JSON document on stdout")
    args = ap.parse_args(argv)
    try:
        text = args.form.read_text(encoding="utf-8")
    except OSError as e:
        ap.error(f"cannot read {args.form}: {e.strerror}")
    problems = check(text)
    if args.json:
        print(json.dumps({"form": str(args.form), "complete": not problems,
                          "problems": problems}, ensure_ascii=False, indent=1))
    else:
        print("\n".join(problems) if problems else f"{args.form}: complete")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
