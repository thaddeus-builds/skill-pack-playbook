#!/usr/bin/env python3
"""kit.event_catalogue: the public events a client may pick its event days from, against dates known independently of the code. Every date below was
worked out from the calendar rule by hand."""

import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import event_catalogue as cat, event_days  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402


def on(market, year):
    return {(c.name): c.day for c in cat.candidates(market, year)}


def main() -> int:
    _shop.use()
    print("[1] the rules against known dates")
    check("Easter: 2026-04-05, 2027-03-28, 2028-04-16, 2025-04-20", [cat.easter(y) for y in (2026, 2027, 2028, 2025)] == [date(2026, 4, 5), date(2027, 3, 28), date(2028, 4, 16), date(2025, 4, 20)])
    us = on("US", 2026)
    check("the fourth Thursday of November 2026 is the 26th; Black Friday the 27th, Cyber Monday the 30th",
          us["thanksgiving"] == date(2026, 11, 26) and us["black_friday"] == date(2026, 11, 27) and us["cyber_monday"] == date(2026, 11, 30), us)
    check("Mother's Day is the second Sunday of May (2026-05-10) and Father's Day the third Sunday of June (2026-06-21)", us["mothers_day"] == date(2026, 5, 10) and us["fathers_day"] == date(2026, 6, 21), us)
    gb = on("GB", 2026)
    check("Mothering Sunday is three weeks before Easter (2026-03-15); Boxing Day the 26th", gb["mothering_sunday"] == date(2026, 3, 15) and gb["boxing_day"] == date(2026, 12, 26), gb)
    check("in Australia Father's Day is the first Sunday of September (2026-09-06)", on("AU", 2026)["fathers_day"] == date(2026, 9, 6))
    check("in Canada Thanksgiving is the second Monday of October (2026-10-12)", on("CA", 2026)["thanksgiving"] == date(2026, 10, 12))
    check("every weekday rule lands on its weekday, over ten years",
          all(on("US", y)["thanksgiving"].weekday() == 3 and on("US", y)["black_friday"].weekday() == 4 and on("US", y)["cyber_monday"].weekday() == 0
              and on("US", y)["mothers_day"].weekday() == 6 and cat.easter(y).weekday() == 6 for y in range(2024, 2034)))

    print("[2] the markets")
    check("a market the catalogue does not list, or none, gets only the events public everywhere",
          set(on(None, 2026)) == {"new_year", "valentines_day", "black_friday", "cyber_monday", "christmas"} and on("ZZ", 2026) == on(None, 2026))
    cn, sg = on("CN", 2026), on("SG", 2026)
    check("China: Singles' Day on 11-11, the 6.18 day, Women's Day, the Lunar New Year of 2026 (02-17), and not Thanksgiving",
          cn["singles_day"] == date(2026, 11, 11) and cn["six_eighteen"] == date(2026, 6, 18) and cn["womens_day"] == date(2026, 3, 8)
          and cn["lunar_new_year"] == date(2026, 2, 17) and "thanksgiving" not in cn, cn)
    check("Singapore has the double-digit days 3.3 to 10.10 and 12.12 on their dates", all(sg[n] == date(2026, m, m) for n, m in
          (("three_three", 3), ("four_four", 4), ("five_five", 5), ("six_six", 6), ("seven_seven", 7), ("eight_eight", 8), ("nine_nine", 9), ("ten_ten", 10), ("double_twelve", 12))), sg)
    sg27 = on("SG", 2027)
    check("Singapore: National Day on 08-09 every year, and the moon-based holidays of the Ministry of Manpower's list for 2026 and 2027",
          sg["singapore_national_day"] == date(2026, 8, 9) and sg27["singapore_national_day"] == date(2027, 8, 9)
          and (sg["hari_raya_puasa"], sg["hari_raya_haji"], sg["deepavali"]) == (date(2026, 3, 21), date(2026, 5, 27), date(2026, 11, 8))
          and (sg27["hari_raya_puasa"], sg27["hari_raya_haji"], sg27["deepavali"]) == (date(2027, 3, 10), date(2027, 5, 17), date(2027, 10, 28)), (sg, sg27))
    sg28, my26 = on("SG", 2028), on("MY", 2026)
    check("a year outside the Singapore table lists none of its moon-based holidays, never a guess (National Day stays: it is fixed)",
          not {"hari_raya_puasa", "hari_raya_haji", "deepavali"} & set(sg28) and "singapore_national_day" in sg28 and "lunar_new_year" in sg28, sorted(sg28))
    check("those dates are Singapore's: Malaysia, which keeps other days, gets none of them", not {"hari_raya_puasa", "hari_raya_haji", "deepavali", "singapore_national_day"} & set(my26), sorted(my26))
    check("a market code that is not two capitals is refused", all(_refused(m) for m in ("us", "USA", "", "U1")))

    print("[3] the table has an end, and what a candidate says of itself")
    check("a lunar year outside the table has no Lunar New Year candidate, not a guess", "lunar_new_year" not in on("CN", cat.TABLE_YEARS[1] + 1) and "lunar_new_year" in on("CN", cat.TABLE_YEARS[1]))
    ok = all(c.basis in ("fixed", "rule", "table") and c.kind in ("sale", "holiday", "gifting") for y in (2026, 2029) for m in (None, "US", "CN", "SG", "GB") for c in cat.candidates(m, y))
    check("every candidate names how its date is known and a kind", ok)
    check("the list is in date order and a name is not listed twice on one day", all(
        [c.day for c in cs] == sorted(c.day for c in cs) and len({(c.name, c.day) for c in cs}) == len(cs) for cs in (cat.candidates(m, 2027) for m in ("US", "CN", "SG", "GB", "AU"))))

    print("[3b] a name is the identity across years, and what is left to ask")
    markets = sorted({m for *_, ms, _r in cat.EVENTS for m in ms.split() if m != cat.ALL}) + [None]
    years = range(cat.TABLE_YEARS[0], cat.TABLE_YEARS[1] + 1)
    listed = lambda m: {n for n, _k, _b, ms, _r in cat.EVENTS if cat.ALL in ms.split() or m in ms.split()}
    left_out = lambda m, y: {n for n, t in cat.TABLES.items() if y not in t and n in listed(m)}   # a `table` event of a year its table does not cover is the only name that may be missing
    drift = {m: [sorted({c.name for c in cat.candidates(m, y)} | left_out(m, y)) for y in years] for m in markets}
    check("every market lists the same names in every year of the table: a name is the identity of an event, so a strike by name holds for every year (a table event is missing only in a year its table leaves out)",
          all(all(names == per[0] for names in per) for per in drift.values()), {m: [len(n) for n in per] for m, per in drift.items()})
    check("each table event is listed in every year its table covers, in the market it is for", all(
        n in {c.name for c in cat.candidates("SG" if n != "lunar_new_year" else "CN", y)} for n, t in cat.TABLES.items() for y in t))
    c26 = cat.candidates("US", 2026)
    black = next(c for c in c26 if c.name == "black_friday")
    from kit import event_days  # noqa: E402
    done = event_days.from_rows([{"date": black.day.isoformat(), "name": "black_friday", "kind": "sale"}])
    check("nothing confirmed or struck: every candidate is still to ask, in the order given", cat.open_candidates(c26) == c26 and cat.open_candidates(c26, [], []) == c26)
    check("a confirmed day (the same name on the same day) is no longer asked, and the rest keep their order", [c.name for c in cat.open_candidates(c26, done)] == [c.name for c in c26 if c.name != "black_friday"])
    check("a strike is by name: it holds for every year", all("black_friday" not in {c.name for c in cat.open_candidates(cat.candidates("US", y), struck=["black_friday"])} for y in (2026, 2027, 2028)))
    c27 = cat.candidates("US", 2027)
    check("a confirmed day of last year does not hide this year's (its date moved): Black Friday of 2027 is asked again", "black_friday" in {c.name for c in cat.open_candidates(c27, done)})
    check("both at once, and a name that matches nothing changes nothing", [c.name for c in cat.open_candidates(c26, done, ["cyber_monday", "no_such_event"])] == [c.name for c in c26 if c.name not in ("black_friday", "cyber_monday")])

    print("[4] the pick becomes the calendar")
    picked = [c for c in cat.candidates("US", 2026) if c.name in ("black_friday", "cyber_monday")]
    f = Path(tmp_dir("event-catalogue-")) / "event_days.tsv"
    f.write_text("date\tname\tkind\n" + "".join(f"{r['date']}\t{r['name']}\t{r['kind']}\n" for r in cat.rows(picked)), encoding="utf-8")
    check("the rows of what a person kept are read back by kit.event_days as the same days", event_days.days(event_days.read(f)) == {date(2026, 11, 27), date(2026, 11, 30)})
    multi = cat.for_markets(["US", "CN", "SG", "GB"], 2027)
    check("a client with several markets: each event once (New Year, Christmas, Black Friday are public in all four), in date order",
          len({(c.name, c.day) for c in multi}) == len(multi) and [c.day for c in multi] == sorted(c.day for c in multi)
          and sum(c.name == "new_year" for c in multi) == 1 and cat.for_markets([], 2027) == cat.candidates(None, 2027), len(multi))
    f.write_text("date\tname\tkind\n" + "".join(f"{r['date']}\t{r['name']}\t{r['kind']}\n" for r in cat.rows(multi)), encoding="utf-8")
    try:
        event_days.read(f)
        every = True
    except Exception as e:  # noqa: BLE001
        every = str(e)
    check("every name and kind the catalogue uses passes the calendar's own strict reader", every is True, every)
    return finish()


def _refused(m) -> bool:
    try:
        cat.candidates(m, 2026)
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
