"""templates/design-first.md: design and a synthetic demo before code, held to what it promises.

Checked, each on a broken copy first, so a check cannot pass by looking at nothing:

  - the template keeps its sections, its five steps in order, the design page's parts, the demo's guards and its
    checklist, and the words that carry the rule (the prior-art scan, a recommended answer, append-only columns proven
    on a scratch copy of real data, DEMO ids, failing closed);
  - docs/lessons.md keeps the lesson (what it paid for, how often it was seen) and points at the template; a new
    harness's CLAUDE.md (templates/AGENT_INSTRUCTIONS.md) names the template where a feature starts; the prior-art
    scan and BUILD.md's B0.5 point at it;
  - the demo guard, the template's one Python block, is run as written: a demo page drawn with kit.pagestyle from a
    synthetic world passes it, and each way a demo breaks the rule is reported (a world not marked synthetic, no ids,
    an id that is not DEMO, no synthetic marker, a page the style did not draw, the client's review folder, a client
    term on the page, and no usable term list: fail closed).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
import _t  # noqa: E402
from test_docs_build import doc, section  # noqa: E402

from kit import pagestyle as ps  # noqa: E402

TEMPLATE = "templates/design-first.md"
LESSON = "Design and a synthetic demo before code (from adcut-harness X45, 2026-10-13)"
SECTIONS = ("When", "The steps", "The design page", "The demo", "After the owner confirms", "Checklist")
STEPS = ("Research first.", "One design page, in the owner's language.", "A clickable demo from a synthetic world.",
         "Wait for the owner's yes.", "Then the code, and the harness draws the demo.")
PARTS = ("What it is.", "How it decides.", "The asks.", "What it stores.", "The traps.")
GUARDS = ("A synthetic marker.", "DEMO ids.", "No client term.", "The harness's own renderer.",
          "Never in the client's review folder.", "Shared privately.")
CHECKLIST = ("The prior-art scan is dated",
             "The design page says what it is, how it decides, the asks",
             "Every append-only column is proven on a scratch copy of real data",
             "The demo is drawn by the harness's own renderer",
             "The demo guard finds nothing",
             "The demo is shared privately, and the owner confirmed before any code",
             "After the code, the harness redraws the demo from a synthetic fixture to the same link")
WORDS = {"The steps": ("](prior-art-scan.md)",),
         "The design page": ("recommended answer", "append-only", "scratch copy of real data"),
         "The demo": ("`DEMO`", "fails closed", "kit.pagestyle", "kit/tools/leak_guard.py")}
PY = re.compile(r"^```python\n(.*?)^```", re.M | re.S)


def bold_items(body: str, bullet: str) -> list[str]:
    """The bold leads of a list's items: `1. **Lead.**` (bullet r"\\d+\\.") or `- **Lead.**` (bullet "-")."""
    return re.findall(r"^" + bullet + r" \*\*(.+?)\*\*", body, re.M)


def template_problems(text: str) -> list[str]:
    """What templates/design-first.md fails to say."""
    out = [f"## {h}" for h in SECTIONS if not section(text, h).strip()]
    steps = bold_items(section(text, "The steps"), r"\d+\.")
    out += [s for s in STEPS if s not in steps]
    if not out and [s for s in steps if s in STEPS] != list(STEPS):
        out.append("the steps out of order")
    out += [p for p in PARTS if p not in bold_items(section(text, "The design page"), "-")]
    out += [g for g in GUARDS if g not in bold_items(section(text, "The demo"), "-")]
    items = re.findall(r"^- \[ \] (.+)$", section(text, "Checklist"), re.M)
    out += [f"checklist: {c}" for c in CHECKLIST if not any(i.startswith(c) for i in items)]
    out += [f"{h}: {w}" for h, words in WORDS.items() for w in words if w not in section(text, h)]
    if len(PY.findall(text)) != 1 or "def demo_problems(" not in "".join(PY.findall(text)):
        out.append("one Python block with demo_problems")
    return out


def pointer_problems(lessons: str, agent: str, scan: str, build: str) -> list[str]:
    """The lesson that is not kept whole, and each pointer at the template that is gone."""
    body = section(lessons, LESSON)
    out = [f"lesson: {w}" for w in ("](../templates/design-first.md)", "*Paid for:*", "*Seen once*", "The rules:")
           if w not in body]
    if "the playbook's `templates/design-first.md`" not in section(agent, "What lives here"):
        out.append("AGENT_INSTRUCTIONS.md: where a feature starts")
    if "](design-first.md)" not in section(scan, "When to scan"):
        out.append("prior-art-scan.md: when to scan")
    if "](templates/design-first.md)" not in section(build, "B0.5 · Prior-art scan"):
        out.append("BUILD.md: B0.5")
    return out


