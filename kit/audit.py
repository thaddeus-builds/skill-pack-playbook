"""The findings of an ads account audit: the rules alone, no database, no platform, no wording.

`findings(f, k)` takes the facts a pack gathered from its own tables (below) and the thresholds it set, and returns the findings that cross them, most
severe first: `{"finding": <code>, "severity": high|medium|info, "params": {...}}`. A finding is a code and the numbers behind it. The sentence, and the
steps for a person (where to look in this platform's screens, what to change, what the next pull should show), are the pack's: it names the platform's
own screens and its own column words, which do not enter the kit. The finding code is the pack's message code, so `daily` gives it the stable id
`audit:<finding>`. A finding only one pack has (a join that exists in its report alone) is that pack's: it adds it to the list and calls `order()`.

Facts `f` (a part that is None or absent gives no finding):

    issues         {ads, spend, days, examples}      ads the platform limits or disapproves that spent in the window
    waste          {ads, spend, share, examples}     the spend on ads with no result
    old            {ads, share, examples}            the share of spend on ads first seen `audit_old_days` ago or more
    concentration  {n, share, examples}              the share the top `n` ads took
    budget         {use, spend_per_day, daily, campaigns}   what the live campaigns spend of the daily budget they are set to

Thresholds `k` (every one a registry row of the pack): `audit_waste_share`, `audit_old_share`, `audit_old_days`, `concentration_alert_share`,
`audit_budget_use_low`, `audit_budget_use_high`. A share is compared with `>=`, the low budget use with `<`, the high one with `>`.

From the video-ads skill pack (`scripts/_lib/audit.py`; its cases are this module's test; its `unlabelled` finding and every sentence stay there).

Test: kit/tests/test_audit.py.
"""

from __future__ import annotations

SEVERITY = ("high", "medium", "info")


def _finding(code: str, severity: str, **params) -> dict:
    return {"finding": code, "severity": severity, "params": params}


def order(found: list[dict]) -> list[dict]:
    """`found` most severe first; the order inside a severity is kept, a severity this module does not know goes last."""
    return sorted(found, key=lambda x: SEVERITY.index(x["severity"]) if x["severity"] in SEVERITY else len(SEVERITY))


def findings(f: dict, k: dict) -> list[dict]:
    """The findings of the facts `f`, most severe first; only what crosses its threshold."""
    out = []
    i = f.get("issues")
    if i and i["ads"]:
        out.append(_finding("audit_issues", "high", ads=i["ads"], spend=round(i["spend"], 2), days=i["days"], examples=i["examples"]))
    w = f.get("waste")
    if w and w["share"] is not None and w["share"] >= k["audit_waste_share"]:
        out.append(_finding("audit_no_result", "medium", share=round(w["share"], 4), spend=round(w["spend"], 2), ads=w["ads"], examples=w["examples"]))
    o = f.get("old")
    if o and o["share"] is not None and o["share"] >= k["audit_old_share"]:
        out.append(_finding("audit_old_ads", "medium", share=round(o["share"], 4), ads=o["ads"], days=int(k["audit_old_days"]), examples=o["examples"]))
    c = f.get("concentration")
    if c and c["share"] is not None and c["share"] >= k["concentration_alert_share"]:
        out.append(_finding("audit_concentration", "medium", share=round(c["share"], 4), n=c["n"], examples=c["examples"]))
    b = f.get("budget")
    if b and b["use"] is not None:
        shown = {"use": round(b["use"], 4), "spend_per_day": round(b["spend_per_day"], 2), "daily": round(b["daily"], 2), "campaigns": b["campaigns"]}
        if b["use"] < k["audit_budget_use_low"]:
            out.append(_finding("audit_budget_unused", "medium", **shown))
        elif b["use"] > k["audit_budget_use_high"]:
            out.append(_finding("audit_budget_over", "medium", **shown))
    return order(out)
