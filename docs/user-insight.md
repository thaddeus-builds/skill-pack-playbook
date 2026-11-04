# User insight for a remake: why one reference video works

A client often brings **one** short video they want to copy. Copying its look is easy and usually misses what made it work. This page is how a skill pack reads that one video before anything is made: whom it speaks to, which of its layers carry the value, whether the client's product can do the same job, and the one or two options a person picks from. Every skill pack that remakes a reference reads this page instead of working it out again. The result is a `remake.brief/1` file ([schema](../contracts/remake.brief-1.schema.json), [example](../contracts/examples/remake.brief-1.example.json)); the rules below are carried by that contract and checked by `kit/tests/test_contracts.py`, not only written here.

*Seen once:* product-image-to-video's first internal remake (2026-11-04, issue #527) copied the reference's structure, shots and captions and missed its story (a parent riding a childhood trail with a small child), its persona and its product use (a child on the rear seat). The form was picked by how often it appears, not by what carries the value. The research behind the rules is [docs/research/2026-11-04-single-reference-remake.md](research/2026-11-04-single-reference-remake.md).

## Who does what

| Piece | Who |
| --- | --- |
| Taking the video apart (cuts, transcript, loudness, a frame per shot for our own reading) | video-recipes' dissect library, vendored into the maker the way adcut takes it (#523); one video is an observation, never a recipe |
| Whom it speaks to and which layers carry the value: this page, written as `remake.brief/1` | the messaging owner (adcut's insight card today); product-image-to-video writes it itself until the insight pack exists |
| The storyboard and the film | the maker (product-image-to-video, adcut) |
| Picking the option, confirming a layer | a person: the client approves the storyboard (R35) |

## The steps

1. **The reference, by its link.** Its public numbers, read on a day: views, likes, comments, shares, the account's median over its recent posts; for a paid ad, the days it has run and how many variants its advertiser runs. No file of it goes into the brief.
2. **Whom it speaks to.** Who uses the product, who pays, how they relate, the situation, the job ("When ..., I want ..., so that ...") and where in the buyer's journey the video meets them, in the words of adcut's insight card and `messages/1`. A brief names the `messages/1` rows it serves by `insight_id`; it does not copy them.
3. **Every layer, once.** Hook, structure, shots, on-screen text, scene, story, persona, product use, sound, and the four where a viewer's reason to buy sits: the promise, the proof, the offer and call to act, and the brand. Each gets `carries_value` (yes, no, unknown), one hypothesis ("We see ..., because ..., but ...") and its evidence.
4. **The fit.** Can the client's product do the reference's job? If not, the brief names the nearest job it can do, from the product's facts, and the remake swaps the job; it never fakes it.
5. **One or two options.** The first is the replica, the reference's structure and story with the client's product. The second, when there is one, changes a single layer: the one whose value is least proven. One is recommended, and each says what a no means.
6. **A person picks**, and the variant's result goes back on its layer as evidence `test`, so the next brief for the product starts from a measurement, not a guess.

## The rules

- **Value is not frequency.** How often a form appears across videos is never evidence that it carries the value. Evidence is one of: days run and variants (a paid ad), a per-second curve the platform showed, engagement against the account's median, what the comments say (n of the comments read), the client's own pick and words, our own test. *Why:* the sample above.
- **Every layer is a hypothesis until a person answers it.** A judgement of yes or no rests on at least one piece of evidence; views never prove a cause.
- **At most two options.** Never a menu of every possible story. The console's own limits on open asks still apply.
- **Structure and story only (R34).** The remake never takes the reference's lines, music, faces, voices or distinctive cues (a colour, a mascot, a sound logo, a catchphrase, a signature shot); the brief lists them under `never_copy`, and the client's brand appears early (`brand_by_s`). A close copy of a competitor's video can be credited to the competitor.
- **AI people (R36).** An AI person may appear in any framing as long as it speaks no review and no endorsement. A market's own label for generated content still applies.
- **The proof part (R37, R38).** "Others use it" may use AI people. "Others bought it" may be played by an AI stand-in while no real customer has signed: the film is delivered and may run, so the client sees the result. The client then finds a real customer, the release goes into a consent record confirmed at the gate (`kit/consent.py`), and the proof part is made again.
- **Stills of the reference.** A frame per shot is for our own reading. The storyboard the client approves carries them (R35), so it is a client page with stills, sent under the owner's switch P02 of video-recipes; every other client page stays without them (P01).

## What a brief does not hold

No media file, still or clip; no line, caption or transcript of the source; no person's name. Those stay in the maker's working files or in its consent records.
