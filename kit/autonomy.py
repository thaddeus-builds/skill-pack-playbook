"""Autonomy levels: what proof a write into someone else's system carries,
and the shared mechanics of the two levels that need no per-change code
(docs/autonomy.md has the model, the worked example and the adoption note).

    L0  hand-carried         the skill pack writes nothing; a person does it
    L1  per-change consent   tty | relay: kit.human.confirm, one yes = one code
    L2  scoped approval      approval: one approve of a work item covers the
                             writes the skill pack classes inside its frozen scope
    L3  owner-switched mode  auto: a switch the owner turned on covers the
                             writes of eligible registry rows, until a day
    L4  rule-started work    rule: a second switch lets a tested rule start the
                             work itself, inside an L3 mode, with no per-item
                             approve
    L5  full autonomy        not built: nobody switches it, nothing expires

Every function here is pure over data the skill pack passes in (registry rows,
the switch fact's history rows, its raw archive's manifests, the clock), so
any skill pack can use it whatever its tables and store; nothing here reads a
database, a file or the time of day. What it decides:

  * the tier registry: canon() reads a skill pack's own column names into
    {id, verb, change, tier, undo, auto}; check_tiers() is the registry's
    test (tier A | B, auto yes | undo | no, a B or yes row names an undo, a
    yes row's undo is itself a registered code-free undo, no orphan undo
    row); tier_of() is A unless every change is B (an unknown pair is A);
    eligible() the yes ids.
  * the switch (L3): one fact whose value is `YYYY-MM-DD[:ID,ID…]`
    (switch_value / parse_switch). mode() reads its history: on only while
    the latest row is a confirm signed by a human channel (tty, relay), its
    day not before the confirm's, today (UTC) on or before min(its day, the
    confirm's day + max_days), and the archive the skill pack counts is its
    own; `ids` the value's ids still eligible now, so a registry edit
    narrows a mode that is on and never widens it. Any later row turns it
    off; may_set() is the agent's write: only a day before today (off).
  * the approval (L2): approval_why() is None when one approve covers the
    write, else the code of why not, in a fixed order (outside the frozen
    scope or not tier B; the target not live; the archive moved; no human
    approve or it left approval since; expired; the item's cap; the week's).
  * auto_verdict() (L3): {why, stop}: why the mode does not cover a write
    (None when it does), and whether that is a stop (a cap reached, the
    item's last write did not read back, rows of two proofs in one write):
    then no code is issued at all, so a hurried agent is never one --code
    away from closing its own code.
  * the rule switch (L4): a second fact, the same value shape, naming rule
    ids instead of registry rows. rules_mode() is on only while the L3 mode
    is on, and then by the same reading of its own history (a person's
    confirm, the max-days clamp, ids frozen); its day never passes the L3
    mode's. may_set() guards it too: an agent may only switch it off.
    may_confirm_rules() is the pack's check before it takes a person's confirm:
    the override rate's bar must be met (see override_rate()).
  * rule_verdict() (L4): {why, stop}: why a rule does not cover a write
    (None when it does), in a fixed order; a stale basis is
    kit.human.stale_basis; a trip, an unverified last write, a mixed run and a
    cap are stops. trip_until() reads the archive's events: two trips in a row
    switch the rule off for a week. week_cap() is the per-week cap counted
    from the manifests.
  * override_rate(): the owner's overrides of one kind of work from the
    archive's events (started, published, undone, edited), and whether a
    bar the skill pack supplies is met: the gate on turning the rule switch on.
  * caps are counted from the archive, never a counter: used() counts
    manifests of one proof since a time (one whose time cannot be read
    counts; a half-done write counts; a weight counts rows); tighten() is a
    client's value over the default, only ever lower.
  * the record: gate() is the manifest's `gate` and suffix() the reason's
    tail for proof approval | auto | rule | undo; changed_by is
    kit.human.changed_by(proof). proof_level() reads a level back off a
    manifest.
  * undo: undo_free() is True for the undo of an auto or rule write while the live
    object is as that write left it and nothing undid it, whatever the
    mode, its caps or the item's status; undone_by() maps each write to the
    undo that undid it.
  * digest(): the covered writes of the last days, newest first, with
    verified, undone_by and the undo command the skill pack words.
  * lock(): the exclusive lock a covered write holds from its cap check
    through its manifest, so parallel runs cannot all pass one cap.

A manifest is the dict a skill pack keeps beside each write under raw: the
keys read here are action, item, dir, applied_at (ISO 8601), verified and
gate {proof, undoes, rule}; a weight function may read others (rows).

An event is the dict a skill pack maps its archive to for the L4 readers:
{rule, item, event, at, kind, proof}, `event` one of started | published |
undone | edited | tripped, `at` ISO 8601; each reader names the keys it reads.

Codes, not messages: every `why` is a code the skill pack registers and
words (the SEO skill pack's own message codes are the same strings).
Seen once: the SEO skill pack's store write (scripts/apply_shopify.py,
S46 and S47); L4 is built from its agreed design (S254), not yet used by any
skill pack. Test: kit/tests/test_autonomy.py.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Iterator

from kit import human

LEVELS = (("L0", "hand-carried"), ("L1", "per-change consent"), ("L2", "scoped approval"),
          ("L3", "owner-switched mode"), ("L4", "rule-started work"), ("L5", "full autonomy"))
BUILT = ("L0", "L1", "L2", "L3", "L4")
PROOFS = {"tty": "L1", "relay": "L1", "approval": "L2", "auto": "L3", "rule": "L4", "undo": None}
HUMAN = ("tty", "relay")                    # the channels a person signs with (kit.human.confirm)
COLUMNS = ("id", "verb", "change", "tier", "undo", "auto")
AUTO = ("yes", "undo", "no")
NONE = ("", "-", "—")                       # an undo cell that names no verb
SWITCH = re.compile(r"(\d{4}-\d{2}-\d{2})(?::([A-Za-z0-9_]+(?:,[A-Za-z0-9_]+)*))?")
VERB = re.compile(r"[a-z][a-z_-]*")
STOPS = ("auto_prev_unverified", "auto_mixed")
OFF = ("auto_off_never", "auto_off_lowered", "auto_off_unproven", "auto_off_expired", "auto_off_paths_moved")
RULE_OFF = tuple(c.replace("auto_", "rule_", 1) for c in OFF) + ("rule_off_no_auto",)
RULE_STOPS = ("rule_mixed", "rule_tripped", "rule_prev_unverified")
EVENTS = ("started", "published", "undone", "edited")
TRIPS, TRIP_DAYS, WEEK_DAYS = 2, 7, 7       # trips in a row, days off, days in a cap's week
BAR_KEYS = ("min_published", "max_overridden", "max_rate")


# ---- the tier registry -----------------------------------------------------

def canon(rows: Iterable[dict], columns: dict[str, str] | None = None,
          words: dict[str, str] | None = None) -> list[dict]:
    """The registry rows as {id, verb, change, tier, undo, auto}: `columns`
    maps the skill pack's own column names to these, `words` its own auto
    values to yes | undo | no (the SEO skill pack: 是 / 撤回 / 否)."""
    columns, words = columns or {}, words or {}
    out = []
    for r in rows:
        c = {columns.get(k, k): (v or "").strip() for k, v in r.items()}
        c = {k: c.get(k, "") for k in COLUMNS}
        c["auto"] = words.get(c["auto"], c["auto"]) or "no"
        out.append(c)
    return out


def undo_verb(cell: str) -> str | None:
    """The verb an undo cell names (its first word), None for none."""
    m = VERB.match(cell.strip())
    return None if cell.strip() in NONE or not m else m.group(0)


def check_tiers(rows: list[dict]) -> list[str]:
    """The registry's problems, [] when whole: each id once; one row per
    (verb, change); tier A or B; auto yes, undo or no; a tier-B row and a
    yes row name an undo verb (only a revertible write may skip a code); a
    yes row's undo verb is an `undo` row's verb (its undo is code-free); an
    `undo` row's verb is the undo of some yes row."""
    out, ids, pairs = [], set(), set()
    undo_rows = {r["verb"] for r in rows if r["auto"] == "undo"}
    yes_undos = {undo_verb(r["undo"]) for r in rows if r["auto"] == "yes"}
    for r in rows:
        i = r["id"] or "?"
        if not r["id"] or r["id"] in ids:
            out.append(f"{i}: id empty or not unique")
        ids.add(r["id"])
        if (r["verb"], r["change"]) in pairs:
            out.append(f"{i}: ({r['verb']}, {r['change']}) has two rows")
        pairs.add((r["verb"], r["change"]))
        if r["tier"] not in ("A", "B"):
            out.append(f"{i}: tier {r['tier']!r} is not A or B")
        if r["auto"] not in AUTO:
            out.append(f"{i}: auto {r['auto']!r} is not yes, undo or no")
        if (r["tier"] == "B" or r["auto"] == "yes") and not undo_verb(r["undo"]):
            out.append(f"{i}: a tier-B or auto row names no undo")
        if r["auto"] == "yes" and undo_verb(r["undo"]) and undo_verb(r["undo"]) not in undo_rows:
            out.append(f"{i}: its undo {undo_verb(r['undo'])!r} is no code-free undo row")
        if r["auto"] == "undo" and r["verb"] not in yes_undos:
            out.append(f"{i}: an undo row no auto row is undone by")
    return out


