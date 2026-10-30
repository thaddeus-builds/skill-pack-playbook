#!/usr/bin/env python3
"""Autonomy levels (kit/autonomy.py) on a SYNTHETIC tier registry shaped
like the SEO skill pack's (its own column names and auto words), with
manifests and switch-history rows built here. Each rule is shown both
ways: the bad case refused AND the good one accepted.

  1. the registry: canon() reads the skill pack's columns and words;
     check_tiers() passes the whole registry and names each broken copy
     (a yes row with no undo, an undo that is not code-free, an orphan
     undo row, a B row with no undo, two rows for one pair, a bad tier);
     tier_of() and eligible().
  2. the switch: the value round-trips; an agent may only write a past
     day; mode() is on for a person's confirm and off for every other
     history (none, a later set, a past day, a client's or an agent's
     confirm, expired, the max-days clamp, moved paths); a registry edit
     narrows a mode that is on and never widens it.
  3. the approval: approval_why() None inside scope, and each refusal in
     its order.
  4. the mode's verdict: covered; each why; caps and unverified are stops
     (no code), a verb's own check is not.
  5. caps from the archive: proof, window, unreadable time, weight;
     tighten() only lowers; lock() serialises.
  6. the record and undo: gate()/suffix() per proof, approval refused
     off tier B; undo_free() whatever the mode, not after an edit, not of a
     coded write, not twice; digest() newest first with the undo command.
  7. the levels.
  8. the rule switch (L4): on only with the L3 mode on and a person's
     confirm; an agent may only switch it off; the confirm refused until
     the override rate's bar is met (a past day never refused).
  9. the rule's verdict: covered; each why in its order; a stale or missing
     basis; the trip rule from the archive's events; the week's cap from the
     manifests; stops.
 10. the override rate: counts per item, an override only after the publish,
     the bar both ways, filters, a bar that names nothing refused.
 11. the rule proof: gate(), suffix(), proof_level(), code-free undo and the
     digest.
"""

import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import autonomy as A  # noqa: E402
from kit.testing.check import check, finish, raises, tmp_dir  # noqa: E402

COLS = {"动作": "verb", "改动": "change", "级别": "tier", "撤回": "undo", "自动": "auto"}
WORDS = {"是": "yes", "撤回": "undo", "否": "no"}
HEAD = ("id", "动作", "改动", "级别", "撤回", "自动")
RAW = [  # SYNTHETIC, the SEO skill pack's shape
    ("T01", "draft", "-", "A", "—", "否"),
    ("T02", "publish", "-", "A", "unpublish", "否"),
    ("T03", "unpublish", "-", "A", "publish", "撤回"),
    ("T04", "update", "links", "B", "revert", "否"),
    ("T05", "update", "image", "B", "revert（the cover stays）", "否"),
    ("T07", "update", "body", "A", "revert", "否"),
    ("T13", "unredirect", "-", "A", "redirect", "撤回"),
    ("T14", "publish", "new", "A", "unpublish", "是"),
    ("T15", "redirect", "create", "A", "unredirect", "是"),
]
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


def registry(raw=RAW) -> list[dict]:
    return A.canon([dict(zip(HEAD, r)) for r in raw], COLS, WORDS)


def swap(i: str, **kw) -> list[dict]:
    return [{**r, **kw} if r["id"] == i else r for r in registry()]


def test_registry() -> None:
    print("\n[1] the tier registry")
    rows = registry()
    check("canon reads the skill pack's columns and words",
          rows[7] == {"id": "T14", "verb": "publish", "change": "new", "tier": "A", "undo": "unpublish",
                      "auto": "yes"}, rows[7])
    check("the whole registry has no problem", A.check_tiers(rows) == [], A.check_tiers(rows))
    for label, broken, want in (
            ("a yes row with no undo", swap("T14", undo="—"), "T14: a tier-B or auto row names no undo"),
            ("a yes row whose undo is not code-free", swap("T03", auto="no"),
             "T14: its undo 'unpublish' is no code-free undo row"),
            ("an undo row nothing is undone by", swap("T15", auto="no"),
             "T13: an undo row no auto row is undone by"),
            ("a tier-B row with no undo", swap("T04", undo="-"), "T04: a tier-B or auto row names no undo"),
            ("two rows for one pair", swap("T07", change="links"), "T07: (update, links) has two rows"),
            ("a tier that is not A or B", swap("T01", tier="C"), "T01: tier 'C' is not A or B"),
            ("an auto word not in the set", swap("T01", auto="maybe"), "T01: auto 'maybe' is not yes, undo or no"),
            ("an id used twice", swap("T02", id="T01"), "T01: id empty or not unique")):
        check(f"check_tiers names {label}", want in A.check_tiers(broken), A.check_tiers(broken))
    check("an undo cell's first word is its verb (text after it is a note)",
          A.undo_verb("revert（the cover stays）") == "revert" and A.undo_verb("—") is None)
    check("tier_of: B only when every change is B", A.tier_of(rows, "update", ["links", "image"]) == "B"
          and A.tier_of(rows, "update", ["links", "body"]) == "A")
    check("tier_of: an unknown pair, and a classless verb not listed, are A",
          A.tier_of(rows, "update", ["tags"]) == "A" and A.tier_of(rows, "translate", None) == "A")
    check("eligible: the yes ids", A.eligible(rows) == ["T14", "T15"], A.eligible(rows))
    check("ids_of: each change's id, None when unlisted",
          A.ids_of(rows, "redirect", ["create", "update"]) == ["T15", None])


