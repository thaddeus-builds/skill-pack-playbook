# Page style: one look for the pages that guide making

A skill pack that makes things for a client (ads, posts, emails) writes pages a person reads to decide what to make next and to see why: the plan's map, the next batch, a make page, an insight page. Read the same way every time, such a page is read in a minute. Module: [`kit/pagestyle.py`](../kit/pagestyle.py), pack `pages` (`[kit] packs = ["pages"]`). It returns HTML strings; it writes no file, runs nothing and reads no skill pack file.

*Seen once:* the video-ads skill pack built it for its first client's plan map (2026-10-13), and the owner made that page the model for every page that guides making and shows the reasoning (its ROADMAP X48): its `pkg/pagestyle.py` (the style, Chinese words only), `pkg/spacepage.py` (a page drawn with it) and its `docs/space.md`. It keeps its own copy for now; this module is that copy with every visible word made a parameter, and with a check a skill pack's tests run on each page it writes (`problems()`).

The same style draws the design page of [templates/design-first.md](../templates/design-first.md) and the pictures any page shows in place of paragraphs: a flow by lanes, a phone's frame, a figure, the choices (rules 10 to 13). *Seen once:* product-image-to-video's design page for its remake storyboard (2026-11-04, its X24). The owner called the version in paragraphs "文字太多了 如果能用图像表示就不用再写字了", read the one redrawn as a flow with L3 and L4 lanes, a phone mock-up and ticked cards in a minute, and asked that every such page be drawn that way. Its session had drawn those pictures by hand; they are these parts now, so the next skill pack draws none.

## Why its own pack

