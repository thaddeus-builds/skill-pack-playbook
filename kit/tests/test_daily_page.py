#!/usr/bin/env python3
"""kit.daily_page: the day's items drawn over kit.pagestyle, on SYNTHETIC content only (DEMO names, made-up ids).

  1. The real thing: the items kit.daily.build() returns (the test may import across packs; the module may not) draw a page whose style check is clean,
     with one decision (the command of the first open item, with its hint), at most three warnings, one row per item, the owner's fold last, and no id,
     flag or code in the visible text.
  2. Warnings: more than three open high items show three and one line that names the owner's fold, the rest sit in that fold; the document's notes join them.
  3. The words: the pack's style and words replace the defaults; an unknown key, an empty word and a template without its placeholder are refused,
     naming the key; the Chinese style reads the registry's Simplified Chinese; `say` replaces the sentence.
  4. What it does not know: an unknown severity reads as info; an item with no id, no sentence or not a mapping is left out and counted; an answered item
     is closed and is not the decision; with nothing open the decision says so and has no copy button.
  5. Nothing today: an empty list draws the page, still clean.
  6. Every text is escaped; the module imports only base and its own pack and names no platform.
"""

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import daily, daily_page, pagestyle  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402
from kit.tools import packs  # noqa: E402

CMD = [r"\bshop\b"]
DEMO_CMD = "shop import action --market DEMO --item {} --answer done"


def part(text, code=None, **params):
    return {"message": text, "message_code": {"code": code or "demo_unregistered", "params": params}}


def item(ident, severity="info", layer=2, name="DEMO one", text=None, last=None, steps=(), doubt=(), evidence=None):
    return {"id": ident, "layer": layer, "severity": severity, **part(text or f"Sentence of {name}"), "evidence": evidence,
            "steps": [part(s) for s in steps], "doubt": [part(d) for d in doubt], "subject": {"name": name},
            "report": DEMO_CMD.format(ident), "last": last}


def doc(items, **kw):
    return {"market": "DEMO", "currency": "USD", "as_of": "2026-10-21", "items": items, "solved": [], "notes": [], "note_codes": [],
            "followed_text": part("Earlier advice: 1 taken"), "held": 2, **kw}


def clean(page, style=daily_page.EN_STYLE, label=""):
    got = style.problems(page, commands=CMD)
    check(f"the style check is clean{label}", got == [], got)


def data_of(page):
    import json
    return json.loads(re.search(r'id="page-data">(.*?)</script>', page, re.S).group(1).replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))


def test_real() -> None:
    print("[1] the items kit.daily.build() returns")
    camp = {"as_of": "2026-10-21", "currency": "USD", "campaigns": [
        {"campaign": "111", "name": "DEMO fatigued", "state": "fatigued", "status": "ACTIVE", "proposals": [
            {"action": "rest_creatives", **part("Its creatives are wearing out: rest the declining ones", "campaign_rest_creatives", declining=4)}]}]}
    audit = {"findings": [{"finding": "audit_issues", "severity": "high", **part("2 ads are limited and spent 3.0 in 14 days"),
                           "steps": [{**part("Open the list of limited ads"), "text": "Open the list of limited ads"}]}]}
    move = {"campaign": "111", "name": "DEMO fatigued", "from": 400.0, "to": 355.0, "change": -0.1125, "cap": 0.1, "fast": False, "z": -2.9, "level": 2.1,
            "marginal": {"value": 1.49, "se": 0.47, "low": 1.01, "high": 1.96}, "binding": "min_daily_budget", "doubt": ["no_counterfactual"]}
    alloc = {"proposal": {"moves": [move], "held": [{"campaign": "333"}], "followed": {"taken": 1, "not_taken": 2, "open": 3}}}
    pacing = {"warnings": ["no target"], "warning_codes": [{"code": "pacing_no_target", "params": {"month": "2026-10"}}], "creative_demand": {
        "n": 10, "batch_size": 5, "capacity": 12, "money": 1000.0, "committed": 100.0, "unit_cost": 80.0, "basis": "measured",
        "batches": [{"size": 5, "daily_budget": 40.0}, {"size": 5, "daily_budget": 40.0}], "constraints": []}}
    d = daily.build("DEMO", "shop", camp, audit, alloc, pacing, {})
    page = daily_page.render(d)
    clean(page)
    z = pagestyle.zones(page)
    ids = [i["id"] for i in d["items"]]
    check("the decision is the first item (the audit finding, high) with its report command and one copy button",
          z["counts"]["decision"] == 1 and z["copies"] == ["decision"] and d["items"][0]["report"] in z["decision"] and ids[0] == "audit:audit_issues", z["copies"])
    check("the decision holds the item's sentence and its step", "2 ads are limited" in z["decision"] and "Open the list of limited ads" in z["decision"])
    check("one row per item", page.count('<details class="row"') == len(ids) == 4, page.count('<details class="row"'))
    check("every item's id is in a fold and nowhere else visible", all(i in z["tech"] for i in ids) and not any(i in z["rest"] for i in ids))
    check("the registry's sentence is used for a registered code, filled with its params",
          "change its daily budget from 400.0 to 355.0" in page and "ask the maker for 10 creatives" in page, "move/request sentence")
    check("the hint says where to paste the command", "paste this in a terminal" in page)
    check("the pacing note is the one warning, in the registry's sentence for its code (the kit registers pacing_no_target since compute_pacing); the page data lists the items in order",
          page.count("<li>2026-10: no spend target for the month: nothing to plan</li>") == 1 and [i["id"] for i in data_of(page)["items"]] == ids)
    check("severity order: high before medium before info", [i["severity"] for i in data_of(page)["items"]] == sorted((i["severity"] for i in d["items"]), key=daily.RANK.get))