def test_the_template_keeps_its_steps_its_parts_its_guards_and_its_checklist():
    text = doc(TEMPLATE)
    assert template_problems(text) == [], template_problems(text)
    for lead in (*STEPS, *PARTS, *GUARDS):                                   # the check would notice each one gone
        assert template_problems(text.replace(f"**{lead}**", "**x**")) == [lead], lead
    for item in CHECKLIST:
        assert template_problems(text.replace(f"- [ ] {item}", "- [ ] x")) == [f"checklist: {item}"], item
    first, second = (f"1. **{STEPS[0]}**", f"2. **{STEPS[1]}**")
    assert template_problems(text.replace(first, "@@").replace(second, first).replace("@@", second)) == [
        "the steps out of order"]
    assert template_problems(text.replace("scratch copy of real data (never", "copy (never")) == [
        "The design page: scratch copy of real data"]
    assert template_problems(text.replace("It fails closed", "It warns")) == ["The demo: fails closed"]
    assert template_problems(text.replace("```python", "```text")) == ["one Python block with demo_problems"]
    assert template_problems("# t\n") == [f"## {h}" for h in SECTIONS] + [*STEPS, *PARTS, *GUARDS] + [
        f"checklist: {c}" for c in CHECKLIST] + [f"{h}: {w}" for h, ws in WORDS.items() for w in ws] + [
        "one Python block with demo_problems"]


def test_the_lesson_and_every_pointer_name_the_template():
    assert os.path.isfile(os.path.join(REPO, TEMPLATE))
    texts = (doc("docs/lessons.md"), doc("templates/AGENT_INSTRUCTIONS.md"), doc("templates/prior-art-scan.md"),
             doc("BUILD.md"))
    assert pointer_problems(*texts) == [], pointer_problems(*texts)
    lessons, agent, scan, build = texts
    assert pointer_problems(lessons.replace(f"## {LESSON}", "## x"), *texts[1:]) == [
        "lesson: ](../templates/design-first.md)", "lesson: *Paid for:*", "lesson: *Seen once*", "lesson: The rules:"]
    seen = section(lessons, LESSON)
    assert pointer_problems(lessons.replace(seen, seen.replace("*Seen once*", "*Seen*")), *texts[1:]) == [
        "lesson: *Seen once*"]
    assert pointer_problems(lessons, agent.replace("`templates/design-first.md`", "`x.md`"), scan, build) == [
        "AGENT_INSTRUCTIONS.md: where a feature starts"]
    assert pointer_problems(lessons, agent, scan.replace("](design-first.md)", "](x.md)"), build) == [
        "prior-art-scan.md: when to scan"]
    assert pointer_problems(lessons, agent, scan, build.replace("](templates/design-first.md)", "](x.md)")) == [
        "BUILD.md: B0.5"]


# ------------------------------------------------------------- the demo guard, run as the template writes it --

def guard():
    """demo_problems() as the template's one Python block defines it."""
    ns: dict = {"__name__": "design_first_guard"}
    exec(compile(PY.findall(doc(TEMPLATE))[0], TEMPLATE, "exec"), ns)       # noqa: S102 - the playbook's own text
    return ns["demo_problems"]


WORLD = {"synthetic": True, "product": "DEMO Desk Lamp", "project": "DEMO",
         "items": [{"code": f"DEMO-{i:04d}", "state": s, "p": p}
                   for i, (s, p) in enumerate((("promising", 0.8), ("testing", 0.5), ("down", 0.2)), 1)]}


TERMS = "# synthetic client terms\nAcme Widgets\nre:\\bACME-\\d{4}\\b\nSmith & Sons\n"


def ids(world: dict) -> list[str]:
    return [world["product"], world["project"], *(c["code"] for c in world["items"])]


