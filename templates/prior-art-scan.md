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
| The owner asks how others design something: where a shared module lives, how remote workers are structured, whether to split or merge, "is there a standard way?" | What do mature systems do, what transfers to ours and what does not? ([a design question](#a-design-question-from-the-owner-a-precedent-scan)) | The question is only about a name or a link (the quick scan) |

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

## A name or a link from the owner (a quick scan)

The owner pastes a repository or a product and asks "did we already look at this, and is there more like it?". That is a lookup with a short tail, not a scan: about 30 tool calls in all, one agent, no fan-out.

1. **Read what is kept first.** Open `docs/prior-art/README.md` and `sources.tsv` (or `docs/research/README.md`), then search the whole repository for the project's name, its owner and its URL. Then run the playbook's `python3 tools/research.py` over the sibling skill packs (the same vendor or question has been researched twice in different packs). Answer "yes, on this date, with this verdict, here" or "no" before any search; the owner is asking exactly this.
2. **Facts before words, per project.** `gh api` for stars, licence, push date, archived and renamed; then the LICENSE file itself; then the README and the one page that shows the interface (an API reference, a schema, an MCP tool list), not the marketing page. A rewrite in progress, a repository closed to contributions, or a licence that forbids linking is a finding: put it in the verdict.
3. **Find the neighbours in three searches at most:** the project's own "alternatives" or "similar" list, one search for the job in plain words ("open source X for agents"), and one in the client's market language when it is not English. Merge the hits into one table: name, licence, size, last push, verdict. Stop when two searches in a row add nothing.
4. **One verdict per project**, the four words of the audit below, each naming the module it would change or the reason it changes none. What only running can answer (fonts, speed, whether two runs give the same bytes) goes on a **spike list** as questions. It is neither guessed nor run unasked.
5. **Write it down in the same turn,** in the repository: rows in the sources registry, the table in the dated file, the front page updated so that step 1 finds it next time. A scan left in a reply is done twice.
6. **Ask the owner after, not before:** which module they hope to improve, and which regions or tool families are not covered yet. Keep the answers as dated "deferred" lines, so a skipped lens reads as a decision, not a hole.

*Seen once, in a video-ad skill pack (2026-10-26):* the owner pasted two open-source editors and asked whether the market had been looked at. Earlier research held licences and schema patterns but nothing on editors, and was spread over one long page. The quick scan found that one editor is under AGPL (a separate process at most), the other is mid-rewrite with its headless mode only promised, and a third project (an HTML-to-video engine with agent skills) was the one worth a spike. The answers went into `docs/prior-art-editors.md`, linked from `docs/prior-art.md`.

## A design question from the owner (a precedent scan)

The owner asks how professional teams design a thing: where a shared module lives, how remote workers are structured, whether to split a package or merge two. It is a lookup that ends in a design, not a scan of the market: one agent, four searches in one turn.

1. **Read what is kept first, in this pack and its siblings:** `docs/research/README.md`, then `python3 tools/research.py` over the sibling skill packs for the question's words. Answer "yes, on this date, with this answer" before any search.
2. **Name the lenses, one search each, in parallel (four at most):** a mature system's own specification or protocol; the most used implementation and what its operators learned; the design rule that applies, and its criticism; one counter-example or failure story. Read the page, not the snippet, for the claim that carries the decision.
3. **Per source, write three things:** what it does, what transfers to ours, and what does not transfer and why. Where our own numbers differ, write the measured one beside it, tagged **[ours]**. A source that only agrees with what we already think is a note, not evidence.
4. **One verdict, and what it changes:** each "what follows for us" line names the module, registry row or page it changes and is tagged **[inference]**; what only a measurement can settle goes on a spike list.
5. **Say what could not be read:** a search that found nothing on a name, a source read second-hand, the reach of the search (one engine, one country). "Unconfirmed" means looked for and not found.
6. **Write it down in the same turn,** as a file in `docs/research/` and a row in its index; the answer to the owner gives the verdict and cites the file, never the search. A pack with no `docs/research/` yet creates the index from [research-index.md](research-index.md) first; a pack that predates the scaffold and keeps one flat page leaves it and points it at the folder.

*Seen once, in the adcut skill pack (2026-10-30):* the owner asked whether to open a CPU skill pack beside the GPU one or to rename the GPU one, and whether professional teams had a way to decide. Four searches (distcc, Bazel's remote execution API, SkyPilot, the rule of three) confirmed the plan (offload only small inputs; launching on machines you have and provisioning rented ones are two layers; extract a shared module when a second pack needs it) and added two changes (cache a result by the hash of its inputs; fall back to the local machine only when the remote could not run, not when the job failed). The first answer left the search in the chat, the index had been read for the pack but not its siblings, and adcut had no `docs/research/`; all three were found only when the owner asked whether the playbook had a process for this.

## Do you need a deep-research tool?

Default no. A scan's claims are mostly mechanical (a licence, a star count, a push date, an endpoint) and rest on a handful of pages; the lens-per-agent split above is already an orchestrator with workers. A hosted agent or an open-source clone adds a long report whose claims need the same spot-check, and a multi-agent run costs about fifteen times the tokens of a chat.

One earns its keep for a lens that is wide reading rather than verification (a body of regulator guidance, a literature of thirty papers). Treat its output as a lead list: open the sources it cites ourselves, fetch the three heaviest claims, and write nothing as a fact without a URL and a date.

What the tools are (read 2026-10-26; stars and licences from `gh api` that day):

- **Gemini Deep Research** is a hosted agent behind Google's Interactions API; what Google open-sourced is a benchmark (DeepSearchQA, about 900 tasks), not the agent. The `gemini-fullstack-langgraph-quickstart` repository (Apache-2.0, 18k stars, last push 2026-06) is a reference app on Gemini 2.5.
- **Open-source clones:** GPT Researcher (Apache-2.0, 30k stars, active), dzhng/deep-research (MIT, 20k, last push 2026-04), LangChain open_deep_research (MIT, archived), Stanford STORM (MIT, 32k, last push 2025-09). None adopted here.

What the people who run research at scale do, and where it lands in this template:

| Source | What to take | Lands in |
| --- | --- | --- |
| "How we built our multi-agent research system" (Anthropic Engineering, 2025) | Brief each worker with an objective, an output format, the tools to use and the boundaries; scale effort with the question (a lookup is one agent and a few calls, a comparison a handful, more only for a whole-pack audit); say which sources count, because agents drifted to search-optimised pages until told to prefer primary ones; about 20 realistic cases show big effects early; judge the outcome, not the path; poor fit when the workers share one context | the lens briefs, the stop rule, the registry's `kind` |
| Simon Willison, "Code research projects with async coding agents" (2025-11-06) and his public `research` repository | A question about code is settled by running code in a throwaway repository, one folder per question with its README; the prompt (and transcript) are linked from the commit; an agent can show that something is possible, never that it is impossible; an unreviewed report is not published | the spike list, and "could not find" is never "does not exist" |
| Andrej Karpathy, the "LLM Wiki" idea file (a public gist, 2026-04) | Sources stay as they were; a maintained layer of linked notes on top; a schema file that tells the agent how; an index read first, an append-only log, periodic lint; good answers are filed back; an index is enough up to about a hundred sources | `sources.tsv`, the front page, the coverage test; the agent's rule file says "read the front page first" |

## Output

A folder in the skill pack repository, `docs/prior-art/`:

- `README.md`: the dated front page. A one-paragraph verdict (where the skill pack sits and why), **Borrow** (at most 12 ideas, each with its module and source), **Avoid**, open questions for the owner (at most 5) and the next re-scan date.
- One file per lens, `<date>-<lens>.md`: a table of name, what it does, what to borrow, what to avoid, source.

## After the scan

1. Borrowed ideas that change meaning or a number become owner asks in the console (at most 10 open, each with the source as evidence).
2. The rest become `proposed` rows in `ssot/user-stories.agent.tsv` or issues, each naming its source.
3. The owner questions go to the next meeting's agenda.
