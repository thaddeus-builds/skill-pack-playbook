#!/usr/bin/env python3
"""kit.pagestyle: one look for the pages that guide making, on SYNTHETIC neutral content only (DEMO names, Group/Row
labels, made-up ids).

  [1] the words: EN and ZH both complete (every key of WORDS, no other, each a word, every template with its {n}); a
      harness's words laid over EN; an unknown key, an empty word, a template without {n}, a more line that does not
      name the owner's fold, a bad lang refused, the message naming the key; the module's own parts are English; a
      Style carries every name the module exports, and docs/page-style.md's parts table names each with its signature
  [2] the states: the five of kit.pathweights, each its own icon; every state renders colour, word and icon (chip,
      vchip, legend, card, fold_row) in English, in Chinese and in a harness's own words; an unknown state refused;
      tenths() reads as kit.pathweights.tenths()
  [3] the small parts: the status bar grows by the counts in ORDER, the legend line in the words' separator, ten dots,
      tiles, money in the harness's template, amounts, fitting; every text escaped, a count that is not a whole number
      refused
  [4] one decision with one copy button (its words, its label too, in its own attributes) and its hint (a command
      without one refused), none without a command; the copy button's script, run under node against a stub page,
      comes back to its label after quick clicks and after the fallback
  [5] at most three warnings and the rest one line that says where; a limit above three refused
  [6] the story, the card, the row, the folds (data-zone="tech"), expand all
  [7] the node map: one rect per cell with a title each, the proposals, an empty leaf, one link per parent and child,
      a stated node's icon before its label (kept, with its space, in a narrow box), three lines for 31 cells, as many
      a line as the waffle column holds and no cell past the edge at any width; the default widths the docstring
      says; None texts empty; two and three columns; bad shapes, a cell without a title or a link and a node with
      nothing under it and no why refused
  [8] the skeleton: doctype, lang, the CSP with default-src 'none' and nothing but data: images (no 'self'), nothing
      remote, exactly two scripts, the page data round-trips with no literal '</' (or <, >, &) and NaN or Infinity
      refused, one-pass fill (a title, body or data holding a placeholder's name, or </script>, stays text), extra_css
      refused with '</'; the script holds no word and calls no network
  [9] problems(): a whole page built with the style keeps every rule (English and Chinese); each rule tried on a
      broken page first, so the check cannot pass by looking at nothing; zones() finds no command or flag outside
      data-zone="decision"/"tech", and the same command inside them passes; every line docs/page-style.md says
      problems() reports for a rule is reported by some broken page here, and every rule has a line
  [10] contrast: each state's text on its fill, the ink and muted text on paper and background and the button's text,
      at least 4.5:1 in the light theme and both dark ones (the system's, guarded by :root:not([data-theme="light"]),
      and the chosen one), the two dark blocks the same; nothing in the stylesheet dims a state's text (no opacity
      below 1) and the map's hover filter keeps each state's text at 4.5:1 on its darkened fill
  [11] the phone: no grid wider than a 320px phone's column (its fixed tracks added up), the cards capped by their
      container, a 16px gutter
"""

import html
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # ROOT

from kit import pagestyle as ps  # noqa: E402
from kit import pathweights as W  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

EVIL = '</script><b>x"&\'<'
DOC = (Path(__file__).resolve().parents[2] / "docs" / "page-style.md").read_text(encoding="utf-8")
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


