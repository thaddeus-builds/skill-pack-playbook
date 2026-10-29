"""A skill pack's page, drawn inside the console's frame. Pure: a page document
in, one HTML document out (the frame, the top navigation, the tech look (light on `data-theme="light"`), the
375 px layout and the safety headers are pages.py's and serve.py's, shared by
every page); no I/O, no process, no clock.

The skill pack's page verb prints ONE JSON object (see manifest.py for how a
page is declared):

    {"count": 3,                                   # optional: the tab's number
     "blocks": [
       {"type": "heading", "text": "Next batch"},
       {"type": "text", "text": "One paragraph, shown as written."},
       {"type": "facts", "items": [{"label": "Rows", "value": "12"}]},
       {"type": "table", "caption": "…", "columns": ["a", "b"], "rows": [["1", "2"]]},
       {"type": "link", "text": "Source", "url": "https://example.com/x"},
       {"type": "details", "summary": "More", "blocks": [ … ]},      # folded
       {"type": "card", "title": "Deliver 3 clips", "blocks": [ … ]}, # a box that opens
       {"type": "button", "label": "Confirm delivery",
        "verb": ["parcel", "release"], "expect": {"items": {"batch": "n7"}},
        "effect": "Sends 3 clips to the client.", "market": "us"}
     ]}

Everything the skill pack writes is shown as text, escaped; the only link is an
http(s) one. A block that is not valid is left out and the page says how many
were, so one bad block never hides the rest; a page that is not an object, or
whose command failed, is a page of its own that says it could not be drawn.
`details` and `card` nest to a depth of 3.

A `button` is a gate the person can click: `verb`, `expect`, `market` mean what
they mean in an ask's gate (core.check_gate; a button has no value, so no
`value_arg`), `effect` is what it will do, in plain words. The form carries only
the page name and the button's hash (core.subject_hash of what was shown); the
verb, the payload and the gate words stay with the console, which draws the page
again at the click and runs a button only if it is still there, unchanged. A
button whose verb is not in the manifest's relay_verbs is drawn as a plain
sentence saying so, never as a form.
"""

from __future__ import annotations

import core
import i18n
import pages

MAX_BLOCKS, MAX_DEPTH = 300, 3
BLOCK_LIMITS = {"heading": 120, "text": 2000, "label": core.LIMITS["label"], "value": core.LIMITS["value"],
                "items": 30, "title": core.LIMITS["title"], "effect": core.LIMITS["effect"],
                "cell": core.LIMITS["cell"], "columns": core.LIMITS["columns"], "rows": core.LIMITS["rows"]}
TYPES = ("heading", "text", "facts", "table", "link", "details", "card", "button")


def _str(x, limit, required=True):
    if not isinstance(x, str) or (required and not x.strip()):
        return None
    x = x.strip()
    return x if len(x) <= limit else None


def _block(b, depth: int, bad: list, left: list):
    """One block, checked and normalised, or None (and `bad` told why)."""
    def no(why):
        bad.append(why)
        return None
    left[0] -= 1
    if left[0] < 0:
        return no("too_many")
    if not isinstance(b, dict) or b.get("type") not in TYPES:
        return no("unknown_type")
    typ, lim = b["type"], BLOCK_LIMITS
    if typ in ("heading", "text"):
        s = _str(b.get("text"), lim[typ])
        return {"type": typ, "text": s} if s else no("bad_text")
    if typ == "facts":
        items = b.get("items")
        if not (isinstance(items, list) and 1 <= len(items) <= lim["items"]):
            return no("bad_items")
        out = []
        for it in items:
            k = _str(it.get("label"), lim["label"]) if isinstance(it, dict) else None
            v = _str(it.get("value"), lim["value"], required=False) if isinstance(it, dict) else None
            if k is None or v is None:
                return no("bad_items")
            out.append({"label": k, "value": v})
        return {"type": "facts", "items": out}
    if typ == "table":
        cols, rows, cap = b.get("columns"), b.get("rows"), b.get("caption")
        ok = (isinstance(cols, list) and 1 <= len(cols) <= lim["columns"] and isinstance(rows, list)
              and len(rows) <= lim["rows"] and all(isinstance(c, str) and c and len(c) <= lim["cell"] for c in cols)
              and all(isinstance(r, list) and len(r) == len(cols)
                      and all(isinstance(c, (str, int, float)) and not isinstance(c, bool) and len(str(c)) <= lim["cell"]
                              for c in r) for r in rows)
              and (cap is None or _str(cap, core.LIMITS["caption"]) is not None))
        return ({"type": "table", "caption": cap, "columns": cols, "rows": [[str(c) for c in r] for r in rows]}
                if ok else no("bad_table"))
    if typ == "link":
        s = _str(b.get("text"), lim["label"] * 2)
        return {"type": "link", "text": s, "url": b.get("url")} if s and isinstance(b.get("url"), str) else no("bad_text")
    if typ in ("details", "card"):
        key = "summary" if typ == "details" else "title"
        s = _str(b.get(key), lim["title"])
        inner = b.get("blocks")
        if s is None or not isinstance(inner, list) or depth >= MAX_DEPTH:
            return no("bad_nesting" if depth >= MAX_DEPTH else "bad_text")
        kids = [k for k in (_block(x, depth + 1, bad, left) for x in inner) if k]
        return {"type": typ, key: s, "blocks": kids}
    return _button(b, no)


def _button(b: dict, no):
    label, effect = _str(b.get("label"), BLOCK_LIMITS["label"]), b.get("effect")
    if label is None or (effect is not None and _str(effect, BLOCK_LIMITS["effect"]) is None):
        return no("bad_button")
    raw = {k: b[k] for k in ("verb", "expect", "market") if k in b}
    if set(b) - {"type", "label", "effect", "verb", "expect", "market"}:
        return no("bad_button")
    gate, errs = core.check_gate(raw, "approve")
    if gate is None or errs:
        return no("bad_button")
    return {"type": "button", "label": label, "effect": effect.strip() if effect else None, "gate": gate}


