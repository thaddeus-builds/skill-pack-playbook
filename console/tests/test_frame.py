"""frame.py and the shared frame in pages.py: a skill pack's page document in, one page out, inside the
same top bar as the console's own pages. Pure (no folder, no process), in both languages; the served half
is test_frame_serve.py. Everything a skill pack writes is escaped, and a block that is not valid is left
out and counted, never allowed to hide the rest.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import _t  # noqa: E402
import core  # noqa: E402
import frame  # noqa: E402
import i18n  # noqa: E402
import manifest  # noqa: E402
import pages  # noqa: E402
from test_pages import Doc, Log, ctx, full_log  # noqa: E402

XSS = '<script>alert("x")</script>&"\''
BUTTON = {"type": "button", "label": "Confirm delivery", "verb": ["queue", "approve"],
          "expect": {"verb": "queue approve", "items": {"batch": "n7"}}, "effect": "Sends 3 clips to the client."}
TAB = {"name": "space", "title": {"en": "Space", "zh": "空间"}}
NAV = [{"name": "waiting", "href": "./"}, {"name": "space", "href": "page-space", "title": "Space", "count": 4},
       {"name": "history", "href": "history"}]
ALLOWED = [["queue", "approve"]]


def page(blocks, count=None, lang="en", relay=ALLOWED, **over):
    cleaned = frame.clean({"blocks": blocks, **({"count": count} if count is not None else {})})
    return Doc(frame.render_page(Log().state(), ctx(lang, relay=relay, nav=NAV, **over), TAB, cleaned)), cleaned


def test_every_block_type_is_drawn_and_the_bad_ones_are_counted_not_fatal():
    blocks = [{"type": "heading", "text": "Next batch"}, {"type": "text", "text": "Line one.\nLine two."},
              {"type": "facts", "items": [{"label": "Rows", "value": "12"}, {"label": "Empty", "value": ""}]},
              {"type": "table", "caption": "Rows", "columns": ["Row", "Cells"], "rows": [["N7", 3], ["N5", "2"]]},
              {"type": "link", "text": "Source", "url": "https://example.com/a?x=1&y=2"},
              {"type": "details", "summary": "More", "blocks": [{"type": "text", "text": "Folded."}]},
              {"type": "card", "title": "Deliver", "blocks": [{"type": "text", "text": "Inside."}]},
              {"type": "blink", "text": "x"}, {"type": "text"}, "text", {"type": "facts", "items": []},
              {"type": "table", "columns": ["a"], "rows": [["1", "2"]]}]
    d, cleaned = page(blocks, count=3)
    assert cleaned["count"] == 3 and len(cleaned["blocks"]) == 7 and len(cleaned["bad"]) == 5, cleaned["bad"]
    main = d.main
    assert main.find("h1").text() == "Space" and main.find("h2").text() == "Next batch"
    assert "Line one.\nLine two." in "".join(main.find("p", cls="txt").texts())
    assert [f.text() for f in main.find_all("li", cls="fact")] == ["Rows 12", "Empty"]
    assert main.find("table").find_all("td")[1].text() == "3" and "num" in main.find("table").find_all("td")[1].classes
    a = main.find("a", cls="src")
    assert a.attrs["href"] == "https://example.com/a?x=1&y=2" and a.attrs["rel"] == "noopener noreferrer"
    assert main.find("details", cls="more").find("summary").text() == "More"
    assert main.find("details", cls="ask").attrs.get("open") is not None and "Inside." in main.text()
    assert main.find("p", cls="banner").text() == i18n.t("page.bad_blocks", "en", n=5)
    z, _ = page(blocks, lang="zh")
    assert z.main.find("h1").text() == "空间" and z.main.find("p", cls="banner").text() == i18n.t("page.bad_blocks", "zh", n=5)


def test_what_a_skill_pack_writes_is_escaped_and_only_an_http_link_is_a_link():
    blocks = [{"type": "heading", "text": XSS}, {"type": "text", "text": XSS},
              {"type": "facts", "items": [{"label": XSS, "value": XSS}]},
              {"type": "table", "caption": XSS, "columns": [XSS], "rows": [[XSS]]},
              {"type": "details", "summary": XSS, "blocks": [{"type": "text", "text": XSS}]},
              {"type": "card", "title": XSS, "blocks": []},
              {"type": "link", "text": XSS, "url": 'https://example.com/"><script>x</script>'},
              {"type": "link", "text": "bad", "url": "javascript:alert(1)"}]
    out = frame.render_page(Log().state(), ctx(nav=NAV), TAB, frame.clean({"blocks": blocks}))
    assert "<script>alert" not in out and "<script>x" not in out and out.count("&lt;script&gt;alert") >= 7
    d = Doc(out)
    assert d.main.find_all("a", cls="src") == []                                      # neither is a link
    assert "javascript:" not in "".join(a.attrs.get("href", "") for a in d.find_all("a"))
    assert "bad" in d.main.text()                                                     # shown as plain text instead


def test_blocks_are_limited_in_size_count_and_depth():
    long = "x" * 2001
    assert frame.clean({"blocks": [{"type": "text", "text": long}]})["bad"] == ["bad_text"]
    assert frame.clean({"blocks": [{"type": "text", "text": "x" * 2000}]})["bad"] == []
    deep = {"type": "text", "text": "leaf"}
    for _ in range(frame.MAX_DEPTH):                                                   # one more than the page may nest
        deep = {"type": "details", "summary": "d", "blocks": [deep]}
    got = frame.clean({"blocks": [deep]})
    assert "bad_nesting" in got["bad"] and frame.clean({"blocks": [{"type": "details", "summary": "d", "blocks": [
        {"type": "details", "summary": "e", "blocks": [{"type": "text", "text": "ok"}]}]}]})["bad"] == []
    many = frame.clean({"blocks": [{"type": "text", "text": "t"}] * (frame.MAX_BLOCKS + 5)})
    assert len(many["blocks"]) == frame.MAX_BLOCKS and many["bad"] == ["too_many"] * 5
    assert frame.clean({"blocks": [{"type": "table", "columns": list("abcdefg"), "rows": []}]})["bad"] == ["bad_table"]
    assert frame.clean({"blocks": [{"type": "table", "columns": ["a"], "rows": [["1"]] * 31}]})["bad"] == ["bad_table"]
    for doc in (None, [], "page", 3):
        assert frame.clean(doc) == {"count": None, "blocks": [], "bad": ["not_a_page"]}
    assert frame.clean({})["bad"] == ["no_blocks"]
    for n, want in ((0, 0), (7, 7), (-1, None), (True, None), ("3", None), (1.5, None), (10 ** 6, None)):
        assert frame.clean({"blocks": [], "count": n})["count"] == want, n


def test_a_button_is_a_form_that_names_the_page_and_a_hash_and_nothing_the_console_holds():
    d, cleaned = page([{"type": "card", "title": "Deliver", "blocks": [BUTTON]}])
    form = d.main.find("form", cls="act")
    assert form.attrs["method"] == "post" and form.attrs["action"] == "act"
    fields = {i.attrs["name"]: i.attrs["value"] for i in form.find_all("input")}
    (h, b), = frame.buttons("space", cleaned).items()
    assert fields == {"token": "tok123", "page": "space", "hash": h} and b["label"] == "Confirm delivery"
    assert form.find("button").text() == "Confirm delivery"
    for held in ("queue approve", "batch", '"verb"', "n7"):                           # the gate words are in the folded box at most
        assert held not in "".join(str(v) for v in fields.values()), held
    assert d.main.find("p", cls="effect").text().endswith("Sends 3 clips to the client.")
    tech = d.main.find("details", cls="tech")                                          # what exactly gets written, folded (U11)
    assert "queue approve" in tech.text() and "batch" in tech.text() and "n7" in tech.text()
    z, _ = page([BUTTON], lang="zh")
    assert z.main.find("p", cls="effect").text().startswith(i18n.t("effect.lead", "zh"))


def test_the_hash_names_exactly_what_was_shown_and_changes_with_any_of_it():
    def h(**over):
        c = frame.clean({"blocks": [{**BUTTON, **over}]})
        (k,), = [list(frame.buttons("space", c))]
        return k
    base = h()
    assert base == h() and len(base) == 32
    for over in ({"label": "Deliver"}, {"effect": "Sends 4 clips."}, {"verb": ["queue", "approve", "x"]},
                 {"expect": {"verb": "queue approve", "items": {"batch": "n5"}}}, {"market": "us"}):
        assert h(**over) != base, over
    c = frame.clean({"blocks": [BUTTON]})
    assert next(iter(frame.buttons("other", c))) != base                              # and the page it is on
    where = frame.clean({"blocks": [{"type": "card", "title": "x", "blocks": [BUTTON]}]})
    assert base in frame.buttons("space", where)                                       # not where it sits


def test_a_button_whose_gate_is_not_well_formed_is_left_out_with_the_rest_of_the_page_intact():
    bad = [{**BUTTON, "verb": []}, {**BUTTON, "verb": ["-x"]}, {**BUTTON, "expect": {}}, {**BUTTON, "value_arg": True},
           {**BUTTON, "label": ""}, {**BUTTON, "label": "x" * 41}, {**BUTTON, "effect": "x" * 201}, {**BUTTON, "colour": "red"},
           {**BUTTON, "market": "has space"}]
    c = frame.clean({"blocks": bad + [{"type": "text", "text": "still here"}]})
    assert c["bad"] == ["bad_button"] * len(bad) and [b["type"] for b in c["blocks"]] == ["text"]
    assert frame.clean({"blocks": [{**BUTTON, "market": "us"}]})["bad"] == []
    assert frame.clean({"blocks": [{k: v for k, v in BUTTON.items() if k != "effect"}]})["bad"] == []


def test_a_button_is_drawn_as_a_form_only_for_a_verb_the_relay_allows_and_only_for_a_person():
    d, _ = page([BUTTON], relay=ALLOWED)
    assert d.main.find("form", cls="act") is not None
    for relay in (None, [], [["facts", "confirm"]], [["queue", "approve", "n7"]]):
        d, _ = page([BUTTON], relay=relay)
        assert d.main.find("form") is None and d.main.find("button") is None, relay
        assert d.main.find("p", cls="banner").text() == i18n.t("btn.norelay", "en", label="Confirm delivery")
        assert "Sends 3 clips" in d.main.text()                                        # the person still reads what it would do
    assert page([BUTTON], relay=[["queue"]])[0].main.find("form") is not None          # a shorter prefix allows it
    d, _ = page([BUTTON], user=None)
    assert d.main.find("form") is None and d.main.find("button") is None and d.main.find("p", cls="banner").text() == i18n.t("ro.banner", "en")


def test_a_page_the_skill_pack_could_not_draw_says_so_and_still_has_the_frame():
    out = frame.render_page(Log().state(), ctx(nav=NAV), TAB, None, "The skill pack is down.")
    d = Doc(out)
    assert i18n.t("err.page_unavailable", "en") in d.main.text() and "The skill pack is down." in d.main.text()
    assert d.find("nav", cls="tabs") is not None and d.main.find("h1").text() == "Space"
    quiet = Doc(frame.render_page(Log().state(), ctx(nav=NAV), TAB, None))
    assert "The skill pack said" not in quiet.main.text()
    empty, _ = page([])
    assert i18n.t("page.empty", "en") in empty.main.text()


def test_the_top_bar_lists_the_pages_in_order_marks_the_current_one_and_counts_the_waiting_tab():
    st = full_log().state()
    n = len(core.open_asks(st))
    d = Doc(pages.render_inbox(st, ctx(nav=NAV, blocking=2)))
    tabs = d.find("nav", cls="tabs").find_all("a")
    assert [a.attrs["href"] for a in tabs] == ["./", "page-space", "history"]
    assert [a.text() for a in tabs] == [f"{i18n.t('nav.waiting', 'en')} {n + 2}", "Space 4", i18n.t("nav.history", "en")]
    assert [a.attrs.get("aria-current") for a in tabs] == ["page", None, None]
    on = Doc(frame.render_page(st, ctx(nav=NAV), TAB, frame.clean({"blocks": []})))
    assert [a.attrs.get("aria-current") for a in on.find("nav", cls="tabs").find_all("a")] == [None, "page", None]
    his = Doc(pages.render_history(st, ctx(nav=NAV)))
    assert [a.attrs.get("aria-current") for a in his.find("nav", cls="tabs").find_all("a")] == [None, None, "page"]
    z = Doc(pages.render_inbox(st, ctx("zh", nav=NAV)))
    assert [a.text() for a in z.find("nav", cls="tabs").find_all("a")][1:] == ["Space 4", i18n.t("nav.history", "zh")]


def test_a_console_without_pages_of_its_own_still_has_waiting_and_history_as_before():
    st = full_log().state()
    d = Doc(pages.render_inbox(st, ctx()))
    assert [a.attrs["href"] for a in d.find("nav", cls="tabs").find_all("a")] == ["./", "history"]
    assert d.find("nav", cls="tabs").find_all("a")[0].find("span", cls="count").text() == str(len(core.open_asks(st)))


def test_the_budget_line_and_meter_follow_the_manifests_number():
    st = full_log().state()
    n = len(core.open_asks(st))
    d = Doc(pages.render_inbox(st, ctx(max_open=n + 3)))
    assert d.find("p", cls="sub").text() == i18n.t("budget.line", "en", open=n, max=n + 3)
    assert len(d.find("span", cls="meter").find_all("b")) == n and len(d.find("span", cls="meter").find_all("i")) == 3
    tight = Doc(pages.render_inbox(st, ctx(max_open=2)))
    assert "over" in tight.find("span", cls="meter").classes
    assert n <= core.MAX_OPEN
    assert Doc(pages.render_inbox(st, ctx())).find("p", cls="sub").text() == i18n.t("budget.line", "en", open=n, max=core.MAX_OPEN)


def test_the_nav_the_console_builds_from_a_manifest_has_every_page_once():
    m = manifest.parse({"version": 1, "cmd": ["x"], "pages": [
        {"name": "space", "title": {"en": "Space", "zh": "空间"}, "order": 20, "verb": ["p", "space"]}]})
    assert [t["name"] for t in manifest.nav(m)] == ["waiting", "space", "history"]


if __name__ == "__main__":
    _t.main(globals())