def hist(*rows) -> list[dict]:
    return [{"id": i + 1, "action": a, "value": v, "changed_by": by, "changed_at": at}
            for i, (a, v, by, at) in enumerate(rows)]


ON = ("confirm", "2026-10-20:T14,T15", "owner@relay", "2026-10-12T08:00:00+00:00")


def on(history, **kw) -> dict:
    return A.mode(history, **{"today": TODAY, "max_days": 28, "eligible_ids": ["T14", "T15"], **kw})


def test_switch() -> None:
    print("\n[2] the switch")
    v = A.switch_value(date(2026, 10, 20), ["T15", "T14", "T14"])
    check("switch_value round-trips through parse_switch",
          v == "2026-10-20:T14,T15" and A.parse_switch(v) == (date(2026, 10, 20), ["T14", "T15"]), v)
    check("parse_switch refuses a malformed value or an impossible day",
          A.parse_switch("next week") is None and A.parse_switch("2026-02-30:T14") is None)
    check("may_set: an agent may write yesterday (off)", A.may_set("2026-10-12", TODAY))
    check("may_set: an agent may not write today or later (on)",
          not A.may_set("2026-10-13:T14", TODAY) and not A.may_set("2026-11-01:T14", TODAY))
    m = on(hist(ON))
    check("a person's relayed confirm turns it on until its day, with its ids",
          m["on"] and m["until"] == "2026-10-20" and m["ids"] == ["T14", "T15"] and m["history_id"] == 1, m)
    check("a tty confirm counts too", on(hist(ON[:2] + ("owner@tty", ON[3])))["on"])
    for label, h, want in (
            ("no history", [], "auto_off_never"),
            ("only an agent's pending set", hist(("set", "2026-10-11", "agent@cli", ON[3])), "auto_off_never"),
            ("a later set of a past day", hist(ON, ("set", "2026-10-11", "agent@cli", "2026-10-13T01:00:00+00:00")),
             "auto_off_lowered"),
            ("a later withdraw", hist(ON, ("withdraw", None, "agent@cli", "2026-10-13T01:00:00+00:00")),
             "auto_off_lowered"),
            ("a confirm of a past day", hist(("confirm", "2026-10-01:T14", "owner@relay", ON[3])), "auto_off_lowered"),
            ("a client's confirm", hist(ON[:2] + ("client:Acme", ON[3])), "auto_off_unproven"),
            ("a confirm signed @cli", hist(ON[:2] + ("agent@cli", ON[3])), "auto_off_unproven"),
            ("a confirm signed @auto", hist(ON[:2] + ("agent@auto", ON[3])), "auto_off_unproven"),
            ("past its day", hist(("confirm", "2026-10-12:T14", "owner@relay", "2026-10-11T08:00:00+00:00")),
             "auto_off_expired")):
        got = on(h)
        check(f"off: {label} ({want})", not got["on"] and got["why_off"] == want, got)
    for by in ("client:Acme@relay", "@relay", "@tty", "a@b@relay", "owner@", "owner", "", None):
        check(f"signed() refuses {by!r}: rule 3 says only a row a person signed raises", not A.signed(by), by)
    check("signed() still takes a person's tty and relay rows", A.signed("owner@tty") and A.signed("uid:501@relay"))
    check("a forged client:<name>@relay confirm does not turn it on",
          on(hist(ON[:2] + ("client:Acme@relay", ON[3])))["why_off"] == "auto_off_unproven")
    far = on(hist(("confirm", "2027-06-01:T14", "owner@relay", "2026-10-01T08:00:00+00:00")))
    check("a far day is clamped to the confirm's day + max_days, then expires",
          far["until"] == "2026-10-29" and far["on"], far)
    check("... and past the clamp it is off",
          on(hist(("confirm", "2027-06-01:T14", "owner@relay", "2026-09-01T08:00:00+00:00")))["why_off"]
          == "auto_off_expired")
    check("moved paths turn it off", on(hist(ON), own_archive=False)["why_off"] == "auto_off_paths_moved")
    check("a registry edit narrows a mode that is on", on(hist(ON), eligible_ids=["T15"])["ids"] == ["T15"])
    check("a registry edit never widens it: a new yes row is not among the frozen ids",
          on(hist(ON), eligible_ids=["T14", "T15", "T16"])["ids"] == ["T14", "T15"])
    check("a switch confirmed with no ids covers nothing",
          on(hist(("confirm", "2026-10-20", "owner@relay", ON[3])))["ids"] == [])


APPR = {"tier": "B", "change": ["links"], "allow": ["links", "image"], "approved_by": "owner@relay",
        "left": False, "approved_at": "2026-10-10T08:00:00+00:00", "now": NOW, "days": 14, "used_item": 1,
        "cap_item": 2, "used_week": 29, "cap_week": 30}


