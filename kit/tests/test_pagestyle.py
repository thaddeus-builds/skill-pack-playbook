#!/usr/bin/env python3
"""kit.pagestyle: one look for the pages that guide making, on SYNTHETIC neutral content only (DEMO names, Group/Row
labels, made-up ids).

  [1] the words: EN and ZH both complete (every key of WORDS, no other, each a word, every template with its {n}); a
      harness's words laid over EN; an unknown key, an empty word, a template without {n}, a bad lang refused, the
      message naming the key; the module's own parts are English
  [2] the states: the five of kit.pathweights, each its own icon; every state renders colour, word and icon (chip,
      vchip, legend, card, fold_row) in English, in Chinese and in a harness's own words; an unknown state refused;
      tenths() reads as kit.pathweights.tenths()
  [3] the small parts: the status bar grows by the counts in ORDER, the legend line in the words' separator, ten dots,
      tiles, money in the harness's template, amounts, fitting; every text escaped
  [4] one decision with one copy button (its words in its own attributes), none without a command
  [5] at most three warnings and the rest one line that says where; a limit above three refused
  [6] the story, the card, the row, the folds (data-zone="tech"), expand all
  [7] the node map: one rect per cell with a title each, the proposals, an empty leaf, one link per parent and child,
      a stated node's icon before its label, three lines for 31 cells; two and three columns; bad shapes refused
  [8] the skeleton: doctype, lang, the CSP with default-src 'none', nothing remote, exactly two scripts, the page data
      round-trips with no literal '</' (or <, >, &), one-pass fill (a title, body or data holding a placeholder's name,
      or </script>, stays text), extra_css refused with '</'; the script holds no word and calls no network
  [9] problems(): a whole page built with the style keeps every rule (English and Chinese); each rule tried on a
      broken page first, so the check cannot pass by looking at nothing; zones() finds no command or flag outside
      data-zone="decision"/"tech", and the same command inside them passes
  [10] contrast: each state's text on its fill, the ink and muted text on paper and background and the button's text,
      at least 4.5:1 in the light theme and both dark ones (the system's, guarded by :root:not([data-theme="light"]),
      and the chosen one), the two dark blocks the same
  [11] the phone: no grid track wider than a 320px phone's column, the cards capped by their container, a 16px gutter
"""

import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # ROOT

from kit import pagestyle as ps  # noqa: E402
from kit import pathweights as W  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

EVIL = '</script><b>x"&\'<'
HOLES = "__LANG__ __TITLE__ __CSS__ __BODY__ __DATA__ __SCRIPT__"
ZHS = ps.Style(ps.ZH, lang="zh-CN")
OWN = ps.Style({"state_down": "weaker", "state_promising": "stronger", "money": "${n}", "warnings": "Look out"},
               lang="en-GB")


def message(fn, *a, **kw) -> str:
    """The ValueError's message, or "" when nothing is refused."""
    try:
        fn(*a, **kw)
    except ValueError as err:
        return str(err)
    return ""


# ---- [1] the words ----------------------------------------------------------------------

def test_words() -> None:
    print("[1] the words")
    keys = [k for k, _ in ps.WORDS]
    check("WORDS names each key once, with what it is", len(keys) == len(set(keys)) and all(w for _, w in ps.WORDS))
    for name, ws in (("EN", ps.EN), ("ZH", ps.ZH)):
        check(f"{name} is complete: every key of WORDS, no other", list(ws) == keys,
              (set(keys) ^ set(ws)) or "order")
        check(f"{name}: every word a non-empty string", all(isinstance(v, str) and v.strip() for v in ws.values()))
        check(f"{name}: every template holds its {{n}}", all("{n}" in ws[k] for k in ps.TEMPLATES))
        check(f"{name}: no other word holds {{n}}", not [k for k, v in ws.items() if "{n}" in v and k not in ps.TEMPLATES])
    check("ZH: the words the source page uses", (ps.ZH["state_promising"], ps.ZH["if_fails"], ps.ZH["owner"],
                                                 ps.ZH["copied"], ps.ZH["collapse_all"])
          == ("有希望", "如果不行", "给负责人看：怎么算的", "已复制", "全部收起"))
    check("ZH's more line names the owner's fold, where the rest are", "给负责人看" in ps.ZH["more"]
          and ps.ZH["owner"].startswith("给负责人看"))
    check("EN's more line names the owner's fold too", "For the owner" in ps.EN["more"]
          and ps.EN["owner"].startswith("For the owner"))
    check("neither set names a currency: money is the harness's", ps.EN["money"] == ps.ZH["money"] == "{n}")
    check("a harness's words are laid over EN", OWN.words["state_down"] == "weaker" and OWN.words["copy"] == "Copy"
          and OWN.lang == "en-GB")
    check("the default style is English, lang en", ps.DEFAULT.words == ps.EN and ps.DEFAULT.lang == "en"
          and ps.Style().words == ps.EN)
    check("wordset() of nothing is EN, a copy", ps.wordset() == ps.EN and ps.wordset() is not ps.EN)
    for over, key in (({"state_maybe": "x"}, "state_maybe"), ({"copy": ""}, "copy"), ({"copy": "  "}, "copy"),
                      ({"copy": 3}, "copy"), ({"more": "the rest below"}, "more"), ({"dots": "about half"}, "dots"),
                      ({"money": "¥"}, "money")):
        m = message(ps.Style, over)
        check(f"refused, naming {key}: {over!r}", key in m, m)
    check("words that are not a mapping are refused", "mapping" in message(ps.Style, [("copy", "x")]))
    for lang in ("", "zh_CN", "e", 'en" onload="x', 3):
        check(f"a bad lang is refused: {lang!r}", "lang" in message(ps.Style, None, lang))
    check("a good lang is taken", ps.Style(lang="zh-Hans-CN").lang == "zh-Hans-CN")
    doc = (Path(__file__).resolve().parents[2] / "docs" / "page-style.md").read_text(encoding="utf-8")
    table = doc.split("## Words", 1)[1].split("\n## ", 1)[0]
    missing = [f"{k}={v!r}" for ws in (ps.EN, ps.ZH) for k, v in ws.items() if v not in table]
    missing += [k for k in keys if not k.startswith("state_") and f"`{k}`" not in table]
    check("docs/page-style.md's word table holds every key and every EN and ZH word as they are", not missing, missing)
    check("the module's parts are the English style's", ps.chip("down") == ps.DEFAULT.chip("down")
          and ps.page is not None and ps.warnings(["a"]).startswith('<section class="warn"><h2>Watch</h2>'))


