"""The skill pack's declaration to the console: which pages it adds, which verbs
a click may run, how many asks may be open. One JSON file, read by both sides
(serve.py to draw and relay, ask.py to refuse early). Pure: no I/O but the one
file read in `load()`, no process, no network.

    {
      "version": 1,
      "cmd": ["uv", "run", "my_skill_pack.py"],
      "relay_verbs": [["parcel", "release"], ["unit", "confirm"]],
      "page_only_verbs": [["unit", "confirm"]],
      "max_open": 20,
      "counts": ["console", "counts"],
      "pages": [
        {"name": "space", "title": {"en": "Space", "zh": "空间"}, "order": 20,
         "verb": ["console", "page", "space"], "blocking": false}
      ]
    }

  version      1 (required: a file for a newer console is refused, not guessed at)
  cmd          the skill pack command (argv). The operator's: it runs the relay
               and every page verb. Needed when there is a page or a relay verb
  relay_verbs  the verb prefixes a gate or a page button may run, each a list of
               words; anything else is refused when an ask is added or a button
               is drawn, never silently left as a no-only form. Default: none
  page_only_verbs  optional: relay verb prefixes that only a button the skill pack's own
               page draws may run (one that grants something: a mode, a spending
               period). An ask whose gate is one of them is refused when it is added
               (`ask.py add`) and when it is answered, so no agent can post a card the
               owner would then click. Each must start with a relay verb. Default: none
  max_open     how many asks may be open at once (default core.MAX_OPEN, at most 100)
  counts       optional: one verb printing {"counts": {"<page>": N}}, a number for
               each page's tab (cached for a few seconds)
  pages        0 to 12 of: name (a-z 0-9 _, starts with a letter), title (text, or
               {en, zh}), order (integer, default 100; the built-in Waiting page
               is 10 and History 1000), verb (the read-only verb that returns the
               page as JSON blocks, see frame.py), blocking (true: its count joins
               the Waiting tab's number, default false)

Unknown keys are errors, as in an ask: a typo must surface, not vanish.
"""

from __future__ import annotations

import json

import core

VERSION = 1
KEYS = {"version", "cmd", "relay_verbs", "page_only_verbs", "max_open", "counts", "pages"}
PAGE_KEYS = {"name", "title", "order", "verb", "blocking"}
RESERVED = {"waiting", "history", "poll", "answer", "answer_all", "reopen", "note", "act", "static"}
NAME_MAX, MAX_PAGES, MAX_OPEN_CEILING, ORDER_MAX = 24, 12, 100, 100000
BUILTIN_ORDER = {"waiting": 10, "history": 1000}
LANGS = ("en", "zh")


class ManifestError(Exception):
    """The manifest cannot be used; the message says what to change."""


def _name_ok(n) -> bool:
    return (isinstance(n, str) and 1 <= len(n) <= NAME_MAX and n[0].isalpha() and n[0].islower() and n.isascii()
            and all(c.islower() or c.isdigit() or c == "_" for c in n))


def _verb(where: str, v) -> list[str]:
    if not (isinstance(v, list) and 1 <= len(v) <= core.LIMITS["verb"]
            and all(isinstance(w, str) and core.TOKEN_RE.fullmatch(w) for w in v)):
        raise ManifestError(f"{where}: a verb is 1 to {core.LIMITS['verb']} plain words "
                            "(letters, digits, _ . : @ / -), none starting with '-'")
    return list(v)


def verbs_from_text(text: str) -> list[list[str]]:
    """The comma form of the relay verbs, `"facts confirm,queue approve"`, as `serve.py --relay-verbs` takes it:
    each verb's words checked as a manifest's are (ManifestError when one is not a plain verb)."""
    return [_verb(f"--relay-verbs[{i}]", w.split()) for i, w in enumerate(x for x in text.split(",") if x.split())]


