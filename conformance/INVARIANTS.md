# Invariants

What every growth skill pack built from this playbook keeps, however it is written. A skill pack may vendor the [kit](../kit/README.md) or have its own tables; it conforms when these hold. Each row says who showed it and whether [`check.py`](check.py) can test it from outside.

A rule is listed only when two skill packs reached it on their own. Evidence was read on 2026-10-05 from the checkouts named; nothing in them was changed.

| # | Invariant | Shown by | Check |
| --- | --- | --- | --- |
| I1 | **Pull is read-only and lands in raw files** that are written once. | seoh (`open(..., "x")`, manifest, hash), kit `raw` (KOL, RedNote) | not yet: needs a pull fixture per skill pack |
| I2 | **Ingest rebuilds the cache from raw and is idempotent**: ingest twice, same rows. | seoh (`ingest_twice_gives_same_rows`), ppc (upsert), kit `db` | not yet: needs a raw fixture per skill pack |
| I3 | **An agent write never changes a value a human confirmed.** Only a human verb confirms; it carries a reference to the decision. | seoh (`h_fact`), kit `facts` | **C1** |
| I4 | **Human data is a separate table family** that ingest never drops. | seoh (`h_` prefix), ppc (`client_facts`), kit stack | not yet: the check is a schema read, which differs per skill pack |
| I5 | **Registries are TSV files in `ssot/`**; a number lives once. | all three | not yet: structure only, covered by each skill pack's own `test_ssot` |
| I6 | **`doctor` runs before work and every warning names its fix.** | all three | **C2** |
| I7 | **One CLI facade; one `RESULT: N passed` line** from the whole suite, and a suite that prints none fails. | all three | not yet: needs the skill pack's test run |
| I8 | **At most 10 open asks per owner**, and a read-only report page built from one data object. | seoh, adcut (kit `queue`) | not yet: ppc has neither on its current branch |

### I3 and a client hub's copies

A client hub keeps the facts every pack of one client shares in its own store, confirmed once through the kit's gate there. `<cli> facts sync-hub` then writes such a fact into a pack's `client_facts` as confirmed without a gate of its own (history action `hub_copy`, changed_by `<user>@hub`). That is still I3: the human act is the hub's gated confirm, and the copy carries a reference to it, its `hub_history_id` and `hub_digest` (in the source `hub:<hub>@<hub_history_id>#<digest16>` and in an append-only `hub_copies` row). Only a hub row whose last history row is a `confirm` signed by a person (tty, relay or the client's own) is copied; a pack's own confirmed value is never overwritten (a differing one is a `conflict` and becomes one ask), and each hub version is copied at most once. Tested in `kit/tests/test_hub_facts.py`.

## How to read a result

`python3 conformance/check.py conformance/adapters/<name>.toml --root <skill pack checkout>` prints PASS, FAIL or SKIP per check. A SKIP is a check the adapter does not cover, not a pass. The runner exits 1 on any failure and when nothing passed.

First run, 2026-10-05:

| Skill pack | C1 | C2 |
| --- | --- | --- |
| seoh | pass | pass |
| ppc (amazon-ads-harness, branch `fix-pr-a-sqlite-utils`) | **fail**: `facts set` on a confirmed fact replaces the value and the fact stays confirmed (`is_assumption` stays 0), so an agent can change what the owner signed | pass |

## Adoption levels

How far a skill pack is on the kit, said once. Each level includes the one below it. A pack sits at the highest level whose proof passes on its **main branch** (merged code only). These are adoption levels of a skill pack, not the autonomy levels of a write ([autonomy.md](../docs/autonomy.md)), which share the letter.

| Level | A skill pack at this level | Proof, run on a checkout of its main branch |
| --- | --- | --- |
| **L0** | keeps the invariants above, however it is written | `python3 conformance/check.py conformance/adapters/<name>.toml --root PACK` ends `RESULT: 2 passed`. A pack that vendors the kit unedited needs no adapter: `python3 tools/fleet.py status PACK` lists no `local` kit file and no `edited` one, so the kit's own gate and doctor are the ones `check.py` would drive |
| **L1** | vendors `base` and `testkit` and routes its CLI through `kit.cli` | `python3 tools/consumers.py PACK` says it vendors the kit and lists `cli` among the modules it imports |
| **L2** | declares in `skill-pack.toml` and vendors only the kit packs it imports, and has deleted its own copy of any module the kit holds (golden diff 0 against the copy it deleted) | each pack in `[kit] packs` owns a module that `tools/consumers.py PACK` lists as imported by it; no file of its own code has a kit module's name |
| **L3** | has the full scaffold structure: `ssot/`, `console/`, a host adapter (`zylos/` on the Zylos host) and the thirteen day-one tests (the files under `scaffold/skeleton/tests/`) | `python3 tools/fleet.py status PACK` shows its console and host adapter copies with no `local` file; its own `scripts/<cli>.py test` ends `RESULT: N passed` |

[`tools/adoption.tsv`](../tools/adoption.tsv) records each known skill pack's level, its target, the day the proofs were last run, and the next step. `tests/test_adoption.py` checks the table's shape and that each row names a folder among the sibling checkouts; it cannot know a pack's level, so `checked` is the day someone ran the commands above, and a level is trusted only as far as that day.

## Adding an invariant or a check

1. A second skill pack must show it, in a path named in the row.
2. A check is an adapter-driven scenario in `check.py` plus a test in `tests/test_conformance.py` that runs it on a skill pack that breaks the rule (each check is tried on a broken input first).
3. Never put an adapter in a skill pack. The adapter is the playbook's statement of how to drive it.
