#!/usr/bin/env python3
"""kit.paths: the data dir is required and never the cwd.

  * unset / blank <P>_DATA_DIR -> data_dir_unset, next naming the var;
  * a relative value -> data_dir_not_absolute (it would be cwd-relative);
  * `~` expands; <P>_DB overrides the DB (relative = under the data dir);
  * raw_dir(): <P>_RAW overrides, relative = under the data dir, default
    <DATA_DIR>/raw; resolve() does not list it (its default output is fixed);
  * resolve() never raises; inside_repo() is the checkout and below only.
"""

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import paths  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.testing.check import check, finish, raises, tmp_dir  # noqa: E402


def main() -> int:
    cfg = _shop.use()
    data = _shop.data_dir()

    print("[1] the data dir")
    check("SHOP_DATA_DIR is the data dir", paths.data_dir() == data)
    for val in (None, "", "   "):
        if val is None:
            os.environ.pop("SHOP_DATA_DIR", None)
        else:
            os.environ["SHOP_DATA_DIR"] = val
        e = raises(paths.data_dir, SkillPackError)
        check(f"SHOP_DATA_DIR={val!r}: data_dir_unset naming the var",
              e is not None and e.message.code == "data_dir_unset"
              and e.message.params == {"var": "SHOP_DATA_DIR"}
              and e.next[0].startswith("export SHOP_DATA_DIR=")
              and "shop doctor" in e.next, e)
    here = os.getcwd()
    os.chdir(tmp_dir("cwd-"))
    try:
        os.environ["SHOP_DATA_DIR"] = "client-data"
        e = raises(paths.data_dir, SkillPackError)
        check("a relative data dir is refused, not resolved against the cwd",
              e is not None and e.message.code == "data_dir_not_absolute"
              and e.message.params == {"var": "SHOP_DATA_DIR",
                                       "value": "client-data"}, e)
    finally:
        os.chdir(here)
    home = Path(tmp_dir("home-"))
    saved_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    os.environ["SHOP_DATA_DIR"] = "~/clients/a"
    check("~ expands", paths.data_dir() == home / "clients" / "a")
    if saved_home is None:
        del os.environ["HOME"]
    else:
        os.environ["HOME"] = saved_home
    os.environ["SHOP_DATA_DIR"] = str(data)

    print("\n[2] the DB path")
    check("default: <DATA_DIR>/<db_file>",
          paths.db_path() == data / cfg.db_file == data / "shop.db")
    os.environ["SHOP_DB"] = str(data / "elsewhere.db")
    check("SHOP_DB absolute: used as is",
          paths.db_path() == data / "elsewhere.db")
    os.environ["SHOP_DB"] = "sub/x.db"
    check("SHOP_DB relative: under the data dir",
          paths.db_path() == data / "sub" / "x.db")
    del os.environ["SHOP_DB"]
    check("resolve(): both vars", paths.resolve() == {
        "SHOP_DATA_DIR": str(data), "SHOP_DB": str(data / "shop.db")})
    del os.environ["SHOP_DATA_DIR"]
    check("resolve() with nothing set: None, no exception",
          paths.resolve() == {"SHOP_DATA_DIR": None, "SHOP_DB": None})
    os.environ["SHOP_DATA_DIR"] = str(data)

    print("\n[3] the raw root")
    os.environ.pop("SHOP_RAW", None)
    check("default: <DATA_DIR>/raw", paths.raw_dir() == data / "raw")
    os.environ["SHOP_RAW"] = str(data / "elsewhere")
    check("SHOP_RAW absolute: used as is", paths.raw_dir() == data / "elsewhere")
    os.environ["SHOP_RAW"] = "sub/raw"
    check("SHOP_RAW relative: under the data dir",
          paths.raw_dir() == data / "sub" / "raw")
    os.environ["SHOP_RAW"] = "  "
    check("SHOP_RAW blank: the default", paths.raw_dir() == data / "raw")
    os.environ["SHOP_RAW"] = "~/raw-x"
    check("SHOP_RAW ~ expands", paths.raw_dir() == Path("~/raw-x").expanduser())
    os.environ["SHOP_RAW"] = "sub/raw"
    check("resolve() does not list SHOP_RAW, set or not",
          paths.resolve() == {"SHOP_DATA_DIR": str(data),
                              "SHOP_DB": str(data / "shop.db")})
    del os.environ["SHOP_RAW"]
    del os.environ["SHOP_DATA_DIR"]
    e = raises(paths.raw_dir, SkillPackError)
    check("raw_dir() with no data dir: data_dir_unset",
          e is not None and e.message.code == "data_dir_unset", e)
    os.environ["SHOP_DATA_DIR"] = str(data)

    print("\n[4] inside_repo")
    root = cfg.root
    check("the checkout itself and anything below it",
          paths.inside_repo(root) and paths.inside_repo(root / "data" / "x"))
    check("a dir outside it", not paths.inside_repo(data))
    check("a sibling sharing the name prefix is outside",
          not paths.inside_repo(Path(str(root) + "-data")))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