def tier_of(rows: list[dict], verb: str, changes: list[str] | None) -> str:
    """A or B, the highest over the write's changes; an unknown (verb,
    change) pair is A. `changes` None: a verb whose writes have no class
    (`-`)."""
    tiers = {(r["verb"], r["change"]): r["tier"] for r in rows}
    return "A" if any(tiers.get((verb, c), "A") != "B" for c in (changes or ["-"])) else "B"


def eligible(rows: list[dict]) -> list[str]:
    """The ids a mode can cover now: the auto=yes rows."""
    return [r["id"] for r in rows if r["auto"] == "yes"]


def ids_of(rows: list[dict], verb: str, changes: list[str] | None) -> list[str | None]:
    """The registry id of each (verb, change) of a write; None for a pair
    the registry does not list."""
    by = {(r["verb"], r["change"]): r["id"] for r in rows}
    return [by.get((verb, c)) for c in (changes or ["-"])]


# ---- the switch (L3) -------------------------------------------------------

def switch_value(until: date, ids: Iterable[str] = ()) -> str:
    ids = sorted(set(ids))
    return until.isoformat() + (":" + ",".join(ids) if ids else "")


def parse_switch(value: str | None) -> tuple[date, list[str]] | None:
    m = SWITCH.fullmatch((value or "").strip())
    if not m:
        return None
    try:
        day = date.fromisoformat(m.group(1))
    except ValueError:
        return None
    return day, sorted(set((m.group(2) or "").split(",")) - {""})


