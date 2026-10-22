#!/usr/bin/env python3
"""docs/ROADMAP.md keeps the one roadmap format: Now, Waiting on owner, Next, Done,
Parked, Decisions, Links, one dated row per item with an id, so a session on any
machine starts from it.

A thin call into the vendored kit (kit.testing.suites.roadmap); the rules live
there, so every skill pack holds the same ones. Another home for the file goes in
skill-pack.toml, [guards.roadmap] file.
"""

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
os.environ["KIT_SKILL_PACK_ROOT"] = str(ROOT)

from kit.testing import suites  # noqa: E402
from kit.testing.check import finish  # noqa: E402

suites.run(suites.roadmap(ROOT))
raise SystemExit(finish())
