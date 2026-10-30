# Design first: one page and a synthetic demo before the code

Before building a feature an owner has to understand and steer, the agent researches it, writes one page the owner can decide on, shows a clickable demo of the real page drawn from a made-up world, and waits for a yes. Only then is the code written; from then on the skill pack draws the demo itself, so the picture people agreed to never drifts from the code. Why, and what it paid for: [docs/lessons.md](../docs/lessons.md#design-and-a-synthetic-demo-before-code-from-adcut-harness-x45-2026-10-13).

*Seen once:* the video-ads skill pack (its ROADMAP X45, 2026-10-12 and 13), before it built a map of its creative plan with a weight on each path. The owner confirmed four decisions in one reply.

## When

A feature an owner has to understand and steer: a page they decide on, a plan they pick from, a model whose output they act on, or a table the skill pack keeps for good. A fix, a refactor or a change only the builder sees goes straight to code with its test.

## The steps

1. **Research first.** Run [the prior-art scan](prior-art-scan.md) on the feature: how others do it, what went wrong for them, what to avoid. Each trap it finds becomes a question the design page answers.
2. **One design page, in the owner's language.** One page, not a thread, holding what the next section lists. The owner reads it in a few minutes and answers in one reply.
3. **A clickable demo from a synthetic world.** The real page the feature will write, drawn by the renderer the code will use, from a made-up product with `DEMO` ids, scanned for client terms and shared privately ([The demo](#the-demo)).
4. **Wait for the owner's yes.** No code before it. A change the owner asks for goes back into the page and the demo, and the owner sees the new version.
5. **Then the code, and the skill pack draws the demo.** Build to the confirmed page. The demo becomes a skill pack tool fed by a synthetic fixture and published to the same link ([After the owner confirms](#after-the-owner-confirms)).

## The design page

One page in the owner's language, for someone who will never read the code:

- **What it is.** One paragraph: what the feature does for the owner, in their words.
- **How it decides.** The rule in plain words, with one worked example on the synthetic world.
- **The asks.** The few decisions only the owner can make (at most five), each with its options and a recommended answer, and one line, in the owner's language, that says how to agree to all of them at once ("reply 'agree' if all are as recommended").
- **What it stores.** Every table it adds, its columns and who writes them. An append-only table is permanent: once it holds rows its columns cannot change, so they are proven on a scratch copy of real data (never the client's live store) before the page fixes them, and the page says they were.
- **The traps.** Each trap the research found, and the answer the design gives to it. For example: a tree whose branches cross counts one item twice; a comparison that brings back a target a person had parked; a column that can never be changed.

## The demo

The page the feature will write, clickable, from a world nobody owns. Its guards:

- **A synthetic marker.** The world is marked synthetic (`"synthetic": true`, that value and no other), and the page says so where it is seen first: `kit.pagestyle`'s badge, `<span class="syn">` with its words, in the page's first `<header>`, before the decision. The guard reads where it sits in the markup: a badge in a comment, a fold (`<details>`), a script or style, or under an element with a `hidden` or `style` attribute does not count.
- **DEMO ids.** The product, the project and every code and id on the page start with `DEMO`, so nothing on it can be taken for, or matched to, a real one.
- **No client term.** Before it is written, the page is scanned with the skill pack's client-term lists (`load_terms` and `scan` of [kit/tools/leak_guard.py](../kit/tools/leak_guard.py)), in each form it reaches a reader: as written, unescaped, as shown (its tags gone, then unescaped, so a term split by `<b>` or `<br>` is whole again), and with its page data's JSON escapes read back (`\u0026` is `&`, `\"` is `"`, `\n` a new line). It fails closed: a hit, no list, a named list missing or unreadable, or lists with no term, and nothing is written.
- **The skill pack's own renderer.** It is drawn by the code that will draw the real page (before that code exists, see the next bullet; for a page that guides making, [`kit.pagestyle`](../docs/page-style.md)) and passes that renderer's check (`problems()`) with the skill pack's own style and command patterns, as every page the skill pack writes does. Never a hand-made mock-up: it shows a page the code will not write.
- **Before the code exists.** There is no renderer yet, so the demo is drawn by a stand-alone generator: one script, kept next to the design page and outside the skill pack's runtime, fed by the synthetic world, that draws the page the way the real one will (with `kit.pagestyle` for a page that guides making) and runs the same guard on what it writes. Its page is the one the owner confirms. After the build, the skill pack's own renderer redraws the same link from a fixture ([After the owner confirms](#after-the-owner-confirms)).
- **When no demo is needed.** A design that is only a set of rule or wording choices, with nothing new to draw, needs none. The design page says so in one line and gives a real worked example instead: the rule applied to the synthetic world, in the owner's words.
- **Never in a client's data.** The demo is written outside every client's data folder (each `$DATA_DIR`, its review folder included), and a client's real page is never shared.
- **Shared privately.** One private link, given to the owner, who decides who else sees it. Every new version goes to the same link.

The guard, for a skill pack to copy into the tool that writes its demo. `ids` is the product, the project and every code and id the page shows; `client_data` is every client's data folder; `style` and `commands` are the skill pack's own style and command patterns (its CLI's name), as in [Checking a page](../docs/page-style.md#checking-a-page). A page drawn with another renderer runs that renderer's check in place of `style.problems`.

```python
import html
import re
from html.parser import HTMLParser
from pathlib import Path

from kit import pagestyle
from kit.tools import leak_guard

JSON_ESCAPE = re.compile(r'\\(u[0-9a-fA-F]{4}|["\\/bfnrt])')
CONTROL = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def read_back(text: str) -> str:
    """JSON's string escapes read back, as an agent that parses the page data reads it: \\u0026 is &, \\" is "."""
    return JSON_ESCAPE.sub(lambda m: chr(int(m[1][1:], 16)) if m[1][0] == "u" else CONTROL.get(m[1], m[1]), text)


def forms(page: str) -> tuple[str, ...]:
    """The page as a reader gets it: as written, unescaped, as shown (tags gone, then unescaped), its data read back."""
    return page, html.unescape(page), html.unescape(re.sub(r"<[^>]*>", " ", page)), read_back(page)


class Badge(HTMLParser):
    """The words of the synthetic badge (<span class="syn">) in the page's first <header>, before the decision; not in
    a comment, a fold, a script, a style or a template, nor under an element with a hidden or style attribute."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self, page: str):
        super().__init__(convert_charrefs=True)
        self.open, self.headers, self.decided, self.words = [], 0, False, ""
        self.feed(page)
        self.close()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.decided = self.decided or a.get("data-zone") == "decision"
        self.headers += tag == "header"
        if tag not in self.VOID:
            self.open.append((tag, a))

    def handle_endtag(self, tag):
        tags = [t for t, _ in self.open]
        if tag in tags:
            del self.open[len(tags) - 1 - tags[::-1].index(tag):]

    def handle_data(self, data):
        tags = {t for t, _ in self.open}
        if (self.headers == 1 and "header" in tags and not self.decided
                and not tags & {"details", "script", "style", "template"}
                and not any("hidden" in a or "style" in a for _, a in self.open)
                and any(t == "span" and "syn" in (a.get("class") or "").split() for t, a in self.open)):
            self.words += data


def demo_problems(world: dict, ids: list[str], page: str, *, out: Path, client_data: list[Path], terms: list[Path],
                  style: pagestyle.Style, commands: list[str]) -> list[str]:
    """Why this demo page may not be written or shared; [] when it may. Fails closed on the term lists."""
    found = []
    if world.get("synthetic") is not True:
        found.append("the world is not marked synthetic")
    if not ids:
        found.append("no ids given: the product and the project at least")
    found += [f"{i!r} is not a DEMO id" for i in ids if not str(i).startswith("DEMO")]
    if not Badge(page).words.strip():
        found.append("no synthetic badge in the page's first header, before the decision")
    found += style.problems(page, commands=commands)
    if not client_data:
        found.append("no client data folder given: where the demo goes cannot be checked")
    elif any(out.resolve().is_relative_to(d.resolve()) for d in client_data):
        found.append("the demo is never written into a client's data folder")
    try:
        lists = leak_guard.load_terms(terms)         # Refusal: no list, one missing or unreadable, no term in them
    except leak_guard.Refusal as why:
        return [*found, f"no usable client-term list ({why}): nothing is written"]
    hits = {h for text in forms(page) for h in leak_guard.scan(text, lists)}
    return [*found, *(f"a client term, {h}" for h in sorted(hits))]
```

The tool writes the page only when the list is empty, and prints the reasons otherwise.

## After the owner confirms

- Build to the confirmed page. A difference the code runs into goes back to the owner; it is not decided quietly.
- The append-only tables land with the columns proven on the scratch copy.
- The demo becomes the skill pack's: a tool draws it from a synthetic fixture in the repository (marked synthetic, every id `DEMO`) with the renderer of the real page, runs the guard before writing, and names the private link it is published to, the same one each time. Its test runs the tool on the fixture and tries each refusal.
- The owner's answers are recorded where the skill pack keeps the owner's decisions, in their words.

## Checklist

- [ ] The prior-art scan is dated, and each trap it found is on the design page with its answer
- [ ] The design page says what it is, how it decides, the asks (each with a recommended answer, and one reply that agrees to all) and what it stores
- [ ] Every append-only column is proven on a scratch copy of real data
- [ ] The demo is drawn by the skill pack's own renderer from a synthetic world and passes the renderer's check (before the code exists, by a stand-alone generator; when none is needed, the page says so and gives a worked example)
- [ ] The demo guard finds nothing: the synthetic world and its badge in the header, `DEMO` ids, the renderer's check with the skill pack's style and commands, no client term in any form of the page, outside every client's data folder
- [ ] The demo is shared privately, and the owner confirmed before any code
- [ ] After the code, the skill pack redraws the demo from a synthetic fixture to the same link