# ---- [2] the states ----------------------------------------------------------------------

def test_states() -> None:
    print("\n[2] the states: colour, word and icon")
    check("the five states of kit.pathweights", ps.STATES == W.STATES, (ps.STATES, W.STATES))
    check("each state its own icon", set(ps.ICON) == set(ps.STATES) and len(set(ps.ICON.values())) == 5)
    check("ORDER holds each state once", sorted(ps.ORDER) == sorted(ps.STATES) and len(ps.ORDER) == 5)
    for st, style in (("EN", ps.DEFAULT), ("ZH", ZHS), ("own", OWN)):
        for s in ps.STATES:
            w, i = style.word(s), ps.ICON[s]
            c = style.chip(s)
            check(f"{st} chip {s}: colour class, icon, word",
                  c == f'<span class="chip s-{s}"><b aria-hidden="true">{i}</b>{ps.e(w)}</span>', c)
            v = style.vchip(s, "Value 1", "2 made")
            check(f"{st} vchip {s}: icon, label, word", v.startswith(f'<span class="vchip s-{s}" title="{ps.e(w)}">'
                                                                    f'<b aria-hidden="true">{i}</b>Value 1<small>')
                  and v.endswith(f"2 made · {ps.e(w)}</small></span>"), v)
            card = style.card(s, anchor=f"p-{s}")
            row = style.fold_row(s, anchor=f"r-{s}", title="Row 1")
            check(f"{st} card and row {s}: the chip", style.chip(s) in card and style.chip(s) in row)
        lg = style.legend({"down": 2})
        check(f"{st} legend: every state's chip, 0 too", all(style.chip(s) in lg for s in ps.STATES)
              and lg.count("<small>0</small>") == 4 and "<small>2</small>" in lg)
    check("the chip of a state a harness renamed says its word", "weaker" in OWN.chip("down")
          and "down" not in OWN.chip("down").split("</b>")[1])
    for fn in (lambda: ps.chip("maybe"), lambda: ps.word("maybe"), lambda: ps.vchip("maybe", "x"),
               lambda: ps.card("maybe", anchor="a"), lambda: ps.fold_row("maybe", anchor="a", title="t")):
        check("an unknown state is refused, naming it", "maybe" in message(fn))
    grid = [i / 1000 for i in range(1001)] + [0.79, 0.21, 0.3, 0.7, 0.8, 0.2]
    check("tenths() reads as kit.pathweights.tenths()", all(ps.tenths(p) == W.tenths(p) for p in grid),
          [p for p in grid if ps.tenths(p) != W.tenths(p)][:5])
    check("tenths(): 0.79 reads 7 and 0.21 reads 3", (ps.tenths(0.79), ps.tenths(0.21), ps.tenths(0.8),
                                                       ps.tenths(0.2)) == (7, 3, 8, 2))


# ---- [3] the small parts -----------------------------------------------------------------

