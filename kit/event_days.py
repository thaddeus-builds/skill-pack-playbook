"""The account's event days: the sale, payday or holiday days whose spend and return differ for their own reasons. The rules alone: a pack keeps the
calendar in `ssot/event_days.tsv` and hands the rows to the engines that need them; no database, no platform.

    date        name                kind
    2026-11-11  autumn_sale         sale
    2026-12-25  midyear_payday      payday

  * `read()`: the file, strictly (a header with `date`, `name`, `kind`; each date an ISO day; a name and a kind in lower snake_case; a date and name
    once), as `Event` rows in date order. A problem is `registry_file_invalid` naming the line;
  * `days()` and `is_event()`: the set of dates, and the `is_event(iso_date)` that `kit.alerts.without_event_days` takes;
  * `kit.pacing.plan(event_days=...)` leaves these days out of the weekday weights and plans an event day from the account's earlier ones.

The kit does not say what a kind means or where a client's calendar comes from: a person or the pack's own import writes the file, the kit reads it.

Test: kit/tests/test_event_days.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

from kit.contract import SkillPackError
from kit.messages import msg
from kit.registry import read_tsv

COLUMNS = ("date", "name", "kind")
WORD = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Event:
    day: date
    name: str
    kind: str


def _bad(path: Path | str, problem: str) -> SkillPackError:
    return SkillPackError(msg("registry_file_invalid", f"{path}: {problem}", path=str(path), problem=problem))


def read(path: Path | str) -> list[Event]:
    """The events of an `event_days.tsv`, in date order. A missing file is `registry_file_missing` (a pack with no calendar does not call this)."""
    events, seen = [], set()
    for n, r in enumerate(read_tsv(path, COLUMNS), start=2):
        try:
            day = date.fromisoformat(r["date"])
        except ValueError:
            raise _bad(path, f"row {n}: {r['date']!r} is not a day (YYYY-MM-DD)") from None
        for col in ("name", "kind"):
            if not WORD.match(r[col]):
                raise _bad(path, f"row {n}: {col} {r[col]!r} is not lower snake_case")
        if (day, r["name"]) in seen:
            raise _bad(path, f"row {n}: {r['date']} {r['name']} is listed twice")
        seen.add((day, r["name"]))
        events.append(Event(day, r["name"], r["kind"]))
    return sorted(events, key=lambda e: (e.day, e.name))


def days(events: Iterable[Event]) -> set[date]:
    return {e.day for e in events}


def is_event(events: Iterable[Event]) -> Callable[[str], bool]:
    """The predicate `kit.alerts.without_event_days` takes: an ISO date string in, whether it is an event day."""
    iso = {e.day.isoformat() for e in events}
    return lambda d: d in iso
