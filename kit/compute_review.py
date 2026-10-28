"""The review document: the week of the creatives, for the people who read the feedback. A view of what the life document, the fission score and the
demand already say, never a contract file. No database, no file, no clock, no platform: the pack hands over the creatives' days (the same `Source` the life
document reads, wrapped) and, if it has one, the demand block its pacing document gave, and prints what `compute()` returns. Read-only.

    {as_of, window {from, to, days},
     moved [{creative, label, date, from, to, reason, read, message, message_code}]   every state change inside the window, newest first,
     now {states {<state>: count}, entities {<entity>: {<state>: count}}},
     early {parked {<reason>: count}, ended {<reason>: count}, doubt, waiting}  what the creatives that did not work say:
         low_reach = the platform never showed it (change the concept or the opening), no_conversion = shown and nobody bought (the offer or the
         page); the signal while no creative has a score yet,
     scored [{creative, label, state, reason, fission}]                          highest first; none until a creative has a verdict,
     unscored {<state>: count},
     demand {...} | None                                                          what the pack's pacing document asks the maker for (None without one),
     warnings, warning_codes}

The pack adds its own `meta`. The states, the moves and their coded messages are the life document's (`kit.compute_life`, run on the same creatives, whose own
warnings this document keeps); the scores are `kit.fission`'s. The page people read is drawn from this document by the pack; its words are the client's own.

From the video-ads skill pack (`scripts/compute_review.py`; its cases are this module's test, over a synthetic fixture).

Test: kit/tests/test_compute_review.py.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from kit import compute_life, fission
from kit.contract import SkillPackError
from kit.messages import coded, msg


@dataclass
class Source:
    """One reading of a pack's tables.

    life     the creatives' days, as `kit.compute_life.Source` has them
    demand   the demand block of the pack's pacing document (what it asks the maker for), or None without a month's spend target: handed through, never guessed
    """
    life: compute_life.Source
    demand: dict | None = None


def _bad(part: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("compute_input_invalid", f"the pack's tables give {part} {problem}", part=part, problem=problem))


def check(src: Source, days: int) -> None:
    """Refuse a `Source` the rules cannot read, naming the part (`compute_input_invalid`)."""
    compute_life.check(src.life)
    if src.demand is not None and not isinstance(src.demand, dict):
        raise _bad("demand", f"{src.demand!r}, which is not a block (a dict) or None")
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise _bad("days", f"{days!r}, which is not a number of days of 1 or more")


def compute(src: Source, k: dict, *, days: int = 7) -> dict:
    """The week (the last `days` complete days) of the creatives of `src`. `k` is the thresholds in effect: the `life_*` rows and `fission_*` rows."""
    check(src, days)
    life = compute_life.compute(src.life, k)
    rows = life["rows"]
    warnings = list(life["warnings"])
    last = life["as_of"]
    window = None
    moved: list[dict] = []
    if last:
        since = (date.fromisoformat(last) - timedelta(days=days - 1)).isoformat()
        window = {"from": since, "to": last, "days": days}
        moved = sorted(({"creative": r["creative"], "label": r["label"], "date": m["date"], "from": m["from"], "to": m["to"], "reason": m["reason"],
                         "read": m["read"], "message": m["message"], "message_code": m["message_code"]}
                        for r in rows for m in r["moves"] if since <= m["date"] <= last),
                       key=lambda m: (m["date"], m["label"]), reverse=True)
    elif not any(c == "life_no_creatives" for c in (w["code"] for w in life["warning_codes"])):
        warnings.append(msg("life_no_creatives", "no creative has a day to read"))
    by_state = Counter(r["state"] for r in rows)
    early = {"parked": dict(Counter(r["reason"] or "none" for r in rows if r["state"] == "parked")),
             "ended": dict(Counter(r["reason"] or "none" for r in rows if r["state"] == "ended")),
             "doubt": by_state.get("doubt", 0), "waiting": sum(1 for r in rows if r["waiting"])}
    counted = {("", cid): c["days"] for cid, c in src.life.creatives.items()}              # fission reads rows by (source, creative): one source here
    scored, _bench, omitted = fission.scores([{**r, "source": ""} for r in rows], counted, int(k["fission_window_days"]), int(k["fission_benchmark_min"]))
    label = {r["creative"]: r for r in rows}
    given = sorted(({"creative": c, "label": label[c]["label"], "state": v["state"], "reason": v["reason"], "fission": round(v["fission"], 2)}
                    for c, v in scored.items() if v["fission"] is not None and c in label), key=lambda x: (-x["fission"], x["label"]))
    return {"as_of": last, "window": window, "moved": moved,
            "now": {"states": dict(by_state), "entities": life["by_entity"]},
            "early": early, "scored": given, "unscored": omitted, "demand": src.demand, **coded("warnings", warnings)}