def test_small_parts() -> None:
    print("\n[3] the small parts")
    counts = {"untested": 30, "testing": 6, "promising": 2, "down": 1, "closed": 0}
    b = ps.bar(counts)
    grows = [(m.group(1), int(m.group(2))) for m in re.finditer(r'<i class="s-(\w+)" style="flex-grow:(\d+)"', b)]
    check("the status bar grows by the counts, in ORDER, a state with none left out",
          grows == [("promising", 2), ("testing", 6), ("down", 1), ("untested", 30)], grows)
    check("the bar is an image whose label is the legend line", f'aria-label="{ps.legend_text(counts)}"' in b
          and 'role="img"' in b and 'class="bar"' in b and 'class="bar big"' in ps.bar(counts, big=True))
    check("a bar of nothing has no segment", "<i " not in ps.bar({s: 0 for s in ps.STATES}))
    check("the legend line in English", ps.legend_text(counts) == "promising 2, testing 6, down 1, untested 30",
          ps.legend_text(counts))
    check("the legend line in Chinese, its own separator", ZHS.legend_text(counts) == "有希望 2，在测 6，降权 1，未测 30",
          ZHS.legend_text(counts))
    for p, n in ((0.0, 0), (0.21, 3), (0.5, 5), (0.79, 7), (0.8, 8), (0.97, 9), (1.0, 10)):
        d = ps.dots(p)
        line = f"about {n} times in 10 better than the account"
        check(f"ten dots for {p}: {n} filled, and the line", d.count("<i ") == 10 and d.count('<i class="on">') == n
              and f"<span>{line}</span>" in d and f'aria-label="{line}"' in d, d)
    check("ten dots in Chinese", "<span>10 次里约 7 次比账户平均好</span>" in ZHS.dots(0.79))
    check("no p, no dots", ps.dots(None) == "")
    check("a caller's own dots line", "4 of 10 would do better" in ps.dots(0.4, "{n} of 10 would do better"))
    t = ps.tiles([("40", "paths planned", "rows x templates"), (EVIL, EVIL, EVIL)])
    check("tiles, every text escaped", t.count('<div class="tile">') == 2 and "<b>40</b>" in t and "<b>x" not in t
          and t.count("&lt;/script&gt;") == 3, t)
    check("money: whole, separated, — for none", (ps.money(None), ps.money(16800), ps.money(922.6), ps.money(0))
          == ("—", "16,800", "923", "0"))
    check("money in the harness's template", (ZHS.money(16800), OWN.money(16800), ps.money(1234.5, "{n} €"),
                                               ps.Style({"money": "¥{n}"}).money(5))
          == ("16,800", "$16,800", "1,234 €", "¥5"))
    check("money: a minus before the currency, none for an amount that rounds to 0",
          (OWN.money(-1500), OWN.money(-0.4)) == ("-$1,500", "$0"))
    check("amounts: fractions as they are, a small one never 0",
          [ps.amount(x) for x in (None, 3, 3.0, 2.4, 0.6, 68.7, 12.25, 0.01, 0)]
          == ["—", "3", "3", "2.4", "0.6", "68.7", "12.2", "<0.1", "0"])
    check("fit(): short text as it is", ps.fit("short", 100, 12) == "short")
    cut = ps.fit("组合一·组合二·组合三·组合四", 100, 13)
    check("fit(): CJK cut to the width, with …", cut.endswith("…") and ps.text_width(cut, 13) <= 100, cut)
    cut = ps.fit("abc" * 20, 40, 12)
    check("fit(): Latin cut to the width, with …", cut.endswith("…") and ps.text_width(cut, 12) <= 40, cut)
    check("e(): None is empty, quotes escaped", ps.e(None) == "" and ps.e('"<&>\'') == "&quot;&lt;&amp;&gt;&#x27;")
    c = ps.chip("down", " · proposed" + EVIL, proposal=True)
    check("a chip's extra text escaped, a proposal dashed", 'class="chip s-down proposal"' in c and "<b>x" not in c
          and "&lt;/script&gt;&lt;b&gt;x" in c, c)


# ---- [4] the decision ------------------------------------------------------------------

def test_decision() -> None:
    print("\n[4] one decision, one copy button")
    d = ps.decision("Decide: close this path?", "<p>Body</p>", 'demo close --path 0a1b2c3d4e --reason "x<y"',
                    "Paste it in a terminal", cmd_id="c9")
    check("the decision zone, its title and body first",
          d.startswith('<section class="decide" data-zone="decision"><h2>Decide: close this path?</h2><p>Body</p>'), d)
    check("one copy button for the one command", d.count("<button") == 1 and 'data-copy="c9"' in d
          and '<code id="c9">' in d)
    check("the command escaped, the hint under it", "--reason &quot;x&lt;y&quot;" in d
          and '<p class="hint">Paste it in a terminal</p>' in d)
    check("the button's words: copy, copied, selected", '>Copy</button>' in d and 'data-done="Copied"' in d
          and 'data-select="Selected: press ⌘C or Ctrl+C"' in d)
    z = ZHS.decision("要你定", "", "demo close", cmd_id="c1")
    check("the button's words in Chinese", ">复制</button>" in z and 'data-done="已复制"' in z
          and 'data-select="已选中，按 ⌘C"' in z)
    bare = ps.decision("Decide: make the next batch?", "<p>Body</p>")
    check("no command: no button, no code, no hint", 'data-zone="decision"' in bare and "<button" not in bare
          and "<code" not in bare and "hint" not in bare)
    check("the title escaped", "&lt;b&gt;" in ps.decision("<b>", ""))
    check("a caller's button words escaped", "<b>x" not in ps.Style({"copy": EVIL}).decision("t", "", "c"))


# ---- [5] the warnings ------------------------------------------------------------------

def test_warnings() -> None:
    print("\n[5] at most three warnings")
    check("nothing to warn: no box", ps.warnings([]) == "")
    two = ps.warnings(["a", "b"])
    check("two: both, no more line", two.count("<li>") == 2 and "more" not in two
          and two.startswith('<section class="warn"><h2>Watch</h2>'))
    three = ps.warnings(["a", "b", "c"])
    check("three: all three, no more line", three.count("<li>") == 3 and 'class="more"' not in three)
    five = ps.warnings([f"w{i}" for i in range(5)])
    check("five: three shown, the rest one line that says where",
          five.count("<li>") == 3 and "w3" not in five
          and '<li class="more">2 more, under “For the owner” at the foot of the page.</li>' in five, five)
    zh = ZHS.warnings([f"w{i}" for i in range(4)])
    check("in Chinese: 留意, and the more line names 给负责人看",
          "<h2>留意</h2>" in zh and '<li class="more">另有 1 条，在页尾“给负责人看”里。</li>' in zh, zh)
    one = ps.warnings(["a", "b", "c"], limit=1)
    check("a lower limit: one shown, 2 more", one.count("<li>") == 1 and "2 more" in one)
    own = ps.warnings(["a", "b", "c", "d"], more="{n} more" + EVIL)
    check("a caller's own more line, escaped", '<li class="more">1 more&lt;/script&gt;&lt;b&gt;x' in own
          and "<b>x" not in own, own)
    for bad in (4, 0, -1, True, 2.0, "3"):
        check(f"a limit of {bad!r} is refused", "limit" in message(ps.warnings, ["a"], limit=bad))
    check("the box's title is the harness's", "<h2>Look out</h2>" in OWN.warnings(["a"]))


