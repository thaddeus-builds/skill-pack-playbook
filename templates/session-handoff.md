# Session handoff: the next session starts where this one stopped

Context windows end mid-project. Each session closes one turn of the build loop and leaves a written starting point, so a fresh session (or another agent) can pick up without the transcript.

## What lives where

| File | Holds | Written by |
| --- | --- | --- |
| `docs/ROADMAP.md` in the skill pack ([template](ROADMAP.md), the one format, held by `tests/test_roadmap.py`) | One dated row per item: **Now** (the one turn in progress), **Waiting on owner** (each row names what it unblocks), **Next** (one turn each, in order), **Done** (with its commit or merge request), **Parked**, **Decisions** (the owner's words, quoted), **Links** (where things are) | the session, at its end |
| `<project>/CHANGELOG.md` | Each plan revision: what changed and which owner note or decision asked for it | the session, as it applies feedback |
| `<project>/feedback/<date>.json` | A dated copy of the owner's decisions read from the review page | the session, at its start |
| The agent's memory notes | Only what isn't in the repo: the owner's preferences, account facts (which token is which group), links (review page URL) | the session, when learned |
| `<client workspace>/reports/handoff-<date>.md` | What git cannot hold while work is in flight: a running or rented resource and whose it is, tunnels, group and conversation ids, who answers what, what must not be touched. The roadmap stays the plan; this is the state around it. A memory note points to the newest one | the session, at its end |
| `SKILL.md` | How an agent operates the skill pack: the loop, the verbs, the rules | when a verb or rule changes |

## Start on a new machine

1. Clone the skill pack and every repository the roadmap's **Links** name. A folder with no remote cannot move: give it one first.
2. Install `uv` and Python 3.11 or newer. Run the skill pack tests: `python3 tests/run.py` must end `RESULT: N passed`.
3. Recreate what git does not carry: each data dir's `.env` (chmod 600, never committed), the console secrets, tokens from their owners. Each is a **Links** row of the roadmap (where it lives, who owns it), never its value.
4. Run `{{cli}} doctor --strict` in each client workspace; it names every missing setting.
5. Start the consoles and read the open asks before asking anything new.

## Session start checklist

1. Read `SKILL.md`, `docs/ROADMAP.md` and the memory notes.
2. Read the owner's feedback from the review page, save a dated copy, and summarise it back in about five lines.
3. Check the spend ledger for entries you didn't make (another session or the owner may have spent). Report them.
4. Do the one turn the roadmap names. Anything outside it goes to the backlog.

## Session end checklist

1. Run tests green, then republish the review page to the same URL.
2. Update the roadmap: set `Updated`, move what finished to **Done** with its reference, put the next turn in **Now**, and give everything it needs from the owner a **Waiting on owner** row that names what it unblocks. An id is never reused.
3. Update memory notes only for facts the repo can't hold.
4. Refresh the owner's progress page from ROADMAP ([skills/progress-page](../skills/progress-page/SKILL.md)); the page is a view, the roadmap is the source.
5. Tell the owner, in one screen: what they can look at now, what you need from them, what the next session will do.
6. When the session served a client, end with a **Distil** list: each insight goes to a skill pack issue or MR, a proposed story or policy, or is marked client-only. A rule seen on one client stays proposed until a client with another business model confirms it.

## Rules

- **One turn per session.** "Wire the paid route and make a 4-scene sample" is one turn. "Do the whole ad" is not.
- **The roadmap names what the owner must provide** (a token, a decision, footage) before each turn, so no session starts blocked.
- **Delegate research and review to sub-agents with a written brief.** Examples: prompt craft, vendor docs, frame QA. Keep spending, owner contact and plan edits in the main session.
- **When the context runs low, stop starting things.** Finish the current step, write the handoff, and say what is next.