def clean(doc) -> dict:
    """The page document as it will be drawn: {count, blocks, bad} where `bad` is
    why each left-out block was left out (codes). Never raises."""
    bad: list = []
    if not isinstance(doc, dict):
        return {"count": None, "blocks": [], "bad": ["not_a_page"]}
    raw = doc.get("blocks")
    left = [MAX_BLOCKS]
    blocks = [k for k in (_block(x, 1, bad, left) for x in raw) if k] if isinstance(raw, list) else []
    if not isinstance(raw, list):
        bad.append("no_blocks")
    n = doc.get("count")
    count = n if isinstance(n, int) and not isinstance(n, bool) and 0 <= n < 10 ** 6 else None
    return {"count": count, "blocks": blocks, "bad": bad}


def _walk(blocks):
    for b in blocks:
        yield b
        if "blocks" in b:
            yield from _walk(b["blocks"])


def buttons(page: str, cleaned: dict) -> dict:
    """hash -> button, for every button of the page. The hash is what a click names."""
    out = {}
    for b in _walk(cleaned["blocks"]):
        if b["type"] == "button":
            out[button_hash(page, b)] = b
    return out


def button_hash(page: str, b: dict) -> str:
    return core.subject_hash({"page": page, "label": b["label"], "effect": b["effect"], "gate": b["gate"]})


def button_ask(page: str, b: dict) -> dict:
    """The ask-shaped thing relay.run takes: a yes/no approval of the button's gate."""
    return {"id": "page-" + page, "step": "approve", "title": b["label"], "gate": b["gate"]}


# ------------------------------------------------------------- drawing --

def _render(t, ctx: dict, page: str, blocks: list, relay_verbs) -> str:
    return "".join(_one(t, ctx, page, b, relay_verbs) for b in blocks)


def _one(t, ctx: dict, page: str, b: dict, relay_verbs) -> str:
    e = pages._e
    typ = b["type"]
    if typ == "heading":
        return f'<h2>{e(b["text"])}</h2>'
    if typ == "text":
        return f'<p class="txt">{e(b["text"])}</p>'
    if typ == "facts":
        lis = "".join(f'<li class="fact"><span class="k">{e(i["label"])}</span> <span class="v">{e(i["value"])}</span></li>'
                      for i in b["items"])
        return f'<ul class="facts">{lis}</ul>'
    if typ == "table":
        return pages._table(t, {"caption": b["caption"], "columns": b["columns"], "rows": b["rows"]})
    if typ == "link":
        u = pages._safe(b["url"])
        if not u:
            return f'<p class="txt">{e(b["text"])}</p>'
        return (f'<p><a class="src" href="{e(u)}" target="_blank" rel="noopener noreferrer">{e(b["text"])}</a></p>')
    if typ == "details":
        return (f'<details class="more"><summary>{e(b["summary"])}</summary>'
                f'<div>{_render(t, ctx, page, b["blocks"], relay_verbs)}</div></details>')
    if typ == "card":
        return (f'<details class="ask" open><summary><span class="ttl">{e(b["title"])}</span></summary>'
                f'<div class="inner">{_render(t, ctx, page, b["blocks"], relay_verbs)}</div></details>')
    return _button_html(t, ctx, page, b, relay_verbs)


def _button_html(t, ctx: dict, page: str, b: dict, relay_verbs) -> str:
    e = pages._e
    if not pages._decides(ctx):
        return ""
    effect = f'<p class="effect"><b class="lead">{t("effect.lead")}</b> {e(b["effect"])}</p>' if b["effect"] else ""
    if not core.verb_allowed(relay_verbs, b["gate"]["verb"]):
        return f'{effect}<p class="banner">{t("btn.norelay", label=b["label"])}</p>'
    hidden = "".join(f'<input type="hidden" name="{n}" value="{e(v)}">'
                     for n, v in (("token", ctx.get("token")), ("page", page), ("hash", button_hash(page, b))))
    tech = pages._tech(t, {"gate": b["gate"], "step": "approve"})
    return (f'{effect}{tech}<form class="answer act" method="post" action="act" autocomplete="off">{hidden}'
            f'<button class="btn primary" type="submit">{e(b["label"])}</button></form>')


def render_page(st: dict, ctx: dict, tab: dict, cleaned: dict | None, failure: str = "") -> str:
    """The page `tab` (manifest.nav's entry) inside the frame. `cleaned` is clean()'s
    result, or None when the skill pack could not draw it (`failure` says why, in its words)."""
    t = pages._T(pages._lang(ctx))
    title = (tab["title"] or {}).get(t.lang) or tab["name"]
    head = f'<div class="head"><h1>{pages._e(title)}</h1></div>'
    if cleaned is None:
        body = (f'{head}<div class="res bad"><p>{t("err.page_unavailable")}</p>'
                + (f'<p class="txt">{t("result.refused", message=failure)}</p>' if failure else "") + "</div>")
    else:
        warn = (f'<p class="banner">{t("page.bad_blocks", n=len(cleaned["bad"]))}</p>' if cleaned["bad"] else "")
        empty = "" if cleaned["blocks"] else f'<div class="empty"><p class="big">{t("page.empty")}</p></div>'
        body = head + warn + _render(t, ctx, tab["name"], cleaned["blocks"], ctx.get("relay") or []) + empty
    return pages._shell(ctx, t, title=pages._e(title), body=body, tab=tab["name"], st=st, ro=True)