# ---- [6] story, card, row, folds -------------------------------------------------------------

def test_cards() -> None:
    print("\n[6] the story, the card, the row, the folds")
    check("no story for neither", ps.story(None, None) == "" and ps.story("", "") == "")
    s = ps.story("Change the ending" + EVIL, "Make less of it")
    check("the story: if it works, if it does not, escaped", '<li class="ok"><b>If it works</b>' in s
          and '<li class="bad"><b>If it does not</b>' in s and "<b>x" not in s, s)
    check("one line when only one is given", "If it does not" not in ps.story("x", None)
          and "If it works" not in ps.story(None, "y"))
    z = ZHS.story("a", "b")
    check("the story in Chinese", "<b>如果行</b>" in z and "<b>如果不行</b>" in z)
    c = ps.card("promising", anchor="p-0a1b2c3d4e", head='<span class="why">likely better</span>',
                combo="<span>Opening A</span>", nums=["2 made", EVIL], p=0.83, works="Change the ending",
                fails="Make less of it", note='<p class="note">n</p>', tech="id <code>0a1b2c3d4e</code>")
    check("the card: its anchor, chip and head", c.startswith('<article class="card s-promising" id="p-0a1b2c3d4e">'
                                                             '<header>' + ps.chip("promising")), c)
    check("the card: what it is made of, numbers escaped, eight dots", '<div class="combo"><span>Opening A</span></div>'
          in c and "<b>x" not in c and c.count('<i class="on">') == 8)
    check("the card: the story and its codes behind Details", "If it works" in c and "If it does not" in c
          and '<details class="tech" data-zone="tech"><summary>Details</summary>' in c and c.endswith("</article>"))
    check("a card's fold in Chinese is 详情", "<summary>详情</summary>" in ZHS.card("down", anchor="a", tech="x"))
    bare = ps.card("closed", anchor="p-x")
    check("a bare card: no dots, no story, no fold, no numbers", "dots" not in bare and "story" not in bare
          and "<details" not in bare and "nums" not in bare)
    prop = ps.card("down", anchor="p-y", proposal=True, proposal_word=" · proposed")
    check("a proposal's card and chip", 'class="card s-down proposal"' in prop
          and ps.chip("down", " · proposed", True) in prop)
    r = ps.fold_row("testing", anchor="r-N1", title="Row 1 " + EVIL, sub="Group A", right="<b>3</b>", body="<p>b</p>")
    check("the row: folded, its chip, title escaped, right and body", r.startswith('<details class="row" id="r-N1">'
                                                                                 '<summary>' + ps.chip("testing"))
          and "<b>x" not in r and '<span class="rn"><b>3</b></span>' in r and '<div class="rbody"><p>b</p></div>' in r)
    check("a row opened", ps.fold_row("testing", anchor="r-N2", title="t", opened=True)
          .startswith('<details class="row" open id="r-N2">'))
    d = ps.details("Details", "<p>x</p>")
    check("a fold is data-zone tech", d == '<details class="tech" data-zone="tech"><summary>Details</summary><p>x</p>'
                                         '</details>', d)
    o = ps.owner("<p>how</p>")
    check("the owner's fold: tech, its summary, its inside", 'class="owner" data-zone="tech"' in o
          and "<summary>For the owner: how it was worked out</summary>" in o and '<div class="ow"><p>how</p></div>' in o)
    check("the owner's fold in Chinese, and a caller's own summary", "<summary>给负责人看：怎么算的</summary>"
          in ZHS.owner("") and "<summary>Notes</summary>" in ps.owner("", "Notes"))
    x = ps.expand_all()
    check("expand all: its two words in its own attributes", x == '<button type="button" data-expand="rows" '
          'data-more="Expand all" data-less="Collapse all">Expand all</button>', x)
    check("expand all in Chinese", 'data-more="全部展开" data-less="全部收起">全部展开</button>' in ZHS.expand_all())


# ---- [7] the node map --------------------------------------------------------------------

def _cells(n, state="untested"):
    return [{"state": state, "href": f"#p-{i:010x}", "title": f"Cell {i}" + (EVIL if i == 0 else ""),
             "proposal": i == 1} for i in range(n)]


