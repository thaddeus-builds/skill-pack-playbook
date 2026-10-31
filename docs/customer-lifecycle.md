# Customer stages in paid acquisition

Status: proposal, from the Meta ads skill pack (merged 2026-10-31), for the owner to keep, change or drop. It is **method, not rule**: nothing in the kit checks it, and a pack that reads accounts may follow it in part. Where it comes from and what is untested is at the end.

A growth pack that buys attention reads an account by the ad: which creative, which budget, which day. The same account can be read by the person: someone who has never heard of the brand, someone who looked and left, someone who bought. The three cost different amounts to reach, need different things said, and are paid back on different clocks. A single blended return hides which of them pays. This page is the method for reading and running paid media by stage of the customer, for any channel that can target by who the person already is.

## The stages

A model assembled from practitioners' recency bands and from reasoning, not a standard (no source publishes a full one for apparel):

| Stage | Who | Its job and its number | What is said and offered |
| --- | --- | --- | --- |
| Stranger | never bought, no recent engagement | the first order; the cost of winning a new customer from the shop's own counts, not the platform's return | the problem and the proof; discounts held back |
| Looked, did not buy | visited, viewed or added to cart in the last weeks | convert the first order; the cost of a first order from this pool | remove the objection (fit, returns, real users, delivery); an incentive only if the data shows it is needed |
| First-time customer, second-order window | one order, up to roughly the shop's own median gap to a second order and a margin beyond it | the second order; second-order rate at 30, 60 and 90 days | no persuasion about the claim they already bought; what is new, back in stock, what completes the set |
| Repeat and loyal | two or more orders | orders per customer, share who order again; paid media is a small tool here | early access; no discount by default |
| Lapsed | no order for far longer than the shop's own gap | reactivation rate | "what is new since your last order"; a capped incentive only here |

Each stage has a **different job in the creative, the product shown and the selling point**, not the same ad with another audience. This is consistent with every source read and with one account where the same creative returned several times more to a warm audience than to a cold one, while remarketing that reused cold-style persuasion returned about what prospecting did. No controlled test of stage-specific creative was found.

## Principles

1. **Define stages from the shop's orders, not from a platform's audiences.** A platform's "new" and "existing" are the audiences the advertiser built and the platform matched (customer-list match rates are 20 to 70%). *Fails when* orders cannot be tied to people, or volume leaves bands empty: use three stages.
2. **One question and one metric per stage; never one blended return.** *Fails when* a stage has too few orders: show "not enough data", not a number.
3. **Read a platform's return on a warm or existing pool as "reported", and state the break-even share:** the share of the orders the platform credits that the ads must have caused for the stage to pay, `cost of a purchase / (average order x contribution rate)`. Over 100% means it does not pay even if every credited order is caused by the ads. Never a lift figure without a test. *Fails when* the ads are the only contact with that pool; the share is then higher, still untested.
4. **The first-order case and the repeat case are separate.** If winning a customer costs more than the first order contributes, the rest must come from repeat orders: `(cost - first-order contribution) / contribution of a repeat order` per customer. The share of customers who order again is a floor of repeat orders per customer, and a low repeat rate inside a short wait cannot close a large gap. Repeat marketing then earns its place by making the repeat order cheap and the repeat rate higher, not by repaying the first order. *Fails when* the repeat rate is several times higher or the gap small; recompute from the shop's own gaps.
5. **Owned channels (email, messaging) own the second order first; paid media covers reach gaps, non-responders and launches,** and is held back from anyone just messaged or just converted. *Fails when* consent coverage is small or the per-message cost is high.
6. **Suppress by order date, on a schedule, across prospecting and non-buyer retargeting.** A customer list is a static upload: a buyer after the last upload is outside it. *Fails when* the match rate is low or the campaign type will not hard-exclude; add a purchaser layer from the pixel and accept some leakage.
7. **Size retargeting spend from the pool, not a percentage:** weekly spend at most `pool x weekly frequency / 1000 x CPM`. Published shares run from 0% to 30%; above the pool's ceiling money buys frequency, not reach. *Fails when* the pool refills fast.
8. **Discounts are a stage tool, not a default.** *Fails when* clearing stock is the goal.
9. **Test with a random split of the customer list when the list is large enough; otherwise say it cannot be tested.** Assign a share at random to "held out of every paid ad" for about 60 days, with the owned channels treating both halves alike, and read the second-order rate by assignment from the shop's orders. Seeing a repeat rate move from 10% to 13% takes about 1,800 customers a side (80% power, 5% error, my arithmetic). Geo tests need many markets; platform lift tests need about 100 conversions; pausing the ads for a few weeks is confounded by drops and sales. *Fails when* the list is smaller than the arithmetic needs or the held-out group is still reached by broad campaigns.
10. **A tool states, an agent judges, a person approves.** What is mechanical (reading the targeting, placing an ad set in a stage, the arithmetic above) becomes a read-only check; every threshold is a starting point the agent may overrule with a reason said aloud; whether to split a pool, how much each stage spends and which angle it gets are the agent's to put in front of a person with the cost of each option. The only hard rules are the pack's safety ones.

