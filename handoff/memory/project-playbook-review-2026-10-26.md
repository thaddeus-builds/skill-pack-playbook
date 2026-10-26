---
name: project-playbook-review-2026-10-26
description: State after the 2026-10-26 review: a stack of six playbook PRs (#180 to #185), fourteen sibling re-vendor MRs to kit 0.41.0, the design review's open items (release train, fleet update, adoption levels, research convention, 6b trims)
metadata:
  type: project
  modified: 2026-10-26T15:18:54.804Z
---

On 2026-10-26 the owner approved the design review (scratchpad file 设计评审-2026-10-26.md, not in the repo) and its order. Done that day: playbook PRs #180 (fleet VERSION false positive), #181 (prose-pinning tests removed), #182 (RESTRUCTURE archived, docs/roadmap.md → docs/planning.md), #183 (incubating packs: `tools/pack_status.tsv` + test, CLAUDE.md rule), #184 (kit 0.42.0, `questions.py` removed), #185 (design doc archived, two templates removed). They are stacked in that order (each PR's base is the previous branch) so the CHANGELOG lines never conflict; merge in order. Fourteen sibling skill packs got a `claude/kit-0.41.0` branch in `<repo>_worktrees/kit-0.41.0` and a Draft MR; search-intel's push was refused by its own leak guard (client terms in `docs/prior-art/evidence/` on its unpushed main) and geo-china (kit 0.8.1, still `harness.toml`, `HarnessError`) needs the 0.31.0 rename migration before any re-vendor.

**Why:** the review found 15 packs on 6 kit versions after 52 bumps in four weeks, seven packs with 0 or 1 importer, and 17 tests pinning prose.

**How to apply:** open items, in the owner's approved order: a kit release train (weekly) plus `fleet.py update` and a non-blocking "behind" hint in the drift test; an adoption-level table (L0 conformance to L3 full structure) per pack; scaffold-generated `docs/research/` and `docs/prior-art/` with the research index test lifted from video-ads, and a playbook-level `docs/research-index.tsv`; the 6b trims that need the owner's word (lessons.md to 150 words per lesson, CHANGELOG pre-0.31 archive, the `data` pack with `retry` alone, which cannot be folded into `base` without breaking the eight packs that declare it). GitLab `ming.liu/` also holds `seo-programmatic-skill-pack`, not checked out locally, and five old-name repos (`*-harness`) worth archiving.