def test_node_map() -> None:
    print("\n[7] the node map")
    tree = [{"label": "Group A", "sub": "G1", "state": None, "cls": "held", "children": [
                {"label": "Row 1 " + EVIL, "sub": "need", "state": "testing", "href": "#r-N1", "children": [
                    {"label": "Template 1", "sub": "16 paths", "state": "testing", "href": "#rf-1", "cells": _cells(17),
                     "caption": "untested 17"},
                    {"label": "Template 2", "sub": "2 paths", "state": "promising", "href": "#rf-2",
                     "cells": _cells(2, "promising"), "caption": "promising 2"}]},
                {"label": "Row 2", "sub": "need", "state": "untested", "href": "#r-N2", "cls": "blocked", "children": [],
                 "empty": "no template yet"}]},
            {"label": "Group B", "sub": "G2", "state": None, "children": [
                {"label": "Row 3", "sub": "", "state": "down", "href": "#r-N3", "children": [
                    {"label": "Template 3", "sub": "1 path", "state": "down", "href": "#rf-3",
                     "cells": _cells(1, "down"), "caption": "down 1"}]}]},
            {"label": "Group C", "sub": "G3", "state": None, "children": [], "empty": "no row for this group yet"}]
    svg = ps.node_map(tree, ("Group", "Row", "Template", "One cell = one path"), label="The plan's map")
    squares = re.findall(r'<rect class="sq s-(\w+)( proposal)?"[^>]*><title>([^<]*)</title></rect>', svg)
    check("one rect per cell, a title each", len(squares) == 20 and svg.count('class="sq ') == 20
          and svg.count("<title>") == 20, len(squares))
    check("each cell a link to its item", svg.count('<a href="#p-') == 20)
    check("a proposal's cell is marked", sum(1 for s in squares if s[1]) == 2)
    check("every text escaped", "<b>x" not in svg and "&lt;/script&gt;&lt;b&gt;x" in svg)
    empties = re.findall(r'<g class="leaf empty">.*?<text[^>]*>([^<]*)</text></g>', svg)
    check("a node with nothing under it draws why, in a dashed box", empties == ["no template yet",
                                                                                 "no row for this group yet"], empties)
    links = re.search(r'<g class="links">(.*?)</g>', svg).group(1)
    check("one link per parent and child (an empty leaf too)", links.count("<path ") == 8, links.count("<path "))
    check("a node's extra classes", svg.count('class="node plain held"') == 1 and 'class="node s-untested blocked"' in svg)
    check("the map scrolls in its box, an image with its label", svg.startswith('<div class="scroll"><svg class="map"')
          and 'aria-label="The plan&#x27;s map"' in svg and svg.count('class="col"') == 4)
    labels = re.findall(r'<g class="node ([^"]*)"><rect[^>]*/><text class="t1"[^>]*>([^<]*)</text>', svg)
    ok = all(text.startswith(f"{ps.ICON[st]} ") if (st := next((c[2:] for c in cls.split() if c.startswith("s-")), None))
             else not text.startswith(tuple(ps.ICON.values())) for cls, text in labels)
    check("a node with a state carries its icon before its label, a neutral one none", len(labels) == 9 and ok, labels)
    big = ps.node_map([{"label": "a", "children": [{"label": "b", "children": [
        {"label": "c", "cells": _cells(31), "caption": ""}]}]}], ("1", "2", "3", "4"))
    ys = sorted({float(y) for y in re.findall(r'class="sq s-untested[^"]*" x="[\d.]+" y="([\d.]+)"', big)})
    check("31 cells, 15 a line: three lines", len(ys) == 3, ys)
    two = ps.node_map([{"label": "Template 1", "state": "promising", "cells": _cells(3, "promising")}], ("Template", "Paths"))
    check("two columns: the nodes and their waffle", two.count('class="sq ') == 3 and two.count('class="col"') == 2
          and "<path " not in two)
    three = ps.node_map([{"label": "Row 1", "children": []}, {"label": "Row 2", "children": [
        {"label": "Template 1", "cells": _cells(2)}]}], ("Row", "Template", "Paths"), (180, 180, 200))
    check("three columns, given widths", three.count('class="sq ') == 2 and 'width="600"' in three, three[:120])
    check("one column is refused", "two columns" in message(ps.node_map, [], ("x",)))
    check("widths that do not match the columns are refused", "widths" in message(ps.node_map, [], ("a", "b"), (1, 2, 3)))
    check("a cell of an unknown state is refused", "maybe" in message(
        ps.node_map, [{"label": "x", "cells": [{"state": "maybe"}]}], ("a", "b")))


# ---- [8] the skeleton ------------------------------------------------------------------------

def data_of(page: str) -> tuple[str, object]:
    i = page.index('id="page-data">') + len('id="page-data">')
    raw = page[i:page.index("</script>", i)]
    return raw, json.loads(raw)