def test_approval() -> None:
    print("\n[3] the approval (L2)")
    check("inside the frozen scope, live, proven, in time, under both caps: covered",
          A.approval_why(**APPR) is None)
    for label, kw, want in (
            ("a change outside the scope", {"change": ["links", "seo"]}, "gate_outside_approval"),
            ("a tier-A write", {"tier": "A"}, "gate_outside_approval"),
            ("a hidden target", {"live": False}, "gate_approval_hidden"),
            ("a moved archive", {"own_archive": False}, "gate_approval_paths_moved"),
            ("an approve by an agent", {"approved_by": "agent@cli"}, "gate_approval_unproven"),
            ("an item that left approval", {"left": True}, "gate_approval_unproven"),
            ("an approval past its days", {"approved_at": "2026-09-20T08:00:00+00:00"}, "gate_approval_expired"),
            ("an unreadable approve time", {"approved_at": "soon"}, "gate_approval_expired"),
            ("the item's cap used", {"used_item": 2}, "gate_approval_used_up"),
            ("the week's cap used", {"used_week": 30}, "gate_approval_week_cap")):
        check(f"refused: {label} ({want})", A.approval_why(**{**APPR, **kw}) == want, A.approval_why(**{**APPR, **kw}))
    check("the scope comes first: outside it and expired says outside",
          A.approval_why(**{**APPR, "change": ["body"], "approved_at": "2026-01-01"}) == "gate_outside_approval")


def test_verdict() -> None:
    print("\n[4] the mode's verdict on one write (L3)")
    m = on(hist(ON))
    base = {"mode": m, "write_ids": ["T14"], "item_approved": True, "last_verified": True,
            "caps": [("auto_day_cap", 9, 1, 10)]}
    check("covered: eligible, approved, verified, under the cap", A.auto_verdict(**base) == {"why": None, "stop": False})
    for label, kw, want, stop in (
            ("the mode off", {"mode": on([])}, "auto_off_never", False),
            ("rows of two proofs", {"mixed": True}, "auto_mixed", True),
            ("an id the mode leaves out", {"write_ids": ["T07"]}, "auto_not_eligible", False),
            ("a pair the registry does not list", {"write_ids": [None]}, "auto_not_eligible", False),
            ("no item approve", {"item_approved": False}, "auto_item_unproven", False),
            ("its last write did not read back", {"last_verified": False}, "auto_prev_unverified", True),
            ("the verb's own check", {"check": "auto_body_unsafe"}, "auto_body_unsafe", False),
            ("the day's cap", {"caps": [("auto_day_cap", 10, 1, 10)]}, "auto_day_cap", True),
            ("rows over what is left", {"caps": [("auto_rows_cap", 60, 41, 100)]}, "auto_rows_cap", True)):
        got = A.auto_verdict(**{**base, **kw})
        check(f"{label}: {want}, stop={stop}", got == {"why": want, "stop": stop}, got)
    check("rows that fit what is left pass", A.auto_verdict(**{**base, "caps": [("auto_rows_cap", 60, 40, 100)]})["why"]
          is None)
    check("no last write yet is no trip", A.auto_verdict(**{**base, "last_verified": None})["why"] is None)


def man(action="publish", proof="auto", at="2026-10-13T10:00:00+00:00", **kw) -> dict:
    return {"action": action, "item": kw.pop("item", 1), "dir": kw.pop("dir", f"d-{action}-{at}"),
            "applied_at": at, "verified": kw.pop("verified", True), "gate": {"proof": proof, **kw.pop("gate", {})},
            **kw}


def test_caps() -> None:
    print("\n[5] caps, counted from the archive")
    ms = [man(), man(at="2026-10-12T11:00:00+00:00"), man(proof="relay"), man(at="unreadable"),
          man("redirect", rows=["/a", "/b", "/c"]), man("unpublish", "undo")]
    since = NOW - timedelta(hours=24)
    check("one proof, in the window; an unreadable time counts",
          A.used(ms, proof="auto", since=since, actions=["publish"]) == 2,
          A.used(ms, proof="auto", since=since, actions=["publish"]))
    check("a weight counts rows, not manifests",
          A.used(ms, proof="auto", since=since, actions=["redirect"], weight=lambda m: len(m["rows"])) == 3)
    check("an undo never counts toward an auto cap", A.used(ms, proof="auto", since=since, actions=["unpublish"]) == 0)
    check("no window: everything of that proof", A.used(ms, proof="auto") == 4)
    check("tighten: a client's lower value wins", A.tighten(10, 4) == 4)
    check("tighten: a client's higher value never raises it", A.tighten(10, 40) == 10 and A.tighten(10, None) == 10)
    d, order = tmp_dir("autonomy-lock-"), []

    def hold(tag: str, wait: float) -> None:
        with A.lock(d):
            order.append(f"{tag}+")
            time.sleep(wait)
            order.append(f"{tag}-")
    t = threading.Thread(target=hold, args=("a", 0.2))
    t.start()
    time.sleep(0.05)
    hold("b", 0)
    t.join()
    check("lock(): a second holder waits for the first", order == ["a+", "a-", "b+", "b-"], order)


