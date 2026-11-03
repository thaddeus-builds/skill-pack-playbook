# Consolidation audit, 2026-11-03 (X36)

The owner asked whether much can be merged or cleared up to make the job easier. This page measures each candidate on the `main` of every pack this session can reach (the ten GitHub packs, cloud-gpu and the playbook). The owner says yes or no to each item. Nothing is deleted or merged without that yes. The ten packs that are still on GitLab (see `tools/adoption.tsv`) are not measured here.

How it was measured: each pack's `origin/main` was checked out in full into a scratch folder. `git archive` is not enough, because it drops CLAUDE.md and CI through `export-ignore`. Lines were counted in `.py`, `.js`, `.ts`, `.sh`, `.cjs` and `.mjs` files. A file is "vendored" when it sits under `scripts/kit/`, `kit/`, `console/`, `zylos/` or `tests/golden/`. A file counts as "identical" when its hash is the same in three or more packs and it has 15 lines or more.

## The owner's answers (R29, 2026-11-03)

"C2 C3 C4 C5 C6 C10 都 yes，C8 no". C1 and C9 were already decided (R26, R25). C7 waits until the last host has left GitLab. The work is in ROADMAP: C2 is X34 then X25, C3 is N4, C4 is X37, C5 is X38, C6 is X39, C10 is X40.

## The fleet today

| Pack | Own lines | Vendored lines | Kit | Zylos adapter | Use |
| --- | --- | --- | --- | --- | --- |
| adcut | 219,511 | 35,380 | 0.47.3 | 0.4.2 | earned |
| amazon-ppc | 111,561 | 1,404 | none (its own `_lib`) | its own | earned |
| sdr | 88,811 | 26,849 | 0.47.3 | 0.3.1 | earned |
| seo | 70,168 | 23,771 | 0.47.0 | 0.6.2 | earned |
| video-recipes | 47,815 | 24,525 | 0.45.0 | none | built |
| meta-ads | 22,534 | 31,798 | 0.47.0 | 0.7.0 | earned |
| cloud-gpu | 8,593 | 0 | none (a library) | none | library |
| asset-handoff | 5,681 | 29,477 | 0.47.4 | 0.7.0 | built |
| proofcut | 5,543 | 28,998 | 0.47.0 | 0.7.0 | built |
| google-ads | 5,057 | 26,122 | 0.44.0 | 0.7.0 | earned |
| product-image-to-video | 3,975 | 27,166 | 0.47.2 | 0.7.0 | built |
| ad-copy | 1,502 | 27,154 | 0.47.0 | 0.7.0 | built |

## Candidates

| Id | What | Measured | Gain | Cost and risk | Recommendation |
| --- | --- | --- | --- | --- | --- |
| C1 | Retire the packs no client uses (R26, X35). ad-copy is kept (R28) | 6 GitLab repos: outbound now; creator-program, koc-script, measurement, product-feed and search-intel on 2026-12-31 unless a client is named | 21 entries in `tools/adoption.tsv` become 15. Fewer repos to re-vendor, upgrade and triage | Needs GitLab access. Each gets a last release that says where each piece went | yes (already decided) |
| C2 | One kit version across the fleet | 6 versions in 10 packs: 0.44.0, 0.45.0, 0.47.0, 0.47.2, 0.47.3, 0.47.4 | One upgrade note instead of six. A fix reaches every pack in one train | One train (X34) and one re-vendor PR per pack (X25) | yes, next |
| C3 | One Zylos adapter version | 6 packs at 0.7.0; seo 0.6.2, adcut 0.4.2, sdr 0.3.1; amazon-ppc has its own; video-recipes has none | One install and upgrade procedure for the host agent | sdr and adcut change their command name on running hosts (an upgrade note each). amazon-ppc's own adapter has rules the shared one lacked (R3), so it moves last | yes, sdr and adcut first |
| C4 | amazon-ppc onto the kit | 16 own modules, 2,754 lines, that the kit also has: `human`, `db`, `messages`, `dates`, `atomic`, `paths`, `runner`, `single_instance`, the test runner and more | The biggest pack stops carrying a second copy of the gate and the database rules | Its write path and human gate are on its risky list. A golden diff and a clean run come before each swap. Several sessions | yes, one module per PR, after C2 |
| C5 | Scaffold docs copied into every pack | 175 identical file copies, 6,069 lines, in 8 packs. The largest: `docs/bug-classes.md` (113 lines × 8), `ssot/README.md` (98 × 8), `docs/doctor-checks.md`, `owner-review-loop.md`, `triage-checklist.md`, `vendor-api-discovery.md`, `decision-rights.md` | About 3,500 lines of docs that drift stop drifting. A pack keeps a link to the playbook's copy | Mechanical. The thin test wrappers (about 22 lines each) stay, because the runner finds the guards through them | yes |
| C6 | The shared CLAUDE.md text | 35 long lines repeated word for word in 5 or more packs, 277 copies | A rule changes once, not eight times | The vendored kit would carry the shared part, and each pack's CLAUDE.md imports it and keeps only its own lines. Test first that Claude Code reads the import in a cloud session and on a host | yes, after a test |
| C7 | GitLab leftovers | `.gitlab-ci.yml` in seo and adcut; the `gitlab` remotes | Less confusion about where CI runs | SEO keeps its file until every host has moved (its CLAUDE.md) | when the last host has moved |
| C8 | Merge the small video packs | proofcut 5,543 and product-image-to-video 3,975 own lines | Small: most of each pack is the vendored kit | They do different jobs for the client (the owner, 2026-11-03); one merged pack would carry two gates | no |
| C9 | adcut's formula dissection into video-recipes (R25, X31) | adcut 219,511 own lines; about 35 adcut modules import `dimensions` | adcut gets smaller; video-recipes owns the formula | adcut must keep working at every step | yes (already decided), piece by piece |
| C10 | The `seen-once` issues | 22 open in the playbook | A shorter list of real work | None: close an issue after 90 days with no second sighting | yes |

## Not measured

- The ten GitLab packs, including whether `seo-programmatic` should merge into `seo` and `video-ads` into `adcut` or `meta-ads`. Measure them when there is GitLab access (W3, W8).
- The size of the vendored kit (24,000 to 35,000 lines per pack). It is copied on purpose: a pack runs with the standard library only and no install step. A smaller kit comes from pruning modules nobody imports (`kit/packs.tsv`), not from sharing a copy.
