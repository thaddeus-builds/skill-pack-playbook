#!/usr/bin/env python3
"""kit.proof: proven and unproven, on planted days. The paid-search skill pack's cases (its certainty rule) and the wallet rule the
video-ads skill pack applies to a creative.

  * proves(): orders and order days, no click minimum, never on the brand's own search;
  * loss_verdict(): lost / kept / undetermined, with the hysteresis (an order, or too few clicks, keeps the status);
  * move(): an explore target that proves goes up, a perform target that is lost goes back, nothing else moves;
  * a bad day table is not read as proof: order days count distinct days.
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import proof  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

K = {"min_orders": 1, "min_order_days": 1, "click_min": 20}
D = proof.Day


def main() -> int:
    print("[1] tally")
    t = proof.tally([D("2026-09-01", 10, 5.0, 1, 20.0), D("2026-09-01", 4, 2.0, 1, 10.0), D("2026-09-03", 6, 3.0, 0, 0.0)])
    check("sums, and order days are distinct days with an order", t == {"clicks": 20, "orders": 2, "order_days": 1, "spend": 10.0, "sales": 30.0}, t)
    check("no rows: all zero", proof.tally([]) == {"clicks": 0, "orders": 0, "order_days": 0, "spend": 0, "sales": 0})

    print("[2] proves")
    check("one order is a proof at the defaults, with no click minimum", proof.proves(proof.tally([D("2026-09-01", 1, 0.5, 1, 9.0)]), 1, 1))
    check("no order: not proved", not proof.proves(proof.tally([D("2026-09-01", 99, 50.0, 0, 0.0)]), 1, 1))
    two_one_day = proof.tally([D("2026-09-01", 5, 2.0, 2, 30.0)])
    check("two orders on one day do not prove when two days are asked", not proof.proves(two_one_day, 2, 2))
    two_days = proof.tally([D("2026-09-01", 5, 2.0, 1, 30.0), D("2026-09-04", 5, 2.0, 1, 30.0)])
    check("two orders on two days do", proof.proves(two_days, 2, 2))
    check("never on the brand's own search, however many orders", not proof.proves(two_days, 1, 1, own_brand=True))

    print("[3] loss_verdict")
    zero = proof.tally([D("2026-09-01", 20, 9.0, 0, 0.0)])
    check("20 clicks and no order, the days all there: lost", proof.loss_verdict(zero, True, 20) == proof.LOST)
    check("19 clicks and no order: kept (still learning)", proof.loss_verdict(proof.tally([D("2026-09-01", 19)]), True, 20) == proof.KEPT)
    check("an order keeps it whatever the clicks", proof.loss_verdict(proof.tally([D("2026-09-01", 500, 100.0, 1, 5.0)]), True, 20) == proof.KEPT)
    check("no order and the daily table misses days: undetermined, never lost", proof.loss_verdict(zero, False, 20) == proof.UNDETERMINED)
    check("an order beats missing days", proof.loss_verdict(proof.tally([D("2026-09-01", 1, 1.0, 1, 5.0)]), False, 20) == proof.KEPT)

    print("[4] move")
    up = proof.tally([D("2026-09-01", 3, 1.0, 1, 12.0)])
    check("explore + proved: to perform", proof.move(proof.EXPLORE, up, proof.tally([]), True, K) == "to_perform")
    check("explore + not proved: stays", proof.move(proof.EXPLORE, zero, zero, True, K) is None)
    check("explore + proved on the brand's own search: stays", proof.move(proof.EXPLORE, up, proof.tally([]), True, K, own_brand=True) is None)
    check("perform + lost: back to explore", proof.move(proof.PERFORM, up, zero, True, K) == "to_explore")
    check("perform + kept: stays", proof.move(proof.PERFORM, up, proof.tally([D("2026-09-01", 5)]), True, K) is None)
    check("perform + undetermined: stays (no verdict without the days)", proof.move(proof.PERFORM, up, zero, False, K) is None)
    check("a perform target never moves up, an explore target never moves down",
          proof.move(proof.PERFORM, up, proof.tally([]), True, K) is None and proof.move(proof.EXPLORE, up, zero, True, K) == "to_perform")

    print("[5] the wallet of a verdict")
    check("proven pays from perform, unproven from explore", proof.wallet(True) == "perform" and proof.wallet(False) == "explore")
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
