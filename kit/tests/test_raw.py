#!/usr/bin/env python3
"""kit.raw: raw only grows.

  * write-once: a new name is written; the same name with identical bytes
    is a no-op (same inode, same mtime); with different bytes it is
    refused (raw_would_overwrite) and the file is untouched, also when a
    concurrent writer claims the name between the check and the write;
  * import_file() twice = one raw file under <stem>.<sha256[:12]><suffix>;
  * save_json is canonical: equal objects = equal bytes;
  * names are plain components; temp files never show and never linger;
  * a client hub's exchange folder: exchange_write puts a document at
    <hub>/exchange/<contract>/<producer>/<date>.json once and refuses a
    taken name (identical bytes too, and a lost race); a bad contract,
    producer or day, a hub without exchange/ and a non-bytes body are
    refused with nothing written; exchange_list gives a contract's
    documents by producer then date and skips what is not one;
    exchange_scan also names every path out of place.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
import datetime  # noqa: E402
from kit import raw  # noqa: E402
from kit.contract import SkillPackError  # noqa: E402
from kit.testing.check import check, finish, raises, tmp_dir  # noqa: E402


def refusal(fn) -> str | None:
    e = raises(fn, SkillPackError)
    return getattr(e.message, "code", None) if e else None


def main() -> int:
    _shop.use()
    data = _shop.data_dir()

    print("[1] write-once")
    p = raw.save("orders", "2026-09-01.json", b'{"n":1}')
    check("saved under <DATA_DIR>/raw/<source>/<name>",
          p == data / "raw" / "orders" / "2026-09-01.json"
          and p.read_bytes() == b'{"n":1}')
    st = p.stat()
    again = raw.save("orders", "2026-09-01.json", b'{"n":1}')
    st2 = again.stat()
    check("identical re-save: a no-op (same path, inode, mtime)",
          again == p and (st.st_ino, st.st_mtime_ns) == (st2.st_ino,
                                                         st2.st_mtime_ns))
    e = raises(lambda: raw.save("orders", "2026-09-01.json", b'{"n":2}'),
               SkillPackError)
    check("different bytes, same name: raw_would_overwrite",
          e is not None and e.message.code == "raw_would_overwrite"
          and e.message.params == {"source": "orders",
                                   "name": "2026-09-01.json"}, e)
    check("… and the file on disk is untouched", p.read_bytes() == b'{"n":1}')

    real_link = raw.os.link

    def racing_link(src, dst):
        Path(dst).write_bytes(b"the other writer won")
        return real_link(src, dst)
    raw.os.link = racing_link
    try:
        code = refusal(lambda: raw.save("orders", "race.json", b"mine"))
    finally:
        raw.os.link = real_link
    check("a writer that claims the name first wins; the second is refused",
          code == "raw_would_overwrite"
          and (data / "raw/orders/race.json").read_bytes()
          == b"the other writer won", code)
    raw.os.link = racing_link
    try:
        same = raw.save("orders", "race2.json", b"the other writer won")
    finally:
        raw.os.link = real_link
    check("… unless it wrote the very same bytes (then a no-op)",
          same.read_bytes() == b"the other writer won")
    check("no temp file lingers after any of that",
          sorted(x.name for x in (data / "raw" / "orders").iterdir())
          == ["2026-09-01.json", "race.json", "race2.json"],
          sorted(os.listdir(data / "raw" / "orders")))

    print("\n[2] import_file(): same file twice = one raw file")
    src = Path(tmp_dir("export-")) / "Orders Export.csv"
    src.write_bytes(b"sku,units\nA,2\n")
    a = raw.import_file("orders_csv", src)
    b = raw.import_file("orders_csv", src)
    digest = hashlib.sha256(b"sku,units\nA,2\n").hexdigest()[:12]
    check("named <stem>.<sha256[:12]><suffix>",
          a.name == f"Orders Export.{digest}.csv", a.name)
    check("importing it twice leaves one raw file",
          a == b and raw.listing("orders_csv") == [a])
    src.write_bytes(b"sku,units\nA,3\n")
    c = raw.import_file("orders_csv", src)
    check("a changed export is a second file; the first stays",
          c != a and len(raw.listing("orders_csv")) == 2
          and a.read_bytes() == b"sku,units\nA,2\n")
    check("a missing export: raw_import_missing",
          refusal(lambda: raw.import_file("orders_csv", src.parent / "nope"))
          == "raw_import_missing")
    dot = src.parent / ".hidden.csv"
    dot.write_bytes(b"x")
    check("a dot-file export gets a plain name",
          not raw.import_file("orders_csv", dot).name.startswith("."))

    print("\n[3] save_json() is canonical")
    j1 = raw.save_json("api", "page1.json", {"b": [1, 2], "a": "价格"})
    j2 = raw.save_json("api", "page1.json", {"a": "价格", "b": [1, 2]})
    check("equal objects, any key order: one file, a no-op re-save",
          j1 == j2 and json.loads(j1.read_bytes()) == {"a": "价格", "b": [1, 2]}
          and j1.read_bytes() == '{"a":"价格","b":[1,2]}'.encode())
    check("a different object under that name is refused",
          refusal(lambda: raw.save_json("api", "page1.json", {"a": 1}))
          == "raw_would_overwrite")

    print("\n[4] names and listing")
    for label, fn in (
            ("a parent path", lambda: raw.save("orders", "../x", b"")),
            ("a separator", lambda: raw.save("orders", "a/b", b"")),
            ("a leading dot", lambda: raw.save("orders", ".x", b"")),
            ("an empty name", lambda: raw.save("orders", "", b"")),
            ("'..'", lambda: raw.save("orders", "..", b"")),
            ("a source with a separator", lambda: raw.save("a/b", "x", b""))):
        check(f"refused: {label} (raw_bad_name)", refusal(fn) == "raw_bad_name")
    (data / "raw" / "orders" / ".leftover.tmp").write_bytes(b"x")
    check("listing: sorted, temp/hidden files never shown",
          [x.name for x in raw.listing("orders")]
          == ["2026-09-01.json", "race.json", "race2.json"])
    check("save() takes bytes only",
          raises(lambda: raw.save("orders", "s.txt", "text"), TypeError)
          is not None)

    print("\n[5] no data dir, no raw")
    del os.environ["SHOP_DATA_DIR"]
    check("unset data dir: data_dir_unset, nothing written in the cwd",
          refusal(lambda: raw.save("orders", "x", b"")) == "data_dir_unset"
          and not Path("raw").exists())

    exchange()
    return finish()


def exchange() -> None:
    print("\n[6] the hub's exchange folder: one document, once")
    hub = Path(tmp_dir("hub-"))
    check("a hub without exchange/: exchange_no_folder, nothing made",
          refusal(lambda: raw.exchange_write(hub, "ads.results/1", "vads",
                                             "2026-10-23", b"x"))
          == "exchange_no_folder"
          and refusal(lambda: raw.exchange_list(hub, "ads.results/1"))
          == "exchange_no_folder" and not (hub / "exchange").exists())
    (hub / "exchange").mkdir()
    p = raw.exchange_write(hub, "ads.results/1", "vads", "2026-10-23",
                           b"# ads.results/1\n{}")
    check("written at <hub>/exchange/<contract>/<producer>/<date>.json",
          p == (hub / "exchange" / "ads.results" / "1" / "vads"
                / "2026-10-23.json").resolve()
          and p.read_bytes() == b"# ads.results/1\n{}")
    st = p.stat()
    e = raises(lambda: raw.exchange_write(hub, "ads.results/1", "vads",
                                          "2026-10-23", b"# ads.results/1\n{}"),
               SkillPackError)
    check("the same name with the SAME bytes is refused too (exchange_exists)",
          e is not None and e.message.code == "exchange_exists"
          and e.message.params["contract"] == "ads.results/1"
          and e.message.params["producer"] == "vads"
          and e.message.params["date"] == "2026-10-23", e)
    check("… different bytes likewise; the file is untouched",
          refusal(lambda: raw.exchange_write(hub, "ads.results/1", "vads",
                                             datetime.date(2026, 10, 23), b"other"))
          == "exchange_exists" and p.read_bytes() == b"# ads.results/1\n{}"
          and (st.st_ino, st.st_mtime_ns) == (p.stat().st_ino, p.stat().st_mtime_ns))

    real_link = raw.os.link

    def racing_link(src, dst):
        Path(dst).write_bytes(b"the other writer won")
        return real_link(src, dst)
    raw.os.link = racing_link
    try:
        code = refusal(lambda: raw.exchange_write(
            hub, "ads.results/1", "vads", "2026-10-24", b"mine"))
    finally:
        raw.os.link = real_link
    check("two writers racing for a name: the first stays, the second is refused",
          code == "exchange_exists" and (p.parent / "2026-10-24.json").read_bytes()
          == b"the other writer won", code)
    check("no temp file lingers",
          sorted(x.name for x in p.parent.iterdir())
          == ["2026-10-23.json", "2026-10-24.json"], sorted(os.listdir(p.parent)))

    before = sorted(str(x) for x in (hub / "exchange").rglob("*"))
    for label, args in (
            ("a contract with no version", ("ads.results", "vads", "2026-10-23")),
            ("a contract with a path in it", ("../x/1", "vads", "2026-10-23")),
            ("a contract version 0", ("ads.results/0", "vads", "2026-10-23")),
            ("a producer with a separator", ("ads.results/1", "a/b", "2026-10-23")),
            ("a producer in capitals", ("ads.results/1", "VADS", "2026-10-23")),
            ("a day not in YYYY-MM-DD", ("ads.results/1", "vads", "20261023")),
            ("a day that is not real", ("ads.results/1", "vads", "2026-02-30")),
            ("a date with a time", ("ads.results/1", "vads", "2026-10-23T09:00")),
            ("a path as the day", ("ads.results/1", "vads", "../2026-10-23"))):
        check(f"refused: {label} (exchange_bad_name)",
              refusal(lambda: raw.exchange_write(hub, *args, b"x"))
              == "exchange_bad_name")
    check("… and nothing was made by any of them",
          sorted(str(x) for x in (hub / "exchange").rglob("*")) == before)
    check("a body that is not bytes is a TypeError",
          raises(lambda: raw.exchange_write(hub, "ads.results/1", "vads",
                                            "2026-10-25", "text"), TypeError)
          is not None)

    print("\n[7] listing a contract: by producer, then date")
    for c, prod, day in (("ads.results/1", "ppc", "2026-10-22"),
                         ("ads.results/1", "gads", "2026-10-24"),
                         ("ads.results/1", "gads", "2026-10-21"),
                         ("ads.results/2", "vads", "2026-10-23"),
                         ("catalog/1", "feed", "2026-10-23")):
        raw.exchange_write(hub, c, prod, day, b"{}")
    got = [(d.producer, d.date) for d in raw.exchange_list(hub, "ads.results/1")]
    check("sorted by producer, then date, oldest first; other contracts and "
          "versions are not mixed in",
          got == [("gads", "2026-10-21"), ("gads", "2026-10-24"),
                  ("ppc", "2026-10-22"), ("vads", "2026-10-23"),
                  ("vads", "2026-10-24")], got)
    d0 = raw.exchange_list(hub, "ads.results/1")[0]
    check("a document names its contract, producer, day and path",
          d0.contract == "ads.results/1" and d0.path.read_bytes() == b"{}"
          and d0.path.name == "2026-10-21.json")
    check("a contract nobody wrote: an empty list, and nothing is made",
          raw.exchange_list(hub, "leads/1") == []
          and not (hub / "exchange" / "leads").exists())
    check("a bad contract name is refused (exchange_bad_name)",
          refusal(lambda: raw.exchange_list(hub, "ads.results"))
          == "exchange_bad_name")
    (p.parent / ".2026-10-25.json.123.tmp").write_bytes(b"in flight")
    (p.parent / "notes.txt").write_bytes(b"x")
    (p.parent / "2026-10-26.json.bak").write_bytes(b"x")
    (p.parent / "2026-1-2.json").write_bytes(b"x")
    check("a write in flight and files that are not a dated .json are not listed",
          [d.date for d in raw.exchange_list(hub, "ads.results/1")
           if d.producer == "vads"] == ["2026-10-23", "2026-10-24"])

    print("\n[8] exchange_scan names what is out of place")
    docs, strays = raw.exchange_scan(hub)
    check("every document of every contract, sorted",
          [(d.contract, d.producer, d.date) for d in docs]
          == [("ads.results/1", "gads", "2026-10-21"),
              ("ads.results/1", "gads", "2026-10-24"),
              ("ads.results/1", "ppc", "2026-10-22"),
              ("ads.results/1", "vads", "2026-10-23"),
              ("ads.results/1", "vads", "2026-10-24"),
              ("ads.results/2", "vads", "2026-10-23"),
              ("catalog/1", "feed", "2026-10-23")],
          [(d.contract, d.producer, d.date) for d in docs])
    check("the stray files of that folder are named, relative to exchange/",
          strays == ["ads.results/1/vads/2026-1-2.json",
                     "ads.results/1/vads/2026-10-26.json.bak",
                     "ads.results/1/vads/notes.txt"], strays)
    ex = hub / "exchange"
    (ex / "README.md").write_text("what this folder is")
    (ex / ".gitkeep").write_text("")
    (ex / "loose.json").write_text("{}")
    (ex / "catalog" / "one").mkdir()
    (ex / "catalog" / "1" / "Feed2").mkdir()
    (ex / "catalog" / "1" / "stray.json").write_text("{}")
    strays = raw.exchange_scan(hub)[1]
    check("a file in exchange/, a version that is not one, a producer folder "
          "not named for a cli and a file beside the producers are strays; "
          "README.md and dotfiles are not",
          "loose.json" in strays and "catalog/one" in strays
          and "catalog/1/Feed2" in strays and "catalog/1/stray.json" in strays
          and "README.md" not in strays and ".gitkeep" not in strays, strays)
    empty = Path(tmp_dir("hub2-"))
    (empty / "exchange").mkdir()
    check("an empty exchange/ has nothing and no strays",
          raw.exchange_scan(empty) == ([], []))


if __name__ == "__main__":
    raise SystemExit(main())
