# The kit, the build tools and the templates

Moved from the playbook's [README](../README.md) unchanged; the README keeps the overview.

## Build the next skill pack faster

The checklist above, already built: a new skill pack starts from these instead of from a blank folder. [BUILD.md](../BUILD.md) says which step uses which.

- [`kit/`](../kit/): the shared skill pack modules (the gate, human tables, the write guard, message codes, the `--json` contract, the verb table and dispatcher, doctor, the guards), vendored into each skill pack as `scripts/kit/`; each module belongs to one pack ([the admission rule](#the-admission-rule), [`kit/packs.tsv`](../kit/packs.tsv)). *Test:* `python3 kit/tests/run.py`, with `kit/tests/test_e2e_shop.py` proving the gate together with the console.
- [`hosts/zylos/`](../hosts/zylos/): the worked example of a host adapter (write one per host), driven by one manifest: install, configure, scheduled tasks and the console as a service. *Test:* `python3 hosts/zylos/tests/run.py`.
- [`scaffold/`](../scaffold/): `scaffold/new_skill_pack.py` renders the templates, writes the skeleton, vendors the kit and the console, and generates the thirteen day-one tests; the result is green before its first feature. *Test:* `python3 scaffold/tests/run.py` (`scaffold/tests/test_new_skill_pack.py`).
- [`build/`](../build/): the build-time tools: check meeting intakes, turn items into console asks, apply the answers. *Test:* `python3 build/tests/run.py`.
- [BUILD.md](../BUILD.md): the step-by-step workflow, B0 to B10: what each step produces, what fans out, who signs which gate. *Test:* `python3 tests/run.py` (`tests/test_docs_build.py`).
- [`skills/build-skill-pack/`](../skills/build-skill-pack/SKILL.md): the skill an agent loads to follow BUILD.md from the files alone. *Test:* `tests/test_docs_build.py` holds it to the same steps.

**Check the whole playbook with one command.** [`run_all.py`](../run_all.py) runs every test suite in the repository (the ones above, the console's, the templates' self-test, the workflow templates' and the golden-diff tool's), one line each, and ends with one `RESULT:` line; it exits 1 if any suite fails. A suite that prints no `RESULT:` line, has gone missing or lacks its tool (`node` for the Zylos adapter, `git`) fails and is never skipped; every `run.py` in the tree is a suite or is listed as a template, so a new one cannot be left out. `python3 run_all.py --list` names the suites and `python3 run_all.py kit console` runs some. [CI](../.github/workflows/ci.yml) runs `python3 run_all.py` on every pull request and on every push to main. *Test:* `python3 tests/run.py` (`tests/test_run_all.py`).

### The admission rule

Every module in [`kit/`](../kit/) belongs to exactly one pack, listed in [`kit/packs.tsv`](../kit/packs.tsv).

- **A new module goes in the pack named for its concern, never in `base`.**
- **It moves to `base` once two skill packs import it from code merged to their main branches.** Only merged use counts ([RESTRUCTURE.md](../RESTRUCTURE.md), decision 4): a branch that has not merged, a locally changed copy of the kit and a skill pack that wrote its own version of the job are not uses.
- **A module no skill pack imports for two minor versions is deleted.** Git history keeps it. Several modules in `testkit` and `base` are reached by every generated skill pack, the console's integration test or the Zylos adapter: look there before calling one unused.
- **`python3 tools/consumers.py SKILL_PACK...` counts the first two.** Point it at a checkout of each skill pack's main branch: it lists the kit modules the skill pack's own code imports (tests do not count), and which modules only come in through another one.
- **A pack imports only `base` and itself.** [`kit/tests/test_packs.py`](../kit/tests/test_packs.py) fails on a module with no row, a row with no module, and an import that crosses packs (lazy imports included).

**Packs decide what a skill pack vendors.** `base`, `compliance`, `generation`, `data`, `workbook`, `learning`, `pages`, `autonomy` and `testkit` ([kit/README.md](../kit/README.md), "Packs"). A skill pack names its packs under `[kit] packs` in `skill-pack.toml`, and `kit/tools/vendor.py` copies only those, plus `base` and `testkit`. A skill pack without the line still receives every pack.

## Templates

| File | Stage | What it is |
| --- | --- | --- |
| [`templates/meeting-intake.md`](../templates/meeting-intake.md) | 0 | The organizer prompt and its output shape |
| [`templates/decision-rights.md`](../templates/decision-rights.md) | 1 | The three lanes and the risky list |
| [`templates/CODEOWNERS`](../templates/CODEOWNERS) | 1, 10 | Protected paths for the risky list |
| [`templates/ssot/`](../templates/ssot/) | 1–2, 5–7 | Registry index, glossary, user stories and policies (owner file + agent sibling), thresholds, message codes, fact and decision keys, alert rules, story checks |
| [`templates/ci/gitlab-ci.yml`](../templates/ci/gitlab-ci.yml) | 2–3, 10 | The fuller CI to grow into: one pipeline per change, every job with its rules, story id (with a note for GitHub Actions), offline tests with a cache, a check of the Zylos adapter, adapter smoke, secret scan with a placeholder convention; `templates/gitlab-ci.yml` is its short form |
| [`templates/AGENT_INSTRUCTIONS.md`](../templates/AGENT_INSTRUCTIONS.md) | 3 | Invariants-only instructions for the coding agent (a `CLAUDE.md`) |
| [`kit/`](../kit/) | 3, 6, 8 | A module, not a template: the human gate, message codes with their contract test, the child-verb runner, one clock, and the raw and database guards, vendored into a skill pack by `scaffold/new_skill_pack.py` *(the rules and their tests come from the source project, where the original code ran on real data; the kit has since run inside three skill packs, one of them as a locally changed copy)* |
| [`templates/evals/`](../templates/evals/) | 8 | Agent-behaviour evals: the case layout (`case.yaml`, `prompt.md`, graders), the ablation table, the offline rules `kit/guards/evals.py` holds (the forbidden-verbs pattern is generated from the verb table), and a fixture builder that refuses a checkout holding client data *(untried as copied here: seen on one skill pack, run only against the toy skill pack)* |
| [`templates/tests/`](../templates/tests/) | 3, 9 | The test kit: a runner with a temp-leak gate, a one-clock lint, an import-graph layering engine with rules in a table, and a release-archive test; `selftest/` breaks each gate on the case it exists to catch *(untried as copied here)* |
| [`templates/tests/golden/`](../templates/tests/golden/) | 3, 10 | A module to copy: the golden-diff engine, the cases hook your skill pack fills from its verb table, and the tests that prove it can say 1 *(untried as copied here)* |
| [`templates/workflows/`](../templates/workflows/) | 3–10 | Workflow scripts for building with many agents (build → review → fix → verify; sweep → skeptic → plan), the ref check to run before any push, and the prompt rules with what each one prevented |
| [`templates/bug-classes.md`](../templates/bug-classes.md) | 4, 7, 10 | Data bug classes, each with the fixture test that pins it; the ids for the triage line's `Class:` |
| [`templates/doctor-checks.md`](../templates/doctor-checks.md) | 4–5, 9 | What the doctor checks: when each warns, the fix it names, the bug it caught |
| [`templates/console/ui_rules.tsv`](../templates/console/ui_rules.tsv) | 8 | UI rules as an owner file, each checked by name |
| [`templates/gitattributes`](../templates/gitattributes) | 9 | Copied to the root as `.gitattributes`: the internal files every release leaves out |
| [`templates/install-checklist.md`](../templates/install-checklist.md) | 9 | The install message, the host report, and what a host agent can read |
| [`templates/owner-queue-item.md`](../templates/owner-queue-item.md) | 10 | The shape of one owner ask |
| [`console/`](../console/) | 10 | A module, not a template: the agent's ask CLI and the owner's one-page console |
| [`templates/triage-checklist.md`](../templates/triage-checklist.md) | 10 | Judging an agent-filed issue; the triage line |
| [`templates/verify-challenge.md`](../templates/verify-challenge.md) | 10 | Reader and skeptic prompts for an outside report |
| [`templates/intake.schema.json`](../templates/intake.schema.json) | 0 | The shape of one meeting's intake; `build/check_intake.py` reads it |
| [`templates/prior-art-scan.md`](../templates/prior-art-scan.md) | 0, 4, 8 | When and how to scan what already exists, each claim with its link and date |
| [`templates/vendor-api-discovery.md`](../templates/vendor-api-discovery.md) | 0, 4, 8 | Pinning down a paid vendor API cheaply, and preflighting every request against its published schema |
| [`templates/third-party-consent.md`](../templates/third-party-consent.md) | 5, 8 | A real person in a marketing output: the record, confirmed only through the gate, bound to its content |
| [`templates/claim-scope.md`](../templates/claim-scope.md) | 5, 7, 10 | Regulated copy names only what the approved document allows: the claims record at the gate, the lexicon, waivers, the phrase library, rejections as recall tests |
| [`templates/design-first.md`](../templates/design-first.md) | 7, 10 | Before a feature an owner steers: research, one design page with the asks and what it stores, a synthetic demo drawn by the skill pack's own renderer, the owner's yes, then the code |
| [`templates/owner-review-loop.md`](../templates/owner-review-loop.md) | 7, 10 | One published page the owner decides on per item, read back by the next session |
| [`templates/outcome-learning.md`](../templates/outcome-learning.md) | 10 | Winners against the rest on one factor catalog; rules stay pending until a variant confirms them |
| [`templates/session-handoff.md`](../templates/session-handoff.md) | all | Each session closes one turn and leaves the next one ready |
| [`templates/skill-pack.toml`](../templates/skill-pack.toml) | 3 | The skill pack declares itself once: names, languages, scopes, layers, what a release ships |
| [`templates/gitlab-ci.yml`](../templates/gitlab-ci.yml) | 3, 9 | The short form of that CI, the one the scaffolder renders into every skill pack: secret scan, story id in the title, the RESULT-gated test job, each with its rules |
| [`templates/gitignore`](../templates/gitignore) | 3 | Secrets, the console's log and client data never enter the repository |
| [`templates/SKILL.md`](../templates/SKILL.md) | 9 | The agent's rules and the skill's scope: read, pending writes, out of scope |
| [`templates/README-operator.md`](../templates/README-operator.md) | 9 | The operator guide: install, configure, the daily loop, what needs a human |
| [`templates/workflows.md`](../templates/workflows.md) | 9, 10 | Recipes: the daily check, why a number moved, a client meeting |
| [`templates/README.md`](../templates/README.md) | all | Every template, the step that uses it and its target in a skill pack; the thirteen tests a new skill pack starts with |
