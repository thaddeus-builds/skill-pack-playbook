#!/usr/bin/env python3
"""kit/tools/trial_form.py: a field trial's form, complete and frozen in time.

  [1] the template has exactly the tool's fields, in order, and every one
      of them still unfilled
  [2] a filled form is complete; a value may go on over the next lines and
      a heading ends it; "not yet" is a first_publish
  [3] each way a form is incomplete is named: missing, twice, unknown, out
      of order, empty, a `<...>`, TODO or TBD left
  [4] the freeze: frozen must be a date, and a first publish before it fails
  [5] the CLI: exit 0 complete, 1 with the problems, --json one document,
      2 on a file it cannot read
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from kit.testing.check import capture, check, finish, one_doc, tmp_dir  # noqa: E402
from kit.tools import trial_form as tf  # noqa: E402

TEMPLATE = ROOT / "templates" / "evals" / "trial-form.md"


def form(**values: str) -> str:
    """A filled form, with `values` replacing the default of a field (None drops it)."""
    lines = ["# Field trial: shop, example", "", "## Fields", ""]
    for name in tf.FIELDS:
        value = values.get(name, "2026-11-02" if name in ("frozen",) else f"the {name}")
        if name == "first_publish" and name not in values:
            value = "not yet"
        if value is not None:
            lines.append(f"- **{name}**: {value}")
    lines += ["", "## Changes after freezing", "", "2026-11-20: a note, not a field."]
    return "\n".join(lines) + "\n"


def main() -> int:
    print("[1] the template")
    text = TEMPLATE.read_text(encoding="utf-8")
    fields = tf.read(text)
    check("the template has the tool's fields, in order",
          [n for n, _ in fields] == list(tf.FIELDS), [n for n, _ in fields])
    problems = tf.check(text)
    check("every field of the template is reported as not filled, and nothing else",
          problems == [f"not filled: {n} (" + tf.UNFILLED.search(v).group(0) + ")"
                       for n, v in fields], problems)

    print("[2] a filled form")
    check("complete", tf.check(form()) == [], tf.check(form()))
    joined = form(question="does the pack help\n  over two lines")
    check("a value goes on over the next line",
          dict(tf.read(joined))["question"] == "does the pack help over two lines")
    check("the change log after a heading is not part of the last field",
          dict(tf.read(form()))["first_publish"] == "not yet")
    check("a first publish on the freeze day is fine",
          tf.check(form(first_publish="2026-11-02")) == [])

    print("[3] what makes a form incomplete")
    for label, text, want in [
        ("a missing field", form(costs=None), "missing: costs"),
        ("an empty field", form(costs=""), "empty: costs"),
        ("a template value left", form(site="<the one site>"), "not filled: site (<the one site>)"),
        ("TODO left", form(referee="TODO ask li"), "not filled: referee (TODO)"),
        ("TBD left", form(read_at="weeks 4, 8, TBD"), "not filled: read_at (TBD)"),
        ("a field twice", form() + "- **site**: again\n", "twice: site"),
        ("a field the form does not have", form() + "- **mood**: good\n",
         "not a field of the form: mood"),
    ]:
        problems = tf.check(text)
        check(f"{label}: {want!r}", want in problems, problems)
    swapped = form().replace("- **question**", "- **QQ**").replace("- **decision**", "- **question**") \
                    .replace("- **QQ**", "- **decision**")
    check("two fields swapped: out of order",
          any(p.startswith("out of order") for p in tf.check(swapped)), tf.check(swapped))

    print("[4] the freeze")
    check("frozen not a date", "frozen is not a date (YYYY-MM-DD)" in tf.check(form(frozen="Monday")))
    check("frozen not a real day", "frozen is not a date (YYYY-MM-DD)" in tf.check(form(frozen="2026-02-30")))
    late = tf.check(form(frozen="2026-11-10", first_publish="2026-11-05"))
    check("a first publish before the freeze fails",
          any(p.startswith("frozen 2026-11-10 after the first publish 2026-11-05") for p in late), late)

    print("[5] the CLI")
    d = Path(tmp_dir("trial-form-"))
    good, bad = d / "good.md", d / "bad.md"
    good.write_text(form(), encoding="utf-8")
    bad.write_text(form(costs=""), encoding="utf-8")
    rc, out, _ = capture(tf.main, [str(good)])
    check("complete: exit 0, says so", rc == 0 and "complete" in out, out)
    rc, out, _ = capture(tf.main, [str(bad)])
    check("incomplete: exit 1, the problem listed", rc == 1 and "empty: costs" in out, out)
    rc, out, _ = capture(tf.main, [str(bad), "--json"])
    doc = one_doc(out)
    check("--json is one document", rc == 1 and doc and doc["complete"] is False
          and doc["problems"] == ["empty: costs"], out)
    rc, _, err = capture(tf.main, [str(d / "missing.md")])
    check("a file it cannot read: exit 2, named", rc == 2 and "missing.md" in err, err)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
