"""The report ledger's rules, no database, no files, no platform: settled days, restatement, one currency.

A platform's report is restated: a day exported during the day is partial, the same day exported later is complete, and a day's
orders keep moving until its attribution window has passed. The ledger keeps every export and reads the newest.

  * `export_day()`, `is_complete()`, `is_settled()`, `day_state()`: a day is *partial* if it was exported on the platform's own
    calendar day it ended, *complete* if exported after that day, *settled* once the export is `settle_days` or more days after it;
  * `Book`: the rules of an import, in memory. A row is identified by its natural key (platform, account, id, plan, placement,
    period). A row whose key exists adds a row only when its numbers changed, or when it finishes a day an earlier export held
    only in part, or settles one whose orders had not (the same numbers, a later export). The current row of a key is the
    newest by the export's own time, never by import order. A retraction keeps the import's rows (they leave the current set)
    and brings back the rows a later import left out because the retracted one already had their numbers;
  * a row that would count some spend twice (another key, the same entity, periods that share a day, a blank account, plan or
    placement standing for all of them) refuses the whole import (`Overlap`); amounts in two currencies under one owner refuse
    it too (`CurrencyMix`): nothing converts them until a rate is confirmed.

Who a row's id belongs to (a creative code in a name, a mapping an id taught) is the pack's: it passes each row its `owner`.

From the video-ads skill pack (`perfledger`, `perfread`: its report importer's tests are the cases here).

Test: kit/tests/test_ledger.py.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NK_FIELDS = ("platform", "account", "ref_kind", "ref_value", "unit_id", "placement", "date_from", "date_to")
PARTIAL, COMPLETE, SETTLED = "partial", "complete", "settled"


class Overlap(ValueError):
    """Rows that would count some spend twice."""

    def __init__(self, clash: list[dict]):
        super().__init__(f"{len(clash)} row(s) would count some spend twice")
        self.clash = clash


class CurrencyMix(ValueError):
    """One owner with amounts in two currencies."""

    def __init__(self, owners: dict[str, list[str]]):
        super().__init__(f"{len(owners)} owner(s) would have amounts in two currencies")
        self.owners = owners


# ---- the day -------------------------------------------------------------------

def export_day(exported_at: str, tz: str) -> str:
    """The platform's calendar day on which an export (`YYYY-MM-DDTHH:MM:SSZ`, UTC) was taken."""
    dt = datetime.strptime(exported_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz)).date().isoformat()


def is_complete(exported_at: str, date_to: str, tz: str) -> bool:
    """A day is finished only if it was exported after it ended: a same-day export holds a partial day."""
    return export_day(exported_at, tz) > date_to


def is_settled(exported_at: str, date_to: str, tz: str, settle_days: int) -> bool:
    """A day's orders will not move again once its export is `settle_days` or more days after it."""
    return date.fromisoformat(export_day(exported_at, tz)) >= date.fromisoformat(date_to) + timedelta(days=int(settle_days))


def day_state(exported_at: str, date_to: str, tz: str, settle_days: int) -> str:
    if is_settled(exported_at, date_to, tz, settle_days):
        return SETTLED
    return COMPLETE if is_complete(exported_at, date_to, tz) else PARTIAL


# ---- keys and fingerprints --------------------------------------------------------

def natural_key(row: dict) -> str:
    return hashlib.sha256("\x1f".join(str(row.get(c, "")) for c in NK_FIELDS).encode("utf-8")).hexdigest()[:24]


def fingerprint(row: dict, metrics: tuple[str, ...]) -> str:
    """The fingerprint of a row's numbers, so a re-export with the same numbers adds nothing."""
    payload = {c: row.get(c) for c in metrics}
    payload["extra"] = row.get("extra")
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]


# ---- double counting ----------------------------------------------------------------

def _compat(a: str, b: str) -> bool:
    """Two accounts, plans or placements can refer to the same spend when equal or when one is blank: blank means "all"."""
    return a == b or not a or not b


def conflict(a: dict, b: dict) -> bool:
    """Would counting both rows count some spend twice? Same platform, compatible account, plan and placement, periods that share
    a day, and not the very same key (the same key is a restatement: the newest export wins). The caller has established that the
    two are the same entity; the id kind is deliberately not compared, because one entity reached by an id in one export and by its
    name in another is still one entity."""
    if a["platform"] != b["platform"]:
        return False
    if not (_compat(a.get("account", ""), b.get("account", "")) and _compat(a.get("unit_id", ""), b.get("unit_id", ""))
            and _compat(a.get("placement", ""), b.get("placement", ""))):
        return False
    if natural_key(a) == natural_key(b):
        return False
    return a["date_from"] <= b["date_to"] and b["date_from"] <= a["date_to"]


def single_currency(rows: list[dict]) -> dict[str, list[str]]:
    """{owner: currencies} for every owner whose rows name two currencies or more."""
    seen: dict[str, set[str]] = {}
    for r in rows:
        if r.get("owner") is not None:
            seen.setdefault(r["owner"], set()).add(r.get("currency") or "")
    return {o: sorted(c) for o, c in sorted(seen.items()) if len(c) > 1}


