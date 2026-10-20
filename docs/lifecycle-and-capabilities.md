# Lifecycle and capabilities: one flow every client shares

A skill pack for lead handling meets a new client whose data goes from somewhere to somewhere else, and no two clients agree. This chapter keeps what one skill pack, built from an existing sales system, learned about holding that variety in data: a fixed lifecycle, a catalog of what each stage can do, and each client's route through them as rows. It also keeps the smaller things the same build paid for: a profile stage that comes before everything, rules moved out of code with a test that proves nothing changed, a provider that may be absent, and the proofs that keep a write path off.

*Seen once:* the SDR skill pack, here called **the worked example**, built from an older TypeScript/SQLite system, here called **the source system**, between 2026-10-19 and 2026-10-20. Its decisions R18 to R31 hold the owner's words. Paths that start with `example:` are in the worked example's repository, not in this one; every other path is in this repository, and `tests/test_docs_build.py` checks that it exists. No client data is in this chapter: no names, no addresses, no ids of people.

The playbook has no kit module for this. A module needs two skill packs that use it ([the admission rule](kit-and-tools.md#the-admission-rule)), and only one has. What follows is a pattern with a worked example, not code to vendor.

*Not yet proven:* the worked example ran on synthetic data only. The owner said so and asked for no reliance on a live interface (its R21). Nothing here has met a real client's leads.

## The owner's design

The design is in two quotes from the owner. The first is all of it:

> 我们做的是 skill pack，具体每一个客户数据的流程从哪儿到哪儿都是不确定的。所以 … 首先应该有一个抽象的最统一的流程，是持久不变的，然后给出每一个节点的能力，再让 AI Agent 自己判断下一步该做什么。

*In English:* what we build is a skill pack, and where each client's data goes from and to is uncertain. So first there should be one abstract, most unified flow that stays fixed. Then give each node its capabilities. Then let the AI agent judge what to do next. (`example:docs/ROADMAP.md`, R18)

> Inbound 和 outbound 对于线索的处理 … 是一样的 … 区别在于 … inbound 是客户主动找过来 … outbound 本质上是 cold call。

*In English:* inbound and outbound handle a lead the same way. The difference is that inbound is the customer coming to us, and outbound is at heart a cold call. (R19)

The design has three layers, and each is data:

| Layer | What it is | Who changes it | Where it lives in the worked example |
| --- | --- | --- | --- |
| Lifecycle | The stages every client shares. Fixed. | The playbook and the skill pack's builder, rarely | `example:ssot/lifecycle.tsv` |
| Capability catalog | What each stage can do, with its status | The skill pack, when a capability is built | `example:ssot/capabilities.tsv` |
| Wiring | One client's route: which capabilities, in which order, who acts, what leaves the company, where a person decides | The client's own file; one row per step | `example:ssot/dataflow.tsv` |

1. **There is one lifecycle, and inbound and outbound are the same one.** They differ in *origin* (does the other side want to be contacted: yes for inbound, not known for outbound) and in what the **engage** stage means. For inbound, engage only answers a contact the other side already asked for (a receipt, a reply). For outbound, engage is the first contact: we speak first, maybe on several channels. Every other stage is the same or nearly so, and the table below says where it differs. Other sources (a referral, a list import, a trade show, a phone call) are further values of origin, not further lifecycles.
2. **The catalog names what a stage can do, whether or not a client uses it.** A client's workflow may leave a capability out. The worked example's owner kept a sheet writer, a website-admin scraper, a thank-you email and an outreach email in the catalog and took them out of the example client's route (its R22). The capability stays real; the client does not use it.
3. **A client's route is data, never code.** A step names catalog capabilities by id. A new client is a new file of rows, and a capability the catalog lacks is a catalog row first.
4. **The agent proposes the next step among the catalog's capabilities, and the program checks the proposal.** The check is what the program already knows how to ask: are the prerequisite fields present on the lead, is the capability enabled for this client, does the write stay under its ceiling ([autonomy](autonomy.md), rule 2), is there budget left. The agent never names a capability that is not in the catalog, and never raises its own ceiling.

   The owner's words stop at "let the agent judge what to do next". The four checks are this chapter's reading of what that needs, taken from the rules the playbook already has ([rule 12](rules.md#human-in-the-loop-rules) and the [write rules](rules.md#writing-into-someone-elses-system)).

## What is built, and what is only a design

The worked example shows both halves, and they are not at the same stage.

| Piece | State | Held by |
| --- | --- | --- |
| The lifecycle table | Built | `example:tests/test_pipeline_page.py` |
| The capability catalog (32 rows: 21 `ported`, 2 `built`, 9 `todo`) | Built | the same test |
| One client's wiring (two lanes, 9 steps) | Built | the same test: it may name only catalog ids |
| The pipeline page generated from the three tables | Built, with `--check` | the same test, which CI runs |
| Guards on the write ceiling, the opt-in, the approvals | Built, all off | `example:tests/test_write_path.py` |
| **The agent proposing the next step among catalog capabilities, and the program checking it** | **Design only** | nothing |

*Not yet proven:* the last row. No code reads the catalog to offer an agent its choices, and none checks a proposed step against prerequisite fields, the client's enabled list, the ceiling or a budget. The worked example's wiring is read by people and by the page, not by a runner. What exists are the parts the check would call: the ceiling per write kind is checked at the write ([autonomy](autonomy.md)); budget is a catalog row with status `todo`. Do not describe the catalog as something that drives the agent until a test shows a proposal refused for each of the four reasons.

## The stages and the capability catalog

Eleven stages, numbered from 0. The stage ids are lowercase words and the first part of every capability id.

| # | Stage | What it does | Inbound | Outbound | Produces |
| --- | --- | --- | --- | --- | --- |
| 0 | `profile` | Work out who to look for: the salespeople's descriptions become a target customer profile with concrete requirements | Same | Same | The profile: hard requirements, pluses, exclusions, countries, company size |
| 1 | `acquire` | The lead enters the system | The other side came to us, typed their own contact details, and wants to be contacted | We go looking; they may not know us or care | A raw lead with its source and the source's type |
| 2 | `identify` | New or known? Already a company in the CRM? | Same | Same | One identity per lead; a duplicate joins the existing one |
| 3 | `enrich` | Company identity, contact details, public information | Same | Same, and the contact details often have to be found | The enriched company and contact |
| 4 | `judge` | Classify, score, decide whether it is worth going on | Same | Same, usually stricter: a lead that fails ends here | Type, score, qualified or not |
| 5 | `assign` | Decide who follows the lead | Same | Same | An owner |
| 6 | `engage` | Contact the other side | Only answers a contact they already asked for | The first contact, on one or more channels | One contact sent |
| 7 | `respond` | Read the reply and judge the interest | Same | Same | The reply's intent and the suggested next step |
| 8 | `handoff` | Pass it to a person or another system | Same | Same; an interested reply becomes an inbound lead | A record or notice in their system |
| 9 | `nurture` | Stay in touch until they want to meet sales | Not built | Not built | (a to-do; the source system had none) |
| 10 | `learn` | Outcomes flow back to scoring and sources | Not built | Not built | (a to-do) |

The owner said nurture should be a to-do if the old code did it poorly (its R20). Learn is a to-do too: the source system had only blacklist suggestions and a CRM reconcile. A stage with no capability built still has a catalog row with status `todo`, so the gap is visible.

Six more rows belong to no stage, because every stage uses them. They are in the catalog with stage `cross` and an id that starts `x.`:

| Row | What it is | State in the worked example |
| --- | --- | --- |
| `x.store` | The one source of state; every stage writes back to it | ported |
| `x.review` | An error or doubt stops the lead until a person handles it | ported |
| `x.gate` | Every write out of the company goes through the tiered approval; off by default | todo (see below) |
| `x.compliance` | Opt-out, a do-not-contact list, data retention | todo |
| `x.budget` | A cost ceiling for searches, scrapes and AI calls | todo |
| `x.audit` | A trace per step; stage counts and data freshness | todo |

The `x.gate` row says `todo` while the write path exists, all off. The status column is kept by hand and no test relates it to the code, so it is out of date there. Treat a status as a claim a person made on a date.

**The columns.** `lifecycle.tsv`: `id`, `order`, `name_zh`, `does_zh`, `inbound_zh`, `outbound_zh`, `produces`. `capabilities.tsv`: `id`, `stage`, `name_zh`, `does_zh`, `applies_to` (`inbound`, `outbound` or `both`), `uses_ai`, `outside_effect` (what leaves the company, or `—`), `status`, `source_ref` (where the old system did it, or why it is not built). The `_zh` columns are in the owner's language because the owner reads the page (its R14); ids and column names stay English.

5. **`status` is `ported`, `built` or `todo`.** `ported` is a capability carried over from the source system with its tests; `built` is new in the skill pack (the profile stage's first two rows); `todo` is named and not done. A fourth word is a failing test.
6. **A wiring row may name only catalog capabilities.** This is the guard that keeps the three layers one thing. `example:tests/test_pipeline_page.py` has the checks to copy:
   - a capability id is never reused;
   - every capability belongs to a known stage, and its id starts with that stage (`cross` has the prefix `x`);
   - every stage has at least one capability, built or to do;
   - every wiring step names only ids in the catalog, and at least one;
   - inbound and outbound differ in `engage`.

   *Seen once:* the first page (v1) was one flat table of steps. The layered version, three tables and the checks above, replaced it the same day, after the owner's R18. Checking the names across the tables took one test.

## The pipeline page

The owner reads a page, not the tables. The worked example generates it.

7. **A page generated from tables is checked for staleness in CI.** `example:scripts/render_pipeline.py` writes `example:docs/pipeline/index.html` from the three tables and the write-kind registry. `--check` exits 1 when the committed page differs from a fresh render, and the test tries both a stale and a current copy; CI runs the test. Without it the page and the tables drift; with it, a changed row fails the pipeline until the page is rendered again.
8. **The committed page is self-contained and holds no live section.** One file, no link, script or remote file, in both colour themes, with a gutter that respects the phone's safe area. The test greps for `http`, `<script`, `<link` and `src=`. A `--fragment` mode gives the same page without the document wrapper, for pasting into a hosted page.
9. **A live section shows counts, freshness and trust, and nothing about a lead.** `--live OUT` adds counts per stage for the two pipelines, how many days ago each source was last pulled, how many decisions are confirmed and how many wait, and the write switch with the approvals waiting. It is never committed. The test feeds the renderer a synthetic status with extra keys and checks that only the two pipelines are drawn. It then reads every company name and email from the fixture database and fails if one appears in the rendered live page.

   *Not yet proven:* that last check runs only `if fixture.is_file()`. When the fixture is missing, it skips without a word. Make a missing fixture a failure (see [the first lesson](#small-lessons-with-what-each-cost)).

The page uses none of the playbook's `pages` pack ([page-style](page-style.md)); the worked example vendors only the `data` pack. Whether it should is open.

## The profile stage

The owner added this stage after the first lifecycle was drawn: before judging a lead, say who the client's salespeople want (its R29: ingest what sales provide to plan the target customer profile and its concrete requirements).

10. **Briefs are kept raw and write-once.** `example:scripts/import_brief.py` stores a file a salesperson gave (a transcript, notes, a screenshot of a scoring sheet, a spreadsheet) as it came, under a name made from its content. The same file twice leaves one file; nothing is replaced; a file over a size limit is a coded refusal. Briefs hold client words, so they live under the data folder, never in the repository, and the tests use a synthetic brief.
11. **The profile is pending data with a quote behind every requirement.** The agent reads the briefs and writes a profile as a decision (`icp_profile <id> spec`), pending, with the kept file's name as its source. Each requirement carries the quote and where it is. A requirement with no quote is not written; a range stays a range; when two salespeople disagree the agent shows both quotes and writes neither (`example:references/workflows.md`, section 5). It is [Stage 0's](stages.md#stage-0-client-meetings-are-the-first-input) rule, applied to the client's sales team instead of a meeting.
12. **A shape check at export.** `example:scripts/_lib/profile.py` checks the confirmed JSON: a name, the client type it scores, at least one hard requirement, exclusions (may be empty), countries as two-letter codes, a company size with a minimum or a maximum that do not cross, at least one `{brief, quote}`, and a rubric whose items add up to no more than their dimension. `example:scripts/export_profile.py` writes `exports/customer-profiles.json` only from confirmed values and writes nothing, listing every problem, if one profile is the wrong shape. The same module is the shape the agent follows when it writes the pending value.
13. **The judge step reads only confirmed profiles.** A pending profile is not exported (`export_profile_incomplete`), so it cannot reach scoring. `example:tests/test_profile.py` shows this on a synthetic client: a pending profile is not exported; a confirmed one is, equal to what was confirmed; a confirmed profile of the wrong shape is refused whole.

*Not yet proven:* nothing scores a lead against the profile. The judge step is still the source system's prompts with its criteria written in them. Wiring the exported file into them is a change to the TypeScript chain behind its own test, and the owner put it after the first release (its X27, R31). Until then the profile is a confirmed document that no stage reads. The first profile (one kind of European distributor) was drafted from interviews and a scoring sheet, and the owner accepted the draft as written (R31); it is to become a pending decision on the host and be confirmed there through the gate.

## Rules as data, with a parity test

A client's assignment rules were a tree of conditions in code: which country, which company name, which client type, which product line, which person or pool, which CRM pool. Rules that a client changes belong in data a person confirms. Moving them is a change in what decides, so it needs a proof that nothing else changed.

14. **Ordered rules in a data file; first match wins; one fallback.** `example:ts/src/db-cli/sales-rules.ts` reads a JSON file of `version`, a directory of people, pools, CRM pools, ordered `rules` (each with optional conditions on company text, country, client type and products, an `assign` to a person or a pool, and a CRM pool) and one `fallback`. The Python side writes that file from confirmed decisions (`example:scripts/export_sales_rules.py`) and refuses, with the full list, if a rule names a person, a pool or a CRM pool nobody confirmed.
15. **A switch selects the data. Without it, the old code decides, unchanged.** The switch is an environment variable naming the file. Unset, the built-in tree runs as before. Set to a file that is not a rules file, the run fails loudly. A switch is a rollback that needs no deploy.
16. **A parity test writes the old tree out as a rules file and compares both over every input.** `example:ts/tests/typescript/sales-rules-parity.test.ts` holds a fixture that is the built-in tree written as data. For each case it resets the round-robin state, asks the built-in rules, resets again, asks the file, and requires equal answers. The cases are every country the file names plus unknown ones, three client types and five product combinations, over 1000 in all (the test asserts it), then the company override, then a sequence of seven leads to show the round-robin advances the same way. It fails when one rule changes on either side.
17. **The parity fixture carries what the old tree carried.** If the old tree names real salespeople, so does the fixture. Generate the fixture from synthetic names, or keep it out of the repository, before the first push. The worked example's fixture holds the source system's people and should be reviewed for that.

*Seen once:* the worked example, for sales assignment. *Not yet proven:* that the file path ran against a real client's confirmed rules; and what retires the built-in tree. A parity test that has held for a release is the evidence to delete it. Nobody has decided that.

## An optional provider: the TypeScript chain

The source system's data chain is TypeScript. The owner called it optional and said it could be rewritten in Python when needed (its R24).

18. **The Python side never assumes the provider.** `example:scripts/_lib/ts_bridge.py` is the only place that calls it. It runs a command with the data path in the environment, a temp folder of its own, a timeout, and no credential unless the caller names it: variables ending `_PASS`, `_SECRET`, `_TOKEN`, `_KEY` and `_CODE` are dropped from the child's environment.
19. **A verb that needs the provider refuses with a coded reason.** `ts_deps_missing` when its dependencies are not installed (the message names the install command), `ts_timeout`, `ts_failed` (with the last line of the child's error), `ts_not_json`, and `no_db` when the database it would create is not there. Each is a registry row; none is a traceback.
20. **`doctor` reports the provider's absence as information.** [`kit/doctor.py`](../kit/doctor.py) takes a check from the skill pack (`example:scripts/_lib/doctor_checks.py`); the TypeScript check says `ok` when `node` and the dependencies are there and `info`, with the install command, when they are not. A warning would send a Python-only install to fix what it does not use.
21. **The provider has its own CI job.** The worked example's `.gitlab-ci.yml` has an `sdr test` job for Python and a `ts test` job for the chain (`npm ci`, `tsc --noEmit`, the TypeScript suite). A job with no `rules:` runs only on branch pipelines, so each states its rules. The `ts test` job also installs the `sqlite3` command, because two TypeScript tests call it.

*Seen once:* the TypeScript chain behind a Python facade. *Not yet proven:* the Python replacement the owner allowed for. Nobody has tried it.

## The write path, off by default

The worked example builds the write machinery generically and a CRM adapter shallowly, because the CRM differs for every client (its R25). Every kind stays at per-item approval until a client proves an inverse. Email and sheet writes are registered kinds, not wired.

22. **A skill pack that can write should have these proofs, each as a test that runs offline against a fake transport.** `example:tests/test_write_path.py` has them; copy the list, not the CRM.
    - The allowlist is empty. An entry is its own merge request, merged by the owner.
    - The kill switch, the STOP file and a missing opt-in each stop a send that is otherwise approved.
    - An opt-in with an empty allowlist sends nothing, and the item is marked failed.
    - A dry run, and `--apply` with writes off, send nothing.
    - An unapproved item is never sent; an expired approval is never sent.
    - An approved item is sent once; a second run sends nothing more; the same proposal again is the same row, not a new send. The item becomes `executed` only after a read-back.
    - The approved payload is frozen: an attempt to swap it in the table is refused.
    - A payload outside the kind's shape is a coded refusal, not a send.
    - The daily cap is counted from the ledger of sends, never from a counter.
    - Every write kind has a row in the ceiling registry (`example:ssot/apply_tiers.tsv`), no kind rises above per-item approval without a proven inverse, and every undo names a registered kind.
23. **A ceiling row says why it is low.** Each row of the worked example's registry has a `why`: a CRM record cannot be deleted by the tool, so a create cannot be taken back; a patch's inverse is a patch from a before-snapshot that no client has proved; an email cannot be unsent. The six columns are those of [`kit/autonomy.py`](../kit/autonomy.py) ([autonomy](autonomy.md), "The shared mechanics"), plus `why` and a label in the owner's language.

The mechanics are [`kit/write_guard.py`](../kit/write_guard.py), [`kit/queue.py`](../kit/queue.py) and [`kit/execute.py`](../kit/execute.py); this chapter adds nothing to them.

*Not yet proven:* any write against a real CRM. Eight kinds are registered (five CRM kinds, of which the example adapter routes four, two emails and a sheet row) and the tests use a fake transport.

## Small lessons, with what each cost

Each was met once in this build. None is general law; each is cheap to check.

- **An ignore rule hid a test fixture, and the suite passed locally.** The line `!tests/fixtures/leads.db` stood above `*.db`, so the later rule ignored the file again. The fixture was on the developer's disk, so every test passed. CI saw no file and failed. The fix moved the exception below the ignore line, and it was made twice, once on each of two branches. *Rule:* a negation (`!`) comes after the pattern it undoes, and a test that needs a fixture asserts the fixture is tracked (`git ls-files`) or fails when it is missing, not skips. The leak test in rule 9 is the one in this build that still skips.
- **A test runner exited non-zero though every test passed.** Vitest reported "Timeout calling onTaskUpdate" from a worker kept busy by a long synchronous child process, and exited 1. Three CI changes followed: two workers, then one file at a time, then a flag that ignores unhandled worker errors only (`--dangerouslyIgnoreUnhandledErrors`; a failing test still fails the job, as the flag's documentation says). *Rule:* when a runner is red and every test is green, read the runner's own error before changing parallelism, and say in the CI file what the flag hides. *Not yet proven:* no test makes the job go red on a failing test to show the flag hides nothing else.
- **An `rm -rf` with a relative glob was refused by the agent runtime's safety check.** A cleanup line in a script or a command used a glob relative to the working directory, and the check stopped it. The check was right: a relative glob run from the wrong folder deletes the wrong files. *Rule:* a test removes only a temp folder it made itself, by its own absolute path (`tempfile` and `shutil.rmtree`), and a script never deletes by a glob from the working directory. The playbook's runner already fails a test that leaves a temp file behind ([templates/tests](../templates/tests/)).
- **A message-code registry must be closed both ways, and a reword touches both halves.** Every `msg()` call names a literal code, the code is registered, the call passes exactly the registered params, and every registered code is emitted somewhere ([`kit/messages.py`](../kit/messages.py), `check_registry_closed`; [rules](rules.md#registries-one-place-per-value), "Code every message"). Each new verb in this build added its rows in the same commit. When the bridge grew from one TypeScript tool to two, the text of `ts_timeout` and `ts_failed` lost its word "db" in the registry and at the call, in one commit. A code registered ahead of its verb fails the "never emitted" half, so rows are not pre-registered.

## Adopting it in another skill pack

1. **Write the lifecycle once** as a table of stages with a column for each origin that differs, and give the `engage` row both meanings. Take the eleven stages as they are; add a stage only when a client's flow cannot be placed.
2. **Start the catalog from what the source system already does,** one row per capability with its stage, origin, whether it uses AI, what leaves the company, and a `status`. Mark what the system never did `todo`.
3. **Write the client's route as rows that name catalog ids,** with who acts, where the result is kept, what leaves the company and where a person decides.
4. **Generate the page and its `--check`,** and run both in CI. Add the live section only with the leak test, and make the fixture's absence a failure.
5. **Start with the profile stage** before anything is scored: briefs raw, a profile pending, a quote behind each line, a shape check at export, and nothing reading a pending profile.
6. **Move a rule tree to data only with a switch and a parity test.** Keep the old code until the test has held for a release, and keep client names out of the fixture.
7. **Treat any language runtime that is not the skill pack's own as optional.** One module calls it, a missing runtime is a coded refusal, `doctor` says information, and CI has a job for it.
8. **Keep the write path off, and write the list of proofs before the first kind.**

## Not yet proven, and open

- That the agent's choice of the next step, checked by the program, works. It is a design; the checks it would need are in the first section.
- That the catalog's `status` stays true. No test relates a status to the code, and one row is already out of date.
- That the pipeline page helps a client owner decide anything. The worked example's owner read and corrected it twice (its R15 removed a sheet step, its R22 moved four capabilities out of the route); no one else has used it.
- That the profile makes scoring better. Nothing reads it yet.
- That rules as data run correctly on a real client's confirmed rules, and when the built-in tree may go.
- Whether the `pages` pack should hold the page to its style check.
- Whether a second skill pack's lifecycle looks like this one's. The eleven stages come from one build. A second skill pack is the test, and the second consumer the kit's admission rule asks for before any of it becomes a module.
