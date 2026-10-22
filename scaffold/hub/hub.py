#!/usr/bin/env python3
"""The client hub's own facts program: `bin/hub hub <verb…>`.

A client hub (scaffold/new_hub.py) keeps the facts every pack of the client
shares (the markets, the currency, break-even ROAS, …) in its own store,
`<hub>/hub/hub.db`, with the kit's client_facts tables, gate and history
unchanged: this program is the kit's own `facts` and `pending` verbs over
that store, run from the playbook like the hub's console. Nothing here is
vendored; nothing here is new logic.

How it is bound (the hub's `hub/bin/hub` wrapper, written by new_hub.py):

  * KIT_SKILL_PACK_ROOT = <hub>/hub/defs: its skill-pack.toml (cli `hub`,
    env prefix `HUB`, the hub's markets) and fact_keys.tsv (the shared
    keys; the markets enter through the kit's market door, `facts init`);
  * HUB_DATA_DIR = <hub>/hub, so the store is <hub>/hub/hub.db; outside the
    definitions folder, as the kit wants a data dir outside the checkout;
  * the hub console relays `hub facts confirm` (HUB_CONFIRM_CODE_SECRET is
    made by bin/console like every pack's).

Each pack copies these facts with its own `<cli> facts sync-hub` (kit.facts).

Test: scaffold/tests/test_hub_program.py.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))      # the playbook: its kit/

from kit.cli import Dispatcher  # noqa: E402

from schema import SPEC  # noqa: E402
from verbs import VERBS  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(Dispatcher(VERBS, scripts_dir=HERE, spec=SPEC,
                                description="The client hub's own facts: "
                                            "confirmed once here, copied by "
                                            "each pack.").main(sys.argv[1:]))
