#!/usr/bin/env python3
"""kit.compute_allocate: the allocation document over two hand-made campaigns (invented DEMO ids, invented numbers). The cases are the video-ads skill pack's
document test: the params, the replay's summary, the run without acceleration, the calibrated evidence bar read from a grid, the empty wallet of young
campaigns, the proposal for tomorrow with the platform's range and the fate of recorded advice, a bad part refused. The rules themselves are test_allocation.py.
"""

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import compute_allocate as ca, messages  # noqa: E402
from kit.registry import Thresholds  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

END = date(2026, 9, 30)


def thresholds() -> dict:
    empty = Path(tmp_dir("compute-allocate-")) / "constants.tsv"
    empty.write_text("\t".join(["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why"]) + "\n", encoding="utf-8")
    return Thresholds(empty).load()


def campaign_days(c, e, phase, n=90, base=100.0, conv_div=3.0) -> dict:
    """n days of a campaign whose revenue is c x spend^e, the spend swinging +-40 % so that the response to a budget can be read."""
    out = {}
    for i in range(n):
        s = base * (1 + 0.4 * math.sin(i * 0.9 + phase))
        r = c * s ** e
        out[(END - timedelta(days=n - 1 - i)).isoformat()] = (s, r, r / conv_div, 1000, 20)
    return out


def source(**kw) -> ca.Source:
    base = dict(as_of=END.isoformat(), currency="EUR",
                campaigns={c: {"name": f"DEMO {c}", "status": "active", "budget": 100.0, "group_budget": None} for c in "AB"},
                days={"A": campaign_days(20.0, 0.9, 0.0), "B": campaign_days(60.0, 0.4, 1.3)},      # A answers to money (e 0.9), B hardly (e 0.4)
                states={"A": {"2026-08-01": "earning"}, "B": {"2026-08-01": "steady"}})
    return ca.Source(**{**base, **kw})


def codes(doc) -> list:
    return [w["code"] for w in doc["warning_codes"]]


def refused(src, k, **kw):
    try:
        ca.compute(src, k, **kw)
    except Exception as e:  # noqa: BLE001
        f = messages.failure(e)
        return f["code"], f["params"].get("part")
    return None, None


def budget_at(row, day_index) -> float:
    b = row["start"]
    for m in row["moves"]:
        if m["day"] <= day_index:
            b = m["to"]
    return b


