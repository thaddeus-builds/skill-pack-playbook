"""The hub's store: the kit's human tables and nothing else."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the playbook

from kit import db  # noqa: E402

SPEC = db.with_human({}, version=1)