## What a pack reads, and what it cannot

From an ad set's targeting text a pack can read which audiences it includes and excludes, the purchase-recency windows, whether the platform's automatic widening is on, the goal it optimises for, and which creative is shown to more than one stage. It cannot read how many people an audience holds, whether the customer list is current, whether the platform's own new-customer setting is on, how many of a returning pool would have bought anyway, or the real repeat interval and repeat rate: those come from the client's agent, the shop's orders and a test. A pack that cannot read a stage says so and names who can close it; it does not guess.

## What a pack provides to land it

- A read-only check that places each ad set in a stage from its targeting (falling back to the client's own naming rules, said so), and reports per stage the spend, the cost of a purchase, the return as reported, the cost against a new customer's, the break-even share, the creative shown to more than one stage, and what the data cannot see.
- The shop's own repeat facts as pending values (repeat rate; median days to a second order) and, when the client allows, aggregated counts of customers by days since their last order and by number of orders. No personal data crosses the pack.
- Plain wording rules: "reported" before every platform return; "caused" only with a test; the first order and the repeat order never merged.
- A reading note for the agent that gives the reasons and leaves the judgment open.

The Meta ads skill pack carries this as `mads compute lifecycle`, `mads lifecycle page`, the decision `audience_roles` and `references/lifecycle.md`. When a second pack needs the same placement and arithmetic, they move to the `ads-core` engines ([kit/packs.tsv](../kit/packs.tsv) rule); until then they live where they were paid for.

## Cross-channel and platform-specific

| Part | Any paid channel | Platform-specific |
| --- | --- | --- |
| Stages from the shop's orders (days since first and last order, order count) | Yes | Mapping them to audiences, retention windows, match rates, the platform's own settings |
| One question and one metric per stage | Yes | Which report columns approximate them |
| Break-even share, the first-order gap | Yes | The platform's attribution defaults and what they claim |
| Random list split, the power arithmetic | Yes | The platform's lift tool and its minimums |
| Owned channels first, suppression of what owned reached | Yes | List syncing, per-message pricing |
| Stage creative and offer discipline | Yes | Formats, catalogue sets |

## Where it was seen, and what is untested

Seen once: the Meta ads skill pack, reading a small direct-to-consumer apparel account (merge 2026-10-31). The account's media team already separated strangers from returning people in its audiences and in its copy; what the pack found was one remarketing pool that mixed people who looked with people who bought, no ad set for either alone, the same posts shown to both sides, and exclusion windows never set against the shop's gap to a second order.

Untested or unread: any controlled test of stage-specific creative for apparel, of email against paid sequencing, or of retargeting's incrementality at a small account's scale (the only published factor read for existing-customer audiences is about 0.6 of the platform's return, from one agency, test count not given, and the figures widely quoted for retargeting's overstatement are unsourced); Singapore's data-protection guidance on uploading a customer list to an ad platform could not be read (only secondary sources), so that is for the client or counsel to confirm before any upload.