def may_set(value: str | None, today: date) -> bool:
    """An agent's write of the switch is accepted only when it switches the
    mode off: a day before today. Only a human's confirm raises it."""
    p = parse_switch(value)
    return p is not None and p[0] < today


def when(ts: str | None) -> datetime | None:
    """An ISO 8601 time, UTC when it names no zone; None when unreadable."""
    try:
        t = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def signed(by: str | None) -> bool:
    """True when a history row was signed by a person: `<user>@tty|relay`
    (kit.human.changed_by); a client:<name> row, an empty user, a second
    `@`, `@cli`, `@approval`, `@auto`, `@rule` and `@undo` are no one's switch
    (docs/autonomy.md rule 3)."""
    by = str(by or "")
    user, at, channel = by.partition("@")
    return bool(user) and not user.startswith("client:") and at == "@" and channel in HUMAN


def mode(history: list[dict], *, today: date, max_days: int, eligible_ids: Iterable[str],
         own_archive: bool = True) -> dict:
    """The owner's mode from the switch fact's history rows ({id, action,
    value, changed_by, changed_at}; the newest is the highest id):
    {on, until, ids, history_id, confirmed_by, confirmed_at, why_off}.
    why_off is None when on, else auto_off_never (no human confirm ever),
    _lowered (a later row, or a confirm of a past day), _unproven (the
    latest confirm signed by no person), _expired, _paths_moved (the
    skill pack counts its caps from an archive that is not its own)."""
    out = {"on": False, "until": None, "ids": [], "history_id": None, "confirmed_by": None,
           "confirmed_at": None, "why_off": "auto_off_never"}
    if not history:
        return out
    last = max(history, key=lambda r: r["id"])
    ever = any(r["action"] == "confirm" for r in history)
    p = parse_switch(last.get("value")) if last["action"] == "confirm" else None
    at = when(last.get("changed_at"))
    out["history_id"] = last["id"]
    if not p or not at:
        out["why_off"] = "auto_off_lowered" if ever else "auto_off_never"
        return out
    day, frozen = p
    until = min(day, (at + timedelta(days=max_days)).date())
    out.update(until=until.isoformat(), ids=sorted(set(frozen) & set(eligible_ids)),
               confirmed_by=last["changed_by"], confirmed_at=last["changed_at"])
    out["why_off"] = ("auto_off_unproven" if not signed(last["changed_by"]) else
                      "auto_off_lowered" if day < at.date() else
                      "auto_off_expired" if today > until else
                      "auto_off_paths_moved" if not own_archive else None)
    out["on"] = out["why_off"] is None
    return out