def test_record_and_undo() -> None:
    print("\n[6] the record, undo and the digest")
    appr = {"history_id": 12, "approved_by": "owner@relay", "approved_at": "2026-10-10T08:00:00+00:00"}
    m = on(hist(ON))
    check("approval: the gate names the approve, the suffix too",
          A.gate("approval", tier="B", change=["links"], ref=appr)["approval"] == appr
          and A.suffix("approval", appr) == " [approval=#12 by=owner@relay at=2026-10-10T08:00:00+00:00]")
    check("an approval never records a tier-A write",
          isinstance(raises(lambda: A.gate("approval", tier="A", change=["body"], ref=appr), ValueError), ValueError))
    g = A.gate("auto", tier="A", change=["new"], ref=m)
    check("auto: the gate names the switch row, who, until and the ids",
          g["mode"] == {"history_id": 1, "confirmed_by": "owner@relay", "confirmed_at": ON[3], "until": "2026-10-20",
                        "ids": ["T14", "T15"]} and A.suffix("auto", m).startswith(" [auto=#1 by=owner@relay"), g)
    check("undo: the gate names the write it undoes",
          A.gate("undo", tier="A", change=None, ref={"dir": "d1"})["undoes"] == "d1"
          and A.suffix("undo", {"dir": "d1"}) == " [undoes=d1]")
    check("tty and relay are kit.human's, not gate()'s",
          isinstance(raises(lambda: A.gate("relay", tier="A", change=None), ValueError), ValueError))
    check("proof_level reads the level back", [A.proof_level(man(proof=p)) for p in ("tty", "relay", "approval",
                                                                                         "auto", "undo")]
          == ["L1", "L1", "L2", "L3", None])
    pub, coded = man(dir="p1"), man(proof="relay", dir="p2")
    undo = man("unpublish", "undo", at="2026-10-13T11:00:00+00:00", dir="u1", gate={"undoes": "p1"})
    check("undo_free: an auto write, not undone, live as it left it, mode off or not",
          A.undo_free(pub, undone=False, live_as_left=True))
    check("not free once someone edited it", not A.undo_free(pub, undone=False, live_as_left=False))
    check("not free for a write a code proved", not A.undo_free(coded, undone=False, live_as_left=True))
    check("not free twice", not A.undo_free(pub, undone="p1" in A.undone_by([pub, undo]), live_as_left=True))
    ds = A.digest([pub, coded, undo, man(proof="approval", action="update", dir="a1", at="2026-10-13T09:00:00+00:00"),
                   man(dir="old", at="2026-10-01T09:00:00+00:00")], now=NOW, days=7,
                  undo=lambda x: f"apply unpublish --item {x['item']}")
    check("digest: covered writes of the window, newest first, coded and old ones out",
          [(r["proof"], r["action"]) for r in ds] == [("auto", "publish"), ("approval", "update")], ds)
    check("digest: an undone write shows its undo and no command; a live one its command",
          ds[0]["undone_by"] == "u1" and ds[0]["undo"] is None and ds[1]["undo"] == "apply unpublish --item 1"
          and ds[1]["level"] == "L2", ds)


def test_levels() -> None:
    print("\n[7] the levels")
    check("six levels, L0 to L5, the first five built (L5 never)",
          [l for l, _ in A.LEVELS] == ["L0", "L1", "L2", "L3", "L4", "L5"]
          and A.BUILT == ("L0", "L1", "L2", "L3", "L4"))
    check("every proof label names a built level or none (undo)",
          set(A.PROOFS) == {"tty", "relay", "approval", "auto", "rule", "undo"}
          and {v for v in A.PROOFS.values() if v} <= set(A.BUILT))
    check("autonomy.py reads no database, file or clock of its own",
          not any(w in (Path(A.__file__).read_text(encoding="utf-8"))
                  for w in ("sqlite3", "datetime.now", "date.today", "time.time", "open(os.path.join(raw")))


# ---- L4 ---------------------------------------------------------------------

RULES = ["R01", "R02"]
RON = ("confirm", "2026-10-20:R01", "owner@relay", "2026-10-12T09:00:00+00:00")


def rules(history, **kw) -> dict:
    kw = {"today": TODAY, "max_days": 28, "eligible_rules": RULES, "auto_mode": on(hist(ON)), **kw}
    return A.rules_mode(history, **kw)


def bar_met(**kw) -> dict:
    return {"met": True, "why": None, **kw}


