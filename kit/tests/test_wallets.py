#!/usr/bin/env python3
"""kit.wallets: the wallet of an ad group, on hand-made days. The learning stage is the ad group's: one past learning and judged spends from perform, a new batch or one with too little evidence from explore, a stopped or never-spent one from nothing.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from kit import wallets  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

P = wallets.Params(learning_days=7, window_days=14, judge_spend=500.0, min_conversions=3.0, end_idle_days=14)
END = date(2026, 10, 15)
AS_OF = END.isoformat()


def days(n, spend=100.0, conv=5.0, back=0):
    return {(END - timedelta(days=back + i)).isoformat(): (spend, conv) for i in range(n)}


def main() -> int:
    check("never spent and still active: exploration, waiting for its first spend", wallets.judge({}, True, AS_OF, P) == ("explore", "no_spend_yet"))
    check("never spent and stopped: nothing", wallets.judge({}, False, AS_OF, P) == ("none", "never_ran"))
    check("a new batch, three days old: exploration (learning), whatever it earned", wallets.judge(days(3, conv=50.0), True, AS_OF, P) == ("explore", "learning"))
    check("past the learning days with the judging spend and conversions: performance", wallets.judge(days(20), True, AS_OF, P) == ("perform", "judged"))
    check("past the learning days with too little spend in the window: exploration (unjudged), R74", wallets.judge(days(20, spend=10.0), True, AS_OF, P) == ("explore", "unjudged"))
    check("past the learning days with spend but no conversion: exploration (unjudged)", wallets.judge(days(20, conv=0.0), True, AS_OF, P) == ("explore", "unjudged"))
    check("stopped and idle for 20 days: nothing", wallets.judge(days(30, back=20), False, AS_OF, P) == ("none", "stopped_idle"))
    check("stopped three days ago is judged on its days: still performance", wallets.judge(days(30, back=3), False, AS_OF, P)[0] == "perform")
    check("the window is the last 14 days: old money does not make a group judged", wallets.judge({**days(5, spend=1.0), **days(20, back=30, spend=100.0)}, True, AS_OF, P)[0] == "explore")
    check("exactly the learning days counts as past learning (7 days from the first spend)", wallets.judge(days(7), True, AS_OF, P)[0] == "perform" and wallets.judge(days(6), True, AS_OF, P)[0] == "explore")
    check("a judged group holds nothing back: the creative's own wallet pays", wallets.pay("perform", "perform") == "perform" and wallets.pay("explore", "perform") == "explore")
    check("a new creative in an old, judged ad group is still exploration (it has no verdict of its own)", wallets.pay("explore", "perform") == "explore")
    check("a group still learning or unjudged pays its mature creative from exploration", wallets.pay("perform", "explore") == "explore")
    check("a stopped group pays nobody; a parked or ended creative is paid by nobody", wallets.pay("explore", "none") is None and wallets.pay(None, "perform") is None and wallets.pay(None, "explore") is None)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
