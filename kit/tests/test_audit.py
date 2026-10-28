#!/usr/bin/env python3
"""kit.audit: each finding appears only when its facts cross the threshold, carries its numbers as params, and the most severe comes first. The module
holds no sentence and no platform word: the pack's wording and its own findings join the list through `order()`. The facts are hand-made and every
number is synthetic."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import audit  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

K = {"audit_old_days": 90, "audit_old_share": 0.20, "audit_waste_share": 0.05, "audit_budget_use_low": 0.70,
     "audit_budget_use_high": 1.20, "concentration_alert_share": 0.80}


def facts(**over):
    f = {"issues": {"ads": 0, "spend": 0.0, "days": 14, "examples": []},
         "waste": {"ads": 0, "spend": 0.0, "share": 0.0, "examples": []},
         "old": {"ads": 0, "spend": 0.0, "share": 0.0, "examples": []},
         "concentration": {"n": 3, "share": 0.5, "examples": []},
         "budget": {"daily": 100.0, "spend_per_day": 90.0, "use": 0.9, "campaigns": 2}}
    f.update(over)
    return f


def main() -> int:
    check("nothing crosses a threshold: no finding", audit.findings(facts(), K) == [])
    got = audit.findings(facts(issues={"ads": 2, "spend": 50.123, "days": 14, "examples": [{"ad_id": "1"}]}), K)
    check("ads with issues: one high finding, its code and its numbers as params, no sentence",
          len(got) == 1 and got[0] == {"finding": "audit_issues", "severity": "high",
                                       "params": {"ads": 2, "spend": 50.12, "days": 14, "examples": [{"ad_id": "1"}]}}, got)
    at = audit.findings(facts(waste={"ads": 3, "spend": 50.0, "share": 0.05, "examples": []}), K)
    under = audit.findings(facts(waste={"ads": 3, "spend": 40.0, "share": 0.049, "examples": []}), K)
    check("a share at the threshold is a finding, a hair under it is not", [x["finding"] for x in at] == ["audit_no_result"] and under == [])
    old = audit.findings(facts(old={"ads": 4, "spend": 300.0, "share": 0.3, "examples": []}), K)
    check("old ads carry the number of days the threshold names", old[0]["finding"] == "audit_old_ads" and old[0]["params"]["days"] == 90, old)
    every = audit.findings(facts(issues={"ads": 1, "spend": 5.0, "days": 14, "examples": []},
                                 waste={"ads": 1, "spend": 100.0, "share": 0.1, "examples": []},
                                 old={"ads": 4, "spend": 300.0, "share": 0.3, "examples": []},
                                 concentration={"n": 3, "share": 0.9, "examples": []},
                                 budget={"daily": 100.0, "spend_per_day": 50.0, "use": 0.5, "campaigns": 2}), K)
    check("all together: five findings (the budget one is the unused kind), the high one first",
          every[0]["finding"] == "audit_issues" and {x["finding"] for x in every} == {
              "audit_issues", "audit_no_result", "audit_old_ads", "audit_concentration", "audit_budget_unused"}, [x["finding"] for x in every])
    over = audit.findings(facts(budget={"daily": 100.0, "spend_per_day": 130.0, "use": 1.3, "campaigns": 2}), K)
    check("spending past the budget is its own finding", [x["finding"] for x in over] == ["audit_budget_over"], over)
    edge = audit.findings(facts(budget={"daily": 100.0, "spend_per_day": 70.0, "use": 0.70, "campaigns": 2}), K) + \
        audit.findings(facts(budget={"daily": 100.0, "spend_per_day": 120.0, "use": 1.20, "campaigns": 2}), K)
    check("a budget use exactly at either threshold is not a finding", edge == [], edge)
    nobudget = audit.findings(facts(budget={"daily": 0.0, "spend_per_day": 0.0, "use": None, "campaigns": 0}), K)
    check("no budget named: nothing is said about it", nobudget == [], nobudget)
    check("no spend at all: shares are None and nothing is said",
          audit.findings(facts(waste={"ads": 0, "spend": 0.0, "share": None, "examples": []},
                               old={"ads": 0, "spend": 0.0, "share": None, "examples": []},
                               concentration={"n": 3, "share": None, "examples": []}), K) == [])
    check("a part the pack did not gather is left out, not an error", audit.findings({"waste": facts()["waste"]}, K) == [])
    mine = {"finding": "audit_pack_only", "severity": "high", "params": {}}
    mixed = audit.order([*audit.findings(facts(waste={"ads": 1, "spend": 9.0, "share": 0.1, "examples": []}), K), mine,
                         {"finding": "audit_odd", "severity": "bogus", "params": {}}])
    check("a pack's own finding joins the list through order(): by severity, an unknown severity last",
          [x["finding"] for x in mixed] == ["audit_pack_only", "audit_no_result", "audit_odd"], mixed)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