def test_skeleton() -> None:
    print("\n[8] the document")
    page = ps.page("The plan's map · " + EVIL, "<section>Body</section>", {"project": EVIL, "n": 1, "zh": "模板"})
    check("doctype, then lang en", page.startswith('<!doctype html>\n<html lang="en">'))
    check("lang zh-CN for the Chinese style", ZHS.page("t", "").startswith('<!doctype html>\n<html lang="zh-CN">'))
    check("the CSP meta", f'<meta http-equiv="Content-Security-Policy" content="{ps.CSP}">' in page)
    check("the CSP allows no network: default-src 'none', no connect-src, no form, no base",
          ps.CSP.startswith("default-src 'none';") and "connect-src" not in ps.CSP and "form-action 'none'" in ps.CSP
          and "base-uri 'none'" in ps.CSP and "http" not in ps.CSP and "*" not in ps.CSP)
    check("exactly two script tags: the page data and the style's", page.count("<script") == 2
          and page.count("</script>") == 2, page.count("</script>"))
    for bad in ("<form", "<link", "<iframe", 'src="', "http://", "https://", "@import"):
        check(f"nothing remote: no {bad}", bad not in page)
    check("the title escaped", "<b>x" not in page and "<title>The plan&#x27;s map · &lt;/script&gt;" in page)
    check("the body inside main", "<main><section>Body</section></main>" in page)
    raw, data = data_of(page)
    check("the page data round-trips", data == {"project": EVIL, "n": 1, "zh": "模板"}, data)
    check("the page data has no literal </, <, > or &", "</" not in raw and not set("<>&") & set(raw), raw)
    check("no data: {}", ps.page("t", "", None).count('id="page-data">{}</script>') == 1)
    check("light and dark tokens", "@media (prefers-color-scheme: dark){:root:not([data-theme=\"light\"])" in page
          and ':root[data-theme="dark"]{' in page)
    hole = ps.page("t " + HOLES, f"<section>{HOLES}</section>", {"name": HOLES})
    check("one pass: a placeholder's name stays text (scripts, styles, main)", hole.count("<script") == 2
          and hole.count("</script>") == 2 and hole.count("<style") == 1 and hole.count("<main>") == 1)
    check("one pass: the title, body and data hold the names as they were", f"<title>t {HOLES}</title>" in hole
          and f"<main><section>{HOLES}</section></main>" in hole and data_of(hole)[1] == {"name": HOLES})
    check("one pass: the style and the script once each", hole.count(ps.SCRIPT) == 1 and ps.CSS in hole
          and '<html lang="en">' in hole)
    check("extra_css after the style's", ps.page("t", "", extra_css=":root{--f-body:serif}")
          .count(ps.CSS + ":root{--f-body:serif}") == 1)
    check("extra_css that closes the style is refused", "extra_css" in message(ps.page, "t", "", extra_css="</style>"))
    check("the script holds no word: ASCII only", all(ord(ch) < 128 for ch in ps.SCRIPT))
    check("the script reads each button's words from its attributes", all(
        f"'{a}'" in ps.SCRIPT for a in ("data-done", "data-select", "data-more", "data-less")))
    check("the script: copy buttons, expand all, a link opens its fold, print opens every fold",
          "button[data-copy]" in ps.SCRIPT and "button[data-expand]" in ps.SCRIPT and 'a[href^="#"]' in ps.SCRIPT
          and "beforeprint" in ps.SCRIPT and "p.open=true" in ps.SCRIPT)
    quoted = set(re.findall(r"'([^']*)'", ps.SCRIPT))
    words = {q for q in quoted if re.search(r"[A-Za-z]{2,}\s+[A-Za-z]", q)}
    check("the script quotes no visible text", not words, words)
    for net in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "import(", ".src", "http",
                "location", "eval(", "innerHTML"):
        check(f"the script does not call {net}", net not in ps.SCRIPT)


# ---- [9] problems() and the zones --------------------------------------------------------------

def demo_page(style: ps.Style, *, command: str = "demo close --path 0a1b2c3d4e --shown 3f9a2c1b", warns: int = 2,
              body_extra: str = "", data=None) -> str:
    """A whole page as a harness writes one: tiles, the bar, the decision, warnings, the map, rows with cards, the
    owner's fold; ids and the command only in the decision and the folds."""
    counts = {"untested": 3, "testing": 2, "promising": 1, "down": 1, "closed": 1}
    cells = [{"state": s, "href": f"#p-{s}", "title": f"{style.word(s)}: Value {i}"}
             for i, s in enumerate(("promising", "testing", "testing", "down", "closed", "untested", "untested",
                                    "untested"))]
    tree = [{"label": "Group A", "sub": "G1", "state": None, "children": [
        {"label": "Row 1", "sub": "need", "state": "testing", "href": "#r-1", "children": [
            {"label": "Template 1", "sub": "8 paths", "state": "testing", "href": "#r-1", "cells": cells,
             "caption": style.legend_text(counts)}]}]}]
    cards = "".join(style.card(s, anchor=f"p-{s}", head="<span>why</span>", combo="<span>Value</span>",
                               nums=["2 made", style.money(1200)], p=0.6, works="Change one value",
                               fails="Make less of it", tech=f"id <code>{i}a2b3c4d5e</code>")
                    for i, s in enumerate(ps.STATES))
    body = (ps.tiles([("8", "paths planned", "rows x templates"), (style.money(4800), "settled spend", "3 orders")])
            + f'<div class="space">{style.bar(counts, big=True)}{style.legend(counts)}</div>'
            + style.decision("Decide: close this path?", "<p>Row 1 · Value 3</p>", command, "Paste it in a terminal")
            + style.warnings([f"Warning {i}" for i in range(warns)])
            + '<section class="mapbox"><h2>The map</h2>' + ps.node_map(tree, ("Group", "Row", "Template", "Paths"))
            + "</section>"
            + f'<section class="rows"><div class="rowhead"><h2>Row by row</h2>{style.expand_all()}</div>'
            + style.fold_row("testing", anchor="r-1", title="Row 1", sub="Group A", right=style.bar(counts),
                             body=f'<div class="cards">{cards}</div>') + "</section>"
            + style.owner("<p>How it is worked out: <code>min_expected_conv</code> and <code>--flag</code>.</p>")
            + body_extra)
    return style.page("The plan's map · DEMO", body, data if data is not None else {"project": "DEMO", "n": 8})