# ---- the approval (L2) -----------------------------------------------------

def approval_holds(approved_by: str | None, left: bool) -> bool:
    """The item's latest approve was a person's and it has not left
    approval since (revoked, done), whatever its status column says now."""
    return signed(approved_by) and not left


def approval_why(*, tier: str, change: list[str] | None, allow: list[str], approved_by: str | None,
                 left: bool, approved_at: str | None, now: datetime, days: int, used_item: int,
                 cap_item: int, used_week: int, cap_week: int, live: bool = True,
                 own_archive: bool = True) -> str | None:
    """None when the item's approval is the write's proof (L2), else why
    not: gate_outside_approval (not tier B, or a change outside the scope
    frozen when the work was proposed: a code never overrides it),
    gate_approval_hidden (the target is not live: it could go public later
    unseen), gate_approval_paths_moved, gate_approval_unproven,
    gate_approval_expired, gate_approval_used_up (the item's cap),
    gate_approval_week_cap (the workspace's)."""
    at = when(approved_at)
    return ("gate_outside_approval" if tier != "B" or not set(change or []) <= set(allow) else
            "gate_approval_hidden" if not live else
            "gate_approval_paths_moved" if not own_archive else
            "gate_approval_unproven" if not approval_holds(approved_by, left) else
            "gate_approval_expired" if not at or now > at + timedelta(days=days) else
            "gate_approval_used_up" if used_item >= cap_item else
            "gate_approval_week_cap" if used_week >= cap_week else None)


# ---- the mode's verdict on one write (L3) ----------------------------------

