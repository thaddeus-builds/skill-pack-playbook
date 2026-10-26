# Prior-art scan

Before building, look at what already exists: tools the client could buy, open-source code, the platform's own features, and how practitioners measure the same thing. A scan is a few hours at fixed points, not a background job.

## When to scan

| When | Question it answers | Skip if |
| --- | --- | --- |
| After the first meeting's intake, before stories are accepted ([BUILD.md](../BUILD.md) B0.5) | Is this already solved? What does the client compare us to? | Never skip the first scan |
| Before the data and rules stages (3–6; BUILD.md B3 and B4) | Which API fields, metrics and thresholds do others use? What guardrails do their write paths have? | The last scan is under 30 days old and covered these |
| Before a release that adds a write path or a paid call (BUILD.md B7 and B9) | What went wrong for others doing the same writes? | No new write or paid call |
| When the client names a tool or a competitor | What does that tool do that we do not? | — |
| Before a feature an owner has to understand and steer ([design-first.md](design-first.md), step 1) | How do others do it, and which traps does it hide? | A fix, a refactor, or a change only the builder sees |

Each scan is dated. A scan older than 90 days is stale: re-scan before quoting it to the owner.

## How to scan

Split the scan into lenses and give each one to its own agent, so no lens is starved:

1. **Products the client could buy instead**: what they do, how they price (per seat, % of spend, per outcome).
2. **The platform's own features and API**: what it already automates, what the API can read and write, rate limits, permissions.
3. **Method**: how practitioners measure success and set thresholds (minimum data before a call, leading signals).
4. **Agent patterns**: open-source tools and servers doing the same job for agents, their write actions and guardrails.
5. **The law, per jurisdiction** (whenever the skill pack checks or produces copy people will see): the statutes and the regulators' own guidance on disclosure (paid relationships), claims the product may not make (medical, financial, environmental), price and scarcity claims, trial and return wording, origin, and personal data in the exports the skill pack keeps. Official sources only: the statute database, the regulator's guidelines and published decisions. Its output is a registry of **draft rules**, not prose: one row per rule with its jurisdiction, a pattern, `law_ref`, an official `source` URL and `status: pending` ([`kit/copylint.py`](../kit/copylint.py) runs the `banned` rows; a disclosure is a `required` row; what only a person can judge is a `human` row). A draft rule gives "a person reads this line", never a verdict; the client's counsel confirms rules one by one. Also list which of the client's own brief rules the law puts at risk: the brief can ask creators for exactly the wording the law forbids.

Rules:

- Every claim carries its URL and the date it was read. A claim whose page could not be opened is dropped, not guessed.
- Never copy code or text from a source into the skill pack; write down the idea and where it came from.
- Record what to **avoid** as carefully as what to borrow.
- A borrowed idea names the module it changes (a report, a rule, the gate, a registry). An idea with no module is a note, not a change.
- **Verify mechanically before trusting a README.** `gh api repos/O/R --jq '[.full_name,.stargazers_count,.pushed_at,.license.spdx_id,.archived]'` catches renames and archives. Then read LICENSE itself: custom terms hide there ("non-commercial", "company licence above 3 staff"). Mark anything not confirmed UNVERIFIED; never fill a gap from memory.
- **Read the vendor's product pages, not only its docs index.** Workflow, model and marketplace pages often hold the endpoint list, the parameters and the price; pin the API down with [vendor-api-discovery.md](vendor-api-discovery.md).
- **Stop a lens** when two new searches in a row surface nothing better than its top three, or at about 20–30 tool calls.
- **Prices and limits enter as pending facts** with their source and date; code never hard-codes a number read on a web page. A decision names what would change it ("if the gateway accepts `data:` URIs, drop the hosting layer").

*Seen once, in a KOL skill pack:* the first scan left the law out; the second found that the client's creator brief made disease names required keywords (sleep apnoea, insomnia, a herniated disc) and had no sponsorship disclosure, where both markets fine a medical-efficacy claim for a non-medical product per case and hold the creator liable too. The brand's own sample scripts passed the brief check with nothing flagged until the law was a registry.

