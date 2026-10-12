# Changelog

What a harness gets when it re-vendors the kit, and what else changed in the
playbook, newest first. Format: Keep a Changelog.
A release is a `kit/VERSION` (a patch for a fix, a minor for a new module or hook,
a major when a harness must change). `hosts/zylos` has its own `VERSION`, noted
where it moved. The short hash on a version line is the commit that set it; dates
are the merge day. Everything under *Other* is outside the kit: templates, build,
scaffold, console, docs, conformance.

## [Unreleased]

## [0.18.0] - 2026-10-12
### Added
- A "Never" table of the verbs only a person runs, first in a harness's SKILL.md, held to the
  verb table (`kit/guards/evals.py`; seen once: a newcomer agent found the video-ads harness's
  person-only rules scattered over five places, and that harness gathered them in one table at
  the top of its SKILL.md). `never_problems()` and `check_never_table()` fail when a verb of
  kind `gated`, or one `[guards.evals].extra` names, has no row; when a row names a verb an agent
  may run, or no verb of the table, or does not say why; and when `## Never` is not the first
  `##` section. A cell names verbs in code font, with or without the cli word. The kind
  `external` is not person-only (a pull is the agent's own read; an eval forbids it only because
  the run is offline): an external verb only a person runs goes in `extra`. `[guards.evals].never`
  renames the heading. `never_self_test()` plants each fault, `check_never()` reports, and
  `kit.testing.suites.never_table(root)` is the suite a harness's test calls.

## [0.14.0] - 2026-10-12
### Added
- `kit/guards/roadmap.py` and `kit.testing.suites.roadmap`: one ROADMAP.md format. The title,
  `Updated: YYYY-MM-DD`, then exactly Now, Waiting on owner, Next, Done, Parked, Decisions,
  Links; every item `- [ID] YYYY-MM-DD text`, the id's letter naming its section (N, W, X, D, P,
  R) and unique, the date a real day not after `Updated`; at most one Now row; a Waiting row ends
  `unblocks: <ids of the file>`; a Done row ends in a parenthesised reference; a decision quotes
  the owner; Links are `name: where`. `problems(text)`, `check_file(path)`, `check_roadmap(root)`
  (`[guards.roadmap] file`, else `docs/ROADMAP.md` or `ROADMAP.md`; both is a problem), and a
  self-test that plants each break. From the video-ads harness, which has kept its roadmap in this
  format, held by its own test, since 2026-10-01. A second harness copied the format without a test and does not pass the guard yet: a harness
  still on the old template moves its "Start on a new machine" section to `docs/session-handoff.md`, gives each Done
  row its reference, each Decisions row the owner's quoted words and each Waiting row its `unblocks:` before it adds
  `tests/test_roadmap.py`.
### Other
- A new harness is generated with `docs/ROADMAP.md` (from `templates/ROADMAP.md`, now the format
  as a short skeleton, `{{today}}` filled by the scaffolder) and `tests/test_roadmap.py`: twelve
  day-one tests, not eleven. `templates/AGENT_INSTRUCTIONS.md` gains the **Roadmap** invariant.
  Starting on a new machine moves to `templates/session-handoff.md`.
- The playbook's own `ROADMAP.md` is in the format (`tests/test_playbook_roadmap.py`), its stale
  status (kit 0.7.0, 2026-10-05) refreshed as dated Done rows through kit 0.14.0.

## [0.13.0] - 2026-10-12
### Added
- Pack `learning` (new; a harness takes it with `[kit] packs = ["learning"]`): `patternstore.py`, a
  per-client pattern store, generalised from the video-ads harness's own (which keeps its copy for
  now). Each client's evidence stays in its own database; nothing crosses clients. Docs:
  `docs/pattern-store.md`.
  - The row: context x ICP archetype x playbook, the fields the harness's `Shape` names, every value
    an id of a vocabulary the harness passes or null, with `n`, hashed family tokens and outcome
    counts; `group()` pools items into rows, `row_id()` is the content id. `validate()` never raises
    and refuses free text, a trailing newline, unknown or missing keys, wrong types, a bad sum, an
    outcome on a presence-only source and an id that does not recompute; a problem never quotes the
    value. `shape_problems()` for the harness's own test.
  - Two coders: `agreement()`, `meets_floor()` (0.70, from the counts), `agreed_values()`.
  - The shrinkage: `prior()` (mean anchored off the edges, method-of-moments kappa clipped to 5-10
    tests; none for fewer than two labelled cells, `prior_reason()`), `shrunk()`, `ranks()` (ties
    share), `shrink()`; a stdlib Beta CDF and quantile.
  - The store: `TABLES` and `APPEND_ONLY` in kit.db's format (extra human tables), `state()`,
    `live_rows()` (a row retracted by hand in any scope is out of the all-scopes union), `plan()` (an
    export supersedes every live record of what it no longer makes; a duplicate id is inserted once
    and counted), `apply()` (refuses a row whose id does not recompute), `retract()`.