def test_rules_mode() -> None:
    print("\n[8] the rule switch (L4)")
    m = rules(hist(RON))
    check("a person's confirm turns it on with the L3 mode on: its day and the rule ids",
          m["on"] and m["until"] == "2026-10-20" and m["ids"] == ["R01"] and m["why_off"] is None, m)
    check("the L3 mode off turns it off (rule_off_no_auto), whatever its own confirm",
          rules(hist(RON), auto_mode=on([]))["why_off"] == "rule_off_no_auto")
    check("... and an L3 mode that was lowered or expired does the same",
          rules(hist(RON), auto_mode=on(hist(ON, ("set", "2026-10-11", "agent@cli", "2026-10-13T01:00:00+00:00"))))
          ["why_off"] == "rule_off_no_auto")
    check("its day never passes the L3 mode's: min of the two",
          rules(hist(("confirm", "2026-10-30:R01", "owner@relay", RON[3])))["until"] == "2026-10-20")
    check("a shorter day of its own stands", rules(hist(("confirm", "2026-10-15:R01", "owner@relay", RON[3])))
          ["until"] == "2026-10-15")
    for label, h, want in (
            ("no history", [], "rule_off_never"),
            ("only an agent's pending set", hist(("set", "2026-10-11", "agent@cli", RON[3])), "rule_off_never"),
            ("a later set of a past day", hist(RON, ("set", "2026-10-11", "agent@cli", "2026-10-13T01:00:00+00:00")),
             "rule_off_lowered"),
            ("a later withdraw", hist(RON, ("withdraw", None, "agent@cli", "2026-10-13T01:00:00+00:00")),
             "rule_off_lowered"),
            ("a client's confirm", hist(RON[:2] + ("client:Acme@relay", RON[3])), "rule_off_unproven"),
            ("a confirm signed @rule", hist(RON[:2] + ("agent@rule", RON[3])), "rule_off_unproven"),
            ("a confirm signed @auto", hist(RON[:2] + ("agent@auto", RON[3])), "rule_off_unproven"),
            ("a confirm signed @cli", hist(RON[:2] + ("agent@cli", RON[3])), "rule_off_unproven"),
            ("past its day", hist(("confirm", "2026-10-12:R01", "owner@relay", "2026-10-11T08:00:00+00:00")),
             "rule_off_expired")):
        got = rules(h)
        check(f"off: {label} ({want})", not got["on"] and got["why_off"] == want, got)
    check("a tty confirm counts", rules(hist(RON[:2] + ("owner@tty", RON[3])))["on"])
    far = rules(hist(("confirm", "2027-06-01:R01", "owner@relay", "2026-09-20T08:00:00+00:00")),
                auto_mode=on(hist(("confirm", "2027-06-01:T14", "owner@relay", "2026-09-20T08:00:00+00:00"))))
    check("a far day is clamped to the confirm's day + max_days (2026-10-18), still on", far["until"] == "2026-10-18"
          and far["on"], far)
    check("... and past the clamp it is off", rules(hist(("confirm", "2027-06-01:R01", "owner@relay",
                                                           "2026-09-01T08:00:00+00:00")))["why_off"] == "rule_off_expired")
    check("moved paths turn it off", rules(hist(RON), own_archive=False)["why_off"] == "rule_off_paths_moved")
    check("a registry edit narrows it and never widens it",
          rules(hist(("confirm", "2026-10-20:R01,R02", "owner@relay", RON[3])), eligible_rules=["R02"])["ids"] == ["R02"]
          and rules(hist(RON), eligible_rules=["R01", "R02", "R03"])["ids"] == ["R01"])
    check("an agent may only switch it off: may_set takes the same value shape",
          A.may_set("2026-10-12", TODAY) and not A.may_set("2026-10-20:R01", TODAY))
    check("every rule_off code is the auto_off one renamed, plus no_auto",
          A.RULE_OFF == ("rule_off_never", "rule_off_lowered", "rule_off_unproven", "rule_off_expired",
                         "rule_off_paths_moved", "rule_off_no_auto"), A.RULE_OFF)
    # the confirm's precondition
    ok = {"today": TODAY, "eligible_rules": RULES, "auto_mode": on(hist(ON)), "rate": bar_met()}
    check("a confirm is taken: a rule row, L3 on, the bar met", A.may_confirm_rules("2026-10-20:R01", **ok) is None)
    for label, v, kw, want in (
            ("a malformed value", "next week", {}, "rule_switch_malformed"),
            ("no rule named", "2026-10-20", {}, "rule_switch_no_rules"),
            ("a rule that is no registry row", "2026-10-20:R01,R09", {}, "rule_switch_unknown_rule"),
            ("the L3 mode off", "2026-10-20:R01", {"auto_mode": on([])}, "rule_switch_no_auto"),
            ("the bar not met", "2026-10-20:R01", {"rate": bar_met(met=False, why="override_too_few")},
             "rule_switch_bar_not_met")):
        got = A.may_confirm_rules(v, **{**ok, **kw})
        check(f"confirm refused: {label} ({want})", got == want, got)
    check("a past day is a way off and is never refused, bar or not",
          A.may_confirm_rules("2026-10-12", **{**ok, "auto_mode": on([]), "rate": bar_met(met=False)}) is None)
    check("today counts as raising: it needs the bar",
          A.may_confirm_rules("2026-10-13:R01", **{**ok, "rate": bar_met(met=False)}) == "rule_switch_bar_not_met")


def RG(rule: str) -> dict:  # noqa: N802
    return {"rule": {"id": rule, "basis": "2026-10-11"}}


def ev(event, item=1, at="2026-10-13T09:00:00+00:00", rule="R01", **kw) -> dict:
    return {"rule": rule, "item": item, "event": event, "at": at, "kind": kw.pop("kind", "article"),
            "proof": kw.pop("proof", "rule"), **kw}


def rv(**kw) -> dict:
    base = {"rules": rules(hist(RON)), "auto_mode": on(hist(ON)), "rule": "R01", "write_ids": ["T14"], "now": NOW,
            "basis_saved": "2026-10-11", "basis_now": "2026-10-11", "last_verified": True,
            "caps": [("rule_week_cap", 2, 1, 3)]}
    return A.rule_verdict(**{**base, **kw})


