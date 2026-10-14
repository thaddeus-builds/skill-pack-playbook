# Path weights: which variants beat the account, what to make next

> Status: parked 2026-10-14. The code (`pathweights.py`, `questions.py`) is in [`_parked/learning/`](../_parked/README.md), not in `kit/`: written from the video-ads harness, which keeps its own copy. The design below stays.

A harness that makes variants a client pays to run (ads, posts, emails) and gets back, per variant, its spend and its conversions can read from them which kinds of variant do better than the client's own account, which to make more of, which to make less of, and which a person may close. Module: [`_parked/learning/pathweights.py`](../_parked/learning/pathweights.py), pack `learning` (`[kit] packs = ["learning"]`). It reads numbers and proposes; it writes nothing, pays for nothing and closes nothing.

*Seen once:* the video-ads harness built it for its first client (2026-10-13) and is the worked example: its `pkg/spacemodel.py` (the statistics, pure), `pkg/space.py` (what it reads, its verbs, its tables, a person's close at the gate) and its `docs/space.md`. It keeps its own copy for now; this module is that copy with the channel taken out, and with fixes that copy takes when it adopts the module (warmth under the thresholds in hand, the explore share's fill within the batch first, a `twin_ratio` above 1, `downweight_p` below `promising_p`, sorted move keys, the Gamma series at large shapes).

## When to use it

