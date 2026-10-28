#!/usr/bin/env python3
"""kit.event_days: the account's event-day calendar (ssot/event_days.tsv), read strictly, on synthetic files. Every date and name is invented."""

import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import alerts, event_days, messages  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402

HEAD = "date\tname\tkind\n"


def write(body: str, head: str = HEAD) -> Path:
    p = Path(tmp_dir("event-days-")) / "event_days.tsv"
    p.write_text(head + body, encoding="utf-8")
    return p


def refused(body: str, head: str = HEAD) -> str | None:
    try:
        event_days.read(write(body, head))
    except SkillPackError as e:
        return getattr(e, "code", None) or str(e)
    return None


def main() -> int:
    _shop.use()
    print("[1] reading the calendar")
    ev = event_days.read(write("2026-11-11\tdemo_sale\tsale\n2026-10-30\tdemo_payday\tpayday\n"))
    check("rows come back as events in date order", [(e.day, e.name, e.kind) for e in ev] == [(date(2026, 10, 30), "demo_payday", "payday"), (date(2026, 11, 11), "demo_sale", "sale")], ev)
    check("two events on one day are both kept, and the day is in the set once",
          len(event_days.read(write("2026-11-11\ta_sale\tsale\n2026-11-11\tb_sale\tsale\n"))) == 2
          and event_days.days(event_days.read(write("2026-11-11\ta_sale\tsale\n2026-11-11\tb_sale\tsale\n"))) == {date(2026, 11, 11)})
    check("a header with only the three columns and no rows is an empty calendar", event_days.read(write("")) == [])

    print("[2] a bad file is refused, naming the row")
    check("a day that is not a day", refused("2026-13-40\tdemo_sale\tsale\n") is not None)
    check("a name that is not lower snake_case", refused("2026-11-11\tDemo Sale\tsale\n") is not None)
    check("a kind that is not lower snake_case", refused("2026-11-11\tdemo_sale\tSale!\n") is not None)
    check("the same day and name twice", refused("2026-11-11\tdemo_sale\tsale\n2026-11-11\tdemo_sale\tsale\n") is not None)
    check("a header that lacks a column", refused("2026-11-11\tdemo_sale\n", "date\tname\n") is not None)
    try:
        event_days.read(write("", "date\tname\tkind\n").with_name("absent.tsv"))
        gone = None
    except SkillPackError as e:
        gone = e
    check("a missing file is an error (a pack with no calendar does not call this)", gone is not None)

    print("[2b] the same rules over rows a pack holds elsewhere")
    rows = [{"date": "2026-11-11", "name": "demo_sale", "kind": "sale"}, {"date": "2026-10-30", "name": "demo_payday", "kind": "payday"}]
    got = event_days.from_rows(rows)
    check("rows give the same events as the file would, in date order", got == event_days.read(write("2026-11-11\tdemo_sale\tsale\n2026-10-30\tdemo_payday\tpayday\n")) and got[0].name == "demo_payday")
    check("no rows is no events", event_days.from_rows([]) == [])

    def bad(rs, **kw):
        try:
            event_days.from_rows(rs, "the decision", **kw)
        except SkillPackError as e:
            return messages.failure(e)["code"], str(e)
        return None, ""
    cases = {"a day that is not a day": ([{**rows[0], "date": "11 Nov"}], "row 1"), "a date that is a number": ([{**rows[0], "date": 5}], "row 1"),
             "a name with capitals": ([{**rows[0], "name": "Demo Sale"}], "name"), "a kind that is not text": ([{**rows[0], "kind": None}], "kind"),
             "a row without its kind": ([{"date": "2026-11-11", "name": "demo_sale"}], "without kind"), "a row that is not a dict": (["x"], "without date"),
             "the same day and name twice": ([rows[0], rows[0]], "listed twice"),
             "a name that is not text but reads as a word": ([{**rows[0], "name": type("W", (), {"__str__": lambda self: "demo_sale"})()}], "name")}
    got = {n: bad(rs) for n, (rs, _) in cases.items()}
    check("each is registry_file_invalid, naming the source, the row and the problem", all(c == "registry_file_invalid" and "the decision" in m and w in m for (c, m), (_, w) in zip(got.values(), cases.values())), got)
    check("the row number counts from first_row", "row 7" in bad([rows[0], {**rows[1], "date": "x"}], first_row=6)[1])
    try:
        event_days.read(write("2026-11-11\tdemo_sale\tsale\n2026-13-40\tdemo_sale\tsale\n"))
        msg = ""
    except SkillPackError as e:
        msg = str(e)
    check("and a file counts from 2, under its header, as before: its second data row is row 3", "row 3" in msg and "event_days.tsv" in msg, msg)

    print("[3] the hand-off to alerts")
    ev = event_days.read(write("2026-10-17\tdemo_sale\tsale\n"))
    iso = lambda n: f"2026-10-{n:02d}"  # noqa: E731
    pts = [alerts.Point(iso(d), 100.0, 300.0) for d in range(20, 11, -1)]
    kept, dropped = alerts.without_event_days(pts, event_days.is_event(ev))
    check("is_event is what without_event_days takes: the sale day leaves the baseline", dropped == [iso(17)] and all(p.date != iso(17) for p in kept[1:]), (dropped, kept))
    check("days() is the set of dates", event_days.days(ev) == {date(2026, 10, 17)})
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
