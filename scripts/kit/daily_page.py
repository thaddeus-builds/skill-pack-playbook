"""The day's advice as one page a person reads: the items of a pack's day (and with them the audit's findings) drawn over kit.pagestyle.

`render(doc)` takes the document `kit.daily.build()` returns and gives back one HTML document that passes `pagestyle.problems()`: number tiles and the status
bar first, the one decision (the first open item of the most severe kind, with the command that reports back and the hint where to paste it), at most three
warnings, one row per item that unfolds into its card, and the owner's fold last. It reads nothing, writes nothing and runs nothing; it decides nothing: the
sentences are the items' own coded messages, never worded here.

It does not import `kit.daily` (that is pack `ads-core`; this module is pack `pages`, which imports only `base` and itself). The shape of the plain dicts is
the contract. Keys not listed are ignored; a part that is absent is empty:

    doc    items [item], solved [{item, answer, day, note}], notes [str] and note_codes [{code, params}] (the same order), followed_text {message,
           message_code}, held int, market, as_of, currency
    item   id str (audit:<finding>, campaign:<action>:<id>, move:<id>, request:creatives; shown only in the card's fold), layer 1 | 2 | 3,
           severity high | medium | info, message + message_code (its sentence), evidence {message, message_code} | None, steps [{message, message_code}],
           doubt [{message, message_code}], subject {name}, report str (the command that reports back), last None | {answer, day, note}

A sentence is the registry's meaning for the code and its params in the page's language (`meaning_zh` for a zh lang, else `meaning_en`; the kit ships
English and Simplified Chinese only, ROADMAP R7), else the item's own `message`. `say(part)` replaces that for a pack with its own words (Traditional
Chinese, say). An item the page cannot say (not a mapping, no id, no sentence) is left out and counted in the page data's `left_out`, as `kit.daily` leaves
out a doubt it does not know; a severity it does not know reads as `info`.

Severity is the state: high is `down`, medium `testing`, info `untested`, and an item somebody has reported on is `closed`. The state words are the pack's
(`Style`): `EN_STYLE` and `ZH_STYLE` give them as severity words ("do first", "worth doing", "for reference", "answered"); a pack that passes its own `style`
sets `state_down`, `state_testing`, `state_untested` and `state_closed` to its own words. Every other word of the page is `WORDS_EN` or `WORDS_ZH` with the
pack's `words` laid over it; `words()` refuses an unknown key, an empty word, a template without its placeholder, naming the key. Money is not formatted
here: a sentence carries its own numbers, in the currency the document names (shown in the page's first line).

From the video-ads skill pack (`scripts/_lib/daily_page.py` and `audit_page.py`, cut from its main; the cards, the severity words and the owner's fold are
theirs; its Traditional Chinese, its platform names and its structure table stay there) and the weekly page design of the next ads skill pack (ROADMAP X11).

Test: kit/tests/test_daily_page.py.
"""

from __future__ import annotations

from typing import Callable, Mapping

from kit import messages, pagestyle
from kit.config import ConfigError
from kit.pagestyle import Style

RANK = {"high": 0, "medium": 1, "info": 2}
STATE_OF = {"high": "down", "medium": "testing", "info": "untested"}
LAYERS = (1, 2, 3)
ANSWERS = ("done", "declined", "later")
CUT = 90                                              # characters of a sentence kept in a row's title
TEMPLATES = {"as_of": "{day}", "headline": "{n}", "held": "{n}", "reported": "{day}", "solved_line": "{day}"}