def auto_verdict(*, mode: dict, write_ids: list[str | None], item_approved: bool,
                 last_verified: bool | None = None, mixed: bool = False, check: str | None = None,
                 caps: Iterable[tuple[str, int, int, int]] = ()) -> dict:
    """{why, stop}: why the mode does not cover this write (None when it
    does), checked in order: the mode off (its why_off); rows of two proofs
    in one write (auto_mixed: run them apart); a (verb, change) not among
    the mode's ids (auto_not_eligible); the item not approved by a person
    or left approval (auto_item_unproven: a mode covers approved work
    only); its latest write did not read back (auto_prev_unverified); the
    verb's own check (`check`, a skill pack code); then each cap (code, used,
    planned, cap): over it when used + planned > cap. `stop` is True for a
    cap, an unverified last write or a mixed run: issue no code, hand it
    to the owner. Otherwise the write takes its per-change code."""
    caps = list(caps)
    why = (mode["why_off"] if not mode["on"] else
           "auto_mixed" if mixed else
           "auto_not_eligible" if not write_ids or any(i not in mode["ids"] for i in write_ids) else
           "auto_item_unproven" if not item_approved else
           "auto_prev_unverified" if last_verified is False else
           check)
    if why is None:
        why = next((code for code, used_, planned, cap_ in caps if used_ + planned > cap_), None)
    return {"why": why, "stop": why in STOPS or why in {c[0] for c in caps}}


# ---- the rule switch, the rule's verdict and the override rate (L4) --------

def rules_mode(history: list[dict], *, today: date, max_days: int, eligible_rules: Iterable[str],
               auto_mode: dict, own_archive: bool = True) -> dict:
    """The rule switch from its fact's history rows (the same shape as mode()):
    {on, until, ids, history_id, confirmed_by, confirmed_at, why_off}, `ids`
    the rule ids the owner froze that are still eligible now. It is read as
    mode() reads the L3 switch (a person's confirm, a day not before the
    confirm's, the max-days clamp, an archive that is its own; any later row
    turns it off) and it needs the L3 mode on: `auto_mode` is that mode()
    result, and with it off the rule switch is off too (rule_off_no_auto)
    and its day never passes the L3 mode's. why_off is None when on, else
    rule_off_never | _lowered | _unproven | _expired | _paths_moved | _no_auto."""
    m = mode(history, today=today, max_days=max_days, eligible_ids=eligible_rules, own_archive=own_archive)
    if m["why_off"]:
        m["why_off"] = m["why_off"].replace("auto_", "rule_", 1)
    elif not auto_mode["on"]:
        m["why_off"] = "rule_off_no_auto"
    if auto_mode["on"] and m["until"] and auto_mode["until"]:
        m["until"] = min(m["until"], auto_mode["until"])
    m["on"] = m["why_off"] is None
    return m


def may_confirm_rules(value: str | None, *, today: date, eligible_rules: Iterable[str], auto_mode: dict,
                      rate: dict) -> str | None:
    """None when a person's confirm of this value may be taken, else why not:
    rule_switch_malformed (not `YYYY-MM-DD:ID,ID`); a day before today
    switches it off, which is never refused; rule_switch_no_rules (names no
    rule); rule_switch_unknown_rule (a rule that is not a registry row now);
    rule_switch_no_auto (the L3 mode is off: the confirm would do nothing);
    rule_switch_bar_not_met (`rate` is override_rate()'s result for the
    kind of work: the L3 record has not earned the switch yet). The pack
    calls it before its confirm verb takes the code; the code still binds the
    value a person typed."""
    p = parse_switch(value)
    ids = set(p[1]) if p else set()
    return ("rule_switch_malformed" if p is None else
            None if p[0] < today else
            "rule_switch_no_rules" if not ids else
            "rule_switch_unknown_rule" if not ids <= set(eligible_rules) else
            "rule_switch_no_auto" if not auto_mode["on"] else
            "rule_switch_bar_not_met" if not rate["met"] else None)


def trip_until(events: Iterable[dict], rule: str, *, now: datetime, trips: int = TRIPS,
               days: int = TRIP_DAYS) -> datetime | None:
    """When a rule's trip ends, None when it has not tripped. Of one rule's
    outcomes (`published` and `tripped` events, oldest first) the last
    `trips` all tripped: two trips in a row switch the rule off for `days`
    from the latest trip. A published outcome resets the count, so when
    the days pass a rule that trips again at once is off for another
    stretch. An outcome whose time cannot be read counts as `now` (it
    cannot be shown old), so it never ends by itself."""
    out = sorted(((when(e.get("at")) or now, e["event"]) for e in events
                  if e.get("rule") == rule and e.get("event") in ("published", "tripped")), key=lambda r: r[0])
    streak = 0
    for _, ev in reversed(out):
        if ev != "tripped":
            break
        streak += 1
    return out[-1][0] + timedelta(days=days) if streak >= trips else None