def signature(fn) -> str:
    """fn's parameters as the docs write them: `state, extra="", proposal=False`, a bare * before keyword-only ones."""
    parts, star = [], False
    for p in inspect.signature(fn).parameters.values():
        if p.kind is p.KEYWORD_ONLY and not star:
            parts.append("*")
            star = True
        parts.append(p.name if p.default is p.empty else f"{p.name}={p.default!r}".replace("'", '"'))
    return ", ".join(parts)


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
    m = message(ps.Style, {"owner": "How we got here"})
    check("owner renamed without more is refused, naming both: the more line names the owner's fold",
          "more" in m and "owner" in m and "How we got here" in m, m)
    check("... and a more line that names no fold", "owner" in message(ps.Style, {"more": "{n} more below."}))
    both = ps.Style({"owner": "How we got here: the numbers", "more": "{n} more, under “How we got here”."})
    check("owner and more renamed together are taken", both.words["owner"] == "How we got here: the numbers")
    check("fold_name(): the owner's title up to its colon, either colon",
          (ps.fold_name(ps.EN["owner"]), ps.fold_name(ps.ZH["owner"]), ps.fold_name("Notes"), ps.fold_name(": x"))
          == ("For the owner", "给负责人看", "Notes", ": x"))
    table = DOC.split("## Words", 1)[1].split("\n## ", 1)[0]
    missing = [f"{k}={v!r}" for ws in (ps.EN, ps.ZH) for k, v in ws.items() if v not in table]
    missing += [k for k in keys if not k.startswith("state_") and f"`{k}`" not in table]
    check("docs/page-style.md's word table holds every key and every EN and ZH word as they are", not missing, missing)
    check("the module's parts are the English style's", ps.chip("down") == ps.DEFAULT.chip("down")
          and ps.page is not None and ps.warnings(["a"]).startswith('<section class="warn"><h2>Watch</h2>'))
    names = [n for n in ps.__all__ if n not in ("Style", "DEFAULT")]
    check("a Style carries every name the module exports (but Style and DEFAULT): it stands in for the module",
          not [n for n in names if not hasattr(ps.DEFAULT, n)], [n for n in names if not hasattr(ps.DEFAULT, n)])
    check("... the module's own constants", all(getattr(ps.Style, n) is getattr(ps, n) for n in names if n.isupper()))
    parts = DOC.split("## The parts", 1)[1].split("\n## ", 1)[0]
    named = [(m.group(1), m.group(2)) for ln in parts.splitlines() if ln.startswith("| `")
             for m in re.finditer(r"`([A-Za-z_]+)(?:\(([^`]*)\))?`", ln.split("|")[1])]
    check("docs/page-style.md's parts table names the parts", len(named) > 35, len(named))
    gone = [n for n, _ in named if n != "Style" and not hasattr(ps.DEFAULT, n)]
    check("every name in the parts table is a Style's", not gone, gone)
    wrong = []
    for n, args in named:
        fn = ps.Style if n == "Style" else getattr(ps.DEFAULT, n, None)
        if args is None or fn is None:
            continue
        have = signature(fn)
        if not (have.startswith(args.split("...")[0]) if "..." in args else have == args):
            wrong.append(f"{n}({args}) is {n}({have})")
    check("each signature in the parts table is the Style's", not wrong, wrong)


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
    for bad in ('1" onmouseover="alert(1)', "<img src=x onerror=alert(1)>", "3", 2.5, True, -1):
        got = [message(fn, {"down": bad, "testing": 1}) for fn in (ps.bar, ps.legend, ps.legend_text)]
        check(f"a count of {bad!r} is refused by the bar, the legend and the legend line, naming the state",
              all("down" in m and "whole number" in m for m in got), got)
    check("a count left None is 0", ps.legend({"down": None}).count("<small>0</small>") == 5
          and "<i " not in ps.bar({"down": None}) and ps.legend_text({"down": None, "testing": 2}) == "testing 2")
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

# the copy button's script under node: a stub page with one button (its attributes as decision() writes them), a
# clipboard that copies, refuses or is not there, click by click, and a clock; prints the button's text after each step
COPY_RUN = r"""
const fs = require('fs');
const script = fs.readFileSync(process.argv[2], 'utf8');
const button = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
async function run(outcomes, steps) {
  let now = 0, seq = 0, clicks = 0;
  const timers = new Map(), handlers = [], seen = [];
  const b = {attrs: Object.assign({}, button.attrs), textContent: button.text,
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    hasAttribute(k) { return k in this.attrs; },
    closest(sel) { return sel === 'button[data-copy]' ? this : null; }};
  const code = {textContent: 'the command'};
  const document = {addEventListener(t, f) { if (t === 'click') handlers.push(f); },
    getElementById(id) { return id === b.attrs['data-copy'] ? code : null; },
    createRange() { return {selectNodeContents() {}}; }, querySelectorAll() { return []; }};
  const window = {addEventListener() {}, getSelection() { return {removeAllRanges() {}, addRange() {}}; }};
  const navigator = {get clipboard() {
    const o = outcomes[Math.min(clicks - 1, outcomes.length - 1)];
    if (o === 'absent') return undefined;
    return {writeText() { return o === 'copies' ? Promise.resolve() : Promise.reject(new Error('refused')); }};
  }};
  const setTimeout = (f, ms) => { seq += 1; timers.set(seq, {at: now + ms, f}); return seq; };
  const clearTimeout = (id) => { timers.delete(id); };
  new Function('document', 'window', 'navigator', 'setTimeout', 'clearTimeout', script)(
    document, window, navigator, setTimeout, clearTimeout);
  for (const step of steps) {
    if (step === 'click') {
      clicks += 1;
      for (const h of handlers) h({target: b});
      await new Promise((r) => setImmediate(r));
    } else {
      const end = now + step;
      for (;;) {
        let next = null;
        for (const [id, t] of timers) if (t.at <= end && (!next || t.at < next[1].at)) next = [id, t];
        if (!next) break;
        timers.delete(next[0]);
        now = next[1].at;
        next[1].f();
      }
      now = end;
    }
    seen.push(b.textContent);
  }
  return seen;
}
(async () => {
  const out = {};
  out.quick = await run(['copies'], ['click', 250, 'click', 100000]);
  out.refused = await run(['refuses'], ['click', 100000]);
  out.absent = await run(['absent'], ['click', 100000]);
  out.refused_then_copies = await run(['refuses', 'copies'], ['click', 500, 'click', 100000]);
  out.copies_then_refused = await run(['copies', 'refuses'], ['click', 100, 'click', 100000]);
  process.stdout.write(JSON.stringify(out));
})().catch((err) => { console.error(err); process.exit(1); });
"""