## [0.12.0] - 2026-10-11
### Added
- One human gate per client file (#66; the KOL harness's R34, owner's option B): the map of a
  client's workbook and the values the agent read from it pass ONE retype or ONE relayed code,
  once per version, never one number at a time.
  - `workbook_map.py`: an optional `values.tsv` (key, market, value, sheet, cell or range,
    status, note); fact keys checked when the harness gives them; a map without it keeps its
    version. `texts_confirmed()` (a staged bundle with every row confirmed), `confirmed_rows()`
    and `gate_rows()` (what a bundle confirms that the one in force did not).
  - `file_gate.py` (pack `workbook`): `plan()`, `ask()`, `confirm()`. The console ask and the
    gate are built from the same plan; the binding is both bundles' versions, the row count and
    every value, so it stays small whatever the map's size.
  - `facts.py`: `plan_file()` checks a file's values as `set` would, before any gate;
    `apply_file()` writes them confirmed with the gate's channel (history action `confirm`),
    all or nothing if one moved meanwhile.
  - `pending.py`: a `staged=` hook, one `file` ask per staged client file
    (`pending_summary_files` when there is one).
### Changed
- `pending.py`: with several markets declared or waiting, a fact or decision ask keeps its gate
  and names the market (`gate.market`); `pending_gate_market_ambiguous` is left for a market
  that is not a plain word. A one-market harness gets the same asks as before.

### Other
- Console: a gate may carry `market` (one plain word); the relay passes it as one `--market=M`
  element after the verb, and `expect` holds the same market, so the harness's subject must
  name it (#66).
- Client template: the first call is `doctor` and `pending`, not a status verb (#55).
- `templates/CHANGELOG.md`, rendered into every new harness, and a `changelog` job in both CI
  templates: a merge request that changes the code, a registry, the skill or the console must
  add its line under Unreleased, or say `[no changelog]` in its title. Tested by running the
  job's own shell on sample file lists.

## [0.11.0] - 2026-10-10
### Added
- Pack `workbook` (new; a harness takes it with `[kit] packs = ["workbook"]`): a client's
  .xlsx read as it is and kept as a generic store, for a client that runs every project
  in one workbook (the KOL harness's X33, R29). Stdlib only (`zipfile`, `xml.etree`).
  Design: `docs/workbook-and-browser-ops.md`.
  - `workbook.py`: `read()` gives every sheet's cells with their kind, text, number,
    number format, ISO date (1900 or 1904 system), formula text beside its saved value
    (never recalculated; shared and array formulas kept), hyperlink, comment mark,
    hidden row or column and merge anchor; sheet states (hidden kept), merges,
    validations, core properties and every part's sha256. A part with a DOCTYPE or an
    ENTITY, or over the size caps, is refused (`workbook_unsafe`); a file that is not an
    xlsx is `workbook_unreadable`.
  - `workbook_map.py`: the client's map, `tables.tsv` (where each table is: sheet,
    anchor text, search box, stop, key, market) and `columns.tsv` (what each column
    means: field, direction in/out/both, owning harness, type, proposed/confirmed).
    Three rules: an outgoing column has one owner; every field is in the harness's
    vocabulary; `pending()` lists what the owner has not confirmed and `confirmed()`
    is all a projection reads.
  - `workbook_store.py`: eight cache tables (`wb_file`, `wb_sheet`, `wb_table`,
    `wb_column`, `wb_row`, `wb_cell`, `wb_change`, `wb_issue`) in kit.db's format,
    none naming a business field; tables found by anchor (blocks side by side,
    group rows, a stop text, blank rows inside counted); rows keyed by the map; the
    change record between imports of one workbook (the write-back conflict list);
    `records()` for a harness's projection (typed values, each with its source cell,
    an empty cell None, never 0); `summary()` for a read verb, personal columns and
    any e-mail address masked.
- `testing/xlsx.py` (testkit): a small deterministic xlsx writer, so a test builds the
  workbook it reads. Tested on two SYNTHETIC clients' workbooks (`kit/tests/_workbooks.py`).

## [0.10.1] - 2026-10-10
### Changed
- `TakeStore.approve(version=)`: a caller may bind the spend code to its own approval record (the
  newest history id the approval moves) instead of the ledger's length. A Make page open while
  another job on the same project charges the ledger kept going stale, so the person clicked
  again (adcut-harness, once, after it queued Makes clicked during a running job). The default
  (None) is the ledger's length, as before; a caller that passes its own version keeps the code
  single use and checks the cap again before it pays.

## [0.10.0] - 2026-10-10
### Added
- `kit/guards/changelog.py` and `kit.testing.suites.changelog`: `CHANGELOG.md` starts with
  Unreleased, its releases are in order (versions descending, dates not increasing, each with
  a `### ` section), `SKILL.md`'s version is the newest release (a harness not yet released is
  at 0.1.0), and every `vX.Y.Z` tag has a heading. A self-test plants each fault. Seen in
  amazon-ads-harness, which wrote the same rule for itself.
### Other
- A new harness is generated with `tests/test_changelog.py`: eleven day-one tests, not ten.
  `templates/AGENT_INSTRUCTIONS.md` gains the **Changelog** invariant, naming that test.

## [0.9.0] - 2026-10-08 · `7569fb2`
### Added
- `tools/skill_upload.py` writes the copy of SKILL.md that claude.ai and the Skills API
  accept (`name`, `description`, `metadata`…), leaving the repository's frontmatter, which
  Zylos reads, untouched (#54).
### Other
- Evals: one method; the pair-run lessons move into `templates/evals/README.md` (#46).
- `build`: `apply_answers` applies the owner's answer to a builder's own proposal.
- Scaffold: client wrappers run `<PREFIX>_PYTHON` and refuse a Python older than 3.11.
- `CLAUDE.md`: the parent's rules for working here — small, decoupled, one concern per
  change (#52). Lessons for paid generation jobs (#53). Geo-china fixes (#51).
- Conformance: the `ppc` adapter follows its current CLI; adapters may type values and
  answer a TTY.

## [0.8.1] - 2026-10-05 · `e8e14c9`
### Fixed
- An agent-only row `asked` (sent to the console, not answered) is a legal status in the
  ssot guard; `proposed_statuses` defaults to `["proposed", "asked"]`. Seen in geo-china-harness.

## [0.8.0] - 2026-10-05 · `5867752`
### Changed
- **`facts set` and rollback never replace a confirmed value.** An ungated write over a
  confirmed value is refused (`fact_set_confirmed`), naming the two ways forward: unconfirm
  (lower trust, recorded) or `confirm --value`. Found by conformance C1 in
  amazon-ads-harness. **A harness that relied on the old replace must change.**

## [0.7.0] - 2026-10-05 · `8e13e16`
### Added
- **Packs and selective vendoring** (phase 2 of `RESTRUCTURE.md`): every module belongs to
  one pack in `kit/packs.tsv` (`base`, `compliance`, `generation`, `data`, `testkit`); a
  harness names its packs under `[kit] packs`; `vendor.py` copies only those plus `base`
  and `testkit`, and refuses to leave out a module the harness imports. With no
  `[kit] packs` a harness receives every pack, so existing harnesses see no change.
- `tools/fleet.py`: where each harness's vendored copies stand (phase 1).
### Removed
- `kit/pull.py` (no consumer).
### Other
- `conformance/`: the invariants every harness keeps and a black-box check for two of them
  (C1 a confirmed value is never replaced by an agent, C2 doctor).
- README is the overview; the detail moves unchanged into `docs/` (phase 4).
- `hosts/zylos` 0.1.1: a zombie job is not alive; Node 22 is the minimum (#21).
- `templates/SKILL.md`: agent rules from a second harness's client rehearsal; the
  playbook's own `ROADMAP.md`.

## [0.6.2] - 2026-10-01 · `c9aa076`
### Added
- `scaffold/new_client.py`: one folder per client — wrappers pinned to `./workspace`, its
  console, a `CLAUDE.md` brief, deny rules for gated verbs. `templates/ROADMAP.md`, the
  `docs/ROADMAP.md` every harness keeps.
### Changed
- `kit.copylint`: 兩 reads as 2. Law lens added to the prior-art scan; doctor check for a
  vendor API version still alive. Landed from KOL's local 0.3.1 work.

## [0.6.1] - 2026-10-01 · `b3ebb74`
### Changed
- `--help` examples and JSON keys come from the verb table; `--for-client` on facts and
  decisions `confirm`; the console user comes from the OS account (#37).

## [0.6.0] - 2026-10-01 · `1eb183d`
### Added
- Agent evals, the offline half: `kit/guards/evals.py` holds a suite to what needs no
  model — each case names the SKILL.md rule it tests, carries the forbidden-verbs grader
  generated from the verb table, and has a row in the ablation table (an eval counts only
  if it fails when its rule is cut). Template `templates/evals/` and fixture (#17).

## [0.5.0] - 2026-09-30 · `4b49354`
### Added
- Claim scope and phrasebook (#11).
- **0.4.0, the price registry, landed with this version** (it missed #9): `kit/prices.py`
  reads an owner TSV of prices whose rows stay pending until a person confirms them; a
  blank price is unknown, never zero.
### Other
- Evals run as a pair, the rule's text deleted from the twin. README and templates: sources
  kept apart, cited rules capped and re-verified, one-client rules stay proposed.
- Slimmed: CI and `run_all.py`, the kit tier registry, duplicates removed.

## [0.3.0] - 2026-09-29 · `3af9c7f`
### Added
- Generated creative and real people: `takes` (paid generation planned, priced, capped,
  approved for exactly the plan, kept once), `preflight`, consent, `copylint` (#9).
### Changed
- `kit.human`: attribution by OS account, never `LOGNAME`/`USER`; a third party's own
  confirmation bound into the code's subject (`--for-client`) (#8).
### Removed
- Team review (adviser agree/disagree) from the console, the Zylos adapter and the docs (#5).

## [0.2.0] - 2026-09-29 · `090f788`
### Added
- `scaffold/new_harness.py`: a new harness, green before its first feature.
### Changed
- The kit absorbs `core/` (owner decision, 2026-09-29): raw guards, store and gate checks,
  the one-clock guard, the verb-case contract; `core/` stays as a pointer.
- `queue add` never supersedes an approved row, only pending ones; a dry run says when
  `--apply` cannot send (new optional `allowlist` hook).

## [0.1.0] - 2026-09-29 · `ab1871a`
First kit: the shared modules distilled from amazon-ads-harness. Stdlib only, Python 3.11+,
configured once by a harness's `harness.toml`.
### Added
- `kit/`: config, messages (closed registries), contract (one `--json` document, `meta`,
  coded failures), dates/atomic/raw, paths/env/auth/retry, db (protected human tables:
  triggers, shrink guard, backups, lossy-rebuild refusal, version stamp), human (TTY retype
  or a relayed HMAC code bound to the subject), market, registry, facts, decisions, queue,
  execute (dry run by default), write_guard (kill switch, opt-in, allowlist, no retries),
  pending, stories, guards (ssot, release, layering, JSON contract, boundary, drift), the verb
  table, dispatcher and doctor, and `kit/README.md` with `MANIFEST.sha256`.
- `hosts/zylos` 0.1.0: a manifest-driven Zylos host adapter.
### Other (the playbook before the kit, 2026-09-27 to 09-29)
- The playbook itself: client meetings, the ten stages, decision rights, trust ladder, data
  layers, human-in-the-loop rules.
- `console/`, the owner console, forms sent in place.
- `templates/`: data bug classes each with its fixture test, a full GitLab CI, a test kit,
  the doctor's checks, many-agent workflows, golden-diff engine; `BUILD.md`.
