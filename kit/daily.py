"""The day's advice of the three layers as one list of items: the rules alone, no database, no clock, no platform.

It reads nothing itself: the pack hands it the documents of its campaign, audit, allocation and pacing computes, and the answers people gave. Every item
is one of their own findings under a stable id, never a second reading:

    campaign:<action>:<campaign id>   layer 2: a campaign's proposal (`lifecycle` and the pack's rules)
    audit:<finding>                   layer 2: an audit finding with its steps (`kit.audit`, plus the pack's own)
    move:<campaign id>                layer 3: tomorrow's budget move (`allocation`), with its interval, doubt and the platform's limit that held it
    request:creatives                 layer 1: how many creatives to ask the maker for (`creative_demand`), or why none

Each item has a coded sentence, the evidence, its doubts, the steps, the command that reports back, and the latest answer. An answered item that no
longer comes up is `solved`. A thing the composer does not know (a doubt name, a severity, a pacing warning) is left out, never an error. Nothing here
writes. A campaign proposal and an audit finding arrive with their own coded sentence and keep it: this module's own codes are the `daily_*` rows of
kit/message_codes.d/daily.tsv.

From the video-ads skill pack (`scripts/_lib/daily.py`; its cases are this module's test, its Traditional Chinese rendering stays with its page).

Test: kit/tests/test_daily.py.
"""

from __future__ import annotations

from kit.messages import Msg, coded, msg

STATE_SEVERITY = {"blocked": "high", "fatigued": "medium", "declining": "medium", "lagging": "medium"}
RANK = {"high": 0, "medium": 1, "info": 2}
NOTE_CODES = ("pacing_no_target", "pacing_demand_unknown")


def _doubt(name: str) -> Msg | None:
    """The sentence of a doubt or a platform limit; None for a name this module does not know."""
    make = {"no_counterfactual": lambda: msg("daily_doubt_no_counterfactual", "it replays past days: there is no control group, so it is not a promise that the change earns more"),
            "elasticity_pooled": lambda: msg("daily_doubt_elasticity_pooled", "this campaign's own days are too few to read its response: the pooled value of the others is used"),
            "budget_from_ad_sets": lambda: msg("daily_doubt_budget_from_ad_sets", "its budget is the sum of its ad groups', not one set on the campaign"),
            "no_budget_change_seen": lambda: msg("daily_doubt_no_budget_change_seen", "no budget change of this campaign has been seen yet, so how it responds is not measured"),
            "min_daily_budget": lambda: msg("daily_limit_min_daily_budget", "stopped by the platform's minimum daily budget: the move is smaller than the rule wanted"),
            "max_daily_budget": lambda: msg("daily_limit_max_daily_budget", "stopped by the platform's maximum daily budget: the move is smaller than the rule wanted")}.get(name)
    return make() if make else None


def _none_message(constraints: list[str]) -> Msg:
    for c in constraints:
        make = {"money_committed": lambda: msg("daily_request_none_committed", "no creatives to ask for: the exploration money is already taken by the creatives in testing and in production"),
                "no_exploration_money": lambda: msg("daily_request_none_money", "no creatives to ask for: the exploration money cannot carry another one to a verdict"),
                "cost_unknown": lambda: msg("daily_request_none_cost", "no number of creatives yet: what it costs to reach a verdict is not known"),
                "limit_binds": lambda: msg("daily_request_none_limit", "no creatives to ask for: the platform's budget range leaves no room for a new ad group")}.get(c)
        if make:
            return make()
    return msg("daily_request_none", "no creatives to ask for now")


def _item(item_id: str, layer: int, severity: str, message, evidence, cli: str, market: str, *, steps=(), doubt=(), subject=None) -> dict:
    m = coded("message", message) if not isinstance(message, dict) else message
    return {"id": item_id, "layer": layer, "severity": severity if severity in RANK else "info", **m,
            "evidence": coded("message", evidence) if evidence is not None else None, "steps": list(steps), "doubt": list(doubt), "subject": subject or {},
            "report": f"{cli} import action --market {market} --item {item_id} --answer done"}


def campaign_items(camp: dict, cli: str, market: str) -> list[dict]:
    out = []
    for c in camp["campaigns"]:
        if c["state"] == "ended":
            continue
        for p in c.get("proposals", []):
            out.append(_item(f"campaign:{p['action']}:{c['campaign']}", 2, STATE_SEVERITY.get(c["state"], "info"),
                             {"message": p["message"], "message_code": p.get("message_code")}, None, cli, market,
                             subject={"campaign": c["campaign"], "name": c.get("name"), "state": c["state"], "status": c.get("status")}))
    return out


def audit_items(audit: dict, cli: str, market: str) -> list[dict]:
    return [_item(f"audit:{f['finding']}", 2, f["severity"], {"message": f["message"], "message_code": f["message_code"]}, None, cli, market,
                  steps=[{"message": s["text"], "message_code": s["message_code"]} for s in f["steps"]], subject={"finding": f["finding"]})
            for f in audit["findings"]]


