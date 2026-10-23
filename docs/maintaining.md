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
6. **Skill packs take the change when they need it,** not on a schedule: `python3 kit/tools/vendor.py --skill-pack PATH`, then the skill pack's own suite, then a merge request in that skill pack. A skill pack that does not need the change stays on its version; that costs nothing until it needs something newer.

## Where the agent starts and stops

- **Start of a session:** read [ROADMAP.md](../ROADMAP.md), fetch every remote, look at the open pull requests, do the one turn "Now" names.
- **End of a session:** tests green, everything pushed, ROADMAP updated (done rows with a reference, the next turn in Now, what needs the owner as a Waiting row). A session ends with one screen for the owner: what to look at, what the agent needs, what the next session does.
- **Checking a pull request** (the agent does this for any pull request, its own or another's): one concern; a test that fails without it; no channel code in `kit/`, `console/`, `build/`, `scaffold/`; the version, manifest and changelog if vendored bytes changed; merges cleanly with main; the whole suite passes on the merged result, not only the branch.
- **Once a month, or before a decision about a module:** `python3 tools/consumers.py SKILL_PACK_PATH...` on each skill pack's main branch says which kit modules its own code imports; `python3 tools/fleet.py status SKILL_PACK_PATH...` says which kit version each holds and whether anyone edited a vendored copy. A module nobody imports for two minor versions is deleted, unless the owner parks it in the ROADMAP.

## Access: what to give the agent

The agent can write to this repository (GitHub) and can attach a skill pack repository for reading. It needs nothing else to keep the playbook.

**To look at the skill packs (the monthly check, a decision about a module, upgrading one):**

- One **read-only** token per GitLab server, set up in the cloud environment's settings, not typed in chat and not written to any file. Name it `GITLAB_TOKEN`. Add the GitLab host to the environment's allowed domains. A new session reads it; a running one does not.
- Fine-grained GitLab tokens are denied by default, so each permission has to be ticked. What worked: **Project: Read** and **Code: Download**, for the projects the agent should read. That is enough to read and clone a project whose path the agent is told.
- Add **User: Read** and **Group: Read** only if you want the agent to find projects itself. Without them the agent can read a project it is given by name, but cannot list projects.
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
