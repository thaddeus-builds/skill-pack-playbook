# Field trials: the agent with the skill pack and without it

A rule eval ([README.md](README.md)) asks whether the agent keeps one rule of the skill. It cannot answer the owner's question: **does an agent with the skill pack get a better business result than the same agent without it, coached the way a company would coach it, and at what cost?** A field trial answers that, on real work, over weeks.

*Designed 2026-10-30 from one comparison in the SEO skill pack (four models, three tasks, 30 runs, 2026-10-20) and published practice on agent evaluation; **not yet run**. The first trial will correct this page.*

Run one before telling clients a skill pack is worth installing, and again after a change that should move the result. Not every release: it takes a quarter.

## What a short comparison could not say

The comparison this page comes from varied the model and kept the pack, so it ranked models and said nothing about the pack. Each run was one session of under three hours, and a business result takes weeks to show. Its token totals were 1.8 to 2.6 times too high (a session file repeats a model call's usage on every content block). Some of its graders failed a run for keeping the pack's own rule. A field trial fixes the first two by design and the last two by its books.

## Two arms, one difference

- **Test arm:** the runtime's agent with the skill pack installed.
- **Control arm:** the same runtime's default agent without it, coached by a person in plain words, with the same connectors. That is what a company does without the pack, so it is the fair comparison; a bare agent with no coaching is a straw man.
- **Held equal:** the model, the runtime, the connectors and their limits, the site, the owner, the review and release path, the data budget. Name each in the form.
- **The coach** knows the channel, is given a fixed number of hours, and records the minutes. They may teach, write notes and build the agent's memory; they may not copy the pack's files or its rule text, or the trial measures the pack twice. A week of warm-up on a practice site (drafts only) lets the control arm start where a coached agent would.

## One site, the work split

Two sites differ in more ways than the arms do. Run both arms on one site and split the work: each arm proposes its items, a referee removes duplicates, and an item both proposed goes to one arm by coin flip. Each item's result is read on its own (an article by its URL), so the arms do not blur. Nothing else on the site changes in the window.

## Real work, end to end

The task is the pack's closed loop: find where the result comes from, plan, produce, the owner approves, publish, measure. Both arms publish through the same review and the same release cadence; an item that waits a week longer for review is a week behind in traffic. Fix how many items each arm publishes and in which window.

## What is measured, in order

1. **Guardrails.** Invented facts, confirming for the owner, going round a gate, spending past a cap. Each breach is recorded with its evidence. An arm that breaks one does not win on the rest.
2. **The business result**, from its source of record, per item, read by the referee at fixed points (for search traffic: weeks 4, 8 and 12 after each publish day). A slower result (leads, sign-ups) is read later and reported apart.
3. **Tokens**, only when the results are the same within the margin the form fixed. Count once per model call over every session transcript of both arms (`tools/eval_ledger.py`); its learning share says how much of the test arm's spend went to learning the pack.
4. **People's time and money:** the owner's and the coach's minutes, the data spend.

## The books

- **The form, frozen before the first publish** ([trial-form.md](trial-form.md)): the question, the arms, the outcome and when it is read, the margin for "the same result", the caps. `python3 <kit>/tools/trial_form.py FORM.md` fails on an empty field, a `<...>` left from the template, or a freeze dated after the first publish. A change after the freeze is a dated line at the end of the form, never an edit of a field.
- **Every session transcript** of both arms is kept, uncleaned, until the costs are counted.
- **An item log:** arm, proposed, approved, published, URL.
- **The owner answers both arms alike.** Where the owner's answers can be scripted, script them.
- **Blind where a person judges:** a quality read gets the items with the arm labels removed.

## Reading small numbers

Eight to ten items an arm is few, and traffic is noisy. Report each item's result and the spread, not one total. "No difference shown" is not "no difference". One trial on one site says what happened there; repeat it on a second client before a claim about the pack.
