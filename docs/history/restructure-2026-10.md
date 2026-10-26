# Restructuring plan: a smaller parent

> **Archived 2026-10-26.** This is the plan as accepted on 2026-10-05, kept as written. What it decided is now the rule in [CLAUDE.md](../../CLAUDE.md) and [kit-and-tools.md](../kit-and-tools.md). Phases 2, 4 and 5 are done; phase 3 finished when the prose-pinning tests went (kit 0.41.0, unreleased); phase 1 (one kit version in every skill pack) is the open turn of [ROADMAP.md](../../ROADMAP.md) (N2) and selective vendoring per skill pack is X2. Phase 6 is a list of separate decisions, none taken. Links below point at the tree as it was.

Status: **accepted 2026-10-05** (decisions 1 and 2: packs as drawn, phase 1 first). Phase 1 is in progress: step 4 and the comparison tool are done; steps 1 to 3 need the skill pack checkouts. Phase 2 steps 1 to 5 are done in kit 0.7.0 (packs, selective vendoring, `--packs`); step 6 needs the skill pack checkouts. Phases 4 and 5 are done. Phase 3 is done for the registry (2026-10-21: `kit-tiers.tsv` and its test are deleted; the consumers script and the prose-pinning tests are not). Each phase lists the decisions it needs from the owner. Related issues: #19, #20, #22, #24, #26.

## Why

This repository is meant to be the parent of every growth-marketing skill pack (KOL, Amazon Ads, Meta ads for retail, ecommerce SEO, ...), so that each skill pack only has to build its own channel. Today the parent has three problems:

1. **Every skill pack gets everything.** `vendor.py` copies all 49 kit modules (about 17k lines, plus a 4k-line test kit). Only 6 modules have two production consumers. 32 have one consumer or none, and six of those exist only for generated video creative.
2. **The shared copies have drifted.** The three skill packs that vendor the kit are on three versions. KOL edited its copy into a 0.3.1 that never existed here. SEO and outreach wrote their own versions instead.
3. **Governance costs more than it protects.** `kit-tiers.tsv` keeps hand-written evidence strings that tests enforce. The README has paragraphs that tests require. The README itself is 73 KB. Every change pays for all of this, and the real guarantees (the gate, the human tables, the money path) are hard to find.

## What stays the same

These constraints are good, and the plan keeps them:

- **Stdlib only. A release is the `git archive` of a tag. A host installs nothing.** That is why the kit is vendored rather than pip-installed, and the plan keeps vendoring. The drift came from upgrades being costly, not from vendoring itself.
- **Import paths stay `from kit import X`.** No module is renamed or moved in phases 1 to 5, so no skill pack has to change its imports.
- **The guarantees and their tests:** the gate bound to its subject, human tables that never shrink, pending until confirmed, the queue, dry-run and allowlist, the `--json` contract, coded messages, the drift guard.
- **One repository for now.** The owner is solo, and `test_e2e_shop.py` tests the kit and the console together. Splitting repos would add cross-repo CI and give little back. This is reconsidered in phase 6.

## Target shape

### Packs instead of tiers

Each kit module belongs to exactly one **pack**. A skill pack names its packs in `skill-pack.toml`, and `vendor.py` copies only those. Every skill pack gets `base` and `testkit`.

