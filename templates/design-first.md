# Design first: one page and a synthetic demo before the code

Before building a feature an owner has to understand and steer, the agent researches it, writes one page the owner can decide on, shows a clickable demo of the real page drawn from a made-up world, and waits for a yes. Only then is the code written; from then on the harness draws the demo itself, so the picture people agreed to never drifts from the code. Why, and what it paid for: [docs/lessons.md](../docs/lessons.md#design-and-a-synthetic-demo-before-code-from-adcut-harness-x45-2026-10-13).

*Seen once:* the video-ads harness (its ROADMAP X45, 2026-10-12 and 13), before it built a map of its creative plan with a weight on each path. The owner confirmed four decisions in one reply.

## When

A feature an owner has to understand and steer: a page they decide on, a plan they pick from, a model whose output they act on, or a table the harness keeps for good. A fix, a refactor or a change only the builder sees goes straight to code with its test.

## The steps

1. **Research first.** Run [the prior-art scan](prior-art-scan.md) on the feature: how others do it, what went wrong for them, what to avoid. Each trap it finds becomes a question the design page answers.
2. **One design page, in the owner's language.** One page, not a thread, holding what the next section lists. The owner reads it in a few minutes and answers in one reply.
3. **A clickable demo from a synthetic world.** The real page the feature will write, drawn by the renderer the code will use, from a made-up product with `DEMO` ids, scanned for client terms and shared privately ([The demo](#the-demo)).
4. **Wait for the owner's yes.** No code before it. A change the owner asks for goes back into the page and the demo, and the owner sees the new version.
5. **Then the code, and the harness draws the demo.** Build to the confirmed page. The demo becomes a harness tool fed by a synthetic fixture and published to the same link ([After the owner confirms](#after-the-owner-confirms)).

## The design page

One page in the owner's language, for someone who will never read the code:

- **What it is.** One paragraph: what the feature does for the owner, in their words.
- **How it decides.** The rule in plain words, with one worked example on the synthetic world.
- **The asks.** The few decisions only the owner can make (at most five), each with its options and a recommended answer, and one line, in the owner's language, that says how to agree to all of them at once ("reply 'agree' if all are as recommended").
- **What it stores.** Every table it adds, its columns and who writes them. An append-only table is permanent: once it holds rows its columns cannot change, so they are proven on a scratch copy of real data (never the client's live store) before the page fixes them, and the page says they were.
- **The traps.** Each trap the research found, and the answer the design gives to it. For example: a tree whose branches cross counts one item twice; a comparison that brings back a target a person had parked; a column that can never be changed.

## The demo

The page the feature will write, clickable, from a world nobody owns. Its guards:

- **A synthetic marker.** The world is marked synthetic (`"synthetic": true`), and the page says so where it is seen first: `kit.pagestyle`'s badge, `<span class="syn">`, in the header.
- **DEMO ids.** The product, the project and every code and id on the page start with `DEMO`, so nothing on it can be taken for, or matched to, a real one.
- **No client term.** Before it is written, the page is scanned with the harness's client-term lists (`load_terms` and `scan` of [kit/tools/leak_guard.py](../kit/tools/leak_guard.py)). It fails closed: a hit, no list, a named list missing or unreadable, or lists with no term, and nothing is written.
- **The harness's own renderer.** It is drawn by the code that will draw the real page (for a page that guides making, [`kit.pagestyle`](../docs/page-style.md)) and passes that renderer's check (`problems()`). Never a hand-made mock-up: it shows a page the code will not write.
- **Never in the client's review folder.** The demo is written outside the client's data, and a client's real page is never shared.
- **Shared privately.** One private link, given to the owner, who decides who else sees it. Every new version goes to the same link.

The guard, for a harness to copy into the tool that writes its demo. `ids` is the product, the project and every code and id the page shows; a page drawn with another renderer runs that renderer's check in place of `style.problems`.

```python
import html
from pathlib import Path

from kit import pagestyle
from kit.tools import leak_guard

MARK = '<span class="syn">'                         # kit.pagestyle's "synthetic data" badge


def demo_problems(world: dict, ids: list[str], page: str, *, out: Path, review: Path, terms: list[Path],
                  style: pagestyle.Style = pagestyle.DEFAULT) -> list[str]:
    """Why this demo page may not be written or shared; [] when it may. Fails closed on the term lists."""
    found = []
    if world.get("synthetic") is not True:
        found.append("the world is not marked synthetic")
    if not ids:
        found.append("no ids given: the product and the project at least")
    found += [f"{i!r} is not a DEMO id" for i in ids if not str(i).startswith("DEMO")]
    if MARK not in page:
        found.append("the page carries no synthetic marker")
    found += style.problems(page)
    if out.resolve().is_relative_to(review.resolve()):
        found.append("the demo is never written into the client's review folder")
    try:
        lists = leak_guard.load_terms(terms)         # Refusal: no list, one missing or unreadable, no term in them
    except leak_guard.Refusal as why:
        return [*found, f"no usable client-term list ({why}): nothing is written"]
    hits = set(leak_guard.scan(page, lists)) | set(leak_guard.scan(html.unescape(page), lists))
    return [*found, *(f"a client term, {h}" for h in sorted(hits))]
```

The tool writes the page only when the list is empty, and prints the reasons otherwise.

## After the owner confirms

- Build to the confirmed page. A difference the code runs into goes back to the owner; it is not decided quietly.
- The append-only tables land with the columns proven on the scratch copy.
- The demo becomes the harness's: a tool draws it from a synthetic fixture in the repository (marked synthetic, every id `DEMO`) with the renderer of the real page, runs the guard before writing, and names the private link it is published to, the same one each time. Its test runs the tool on the fixture and tries each refusal.
- The owner's answers are recorded where the harness keeps the owner's decisions, in their words.

## Checklist

- [ ] The prior-art scan is dated, and each trap it found is on the design page with its answer
- [ ] The design page says what it is, how it decides, the asks (each with a recommended answer, and one reply that agrees to all) and what it stores
- [ ] Every append-only column is proven on a scratch copy of real data
- [ ] The demo is drawn by the harness's own renderer from a synthetic world and passes the renderer's check
- [ ] The demo guard finds nothing: the synthetic marker, `DEMO` ids, no client term, outside the client's review folder
- [ ] The demo is shared privately, and the owner confirmed before any code
- [ ] After the code, the harness redraws the demo from a synthetic fixture to the same link
