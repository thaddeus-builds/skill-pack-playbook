# Lessons

What the source project and the harnesses after it paid for, kept here when the code that carried a lesson is gone or not yet written.

## Pulling into raw (from `kit/pull.py`, removed in kit 0.7.0)

`kit/pull.py` merged each pull into raw, planned long pulls in chunks and kept a ledger of gaps. No harness imported it, so it was removed (RESTRUCTURE.md, phase 5). The last version is at commit `8e13e16` (`git show 8e13e16:kit/pull.py`), with its test in `kit/tests/test_pull.py`. Before writing a pull layer again, compare dlt (incremental cursors and state) and Airbyte's Amazon Ads source, which re-pulls a lookback window (3 days by default) for numbers the platform restates.

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
(merge requests 9 and 10 and the lessons commit after them); the rules carry to any harness that pays per generated asset.

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
  "stopped without an end", with no exit code. *Seen once (2026-10-11):* the harness, its data and its virtualenv sat
  on an external disk that the OS unmounted at screen lock; a queued paid job died two minutes after it started and
  nobody was told. Keep all three on the internal disk ([install checklist](../templates/install-checklist.md#scheduled-tasks-and-long-jobs)).

## Design and a synthetic demo before code (from adcut-harness X45, 2026-10-13)

Before it built a map of its creative plan, with a weight on each path and a close only a person confirms, the
video-ads harness wrote one design page and a clickable demo of the real page, and wrote the code only after the owner
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
- The demo is the real page, drawn by the harness's own renderer from a synthetic world. A hand-made mock-up shows a
  page the code will not write.
- A demo is shared only when it is synthetic (marked, `DEMO` ids) and a scan for client terms that fails closed found
  nothing in any form the page reaches a reader, its page data too; it is never written into a client's data, and a
  client's real page is never shared.
- Once the code exists, the harness draws the demo itself, from a synthetic fixture to the same link, so the picture
  never drifts from the code.

*Seen once* (2026-10-12 and 13), in that harness's ROADMAP X45.

## A guard's refinement never costs the recall it had (from the playbook's ssot write rule, kit 0.26.0, 2026-10-13)

A guard that scans code for a forbidden act (here, a harness writing into `ssot/`) is reviewed for false hits and
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

## A past winner the harness cannot say is studied for its mechanism, never copied

When a harness reads a client's past results ([path-weights.md](path-weights.md#past-results-a-gap-signal-never-a-weight)), the strongest single ad may win on an angle the harness cannot say: no template or direction of the plan states it. The tempting move is to make that ad a template or a next move. The harness learns the mechanism instead and proposes that.

*Why:* the owner of the video-ads harness (2026-10-13), on its first client's strongest past ad, which had a large share of all past conversions: if we are to learn from it, learn the underlying logic, not this specific case. Copying a winner the harness cannot say risks a compliance problem and overfits one ad.

The rules:

- A strong past ad that nothing in the plan can say is not a template and not a move. It is a proposal for a person to confirm.
- The proposal states a mechanism in the harness's own words, not the ad's: what can be separated from the claim, which is who the ad reached, how it opened, its timing, and why people converted. The ad's id and numbers are its evidence.
- A strong past ad the harness can say is the other case: its gap is a proposal for a template, and the mechanism is still what is studied.
- A reference ad the client hands over to be copied, one that already runs on the platform, is neither: it is the client's request, it is built faithfully (even if it is also the strongest past ad), and its risks stay warnings that a person can waive ([claim-scope waivers](../templates/claim-scope.md#waivers)). The harness never promotes a past ad to a template by itself; a reference is the client's choice, not a result.

No code enforces this: it is a judgement the agent makes and a person confirms, and `tests/test_docs_build.py` pins only the lesson's wording.

*Seen once* (2026-10-13), in that harness; its ROADMAP D64 holds the gap signal this feeds.

## An export branch never merges back (from the SEO harness, 2026-10-13)

A harness packaged for someone else gets a branch of its own. Here it was a library of use cases that takes `git archive` of a branch and allows no real client name. That branch adds what only the package needs (an agent brief, a version, a changelog, examples, `export-ignore` lines) and replaces real names with placeholders. Main merges into it; it never merges into main.

*Paid for:* the package's first branch was merged into main. Main then carried an agent brief, a version file, a changelog and placeholder folders that only the archive used; nothing in the code, tests or docs read them. They were removed the same day. The de-identification came after and stayed on the branch: merged back, it would have put placeholders where main's docs and examples name the real clients.

The rules:

- An export is a branch main merges into, never the other way. Its packaging and its de-identification live only there, and main's README says so.
- The export's scan for real names runs on the export branch, over what `git archive` ships; the list of names does not ship. The kit's `kit/tools/leak_guard.py` is the same kind of scan for a push.
- Before a packaging file lands on main, name what in the code, tests or docs reads it. A file nothing reads belongs on the export branch.

*Seen once* (2026-10-13), in the SEO harness: its README, and the commits "remove the fde-usecase packaging from main" and "de-identify the fde-usecase export (export branch only)". No code there enforces the direction.

## Checking the specification and the tests (from the SEO skill pack, 2026-10-15)

Two questions a harness owner asks and cannot answer by reading: "could another agent build this from what we wrote down?" and "do thousands of assertions guard anything?" Both can be measured in an hour or two, and the answers were not the ones the owner or the agent expected. Neither measurement belongs in CI; run them at a milestone and when the owner doubts.

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
