"""A client hub's facts mean the same in every skill pack that copies them.

`facts sync-hub` copies a hub fact into a skill pack only when the skill
pack's own fact_keys.tsv defines the key as the hub's does
(kit.registry.definition_diffs: type with its options, unit, min, max and
the labels both files carry); a key defined otherwise is skipped. This
guard makes the same comparison a test failure, so a skill pack learns of
the difference when its definitions change, not when a copy is skipped:

    from kit.guards import hub_keys
    problems = hub_keys.check(os.environ.get("GADS_HUB_DIR"))  # [] = agree

  * `check(hub, root=None)`: one problem per key both files define with a
    different definition, naming what differs; the hub's file missing or
    unreadable is a problem too. `hub` None or "" checks nothing ([]): a
    skill pack's suite runs without a hub as well.

Test: kit/tests/test_hub_facts.py.
"""

from __future__ import annotations

from pathlib import Path

from kit import facts, registry
from kit.contract import SkillPackError
from kit.guards import skill_pack


def check(hub: Path | str | None, root: Path | str | None = None
          ) -> list[str]:
    """Every shared key the skill pack (at `root`, else the bound one)
    defines otherwise than the hub at `hub`."""
    if hub is None or not str(hub).strip():
        return []
    cfg = skill_pack(root)
    mine = cfg.ssot_path("fact_keys")
    if mine is None:
        return ["skill-pack.toml declares no [ssot].fact_keys"]
    try:
        theirs = facts.hub_keys_path(Path(hub))
        diffs = registry.definition_diffs(mine, theirs)
    except SkillPackError as e:
        return [str(e)]
    return [f"{key}: {'; '.join(d)} ({mine.name} here, {theirs} at the hub)"
            for key, d in sorted(diffs.items())]
