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
    check("six levels, L0 to L5, the first four built",
          [l for l, _ in A.LEVELS] == ["L0", "L1", "L2", "L3", "L4", "L5"] and A.BUILT == ("L0", "L1", "L2", "L3"))
    check("every proof label names a built level or none (undo)",
          set(A.PROOFS) == {"tty", "relay", "approval", "auto", "undo"}
          and {v for v in A.PROOFS.values() if v} <= set(A.BUILT))
    check("autonomy.py reads no database, file or clock of its own",
          not any(w in (Path(A.__file__).read_text(encoding="utf-8"))
                  for w in ("sqlite3", "datetime.now", "date.today", "time.time", "open(os.path.join(raw")))


if __name__ == "__main__":
    test_registry()
    test_switch()
    test_approval()
    test_verdict()
    test_caps()
    test_record_and_undo()
    test_levels()
    raise SystemExit(finish())