def main() -> int:
    _shop.use()
    k = thresholds()

    print("[1] the calibrated evidence bar")
    grid = [{"evidence_z": z, "moves": m, "flip_share": f} for z, m, f in ((0.5, 3, 0.0), (0.75, 8, 0.25), (1.0, 8, 0.10), (1.25, 6, 0.0))]
    check("the lowest bar with enough moves and few enough flips: 0.5 has too few moves, 0.75 flips too much, 1.0 is at the target", ca.calibrated_z(grid, k) == 1.0)
    check("a grid where no bar qualifies gives None (the base stands)", ca.calibrated_z([{"evidence_z": 1.0, "moves": 0, "flip_share": None}, {"evidence_z": 2.0, "moves": 9, "flip_share": 0.5}], k) is None)

    print("[2] the replay")
    d = ca.compute(source(), k)
    ev = d["params"]["evidence_z"]
    check("the params are the thresholds in effect: 10 %, 20 %, 3 days, a 3-day cooldown", (d["params"]["step"], d["params"]["fast_step"], d["params"]["fast_days"], d["params"]["cooldown_days"]) == (0.10, 0.20, 3, 3), d["params"])
    check("the evidence bar is a record: the grid of seven, the base, and the value is what the rule picks from that grid",
          [g["evidence_z"] for g in ev["grid"]] == list(ca.GRID) and ev["base"] == k["allocation_evidence_z"] and ev["source"] == "calibrated"
          and ev["value"] == ca.calibrated_z(ev["grid"], k), ev)
    rows = {r["campaign"]: r for r in d["campaigns"]}
    s = d["summary"]
    check("the summary is the sum of the campaigns' own stats", s["moves"] == sum(r["stats"]["moves"] for r in rows.values()) > 0 and s["campaigns"] == 2
          and s["flips"] == sum(r["stats"]["flips"] for r in rows.values()) and s["campaigns_moved"] == 2, s)
    check("only the split moves: the money of the wallet is the same every day", all(abs(sum(budget_at(r, t) for r in rows.values()) - sum(r["start"] for r in rows.values())) < 0.1 for t in range(0, 56)))
    check("the campaign that answers to money ends above the one that does not; the money came from the second", rows["A"]["end"] > rows["A"]["start"] and rows["B"]["end"] < rows["B"]["start"], (rows["A"]["end"], rows["B"]["end"]))
    steps = [abs(m["to"] / m["from"] - 1) for r in rows.values() for m in r["moves"]]
    check("no move is larger than the step in force on that day (10 %, or 20 % after the sign held; budgets are recorded to the cent)", all(abs(m["to"] - m["from"]) <= m["cap"] * m["from"] + 0.011 and m["cap"] in (0.10, 0.20) for r in rows.values() for m in r["moves"]) and max(steps) > 0.15, max(steps))
    check("a campaign waits out its cooldown between moves (3 days)", all(b["day"] - a["day"] >= 3 for r in rows.values() for a, b in zip(r["moves"], r["moves"][1:])))
    plain = d["without_acceleration"]["summary"]
    check("the same run with the acceleration off never takes the faster step and needs more moves for the same distance", plain["fast_moves"] == 0 and plain["moves"] > s["moves"], (plain, s))
    check("it says it is a replay and that the thresholds are drafts (coded); no proposal unless asked",
          codes(d) == ["campaign_thresholds_draft", "allocate_replay_only"] and "proposal" not in d, codes(d))
    check("the document is plain data and every warning has a code", json.dumps(d) and len(d["warnings"]) == len(d["warning_codes"]))
    check("--step, --fast-step and --fast-days replace the thresholds for one run", (lambda p: (p["step"], p["fast_step"], p["fast_days"]))(ca.compute(source(), k, step=0.05, fast_step=0.1, fast_days=2)["params"]) == (0.05, 0.1, 2))
    young = ca.compute(source(states={"A": {"2026-08-01": "learning"}, "B": {"2026-08-01": "unjudged"}}), k, propose=True)
    check("campaigns that are not past learning: an empty wallet, no move, the base evidence bar stands, and the proposal has nothing to move or hold",
          young["campaigns"] == [] and young["summary"]["moves"] == 0 and young["params"]["evidence_z"]["source"] == "base"
          and young["proposal"]["moves"] == [] and young["proposal"]["held"] == [], young["params"]["evidence_z"])
    capped = ca.compute(source(), k, weekly_step_cap=0.2)["campaigns"]
    free_week = max(abs(budget_at(r, t) / budget_at(r, t - 7) - 1) for r in rows.values() for t in range(7, 56))
    cap_week = max(abs(budget_at(r, t) / budget_at(r, t - 7) - 1) for r in capped for t in range(7, 56))
    check("a weekly cap of 20 %: no campaign's budget is more than 20 % from what it was 7 days before, where without it two moves compound past it",
          free_week > 0.2 + 0.002 and cap_week <= 0.2 + 0.002, (free_week, cap_week))

    print("[3] tomorrow's proposal")
    p = ca.compute(source(), k, days=6, propose=True)["proposal"]
    mv = {m["campaign"]: m for m in p["moves"]}
    check("the day is the day after the last complete one; the better campaign up a step, the other down, from the real budgets, the faster step after the sign held",
          p["day"] == "2026-10-01" and (mv["A"]["from"], mv["A"]["to"]) == (100.0, 120.0) and (mv["B"]["from"], mv["B"]["to"]) == (100.0, 80.0)
          and mv["A"]["fast"] and mv["A"]["change"] == 0.2 and p["unallocated"] == 0.0 and p["currency"] == "EUR", p["moves"])
    m = mv["A"]
    check("each move has its marginal return with an interval around it, and says what it does not know",
          m["marginal"]["low"] < m["marginal"]["value"] < m["marginal"]["high"] and "no_counterfactual" in m["doubt"] and "no_budget_change_seen" in m["doubt"]
          and "elasticity_pooled" not in m["doubt"] and m["budget_basis"] == "campaign", m)
    check("a budget change seen in the platform's record removes that doubt", "no_budget_change_seen" not in
          {x["campaign"]: x for x in ca.compute(source(budget_history={"A": [80.0, 100.0]}), k, days=6, propose=True)["proposal"]["moves"]}["A"]["doubt"])
    check("the moves are in order of size", [abs(x["to"] - x["from"]) for x in p["moves"]] == sorted((abs(x["to"] - x["from"]) for x in p["moves"]), reverse=True))
    lim = ca.compute(source(limits={"min": None, "max": 110.0}), k, days=6, propose=True)["proposal"]
    a = {x["campaign"]: x for x in lim["moves"]}["A"]
    check("the platform's range is applied: 120 is held to 110, the binding end is named, and the money not placed is said",
          a["to"] == 110.0 and a["binding"] == "max_daily_budget" and lim["unallocated"] == 10.0 and lim["limits"] == {"min": None, "max": 110.0}, lim)
    sets = ca.compute(source(campaigns={"A": {"name": "DEMO A", "status": "active", "budget": None, "group_budget": 100.0}, "B": {"name": "DEMO B", "status": "active", "budget": 100.0, "group_budget": None}}), k, days=6, propose=True)["proposal"]
    check("a campaign with no budget of its own is read from its ad groups' and says so", {x["campaign"]: x for x in sets["moves"]}["A"]["budget_basis"] == "ad sets"
          and "budget_from_ad_sets" in {x["campaign"]: x for x in sets["moves"]}["A"]["doubt"])
    why = ca.compute(source(campaigns={"A": {"name": "DEMO A", "status": "paused", "budget": 100.0, "group_budget": None}, "B": {"name": "DEMO B", "status": "active", "budget": None, "group_budget": None}}), k, days=6, propose=True)["proposal"]
    check("a campaign that does not deliver, and one whose budget is unknown, are held with their reason, and nothing moves",
          {h["campaign"]: h["why"] for h in why["held"]} == {"A": "not_delivering", "B": "budget_unknown"} and why["moves"] == [], why["held"])
    cool = ca.compute(source(), k, days=1, propose=True)["proposal"]
    check("a campaign that just moved is held for its cooldown", {h["campaign"]: h["why"] for h in cool["held"]} == {"A": "cooldown", "B": "cooldown"}, cool["held"])
    recs = [{"day": "2026-09-20", "moves": [{"campaign": "A", "from": 100.0, "to": 110.0}, {"campaign": "B", "from": 100.0, "to": 90.0}]},
            {"day": "2026-09-29", "moves": [{"campaign": "A", "from": 100.0, "to": 110.0}]}]
    fol = ca.compute(source(records=recs, campaigns={"A": {"name": "DEMO A", "status": "active", "budget": 111.0, "group_budget": None},
                                                    "B": {"name": "DEMO B", "status": "active", "budget": 100.0, "group_budget": None}}), k, days=6, propose=True)["proposal"]["followed"]
    check("what became of the advice recorded earlier: A rose as advised (taken), B did not move (not taken), the day-old advice is still open",
          (fol["taken"], fol["not_taken"], fol["open"], fol["recorded"]) == (1, 1, 1, 3), fol)
    pw = ca.compute(source(), k, days=6, propose=True)
    check("it says it is a proposal, not an instruction (coded)", "allocate_proposal_draft" in codes(pw), codes(pw))
    check("the pack's own coded warnings are kept", codes(ca.compute(source(warnings=[messages.msg("allocate_replay_only", "x")]), k))[0] == "allocate_replay_only")

    print("[4] a Source the rules cannot read is refused, naming the part")
    good = source()
    bad = {"no complete day": source(as_of=None), "an as_of that is not a day": source(as_of="later"),
           "a campaign without its budget": source(campaigns={"A": {"name": "x", "status": None, "group_budget": None}}),
           "a day that is not 5 numbers": source(days={"A": {"2026-09-01": (1.0, 2.0)}}),
           "a day of the campaign that is not a day": source(days={"A": {"monday": (1, 2, 3, 4, 5)}}),
           "a state that is not one": source(states={"A": {"2026-09-01": "dead"}}),
           "a limit that is a word": source(limits={"max": "110"}),
           "a record without moves of the right shape": source(records=[{"day": "2026-09-01", "moves": [{"campaign": "A"}]}])}
    got = {name: refused(s, k) for name, s in bad.items()}
    check("each is compute_input_invalid", all(c == "compute_input_invalid" for c, _ in got.values()), got)
    check("and names the part", [p for _, p in got.values()] == ["as_of", "as_of", "campaigns[A]", "days[A][2026-09-01]", "days[A]", "states[A][2026-09-01]", "limits", "records[0]"], got)
    check("a number of days to replay that is not 1 or more is refused", refused(good, k, days=0) == ("compute_input_invalid", "days"))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