def week_cap(manifests: Iterable[dict], *, now: datetime, cap: int, rule: str | None = None, planned: int = 1,
             actions: Iterable[str] | None = None, code: str = "rule_week_cap") -> tuple[str, int, int, int]:
    """The per-week cap as rule_verdict()'s `caps` take it, (code, used,
    planned, cap): the rule-proof writes of the last 7 days counted from
    the manifests (`rule` only that rule's; an undo never counts; a client's
    value goes through tighten())."""
    ms = [m for m in manifests if rule is None or ((m.get("gate") or {}).get("rule") or {}).get("id") == rule]
    return code, used(ms, proof="rule", since=now - timedelta(days=WEEK_DAYS), actions=actions), planned, cap


def rule_verdict(*, rules: dict, auto_mode: dict, rule: str | None, write_ids: list[str | None], now: datetime,
                 basis_saved: str | None, basis_now: str | None, events: Iterable[dict] = (),
                 last_verified: bool | None = None, mixed: bool = False, check: str | None = None,
                 caps: Iterable[tuple[str, int, int, int]] = (), trips: int = TRIPS,
                 trip_days: int = TRIP_DAYS) -> dict:
    """{why, stop}: why the rule switch does not cover this write (None when
    it does), checked in order: the switch off (rules_mode's why_off); rows of
    two proofs in one write (rule_mixed); the work matched no rule, or one
    the owner did not switch on (rule_not_eligible); the write's registry
    rows not among the L3 mode's ids (rule_write_not_covered: the rule only
    picks work an L3 write could carry); the rule tripped (rule_tripped:
    trip_until() over `events`); the basis the rule read is stale
    (rule_basis_stale: kit.human.stale_basis, a missing one too); the
    rule's latest write did not read back (rule_prev_unverified); the pack's
    own check (`check`, a code it registers); then each cap (code, used,
    planned, cap), over when used + planned > cap. `stop` is True for a
    mixed run, a trip, an unverified last write and a cap: nothing is started
    and nobody is one --code away from it. Otherwise the work stays pending
    for a person, as it did before the switch. A rule's work still takes
    the L3 mode's own checks on the write (auto_verdict(), item_approved
    True: the rule is what approved it)."""
    caps = list(caps)
    until = trip_until(events, rule, now=now, trips=trips, days=trip_days) if rule else None
    why = (rules["why_off"] if not rules["on"] else
           "rule_mixed" if mixed else
           "rule_not_eligible" if not rule or rule not in rules["ids"] else
           "rule_write_not_covered" if not write_ids or any(i not in auto_mode["ids"] for i in write_ids) else
           "rule_tripped" if until is not None and now < until else
           "rule_basis_stale" if human.stale_basis(basis_saved, basis_now) else
           "rule_prev_unverified" if last_verified is False else
           check)
    if why is None:
        why = next((code for code, used_, planned, cap_ in caps if used_ + planned > cap_), None)
    return {"why": why, "stop": why in RULE_STOPS or why in {c[0] for c in caps}}