def test_warnings() -> None:
    print("\n[2] at most three warnings, the rest in the owner's fold")
    highs = [item(f"audit:demo_{n}", "high", name=f"DEMO high {n}") for n in range(6)]
    page = daily_page.render(doc(highs, notes=["a note"], note_codes=[part("a note")["message_code"]]))
    clean(page)
    shown = sum(box.count("<li>") for box in re.findall(r'<section class="warn">(.*?)</section>', page, re.S))
    check("three shown", shown == 3, shown)
    check("one more line names the owner's fold", re.search(r'<li class="more">(\d+) more, under “For the owner”', page) is not None
          and re.search(r'<li class="more">(\d+)', page).group(1) == "3", re.findall(r'<li class="more">(.*?)</li>', page))
    fold = re.search(r'<details class="owner".*', page, re.S).group(0)
    check("the three not shown are in the owner's fold; the decision item is not a warning", all(f"Sentence of DEMO high {n}" in fold for n in (3, 4, 5))
          and "Sentence of DEMO high 0</li>" not in re.search(r'<section class="warn">(.*?)</section>', page, re.S).group(1))
    check("exactly one decision", pagestyle.zones(page)["counts"]["decision"] == 1)
    few = daily_page.render(doc([item("a:1", "high"), item("a:2", "high", name="DEMO two")]))
    clean(few)
    check("one other high item: one warning, no more line", few.count('class="more"') == 0 and "Sentence of DEMO two" in re.search(r'<section class="warn">(.*?)</section>', few, re.S).group(1))


def test_words() -> None:
    print("\n[3] the pack's words")
    mine = pagestyle.Style({"state_down": "URGENT", "state_testing": "SOON", "state_untested": "LATER", "state_closed": "DONE"}, lang="en-GB")
    page = daily_page.render(doc([item("a:1", "high"), item("a:2", "medium", name="DEMO two"), item("a:3", "info", name="DEMO three")]), style=mine,
                             words_over={"title": "DEMO board", "layer_2": "Things in the account", "decision_title": "Start here"})
    clean(page, mine, " with the pack's style")
    check("its style words replace the defaults", all(x in page for x in ("URGENT", "SOON", "LATER")) and "do first" not in page)
    check("its words replace the defaults", "DEMO board" in page and "Things in the account" in page and "Start here" in page and "Do this first" not in page)
    check("its lang is the page's", '<html lang="en-GB">' in page)
    for label, over, want in (("an unknown key", {"nope": "x"}, "nope"), ("an empty word", {"title": " "}, "title"),
                              ("a template without its placeholder", {"headline": "suggestions"}, "headline"),
                              ("a date template without {day}", {"as_of": "data"}, "as_of")):
        try:
            daily_page.render(doc([]), words_over=over)
            err = ""
        except ValueError as e:
            err = str(e)
        check(f"{label} is refused, naming the key", want in err, err)
    zh = daily_page.render(daily.build("DEMO", "shop", {"as_of": "2026-10-21", "currency": "USD", "campaigns": []}, {"findings": []}, {}, {
        "creative_demand": {"n": 10, "batch_size": 5, "capacity": 12, "money": 1.0, "committed": 1.0, "unit_cost": 8.0, "basis": "measured",
                            "batches": [{"size": 5, "daily_budget": 4.0}], "constraints": []}}, {}), style=daily_page.ZH_STYLE)
    clean(zh, daily_page.ZH_STYLE, " in Chinese")
    check("the Chinese style reads the registry's Simplified Chinese and its own words", '<html lang="zh-CN">' in zh and "今天有 1 项建议" in zh and "数据到 2026-10-21" in zh
          and "先做这一件" in zh and "Sentence" not in zh and "ask the maker" not in zh, re.findall(r"<h1>.*?</h1>", zh))
    page = daily_page.render(doc([item("a:1", "high")]), say=lambda p: "SAID " + p["message"].upper())
    check("say() replaces the sentence everywhere", "SAID SENTENCE OF DEMO ONE" in page and "Sentence of DEMO one" not in page)


