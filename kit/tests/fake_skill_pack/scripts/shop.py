"""The shop skill pack CLI: `shop <verb> [args…]` (kit.cli.Dispatcher over
scripts/verbs.py). The kit is not vendored in this test fixture: run it
with the playbook root on PYTHONPATH and KIT_SKILL_PACK_ROOT set to this
skill pack (kit/tests/test_cli.py does)."""

import sys
from pathlib import Path

from kit.cli import Dispatcher

from _lib.schema import SPEC
from verbs import VERBS

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    raise SystemExit(Dispatcher(VERBS, scripts_dir=HERE, spec=SPEC,
                                description="The shop skill pack: a tiny "
                                            "skill pack the kit's tests run.")
                     .main(sys.argv[1:]))
