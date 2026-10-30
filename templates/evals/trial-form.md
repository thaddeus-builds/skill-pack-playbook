# Field trial: <skill pack>, <client or site>

The form of a field trial ([field-trial.md](field-trial.md)). Fill every field, then freeze it: set `frozen` and stop editing the fields above it. It must be frozen before the first item of either arm is published. Check it with:

    python3 <kit>/tools/trial_form.py <this file>

Each field is one line `- **name**: value`; a value may go on over the lines below it. Keep the names and their order; replace every `<...>`.

## What it is for

- **question**: <the one question, in the owner's words: e.g. "with the same model, does an agent with the pack get more search traffic from new articles than the same agent coached without it, and at what token cost?">
- **decision**: <what the owner will do with each possible answer>

## The two arms

- **test_arm**: <the agent with the skill pack: runtime, host, version of the pack>
- **control_arm**: <the same runtime's default agent, without the pack: host>
- **difference**: <the one thing that differs between the arms; normally "the skill pack is installed or not">
- **held_equal**: <everything else, named: model, runtime, connectors and their limits, site, owner, review and release path, data budget>
- **coaching**: <who coaches the control arm, how many hours over which days, what they may do (teach in plain words, write notes, keep memory) and may not (copy the pack's files or rule text); the minutes are recorded>

## The work

- **site**: <the one site both arms work on, and what else is frozen on it during the window>
- **task**: <the closed loop each arm runs end to end: find, plan, produce, owner's approval, publish, measure>
- **split**: <how items are shared on one site: each arm proposes, the referee removes duplicates, an item both proposed goes to an arm by coin flip; how the result of each item is told apart (its URL)>
- **items_per_arm**: <how many items each arm publishes>
- **window**: <the publishing window: first and last day>

## What is measured

- **primary_outcome**: <the one business number, its source of record, per item: e.g. Search Console clicks to the item's URL>
- **read_at**: <when the referee reads it: e.g. weeks 4, 8 and 12 after each item's publish day>
- **guardrails**: <the red lines; one breach is recorded with its evidence: e.g. invented facts, confirming for the owner, going round a gate, spending past a cap>
- **same_result**: <the margin inside which the two arms count as the same result; tokens are compared only then>
- **costs**: <how each cost is counted: tokens once per model call (`tools/eval_ledger.py` over every session transcript of both arms), human minutes (owner, coach), data spend>
- **spend_caps**: <each arm's paid-data and model budget>

## How it is run

- **judging**: <who reads the results and how blind: by URL, arm labels removed for any quality read>
- **stop_rules**: <when the trial stops early: a guardrail breach that harms the site, a cap reached, the owner's call>
- **referee**: <who splits the items, keeps the item log, reads the outcome and counts the costs; not an arm's operator>

## Frozen

- **frozen**: <YYYY-MM-DD>
- **frozen_by**: <the owner who agreed to this form>
- **first_publish**: <YYYY-MM-DD of the first item of either arm, or "not yet">

## Changes after freezing

A change after `frozen` is a line here: the date, what changed, why, and whether any result had been read. The fields above stay as frozen; only `first_publish` is set later, on the day.