def test_unknown() -> None:
    print("\n[4] what it does not know")
    odd = [item("a:1", "urgent", name="DEMO urgent"), {"id": "a:2", "severity": "high"}, {"severity": "high", **part("no id")}, "not an item", None,
           {**item("a:3", "high", name="DEMO blank"), "message": "  ", "message_code": {"code": "demo_unregistered", "params": {}}},
           item("a:4", "high", name="DEMO answered", last={"answer": "done", "day": "2026-10-20", "note": "fixed"}),
           item("a:5", "high", name="DEMO open")]
    page = daily_page.render(doc(odd))
    clean(page)
    data = data_of(page)
    check("what cannot be said is left out and counted, the rest is drawn, most severe first",
          data["left_out"] == 5 and [i["id"] for i in data["items"]] == ["a:4", "a:5", "a:1"], data)
    got = {i["id"]: i for i in data["items"]}
    check("an unknown severity reads as info", got["a:1"]["severity"] == "info" and got["a:1"]["state"] == "untested")
    check("an answered item is closed and says what was reported", got["a:4"]["state"] == "closed" and "Reported 2026-10-20: “done” — fixed" in page)
    check("the decision is the open item, not the answered one", "shop import action --market DEMO --item a:5 --answer done" in pagestyle.zones(page)["decision"]
          and "--item a:4" not in pagestyle.zones(page)["decision"])
    allgone = daily_page.render(doc([item("a:4", "high", last={"answer": "declined", "day": "2026-10-20", "note": ""})]))
    clean(allgone)
    z = pagestyle.zones(allgone)
    check("nothing open: the decision says so and has no copy button", "No suggestion is open" in z["decision"] and z["copies"] == [] and "Nothing to decide today" in z["decision"])
    nocmd = {**item("a:6", "high"), "report": None}
    page = daily_page.render(doc([nocmd]))
    clean(page)
    check("an item without a report command is the decision without a button", pagestyle.zones(page)["copies"] == [] and "Sentence of DEMO one" in pagestyle.zones(page)["decision"])
    solved = daily_page.render(doc([item("a:1")], solved=[{"item": "move:999", "answer": "declined", "day": "2026-10-19", "note": ""}]))
    clean(solved)
    check("a solved item sits in the owner's fold, its id in code", "move:999" in pagestyle.zones(solved)["tech"] and "move:999" not in pagestyle.zones(solved)["rest"]
          and "2026-10-19: “declined”, no longer comes up" in solved)


def test_nothing() -> None:
    print("\n[5] nothing today")
    page = daily_page.render(doc([], held=0, followed_text=None))
    clean(page)
    check("the empty page says so, with no rows and no copy button", "Nothing to do today" in page and 'class="row"' not in page and pagestyle.zones(page)["copies"] == [])
    bare = daily_page.render({"items": []})
    clean(bare)
    check("a document with nothing but an empty list still draws", "Nothing to decide today" in bare)


def test_module() -> None:
    print("\n[6] escaped, and the module's place")
    evil = '<script>alert(1)</script> "&'
    page = daily_page.render(doc([item("a:1", "high", name=evil, text=evil, steps=[evil], doubt=[evil], evidence=part(evil))], notes=[evil], note_codes=[part(evil)["message_code"]]))
    check("every text is escaped", "<script>alert(1)" not in page and page.count("<script") == 2, page.count("<script"))
    clean(page)
    src = (Path(daily_page.__file__)).read_text("utf-8")
    table = packs.table(_shop.KIT)
    deps = packs.imports(src, set(table))
    check("it is in pack pages and imports only base and pages", table.get("daily_page") == "pages" and all(table[d] in ("base", "pages") for d in deps), sorted(deps))
    check("it does not import kit.daily", "daily" not in deps)
    words = " ".join(list(daily_page.WORDS_EN.values()) + list(daily_page.WORDS_ZH.values()) + list(daily_page.STATES_EN.values()))
    check("no platform or pack named in the module or its words", not [w for w in ("smartly", "meta ", "tiktok", "vads", "adcut", "video-ads") if w in (src + words).lower().replace("video-ads skill pack", "")],
          "a name")
    check("both word sets hold the same keys", set(daily_page.WORDS_EN) == set(daily_page.WORDS_ZH))


def main() -> int:
    _shop.use()
    for fn in (test_real, test_warnings, test_words, test_unknown, test_nothing, test_module):
        fn()
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