| Pack | Modules | Lines | Who needs it |
| --- | --- | --- | --- |
| `base` | config, contract, dates, messages, paths, db, schema_base, human, market, registry, raw, facts, decisions, pending, queue, execute, write_guard, cli, verbs, doctor, env, auth, runner, stories, single_instance, atomic | ~9,900 | every skill pack: what the skeleton runs, as measured from `scaffold/skeleton/` and the import graph |
| `compliance` | copylint, claimscope, phrasebook | ~1,100 | skill packs that write ad copy, especially regulated copy (video-ads; KOL for copylint) |
| `generation` | takes, prices, preflight, consent | ~1,500 | skill packs that pay for AI generation or use real people's likeness (video-ads) |
| `data` | retry (pull: see phase 5) | ~560 | skill packs that pull rate-limited APIs (KOL) |
| `testkit` | guards/*, testing/*, tools/manifest | ~4,000 | every skill pack's own tests; listed in `[release].internal` so it does not ship |

`tools/vendor.py` (and `tools/packs.py`, which it reads) are playbook tooling, kept in `testkit` for now so a skill pack's copy is unchanged; dropping them from the copy is a later, separate change.

There is one rule: **a pack imports only `base` and itself.** A test enforces it using the import graph, lazy imports included. This replaces the core/stack/extra layering rule. Checked against today's imports, compliance and generation need only base modules (human, atomic, registry, messages, dates), so the rule holds.

Approximate result per skill pack:

| Skill pack | Packs | Kit lines vendored, testkit excluded |
| --- | --- | --- |
| video-ads | base, compliance, generation | ~12,500 (today ~17,000) |
| KOL | base, compliance, data | ~11,500 |
| RedNote | base | ~9,900 |
| a new Amazon Ads or Meta skill pack | base, data | ~10,500 |

**Correction to the earlier review.** The review estimated a 7k-line parent. Once you add the modules the skeleton actually runs (cli, doctor, env, auth, runner, stories, execute), the true base is about 9.9k lines. The bigger gain is that it becomes clear what the parent is and what belongs to a channel. A skill pack also has a smaller surface to upgrade.

### The admission rule, simplified

- A new module goes into the pack named for its concern, never into `base`.
- A module moves to `base` once two skill packs import it **from code merged to their main branches**. Unmerged branches no longer count.
- A module that no skill pack imports for two minor versions is deleted. Git history keeps it.
- Consumers are counted by a script you run on demand (`kit/tools/consumers.py --skill-pack PATH ...`), not by a hand-kept evidence column checked in CI.

### The repository after the plan

```
README.md            ~2,000 words: what it is, the five owner gates, the guarantees, how to start
BUILD.md             the build steps (unchanged in role)
ROADMAP.md
docs/
  lessons.md         every "paid for" incident, one table (from README + kit/README)
  channels.md        the reuse map and per-channel notes (from README)
  hosting.md         short; points at hosts/zylos/README.md
kit/
  packs.tsv          module -> pack (replaces kit-tiers.tsv)
  README.md          one section per pack
console/  hosts/zylos/  scaffold/  build/  templates/  skills/   (roles unchanged)
```

## Phases

Each phase is one or a few PRs and ends green on `python3 run_all.py`. Phases 1 and 2 must happen in order. Phases 3 to 5 can follow in any order.

### Phase 0: decide (owner, one session)

Answer the decisions at the end of this file. Nothing else starts until decisions 1 and 2 are made.

### Phase 1: one kit version everywhere (#20)

This is a prerequisite. Selective vendoring on top of three versions and a fork would only multiply the drift.

1. Run `python3 tools/fleet.py status <video-ads> <kol> <rednote>` from this checkout (full history, not a shallow clone). For each copy (kit, console, `zylos/`) it gives the version and a verdict: `in sync`, `behind` (re-vendor, nothing lost) or `local changes`. It lists each file that differs as `older` (an earlier playbook version, named), `local` (in no version the playbook ever had), `missing` or `extra`. `python3 tools/fleet.py diff <kol> kit/facts.py` shows one file. For each `local` file in KOL's 0.3.1 copy, either upstream the change here as a fix with a test, or drop it.
2. Release that as a kit patch version.
3. Re-vendor video-ads, KOL and RedNote. Fix the CI jobs that have no `rules:` (BUILD.md, B10).
4. ~~Fix the Zylos adapter test that fails under Node 22 (#21).~~ Done in adapter 0.1.1. The cause was not Node: a finished job left as a zombie, under an init that never reaps (a container without `--init`), counted as running. Node 22 is now the stated minimum, and CI runs on it.

**Done when** all three skill packs hold the same `VERSION`, their drift tests pass on `main`, and KOL has no local kit edits.

**Breaking?** No. **Needs:** each skill pack owner's review.

### Phase 2: packs and selective vendoring (#19)

1. Add `kit/packs.tsv` with columns `module`, `pack`, `note`, seeded from the table above.
2. Add `kit/tests/test_packs.py`. Every module has exactly one row. No row points to a missing module. Each pack imports only `base` and itself.
3. Change `vendor.py`:
   - Read `[kit] packs = [...]` from the skill pack's `skill-pack.toml`. If the key is missing, use **all packs**, which is today's behaviour, so nothing breaks.
   - Always add `base` and `testkit`.
   - Copy only the chosen modules, and their `message_codes.d/` fragments.
   - Write the manifest for that subset. `guards/drift.py` already checks a copy against its own manifest, so it needs no change.
   - **Refuse** to remove a module that the skill pack's own code still imports, using an AST scan of `scripts_dir` and naming the importing file. This stops a skill pack from losing a module it uses.
4. ~~Move the `raw`, `human` and `env` rows out of `kit/message_codes.tsv`.~~ Not needed: those three modules are all in `base`, which every skill pack takes. Fragments of other modules travel with their pack.
5. `scaffold/new_skill_pack.py --packs base,data`, defaulting to `base`. Add `templates/skill-pack.toml` `[kit] packs`.
6. Opt each skill pack into its packs, one PR per skill pack. Video-ads goes last, in a quiet week, as already planned.

**Done when** each skill pack vendors only its packs and passes its own suite. `run_all.py` is green.

Since the skill packs converge in phase 1, they can converge directly on 0.7.0 and set `[kit] packs` in the same change: one re-vendor per skill pack instead of two.

**Breaking?** No for imports. A skill pack that opts in loses modules it does not import, and the vendor tool's refusal protects the ones it does. Bump the kit **minor** version.

### Phase 3: retire the tier registry

1. Delete `kit-tiers.tsv` and `kit/tests/test_tiers.py`. `packs.tsv` and `test_packs.py` replace them.
2. Add `kit/tools/consumers.py`, which prints who imports what across skill pack checkouts given on the command line. It is used when deciding a promotion or a deletion, never in CI.
3. Remove README text that tests require, such as the paragraph for each "FRAGILE" core row. Keep the tests that guard behaviour.
4. Keep the kit rules: stdlib only, no domain words, the kit and console never import each other, every message coded.

**Done 2026-10-21 for steps 1 and 4.** `kit-tiers.tsv` and `kit/tests/test_tiers.py` are deleted; `docs/kit-and-tools.md` states the admission rule in terms of packs; the layering rule it held is `kit/tests/test_packs.py` (a pack imports only `base` and itself). Consumers per module are no longer written down: the history of `kit-tiers.tsv` has the last count. Steps 2 and 3 (the `consumers.py` script, and the tests that pin prose in `tests/test_docs_build.py` and `console/tests/test_docs.py`) are open.

**Done when** no test reads a prose document for a required paragraph, except `test_docs_build.py`'s check that every path a doc names exists.

**Breaking?** No.

### Phase 4: docs (#24)

1. Cut `README.md` to about 2,000 words:
   - what a skill pack is;
   - the pipeline diagram;
   - the five owner gates;
   - one list of guarantees, each with the module and test behind it;
   - how to start a skill pack (BUILD.md);
   - links to everything else.
2. Move whole sections, keeping their wording, rather than rewriting them:
   - the incident lessons from README and `kit/README.md` to `docs/lessons.md`;
   - the reuse map and "Generated creative" to `docs/channels.md` and the pack sections of `kit/README.md`;
   - hosting to `hosts/zylos/README.md`;
   - console material to `console/README.md`;
   - the day-one checklist to `BUILD.md`.
3. Make `skills/build-skill-pack/SKILL.md` follow the Agent Skills spec (agentskills.io): `name` and `description` frontmatter, with long material in `references/`.

**Done when** README is 2,000 words or fewer and `test_docs_build.py` passes. A new agent can find the guarantees from README alone.

**Done 2026-10-05.** The README is about 1,400 words: the overview, the pipeline, who decides, trust in the data, the guarantees, how to start, and a map. Every other section moved unchanged into `docs/`, as `stages.md`, `rules.md`, `consoles.md`, `operating.md`, `channels.md` and `kit-and-tools.md`. Its tests now read those files, and a new test checks every link and anchor in the README and `docs/`, and keeps the README to 2,000 words or fewer.

This differs from the steps above in four ways:

- The day-one checklist went to `docs/stages.md`, not `BUILD.md`.
- Hosting went to `docs/operating.md`, and console material to `docs/consoles.md`, instead of being merged into the adapter's and the console's own READMEs.
- The incident lessons stay next to the rules they explain. `docs/lessons.md` holds only lessons whose code is gone.
- Only `skills/build-skill-pack/SKILL.md` follows the Agent Skills spec. `templates/SKILL.md` keeps its top-level `version` and `type`, which the Zylos host reads, so changing it waits on the adapter.

**Breaking?** No.

### Phase 5: remove what has no consumer (#22)

- ~~**`pull.py`** has no importer anywhere.~~ Done in kit 0.7.0. Delete it, along with its message codes and test. Before deleting, record its design notes in `docs/lessons.md` (merge by natural key, chunked resume, gap ledger). Then compare dlt and Airbyte's Amazon Ads source, which re-pulls the last 3 days by default, before writing a pull layer again.
- **`guards/evals.py`** is new (0.6.0) and BUILD.md B8 relies on it. Keep it in `testkit`. Delete it if no skill pack calls it by kit 0.9.
- Each remaining one-consumer module stays in its pack. Packs make this cheap: a skill pack that doesn't need a module never receives it.

**Breaking?** No, because nothing imports these. Bump the kit **minor** version.

### Phase 6: later, each its own decision

Each of these is a separate decision, not part of this restructure:

- **Copier for templates.** Run a one-day spike: turn `scaffold/skeleton/` and `templates/` into a Copier template, and try `copier update` on one skill pack. Copier runs on the builder's machine, so skill packs still install nothing. Adopt it only if it handles updates to the CI file and CLAUDE.md, which `--update-kit` cannot, better than the current scaffold.
- **Rename `market` to `scope`.** This breaks the gate subject and the human tables, so it needs a **major** kit version and a migration for each skill pack. Do it only if a non-market skill pack, such as SEO or KOL, actually needs it.
- **The console and the Zylos adapter in their own repositories.** Do this when decision 2 of ROADMAP.md (which console copy stays, now its R1) is made and the console has users beyond this owner. Until then, one repository is cheaper.
- **SEO and outreach onto the kit (#26).** Once packs exist, migrating SEO means `base` plus whatever it needs, instead of all 49 modules.

## Out of scope: per-channel work this plan makes easier

These belong in each channel skill pack, never in the parent:

- **Platform dry-runs.** Google Ads and Meta both offer a `validate_only` option, and Meta can create ads paused. Have `execute`'s dry run send the real request in validate mode where the platform supports it. Amazon Ads has a sandbox for tests.
- **Official vendor tooling behind the gate:**
  - Amazon Ads MCP server
  - Meta's Ads CLI/MCP
  - Google's Ads MCP, which is read-only
  - Ahrefs and Semrush for SEO
  - Shopify for catalogue data
  - HypeAuditor and Modash for KOL vetting

  The skill pack wraps them as verbs. Writes still go through the queue and the allowlist.
- **Prior art for the safety layer:** kLOsk/adloop's draft → preview → confirm flow, caps and audit log. Compare it with `queue`, `execute` and `write_guard` before adding features to them.

## Risks

| Risk | Mitigation |
| --- | --- |
| A skill pack opts out of a pack it secretly needs (a lazy or dynamic import) | `vendor.py` refuses to remove anything the skill pack imports, using an AST scan. The skill pack's own suite runs before merge. |
| Phase 1 stalls on KOL's unmerged branch | Upstream the fork's changes from the branch as it is. KOL merges its branch or rebases later. Phase 2 waits only for the version to line up. |
| `packs.tsv` drifts from the code | `test_packs.py` fails on a module with no row, a row with no module, or an import across packs. |
| Docs move breaks links | `test_docs_build.py` already fails on a named path that does not exist. Move sections, don't rewrite them. |

## Decisions for the owner

All five decided 2026-10-05 as recommended: 1 and 2 first, then 3, 4 and 5. Done: 3 (`pull.py` removed in kit 0.7.0, its notes in [docs/lessons.md](docs/lessons.md)) and 4 (`copylint` is extra in `kit-tiers.tsv` until KOL's branch merges). 5 waits on phase 4 as recommended.

1. **Packs, and their names and contents** as in the table above. The specific question is whether KOL takes the whole `compliance` pack for `copylint` alone. The recommendation is yes: it is 1.1k lines, and splitting further adds a pack for one module.
2. **Phase 1 first.** All skill packs converge on one kit version before selective vendoring. Recommended: yes.
3. **Delete `pull.py`** (phase 5). Recommended: yes, with its design notes kept in `docs/lessons.md`.
4. **Count only merged use for promotion to `base`.** Recommended: yes. Under this rule, `copylint` would not count as shared by two skill packs today.
5. **Run the Copier spike** (phase 6). Recommended: after phase 4, and only if template updates to skill packs keep needing hand edits.