def test_rule_verdict() -> None:
    print("\n[9] the rule's verdict on one write (L4)")
    check("covered: switch on, eligible rule, L3 kind, fresh basis, no trip, under the cap",
          rv() == {"why": None, "stop": False}, rv())
    t = lambda *rest: [ev(e, i, at) for e, i, at in rest]  # noqa: E731
    for label, kw, want, stop in (
            ("the switch off", {"rules": rules([])}, "rule_off_never", False),
            ("the L3 mode off under it", {"rules": rules(hist(RON), auto_mode=on([]))}, "rule_off_no_auto", False),
            ("rows of two proofs", {"mixed": True}, "rule_mixed", True),
            ("work that matched no rule", {"rule": None}, "rule_not_eligible", False),
            ("a rule the owner did not switch on", {"rule": "R02"}, "rule_not_eligible", False),
            ("a write kind the L3 mode leaves out", {"write_ids": ["T07"]}, "rule_write_not_covered", False),
            ("a pair the registry does not list", {"write_ids": [None]}, "rule_write_not_covered", False),
            ("no write ids at all", {"write_ids": []}, "rule_write_not_covered", False),
            ("a stale basis", {"basis_now": "2026-10-13"}, "rule_basis_stale", False),
            ("a basis never saved", {"basis_saved": None}, "rule_basis_stale", False),
            ("a basis that cannot be recomputed now", {"basis_now": None}, "rule_basis_stale", False),
            ("the rule's last write not read back", {"last_verified": False}, "rule_prev_unverified", True),
            ("the pack's own check", {"check": "rule_topic_overlap"}, "rule_topic_overlap", False),
            ("the week's cap", {"caps": [("rule_week_cap", 3, 1, 3)]}, "rule_week_cap", True),
            ("a second cap of the pack's", {"caps": [("rule_cluster_cap", 1, 1, 1)]}, "rule_cluster_cap", True)):
        got = rv(**kw)
        check(f"{label}: {want}, stop={stop}", got == {"why": want, "stop": stop}, got)
    check("no last write yet is no trip", rv(last_verified=None)["why"] is None)
    check("a cap with room left passes", rv(caps=[("rule_week_cap", 2, 1, 3)])["why"] is None)
    check("the switch comes first: off and stale says off", rv(rules=rules([]), basis_now="x")["why"] == "rule_off_never")
    check("not eligible comes before the basis", rv(rule="R02", basis_now="x")["why"] == "rule_not_eligible")
    check("a stale basis comes before the pack's check and the cap",
          rv(basis_now="x", check="c", caps=[("rule_week_cap", 9, 1, 3)])["why"] == "rule_basis_stale")
    check("the pack's check comes before the cap", rv(check="c", caps=[("rule_week_cap", 9, 1, 3)])["why"] == "c")
    # trips
    two = t(("tripped", 1, "2026-10-12T09:00:00+00:00"), ("tripped", 2, "2026-10-13T09:00:00+00:00"))
    got = rv(events=two)
    check("two trips in a row switch the rule off: rule_tripped, a stop", got == {"why": "rule_tripped", "stop": True}, got)
    check("...until a week after the latest trip: the end is read from the events",
          A.trip_until(two, "R01", now=NOW) == datetime(2026, 10, 20, 9, tzinfo=timezone.utc))
    check("...and it covers again once that week has passed",
          rv(events=two, now=NOW + timedelta(days=7, hours=1))["why"] is None)
    check("one trip is a warning, not a stop",
          rv(events=t(("tripped", 1, "2026-10-13T09:00:00+00:00")))["why"] is None)
    check("a published outcome between two trips resets the count",
          rv(events=t(("tripped", 1, "2026-10-11T09:00:00+00:00"), ("published", 2, "2026-10-12T09:00:00+00:00"),
                      ("tripped", 3, "2026-10-13T09:00:00+00:00")))["why"] is None)
    check("two trips, the order of the rows does not matter, only their times",
          rv(events=list(reversed(two)))["why"] == "rule_tripped")
    check("events of another rule do not trip this one", rv(events=[{**e, "rule": "R02"} for e in two])["why"] is None)
    check("started, undone and edited are not outcomes: they neither trip nor reset",
          rv(events=two + [ev("started", 3, "2026-10-13T10:00:00+00:00"), ev("edited", 1, "2026-10-13T11:00:00+00:00")])
          ["why"] == "rule_tripped")
    check("a trip whose time cannot be read counts as now: it does not end by itself",
          rv(events=[ev("tripped", 1, "2026-10-12T09:00:00+00:00"), ev("tripped", 2, "soon")],
             now=NOW + timedelta(days=30))["why"] == "rule_tripped"
          and A.trip_until([ev("tripped", 1, "soon"), ev("tripped", 2, "soon")], "R01", now=NOW)
          == NOW + timedelta(days=7))
    check("trips in a row is a parameter: three needed, two do not trip it",
          rv(events=two, trips=3)["why"] is None and rv(events=two, trips=2)["why"] == "rule_tripped")
    check("a rule that trips again straight after its week is off again (no free retry)",
          rv(events=two + t(("tripped", 3, "2026-10-21T09:00:00+00:00")), now=datetime(2026, 10, 21, 10,
                                                                                         tzinfo=timezone.utc))["why"]
          == "rule_tripped")
    # the week's cap, from the archive
    ms = [man(proof="rule", at="2026-10-12T10:00:00+00:00", gate=RG("R01")),
          man(proof="rule", at="2026-10-08T10:00:00+00:00", gate=RG("R01")),          # 5 days: in the week
          man(proof="rule", at="2026-10-05T10:00:00+00:00", gate=RG("R01")),          # 8 days: out
          man(proof="rule", at="2026-10-12T11:00:00+00:00", gate=RG("R02")),
          man(proof="auto", at="2026-10-12T12:00:00+00:00"),
          man("unpublish", "undo", at="2026-10-12T13:00:00+00:00")]
    check("week_cap counts the rule proof of the last 7 days from the manifests, not auto or undo",
          A.week_cap(ms, now=NOW, cap=3) == ("rule_week_cap", 3, 1, 3), A.week_cap(ms, now=NOW, cap=3))
    check("...of one rule when asked", A.week_cap(ms, now=NOW, cap=3, rule="R01")[1] == 2)
    check("...an unreadable time counts, a half-done write too",
          A.week_cap(ms + [man(proof="rule", at="unreadable", verified=False)], now=NOW, cap=3)[1] == 4)
    check("...and the cap it feeds is a stop at the cap",
          rv(caps=[A.week_cap(ms, now=NOW, cap=3, planned=1)]) == {"why": "rule_week_cap", "stop": True}
          and rv(caps=[A.week_cap(ms, now=NOW, cap=4, planned=1)])["why"] is None)