def override_rate(events: Iterable[dict], *, bar: dict, kind: str | None = None, proof: str | None = None,
                  rule: str | None = None, since: datetime | None = None) -> dict:
    """How often the owner overrode one kind of work, from the archive's events
    ({item, event, at, kind, proof, rule}; `event` is started | published |
    undone | edited, anything else, as `tripped`, is not read here), and
    whether the pack's `bar` is met: {kind, started, published, undone,
    edited, overridden, rate, bar, met, why}. Each count is of items, so an
    item edited twice is one. An item is overridden when it was published
    and then undone or edited (a time that cannot be read counts, as a cap
    does: it cannot be shown to be before the publish); `rate` is
    overridden / published, None with none published. `bar` is the pack's:
    `min_published` (required; fewer is override_too_few), `max_overridden`
    (override_too_many), `max_rate` (override_rate_high); each other key is
    refused. `kind`, `proof` and `rule` keep only the events of that kind,
    proof and rule, `since` only those after it; give the L3 proof to ask what
    L3 earned for the rule switch. This reader never turns anything on: it
    is the input of may_confirm_rules()."""
    if "min_published" not in bar or set(bar) - set(BAR_KEYS):
        raise ValueError(f"a bar names min_published and may name {BAR_KEYS[1:]}, not {sorted(bar)}")
    seen: dict[str, dict[str, list]] = {e: {} for e in EVENTS}
    for e in events:
        if (e.get("event") not in EVENTS or e.get("item") is None
                or any(want is not None and e.get(k) != want for k, want in
                       (("kind", kind), ("proof", proof), ("rule", rule)))):
            continue
        at = when(e.get("at"))
        if since is None or at is None or at > since:
            seen[e["event"]].setdefault(e["item"], []).append(at)
    pub = seen["published"]

    def after(item: str, first: datetime | None) -> bool:
        return any(t is None or first is None or t >= first
                   for ev in ("undone", "edited") for t in seen[ev].get(item, ()))
    overridden = sum(1 for item, ts in pub.items()
                     if after(item, min((t for t in ts if t is not None), default=None)))
    n, rate = len(pub), (overridden / len(pub) if pub else None)
    why = ("override_too_few" if n < bar["min_published"] else
           "override_too_many" if bar.get("max_overridden") is not None and overridden > bar["max_overridden"] else
           "override_rate_high" if bar.get("max_rate") is not None and rate is not None and rate > bar["max_rate"]
           else None)
    return {"kind": kind, "started": len(seen["started"]), "published": n, "undone": len(seen["undone"]),
            "edited": len(seen["edited"]), "overridden": overridden, "rate": rate, "bar": dict(bar),
            "met": why is None, "why": why}


# ---- caps, counted from the archive ----------------------------------------

def used(manifests: Iterable[dict], *, proof: str, since: datetime | None = None,
         actions: Iterable[str] | None = None, weight: Callable[[dict], int] | None = None) -> int:
    """What writes of one proof used since `since`, from the manifests
    under raw (never a counter a crash could leave behind): a half-done
    write counts, one whose time cannot be read counts. `weight` counts a
    manifest as more than one (a batch of redirect rows, each a row)."""
    acts = set(actions) if actions is not None else None
    n = 0
    for m in manifests:
        t = when(m.get("applied_at"))
        if (m.get("gate") or {}).get("proof") != proof or (acts is not None and m.get("action") not in acts):
            continue
        if since is not None and t is not None and t <= since:
            continue
        n += weight(m) if weight else 1
    return n


def tighten(default: float, *client: float | None) -> float:
    """A cap a client may only lower: the default, or a confirmed client
    value below it. A pending value is never passed: an agent cannot raise
    its own cap."""
    return min([default, *(c for c in client if c is not None)])


