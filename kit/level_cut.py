"""The level cut: where on a ladder of levels the rate of reaching the next level jumps, read from counts alone. No database, no clock, no platform, no I/O.

A customer sits on a level (the orders placed to date; a count or a bucketed amount of anything else, e.g. a top-up tier). For each level the caller knows how many
customers were eligible (they had the level long enough for the window to be observed) and how many of them reached the next level within the window. The rate at a level
is `reached / eligible`; the rate usually rises with the level, and the step where it rises most is where a customer starts to behave like a regular. This module reads that
step and says how sure it is. It decides nothing about who belongs where: a caller applies the cut.

  * `level_cut(levels, params)`: one window. `levels` is a list in ladder order of `{"level": label, "eligible": n, "reached": k}` (or `(label, n, k)`). It returns
    - `levels`: per level the rate with its Wilson interval (`status` `ok`, or `no_data` when nobody was eligible: no rate, no interval);
    - `steps`: per pair of consecutive levels the change in the rate (the higher level's minus the lower's) with its Newcombe interval (the two Wilson intervals combined, so a
      tiny level gives a wide interval, never a false precision), `rises` when the whole interval is above zero, and `status` `no_data` when either level has none;
    - `cut`: the step with the largest change among the steps that `rise`, ties to the lowest; `level` is the first level on the far side (the level whose own rate is the
      higher one), `after` the level below it, with its change and interval, and `competing`: the other rising steps whose interval still holds the cut's change, so
      "the largest" is not read as "alone" on a ladder that rises evenly; or `None`;
    - `result`: `cut`, `no_clear_cut` (data, but no step whose interval excludes zero) or `no_data` (no step with data on both sides); `message` and `message_code`.
  * `level_cuts(windows, params)`: several windows side by side (90, 180, 365 days ...). `windows` maps a window label to its `levels`; every window must list the same
    levels in the same order (its counts differ: a longer window has fewer eligible customers). It returns each window's `level_cut` under `windows`, `cuts` (the cut's
    level per window, `None` for none), `agree` (every window names a cut and the same one), `level` (that level when they agree) and a `result` of `cut`, `windows_differ`,
    `no_clear_cut` or `no_data`.
  * `side_of(result, level)`: `"below"` or `"at_or_above"` the cut for a level label, `None` when the result has no cut; the one place a pack asks which side a customer is on.
  * `wilson(k, n, z)`, `change_interval(lower, higher, z)`, `z_for(params, tests)`: the pieces, public so a pack can show the arithmetic.

The interval is Wilson's for a rate and Newcombe's hybrid score interval for a difference of two independent rates (Newcombe 1998, method 10): both are exact in their
tails for small and extreme counts where the plain normal interval fails (0 of 12, 12 of 12). Everything is stdlib arithmetic, so the same counts give the same bytes.

What it assumes: that a customer counts once in a level's `eligible` and reached the next level at most once, that the levels are independent samples (a customer is eligible
at one level at a time: the ladder is a snapshot of where each customer is, not a customer's whole path), and that the window is the same for every level. It does not correct
for choosing the largest of several steps: with `adjust="none"` (the default, as the brief says) a flat ladder of eight levels (seven steps) shows a false cut in about one run in seven (15 % measured in the test);
`adjust="bonferroni"` divides the error over the steps with data and costs power (docs/level-cut.md).

Test: kit/tests/test_level_cut.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

from kit.contract import SkillPackError
from kit.messages import coded, msg

ADJUSTS = ("none", "bonferroni")
ROUND = 6


@dataclass(frozen=True)
class Params:
    confidence: float = 0.95     # the coverage of every interval, two-sided
    adjust: str = "none"         # "bonferroni": the error is divided over the steps that have data on both sides


def _bad(where: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("level_cut_bad_input", f"{where} {problem}", where=where, problem=problem))


def _check_params(params: Params) -> None:
    if not isinstance(params, Params):
        raise _bad("params", "must be a Params")
    c = params.confidence
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0.5 <= c < 1:
        raise _bad("params.confidence", "must be a number from 0.5 up to (not including) 1")
    if params.adjust not in ADJUSTS:
        raise _bad("params.adjust", f"must be one of {', '.join(ADJUSTS)}")


def z_for(params: Params = Params(), tests: int = 1) -> float:
    """The normal quantile for a two-sided interval at `params.confidence`; with `adjust="bonferroni"` the error is shared by `tests` comparisons."""
    _check_params(params)
    alpha = 1 - params.confidence
    if params.adjust == "bonferroni":
        alpha /= max(1, tests)
    return NormalDist().inv_cdf(1 - alpha / 2)


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float, float] | None:
    """(rate, low, high) of `k` out of `n` by Wilson's score interval; None when n is 0."""
    if n <= 0:
        return None
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def change_interval(lower: tuple[int, int], higher: tuple[int, int], z: float = 1.959963984540054) -> tuple[float, float, float] | None:
    """(change, low, high) of the rate at `higher` minus the rate at `lower`, each given as (reached, eligible), by Newcombe's hybrid score interval; None when either has no
    one eligible."""
    a, b = wilson(lower[0], lower[1], z), wilson(higher[0], higher[1], z)
    if a is None or b is None:
        return None
    (p1, l1, u1), (p2, l2, u2) = b, a            # p1 - p2, the rise from the lower level to the higher
    d = p1 - p2
    low = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    high = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, max(-1.0, low), min(1.0, high)


