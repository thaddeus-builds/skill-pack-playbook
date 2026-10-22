#!/usr/bin/env python3
"""SKILL.md's first section is `## Never`, and its table names exactly the
verbs only a person runs: every gated verb of scripts/verbs.py, and each verb
skill-pack.toml names in [guards.evals].extra.

A thin call into the vendored kit (kit.testing.suites.never_table); the rules
live there, so every skill pack holds the same ones.
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

suites.run(suites.never_table(ROOT))
raise SystemExit(finish())
