# Changelog

What a skill pack gets when it re-vendors the kit, and what else changed in the
playbook, newest first. Format: Keep a Changelog.
A release is a `kit/VERSION` (a patch for a fix, a minor for a new module or hook,
a major when a skill pack must change). `hosts/zylos` has its own `VERSION`, noted
where it moved. The short hash on a version line is the commit that set it; dates
are the merge day. Everything under *Other* is outside the kit: templates, build,
scaffold, console, docs, conformance.
From 0.45.0 each version has one line `- Skill packs: nothing | mechanical (...) | judgement (...)`:
what a skill pack's own session does with it (`tests/test_changelog.py`).

## [Unreleased]

### Kit
- `kit/tools/pre-push.sample`: the optional test command (`git config skillpack.prepush-tests`) no longer inherits the variables git sets for a hook (found by the SDR skill pack, 2026-10-29, issue #315; reproduced in a scratch repository, not yet seen to break a pack's suite): from a linked worktree git sets `GIT_DIR` to the worktree's own, so a test that ran `git init`, `commit` or `archive` in a temporary folder acted on the pack's repository instead. The sample now clears `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_PREFIX`, `GIT_COMMON_DIR`, `GIT_OBJECT_DIRECTORY` and `GIT_ALTERNATE_OBJECT_DIRECTORIES` for that command only; the leak guard still runs with git's own environment. A pack that pushes from the main checkout sees no difference. Tested in `kit/tests/test_leak_guard.py` [5] (a push from a linked worktree: the command sees no `GIT_DIR`, and a repository it makes in a temporary folder is that folder's own); two deliberate breaks each fail a case. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
- Skill packs: mechanical (re-vendor with `python3 tools/fleet.py update`; a clone that already installed the hook copies the new sample over `.git/hooks/pre-push` with the `install` line in its header, since the hook is a copy)
- `kit.bridge` in a new pack `bridge` (asked by the Google Ads and Meta Ads skill packs, 2026-10-29; design [docs/design/support-channel-wrapper.md](docs/design/support-channel-wrapper.md), agreed by the owner the same day): `send_and_verify(send, read, text)` reports a message sent only when it is read back, by the id the send returned, equal to what was meant; an empty or different read-back is resent once, a missing id or a failed read-back is never resent, a full-width `＠` or an empty text is refused before sending; `runners(run, conversation_id)` and the prompts give the strict wording for the headless `comm_send` and `comm` calls. The pack is `incubating` until 2026-12-31 (`tools/pack_status.tsv`). `kit/VERSION` does not move with this merge.
- Skill packs: nothing (a pack that reaches a client's agents through the bridge takes `bridge` in `[kit] packs` and calls it in place of the hand-run send and read-back of `docs/support-channel.md`)
- `kit.bridge.send_to`, `rest_runners`, `load_credentials` and `check_isolation` (asked by the owner, 2026-10-30, for several bridges used at once by one session and by sibling sessions; design [docs/design/bridge-isolation.md](docs/design/bridge-isolation.md); tested against a local fake server; the token exchange and the read-back were also run against the real API on 2026-10-30, which showed two things the fake server had not: the edge refuses Python's own User-Agent (403, error 1010), and a message's content sits beside the message in the answer; the send and its read-back were then seen on the real API the same day, one message to one group; an @ mention object is not yet): a message is sent and read back by id over the bridge plugin's own HTTP calls, so no `claude -p` process, no model call and no extra connection of the same identity; the api key comes from the plugin's config, is held only in memory and is in no result, reason or repr; `check_isolation` refuses a missing, world-readable or key-less config, an organization the config does not hold, a data dir shared by two configs and one config used with two data dirs. `runners` (headless `claude -p`) stays for a machine with no key file. `kit/VERSION` does not move with this merge.
- Skill packs: nothing (a pack that sends through the bridge may call `send_to(Target(config, data_dir, conversation_id, org_id), text)`; one that keeps `runners` is unchanged)
- `kit.bridge.wait_for_reply`, `wait_for_reply_to`, `rest_waiter` and `next_round` (asked by the owner, 2026-10-30: the bridge only sent once and nothing read the answer or decided on a next round; design [docs/design/bridge-reply.md](docs/design/bridge-reply.md), agreed the same day; seen once): after a send, read the group over REST (no model call) until a message from someone else answers the sent one -- under it (`parent_id`), mentioning us, or from an asked agent (`from_ids`) -- or the time limit passes; the states are `replied`, `timeout` and `unreadable`; `next_round(used, why)` allows a follow-up only under three requests and with a written reason. Read-only against the real API on 2026-10-30 (the group's list answers newest first with `seq`, `sender_id`, `mentions`; a real reply was found with `from_ids`, none without it, since that agent's answers carried no mention). `kit/VERSION` does not move with this merge.
- Skill packs: nothing (a pack that wants the answer calls `wait_for_reply_to(target, sent.id, from_ids=[the asked agent])` in a background run and decides from the replies whether `next_round` allows another request)
- `kit.bridge.send_and_verify(..., dm=, mention_ok=)`, `Target.dm` and `send_to` (asked by the owner, 2026-10-30; seen again the same day: a pack's messages to a remote agent in a group carried no `@`, and in a group an agent answers only when it is mentioned; a note in the agent's memory did not stop it): a message to a group with no mention is refused with `no_mention` before anything is sent -- over REST `send_to` needs member ids to mention, on the headless path the text needs an ASCII `@name` (an address such as a@b.test is none) -- and a direct message (`dm=True`) needs none. The check is that a mention is present, not that the member exists. `docs/support-channel.md` section 3 and `templates/support-channel/send.md` say why. `kit/VERSION` does not move with this merge.
- Skill packs: judgement (a pack that sends to a group through `kit.bridge` passes the member ids to mention, or writes an `@name` on the headless path; one that sends direct messages sets `dm=True`; no pack imports `bridge` yet, so nothing breaks)
- `ads.demand/1`: `unit_cost_cny` becomes `unit_cost` with a `currency` beside it (the owner's decision, 2026-10-29, the same as `ads.results/2`): the cost of judging one creative is written in the client's money with its ISO 4217 code (three capitals), whatever that is, never converted, and not at all when the pack does not know the currency. The contract is still `draft` (no consumer reads it from merged code: adcut does not), so it changes in place, with no `/2`; `contracts/ads.demand-1.schema.json` (also in `kit/contracts.d/`) and its example change, and a rule says the figure and its currency go together. `kit.export_demand` writes `unit_cost` and `currency` whenever `Source.currency` is known (before, only a CNY client got a cost field and any other money was said in the note alone), and refuses a `Source.currency` that is not three capitals (`compute_input_invalid` naming `currency`). The note is unchanged. No pack calls `kit.export_demand` yet (video-ads' `export_demand.py` is its own script, which writes `unit_cost_cny` for a CNY client until it moves). Tested in `kit/tests/test_export_demand.py` (the HKD client now gets the figure with its currency, an unknown currency gets neither, the schema holds three capitals and has no `_cny` field, two refusals; five deliberate breaks each fail a case). `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
- Skill packs: judgement (a pack that writes `ads.demand/1` itself -- video-ads -- writes `unit_cost` and `currency` instead of `unit_cost_cny` at its kit move, or calls `kit.export_demand`; nothing reads this contract yet, so nothing breaks)
- `ads.results/2` and `kit.export_results(..., version=)` (the owner's decision, 2026-10-29: the money columns of the results file carry the currency, not a suffix that says CNY; seen once, in the golden comparison, where the `_cny` columns held the ledger's own currency, ROADMAP X11): `contracts/ads.results-2.schema.json` (also in `kit/contracts.d/`) is `ads.results/1` with `spend_cny`, `gmv_cny`, `net_gmv_cny` and `cpa_cny` named `spend`, `gmv`, `net_gmv` and `cpa`, and a required `currency` column after `restated` (ISO 4217, three capitals; every money column of the row is in it; a file may hold more than one currency). It is `draft` until a producer writes it and a consumer reads it from merged code. `ads.results/1` stays `in-use`: adcut uses `spend_cny` in fourteen modules, so the change is a new version and the producer writes both for one release (`contracts/README.md`, rule 3). `kit.export_results` now builds version 2 by default (`KIND, VERSION = "ads.results", 2`) from rows named `spend`, `gmv`, `net_gmv`, `cpa`, with `Source.currency` for the rows that have no `currency` of their own (a row's own wins); `compute(..., version=1)` builds the first contract's file from the same rows: the old names, no `currency` column, and **CNY only**: a row or a Source in another currency is `compute_input_invalid` naming `currency`, instead of written under a name that says CNY. A pack that gives no currency at all gets version 1 exactly as before and is refused by version 2. A currency that is not three capitals is refused by both. The input names of the module changed in the same release it appeared in (0.47.0, a day old): no pack imports it yet (the three `export_*` scripts in video-ads are its own). Tested in `kit/tests/test_export_results.py` (section 6: the Source's currency and a row's own, a file of two currencies, the refusals, version 1 equal to version 2 but for the names and the column, the old file read as `ads.results/1`; fourteen deliberate breaks each fail a case) and `kit/tests/test_contracts.py` (section 3b: the second schema is the first with four columns renamed and one added, no column still says CNY, the currency pattern, the two marks are not read as each other). `ads.demand/1` (`unit_cost_cny`) is not changed here. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
- Skill packs: judgement (a pack that writes `ads.results/1` -- video-ads, Meta -- decides when to write `/2` beside it and passes `Source.currency`; a consumer -- adcut, measurement, creator-program -- reads `/2` (`currency`, `spend`, `gmv`, `net_gmv`, `cpa`) and may stop reading `/1` when no producer writes it; nothing breaks until a producer stops writing `/1`)
- `kit.event_days.from_rows(rows, source, first_row=1)` and `kit.event_catalogue.open_candidates(candidates, confirmed, struck)` (asked by the Meta operator pack's proposal for the event-day pick, playbook issue #238, 2026-10-29; seen once): a pack that keeps its event days as a decision in the client's database, not in `ssot/event_days.tsv`, has no file for `read`. `from_rows` is the same strict reading over rows `[{date, name, kind}]` (a day that is a day, a name and a kind in lower snake_case and text, a date and a name once, no row without its three columns), with the same `registry_file_invalid` naming the source and the row; `read` is now `read_tsv` plus `from_rows` and says exactly what it said (the file's rows are counted from 2). `open_candidates` is the filter every pack would write: the candidates still to ask, in the order given, without one whose name was struck (by name, so for every year) and without one already confirmed (the same name on the same day; a confirmed day of last year does not hide this year's, whose date moved). The catalogue now states, and a test holds, that **a candidate's `name` is its identity and is stable across years** (every market lists the same names in every year of the table), so a strike by name is safe. Where the calendar lives is the pack's choice: the owner's earlier decision was a registry file, the Meta pack proposes a decision in its database (same shape as its campaign kinds); the kit works with either. Tested in `kit/tests/test_event_days.py` and `test_event_catalogue.py`; ten deliberate breaks each fail a case. `kit/VERSION` does not move with this merge (the release train).
- Skill packs: nothing (a pack that keeps its calendar in a database calls `event_days.from_rows`; one that reads the file is unchanged)
- `kit.creative_life.replay(..., read_cost=)` and `kit.compute_life.Source.read_cost` (issue #291, found on 2026-10-28 by reading the replay after the maturity hooks; designed on the issue and decided there; not seen on a real account): a mature creative's 7-day cost per conversion, read on what its unsettled last days will come to. The replay is run on today's numbers, so the last days understate conversions and the 7-day cost rises; three such days in a row were `declining` and recovered when the numbers settled. A pack that wants the estimate hands over a function `window (the last 7 counted days) -> (cost, low, high) | None` (built in a few lines from `kit.maturity`, which `creative_life` cannot import: another pack; `None` leaves the window as seen). With it, a day is `worse` by cost only when the **whole interval** is over the line (`low >= best * (1 + decline_rise)`), an interval that straddles it is not a worse day (it neither counts toward the run nor ends it: the next replay on settled numbers counts it), and the best cost is never set lower than the interval's high edge. The spend rule, the graduation to `mature` and the `doubt` rule stay on what was seen. Without the function every state and move is exactly as before (the golden comparison's life document is still equal to video-ads' field for field). An answer that is not None or `(cost, low, high)` with `low <= cost <= high` is `compute_input_invalid` naming `read_cost`, and so is a `Source.read_cost` that is not a function. Tested in `kit/tests/test_creative_life.py` (section 7: a steady creative is `declining` as seen and `mature` read on the estimate, a rise in settled days and a rise the interval backs are still `declining`, a rise whose interval straddles the line is not, one lucky reading does not make a later steady cost a decline; seven deliberate breaks each fail a case) and `kit/tests/test_compute_life.py`. Still on the tail, for their own changes: `fission.recent`, the pacing efficiency and the `doubt` rule. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
- Skill packs: nothing (a pack that wants the estimate passes `Source.read_cost`, built from its `maturity.Reading`; one that passes nothing is unchanged)
- `kit.human.confirm(..., need_quote=False)`, `CodeRequired.need_quote` and `kit.contract.failure_doc` (seen once, in the Ecommerce SEO skill pack wiring `need_quote` onto its four gate verbs, 2026-10-28): the challenge that precedes a relayed confirm now names `--relay-quote` when the verb needs it. Before, `relay_audit(..., need_quote=True)` refused a relay without `--relay-quote` (`confirm_relay_quote_missing`), but the `next` hint of the `confirm_code_required` challenge ended at `--relay-at <iso_time>`, so an agent following it was refused one step later. A pack passes `need_quote=True` to `confirm()` as well as to `relay_audit()` (it decides per call); `failure_doc` then appends ` --relay-quote <their_words>` to the `next` command. The default is `False` and the document is byte-identical to before (`subject`, `code`, `params` and the other keys do not change). Tested in `kit/tests/test_human.py` and `kit/tests/test_contract.py`. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
- Skill packs: nothing (a pack that passes `need_quote=True` to `relay_audit` also passes it to `confirm` for the same call, so the hint is right; one that does not changes nothing)
- `kit.atomic` `makedirs=` and `write_text_atomic` (seen in the ecommerce-seo pack, whose `_lib/atomic.py` creates the folder before every write; a `mkdir(parents=True, exist_ok=True)` straight before an `atomic.write_*` call is also in creator-program's `export_workbook.py` (3 writes after one mkdir) and sdr's `_lib/export_confirmed.py` (1); outbound's `config.py` hand-rolls the same temp-and-rename): `open_atomic`, `write_json_atomic` and `write_bytes_atomic` take `makedirs: bool = False`; true makes the missing parent folders (`os.makedirs(..., exist_ok=True)`) before the temp file is written, so a pack that writes into a folder that may not exist yet (`raw/pull/<source>/<date>/...`) no longer repeats a `makedirs` line at every call. `write_text_atomic(path, text, *, makedirs=False)` is new. Without the keyword nothing changes: no folder is created and a missing one is still `FileNotFoundError`, so a mistyped path does not build a tree. Tested in `kit/tests/test_atomic.py`. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
- Skill packs: nothing (a pack with its own folder-creating wrapper, ecommerce-seo's `_lib/atomic.py`, replaces it with these calls at its kit move)
- `kit.db.SchemaSpec.extra_triggers` and `with_human(extra_triggers=)` (seen once, in the ecommerce-seo skill pack's move to adoption level L2, 2026-10-28; its own `db.py` holds three hand-written triggers on human tables that `append_only` and `frozen_columns` cannot say: a version never reused, a new row written active with a kind, a text and a source, and a status that only moves active to retired with a reason): `{name: what follows CREATE TRIGGER "name"}` for a rule on a human table. The kit installs it with the generated triggers, puts back a missing or changed one on the next write open, a file made before the rule gets it on its next write open, and `schema_hash` covers it (a spec with none hashes as before, the kit's own pin included). Refused at construction: the name of a generated trigger, a body that is not `BEFORE|AFTER INSERT|UPDATE|DELETE ON <table> ... BEGIN ...; END`, a table that is not a human table, and (in `with_human`) one of the kit's own human tables. A rule the spec stops listing is left in the file: removing one is the pack's own migration. Additive: no spec that does not pass it changes, and `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`). Tested in `kit/tests/test_db.py` [17].
- Skill packs: nothing (a pack with its own triggers on a human table lists them in its spec instead of installing them itself after `connect`; ecommerce-seo is the first)
- `kit.paths.raw_dir()` (seen once, in the Ecommerce SEO skill pack's `SEO_RAW`, which its own `paths.py` resolved beside `SEO_DATA_DIR` and `SEO_DB`; of the 17 sibling `*-skill-pack` checkouts only that one has a raw-folder variable, sdr and creator-program write `<data>/raw` as a literal): `<P>_RAW` is the root of the raw store, a relative value sits under the data dir like `<P>_DB`, a blank one is unset, and the default is `<DATA_DIR>/raw`, which `kit.raw` already fixed (`kit.paths.RAW`, and `kit.raw.RAW` is the same word). `kit.raw.raw_dir(source)` now reads the root from it, so `save`, `import_file`, `listing` and `kit.contracts.read` follow `<P>_RAW` with no change in a pack that never sets it. `paths.resolve()` does not list it (its output, and so every pack's tests that compare it, stay as they were; a pack that wants the root calls `raw_dir()`), and `doctor` reports `<P>_RAW` and warns if it is inside the checkout only when it is set. Note for a pack that had its own resolver: an unset data dir is `SkillPackError(data_dir_unset)` here, where the SEO pack's `paths.py` raised `SystemExit(text)`; the pack catches `SkillPackError` (the kit's CLI already prints it as `--json` or text). Tested in `kit/tests/test_paths.py`, `test_raw.py` and `test_doctor.py`. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
- Skill packs: nothing (a pack that never sets `<P>_RAW` sees no change; the SEO pack, at its kit move, deletes its `scripts/_lib/paths.py` for `kit.paths` and reads `paths.raw_dir()` where it read `SEO_RAW`, and catches `SkillPackError` where it let `SystemExit` through)
- `kit/doctor.py` and `kit.cli.Dispatcher` (seen once, 2026-10-28: the SEO skill pack's own `seo doctor`, `scripts/seo.py`, which answers `doctor` itself because the kit's could not carry what it has: a `--json` document of thirteen keys that its contract says only grows, and a `--health` flag with its own lines): a skill pack may add to doctor without replacing any of it. `doctor.main(..., flags=fn)` (`Dispatcher(doctor_flags=fn)`) calls `fn(parser)` after the kit's three options (`--live`, `--strict`, `--json`), so a skill pack declares its own; declaring one of those again is argparse's own conflict error. What was parsed, the pack's flags included, is `ctx.args` in every check (an empty Namespace when `doctor.collect()` is called with none). A check may store a value as `ctx.extra[key] = value`; `--json` carries it as a top-level key after the kit's, and a key the document already has (`skill_pack`, `live`, `strict`, `checks`, `summary`, `healthy`, `message`, `message_code`) is refused when the document is built: `doctor_extra_key_taken`, one coded failure (exit 2) naming every such key, so a pack's own test of `doctor --json` catches it, a key the kit adds later included. Left out on purpose: a hook for extra text lines (the text report is the findings, each a coded message with its fix in `next`; a pack's health block is a few `info` findings, and what a person must read is not a line only one pack can word), and a hook on the verdict (a pack's own warning already makes `--strict` fail). With no flags and no extras the parser, the findings and the document are the kit's, key for key. Survey, the 16 `*-skill-pack` checkouts at their `origin/main`: 14 route `doctor` through `kit.doctor` with `doctor_checks` only (12 pass an empty list, sdr two checks, video-ads checks and a platform lock) and none adds a flag, a key or a line; 1 (ecommerce-seo) answers `doctor` itself; 1 (cloud-gpu) has no kit and no doctor. So this is one pack's need, held to two small additions and a refusal; a second pack that wants more says so in its own issue. One new code, `doctor_extra_key_taken`, in `kit/message_codes.d/doctor.tsv`. Tested in `kit/tests/test_doctor.py` [11] (defaults unchanged, a flag reaching a check, `--help`, a typo and a repeated kit flag, extra keys and the refusal, text without extras, `--strict`, the Dispatcher). `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`); it is a minor when the train runs.
- Skill packs: judgement (only a pack that answers `doctor` itself: ecommerce-seo can, at its move to L2, route `seo doctor` through the kit by passing `doctor_flags` for `--health`, keeping its thirteen `--json` keys through `ctx.extra`, and turning its health block and its "more than 50 commits behind" line into findings, a warning under `--health` so `--strict` still fails on it; every other pack changes nothing)
- `kit.runner.needs_uv` and `KIT_RUNNER=auto`, `Dispatcher(runner=...)` (seen once, 2026-10-28: the ecommerce-seo skill pack's `scripts/seo.py::_needs_uv`, its story S182: that pack's entry point starts each verb's script itself because `script_cmd` could not choose per script): `KIT_RUNNER` was all or nothing, `uv` ran every script under `uv run`, anything else none. `auto` decides per script: `uv run` only when `needs_uv(script)` says the script has something to install that this interpreter cannot give, this interpreter for the rest (a second interpreter start costs time, and a host without uv still runs every verb that has no dependency); uv missing is this interpreter, as `uv` mode already was. `needs_uv` reads the PEP 723 block (the reference pattern, `tomllib`): true for dependencies, for a `requires-python` this interpreter does not meet (`>=`, `>`, `<=`, `<` over dotted numbers, as in `>=3.11,<3.15`; any other form is left to uv), for no block at all (`uv run` would take the dependencies from the project), and for any block that is repeated, not TOML or unreadable; false for a block with no dependencies and no `requires-python`. `Dispatcher(..., runner="auto")` is that choice made by the pack's entry point instead of by every host's environment; `"uv"` is the other value, any other word raises `ValueError`, None (the default) leaves it to `KIT_RUNNER` and an explicit value wins over the variable. `script_cmd` takes the same keyword. Unset and `uv` give the argv they always gave (`uv run <script> <args>`: the `--quiet --script` flags of the seo pack's own call are not added); `run_json` still reads the variable alone. Survey of the 16 sibling `*-skill-pack` checkouts (15 on main, one on a feature branch), non-vendored `.py` files with a PEP 723 block: 150, of which 25 list dependencies (ecommerce-seo 5 of 46, one of them its entry point; outbound 19 of 20; video-ads 1 of 36, a browser tool a person runs and no verb starts) and 125 do not; only ecommerce-seo's verb scripts mix the two, and the only pack that sets `KIT_RUNNER` is outbound, to `uv` (its CI job and its console), where every verb script has dependencies. Tested in `kit/tests/test_runner.py` (the rule, one row per case, and `script_cmd` with a fake `uv`) and `kit/tests/test_cli.py` ([7], the dispatcher routing through a fake `uv`). `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
- Skill packs: nothing (default behaviour is byte for byte what it was; ecommerce-seo can pass `runner="auto"` when its entry point moves onto `kit.cli.Dispatcher`, and a pack that sets `KIT_RUNNER=uv` because most of its scripts declare dependencies may choose `auto` for the few that do not)

### Other
- `docs/support-channel.md` and `templates/support-channel/` (the owner, 2026-10-30; seen when setting up a further bridge; design [docs/design/bridge-isolation.md](docs/design/bridge-isolation.md)): every bridge sets both `CLAUDE_OPENMAX_CONFIG` and `CLAUDE_OPENMAX_DATA_DIR`, unique per identity, and an identity is resident in one place at a time (read in the plugin's source, not seen to fail; `kit.bridge.check_isolation` enforces the pair); the config example gains `data_dir`; sending and reading back go through `kit.bridge.send_to`; the headless templates put the prompt before `--allowedTools` and name the tool in full (`mcp__plugin_openmax-channel_openmax__comm`; the bare `comm` was refused as not granted, and the old order made the flag swallow the prompt, both seen on 2026-10-30).
- Skill packs: judgement (a pack that copied the headless templates fixes the order and the tool name in its own copy; one that keeps a bridge config adds `data_dir` and gives each identity its own)
- `tools/fleet.py export SKILL_PACK... --out DIR`: each pack's default branch on its remote as plain files, with how far the checkout is behind it and a warning when another remote is ahead; the monthly census (`status`, `consumers.py`) reads those, not the checkouts. 2026-10-30: eight checkouts were behind their remotes (meta-ads by 110 commits) and the census described them, not the packs' mains. `default_branch` falls back to the branch recorded at the last fetch when the server does not answer.
- Skill packs: nothing (the playbook's own tool)
- `tools/fleet.py update` refuses when another remote of the pack has commits on the default branch that the remote it would cut from lacks (a pack whose home moved from GitLab to GitHub while `origin` still names the old server), and names the remote to pass with `--remote`; #316 caught only a local branch that was ahead.
- Skill packs: nothing (the playbook's own tool)
- `tools/fleet.py status` no longer lists as `missing`, nor counts in the verdict, the kit files of a pack the skill pack does not take (`[kit] packs`, decided by `kit/tools/packs.py` as `vendor.py` does): sdr and ecommerce-seo, on four packs each, were told 80 of 84 files were missing or changed since.
- Skill packs: nothing (the playbook's own tool)
- `tools/fleet.py status` read the playbook's history without its merge commits, so a file the playbook had only through a conflict resolution in a merge (the kit's `README.md`, `VERSION` and `packs.tsv` at 0.44.0) was called `local`: nine packs on 0.44.0 were told they had local changes when they had none. It reads merges now (`git log -m`).
- Skill packs: nothing (the playbook's own tool; `fleet.py status` now says `behind` where it said `local changes`)
- `hosts/zylos` 0.4.0 (issue #215, seen on a Zylos host that upgraded a pack about ten times in two days, each time losing the Caddy route until someone pasted it back): post-install and post-upgrade restore the Caddy block pre-uninstall kept, when logins exist and the block is missing. The candidate Caddyfile must pass `caddy validate`, the old one stays as `Caddyfile.before-<name>`, Caddy is reloaded with `pm2 reload caddy`, and the old file is put back if the reload fails; any step that cannot be done leaves the Caddyfile alone and prints the old warning. Tested with a fake `caddy` and `pm2` (restored in the first site block, idempotent, validate failure, reload failure, no saved copy, no site block; two deliberate breaks each fail a case); not yet run under a real Caddy. The pm2 app not restarting by itself after an upgrade is not covered.
- Skill packs: mechanical (copy `hosts/zylos` again into `zylos/`, then upgrade once more to see the route come back)
- `tests/test_changelog.py` fails when a released version's section differs from the one at this branch's merge base with `origin/main`: a release note is never rewritten, and an entry rebased under a version the release created is caught the same way (issue #222).
- Skill packs: nothing (a playbook test only)
- `tools/release.py` (issue #222; the train of `docs/maintaining.md` as one command, so the 2026-11-03 train is not hand-made): sets `kit/VERSION`, moves the `[Unreleased]` heading, regenerates the manifest, runs `tests/test_changelog.py`, prints how many entries ask a skill pack for nothing, a mechanical step or a judgement, and refuses an empty `[Unreleased]`, an entry without its own `- Skill packs:` line, a version that is not above the current one or is already in the file, a second train inside a week without `--urgent` (patch only) and a date before the last release. Three entries already merged lacked their line (the lessons, the adoption row and `mutate.py`); they have it. The pre-push check for a rewritten release note in #222 is not in this change. Test: `tests/test_release.py`, eleven mutants caught
- Skill packs: nothing
- `tools/fleet.py status`: a file the playbook's main changed after a release, with no version bump, is listed `older` with the note "its main changed it since with no version bump (unreleased)" and the copy's verdict is `same version, ... unreleased: the next train carries them`; before, a pack's copy of such a file could read as `local`, which looks like the pack's own edit (found by the SDR skill pack, 2026-10-29, issue #321, last point; the `local` it saw could not be reproduced here with full history, so the case covered is the one where the pack holds the released bytes; a shallow clone of the playbook still cannot tell them apart and says so; test in `tests/test_fleet.py`)
- Skill packs: nothing
- `docs/maintaining.md` "Retiring a pack" (issue #227, from the planned end of video-ads): six steps from "every piece has a home that runs" to archiving, with the pointer release, the roadmap rows that move with their ids, everything that names the old pack, and client data left alone; `docs/portfolio.md` points to it. No test: the first pack that follows it corrects it
- Skill packs: nothing
- `docs/lessons.md`: a lesson on a host that holds the platform credential itself (a client's agent with a connector it calls in a tool call): the pack holds none and has no `pull`, the agent writes the report as a file and `import` reads it, with a freshness check, one standing approval for sharing and a review sheet before the agent installs a pack (seen once, the Meta skill pack, 2026-10-29)
- Skill packs: nothing
- `conformance/check.py` C2 reads the kit doctor's own format (`WARN` marks the warning, the fix is on a `next:` line); before, a pack on the unedited kit doctor could not pass C2 with any adapter, and `INVARIANTS.md` L2 names the skeleton's five entry points (`cli`, `facts`, `decisions`, `pending`, `verbs`) as exempt from "no file has a kit module's name" (found by the SDR skill pack, 2026-10-29, issue #321; tests in `tests/test_conformance.py`; its other two points, an `sdr` adapter and `fleet.py status` saying `local` for a file the playbook moved on, are not in this change)
- Skill packs: nothing
- `console/static/console.css`: the console's default look is now the near-black "tech" one (hairline borders, one cool accent, a glass bar, a glowing dot by the name), the same on every system; it no longer follows the system's light or dark. The light look stays as the same tokens under `data-theme="light"` on `<html>` (nothing sets it yet). Asked by the owner, 2026-10-29, after seeing it in the Amazon PPC skill pack's customer demo; the demo's own stylesheet had measured 4.5:1 or better on every text pair. `test_ui_rules.py` now checks the default and light token sets for completeness and contrast instead of light and dark by system
- Skill packs: mechanical (`python3 tools/fleet.py update`; a pack's console then looks different on its next serve, no pack code reads the colours)
- `tools/fleet.py update`: says which remote and commit it cut the worktree from, takes `--remote NAME` (default `origin`), and refuses when the checkout's own default branch has commits the remote's does not (found by the SDR skill pack, 2026-10-29, issue #316: its `origin` is an archived GitLab remote and the real `main` is on `github`, so the re-vendor commit sat on a stale base and was moved by hand). Nothing is left behind on a refusal. A pack whose local default branch is behind or equal to the remote's is unchanged. Tested in `tests/test_fleet.py` (the line names the base; a stale `origin` is refused and `--remote github` cuts from the real trunk after a fetch; an unknown remote is refused by name; seven deliberate breaks each fail a case).
- Skill packs: nothing
- `tools/adoption.tsv`: the ecommerce-seo-skill-pack row is re-read on its `main` (`1478f65`, 2026-10-29) and stays L1 (target L2), kit 0.46.0 -> 0.47.0: eight of nine modules moved (atomic, cli, human, messages, paths, registry, runner, doctor; its `seo doctor` is `kit.doctor` with its own check and `--health`, the thirteen `--json` keys kept, eight added; playbook PRs 274 and 275), each with a golden diff of 0. Only `scripts/_lib/db.py` is left, which the L2 proof ("no file of its own code has a kit module's name") catches, so L2 is not recorded; its owner keeps the file for now (a primary key for four cache tables, a schema bump and a re-ingest on every host, WAL, the nullable `ranked_history.keyword`). The next step names the two ways out. No kit change.
- Skill packs: nothing
- `tools/mutate.py` (seen every pull request since 2026-10-28: each new rule was checked by hand, a scratch script that breaks one line, runs the test and puts the line back; CLAUDE.md says "no new rule without a check that fails when the rule is broken"): `python3 tools/mutate.py SOURCE MUTANTS --test "CMD"` takes a file of breaks (text to replace, a line `=>>`, its replacement; breaks separated by a line `####`), runs the test command on each broken copy of SOURCE and reports CAUGHT or SURVIVED; exit 0 only when every break was caught. It refuses what would make a pass meaningless: a test command that is red on the unbroken file, a text found twice or not at all, a Python break that does not compile (INVALID, not caught) and a hang (TIMEOUT, not caught). SOURCE is put back byte for byte after every run, on an error, Ctrl-C and SIGTERM too. It is a tool for the person writing a rule, not a suite: nothing runs it in `run_all.py`, and the files of breaks are not kept. Tested in `tests/test_mutate.py` (caught and survivor, exit codes, the bytes restored after a hang and after SIGTERM and SIGINT, six refusals, a non-Python file); run on itself, eleven deliberate breaks of `tools/mutate.py` are each caught.
- Skill packs: nothing
- `.gitattributes` with `CHANGELOG.md merge=union` (seen every time, 2026-10-28 and -29: six open pull requests rebased one after another each conflicted in `CHANGELOG.md`, because each adds its entry at the top of `[Unreleased]`, and each was resolved by hand): git now keeps both sides' lines when two branches add entries in the same place, on `git merge` and `git rebase`. An entry is two lines (the text, then its `- Skill packs:` line) and each side adds them together, so the pairs stay whole. Two limits, stated in `docs/maintaining.md`: GitHub's own merge button ignores the setting (a pull request can still show a conflict there; rebase it locally), and when the release pull request has moved the `[Unreleased]` heading, an entry rebased over it lands silently under the new version where a conflict would have stopped it, so after the train every open pull request is looked at. Tested in `tests/test_changelog.py`: two branches that add entries at the same place merge and rebase without a conflict and keep both pairs, the same merge conflicts without the file, and the file names `CHANGELOG.md`.
- Skill packs: nothing
- `docs/support-channel.md` and `templates/support-channel/` (asked by the Google Ads skill pack, 2026-10-29, and confirmed by the Meta Ads skill pack the same day: two packs): how a pack's agent works with a client's agents through the OpenMax bridge -- one bridge per client organization, where to find it when unknown, headless `claude -p` with only the tool each step needs, send with `comm_send` and one plain string using an ASCII `@name` (the structured form was stored as an empty message once) and read that message back by the id the send returned before saying it was sent, a 10-minute read-only poll with a newest-id cutoff, an agent the client switched off (report once, do not poll), the REST route with a typed body, who to ask and in what order, one ask to the client's lead for real data, no real value in git, and the defect to report to the plugin's maker. A guide and templates only; the send-and-read-back wrapper is a separate change. No client data in it.
- Skill packs: nothing

## [0.47.0] - 2026-10-28

### Kit
- `kit/compute_campaign.py` (pack `ads-core`; issue #252, from the video-ads skill pack's `scripts/compute_campaign.py`, cut from its main): the part between a pack's tables and `kit.lifecycle`, which the hand-over plan called a thin verb and which is 328 lines and names no platform. The pack's adapter reads its own tables into a `Source` (campaigns with their budgets, the days each spent, which ads have issues, the creatives' states, the doubt line, its registry of campaign kinds) and `compute_campaign.compute(read_at, k, market=...)` returns the `--json` document: the state and reason of every campaign, its budget and where it came from, the benchmark of its kind or of the account's other judged campaigns, the hold across the last weekly readings (`raw_state`, `pending`), and the proposals with their coded sentences. `Source` is checked first: a part missing or mis-shaped is `compute_input_invalid`, naming the part, and a market with no complete day is `campaign_no_data`. The pack adds its own `meta`. Its 12 codes are `campaign_*` and `compute_input_invalid` rows in `kit/message_codes.d/compute_campaign.tsv` (English and Simplified Chinese; the source's wording named the platform's Insights). The same synthetic fixture through video-ads' verb at origin/main and through this module gives the same document (states, reasons, windows, benchmarks, holds, proposals), but for four things: `status` reads as the pack's word (`lifecycle.ACTIVE` is `active`), the budget's `basis` for a campaign without its own is `ad groups` where it said `ad sets`, `meta` is the pack's, and the `campaign_thresholds_draft` warning also names `campaign_min_conversions` and `campaign_end_idle_days`. The other documents (`allocate`, `pacing`, `life`, `portfolio`, `review`, the three exports) follow one at a time. Tested in `kit/tests/test_compute_campaign.py`.
  - For a skill pack: judgement (only a pack that runs ads: video-ads, at its kit move, keeps its SQL and its Smartly mapping as `read_at`, maps the platform's delivery status to `lifecycle.ACTIVE`/`DISAPPROVED` and `has_issue`, deletes its `compute_campaign.py` and `_lib/campaign.py` and the `campaign_*` message rows this fragment now defines (a code defined twice refuses to load), and reads `campaign_min_conversions` and `campaign_end_idle_days` (#251); meta-ads writes only `read_at` over its own tables)
- `kit/constants.d/*.tsv` and `kit.registry.Thresholds` (issue #251, seen in video-ads, which holds 111 threshold rows, and in meta-ads, which holds 4): the engines' own default thresholds ship with the kit, one file per module (`lifecycle`, `allocation`, `audit`, `pacing`, `reconcile` in `ads-core`; `creative_life`, `creative_demand`, `fission` in `creative`; 57 rows), and travel with the pack that holds the module (`kit.tools.packs.module_of`). `Thresholds()` reads them first and the skill pack's `ssot/constants.tsv` replaces a row by name (the whole row), so a skill pack lists only what it changed; `Thresholds(defaults=())` reads the skill pack's file alone, and a default file with no `label_<lang>` of a pack language reads its English one. `Thresholds.origin(name)` says `kit`, `pack over kit` or `pack`, and `facts list --thresholds` carries it. Each row's `reads` names the engine parameter it feeds; a row's default equals the engine's default in code where there is one (`allocation_evidence_z` is 1.64, the engine's, where video-ads confirmed 1.0: it keeps its row as an override), and the thresholds an engine's `Params` needs from the pack's own tables (`reach_impressions`, `doubt_spend`, `weak_signal`) come with the compute that derives them. The campaign engines get their own two names, `campaign_min_conversions` and `campaign_end_idle_days` (3 and 14, as the two `life_*` rows they shared with the creative engine), so `ads-core` needs nothing from `creative`. Tested in `kit/tests/test_constants_d.py` (every row is read by an engine, every parameter without a default in code has a row, the defaults agree) and `kit/tests/test_registry.py`.
  - For a skill pack: judgement (only a pack that takes `ads-core` or `creative`: a name it already lists keeps its own row, so nothing changes in what runs; delete the rows that equal the kit's, keep the ones that differ; read `campaign_min_conversions` and `campaign_end_idle_days` for the campaign engines in place of the two `life_*` rows, moving a client's confirmed `threshold_life_min_conversions_for_cost` or `threshold_life_end_idle_days` to them if it differs from 3 and 14; a test that counts `Thresholds().names()` now counts the kit's rows too)
- `kit.registry.FactKeys` and `kit.facts` (issue #254, seen once in a Meta operator pack and a client hub, 2026-10-28): a pack's `ssot/fact_keys.tsv` may carry an optional `owner` column, `pack` (the default) or `hub`; any other word is `registry_file_invalid`, and `FactKeys.hub_owned()` lists the hub's keys. A hub key keeps its definition in the pack's file (so `kit.guards.hub_keys` still checks it against the hub's and `facts sync-hub` still copies only declared keys) and is read like any other; while a hub is in force (`<P>_HUB_DIR`) `facts set`, `confirm`, `rollback` and the init question refuse it with `fact_hub_owned`, naming the hub's `facts set` and `facts sync-hub`, and with no hub it is an ordinary key. Before, the break-even return `npr_roas`, which the hub requires, was "unknown, nothing reads it" in a pack that did not list it, and a pack that did list it could confirm its own value beside the hub's. A key the hub defines and the pack does not list is now refused as `fact_key_hub_undeclared` ("add its row, with owner = hub") when a hub is in force, where it was `fact_key_unknown`. Two rows in `kit/message_codes.d/facts.tsv`. Tested in `kit/tests/test_hub_owned.py`. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: nothing (a pack that reads a hub key adds `owner = hub` to its row, or lists the key with it; video-ads' `npr_roas` is the first)
- `kit/constants.d/wallets.tsv` (issue #262, seen in the Meta operator pack on a real account, 2026-10-28): the ad group's wallet gets its own default rows, `adgroup_learning_days` 7, `adgroup_window_days` 14, `adgroup_judge_spend` 100, `adgroup_min_conversions` 3, `adgroup_end_idle_days` 14, each read by the matching `wallets.Params` field. Before, the five fields of `wallets.Params` were fed by the *campaign* rows (`campaign_window_days`, `campaign_learning_days`, `campaign_judge_spend_multiple`, `campaign_min_conversions`, `campaign_end_idle_days`), and a pack that judged its ad groups with a campaign's judging spend (ten times the doubt line) found every ad group "unjudged": all of them spent from the exploration wallet and none from performance. The ad group is the unit of the wallet and spends 20 to 50 a day, so its judging spend is a number of its own. Those five campaign rows now read `lifecycle.Params` only. `adgroup_judge_spend` is in the account's currency, so a pack in a currency far from 1 to 1 sets it (a draft until a person confirms it, like every row here). Tested in `kit/tests/test_wallets.py` (a group of 20 a day for 14 days with 4 conversions is `perform`, with 1 conversion `explore`) and `kit/tests/test_constants_d.py`. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that calls `wallets.judge`: video-ads and the Meta operator pack read the five `adgroup_*` names in place of any campaign row or number they passed it; a name a pack already lists keeps its own row)
- `kit.pacing.plan` takes an exploration band, `explore_min_share` and `explore_max_share` (issue #263, seen in the Meta operator's design review with its owner, 2026-10-28), fed by two new rows in `constants.d/pacing.tsv`, `pacing_explore_min_share` 0 and `pacing_explore_max_share` 1. Before, performance was what the month's result still needed and exploration the rest, so a month behind its result starved exploration to nothing and one ahead put almost the whole day into it. Now the day's exploration money is clipped into the band; a clipped day carries `explore_clip` (`explore_floor` or `explore_cap`), the floor also `perform_given_up` (the performance need it took the money from), and the plan's `flags` name each. The defaults are no band, so a pack that sets nothing gets the plan it had (the documents differ by no key). The kit ships no share on purpose: practitioners keep testing a minority of spend, mostly 10 to 30 %, and the sources disagree. The cap moves money to performance only when there is a proven efficiency to spend it at (with none the day stays in exploration and `no_performance` says why). A band that is not `0 <= min <= max <= 1` is a `ValueError`. Tested in `kit/tests/test_pacing.py`. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: nothing (a pack that wants a band reads the two rows and passes them to `pacing.plan`; one that passes nothing is unchanged)
- `kit.allocation.Params.weekly_step_cap` (issue #264, seen in the Meta operator's design review, 2026-10-28; practitioners' account, unconfirmed against any platform: budget edits that add up past about 20 % in a week reset a campaign's learning): `day` keeps a campaign's budget within that share of what it was before its earliest move of the last 7 days (`weekly_room`), so a step that is safe per move is also safe per week. The week's room tightens the campaign's box *before* the money is solved, so the money still adds up across campaigns; a move the cap shortened carries `weekly_cap: True`, and `held_reason` answers `weekly_cap` when the evidence points a way the room no longer allows. A budget already outside the band (the cap set late) may only come back. The field defaults to `None` and the kit ships no figure (no `constants.d` row: a row needs a number, and the platform's rule is unconfirmed), so a pack that sets nothing gets exactly the moves it had; a pack that wants a cap sets `weekly_step_cap` from its own row. The cap bounds the net compounded change, not the sum of absolute steps: a rise then a fall inside a week nets out. Tested in `kit/tests/test_allocation.py`. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: nothing (a pack that wants the cap passes `weekly_step_cap`, and may show `weekly_cap` in its words; one that passes nothing is unchanged)
- `kit/event_days.py` (pack `ads-core`) and `pacing.plan(event_days=...)` (issue #265, seen in the video-ads skill pack's `docs/budget.md`, "Promotions and big sales days are not read yet", and in the Meta operator's design review, 2026-10-28; owner's decision 2026-10-28: a registry file, not a fact): a pack keeps its event-day calendar in `ssot/event_days.tsv` (`date`, `name`, `kind`; a date is an ISO day, a name and a kind lower snake_case, a date and name once) and reads it with `event_days.read(path)`, strictly (`registry_file_invalid` naming the row; `registry_file_missing` for no file). `event_days.is_event()` is the predicate `kit.alerts.without_event_days` already takes. `pacing.weekday_weights` and `pacing.plan` take the days as a set: they are left out of the weekday weights (and do not count toward `min_weeks`), and an event day of the month is planned at its weekday's weight times the lift the account's earlier event days showed (spend over the mean ordinary day of that weekday, or over the mean ordinary day while the weights are flat), reported as `event_lift` and `event_lift_days`; each such row has `event: true`. With no earlier event day that spent it is planned as an ordinary day and the flag `event_no_history` says so. With no event days (the default) the plan is what it was, with no new key. The lift ignores how long ago an event was and takes the plain mean of the earlier ones. Tested in `kit/tests/test_event_days.py` and `kit/tests/test_pacing.py`. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: nothing (a pack that wants event days keeps the file and passes `event_days.days(event_days.read(path))` to `pacing.plan`, and `event_days.is_event(...)` to `alerts.without_event_days`; one that passes nothing is unchanged)
- `kit/event_catalogue.py` (pack `ads-core`; owner's remark, 2026-10-28: the public event days of the world are few and can be collected before a client picks them): `candidates(market, year)` and `for_markets(markets, year)` list, in date order, the public events a market's client may pick its event days from, and `rows()` turns the ones a person kept into the rows of `ssot/event_days.tsv` that `kit.event_days.read` takes. 25 events, each with a `basis`: `fixed` (a calendar day: New Year, Valentine's Day, Women's Day, White Day, the double-digit days 3.3 to 10.10 and 12.12 of the south-east Asian markets, Singles' Day, Christmas, Boxing Day, the 6.18 day), `rule` (Easter by the computus and the days counted from it, Mothering Sunday, Mother's and Father's Day, Thanksgiving, Black Friday and Cyber Monday) or `table` (Lunar New Year, 2026 to 2030 only: a year outside the table has no such candidate, never a guess). The markets are ISO 3166-1 alpha-2 codes; a market not listed, or none, gets the events public everywhere. A candidate is a proposal, not a fact: a client may not run a sale on it, and the pack puts the list to the client to confirm or strike. Left out on purpose: a sale a platform schedules itself (announced late and named for the platform, which the kit does not name) and a client's own promotions or paydays, which go in the file by hand. Tested in `kit/tests/test_event_catalogue.py` against dates worked out from the calendar rule. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: nothing (a pack that wants the list reads `event_catalogue.for_markets(<the client's market codes>, <year>)`, shows it for the client to keep or strike, and writes what was kept with `event_catalogue.rows()`)
- `kit/compute_pacing.py` (pack `ads-core`; issue #260, the first of the remaining compute documents, from the video-ads skill pack's `scripts/compute_pacing.py`, cut from its main): the part between a pack's tables and `kit.pacing` and `kit.wallets`. The pack reads its own tables into a `Source` (the month and the two targets with where they came from, the account's complete days, each creative's paid wallet, ad group and last 7 days' spend and conversions, each ad group's days and whether it delivers, optionally event days) and prints what `compute(src, k)` returns: `{month, inputs, last_day, plan, wallets_now, efficiency, ad_groups, warnings, warning_codes}`. A `Source` the rules cannot read is refused as `compute_input_invalid` naming the part. Seven message codes in `kit/message_codes.d/compute_pacing.tsv` (`pacing_no_data`, `pacing_no_target`, `pacing_flat`, `pacing_no_performance`, `pacing_shortfall`, `pacing_result_met`, `pacing_no_days_left`), one row `pacing_min_conversions` 3 in `constants.d/pacing.tsv`. Differences from video-ads' document, named: (1) no `creative_demand` and no `meta`: demand is its own document (the last of #260's list) and `meta` is the pack's; (2) the ad groups are judged by the `adgroup_*` rows (#262), where video-ads judged them with the campaign rows and a doubt-line multiple, and so an account with no known doubt line no longer has every ad group left unjudged; (3) the efficiency floor is `pacing_min_conversions`, where video-ads read `life_min_conversions_for_cost` (the same 3, but a creative-pack row that an `ads-core`-only pack does not have); (4) the pack hands over each creative's wallet and not its state, because `ads-core` imports no other pack (the pack maps state to wallet with `creative_life.WALLET`); (5) a bad month or a day outside it is `compute_input_invalid` naming `month` or `day`, where video-ads had `pacing_month_invalid` and `pacing_day_outside` for its command line, and the kit's warnings do not name a decision or a flag; (6) with no complete day there is no month (the kit reads no clock), where video-ads named today's; (7) what #263 and #265 add (the exploration band, event days) reaches the plan, and changes nothing while unset. The day's page (`kit.daily_page`) names `pacing_no_target` as a note: it now reads the kit's sentence for that code, which no longer names a decision or a flag (`kit/tests/test_daily_page.py` follows). Its test is video-ads' document cases over an invented account, with the numbers worked out by hand; the golden comparison with video-ads' own document is run at its re-vendor. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that runs ads: video-ads, at its kit move, keeps its SQL and its decisions as `read_at`, maps each creative's state to `creative_life.WALLET`, deletes its `compute_pacing.py` aggregation and the `pacing_*` rows this fragment now defines except `pacing_month_invalid`, `pacing_day_outside` and the demand ones (a code defined twice refuses to load), and keeps `creative_demand` until the kit has it)
- `kit/compute_life.py` (pack `creative`; issue #260, the second remaining compute document, from the video-ads skill pack's `scripts/compute_life.py`, `_lib/life_data.py` (`derive`, `pad_off_tail`) and `_lib/life_view.py`, cut from its main): the part between a pack's tables and `kit.creative_life`. The pack reads its own tables into a `Source` (each creative's `creative_life.Day`s, and optionally its label, ad group, accounts, entities, whether the platform still runs it, and a person's dated overrides) and prints what `compute(src, k)` returns: `{as_of, counts, params, rows, summary, by_entity, wallets, window_days, warnings, warning_codes}`, optionally filtered by state, creative (id or label), entity or account. `derive()` is the thresholds that are rules over the account's own history (the reach a creative needs to have found its people, the doubt line, the weak-signal cut), each with a cold start when the history is short and each saying which it used; a short history is a coded warning, never a guess. A `Source` the rules cannot read is `compute_input_invalid` naming the part. Four message codes in `kit/message_codes.d/compute_life.tsv` (`life_move`, `life_history_insufficient`, `life_doubt_unknown`, `life_no_creatives`) and seven rows in `constants.d/creative_life.tsv` that feed `derive` (`life_history_min_creatives` 10, `life_reach_cold` 1000, `life_reach_min` 300, `life_reach_max` 2000, `life_reach_floor_share` 0.20, `life_doubt_multiple` 2, `life_weak_percentile` 10: video-ads' values, which its owner confirmed on 2026-10-17). Differences from video-ads' document, named: (1) one source per document and no `sources` list: a pack that reads two platforms' tables calls it once for each, because their histories differ, and `counts` replaces `sources`; (2) `spend7` and `conv7` stay on each row, where video-ads popped them, because `kit.compute_pacing` reads them; each row also carries the `group` the pack gave; (3) the pack reads its own tables, applies its own `until` to them, and says whether a creative is still run (`off`), where video-ads read a platform's status words; (4) `life_until_invalid` and `life_needs_ingest` stay in the pack (a command line and a cache's shape); (5) rows with equal state and spend are ordered by creative id, where video-ads left them in reading order; (6) the Chinese meanings of the four codes are Simplified (R7), where video-ads' are Traditional; (7) a person's overrides can be handed over (the rule already took them; video-ads' document passed none). Its test is video-ads' document cases over an invented account, with the derived numbers worked out by hand; the golden comparison with video-ads' own document is run at its re-vendor. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that runs creatives: video-ads, at its kit move, keeps its two readers and its status words as `read_at`, calls `compute_life.compute` once for each, deletes its `_lib/life_data.py` `derive` and `pad_off_tail`, its `_lib/life_view.py` aggregation, the `life_*` rows this change defines (the seven thresholds, if equal) and the `life_move`, `life_history_insufficient`, `life_doubt_unknown` and `life_no_creatives` message rows (a code defined twice refuses to load); the Meta operator pack reads `rows[].wallet`, `spend7` and `conv7` into the pacing document)
- `kit/compute_allocate.py` (pack `ads-core`; issue #260, the third remaining compute document, from the video-ads skill pack's `scripts/compute_allocate.py`, cut from its main): the replay of the performance wallet's split across campaigns day by day (the evidence bar calibrated over a grid of seven, the same run with the acceleration off), and with `propose` tomorrow's moves from the campaigns' real budgets, each with its marginal return and interval, the doubt behind it, the platform's range applied, the money not placed, why a campaign in the wallet has no move, and what became of the advice recorded earlier. The elasticity is estimated from each campaign's own days and shrunk toward the pooled value (`kit.allocation`). The pack reads its tables into a `Source` (the campaigns' structure and days in the shape `compute_campaign` has them, their states over the weeks as dated series, the budget history, the platform's range, the recorded advice) and prints `compute(src, k, days=56, propose=False)`. A `Source` the rules cannot read is `compute_input_invalid` naming the part. Two message codes in `kit/message_codes.d/compute_allocate.tsv` (`allocate_replay_only`, `allocate_proposal_draft`; `campaign_thresholds_draft` is the campaign document's) and three rows in `constants.d/allocation.tsv` (`allocation_flip_target` 0.10, `allocation_calibration_min_moves` 5, `allocation_follow_days` 7: video-ads' values). Differences from video-ads' document, named: (1) no `market` and no `meta`: the pack's; (2) the pack hands over the campaigns' states as a series per campaign (from `compute_campaign.timeline`, three lines) where video-ads called its own timeline, and keeps the log of recorded advice and its `export allocation` verb, handing over its records; (3) a campaign with no complete day is `compute_input_invalid` naming `as_of`, where video-ads refused with `campaign_no_data`; (4) the base evidence bar is the row in effect: the kit's `allocation_evidence_z` is 1.64 (the engine's default) where video-ads' own row is 1.0, so video-ads keeps its row and the grid brackets both; (5) `weekly_step_cap` (#264) may be passed for a run, and the proposal's carried campaigns bring their replayed moves at the real budget's scale for it, which changes nothing while it is unset; (6) campaigns with an equal starting budget are ordered by id; (7) a campaign's status is `lifecycle.ACTIVE`, another word or None. Its test is video-ads' document cases over two invented campaigns whose response to money differs, on invariants (the money of the wallet constant, no step over the one in force, the cooldown kept, the better campaign ahead) and on cases worked out by hand; the golden comparison with video-ads' own document is run at its re-vendor. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that runs ads: video-ads, at its kit move, keeps its SQL and its record of advice as `read_at`, builds `states` from the campaign timeline, deletes its `compute_allocate.py` aggregation and the `allocate_*` message rows this fragment now defines (a code defined twice refuses to load), and its three `allocation_*` rows if equal to the kit's; the Meta operator pack reads `proposal.moves` with their evidence into its queue and writes nothing to a platform)
- `kit/compute_portfolio.py` (pack `creative`; issue #260, the fourth remaining compute document, from the video-ads skill pack's `scripts/compute_portfolio.py`, cut from its main): all the creatives at once. How many are in each state (with the last 7 days' spend and conversions and the mean age in the state), how long the performance ones will keep earning (each creative's 7-day trend, a daily factor, the projection over `horizon` days and its half-life), whether the month still reaches its result if nothing new enters, and how many new creatives closing the gap would take and by when. A warning and a proposal, never a floor. The pack hands over a `Source` wrapping the life document's (`compute_life.Source`: the creatives' days) with the month and the month's result, and prints `compute(src, k, horizon=84)`; the module runs the life document itself (the states, the wallets, the history of becoming mature) and the rules are `kit.creative_portfolio`'s. A `Source` the rules cannot read is `compute_input_invalid` naming the part (a month, a result, a horizon outside 7 to 365 days, or a creative's days). Four message codes in `kit/message_codes.d/compute_portfolio.tsv` (`portfolio_gap`, `portfolio_too_late`, `portfolio_history_insufficient`, `portfolio_no_performance`). Differences from video-ads' document, named: (1) no `meta`: the pack's; (2) one source (see `compute_life`), so a pack that reads two platforms' tables calls it once for each; (3) the warnings of the life document (a short history deriving the thresholds) are kept, as video-ads' were, and with no creative at all the life document's `life_no_creatives` is kept too, where video-ads' portfolio said only `portfolio_no_performance`; (4) a bad month or horizon is `compute_input_invalid` naming `month` or `horizon`, where video-ads had `pacing_month_invalid` and `portfolio_horizon_invalid` for its command line; (5) with no complete day there is no month and no month view (the kit reads no clock), where video-ads named today's month; (6) the Chinese meanings are Simplified (R7), where video-ads' are Traditional. Its test is video-ads' document cases over an invented account, with the numbers worked out by hand (six earners at 3 a day over 31 days, a gap of 1,442, 20 mature and 40 new creatives to close it); the golden comparison with video-ads' own document is run at its re-vendor. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that runs creatives: video-ads, at its kit move, builds the same `compute_life.Source` it builds for the life document and adds its month and result, deletes its `compute_portfolio.py` aggregation and the `portfolio_*` message rows this fragment now defines, except `portfolio_horizon_invalid` (a command-line code; a code defined twice refuses to load))
- `kit/compute_review.py` (pack `creative`; issue #260, the fifth remaining compute document, from the video-ads skill pack's `scripts/compute_review.py`, cut from its main): the week of the creatives, for the people who read the feedback. A view of what the life document, the fission score and the demand already say, never a contract file. Every state change inside the last `days` complete days (newest first, each with its coded message), the states now (and by entity), what the creatives that did not work say (parked and ended by their reason: `low_reach` is "the platform never showed it", `no_conversion` is "shown and nobody bought"), the creatives that have a fission score (highest first) and the others counted by state, and the demand block. The pack hands over a `Source` wrapping the life document's (`compute_life.Source`) and, if it has one, the demand block of its pacing document, and prints `compute(src, k, days=7)`; the module runs the life document itself and the scores are `kit.fission`'s. A `Source` the rules cannot read is `compute_input_invalid` naming the part (days under 1, a demand that is not a block, or a creative's days). No new message code: `life_move` and `life_no_creatives` are the life document's. Differences from video-ads' document, named: (1) no `meta`: the pack's; (2) the demand block is handed over, not computed: video-ads' review ran its own pacing document for it, and the kit's pacing document has no demand yet (it is the last document of #260), so a pack passes the block its pacing gave, or None; (3) one source (see `compute_life`), so a pack that reads two platforms' tables calls it once for each; (4) the cut at `--until` is the life `Source`'s `until`; (5) a move also carries the `read` the rule took it on; (6) a bad `--days` is `compute_input_invalid` naming `days`, where video-ads had `review_days_invalid` for its command line; (7) the life document's warnings are kept, as video-ads' were. Its test is video-ads' document cases over an invented account, with the scores and the window edges worked out by hand (four winners that are each other's benchmark score 0.5 each; the day of the last move is in the window at exactly the days that reach it); the golden comparison with video-ads' own document is run at its re-vendor. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that runs creatives: video-ads, at its kit move, builds the same `compute_life.Source` it builds for the life document, passes the demand block of its pacing document, draws its page from the document, and deletes its `compute_review.py` aggregation; `review_days_invalid` stays in the pack as a command-line code)
- `kit.compute_life`: a row's `spend7` is no longer rounded to the cent (found by running video-ads' own `compute life` and `compute pacing` and the kit's on one synthetic account, 2026-10-28; the kit is not yet released with `compute_life`, so no skill pack has seen the rounded one). The life document's rows feed the pacing document (`spend7`, `conv7`), and the wallets sum them: rounding each creative's seven days to the cent and then adding gave `wallets.other` 315.00 where video-ads has 314.99, and an efficiency that differed from video-ads' in the seventh digit. Now `spend7` and `conv7` are the sums of the days, and the wallets are rounded once, after the sum. Tested in `kit/tests/test_compute_life.py` (three creatives of 0.028 each are 0.08 in the wallet, not 0.09). `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: nothing (no skill pack reads `compute_life` before 0.47.0)
- `kit.allocation.budget_at` no longer divides by zero when a campaign's elasticity is 1 (found 2026-10-28 by running video-ads' own `compute allocate` and the kit's on one synthetic account: video-ads' command failed with `division by zero`, and so did the kit's, which is the same code). `shrink` holds an elasticity reading at or above 1 at exactly `e_max`, 1.0 by default (a proportional response), and the budget at a given marginal return, `b (m / level)^(1 / (1 - e))`, is undefined there: any campaign whose days read as responding at least in proportion to spend, on any day of the replay, stopped the whole document, and so would have stopped a proposal. The elasticity is now read as at most `E_CEILING` (0.999) in that formula, and a budget too large to represent is infinite (the boxes in `solve` clip it). Below the ceiling nothing changes, and a campaign at the bound is not made to pay for it: its marginal return is the common level by construction, so there is no evidence to move it. Tested in `kit/tests/test_allocation.py` and, at the document, `kit/tests/test_compute_allocate.py`; both fail with the `ZeroDivisionError` without the change. With this fix the allocation document equals video-ads' on the golden comparison's account, replay and proposal, at six replay lengths. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: mechanical (video-ads' own `_lib/allocation.py` has the same defect until it moves to the kit's; a skill pack that calls `allocation.day` gets the fix by re-vendoring)
- `kit/compute_demand.py` (pack `creative`; issue #260, the last of the remaining compute documents, from the `creative_demand` block of the video-ads skill pack's pacing document, `scripts/compute_pacing.py` `_demand`, cut from its main): how many creatives to ask the creative maker for. The request follows the exploration money of the pacing plan: what a verdict costs is measured from the creatives' own history (shrunk toward the doubt line while few), how long a verdict takes and how long a request takes to reach a first spend are measured too, and the request is the number of unknown creatives that money can still carry to a verdict, in whole batches, inside the platform's range, with a diagnosis of whether the exploration money can replace what the proven creatives will lose. The pack hands over a `Source` wrapping the life document's (`compute_life.Source`) with the pacing document's `plan` and `creative_wallets`, the ad groups' days (for when a request reached an ad group), its record of earlier requests and the platform's range, and prints `compute(src, k)`: `{month, demand, warnings, warning_codes}`; `kit.compute_review` takes the `demand` block as it is. A `Source` the rules cannot read is `compute_input_invalid` naming the part. Four message codes in `kit/message_codes.d/compute_demand.tsv` (`pacing_demand_unknown`, `pacing_limit_binds`, `pacing_money_limited`, `pacing_surplus`, under the names video-ads gave them). **`kit.compute_pacing` also says, as `creative_wallets`, which wallet pays each creative** once its ad group has had its say: the demand document needs it, `ads-core` cannot be imported by `creative`, and a pack could not rebuild it; a pack that read the pacing document sees one new key. Differences from video-ads' block, named: (1) it is a document of its own, not a key of the pacing document, because the engine is in the `creative` pack and the plan in `ads-core`; (2) the plan, the wallets, the earlier requests, the ad groups' days and the platform's range are handed over, where video-ads read its request log and facts itself; (3) with no plan (no spend target) `demand` is None and the month is None; (4) the Chinese meanings are Simplified (R7). Its test is video-ads' cases over an invented account; and on the golden comparison's account the kit's block equals video-ads' `creative_demand` field for field in six scenarios (no earlier request; two requests, one answered by an ad group's first spend after 13 days and one still in production; the platform's minimum and maximum binding; a lead time measured at 53 days), warnings included. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that runs creatives: video-ads, at its kit move, keeps its request log and its facts as the hand-over, calls `compute_demand.compute` after `compute_pacing.compute` and puts the block back under `creative_demand` if it wants its old document's shape, deletes its `_demand` and the four `pacing_*` demand message rows this fragment now defines (a code defined twice refuses to load); the Meta operator pack passes the block to the review document)
- `kit/maturity.py` (pack `ads-core`; issue #267, seen on a real account by the Meta operator, 2026-10-28: the last seven days returned 1.45 against 2.27 over ninety, and nothing said whether that was a fall or an immature tail; also video-ads' `docs/budget.md`): how much of a day's final number is visible at each age, and what a recent day will come to. A platform's number for a day keeps moving until its attribution window has passed, so every recent day is understated and every window that includes one mixes settled and unsettled days. `fit(observations, window, prior, params, kind)` fits `F(age)`, a truncated exponential or a Weibull, from rows `(key, day, observed_at, spend, count, value)` where the same day is seen at several ages (counts and value apart): the ratios of the earlier numbers to the final, weighted by the final's orders, trimmed of gross outliers, pooled across keys, with a standard error that counts each `(key, day)` once, shrunk toward a cold-start `tau` per window by precision (as `kit.allocation.shrink` does); under `maturity_min_pairs` pairs or `maturity_min_ages` ages the curve is the prior and says `prior_only`; `family="auto"` keeps the exponential unless a Weibull beats it on keys held out. `adjust(days, as_of, count_curve, value_curve)` reads each day as `x / F(age)` with a prediction interval, `summarize` gives a window's estimated return with its interval and `immature` below `maturity_immature_share`, and `judge(window, threshold)` returns `above`, `below` or `undecided_immature` (an immature window whose interval straddles the threshold is never given a verdict; it has no number of its own). `refit`, `drift` (the lag moved by more than `maturity_drift_se` standard errors) and `stale` (older than `maturity_refit_days`) are pure: the kit schedules nothing. `Curve.from_windows` builds a prior from the same days counted under different attribution windows (unverified against any platform). Eleven rows in `constants.d/maturity.tsv`, one message code (`maturity_bad_observation`), the page `docs/maturity.md` (the model, the fit, the interval, what a pack hands over, what breaks it). Decisions made against the synthetic world, said in the page: a symmetric robust loss (Huber) on the raw error biased the curve by 0.7 % because near full maturity a ratio cannot exceed 1, so robustness acts on the error standardised by the binomial and trims only gross outliers; the pairs of one `(key, day)` are one draw, so the standard error clusters on it; a value's remainder scatters more than the binomial says (orders of unequal worth), so the curve carries a measured `dispersion`; a refund is clipped to a ratio of 1 and counted, not refused; a negative number, an unreadable day or an observation before its day is refused. Tested in `kit/tests/test_maturity.py` (41 cases, 4 seconds, on a synthetic world with a known lag; the brief's eight cases: the fit finds the truth and narrows with data; count and value fitted apart; a day seen at age 2 has its true final inside the 90 % interval 91 % (count) and 89 % (value) of 200 runs; no data and one pair give the prior; few pairs sit between prior and data, many follow the data; a day at the window is its own final, a refund is clipped; a drift fires when the lag doubles and a curve goes stale; an interval straddling a threshold is undecided while the same window matured is decided); four mutations of the module (no dispersion, no trim, pairs treated as independent, no shrinkage) each make a test fail. The hooks are not in this change: `kit.lifecycle`, `kit.alerts` and `compute_campaign` do not read an estimate yet. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: nothing (no skill pack calls `maturity` yet; a pack that wants it keeps a table of every export with the time it was taken, rebuilds it from raw, fits weekly and stores the curves with their `fitted_on`)
- The maturity hooks (issue #267, after `kit/maturity.py`): `kit.lifecycle`, `kit.compute_campaign` and `kit.alerts` read a window on the estimate when they are given a `maturity.Reading` (the two curves, the date the days were taken, the parameters), and give no verdict the interval cannot back. `lifecycle.windows(days, as_of, p, reading)` adds each window's `matured` reading; `lifecycle.judge(..., reading)` decides a rule on an immature window's return only when the whole interval is on one side of its threshold, and otherwise returns state `unjudged` with the reason `immature` (an existing state, so `STATES` is unchanged and `hold` treats it as it treats `unjudged`); the evidence gates (enough spend, enough conversions) stay on what was seen. `compute_campaign.Source.maturity` (its `observed_on` must be after `as_of`, else `compute_input_invalid` naming `maturity.observed_on`) builds the benchmark from the other campaigns' estimated revenue, adds `window.matured` to each campaign, a `maturity` block to the document, and warns `campaign_maturity_prior_only` for a curve that is only the cold start. `alerts.check(..., reading=...)` reads a *return* on the current day's estimate: it fires only when the whole interval is on the firing side of `threshold x baseline`, is silent only when none of it is, and otherwise has no verdict (`immature_undecided`); an unsettled day with no `orders` is `orders_unknown`; `alerts.Point` gains an optional `orders`. `maturity` gains `Reading`, `window_reading` and `day_reading`. Without a reading all three are exactly as they were: the existing tests are unchanged and pass, and on the golden account the campaign document with no reading equals video-ads' `compute campaign` field for field but the word `ad groups` for its `ad sets` (a comparison made for the first time here; the warning `life_history_insufficient` comes from the pack's life reading and is the pack's to pass). **Not done on purpose: `kit.creative_life`'s cost reading** (its replay on today's numbers understates the last days, which its "declining" rule can read as a fall: filed as an issue, because it changes a state machine's replay); its conversion counts for graduation stay observed. Tested in `kit/tests/test_maturity_hooks.py` (29 cases: days generated as the truth times the share visible at their age, so the estimate must come back as the truth; a campaign whose true return is the benchmark is `lagging` on its understated 3.29 without a reading and `unjudged/immature` with one, while a campaign at 1.0 is still `lagging` and one at 9.0 still `earning`; a mature window is judged as it always was; five mutations of the hooks each make a test fail). `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that judges a recent window: it passes a `maturity.Reading` where it wants the estimate, built from curves it fitted weekly and stored; a pack that passes none is unchanged; the Meta operator pack needs its table of every export with the time it was taken first)
- `kit/export_demand.py` (pack `creative`; issue #261, first of the three contract documents, from the video-ads skill pack's `scripts/export_demand.py` `request` and `export`, cut from its main): the body of an `ads.demand/1` file from `kit.compute_demand`'s document. The pack hands over a `Source` (the demand document, its CLI word, the platform id, the format in its own words, the day the lead time counts from, optionally the subject of the request id, the client's currency, a product and a placement) and the day, and gets `{body, count, request_id, needed_by, warnings, warning_codes}`: one request with the count, the day it is needed by (the start plus the measured lead time, rounded up), the window of a verdict in days (at least 1), the batches and the cost of one verdict in the note, and the cost as `unit_cost_cny` only when the client's money is CNY (never a converted figure). With nothing to ask for (no plan, no cost of a verdict yet, the platform's range leaves no whole batch) `body` is None and the warning `demand_nothing_to_ask` says why (`kit/message_codes.d/export_demand.tsv`, under video-ads' own name): no file is to be written. **Writing is the pack's**, not the kit's: a `creative` module cannot import `kit.contracts` (packs import only `base` and themselves), so the pack calls `contracts.write("ads.demand", 1, doc["body"], out)`, which checks the body as a reader would and writes it once; `produced_at` is the given day at 00:00 UTC so the same document on the same day is the same bytes (a repeat is a no-op, other bytes under that name are refused). A `Source` the file cannot be written from (not the demand document, a block without its lead time or window, no start day when there is something to ask for, an empty producer, platform or format) is `compute_input_invalid` naming the part. Differences from video-ads' file, named: (1) the pack writes it, the kit builds the body; (2) the start day, the platform id, the format and the currency are handed over where video-ads read its database and its configuration; (3) `product` and `slot`, which the schema has, are written when the pack names them; (4) the note leaves no double space when the money is not known (video-ads wrote `55.54  (measured`); (5) the reason of an empty request is the demand block's own `constraints`, else the document's `pacing_demand_unknown`, where video-ads also read the pacing document's `pacing_no_target`. On the golden comparison's account the kit's body equals the file `vads export demand` writes, byte for byte but for (4), in three scenarios (a spend and a result; a spend with no result target; another month and spend), and in a fourth, where the platform's range leaves no batch, both write nothing and give the same reason. The contract is still a draft (ROADMAP X11): it has only `unit_cost_cny`, so a client whose money is not CNY has the cost of a verdict in the note only; whether the contract takes a currency is for its first producer and consumer to settle. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that asks a maker for creatives: video-ads, at its kit move, replaces `request` and the body of `export` by `export_demand.compute` and keeps `contracts.write` and its own `--out`, and deletes its `demand_nothing_to_ask` message row, which the kit now defines (a code defined twice refuses to load); the Meta operator pack builds its `Source` from the demand document and the plan's first day and writes the file the same way)
- `kit/export_results.py` (pack `creative`; issue #261, second of the three contract documents, from the video-ads skill pack's `scripts/export_results.py` `results` and `export` and `scripts/_lib/contracts.py` `RESULTS_COLUMNS`, cut from its main): the rows of an `ads.results/1` file. The pack hands over the report's current rows that resolve to a creative (the contract's columns as numbers and flags: the key, `nk`, `exported_at`, `complete`, `settled`, `restated`, the counts and ratios; it knows the platform's time zone and how many days settle a day, so the three flags are its own) and, if it wants the stage and the score, the creatives' days (`compute_life.Source`), and gets `{rows, counts, scored, scored_at, benchmark, unscored, scores, warnings, warning_codes}`. `rows` are sorted by key and every cell is text as the contract wants it (a flag `1` or `0`, a whole number without a point, blank for unknown, never 0), ready for `contracts.write("ads.results", 1, doc["rows"], out)`. Each row's `stage` and `stage_reason` are its creative's state and reason in the life document; a creative that has earned a verdict (mature, declining, or ended as faded or a weak creative) is given `fission` (0.00 to 1.00, `kit.fission`, against the account's proven creatives) and `scored_at`, the time the pack gives; the others are blank. With fewer proven creatives than a benchmark needs (3 at least) only the weak creatives are scored and `fission_benchmark_insufficient` says how many there are (`kit/message_codes.d/export_results.tsv`, under video-ads' own name). **Writing is the pack's**, as for `export_demand`: a `creative` module cannot import `kit.contracts`. A `Source` the file cannot be written from (a row without a required column, a column the contract does not have, a flag that is not 1 or 0, a negative count, a period that ends before it begins, an `nk` on two rows, a creative without days) is `compute_input_invalid` naming the part, e.g. `rows[3].nk`. Differences from video-ads' file, named: (1) the pack writes it, and the three flags come from the pack; (2) the creatives' days are handed over where video-ads read its report ledger and, for the score, only its report days; (3) the kit's file has the optional columns `fission`, `scored_at` and `stage_reason` only when a row has one, where video-ads always wrote them (the schema makes them optional); (4) the document does not carry the file's path, sha256 or the feedback record, which are the pack's. On the golden comparison's account (a report ledger of 740 current rows over 12 creatives, daily rows, monthly rows, one key restated, one row no creative owns) the kit's rows equal the file `vads export results` writes, cell for cell and in the same order: 11 creatives scored, the benchmark of 9 proven creatives the same. **A finding on the contract, not settled here (ROADMAP X11):** the money columns are named `spend_cny`, `gmv_cny`, `cpa_cny` and described as CNY, but video-ads' ledger keeps them in the currency of the import (its schema says the `_cny` is historic), so a Meta client's HKD or USD sits in a column called `_cny`; the file does not say which money it is. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that hands a maker its results: video-ads, at its kit move, replaces the building of the rows and the scores by `export_results.compute` and keeps `contracts.write`, its flags and its feedback record, and deletes its `fission_benchmark_insufficient` message row, which the kit now defines (a code defined twice refuses to load); the Meta operator pack builds its rows from its own report table and decides what money its `*_cny` columns hold until the contract says)
- `kit/export_changes.py` (pack `ads-core`; issue #261, last of the three contract documents, from the video-ads skill pack's `scripts/export_changes.py` `observed`, `reported` and `export`, cut from its main): the body of an `ads.changes/1` file, for the pack that sets the platform's numbers against the company's own. The pack hands over a `Source` (the pulls' history `(level, entity_id, as_of, delivery_status, daily_budget, lifetime_budget)`, the answers people gave on the daily page (`kit.daily`'s item ids), the allocation's advice of each day, its CLI word, the platform id, the entity id of an account-wide change, optionally the account) and the day, and gets `{body, count, observed, reported, warnings, warning_codes}`. Two kinds of change, each with a stable `change_id`: **seen by the pulls** (a campaign's or ad set's budget or delivery status that differs from the pull before; the first pull of an entity is a baseline, not a change; `by_kind` unknown) and **done by a person** (an answer of `done`; `by_kind` person, `by` the reporter; a budget move says its budget before and after as the allocation advised it on that day or the latest day before; `campaign:<action>:<id>` is the campaign's action, `audit:<finding>` and `request:creatives` are the account's). Oldest first, an absent `before`, `after` or `by` is absent (never empty), an empty list is a document too, the window is the last `days` days (90 by default) from 00:00 UTC. **Writing is the pack's**, as for the other two (`contracts.write("ads.changes", 1, doc["body"], out)`). A `Source` the file cannot be written from (a history row of the wrong width or without an entity, a time with no zone, an answer without its `seq`, a `seq` on two answers, advice that is not `{day, moves}`) is `compute_input_invalid` naming the part, e.g. `answers[1].seq`. Differences from video-ads' file, named: (1) the pack writes it; (2) times are compared as moments, whatever zone they are given in (video-ads compared the text, which is wrong across zones); (3) the request for creatives reads `asked the maker for creatives` where video-ads wrote `asked adcut for creatives` (the kit names no pack), and an item the kit does not know is the account's with the item as its words, where video-ads called every such item that request; (4) `account` is written on every change when the pack names it. On the golden comparison's account (10 pulls of 5 entities, two days of advice, six answers) the kit's 9 changes equal the file `vads export changes` writes, in the same order, but for (3). The contract is still a draft (ROADMAP X11): the platform's own change history is not read by either side, so a change a person made in the platform's screen is seen only as a difference between two pulls. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that tells measurement what changed: video-ads, at its kit move, replaces `observed`, `reported` and the body of `export` by `export_changes.compute` and keeps `contracts.write`, its history query, its record folders and its `--out`; the Meta operator pack builds the history from its own pulls and the answers from its daily page)
- `kit.pending` takes `derived=` (issue #249, designed in the issue's comment of 2026-10-28 and decided by the owner the same day): `pending.main(..., derived={key | (market, key): because})` and `pending.asks(..., derived=...)`. A fact a skill pack worked out from data it already holds (an account's id, its currency, a reference return) is posted as before (`facts set KEY VALUE --source "derived: <where>, <window>"`, so it is pending) and named in the hook with the skill pack's own words for where it came from. Such a fact is **one `confirm` ask whatever its registry type**: the value is shown and not typed (before, a number, date or text fact was a box pre-filled with the value that could be overtyped, which is how a break-even assumption once landed in a reference's box), the recommendation is `yes` with that `because` (clipped to 200 characters), `about[].fill` is empty so nothing waits for the agent, and the gate binds the value shown. The derived facts of one market are one group (`Facts, M`), so the console's existing **Answer all as suggested** confirms them with the values shown (four clicks become one); to change one, a person answers no and says the right value, and the agent sets it, which is a new question with a new id. **No fact is in force without a person**: `confirm` is still the human gate, nothing about a key that moves money is decided here, and there is no marker (the earlier proposal of a source in force without a click was not taken). A key not named in `derived=` is drawn exactly as before, and `pending_fill_because` now counts only the asks that still need the agent's argument. A hook written wrongly (an empty because, a key that is not a word or a (market, key) pair) is `pending_derived_invalid` naming the key (`kit/message_codes.d/pending.tsv`). No console change. Tested in `kit/tests/test_pending.py` (section 7): the console takes the derived asks as they are, a relayed yes confirms exactly the value shown, a changed value is a new question; ten deliberate breaks of the hook each fail a case. The event catalogue's pick (`event_catalogue.for_markets`, then the client confirms or strikes) is the second user of the same hook, shipped separately. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`).
  - For a skill pack: judgement (only a pack that derives facts from its own data: it passes `derived=` to `pending.main` for the keys it derived, with a because that says the source and the window, and gives those facts a `--source` that starts `derived:`; the Meta operator pack, whose account id, currency, time zone and reference return are the case; a pack that passes nothing is unchanged, and the shape of every other ask is unchanged)

### Other
- `ROADMAP.md` and `docs/portfolio.md`: the Amazon PPC skill pack now lives on GitHub (`thaddeus-builds/amazon-ppc-skill-pack`, private; owner 2026-10-28), not GitLab; the playbook's own address is `thaddeus-builds/skill-pack-playbook` (the old `thaddeus-growth` name redirects). The GitLab CI templates stay: other skill packs are still on GitLab. Docs only.
- `scaffold/markets.py` and `scaffold/countries.tsv` (owner's decision, 2026-10-28; no pack has been hurt by this yet, it closes the door before one is): `new_hub.py new --markets` and `new_skill_pack.py --markets` accept only ISO 3166-1 alpha-2 codes (249 plus `XK` for Kosovo), in capitals, each once. `UK` is refused with `GB`, `hk` with `HK`, a made-up code is named. Before, any plain word passed, so a hub and the packs it serves could spell one market two ways and `facts sync-hub` would skip the fact. The running kit is unchanged (its closed set is still `[skill_pack].markets`), so a hub or pack already made keeps working; its fixtures in the scaffold tests now use real codes. Tested in `scaffold/tests/test_markets.py`. No kit change.

### Other
- `scaffold/new_hub.py` (issue #254, seen once in a client hub, 2026-10-28): `new` now makes the hub's facts store: it runs the hub's own `facts init` piped once per market of `--markets`, every answer blank, so `hub/hub.db` exists and `bin/hub hub facts list` answers instead of `no_db`; each market's declaration is pending and a person still confirms it on the console (the scaffold confirms nothing and asks no scope `--markets` did not answer). New verb `init-facts --hub DIR` does the same for a hub made earlier that has no store, and refuses one that has. Tested in `scaffold/tests/test_hub_program.py` and `test_new_hub.py`. `docs/consoles.md` says it. No kit change.
- `kit/daily_page.py` (new module, pack `pages`; issue #253, seen in the video-ads skill pack's `scripts/_lib/daily_page.py` and `audit_page.py` at its main, and in the next ads skill pack's weekly page design, ROADMAP X11): `render(doc)` draws the document `kit.daily.build()` returns as one page over `kit.pagestyle`, passing its `problems()`: tiles and the status bar first, the one decision (the first open item of the most severe kind, with its report command and the hint where to paste it), at most three warnings with the rest in the owner's fold, one row per item that unfolds into its card, the owner's fold last. The audit's findings are items of that list (`audit:<finding>`), so one renderer covers both pages. It reads the items as plain dicts and does not import `kit.daily`, because `pages` imports only `base` and itself; the shape is the contract, written in its docstring. A pack passes its `Style` (severity is the state: `down`, `testing`, `untested`, and `closed` for an item somebody reported on, so the pack words those four) and `words_over` for the rest (`WORDS_EN`, `WORDS_ZH`; an unknown key, an empty word or a template without its placeholder is refused, naming the key); the sentences are the items' coded messages in the style's language (the registry's `meaning_zh` or `meaning_en`, else the message the item came with), or the pack's `say(part)`. An item with no id or no sentence is left out and counted in the page data, a severity it does not know reads as `info`, as `kit.daily` does. No message code is added. Tested in `kit/tests/test_daily_page.py`, over the real `kit.daily.build()` as well as synthetic items. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`); it is a minor when the train runs.
  - For a skill pack: judgement (only a pack that already takes `pages` and draws a page of the day's items: video-ads can delete `_lib/daily_page.py` and `_lib/audit_page.py` once it passes its Traditional Chinese `say`, its state words and its structure table as the owner's fold; a pack without `pages` adds it to `[kit] packs` to use the renderer)

### Other
- `tools/adoption.tsv` and `ROADMAP.md` N2 (2026-10-28): the kit versions of adcut (0.44.0), creator-program (0.45.0), geo-china (0.45.0) and ecommerce-seo (0.46.0) are as read from each pack's `origin/main` (GitLab and GitHub clones fetched that day); every one of the 16 packs vendoring the kit matches its own `MANIFEST.sha256`, so nothing has been edited by hand. N2 no longer says the packs sit on 0.32.0 and 0.33.0: what is left of it is the weekly train. The other columns of those rows keep their earlier check date. No kit change.

### Other
- `docs/maintaining.md` (issue #166, seen once in adcut): the agent-access list says to name the git host on every `glab` call (`GITLAB_HOST` or `--hostname`), because outside a checkout it defaults to gitlab.com and the 401 or 404 looks like a bad token. Documentation only, no check possible. No kit change.

### Kit
- `kit/tools/leak_guard.py` (issue #165, seen once in adcut): the docstring says it is a floor, not a proof: it matches across a word break on purpose, sees only listed terms, and runs at push alone, so a client described without a listed term, issue text and a release note pass. `.github/PULL_REQUEST_TEMPLATE.md` gets the checklist line that a person or agent reads the diff, release note and issue text for such a description. A test pins the across-words match so nobody "fixes" it into a miss. No behaviour change. Tested in `kit/tests/test_leak_guard.py`.
  - For a skill pack: nothing

### Other
- `console/` (issue #152, seen once in adcut): the manifest takes an optional `page_only_verbs` list, relay verb prefixes that only a button the skill pack's own page draws may run (a click that grants a mode or a spending period). `ask.py add` refuses an ask whose gate is one of them, and the console refuses to run one when such an ask is answered, so an ask written some other way (or posted with no manifest) is dead; before, any agent that could run `ask.py add` could post a card whose click opened an auto mode. Each page-only verb must start with a relay verb. A manifest without the key behaves as before. Tested in `console/tests/test_manifest.py` and `test_frame_serve.py`. A pack that uses the key re-vendors the console first (an older console refuses an unknown key). No kit change.

### Kit
- `kit.copylint` (issue #151, seen once in adcut): a rule or fact with status `withdrawn` (a confirmation taken back, the word `kit.decisions` already uses) is read as pending, so it fires as a draft; before, one such row made `facts()` and `banned()` refuse the whole lint (`copylint_rule_field_invalid`). A misspelt status is still refused. Tested in `kit/tests/test_copylint.py`.
  - For a skill pack: nothing
- `kit.autonomy.signed()` (issue #155, seen once in adcut): refuses a `client:<name>@relay` author, an empty user and a second `@`, as `docs/autonomy.md` rule 3 says ("a `client:` row never counts"); before, any of them read as a person's confirm and could open a mode. A real `<user>@tty|relay` row is unchanged. Tested in `kit/tests/test_autonomy.py`.
  - For a skill pack: nothing (a pack that wrote its own full-match check around `signed()` can drop it at its next kit move)
### Other
- `templates/client/CLAUDE.md`: a client's agent answers the owner in simple Chinese (plain words, no jargon, command names and the client's own terms kept as they are); what it tells the client is still set by the client-language rule. Seen in three client workspaces of geo-china-skill-pack, where the line was added by hand. A client folder scaffolded earlier adds the line to its `CLAUDE.md`. No kit change.

### Kit
- `kit/daily.py` and `kit/audit.py` (pack `ads-core`; issue #239, from the video-ads skill pack's `scripts/_lib/daily.py` and `audit.py`, cut from its main): the two platform-neutral pieces the thirteen engines of 0.45.0 did not include, so the Meta operator imports them instead of copying. `daily.build()` turns the documents of a pack's campaign, audit, allocation and pacing computes, plus the answers people gave, into one ordered list of items under stable ids (`campaign:<action>:<id>`, `audit:<finding>`, `move:<id>`, `request:creatives`) with the coded sentence, evidence, doubts, steps, the report command and the latest answer; an answered item that no longer comes up is `solved`; a doubt name, a severity or a pacing warning it does not know is left out, where the source raised a `KeyError`. A campaign proposal and an audit finding keep the sentence they arrived with. Its own 21 codes are `daily_*` rows in `kit/message_codes.d/daily.tsv` (English and Simplified Chinese, no platform or pack named; the source's wording named Smartly, adcut and `vads`). `audit.findings(facts, thresholds)` holds the rules only: five findings (`audit_issues`, `audit_no_result`, `audit_old_ads`, `audit_concentration`, `audit_budget_unused` or `audit_budget_over`) as `{finding, severity, params}`, no sentence and no step; the steps name a platform's own screens, so they stay in the pack, and so does the `unlabelled` finding (a join only the video-ads report has), which the pack adds and sorts in with `audit.order()`. Tested in `kit/tests/test_daily.py` and `kit/tests/test_audit.py`. `kit/VERSION` does not move with this merge (the release train, `docs/maintaining.md`); it is a minor when the train runs.
  - For a skill pack: judgement (only a pack that runs ads: add nothing if `ads-core` is already in `[kit] packs`; video-ads, at its kit move, deletes `_lib/daily.py` and the rules of `_lib/audit.py`, deletes its own `daily_*` rows (a code defined twice refuses to load), keeps the sentences and steps of `audit_*` as `msg()` calls built from the kit's params, and renders the Traditional Chinese of the `daily_*` and `campaign_*` sentences in its page, since the kit's rows are Simplified (ROADMAP R7); meta-ads imports both at its X24 and writes its own Ads Manager wording)

### Other
- `docs/portfolio.md` and `tools/adoption.tsv` (issue #223; the owner's decisions of 2026-10-28): the `meta-ads` and `video-ads` rows say where they stand today (kit 0.45.0; the Meta read side moved on a branch, not yet on main), the "rename waits for the second split" note is replaced by the decision (the shared ads layer is `ads-core` with `creative`, no new `ads-skill-pack` repository, `video-ads` is not renamed and keeps 千川 and 腾讯), and one sentence says a pack never imports another pack. Both packs' next steps name `daily` and `audit`. No kit change.

### Other
- `tools/pack_status.tsv` (issue #224): the notes of `ads-core` and `creative` record who the two importers will be (meta-ads at its X23 and X24 once its read side is on main, then video-ads at its X63, google-ads a third) and that the 2026-12-31 date moves once by one month if neither has merged by 2026-11-30. The counts stay empty until `tools/consumers.py` finds merged code. No kit change.
- Skill packs: judgement (a pack that takes `ads-core` or `creative` decides: whether to pass a `maturity.Reading` (none: nothing changes); to build the `Source` of each compute document and of `export_demand`, `export_results` and `export_changes` from its own tables, and to write their files with `contracts.write`; to read the five `adgroup_*` rows in place of campaign rows for wallets, and `pacing_min_conversions` in place of its own efficiency floor; and to delete the message rows the kit now defines, since a code defined twice refuses to load (the four `pacing_*` demand rows, `demand_nothing_to_ask`, `fission_benchmark_insufficient`, and the `life_*`, `portfolio_*`, `daily_*` and `campaign_*` rows of each module it takes); a pack that takes none of these modules and passes `derived=` nowhere is unchanged, and each item above says in its own indented line what a pack does with it; ask the playbook session only for a pack nobody is working on)

## [0.46.0] - 2026-10-27
### Kit
- `kit/snapshot.py` (new pack `ops`, `incubating` until 2026-12-31 in `tools/pack_status.tsv`): pack a client's workspace into one `<client>-snapshot-<UTC>[-N].tgz` that restores it, lifted from the SEO skill pack's S71 so every pack gets it built once. The database is copied with SQLite's backup API and checked (`integrity_check`, `user_version`); the files go in without the pack's own `exclude` patterns (the kit's default is empty; the live database and its journal files are always replaced by the backup copy); a secret value from the env files or the process env, or a token shape, refuses and writes nothing; `MANIFEST.json` has the sha256 of every file; the package and its sidecar are written atomically; `keep` prunes only this client's packages, ordered by (timestamp, `-N`). It raises `SnapshotError` (a `SkillPackError`; codes `snapshot_out_inside`, `snapshot_keep_invalid`, `snapshot_integrity`, `snapshot_secret_found`, in `kit/message_codes.d/snapshot.tsv`). Uploading a copy elsewhere is the operator's step: the kit holds no credentials. Docs: `docs/snapshot.md`. Tested in `kit/tests/test_snapshot.py`. Per `docs/maintaining.md` ("The release train") `kit/VERSION` does not move with this merge; it is a minor (0.46.0) when the train runs.
- Skill packs: judgement (only a pack that wants snapshots; the SEO skill pack, the first importer, re-vendors with the train, adds `ops` to `[kit] packs`, and replaces `scripts/_lib/snapshot.py` by a call to `snapshot.make()` with its own `snapshot_exclude.tsv`, its human-tables export and its Chinese message rows)
### Other
- `docs/planning.md`: the prompt for the building agent no longer says "regenerate the roadmap view, commit"; the view is ignored, so the agent builds it to see it still builds and commits the rows only (follow-up to the generated-views change, 2026-10-27). Tested in `tests/test_docs_build.py`. No kit change.
- `templates/gitignore` also ignores `/docs/pipeline.html`, the page the SEO skill pack's script writes and the example in `templates/system-overview.md` names; a skill pack with another page name adds it (follow-up to the generated-views change, 2026-10-27). Tested in `tests/test_docs_build.py`. No kit change.
- `docs/rules.md` rule 8 is as the SEO skill pack built it (2026-10-27): the story tables are append-only, which is what makes `merge=union` safe, and an id is claimed by pushing a branch the git server grants once, because a reading script alone gave two sessions the same id. It also says the scaffold has none of this yet (the ssot guard refuses a second row of an id; `render_gitattributes` writes no `merge=union`): a second skill pack must ask first. No kit change.
- `docs/lessons.md`: what an agent loads is measured and held by a test (from adcut: `tools/context_cost.py`, `tests/test_context_budget.py`; a procedure as an index plus one file per phase; a session's state in the workspace report, not in `docs/`). Held in shape by `tests/test_docs_build.py` (at most 150 words, says where it was seen). No kit change.
- Generated views are built on demand and not committed (2026-10-27, from adcut: the committed overview page conflicted in about every merge of parallel sessions). `templates/system-overview.md` rule 1 is now "Generated, not committed, checked"; `templates/gitignore` ignores `/docs/overview.html`; `docs/rules.md` rule 8 and `docs/planning.md` say the same; `--check` means "the registries make a page", not "the committed file is fresh". Tested in `tests/test_docs_build.py`. No kit change. A skill pack that committed its overview removes the file from git and ignores it (adcut MR 293 is the example).
- `docs/skill-pack-agent-prompts.md` (new): a common prompt and one each for geo-china, search-intel and creator-program, for the agent that works inside that skill pack, with how to use them; `tests/test_adoption.py` fails on a prompt for a pack that is not a row of `tools/adoption.tsv`. No kit change.
- `tests/test_changelog.py`: from kit 0.45.0 each CHANGELOG version carries a `- Skill packs: nothing | mechanical (...) | judgement (...)` line, so a skill pack's own session can act on a release without asking the playbook (mechanical is `python3 tools/fleet.py update`; judgement is the pack's call). Earlier entries are not rewritten. No kit change.
- `tools/adoption.tsv` and `tools/pack_status.tsv` recounted on every skill pack's main branch (2026-10-27, `tools/consumers.py`): the seven "drop the unused declaration" next steps are done and removed, kit versions are 0.44.0, `exchange` is imported by adcut, sdr and video-ads (not outbound), `data` by video-ads alone. `tests/test_pack_status.py` also fails on a consumer that is not a row of `adoption.tsv`. No kit change.
- The playbook's own `.github/workflows/ci.yml` starts only by hand (`workflow_dispatch`); the pre-push hook runs `run_all.py` before every push. `CLAUDE.md` and the hook's comment say so. Tested in `tests/test_ci_quota.py`. No kit change.
- Both GitLab CI templates (`templates/gitlab-ci.yml`, `templates/ci/gitlab-ci.yml`) run by themselves only the few-second checks (secret scan, story id, changelog); the suite, the Zylos adapter check and adapter smoke become manual jobs with `allow_failure: true`, so a pipeline is never held. The scaffold's next steps add a step 4, `git config skillpack.prepush-tests "python3 scripts/<cli>.py test"`, so the kit's pre-push hook runs the suite before each push (the hook already supported it; no kit change). A skill pack scaffolded earlier edits its `.gitlab-ci.yml` the same way and sets the config once per clone. Tested in `tests/test_ci_quota.py` and `scaffold/tests/test_new_skill_pack.py`.
- The `story id` CI job (`templates/gitlab-ci.yml`, `templates/ci/gitlab-ci.yml`) also accepts a title that starts `Re-vendor the kit` (a maintenance merge request names no story); `templates/AGENT_INSTRUCTIONS.md` says so. A skill pack already scaffolded copies the new pattern into its own `.gitlab-ci.yml` by hand (BUILD.md notes that `--update-kit` does not rewrite it). Tested in `tests/test_docs_build.py`. No kit change.
- `tools/research.py PATH…` (new): one table of what the skill packs already looked up, read from each pack's `docs/research/README.md` and `docs/prior-art/README.md` (pack, kind, question, date, answer, file), optionally written in full as a TSV with `--write docs/research-index.tsv`; documented in `docs/kit-and-tools.md`. Read-only, stdlib only, outside the vendored bytes: no kit version. Tested in `tests/test_research_tool.py` on throwaway packs.
- `scaffold/new_skill_pack.py` writes `docs/research/README.md` and `docs/prior-art/README.md` from the new `templates/research-index.md` and `templates/prior-art-index.md` (listed in `templates/README.md` with their targets), and the generated `tests/test_ssot.py` also runs `suites.research` (kit 0.44.0), so a research file or scan with no row in its index fails from the first commit. BUILD.md B0.5: the index is read before any search. No new test file: the generated set stays thirteen. A skill pack that already exists takes it by adding `suites.run(suites.research(ROOT))` to a test of its own after re-vendoring. Tested in `scaffold/tests/test_new_skill_pack.py` and `kit/tests/test_research.py`.
- `docs/lessons.md` is a quarter of its size: every lesson is at most 150 words (the rule, what it cost, where it was seen, where the detail lives), held by a new check in `tests/test_docs_build.py`; the two SEO client narratives moved in full to that skill pack (`docs/playbook-lessons-2026-10.md`, its MR 305) and the playbook links to them. `tests/test_design_first.py`, `test_prior_art_audit.py` and `test_prior_art_quick.py` keep their template checks and no longer pin a lesson's wording. No kit change.
- Trimmed: `docs/workbook-and-browser-ops.md` (the workbook half is built, the browser half is ROADMAP X8) is archived as `docs/history/workbook-and-browser-ops-2026-10.md`; `templates/verify-challenge.md` and `templates/outcome-learning.md` are removed, no skill pack holds or names either (checked on fifteen, 2026-10-26); `docs/overview.md` loses its hand-written "Where it stands" table, which was already a version behind. No kit change.
- A rule for the packs that exist ahead of their second importer (`ads-core`, `creative`, and the four only adcut imports): CLAUDE.md, "A pack may be born before its second importer, but not for good". `tools/pack_status.tsv` lists every pack but `base` and `testkit` as `shared` (the importers `tools/consumers.py` counted, and when) or `incubating` (with the day by which two skill packs must import it); `tests/test_pack_status.py` fails the day after, on a pack with no row and on a `shared` row with fewer than two importers. Counted 2026-10-26 on the fifteen skill packs that vendor the kit: `compliance`, `workbook` and `exchange` are shared; the rest incubate until 2026-12-31. No kit change.
- The top level reads as what is current: `RESTRUCTURE.md`, the 2026-10 plan that is carried out but for its phase 1 (now ROADMAP N2), is archived unchanged as `docs/history/restructure-2026-10.md` with a status line; `docs/roadmap.md`, the planning method, is `docs/planning.md`, so it no longer shares a name with `ROADMAP.md`, the plan. Every link and mention is updated. No kit change.
- `tests/test_docs_build.py` no longer pins paragraphs of `docs/rules.md`, `lessons.md`, `operating.md`, `consoles.md`, `path-weights.md` and the planning doc: seventeen checks that wanted a lesson's exact sentences are gone (RESTRUCTURE.md phase 3, step 3), and the autonomy check keeps only what holds `docs/autonomy.md` to `kit/autonomy.py` (the levels, built or not, and the proofs). What stays is held to something checkable: paths, links, flags, counts, tables the code defines. A lesson is kept by its readers; a rule by the check that fails when it is broken. No kit change.
- `tools/fleet.py` no longer reports every skill pack's console as `local changes`: the `VERSION` stamp `vendor.py` writes into a console copy (the playbook's `console/` has none) is read for the version and never counted as a file of the skill pack's own. Before this, all fifteen vendoring skill packs read as `local changes in 1 file(s)` on a console that was only behind. Tested in `tests/test_fleet.py`. No kit change.
- `docs/maintaining.md`, "The release train": a `kit/VERSION` bump is a dated train at most once a week, merges to main accumulate under Unreleased, and `tools/fleet.py update` is how every skill pack reaches the train; step 6 of the loop now points there. Decided by the owner after the 2026-10-26 review (52 bumps in four weeks, 14 packs on six versions). No kit change.
- `tools/fleet.py update SKILL_PACK... [--version X] [--no-tests]`: for each skill pack, a worktree beside it (`<repo>_worktrees/kit-<version>`, branch `claude/kit-<version>`, cut from the default branch `git remote show origin` reports), this playbook's kit and console vendored into it, the pack's suite run (`[skill_pack].test_command` in `skill-pack.toml`, else `python3 tests/run.py`), a line under the CHANGELOG's Unreleased, and one commit naming the from and to versions and the suite result; one line per pack (green, red with the failing files, refused by the vendor tool, worktree exists, already current). The pack's own checkout is not touched. First step of the upgrade plan of the 2026-10-26 review (14 packs were re-vendored by hand). No kit change. Tested in `tests/test_fleet.py`.
- `conformance/INVARIANTS.md`, "Adoption levels": L0 (keeps the invariants), L1 (vendors `base` and `testkit`, CLI through `kit.cli`), L2 (declares and vendors only the packs it imports, own copies deleted), L3 (the full scaffold structure), each with the command that proves it; `tools/adoption.tsv` records the level, target, check day and next step of the eighteen skill-pack checkouts, read on their main branches on 2026-10-26 (`tools/fleet.py`, `tools/consumers.py`, `conformance/check.py`). Pointers in `docs/overview.md` Part 2 and `BUILD.md` B1. Tested in `tests/test_adoption.py`. No kit change.
- CI minutes are a quota on a private repository: `.github/workflows/ci.yml` cancels the older run of the same ref (never one on `main`); `.githooks/pre-push` runs every suite in this repository (`git config core.hooksPath .githooks`); `templates/gitlab-ci.yml` marks its jobs `interruptible` as the fuller CI already did, so a new skill pack's GitLab pipelines cancel too. Default hosting stays GitLab and nothing here is required. Tested in `tests/test_ci_quota.py`.
### Other
- `templates/prior-art-scan.md`, "Auditing a skill pack that already exists", and `docs/lessons.md` (Research is kept, not repeated): the module-by-module survey of what is already built, with a verdict per module (adopt, borrow-idea, keep-own, watch), a sources registry with pinned versions, a coverage test, and the owner's three-claim spot-check. Seen once (the Amazon PPC skill pack, 2026-10-26), tested in `tests/test_prior_art_audit.py`.
- `docs/overview.md`: the autonomy levels L0 to L5 on the overview, one row each with who decides the write, an example and whether it is built (L4 and L5 are not), linked to `docs/autonomy.md`. No kit change.
- `docs/overview.md`, "How the work moves": the diagram now follows one example (a promotion on two platforms), names what each arrow carries (the contract) and says in words what each of the four steps does; before, it drew four abstract boxes. No kit change.
- `docs/overview.md` (new): the framework on one page, in two parts: who owns what in growth operations (operator, truth, maker, owner; the five ownership rules; the five solutions), and what the playbook unifies and saves each skill pack (the gate, the money path, the build, the kit's packs); a dated state table that points to `tools/fleet.py` and `tools/consumers.py` for live counts. The README's map links to it. No kit change.
- `docs/operating.md`, "Long or paid runs, and the rehearsal before a demo": a many-item or paid tool records per item and exits non-zero on failure, a rehearsal on the real stack includes failures on purpose, a demo freeze names its exceptions; `templates/session-handoff.md` gets the dated handoff file for the in-flight state the roadmap cannot hold (seen in product-keyframe-video).
- `contracts/` (new; ROADMAP R9, rollout phase 2b, step 1): the files skill packs exchange, one JSON schema and one example each, and the rules in its README (the first line names the file, a consumer ignores fields it does not know, a breaking change is a new version written beside the old for one release, a file is written once). `ads.creatives/1` and `ads.results/1` state the formats adcut and the video-ads skill pack already use, as TSV rows, and change nothing in them; `creators.roster/1` is the video-ads skill pack's K5; `ads.demand/1`, `ads.changes/1`, `catalog/1`, `messages/1`, `truth/1`, `intel/1`, `leads/1`, `handoff.batch/1` and `copy.proposals/1` are drafts from the portfolio page's table (the last two with the fields asset-handoff and ad-copy print today, read from their main branches). `docs/portfolio.md` links to it; `tests/test_contracts.py` holds the shape of every schema and that the two tables list the same contracts. Not vendored: no kit version. The kit helper that writes and reads them is the next pull request.
- `docs/maintaining.md` (new): how the playbook itself changes. The loop from a skill pack's issue to a merged pull request and a re-vendor when a skill pack needs it, what the agent checks in a pull request and at a session's start and end, the monthly look at the skill packs (`tools/consumers.py`, `tools/fleet.py`), and the access an agent needs: a read-only fine-grained GitLab token (Project: Read, Code: Download; User and Group: Read only to list projects), kept in the environment settings and never in chat or a file, with a separate short-lived push token only for changing a skill pack. Linked from the README.
- `build/` and the intake template, for a client hub (ROADMAP X10, step 1): an intake item, or a meeting as the default, may name the `packs` it is for (CLI words); `check_intake.py --packs CLI,...` refuses a pack the client does not have (`unknown_pack`, also when packs are named and no list is given), reports an iid a later file reuses as `iid_reused` with the next free one (`duplicate_iid` is now within one file), and with `--transcript FILE` or the meeting's `transcript` checks each quote is in the speaker block at its source's time (`quote_not_at_source`, `no_transcript`). `intake_to_asks.py --hub` makes the hub's own asks (`hub-intake-<iid>`, one group per meeting and its packs), `--pack CLI` keeps a round to one pack; `apply_answers.py` applies `hub-intake-` answers and writes a `packs` column in `numbers.tsv` and `questions.tsv` (a file made before it gains the column only for an item that names packs). Intakes without `packs` pass as before. Not vendored: no kit version.
- `docs/consoles.md`, client console item 8: a page behind a gateway answers within the gateway's limit (about 15 s)
  whatever the read costs. Profile the read first; keep what is left per state of the data, made in a background
  thread started with the console, with a bounded wait, then the previous result and a note, or a self-reloading page;
  never cache a failure; the keep-alive probe's timeout exceeds the slowest page. Seen once (the SEO skill pack's
  `/insights`, S36), tested in `tests/test_docs_build.py`.
- `kit-tiers.tsv` and `kit/tests/test_tiers.py` are deleted (RESTRUCTURE.md, phase 3): `kit/packs.tsv` and `kit/tests/test_packs.py` already hold what the tiers held (one registry row per module, no import across packs), and the tier rule (core, stack, extra) said the same thing a second way. `docs/kit-and-tools.md`, "The admission rule", is now written in packs: a new module goes in the pack named for its concern, moves to `base` at two merged users, is deleted after two minor versions with none. Outside the vendored bytes: no kit version, no re-vendor.
- `templates/install-checklist.md`, "Scheduled tasks and long jobs": renewals (a cloned voice, a token, a licence) are a plan-and-run verb of the skill pack with no scheduler of its own; the host agent chooses the trigger, says what it set up and the next date, and reports a failed run the same day. Seen once, in the adcut skill pack.
- `.github/ISSUE_TEMPLATE/from-a-skill-pack.md` and `.github/PULL_REQUEST_TEMPLATE.md`: an issue or pull request from a skill pack says where it was seen, who else needs it and what test fails without it; the pull request lists the checks `CLAUDE.md` already requires (one concern, no channel code, version bump with manifest and changelog for vendored bytes, `run_all.py`). No new rule; `CLAUDE.md` points to them.
- `docs/lessons.md`, "Checking the specification and the tests": the rebuild trial (a fresh agent rebuilds rule engines from the spec alone, scored on hidden cases from the real code, its `GUESSES.md` the list of gaps) and the mutation sample (45 random logic mutants against the tests that mention the module), with what each showed in the SEO skill pack.
- `tools/consumers.py` (RESTRUCTURE.md, phase 3, step 2): `python3 tools/consumers.py SKILL_PACK... [--json]` lists the kit modules each skill pack's own code imports (tests, the vendored kit and hidden folders excluded), and the ones that only come in through another module, so "two skill packs import it" and "no skill pack imports it" are counted, not remembered. Playbook tooling, not vendored. Test: `tests/test_consumers.py`.
- `docs/operating.md` rule 4 and the git rules in `docs/roadmap.md`: merge on the local suite (plus the golden diff for a refactor), CI on main is the clean-environment check, fixed or reverted at once when red; the risky list and the environment-dependent changes still wait for the MR's CI. Evidence from the SEO harness: more shards did not shorten a CPU-bound shared runner; 9 of 300 pipelines failed.
- `hosts/zylos` 0.3.0: pre-uninstall keeps a copy of the console's Caddy block in `<data dir>/caddy-block.saved` and post-install names it when the block is missing (found in the SEO skill pack, which had changed its copy: it now comes from here); the adapter's function `harnessEnv` is `cliEnv`, and what the hooks print to the owner no longer says "the harness" ("run it as:", "the CLI"): the adapter serves projects that do not call themselves a harness. No behaviour change; copy the folder again to take it (the SEO skill pack did, S172).
- `docs/rules.md`, registries items 10 and 11, from the SEO harness (each seen once): the owner's own files sit apart
  from the registries (`ssot/intent/`, both still TSV files in `ssot/`, so conformance I5 holds; the index says which
  edit changes behaviour); and a table many branches add to is append-only, a change being a new row of the same id
  with the last row in effect. `tests/test_docs_build.py` holds both.
- Worktrees live beside the checkout, never inside it (`docs/operating.md`, "Where worktrees live"; the layout block
  of `docs/roadmap.md` follows): `<repo>/` stays on main and `<repo>_worktrees/<name>/` holds one worktree per session.
  Paid for once in the SEO harness: a session in `.claude/worktrees/` read the checkout's stale `CLAUDE.md` too, 21 KB
  of context that disagreed with itself. Git commands to create, remove, move and repair; how to point the Claude Code
  desktop app and CLI at it; the sources. `tests/test_docs_build.py` holds the section and the layout.
- `docs/roadmap.md` (new): planning a harness that already runs. The vision cut into four to six pillars plus one for
  operations; a read-only inventory per pillar (state, evidence, smallest task, size, a do-not-build-now list); the
  roadmap kept in the story registry (an owner row with its milestone, an agent row with proof commands as DONE and
  `owner pending: question? (recommended: answer)` notes), a generated view with `--check` and registry tests; three
  open milestones plus later; one story per session on a cheaper model from a fixed builder prompt, merged by the
  coordinator, released per milestone; issue templates for production testers; who works where, the directory layout
  and the git rules. The SEO harness's roadmap of 2026-10-14 is the worked example. Seen once. Linked from the README;
  `tests/test_docs_build.py` holds its sections, its method items and the builder prompt.
- Lessons from the SEO harness, closing the loop on writes into someone else's system, each seen once there and
  tested in `tests/test_docs_build.py`. `docs/rules.md`, stories item 7: "done" for a written object is a fixed
  checklist recomputed from fresh data; a check older than the last write is `unknown`; a slow outside system gets a
  due list after a set number of days, never an assumed delay; a work item closes with its object (S43, S48).
  `docs/operating.md`, "Code filters; the agent judges": the other way round, a mechanical check that lives only in a
  prompt belongs in a read-only verb, and the prompt keeps the judgement. `docs/consoles.md`, one client, one
  workspace: a copied template drifts from its release, and the doctor compares each copy with the harness's template
  (S45, S48; not yet in the kit).
- `docs/lessons.md`, "A past winner the harness cannot say is studied for its mechanism, never copied": a client's
  strongest past ad that nothing in the plan can say is not a template and not a move; the harness proposes the
  mechanism (who it reached, how it opened, its timing, why people converted) for a person to confirm. A reference the
  client hands over to be copied is the other case. Seen once, in the video-ads harness (owner decision 2026-10-13).
  A judgement, not code: `tests/test_docs_build.py` pins the lesson's wording and its link from `docs/path-weights.md`.
- `docs/rules.md`, data layers: a page the harness delivers is drawn by the harness (code and test: `kit.guards.pages`,
  kit 0.30.0 below; tested in `tests/test_docs_build.py`).
- `docs/rules.md`, human-in-the-loop rule 13: an open question never holds the plan (code and test: `kit.questions`,
  kit 0.28.0 below; tested in `tests/test_docs_build.py`).
- `docs/autonomy.md` (new): autonomy levels L0 to L5, like SAE's driving levels, by what proof a write into
  someone else's system carries: L0 hand-carried, L1 per-change consent (`tty`, `relay`, or the approve of a known
  payload), L2 scoped approval (rule 12), L3 an owner-switched mode over a closed registry of revertible kinds,
  L4 rule-started work and L5 full autonomy (neither built; what L4 would need and why no harness is at L5). Per
  level: who decides, the proof recorded, the checks, what is revertible, the default caps, how it switches down
  and the write kinds allowed; eight rules at every level (the harness classes each write; a level is a ceiling
  per kind; raising takes a person, lowering anyone; expiry and caps counted from the archive; only revertible
  kinds above L1 and a code-free undo at L3; a stop issues no code; the digest; the approve still required through
  L3); the judgement that a retype and a relayed code are one level and the item's approve is the destination,
  so the owner's S46/S47 sit at L2/L3, not L3/L4; the SEO harness as the worked example; what the Amazon Ads
  harness must add. `docs/rules.md`: rule 8 admits an owner's mode switch retyped on a page; rule 12 points at the
  levels; the write door's rule 3 lets an L3 mode draft and publish in one step where nobody can preview in place.
  Seen once, in the SEO harness (S46, S47; owner decisions 2026-10-13). Tested in `tests/test_docs_build.py`,
  which holds the doc to `kit/autonomy.py`'s levels and proof labels.
- `docs/rules.md`, Registries item 9: a client's vocabulary is its value too. The options a harness mines or proposes for
  one client (a creative dimension's values, words taken from its own or its competitors' ads) are rows in that client's
  database, confirmed or retired by a person there; `ssot/` keeps the schema (the axes and their code letters) and the
  generic seeds a builder writes for every client. Seen once, in the video-ads harness (owner decision 2026-10-13).
  Tested in `tests/test_docs_build.py`.
- `docs/rules.md`, human-in-the-loop rule 4: one chat yes is quoted for one code only, and a
  wave that needs one yes gets one scoped approval (not yet proven: no harness refuses a reused
  quote). New rule 12: a gate the human clicks through proves nothing, so the harness tiers changes
  by the live diff (routine reversible kinds get one capped, expiring, scoped approval per wave;
  public or irreversible ones keep per-change proof; the approve checkboxes start unticked).
  Workflows rule R14 and `docs/operating.md` item 9: the owner's threat model (`config.threat`) is
  in every reviewer, finder and skeptic prompt, and review stops when only out-of-model findings
  remain; the build reviewer now also gets R11 (`config.known`). Seen once, in the SEO harness
  (S46). Tested in `tests/test_docs_build.py` and `templates/workflows/tests/test_scripts.py`.
- `docs/rules.md`, "Writing into someone else's system": six rules for a write door whose content
  is made after the approval (only approved work of one kind; the gate binds the file's sha256,
  or the live object as read just before a change of state; stage hidden, preview in place,
  then publish; archive every write under raw; read back and say so; revert is the inverse
  write, never a delete). Approve rule 5 points at it. Seen once, the SEO harness's store write
  (`scripts/apply_shopify.py`). Tested in `tests/test_docs_build.py`.
- `docs/rules.md`, "What an agent judges": a judgement quotes the page and the harness checks
  each quote word for word on the kept copy (markup, entities, spacing, dash and quote marks
  normalised; inline tags dropped without a space); an outside party is classified by its
  place in the value chain apart from the analysis switch, and a "no" stays a row on a
  read-only page; a large group competes on a segment, per market. In the data layers: a
  partial (filtered) paid pull is filed apart and flagged; an overview runs each report's own
  build and adds nothing to it. `docs/consoles.md`, client console item 7: a form the client
  fills offline is exported from the key registry, its answers come back as pending values
  sourced to the file. Each seen once, in the SEO harness. Tested in `tests/test_docs_build.py`.
- `templates/design-first.md` (new; used, not copied): before a feature an owner has to understand
  and steer, research it (the prior-art scan), write one design page in the owner's language (what
  it is, how it decides, the few asks each with a recommended answer and one reply that agrees to
  all, the tables it will store, append-only columns proven on a scratch copy of real data), show
  a clickable demo drawn by the harness's own renderer from a synthetic world, wait for the owner's
  yes, then write the code, after which the harness redraws the demo from a synthetic fixture to the
  same private link. The demo's guard is one Python block a harness copies (`demo_problems()`: the
  world marked `"synthetic": true` and nothing else, `DEMO` ids, `kit.pagestyle`'s synthetic badge
  with its words in the page's first header before the decision, `problems()` with the harness's
  own style and command patterns, never in any client's data folder, no client term by
  `kit/tools/leak_guard.py` in any form the page reaches a reader (as written, unescaped, as shown
  with its tags gone, and the page data's JSON escapes read back), failing closed); and a
  checklist. `docs/lessons.md` keeps what it paid for; a new harness's `CLAUDE.md`
  (`templates/AGENT_INSTRUCTIONS.md`), the prior-art scan's "When to scan" and BUILD.md's B0.5
  point at it. Seen once, in adcut-harness (its ROADMAP X45). Tested in
  `tests/test_design_first.py`, which runs the template's guard on a synthetic page drawn with
  `kit.pagestyle` and tries each way a demo can break the rule (a term in the page data or split by
  a tag, a badge folded, hidden or commented out, a demo in a client's data folder outside its review
  folder among them).
- Lessons from the SEO harness on data and platforms, each seen once there and tested in
  `tests/test_docs_build.py`. `docs/rules.md`, data layers: a datum a later decision needs is built from all of raw,
  never the newest snapshot alone, and an object's lifecycle (proposed, decided, written, verified or broken) is
  derived and names no platform (S52). The write door, rule 7: the right to write binds to a host id, never to a
  switch that travels with a copied database; an agent narrows it, only the owner moves it (`write_host`, S34, S47).
  Rule 8: one gate for every platform and an adapter per platform row, the gate extracted when the second platform
  arrives (`apply_gate.py`, S51). `docs/lessons.md`: an export branch never merges back into main.

## [0.45.0] - 2026-10-27
### Changed
- Skill packs: judgement (a skill pack that declares `data` in `[kit] packs` deletes it from `skill-pack.toml` first, then `python3 tools/fleet.py update`; a skill pack that does not declare it just runs the update)
- `kit/retry.py` moves from the pack `data` into `base`, and the pack `data` is retired (it held `retry` alone). An exception to "a module joins base once two skill packs import it" (ROADMAP R12): one skill pack imports it today, the Amazon PPC skill pack becomes the second when it adopts the kit. A skill pack that still declares `data` in `[kit] packs` must delete it before it re-vendors: `kit/tools/vendor.py` refuses with a message that says so (`kit.tools.packs.RETIRED`). A skill pack that imports `kit.retry` changes nothing else; every skill pack now receives `retry.py`. Tested in `kit/tests/test_packs.py` and `kit/tests/test_vendor.py`.

## [0.44.0] - 2026-10-26
### Added
- `kit/guards/research.py` and `suites.research(root)` (pack `testkit`, no new vendored module for a skill pack to import): research is kept, not repeated. `docs/research/` and `docs/prior-art/` each have a `README.md` that lists every file of the folder, and every link of the README is a file; a research file says `Researched YYYY-MM-DD` and tags a claim `[documented]`, `[vendor]`, `[academic]`, `[ours]` or `[inference]`; a prior-art file has its day in its name or on a `Scan date:` line. A skill pack with neither folder is not read. Lifted from the video-ads skill pack's `tests/test_research_index.py`; opt in with `suites.run(suites.research(ROOT))` in a test of your own (the scaffolder's generated `test_ssot.py` calls it from the next playbook pull request). Tested in `kit/tests/test_research.py` and `test_suites.py`.

## [0.43.0] - 2026-10-26
### Added
- `kit.guards.drift.behind(root)`: a hint, never a failure. When a skill pack's `skill-pack.toml` names a playbook checkout (`[kit] playbook = "../skill-pack-playbook"`, relative to the skill pack or absolute) whose `kit/VERSION` is more than two minor versions ahead of the vendored kit, `check_drift()` and the generated `tests/test_kit_drift.py` (`kit.testing.suites.kit_drift`) print `behind: kit X.Y.Z, playbook A.B.C`. Seen in the 2026-10-26 review: 14 skill packs on six different kit versions, none current, and nothing in their own suites said so. A skill pack takes it by re-vending (`python3 kit/tools/vendor.py --skill-pack PATH`), then adds the `[kit] playbook` line if it wants the hint. Tested in `kit/tests/test_guards.py`.

## [0.42.0] - 2026-10-26
### Removed
- `kit/questions.py` and its test (pack `learning`): open questions that never hold the plan. No skill pack imported it in the two minor versions after ROADMAP P1 parked it (counted 2026-10-26 on the fifteen skill packs that vendor the kit), so the admission rule removes it; the rule it checked moves from `docs/rules.md` (rule 13) to `docs/lessons.md`, as a lesson. A skill pack that re-vendors loses the file; none imports it. `learning` is `patternstore` and `pathweights`.

## [0.41.0] - 2026-10-26
### Added
- `kit/tools/pre-push.sample`: an optional second step after the leak guard. `git config skillpack.prepush-tests "<the pack's test command>"` runs that command from the top level before a push and refuses the push when it fails; unset (the default) it does nothing, and `git push --no-verify` skips the hook. Moves a failing suite ahead of a CI run that spends quota. A skill pack takes it by re-vendoring; no other change needed.

## [0.40.0] - 2026-10-25
### Added
- `creative` (new pack; ROADMAP X12, `docs/portfolio.md` "Engines in the kit"): the creative-side rules of the video-ads skill pack, pure and platform-free, four modules. `kit/creative_life.py`: a creative's state machine walked a day at a time (`testing`, `learning`, `doubt`, `mature`, `declining`, `parked`, `ended`), a blocked or partial day stops every clock, a person's override sets the state on its day, and the state names the wallet it spends from (mature and declining are proven: perform; the rest explore). `kit/fission.py`: the 0 to 1 score of how much a creative should go on being multiplied, read over its recent days against the median of the account's proven creatives, damped when it earns less each week; unknown, never 0, until a verdict is earned. `kit/creative_demand.py`: how many creatives to ask the maker for, from the exploration money, the measured cost per verdict (shrunk toward the doubt line while few), the lead time, whole batches inside the platform's limits, and the diagnosis `money_limited` or `surplus`. `kit/creative_portfolio.py`: the week's conversions against the week before, the projection, the half-life, the yield of a cohort and what closing a gap takes. A campaign's own state machine is `lifecycle` in `ads-core`. Their cases are the video-ads skill pack's tests, with its contract-file section left to `kit.contracts`.
- To take it: add `creative` to `[kit] packs` in `skill-pack.toml` (a pack with no `[kit] packs` line gets every pack), re-vendor, delete the pack's own copies and run its golden diff. Nothing existing changes. Test: `kit/tests/test_creative_life.py`, `test_fission.py`, `test_creative_demand.py`, `test_creative_portfolio.py`.

## [0.39.0] - 2026-10-25
### Added
- `console/` (issue #148, seen once in adcut): an ask may name who posted it, an optional `source` (a token of letters, digits and `. _ : @ / -`, at most 40 characters, allowed for every step). `ask.py list` and `ask.py digest` return it (`null` when the ask names none) and `ask.py schema` describes it; the console stores and returns it and never reads it. An ask without it is stored and hashed exactly as before. A skill pack that posts with its own name can tell its open asks from the rest on a console shared by several packs, with no per-folder memory. Nothing in `kit/` sets it yet: `kit.pending` filling it from the pack's cli word is the next pull request. To take it: re-vendor. Tests: `console/tests/test_core.py` (`test_source_is_a_kept_token_and_only_when_named`, `test_limits`), `console/tests/test_ask_cli.py`.

## [0.38.0] - 2026-10-24
### Added
- `ads-core` (new pack; ROADMAP W5/X12, `docs/portfolio.md` "Engines in the kit"): the rules that two or more ad skill packs wrote each for themselves, as pure functions with no database, no clock and no platform field. Nine modules. `kit/ledger.py`: a day is partial (exported on its own day), complete (after) or settled (after its attribution window); `Book` replays an import in memory: the same numbers add nothing unless the later export finishes or settles the day, the current row of a key is the newest export, a retraction brings back the rows a later import left out, a row that would count spend twice refuses the import (`Overlap`), two currencies under one owner refuse it (`CurrencyMix`). `kit/pacing.py`: a month's budget over its days by the account's own weekday weights, split into the perform and explore wallets, with `shortfall`, `result_met`, `no_performance` and `flat` flags; `cap_status()` for a monthly cap at the recent run-rate (a month with days missing is a lower bound, never `ok`). `kit/wallets.py`: an ad group is `perform`, `explore` or `none`, and `pay()` says which wallet pays a creative. `kit/allocation.py`: the perform wallet across campaigns, equal marginal return in bounded steps. `kit/proof.py`: proven and unproven (orders on days, never on the brand's own search; the loss verdict with hysteresis; the wallet move). `kit/alerts.py`: an entity's latest settled day against the mean of its own 7 settled days before it (spend or return, spike or drop), event days left out, a zero baseline coded, the cooldown. `kit/changes.py`: our own writes merged with the platform's recorded events, the learning window, the before and after windows, episodes, overlaps, and the noise test. `kit/reconcile.py`: two routes of one platform side by side. `kit/lifecycle.py`: a campaign's states and the hold that keeps one week's noise from moving them. Sources: the video-ads skill pack (`perfledger`, `perfread`, `pacing`, `adgroup`, `allocation`, `reconcile`, `campaign`: their cases are the tests) and the Amazon Ads skill pack (`compute_budget`, `certainty`, `compute_alerts`, `change_history`, `compute_changes`: their cases are the second set; it keeps its own copies, R3). The creative's own state machine (`life`) goes to the next pack, `creative`.
- To take it: add `ads-core` to `[kit] packs` in `skill-pack.toml` (a pack with no `[kit] packs` line gets every pack), re-vendor, delete the pack's own copy and run its golden diff. Nothing existing changes. Test: `kit/tests/test_ledger.py`, `test_pacing.py`, `test_wallets.py`, `test_allocation.py`, `test_proof.py`, `test_alerts.py`, `test_changes.py`, `test_reconcile.py`, `test_lifecycle.py`.

## [0.37.0] - 2026-10-23
### Added
- `kit/contracts.py` (new, pack `exchange`; ROADMAP R9, rollout phase 2b, step 2): the one way a pack writes and reads a contract file (`contracts/README.md`). `write(kind, version, body, out)` renders the first line (`# ads.results/1`) and the body, reads the result back through the check a reader makes, and writes it to `out` once: the same bytes again are a no-op, other bytes under the name are `exchange_would_overwrite`, and a document that does not fit its schema never reaches the disk. `read(path, kind, version, source)` refuses another mark (`exchange_mark_wrong`), another version (`exchange_version_unknown`) or a body that does not fit (`exchange_invalid`, with the problems), and otherwise saves the bytes as they came into `raw/<source>/` (`<kind>-<version>.<sha256[:12]>.json|tsv`; raw only grows) and returns a `Document`. A field the schema does not name is ignored. `schema()`, `problems()`, `parse()`, `render()` and `add_out_arg(parser)` (the `--out PATH` flag) are public. The check is the schema's basic keywords; a hub's exchange folder comes with the hub, so only `--out` for now.
- `kit/contracts.d/*.schema.json`: the twelve schemas of the playbook's `contracts/` (a test holds them equal), vendored with the module. `kit/message_codes.d/contracts.tsv`: six `exchange_*` codes. `kit/tools/packs.py` `module_of`: a file under `contracts.d/` belongs to module `contracts`, so a pack that takes no `exchange` does not get them.
- To take it: add `exchange` to `[kit] packs` in `skill-pack.toml` (a pack with no `[kit] packs` line gets every pack), re-vendor, and call `contracts.write` / `contracts.read` where the pack hands over or takes a document. Nothing existing changes. Test: `kit/tests/test_contracts.py`.

## [0.36.0] - 2026-10-23
### Added
- A client hub's exchange folder, the place packs hand each other versioned `--json` documents (ROADMAP R9, `docs/portfolio.md` "Contracts" and "Rollout" phase 2a). `kit/raw.py`: `exchange_write(hub, contract, producer, date, data)` writes `<hub>/exchange/<contract>/<producer>/<date>.json` once (`contract` is `name/version`, `ads.results/1`, its version a folder; `producer` the cli word; `date` YYYY-MM-DD; the hub's `exchange/` must exist) and refuses a name that is taken, identical bytes included (`exchange_exists`; two writers racing: the first stays), a malformed name or a day that is not real (`exchange_bad_name`) and a hub without `exchange/` (`exchange_no_folder`), writing nothing; `exchange_list(hub, contract)` returns the contract's `Document(contract, producer, date, path)` by producer, then date, and skips files that are not a dated `.json` and writes in flight; `exchange_scan(hub)` returns every document and the paths out of place. Nothing here reads a document or knows what a contract carries. A reader imports what it reads into its own `raw/`. No new module (a new one would sit outside `base`, which `doctor` cannot import), no new verb; `raw.save` is unchanged in behaviour (the claim of a name is now `_claim`, shared). Test: `kit/tests/test_raw.py` [6] to [8].
- `kit/doctor.py`, check `exchange`: with `<P>_HUB_DIR` set, ok with the count of documents and contracts; warns `doctor_exchange_missing` (a hub made before the folder; next: the `mkdir`) or `doctor_exchange_stray` (names up to five paths that are not at `<contract>/<producer>/<date>.json`). No hub named: no line. Test: `kit/tests/test_doctor.py` [10].
- To take it: re-vendor; a pack that writes a contract calls `raw.exchange_write`, one that reads calls `raw.exchange_list` and saves what it reads with `raw.save`. Nothing to add to `verbs.py`, no schema change.
### Other
- `scaffold/new_hub.py new` makes `exchange/README.md` (the rules above in four lines) and `exchange/.gitkeep`; the hub's `.gitignore` keeps both and ignores the rest of `exchange/` (the client's content); `CLIENT.md` and the agent's `CLAUDE.md` name the folder. A hub made earlier needs `mkdir exchange` (doctor says so). Test: `scaffold/tests/test_new_hub.py` [2] and [6].
- `docs/consoles.md`, "One client, several skill packs": the exchange folder, its layout and its write-once rule.

## [0.35.0] - 2026-10-22
### Added
- A client hub's facts, confirmed once at the hub and copied by each pack (ROADMAP X10, step 4). `kit/facts.py`: `<cli> facts sync-hub [--hub DIR] [--json]` (default `$<PREFIX>_HUB_DIR`, which the hub's `bin/hub` exports) reads the hub's store `<hub>/hub/hub.db` as one in-memory snapshot (the backup API over a `mode=ro` connection: consistent, the hub's read lock held only for the copy, never `immutable=1` on a live WAL file, never a write; SQLite may touch the hub's `-shm`) and takes the confirmed rows of the keys this pack's `fact_keys.tsv` declares, plus the declarations of its own markets, declarations first. A hub row whose last history row is not a `confirm` a person signed (tty, relay or the client's own) is `refused` (`fact_hub_ungated`); a market the pack does not keep, a key defined otherwise at the hub and a value the pack refuses are `skipped` (`fact_hub_skipped`). Each other row goes through `apply_hub_copy()`: `same`, `conflict` (the pack's own confirmed value differs: never overwritten, `fact_hub_conflict`), `copied` (absent or pending here: written confirmed, source `hub:<hub>@<history id>#<digest16>`, changed_by `<user>@hub`, history action `hub_copy`, now in `facts.ACTIONS`) or `kept` (this hub version was applied before: a person's later unconfirm stands). Summary `fact_hub_synced`; refusals `fact_hub_none`, `fact_hub_not_absolute`, `fact_hub_missing`, `fact_hub_unreadable`, `fact_hub_value_form`.
- `kit/schema_base.py`: a seventh human table, `hub_copies` (copy_id, market, key, value, hub, hub_history_id, hub_digest, outcome, pack_history_id, copied_at, copied_by; all NOT NULL, unique per market, key, hub, hub version and pack version), append-only (UPDATE and DELETE refused in the file). `schema_base.ADDED_LATER` names it and `db.with_human()` always passes it as `human_added_later`: a file written before it opens read-only as before, the next write-mode open creates it. **A skill pack's pinned `schema_hash` moves: bump its schema version when it re-vendors** (no row of any other table changes).
- A pack without markets (one workspace per market account) serves one hub market: `<P>_HUB_MARKET`, which the hub's `bin/hub` exports for a folder added with `new_hub.py add-pack --market M`. `sync-hub` copies that market's facts into the pack's `_` (its declaration never: no market door there; `hub_copies.market` is `_`, the hub row named by `hub_history_id` and a digest over the hub's own market, no column added); serving none, a hub row of a market is skipped (`no_hub_market`). A pack with markets keeps same-market copying and refuses a hub market (`fact_hub_market_partitioned`). `pending --hub` names a folder by `<P>_HUB_CLI` (ids, gate verbs, group), e.g. `gads-tw`.
- `kit/doctor.py`, check `hub` (`facts.doctor_hub`): with `<P>_HUB_DIR` set, each gated hub fact of a key the pack declares, in a market it serves, that `hub_copies` never saw warns `fact_hub_copy_missing` (key and market; also every hub row of a market for a pack without markets serving none), one seen at an older version `fact_hub_copy_stale` (the key, the hub's version and the one copied; next `<cli> facts sync-hub`); ok only when every checked fact is current; a hub row not from the gate warns `fact_hub_ungated`, a key defined otherwise `fact_hub_definition_differs`; all current is `fact_hub_current`. No hub named: no line.
- `kit/pending.py`: an open conflict (`facts.hub_conflicts`) is one `choose` ask (`hubfact-<market>-<key>-…`; the hub's value, recommended, or the pack's own), gated by `facts confirm KEY --value`; choosing the own value is a confirm that changes nothing. Codes `pending_title_hub_conflict`, `pending_why_hub_conflict`, `pending_if_no_hub_conflict`.
- `kit/registry.py` `definition_diffs(mine, theirs)`: what two fact key files say differently about the keys both define (type with its options, unit, min and max as numbers, the labels both carry; `why` and `group` are each file's own). `kit/guards/hub_keys.py` `check(hub, root=None)`: the same as a pack's test (`[]` = alike; no hub given checks nothing).
- To take it: re-vendor, bump the schema version, add `Verb(("facts", "sync-hub"), "facts.py", "human")` to `scripts/verbs.py`, and call `kit.guards.hub_keys.check(os.environ.get("<PREFIX>_HUB_DIR"))` from a test. Tests: `kit/tests/test_hub_facts.py`, `kit/tests/test_db.py` [6] [11].
### Other
- `scaffold/hub/` (new, not vendored): the hub's own facts program, the kit's `facts` and `pending` verbs over `<hub>/hub/hub.db`, run from the playbook like the hub's console. `scaffold/new_hub.py new --markets A,B` writes `hub/bin/hub` (it binds `KIT_SKILL_PACK_ROOT=<hub>/hub/defs`, `HUB_DATA_DIR=<hub>/hub`), `hub/defs/skill-pack.toml` (cli `hub`, env prefix `HUB`, the markets) and `hub/defs/fact_keys.tsv` (currency, npr_roas, avg_order_value, npr_includes_creator_fee, incremental_source, incremental_factor, defined as the two packs that hold them define them; the markets enter through the kit's door, `facts init`); `bin/hub hub …` runs it and `bin/hub <cli> …` exports `<PREFIX>_HUB_DIR`; the console relays `hub facts confirm` first and makes `HUB_CONFIRM_CODE_SECRET`; the deny list holds `hub facts confirm` and `hub facts restore`; `add-pack` refuses a pack named `hub`; `add-pack --market M` (required for a pack without markets in a hub with markets, refused for one with its own) gives the folder `<name>-<m>`, the dispatch name `<cli>-<m>` and `<PREFIX>_HUB_MARKET`/`<PREFIX>_HUB_CLI`, and the same pack may be added once per market; `hub/defs` and `hub/bin` are versioned, the rest of `hub/` is not. A short `CLAUDE.md` for the agent at the hub (how to start, one console, chat answers only for words and choices, intake, never a gate verb), rewritten by `add-pack`. Tests: `scaffold/tests/test_hub_program.py`, `scaffold/tests/test_new_hub.py`.
- `conformance/INVARIANTS.md`: how a hub copy keeps I3 (the human act is the hub's gated confirm, referenced by `hub_history_id` and `hub_digest`).

## [0.34.0] - 2026-10-22
### Added
- `kit/pending.py` hub mode: `<cli> pending --hub` (`asks(..., hub=True)`) makes asks for a client hub's one console, shared by every skill pack that serves the client. Every ask id starts with the cli word (`gads-fact-us-…`), every gate verb with it (`["gads", "facts", "confirm", key]`, relayed through the hub's dispatcher `bin/hub <cli> …`), every group with the skill pack's name (`google-ads · Facts, US`); the gate's `expect` is unchanged. A verb that would pass the console's word limit gets no gate and the coded warning `pending_gate_too_many_words`. A flag, not an environment switch. Without `--hub` nothing changes; the JSON gains `hub`. Test: `kit/tests/test_pending.py` [6].
- Console (re-vendored with the kit): a gate or relay verb may be 7 words (was 6), one more for the hub's cli word.
- Console: every ask may carry `expires` (`YYYY-MM-DD`, open through that day UTC, or `YYYY-MM-DDTHH:MM:SSZ`); `ask.py add` gives a new ask 7 days when it names none, and a revision keeps its own. Past it an open ask is `expired`: nothing changes, nobody can answer it, its id is never used again, `answers` and `wait` list it under `expired` until the agent records it with `applied ID`, `list --status expired` finds it, History and `digest` say "Expired unanswered: nothing changes". Derived from the clock and the events' own times, so no new event; `wait` also returns when an ask expires.
- Console: `ask.py chat ID --value=V --quote=TEXT [--source=TEXT]`, the agent's record of an answer the owner gave in chat: a new agent event `chat` (`via: chat`, `by: agent:NAME`, never signed, `verified: null`), checked like a click and applied like one; History shows it as "Answered in chat" with the quote and source, "not clicked here". Refused with the new code `gate_needs_click` for an ask with a gate, one that approves a change or one that takes a number.
- Console: the cap of 10 open asks is the owner's across every agent posting to one log (each pack `--as` its own name), now tested and said in `docs/consoles.md`.
### Changed
- The console's event log gains `chat` events, an ask's `expires` and answer rows' `via` (and `quote`, `source` for chat): additive. A log written before folds exactly as it did at any clock (`test_an_old_log_replays_unchanged_whatever_the_clock_says`); a console older than this one sets a `chat` event aside as `unknown_type`.

## [0.33.1] - 2026-10-21
### Fixed
- `kit.guards.release`: a `[release].must_ship` entry that is a directory (for instance `kit` where `scripts_dir` is `.`) ships when a tracked file under it ships and none under it is internal; it was always reported as `[release].must_ship paths do not ship`, because only file paths were compared. Seen in the video-ads skill pack (kit 0.30.1), which dropped `kit` from its list meanwhile (issue 108).

## [0.33.0] - 2026-10-17
### Added
- `console/manifest.py`, `console/frame.py`, `console/PAGES.md`: a skill pack registers its own pages and buttons with the
  console. One manifest file (`serve.py --manifest FILE` or `$CONSOLE_MANIFEST`; `ask.py --manifest FILE` or the same
  variable) declares `cmd`, `relay_verbs`, `max_open`, an optional `counts` verb and `pages` (name, zh/en title, order,
  the read-only verb that prints the page as JSON blocks, `blocking`). The pages join the built-in Waiting and History in
  one top bar with a number on each tab (the bar scrolls inside itself at 375 px), at `page-<name>`. A page `button`
  is relayed to the skill pack's gate with the console's own words: the form carries only the page and a hash, the page
  is drawn again at the click, and the click is the signed, append-only `action` event (a new human event type; `fold`
  gains `actions`; `ask.py verify` checks it). Read `console/PAGES.md` to write one; nothing changes for a skill pack that
  passes no manifest.
- `ask.py add` refuses (`invalid_ask`, field `gate.verb`, code `not_allowed`, naming the verb and the allowed ones) a gated
  ask whose verb the manifest's `relay_verbs` do not allow, instead of leaving the owner a form that can only be declined.
  A button on an unallowed verb is drawn as a sentence, and a forged click on it is refused (`verb_not_allowed`).
### Changed
- The cap of 10 open asks is the default of the manifest's `max_open` (1 to 100), no longer a constant of the store:
  `core.Store.post(max_open=...)` takes the caller's number (it no longer clamps it to `MAX_OPEN`); `ask.py add` passes
  the manifest's, or `MAX_OPEN`, and `--max-open N` still can only lower it. The budget line and meter of the Waiting page
  follow it. New codes `verb_not_allowed` and `page_unavailable`; new `relay.fetch()` runs a page verb the way
  `relay.run()` runs a gate (no shell, no stdin, no terminal, the console's secret withheld, killed on a timeout).
  Copy the console again to take it (`python3 kit/tools/vendor.py --skill-pack PATH --console`).

## [0.32.0] - 2026-10-17
### Added
- `kit.guards.roadmap`: an optional `## Milestones` section right after Next (rule 8 of its docstring). A row `- [M1] YYYY-MM-DD name. includes: X1, D2. closes when: the proof` is one integration unit; the guard refuses a row with no items or no proof, an item that is no row of the file or is not in Next/Done, an item in two milestones, a fourth open milestone, and a milestone whose items are all Done (it leaves and a Done row records it). A skill pack without the section is unchanged: nothing to do when re-vendoring.
### Other
- `docs/operating.md` rule 8, "Integrate by milestone, not by step": one branch per milestone, one commit per item (every commit with the whole local suite green; a refactor never shares a commit with a behaviour change), no merge request until the closing proof is green, a backup push without a pipeline (`git push -o ci.skip`), one merge request per milestone, an early one only for an owner's question (draft), a client's fix or the risky list, a milestone splits past about ten items or two weeks. `docs/roadmap.md` (planning item 6, executing item 3): a builder's branch merges into the milestone's branch, not main. Paid for in the video-ads skill pack: five merge requests in two days for one restructure, three stacked, each waiting for a pipeline the local suite had already answered.
- `templates/gitlab-ci.yml` and `templates/ci/gitlab-ci.yml`: pipelines run for merge requests, the default branch and tags, no longer for each push to a branch; the `story id` job also accepts `M..` in a title. `templates/AGENT_INSTRUCTIONS.md` and `templates/ROADMAP.md` say so. A skill pack takes it by copying the two `workflow:` and `story id` blocks.

## [0.31.0] - 2026-10-16
### Changed (breaking: a project must follow the table below when it re-vendors)
The noun "harness" is "skill pack" everywhere in the playbook: the kit, the console, the scaffolder, the build and
conformance tools, the templates, the Zylos adapter and the docs. Nothing else changed: no behaviour, no new check.
A project pinned at 0.30.x keeps working as it is until it re-vendors, because a vendored copy brings its own kit; the
rename is felt only when `kit/` is copied again (`kit/tools/vendor.py --skill-pack PATH`, or `scaffold/new_skill_pack.py
--update-kit`). Then follow the table, search the project for `harness` and run its suite.

| Old name | New name | Where |
| --- | --- | --- |
| `harness.toml` | `skill-pack.toml` | the project's one declaration; `kit.config.FILE`; renamed in the project root |
| `[harness]` (table in the TOML) | `[skill_pack]` | the keys under it keep their names (`name`, `cli`, `env_prefix`, `db_file`, ...) |
| `[harness].version` | `[skill_pack].version` | read by `kit.contract` |
| `HarnessError` | `SkillPackError` | `kit.contract` (and the raise/except sites of the project) |
| `HarnessConfig` | `SkillPackConfig` | `kit.config` |
| `KIT_HARNESS_ROOT` | `KIT_SKILL_PACK_ROOT` | the env var that binds a project root for tests and child processes |
| `<PREFIX>_HARNESS` | `<PREFIX>_SKILL_PACK` | the checkout path in a client's wrapper (`scaffold/new_client.py`) |
| `--harness` | `--skill-pack` | `kit/tools/vendor.py`, `scaffold/new_client.py`; `tools/fleet.py` names its arguments `SKILL_PACK...` |
| `scaffold/new_harness.py` | `scaffold/new_skill_pack.py` | the project generator; its tests `scaffold/tests/test_new_skill_pack.py` |
| `skills/build-harness/` | `skills/build-skill-pack/` | the build skill |
| `templates/harness.toml` | `templates/skill-pack.toml` | the template for `skill-pack.toml` |
| `kit.messages.harness_files` | `kit.messages.skill_pack_files` | the project's message-code files |
| `kit.guards.drift.check_harness` | `kit.guards.drift.check_skill_pack` | the drift check of a vendored copy |
| `kit.contract.harness_version` | `kit.contract.skill_pack_version` | |
| `kit.tools.packs.harness_imports` | `kit.tools.packs.skill_pack_imports` | the import reader of the pack table |
| `DecisionRegistry.harness_written` | `DecisionRegistry.skill_pack_written` | `kit.registry` |
| `confirm = harness` (decision keys) | `confirm = skill_pack` | the value in the `confirm` column of `ssot/decision_keys.tsv`; `kit.registry.CONFIRM` |
| message code `decision_harness_written` | `decision_skill_pack_written` | `kit/message_codes.d/decisions.tsv` |
| message code `doctor_harness` | `doctor_skill_pack` | `kit/message_codes.d/doctor.tsv` |
| `origin: "harness"` (merged message registry) | `origin: "skill_pack"` | `kit.messages.registry()` |
| key `harness` in the `--json` meta and in `doctor --json` | key `skill_pack` | `kit.contract`, `kit.doctor`; `kit.guards.json_contract` checks it |
| doctor check id `harness` | `skill_pack` | `kit.doctor` |
| `FAKE_HARNESS_*` | `FAKE_SKILL_PACK_*` | the fake used by the console and golden tests |
| `kit/tests/fake_harness/`, `fake_harness.py` | `kit/tests/fake_skill_pack/`, `fake_skill_pack.py` | test stand-ins |
| `{{harness_name}}`, `{{harness_dir}}` | `{{skill_pack_name}}`, `{{skill_pack_dir}}` | placeholders in `templates/client/` |
| `harness.py` (a project's entry file) | `skill_pack.py` | name used in the docs and the tier table only |
| prose "harness", "harnesses" | "skill pack", "skill packs" | docs, docstrings, messages |

Not renamed: the repository and directory name `Agent-Harness-playbook` and the title "Agent Harness Playbook" (the
repository's own name), the names of other projects (`shop-harness`, `adcut-harness`, `amazon-ads-harness`, ...), the
old entries of this file and the generic phrase "test harness" (the little runner in each `tests/_t.py`).
Each of these is one mechanical search and replace in a project; the whole suite of the playbook (`python3 run_all.py`)
passes on the new names.

### Other
- `hosts/zylos` 0.3.1: wording only (the usage line of `bin/detach.js`, comments and the README say "skill pack"); no behaviour change. Copy the folder again to take it.
- `docs/lessons.md` and the other docs say "skill pack" for the noun; the sibling projects keep their own names.

## [0.30.1] - 2026-10-13
### Fixed
- `kit.guards.pages` read a vendored kit that sits at `kit/` (`scripts_dir = "."`): the skip path was `./kit`, which matched nothing, so the guard flagged its own host line. The path is normalised. Seen in the video-ads harness, which allowed the line meanwhile.

## [0.30.0] - 2026-10-13
### Added
- `kit.guards.pages` (pack `testkit`) and `suites.page_links(root)`: a page the harness delivers is drawn by the harness
  (`docs/rules.md`, data layers), so no file the harness ships links to a hosted artifact. `check_links(root)` reads
  what `git archive` ships (untracked files are not read; nothing tracked is a problem; with no repository the whole
  tree less .git, virtualenvs, caches and node_modules, never a skip) as text unless it holds a NUL byte (UTF-16 with a
  byte order mark is decoded) or is over 5 MB, follows no symlink, and
  names each file and line that holds a hosted-artifact link, never the link. A line is read after HTML-entity,
  percent (twice), `\uXXXX` and backslash decoding, with a trailing dot or a port on the host and a link wrapped across
  a line break; a link built from parts is not read. Not read: the vendored kit and console (when they hold a
  MANIFEST.sha256) and harness.toml's `[guards.pages]` tables. A link in an export-ignore file is fine.
  `[guards.pages]` takes `hosts` (more hosts) and `allow` ({path: reason} or {path: {reason, max}}; a row with no
  reason, a gone path, a file that does not ship or holds no such link now, or one over its `max` is a problem; a bad
  config is a problem). It errs toward a false hit (any text that spells a host, prose included), which an `allow` row
  answers. `self_test()` plants each form. Seen once, in the video-ads harness (owner decision 2026-10-13). A harness
  opts in with `run(suites.page_links(ROOT))` in a test; `templates/harness.toml` documents the table.

## [0.29.0] - 2026-10-13
### Added
- `kit.pathweights.past_signal(units, groups, cfg)` and two thresholds, `past_min_expected_conv` (3) and `past_warn_units`
  (3): past results (a client's past ads, another period and another hand) as a gap signal, never a weight
  (`docs/path-weights.md`, "Past results"). A group of past units is judged against the past pool's own rate, never the
  account's (P(better) under Gamma-Poisson, the prior worth `prior_conv`), speaks once its spend buys
  `past_min_expected_conv` at that rate, and reads strong or weak at `promising_p` and `downweight_p`. `gaps` are strong
  groups with none of the plan's own units, `warnings` weak groups with `past_warn_units` or more. Nothing from it is an
  input of `posteriors()`, `judge()` or `pick()`: the test holds that their results do not change when the past is read
  and that none of their sources names it (no module state is left behind), and it measures how often an equally good group
  reads strong or weak (about 1 in 6 and 1 in 5 with Poisson noise only, a third and 2 in 5 with spread between units).
  The pool includes the group, so a group that is most of it reads conservatively; `p_better` and `expected` are
  rounded and the read is decided on the rounded numbers. Additive: `settings()` gains two keys, and nothing else changes. Seen once, in the video-ads harness
  (its ROADMAP D64), which keeps its own copy for now.

## [0.28.0] - 2026-10-13
### Added
- `kit.questions` (pack `learning`; rule: `docs/rules.md`, human-in-the-loop rule 13): open questions that never hold the
  plan. A question names `by_data` (the data that can answer it, from the harness's closed list of kinds, or `ask_only`)
  and `meanwhile` (what the plan does until then: an action, never a wait). `problems(questions, sources)` is the check a
  harness's tests run (a missing or repeated id, a `by_data` outside the kinds, a blank, placeholder or waiting
  `meanwhile`; an answered or dropped question needs neither). The wait test is a floor: it catches the obvious waits
  (English, a few Chinese, `extra_waits` for a harness's own words); a word that also opens ordinary actions (hold,
  pause, stop) counts only in a short text or with an "until" cue, and a short one may be a false hit, which a reworded
  `meanwhile` answers. `groups()` sorts the questions for a page; `readback(questions, held)` lists the unanswered ones
  whose data the harness now holds and has no read record for (the record is the fingerprint the agent read, so a new
  version of the data prompts again; `ask_only` never does); `self_test()` plants each break and the words its problem
  must say. Pure, stdlib only, no message codes. Seen once, in the video-ads harness (its ROADMAP D65), which keeps
  its own copy for now.

## [0.27.0] - 2026-10-13
### Added
- `kit.autonomy` (new pack `autonomy`; imports nothing from the kit): the autonomy levels' shared mechanics, pure over
  data the harness passes. The tier registry under the harness's own column names (`canon`) and its check
  (`check_tiers`: a tier-B or auto row names its undo, an auto row's undo is a registered code-free undo, no orphan
  undo row); `tier_of`, `eligible`, `ids_of`. The owner's switch, one fact `YYYY-MM-DD:ID,…` (`switch_value`,
  `parse_switch`), on only while its latest history row is a person's confirm, clamped to `max_days`, its ids frozen
  so a registry edit narrows and never widens (`mode`), an agent's write only ever off (`may_set`). The verdicts:
  `approval_why` (L2, a fixed order) and `auto_verdict` (L3: a cap, an unverified last write or a mixed run is a
  stop, no code issued). Caps from the archive (`used`, `tighten` only lowers, `lock`). The record (`gate`,
  `suffix`, `proof_level`), code-free undo (`undo_free`, `undone_by`) and the digest. No harness imports it yet: the
  SEO harness keeps its own copy (`scripts/apply_shopify.py`), so it is extra with no consumer (`kit-tiers.tsv`).
  Test: `kit/tests/test_autonomy.py`.

## [0.26.2] - 2026-10-13
### Fixed
- `tools/leak_guard.py` failed open when a `re:` term sat beside other terms: every term was
  joined into one pattern and a line it missed was passed over. Joined, a later term's
  backreference pointed at another term's group (`re:(a)\1` then `re:(b)\1`: an added `bb`
  passed, though `re:(b)\1` alone refused it); and on Python 3.9 (macOS's `/usr/bin/python3`,
  which a pre-push hook may run) an inline global flag not at the start, such as `(?a)`, only
  warned and reached every term (`re:X\wY` beside `re:(?a)zzz`: an added `X示Y` passed under
  3.9, refused under 3.12). Now only plain terms are joined for the quick pass; every `re:`
  term is always searched on its own. Seen once, in the video-ads harness, whose own guard
  fixed it first. (Carried from PR 83, written against 0.21.0.)

## [0.26.1] - 2026-10-13
### Fixed
- `kit.guards.ssot.check_writes` missed writes 0.25.0 caught. 0.26.0's refinements are dropped where they cost a hit:
  a name is a path when any binding of it in its scope is (0.26.0 kept only the last one in straight code); `self.p`
  is matched by its text in any class (0.26.0 keyed it by the inheritance family); a name imported from any scanned
  module is matched by the name alone, so a star re-export or an import path with a package prefix is followed again
  (0.26.0 looked the name up in the one module the import path named); an attribute that holds an ssot path is a path
  whatever it is called (`self.name`), and only `.name`, `.stem`, `.suffix` and `.suffixes` of a path are its words
  (`.parts` rebuilds the path); a call returns data only when its name's first word reads (read, reads, reader,
  readlines, load, loads, parse) or it ends in rows, so `ensure_ready(SSOT)` or `upload_dir(SSOT)` is a path again.
  0.26.0's additions stay: `m.NAME` and `from pkg import m` are followed, os.walk's file names are not paths, a class
  attribute is followed into `self.p`. The rule prefers a false hit, which a writers row answers, to a miss
  (`docs/lessons.md`, "A guard's refinement never costs the recall it had"); each missed write is a must-hit case of
  `writes_self_test()`, and a test holds the list. Run case by case against 0.25.0, the only hits 0.26.1 no longer
  reports are three false ones: copying out of ssot under a file's own `.name` or `.stem`, and writing a row's own file
  with what a read returned from ssot.
- `facts confirm` without `--value`: a test that it confirms the stored value as stored (0.26.0's behaviour).

## [0.26.0] - 2026-10-13
### Added
- `kit.testing.suites.ssot_writes(root)`: the ssot write rule alone (its self-test and `check_writes`), reading no
  ssot index; `suites.ssot` ends with it. A harness that uses `suites.ssot` already runs it; one with its own
  `tests/test_ssot.py` adds `suites.run(suites.ssot_writes(ROOT))` (0.25.0 said every ssot test ran it on re-vendoring:
  only the generated one did).
### Changed
- `[guards.ssot.write_skip]` is a {folder: reason} table: each row needs its reason, and a row whose folder is gone is a
  problem (a list gives no reasons, so each entry is reported). The vendored kit is always left out, with no row.
### Fixed
- `check_writes` read some paths wrong. Now a path's words (`.name`, `.stem`, `.suffix`) are not a path, so
  `shutil.copy(CONST, DATA / CONST.name)` passes; a name the word `ssot` is in is a path only when it is not bound to
  data (a call that builds no path: `ssot_rows = read_tsv(...)` is rows, `ssot = Path(sys.argv[1])` is still a path); a
  name bound only by plain assignments in its scope's own statements holds what the last one above the line put in it
  (under a branch, loop, try, augmented assignment or comprehension any binding still counts); `self.p` is keyed by its
  class and followed into subclasses in the module (any other attribute by its text, as before), and a class attribute
  (`p = Path(...)` in the class body, then `self.p`) is followed; another
  module's ssot name is followed as `m.NAME` and `from pkg import m`, through a re-export, and only from the module
  that defines it (a same-named data path elsewhere passes); os.open writes unless its flags only read; os.walk and
  os.scandir keep a path. Each entry of `write_code` must find code (a misspelled one beside a good one was silent); a
  file is parsed as bytes (a UTF-8 BOM parses; a NUL byte is reported, never a crash); an expression too deep to read
  is reported, never a crash; a virtualenv or `site-packages` inside the harness is not its code; a writers file row
  under a folder row is used, not stale. `writes_self_test()` tries each form.
- `Thresholds.confirmed()` (and `load`, `get`, `overridden`) drops a confirmed `threshold_<name>` fact outside the
  TSV's current min..max, so the default stands; `Thresholds.out_of_bounds(con)` lists those facts for a harness's
  doctor (the client is asked again) and `facts list --thresholds` shows `default (outside min..max)` for them;
  `facts confirm` without `--value` checks the pending threshold value against today's bounds
  (`fact_value_out_of_range`) and confirms the value as stored. Both are what `docs/rules.md` "Registries" item 9 says: a value
  the bounds refuse is refused when written and again when read, since a bound may have moved.

## [0.25.0] - 2026-10-13
### Added
- `kit.guards.ssot.check_writes` (run by `kit.testing.suites.ssot`; a harness with its own `tests/test_ssot.py` adds
  it, see 0.26.0): `ssot/` is the builder's, and what a client sets or decides through its agent lives in that
  client's own database (`docs/rules.md`, "Registries", item 9). The check fails on harness code that writes under the
  ssot dir, by AST, as `path:line` and never what is written: Path `write_text` / `write_bytes` / `touch` / `unlink` /
  `mkdir` / `rename` / `replace`, `open` (builtin, Path, io, codecs, gzip, bz2, lzma, os) with a write mode (a mode that
  is not a literal counts), `os.replace` / `rename` / `remove` / `makedirs` …, `shutil.copy*` into it, `move`,
  `rmtree`, `kit.atomic`'s writers, and the harness's own helpers named in `[guards.ssot] write_calls`. A path is under
  ssot when its expression holds the dir as path segments, an identifier with the word `ssot` (`SSOT`, `cfg.ssot`,
  `ssot_dir`), or a name bound to such a path in the same or an enclosing scope, or at module level in another module
  it imports; a value read from an ssot file is data, not a path, so reading ssot, copying from it and writing a row's
  own file elsewhere pass. It reads every .py of the harness (`write_code`, default the whole tree; `write_skip`,
  default the vendored kit), never a test, a hidden folder or `node_modules`. `[guards.ssot.writers]` = {path or folder:
  reason} names the builder's own tools that may write there: a row with no reason, or one that writes nothing any
  more, fails. A file that does not parse, or a code path that finds nothing, is not a pass. `writes_self_test()` is
  its planted self-test, also in the suite. A harness whose code writes ssot fails the check: move the client's value to its database, or name a builder's tool in `writers` with its reason. Seen
  once, in the video-ads harness (owner decision 2026-10-13: a client's space thresholds go through a `set` verb into
  an append-only table of its database, over the ssot default).

## [0.24.0] - 2026-10-13
### Added
- `kit.pagestyle` (new pack `pages`, `[kit] packs = ["pages"]`; `docs/page-style.md`): one look for the pages a harness
  writes to guide making and show the reasoning (a plan's map, the next batch, a make page, an insight page). A state is
  colour, word and icon (`chip()`, `vchip()`; the five states of `kit.pathweights`, Okabe-Ito blue and orange, grey for
  closed; each state's text 4.5:1 on its fill in the light theme and both dark ones, and nothing dims it: no opacity,
  the map's hover only as dark as keeps 4.5:1); a status bar and number tiles first (`bar()`, `legend()`, `tiles()`; a
  count is a whole number of items, anything else refused); one decision with one copy button and its hint
  (`decision()`; a command without its hint refused), commands, flags, ids and hashes (either case, after Chinese text
  too) only there and in folds (`data-zone="decision"` / `"tech"`: `details()`, `owner()`); at most three warnings on
  the page, all its boxes together, the rest one line that names the owner's fold (`warnings()`; a limit above three
  refused); a node map with one cell per item, each a link with its title, as many to a line as the waffle column's
  width holds so none is past the map's edge, a stated node's icon never cut, and an empty leaf that says why
  (`node_map()`; a cell without a title or a link and a node with nothing under it and no why refused, a text left None
  empty); cards that unfold row by row with ten dots and if it works / if it does not (`fold_row()`, `card()`,
  `story()`, `dots()`, `expand_all()`); the owner's fold, folded and last, which the more line names by its title up to
  the colon (`fold_name()`), so `owner` and `more` are renamed together. `page()` is the whole document: doctype, lang,
  a CSP that allows no network (`default-src 'none'`, never `'self'`, an image only inline as `data:`), light and dark
  tokens on `:root`, the page data as strict JSON with no `</` (NaN and Infinity refused), filled in one pass (a text
  holding `__DATA__` stays text), a script that holds no word (a button's words, its label too, are its own attributes;
  a copy button comes back to its label after quick clicks and after the fallback). Every visible word is the
  harness's: `Style(words, lang)` lays them over `EN` and refuses an unknown key, an empty word, a template without
  `{n}` or a `more` that does not name the owner's fold; `ZH` is a ready Simplified Chinese set; the module-level parts
  are English; a Style carries every name the module exports; the currency is the harness's (`money`: `"¥{n}"`).
  `problems(page)` is the check a harness's tests run on every page, one line for each rule a page can break (the
  skeleton with the style's own stylesheet and script, nothing loaded from outside the page, the harness's CSS dimming
  or recolouring no state, a status bar or tiles before the one decision zone, one copy button with its hint and only
  there, no command, flag, hash or code outside the zones plus the harness's own patterns, three warnings on the page
  and a more line that names the owner's fold, the owner's fold folded and last, every card in a row, a state's icon and
  word on every chip, node and cell, a title and a link on every cell and none past the map's edge, every in-page link
  landing, a node with nothing under it saying why, no grid wider than a 320px phone's column, its fixed tracks added
  up); `zones(page)` is the visible text by zone. Its test runs the copy button's script under node, so the `kit` suite
  of `run_all.py` names node beside git. From the video-ads harness's page style (seen once, 2026-10-13; the owner made
  it the model for such pages), which keeps its own copy for now.

## [0.23.0] - 2026-10-13
### Added
- `kit.pathweights` (pack `learning`; `docs/path-weights.md`): path weights for variants that come back with spend and
  conversions. Exact Gamma statistics, stdlib only (`gamma_cdf`, `p_above`, `quantile`, run to convergence at any
  shape, ValueError rather than a truncated value; `tenths` rounded toward a half). `posteriors()`: each leaf of a
  partition (its ancestors' keys in order, any depth; a set refused) gets a Gamma-Poisson posterior on its settled
  numbers, the prior borrowed leave-one-out from its parent and worth `prior_conv` conversions, an optional per-leaf
  prior factor clipped to [1 / `prior_shift_max`, `prior_shift_max`]; conversions may be fractional; a node's numbers
  are its leaves' sums and the account covers them all. `judge()`: untested, testing, promising, down, closed, each
  with its reason (the account's warmth decided under the thresholds it is given), and a close proposal (down, enough
  settled spend and units, unlikely to reach `close_ratio` of the account rate) that a person confirms and the harness
  records: never decided here. `pick()`: the next batch over the harness's moves, coverage order when cold, batched
  top-two Thompson when warm, at least `explore_share` from moves not known yet, half a batch per group, `exclusive`
  and `shared` keys (a list or a set, kept sorted), a move within the batch before one up to two over (taken only when
  none fits, the explore share too), the seed from the data, the same in any process. `twins()`: same-tag units whose
  rates differ by `twin_ratio` (above 1) with probability `twin_p`, a clue with what is known to differ. Every
  threshold in `DEFAULTS`; `settings()` refuses one that is not a value, naming the key, and a `downweight_p` not
  below `promising_p`. The test includes the calibration (every leaf equally good, five rounds, spend pushed to early
  leaders: at most 5 in 100 made leaves ever proposed for closing). From the video-ads harness's creative space model
  (seen once, 2026-10-13), which keeps its own copy for now.

## [0.22.0] - 2026-10-12
### Added
- `human.py`: `relay_audit(..., relay_quote, need_quote=True)` and `add_gate_args(quote=True)`
  (`--relay-quote`). A verb whose write leaves the harness on a person's chat yes asks for the
  confirming person's own words, as sent, beside `--relay-user` and `--relay-at`; a relay
  without them is refused (`confirm_relay_quote_missing`), and the words are kept on the
  history reason as ` [quote="…"]`, one JSON string that cannot close the suffix. The code
  proves the person saw the summary; the words show what they said to it. Off by default:
  existing callers are unchanged, and the console (which relays a click, not words) never
  confirms such a verb. From the SEO harness (seen once, an owner decision on its store write,
  2026-10-12).

## [0.21.0] - 2026-10-12
### Added
- `kit.workbook_patch` (pack `workbook`, slice 4 of `docs/workbook-and-browser-ops.md`): cells set
  in a copy of a client's xlsx, stdlib only. Every part it does not set stays byte for byte (a
  sheet with cells to set is edited as text, cell by cell; texts inline, styles kept); the workbook
  part gains full recalculation on open; the same inputs give the same bytes. A formula, a value
  the client entered (not the harness's previous copy, `ours`), a merged cell or a missing sheet is
  never set, listed by ref. `table_sets` places a harness's results by the map (a table's `out` and
  `both` columns by key, new columns in the first column after the header block that is empty on the header row and every row of the table, never under the client's own data, found again by header on the next copy); `cell_sets` fills
  the map's new `cells.tsv`. First consumer: the KOL harness (meta-ads-retail-harness X39), which
  tried it on the client's real workbook: two parts changed, every other part identical.
- `kit.workbook_map`: an optional `cells.tsv` (`field, sheet, cell, owner, status, note`), where a
  harness writes outside a table's rows (a month's figure across a row); a cell written by two rows
  is refused (`workbook_map_cell_twice`); `confirmed()`, `pending()` and `confirmed_rows()` carry
  it, so the file gate binds it; a map without it keeps its version.
### Other
- `templates/claim-scope.md`: "What stops, what warns". A harness picks per channel whether an
  open compliance finding stops the step or warns a person (one switch, `warn` or `block`); where
  the platform's own review stops a bad ad at no cost to the ad, the default is `warn`. Unconfirmed
  spend, the spend gate, consent and technical QC always stop. Seen once, an owner decision in the
  video-ads harness. Tested in `tests/test_docs_build.py`.
- `docs/operating.md`, "Keeping a harness small as it grows": slim before features (an inventory
  by loop stage, one home per concept, a `_parked/` folder with no verbs, docs or tests and a way
  back, no new features while slimming), code filters and the agent judges (candidates listed
  unranked, a skill picks with a `why` the code checks), and a newcomer-agent acceptance test
  (`templates/client-handoff.md` rule 4 points at it). `docs/lessons.md`: a detached job that
  vanished without its end gets one notice on the next listing; `templates/install-checklist.md`:
  keep the harness, data and virtualenv on the internal disk. Each seen once, in the video-ads
  harness. Tested in `tests/test_docs_build.py`.
- Scaffold: the next steps `scaffold/new_harness.py` prints end with the leak guard, in order:
  create the client-term list outside the repository (seeded with the client's name from the
  intake), name it in `[guards.leak] terms`, install `scripts/kit/tools/pre-push.sample` as the
  pre-push hook, push. The hook is installed only once a list is named, since it refuses a push
  without one.

## [0.20.0] - 2026-10-12
### Fixed
- `messages.lint_registry()` (and so `check_registry_closed()`) refuses a registry param named
  after one of `msg()`'s own arguments (`code`, `text`): `msg(code, text, **params)` cannot be
  called with it, a TypeError at the one moment the message is needed. The names are read from
  `msg()`'s signature (`messages.MSG_ARGS`), so they cannot drift. Seen once: in the video-ads
  harness a param named `text` crashed `msg()`, and that harness has held the rule in its own
  contract test since.

## [0.19.0] - 2026-10-12
### Added
- `doctor.py`: `checkout` warns (`doctor_checkout_differs`) when the cwd is in another git
  checkout of the same harness (a `harness.toml` of the same name at or above it) than the
  bound one whose code runs, and the two differ: other HEADs, or docs or code (`*.md`, `*.py`,
  `*.toml`, `*.tsv`, `*.js`, `*.sh`) changed and not committed in either. Several sessions
  work in worktrees; an agent read SKILL.md in one and ran another's harness. Silent outside
  git, without git, in the bound checkout and in another harness's checkout. `git_head()`
  (HEAD plus the uncommitted docs and code; git's optional locks never taken; inherited
  `GIT_*` variables dropped, so a hook's `GIT_DIR` cannot point both at one repository).
  From the video-ads harness (seen once, a newcomer-agent audit).

## [0.18.0] - 2026-10-12
### Added
- A "Never" table of the verbs only a person runs, first in a harness's SKILL.md, held to the
  verb table (`kit/guards/evals.py`; seen once: a newcomer agent found the video-ads harness's
  person-only rules scattered over five places, and that harness gathered them in one table at
  the top of its SKILL.md). `never_problems()` and `check_never_table()` fail when a verb of
  kind `gated`, or one `[guards.evals].extra` names, has no row; when a row names a verb an agent
  may run, or no verb of the table, or does not say why; and when `## Never` is not the first
  `##` section. A cell names verbs in code font, with or without the cli word; a code span with
  a flag is a flag-level gate (`claims --confirm`, an agent's verb with a person's flag, or
  `any --code`, a flag on every verb): its verb must exist (or be `any`) and need not be gated.
  YAML front matter is skipped. The kind `external` is not person-only by itself (an external
  read, a pull, is the agent's own; an eval forbids it only because the run is offline): an
  external write only a person runs (`execute apply`) goes in `extra`. `[guards.evals].never`
  renames the heading. `never_self_test()` plants each fault, `check_never()` reports, and
  `kit.testing.suites.never_table(root)` is the suite a harness's test calls.

### Other
- Template `SKILL.md`: a `## Never` section first, the table of the verbs only a person runs
  (`facts confirm`, `decisions confirm`, `facts restore`, `facts init`, `queue approve`,
  `execute apply`), each with why; "Out of scope" points to it instead of listing them again.
  `templates/harness.toml` sets `[guards.evals] extra = ["facts init", "execute apply"]`.
- Scaffold: a thirteenth generated test, `tests/test_never_table.py` (`suites.never_table`), so a
  new harness's Never table stays the verb table's. A harness scaffolded before adds the table
  and the file (any generated test, calling `suites.never_table`) by hand; until then nothing
  changes for it.

## [0.17.0] - 2026-10-12
### Added
- `tools/leak_guard.py` and `tools/pre-push.sample` (testkit): a push whose added lines, file paths
  or commit messages hold a client term is refused; `--range A..B` and `--tree` check by hand. A
  term matches case- and whitespace-insensitively (`re:` for a regular expression), and a hit names
  the term's line and list, never the term. The lists are client data and stay outside the
  repository: `[guards.leak] terms` in harness.toml (paths or globs, one list per client workspace)
  and `<PREFIX>_CLIENT_TERMS`. Fail closed: no list, a named list missing, an empty or unreadable
  list, a bad pattern, one matching the empty string, or a git error refuses the push. Generalised
  from the video-ads harness's own guard and its local hook, which read every client workspace's
  list (seen once). Fixed here, and still open in that harness's copy: a non-ASCII path was read
  as git's octal escape, so a CJK term in a file name passed; a path hit printed the path, which
  holds the term; full-width and zero-width spellings passed (terms and text are now NFKC-normalised
  without format characters); a binary or empty file's path and a merge's own resolution lines
  were not read; an added line starting `++ ` was taken for a file header. Two `git log` runs read
  every commit, and all terms are tried as one pattern first: 125 commits and 200 terms take about
  0.1 s, not seconds.
### Other
- BUILD.md B1: install the hook before the first push; `templates/harness.toml` shows
  `[guards.leak]`. `kit-tiers.tsv`: `tools.leak_guard`, extra, no consumer yet.

## [0.16.0] - 2026-10-12
### Added
- `kit.testing.run_tests`: a file's own budget, a `# kit-timeout: S` comment (a comment may follow
  it), and `--timeout S` for
  one run's default (still 300 s), so a slow end-to-end file need not make every hang wait as long
  as it does (#56; the video-ads harness's files that build whole outputs take 3-5 minutes, every
  other file under 40 s, and it raised its one timeout to 600 s).
- `KIT_TEST_RUN=1` (`kit.config.TEST_RUN_ENV`) marks a process as a test: the runner exports it to
  every file, importing `kit.testing.check` sets it, `sandbox_env()` hands it to every child. A
  harness that honours the `KIT_TTY` seam only in a test checks it, not pytest's variable (#56; the
  video-ads harness's seam was refused under the runner and passed under pytest). It tells a test
  from a run; any process can export it, so it is no security boundary.
### Fixed
- `run_functions()` fails a file with a top-level `test_*` it never collected, naming it (defined
  below the call, or hidden by a decorator without functools.wraps): such a test never ran, and the
  file still printed `RESULT: N passed` (#56; the video-ads harness, 38 tests in 8 files).
- `sandbox_env()` drops every credential-looking variable (a name ending in TOKEN, _KEY, _KEY_ID,
  PASSWORD or _API, or holding SECRET), as the video-ads harness's own test setup does; a test
  passes the one it needs as an extra.
### Other
- Console: `tests/_t.py`'s `main(globals())` fails a file the same way (#56).
### Changed
- `kit/env.py`: `KIT_TEST_RUN` joins the names never loaded from an env file (with 0.15.0's list).

## [0.15.0] - 2026-10-12
### Changed
- `env.py`: the env chain never loads a gate secret or a test seam from a file, only from the
  process env: any `*CONFIRM_CODE_SECRET` (kit.human's relayed-code key, any harness's prefix),
  `CONSOLE_SECRET`, `KIT_TTY`, `PYTEST_CURRENT_TEST`, `KIT_HARNESS_ROOT`, and `DYLD_*`, `LD_*`,
  `PYTHON*`, plus a harness's own `[env].never_from_file` names. Such a line (plain, `export `
  or spaced) is skipped by `load`, `resolve`, `get` and `load_into_environ`;
  `is_gate_secret()`, `never_from_file()`, `EnvChain.refused()` (file and name, never the
  value). An agent can read or write a .env; with the secret or the seam it could mint its own
  approval. From the video-ads harness (seen once). No harness code changes; a deployment that
  kept one of these in a .env sets it in the process env of what runs the gate instead (the
  steps for a client console and a Zylos host are under Other).
### Added
- `doctor.py`: `env_files` warns for each such line, naming the file and the name, never the
  value (`doctor_env_gate_secret_in_file`, `doctor_env_file_unsafe_name`); its `next` says to
  delete the line and, for the confirm-code secret, the `bin/console` edit below.
  `console_secret` warns when `CONSOLE_SECRET`, which the console withholds from every harness
  call, is in the harness's own process env (`doctor_console_secret_in_env`).
  `<P>_CONFIRM_CODE_SECRET` there is not warned: the harness process issues and checks the code.

### Other
- Scaffold: a new client's `bin/console` exports a fresh random `<P>_CONFIRM_CODE_SECRET` into
  its own process env at each start instead of appending it to `workspace/.env`. **Deployment
  step for an existing client** (its generated `bin/console` is not regenerated): in
  `bin/console`, replace these 4 lines

      envf="$root/workspace/.env"
      if ! grep -qs '^<P>_CONFIRM_CODE_SECRET=' "$envf"; then
        (umask 077; printf '<P>_CONFIRM_CODE_SECRET=%s\n' "$(openssl rand -hex 32)" >> "$envf")
      fi

  with these 2, delete the `<P>_CONFIRM_CODE_SECRET=` line from `workspace/.env`, and restart
  the console; until then a console click ends in the no-terminal refusal.

      <P>_CONFIRM_CODE_SECRET="$(openssl rand -hex 32)"
      export <P>_CONFIRM_CODE_SECRET

  `.env.example`, `templates/harness.toml` and the operator README say where the secret goes.
- `hosts/zylos` 0.2.0: `bin/console.js` exports a fresh random `<PREFIX>_CONFIRM_CODE_SECRET`
  into the console's process env at each start (its relay read it from `<data dir>/.env`,
  which the kit no longer loads); the configure hook refuses a gate secret
  (`*CONFIRM_CODE_SECRET`, `CONSOLE_SECRET`) and writes nothing; the manifest and `SKILL.md`
  config may not name one. Re-vendor `zylos/` and delete the line from `<data dir>/.env`.

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