def _rows(levels, where: str) -> list[tuple]:
    if isinstance(levels, (str, bytes, dict)) or not hasattr(levels, "__iter__"):
        raise _bad(where, "must be a list of levels")
    out: list[tuple] = []
    for i, row in enumerate(levels):
        at = f"{where}[{i}]"
        if isinstance(row, dict):
            if set(row) != {"level", "eligible", "reached"}:
                raise _bad(at, "needs exactly level, eligible and reached")
            label, n, k = row["level"], row["eligible"], row["reached"]
        elif isinstance(row, (tuple, list)) and len(row) == 3:
            label, n, k = row
        else:
            raise _bad(at, "must be {level, eligible, reached} or (level, eligible, reached)")
        if label is None or isinstance(label, (bool, float, dict, list, tuple)) or label == "":
            raise _bad(at, "has a level that is not a name or a whole number")
        for name, v in (("eligible", n), ("reached", k)):
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise _bad(at, f"has {name} that is not a whole number of 0 or more")
        if k > n:
            raise _bad(at, "reached more customers than were eligible")
        if any(label == r[0] and type(label) is type(r[0]) for r in out):
            raise _bad(at, "repeats a level")
        out.append((label, n, k))
    if len(out) < 2:
        raise _bad(where, "needs at least two levels")
    return out


def _r(x: float) -> float:
    return round(x, ROUND) + 0.0               # + 0.0: no -0.0 in the JSON


def level_cut(levels, params: Params = Params()) -> dict:
    """One window's levels, rates, steps and cut (the module docstring says what each key holds)."""
    _check_params(params)
    rows = _rows(levels, "levels")
    tests = sum(1 for a, b in zip(rows, rows[1:]) if a[1] > 0 and b[1] > 0)
    z = z_for(params, tests)

    out_levels = []
    for i, (label, n, k) in enumerate(rows):
        w = wilson(k, n, z)
        row = {"index": i, "level": label, "eligible": n, "reached": k}
        if w is None:
            row.update(rate=None, low=None, high=None, status="no_data")
        else:
            row.update(rate=_r(w[0]), low=_r(w[1]), high=_r(w[2]), status="ok")
        out_levels.append(row)

    steps = []
    for i, (a, b) in enumerate(zip(rows, rows[1:])):
        ci = change_interval((a[2], a[1]), (b[2], b[1]), z)
        step = {"index": i, "from": a[0], "to": b[0]}
        if ci is None:
            step.update(change=None, low=None, high=None, rises=False, status="no_data")
        else:
            step.update(change=_r(ci[0]), low=_r(ci[1]), high=_r(ci[2]), rises=_r(ci[1]) > 0, status="ok")
        steps.append(step)

    rising = [s for s in steps if s["rises"]]
    cut = None
    if rising:
        best = max(rising, key=lambda s: (s["change"], -s["index"]))
        cut = {"step": best["index"], "level": best["to"], "after": best["from"], "change": best["change"], "low": best["low"], "high": best["high"],
               "competing": [s["index"] for s in rising if s is not best and best["change"] <= s["high"]]}

    if cut is not None:
        result = "cut"
        m = msg("level_cut_found", f"the rate rises most from level {cut['after']} to level {cut['level']}: {cut['change']:+.1%} "
                f"(interval {cut['low']:+.1%} to {cut['high']:+.1%})", level=cut["level"], after=cut["after"], change=cut["change"])
    elif tests:
        result = "no_clear_cut"
        m = msg("level_cut_no_clear", f"no clear cut: none of the {tests} steps with data rises with an interval above zero", steps=tests)
    else:
        result = "no_data"
        m = msg("level_cut_no_data", "no cut can be read: no two consecutive levels both have eligible customers", levels=len(rows))
    return {"params": {"confidence": params.confidence, "adjust": params.adjust, "z": _r(z), "tests": tests},
            "levels": out_levels, "steps": steps, "cut": cut, "result": result, **coded("message", m)}


