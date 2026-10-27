# Prompts for a skill pack's own agent

Most of what moves the whole fleet is done from the playbook with `tools/fleet.py`: the kit version, the CI file, a declaration a pack never imports. What needs a person who knows the skill pack (a migration, a branch to merge, a test that fails for a reason of the pack's own) is done by the agent that works in that skill pack. This page holds the words to give it.

## How to use

1. Open an agent session **inside the skill pack's checkout** (not in the playbook), with the playbook cloned beside it (`../skill-pack-playbook`; `git pull` it first).
2. Paste the **common part**, then the pack's own part below. Nothing else needs to be said.
3. The agent opens a merge request and stops. The owner reads it and merges; the agent does not merge, and does not push a branch other than its own.
4. The playbook side then reruns `python3 tools/consumers.py` and fixes `tools/adoption.tsv` (the row's `checked` day and `next_step`).

## Common part

```text
You work in this skill pack. The playbook that holds the shared kit is cloned at ../skill-pack-playbook; run
`git -C ../skill-pack-playbook pull` first and read its CLAUDE.md, kit/README.md ("Upgrades and drift") and
docs/skill-pack-agent-prompts.md (the part about this pack).

Rules:
- scripts/kit/ and console/ are copies. Never edit them; a fix goes to the playbook first.
- One merge request, one concern. Title it "Re-vendor the kit: <from> to <to>" for a re-vendor (no story id needed);
  anything else names its story or ROADMAP item. Never squash. Do not merge it yourself.
- Before every push run this pack's own test command (README or CLAUDE.md). Report a red test with its output; say
  whether it is red on the default branch too (check on a clean worktree). Never skip a failing test to get green.
- Tell the owner in Chinese, in plain words, numbers in a table: what you did, what you did not, what you need decided.
- Stop and ask when a step below says "ask".
```

## geo-china-skill-pack

Stands at kit 0.8.1 with `harness.toml` and `HarnessError`, so `fleet.py update` cannot read it until the rename of kit 0.31.0 is done by hand.

```text
Bring this skill pack from kit 0.8.1 to the playbook's current kit (kit/VERSION).
1. Branch from main. Read the playbook CHANGELOG.md entry [0.31.0]: its table lists every rename.
2. Make the renames of that table in this pack first, one commit, nothing else in it: harness.toml -> skill-pack.toml,
   [harness] -> [skill_pack], HarnessError -> SkillPackError, KIT_HARNESS_ROOT -> KIT_SKILL_PACK_ROOT, the other rows that
   `grep -rn -i harness .` finds here. Leave the repository's old names in prose history alone.
3. In skill-pack.toml, [kit] packs lists what this pack imports besides base and testkit: compliance (copylint). Run
   `python3 ../skill-pack-playbook/tools/consumers.py .` and list exactly the packs it shows imported, no more.
4. Run `python3 ../skill-pack-playbook/tools/fleet.py update .` (it re-vendors the kit and console, runs the suite,
   commits on claude/kit-<version>). Fix what the 0.8.1 to current gap breaks, in this pack's own code, in separate commits.
5. Push the branch, open the merge request, add a line to CHANGELOG.md under [Unreleased]. Stop.
Ask the owner before: deleting any of this pack's own copies of a kit module, or changing a client-facing output.
```

## search-intel-skill-pack

Its default branch is clean on the remote at kit 0.33.1; an old Draft MR (!1) holds 0.43.0. The checkout on the owner's other machine has nine local commits that a leak guard refused: they hold client terms and must never be pushed.

```text
Bring this skill pack to the playbook's current kit.
1. Work from origin/main only. Do not push, copy or cherry-pick any commit of a local main that is ahead of origin/main,
   and never anything under docs/prior-art/evidence/. If the leak guard (scripts/kit/tools/leak_guard.py) refuses a push,
   stop and tell the owner; never turn it off and never use --no-verify.
2. Close the old Draft MR !1 (0.43.0) with a comment that it is replaced; do not build on its branch.
3. Run `python3 ../skill-pack-playbook/tools/consumers.py .` and make [kit] packs in skill-pack.toml list exactly the packs
   this pack imports besides base and testkit (it declares data and imports base only: drop data).
4. Run `python3 ../skill-pack-playbook/tools/fleet.py update .`, fix what it reports in this pack's own code, push the
   branch, open one merge request, add the CHANGELOG.md line. Stop.
Ask the owner before: anything touching the nine local commits or the evidence folder.
```

## creator-program-skill-pack

Its default branch is `m1-roster`, which imports `workbook`; `main` does not. The 0.41.0 re-vendor MR (!2) targets `m1-roster` and is behind. It has one test, `test_ads_docs.py`, that is red for a reason of its own.

```text
Bring this skill pack to the playbook's current kit, on its default branch m1-roster.
1. Branch from origin/m1-roster. Close Draft MR !2 (0.41.0) with a comment that it is replaced.
2. Check [kit] packs in skill-pack.toml against `python3 ../skill-pack-playbook/tools/consumers.py .` (it declares and imports
   workbook: keep it) and run `python3 ../skill-pack-playbook/tools/fleet.py update .`.
3. tests/test_ads_docs.py is red on m1-roster before your change and has nothing to do with the kit: say so in the merge
   request, do not fix it here (its own merge request, its own story).
4. Target the merge request at m1-roster, add the CHANGELOG.md line, stop.
Ask the owner before: merging m1-roster into main, or changing the default branch.
```

## What this page does not do

It gives no pack a new rule. The kit is still `Re-vendor the kit` titled, vendor-tool made, and tested by the pack's own suite; the prompts only say whose job each step is. A new skill pack's `AGENT_INSTRUCTIONS.md` is not changed by this page.
