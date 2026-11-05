#!/usr/bin/env python3
"""kit/guards/asks.py: every POST form on a page a person answers says how to say no (a control marked
data-answer="no", or data-no="why" on a form that is not an ask). Each rule shown both ways: the sound page passes,
each planted break is named.

  1. the sound page: a batch confirm with its reject, a row's no tied by form=, a note with its reason, a select
     with a no option, a GET search: no problem.
  2. each planted break is a problem: a yes alone (the SEO console's confirm page, 2026-11-05), an unmarked form,
     a disabled or hidden no, an empty data-no, a no tied to another form, a no outside every form.
  3. the problem names the form, its line and its action, and says how to fix it.
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit.guards import asks  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402


def main() -> int:
    print("[1] the sound page")
    check("every form says how to say no", asks.problems(asks.SOUND) == [], asks.problems(asks.SOUND))
    check("a GET form writes nothing and is not read", asks.problems('<form action="/q"><button>Go</button></form>') == [])

    print("[2] each planted break")
    for what, html in asks.PLANTED.items():
        check(f"named: {what}", asks.problems(html) != [], html)
    check("self_test finds every planted break and passes the sound page", asks.self_test() == [], asks.self_test())

    print("[3] the problem")
    p = asks.problems('<p>x</p>\n<form method="post" action="/confirm"><button data-answer="yes">确认</button></form>',
                      "confirm page")
    check("it names the page, the form, its line and action, and the fix",
          len(p) == 1 and p[0].startswith("confirm page: form 1 (line 2, action /confirm)")
          and 'data-answer="no"' in p[0] and "data-no=" in p[0], p)
    check("an empty reason is its own problem", asks.problems('<form method="post" data-no=" "></form>')[0].endswith(
        "data-no names no reason"))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
