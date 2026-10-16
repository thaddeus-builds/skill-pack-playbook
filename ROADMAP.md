# Agent Harness Playbook roadmap
Updated: 2026-10-13
<!-- The playbook's own roadmap, in the one format of templates/ROADMAP.md (kit.guards.roadmap; tests/test_playbook_roadmap.py). Detail lives in the GitHub issues (#19 to #27). The loop: skill packs adopt the kit, learn what is shared and what is not, and the lesson comes back here as a small change with a test. Each session closes one turn of it. -->
## Now
- [N1] 2026-10-12 fold the video-ads skill pack's lessons into the kit, one pull request per lesson (kit 0.14.0 and the branches beside it); the lead reviews, merges in order and re-vendors
## Waiting on owner
- [W1] 2026-10-05 Anthropic source links in the README (#23): allow-list `www.anthropic.com` in the console leak scan and restore the three links (recommended); "no" leaves sources named by title only. unblocks: X4
- [W2] 2026-10-05 does the SEO skill pack migrate onto the kit; does the outreach scraper take only the guide (#26)? Recommended: migrate SEO after selective vendoring; outreach takes the guide only. unblocks: X6
- [W3] 2026-10-05 the skill pack checkouts for turn 2, and each skill pack owner's review. unblocks: X1
## Next
- [X1] 2026-10-05 turn 2 (#20): bring the three skill packs to one kit version: start with `python3 tools/fleet.py status` on the three checkouts; the stale digest.py mention, CI jobs with no rules, the KOL skill pack's forked copy upstreamed. Needs the skill pack checkouts and each skill pack owner's review (W3)
- [X2] 2026-10-05 turn 3 (#19): selective vendoring, a skill pack takes only the tiers it needs (breaking). Needs turn 2 done, the owner's go-ahead (R2) and a quiet week for the short-video skill pack. Packs and the vendor side are built (D3); what is left is moving each skill pack onto them
- [X3] 2026-10-05 the scaffold sets up Zylos itself: vendors the adapter, writes the manifest, passes `node zylos/lib.js check` (#25)
- [X4] 2026-10-05 restore the three Anthropic source links in the README once the leak scan allows them (#23, W1)
- [X5] 2026-10-05 kit modules with no or one user: delete, move or keep; recheck `copylint` after the KOL skill pack merges (#22)
- [X6] 2026-10-05 quality evals in every skill pack; SEO and outreach adoption (#26)
- [X7] 2026-10-05 consent check limits, kept template copies, the golden engine run end to end (#27)
- [X8] 2026-10-10 `browser-ops`, the second proposed kit module from the KOL skill pack's client (a guarded browser: read, draft, operate): design in docs/workbook-and-browser-ops.md, no code yet
- [X9] 2026-10-13 a first skill pack imports `kit.autonomy` (0.27.0): the SEO skill pack when it moves onto the kit (W2), or the Amazon Ads skill pack once its owner names which write kinds may rise above L1 (docs/autonomy.md, "Adopting it in another skill pack"); with no importer by 0.29.0 the module is deleted (kit/packs.tsv)
## Done
- [D1] 2026-09-30 CI and `run_all.py`, the kit tier registry with its guard test (commit 0f01846)
- [D2] 2026-10-05 turn 1 (#21): Zylos adapter 0.1.1 on Node 22, Node 22 the minimum (commit b5a3cef)
- [D3] 2026-10-05 kit 0.7.0: packs and selective vendoring (`kit/packs.tsv`), RESTRUCTURE.md phase 2 (commit 8e13e16)
- [D4] 2026-10-05 `tools/fleet.py`, where each skill pack's vendored copies stand, RESTRUCTURE.md phase 1 (commit 4eb08a6)
- [D5] 2026-10-05 `kit/pull.py` removed: no consumer (commit 3807e58)
- [D6] 2026-10-05 turn 4 (#24): the README is the overview, the detail is in `docs/`, RESTRUCTURE.md phase 4 (commit 2b962aa)
- [D7] 2026-10-05 `amazon-ads-harness` passed conformance C1 and C2 after its fix for thaddeus-growth-hacking/amazon-ads-harness#448 (`facts set` and `facts rollback` refuse to replace a confirmed value); the ppc adapter follows its current CLI: numeric `values`, `init`'s profit-model prompts, `--reason`, no `--type`, the confirm retyped on a terminal, `tty` (commit 199c218)
- [D8] 2026-10-05 kit 0.8.0 and 0.8.1: `facts set` and rollback never replace a confirmed value; an agent-only row may be `asked` (commits 5867752, e8e14c9)
- [D9] 2026-10-08 kit 0.9.0: the upload copy of SKILL.md (`tools/skill_upload.py`), one eval method, the playbook's CLAUDE.md (commit 7569fb2)
- [D10] 2026-10-10 kit 0.10.0 and 0.10.1: the changelog guard and the eleventh generated test; the spend code bound to the caller's approval record (PR #60, PR #63)
- [D11] 2026-10-10 kit 0.11.0: the `workbook` pack, the first slice of the two proposed modules, owner agreed 2026-10-10 (PR #64, PR #65)
- [D12] 2026-10-11 kit 0.12.0: one human gate per client file (PR #67)
- [D13] 2026-10-12 kit 0.13.0: the `learning` pack, a per-client pattern store (PR #68)
- [D14] 2026-10-12 kit 0.14.0: one roadmap format, `kit.guards.roadmap` and the twelfth generated test, from the video-ads skill pack; this file converted to it (branch kit-roadmap-guard)
## Parked
## Decisions
- [R1] 2026-10-05 which console copy stays (#24): "the playbook's" (as recorded in this roadmap's open decisions, 2026-10-05)
- [R2] 2026-10-05 selective vendoring go-ahead and date (#19): "yes, after turn 2"; built in kit 0.7.0, RESTRUCTURE.md phase 2 (as recorded in this roadmap's open decisions, 2026-10-05)
## Links
- playbook: this repository, default branch `main`; CI runs `python3 run_all.py` on every push and pull request
- kit: `kit/`, version in `kit/VERSION`; packs in `kit/packs.tsv`; tiers in `kit-tiers.tsv` (5 core, 11 stack, 42 extra), enforced by `kit/tests/test_tiers.py`
- Zylos adapter and console: `hosts/zylos/` (0.1.1) and `console/`; the host every skill pack is adapted to; always stays
- skill packs that vendor the kit: the short-video ad skill pack (two worktrees of one repository), the KOL skill pack, the RedNote skill pack; on different kit versions
- skill packs that do not: the SEO skill pack (forked its own gate), the outreach scraper, the ads skill pack the kit came from (#26)
- restructure: RESTRUCTURE.md (accepted 2026-10-05); turns 2 to 4 follow it: one kit version first, then packs and selective vendoring, then docs
- new machine: clone this repository; install Python 3.11 or newer and Node 22 or newer; `python3 run_all.py` must end `RESULT: N passed` (9 suites, about 2 minutes); clone each skill pack you will touch (the kit is copied into them, never imported from here); read the open issues, then Now and Next
- session start: read this file and `kit-tiers.tsv`; fetch every remote (other sessions may have merged since this file was written); do the one turn Now names, anything else goes to an issue; before changing `kit/`, a changed byte the vendor tool copies needs a `VERSION` bump and a regenerated `MANIFEST.sha256` (kit/README.md, "Upgrades and drift"), and a move or rename breaks the skill packs that import it
- session end: tests green, push, pull requests opened; set Updated and move the rows above (Done with its reference, the next turn in Now, what it needs as a Waiting row); file an issue for every loose end, nothing lives only in a transcript; memory notes only for what the repository cannot hold; tell the owner in one screen what to look at, what you need, what the next session does
- issues: the repository's issues; #19 to #27 hold the detail