When a harness lays what it makes out as a plan with a shape (directions, templates, the values of each template's variables) and wants to steer the next batch by the numbers that come back. It compares a variant with **the account's own rate** (settled conversions per unit of spend), sets no target cost, and pauses, scales or stops nothing on the platform: those stay with whoever runs the ads. What counts as a conversion is the harness's (one field it reads); conversions may be fractional (expected counts from early signals).

## The partition

| Word | What it is |
| --- | --- |
| unit | one variant the harness made; it sits on exactly one leaf |
| leaf | one path of the plan (in the video-ads harness: one direction x one template x one value of each of its variables): `{id, parents, conv, spend, shift?}`, its numbers the sum of its units' |
| parents | the leaf's ancestors' keys from the top, in order, any depth (none: directly under the account): a list, never a set (a set's order changes from process to process, and the tree with it); a node is a tuple of them, and its numbers are the sum of its children's |
| account | every unit the harness counts, on a leaf or not: never less than the leaves' sums (`total=`) |
| move | a step the harness can take next, and the units it makes: `{id, group, n, kind, post, exclusive?, shared?}`; its keys are a list or a set, their order meaning nothing (kept sorted) |

So the tree is a partition: a unit on no leaf (its template unknown, say) still counts in the account and on no node.

## The rules

1. **Only settled numbers count.** A unit's numbers judge once the harness says they are settled; open numbers only show. A leaf the platform starved stays `testing`, never `down`.
2. **The prior is borrowed down the partition, leave-one-out** (`posteriors()`). A leaf's rate is a Gamma-Poisson posterior on its settled spend and conversions (the Poisson kernel is a quasi-likelihood for fractional conversions; the mean stays right). Each level's prior mean is its parent's posterior mean with the level's own numbers taken out, so nothing counts twice, and it is worth `prior_conv` conversions: once a leaf has numbers of its own, the prior matters little. The weight is P(leaf rate > account rate). The Gamma functions run their series to convergence at any count (the terms allowed grow with the square root of the shape, so a leaf with 1e9 conversions is not cut short either) and raise rather than return a truncated number.
3. **Outside evidence moves a prior, never the data.** A leaf's optional `shift` multiplies its prior mean (the video-ads harness takes it from its pattern store, [pattern-store.md](pattern-store.md), only where a value's cell reads), clipped to [1 / `prior_shift_max`, `prior_shift_max`]; its nodes are untouched.
4. **Five states, each with its reason** (`judge()`, decided on the rounded numbers it returns, so what is shown never contradicts it):

   | State | Reason | When |
   | --- | --- | --- |
   | untested | `not_made` | no unit made on it |
   | testing | `account_thin` | the account has no rate, or fewer than `account_min_conv` settled conversions under the thresholds `judge()` is given |
   | testing | `no_settled_numbers` | made, no settled spend yet |
   | testing | `spend_thin` | its settled spend buys fewer than `min_expected_conv` at the account rate |
   | testing | `no_difference_yet` | P(better) between the two lines |
   | promising | `likely_better` | P(better) at least `promising_p` |
   | down | `likely_worse` | P(better) at most `downweight_p`: the next batch makes less of it |
   | closed | `closed_by_person` | a person's close stands on it |

   A node is judged by the same rule on its own posterior; whether a node's proposal is shown is the harness's (the video-ads harness shows none). `judge()` and `pick()` decide whether the account is warm from its rate and conversions under the thresholds they are given; the `warm` an `account()` dict carries answers only for the thresholds that built it, and neither reads it.
5. **A close is only ever a proposal.** A down leaf is proposed when its settled spend buys at least `close_min_expected_conv` at the account rate, at least `close_min_units` of its units have settled spend, and P(rate >= `close_ratio` x the account rate) is at most `close_p`. A person confirms it at the gate (`kit.human`), the harness records it in its own append-only table and passes `closed=True` from then on; a reopen is a newer record. Nothing here decides a close.
6. **The next batch is drawn from moves, not leaves** (`pick()`): the largest of thousands of draws is always some leaf nobody tried, so the harness builds the moves it can really make (a promising leaf's neighbour is `known`; a first try, an untried neighbour or a new direction is `unknown`), each with `n`, the units it makes, and the posterior it stands on (a leaf's, a node's, or None: the account's own rate).
   - **Cold** (the account not warm): coverage, in the order the harness gives, each move whole, so a batch may run up to two over.
   - **Warm:** at least `explore_share` of the batch from `unknown` moves (plain Thompson draws), then batched top-two Thompson over all (the leader, or half the time the best of a fresh draw over the others). In both, the draw is among the moves that fit within the batch; a move up to two over is taken only when none fits, rather than leaving the batch (or its explore share) short.
   - **Always:** a group takes at most half a batch, rounded down (2 of 5, at least 1), and a move bigger than that only into an empty group, then alone. Two moves never both hold a key when either holds it `exclusive`; `shared` holders fit together (several moves may build on a template, one may remake it, never both in one batch). The seed comes from the moves (their keys sorted) and the account, or the harness's `seed`, so the same data gives the same batch, in any process.
7. **Twins are a clue, never proof** (`twins()`). Units of one group with the same tags whose settled rates differ by `twin_ratio` with probability `twin_p` under a weak prior, once the group has `twin_min_conv` settled conversions and each compared unit spend worth `twin_min_expected_conv`: at most three, the largest gap first, with what the harness knows to differ (`known`). A tag nobody records may hide there, or the two were bought differently; the agent proposes the tag and tests it on new units, never on the numbers that raised it.

## Past results: a gap signal, never a weight

A client who starts with a harness has usually run ads before. Those past units (another period, bought by another hand, never made from this plan) are evidence about the plan's design: a direction the plan leans on that the past read badly, an angle that worked and that no template serves. `past_signal(units, groups, cfg)` reads them. It is the only door they have, and it is a report, not an input.

**Why they stay out of the weights.** Rule 1 counts only settled numbers, and every number the partition holds is the plan's own, the account's included. Pour past numbers into a leaf, the account or a prior and four things go wrong: every state would then mean "better than the account, as it was bought by someone else"; a close, which a person confirms against the leaf's own numbers, would rest on spend nobody here chose; a unit that is both a past one and one of the plan's would count twice; and the platform's steering of that older spend (to what it predicted would respond) would read as the variant's quality. Rule 3 lets outside evidence move a prior; this does not even do that.

**What it does.**

- A past unit is `{id, spend, conv}` (conversions may be fractional; a unit with conversions and no spend counts nowhere); a group is `{units: [ids], ours?: how many units of the harness's own sit in it}`. The harness decides what a group is: a cut of the pool by audience, by angle, by script family, by direction. A unit may sit in several.
- The pool is every past unit with spend, and its rate R is its own conversions over its own spend. A group is judged against **R, never the account's rate**: P(its rate > R) under a Gamma-Poisson posterior whose prior is R worth `prior_conv` conversions. The pool includes the group (unlike rule 2's leave-one-out), so a group that is most of the pool reads conservatively and its `vs_pool` is understated. It speaks once its spend would buy `past_min_expected_conv` at R. It reads `strong` at `promising_p` or more, `weak` at `downweight_p` or less, else nothing.
- `gaps` are strong groups the plan has no unit on (`ours == 0`); `warnings` are weak groups the plan has `past_warn_units` or more units on. With no pool rate nothing is judged. Each group also carries its unit count, spend, conversions, `vs_pool` (its rate over R), `expected`, and the top three units by conversions, so the agent can study them.
- It returns lists of keys and numbers for people to read. Nothing in the result is an input of `posteriors()`, `judge()` or `pick()`; the test holds that those functions' results do not change when the past is read, and that none of their sources names it.

**What a gap or a warning leads to.** A proposal for a person to confirm: a new row or template for an angle the plan does not serve, a look at a direction the plan leans on. Whether a gap can be acted on is the harness's (can the client say it, is the audience right): a strong group nothing can say is a proposal for the agent to raise, never a move. A past winner is studied for the mechanism that worked, never copied ([lessons](lessons.md#a-past-winner-the-harness-cannot-say-is-studied-for-its-mechanism-never-copied)).

