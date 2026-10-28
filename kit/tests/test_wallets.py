#!/usr/bin/env python3
"""kit.wallets: the wallet of an ad group, on hand-made days. The learning stage is the ad group's: one past learning and judged spends from perform, a new batch or one with too little evidence from explore, a stopped or never-spent one from nothing.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _shop  # noqa: E402
from kit import wallets  # noqa: E402
from kit.registry import Thresholds  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

P = wallets.Params(learning_days=7, window_days=14, judge_spend=500.0, min_conversions=3.0, end_idle_days=14)
END = date(2026, 10, 15)
AS_OF = END.isoformat()


def days(n, spend=100.0, conv=5.0, back=0):
    return {(END - timedelta(days=back + i)).isoformat(): (spend, conv) for i in range(n)}


def defaults() -> wallets.Params:
    """The kit's own ad-group rows, as a skill pack with an empty constants file gets them."""
    empty = Path(tmp_dir("wallets-")) / "constants.tsv"
    empty.write_text("\t".join(["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why"]) + "\n", encoding="utf-8")
    th = Thresholds(empty)
    names = {f: f"adgroup_{f}" for f in ("learning_days", "window_days", "judge_spend", "min_conversions", "end_idle_days")}
    assert all(n in th.names() and th.origin(n) == "kit" for n in names.values()), th.names()
    v = {f: th.get(n) for f, n in names.items()}
    return wallets.Params(int(v["learning_days"]), int(v["window_days"]), v["judge_spend"], v["min_conversions"], int(v["end_idle_days"]))


def test_defaults() -> None:
    print("[2] the kit's defaults are at an ad group's scale (issue #262)")
    d = defaults()
    check("an empty constants file gives the five ad-group rows, from the kit", d.learning_days == 7 and d.window_days == 14 and d.end_idle_days == 14)
    check("a group of 20 a day for 14 days with 4 conversions is judged: performance", wallets.judge(days(14, spend=20.0, conv=4 / 14), True, AS_OF, d) == ("perform", "judged"))
    check("the same group with 1 conversion is not judged: exploration", wallets.judge(days(14, spend=20.0, conv=1 / 14), True, AS_OF, d) == ("explore", "unjudged"))
    check("a group of 50 a day with its conversions is judged too", wallets.judge(days(14, spend=50.0, conv=0.5), True, AS_OF, d)[0] == "perform")
    check("a group spending 2 a day for 14 days has too little money to judge, whatever it earned", wallets.judge(days(14, spend=2.0, conv=1.0), True, AS_OF, d) == ("explore", "unjudged"))
    check("a campaign's judging spend would have left the same group unjudged (why the ad group has its own rows)",
          wallets.judge(days(14, spend=20.0, conv=4 / 14), True, AS_OF, wallets.Params(7, 14, 3000.0, 3.0, 14))[0] == "explore")


def main() -> int:
    _shop.use()
    print("[1] the rules")
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
    test_defaults()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