def draw(world: dict, *, marker: bool = True, extra: str = "") -> str:
    """The demo page a harness would draw from `world` with kit.pagestyle: the marker in the header, the tiles and
    the bar, one decision, a row of cards, the owner's fold last."""
    style = ps.DEFAULT
    counts = {s: sum(c["state"] == s for c in world["items"]) for s in ps.STATES}
    syn = '<span class="syn">Synthetic data · demo</span>' if marker else ""
    cards = "".join(style.card(c["state"], anchor=c["code"].lower(), head=f"<span>{ps.e(c['code'])}</span>",
                               p=c["p"], works="Make one more like it", fails="Make fewer of it")
                    for c in world["items"])
    body = (f'<header class="top"><p class="eyebrow">The plan\'s map{syn}</p><h1>{ps.e(world["product"])}</h1>'
            f"{extra}</header>"
            + ps.tiles([(str(len(world["items"])), "items planned", "one row")])
            + f'<div class="space">{style.bar(counts, big=True)}{style.legend(counts)}</div>'
            + style.decision("Decide: make the next two?", "<p>The two most promising items</p>",
                             "demo make --next 2", "Paste it in a terminal")
            + f'<section class="rows"><div class="rowhead"><h2>Item by item</h2>{style.expand_all()}</div>'
            + style.fold_row("testing", anchor="row-1", title="Row 1", body=f'<div class="cards">{cards}</div>')
            + "</section>"
            + style.owner("<p>How it is worked out: the rates against the account's own.</p>"))
    return style.page(f"The plan's map · {world['product']}", body, {"project": world["project"], "synthetic": True})


def test_a_synthetic_demo_drawn_with_the_style_passes_the_guard():
    demo_problems = guard()
    with _t.tmpdir() as d:
        d = Path(d)
        terms = d / "client_terms.txt"
        terms.write_text(TERMS, encoding="utf-8")
        review, out = d / "data" / "review", d / "share" / "demo.html"
        page = draw(WORLD)
        assert '<span class="syn">' in page and ".syn{" in ps.CSS                # the style still draws the badge
        assert demo_problems(WORLD, ids(WORLD), page, out=out, review=review, terms=[terms]) == []


def test_the_guard_reports_each_way_a_demo_breaks_the_rule():
    demo_problems = guard()
    with _t.tmpdir() as d:
        d = Path(d)
        terms = d / "client_terms.txt"
        terms.write_text(TERMS, encoding="utf-8")
        empty = d / "empty.txt"
        empty.write_text("# only a comment\n\n", encoding="utf-8")
        review, out = d / "data" / "review", d / "share" / "demo.html"
        page = draw(WORLD)

        def said(world=WORLD, page=page, out=out, terms=(terms,), given=None) -> list[str]:
            return demo_problems(world, ids(world) if given is None else given, page, out=out, review=review,
                                 terms=list(terms))

        assert said(world={**WORLD, "synthetic": False}) == ["the world is not marked synthetic"]
        assert said(world={k: v for k, v in WORLD.items() if k != "synthetic"}) == ["the world is not marked synthetic"]
        assert said(given=[]) == ["no ids given: the product and the project at least"]
        real = {**WORLD, "items": [*WORLD["items"], {"code": "ACME-0001", "state": "testing", "p": 0.5}]}
        got = said(world=real, page=draw(real))
        assert got[0] == "'ACME-0001' is not a DEMO id" and got[1:] == ["a client term, line 3 of list 1"], got
        assert said(page=draw(WORLD, marker=False)) == ["the page carries no synthetic marker"]
        mockup = '<!doctype html><html><body><span class="syn">Synthetic data</span><h1>DEMO Desk Lamp</h1></body></html>'
        got = said(page=mockup)
        assert got and all(not g.startswith(("the world", "a client term", "no usable")) for g in got), got
        assert said(out=review / "demo" / "map.html") == ["the demo is never written into the client's review folder"]
        assert said(page=draw(WORLD, extra="<p>Made for Acme Widgets</p>")) == ["a client term, line 2 of list 1"]
        assert said(page=draw(WORLD, extra="<p>Made for acme   widgets</p>")) == ["a client term, line 2 of list 1"]
        assert said(page=draw(WORLD, extra=f"<p>{ps.e('Made by Smith & Sons')}</p>")) == [
            "a client term, line 4 of list 1"]                                       # found through the page's escaping
        for lists in ((), (d / "nowhere.txt",), (d / "nowhere.txt", terms), (empty,)):     # fail closed
            got = said(terms=lists)
            assert len(got) == 1 and got[0].startswith("no usable client-term list"), (lists, got)


if __name__ == "__main__":
    _t.main(globals())