**How much to trust it.** It is a pointer, not a finding. With every group equally good and only Poisson noise, groups of five units (spend 500 to 4000 each) read strong about 1 time in 6 and weak about 1 time in 5. Real ads differ by more than Poisson noise (the model has no spread between units), so expect more: with unit rates spread by half a log-unit, about a third read strong and 2 in 5 weak (the test prints both). Among many groups some will read strong by chance: look at the ones with a reason, and let the plan's own numbers decide.

*Seen once:* the video-ads harness (its ROADMAP D64, owner decision 2026-10-13), on its first client's past ads: it flagged a direction the plan leaned on that the past read weak, and angles no template served, and kept the plan's weights and closes untouched. It keeps its own copy for now (it adds which rows can say an angle); this function is that part with the channel taken out. Test: [`_parked/learning/tests/test_pathweights.py`](../_parked/learning/tests/test_pathweights.py), section 8.

## Thresholds

Every threshold is in `DEFAULTS`; `settings(over)` lays the harness's defaults or a client's own values (kept in that client's database) over them and refuses one that is not a value of it, naming the key: an unknown key, not a finite number, a count not whole, a probability or share not strictly between 0 and 1, a `close_ratio` outside (0, 1], a `prior_shift_max` below 1, a `twin_ratio` not above 1, anything else not above 0. Across keys it refuses a `downweight_p` not below `promising_p` (one P(better) would be both down and promising), so a client who moves one line past the other moves both.

| Key | Default | What it is |
| --- | --- | --- |
| `prior_conv` | 2 | a prior is worth this many conversions at its parent's rate |
| `account_min_conv` | 10 | settled conversions the account needs before anything is judged |
| `min_expected_conv` | 3 | a leaf is judged once its settled spend would buy this many at the account rate |
| `promising_p` | 0.8 | P(better than the account) at or above which a leaf is promising |
| `downweight_p` | 0.2 | P(better than the account) at or below which a leaf is down |
| `close_min_expected_conv` | 5 | settled spend, in conversions at the account rate, before a close is proposed |
| `close_min_units` | 2 | units with settled spend a leaf needs before a close is proposed |
| `close_ratio` | 0.7 | a close asks whether the leaf reaches this share of the account rate |
| `close_p` | 0.1 | P(rate >= close_ratio x account rate) at or below which a close is proposed |
| `batch_size` | 5 | units in a next batch |
| `explore_share` | 0.3 | the least share of a batch kept for moves not known yet |
| `twin_min_conv` | 6 | settled conversions a group of same-tag units needs before it is compared |
| `twin_min_expected_conv` | 2 | settled spend, in conversions at the account rate, each compared unit needs |
| `twin_ratio` | 2 | how many times better the best twin must be (above 1) |
| `twin_p` | 0.9 | the probability of that ratio before twins are flagged |
| `prior_shift_max` | 1.5 | the most a leaf's shift moves its prior mean (and 1 / it, the least) |
| `past_min_expected_conv` | 3 | a group of past units speaks once its settled spend buys this many conversions at the past pool's own rate |
| `past_warn_units` | 3 | units of the harness's own on a group the past reads weak before it is warned about |

## What the harness supplies

- **Its plan and its partition:** what a leaf is, its parents, which units sit on it, and a stable leaf id (the video-ads harness hashes the leaf's direction, template and values).
- **Its numbers:** each unit's settled spend and conversions from one results file, and the account's total.
- **Its moves:** what each one makes (`n`), its group, its kind, the posterior it stands on, its keys, and the coverage order for a cold account.
- **Its records and its gate:** the closes and reopens a person made, the tables they live in, the shown digest a close is bound to, and how a person sees all of it.
- **Its thresholds:** its defaults and where a client's own values are kept.
- **Its past units and their groups,** if it has any: the cuts it makes of them and what `ours` counts.

## What it cannot say

- The numbers are observational: a platform steers spend to the variants it predicts will respond, so "better than the account" is a statement about these numbers, never a cause.
- At tens of variants and single-digit conversions only gaps of about 2x show; smaller ones stay invisible, and most leaves stay `testing` for weeks. Borrowing down the partition is what lets anything be said earlier.
- Calibration, held by the test: with every leaf equally good, five rounds of numbers and spend pushed to early leaders, at most 5 in 100 made leaves are ever proposed for closing (the test prints the measured rates).

Test: [`_parked/learning/tests/test_pathweights.py`](../_parked/learning/tests/test_pathweights.py).
