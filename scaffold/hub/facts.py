"""The hub's facts: the kit's facts verb over <hub>/hub/hub.db."""

import sys

from schema import SPEC  # first: it puts the playbook's kit on the path

from kit import facts  # noqa: E402
from kit.registry import FactKeys  # noqa: E402

if __name__ == "__main__":
    keys = FactKeys()
    raise SystemExit(facts.main(sys.argv[1:], spec=SPEC, keys=keys,
                                thresholds=None,
                                init_questions=[{"key": k}
                                                for k in keys.keys()]))
