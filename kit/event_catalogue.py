"""The public events a client may pick its event days from: the days most markets share, listed once, so the calendar (`kit.event_days`) does not start
empty and a person confirms or strikes a line instead of remembering a date. The rules alone: no file, no clock, no platform.

    candidates("US", 2026) -> [Candidate(day, name, kind, basis, markets), ...] in date order
    for_markets(["US", "GB"], 2026) -> the same for a client with several markets, each event once

A candidate is a *proposal*, never a fact: a client may not run a sale on it. `basis` says how the date is known:

  * `fixed`: the same calendar day every year (a double-digit day, a holiday on a date);
  * `rule`:  computed from a rule (the day after the fourth Thursday of November; Easter by the Gregorian computus and the days counted from it);
  * `table`: a lunar date, from a short table (`TABLE_YEARS`); a year outside it gives no such candidate, never a guess.

`markets` is the ISO 3166-1 alpha-2 codes the event is public in, or `*` for every market. A market the catalogue does not list gets the `*` events only.

What is not here, on purpose: a sale a platform schedules itself (its dates are announced late and name the platform, which the kit does not), and a client's
own promotions or paydays. Those go in the client's `ssot/event_days.tsv` by hand.

Test: kit/tests/test_event_catalogue.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

ALL = "*"
# Lunar New Year, the first day, by Gregorian year. The only lunar date here; a year outside the table has no such candidate.
LUNAR_NEW_YEAR = {2026: date(2026, 2, 17), 2027: date(2027, 2, 6), 2028: date(2028, 1, 26), 2029: date(2029, 2, 13), 2030: date(2030, 2, 3)}
TABLE_YEARS = (min(LUNAR_NEW_YEAR), max(LUNAR_NEW_YEAR))

MON, THU, SUN = 0, 3, 6
SEA = "ID MY PH SG TH VN TW"
MOTHERS_MAY = "US CA AU NZ JP CN TW HK IN DE SG"


@dataclass(frozen=True)
class Candidate:
    day: date
    name: str
    kind: str
    basis: str
    markets: str


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th (1-based) `weekday` (Monday 0) of the month."""
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def easter(year: int) -> date:
    """Easter Sunday (the Gregorian computus, the anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _black_friday(y: int) -> date:
    return nth_weekday(y, 11, THU, 4) + timedelta(days=1)


# (name, kind, basis, markets, the day in a year or None)
EVENTS: list[tuple[str, str, str, str, Callable[[int], date | None]]] = [
    ("new_year", "holiday", "fixed", ALL, lambda y: date(y, 1, 1)),
    ("lunar_new_year", "holiday", "table", "CN TW HK SG MY VN KR", lambda y: LUNAR_NEW_YEAR.get(y)),
    ("valentines_day", "gifting", "fixed", ALL, lambda y: date(y, 2, 14)),
    ("womens_day", "gifting", "fixed", "CN TW", lambda y: date(y, 3, 8)),
    ("white_day", "gifting", "fixed", "JP KR TW", lambda y: date(y, 3, 14)),
    ("easter", "holiday", "rule", "US CA GB AU NZ DE FR IT ES", easter),
    ("mothering_sunday", "gifting", "rule", "GB IE", lambda y: easter(y) - timedelta(days=21)),
    ("mothers_day", "gifting", "rule", MOTHERS_MAY, lambda y: nth_weekday(y, 5, SUN, 2)),
    ("fathers_day", "gifting", "rule", "US CA GB IN", lambda y: nth_weekday(y, 6, SUN, 3)),
    ("fathers_day", "gifting", "rule", "AU NZ", lambda y: nth_weekday(y, 9, SUN, 1)),
    ("six_eighteen", "sale", "fixed", "CN", lambda y: date(y, 6, 18)),
    ("nine_nine", "sale", "fixed", SEA, lambda y: date(y, 9, 9)),
    ("thanksgiving", "holiday", "rule", "US", lambda y: nth_weekday(y, 11, THU, 4)),
    ("thanksgiving", "holiday", "rule", "CA", lambda y: nth_weekday(y, 10, MON, 2)),
    ("singles_day", "sale", "fixed", "CN TW HK SG MY", lambda y: date(y, 11, 11)),
    ("black_friday", "sale", "rule", ALL, _black_friday),
    ("cyber_monday", "sale", "rule", ALL, lambda y: _black_friday(y) + timedelta(days=3)),
    ("double_twelve", "sale", "fixed", "CN " + SEA, lambda y: date(y, 12, 12)),
    ("christmas", "holiday", "fixed", ALL, lambda y: date(y, 12, 25)),
    ("boxing_day", "sale", "fixed", "GB CA AU NZ", lambda y: date(y, 12, 26)),
]
# The double-digit days of the south-east Asian markets (3.3 to 10.10), named by their date.
for _m, _name in ((3, "three_three"), (4, "four_four"), (5, "five_five"), (6, "six_six"), (7, "seven_seven"), (8, "eight_eight"), (10, "ten_ten")):
    EVENTS.append((_name, "sale", "fixed", SEA, lambda y, m=_m: date(y, m, m)))

_MARKET = re.compile(r"^[A-Z]{2}$")


def candidates(market: str | None, year: int) -> list[Candidate]:
    """The catalogue's events for `market` (an ISO alpha-2 code in capitals, None: only the events public everywhere) in `year`, in date order. A `table`
    event of a year the table does not cover is left out. The same name in the same market is listed once."""
    if market is not None and not _MARKET.match(market):
        raise ValueError(f"market {market!r} is not an ISO 3166-1 alpha-2 code in capitals")
    out, seen = [], set()
    for name, kind, basis, markets, rule in EVENTS:
        listed = markets.split()
        if listed != [ALL] and (market is None or market not in listed):
            continue
        day = rule(year)
        if day is None or (name, day) in seen:
            continue
        seen.add((name, day))
        out.append(Candidate(day, name, kind, basis, markets))
    return sorted(out, key=lambda c: (c.day, c.name))


def for_markets(markets: list[str], year: int) -> list[Candidate]:
    """The candidates of every market of a client in one list: an event public in several is listed once (its `markets` is the first market's list), in date order.
    An empty list gives the events public everywhere."""
    seen, out = set(), []
    for m in markets or [None]:
        for c in candidates(m, year):
            if (c.name, c.day) not in seen:
                seen.add((c.name, c.day))
                out.append(c)
    return sorted(out, key=lambda c: (c.day, c.name))


def rows(picked: list[Candidate]) -> list[dict[str, str]]:
    """The candidates a person kept, as the rows of `ssot/event_days.tsv` (`date`, `name`, `kind`): what `kit.event_days.read` takes."""
    return [{"date": c.day.isoformat(), "name": c.name, "kind": c.kind} for c in picked]
