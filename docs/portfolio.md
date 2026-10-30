# The growth portfolio: where each skill pack sits, what it owns, how they talk

Status: design. The owner adopted the structure on 2026-10-23. Three decisions are still open (at the end). This page is the map every acquisition and growth skill pack is checked against; a pack's own `SKILL.md` names its neighbours from here.

How the packs combine for each kind of client is [solutions.md](solutions.md).

It was drawn from a survey of the owner's repositories on 2026-10-23: about thirty, of which fifteen are live skill packs, four are new scaffolds, and the rest are superseded, client cases or data. Two more packs built the same week, `asset-handoff` and `ad-copy`, were placed on 2026-10-23.

## Two axes, and why neither alone is a pack boundary

1. **How the person meets the brand.**
   - *Pull:* the person searches. Keywords, search terms, bids and impression share are the levers.
   - *Push:* the platform puts it in front of them. The creative is the lever.
2. **What it costs.**
   - *Paid:* ads.
   - *Organic or earned:* SEO, AI answers, creators, own social.
   - *Sales-led:* lead lists and a pipeline.

Pull and push need different engines, but **one platform account often holds both**:
- Google: Search and Shopping are pull; YouTube, Demand Gen and Display are push.
- Amazon: Sponsored Products is pull; Sponsored Brands video and Display are push.
- 千川: the feed is push, and 千川 search is pull.

Two packs on one account would share a credential, a change log and a write path, which is the worst coupling there is. So:

- **A pack is cut by platform account**: one credential, one ledger, one writer per platform.
- **Pull and push are engine families in the kit.** A platform's pack takes one family or both.

## Five layers

| Layer | What it is | Members |
| --- | --- | --- |
| **1. Platform** | What every pack shares | the kit, the client hub (one facts store, one tagged intake, one inbox per owner, the exchange folder), `cloud-gpu` (a compute library, not a skill pack), `filmkit` (a render library, not a skill pack: a film spec in, a finished film out) |
| **2. Operators** | One pack per platform account. It holds the credential, the pulls, the ledger, the change log, the proposals and the guarded writer | see the table below |
| **3. Truth** | Facts several packs need. One owner each; everyone else reads the owner's documents | `product-feed` (catalog, prices, stock, promotion windows), `measurement` (internal attribution, coefficients, break-even ROAS, incrementality), `search-intel` (demand and competitors for paid *and* organic search), `asset-handoff` (a creative's identity and tags: one name across its sizes, the UTM tags from the client's table, the rows for the client's intake form), messaging (the insight matrix and the claims scope; today inside adcut) |
| **4. Makers** | Make assets to a spec and hand them over with a manifest. They know no platform's API | `adcut` (video), `proofcut` (video from a B2B manufacturer's own footage), `product-keyframe-video` (product images), `ad-copy` (text: what each placement allows, the check of candidate text against it, and the proposals) |
| **5. Engines** | Logic that two or more packs use, in the kit | `ads-core`, `intent`, `creative`, `compliance`, `generation` (below) |

Operators by axis:

| | Pull | Push |
| --- | --- | --- |
| **Paid** | `amazon-ppc` (Amazon Ads), `google-ads` (every Google Ads campaign type). Later: Microsoft Ads, Naver, Apple Search Ads | `meta-ads` (Meta, through Smartly or its API), `video-ads` (千川, 腾讯广告/视频号). Later: TikTok, in a pack of its own |
| **Organic / earned** | `ecommerce-seo` (Google organic), `seo-programmatic`, `seo-tools` (frozen), `geo-china` (Chinese AI assistants) | creators: `koc-script` (briefs), `creator-program` (economics, coupons, affiliate). Own social: `social-marketing` (dormant) |
| **Sales-led** | `outbound` (find companies and contacts) hands to `sdr` (the pipeline to the CRM) | — |

## Meta is its own operator; the 千川 and 腾讯 bundle is temporary