WORDS_EN = {
    "title": "Today's actions", "as_of": "data to {day}", "headline": "{n} suggestions today", "headline_none": "Nothing to do today",
    "tile_items": "Suggestions", "tile_answered": "Answered", "tile_answered_small": "the report is on each card",
    "tile_solved": "Solved", "tile_solved_small": "reported, and no longer coming up",
    "rows_title": "Suggestion by suggestion",
    "layer_1": "Creatives", "layer_2": "Campaigns and account", "layer_3": "Budget",
    "decision_title": "Do this first", "decision_none_title": "Nothing to decide today",
    "decision_none": "No suggestion is open. Read the cards below, or come back after the next pull.",
    "report_hint": "When it is done, paste this in a terminal to report back. Say declined or later in place of done if that is the answer.",
    "evidence": "Why", "left_out": "What it leaves out", "steps": "Steps",
    "not_reported": "Nobody has reported on this yet.", "reported": "Reported {day}: “{answer}”",
    "answer_done": "done", "answer_declined": "declined", "answer_later": "later",
    "held": "{n} more stay put today: not enough evidence, or still cooling down.",
    "solved_title": "Reported, and gone from the list", "solved_line": "{day}: “{answer}”, no longer comes up",
    "readonly": "This page decides nothing and changes nothing: make the change where the account is managed, report it with the command above, "
                "and read the page again after the next pull.",
}
WORDS_ZH = {
    "title": "每日行动", "as_of": "数据到 {day}", "headline": "今天有 {n} 项建议", "headline_none": "今天没有要做的事",
    "tile_items": "建议", "tile_answered": "已回报", "tile_answered_small": "回报写在每张卡片上",
    "tile_solved": "已解决", "tile_solved_small": "回报过、现在不再出现",
    "rows_title": "逐项看",
    "layer_1": "素材", "layer_2": "广告系列与账户", "layer_3": "预算",
    "decision_title": "先做这一件", "decision_none_title": "今天没有要决定的事",
    "decision_none": "没有待处理的建议。可以看下面的卡片，或下次拉取数据后再来。",
    "report_hint": "做完后把它贴到终端里回报；如果答案是不做或以后再说，把 done 换成 declined 或 later。",
    "evidence": "依据", "left_out": "没算进去的", "steps": "步骤",
    "not_reported": "还没有人回报。", "reported": "{day} 回报：“{answer}”",
    "answer_done": "已完成", "answer_declined": "不做", "answer_later": "以后再说",
    "held": "另有 {n} 项今天不动：证据不够，或还在冷却。",
    "solved_title": "回报过、已从清单消失", "solved_line": "{day}：“{answer}”，现在不再出现",
    "readonly": "这一页只用来看，不改动任何东西：请在管理账户的地方做调整，用上面的命令回报，下次拉取数据后再回来看。",
}
STATES_EN = {"state_untested": "for reference", "state_testing": "worth doing", "state_down": "do first", "state_closed": "answered"}
STATES_ZH = {"state_untested": "供参考", "state_testing": "值得处理", "state_down": "要先处理", "state_closed": "已回报"}
EN_STYLE = Style(STATES_EN)
ZH_STYLE = Style({**pagestyle.ZH, **STATES_ZH}, lang="zh-CN")


def words(over: Mapping[str, str] | None = None, *, zh: bool = False) -> dict[str, str]:
    """The page's words: `WORDS_ZH` (zh) or `WORDS_EN` with `over` laid over it. ValueError, naming the key: an unknown key, a word that is not a
    non-empty string, a template without its placeholder (`{day}` or `{n}`)."""
    base = WORDS_ZH if zh else WORDS_EN
    if over is not None and not isinstance(over, Mapping):
        raise ValueError(f"daily_page words: a mapping of key -> word, not {type(over).__name__}")
    out = dict(base)
    for k, v in (over or {}).items():
        if k not in base:
            raise ValueError(f"daily_page words: unknown key {k!r} (the keys: {', '.join(base)})")
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"daily_page words: {k} must be a word, not {v!r}")
        out[k] = v
    for k, holder in TEMPLATES.items():
        if holder not in out[k]:
            raise ValueError(f"daily_page words: {k} must hold {holder}: {out[k]!r}")
    return out


# ---- the sentences

def _meaning(lang: str) -> str:
    return "zh" if lang.lower().startswith("zh") else "en"


def _plain(v, meaning: str):
    """A message param as the text a sentence takes: a nested message says itself, a list is joined, a number stays a number."""
    if isinstance(v, Mapping) and "code" in v:
        return _say({"message": "", "message_code": v}, meaning)
    if isinstance(v, (list, tuple)):
        return ", ".join(str(_plain(x, meaning)) for x in v)
    return v