def parse(doc) -> dict:
    """The manifest as the console uses it, or ManifestError. Always has every key."""
    if not isinstance(doc, dict):
        raise ManifestError("the manifest is a JSON object")
    extra = sorted(set(doc) - KEYS)
    if extra:
        raise ManifestError(f"unknown key {extra[0]!r}; the keys are {sorted(KEYS)}")
    if doc.get("version") != VERSION or isinstance(doc.get("version"), bool):
        raise ManifestError(f'"version" must be {VERSION} (this console reads version {VERSION} only)')
    cmd = doc.get("cmd", [])
    if not (isinstance(cmd, list) and all(isinstance(w, str) and w and "\x00" not in w for w in cmd)):
        raise ManifestError('"cmd" is the skill pack command as a list of words, e.g. ["uv", "run", "pack.py"]')
    verbs = doc.get("relay_verbs", [])
    if not isinstance(verbs, list):
        raise ManifestError('"relay_verbs" is a list of verb prefixes, each a list of words')
    verbs = [_verb(f"relay_verbs[{i}]", v) for i, v in enumerate(verbs)]
    only = doc.get("page_only_verbs", [])
    if not isinstance(only, list):
        raise ManifestError('"page_only_verbs" is a list of verb prefixes, each a list of words')
    only = [_verb(f"page_only_verbs[{i}]", v) for i, v in enumerate(only)]
    for v in only:
        if not core.verb_allowed(verbs, v):
            raise ManifestError(f'"page_only_verbs": {" ".join(v)!r} does not start with a relay verb; add its prefix to "relay_verbs" or drop it')
    mo = doc.get("max_open", core.MAX_OPEN)
    if not (isinstance(mo, int) and not isinstance(mo, bool) and 1 <= mo <= MAX_OPEN_CEILING):
        raise ManifestError(f'"max_open" is a whole number from 1 to {MAX_OPEN_CEILING}')
    counts = _verb('"counts"', doc["counts"]) if doc.get("counts") is not None else None
    raw_pages = doc.get("pages", [])
    if not (isinstance(raw_pages, list) and len(raw_pages) <= MAX_PAGES):
        raise ManifestError(f'"pages" is a list of at most {MAX_PAGES} pages')
    pages, seen = [], set()
    for i, p in enumerate(raw_pages):
        pages.append(_page(i, p, seen))
    if (pages or verbs or counts) and not cmd:
        raise ManifestError('"cmd" is needed: pages, relay_verbs and counts all run through the skill pack command')
    if counts and not pages:
        raise ManifestError('"counts" without pages: there is no tab to put a number on')
    return {"version": VERSION, "cmd": cmd, "relay_verbs": verbs, "page_only_verbs": only, "max_open": mo, "counts": counts, "pages": pages}


def _page(i: int, p, seen: set) -> dict:
    where = f"pages[{i}]"
    if not isinstance(p, dict):
        raise ManifestError(f"{where} is an object {{name, title, verb, ...}}")
    extra = sorted(set(p) - PAGE_KEYS)
    if extra:
        raise ManifestError(f"{where}: unknown key {extra[0]!r}; the keys are {sorted(PAGE_KEYS)}")
    name = p.get("name")
    if not _name_ok(name):
        raise ManifestError(f"{where}: name is lowercase letters, digits and _, starting with a letter, "
                            f"at most {NAME_MAX}")
    if name in RESERVED or name in seen:
        raise ManifestError(f"{where}: the name {name!r} is " + ("taken by the console" if name in RESERVED
                                                                 else "used twice"))
    seen.add(name)
    t = p.get("title")
    if isinstance(t, str):
        t = {"en": t}
    if not (isinstance(t, dict) and t and set(t) <= set(LANGS) and "en" in t
            and all(isinstance(v, str) and v.strip() and len(v) <= 40 for v in t.values())):
        raise ManifestError(f'{where}: "title" is a text of at most 40 characters, or {{"en": …, "zh": …}} with "en"')
    order = p.get("order", 100)
    if not (isinstance(order, int) and not isinstance(order, bool) and 0 <= order <= ORDER_MAX):
        raise ManifestError(f'{where}: "order" is a whole number from 0 to {ORDER_MAX}')
    blocking = p.get("blocking", False)
    if not isinstance(blocking, bool):
        raise ManifestError(f'{where}: "blocking" is true or false')
    return {"name": name, "title": {"en": t["en"], "zh": t.get("zh", t["en"])}, "order": order,
            "verb": _verb(f"{where}: verb", p.get("verb")), "blocking": blocking}


def load(path: str) -> dict:
    """Read and check the file; ManifestError names the file and the problem."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ManifestError(f"cannot read the manifest {path}: {e.strerror or e}") from None
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise ManifestError(f"the manifest {path} is not valid JSON: {e}") from None
    try:
        return parse(doc)
    except ManifestError as e:
        raise ManifestError(f"{path}: {e}") from None


def limit(manifest: dict | None) -> int:
    """How many asks may be open: the manifest's number, else core.MAX_OPEN."""
    return manifest["max_open"] if manifest else core.MAX_OPEN


def nav(manifest: dict | None) -> list[dict]:
    """The tabs, in order: the two built-in pages and the manifest's, by `order`
    (ties by name). Each is {name, order, title: {en, zh} | None (built-in: the
    dictionary's words), blocking}."""
    tabs = [{"name": n, "order": o, "title": None, "blocking": False} for n, o in BUILTIN_ORDER.items()]
    tabs += [{"name": p["name"], "order": p["order"], "title": p["title"], "blocking": p["blocking"]}
             for p in (manifest or {}).get("pages", [])]
    return sorted(tabs, key=lambda x: (x["order"], x["name"]))