Decided 2026-10-26 (the owner, in chat): Meta becomes `meta-ads` (`mads`), split out of `video-ads`. Ownership rule 1 already says one operator per platform account. `video-ads` grew from one client's creative loop into a pack holding three platforms, and the three differ where it matters:

- **Different write risk and route.** Meta is read through Smartly's reports and exports, or Meta's API; where a client's own team pushes to Meta, the pack holds no right to write to the ad account. 千川 and 腾讯 are reached through their APIs, read and write (video-ads R66). One pack would hold a write guard that is on for one platform and off for another.
- **The media library is the platform's.** The upload to Meta's media library, through Smartly or the API, is one write with two routes (video-ads R80), and ownership rule 3 gives it to the platform's operator.
- **The engines are in the kit.** With `ads-core` and `creative` there (kit 0.38.0 and 0.40.0), what a platform pack keeps is small: its pull adapters, its field mapping, its limits table and its guarded writer. Splitting no longer copies a ledger, a pacing rule or a lifecycle.

The split is behaviour-preserving: its steps are the Next rows of `meta-ads`' `docs/ROADMAP.md` (X1 to X7). `meta-ads` vendors the kit itself and has no code dependency on `video-ads`, so the new pack does not copy a copy; `video-ads` deletes its own engine copies at its X63 (portfolio phase 4) and its Meta side after that.

**When `video-ads` splits again.** 千川 and 腾讯 stay together only while neither has its own writer: both are read from report files or an API, into one ledger route each. Each becomes a pack of its own (one per platform account) when any of these holds:
1. one of them gets its guarded writer (video-ads X89): a different credential, a different allowlist and kill switch;
2. a client uses one and not the other;
3. one of them needs pull logic the other does not use.

TikTok is not added to `video-ads`: it is a pack of its own when a client needs it. Decided 2026-10-28 (the owner): the shared ads layer is the kit's `ads-core` (with `creative`), not a new `ads-skill-pack` repository, and `video-ads` is not renamed. After the refactor it holds 千川 and 腾讯 only; its command word, environment prefix and database file stay.

## Where every repository sits

What a repository is and where it sits in the layers. Whether a client has used it is the `use` column, read from [`tools/adoption.tsv`](../tools/adoption.tsv) and checked by `tests/test_adoption.py`; the long state notes this table used to hold went stale in a week. `earned`: a client's data has gone through it; `built`: tests, no client; `shell`: a scaffold; `library`: not a skill pack.

