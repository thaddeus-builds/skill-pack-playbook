"""Every page a person answers on offers a no beside the yes.

The rule (docs/rules.md, "Human-in-the-loop rules", rule 7): an ask states what "no" means, and the page that asks offers
a way to say it, as plainly as the yes: beside "Confirm the checked ones", a "Reject the checked ones"; beside a row's
yes, that row's no. An ask with only a yes is a gate nobody can refuse. *Seen once:* the SEO skill pack's own web
console, 2026-11-05, a confirm page whose one button was "确认勾选的项"; the owner caught it on a client's deploy.

A skill pack that draws its own pages (the shared console has its own tests) runs this over each page its verbs draw,
from a synthetic fixture, in a test:

    from kit.guards import asks
    assert not asks.problems(html, "confirm page"), asks.problems(html, "confirm page")

`problems(html, where)` reads every `<form method="post">` (a GET form writes nothing) and returns one problem for each
that says no way to say no. A form says it one of two ways:

  * a control marked `data-answer="no"` inside it, or tied to it by `form="ID"` (a button, a submit input, a radio or
    a select option): the no is right there;
  * `data-no="WHY"` on the form, with a reason, for a form that is not an ask (a search, a note, a login, a sign-out,
    a reopen of history): saying why there is no no is part of the page.

The marking is required on every POST form, not guessed from its words: a check that reads button labels in two
languages misses the third, and the rule prefers a false hit, which a `data-no` answers, to a miss (docs/lessons.md,
"A guard's refinement never costs the recall it had"). A `data-answer="no"` control that is disabled or hidden does not
count. `self_test()` plants each form and returns the ones the check missed.

Test: kit/tests/test_asks_guard.py.
"""

from __future__ import annotations

from html.parser import HTMLParser

CONTROLS = ("button", "input", "option")


class _Forms(HTMLParser):
    """Each POST form: its line, action, `data-no`, id, and whether a usable no control sits in it or names it."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self.open: list[dict | None] = []           # the form stack (None for a GET form)
        self.loose: list[str] = []                  # ids named by a no control's form= attribute
        self.hidden: list[bool] = []                # inside an element marked hidden

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "form":
            post = a.get("method", "get").strip().lower() == "post"
            f = {"line": self.getpos()[0], "action": a.get("action", ""), "why": a.get("data-no", "").strip(),
                 "id": a.get("id", ""), "no": False, "marked": "data-no" in a} if post else None
            self.open.append(f)
            if f is not None:
                self.forms.append(f)
            return
        if tag in CONTROLS and a.get("data-answer", "").strip().lower() == "no" and not self._dead(a):
            if a.get("form"):
                self.loose.append(a["form"])
            elif self.open and self.open[-1] is not None:
                self.open[-1]["no"] = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self.open:
            self.open.pop()

    def _dead(self, a: dict) -> bool:
        return "disabled" in a or "hidden" in a or a.get("type", "").lower() == "hidden" \
            or a.get("aria-hidden", "").lower() == "true"


def problems(html: str, where: str = "page") -> list[str]:
    """One line per POST form in `html` that offers no way to say no; [] when every form does."""
    p = _Forms()
    p.feed(html)
    p.close()
    out = []
    for n, f in enumerate(p.forms, 1):
        has_no = f["no"] or (f["id"] and f["id"] in p.loose)
        if has_no:
            continue
        if f["marked"] and f["why"]:
            continue
        if f["marked"]:
            out.append(f"{where}: form {n} (line {f['line']}, action {f['action'] or '-'}): data-no names no reason")
        else:
            out.append(f"{where}: form {n} (line {f['line']}, action {f['action'] or '-'}) offers no way to say no: "
                       'add a control marked data-answer="no" beside the yes, or data-no="why there is none" '
                       "on a form that is not an ask")
    return out


SOUND = """<form method="post" action="/confirm"><input type="checkbox" name="id" value="1">
<button name="answer" value="yes" data-answer="yes">Confirm the checked</button>
<button name="answer" value="no" data-answer="no">Reject the checked</button></form>
<form method="post" action="/row/2" id="r2"><button data-answer="yes">Yes</button></form>
<button form="r2" data-answer="no">No</button>
<form method="post" action="/note" data-no="a note is not an ask"><textarea name="t"></textarea><button>Save</button></form>
<form method="post" action="/pick"><select name="a"><option data-answer="yes">Use it</option>
<option data-answer="no">Not this one</option></select><button>Send</button></form>
<form action="/search"><input name="q"></form>"""

PLANTED = {
    "a confirm with only a yes": '<form method="post" action="/confirm"><button data-answer="yes">确认勾选的项</button></form>',
    "an unmarked form": '<form method="POST"><button>Approve</button></form>',
    "a disabled no": '<form method="post"><button data-answer="yes">Yes</button><button data-answer="no" disabled>No</button></form>',
    "a hidden no": '<form method="post"><button>Yes</button><input type="hidden" data-answer="no" name="a" value="no"></form>',
    "a data-no with no reason": '<form method="post" data-no=""><button>Go</button></form>',
    "a no tied to another form": '<form method="post" id="a"><button>Yes</button></form>'
                                 '<form method="post" id="b" data-no="b is a note"></form><button form="b" data-answer="no">No</button>',
    "a no outside every form": '<form method="post"><button>Yes</button></form><button data-answer="no">No</button>',
}


def self_test() -> list[str]:
    """The planted forms the check missed, or "the sound page fails"; empty is sound."""
    missed = [what for what, html in PLANTED.items() if not problems(html)]
    if problems(SOUND):
        missed.append("the sound page fails")
    return missed
