# Path weights: which variants beat the account, what to make next

A harness that makes variants a client pays to run (ads, posts, emails) and gets back, per variant, its spend and its conversions can read from them which kinds of variant do better than the client's own account, which to make more of, which to make less of, and which a person may close. Module: [`kit/pathweights.py`](../kit/pathweights.py), pack `learning` (`[kit] packs = ["learning"]`). It reads numbers and proposes; it writes nothing, pays for nothing and closes nothing.

*Seen once:* the video-ads harness built it for its first client (2026-10-13) and is the worked example: its `pkg/spacemodel.py` (the statistics, pure), `pkg/space.py` (what it reads, its verbs, its tables, a person's close at the gate) and its `docs/space.md`. It keeps its own copy for now; this module is that copy with the channel taken out.

## When to use it

When a harness lays what it makes out as a plan with a shape (directions, templates, the values of each template's variables) and wants to steer the next batch by the numbers that come back. It compares a variant with **the account's own rate** (settled conversions per unit of spend), sets no target cost, and pauses, scales or stops nothing on the platform: those stay with whoever runs the ads. What counts as a conversion is the harness's (one field it reads); conversions may be fractional (expected counts from early signals).

## The partition

| Word | What it is |
| --- | --- |
| unit | one variant the harness made; it sits on exactly one leaf |
| leaf | one path of the plan (in the video-ads harness: one direction x one template x one value of each of its variables): `{id, parents, conv, spend, shift?}`, its numbers the sum of its units' |
| parents | the leaf's ancestors' keys from the top, any depth (none: directly under the account); a node is a tuple of them, and its numbers are the sum of its children's |
| account | every unit the harness counts, on a leaf or not: never less than the leaves' sums (`total=`) |
| move | a step the harness can take next, and the units it makes: `{id, group, n, kind, post, exclusive?, shared?}` |

So the tree is a partition: a unit on no leaf (its template unknown, say) still counts in the account and on no node.

## The rules

1. **Only settled numbers count.** A unit's numbers judge once the harness says they are settled; open numbers only show. A leaf the platform starved stays `testing`, never `down`.
2. **The prior is borrowed down the partition, leave-one-out** (`posteriors()`). A leaf's rate is a Gamma-Poisson posterior on its settled spend and conversions (the Poisson kernel is a quasi-likelihood for fractional conversions; the mean stays right). Each level's prior mean is its parent's posterior mean with the level's own numbers taken out, so nothing counts twice, and it is worth `prior_conv` conversions: once a leaf has numbers of its own, the prior matters little. The weight is P(leaf rate > account rate).
3. **Outside evidence moves a prior, never the data.** A leaf's optional `shift` multiplies its prior mean (the video-ads harness takes it from its pattern store, [pattern-store.md](pattern-store.md), only where a value's cell reads), clipped to [1 / `prior_shift_max`, `prior_shift_max`]; its nodes are untouched.
4. **Five states, each with its reason** (`judge()`, decided on the rounded numbers it returns, so what is shown never contradicts it):

   | State | Reason | When |
   | --- | --- | --- |
   | untested | `not_made` | no unit made on it |
   | testing | `account_thin` | the account has fewer than `account_min_conv` settled conversions |
   | testing | `no_settled_numbers` | made, no settled spend yet |
   | testing | `spend_thin` | its settled spend buys fewer than `min_expected_conv` at the account rate |
   | testing | `no_difference_yet` | P(better) between the two lines |
   | promising | `likely_better` | P(better) at least `promising_p` |
   | down | `likely_worse` | P(better) at most `downweight_p`: the next batch makes less of it |
   | closed | `closed_by_person` | a person's close stands on it |

   A node is judged by the same rule on its own posterior; whether a node's proposal is shown is the harness's (the video-ads harness shows none).
5. **A close is only ever a proposal.** A down leaf is proposed when its settled spend buys at least `close_min_expected_conv` at the account rate, at least `close_min_units` of its units have settled spend, and P(rate >= `close_ratio` x the account rate) is at most `close_p`. A person confirms it at the gate (`kit.human`), the harness records it in its own append-only table and passes `closed=True` from then on; a reopen is a newer record. Nothing here decides a close.
6. **The next batch is drawn from moves, not leaves** (`pick()`): the largest of thousands of draws is always some leaf nobody tried, so the harness builds the moves it can really make (a promising leaf's neighbour is `known`; a first try, an untried neighbour or a new direction is `unknown`), each with `n`, the units it makes, and the posterior it stands on (a leaf's, a node's, or None: the account's own rate).
   - **Cold** (the account not warm): coverage, in the order the harness gives, each move whole, so a batch may run up to two over.
   - **Warm:** at least `explore_share` of the batch from `unknown` moves (plain Thompson draws), then batched top-two Thompson over all (the leader, or half the time the best of a fresh draw over the others); a move up to two over is taken rather than leaving the batch short.
   - **Always:** a group takes at most half a batch, rounded down (2 of 5, at least 1), and a move bigger than that only into an empty group, then alone. Two moves never both hold a key when either holds it `exclusive`; `shared` holders fit together (several moves may build on a template, one may remake it, never both in one batch). The seed comes from the moves and the account (or the harness's `seed`), so the same data gives the same batch.
7. **Twins are a clue, never proof** (`twins()`). Units of one group with the same tags whose settled rates differ by `twin_ratio` with probability `twin_p` under a weak prior, once the group has `twin_min_conv` settled conversions and each compared unit spend worth `twin_min_expected_conv`: at most three, the largest gap first, with what the harness knows to differ (`known`). A tag nobody records may hide there, or the two were bought differently; the agent proposes the tag and tests it on new units, never on the numbers that raised it.

## Thresholds

Every threshold is in `DEFAULTS`; `settings(over)` lays the harness's defaults or a client's own values (kept in that client's database) over them and refuses one that is not a value of it: an unknown key, not a finite number, a count not whole, a probability or share not strictly between 0 and 1, a `close_ratio` outside (0, 1], a `prior_shift_max` below 1, anything else not above 0.

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
| `twin_ratio` | 2 | how many times better the best twin must be |
| `twin_p` | 0.9 | the probability of that ratio before twins are flagged |
| `prior_shift_max` | 1.5 | the most a leaf's shift moves its prior mean (and 1 / it, the least) |

## What the harness supplies

- **Its plan and its partition:** what a leaf is, its parents, which units sit on it, and a stable leaf id (the video-ads harness hashes the leaf's direction, template and values).
- **Its numbers:** each unit's settled spend and conversions from one results file, and the account's total.
- **Its moves:** what each one makes (`n`), its group, its kind, the posterior it stands on, its keys, and the coverage order for a cold account.
- **Its records and its gate:** the closes and reopens a person made, the tables they live in, the shown digest a close is bound to, and how a person sees all of it.
- **Its thresholds:** its defaults and where a client's own values are kept.

## What it cannot say

- The numbers are observational: a platform steers spend to the variants it predicts will respond, so "better than the account" is a statement about these numbers, never a cause.
- At tens of variants and single-digit conversions only gaps of about 2x show; smaller ones stay invisible, and most leaves stay `testing` for weeks. Borrowing down the partition is what lets anything be said earlier.
- Calibration, held by the test: with every leaf equally good, five rounds of numbers and spend pushed to early leaders, at most 5 in 100 made leaves are ever proposed for closing (the test prints the measured rates).

Test: [`kit/tests/test_pathweights.py`](../kit/tests/test_pathweights.py).