| Repository | CLI | Layer and role | Use ([tools/adoption.tsv](../tools/adoption.tsv)) | What changes |
| --- | --- | --- | --- | --- |
| amazon-ppc-skill-pack | `ppc` | Operator, paid pull, Amazon | built | Names its neighbours; its intent engines are the source for the kit's `intent` |
| google-ads-skill-pack | `gads` | Operator, paid pull and push, Google | earned | Takes YouTube and Display (open decision 1); takes `intent` and `creative` from the kit at B3 |
| meta-ads-skill-pack | `mads` | Operator, paid push, Meta | earned | Takes the Meta side of `video-ads` (its `docs/ROADMAP.md`, X1 to X7), on the kit's `ads-core` and `creative` (its thin verbs, X23 and X24, import them); the upload to Meta's media library is its write (video-ads R80) |
| video-ads-skill-pack | `vads` | Operator, paid push: 千川, 腾讯 (Meta leaves it, see below) | earned | R43 rewritten; engines to `ads-core` and `creative` (its X63), then the Meta side to `meta-ads` |
| ecommerce-seo-skill-pack | `seo` | Operator, organic pull, Google organic | earned | Owns website content fields; reads `intel/1` for new demand work |
| ecommerce-seo-skill-pack-plugins | — | Distribution of `seo` (web audit, app, MCP) | distribution of `seo` | None |
| seo-programmatic-skill-pack | `pseo` | Operator, organic pull, page sets | shell | Reads its page list from `seo` (its S07) |
| seo-tools-harness | `seoh` | Operator, organic pull, free tools | frozen | Demand checks move to `search-intel` when it next changes |
| geo-china-skill-pack | `geo` | Operator, organic pull, AI answers (China) | earned | Global AI answers become the same pack with a market, or a sibling (open, not urgent) |
| koc-script-skill-pack | `kos` | Operator, earned push, creator briefs | built | Its claims check moves to the kit's `compliance` |
| creator-program-skill-pack | `crp` | Operator, earned push, creator economics and affiliate | built | Publishes `creators.roster/1`; takes affiliate commissions |
| social-marketing-harness | `smh` | Operator, own social (RedNote) | dormant since 2026-10-01 (R8) | Keep; its browser reader is the model for a kit browser module |
| outbound-skill-pack | `obd` | Operator, sales-led, sourcing | built | Hands `leads/1` to `sdr` (open decision 2) |
| sdr-skill-pack | `sdr` | Operator, sales-led, pipeline | earned | Reads `leads/1` (companies another pack found) and `inquiries/1` (what people wrote to the client); a first email in a country that needs consent goes out only with the recipient's own message as evidence, so an inquiry is the lawful way in |
| product-feed-skill-pack | `feed` | Truth: catalog | shell | Publishes `catalog/1`; owns the merchant-feed override fields |
| measurement-skill-pack | `meas` | Truth: outcomes | built | Publishes `truth/1`; reads `ads.results/1` and `ads.changes/1` |
| asset-handoff-skill-pack | `handoff` | Truth: a creative's identity and tags | built | Publishes `handoff.batch/1`; writes nothing outside: the upload to a media library is the platform operator's write |
| search-intel-skill-pack | `intel` | Truth: demand and competitors | shell | Publishes `intel/1` for paid and organic search |
| adcut-skill-pack | `adcut` | Maker, video | earned | Writes `ads.creatives/1`, reads `ads.results/1` from any operator; the insight matrix is the messaging source (open decision 3) |
| ad-copy-skill-pack | `adcopy` | Maker, text | built | Publishes `copy.proposals/1`; `gads`, `mads` and `vads` read its placement checks instead of building their own |
| product-keyframe-video | `keyframe` | Maker, product images, then the storyboard and intro that follow | built | The product in every frame is a real cutout and a model draws only the empty place (its M3, 2026-10-31); hands frames with `ads.creatives/1` when it has a consumer; its intro video would be a `filmkit.film/1` spec |
| proofcut-skill-pack | `proof` | Maker, video from the client's own footage | shell | The first client class is B2B exporters (solution D): a story spine, facts that carry their source quote, a release step for people on camera, TikTok first. Renders through `filmkit`; adcut is untouched |
| cloud-gpu-skill-pack | `cloudgpu` | Platform, GPU jobs | library | The one provider behind the kit's `generation` for self-hosted runs |
| filmkit | `filmkit` | Platform, render | library | The engine under `proofcut`: one JSON film spec (`filmkit.film/1`) in, a finished film out, with static checks first. Needs numpy, Pillow, scipy and ffmpeg, so a pack runs it as a program from a vendored copy; adcut keeps its own composer until a second maker needs this one |
| skill-pack-playbook | — | Platform | this repository | Holds the contract schemas, the exchange folder and the engines |

Not skill packs, or superseded (archive or leave): how a pack that has been split is retired is in [maintaining.md](maintaining.md), "Retiring a pack".
- `amazon-ads-harness`: superseded by `amazon-ppc`.
- `geo-china-harness`: superseded by `geo-china-skill-pack`.
- `openmax-seo`: superseded by `seo-programmatic`'s case repository.
- `douyin-ads-creative-harness`: superseded by `adcut`.
- `commerce-ads-harness`: absorbed by `video-ads` (its D41, D45).
- `social-media-meta-data`: a data project.
- `daily-report`: an internal tool.
- `seo-tools-ecommerce`: a case of `seoh`.
- `*-workspaces` repositories: client workspaces.

