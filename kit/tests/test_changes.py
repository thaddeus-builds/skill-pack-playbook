#!/usr/bin/env python3
"""kit.changes: the change record, on the paid-search skill pack's window arithmetic and planted events.

  * merge(): a recorded event one of our writes explains (same object, same new value, within the slack) is ours once; every other
    recorded event is external; the list is oldest first and starts at `since`;
  * after_start() and effect_windows(): 48 h and 7 days give D-8..D-2 against D+3..D+9 at 00:10 and 23:50 UTC; 36 h makes the
    time of day move the after window;
  * episodes(): a chain of changes to one object is one episode while each falls on or before the last after-window's last day;
  * overlaps(): changes to the parents and inside the object that fall in the episode's span;
  * beyond_noise(): a clear step is beyond noise, alternating noise of the same mean is not, a flat series with a step is beyond.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import changes  # noqa: E402
from kit.testing.check import check, finish  # noqa: E402

D = date.fromisoformat


def u(ts):
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def main() -> int:
    print("[1] merge")
    since = u("2026-09-01T00:00")
    own = [{"object": ("target", "k1"), "at": "2026-09-05T10:00:00+00:00", "before": "1.00", "after": "1.20"}]
    rec = [{"object": ("target", "k1"), "at": "2026-09-05T10:30:00+00:00", "before": "1.0", "after": "1.2"},       # ours, 30 min later
           {"object": ("target", "k1"), "at": "2026-09-07T08:00:00+00:00", "before": "1.2", "after": "0.9"},        # a hand edit
           {"object": ("target", "k2"), "at": "2026-09-05T10:00:00+00:00", "before": "1.0", "after": "1.2"},        # same value, another object
           {"object": ("target", "k1"), "at": "2026-09-05T13:00:00+00:00", "before": "1.0", "after": "1.2"},        # same value, 3 h later
           {"object": ("target", "k3"), "at": "2026-08-20T00:00:00+00:00", "before": "1", "after": "2"}]           # before `since`
    m = changes.merge(own, rec, since)
    check("our write once; the 30-minute echo is dropped; the others are external, oldest first",
          [(c["object"][1], c["source"], c["after"]) for c in m]
          == [("k1", "own", 1.2), ("k2", "external", 1.2), ("k1", "external", 1.2), ("k1", "external", 0.9)], m)
    check("nothing before `since`", all(c["at"] >= since for c in m))
    check("a value that is not a number reads as None, not a crash",
          changes.merge([], [{"object": ("campaign", "c"), "at": "2026-09-05T00:00", "before": "PAUSED", "after": "ENABLED"}], since)[0]["after"] is None)
    check("with no history the pack has pulled: all that is left is ours", [c["source"] for c in changes.merge(own, [], since)] == ["own"])
    check("history_missing: none when every object was read, else how many were not",
          changes.history_missing({"a", "b"}, {"a", "b", "c"}) is None and changes.history_missing({"a", "b", "c"}, {"a"}) == 2)

    print("[2] the windows")
    w48 = ((D("2026-08-24"), D("2026-08-30")), (D("2026-09-04"), D("2026-09-10")))
    check("48 h, 7 days: D-8..D-2 against D+3..D+9, at 00:10 and 23:50 UTC",
          all(changes.effect_windows(u(t), u(t), 48, 7) == w48 for t in ("2026-09-01T00:10", "2026-09-01T23:50")))
    check("36 h: then the time of day moves the after window",
          [changes.effect_windows(u(t), u(t), 36, 7)[1][0] for t in ("2026-09-01T00:10", "2026-09-01T23:50")] == [D("2026-09-03"), D("2026-09-04")])
    check("a chain's after window starts from its last change", changes.effect_windows(u("2026-09-01T10:00"), u("2026-09-03T10:00"), 48, 7)
          == ((D("2026-08-24"), D("2026-08-30")), (D("2026-09-06"), D("2026-09-12"))))

    print("[3] episodes")
    def ch(obj, at, parents=()):
        return {"object": obj, "at": at, "parents": list(parents), "before": 1, "after": 2, "source": "own"}
    cs = [ch(("target", "k1"), "2026-09-01T10:00:00+00:00", [("ad_group", "g1"), ("campaign", "c1")]),
          ch(("target", "k1"), "2026-09-08T10:00:00+00:00"),          # inside the first after window (09-04..09-10): joins
          ch(("target", "k1"), "2026-09-20T10:00:00+00:00"),          # after it: starts the next
          ch(("campaign", "c1"), "2026-09-02T10:00:00+00:00"),
          ch(("target", "k2"), "2026-09-02T10:00:00+00:00", [("ad_group", "g1"), ("campaign", "c1")])]
    cs.sort(key=lambda c: c["at"])
    eps = changes.episodes(cs, 48, 7)
    k1 = [e for e in eps if e["object"] == ("target", "k1")]
    check("a change inside the last after window joins the episode, a later one starts the next",
          len(k1) == 2 and len(k1[0]["changes"]) == 2 and len(k1[1]["changes"]) == 1, [(e["object"], len(e["changes"])) for e in eps])
    check("the episode's after window follows the chain's last change", k1[0]["after"] == (D("2026-09-11"), D("2026-09-17")), k1[0]["after"])
    check("an episode keeps its parents", k1[0]["parents"] == [("ad_group", "g1"), ("campaign", "c1")])
    anc, inner = changes.overlaps(k1[0], cs)
    check("the campaign's change in the span counts as a parent change; none inside a target", (anc, inner) == (1, 0), (anc, inner))
    camp = next(e for e in eps if e["object"] == ("campaign", "c1"))
    anc, inner = changes.overlaps(camp, cs)
    check("a campaign's episode counts the changes inside it", inner >= 2 and anc == 0, (anc, inner))

    print("[4] beyond noise")
    before, after = [10.0, 11.0, 9.0, 10.0, 10.0, 11.0, 9.0], [20.0, 21.0, 19.0, 20.0, 20.0, 21.0, 19.0]
    t, beyond = changes.beyond_noise(before, after, 3)
    check("a clear step: beyond noise", beyond is True and t > 3, (t, beyond))
    t, beyond = changes.beyond_noise([10.0, 14.0, 6.0, 12.0, 8.0, 10.0, 10.0], [14.0, 6.0, 10.0, 12.0, 8.0, 10.0, 10.0], 3)
    check("alternating noise with the same mean: within noise", beyond is False and abs(t) < 3, (t, beyond))
    check("a flat series that steps: no t, but beyond", changes.beyond_noise([5.0] * 7, [6.0] * 7, 3) == (None, True))
    check("a flat series that stays: nothing", changes.beyond_noise([5.0] * 7, [5.0] * 7, 3) == (None, None))
    check("under two days in a window: no reading", changes.beyond_noise([5.0], [6.0, 7.0], 3) == (None, None))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
