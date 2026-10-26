---
name: feedback-commit-identity-and-gitlab
description: No git identity is configured on this machine; commit as Claude Code with -c flags; GitLab pushes to git.coco.xyz fail intermittently and need retries; sibling MRs need a story id in the title
metadata:
  node_type: memory
  type: feedback
  originSessionId: d994ec77-cfab-4c70-a65c-b182cbce8499
  modified: 2026-10-26T15:18:41.527Z
---

On this machine no `user.name`/`user.email` is set anywhere, so plain `git commit` fails. Commit with `git -c user.name="Claude Code" -c user.email="noreply@anthropic.com" commit …` (a precedent in the playbook's history) and the Co-Authored-By trailer; never write the identity into config.

**Why:** the owner never configured git identity and earlier agent commits in the repository are authored "Claude Code"; writing config would change their setup.

**How to apply:** also for `git rebase --continue` and amend. Pushes to `https://git.coco.xyz` (the skill packs' GitLab) fail with LibreSSL `SSL_ERROR_SYSCALL` on roughly one push in three: retry up to three times with a short sleep; ssh to that host is refused. `glab` works for that host (`glab mr create --draft -t … -d … -b main -s … -y`). The skill packs' CI job `story id` requires an `S..`, `P..` or `M..` id or `release X.Y.Z` in the MR title, so a maintenance MR (a re-vendor) is opened as a Draft and the owner adds the id. Amend plus force-push is refused by the auto-mode classifier: use a follow-up commit instead. The playbook (GitHub, thaddeus-growth/skill-pack-playbook) works with `gh`.
