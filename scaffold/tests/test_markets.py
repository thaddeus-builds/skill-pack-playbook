#!/usr/bin/env python3
"""scaffold/markets.py: a market is an ISO 3166-1 alpha-2 code.

  1. The table: 249 ISO codes plus XK (Kosovo), each once, two capitals, a name; the codes a client is likely to have are in it.
  2. check(): a listed code passes; `UK` is refused with `GB`; a lower-case code with the capital form; a made-up code, a word, a code
     listed twice are refused, each named.
  3. The doors: `new_hub.py new` and `new_skill_pack.py` refuse `UK` and write nothing.
"""

import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PLAYBOOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLAYBOOK))
sys.path.insert(0, str(PLAYBOOK / "scaffold"))

import markets  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402


def refused(fn) -> str | None:
    try:
        fn()
    except ValueError as e:
        return str(e)
    return None


def main() -> int:
    print("[1] the table")
    t = markets.table()
    check("249 ISO codes and XK, each two capitals", len(t) == 250 and all(re.fullmatch(r"[A-Z]{2}", c) for c in t) and "XK" in t, len(t))
    check("the markets a client is likely to have",
          all(c in t for c in ("HK", "TW", "GB", "US", "CN", "JP", "SG", "ME", "MD", "XK", "DE", "FR", "AE", "AU")))
    check("Hong Kong, Taiwan and Macao are listed as themselves", (t["HK"], t["TW"], t["MO"]) == ("Hong Kong", "Taiwan", "Macao"))
    check("UK is not an ISO code", "UK" not in t)

    print("[2] check()")
    check("listed codes pass", markets.check(["HK", "TW", "GB", "XK"]) == ["HK", "TW", "GB", "XK"] and markets.check([]) == [])
    e = refused(lambda: markets.check(["UK"]))
    check("UK: write GB", e is not None and "'GB'" in e and "United Kingdom" in e, e)
    e = refused(lambda: markets.check(["hk"]))
    check("lower case: the capital form", e is not None and "'HK'" in e, e)
    check("a made-up code and a word are refused",
          all(refused(lambda c=c: markets.check([c])) for c in ("ZZ", "DA", "Hong Kong", "H K", "")))
    e = refused(lambda: markets.check(["HK", "HK"]))
    check("a code twice", e is not None and "HK" in e and "twice" in e, e)

    print("[3] the doors")
    root = Path(tmp_dir("markets-"))
    r = subprocess.run([sys.executable, str(PLAYBOOK / "scaffold" / "new_hub.py"), "new", "--hub", str(root / "h"), "--title", "Tea", "--markets", "HK,UK"],
                       capture_output=True, text=True)
    check("new_hub.py new refuses UK, naming GB, and writes nothing", r.returncode == 2 and "GB" in r.stderr and not (root / "h").exists(), r.stderr[-300:])
    r = subprocess.run([sys.executable, str(PLAYBOOK / "scaffold" / "new_skill_pack.py"), "--name", "acme-skill-pack", "--cli", "acme", "--prefix", "ACME", "--dir", str(root / "p"), "--markets", "HK,UK"],
                       capture_output=True, text=True)
    check("new_skill_pack.py refuses UK, naming GB, and writes nothing", r.returncode != 0 and "GB" in (r.stderr + r.stdout) and not (root / "p").exists(),
          (r.stderr + r.stdout)[-300:])
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