`asset-handoff` was first planned as no pack and was then built. It holds a fact several packs need, a creative's identity and tags, so it sits in the truth layer and stays read-only. Its planned writes do not stay with it:
- uploading to a media library (Smartly, for Meta) is the Meta operator's write, in `meta-ads`;
- appending rows to the client's intake form is a person's step in v1.

The pack that runs the ads still owns the delivery spec (video-ads R43 for 千川 and 腾讯; `meta-ads` for Meta once the split is done); `handoff.batch/1` carries the names and tags it reads.

## How the Google Ads work was cut (2026-10-22)

A client meeting on Google Ads on 2026-10-22 gave the cut the table above shows for `gads`, `feed`, `meas` and `intel`. The owner agreed to it then; open decision 1 below is the one part still undecided. The cut follows the external system and the write risk, keeps work that has no channel out of the channel packs, and names no client in a pack.

| Pack | What it owns | Writes to an external system |
| --- | --- | --- |
| `google-ads` (`gads`) | One Google Ads account: pacing and KPI, search terms turned into keyword proposals, responsive search ad copy per promotion period, impression share, the Shopping split between new and proven budget, the change history | Yes, guarded. It is the only pack that writes to the account |
| `product-feed` (`feed`) | The website against the merchant feed: price, stock, errors | Its own override fields only |
| `measurement` (`meas`) | The company's own attribution exports against the platforms' numbers, trust per campaign type, the coefficient, the change and incrementality ledger. Channel-neutral | No. It reads other packs' saved `--json` documents and never their databases |
| `search-intel` (`intel`) | Trends, competitors' public ads, brand-term poaching | No |

- **Affiliate commission reconciliation** goes into the existing `creator-program`, not into a new pack.
- **Headline and ad copy** read the messaging source (the insight matrix, today inside `adcut`) and do not own it (open decision 3).
- **Display and YouTube** become `gads` modules if open decision 1 is settled as recommended.
- **No market is written into any pack's `skill-pack.toml`.** A client's markets are separate accounts, so each gets its own data folder in the client's workspace. A pack without markets serves one hub market: `new_hub.py add-pack --market M` adds the folder, and the hub runs it as `<cli>-<m>` (for example `gads-tw`).

## Ownership rules

1. **One operator per platform account.** Nobody else holds that platform's credential or writes to it.
2. **One owner per fact.** A fact several packs need (a price, a break-even ROAS, a coefficient, a promotion window) is published by its owner and read by the rest. A confirmed value lives in the client hub's facts store.
3. **One writer per external field.** For example: website product content belongs to `seo`; merchant-feed overrides belong to `feed`; campaign settings belong to that platform's operator; uploads to a platform's media library (Smartly included) belong to that platform's operator alone.
4. **Within a platform vs across sources.** Comparing two routes of the *same* platform's data (an export against the API) is plumbing in `ads-core`. Comparing a platform with the company's own numbers is `measurement`.
5. **A pack never opens another pack's database.** It reads the documents below.

## Contracts

A contract is a versioned `--json` document. Its first line names it (`# ads.results/1`). Its schema lives in the playbook, in [`contracts/`](../contracts/README.md), one JSON schema and one example per contract. Rules:
- A consumer ignores fields it does not know.
- A breaking change is a new version, and the producer emits both versions for one release.
- Documents are written once into the client hub's exchange folder, `exchange/<contract>/<producer>/<date>.json`. Without a hub, a path flag does the same.
- A consumer imports a document into its own raw files, so raw only grows.

