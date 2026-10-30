"""Autonomy levels: what proof a write into someone else's system carries,
and the shared mechanics of the two levels that need no per-change code
(docs/autonomy.md has the model, the worked example and the adoption note).

    L0  hand-carried         the skill pack writes nothing; a person does it
    L1  per-change consent   tty | relay: kit.human.confirm, one yes = one code
    L2  scoped approval      approval: one approve of a work item covers the
                             writes the skill pack classes inside its frozen scope
    L3  owner-switched mode  auto: a switch the owner turned on covers the
                             writes of eligible registry rows, until a day
    L4  rule-started work    not built: the mode also starts work a fixed
                             rule picked, with no per-item approve
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
  * caps are counted from the archive, never a counter: used() counts
    manifests of one proof since a time (one whose time cannot be read
    counts; a half-done write counts; a weight counts rows); tighten() is a
    client's value over the default, only ever lower.
  * the record: gate() is the manifest's `gate` and suffix() the reason's
    tail for proof approval | auto | undo; changed_by is
    kit.human.changed_by(proof). proof_level() reads a level back off a
    manifest.
  * undo: undo_free() is True for the undo of an auto write while the live
    object is as that write left it and nothing undid it, whatever the
    mode, its caps or the item's status; undone_by() maps each write to the
    undo that undid it.
  * digest(): the covered writes of the last days, newest first, with
    verified, undone_by and the undo command the skill pack words.
  * lock(): the exclusive lock a covered write holds from its cap check
    through its manifest, so parallel runs cannot all pass one cap.

A manifest is the dict a skill pack keeps beside each write under raw: the
keys read here are action, item, dir, applied_at (ISO 8601), verified and
gate {proof, undoes}; a weight function may read others (rows).

Codes, not messages: every `why` is a code the skill pack registers and
words (the SEO skill pack's own message codes are the same strings).
Seen once: the SEO skill pack's store write (scripts/apply_shopify.py,
S46 and S47). Test: kit/tests/test_autonomy.py.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Iterator

LEVELS = (("L0", "hand-carried"), ("L1", "per-change consent"), ("L2", "scoped approval"),
          ("L3", "owner-switched mode"), ("L4", "rule-started work"), ("L5", "full autonomy"))
BUILT = ("L0", "L1", "L2", "L3")
PROOFS = {"tty": "L1", "relay": "L1", "approval": "L2", "auto": "L3", "undo": None}
HUMAN = ("tty", "relay")                    # the channels a person signs with (kit.human.confirm)
COLUMNS = ("id", "verb", "change", "tier", "undo", "auto")
AUTO = ("yes", "undo", "no")
NONE = ("", "-", "—")                       # an undo cell that names no verb
SWITCH = re.compile(r"(\d{4}-\d{2}-\d{2})(?::([A-Za-z0-9_]+(?:,[A-Za-z0-9_]+)*))?")
VERB = re.compile(r"[a-z][a-z_-]*")
STOPS = ("auto_prev_unverified", "auto_mixed")
OFF = ("auto_off_never", "auto_off_lowered", "auto_off_unproven", "auto_off_expired", "auto_off_paths_moved")


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
    `@`, `@cli`, `@approval`, `@auto` and `@undo` are no one's switch
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
    """The manifest's `gate` for a write proved by approval, auto or undo:
    `ref` is the approve row (approval), the mode (auto: history_id,
    confirmed_by, confirmed_at, until, ids) or the undone write's dir
    (undo: {"dir": …})."""
    if proof not in ("approval", "auto", "undo"):
        raise ValueError(f"gate() records approval, auto or undo, not {proof!r} (tty and relay: kit.human)")
    if proof == "approval" and tier != "B":
        raise ValueError("an approval covers tier-B writes only")
    ref = ref or {}
    out = {"proof": proof, "tier": tier, "change": change}
    if proof == "approval":
        out["approval"] = ref
    elif proof == "auto":
        out["mode"] = {k: ref.get(k) for k in ("history_id", "confirmed_by", "confirmed_at", "until", "ids")}
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
    if proof == "undo":
        return f" [undoes={ref['dir']}]"
    raise ValueError(f"no suffix for proof {proof!r}")


def proof_level(manifest: dict) -> str | None:
    """The level a manifest's write ran at (L1 tty | relay, L2 approval, L3
    auto); None for an undo (it lowers exposure) or no gate."""
    return PROOFS.get((manifest.get("gate") or {}).get("proof"))


# ---- undo and the digest ---------------------------------------------------

def undone_by(manifests: Iterable[dict]) -> dict[str, str]:
    """{dir of a write: dir of the undo that undid it}."""
    return {(m.get("gate") or {})["undoes"]: m.get("dir") for m in manifests
            if (m.get("gate") or {}).get("undoes")}


def undo_free(done: dict, *, undone: bool, live_as_left: bool) -> bool:
    """True when undoing `done` needs no code: it was an auto write, no
    undo has undone it, and the live object is as it left it (an edit made
    since takes the code). The mode, its caps and the item's status do not
    matter: an undo only lowers exposure, and a cap never blocks it."""
    return (done.get("gate") or {}).get("proof") == "auto" and not undone and live_as_left


def digest(manifests: list[dict], *, now: datetime, days: int, proofs: Iterable[str] = ("approval", "auto"),
           undo: Callable[[dict], str | None] | None = None) -> list[dict]:
    """The covered writes of the last `days`, newest first: {at, item,
    action, proof, level, verified, undone_by, undo}. `undo` words the
    command that undoes one (the skill pack's own verb); None once undone."""
    by, ps, since = undone_by(manifests), set(proofs), now - timedelta(days=days)
    out = []
    for m in manifests:
        t, g = when(m.get("applied_at")), m.get("gate") or {}
        if g.get("proof") not in ps or (t is not None and t <= since):
            continue
        gone = by.get(m.get("dir"))
        out.append({"at": m.get("applied_at"), "item": m.get("item"), "action": m.get("action"),
                    "proof": g["proof"], "level": proof_level(m), "verified": m.get("verified"),
                    "undone_by": gone, "undo": None if gone or not undo else undo(m)})
    return sorted(out, key=lambda r: str(r["at"] or ""), reverse=True)