def _say(part: Mapping, meaning: str) -> str:
    """The sentence of `part` ({message, message_code}): the registry's meaning filled with the params, else the message it came with."""
    code = part.get("message_code") or {}
    try:
        row = messages.registry().get(code.get("code"))
    except ConfigError:                                # no skill pack is bound: the page still reads from what the items carry
        row = None
    text = row and (row.get(f"meaning_{meaning}") or row.get("meaning_en"))
    if text:
        try:
            return text.format(**{k: _plain(v, meaning) for k, v in (code.get("params") or {}).items()})
        except (KeyError, IndexError, ValueError, TypeError):
            pass
    return str(part.get("message") or "")


def _cut(text: str, n: int = CUT) -> str:
    return text if len(text) <= n else text[:n].rstrip() + "…"


# ---- the page

def _items(doc: Mapping, say: Callable[[Mapping], str]) -> tuple[list[dict], int]:
    """([the items that can be drawn, each with its sentence, most severe first], how many were left out)."""
    out, left = [], 0
    for raw in doc.get("items") or []:
        ident = raw.get("id") if isinstance(raw, Mapping) else None
        sentence = say(raw).strip() if isinstance(ident, str) and ident else ""
        if not sentence:
            left += 1
            continue
        sev = raw.get("severity") if raw.get("severity") in RANK else "info"
        last = raw.get("last") if isinstance(raw.get("last"), Mapping) else None
        out.append({"raw": raw, "id": ident, "severity": sev, "layer": raw.get("layer") if raw.get("layer") in LAYERS else 9,
                    "text": sentence, "last": last, "state": "closed" if last else STATE_OF[sev]})
    out.sort(key=lambda i: (RANK[i["severity"]], i["layer"]))      # stable: the composer's order inside a kind stands
    return out, left


def _parts(raw: Mapping, key: str) -> list[Mapping]:
    return [p for p in raw.get(key) or [] if isinstance(p, Mapping)]


def _reported(i: dict, w: dict[str, str]) -> str:
    last = i["last"]
    if not last:
        return w["not_reported"]
    answer = w.get(f"answer_{last.get('answer')}", str(last.get("answer") or ""))
    line = w["reported"].replace("{day}", str(last.get("day") or "")).replace("{answer}", answer)
    return f"{line} — {last['note']}" if last.get("note") else line


