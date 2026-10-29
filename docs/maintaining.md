# Keeping the playbook: how it changes, who does what, what access is needed

For the owner. The playbook is the parent of every skill pack. It changes only when a skill pack has paid for a lesson, and only in small steps. This page is the loop, who decides, and the access an agent needs. The rules themselves are in [CLAUDE.md](../CLAUDE.md); this page does not repeat them.

## The loop

1. **A skill pack hits something.** A bug in a shared module, a missing piece, or a lesson. It files an issue here with the template in `.github/ISSUE_TEMPLATE/`: where it was seen (a merged commit, not a branch), what happened, who else needs it.
2. **The agent triages it against CLAUDE.md** and answers in one of four ways:

   | What it is | What happens |
   | --- | --- |
   | A bug in a module that exists | Fixed after one report, with a test. A new kit patch version. |
   | A new module | Goes in the pack named for its concern, never in `base`. Moves to `base` when two skill packs import it from merged code. |
   | A lesson | Goes in [docs/lessons.md](lessons.md) once, labelled "seen once" if it was. |
   | Channel-specific (one platform's API, fields, words) | Stays in that skill pack. The issue is closed with that said. |

3. **One small pull request, one concern, with a test.** The pull request template lists the checks. A change to a byte the vendor tool copies also needs a `kit/VERSION` bump, a regenerated `kit/MANIFEST.sha256` and a line in `CHANGELOG.md`.
4. **CI runs `python3 run_all.py`.** It must end `RESULT: N passed`.
5. **The owner merges.** The agent merges only when told, after CI is green. Anything on the risky list (the human gate, the write path, human-data tables, contract removals or renames, threshold values) is the owner's merge, not the agent's own call.
6. **Skill packs take the kit on the train** (next section), with one command: `python3 tools/fleet.py update SKILL_PACK_PATH...`. A skill pack that is behind and needs nothing from the train costs nothing; one that needs a change waits for the next train, not for a merge.

## The release train

Why: on 2026-10-26 the kit had been bumped 52 times in four weeks while the skill packs sat on six versions, none current. A version that moves on every merge cannot be followed.

- **A merge to main does not bump `kit/VERSION`.** Its line goes under `## [Unreleased]` in `CHANGELOG.md` and the merges accumulate there. The tests that tie `VERSION`, `MANIFEST.sha256` and the newest heading together run on the train commit, not on every merge.
- **The train runs at most once a week,** on a day the owner names, in one pull request: pick the size from what accumulated (a patch for fixes only, a minor for a new module or hook, a major when a skill pack must change), then `python3 tools/release.py X.Y.Z` (add `--dry-run` to look first). It sets `kit/VERSION`, runs `python3 kit/tools/manifest.py kit`, turns `[Unreleased]` into `## [X.Y.Z] - DATE` and refuses an empty `[Unreleased]`, an entry without its `- Skill packs:` line, a version already in the CHANGELOG, a second train inside a week without `--urgent "why"` (a patch only) and an earlier date; it commits nothing. An urgent fix may ride a patch train in between; say why in the pull request.
- **Every version says what a skill pack does with it.** From 0.45.0 its CHANGELOG section has one line, `- Skill packs: nothing`, `mechanical (...)` (one command, usually `fleet.py update`) or `judgement (...)` (the pack's own call, with what to decide). A pack's own session acts on it without asking the playbook; the playbook's session steps in only for a pack nobody is working on and for what spans packs (`tests/test_changelog.py`).
- **Every skill pack reaches the train with `fleet.py update`.** For each path it makes a worktree beside the pack (`<repo>_worktrees/kit-<version>`, branch `claude/kit-<version>`, cut from the default branch), vendors into it, runs the pack's suite (`[skill_pack].test_command` in `skill-pack.toml`, else `python3 tests/run.py`) and commits. It prints one line per pack: green, red with the failing files, refused by the vendor tool, worktree exists. The pack's own checkout is never touched. **Run it from the commit that set `kit/VERSION`, not from main after later merges:** the vendor tool copies the files as they are, so a main with unreleased kit changes would put those bytes in the pack under the released number (it happened once, at 0.47.0, and was redone); `update` refuses such a checkout and names the files, and `--allow-unreleased` takes it on purpose. The line also says which remote and commit the branch was cut from. A pack whose `origin` is archived or stale (its real default branch is on another remote) says so with `--remote NAME`; without it, `update` refuses when the checkout's own default branch has commits the remote's does not (#316). The owner or the agent then opens a merge request for each green one.
- **A pack that falls more than two minor versions behind says so** in its own suite (`behind: kit X, playbook Y`) when its `skill-pack.toml` has `[kit] playbook = "<path to this checkout>"`. It never fails on it.

## Merging CHANGELOG.md

Every pull request that matters to a skill pack adds its entry at the top of `[Unreleased]`, so two open pull requests always touch the same lines. `.gitattributes` sets `CHANGELOG.md merge=union`: git keeps both sides' lines, in the order of the merge, on `git merge` and `git rebase`, with no conflict to resolve by hand. An entry is two lines (the text and its `- Skill packs:` line) added together, so the pairs stay whole.

- **GitHub's merge button does not read the setting.** A pull request may show "conflicts" there; rebase it on main locally (the setting applies) and push.
- **After the release pull request, look at every open pull request.** The release moves the `[Unreleased]` heading below the new version's; an entry rebased over it lands under the new version without a conflict. Move it back to `[Unreleased]` before the pull request merges.
- `tests/test_changelog.py` merges and rebases two such branches and checks both pairs survive.

## Retiring a pack

A pack ends when its pieces have moved: engines to the kit, a channel to a pack of its own (video-ads first: its Meta side to `meta-ads`, its engines to the kit, 千川 and 腾讯 to a pack of their own). Archiving is the last step, not the first; the repository is read-only afterwards, and GitLab and GitHub both undo it, but a client wrapper pointing at it is not undone by that. In this order:

1. **Every piece has a new home that runs** (its own tests, a golden diff of 0 against the old one, and the first client's numbers equal on both sides for the days that matter). Until then the old pack keeps running; nothing is deleted from it first.
2. **One last release of the old pack** whose `CHANGELOG` says, piece by piece, where it went (`pull_meta` → `meta-ads`, `scripts/_lib/pacing.py` → `kit.pacing`), and whose `README.md` and `SKILL.md` start with the same list. It is the pointer anyone arriving from an old link reads.
3. **The roadmap rows move with their ids kept in the text** (`[X63]` stays findable by search), to the pack that now owns the work; the old roadmap ends with a table of where each went.
4. **Everything that names the old pack is changed:** client wrappers and `_env.sh`, data folders and `*_DATA_DIR` names (copy the data to the new pack's folder, check it there, leave the original in place), hub and portfolio links, `tools/adoption.tsv`, `tools/pack_status.tsv` and `kit/packs.tsv` rows, and CI or scheduled jobs. `grep -r` the old name in the client folders and the playbook; zero hits that are not a pointer.
5. **Archive** the repository when 1 to 4 hold and no merge request is open (close or move each). The portfolio's "Not skill packs, or superseded" lists it with the date and the new homes.
6. **Leave the client's data folder alone** until the owner says it can go; the playbook never deletes client data.

No test enforces this list: the first pack that follows it corrects it (issue #227).

## Where the agent starts and stops

- **Start of a session:** read [ROADMAP.md](../ROADMAP.md), fetch every remote, look at the open pull requests, do the one turn "Now" names.
- **End of a session:** tests green, everything pushed, ROADMAP updated (done rows with a reference, the next turn in Now, what needs the owner as a Waiting row). A session ends with one screen for the owner: what to look at, what the agent needs, what the next session does.
- **Checking a pull request** (the agent does this for any pull request, its own or another's): one concern; a test that fails without it; no channel code in `kit/`, `console/`, `build/`, `scaffold/`; the version, manifest and changelog if vendored bytes changed; merges cleanly with main; the whole suite passes on the merged result, not only the branch.
- **Once a month, or before a decision about a module:** `python3 tools/consumers.py SKILL_PACK_PATH...` on each skill pack's main branch says which kit modules its own code imports; `python3 tools/fleet.py status SKILL_PACK_PATH...` says which kit version each holds and whether anyone edited a vendored copy (the day after a train, run `update`, not `status`). A module nobody imports for two minor versions is deleted, unless the owner parks it in the ROADMAP.

## Access: what to give the agent

The agent can write to this repository (GitHub) and can attach a skill pack repository for reading. It needs nothing else to keep the playbook.

**To look at the skill packs (the monthly check, a decision about a module, upgrading one):**

- One **read-only** token per GitLab server, set up in the cloud environment's settings, not typed in chat and not written to any file. Name it `GITLAB_TOKEN`. Add the GitLab host to the environment's allowed domains. A new session reads it; a running one does not.
- Fine-grained GitLab tokens are denied by default, so each permission has to be ticked. What worked: **Project: Read** and **Code: Download**, for the projects the agent should read. That is enough to read and clone a project whose path the agent is told.
- Add **User: Read** and **Group: Read** only if you want the agent to find projects itself. Without them the agent can read a project it is given by name, but cannot list projects.
- Name the host on every call. `glab` run outside a checkout (a scratch directory has no git remote) defaults to gitlab.com and answers `401 Unauthorized`, `404 Project Not Found` or a TLS timeout, which looks like a bad token. Set `GITLAB_HOST` (or pass `--hostname`) and prefer a call from a worktree; read the host in the error's URL before blaming the token. The playbook itself is on GitHub, the packs on a private GitLab, so the wrong host is easy to reach. Seen once, in adcut (issue #166).
- Scope it to the skill pack projects (or their group), not the whole server. Give it a short life, a few days, and delete it when the work is done.

**To change a skill pack (upgrading its kit copy, a fix there):**

- A separate token that can push a branch and open a merge request in that one project; use the write permissions GitLab's token screen lists next to the read ones (not yet tried here). Short life, one project, deleted after.
- The agent does not merge in a skill pack unless that skill pack's own instructions let it, and never runs a skill pack's `execute --apply` or turns its write switch on.

**Never:** put a token in the chat if it can be avoided (a pasted one stays in the transcript; delete it afterwards), commit one, or leave one in a settings file in a repository.

## What decides how big a step is

- If a step needs a skill pack owner's answer, it is a Waiting row in the ROADMAP, not a guess.
- If the owner has no use for something, it goes to Parked with the reason; its code stays until a skill pack asks again.
- If a pull request grows past one concern, it is split before it is merged.
- A decision of the owner is written in the ROADMAP's Decisions with the owner's words in quotes, so a later session does not ask again.