def copy_runs(decision_html: str):
    """What the copy button shows after each step of COPY_RUN's scenarios, run under node; a str when node is not on
    PATH or the run fails (the check that reads it then fails: never a silent skip)."""
    if not shutil.which("node"):
        return "node is not on PATH: the copy button's script runs under it"
    m = re.search(r"<button ([^>]*)>([^<]*)</button>", decision_html)
    attrs = {k: html.unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', m.group(1))}
    d = tmp_dir()
    for name, text in (("run.js", COPY_RUN), ("script.js", ps.SCRIPT),
                       ("button.json", json.dumps({"attrs": attrs, "text": html.unescape(m.group(2))}))):
        Path(d, name).write_text(text, encoding="utf-8")
    r = subprocess.run(["node", os.path.join(d, "run.js"), os.path.join(d, "script.js"), os.path.join(d, "button.json")],
                       capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout) if r.returncode == 0 else f"node failed: {r.stderr}"


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
    check("the button's words: copy, copied, selected, and its own label in its attributes", '>Copy</button>' in d
          and 'data-label="Copy"' in d and 'data-done="Copied"' in d and 'data-select="Selected: press ⌘C or Ctrl+C"' in d)
    z = ZHS.decision("要你定", "", "demo close", "粘到终端里", cmd_id="c1")
    check("the button's words in Chinese", ">复制</button>" in z and 'data-label="复制"' in z and 'data-done="已复制"' in z
          and 'data-select="已选中，按 ⌘C"' in z)
    for hint in (None, "", "  "):
        check(f"a command without its hint is refused: {hint!r}",
              "hint" in message(ps.decision, "Decide", "", "demo close", hint))
    bare = ps.decision("Decide: make the next batch?", "<p>Body</p>")
    check("no command: no button, no code, no hint", 'data-zone="decision"' in bare and "<button" not in bare
          and "<code" not in bare and "hint" not in bare)
    check("the title escaped", "&lt;b&gt;" in ps.decision("<b>", ""))
    check("a caller's button words escaped", "<b>x" not in ps.Style({"copy": EVIL}).decision("t", "", "c", "h"))
    got = copy_runs(d)
    sel = "Selected: press ⌘C or Ctrl+C"
    want = {"quick": ["Copied", "Copied", "Copied", "Copy"], "refused": [sel, "Copy"], "absent": [sel, "Copy"],
            "refused_then_copies": [sel, sel, "Copied", "Copy"], "copies_then_refused": ["Copied", "Copied", sel, "Copy"]}
    for case, steps in want.items():
        check(f"the copy button under node, {case.replace('_', ' ')}: back to its label in the end",
              isinstance(got, dict) and got.get(case) == steps, got.get(case) if isinstance(got, dict) else got)
    zh = copy_runs(z)
    check("... in Chinese too", isinstance(zh, dict) and zh.get("quick") == ["已复制", "已复制", "已复制", "复制"]
          and zh.get("refused") == ["已选中，按 ⌘C", "复制"], zh)
    hand = copy_runs(d.replace(' data-label="Copy"', ""))
    check("a button made without data-label keeps the label it had at the first click", isinstance(hand, dict)
          and hand.get("quick") == ["Copied", "Copied", "Copied", "Copy"] and hand.get("refused") == [sel, "Copy"], hand)


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


def _chain(k):
    """A tree of one node a column down to a waffle of three cells, for k columns."""
    node = {"label": "Template", "cells": _cells(3)}
    for i in range(k - 2):
        node = {"label": f"Node {i}", "children": [node]}
    return [node]


def drawn(svg: str) -> list[int]:
    """The width of each column a map draws: its nodes' boxes, left to right, then the waffle's (the rest)."""
    boxes = sorted({(float(x), float(w)) for x, w in re.findall(r'<g class="node[^"]*"><rect x="([\d.]+)" y="[\d.]+" '
                                                                 r'width="([\d.]+)"', svg)})
    width = float(re.search(r'<svg class="map" viewBox="\S+ \S+ ([\d.]+)', svg).group(1))
    return [int(w) for _, w in boxes] + [int(width - boxes[-1][0] - boxes[-1][1] - 20)]


def past_edge(svg: str) -> list[str]:
    """The cells of a map whose right edge is past the map's (its viewBox width)."""
    width = float(re.search(r'<svg class="map" viewBox="\S+ \S+ ([\d.]+)', svg).group(1))
    return [x for x, w in re.findall(r'<rect class="sq [^"]*" x="([\d.]+)"[^>]*? width="([\d.]+)"', svg)
            if float(x) + float(w) > width]


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
    three = ps.node_map([{"label": "Row 1", "children": [], "empty": "no template yet"}, {"label": "Row 2", "children": [
        {"label": "Template 1", "cells": _cells(2)}]}], ("Row", "Template", "Paths"), (180, 180, 200))
    check("three columns, given widths", three.count('class="sq ') == 2 and 'width="600"' in three, three[:120])
    narrow = ps.node_map([{"label": "R", "children": [{"label": "T", "cells": _cells(15)}]}], ("Row", "Template", "Paths"),
                         (180, 180, 200))
    check("a 200px waffle column: 12 cells a line, so 15 take two lines and none is past the map's edge",
          len(set(re.findall(r'class="sq [^"]*" x="([\d.]+)"', narrow))) == 12 and not past_edge(narrow)
          and len(set(re.findall(r'class="sq [^"]*" x="[\d.]+" y="([\d.]+)"', narrow))) == 2, past_edge(narrow))
    for w in (13, 29, 50, 100, 200, 236, 237, 252, 300):
        svg = ps.node_map([{"label": "T", "cells": _cells(40)}], ("Template", "Paths"), (200, w))
        per = len(set(re.findall(r'class="sq [^"]*" x="([\d.]+)"', svg)))
        check(f"a {w}px waffle column: {(w + 3) // 16} cells a line, none past the map's edge",
              per == (w + 3) // 16 and not past_edge(svg) and svg.count('class="sq ') == 40, (per, past_edge(svg)))
    for w in (40, 47, 60, 24):
        svg = ps.node_map([{"label": "A row with a long name", "state": "down", "cells": _cells(1, "down")}], ("a", "b"),
                          (w, 252))
        text = re.search(r'<g class="node s-down"><rect[^>]*/><text class="t1"[^>]*>([^<]*)</text>', svg).group(1)
        check(f"a {w}px node keeps its icon and the space after it; only the label is cut",
              text.startswith(f"{ps.ICON['down']} ") and not [p for p in ps.problems(svg) if "map node" in p], text)
    four, kids = _chain(4), _chain(3)
    doc = re.search(r"defaults to \((\d+), (\d+), (\d+), (\d+)\) for four columns, else (\d+) a column and (\d+) "
                    r"for the waffle", " ".join(ps.node_map.__doc__.split()))
    check("node_map's docstring says its default widths, four columns apart", doc, ps.node_map.__doc__)
    if doc:
        n = [int(x) for x in doc.groups()]
        check("... and node_map draws them: four columns", drawn(ps.node_map(four, ("1", "2", "3", "4"))) == n[:4],
              drawn(ps.node_map(four, ("1", "2", "3", "4"))))
        check("... and three", drawn(ps.node_map(kids, ("1", "2", "3"))) == [n[4], n[4], n[5]],
              drawn(ps.node_map(kids, ("1", "2", "3"))))
    none = ps.node_map([{"label": None, "sub": None, "state": None, "children": [
        {"label": None, "caption": None, "cells": _cells(1)}]}], ("a", "b", "c"))
    check("a label, sub or caption left None is empty, never the word None", "None" not in none, none)
    check("one column is refused", "two columns" in message(ps.node_map, [], ("x",)))
    check("widths that do not match the columns are refused", "widths" in message(ps.node_map, [], ("a", "b"), (1, 2, 3)))
    for widths in ((200, 12), (200, 0), (0, 252), (-5, 252), ("200", 252), (True, 252)):
        check(f"widths {widths!r} are refused: each above 0, the waffle at least one cell", "node_map" in message(
            ps.node_map, [{"label": "x", "cells": _cells(1)}], ("a", "b"), widths))
    check("a cell of an unknown state is refused", "maybe" in message(
        ps.node_map, [{"label": "x", "cells": [{"state": "maybe"}]}], ("a", "b")))
    for cell, what in (({"state": "testing", "href": "#a"}, "title"), ({"state": "testing", "href": "#a", "title": None},
                       "title"), ({"state": "testing", "href": "#a", "title": ""}, "title"),
                       ({"state": "testing", "href": "#a", "title": "  "}, "title"), ({"state": "testing", "title": "x"},
                       "link"), ({"state": "testing", "title": "x", "href": ""}, "link")):
        m = message(ps.node_map, [{"label": "T 1", "cells": [cell]}], ("a", "b"))
        check(f"a cell without its {what} is refused, naming its node: {cell!r}", what in m and "T 1" in m, m)
    for node in ({"label": "Row 9", "children": []}, {"label": "Row 9", "children": [], "empty": None},
                 {"label": "Row 9", "children": [], "empty": " "}):
        m = message(ps.node_map, [node], ("a", "b", "c"))
        check(f"a node with nothing under it and no why is refused, naming it: {node!r}", "Row 9" in m and "why" in m, m)


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
    check("... not even the page's own host: no 'self', an image only inline (img-src data:)", "'self'" not in ps.CSP
          and re.findall(r"img-src [^;]*;", ps.CSP) == ["img-src data:;"], ps.CSP)
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
    for bad in (float("nan"), float("inf"), float("-inf")):
        m = message(ps.page, "t", "", {"rate": [1, bad]})
        check(f"page data holding {bad} is refused, saying it is not JSON and why", "not JSON" in m and "NaN" in m, m)
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
    check("the script reads each button's words from its attributes, the copy button's label too", all(
        f"'{a}'" in ps.SCRIPT for a in ("data-label", "data-done", "data-select", "data-more", "data-less")))
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
    owner's fold last; ids and the command only in the decision and the folds. `body_extra` goes before the fold."""
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
            + body_extra
            + style.owner("<p>How it is worked out: <code>min_expected_conv</code> and <code>--flag</code>.</p>"))
    return style.page("The plan's map · DEMO", body, data if data is not None else {"project": "DEMO", "n": 8})


SEEN: list[str] = []                            # each line a broken page below was tried for, as problems() said it


def test_problems() -> None:
    print("\n[9] problems(): every rule, each tried on a broken page")
    for name, style in (("English", ps.DEFAULT), ("Chinese", ZHS), ("a harness's own words", OWN)):
        for warns in (2, 6):
            page = demo_page(style, warns=warns)
            got = style.problems(page, commands=[r"\bdemo\b"])
            check(f"a whole {name} page keeps every rule ({warns} warnings given)", got == [], got)
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

    def broken(label: str, page: str, want: str, style: ps.Style | None = None, **kw) -> None:
        got = style.problems(page, **kw) if style is not None else ps.problems(page, **kw)
        SEEN.extend(g for g in got if want in g)
        check(f"seen: {label}", any(want in g for g in got), got)

    def fine(label: str, page: str) -> None:
        got = ps.problems(page, commands=[r"\bdemo\b"])
        check(f"not a problem: {label}", got == [], got)

    # the document
    broken("no doctype", good.replace("<!doctype html>\n", ""), "doctype")
    broken("no lang", good.replace('<html lang="en">', "<html>"), "no lang")
    broken("a lang that is not the style's", good, "lang is", style=ZHS)
    broken("a CSP that allows the network", good.replace("default-src 'none'", "default-src *"), "CSP")
    broken("the old CSP that let the page's host serve images", good.replace("img-src data:", "img-src 'self' data:"),
           "CSP")
    broken("a stylesheet link", good.replace("</head>", '<link rel="stylesheet" href="x.css"></head>'), "<link")
    broken("a form", demo_page(ps.DEFAULT, body_extra='<form action="x"></form>'), "<form")
    for what, extra in (("a remote image", '<img src="https://example.com/x.png">'),
                        ("a protocol-relative image", "<img src='//example.com/x.png'>"),
                        ("a remote url() in a style", '<p style="background:url(http://example.com/y)">x</p>'),
                        ("an image from the page's own host", '<img alt="" src="/api/x.png?t=1">'),
                        ("an image beside the page", "<img alt='' src=x.png>"),
                        ("a relative srcset", '<img alt="" srcset="/a.png 1x">'),
                        ("a video's poster", '<video poster="p.jpg"></video>'),
                        ("an SVG image", '<svg><image href="x.png"/></svg>'),
                        ("an SVG use of another file", '<svg><use xlink:href="icons.svg#a"/></svg>'),
                        ("a relative url() in a style", '<p style="background:url(/api/track?u=1)">x</p>'),
                        ("an @import", "<style>@import 'x.css';</style>")):
        broken(what, demo_page(ps.DEFAULT, body_extra=extra), "remote or relative")
    fine("an inline data: image, an SVG use of the page's own symbol",
         demo_page(ps.DEFAULT, body_extra='<img alt="" src="data:image/png;base64,AAAA"><svg><use href="#s"/></svg>'
                   '<span id="s"></span>'))
    broken("the style's stylesheet changed", good.replace("--p-f:#0072B2", "--p-f:#99CCFF", 1), "stylesheet")
    for what, css in (("an opacity", ".chip{opacity:.7}"), ("an opacity in %", ".vchip small{opacity:60%}"),
                      ("a filter", ".card{filter:grayscale(1)}"), ("a state's fill", ":root{--p-f:#99CCFF}"),
                      ("the ink", ":root{--ink:#777777}")):
        broken(f"the harness's CSS dims or recolours a state's text: {what}", good.replace("\n</style>", css + "\n</style>"),
               "dims or recolours")
    broken("a style attribute that dims", demo_page(ps.DEFAULT, body_extra='<p style="opacity:.5">x</p>'),
           "dims or recolours")
    fine("the harness's own CSS that dims nothing", good.replace("\n</style>", ":root{--f-body:serif}"
                                                                ".x{opacity:1;filter:none}\n</style>"))
    broken("the style's script changed", good.replace("beforeprint", "afterprint", 1), "script is not on the page")
    broken("a third script", good.replace("</body>", "<script>1</script></body>"), "3 scripts")
    broken("the page data holding <", good.replace('"project": "DEMO"', '"project": "<b>"'), "page data holds")
    broken("the page data not JSON", good.replace('"project": "DEMO"', "project"), "not JSON")
    for const in ("NaN", "Infinity", "-Infinity"):
        broken(f"the page data holding {const}", good.replace('"n": 8', f'"n": {const}'), "not JSON")
    broken("no page data", good.replace('type="application/json" id="page-data"', 'type="application/json"'),
           "no page data")
    broken("a grid track wider than a phone", ps.page("t", ps.decision("d", ""), extra_css=".x{grid-template-columns:"
                                                                                           "repeat(auto-fit,minmax(360px,1fr))}"),
           "wider than")
    for css in ("400px 1fr", "repeat(2,360px)", "repeat(auto-fit,minmax(30em,1fr))", "minmax(0,1fr) 400px",
                "200px 200px", "max(400px,10%)"):
        broken(f"a grid wider than a phone: {css}", good.replace("\n</style>", f".x{{grid-template-columns:{css}}}\n</style>"),
               "grid wider than")
    broken("a grid wider than a phone in a style attribute",
           demo_page(ps.DEFAULT, body_extra='<div style="display:grid;grid-template-columns:300px 1fr">x</div>'),
           "grid wider than")
    fine("grids that fit a phone", good.replace("\n</style>", ".x{grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}"
                                                             ".y{grid-template-columns:minmax(min(400px,100%),1fr) 8em}"
                                                             ".z{grid-template-columns:repeat(3,1fr) 288px}\n</style>"))
    # the status bar and tiles first
    broken("the tiles after the decision", ps.page("t", ps.decision("d", "") + ps.tiles([("1", "a", "b")])),
           "no status bar or number tiles before the decision")
    broken("neither a status bar nor tiles", ps.page("t", ps.decision("d", "")),
           "no status bar or number tiles before the decision")
    fine("a status bar alone before the decision", good.replace('<div class="tiles">', '<div class="tilez">', 1))
    # one decision
    broken("two decision zones", demo_page(ps.DEFAULT, body_extra=ps.decision("Also decide", "")), "2 decision zones")
    broken("no decision zone", good.replace('data-zone="decision"', ""), "0 decision zones")
    broken("two copy buttons", demo_page(ps.DEFAULT, body_extra=ps.details("x", ps.decision("y", "", "z", "h")
                                                                           .replace('data-zone="decision"', ""))),
           "2 copy buttons")
    broken("a copy button outside the decision", good.replace('<section class="decide" data-zone="decision">',
                                                              '<section class="decide">', 1)
           .replace('<section class="warn">', '<section class="warn" data-zone="decision">', 1), "outside the decision")
    broken("a command without its hint", good.replace('<p class="hint">Paste it in a terminal</p>', ""),
           "a command without its hint")
    # commands, flags, ids and hashes only in the decision and the folds
    broken("a zone of its own", demo_page(ps.DEFAULT, body_extra='<p data-zone="free">x</p>'), "other than decision")
    broken("a flag in the rest", demo_page(ps.DEFAULT, body_extra="<p>run it with --dry-run</p>"), "a flag")
    broken("a flag straight after Chinese text", demo_page(ZHS, body_extra="<p>请运行--dry-run再看</p>"), "a flag")
    broken("a hash in the rest", demo_page(ps.DEFAULT, body_extra="<p>results 3f9a2c1b77</p>"), "a hash")
    broken("a hash in upper case", demo_page(ps.DEFAULT, body_extra="<p>id 3F9A2C1B77</p>"), "a hash")
    broken("a hash straight after Chinese text", demo_page(ZHS, body_extra="<p>编号0A1B2C3D4E</p>"), "a hash")
    broken("a code in the rest", demo_page(ps.DEFAULT, body_extra="<p>because not_made</p>"), "a code")
    broken("the harness's command in the rest", demo_page(ps.DEFAULT, body_extra="<p>demo close it</p>"),
           "a command", commands=[r"\bdemo\b"])
    fine("a word with digits, a date and a number are not a hash, nor is a dash in Chinese text", demo_page(
        ps.DEFAULT, body_extra="<p>2026-10-13, 16,800 and 12345678 and Value 3a, B2B, 第二批——按顺序</p>"))
    # at most three warnings, the rest where the more line says
    broken("four warnings shown", demo_page(ps.DEFAULT, warns=2).replace("<li>Warning 1</li>",
                                                                          "<li>Warning 1</li><li>2</li><li>3</li>"),
           "4 warnings shown")
    broken("six warnings in two boxes", demo_page(ps.DEFAULT, warns=0, body_extra=ps.warnings(["a", "b", "c"])
                                                  + ps.warnings(["d", "e", "f"])), "6 warnings shown on the page")
    broken("a more line and no owner's fold", ps.page("t", ps.tiles([("1", "a", "b")]) + ps.decision("d", "")
                                                      + ps.warnings(list("abcd"))), "a more line, but no owner's fold")
    broken("a more line that names another fold", demo_page(ps.DEFAULT, warns=5).replace(
        "<summary>For the owner: how it was worked out</summary>", "<summary>Notes</summary>"),
        "a more line that does not name the owner's fold")
    # the node map
    broken("a chip without its icon", good.replace(f'<b aria-hidden="true">{ps.ICON["down"]}</b>', "", 1), "without its icon")
    broken("a chip of an unknown state", demo_page(ps.DEFAULT, body_extra='<span class="chip s-maybe">x</span>'),
           "unknown state")
    own = demo_page(OWN).replace('</b>weaker</span>', '</b>down</span>', 1)
    broken("a chip whose word is not the style's (given the style)", own, "without its word", style=OWN,
           commands=[r"\bdemo\b"])
    broken("a map node without its icon", good.replace(f">{ps.ICON['testing']} Row 1<", ">Row 1<"), "map node")
    broken("a cell without a title", re.sub(r'(<rect class="sq [^>]*>)<title>[^<]*</title>', r"\1", good, count=1),
           "without a title")
    for t in ("", "  "):
        broken(f"a cell whose title is {t!r}", re.sub(r'(<rect class="sq [^>]*>)<title>[^<]*</title>',
                                                      rf"\1<title>{t}</title>", good, count=1), "1 of 8 map cells without a title")
    broken("a cell that is not a link", re.sub(r'<a href="#p-[^"]*">(<rect class="sq .*?</rect>)</a>', r"\1", good,
                                               count=1), "not a link")
    broken("a cell whose title lacks its state's word (given the style)", demo_page(OWN).replace(
        "<title>weaker: Value 3</title>", "<title>down: Value 3</title>"), "does not hold its word", style=OWN,
        commands=[r"\bdemo\b"])
    broken("cells past the map's edge", re.sub(r'(<svg class="map" viewBox="\S+ \S+ )([\d.]+)', r"\g<1>700", good,
                                               count=1), "past the map's edge")
    leaf = ps.node_map([{"label": "Group C", "children": [], "empty": "no row yet"}], ("Group", "Row", "Paths"))
    fine("a node with nothing under it that says why", demo_page(ps.DEFAULT, body_extra=leaf))
    broken("a node with nothing under it that does not say why",
           demo_page(ps.DEFAULT, body_extra=leaf.replace(">no row yet<", "><")), "do not say why")
    broken("a link to nothing on the page", demo_page(ps.DEFAULT, body_extra='<p><a href="#p-nowhere">see</a></p>'),
           "a link to #p-nowhere")
    # cards that unfold row by row
    broken("a card outside a row", demo_page(ps.DEFAULT, body_extra=ps.card("down", anchor="p-z")),
           "cards outside a row")
    # the owner's fold
    broken("two owner's folds", demo_page(ps.DEFAULT, body_extra=ps.owner("<p>x</p>")), "2 owner's folds")
    broken("the owner's fold open", good.replace('<details class="owner"', '<details class="owner" open'),
           "the owner's fold is open")
    broken("something after the owner's fold", good.replace("</main>", "<p>After it</p></main>"),
           "something after the owner's fold")
    broken("the owner's fold first", ps.page("t", ps.owner("<p>x</p>") + ps.tiles([("1", "a", "b")])
                                             + ps.decision("d", "")), "something after the owner's fold")
    check("problems() names nothing on a page that keeps the rules, given the harness's command",
          ps.problems(good, commands=[re.compile(r"\bdemo\b")]) == [])
    rules = re.findall(r"^(\d)\. \*\*", DOC.split("## The rules", 1)[1].split("\n## ", 1)[0], re.M)
    table = DOC.split("## Checking a page", 1)[1].split("\n## ", 1)[0]
    rows = {m.group(1): m.group(2) for m in re.finditer(r"^\| (\d)\. [^|]*\| ([^|]*) \|", table, re.M)}
    check("docs/page-style.md: every rule has a row of the lines problems() reports for it",
          rules and rules == sorted(rows) and all(re.search(r"`[^`]+`", c) for c in rows.values()), (rules, rows))
    said = [(n, f) for n, c in sorted(rows.items()) for f in re.findall(r"`([^`]+)`", c)]
    unseen = [f"{n}: {f}" for n, f in said if not any(f in g for g in SEEN)]
    check("... and each such line is one a broken page above made problems() report", said and not unseen, unseen)
    check("... and every line a broken page above was tried for is in the doc's table",
          not [g for g in SEEN if not any(f in g for _, f in said)], [g for g in SEEN if not any(f in g for _, f in said)])


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


def darker(h: str, k: float) -> str:
    """A colour under brightness(k): each sRGB channel times k (darker in sRGB than in linear light, so the lower
    contrast of the two for dark text on a light fill)."""
    return "#" + "".join(f"{round(int(h[i:i + 2], 16) * k):02X}" for i in (1, 3, 5))


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
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", ps.CSS)
    dim = [f"{sel.strip()}{{{body}}}" for sel, body in rules
           for v, pct in re.findall(r"(?<![\w-])opacity\s*:\s*(\d*\.?\d+)(%?)", body) if float(v) / (100 if pct else 1) < 1]
    check("nothing in the stylesheet dims a state's text: no opacity below 1", not dim, dim)
    filters = [(sel.strip(), f.strip()) for sel, body in rules for f in re.findall(r"(?<![\w-])filter\s*:\s*([^;]*)", body)]
    check("the one filter is the map's hover, a brightness on a box's fill (not on its text)",
          filters == [("svg a:hover rect", "brightness(.92)")], filters)
    k = float(re.search(r"brightness\(([\d.]+)\)", filters[0][1]).group(1)) if filters else 1.0
    for sel, t in blocks.items():
        for s, (fg, bg) in TEXT_ON.items():
            r = contrast(t[fg], darker(t[bg], k))
            check(f"{sel} {s}: its text on its fill under the hover {r:.2f}:1 >= 4.5", r >= 4.5, (t[fg], darker(t[bg], k)))


# ---- [11] the phone ------------------------------------------------------------------------------

def test_phone() -> None:
    print("\n[11] a 320px phone")
    grids = re.findall(r"grid-template-columns\s*:\s*([^;}]*)", ps.CSS)
    over = [(v, ps._grid_px(v)) for v in grids if ps._grid_px(v) > ps.PHONE - 2 * ps.GUTTER]
    check("every grid of the stylesheet fits a 320px phone's column (320 less two 16px gutters), its fixed tracks "
          "added up", len(grids) >= 8 and not over, over)
    reads = {"400px 1fr": 400, "repeat(2,360px)": 720, "repeat(auto-fit,minmax(200px,1fr))": 200,
             "repeat(auto-fill,minmax(min(300px,100%),1fr))": 0, "7.5em 1fr": 120, "minmax(30em,1fr)": 480,
             "max(400px, 10%)": 400, "auto 1fr auto": 0, "clamp(100px, 50%, 400px) 2rem": 132, "subgrid": 0,
             "[a] 100px [b] repeat(2, [c] 50px)": 200, "fit-content(400px) 1fr": 0}
    got = {v: ps._grid_px(v) for v in reads}
    check("a grid's width: its fixed tracks added up (px, em and rem at 16), repeat() and minmax() read, what gives "
          "way to the container 0", got == reads, {v: (got[v], reads[v]) for v in reads if got[v] != reads[v]})
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
