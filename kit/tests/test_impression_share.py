#!/usr/bin/env python3
"""kit.impression_share: the clamped values of an impression share, from the google-ads skill pack's prior-art scan of 2026-10-22 (section 3).

  * a share under 0.1 is reported as 0.0999 and shown `<10%`; a lost share over 0.9 is reported as 0.9001 and shown `>90%`;
  * a missing share is `n/a`, never 0; ordinary values round to a whole percent;
  * a week's share is weighted by impressions, days with none are left out and counted, and a clamped day makes the result a bound;
  * no share for yesterday or today (2 days back, 3 for click share).
"""

import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import impression_share as sh  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402


def main() -> int:
    check("0.0999 is under 10%, never 9.99%", sh.show(0.0999) == "<10%")
    check("0.1 is 10%: the clamp is only the reported value under it", sh.show(0.1) == "10%")
    check("0.9001 as a lost share is over 90%", sh.show(0.9001, "lost") == ">90%")
    check("0.9001 as a share is an ordinary 90%", sh.show(0.9001) == "90%")
    check("0.0999 as a lost share is ordinary: 10%", sh.show(0.0999, "lost") == "10%")
    check("ordinary values round to a whole percent", sh.show(0.456) == "46%" and sh.show(1.0) == "100%" and sh.show(0.0, "lost") == "0%")
    check("missing is n/a, never 0", sh.show(None) == "n/a" and sh.show(None, "lost") == "n/a")
    check("is_clamped names the end", sh.is_clamped(0.0999) == "low" and sh.is_clamped(0.9001, "lost") == "high" and sh.is_clamped(0.5) is None
          and sh.is_clamped(None) is None)
    w = sh.weighted([(0.5, 100), (0.3, 300), (None, 500)])
    check("weighted by impressions, the day with none left out and counted", w == {"value": 0.35, "bound": None, "share_days": 2, "days": 3}, w)
    lo = sh.weighted([(0.0999, 100), (0.5, 100)])
    check("a clamped day makes the result a bound (under)", lo["bound"] == "<" and lo["value"] == 0.2999, lo)
    hi = sh.weighted([(0.9001, 100), (0.5, 100)], "lost")
    check("a clamped lost share makes it a bound (over)", hi["bound"] == ">", hi)
    check("no impressions or no share at all: no value", sh.weighted([(None, 10), (0.4, 0)]) == {"value": None, "bound": None, "share_days": 0, "days": 2}
          and sh.weighted([])["value"] is None)
    check("fresh: two days back, three for click share", sh.fresh(date(2026, 10, 24)) == date(2026, 10, 22) and sh.fresh(date(2026, 10, 24), True) == date(2026, 10, 21))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
