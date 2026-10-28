#!/usr/bin/env python3
"""kit.compute_life: the life document over hand-made creatives (invented DEMO ids, invented numbers). The cases are the video-ads skill pack's document test:
every row has one of the seven states, a wallet and a coded message per move; the thresholds say where each came from (a short history gives the cold
start and a coded warning, never a guess); the filters; a bad part refused. The derived thresholds are worked out by hand.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import compute_life as cl, creative_life as life, messages  # noqa: E402
from kit.registry import Thresholds  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

START = date(2026, 9, 1)


def thresholds() -> dict:
    empty = Path(tmp_dir("compute-life-")) / "constants.tsv"
    empty.write_text("\t".join(["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why"]) + "\n", encoding="utf-8")
    return Thresholds(empty).load()


def days(n, spend=10.0, imp=100, clicks=1, conv=0.0, start=START, **kw) -> list:
    return [life.Day(date=(start + timedelta(days=i)).isoformat(), spend=spend, impressions=imp, clicks=clicks, conversions=conv, **kw) for i in range(n)]


def history(n=12) -> dict:
    """n creatives that all convert on their fifth day (500 impressions by then), cost 20 a conversion over 20 days, and click i in 100."""
    out = {}
    for i in range(1, n + 1):
        ds = days(20, spend=10.0, imp=100, clicks=i)
        ds[4] = life.Day(date=ds[4].date, spend=10.0, impressions=100, clicks=i, conversions=10.0)      # 10 conversions in all: 200 spent / 10 = 20
        out[f"DEMO-{i:02d}"] = {"days": ds}
    return out


def codes(doc) -> list:
    return [w["code"] for w in doc["warning_codes"]]


def refused(src, k, **kw):
    try:
        cl.compute(src, k, **kw)
    except Exception as e:  # noqa: BLE001
        f = messages.failure(e)
        return f["code"], f["params"].get("part")
    return None, None


def main() -> int:
    _shop.use()
    k = thresholds()

    print("[1] the thresholds that are rules over the account's history")
    p, prov, w = cl.derive({c: v["days"] for c, v in history().items()}, k)
    check("12 creatives that converted after 500 impressions: reach 500, a rule (between the 300 and 2,000 bounds), from 12 creatives",
          prov["reach_impressions"] == {"value": 500, "source": "rule", "n": 12} and p.reach_impressions == 500 and p.reach_floor == 100.0, prov["reach_impressions"])
    check("every creative costs 20 a conversion: the doubt line is 2 x 20 = 40, a rule", prov["doubt_spend"] == {"value": 40.0, "source": "rule", "n": 12} and p.doubt_spend == 40.0, prov["doubt_spend"])
    check("the signals are 0.01 to 0.12; the 10th percentile of 12 is the second, 0.02", prov["weak_signal"]["source"] == "rule" and abs(p.weak_signal - 0.02) < 1e-9, prov["weak_signal"])
    check("a full history raises no warning, and the constants say they are constants", w == [] and prov["decline_days"] == {"value": 3, "source": "constant", "n": None}, (w, prov["decline_days"]))
    p, prov, w = cl.derive({c: v["days"] for c, v in list(history().items())[:3]}, k, "demo: ")
    check("three creatives: the cold starts, labelled, and a coded warning for each (never a guess)",
          prov["reach_impressions"]["source"] == "cold_start" and p.reach_impressions == 1000 and prov["doubt_spend"] == {"value": None, "source": "unknown", "n": 3}
          and p.doubt_spend == float("inf") and prov["weak_signal"]["source"] == "history_insufficient" and p.weak_signal is None
          and [c["code"] for c in messages.codes(w)] == ["life_history_insufficient", "life_doubt_unknown"], (prov, w))
    check("an incomplete day is not part of the history", cl.derive({"X": [life.Day(date="2026-09-01", impressions=9999, conversions=5.0, complete=False)]}, k)[1]["reach_impressions"]["n"] == 0)

    print("[2] the document")
    creatives = {**history(), "DEMO-NEW": {"days": days(2, imp=50), "label": "demo new", "group": "G1", "accounts": ["A1"], "entities": ["EntA"]},
                 "DEMO-WIN": {"days": days(10, spend=20.0, imp=400, clicks=8, conv=3.0), "accounts": ["A1", "A2"], "entities": ["EntA", "EntB"]}}
    d = cl.compute(cl.Source(creatives), k)
    rows = {r["creative"]: r for r in d["rows"]}
    check("every row has one of the seven states and the wallet of that state", all(r["state"] in life.STATES and r["wallet"] == life.WALLET[r["state"]] for r in d["rows"]))
    check("two days and no conversion: testing, exploration; 10 days at 3 a day (30 conversions): mature, performance, and it got there by moves",
          rows["DEMO-NEW"]["state"] == "testing" and rows["DEMO-NEW"]["wallet"] == "explore"
          and rows["DEMO-WIN"]["state"] == "mature" and rows["DEMO-WIN"]["wallet"] == "perform" and len(rows["DEMO-WIN"]["moves"]) >= 2, rows["DEMO-WIN"]["moves"])
    mv = rows["DEMO-WIN"]["moves"]
    check("a move carries its day, from, to, reason and a coded message", all({"date", "from", "to", "reason", "read", "message", "message_code"} <= set(m) and m["message_code"]["code"] == "life_move" for m in mv)
          and rows["DEMO-WIN"]["reason"] == mv[-1]["reason"], mv[:1])
    check("the last 7 counted days: 140 spent and 21 conversions for the winner; the label defaults to the id", rows["DEMO-WIN"]["spend7"] == 140.0 and rows["DEMO-WIN"]["conv7"] == 21.0
          and rows["DEMO-WIN"]["label"] == "DEMO-WIN" and rows["DEMO-NEW"]["label"] == "demo new" and rows["DEMO-NEW"]["group"] == "G1" and rows["DEMO-WIN"]["group"] is None)
    check("the summary counts the rows; the wallets are the last 7 days' spend by label",
          sum(d["summary"].values()) == len(d["rows"]) == 14 and abs(sum(d["wallets"].values()) - sum(r["spend7"] for r in d["rows"])) < 0.01
          and d["wallets"]["perform"] >= 140.0, (d["summary"], d["wallets"]))
    order = [cl.ORDER.index(r["state"]) for r in d["rows"]]
    check("rows are in the order of the states, the most spent first within one", order == sorted(order))
    check("each row says its accounts and entities, and the summary counts them by entity", rows["DEMO-WIN"]["accounts"] == ["A1", "A2"] and rows["DEMO-NEW"]["entities"] == ["EntA"]
          and set(d["by_entity"]) == {"EntA", "EntB"} and d["by_entity"]["EntB"] == {"mature": 1}, d["by_entity"])
    check("as_of is the last day read, the counts are the creatives and days handed over, the window is 7", d["as_of"] == "2026-09-20" and d["counts"] == {"creatives": 14, "days": 12 * 20 + 2 + 10}
          and d["window_days"] == 7)
    check("the document is plain data: it survives json, each warning has a code", json.dumps(d) and len(d["warnings"]) == len(d["warning_codes"]))
    cold = cl.compute(cl.Source({c: v for c, v in list(creatives.items())[-2:]}), k)
    check("a short history in the document: the cold start, said, and the codes are life_*", cold["params"]["reach_impressions"]["source"] == "cold_start"
          and cold["params"]["doubt_spend"]["source"] == "unknown" and codes(cold) == ["life_history_insufficient", "life_doubt_unknown"], codes(cold))
    check("every number of a threshold is registered, none invented", all(set(v) == {"value", "source", "n"} for v in d["params"].values()))
    none = cl.compute(cl.Source({}), k)
    check("no creative at all: no rows, no as_of, said", none["rows"] == [] and none["as_of"] is None and codes(none) == ["life_no_creatives"] and none["params"] == {}, none)
    check("the pack's own coded warnings are kept", codes(cl.compute(cl.Source({}, warnings=[messages.msg("life_doubt_unknown", "x", have=1, need=5)]), k))[0] == "life_doubt_unknown")

    ugly = {"U": {"days": [life.Day(date=(START + timedelta(days=i)).isoformat(), spend=0.123456, impressions=100, conversions=0.3333333) for i in range(7)]}}
    u = cl.compute(cl.Source(ugly), k)["rows"][0]
    check("the numbers a document feeds forward are not rounded: spend7 and conv7 are the sums of the days, not of their cents (golden comparison, 2026-10-28)",
          u["spend7"] == sum([0.123456] * 7) and u["conv7"] == sum([0.3333333] * 7), (u["spend7"], u["conv7"]))
    cents = {c: {"days": days(7, spend=0.004)} for c in "XYZ"}
    check("the wallets are rounded to the cent once, after the sum (three creatives of 7 x 0.004 = 0.028 each are 0.08, not 3 x 0.03)",
          cl.compute(cl.Source(cents), k)["wallets"]["explore"] + cl.compute(cl.Source(cents), k)["wallets"]["perform"] + cl.compute(cl.Source(cents), k)["wallets"]["other"] == 0.08, cl.compute(cl.Source(cents), k)["wallets"])

    print("[3] the filters, a person's word, a creative the platform no longer runs")
    check("--state keeps that state only", {r["state"] for r in cl.compute(cl.Source(creatives), k, state="mature")["rows"]} == {"mature"})
    check("--creative keeps one, by its id or its label", [r["creative"] for r in cl.compute(cl.Source(creatives), k, creative="DEMO-NEW")["rows"]] == ["DEMO-NEW"]
          and [r["creative"] for r in cl.compute(cl.Source(creatives), k, creative="demo new")["rows"]] == ["DEMO-NEW"])
    check("--entity and --account keep the creatives that ran there; one nobody ran in is no rows, not an error",
          [r["creative"] for r in cl.compute(cl.Source(creatives), k, entity="EntB")["rows"]] == ["DEMO-WIN"]
          and {r["creative"] for r in cl.compute(cl.Source(creatives), k, account="A1")["rows"]} == {"DEMO-NEW", "DEMO-WIN"}
          and cl.compute(cl.Source(creatives), k, entity="Nobody")["rows"] == [])
    sub = cl.compute(cl.Source(creatives), k, state="testing")
    check("the summary and the wallets follow the filter", sub["summary"] == {"testing": 1} and sub["wallets"]["perform"] == 0.0, sub["summary"])
    ov = {"DEMO-NEW": {**creatives["DEMO-NEW"], "overrides": [("2026-09-02", "parked")]}}
    o = cl.compute(cl.Source({**creatives, **ov}), k, creative="DEMO-NEW")["rows"][0]
    check("a person's dated word sets the state on its day: parked, paid by nobody, counted as other", o["state"] == "parked" and o["wallet"] is None
          and cl.compute(cl.Source({**creatives, **ov}), k, creative="DEMO-NEW")["wallets"]["other"] == o["spend7"], o)
    off = {"DEMO-NEW": {**creatives["DEMO-NEW"], "off": True}}
    padded = cl.pad_off_tail(creatives["DEMO-NEW"]["days"], True, "2026-09-06")
    check("a creative the platform no longer runs: its days after the last delivery up to `until` are blocked off, and the row says so",
          len(padded) == 6 and all(x.blocked == "off" for x in padded[2:]) and padded[2].date == "2026-09-03"
          and cl.compute(cl.Source({**creatives, **off}, until="2026-09-06"), k, creative="DEMO-NEW")["rows"][0]["blocked_now"] == "off"
          and cl.pad_off_tail(creatives["DEMO-NEW"]["days"], False, "2026-09-06") == creatives["DEMO-NEW"]["days"], padded[2:3])
    check("blocked days stop the clocks: the row's last counted day is still the last delivery",
          cl.compute(cl.Source({**creatives, **off}, until="2026-09-06"), k, creative="DEMO-NEW")["rows"][0]["last_day"] == "2026-09-02")

    print("[4] a Source the rules cannot read is refused, naming the part")
    D = life.Day
    bad = {"an until that is not a day": cl.Source(creatives, until="soon"),
           "a creative without days": cl.Source({"X": {"label": "x"}}),
           "days that are not Day": cl.Source({"X": {"days": [("2026-09-01", 1.0)]}}),
           "days not oldest first": cl.Source({"X": {"days": [D(date="2026-09-02"), D(date="2026-09-01")]}}),
           "two rows for one date": cl.Source({"X": {"days": [D(date="2026-09-01"), D(date="2026-09-01")]}}),
           "a day that is not a day": cl.Source({"X": {"days": [D(date="yesterday")]}}),
           "an override to no state": cl.Source({"X": {"days": [D(date="2026-09-01")], "overrides": [("2026-09-01", "dead")]}}),
           "an override on no day": cl.Source({"X": {"days": [D(date="2026-09-01")], "overrides": [("then", "parked")]}})}
    got = {name: refused(s, k) for name, s in bad.items()}
    check("each is compute_input_invalid", all(c == "compute_input_invalid" for c, _ in got.values()), got)
    check("and names the part", [p for _, p in got.values()] == ["until", "creatives[X]", "creatives[X].days", "creatives[X].days", "creatives[X].days", "creatives[X].days",
                                                                 "creatives[X].overrides", "creatives[X].overrides"], got)
    check("a state that is not one, asked for, is refused too", refused(cl.Source(creatives), k, state="dead") == ("compute_input_invalid", "state"))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
