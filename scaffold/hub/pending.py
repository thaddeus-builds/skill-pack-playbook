"""What waits on a person at the hub, as console asks (`--hub` for the
hub's one console: ids and verbs start with `hub`)."""

import sys

from schema import SPEC  # first: it puts the playbook's kit on the path

from kit import pending  # noqa: E402
from kit.registry import FactKeys  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(pending.main(sys.argv[1:], spec=SPEC, keys=FactKeys(),
                                  registry=None))