The concern is how a page looks to a person, not how its numbers are worked out, so it is neither `learning` (the five states are `kit.pathweights`'s, but a make page or an insight page shows states without computing them) nor the owner console (`console/`, which is where asks are answered and never imports the kit). A pack imports only `base` and itself, so the module repeats the states and `tenths()`; its test holds both equal to `kit.pathweights`'s.

## The rules

Each rule has the part that keeps it and a check that fails when it is broken. What a page can break, `problems()` reports, one line per rule broken ([Checking a page](#checking-a-page) lists the lines, rule by rule); what only the module's own code can break (the colours' contrast, the one-pass fill, the script holding no word, the dots' rounding) its test checks.

1. **A state is colour, word and icon, never colour alone.** Five states, `untested ○`, `testing ◐`, `promising ▲`, `down ▼`, `closed ✕`; blue for better and orange for worse (Okabe-Ito, colour-blind safe), grey for what a person closed. `chip(state)`, `vchip(state, label)`, the map's nodes (the icon before the label, never cut when the label is fitted to its box) and its cells (each with a title that holds its state's word). Each state's text reads on its fill at 4.5:1 or more in the light theme and in both dark ones, and nothing dims it: no opacity, and the map's hover darkens a box's fill only as far as its text still reads 4.5:1. A skill pack's own CSS dims nothing and leaves the state colours as they are.
2. **A status bar and number tiles first.** `tiles(items)`, `bar(counts)`, `legend(counts)`: what stands where, before the decision and any detail. A count is a whole number of items (`None` is 0); anything else is refused.
3. **One decision per page.** `decision(title, body, command, hint)`: the one thing a person decides, the command shown whole with one copy button and a hint that says where to paste it (a command without its hint is refused). The page itself runs nothing: its one script is the style's. With nothing to decide, the decision says so.
4. **Commands, flags, ids and hashes only in the decision and the folds.** The decision is `data-zone="decision"`, the folds (`details()`, `owner()`, a card's codes) are `data-zone="tech"`; `zones(page)` reads the visible text of each, and the rest holds none of them (the console's UI rule U01 says the same of every page, [templates/console/ui_rules.tsv](../templates/console/ui_rules.tsv)). A flag is `--x`; a hash or hex id is seven or more hex characters, either case, with a letter and a digit; a code is `snake_case`; each is seen straight after a Chinese character too. The names people use (a creative's code, a row's name) may show anywhere; they are not commands.
5. **At most three warnings.** `warnings(items)` shows the first three; the rest are one line that names the owner's fold, where they are, and the skill pack shows them there. Three is the most a page shows, all its warning boxes together. A limit above three is refused.
6. **A node map with one cell per item.** `node_map(tree, heads)`: columns of nodes linked left to right, the last a waffle of cells, one per item, each a link to its card with a title, as many to a line as the waffle column's width holds (so no cell is past the map's edge); a node with nothing under it draws why. `node_map()` refuses a cell without a title or a link, a node with nothing under it and no why, and a waffle column narrower than a cell; a text left `None` is empty.
7. **Cards that unfold row by row.** `fold_row()` around `card()`: every card sits in a row that unfolds. A card's numbers, ten dots for a probability (`dots(p)`: "about n times in 10", rounded toward a half so a number shown never crosses the line its state was judged on), what happens if it works and if it does not (`story()`), its codes behind a fold.
8. **The owner's fold.** `owner(inner)`: how it was worked out, folded, the last thing on the page, at most one. The more line names it by its title up to the first colon (`fold_name()`: "For the owner", "给负责人看"), so a skill pack renames `owner` and `more` together: `Style()` refuses a `more` that does not name the owner's fold, and `problems()` a page whose more line does not (or that has no owner's fold).
9. **One document.** `page(title, body, data)`: the doctype; `lang`; a CSP that allows no network (`default-src 'none'`, inline style and script only, no form, no base, never `'self'`: an image only inline, `img-src data:`, which makes no request, so a make page can show a frame in the one document); light and dark tokens on `:root` (`@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`, and `:root[data-theme="dark"]`); the page data as strict JSON for agents (NaN and Infinity refused), escaped so it never holds `</`; a little vanilla JS (copy buttons, expand all, a link opens the fold it points into, print opens every fold) that holds no word. A copy button comes back to its own label (`data-label`) after any number of quick clicks and after the fallback that selects the command. The template is filled in one pass, so a client's text that holds a placeholder's name (`__DATA__`) stays text. No grid is wider than a 320px phone's column (320 less two 16px gutters), its fixed tracks added up.

10. **A flow by lanes says who does each step.** `flow(steps, lanes)`: the steps across and one lane a row (an autonomy level, a kind of client), drawn again turned (steps down) for a phone, which the stylesheet shows below 640px. Every cell is one of three kinds, each colour, icon and word: `person` ◆ (a person decides that step; a cell may say who, "the client picks"), `auto` ↻ (it runs by itself), `skip` ∅ (not done in that lane: dashed, struck). A cell may carry a tag over it (a cost) and a stop at its corner (where it stops and asks a person); a lane may go back to an earlier step. The kinds' key, every stop and every way back are written in words under the picture, so a reader that cannot see colours or the picture reads them. `flow()` refuses fewer than two steps, a lane without a cell for every step, an unknown kind and a way back that does not go back or does not say why.
11. **Choices show what is decided, what is recommended and what comes after.** `choices(items)`: one card a choice, its kind colour, icon and word: `decided` ✓ (the owner's), `proposed` ★ (ours: one reply of agree accepts it), `open` ? (asked after the reply).
12. **A picture of someone else's screen says whose it is.** `phone(inner, label)`: a phone's frame around what a client or a user will see, drawn small; `label` is what a reader that cannot see it hears. `figure(inner, caption)`: any other picture a skill pack draws (an SVG, a chart), counted as a picture by a design page.
13. **A design page is pictures first.** `design_page(title, *, box, pictures, choices, record)`: the title and one lead line; the box of templates/design-first.md as four tiles (`BOX`: what agreeing sets going, what it costs, the worst case, what is still needed); the pictures; the choices; the one decision, a reply that agrees to all of it; the record (research, rules, risks, the owner's words) in the owner's fold. The prose outside the pictures, the box, the choices, the decision and the folds is at most `PROSE_MAX` (200 reading units: a CJK character 1, any other character 0.5, about two short sentences); the rest goes into the record.

## Words

Every word a page shows that the caller does not pass in is in one mapping. `Style(words, lang)` lays a skill pack's words over `EN` and refuses an unknown key, an empty word, a template (`money`, `dots`, `more`) without its `{n}`, or a `more` that does not name the owner's fold (`fold_name(owner)`), naming the key. `ZH` is a ready Simplified Chinese set. The module-level functions are an English style's.

| Key | `EN` | `ZH` | What it is |
| --- | --- | --- | --- |
| `state_untested` … `state_closed` | untested, testing, promising, down, closed | 未测, 在测, 表现良好, 表现下滑, 已停止 | the five states |
| `sep` | `, ` | `，` | between the parts of a legend line |
| `money` | `{n}` | `{n}` | an amount of money; the currency is the skill pack's (`¥{n}`, `${n}`, `{n} €`), so neither set names one |
| `dots` | about {n} times in 10 better than the account | 10 次里约 {n} 次比账户平均好 | the line beside ten dots |
| `warnings` | Watch | 需要关注 | the warnings box's title |
| `more` | {n} more, under “For the owner” at the foot of the page. | 另有 {n} 条，在页尾“给负责人看”里。 | the one line for the warnings not shown: it names the fold where they are |
| `if_works`, `if_fails` | If it works, If it does not | 如果有效, 如果无效 | a card's two lines |
| `details` | Details | 详情 | the fold of a card's codes |
| `owner` | For the owner: how it was worked out | 给负责人看：怎么算的 | the owner's fold |
| `copy`, `copied`, `selected` | Copy, Copied, Selected: press ⌘C or Ctrl+C | 复制, 已复制, 已选中，按 ⌘C | the copy button, once copied, and when the browser refuses to copy |
| `expand_all`, `collapse_all` | Expand all, Collapse all | 全部展开, 全部收起 | the button that unfolds every row (`expand_all()`) |
| `flow_person`, `flow_auto`, `flow_skip` | a person, automatic, skipped | 人来定, 自动, 跳过 | a flow's three kinds of cell, in its key and on a cell that names no one |
| `flow_stop`, `flow_back` | stops and asks, goes back | 停下来问, 退回 | a flow's stop and way back, written under the picture |
| `choice_decided`, `choice_proposed`, `choice_open` | decided, recommended, asked after | 已定, 推荐, 之后再问 | a choice's kind |
| `box_agree`, `box_cost`, `box_worst`, `box_needed` | If you agree, What it costs, The worst case, Still needed from you | 同意后, 花费, 最坏的情况, 还需要你 | the design page's box |
| `design_reply` | All of it as shown: reply “agree” | 全部照这样，回复“同意” | the design page's one decision |
| `record` | The record: research, rules, risks | 细节：研究、规则、风险 | the design page's fold |

A button's words travel in its own attributes (`data-label`, `data-done`, `data-select`, `data-more`, `data-less`), so one script serves any language. A skill pack that renames `owner` renames `more` with it; `Style()` refuses one that no longer names the other.

## The parts

| Part | What it makes |
| --- | --- |
| `Style(words=None, lang="en")` | the style with a skill pack's words; every part below is its method or attribute (every name the module exports but `Style` and `DEFAULT`), so a Style stands in for the module |
| `word(state)`, `legend_text(counts)`, `money(x)` | a state's word; "promising 2, testing 6"; an amount in the `money` template (the module's `money(x, fmt="{n}")` takes the template) |
| `chip(state, extra="", proposal=False)`, `vchip(state, label, note="")` | a state; a value in its state's colour |
| `tiles(items)`, `bar(counts, big=False)`, `legend(counts)`, `dots(p, text=None)` | number tiles, the status bar, every state with its count, ten dots |
| `decision(title, body, command=None, hint=None, cmd_id="cmd1")` | the one decision; a command needs its hint |
| `warnings(items, limit=3, more=None)` | at most three warnings and the more line |
| `story(works, fails)`, `card(state, *, anchor, ...)`, `fold_row(state, *, anchor, title, ...)`, `expand_all()` | the cards and the rows that unfold |
| `details(summary, inner, cls="tech")`, `owner(inner, summary=None)` | the folds |
| `node_map(tree, heads, widths=None, *, label="")` | the map; `widths` (px, one a column) defaults to (156, 208, 188, 252) for four columns, else 200 a column and 252 for the waffle (15 cells a line) |
| `page(title, body, data=None, *, extra_css="")` | the document |
| `flow(steps, lanes, *, label="", caption="", ident="flow")` | who does each step, lane by lane: drawn across and turned for a phone, its key, stops and ways back in words |
| `choices(items)`, `phone(inner, label, caption="")`, `figure(inner, caption="")` | the choices; a phone's frame around what someone else will see; any other picture |
| `design_page(title, *, box, pictures, choices, record, lead="", data=None)` | the design page of templates/design-first.md, drawn whole |
| `e`, `amount`, `tenths`, `fit`, `text_width`, `page_data`, `wordset`, `fold_name` | escaping, a count that may be fractional, tenths, a label cut to a width, its width, strict JSON safe in a script, a skill pack's words over `EN`, the owner's fold as a more line names it |
| `CSS`, `CSP`, `SCRIPT`, `PAGE`, `ICON`, `STATES`, `ORDER`, `WARNINGS_MAX`, `PHONE`, `GUTTER`, `NONE`, `EN`, `ZH`, `WORDS`, `TEMPLATES`, `CODE_PATTERNS`, `KINDS`, `KIND_ICON`, `CHOICES`, `CHOICE_ICON`, `BOX`, `PROSE_MAX` | the constants |
| `zones(page)`, `problems(page, *, commands=())` | the visible text by zone; the rules a page breaks, with this style's words and lang (the module's `problems()` also takes `style=`; a Style passes itself) |

The stylesheet also carries classes a skill pack uses in its own markup: `.eyebrow` and `.syn` (a "synthetic data" badge) for the header, `.space`, `.mapbox`, `.rows` and `.rowhead` for sections, `.batch`, `.moves` and `.move` (`known`, `maybe`, `wait`) for the next batch, `.group`, `.vars`, `.var`, `.vname`, `.vals` for a template's variables, `.cards`, `.combo`, `.pv`, `.note`, `details.todo`. `extra_css` adds the skill pack's own after it (a font stack: `:root{--f-body:...}`); it may not close the style element, and it may not dim or recolour a state (`problems()`).

## Checking a page

`problems(page)` returns one line per rule the page breaks; an empty list means it keeps them all. A skill pack's test runs it on every page it writes, with its own command patterns and its style:

```python
from kit import pagestyle

STYLE = pagestyle.Style({**pagestyle.ZH, "money": "¥{n}"}, lang="zh-CN")
assert STYLE.problems(html, commands=[r"\bacme\b"]) == []      # acme: the skill pack's CLI
```

What it reports, rule by rule (each line is tried on a broken page in the module's test, and the test holds this table to them):

| Rule | `problems()` reports | Its test checks instead |
| --- | --- | --- |
| 1. A state is colour, word and icon | `without its icon`, `of an unknown state`, `without its word`, `does not hold its word` (given the style: a chip's, a cell's title), `map cells without a title`, `dims or recolours`, `stylesheet does not start` | each state's text on its fill, plain and under the hover, 4.5:1 in all three themes; no opacity in the stylesheet |
| 2. A status bar and number tiles first | `no status bar or number tiles before the decision` | a count that is not a whole number refused |
| 3. One decision per page | `decision zones, not one`, `copy buttons, not at most one`, `a copy button outside the decision`, `a command without its hint`, `script is not on the page`, `scripts, not two` | the copy button's script, run under node: back to its label after quick clicks and after the fallback |
| 4. Commands, flags, ids and hashes only in the decision and the folds | `outside the decision and the folds`, `a data-zone other than` | |
| 5. At most three warnings | `warnings shown on the page`, `a more line, but no owner's fold`, `a more line that does not name the owner's fold` | a limit above three refused |
| 6. A node map with one cell per item | `a map node of state`, `map cells that are not a link`, `past the map's edge`, `a link to #`, `do not say why` | as many cells a line as the column holds, at any width; a cell without a title or a link, a node with no why refused |
| 7. Cards that unfold row by row | `cards outside a row` | the dots' rounding (`tenths()` as `kit.pathweights`') |
| 8. The owner's fold | `owner's folds, not at most one`, `the owner's fold is open`, `something after the owner's fold` | a `more` that does not name the owner's fold refused |
| 9. One document | `doctype`, `has no lang`, `lang is`, `CSP`, `nothing is sent or loaded`, `remote or relative`, `page data holds`, `page data is not JSON`, `no page data`, `grid wider than` | the one-pass fill, the script holding no word and calling no network, NaN and Infinity refused when the page is written |
| 10. A flow by lanes says who does each step | `a flow without both its layouts`, `a flow stop without its words`, `a flow whose key lacks a kind`, `a flow key of kind`, `a flow cell of an unknown kind`, `a flow cell of kind` | each kind's text on its fill, 4.5:1 in all three themes; the bad shapes `flow()` refuses; the two layouts hold the same cells |
| 11. Choices show what is decided, what is recommended and what comes after | `a choice without its icon, title or word`, `a choice of kind` | an unknown kind and a choice without a title refused |
| 12. A picture of someone else's screen says whose it is | `a phone frame without its label` | a frame without a label refused |
| 13. A design page is pictures first | `a design page whose box lacks`, `a design page with no picture before`, `a design page whose box is not before`, `a design page without its choices`, `of prose outside its pictures` | a box without its four lines, no picture, a picture that is not a figure and no record refused |

The visible text it reads is `zones(page)`'s `rest`: no flag, hash or hex id, or `snake_case` code there, nor any of the skill pack's `commands`. What a page says is the skill pack's: whether a closed card says it is closed, whether the warnings the more line counts really sit in the owner's fold, whether the decision says there is nothing to decide when there is not.

## A skill pack that keeps its words in a table

The style reads no file. A skill pack that keeps the words people see in its own term table reads them there and passes them, and can keep its old module as a thin wrapper:

```python
# the skill pack's own pages module
from kit import pagestyle as _kit
from kit.pagestyle import CSP, CSS, ICON, ORDER, SCRIPT, STATES, WARNINGS_MAX, amount, details, e, fit, node_map, \
    page_data, problems, tenths, tiles, zones
from . import terms                                          # the skill pack's term table

STYLE = _kit.Style({**_kit.ZH, **{f"state_{s}": terms.word(f"state_{s}") for s in STATES},
                    "copy": terms.word("copy"), "money": "¥{n}"}, lang="zh-CN")
word, money, legend_text, chip, vchip, bar, legend, dots = (STYLE.word, STYLE.money, STYLE.legend_text, STYLE.chip,
                                                            STYLE.vchip, STYLE.bar, STYLE.legend, STYLE.dots)
decision, warnings, story, owner, card, fold_row, expand_all, page = (STYLE.decision, STYLE.warnings, STYLE.story,
                                                                      STYLE.owner, STYLE.card, STYLE.fold_row,
                                                                      STYLE.expand_all, STYLE.page)
```

Its pages then draw the expand-all button with `expand_all()` (the script finds it by `data-expand`, not by an id) and its tests call `STYLE.problems()` beside their own.

## A page drawn for you: the day's items

`kit.daily_page.render(doc)` ([`kit/daily_page.py`](../kit/daily_page.py), same pack `pages`) draws the document `kit.daily.build()` returns (the day's advice of an ads skill pack, the audit's findings among it as `audit:<finding>` items) with this style, so a pack does not draw it again: tiles and the status bar first, the one decision (the first open item of the most severe kind, with the command that reports back and its hint), at most three warnings (the other open items of that kind, then the document's notes), one row per item that unfolds into its card, the owner's fold last. It reads the document as plain dicts and never imports `kit.daily` (`pages` imports only itself and `base`); the shape is written in the module's docstring. Severity is the state (`down`, `testing`, `untested`; an item somebody reported on is `closed`), so a pack gives its `Style` its own words for those four states; the other words are `WORDS_EN` or `WORDS_ZH` with the pack's `words_over`; the sentences are the items' coded messages in the style's language (`say=` replaces that for a pack with its own, Traditional Chinese for one). Seen once: the video-ads skill pack draws its own (`daily_page.py`, `audit_page.py`); the next ads skill pack's weekly page is the second reader. The pack's test runs `STYLE.problems()` on the page as on any other.

## What the skill pack supplies

- **Its words and its lang:** the state words, the button words, the currency; where they are kept and who renames them.
- **What each page says:** titles, numbers, the reasons, what happens if it works and if not, what the decision is and its command, which warnings come first and the rest in the owner's fold.
- **Its command patterns** for `problems()`: its CLI's name, and anything else that is a command there.
- **Where the page goes:** a file under the client's data, a shared page; the same document serves both.

## Why no CSS framework

The owner asked (2026-11-04) whether these pages, read offline on a laptop rather than served to a client, should use a popular framework such as Tailwind instead of this one stylesheet. No, for four reasons that hold for every page here, offline or not:

- **A page loads nothing.** Its CSP is `default-src 'none'`: a framework fetched from a network is refused by the page itself, and a page opened with no network would lose its whole look. A client's page must not call out either, so the offline case and the client's case want the same thing.
- **The kit is the standard library only.** A framework's way of shipping only the classes a page uses is a Node build step; nothing in the kit builds.
- **The pictures are not CSS.** A framework sizes and colours boxes; the flow, the phone and the map are drawn here from data as SVG, and that is what made the page readable. A framework would leave all of it to be drawn by hand again.
- **Its colours are not tested against ours.** Each state's and kind's text reads 4.5:1 on its fill in the light theme and both dark ones, and the test proves it; a framework's palette carries no such check.

One stylesheet of tokens and about 150 rules serves every part. Look again if a page ever has to do more than the style's script (copy, unfold, print): that is an app, like the console, not a page.

## What does not use it, and why

- **The owner console** (`console/`) is an app that answers asks and never imports the kit; its own rules are in `templates/console/ui_rules.tsv`.
- **The overview and solutions pages** (`tools/overview_page.py`, `tools/solutions_page.py`) are explorers of the portfolio's diagram: they run their own script to draw a pack's arrows when it is picked, which a page of this style never does. They are the playbook's own tools and are not vendored.

## What it cannot say

- Whether the page is true: it lays out what it is given. Its numbers come from the skill pack (for the five states, from `kit.pathweights`).
- Whether a person understood it. The rules are what one owner confirmed on two pages of one skill pack (seen once); an operator who reads it differently is a lesson for the next version.

Test: [`kit/tests/test_pagestyle.py`](../kit/tests/test_pagestyle.py).
