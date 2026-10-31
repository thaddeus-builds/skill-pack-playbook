#!/usr/bin/env python3
"""Which repositories are skill packs: the GitHub topics against tools/adoption.tsv.

    python3 tools/roster.py [--owner NAME] [--json] [--from-json FILE]

A repository carries the topic `skill-pack` (a library, `skill-pack-library`) on GitHub.
The table lists the same packs by hand. This reads the owner's repositories with `gh repo
list` and says where the two differ, one line each:

  new        has the topic, is not in the table: add its row
  untagged   is in the table, is on GitHub, has no topic: add the topic
  gitlab     is in the table and not on GitHub: not moved yet (listed, not a fault)

Exit 1 when there is a `new` or an `untagged` line; `gitlab` alone is exit 0. The table is
the ledger, the topic is the roster: this never writes either. `--from-json FILE` reads the
output of `gh repo list OWNER --limit 200 --json name,repositoryTopics,isArchived` instead
of calling `gh`, for a run with no network.

Read-only. Stdlib only. Test: tests/test_roster.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

TABLE = Path(__file__).resolve().parent / "adoption.tsv"
OWNER = "thaddeus-builds"
TOPICS = ("skill-pack", "skill-pack-library")


def table_names(text: str) -> list[str]:
    """The `pack` column of adoption.tsv."""
    return [r["pack"] for r in csv.DictReader(text.splitlines(), delimiter="\t") if r.get("pack")]


def topics_of(repo: dict) -> set[str]:
    """A repository's topics from `gh repo list --json repositoryTopics` (null when it has none)."""
    return {t.get("name", "") for t in (repo.get("repositoryTopics") or []) if isinstance(t, dict)}


def compare(repos: list[dict], names: list[str]) -> dict[str, list[str]]:
    """new / untagged / gitlab, each sorted. An archived repository is not a candidate for `new`."""
    on_github = {r["name"]: r for r in repos}
    tagged = {n for n, r in on_github.items() if topics_of(r) & set(TOPICS) and not r.get("isArchived")}
    listed = set(names)
    return {
        "new": sorted(tagged - listed),
        "untagged": sorted(n for n in listed if n in on_github and n not in tagged),
        "gitlab": sorted(n for n in listed if n not in on_github),
    }


def read_repos(owner: str, retries: int = 3) -> list[dict]:
    """The owner's repositories from `gh`; its GraphQL calls time out now and then, so it tries again."""
    last = ""
    for i in range(retries):
        r = subprocess.run(["gh", "repo", "list", owner, "--limit", "200", "--json",
                            "name,repositoryTopics,isArchived"], capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout)
        last = r.stderr.strip()
        time.sleep(2 * (i + 1))
    raise SystemExit(f"gh repo list {owner} failed: {last}")


def render(result: dict[str, list[str]]) -> str:
    words = {"new": "has the topic, no row in tools/adoption.tsv",
             "untagged": "is in the table, lacks the GitHub topic `skill-pack`",
             "gitlab": "is in the table, not on GitHub yet"}
    lines = [f"{kind:9}{name}  ({words[kind]})" for kind in ("new", "untagged", "gitlab") for name in result[kind]]
    return "\n".join(lines) if lines else "the roster and the table agree"


def failed(result: dict[str, list[str]]) -> bool:
    return bool(result["new"] or result["untagged"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--owner", default=OWNER)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--from-json", metavar="FILE")
    a = ap.parse_args(argv)
    repos = json.loads(Path(a.from_json).read_text("utf-8")) if a.from_json else read_repos(a.owner)
    result = compare(repos, table_names(TABLE.read_text("utf-8")))
    print(json.dumps(result, indent=2) if a.json else render(result))
    return 1 if failed(result) else 0


if __name__ == "__main__":
    sys.exit(main())
