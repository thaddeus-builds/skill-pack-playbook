#!/usr/bin/env python3
"""kit.level_cut: the largest rise in the rate of reaching the next level whose interval excludes zero, on synthetic ladders. Every level, count and window below is invented
(no client's number is in this file).

The cases: the interval arithmetic equals the published worked examples (Wilson; Newcombe 1998, method 10) and holds at 0 and at all; a clear cut at step 2 is found with its
interval and stands alone; a flat ladder has no clear cut; tiny samples with a large jump in the point estimates have no clear cut; an evenly rising ladder names the largest
step but lists the steps it cannot be told from; a falling ladder has no cut; a level with nobody eligible has no rate and its steps carry no change, and a ladder with no two
neighbours with data says `no_data`; windows side by side agree, differ, or have no cut, and a window that lists other levels is refused; bad input is refused with a coded
message that names where; `side_of` says which side a level is on; the output is JSON, the same bytes for the same counts in either input form; over 400 simulated flat ladders
the false-cut rate is what the docstring says, with and without the Bonferroni share.
"""

import json
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import level_cut as lc, messages  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402


def ladder(rates, sizes, labels=None):
    """Levels from rates and eligible counts: reached = round(rate * eligible)."""
    labels = labels or list(range(1, len(rates) + 1))
    return [{"level": lab, "eligible": n, "reached": round(r * n)} for lab, r, n in zip(labels, rates, sizes)]


