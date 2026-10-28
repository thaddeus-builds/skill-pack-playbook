"""The market codes a scaffold accepts: ISO 3166-1 alpha-2, from `countries.tsv`.

A market is a country or region, written as its two-letter ISO code (`GB`, not `UK`; `HK`, `TW`, `US`). One standard spelling means a hub and the
skill packs it serves cannot disagree about a market, which would stop `facts sync-hub` from carrying a fact across. Kosovo, which ISO does not
list, is `XK`, the code the European Commission and most platforms use. A code is written in capitals; a lower-case one is refused with the
capital form, not changed silently.

`check(markets)` returns the list when every code is listed and appears once, else raises `ValueError` saying what to write. It is run by
`new_hub.py new` and `new_skill_pack.py` (the doors where a market first enters); the running kit keeps its own closed set (`[skill_pack].markets`).

Test: scaffold/tests/test_markets.py.
"""

from __future__ import annotations

from pathlib import Path

TABLE = Path(__file__).resolve().parent / "countries.tsv"
ALIASES = {"UK": "GB"}          # a code people write that ISO does not have, and the one it means


def table() -> dict[str, str]:
    """{code: name}."""
    rows = TABLE.read_text(encoding="utf-8").splitlines()[1:]
    return dict(r.split("\t", 1) for r in rows if r.strip())


def check(markets: list[str]) -> list[str]:
    known = table()
    problems = []
    for m in markets:
        if m in known:
            continue
        want = ALIASES.get(m.upper()) or (m.upper() if m.upper() in known else None)
        problems.append(f"{m!r}: write {want!r} ({known[want]})" if want else f"{m!r} is not an ISO 3166-1 alpha-2 code (two capital letters, "
                        f"e.g. HK, TW, GB, US; Kosovo is XK)")
    dup = sorted({m for m in markets if markets.count(m) > 1})
    if dup:
        problems.append(f"{', '.join(dup)} listed twice")
    if problems:
        raise ValueError("; ".join(problems))
    return markets