def move_items(alloc: dict, cli: str, market: str) -> tuple[list[dict], dict, int]:
    """(the items of tomorrow's moves, what became of the earlier ones, how many campaigns in the wallet stay put)."""
    prop = alloc.get("proposal") or {}
    out = []
    for m in prop.get("moves", []):
        doubt = [d for d in ([_doubt(n) for n in m["doubt"]] + ([_doubt(m["binding"])] if m.get("binding") else [])) if d is not None]
        mg = m["marginal"]
        out.append(_item(f"move:{m['campaign']}", 3, "medium" if m["fast"] else "info",
                         msg("daily_move", f"{m['name']}: change its daily budget from {m['from']} to {m['to']}", campaign=m["campaign"], name=m["name"] or m["campaign"],
                             frm=m["from"], to=m["to"], change=m["change"], low=mg["low"], high=mg["high"]),
                         msg("daily_move_evidence", "evidence", value=mg["value"], se=mg["se"], level=m["level"], z=m["z"], cap=m["cap"]), cli, market,
                         steps=[coded("message", msg("daily_move_step1", "in the platform's ads manager set that campaign's daily budget to the proposed number (or, when its budget sits on its ad groups, scale them by the same share)")),
                                coded("message", msg("daily_move_step2", "report it with the command below, then read the next pull: spend should follow the budget within a day or two"))],
                         doubt=[coded("message", d) for d in doubt],
                         subject={"campaign": m["campaign"], "name": m["name"], "from": m["from"], "to": m["to"]}))
    f = prop.get("followed") or {}
    return out, {k: f.get(k, 0) for k in ("taken", "not_taken", "open")}, len(prop.get("held", []))


def request_item(pacing: dict, cli: str, market: str) -> tuple[dict | None, list[tuple[str, dict]]]:
    """(the request item, notes): no item without a month target, only the note that says so."""
    cd = pacing.get("creative_demand")
    notes = [(w, c) for w, c in zip(pacing.get("warnings", []), pacing.get("warning_codes", [])) if c["code"] in NOTE_CODES]
    if cd is None:
        return None, notes
    if cd.get("n"):
        size = cd["batch_size"]
        per = ", ".join(f"{b['size']} x {b['daily_budget']}/day" for b in cd["batches"])
        ev = msg("daily_request_evidence", "evidence", money=cd["money"], committed=cd["committed"], unit_cost=cd["unit_cost"], basis=cd["basis"], per=per)
        return _item("request:creatives", 1, "medium", msg("daily_request", f"ask the maker for {cd['n']} creatives", n=cd["n"], batches=len(cd["batches"]), size=size), ev, cli, market,
                     steps=[coded("message", msg("daily_request_step1", "ask the creative maker for the number, one new test group name for each batch, and build the ad group only when the handoff lists nothing as not exported")),
                            coded("message", msg("daily_request_step2", "record the request, so the next page counts it as in production and does not ask again"))], subject={"n": cd["n"]}), notes
    ev = msg("daily_request_none_evidence", "evidence", money=cd["money"], committed=cd["committed"], capacity=cd["capacity"])
    return _item("request:creatives", 1, "info", _none_message(cd.get("constraints", [])), ev, cli, market, subject={"n": 0}), notes


def build(market: str, cli: str, camp: dict, audit: dict, alloc: dict, pacing: dict, answers: dict[str, dict]) -> dict:
    """The page's document: the items in order (severity, layer, id), each with the latest answer in `last`, the answers whose item no longer comes up in `solved`."""
    moves, followed, held = move_items(alloc, cli, market)
    req, notes = request_item(pacing, cli, market)
    items = ([req] if req else []) + campaign_items(camp, cli, market) + audit_items(audit, cli, market) + moves
    items.sort(key=lambda i: (RANK[i["severity"]], i["layer"], i["id"]))
    for i in items:
        a = answers.get(i["id"])
        i["last"] = {k: a[k] for k in ("answer", "day", "note", "by")} if a else None
    now = {i["id"] for i in items}
    solved = [{"item": k, "answer": a["answer"], "day": a["day"], "note": a["note"]} for k, a in sorted(answers.items()) if k not in now]
    counts = {s: sum(1 for i in items if i["severity"] == s) for s in ("high", "medium", "info")}
    return {"market": market, "currency": camp.get("currency"), "as_of": camp["as_of"], "items": items, "solved": solved, "followed": followed,
            "followed_text": coded("message", msg("daily_followed", f"earlier budget advice: {followed['taken']} taken", taken=followed["taken"], not_taken=followed["not_taken"], open=followed["open"])),
            "held": held, "notes": [w for w, _ in notes], "note_codes": [c for _, c in notes],
            "summary": {"items": len(items), **counts, "answered": sum(1 for i in items if i["last"]), "solved": len(solved)}}