| Contract | Producer | Consumers | What it carries |
| --- | --- | --- | --- |
| `ads.creatives/1` (exists) | a maker | operators | creative id, files, the insight row it serves, the compliance state |
| `ads.results/1` (exists) | an operator | makers, `measurement`, `creator-program` | per creative: spend, outcomes, stage, whether the day is settled (its schema requires `creative_code`, so a campaign-level read has no home here until `ads.spend/1`) |
| `ads.results/2` | an operator | makers, `measurement`, `creator-program` | `ads.results/1` with the money columns in the row's own currency (`currency`, ISO 4217) instead of `_cny`; both are written for one release |
| `ads.demand/1` | an operator | makers | how many creatives, of which format and slot, by when |
| `handoff.batch/1` | `asset-handoff` | operators | each creative's name across its sizes, its files, its UTM tags, its form rows, and whether the names match in the media library and the form |
| `copy.proposals/1` | `ad-copy` | operators | candidate text per placement, its check result, the selling-point direction it tests |
| `ads.changes/1` | an operator | `measurement` | each change: when, what, who or which client type |
| `catalog/1` | `product-feed` | operators, makers, `seo` | SKU, price, availability, promotion windows |
| `messages/1` | the messaging owner | makers, `ad-copy`, `gads` (search ad assets), `kos` (briefs) | segment, pain, objection, sayable facts, the claims scope |
| `truth/1` | `measurement` | operators | coefficient per campaign type, break-even ROAS, trust per campaign type; confirmed values go into the hub's facts |
| `intel/1` | `search-intel` | `gads`, `ppc`, `seo`, `pseo` | keyword demand, trends, competitors seen, with sources and dates |
| `ads.spend/1` | an operator | `meas`, the other operators | spend and its return per entity and day on the platform's numbers, money or index, settled or not |
| `ads.status/1` | an operator | the daily page, the console | one day's status: freshness, spend, sections ready or not, what waits for a person |
| `intel.ads/1` | `search-intel` | `adcopy`, `gads`, `ppc` | the ads competitors were seen running on search pages: words as published, first and last day seen, times seen |
| `leads/1` | `outbound` | `sdr` | company, contacts, source, evidence |
| `inquiries/1` | any operator that receives an inquiry (`seo` for site forms, `gads` and `meta-ads` for lead ads) | `sdr` | who wrote, from which company, the words as written, the page, the consent box text |
| `creators.roster/1` (exists as vads K5) | `creator-program` | `meta-ads` | collaborations, codes, ad ids |

## Engines in the kit

The kit's admission rule holds with one allowance: an engine may be lifted out of its first skill pack before a second imports it, as an `incubating` pack with a date by which it must have two importers ([tools/pack_status.tsv](../tools/pack_status.tsv); the rule is in [CLAUDE.md](../CLAUDE.md)).

The cross-platform shared ads layer is `ads-core` and `creative`; a pack never imports another pack, it vendors the kit.

| Kit pack | What | From | Consumers |
| --- | --- | --- | --- |
| `ads-core` (kit 0.38.0; `daily` and `audit` with the next train) | the report ledger (settled days, restatement, currency), pacing and the two wallets, alerts against an entity's own baseline, the change log, two-route reconcile, a campaign's lifecycle state machine, the proven/unproven rule, the account audit's rules, the day's advice as one list of items, the campaign document the pack's verb prints (`compute_campaign`: the pack hands over its tables as a `Source`, the module returns the document; the other documents follow one at a time, issue #252) | `video-ads` (`perfledger`, `pacing`, `adgroup`, `allocation`, `reconcile`, `campaign`, `compute_campaign`, `daily`, `audit`) and `amazon-ppc` (`compute_budget`, `certainty`, `compute_alerts`, `compute_changes`) | `mads`, `vads`, `gads`, `ppc` |
| `intent` | search-term triage, harvest and negatives; auction pressure; impression share with its clamped values | `amazon-ppc` (`compute_triage`, `auction_pressure`, `keyword_leaders`) | `ppc`, `gads` |
| `creative` | creative lifecycle and fission score, creative demand, portfolio life | `video-ads` (`life`, `fission`, `demand`, `portfolio`) | `mads`, `vads`, `gads` (YouTube), `ppc` (Sponsored Brands video) |
| `compliance` (exists) | one claims and copy check, rules per jurisdiction | merges adcut's lint and claim scope, kos's `claim_rules`, geo's draft rules | every maker and `kos` |
| `generation` (exists) | paid takes, prices, preflight, consent; `cloud-gpu` as the self-hosted provider | replaces three separate autodl clients (adcut, keyframe, cloudgpu) | makers |