def test_problems() -> None:
    print("\n[9] problems(): every rule, each tried on a broken page")
    for name, style in (("English", ps.DEFAULT), ("Chinese", ZHS), ("a harness's own words", OWN)):
        page = demo_page(style)
        got = style.problems(page, commands=[r"\bdemo\b"])
        check(f"a whole {name} page keeps every rule", got == [], got)
        check(f"... and the module's problems() agrees", ps.problems(page, commands=[r"\bdemo\b"]) == [])
    good = demo_page(ps.DEFAULT)
    z = ps.zones(good)
    check("zones(): one decision, the folds, the rest", z["counts"]["decision"] == 1 and z["counts"]["tech"] == 6
          and z["copies"] == ["decision"], (z["counts"], z["copies"]))
    check("zones(): the command and its flags in the decision, the codes in the folds",
          "demo close --path 0a1b2c3d4e" in z["decision"] and "min_expected_conv" in z["tech"]
          and "--flag" in z["tech"] and "1a2b3c4d5e" in z["tech"])
    check("zones(): the rest holds no command, flag, id or code", "demo" not in z["rest"].replace("DEMO", "")
          and "--" not in z["rest"] and "0a1b2c3d4e" not in z["rest"] and "_" not in z["rest"])
    check("zones(): a cell's title is visible text, a script's is not", "promising: Value 0" in z["rest"]
          and "addEventListener" not in z["rest"] and "--bg" not in z["rest"])

    def broken(label: str, page: str, want: str, **kw) -> None:
        got = ps.problems(page, **kw)
        check(f"seen: {label}", any(want in g for g in got), got)

    broken("no doctype", good.replace("<!doctype html>\n", ""), "doctype")
    broken("no lang", good.replace('<html lang="en">', "<html>"), "no lang")
    check("seen: a lang that is not the style's", any("lang is" in g for g in ZHS.problems(good)), ZHS.problems(good))
    broken("a CSP that allows the network", good.replace("default-src 'none'", "default-src *"), "CSP")
    broken("a stylesheet link", good.replace("</head>", '<link rel="stylesheet" href="x.css"></head>'), "<link")
    broken("a form", demo_page(ps.DEFAULT, body_extra='<form action="x"></form>'), "<form")
    broken("a remote image", demo_page(ps.DEFAULT, body_extra='<img src="https://example.com/x.png">'), "remote")
    broken("a protocol-relative image", demo_page(ps.DEFAULT, body_extra="<img src='//example.com/x.png'>"), "remote")
    broken("a remote url() in a style", demo_page(ps.DEFAULT, body_extra='<p style="background:url(http://example.com/y)">'),
           "remote")
    check("an inline data: image is not remote", ps.problems(demo_page(
        ps.DEFAULT, body_extra='<img alt="" src="data:image/png;base64,AAAA">'), commands=[r"\bdemo\b"]) == [])
    broken("a third script", good.replace("</body>", "<script>1</script></body>"), "3 scripts")
    broken("the page data holding <", good.replace('"project": "DEMO"', '"project": "<b>"'), "page data holds")
    broken("the page data not JSON", good.replace('"project": "DEMO"', "project"), "not JSON")
    broken("no page data", good.replace('type="application/json" id="page-data"', 'type="application/json"'),
           "no page data")
    broken("two decision zones", demo_page(ps.DEFAULT, body_extra=ps.decision("Also decide", "")), "2 decision zones")
    broken("no decision zone", good.replace('data-zone="decision"', ""), "0 decision zones")
    broken("two copy buttons", demo_page(ps.DEFAULT, body_extra=ps.details("x", ps.decision("y", "", "z")
                                                                           .replace('data-zone="decision"', ""))),
           "2 copy buttons")
    broken("a copy button outside the decision", good.replace('<section class="decide" data-zone="decision">',
                                                              '<section class="decide">', 1)
           .replace('<section class="warn">', '<section class="warn" data-zone="decision">', 1), "outside the decision")
    broken("a zone of its own", demo_page(ps.DEFAULT, body_extra='<p data-zone="free">x</p>'), "other than decision")
    broken("a flag in the rest", demo_page(ps.DEFAULT, body_extra="<p>run it with --dry-run</p>"), "a flag")
    broken("a hash in the rest", demo_page(ps.DEFAULT, body_extra="<p>results 3f9a2c1b77</p>"), "a hash")
    broken("a code in the rest", demo_page(ps.DEFAULT, body_extra="<p>because not_made</p>"), "a code")
    broken("the harness's command in the rest", demo_page(ps.DEFAULT, body_extra="<p>demo close it</p>"),
           "a command", commands=[r"\bdemo\b"])
    check("a word with digits, a date and a number are not a hash", ps.problems(demo_page(
        ps.DEFAULT, body_extra="<p>2026-10-13, 16,800 and 12345678 and Value 3a</p>"), commands=[r"\bdemo\b"]) == [])
    broken("four warnings shown", demo_page(ps.DEFAULT, warns=2).replace("<li>Warning 1</li>",
                                                                          "<li>Warning 1</li><li>2</li><li>3</li>"),
           "4 warnings shown")
    check("four warnings given: three shown and the more line keep the rule",
          ps.problems(demo_page(ps.DEFAULT, warns=6), commands=[r"\bdemo\b"]) == [])
    broken("a chip without its icon", good.replace(f'<b aria-hidden="true">{ps.ICON["down"]}</b>', "", 1), "without its icon")
    broken("a chip of an unknown state", demo_page(ps.DEFAULT, body_extra='<span class="chip s-maybe">x</span>'),
           "unknown state")
    own = demo_page(OWN).replace('</b>weaker</span>', '</b>down</span>', 1)
    check("seen: a chip whose word is not the style's (given the style)",
          any("without its word" in g for g in OWN.problems(own, commands=[r"\bdemo\b"])), OWN.problems(own))
    broken("a map node without its icon", good.replace(f">{ps.ICON['testing']} Row 1<", ">Row 1<"), "map node")
    broken("a cell without a title", re.sub(r'(<rect class="sq [^>]*>)<title>[^<]*</title>', r"\1", good, count=1),
           "without a title")
    broken("a grid track wider than a phone", ps.page("t", ps.decision("d", ""), extra_css=".x{grid-template-columns:"
                                                                                           "repeat(auto-fit,minmax(360px,1fr))}"),
           "wider than")
    check("problems() names nothing on a page that keeps the rules, given the harness's command",
          ps.problems(good, commands=[re.compile(r"\bdemo\b")]) == [])