@contextlib.contextmanager
def lock(data_dir: str, name: str = ".apply.lock") -> Iterator[None]:
    """An exclusive lock in the data dir (never under raw, which is never
    rewritten), held by a covered write from its cap check through its
    manifest: parallel runs are counted one after another."""
    with open(os.path.join(data_dir, name), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


# ---- the record ------------------------------------------------------------

def gate(proof: str, *, tier: str, change: list[str] | None, ref: dict | None = None) -> dict:
    """The manifest's `gate` for a write proved by approval, auto, rule or
    undo: `ref` is the approve row (approval), the mode (auto: history_id,
    confirmed_by, confirmed_at, until, ids), the rule switch's mode as auto's
    plus the rule's `rule` id and the `basis` it read (rule), or the undone
    write's dir (undo: {"dir": …})."""
    if proof not in ("approval", "auto", "rule", "undo"):
        raise ValueError(f"gate() records approval, auto, rule or undo, not {proof!r} (tty and relay: kit.human)")
    if proof == "approval" and tier != "B":
        raise ValueError("an approval covers tier-B writes only")
    ref = ref or {}
    out = {"proof": proof, "tier": tier, "change": change}
    if proof == "approval":
        out["approval"] = ref
    elif proof in ("auto", "rule"):
        out["mode"] = {k: ref.get(k) for k in ("history_id", "confirmed_by", "confirmed_at", "until", "ids")}
        if proof == "rule":
            if not ref.get("rule") or not ref.get("basis"):
                raise ValueError("a rule write names its rule and the basis it read")
            out["rule"] = {"id": ref["rule"], "basis": ref["basis"]}
    else:
        out["undoes"] = ref.get("dir")
    return out


def suffix(proof: str, ref: dict) -> str:
    """The reason's tail naming what the write rode on, so the history row
    reads without the manifest."""
    if proof == "approval":
        return f" [approval=#{ref['history_id']} by={ref['approved_by']} at={ref['approved_at']}]"
    if proof == "auto":
        return f" [auto=#{ref['history_id']} by={ref['confirmed_by']} until={ref['until']}]"
    if proof == "rule":
        return f" [rule={ref['rule']} basis={ref['basis']} mode=#{ref['history_id']}]"
    if proof == "undo":
        return f" [undoes={ref['dir']}]"
    raise ValueError(f"no suffix for proof {proof!r}")


def proof_level(manifest: dict) -> str | None:
    """The level a manifest's write ran at (L1 tty | relay, L2 approval, L3
    auto, L4 rule); None for an undo (it lowers exposure) or no gate."""
    return PROOFS.get((manifest.get("gate") or {}).get("proof"))


# ---- undo and the digest ---------------------------------------------------

def undone_by(manifests: Iterable[dict]) -> dict[str, str]:
    """{dir of a write: dir of the undo that undid it}."""
    return {(m.get("gate") or {})["undoes"]: m.get("dir") for m in manifests
            if (m.get("gate") or {}).get("undoes")}


def undo_free(done: dict, *, undone: bool, live_as_left: bool) -> bool:
    """True when undoing `done` needs no code: it was an auto or rule write,
    no undo has undone it, and the live object is as it left it (an edit made
    since takes the code). The mode, its caps and the item's status do not
    matter: an undo only lowers exposure, and a cap never blocks it."""
    return (done.get("gate") or {}).get("proof") in ("auto", "rule") and not undone and live_as_left


def digest(manifests: list[dict], *, now: datetime, days: int, proofs: Iterable[str] = ("approval", "auto", "rule"),
           undo: Callable[[dict], str | None] | None = None) -> list[dict]:
    """The covered writes of the last `days`, newest first: {at, item,
    action, proof, rule, level, verified, undone_by, undo}. `undo` words the
    command that undoes one (the skill pack's own verb); None once undone."""
    by, ps, since = undone_by(manifests), set(proofs), now - timedelta(days=days)
    out = []
    for m in manifests:
        t, g = when(m.get("applied_at")), m.get("gate") or {}
        if g.get("proof") not in ps or (t is not None and t <= since):
            continue
        gone = by.get(m.get("dir"))
        out.append({"at": m.get("applied_at"), "item": m.get("item"), "action": m.get("action"),
                    "proof": g["proof"], "rule": (g.get("rule") or {}).get("id"), "level": proof_level(m), "verified": m.get("verified"),
                    "undone_by": gone, "undo": None if gone or not undo else undo(m)})
    return sorted(out, key=lambda r: str(r["at"] or ""), reverse=True)
