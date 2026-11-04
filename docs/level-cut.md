# The level cut: where on a ladder the rate of going further jumps

Customers climb a ladder: the orders placed to date, or any count or bucketed amount (the coins topped up, a tier). At each level some of them go on to the next level within a window, say 180 days. That share usually rises with the level, and a customer past the step where it rises most behaves like a regular. Where that step is should be read from the data, not set by hand (the owner's R54, 2026-11-03: "先看一下每一层到下一层的转化率的变化率，以变化基点为切分的地方"). `kit/level_cut.py` (pack `ads-core`) reads it from counts. It is pure: no database, no clock, no platform, no I/O. It names the cut; what to do with the two sides (who is advertised to, who is left to the client's own channels) is the pack's.

## What goes in

A list of levels in ladder order. Each level has a label, the customers **eligible** at it, and how many of them **reached** the next level within the window:

```python
[{"level": 1, "eligible": 4200, "reached": 760},
 {"level": 2, "eligible":  760, "reached": 266},
 ...]
```

*Eligible* means the customer sat at that level long enough for the whole window to have passed. A customer whose level was reached last week is not eligible for a 180-day window; counting them lowers every rate and makes the longer window look worse than the shorter. A pack that reads a shop's order table decides this when it builds the counts; the module cannot see it.

Several windows go in as `{"90": levels, "180": levels, "365": levels}`. Every window lists the same levels in the same order; only the counts differ.

## What it does

1. **A rate per level**, `reached / eligible`, with a Wilson score interval (95 % by default). A level nobody was eligible for has no rate and no interval; it is `no_data`, never 0.
2. **A change per step**, the rate at the higher level minus the rate at the lower, with Newcombe's hybrid score interval for the difference of two independent rates. A level with few customers has a wide interval, so a jump between two small levels does not count.
3. **The cut.** Among the steps whose whole interval is above zero (`rises`), the one with the largest change; a tie goes to the lowest step. The level it names is the first one on the far side, the level whose own rate is the high one. If no step rises, the result is `no_clear_cut`; if no two neighbouring levels both have customers, `no_data`.
4. **Who stands with the cut.** `competing` lists the other rising steps whose interval still holds the cut's change. An empty list means the cut stands alone. On an evenly rising ladder it lists the others: the largest step is named, and the output says it cannot be told from them.
5. **Side by side.** `level_cuts` runs each window and says whether they `agree` on the level. If one window names a different level, or none, the result is `windows_differ` and no level is returned; the pack shows the windows and a person decides.

## Output (`--json`-ready dict)

```
level_cut(levels, Params()) ->
  params   {confidence, adjust, z, tests}
  levels   [{index, level, eligible, reached, rate, low, high, status}]       status ok | no_data
  steps    [{index, from, to, change, low, high, rises, status}]
  cut      {step, level, after, change, low, high, competing[]}  |  None
  result   cut | no_clear_cut | no_data
  message, message_code {code, params}

level_cuts({window: levels}, Params()) ->
  windows  {window: level_cut result}        in the order given
  cuts     {window: level | None}
  agree    bool                              every window names a cut and the same one
  level    the agreed level | None
  result   cut | windows_differ | no_clear_cut | no_data
  message, message_code

side_of(result, level) -> "below" | "at_or_above" | None
```

Message codes (`kit/message_codes.d/level_cut.tsv`): `level_cut_found`, `level_cut_found_all`, `level_cut_windows_differ`, `level_cut_no_clear`, `level_cut_no_data`; bad input raises `SkillPackError` with `level_cut_bad_input` (`where` names the level or window, `problem` says what). Refused: fewer than two levels, a count that is not a whole number of 0 or more (a boolean included), `reached` above `eligible`, a repeated label, a window that lists other levels, a confidence outside 0.5 to under 1.

## What the test world showed

On invented ladders, not on any client's numbers (`kit/tests/test_level_cut.py`):

| | |
| --- | --- |
| Wilson and Newcombe | equal the published worked examples (10 of 20; 56 of 70 against 48 of 80: +0.2000, 0.0524 to 0.3339); correct at 0 of n and n of n |
| Rates 0.10, 0.12, 0.45, 0.47, 0.50 on 400 customers a level | the cut is level 3, change +0.33, and it stands alone |
| Flat ladder; falling ladder; 3 customers a level with a 0.67 jump | no clear cut |
| An even climb of 0.10 a level | the cut is the first step, and the other three are listed as competing |
| 400 flat ladders, 8 levels of 300 customers, true rate 0.30 | a cut is wrongly named in 15 % of them with the default; 2 % with `adjust="bonferroni"` |
| 400 ladders that jump from 0.15 to 0.35 at level 4 | level 4 is found in 399 of 400, with the default and with the correction |

## What it assumes, and what breaks it

- **The largest of several steps is chosen,** and each step's interval is a 95 % one on its own. Looking at seven steps and keeping the largest one that clears zero names a cut on a flat ladder one time in seven. That is the brief's definition, so it is the default; `Params(adjust="bonferroni")` divides the error over the steps that have data and brings the false rate under 5 % at a small cost in power. A pack that acts on the cut alone, with no person looking at the intervals, uses the correction.
- **Each customer is counted at one level,** the one they are at. The ladder is a snapshot of where customers are, not each customer's whole path, so the levels are independent samples. A pack that counts a customer at every level they passed has counted the same people many times, and its intervals are too narrow.
- **One window for every level,** and the same rule for who is eligible.
- **Small ladders and the top.** The top levels are often thin; their intervals are wide and they seldom decide the cut. That is the intended behaviour, not a gap.
- **A cut is a statement about rates, not a reason.** A step can rise because the shop sends a coupon with the second order. The module does not know.

## Seen where

The Meta ads skill pack (its ROADMAP X112, R54, R66, 2026-11-04) reads a client's order ladder to say who belongs in Retargeting and who in the client's own channels; a hand reading put the first rise whose interval excludes zero at the second order in every window. The owner said yes to building it in the kit, because other businesses have the same shape (top-up tiers, a count of plays). It lives in `ads-core` because the Meta ads skill pack already takes that pack; it imports only the stdlib and `base`, so it moves to a pack of its own the day a skill pack outside advertising needs it. `ads-core` is `incubating` until two packs import it ([tools/pack_status.tsv](../tools/pack_status.tsv)).