def test_override_rate() -> None:
    print("\n[10] the override rate")
    bar = {"min_published": 10, "max_overridden": 1}
    pub = [ev("published", i, "2026-10-01T09:00:00+00:00", proof="auto") for i in range(1, 11)]
    got = A.override_rate([ev("started", i, proof="auto") for i in range(1, 11)] + pub, bar=bar, kind="article")
    check("ten published, none overridden: the bar is met",
          got["started"] == 10 and got["published"] == 10 and got["overridden"] == 0 and got["rate"] == 0
          and got["met"] and got["why"] is None and got["kind"] == "article" and got["bar"] == bar, got)
    undone = ev("undone", 3, "2026-10-02T09:00:00+00:00", proof="auto")
    edited = ev("edited", 4, "2026-10-02T10:00:00+00:00", proof="auto")
    got = A.override_rate(pub + [undone], bar=bar)
    check("one undone of ten is inside a bar of one", got["overridden"] == 1 and got["rate"] == 0.1 and got["met"], got)
    got = A.override_rate(pub + [undone, edited], bar=bar)
    check("an undo and an edit are two overridden items: over a bar of one (override_too_many)",
          got["undone"] == 1 and got["edited"] == 1 and got["overridden"] == 2 and not got["met"]
          and got["why"] == "override_too_many", got)
    got = A.override_rate(pub + [undone, ev("edited", 3, "2026-10-03T09:00:00+00:00", proof="auto")], bar=bar)
    check("one item undone and edited is one overridden item", got["overridden"] == 1 and got["met"], got)
    got = A.override_rate(pub[:9], bar=bar)
    check("nine published of ten needed: not met, override_too_few", not got["met"] and got["why"] == "override_too_few")
    check("none published: rate None, and a bar of zero is met only with min_published 0",
          A.override_rate([], bar=bar)["rate"] is None and A.override_rate([], bar={"min_published": 0})["met"])
    check("an edit before the publish is the owner's work on a draft, not an override",
          A.override_rate(pub + [ev("edited", 5, "2026-09-30T09:00:00+00:00", proof="auto")], bar=bar)["overridden"] == 0)
    check("an undo whose time cannot be read counts: it cannot be shown to be earlier",
          A.override_rate(pub + [ev("undone", 5, "?", proof="auto")], bar=bar)["overridden"] == 1)
    check("an undo of an item that was never published is not an override of a publish",
          A.override_rate(pub + [ev("undone", 99, "2026-10-02T09:00:00+00:00")], bar=bar)["overridden"] == 0)
    check("the same item published twice is one", A.override_rate(pub + [pub[0]], bar=bar)["published"] == 10)
    rate = {"min_published": 10, "max_rate": 0.05}
    check("max_rate: one of ten is 0.1, over 0.05 (override_rate_high); the count bar alone would pass",
          A.override_rate(pub + [undone], bar=rate)["why"] == "override_rate_high"
          and A.override_rate(pub + [undone], bar=bar)["met"])
    check("max_rate in range passes", A.override_rate(pub + [undone], bar={"min_published": 10, "max_rate": 0.1})["met"])
    # filters
    mixed = pub + [ev("published", 50 + i, "2026-10-01T09:00:00+00:00", kind="page", proof="auto") for i in range(5)]
    check("kind keeps one kind of work", A.override_rate(mixed, bar=bar, kind="article")["published"] == 10
          and A.override_rate(mixed, bar=bar, kind="page")["published"] == 5 and A.override_rate(mixed, bar=bar)["published"] == 15)
    check("proof keeps what L3 earned, not what the rule did",
          A.override_rate(pub + [ev("published", 70, proof="rule")], bar=bar, proof="auto")["published"] == 10)
    check("rule keeps one rule's events", A.override_rate([ev("published", 1), ev("published", 2, rule="R02")],
                                                          bar={"min_published": 1}, rule="R02")["published"] == 1)
    check("since keeps what came after it (an unreadable time stays)",
          A.override_rate(pub + [ev("published", 80, "2026-09-01T00:00:00+00:00", proof="auto"),
                                 ev("published", 81, "?", proof="auto")], bar=bar,
                          since=datetime(2026, 9, 15, tzinfo=timezone.utc))["published"] == 11)
    check("tripped and unknown events and rows with no item are not read",
          A.override_rate(pub + [ev("tripped", 1), ev("seen", 2), {"event": "published", "at": "2026-10-01"}],
                          bar=bar)["published"] == 10)
    for label, b in (("a bar that names no min_published", {"max_overridden": 1}),
                     ("a bar with a key of nobody's", {"min_published": 1, "max_unhappy": 0}),
                     ("an empty bar", {})):
        check(f"refused: {label}", isinstance(raises(lambda b=b: A.override_rate(pub, bar=b), ValueError), ValueError))
    check("the result is plain data (it goes to --json as it is)",
          __import__("json").loads(__import__("json").dumps(A.override_rate(pub, bar=bar))) == A.override_rate(pub, bar=bar))


