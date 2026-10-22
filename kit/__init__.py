"""The skill pack kit: the generic half of an agent skill pack (stdlib only,
Python >= 3.11). A skill pack binds it once with `skill-pack.toml` (kit.config).

Importing `kit` loads nothing but the version, so a puller can import
`kit.dates` or `kit.atomic` without a skill pack config, a DB or a registry.
Test: kit/tests/test_config.py (the version matches kit/VERSION).
"""

from __future__ import annotations

from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent
__version__ = (KIT_DIR / "VERSION").read_text(encoding="utf-8").strip()
