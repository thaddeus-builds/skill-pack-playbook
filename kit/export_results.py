"""The `ads.results/2` rows (and, for one release, the `ads.results/1` rows): the report's current rows with each creative's stage and, for one that has earned a verdict, its fission score. One row per report row that
resolves to a creative, in the columns of the contract (`contracts.d/ads.results-2.schema.json`): the row's natural key and `nk`, the export time, whether the day was
complete when exported, whether it is settled, whether its key was ever restated, the row's `currency` (ISO 4217), the counts and the ratios as exported, then the creative's `stage` (its state in the
life document) and `stage_reason`, and for a creative that has earned a verdict `fission` (0 to 1, `kit.fission`) with `scored_at`. A creative with no verdict has both
blank: unknown, never 0. No database, no file, no clock, no platform: the pack hands over the rows its report ledger holds as current (it knows the platform's time zone
and how many days settle a day, so `complete`, `settled` and `restated` are its flags) and the creatives' days (the same `Source` the life document reads), and writes
what `compute()` returns.

    {rows [{<column>: text | None}], counts {rows, creatives}, scored, scored_at, benchmark {cost, volume, n} | None, unscored {<state>: count},
     scores [{creative, state, reason, fission}], warnings, warning_codes}

`rows` are ready for `kit.contracts.write("ads.results", 2, doc["rows"], out)`: every cell is text as the contract wants it (a flag `1` or `0`, a whole number without a
point), sorted by key so the same rows are the same bytes. Writing is the pack's: a `creative` module cannot import `kit.contracts`. Without `life` only the facts are
given (the pack's own `stage`, if the rows have one, is kept).

Money: the pack hands over `spend`, `gmv`, `net_gmv` and `cpa` and the ledger's currency (`Source.currency`, or `currency` on a row that differs), an ISO 4217 code of
three capitals. Version 2 (the default) writes them under those names with the `currency` column. `compute(..., version=1)` writes the first version for the release in
which a consumer has not moved: the same file with the names `spend_cny`, `gmv_cny`, `net_gmv_cny`, `cpa_cny` and no currency column; it holds CNY only, so a row in
another currency is refused (`compute_input_invalid`, naming `currency`) rather than written under a name that says CNY. A pack that gives no currency at all gets
version 1 as before (the file does not say which, ROADMAP X11) and is refused by version 2.

From the video-ads skill pack (`scripts/export_results.py` `results` and `export`, `scripts/_lib/contracts.py` `RESULTS_COLUMNS`; its cases are this module's test, over a
synthetic fixture).

Test: kit/tests/test_export_results.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from kit import compute_life, fission
from kit.contract import SkillPackError
from kit.messages import coded, msg

KIND, VERSION = "ads.results", 2
VERSIONS = (1, 2)
OLD_NAMES = {"spend": "spend_cny", "gmv": "gmv_cny", "net_gmv": "net_gmv_cny", "cpa": "cpa_cny"}
COUNTS = ("spend", "impressions", "clicks", "plays", "plays_3s", "plays_complete", "conversions", "gmv", "net_conversions", "net_gmv")
RATIOS = ("ctr", "play_3s_rate", "completion_rate", "cpa", "roi")
FLAGS = ("complete", "settled", "restated")
KEY = ("creative_code", "platform", "account", "ref_kind", "ref_value", "unit_id", "placement", "date_from", "date_to")
COLUMNS = (*KEY[:-2], "date_from", "date_to", "nk", "exported_at", *FLAGS, "currency", *COUNTS, *RATIOS, "stage", "verdict", "verdict_reason")
OPTIONAL = ("fission", "scored_at", "stage_reason")
REQUIRED = ("creative_code", "platform", "ref_kind", "ref_value", "date_from", "date_to", "nk", "exported_at", *FLAGS, "currency")
TEXT = ("creative_code", "platform", "account", "ref_kind", "ref_value", "unit_id", "placement", "nk", "exported_at", "currency", "stage", "stage_reason", "verdict", "verdict_reason")


@dataclass
class Source:
    """What the pack hands over.

    rows   the current report rows that resolve to a creative, each a dict of the contract's columns (`COLUMNS`, and `stage_reason` if it keeps one): the key, `nk`,
           `exported_at` (ISO 8601 with its zone), the flags `complete`, `settled`, `restated` (a flag, 1 or 0), the counts and ratios as numbers (None when the platform
           gave none: unknown, never 0). `creative_code` is the creative's id in `life`
    life   the creatives' days, as `kit.compute_life.Source` has them, or None for the facts only
    currency  the ISO 4217 code (three capitals) of the money in `rows`, for every row that has no `currency` of its own; None when the pack does not know it
    """
    rows: list
    life: compute_life.Source | None = None
    currency: str | None = None


def _bad(part: str, problem: str) -> SkillPackError:
    return SkillPackError(msg("compute_input_invalid", f"the pack's tables give {part} {problem}", part=part, problem=problem))


def _iso(v) -> bool:
    return isinstance(v, str) and len(v) == 3 and v.isascii() and v.isalpha() and v.isupper()


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _currency(r: dict, src: Source):
    return r.get("currency") if r.get("currency") is not None else src.currency


def check(src: Source, at: str, version: int = VERSION) -> None:
    """Refuse a `Source` the file cannot be written from, naming the part (`compute_input_invalid`)."""
    if version not in VERSIONS:
        raise _bad("version", f"{version!r}, which is not one of {', '.join(map(str, VERSIONS))}")
    if not isinstance(at, str) or not at.strip():
        raise _bad("at", f"{at!r}, which is not a time")
    if src.currency is not None and not _iso(src.currency):
        raise _bad("currency", f"{src.currency!r}, which is not an ISO 4217 code (three capitals)")
    if not isinstance(src.rows, (list, tuple)):
        raise _bad("rows", "that are not a list")
    known = {*COLUMNS, *OPTIONAL}
    seen: dict[str, int] = {}
    for i, r in enumerate(src.rows):
        part = f"rows[{i}]"
        if not isinstance(r, dict):
            raise _bad(part, "that is not a dict of columns")
        absent = [c for c in REQUIRED if c != "currency" and (r.get(c) is None or (isinstance(r[c], str) and not r[c].strip()))]
        cur = _currency(r, src)
        if version == 2 and (cur is None or (isinstance(cur, str) and not cur.strip())):
            absent.append("currency")
        if absent:
            raise _bad(part, f"without {', '.join(absent)}")
        stray = sorted(set(r) - known)
        if stray:
            raise _bad(part, f"with {', '.join(stray)}, which are not columns of the contract")
        for c in TEXT:
            if r.get(c) is not None and not isinstance(r[c], str):
                raise _bad(f"{part}.{c}", f"{r[c]!r}, which is not text")
        if cur is not None and not _iso(cur):
            raise _bad(f"{part}.currency", f"{cur!r}, which is not an ISO 4217 code (three capitals)")
        if version == 1 and cur is not None and cur != "CNY":
            raise _bad(f"{part}.currency", f"{cur}, which version 1 cannot hold (its money columns are named for CNY): write version 2")
        for c in FLAGS:
            if r[c] not in (0, 1, True, False):
                raise _bad(f"{part}.{c}", f"{r[c]!r}, which is not a flag (1 or 0)")
        for c in COUNTS:
            if r.get(c) is not None and not (_number(r[c]) and r[c] >= 0):
                raise _bad(f"{part}.{c}", f"{r[c]!r}, which is not a number of 0 or more")
        for c in RATIOS:
            if r.get(c) is not None and not _number(r[c]):
                raise _bad(f"{part}.{c}", f"{r[c]!r}, which is not a number")
        for c in ("date_from", "date_to"):
            try:
                date.fromisoformat(r[c])
            except (TypeError, ValueError):
                raise _bad(f"{part}.{c}", f"{r[c]!r}, which is not a day (YYYY-MM-DD)") from None
        if r["date_from"] > r["date_to"]:
            raise _bad(f"{part}.date_from", f"{r['date_from']}, which is after date_to {r['date_to']}")
        if r["nk"] in seen:
            raise _bad(f"{part}.nk", f"{r['nk']!r}, which rows[{seen[r['nk']]}] has too: a key is one row")
        seen[r["nk"]] = i
    if src.life is not None:
        compute_life.check(src.life)


def _cell(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)
    return str(v)


def compute(src: Source, k: dict, *, at: str, version: int = VERSION) -> dict:
    """The rows of the file, stamped `at` (ISO 8601 with its zone) when a creative is given a score. `k` is the thresholds in effect: the `life_*` and `fission_*` rows.
    `version` 2 is the contract; 1 is the same file for a consumer that has not moved (`_cny` names, no `currency`, CNY only)."""
    check(src, at, version)
    scored, bench, omitted, warnings, staged = {}, None, {}, [], False
    if src.life is not None and src.life.creatives:
        life = compute_life.compute(src.life, k)
        counted = {("", cid): c["days"] for cid, c in src.life.creatives.items()}
        scored, bench, omitted = fission.scores([{**r, "source": ""} for r in life["rows"]], counted, int(k["fission_window_days"]), int(k["fission_benchmark_min"]))
        staged = True
        proven = sum(1 for v in scored.values() if fission.speaks(v["state"], v["reason"]) and v["reason"] != "weak_creative")
        if bench is None and proven:
            need = max(3, int(k["fission_benchmark_min"]))
            warnings.append(msg("fission_benchmark_insufficient", f"{proven} proven creative(s), {need} needed for a benchmark: only the weak_creative zeros are scored",
                                have=proven, need=need))
    rows = []
    for r in sorted(src.rows, key=lambda x: tuple(x.get(c) or "" for c in KEY)):
        full = {**r, "currency": _currency(r, src)}
        out = {(OLD_NAMES.get(c, c) if version == 1 else c): _cell(full.get(c)) for c in (*COLUMNS, *OPTIONAL) if not (version == 1 and c == "currency")}
        sc = scored.get(r["creative_code"])
        if staged and sc:
            out["stage"], out["stage_reason"] = sc["state"], sc["reason"] or None
            if sc["fission"] is not None:
                out["fission"], out["scored_at"] = f"{sc['fission']:.2f}", at
        rows.append(out)
    given = {c: v for c, v in scored.items() if v["fission"] is not None}
    return {"rows": rows, "counts": {"rows": len(rows), "creatives": len({r["creative_code"] for r in rows})},
            "scored": len(given), "scored_at": at if given else None,
            "benchmark": None if bench is None else {"cost": round(bench["cost"], 2), "volume": round(bench["volume"], 3), "n": bench["n"]},
            "unscored": omitted, "scores": [{"creative": c, **{x: v[x] for x in ("state", "reason", "fission")}} for c, v in given.items()],
            **coded("warnings", warnings)}