# ---- [10] contrast ------------------------------------------------------------------------------

def tokens(css: str) -> dict[str, dict[str, str]]:
    """{selector: {token: #hex}} of each :root block of the stylesheet."""
    return {sel.strip(): dict(re.findall(r"--([\w-]+):(#[0-9A-Fa-f]{6})", body))
            for sel, body in re.findall(r"(:root[^{]*)\{([^}]*)\}", css)}


def contrast(a: str, b: str) -> float:
    def lum(h: str) -> float:
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


TEXT_ON = {"untested": ("ink", "u-f"), "testing": ("ink", "t-f"), "promising": ("p-t", "p-f"), "down": ("d-t", "d-f"),
           "closed": ("c-t", "c-f")}


def test_contrast() -> None:
    print("\n[10] contrast, light and dark")
    check("the contrast formula: black on white is 21, white on white 1",
          round(contrast("#000000", "#FFFFFF"), 1) == 21.0 and contrast("#FFFFFF", "#FFFFFF") == 1.0)
    blocks = tokens(ps.CSS)
    sels = {":root", ':root:not([data-theme="light"])', ':root[data-theme="dark"]'}
    check("three :root blocks: light, the system's dark, the chosen dark", set(blocks) == sels, set(blocks))
    check("the system's dark sits inside prefers-color-scheme: dark",
          '@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){' in ps.CSS)
    check("the two dark blocks are the same", blocks.get(':root:not([data-theme="light"])')
          == blocks.get(':root[data-theme="dark"]'))
    check("every block sets every colour token", len({frozenset(t) for t in blocks.values()}) == 1)
    check("the state text tokens are the ones the chips, cards and nodes use",
          all(f".s-{s}.chip{{" in ps.CSS and f"color:var(--{TEXT_ON[s][0]})" in
              re.search(rf"\.s-{s}\.chip\{{([^}}]*)\}}", ps.CSS).group(1) for s in ps.STATES)
          and "svg .node.s-closed text{fill:var(--c-t)}" in ps.CSS and "svg .node.s-down text{fill:var(--d-t)}" in ps.CSS
          and "svg .node.s-promising text{fill:var(--p-t)}" in ps.CSS)
    for sel, t in blocks.items():
        for s, (fg, bg) in TEXT_ON.items():
            r = contrast(t[fg], t[bg])
            check(f"{sel} {s}: its text on its fill {r:.1f}:1 >= 4.5", r >= 4.5, (t[fg], t[bg]))
        for fg, bg in (("ink", "paper"), ("ink", "bg"), ("muted", "paper"), ("muted", "bg"), ("paper", "accent"),
                       ("accent", "paper")):
            r = contrast(t[fg], t[bg])
            check(f"{sel} {fg} on {bg}: {r:.1f}:1 >= 4.5", r >= 4.5, (t[fg], t[bg]))


# ---- [11] the phone ------------------------------------------------------------------------------

def test_phone() -> None:
    print("\n[11] a 320px phone")
    fixed = [float(x) for x in re.findall(r"minmax\((\d+(?:\.\d+)?)px", ps.CSS)]
    check("every fixed grid track fits a 320px phone's column (320 less two 16px gutters)",
          fixed and all(x <= ps.PHONE - 2 * ps.GUTTER for x in fixed), re.findall(r"minmax\([^)]*\)", ps.CSS))
    check("the cards' track is capped by its container",
          ".cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr))" in ps.CSS)
    check("a 16px side gutter", "padding-inline:16px" in ps.CSS and ps.GUTTER == 16)
    widths = [int(x) for x in re.findall(r"grid-template-columns:(\d+)px", ps.CSS)]
    check("no column fixed wider than a phone", all(w <= ps.PHONE - 2 * ps.GUTTER for w in widths), widths)
    check("the map scrolls inside its box, not the page", ".scroll{overflow-x:auto" in ps.CSS)
    check("on a phone a row's counts go under its title", "@media (max-width:640px){details.row>summary"
          "{grid-template-columns:auto 1fr}" in ps.CSS)


def main() -> int:
    test_words()
    test_states()
    test_small_parts()
    test_decision()
    test_warnings()
    test_cards()
    test_node_map()
    test_skeleton()
    test_problems()
    test_contrast()
    test_phone()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
