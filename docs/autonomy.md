# Autonomy levels

A skill pack that writes into someone else's system runs each write at a level, the way a car runs at an SAE driving level. The level says what proof the write carries and who gave it. The work item a person approved is the destination; the writes that carry it out are the driving. Below L4 a person sets every destination; the levels differ in how much of the driving still needs a person.

The shared mechanics are [`kit/autonomy.py`](../kit/autonomy.py) (the `autonomy` pack, since 0.27.0; pure over data the skill pack passes, so it fits any store). [Rule 12](rules.md#human-in-the-loop-rules) starts here. *Seen once:* the SEO skill pack, its S46 (L2) and S47 (L3), on the owner's decisions of 2026-10-13. *Paid for:* there one chat "1. 同意" was quoted for eleven store-write codes, and nobody saw the eleven diffs. Then the owner, who has no login to the store's admin, could not preview a single draft, so nothing shipped unless they typed at a terminal.

## The levels

| Level | Who decides each write | Proof in the manifest | What the skill pack checks | What is revertible | Default caps | How it switches down | Write kinds allowed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L0 hand-carried | a person, in the system itself | none: the skill pack writes nothing | the write switches are off (`kit.write_guard`: opt-in unset, kill switch, STOP file); the plan says the change is for a person to make | whatever the system allows the person | none | it is the floor; the kill switch drops every level here | none through the skill pack |
| L1 per-change consent | a person, per change: a retype at the terminal or a relayed code (`kit.human.confirm`); where the payload is known at approve time, the approve of that payload (rule 5) | `tty` or `relay` (with `--relay-quote`), or the approved queue row | the code is bound to the ids, the values and a version the write moves (single use); content made after the approval is bound by its sha256, a change of state by the live object; one chat yes for one code | per kind; a revert is its own L1 write | per run (`kit.execute`: `max_items`, `max_delta`); an approval's `ttl_hours` | unset the relay secret (terminal only), withdraw the approval, the kill switch | every kind on the door's allowlist |
| L2 scoped approval | a person approves a work item with a scope frozen when it was proposed; the skill pack classes each write from the live diff | `approval`, naming the approve row (`<user>@approval`, ` [approval=#id by= at=]`) | the class is tier B and inside the frozen scope; the target is live; the approve row is a person's and the item has not left approval; inside its days; the item's and the week's caps, counted from the archive under a lock; the archive is the workspace's own | every covered kind has an inverse write; the revert asks its own code (it can swap any version) | SEO: 2 writes per item, 30 per week, 14 days | revoke the item (`rejected`), let it expire, file items with no scope; a client's threshold only lowers the caps | low-risk kinds that change no visible meaning: internal links, a cover image, the meta title and description |
| L3 owner-switched mode | the owner, once, for a period: a confirmed switch fact naming registry rows; the skill pack checks each write | `auto`, naming the switch row (`<user>@auto`, ` [auto=#id by= until=]`); the undo `undo` (` [undoes=dir]`) | the switch's latest history row is a person's confirm; today is on or before min(its day, the confirm's day + `max_days`); the write's row is eligible and among the frozen ids; the item was approved by a person; its last write read back; the verb's own checks; the daily caps from the archive under a lock; one write never mixes proofs; a cap or a trip stops with no code issued | every eligible kind has a code-free undo while the live object is as the write left it; the undo restores the system, not what the public or a crawler already saw | SEO: at most 28 days, 10 new articles and 100 redirect rows per 24 hours | anyone, at any time: an agent's write of a past day, any later row of the fact, the expiry, a cap, the kill switch | a closed registry of revertible kinds the owner judged likely right: a new article in one step, a new 301 from a page the crawl saw gone to one it saw live |
| L4 rule-started work | a fixed rule the skill pack tests picks the work itself, inside an L3 mode, with no per-item approve; the owner switches on the rules by name, on a switch of their own | `rule`, naming the rule switch row, the rule and its basis (`<user>@rule`, ` [rule=ID basis=DATE mode=#N]`) | the L3 mode is on and covers the write's kind; the rule switch's latest history row is a person's confirm, inside its days (never past the L3 mode's); the rule is among the frozen ids and is a registry row now; its basis is current (`kit.human.stale_basis`); it has not tripped (two trips in a row: off for a week); its last write read back; the pack's own checks; the week's cap, counted from the archive; a confirm is taken only when the override rate of the same kind at L3 meets the pack's bar (rule 11) | as L3: a code-free undo while the live object is as the write left it | the kit sets none: a per-week cap counted from the archive and the trip rule (2 in a row, 7 days off); the numbers are the skill pack's | anyone, at any time: an agent's write of a past day, any later row, the expiry, the L3 mode going off, a trip, a cap, the kill switch; only a person's confirm raises it, and only with the bar met | the L3 mode's own kinds; which of them a rule may start is the skill pack's registry (the SEO skill pack's design is a new article from a demand-gap rule; the nearest older candidate was its computed 301s for pages the crawl saw gone, its T15, still filed under an approved item). No skill pack uses it yet |
| L5 full autonomy (not built) | the agent picks the goals and the writes; nobody switches it on, nothing expires | none a person gave | nothing a person could rely on | not all of it: public exposure and money spent do not come back | none | none by design, which is why no skill pack is here | none |

## Rules at every level

1. **The skill pack classes each write, never the agent.** The tier and the eligible row come from the skill pack's own diff of the live object against the new content, read against the registry. An agent never names the level its write runs at.
2. **A level is a ceiling per write kind, not a mode of the whole skill pack.** One skill pack runs several levels at once. In the SEO skill pack, a cover image edit may run at L2, a new article at L3 and a body-text edit at L1, all on the same day. The registry row sets the highest level a kind may reach. The approvals and the switch in force set the level it runs at now.
3. **Raising takes a person; lowering takes anyone.** Only a row a person signed raises a level: the approve, or the switch's confirm (`tty`, `relay`; a `client:` row, `@cli` and `@auto` never count). An agent may lower a level, and so may a later fact row, the expiry, a cap or the kill switch. History is append-only, so nothing but a new confirm turns a mode back on.
4. **Every level above L1 expires and is capped, and the caps are counted from the archive.** The skill pack counts the manifests under raw, including a half-done write and one whose time cannot be read. It never keeps a counter that a crash could leave behind. A client's confirmed threshold can only lower a cap. A covered write holds one lock from its cap check through its manifest.
5. **Above L1 only revertible kinds, and the undo of an L3 write needs no code.** The undo stays code-free whatever the mode, its caps or the item's status, as long as the live object is still as that write left it. After an edit, the undo takes a code. Say on the switch card and in the digest that an undo restores the system, not what was already seen.
6. **A stop issues no code.** When a cap is reached, the item's last write did not read back, or one run mixes rows of two proofs, the write stops and the skill pack issues no code: an agent in a hurry must never be one `--code` away from closing its own code. The agent hands the write to the owner (rule 10). A write that is merely not covered falls back to L1.
7. **The person sees what ran.** Every page of the console shows the mode in one line: off, or on until a day with the caps used. A digest lists the covered writes of the last days, each with whether it read back, whether it was undone, and its undo command as text. The console still runs only gate verbs, so it shows the undo command and has no undo button.
8. **A person's approve of the work is still required through L3.** At L2 the approve also carries the scope. At L3 the mode covers only work a person approved, and only kinds the owner switched on. Dropping that approve is L4, and L4 swaps it for a rule the skill pack tests, on a switch of its own ([the L4 section](#l4-what-is-built-and-what-is-not)).


## L4: what is built and what is not

*Seen once:* the SEO skill pack's design for blog work started by a rule (its S254, owner-agreed 2026-10-30, the pack not yet built on this). Its owner asked for topic and content to be decided without a person; the pack first found that its L3 mode already approved any agent-proposed new article the moment it was filed, so the rule is a tightening, not a loosening. The generic half is here; nothing in `kit/autonomy.py` names a channel or a kind of work.

**Built here (pure functions over data the skill pack passes):**

1. **A second switch** for rule-started work: one fact, the value `YYYY-MM-DD:RULE,RULE`, read by `rules_mode` as `mode` reads the L3 switch (a person's confirm, the max-days clamp, ids frozen against the registry, an agent's write only ever off via `may_set`, any later row turns it off). It needs the L3 mode on and its day never passes the L3 mode's. A person raises it only through `may_confirm_rules`: the rule must be a registry row now, the L3 mode on, and the override rate at L3 must meet the pack's bar. Switching it off is never refused.
2. **The proof `rule`**: `gate` and `suffix` record the switch row, the rule and the basis it read; `proof_level` gives L4; the undo is code-free and the digest names the rule.
3. **The eligibility verdict** `rule_verdict`, in a fixed order, a stop issuing nothing: the switch off; a mixed run; no rule or a rule not switched on; a write kind the L3 mode does not cover; the rule tripped; a stale or missing basis; the rule's last write not read back; the pack's own check; each cap. A write the verdict does not cover is not started: the work waits for a person, as it did before the switch.
4. **The trip rule** (`trip_until`): two `tripped` outcomes in a row (a `published` resets the count) switch the rule off for 7 days from the latest trip. **The week's cap** (`week_cap`) counts the `rule`-proof manifests of the last 7 days from the archive; a client's value goes through `tighten`.
5. **The override reader** (`override_rate`): from the archive's events (`started`, `published`, `undone`, `edited`) of one kind, the counts per item, how many published items were undone or edited afterwards, the rate, and whether the pack's bar (`min_published`, `max_overridden`, `max_rate`) is met. It is [rule 11](rules.md#human-in-the-loop-rules)'s measure for this kind of ask and it gates the switch's confirm. Nothing else turns on from it.

**What the skill pack passes in, and keeps:**

- The **rules as a registry**: one row per rule, a test per row, the basis it reads (the pack hashes or dates it; `rule_verdict` only compares the saved basis with the one recomputed now). What a rule is, how it picks a topic, and every check before a write are the pack's judgement and data. The kit never sees them.
- **Events** mapped from its archive: `{rule, item, event, at, kind, proof}`. The pack decides what a trip is (a failed pre-write check parks the work as a hidden draft, say) and records it.
- **The numbers**: the max days, the week's cap, the bar. The kit sets none. A client's confirmed value may only lower a cap (`tighten`).
- **The recompute at filing**: whether a rule covers an item is recomputed by the pack when the item is filed, never taken from the agent's word.
- **The codes**: every `why` above (`rule_off_*`, `rule_mixed`, `rule_not_eligible`, `rule_write_not_covered`, `rule_tripped`, `rule_basis_stale`, `rule_prev_unverified`, `rule_switch_*`, `override_*`, the cap codes it names) is a code the pack registers and words, as for L3.

**Honest limits.**

- No skill pack uses it yet, so the mechanics are proved on synthetic registries only; a pack's first use may show what is missing. L4 stays "seen once" until a second pack or a first live run says otherwise.
- The override rate counts what the pack's own archive saw: an undo or an edit made through its door. An owner who changes or hides the page directly in the system is not an override the reader can see unless the pack reads it. A low rate can mean content is right or that nobody looked. The bar is the owner's number and a floor, not proof the rule is right; a person still spot-checks.
- A trip is only as good as the pack's checks: a rule whose checks do not fail cannot trip. An event whose time cannot be read counts as now, so such a trip never ends by itself.
- A rule that trips straight after its week is off for another week; there is no free retry.
- Public exposure does not come back: the undo restores the system, not what was already seen or crawled (rule 5).

## Where this differs from the owner's first guess

The owner placed S46 and S47 at L3 and L4. This model puts them one level lower, at L2 and L3, for three reasons.

- **A terminal retype and a relayed code are one level.** Both are one person consenting to one change, bound to its bytes by the same protocol (`kit.human`). They differ in channel, not in who drives. A level counts who drives; which pedal they use does not change it.
- **The approve of an item is not a level of its own.** For content made after the approval ([Writing into someone else's system](rules.md#writing-into-someone-elses-system), rule 2), the approve is the destination, and every write still needs its code. That is L1, and both L2 and L3 still need the approve. Where the payload is known when it is approved (the Amazon Ads queue), the approve is the per-change consent itself, so that is also L1.
- **L4 is kept for the next real jump.** That jump is the skill pack starting work that its own rule picked, with no person approving the item. Calling S47 L4 would hide it. Its mechanics are now built ([below](#l4-what-is-built-and-what-is-not)).

SAE's split between L3 and L4 turns on fallback: at L3 the human takes over when asked, at L4 the system reaches a safe state alone. A skill pack always has a safe state of its own, which is to write nothing. So that split does not carry over. What does carry over is the operating domain (the registry rows a mode covers) and who sets the destination.

## The shared mechanics

`kit/autonomy.py` decides these from the skill pack's own data. Its codes are the SEO skill pack's message codes, and the skill pack words them.

1. **The tier registry** (`canon`, `check_tiers`, `tier_of`, `eligible`). One row per (verb, change): `id`, `verb`, `change`, `tier` (A or B), `undo` (the verb that reverts it; any text after the first word is a note), `auto` (`yes`, `undo` or `no`), plus the skill pack's own label and reason columns. A skill pack keeps its own column names and words, and `canon` maps them. The check requires the following. A tier-B row and a `yes` row name an undo. A `yes` row's undo is an `undo` row, so the undo is code-free. Every `undo` row is the undo of some `yes` row. An unknown pair is tier A.
2. **The switch** (`switch_value`, `parse_switch`, `mode`, `may_set`). One fact, typed in the skill pack's fact registry, with the value `YYYY-MM-DD:ID,ID`. A person turns it on through the skill pack's confirm verb (a relayed code, or the terminal). On the console card, the person retypes the number of days, and that value is what the gate binds. An agent's `set` is refused unless its day is before today (off). The value freezes the ids the owner saw, so a registry edit can narrow a mode that is on but never widen it.
3. **The proof labels.**

   | Proof | Level | `changed_by` | Reason tail | Manifest `gate` |
   | --- | --- | --- | --- | --- |
   | `tty` | L1 | `<user>@tty` | none | `proof`, `tier`, `change` |
   | `relay` | L1 | `<user>@relay` | ` [relay user= at=] [quote=…]` | the same, plus `relay_stale` |
   | `approval` | L2 | `<user>@approval` | ` [approval=#id by= at=]` | the same, plus `approval` (the approve row) |
   | `auto` | L3 | `<user>@auto` | ` [auto=#id by= until=]` | the same, plus `mode` (`history_id`, `confirmed_by`, `confirmed_at`, `until`, `ids`) |
   | `rule` | L4 | `<user>@rule` | ` [rule=ID basis=DATE mode=#N]` | the same, plus `mode` (the rule switch row, as for `auto`) and `rule` (`id`, `basis`) |
   | `undo` | none: it lowers exposure | `<user>@undo` | ` [undoes=dir]` | the same, plus `undoes` |

4. **Caps** (`used`, `tighten`, `lock`). These count one proof's manifests since a time, weighted when one manifest holds many rows. An undo never counts. A client's value never raises a cap.
5. **The verdicts** (`approval_why`, `auto_verdict`). Each returns the reason a write is not covered, checked in a fixed order, or None when it is covered. `auto_verdict` also says whether the reason is a stop.
6. **The record** (`gate`, `suffix`, `proof_level`). `gate` refuses an approval on a tier-A write and a rule write that names no rule or no basis.
7. **Undo and the digest** (`undo_free`, `undone_by`, `digest`). The undo of a `rule` write is code-free like an `auto` one; a digest row names the rule.
8. **The rule switch and its verdict** (`rules_mode`, `may_confirm_rules`, `rule_verdict`, `trip_until`, `week_cap`, `override_rate`; L4, below).

## Worked example: the SEO skill pack

- **`ssot/apply_tiers.tsv`.** The columns are `动作 改动 级别 撤回 自动`, and 自动 takes `是 / 撤回 / 否`. T04 to T06 are tier B (links, image, SEO fields: L2). T14 (a new article drafted and published in one step) and T15 (a new 301, its source seen 4xx and its target seen live) are 自动=是 (L3). T03 (unpublish) and T13 (unredirect) are their code-free undos.
- **`ssot/fact_keys.tsv`.** The switch `apply_auto`, of kind `auto`, value `2026-11-10:T14,T15`.
- **`ssot/constants.tsv`.** The L2 caps are `approval_writes_per_item` 2, `approval_writes_per_week` 30 and `approval_valid_days` 14. The L3 caps are `auto_mode_max_days` 28, `auto_publish_per_day` 10 and `auto_redirect_rows_per_day` 100.
- **`scripts/apply_shopify.py`.** `scope()` is `approval_why`, `auto_mode()` is `mode`, and `auto_why()` is `auto_verdict`. `by_approval()`, `by_auto()` and `by_undo()` are `gate` + `suffix`, and `covered_lock()` is `lock`. The order inside `gate()`: the hard scope refusals, then the approval, then a code-free undo, then the mode, and last the per-change code.
- **`webconsole/serve.py`.** The switch card retypes the days, through `facts confirm apply_auto`, and a day already past switches it off. It also holds the banner on every page and the digest of the last 7 days.
- **`tests/test_apply_shopify.py`.**
- **The stories.** S46 and P22 (L2), S47 and P23 (L3).
- **Where it ran.** Local runs are for debugging; production runs on a cloud host through a remote bridge. The owner switched the mode on in the inbox on 2026-10-13, and nine articles went live and a first wave of 100 redirects was written under it, each with its undo command.

## Adopting it in another skill pack

The Amazon Ads skill pack runs at L1 today. `queue approve` binds the exact payload, and `execute --apply` sends it under the allowlist, the opt-in, the kill switch and the per-run caps. With the opt-in unset it runs at L0. Its operating owner decides which of its kinds may rise, and the business "not yet" (rule 6) holds. To add L2 or L3, a skill pack adds the following.

1. **A tier registry** for its write door, in the six columns (or its own names through `canon`), with a test that runs `check_tiers`. Only kinds with an inverse write may be tier B or `yes`. For ads, a bid move inside a band on an approved campaign might qualify (the undo puts the old bid back); its owner judges each row.
2. **The class computed by the skill pack** from the payload against the live object, never named by the agent.
3. **The proof on every write record.** `gate.proof` is one of `tty`, `relay`, `approval`, `auto`, `undo`, and `changed_by` is `<user>@<proof>`. Caps are counted with `used` over the append-only record the skill pack already keeps: raw manifests, or an effect ledger mapped to `{action, applied_at, gate}`.
4. **The switch.** A fact key whose value `parse_switch` reads, a `set` that `may_set` guards, and constants for `max_days` and each daily cap (a client's threshold passed through `tighten`).
5. **The verdict in the executor.** `auto_verdict` decides, a stop issues no code, and one run never mixes proofs.
6. **An undo verb** for each `yes` row, code-free under `undo_free`.
7. **The console.** It gets the switch card (retype the days), the banner and the digest, and still runs only gate verbs. The kill switch still drops everything to L0, and the mode never sets the write opt-in.
8. **Tests.** Write each case both ways on the skill pack's own registry: a write under each proof, the mode off for each `why_off`, an agent unable to switch it on, the expiry and the clamp, caps from the archive, a stop with no code, and an undo after an edit that takes the code.
