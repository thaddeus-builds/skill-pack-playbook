# Lessons

What the source project and the skill packs after it paid for, kept here when the code that carried a lesson is gone or not yet written.

## Pulling into raw (from `kit/pull.py`, removed in kit 0.7.0)

`kit/pull.py` merged each pull into raw, planned long pulls in chunks and kept a ledger of gaps. No skill pack imported it, so it was removed (RESTRUCTURE.md, phase 5). The last version is at commit `8e13e16` (`git show 8e13e16:kit/pull.py`), with its test in `kit/tests/test_pull.py`. Before writing a pull layer again, compare dlt (incremental cursors and state) and Airbyte's Amazon Ads source, which re-pulls a lookback window (3 days by default) for numbers the platform restates.

*Paid for:* each pull replaced raw and the platform keeps only a few months; a late resumed report put older numbers back; an unreadable raw file was overwritten by one pull's rows; a long pull killed halfway started over and the quota ran out again; a run that cleared the last run's gaps lost the list a gaps-only pull needed.

The rules, each learned from one of those bugs:

- A pull is merged, never saved over the last one: rows are keyed by
  their natural key, the newer pull wins per key, and days outside this
  pull's window stay. Each row carries its own `pulledAt`, so an old row
  is never relabelled by a new pull, and an older pull that lands late (a
  resumed report) never overwrites a newer row. A key this pull no longer
  returns stays: raw never shrinks. Two rows of one pull with the same
  key are refused: the key is wrong, and merging would silently drop one.
- A raw file that cannot be read is moved aside to
  `<path>.unreadable-<stamp>` (never over an earlier one), never
  overwritten; the pull starts a new one.
