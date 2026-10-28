#!/usr/bin/env python3
"""kit.compute_review: the week of the creatives over a hand-made account (invented DEMO ids, invented numbers). The cases are the video-ads skill pack's
document test: the window is the last N complete days and `moved` holds exactly the state changes inside it, newest first; `now` counts the states as the life
document does; `early` splits the parked and ended by their reason; `scored` lists only creatives with a score, highest first; `demand` is handed through,
never a guess; a bad part refused.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import compute_life as cl, compute_review as cr, creative_life as life, messages  # noqa: E402
from kit.registry import Thresholds  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

START = date(2026, 9, 1)


def thresholds() -> dict:
    empty = Path(tmp_dir("compute-review-")) / "constants.tsv"
    empty.write_text("\t".join(["name", "default", "unit", "min", "max", "group", "label_en", "label_zh", "explain", "why"]) + "\n", encoding="utf-8")
    return Thresholds(empty).load()


def days(n, spend=20.0, imp=400, clicks=8, conv=0.0, start=START) -> list:
    return [life.Day(date=(start + timedelta(days=i)).isoformat(), spend=spend, impressions=imp, clicks=clicks, conversions=conv) for i in range(n)]


def account() -> dict:
    """Four winners (3 a day from the first day, mature on the 7th), two that spent without a conversion, one that never found its people, one that
    faded to almost nothing, one that spent and never converted, one two days old."""
    out = {f"WIN-{i}": {"days": days(30, conv=3.0), "entities": ["EntA"]} for i in range(4)}
    out.update({f"DUD-{i}": {"days": days(30, spend=5.0, imp=50, clicks=0)} for i in range(2)})
    out["LATE"] = {"days": days(30)}
    out["SILENT"] = {"days": days(30)}
    out["LOWREACH"] = {"days": days(12, spend=1.0, imp=10, clicks=0)}
    out["FADED"] = {"days": days(10, conv=3.0) + [life.Day(date=(START + timedelta(days=10 + i)).isoformat(), spend=0.5, impressions=5) for i in range(20)]}
    out["NEW"] = {"days": days(2, imp=50, start=date(2026, 9, 29))}
    return out


def src(creatives=None, **kw) -> cr.Source:
    return cr.Source(cl.Source(account() if creatives is None else creatives), **kw)


def codes(doc) -> list:
    return [w["code"] for w in doc["warning_codes"]]


def refused(s, k, **kw):
    try:
        cr.compute(s, k, **kw)
    except Exception as e:  # noqa: BLE001
        f = messages.failure(e)
        return f["code"], f["params"].get("part")
    return None, None


def main() -> int:
    _shop.use()
    k = thresholds()
    s = src()
    life_doc = cl.compute(s.life, k)
    d = cr.compute(s, k)

    print("[1] the window and the moves")
    w = d["window"]
    check("the window is the last 7 days up to the last complete day", w == {"from": "2026-09-24", "to": "2026-09-30", "days": 7} and d["as_of"] == "2026-09-30", w)
    check("every move is inside the window, newest first, each with its coded message",
          all(w["from"] <= m["date"] <= w["to"] for m in d["moved"]) and [(m["date"], m["label"]) for m in d["moved"]] == sorted(((m["date"], m["label"]) for m in d["moved"]), reverse=True)
          and all(m["message_code"]["code"] == "life_move" for m in d["moved"]), d["moved"][:2])
    every = sum(len(r["moves"]) for r in life_doc["rows"])
    wide = cr.compute(s, k, days=3650)
    check("a window wide enough holds every move the life document knows", len(wide["moved"]) == every > 0, (len(wide["moved"]), every))
    last_move = max(m["date"] for r in life_doc["rows"] for m in r["moves"])
    inside = (date.fromisoformat("2026-09-30") - date.fromisoformat(last_move)).days + 1
    check("the window edges are inclusive: the day of the last move is in at exactly the days that reach it, and out one day fewer",
          any(m["date"] == last_move for m in cr.compute(s, k, days=inside)["moved"]) and not any(m["date"] == last_move for m in cr.compute(s, k, days=inside - 1)["moved"]), (last_move, inside))
    check("--days narrows it", cr.compute(s, k, days=3)["window"]["from"] == "2026-09-28" and len(cr.compute(s, k, days=3)["moved"]) <= len(wide["moved"]))

    print("[2] the states now, and what the ones that did not work say")
    check("now counts the states as the life document does, and by entity", d["now"]["states"] == life_doc["summary"] and d["now"]["entities"] == {"EntA": {"mature": 4}}, d["now"])
    check("early splits the parked and the ended by the reason they carry: four shown and nobody bought, one never shown, one faded",
          d["early"]["parked"] == {"no_conversion": 4, "low_reach": 1} and d["early"]["ended"] == {"faded": 1} and d["early"]["doubt"] == 0 and d["early"]["waiting"] == 5, d["early"])

    print("[3] the scores")
    check("four winners that are each other's benchmark: efficiency 0.5 x impact 0.5, the square root is 0.5; the faded one earned nothing lately: 0",
          [(x["creative"], x["fission"]) for x in d["scored"]] == [("WIN-0", 0.5), ("WIN-1", 0.5), ("WIN-2", 0.5), ("WIN-3", 0.5), ("FADED", 0.0)], d["scored"])
    check("the highest first, ties by label; each carries its state and reason", [x["fission"] for x in d["scored"]] == sorted((x["fission"] for x in d["scored"]), reverse=True)
          and d["scored"][0]["state"] == "mature" and d["scored"][0]["reason"] == "learned" and d["scored"][-1]["reason"] == "faded")
    check("the creatives with no verdict are counted by state, never scored 0", d["unscored"] == {"testing": 1, "parked": 5} and not any(x["state"] in ("parked", "testing") for x in d["scored"]), d["unscored"])
    two = cr.compute(src({f"WIN-{i}": {"days": days(30, conv=3.0)} for i in range(2)}), k)
    check("under three proven creatives there is no benchmark: nobody is scored, and they are counted as unscored", two["scored"] == [] and two["unscored"] == {"mature": 2}, two)

    print("[4] the demand, no creative, a Source the rules cannot read")
    check("without a demand block there is none, never a guess; with one it is handed through untouched", d["demand"] is None and cr.compute(src(demand={"n": 10, "batches": 2}), k)["demand"] == {"n": 10, "batches": 2})
    none = cr.compute(src({}), k)
    check("no creative: no window, nothing moved, said once", none["window"] is None and none["as_of"] is None and none["moved"] == [] and none["scored"] == [] and codes(none).count("life_no_creatives") == 1, codes(none))
    incomplete = cr.compute(src({"X": {"days": [life.Day(date="2026-09-01", spend=1.0, complete=False)]}}), k)
    check("creatives but no complete day: no window, and it says there is nothing to read, once", incomplete["window"] is None and codes(incomplete).count("life_no_creatives") == 1, codes(incomplete))
    check("the life document's warnings are kept (a short history deriving the thresholds)", "life_history_insufficient" in codes(d), codes(d))
    check("the document is plain data and every warning has a code", json.dumps(d) and len(d["warnings"]) == len(d["warning_codes"]))
    bad = {"a number of days under 1": ("days", dict(s=src(), kw={"days": 0})), "a demand that is not a block": ("demand", dict(s=src(demand=[1]), kw={})),
           "a creative without days": ("creatives[X]", dict(s=src({"X": {"label": "x"}}), kw={}))}
    got = {name: refused(v["s"], k, **v["kw"]) for name, (_, v) in bad.items()}
    check("each is compute_input_invalid, naming its part", all(c == "compute_input_invalid" for c, _ in got.values()) and [p for _, p in got.values()] == [x for x, _ in bad.values()], got)
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