*Seen once, in a video-ad skill pack:* the scan replaced a planned renderer whose licence needed a company licence, found that the target editor's drafts are encrypted on read, and found that the client's "model API" key belonged to a gateway serving the model's open weights as ComfyUI workflows, with a lip-sync workflow the vendor's own API lacked. None of this was in the brief.

## Auditing a skill pack that already exists

The scan above runs before a build. A skill pack that is already built needs the other question, once its module list has grown or before a rewrite or a new dependency: **for each module we made, is there a mature open-source answer, so we stop reinventing it?** Scan again after 90 days, or at any trigger the front page names.

- **Lenses are groups of modules**, taken from the skill pack's pipeline map, not the five lenses above: four to six agents in parallel, each owning the modules of one area. Read this template before briefing them, so their files land where it says (`docs/prior-art/`).
- **Brief each agent with the skill pack's own invariants** (its `CLAUDE.md`): they decide whether a candidate fits (single-file CLIs, offline hosts, a guarded write path, closed registries), and they are why most answers are "keep ours". Tell it to read pages, not clone or run anything, and to finish with a reply of at most 150 words.
- **One verdict per module section**, one of `adopt` (a dependency), `borrow-idea` (copy the idea, not the code), `keep-own` (say why) or `watch` (say what would change it), then **Why** in at most four lines naming the invariant or fact that decides. "Keep ours" is a finished answer: a dependency costs supply chain, offline installs and a version to follow.
- **Sources go in one registry**, `docs/prior-art/sources.tsv`: `id, url, kind, title, author_or_org, published_or_version, accessed, pinned, licence, claim_tag, used_for, note`. `pinned` is a release tag, PyPI version, arXiv id or DOI (a commit SHA when the host will show it), so a moved page can be found again; `claim_tag` is the one from [Research is kept, not repeated](../docs/lessons.md); `note` is the fact relied on, in your own words. A cited `[id]` with no row is a failure.
- **The front page** (`README.md`) carries the verdict counts, **Borrow** (at most 12, each naming the module it would change), **Avoid**, at most 5 owner questions, **Not surveyed** (modules left out and why, including a lens skipped), **Could not verify** and the re-scan date.
- **A test holds the coverage:** every module of the pipeline map has a section or a line under *Not surveyed*, every section has one valid verdict, every cited id has a row. Without it the next module slips in unasked.
- **Before the owner reads it, fetch the three heaviest claims yourself.** An agent's report is a claim; the ids resolving shows the paper trail exists, not that the page says it.

*Seen once, in the Amazon PPC skill pack (2026-10-26):* five agents, 97 to 132 tool calls each, 254 sources and 47 verdicts (31 keep-own, 13 borrow-idea, 3 watch, none adopt). It found no mature open-source Amazon PPC optimiser, and 12 ideas worth borrowing, two of them about Amazon's own platform (the stream it reads is marked outdated; a published migration kit) rather than about any library. Every agent hit pages it could not read (script-rendered, 403, 503, certificate errors); each said so in its row instead of filling the gap from memory. The first brief named `docs/research/`, the template said `docs/prior-art/`; the files were moved.

## Output

A folder in the skill pack repository, `docs/prior-art/`:

- `README.md`: the dated front page. A one-paragraph verdict (where the skill pack sits and why), **Borrow** (at most 12 ideas, each with its module and source), **Avoid**, open questions for the owner (at most 5) and the next re-scan date.
- One file per lens, `<date>-<lens>.md`: a table of name, what it does, what to borrow, what to avoid, source.

## After the scan

1. Borrowed ideas that change meaning or a number become owner asks in the console (at most 10 open, each with the source as evidence).
2. The rest become `proposed` rows in `ssot/user-stories.agent.tsv` or issues, each naming its source.
3. The owner questions go to the next meeting's agenda.
