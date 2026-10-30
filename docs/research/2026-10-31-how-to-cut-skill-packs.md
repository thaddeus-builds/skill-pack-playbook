# How to cut skill packs: what mature systems do

Researched 2026-10-31. Asked by the owner: think hard about how the clients' business scenarios are best abstracted into skill packs, and learn from the authorities. One agent, five searches and six pages read; the pages are cited per claim.

## Verdict

1. **Keep the cut by external system and credential.** Every source that builds many integrations ends in the same rule: one component per API or problem domain, a unit of work that talks to one service only, and the higher-level combination kept outside. Our ownership rules 1 and 3 are that rule. **[documented]**
2. **A combination of several operators is not another operator.** HashiCorp puts abstractions over several components in modules, not in providers. For us the five solutions (`docs/solutions.md`) are such modules: the hub, the contract files and the weekly routine, never a verb of one operator that reaches into another platform. **[documented]** for the rule, **[inference]** for the mapping.
3. **A boundary drawn before use is the expensive one.** Fowler's argument is that even experienced architects find boundaries hard to place early and that moving a function across a service is harder than across a package; he says it tentatively and for new systems. Ten of our thirteen contracts and six truth or maker packs were drawn on 2026-10-23, and on 2026-10-31 they have no working producer and reader pair **[ours]**. The cut by account has held; the layers above it are hypotheses. **[documented]** (tentative) and **[ours]**
4. **Where the same word means different things, keep separate models.** A "creative", a "conversion" and a "campaign" are not the same object on Meta, 千川 and Google. Bounded contexts say a shared model across such groups produces confusion; a contract file between them is the map. **[documented]**
5. **Start with the simplest workflow; give an agent freedom only where the path cannot be known.** An operator's week (pull, propose, approve, write) is a predefined path and stays a workflow with an agent for judgement; autonomy needs guardrails and stop conditions. This matches our levels L0 to L3. **[documented]**
6. **A skill is measured, not declared.** Anthropic's authoring guide: write the evaluations before the documentation, describe what the skill does and when to use it, keep the body under 500 lines, keep references one level from the file, and set freedom by how fragile the step is. Four of our packs still carry `<<fill>>` in `SKILL.md`. **[documented]** and **[ours]**
7. **A measured factor carries its basis.** Google's Meridian calibrates a media-mix model with experiment results and says the experiment's ROI rarely equals the model's, because the baseline, the population and the period differ. A coefficient in `truth/1` is only as good as the experiment behind it, so it must name that experiment or it is an assumption (issue #168). **[documented]** and **[inference]**

## What each source says, and what does not transfer

- **HashiCorp, provider design principles.** A provider focuses on one API or problem domain (simpler authentication, easier discovery, maintainers who know one system); a resource is one API object (smaller blast radius); schemas follow the API; resources can be imported (adopt what already exists); breaking changes bump the major version. *Transfers:* rules 1 to 5 of the portfolio; "import" is our brownfield case, a client whose ads already run by hand. *Does not transfer:* Terraform is declarative with state; an operator pack is an advise-and-approve loop, so there is no plan/apply diff to reuse.
- **Airbyte, protocol.** Source and destination are separate roles that exchange serialized messages; the protocol is versioned apart from the platform. *Transfers:* contracts (`<name>/<version>`) versioned apart from the packs. *Does not transfer:* streaming records; ours are files written once.
- **Anthropic, "Building effective agents".** Predefined code paths (workflows) for well-defined tasks, agents where the model must decide the steps; use the simplest solution and add complexity only when it is needed; agents cost more and compound errors, so test in a sandbox and add stop conditions; invest in tool interfaces. *Transfers:* leave the daily routine a script and the judgement to the agent. *Does not transfer:* nothing material found.
- **Anthropic, skill authoring best practices.** See verdict 6. *Transfers:* a check on each pack's `SKILL.md` (description length and the "when to use", body lines) is cheap. *Does not transfer:* the guide is written for one skill; a pack is a set of verbs, a registry and a console.
- **Fowler, MonolithFirst and BoundedContext.** See verdicts 3 and 4. *Does not transfer:* his case is services over a network; ours are repositories whose kit is copied, so a wrong boundary costs a re-vendor, not an outage. That is why the cost is real but smaller.
- **Google Meridian, calibrating priors.** See verdict 7. *Does not transfer:* a media-mix model needs long geo-level history; our clients do not have it, so the lesson is the discipline (name the basis), not the model.

## What could not be read

- The Anthropic page for the 5,000-token body limit: only third-party copies were found, so it is **unconfirmed**; the 500-line guidance is from Anthropic's own page.
- Airbyte's protocol page and Meridian's calibration page were read only through search summaries, not fetched.
- Team Topologies and the DDD book were not read; only secondary summaries of Team Topologies were found, and nothing from them is used above.
- No public primary source was found on how agencies that run many clients' accounts structure their operators' weekly work. One search engine, one country.

## Kinds of claim and where it is used

[documented] verdicts 1, 2 (rule), 3 (tentative), 4, 5, 6, 7; [ours] verdicts 3, 6 (counts from the pack exports of 2026-10-31); [inference] verdicts 2 (mapping), 7. Used by [docs/design/cut-by-use.md](../design/cut-by-use.md).

Sources: [HashiCorp provider design principles](https://developer.hashicorp.com/terraform/plugin/best-practices/hashicorp-provider-design-principles); [Airbyte protocol](https://docs.airbyte.com/platform/understanding-airbyte/airbyte-protocol); [Anthropic, Building effective agents](https://www.anthropic.com/research/building-effective-agents); [Anthropic, skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices); [Fowler, MonolithFirst](https://www.martinfowler.com/bliki/MonolithFirst.html); [Fowler, BoundedContext](https://martinfowler.com/bliki/BoundedContext.html); [Google Meridian, calibrate treatment priors](https://developers.google.com/meridian/docs/advanced-modeling/roi-priors-and-calibration).