def level_cuts(windows, params: Params = Params()) -> dict:
    """Several windows side by side: each window's `level_cut`, the cut level per window, and whether they agree."""
    if not isinstance(windows, dict) or not windows:
        raise _bad("windows", "must be a mapping from a window label to its levels")
    results: dict[str, dict] = {}
    ladder = None
    for w, levels in windows.items():
        if not isinstance(w, (str, int)) or isinstance(w, bool):
            raise _bad("windows", "has a window label that is not a name or a number")
        rows = _rows(levels, f"windows[{w}]")
        names = [r[0] for r in rows]
        if ladder is None:
            ladder = names
        elif names != ladder:
            raise _bad(f"windows[{w}]", "lists other levels than the first window")
        results[str(w)] = level_cut(rows, params)

    cuts = {w: (r["cut"]["level"] if r["cut"] else None) for w, r in results.items()}
    named = [v for v in cuts.values() if v is not None]
    agree = len(named) == len(cuts) and all(v == named[0] for v in named)
    if agree:
        result, level = "cut", named[0]
        m = msg("level_cut_found_all", f"all {len(cuts)} windows put the cut at level {level}", level=level, windows=len(cuts))
    elif named:
        result, level = "windows_differ", None
        m = msg("level_cut_windows_differ", "the windows do not agree on the cut: " + ", ".join(f"{w}: {v if v is not None else 'none'}" for w, v in cuts.items()),
                cuts=[{"window": w, "level": v} for w, v in cuts.items()])
    elif any(r["result"] == "no_clear_cut" for r in results.values()):
        result, level = "no_clear_cut", None
        m = msg("level_cut_no_clear", f"no clear cut in any of the {len(cuts)} windows", steps=sum(r["params"]["tests"] for r in results.values()))
    else:
        result, level = "no_data", None
        m = msg("level_cut_no_data", "no cut can be read in any window: no two consecutive levels both have eligible customers", levels=len(ladder))
    return {"windows": results, "cuts": cuts, "agree": agree, "level": level, "result": result, **coded("message", m)}


def side_of(result: dict, level) -> str | None:
    """`"below"` or `"at_or_above"` the cut for a level label of `result` (a `level_cut`, or the agreed cut of a `level_cuts`); None when it has no cut. An unknown level is
    refused."""
    if "windows" in result:
        if not result["agree"]:
            return None
        first = next(iter(result["windows"].values()))
        cut_level = result["level"]
    else:
        first, cut_level = result, (result["cut"]["level"] if result["cut"] else None)
    names = [row["level"] for row in first["levels"]]
    if not any(level == n and type(level) is type(n) for n in names):
        raise _bad("level", f"{level!r} is not on the ladder")
    if cut_level is None:
        return None
    pos = {n: i for i, n in enumerate(names)}
    return "below" if pos[level] < pos[cut_level] else "at_or_above"