# ---- the book -------------------------------------------------------------------------

class Book:
    """Imports in the order they landed. A row is a dict with the `NK_FIELDS`, its `metrics` (numbers), optionally `extra`,
    `currency` and `owner` (who it belongs to, or None)."""

    def __init__(self, tz: str, settle_days: int, metrics: tuple[str, ...]):
        self.tz, self.settle_days, self.metrics = tz, int(settle_days), tuple(metrics)
        self.imports: list[dict] = []

    # -- reading
    def live(self) -> list[dict]:
        return [i for i in self.imports if not i["retracted"]]

    def current(self) -> list[dict]:
        """The current row of each key (the newest export, then the later import), with its `state`."""
        best: dict[str, tuple] = {}
        for imp in self.live():
            for r in imp["rows"]:
                rank = (imp["exported_at"], imp["id"])
                if r["nk"] not in best or rank > best[r["nk"]][0]:
                    best[r["nk"]] = (rank, imp, r)
        return [{**r, "import_id": imp["id"], "exported_at": imp["exported_at"],
                 "state": day_state(imp["exported_at"], r["date_to"], self.tz, self.settle_days)}
                for _, imp, r in sorted(best.values(), key=lambda x: (x[2]["date_from"], x[2]["nk"]))]

    def _last(self, nk: str) -> tuple[dict, dict] | None:
        found = [(imp, r) for imp in self.live() for r in imp["rows"] if r["nk"] == nk]
        return max(found, key=lambda x: (x[0]["exported_at"], x[0]["id"])) if found else None

    # -- writing
    def add(self, rows: list[dict], exported_at: str) -> dict:
        """One import. Raises `Overlap` or `CurrencyMix` and changes nothing. {import_id, rows_new, rows_unchanged}."""
        keyed = []
        for row in rows:
            r = dict(row)
            r["nk"], r["row_sha"] = natural_key(r), fingerprint(r, self.metrics)
            keyed.append(r)
        seen: set[str] = set()
        for r in keyed:
            if r["nk"] in seen:
                raise ValueError(f"two rows of the same key in one import: {r['ref_value']}")
            seen.add(r["nk"])
        clash = self._overlaps(keyed)
        if clash:
            raise Overlap(clash)
        plan = []
        for r in keyed:
            last = self._last(r["nk"])
            same = bool(last and last[1]["row_sha"] == r["row_sha"])
            confirms = same and exported_at > last[0]["exported_at"] and (
                (not is_complete(last[0]["exported_at"], r["date_to"], self.tz) and is_complete(exported_at, r["date_to"], self.tz))
                or (not is_settled(last[0]["exported_at"], r["date_to"], self.tz, self.settle_days)
                    and is_settled(exported_at, r["date_to"], self.tz, self.settle_days)))
            plan.append((r, (not same) or confirms, last[0]["id"] if same else None))
        imp = {"id": len(self.imports) + 1, "exported_at": exported_at, "retracted": False,
               "rows": [r for r, add, _ in plan if add], "unchanged": [(m, r) for r, add, m in plan if not add]}
        self.imports.append(imp)
        bad = single_currency([r for i in self.live() for r in i["rows"]])
        if bad:
            self.imports.pop()
            raise CurrencyMix(bad)
        return {"import_id": imp["id"], "rows_new": len(imp["rows"]), "rows_unchanged": len(imp["unchanged"])}

    def _overlaps(self, keyed: list[dict]) -> list[dict]:
        existing = [r for i in self.live() for r in i["rows"]]
        by: dict[tuple, list] = {}
        for e in existing:
            by.setdefault((e["platform"], e.get("owner") or f"{e['ref_kind']}:{e['ref_value']}"), []).append(e)
        found = []
        for r in keyed:
            mine = by.setdefault((r["platform"], r.get("owner") or f"{r['ref_kind']}:{r['ref_value']}"), [])
            for other in mine:
                if conflict(r, other):
                    found.append({"id": r.get("owner") or r["ref_value"], "this": f"{r['date_from']}..{r['date_to']}",
                                  "other": f"{other['date_from']}..{other['date_to']}"})
            mine.append(r)
        return found

    def retract(self, import_id: int) -> dict:
        """Switch an import off. The rows a later import left out because this one already had their numbers come back, under
        that later import: that export still says them."""
        imp = next((i for i in self.imports if i["id"] == import_id), None)
        if imp is None or imp["retracted"]:
            raise ValueError(f"no live import #{import_id}")
        imp["retracted"] = True
        back = 0
        for other in self.live():
            keep = []
            for matched, r in other["unchanged"]:
                if matched == import_id:
                    other["rows"].append(r)
                    back += 1
                else:
                    keep.append((matched, r))
            other["unchanged"] = keep
        return {"import_id": import_id, "rows_restored": back}
