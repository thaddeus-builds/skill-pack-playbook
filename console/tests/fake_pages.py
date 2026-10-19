#!/usr/bin/env python3
"""A stand-in for a skill pack that draws pages, for the tests of the page registry (serve.py, relay.fetch).

    fake_pages.py console <name> [--lang=L] --json    prints $FAKE_PAGES_DIR/<name>.json
    fake_pages.py <anything else>                     is tests/fake_skill_pack.py (the gate), unchanged

A page file is the document the console draws. If it holds `"__exit": N` the call ends with exit N (its `error`
printed as the document), and `"__sleep": S` waits S seconds first; a missing file is exit 2 with no output.
Every call is appended to $FAKE_PAGES_LOG (one JSON line: argv), so a test can count how often a verb ran.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    log = os.environ.get("FAKE_PAGES_LOG")
    if log:
        with open(log, "a") as f:
            f.write(json.dumps(argv) + "\n")
    if not argv or argv[0] != "console":
        os.execv(sys.executable, [sys.executable, os.path.join(HERE, "fake_skill_pack.py"), *argv])
    name = argv[1]
    try:
        with open(os.path.join(os.environ["FAKE_PAGES_DIR"], name + ".json"), encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        return 2
    time.sleep(doc.pop("__sleep", 0))
    code = doc.pop("__exit", 0)
    print(json.dumps(doc, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
