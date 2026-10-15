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
   repository), and its description in `docs/nextjs-static-adapter.md` ("pre-flight"; S163, on branch
   `claude/s163-preflight-lessons` when this was written).
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
   items to 5 with no new branch on the business model in code. The same fault turned up in a second registry the same day
   (S174, proposed): the page-type modules still require a spec table and factory media for every article.
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
   item's own open branch while its base is unchanged; that is still not built, and the amend must be a gated write
   bound to the new bytes like any other. Where: `push_branch` in `scripts/_lib/nextjs_static.py`;
   `docs/nextjs-static-adapter.md` ("What the review of the first merge request found") (S163).
7. **Prove the door is open before asking the owner for a one-time code.** *Paid for:* of the 7 archived write runs of
   that first day, 3 ended in a refused push (HTTP 403, then a token without the push permission). Each had cost the
   owner a relayed code and a sentence of approval for a write that could not succeed. The read of the remote worked
   all along, so the adapter's `ls-remote` checks proved nothing about the right to push. No access probe is built
   yet. Sharpens [Human-in-the-loop](rules.md#human-in-the-loop-rules) rule 7 (budget the owner's attention). Where: the
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