## Placing a new capability: four questions

1. Does it write to an external system or hold a credential? Then it goes in that platform's operator. There is only ever one.
2. Do other packs need it as a fact? Then it has one owner, which publishes a document.
3. Do two or more packs need the logic? Then it goes in the kit. Until a second pack needs it, it stays in the first.
4. Is it about one client? Then it goes in that client's workspace or hub, never in a pack.

## Conflicts to fix, in order

1. `video-ads` R43 sends Google Search to `amazon-ppc` and claims YouTube Shorts. Google belongs to `gads`; Meta belongs to `meta-ads`; what R43 keeps is 千川 and 腾讯 (TikTok later, in a pack of its own).
2. adcut's results contract names `commerce-ads-harness`, which `video-ads` absorbed. Any operator emits `ads.results/1`.
3. Demand research exists three times (`seo`'s DataForSEO, `seoh/kw`, `ppc`'s SellerSprite), and competitor discovery four times. `search-intel` owns them; older packs move only when they next change.
4. Two writers of product data: `seo` writes website product fields and `feed` writes merchant-feed overrides. Rule 3 above settles it.
5. `outbound` and `sdr` repeat discovery, enrichment and registries without knowing each other. `leads/1` joins them.
6. The claims check exists three times (adcut, kos, geo). It merges into the kit's `compliance`.
7. Three autodl clients. One provider behind `generation`.
8. Three upload paths to Smartly (adcut's person-run `tools/smartly_upload.py`, asset-handoff's planned upload, video-ads' upload contract). Only `meta-ads` writes to Smartly (video-ads R80: Smartly and the Meta API are two routes of one platform); the other two hand it files.
9. Archive the five superseded repositories.

## Rollout

Phases run in order; the sessions inside a phase touch disjoint repositories and can run together.

| Phase | Who | What | Waits for |
| --- | --- | --- | --- |
| 0 | the owner | the three open decisions; archive the superseded repositories | — |
| 1 | one session per pack | boundaries in each pack's `SKILL.md` and roadmap (docs only) | 0 |
| 2 | two playbook sessions | (a) the client hub's steps 2–4 merged, then the exchange folder; (b) the contract schemas and a kit helper | 0 |
| 3 | one session per producer and consumer pair | emit and read contracts through the kit helper | 2 |
| 4 | a playbook session with `vads`, then `ppc` | the `ads-core`, `creative` and `intent` engines into the kit | 3 |
| 5 | one session per truth pack | `product-feed`, `search-intel`, `measurement` start; messaging per decision 3 | 2 |
| 6 | the playbook, then each maker | `compliance` merged; `generation` with `cloud-gpu` | 4 |

`google-ads` keeps building throughout. It takes `ads-core`, `intent` and `creative` at its B3 if phase 4 is done by then, or builds against the contracts and swaps in the kit later.

## Open decisions

1. **YouTube and Display go to `google-ads`.** Recommended: yes, by rule 1 (one operator per account). `video-ads` keeps no Google surface.
2. **`outbound` and `sdr`.** Recommended: two packs joined by `leads/1`. Sourcing scrapes and spends on its own budget, while the pipeline writes to a CRM; their risks differ.
3. **Messaging.** Recommended: take the insight matrix and the claims scope out of adcut into a small truth pack that publishes `messages/1`, once a second consumer (`gads` or `ad-copy`) is ready. Until then adcut emits `messages/1` itself.