- A long window is cut into chunks the platform accepts, and the plan
  (each chunk's window, request id and status) is saved after every step,
  so a killed job resumes the chunks not yet saved. If a newer pull
  landed since, a resumed chunk is requested again, never polled: an old
  report would overwrite newer rows.
- Every gap goes into an append-only ledger with its reason, and a later
  pull that gets the day appends that it was filled. `open_gaps` is what
  a gaps-only pull asks for again; no run clears the list the next one
  needs. A torn last line (a writer killed mid-line) was never a record
  and is cut off by the next write; any other broken line raises.

Its neighbours stay in the kit: `kit/raw.py` (write-once raw files), `kit/atomic.py` (the write), `kit/single_instance.py` (one run at a time) and `kit/retry.py` (`call` waits at least the quota's refill period; `GaveUp` carries the reason a gap is recorded with).

## Paid generation jobs (from adcut-harness, its first real batch, 2026-10-06)

A background job generates paid takes (a video model behind a hosted workflow), renders, checks and exports each file under
a code. The first real batch ran three times before one pair of files was usable. The fixes are in adcut-harness
(merge requests 9 and 10 and the lessons commit after them); the rules carry to any skill pack that pays per generated asset.

*Paid for:* the plan priced a re-run that the job then skipped (the codes were exported, and a code names one file); a
provider task finished and was paid, its download failed, and the resumed job refused the take as already paid, so the only
way on was to send it again; QC passed files whose generated takes had burned their own captions in and showed an invented
product, because QC reads the finished video, not the takes.

The rules:

- A plan prices only what the run will do. An item the run skips (already exported, already cached) is priced 0 and
  named as skipped, or the person approves money that is never spent and the work they wanted is not done.
- An identity that names a delivered file is never reused for a different file. A fix after delivery is a new identity
  (a new batch, new codes) with a one-command path to make it; the old ones are retired, not overwritten.
- A paid call is resumable by its provider task id. Write the id before waiting on the result; a later run that finds the
  id fetches that task instead of sending a new one, and settles the reservation the first run left, so one call is
  charged once. A task the provider failed is set aside, so the next run may send afresh.
- Look at the generated parts, not only the finished product. A generator adds what it was told not to (captions despite
  "no captions"), and draws what it was not given a picture of (a product it was told to hold). Check the raw takes, and
  warn at authoring time on instructions that need a reference the generator does not have.
- Prefer a free cover to a paid retry when the defect is in a known place (footage over the lower third), and verify it
  on a free sample render before asking a person to click.
- When a download fails, test the host before resuming: a local proxy can route one storage host to a dead exit while
  the API host works.
- A command handed to a person is one complete line they can paste, including the environment it needs.
- A detached job that vanished without its end is still told. A job writes an exit marker and a notice when it ends; one
  killed from outside writes neither. So the next listing of jobs checks each job with no marker: when its pid is gone,
  or belongs to another process now (its start time differs from the one recorded), it writes one notice once,
  "stopped without an end", with no exit code. *Seen once (2026-10-11):* the skill pack, its data and its virtualenv sat
  on an external disk that the OS unmounted at screen lock; a queued paid job died two minutes after it started and
  nobody was told. Keep all three on the internal disk ([install checklist](../templates/install-checklist.md#scheduled-tasks-and-long-jobs)).

## Design and a synthetic demo before code (from adcut-harness X45, 2026-10-13)

Before it built a map of its creative plan, with a weight on each path and a close only a person confirms, the
video-ads skill pack wrote one design page and a clickable demo of the real page, and wrote the code only after the owner
said yes. The steps, what the design page holds, the demo's guards and a checklist:
[templates/design-first.md](../templates/design-first.md).

*Paid for:* the owner confirmed four decisions in one reply, and the code was built to a picture people had already
agreed on; writing the page forced an answer to each trap the research had found before any of them was code (a tree
whose branches crossed would have counted an item twice, a comparison would have brought back a target a person had
parked, and the new append-only tables had columns that could never change once written); and the demo could be shown
to other people because it held no client data.

The rules:

- A feature an owner has to understand and steer starts with research and one page the owner decides on, not with
  code. Every ask on the page carries a recommended answer, so one reply can agree to all of them.
- An append-only table's columns are proven on a scratch copy of real data before the page fixes them: once it holds
  rows they cannot change.
- The demo is the real page, drawn by the skill pack's own renderer from a synthetic world. A hand-made mock-up shows a
  page the code will not write.
- A demo is shared only when it is synthetic (marked, `DEMO` ids) and a scan for client terms that fails closed found
  nothing in any form the page reaches a reader, its page data too; it is never written into a client's data, and a
  client's real page is never shared.
- Once the code exists, the skill pack draws the demo itself, from a synthetic fixture to the same link, so the picture
  never drifts from the code.

*Seen once* (2026-10-12 and 13), in that skill pack's ROADMAP X45.

## A guard's refinement never costs the recall it had (from the playbook's ssot write rule, kit 0.26.0, 2026-10-13)

A guard that scans code for a forbidden act (here, a skill pack writing into `ssot/`) is reviewed for false hits and
misses, and each false hit invites a refinement that makes it smarter. Each refinement is tried on the cases the last
version caught, and dropped when it misses one: the guard prefers a false hit, which one allowlist row with its reason
answers, to a miss, which nobody sees.

*Paid for:* `kit.guards.ssot.check_writes` went through four review rounds in one day, and its 0.26.0 shipped with
misses. Round one asked for a name to hold only its last binding and for `self.p` to be keyed by its class, to stop
two false hits. Round two found that each one missed writes 0.25.0 caught (a path set in an if/else branch, an
augmented assignment, a comprehension, a subclass writing what its base set); its fixes made the rules narrower still,
and round three found more misses (a call wrapped over two lines, a helper that returns the ssot dir, a mixin). Both
refinements were dropped, and round four, comparing every case with 0.25.0, found three smaller ones that had stayed
(imports looked up per module, which lost star re-exports; a stored attribute named `name`; "named for reading" matched
inside `ensure_ready`). 0.26.1 drops or narrows each; run case by case against 0.25.0, the only hits it no longer
reports are the false hits it was meant to remove.

The rules:

- A refinement that removes false hits ships with the cases the old version caught as must-hit cases in the guard's
  self-test (`_WRITE_CASES` in `kit/guards/ssot.py`, run by `writes_self_test()`); the review compares the two versions
  on them, case by case.
- When a refinement's second round of review finds new misses, drop it: put the allowlist row where the false hit was.
- A guard says which way it errs, in its docstring and in the changelog line.

*Seen once* (2026-10-13), in this playbook (PRs 88 and 89).

## A past winner the skill pack cannot say is studied for its mechanism, never copied

When a skill pack reads a client's past results ([path-weights.md](path-weights.md#past-results-a-gap-signal-never-a-weight)), the strongest single ad may win on an angle the skill pack cannot say: no template or direction of the plan states it. The tempting move is to make that ad a template or a next move. The skill pack learns the mechanism instead and proposes that.

*Why:* the owner of the video-ads skill pack (2026-10-13), on its first client's strongest past ad, which had a large share of all past conversions: if we are to learn from it, learn the underlying logic, not this specific case. Copying a winner the skill pack cannot say risks a compliance problem and overfits one ad.

The rules:

- A strong past ad that nothing in the plan can say is not a template and not a move. It is a proposal for a person to confirm.
- The proposal states a mechanism in the skill pack's own words, not the ad's: what can be separated from the claim, which is who the ad reached, how it opened, its timing, and why people converted. The ad's id and numbers are its evidence.
- A strong past ad the skill pack can say is the other case: its gap is a proposal for a template, and the mechanism is still what is studied.
- A reference ad the client hands over to be copied, one that already runs on the platform, is neither: it is the client's request, it is built faithfully (even if it is also the strongest past ad), and its risks stay warnings that a person can waive ([claim-scope waivers](../templates/claim-scope.md#waivers)). The skill pack never promotes a past ad to a template by itself; a reference is the client's choice, not a result.

No code enforces this: it is a judgement the agent makes and a person confirms, and `tests/test_docs_build.py` pins only the lesson's wording.

*Seen once* (2026-10-13), in that skill pack; its ROADMAP D64 holds the gap signal this feeds.

## An export branch never merges back (from the SEO skill pack, 2026-10-13)

A skill pack packaged for someone else gets a branch of its own. Here it was a library of use cases that takes `git archive` of a branch and allows no real client name. That branch adds what only the package needs (an agent brief, a version, a changelog, examples, `export-ignore` lines) and replaces real names with placeholders. Main merges into it; it never merges into main.

*Paid for:* the package's first branch was merged into main. Main then carried an agent brief, a version file, a changelog and placeholder folders that only the archive used; nothing in the code, tests or docs read them. They were removed the same day. The de-identification came after and stayed on the branch: merged back, it would have put placeholders where main's docs and examples name the real clients.

The rules:

- An export is a branch main merges into, never the other way. Its packaging and its de-identification live only there, and main's README says so.
- The export's scan for real names runs on the export branch, over what `git archive` ships; the list of names does not ship. The kit's `kit/tools/leak_guard.py` is the same kind of scan for a push.
- Before a packaging file lands on main, name what in the code, tests or docs reads it. A file nothing reads belongs on the export branch.

*Seen once* (2026-10-13), in the SEO skill pack: its README, and the commits "remove the fde-usecase packaging from main" and "de-identify the fde-usecase export (export branch only)". No code there enforces the direction.

## Checking the specification and the tests (from the SEO skill pack, 2026-10-15)

Two questions a skill pack owner asks and cannot answer by reading: "could another agent build this from what we wrote down?" and "do thousands of assertions guard anything?" Both can be measured in an hour or two, and the answers were not the ones the owner or the agent expected. Neither measurement belongs in CI; run them at a milestone and when the owner doubts.

*Paid for:* a spec of 40 registries, 160 stories and policies that nobody could say was enough to rebuild from; and a suite whose headline count ("6500 assertions") was twice its real number of assertion sites (loops re-run one assertion per row) and was suspected, by the owner, of guarding nothing.

### Rebuild trial: can a fresh agent rebuild a rule engine from the spec alone?

1. Pick three to five small rule engines whose answer is a pure function of an input (a classifier, a relevance rule, a de-duplication, a scorer). Give each one a stdin-to-stdout JSON contract; the contract is yours, the rules must come from the spec.
2. Make a sandbox that holds only the spec folder (the registries, the owner's intent files, the blueprint) and a small file of visible examples. No code, no tests, no git history. Say in the brief that reading anything outside the folder voids the trial, and ask the agent to say honestly whether it did.
3. Generate the hidden cases by running the real implementation (50 to 100 per engine, edge cases included: plurals, other languages, empty input, ties, hyphens). The judge compares, per engine, the agent's answers with the real ones. Keep cases and judge outside the sandbox.
4. Require a `GUESSES.md`: every place the spec was silent or ambiguous, what the agent guessed and how sure it was. This file, not the score, is the product: it is the list of what the spec lacks.
5. Fix the spec where `GUESSES.md` says, then repeat with a new agent in a clean sandbox. Rounds with one agent teach it the answers.

What it showed: a registry-driven engine (page-type rules held in one table) was rebuilt 83 of 83; a rule whose details live only in code (what "contains a term" means, which label wins when two apply, how near-duplicate keywords pool their volume) scored 40/47 and 10/16, and every miss was one of the agent's logged guesses. Write those details into the spec as rules (order of checks, boundary characters, how a tie breaks, which file a name refers to), not as examples. After the fix the second agent scored 106/106; that proves the written rules transfer, not that the spec is complete, because the author knew the answers. Completeness is shown by trying more engines.

- A rule that exists only in code is a gap in the spec, and the registries do not close it: the table holds the values, the code holds the semantics.
- Name the registry a sentence refers to ("the units column of the page-type table", not "the unit registry"): two tables held overlapping lists and the agent had to guess.
- Do not describe a quantity that the output does not depend on; the agent spent guesses on it.
- The trial costs one agent run per round and no repository change except the spec. Keep the trial's material out of the repository.

### Mutation sample: do the tests notice a change in the logic?

A mutant is a copy of the code with one small change (a comparison flipped, `and` turned into `or`, a number plus one). A test suite guards a line if some test fails on its mutant.

1. Sample, do not sweep: 40 to 50 mutants drawn at random from the modules whose behaviour matters, at most three per module, from three kinds only (comparison operator, boolean operator, integer constant). Work in scratch copies of the repository, never the working tree; restore each file after its run.
2. For each mutant run only the test files that mention the module, smallest first, and stop at the first failing file (a non-zero exit, a missing result line, zero passed, or a hang past the timeout all count as "caught").
3. Report caught over sampled, per module, and name every survivor with its line. Read the survivors: some are equivalent mutants (the change cannot alter behaviour) and some are real, usually a boundary (`>=` against `>`) that no test sits on.
4. A sample of 45 has a margin of about 12 points. Say so; do not report it as a coverage figure.

What it showed: 36 of 45 mutants were caught (80%), including 8 of 8 in the human gate, the apply gate, the auto-confirm and the human tables, which is where the owner most needed it; the survivors were boundary conditions in a status report and in a peer-recognition rule, and each was a real untested behaviour, not junk. The same session found that the suite's headline count was inflated by loops, and the number the owner should read is the count of assertion sites (about half).

- Report both numbers: assertion sites and assertion executions.
- Judge a suite by what it catches in the code that must not break (the gate, the money, the data), not by its size. Registry-shape and documentation checks are cheap and have their own value; they are not behaviour tests, and the sample does not measure them.
- A survivor is a test to write only if the behaviour is one the owner relies on; otherwise delete the doubt, not the code.

*Seen once* (2026-10-15), in the SEO skill pack: the rebuild trial is in its blueprint (`ssot/intent/blueprint.md`, section 15) and story S173; the mutation sample was run from a scratch script that is not kept, because the method is five steps and the sample must be redrawn each time.

## Research is kept, not repeated (from the video-ads skill pack, 2026-10-22)

[design-first.md](../templates/design-first.md) says to research before a feature an owner steers. It does not say where the research lives afterwards, and in a long project the same question gets looked up twice. The owner asked whether the authoritative documents had been searched, and remembered a local document that recorded their own idea.

*Paid for:* the video-ads skill pack researched budget methods, platform learning signals, fatigue and decline, hourly data and a platform's hard limits across several sessions. Until the findings had a home, each session started from the search engine, and options already looked at and rejected came back on a page the owner was asked to decide.

The rules:

- A question looked up (a platform's documents, papers, vendors) is a file in `docs/research/`, and its row in `docs/research/README.md` says the question, the date, the answer in one line and where it is used. A test fails on a file with no row and a row with no file (`tests/test_research_index.py` there).
- Every file says when it was researched, tags each claim *documented*, *vendor*, *academic*, *ours* (measured on a client's data) or *inference*, and says what it could not read (a page that did not render, a figure two official pages give differently, and which one was used).
- The index is read before anything is researched; a new finding extends the file that holds the topic.
- What the research changed lands in the design page, and the page cites the file. The page never carries the search.

*Seen once* (2026-10-22), in the video-ads skill pack: `docs/research/` has seven files and an index; its CLAUDE.md states the rule.

## The overview shows only what is decided (from the video-ads skill pack, 2026-10-22)

[system-overview.md](../templates/system-overview.md) makes the page generated, committed and checked. A generated page can still carry the wrong things: the video-ads one first listed the algorithms that had been looked at and rejected, a table of options, "can the platform tell us this?" and questions to the owner, because the registries it was drawn from held the working. The owner's instruction: the overview gives the final plan, what is not certain does not go on it, and the research goes in a folder of its own.

The rules:

- The page draws the decided plan: states, thresholds with whether the owner confirmed each, what is built and what is next. A registry row is written for the page's reader, never as notes to self.
- A test fails on a rejected option, a table of alternatives or a question to the owner appearing on the page. The test is the rule: without it the working came back within a day.
- Alternatives and open questions live in the research files and the roadmap's waiting list, each with its one home. When the page can draw something, the hand-written copy of it is deleted.
- A client's own data (its campaigns, its audit) is drawn only on request (`--market M`) and is never part of the committed copy.

*Seen once* (2026-10-22), in the video-ads skill pack (`tests/test_overview.py`).

## Advice is recorded, then read back (from the video-ads skill pack, 2026-10-22)

A skill pack that writes nothing to a platform still gives advice: a budget move, a number of creatives to ask a producer for. Advice with no memory repeats itself and cannot be judged. Two pieces were added to the video-ads skill pack, one for each kind.

- **A request is a record.** After the agent asks the producing pack for N creatives it runs one verb that lands a raw record (`import request`, never edited). The next report counts what was asked and has not started as *in production*, so the same creatives are not asked for twice; a request is matched to the first start on or after it, which also measures the lead time (the median of the requests seen, a draft until one has been seen), and a request with no start after two lead times is taken as lost and asked for again.
- **A proposal is a record, once a day.** `export allocation` lands the day's proposed moves; the next report says, for each move, `open` before seven days, then `taken` when the budget moved the proposed way by at least half the distance, else `not_taken`.

The rules:

- The record is raw, written by a verb a person or the agent runs, never by a report: reports stay read-only.
- What is read back is what was done, not what it earned. The data has no counterfactual, so "taken" is the whole claim, and every proposal carries `no_counterfactual` among its doubts.
- Every window in the matching (seven days, two lead times) is a registered draft the owner confirms, not a literal.

*Seen once* (2026-10-22), in the video-ads skill pack (`scripts/_lib/demand_log.py`, `allocation_log.py`).

## A rate learned from a stream is a flow; a threshold with no right answer is picked by a rule on a replay (from the video-ads skill pack, 2026-10-22)

Two numbers the budget logic rests on looked like constants and were not.

*The cost of a verdict.* The obvious estimate is the mean spend of the creatives that have finished. That drops the ones still running and the ones starved, so it is the cost of the winners and the fast losers: survivorship. The measured quantity is a flow: the money spent on creatives while they were still in the exploration states over the last eight weeks, divided by the verdicts reached in the same weeks, shrunk toward the lifecycle's own doubt line by `n / (n + k)` while verdicts are few. On the first client's data this gave 540 per verdict in one market and 154 in the other, from 136 and 368 verdicts; nothing was typed.

*The evidence bar of a move.* The bar a campaign's marginal return must clear before money moves has no known right value, and the owner could not judge "1.64". The rule: base value 1.0; the replay is run at each bar of a fixed grid, and the bar used is the lowest at which at most a registered share of the moves is undone within a week and enough moves were made to believe it; with no bar that qualifies, the base value stands and the report says so. It is recomputed on every run, so it follows the data. It picked 1.5 in one market and left the base in the other, where about a fifth of the moves still flipped; that is shown as it is, not tuned.

The rules:

- A quantity estimated from outcomes that arrive over time counts the money still in flight; a mean of the finished is named for what it is.
- A threshold nobody can state is not guessed and not asked of the owner: a fixed rule over a replay of the real data picks it, the base value is the fallback, and the choice's source (`calibrated` or `base`) is in the output.
- A replay shows what a rule does (how often it moves, whether it flips), never what it would have earned.

*Seen once* (2026-10-22), in the video-ads skill pack (`docs/creative-demand.md`, `docs/allocation.md`).

## Retiring a subsystem: map it, prove only it went, keep what another pack reads (from the video-ads skill pack, 2026-10-23)

The video-ads skill pack carried a Meta-era loop (a staged read, a launch sheet, a steering queue, a script pre-check) that its newer layers had replaced. The owner decided to retire it after the agent ran each of its verbs on a copy of the client's real data: two refused (no deliveries), one had no scripts, two were empty, the queue held nothing, and four ran but said their money needs inputs the client does not give. The removal was one merge request, about 10,000 lines out.

The steps that held:

- **Ask with evidence.** Run every verb of the old loop on a copy of real data and show which return anything.
- **Map before deleting.** Build the import graph from the verbs that stay; a module reachable only from the retired verbs goes. One did not: the new audit page took its page helpers from the retired page module, so they were moved to a small shared module first.
- **Let the guards list the rest, in this order:** the verb table and its help, the forwarding lists in the CLI test, the registries (index rows, story checks, stage rows), the message codes nothing emits any more (delete them with a script, not by hand), the rendered `.gitattributes`, and the README and SKILL text that tests pin by wording. Owner files are not edited by the agent: their `.agent.tsv` siblings say *retired* with the owner's answer, and an owner row that points at deleted code is named as a question.
- **The golden diff proves "only this went".** Removed cases are failures by design, so the merge request quotes the list: the removed cases, the verb table, the stage checks (10 to 2), nothing else.
- **Keep what another pack reads, and say so.** The generic outside-orders documents stayed, and what only the retired code used (a roster import, five cache tables, a schema change) became its own roadmap row rather than widening the merge request.

*Seen once* (2026-10-23), in the video-ads skill pack (its ROADMAP D102 and X124).

## The interpreter on the machine is not CI's (from the video-ads skill pack, 2026-10-22)

A pipeline failed on the first merge request of a milestone with every test green locally: `skill-pack.toml` held an inline table across several lines, which is TOML 1.1; the developer's Python 3.15 reads it, CI's 3.12 refuses it.

The rules:

- Run the whole suite on the interpreter CI uses before pushing (`python3.12 tests/run.py`), and say it in the agent instructions; "tests pass" with a newer local Python proves less than it appears to.
- A change that depends on the interpreter, the OS or a schema waits for its own merge request's pipeline before the agent merges, even when the rest of the project's merges need none.

*Seen once* (2026-10-22), in the video-ads skill pack (merge request 79); its CLAUDE.md "Tests" invariant carries the rule.

## Ask another pack for nothing you can do with what it already has (from the video-ads skill pack, 2026-10-22)

The video-ads skill pack needed a batch of new creatives to run together as one ad group, and its first design asked the producing pack (adcut) for a `move` column, a forced new batch code and an incomplete-handoff warning. The owner's reminder, 2026-10-22: the producer's core job is making videos, not managing ads; if the consumer can do it, the consumer does it. On a second look nothing was needed: the producer's `variants spawn` already took a test-group name, and `variants handoff` already listed what it had not exported, so the consuming pack's agent passes a name no group uses and builds the ad group only when that list is empty. The group is read from the ad set id of the platform's own export, so the contract file got no new column either.

The rules:

- Before asking another pack for a change, list what its CLI and its documents already give and what the consumer's agent can do with them. A change is asked only for what is left, and the ask says what was tried.
- A unit the platform's export already names (here the ad set) is not added to a contract file: a column in the contract is a promise both packs keep.
- When the producer's answer shows it cannot do a thing (here it could not copy a creative under a new code, and the report ledger refuses one code on the same days twice), the design changes on the consumer's side; the limit is recorded in `docs/research/` so the question is not asked again.

*Seen once* (2026-10-22), in the video-ads skill pack (its ROADMAP R77, R78 and D96; `docs/research/adcut-creative-space.md`).

## A rule that overrides another stage's state is tested at the override (from the video-ads skill pack, 2026-10-22)

A new rule decided which wallet pays a creative from its ad group's state, and it overwrote the creative's own wallet. Its tests covered the group's judging function alone and one presence check on the report. Every green run was true and the bug was still there: a brand-new creative added to an old, judged ad group was paid from the performance wallet, so the exploration wallet read zero on the first client's data (3,819 and 2,116 under the old rule) and the count of performance creatives went from 24 to 134. Nobody saw it until a review of the whole milestone's diff, in one sitting, found ten issues, this one first.

The rules:

- When a rule replaces or overrides a value another stage owns, the combination is a pure function with its own cases (here `pay(own, group)`): no verdict yet in a judged group stays exploration, a parked creative is paid by nobody, a stopped group pays nobody. An override that can only hold money back is easier to believe than one that can also grant it.
- A replay on real data before and after, with both numbers quoted, is what shows an override over-reaching; a unit test of the new rule alone cannot.
- A milestone closes with a review of its whole diff against the base, not only of each item; each finding is fixed in a commit of its own with the replay quoted, and the cleanups run under the golden diff in strict mode.

*Seen once* (2026-10-22), in the video-ads skill pack (its ROADMAP D97; commits "Ad group wallet can only hold money back" and the refactor after it).

## A fact the client has not given is a typed optional field and a rule that says it does not know (from the video-ads skill pack, 2026-10-21)

[rules.md](rules.md) says trust lives in the data: values are pending or confirmed, every rule reads confirmed first. Three times the video-ads skill pack was stopped by a number only the client knows: the rate between two currencies, the lowest daily budget an ad group may have, the target return. Each time the first move was a question to the owner, and the owner's answer was the same: build the field and let the client fill it; a number given now would not change the logic.

The rules:

- The fact gets a registry row (`ssot/fact_keys.tsv`): a type, a unit, bounds, optional, and a sentence for the person who fills it. Nothing reads a default for it.
- The rule that needs it reads it and, when it is empty, says so in the output (`limits: {min: null, max: null}`, a coded warning), and does what it can without it: the request for creatives is bound by money alone, a sum across two currencies is refused (`report_currency_mix`) until a rate is confirmed.
- A public lookup may suggest a value (`fx lookup`), never store it. The rate in force is what a person typed and confirmed.
- The roadmap row is a waiting item that says "structure built; the client fills; nothing for the owner to decide", so the owner's list holds only decisions.

*Seen once* (2026-10-21 and 22), in the video-ads skill pack (ROADMAP W34, W20 to W29, X120).

## Reading a client's software by its screens: the CLI first, the browser for what it lacks, nothing saved (from the video-ads skill pack, 2026-10-14 and 23)

[workbook-and-browser-ops.md](workbook-and-browser-ops.md) proposes a guarded browser for a platform with no API access. The video-ads skill pack's practice before that module exists, on Emma Sleep's Smartly:

- Fresh numbers came from the pack's own pull (a saved report's read-only export), not from the screens. The browser was used for the one question the export could not answer: what the report builder offers (an hour dimension, a learning-phase column, an ad set's bid and targeting). The answer: an `Hour (S2S)` dimension of unknown meaning, bid and budget columns, no learning column, targeting only as an audience segment.
- The session was the owner's, already signed in; the agent signed nothing in and entered no credential. Each picker was opened, read and closed with "discard changes"; the Save button stayed greyed out; nothing was downloaded. A control the session's guard refused (the access-tokens tab of an export dialog, 2026-10-14) was not gone around.
- What was seen is written down the same day, with the date, in a research file, and the roadmap rows it answers are updated: a screen read that lives only in a chat is looked up again.
- A search box in such a UI can answer late: an empty list straight after typing proves nothing; wait and look again before concluding something is absent.

*Seen twice* (2026-10-14 and 23), in the video-ads skill pack: `workspace/intake/2026-10-14-smartly-inventory.md` in its client folder, and `docs/research/time-of-day-and-video-metrics.md` ("Smartly's report builder").

## Ecommerce SEO Skill Pack, first non-manufacturer client (2026-10)

The SEO harness (renamed "skill pack": the repository `ecommerce-seo-skill-pack`, on the owner's GitLab;
ids below are its story ids, `S..`) was calibrated on B2B manufacturers. Its first software client closed a full loop
in one day: a blog page written, checked, reviewed and sent as a merge request into the client's protected site
repository. Nine lessons came out of it. Each was checked on 2026-10-15 against that repository, its client folder and its git history; where the code is not
on its `main` yet, the entry says so. Some sharpen a rule above; the entry names the rule.

1. **A check ships with a known-bad input it must refuse.** Sharpens [Building with many agents](operating.md#building-with-many-agents)
   rule 2, from tests to the checks that gate a generated artifact. *Paid for:* the first merge request carried a leaked
   template variable (`\g<1>`) in its table of contents, which also lost its list wrapper. Every check passed, because
   none of them had ever been shown to fail on such a page. An independent review found it. Where: `markup_leaks` in `scripts/_lib/pagetext.py`, registry row `ph10` in `ssot/placeholder_patterns.tsv`,
   the "generator leak" case in `tests/test_nextjs_static.py` (S163).
2. **Judge a regression against the baseline, on the same copy.** Run each of the site's own checks on its clean `main`
   and on `main` plus the change; only a check that passes on `main` and fails with the change counts. Anything red
   on both is reported as `baseline`, not as the change's fault. *Paid for:* the site's own `test-china-legal-links.mjs`
   is red on its clean `main` (2 of 5 tests); read as a verdict, it would blame every page for a failure no page
   caused. Where: the client's pre-flight, `content/preflight/preflight.py` in the client folder (not in the skill pack
   repository), and its description in `docs/nextjs-static-adapter.md` ("pre-flight"; S163).
3. **A check reads the representation the consumer sees, not the one that is easiest to scan.** *Paid for:* the
   placeholder scan read the page through `html_text`, which drops `<1>` as a tag; a browser shows `\g<1>` as visible
   text. The leak was invisible to the scan, and the local preview was looked at on a narrow window, where that column
   is hidden. Now the leak scan reads the markup with its tags kept, and the adapter note tells builders to preview at desktop width,
   not only on a phone.
   Where: `markup_leaks` and the `html_text` docstring in `scripts/_lib/pagetext.py` (S163).
4. **A rule that depends on the client's kind is a column of a registry row read by one function, never a branch.**
   Extends [Registries](rules.md#registries-one-place-per-value) rules 6 and 9: the row also says whom it applies to.
   *Paid for:* the client was a software company, and its missing-materials list still asked for a catalogue, data
   sheets, factory photos and SKU parameters, which it cannot supply. S172 added an applies-to column to the
   prerequisites registry, written like the one the slot registry already had; the list for that client went from 7
   items to 5 with no new branch on the business model in code. The same fault turned up in a second place the same day
   (S174): an article still asked a software client for test results and factory media. It closed with three more
   applies-to values on existing slot rows and no code.
   Where: `ssot/intent/prerequisites.tsv` (the applies-to column), `applies` in `scripts/_lib/compute_common.py`, read by
   `compute_status.py` and `compute_brief.py` (S172).
5. **Every read verb that can return more than a few kilobytes has narrowing flags and a `--summary`; its default output
   size is a quality measure.** Extends [Teach the agent from `--help`](rules.md#data-layers-and-their-guards).
   *Paid for:* on the real client the gap report was 830 KB, opportunities 497 KB, inventory 439 KB, competitors 301 KB,
   and the status report 61 KB just to learn the next command. One read cost the agent hundreds of thousands of tokens, so it
   filtered each report with a throwaway script, outside the verbs. S179 added `--only`, `--limit`,
   `--summary` and per-report filters. The default output stayed byte for byte the same, which the refactor diff
   showed, and a narrowed run adds a `narrowed` key saying what it cut. Where: `narrow` in
   `scripts/_lib/compute_common.py` (S179).
6. **Writing into a repository whose main branch is protected is a work branch plus a merge request, never the base
   branch, and a review cycle needs an amend path from the first slice.** Applies [Writing into someone else's
   system](rules.md#writing-into-someone-elses-system) to a forge. *Paid for:* the adapter pushes only new branches
   and never reuses a name, so when review sent the first merge request back with findings, the fix could only be a
   new branch, a new request, and a person closing the old one. The note proposes adding a fast-forward commit to the
   item's own open branch while its base is unchanged; S184 (an open merge request when this was written)
   builds it, and the amend must be a gated write bound to the new bytes like any other. Where: `push_branch` in `scripts/_lib/nextjs_static.py`;
   `docs/nextjs-static-adapter.md` ("What the review of the first merge request found") (S163).
7. **Prove the door is open before asking the owner for a one-time code.** *Paid for:* of the 7 archived write runs of
   that first day, 3 ended in a refused push (HTTP 403, then a token without the push permission). Each had cost the
   owner a relayed code and a sentence of approval for a write that could not succeed. The read of the remote worked
   all along, so the adapter's `ls-remote` checks proved nothing about the right to push. A push preflight is in S184 (open when this was written);
   nothing on `main` tried the right to push before. Sharpens [Human-in-the-loop](rules.md#human-in-the-loop-rules) rule 7 (budget the owner's attention). Where: the
   refusal is `nextjs_push_rejected` in `push_branch` (`scripts/_lib/nextjs_static.py`); the runs are under
   `raw/apply/nextjs-static/` in that client's workspace (S163).
8. **Allocate a shared id where the writes meet, not where each session claims it.** Sharpens "Only the coordinator
   allocates story ids" in [roadmap.md](roadmap.md#who-works-where) and [Registries](rules.md#registries-one-place-per-value)
   rule 11. *Paid for:* with many sessions in parallel, picking "the next free id" on a branch raced even after the
   picker learned to read every branch and merge request. In the two days to 2026-10-15 the skill pack's `main` took at
   least 8 fix-up commits that renumbered a story ("S180: renumber from S179 (taken by !196 and !197)", "S172 was taken
   twice"); `git log origin/main --since='2026-10-14' --oneline | grep -i -E 'renumber|was taken'` lists them. Where:
   `tools/story_next.py` (its docstring admits two simultaneous runs can still collide) and the parallel-sessions
   paragraph of the skill pack's `CLAUDE.md`. An allocation at merge is not built.
9. **A copy of a shared file set carries a stamp naming its source, and the doctor treats a missing stamp as the
   finding.** Extends the vendored-copy rule in the README ("What the kit guarantees") to client folders. *Paid for:*
   the doctor checked a client folder against the template only when the folder held `client.env`. The client's
   folder, made before the template existed, had none, so the doctor said ok while its launcher still read an
   old variable and lacked the guard that blocks the four human-confirm commands (S180). The skill pack's own
   main checkout showed the same class: found on a side branch with uncommitted work from 2026-10-08, more than 400 commits
   behind `main`, until it was fast-forwarded on 2026-10-15. Where: `client_folder` and `doctor` in `scripts/seo.py`,
   message code `client_folder_legacy`, `templates/client/` (S45, S180).