def render(doc: Mapping, *, style: Style | None = None, words_over: Mapping[str, str] | None = None,
           say: Callable[[Mapping], str] | None = None) -> str:
    """The page of `doc` (the module docstring has its shape), in `style` (default `EN_STYLE`; `ZH_STYLE` is the ready Chinese one). `words_over` are the
    pack's words over the defaults of the style's language (words()); `say(part)` is the sentence of a {message, message_code} part (default: the
    registry's meaning in the style's language)."""
    st = style or EN_STYLE
    zh = _meaning(st.lang) == "zh"
    w = words(words_over, zh=zh)
    e = pagestyle.e

    said = say or (lambda part: _say(part, _meaning(st.lang)))

    items, left = _items(doc, said)
    counts: dict[str, int] = {}
    for i in items:
        counts[i["state"]] = counts.get(i["state"], 0) + 1
    answered = sum(1 for i in items if i["last"])
    solved = [s for s in doc.get("solved") or [] if isinstance(s, Mapping)]
    notes = [said({"message": m, "message_code": c}) for m, c in zip(doc.get("notes") or [], doc.get("note_codes") or [])]
    first = next((i for i in items if not i["last"]), None)

    # the decision: the first open item, its steps and the command that reports back
    if first is None:
        decision = st.decision(w["decision_none_title"], f"<p>{e(w['decision_none'])}</p>")
    else:
        steps = "".join(f"<li>{e(said(s))}</li>" for s in _parts(first["raw"], "steps") if said(s).strip())
        report = first["raw"].get("report")
        decision = st.decision(w["decision_title"], f'<p class="dq">{e(first["text"])}</p>' + (f"<ol>{steps}</ol>" if steps else ""),
                               report if isinstance(report, str) and report.strip() else None, w["report_hint"])

    # warnings: the other open items of the most severe kind, then the document's own notes; three show, the rest sit in the owner's fold
    warned = [i["text"] for i in items if i["severity"] == "high" and not i["last"] and i is not first] + [n for n in notes if n.strip()]
    warning = st.warnings([e(x) for x in warned])

    rows = ""
    for n, i in enumerate(items, 1):
        raw = i["raw"]
        subject = raw.get("subject") if isinstance(raw.get("subject"), Mapping) else {}
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), Mapping) else None
        doubt = [d for d in (said(p) for p in _parts(raw, "doubt")) if d.strip()]
        steps = [s for s in (said(p) for p in _parts(raw, "steps")) if s.strip()]
        note = (f'<p class="note"><b>{e(w["evidence"])}</b> {e(said(evidence))}</p>' if evidence and said(evidence).strip() else "")
        note += (f'<div class="note"><b>{e(w["left_out"])}</b><ul>{"".join(f"<li>{e(d)}</li>" for d in doubt)}</ul></div>' if doubt else "")
        note += (f'<div class="note"><b>{e(w["steps"])}</b><ol>{"".join(f"<li>{e(s)}</li>" for s in steps)}</ol></div>' if steps else "")
        note += f'<p class="note">{e(_reported(i, w))}</p>'
        card = st.card(i["state"], anchor=f"c{n}", head=f"<b>{e(i['text'])}</b>", note=note, tech=f"<code>{e(i['id'])}</code>")
        rows += st.fold_row(i["state"], anchor=f"d{n}", title=str(subject.get("name") or _cut(i["text"])), sub=w.get(f"layer_{i['layer']}", ""), body=card)
    section = (f'<section class="rows"><div class="rowhead"><h2>{e(w["rows_title"])}</h2>{st.expand_all()}</div>{rows}</section>' if rows else "")

    crumb = " · ".join(x for x in (w["title"], str(doc.get("market") or ""), str(doc.get("currency") or ""),
                                   w["as_of"].replace("{day}", str(doc["as_of"])) if doc.get("as_of") else "") if x)
    headline = w["headline"].replace("{n}", str(len(items))) if items else w["headline_none"]
    lead = (f'<section class="space"><div class="eyebrow">{e(crumb)}</div><h1>{e(headline)}</h1></section>'
            + st.tiles([(str(len(items)), w["tile_items"], st.legend_text(counts) or "—"),
                        (str(answered), w["tile_answered"], w["tile_answered_small"]),
                        (str(len(solved)), w["tile_solved"], w["tile_solved_small"])])
            + f'<div class="space">{st.bar(counts, big=True)}{st.legend(counts)}</div>')

    inner = ""
    if len(warned) > pagestyle.WARNINGS_MAX:
        inner += f'<ul>{"".join(f"<li>{e(x)}</li>" for x in warned[pagestyle.WARNINGS_MAX:])}</ul>'
    followed = doc.get("followed_text")
    if isinstance(followed, Mapping) and said(followed).strip():
        inner += f"<p>{e(said(followed))}</p>"
    if isinstance(doc.get("held"), int) and doc["held"] > 0:
        inner += f"<p>{e(w['held'].replace('{n}', str(doc['held'])))}</p>"
    if solved:
        lines = "".join(f"<li><code>{e(s.get('item'))}</code> · "
                        f"{e(w['solved_line'].replace('{day}', str(s.get('day') or '')).replace('{answer}', w.get('answer_' + str(s.get('answer')), str(s.get('answer') or ''))))}</li>"
                        for s in solved)
        inner += f"<h4>{e(w['solved_title'])}</h4><ul>{lines}</ul>"

    body = lead + decision + warning + section + f'<p class="muted">{e(w["readonly"])}</p>' + st.owner(inner or "<p>—</p>")
    data = {"market": doc.get("market"), "as_of": doc.get("as_of"), "currency": doc.get("currency"), "left_out": left,
            "items": [{"id": i["id"], "layer": None if i["layer"] == 9 else i["layer"], "severity": i["severity"], "state": i["state"],
                       "answered": bool(i["last"]), "text": i["text"]} for i in items],
            "solved": [{"item": s.get("item"), "answer": s.get("answer"), "day": s.get("day")} for s in solved]}
    return st.page(w["title"], body, data)