def test_rule_record() -> None:
    print("\n[11] the rule proof: record, undo and the digest")
    rm = rules(hist(RON))
    ref = {**rm, "rule": "R01", "basis": "2026-10-11"}
    g = A.gate("rule", tier="A", change=["new"], ref=ref)
    check("rule: the gate names the switch row, the rule and its basis",
          g["proof"] == "rule" and g["rule"] == {"id": "R01", "basis": "2026-10-11"}
          and g["mode"] == {"history_id": 1, "confirmed_by": "owner@relay", "confirmed_at": RON[3],
                            "until": "2026-10-20", "ids": ["R01"]}, g)
    check("rule: the reason's tail is [rule=ID basis=DATE mode=#N]",
          A.suffix("rule", {"rule": "R01", "basis": "2026-10-11", "history_id": 7}) == " [rule=R01 basis=2026-10-11 mode=#7]")
    for label, bad in (("no rule", {**ref, "rule": None}), ("no basis", {**ref, "basis": ""})):
        check(f"a rule write with {label} is refused",
              isinstance(raises(lambda bad=bad: A.gate("rule", tier="A", change=["new"], ref=bad), ValueError), ValueError))
    check("the other proofs carry no rule key", "rule" not in A.gate("auto", tier="A", change=["new"], ref=on(hist(ON))))
    check("proof_level: rule is L4", A.proof_level(man(proof="rule")) == "L4")
    import pwd
    import os
    want = f"{pwd.getpwuid(os.geteuid()).pw_name}@rule"
    from kit import human
    check("changed_by(rule) is <user>@rule, and nobody's confirm", human.changed_by("rule") == want
          and not A.signed(want))
    pub = man(proof="rule", dir="r1", gate=RG("R01"))
    check("undo_free: a rule write is undone with no code, as an auto write is",
          A.undo_free(pub, undone=False, live_as_left=True))
    check("... not after an edit, not twice", not A.undo_free(pub, undone=False, live_as_left=False)
          and not A.undo_free(pub, undone=True, live_as_left=True))
    check("... and a coded write still is not free", not A.undo_free(man(proof="relay"), undone=False, live_as_left=True))
    undo = man("unpublish", "undo", at="2026-10-13T11:00:00+00:00", dir="u1", gate={"undoes": "r1"})
    ds = A.digest([pub, undo, man(dir="a1", at="2026-10-13T09:00:00+00:00")], now=NOW, days=7,
                  undo=lambda x: f"apply unpublish --item {x['item']}")
    check("digest: a rule write shows its rule, level L4 and its undone state; the other proofs have none",
          [(r["proof"], r["rule"], r["level"]) for r in ds] == [("rule", "R01", "L4"), ("auto", None, "L3")]
          and ds[0]["undone_by"] == "u1" and ds[1]["undo"] == "apply unpublish --item 1", ds)
    real = man(proof="rule", at="2026-10-12T10:00:00+00:00", gate=A.gate("rule", tier="A", change=["new"], ref=ref))
    check("a manifest carrying gate()'s own output is what week_cap and digest read",
          A.week_cap([real], now=NOW, cap=3, rule="R01")[1] == 1 and A.week_cap([real], now=NOW, cap=3, rule="R02")[1] == 0
          and A.digest([real], now=NOW, days=7)[0]["rule"] == "R01")


if __name__ == "__main__":
    test_registry()
    test_switch()
    test_approval()
    test_verdict()
    test_caps()
    test_record_and_undo()
    test_levels()
    test_rules_mode()
    test_rule_verdict()
    test_override_rate()
    test_rule_record()
    raise SystemExit(finish())