def refused(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except Exception as e:                                   # the kit's own error carries a coded message
        return messages.failure(e)
    return None


def main() -> int:
    _shop.use()

    print("[1] the arithmetic")
    p, lo, hi = lc.wilson(10, 20)
    check("Wilson 10 of 20: 0.5, 0.2993 to 0.7007 (the textbook value)", p == 0.5 and abs(lo - 0.2993) < 5e-5 and abs(hi - 0.7007) < 5e-5, (p, lo, hi))
    p, lo, hi = lc.wilson(0, 10)
    check("Wilson 0 of 10: from 0 to 0.2775, not a zero-width interval", p == 0 and lo == 0 and abs(hi - 0.2775) < 5e-5, (p, lo, hi))
    p, lo, hi = lc.wilson(12, 12)
    check("Wilson 12 of 12: up to exactly 1, and the lower edge is well under 1", p == 1 and hi == 1 and 0.7 < lo < 0.8, (p, lo, hi))
    check("no one eligible: no rate", lc.wilson(0, 0) is None and lc.change_interval((0, 0), (5, 10)) is None and lc.change_interval((5, 10), (0, 0)) is None)
    d, lo, hi = lc.change_interval((48, 80), (56, 70))
    check("Newcombe's worked example (56 of 70 against 48 of 80): +0.2000, 0.0524 to 0.3339", abs(d - 0.2) < 1e-12 and abs(lo - 0.0524) < 5e-5 and abs(hi - 0.3339) < 5e-5, (d, lo, hi))
    d2, lo2, hi2 = lc.change_interval((56, 70), (48, 80))
    check("swapped, the change is the mirror image", abs(d2 + d) < 1e-12 and abs(lo2 + hi) < 1e-12 and abs(hi2 + lo) < 1e-12)
    z1, zb = lc.z_for(), lc.z_for(lc.Params(adjust="bonferroni"), 8)
    check("z for 95 % is 1.96, and the Bonferroni z for eight comparisons is larger (2.73), but with one comparison it is the same",
          abs(z1 - 1.96) < 1e-3 and abs(zb - 2.73) < 5e-3 and lc.z_for(lc.Params(adjust="bonferroni"), 1) == z1 and lc.z_for(lc.Params(confidence=0.9)) < z1, (z1, zb))

    print("\n[2] a clear cut at step 2")
    clear = ladder([0.10, 0.12, 0.45, 0.47, 0.50], [400] * 5)
    r = lc.level_cut(clear)
    c = r["cut"]
    check("the cut is the step from level 2 to level 3: its change is +0.33, its interval is above zero, and the level it names is 3",
          r["result"] == "cut" and c and c["step"] == 1 and c["after"] == 2 and c["level"] == 3 and abs(c["change"] - 0.33) < 1e-9 and 0 < c["low"] < c["change"] < c["high"], c)
    check("it stands alone: no other rising step is a competitor", c["competing"] == [] and [s["index"] for s in r["steps"] if s["rises"]] == [1], (c, r["steps"]))
    check("every level has a rate and an interval around it, every step a change", all(x["status"] == "ok" and x["low"] <= x["rate"] <= x["high"] for x in r["levels"])
          and all(s["status"] == "ok" and s["low"] <= s["change"] <= s["high"] for s in r["steps"]) and len(r["levels"]) == 5 and len(r["steps"]) == 4)
    check("the message is coded with the registered code and its params", r["message_code"] == {"code": "level_cut_found", "params": {"level": 3, "after": 2, "change": c["change"]}}
          and "level 3" in r["message"], r["message_code"])
    check("the step's `from` and `to` are the labels, and the levels carry the counts they were given", r["steps"][1]["from"] == 2 and r["steps"][1]["to"] == 3
          and r["levels"][2]["eligible"] == 400 and r["levels"][2]["reached"] == 180)
    named = ladder([0.10, 0.12, 0.45, 0.47], [400] * 4, ["0", "1", "2", "3+"])
    check("labels may be names, and the cut names the level whose rate is the high one", lc.level_cut(named)["cut"]["level"] == "2" and lc.level_cut(named)["cut"]["after"] == "1")

    print("\n[3] no clear cut")
    flat = ladder([0.30] * 6, [200] * 6)
    r = lc.level_cut(flat)
    check("a flat ladder: no step rises, no clear cut", r["result"] == "no_clear_cut" and r["cut"] is None and not any(s["rises"] for s in r["steps"]), r["steps"])
    check("and says so in a coded message with the number of steps it looked at", r["message_code"] == {"code": "level_cut_no_clear", "params": {"steps": 5}}, r["message_code"])
    tiny = [{"level": i + 1, "eligible": 3, "reached": k} for i, k in enumerate([0, 2, 3, 3])]
    r = lc.level_cut(tiny)
    biggest = max(s["change"] for s in r["steps"])
    check("tiny samples (3 customers a level): the point estimates jump by 0.67 and there is still no clear cut, because the intervals are wide",
          biggest > 0.6 and r["result"] == "no_clear_cut" and r["cut"] is None and all(s["low"] < 0 for s in r["steps"]), [(s["change"], s["low"]) for s in r["steps"]])
    r = lc.level_cut(ladder([0.50, 0.40, 0.30, 0.20, 0.10], [500] * 5))
    check("a falling ladder: steps with a negative change are not rises, so no cut", r["result"] == "no_clear_cut" and all(s["change"] < 0 and not s["rises"] for s in r["steps"]))
    r = lc.level_cut(ladder([0.30, 0.34], [60, 60]))
    check("a small rise on small counts is inside the noise: no clear cut", r["result"] == "no_clear_cut")

    print("\n[4] a monotone ladder")
    even = ladder([0.10, 0.20, 0.30, 0.40, 0.50], [2000] * 5)
    r = lc.level_cut(even)
    check("an evenly rising ladder: all four steps rise by the same amount; the cut is the first of them (a tie goes to the lowest step)",
          r["result"] == "cut" and sum(s["rises"] for s in r["steps"]) == 4 and r["cut"]["step"] == 0 and r["cut"]["level"] == 2, r["cut"])
    check("and it is not alone: the other three steps are listed as ones the cut cannot be told from", r["cut"]["competing"] == [1, 2, 3], r["cut"])
    r = lc.level_cut(ladder([0.10, 0.20, 0.30, 0.55, 0.65], [2000] * 5))
    check("a rising ladder with one big step: the big step is the cut (level 4), and the small rises are not competitors",
          r["cut"]["level"] == 4 and r["cut"]["step"] == 2 and r["cut"]["competing"] == [], r["cut"])
    r = lc.level_cut(ladder([0.10, 0.40, 0.45, 0.50], [3000] * 4))
    check("the largest rise wins even when it is not the first: step 0 (+0.30) over steps 1 and 2 (+0.05)", r["cut"]["step"] == 0 and r["cut"]["competing"] == [], r["cut"])

    print("\n[5] a level with nobody eligible")
    r = lc.level_cut([{"level": 1, "eligible": 500, "reached": 50}, {"level": 2, "eligible": 400, "reached": 160}, {"level": 3, "eligible": 0, "reached": 0},
                      {"level": 4, "eligible": 30, "reached": 15}])
    l3 = r["levels"][2]
    check("the empty level has no rate and no interval", l3["status"] == "no_data" and l3["rate"] is None and l3["low"] is None and l3["high"] is None)
    check("the steps on both sides of it have no change; the step between the levels with data still counts",
          [s["status"] for s in r["steps"]] == ["ok", "no_data", "no_data"] and r["steps"][1]["change"] is None and r["steps"][1]["rises"] is False
          and r["cut"]["step"] == 0 and r["cut"]["level"] == 2 and r["params"]["tests"] == 1, r["steps"])
    r = lc.level_cut([{"level": 1, "eligible": 50, "reached": 10}, {"level": 2, "eligible": 0, "reached": 0}, {"level": 3, "eligible": 0, "reached": 0}])
    check("no two neighbours with data: no_data, no cut, and the message says so", r["result"] == "no_data" and r["cut"] is None and r["message_code"]["code"] == "level_cut_no_data", r)
    r = lc.level_cut([{"level": 1, "eligible": 0, "reached": 0}, {"level": 2, "eligible": 0, "reached": 0}])
    check("nobody anywhere: no_data too", r["result"] == "no_data" and all(x["rate"] is None for x in r["levels"]))
    r = lc.level_cut([{"level": 1, "eligible": 40, "reached": 0}, {"level": 2, "eligible": 40, "reached": 0}, {"level": 3, "eligible": 40, "reached": 0}])
    check("a rate of exactly zero everywhere is data, not no data: no clear cut", r["result"] == "no_clear_cut" and r["levels"][0]["rate"] == 0 and r["levels"][0]["high"] > 0)
    r = lc.level_cut([{"level": 1, "eligible": 40, "reached": 40}, {"level": 2, "eligible": 40, "reached": 40}])
    check("a rate of exactly one everywhere: no clear cut, and the interval does not pass 1", r["result"] == "no_clear_cut" and r["levels"][0]["high"] == 1.0)

    print("\n[6] several windows side by side")
    base = ladder([0.10, 0.12, 0.45, 0.47, 0.50], [400] * 5)
    w = lc.level_cuts({"90": base, "180": ladder([0.12, 0.15, 0.55, 0.58, 0.60], [300] * 5), "365": ladder([0.20, 0.22, 0.62, 0.65, 0.66], [200] * 5)})
    check("three windows that put the cut at the same level: agree, level 3, a `cut` result and the one message", w["agree"] and w["level"] == 3 and w["result"] == "cut"
          and w["cuts"] == {"90": 3, "180": 3, "365": 3} and w["message_code"] == {"code": "level_cut_found_all", "params": {"level": 3, "windows": 3}}, w["cuts"])
    check("each window carries its own full result, in the order given", list(w["windows"]) == ["90", "180", "365"] and w["windows"]["180"]["cut"]["level"] == 3
          and w["windows"]["365"]["levels"][0]["eligible"] == 200)
    w = lc.level_cuts({"90": base, "180": ladder([0.10, 0.12, 0.14, 0.50, 0.52], [400] * 5)})
    check("windows that name different levels: not agree, no level, windows_differ, and the message lists them", not w["agree"] and w["level"] is None and w["result"] == "windows_differ"
          and w["cuts"] == {"90": 3, "180": 4} and w["message_code"]["code"] == "level_cut_windows_differ"
          and w["message_code"]["params"]["cuts"] == [{"window": "90", "level": 3}, {"window": "180", "level": 4}], w["message_code"])
    w = lc.level_cuts({"90": base, "365": ladder([0.30] * 5, [100] * 5)})
    check("one window with a cut and one with none: they differ, and the one without is None", w["result"] == "windows_differ" and w["cuts"] == {"90": 3, "365": None} and not w["agree"])
    w = lc.level_cuts({"90": flat, "180": flat})
    check("no cut in any window: no_clear_cut, the steps counted over the windows", w["result"] == "no_clear_cut" and not w["agree"] and w["level"] is None
          and w["message_code"] == {"code": "level_cut_no_clear", "params": {"steps": 10}}, w["message_code"])
    empty = [{"level": i, "eligible": 0, "reached": 0} for i in range(1, 4)]
    w = lc.level_cuts({"90": empty, "180": empty})
    check("no data in any window: no_data", w["result"] == "no_data" and w["message_code"]["code"] == "level_cut_no_data")
    w = lc.level_cuts({90: base})
    check("one window is allowed, a number is a fine label (read as its text)", w["agree"] and list(w["windows"]) == ["90"] and w["level"] == 3)
    e = refused(lc.level_cuts, {"90": base, "180": ladder([0.1, 0.2, 0.3], [100] * 3)})
    check("a window that lists other levels is refused, naming it", e and e["code"] == "level_cut_bad_input" and e["params"]["where"] == "windows[180]", e)
    e = refused(lc.level_cuts, {"90": base, "180": list(reversed(base))})
    check("the same levels in another order are other levels: refused", e and e["code"] == "level_cut_bad_input", e)

    print("\n[7] bad input is refused with a coded message that names where")
    good = {"level": 1, "eligible": 10, "reached": 2}
    two = [good, {"level": 2, "eligible": 10, "reached": 5}]
    cases = [
        ("one level", [good], "levels"),
        ("no levels", [], "levels"),
        ("not a list", "abc", "levels"),
        ("a mapping instead of a list", {"level": 1}, "levels"),
        ("reached above eligible", [good, {"level": 2, "eligible": 4, "reached": 5}], "levels[1]"),
        ("a negative count", [good, {"level": 2, "eligible": -4, "reached": 0}], "levels[1]"),
        ("a fractional count", [good, {"level": 2, "eligible": 4.5, "reached": 1}], "levels[1]"),
        ("a boolean count", [good, {"level": 2, "eligible": True, "reached": 1}], "levels[1]"),
        ("a repeated level", [good, {"level": 1, "eligible": 4, "reached": 1}], "levels[1]"),
        ("a missing key", [good, {"level": 2, "eligible": 4}], "levels[1]"),
        ("an extra key", [good, {"level": 2, "eligible": 4, "reached": 1, "note": "x"}], "levels[1]"),
        ("a row of the wrong length", [good, (2, 4)], "levels[1]"),
        ("no label", [good, {"level": None, "eligible": 4, "reached": 1}], "levels[1]"),
        ("an empty label", [good, {"level": "", "eligible": 4, "reached": 1}], "levels[1]"),
    ]
    for label, levels, where in cases:
        e = refused(lc.level_cut, levels)
        check(f"refused: {label}", e and e["code"] == "level_cut_bad_input" and e["params"]["where"] == where, e)
    for label, p, where in [("confidence 1", lc.Params(confidence=1.0), "params.confidence"), ("confidence 0.3", lc.Params(confidence=0.3), "params.confidence"),
                            ("confidence a string", lc.Params(confidence="0.95"), "params.confidence"), ("an unknown adjust", lc.Params(adjust="holm"), "params.adjust")]:
        e = refused(lc.level_cut, two, p)
        check(f"refused: {label}", e and e["code"] == "level_cut_bad_input" and e["params"]["where"] == where, e)
    check("the refusal leaves nothing half-done: a good call afterwards is unaffected", lc.level_cut(two)["result"] in ("cut", "no_clear_cut"))
    check("1 and \"1\" are two different levels, not a repeat", lc.level_cut([{"level": 1, "eligible": 10, "reached": 2}, {"level": "1", "eligible": 10, "reached": 5}])["levels"][1]["level"] == "1")

    print("\n[8] which side a level is on")
    r = lc.level_cut(clear)
    check("levels 1 and 2 are below the cut, 3 and up are at or above it", [lc.side_of(r, n) for n in (1, 2, 3, 4, 5)] == ["below", "below", "at_or_above", "at_or_above", "at_or_above"])
    check("no cut, no side", lc.side_of(lc.level_cut(flat), 2) is None)
    w = lc.level_cuts({"90": clear, "180": clear})
    check("for windows that agree the side is read against the agreed level", lc.side_of(w, 2) == "below" and lc.side_of(w, 3) == "at_or_above")
    w = lc.level_cuts({"90": clear, "180": ladder([0.1, 0.12, 0.14, 0.50, 0.52], [400] * 5)})
    check("for windows that differ there is no side", lc.side_of(w, 2) is None)
    e = refused(lc.side_of, r, 99)
    check("a level that is not on the ladder is refused", e and e["code"] == "level_cut_bad_input" and e["params"]["where"] == "level", e)

    print("\n[9] the output is JSON and does not depend on the input form")
    tuples = [(x["level"], x["eligible"], x["reached"]) for x in clear]
    a, b = lc.level_cut(clear), lc.level_cut(tuples)
    check("tuples and mappings give the same result, byte for byte as JSON", json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True))
    check("the same counts give the same bytes on a second call", json.dumps(lc.level_cut(clear)) == json.dumps(lc.level_cut(clear)))
    check("it round-trips through JSON (nothing but strings, numbers, lists, dicts and None)", json.loads(json.dumps(a)) == json.loads(json.dumps(b)) and
          json.loads(json.dumps(lc.level_cuts({"90": clear}))) is not None)
    before = json.dumps(clear)
    lc.level_cut(clear)
    check("the caller's levels are not changed", json.dumps(clear) == before)
    check("no negative zero in the output", "-0.0" not in json.dumps(lc.level_cut(ladder([0.3, 0.3, 0.3], [100] * 3))))
    check("every code it emits is in the registry with those very params", all(set(messages.registry()[c]["params"]) == set(p) for c, p in [
        ("level_cut_found", {"level": 0, "after": 0, "change": 0}), ("level_cut_found_all", {"level": 0, "windows": 0}), ("level_cut_windows_differ", {"cuts": 0}),
        ("level_cut_no_clear", {"steps": 0}), ("level_cut_no_data", {"levels": 0}), ("level_cut_bad_input", {"where": 0, "problem": 0})]))

    print("\n[10] the false-cut rate on flat ladders")
    rng = random.Random(112)
    runs, falses, falses_b = 400, 0, 0
    for _ in range(runs):
        flat_run = [{"level": i + 1, "eligible": 300, "reached": sum(rng.random() < 0.3 for _ in range(300))} for i in range(8)]
        falses += lc.level_cut(flat_run)["result"] == "cut"
        falses_b += lc.level_cut(flat_run, lc.Params(adjust="bonferroni"))["result"] == "cut"
    check("eight levels of 300 customers, every true rate 0.30: a cut is wrongly named in about one run in seven (measured 15 %) without the correction", 0.04 <= falses / runs <= 0.20, falses / runs)
    check("with the Bonferroni share it is well under the 5 % the confidence promises", falses_b / runs <= 0.05 and falses_b < falses, (falses_b / runs, falses / runs))
    found, found_b = 0, 0
    for _ in range(runs):
        run = [{"level": i + 1, "eligible": 300, "reached": sum(rng.random() < (0.15 if i < 3 else 0.35) for _ in range(300))} for i in range(8)]
        c1, c2 = lc.level_cut(run)["cut"], lc.level_cut(run, lc.Params(adjust="bonferroni"))["cut"]
        found += bool(c1 and c1["level"] == 4)
        found_b += bool(c2 and c2["level"] == 4)
    check("a real jump from 0.15 to 0.35 at level 4 is found at level 4 in nearly every run, with or without the correction", found / runs >= 0.97 and found_b / runs >= 0.95, (found / runs, found_b / runs))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
