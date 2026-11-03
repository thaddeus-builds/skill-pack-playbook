"""hosts/zylos/fleet.tsv: one row per skill pack on a Zylos host, its linked command, console port and public path.

Two packs on one host must not share any of the three (on 2026-11-03 the seo and amazon-ppc consoles both defaulted to
8766). Every command is `openmax-<cli>` (the owner's decision R19). A new port stays out of the range a client hub's
console takes (8770 to 8799, scaffold/new_hub.py); the rows already on hosts keep theirs and say so. scaffold/add_zylos.py
takes a pack's default port from here. Each check is tried on a planted break first.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _t import main  # noqa: E402

TABLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fleet.tsv")
COLUMNS = ["pack", "cli", "bin", "port", "base_path", "note"]
HUB_RANGE = range(8770, 8800)


def problems(text: str) -> list[str]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or lines[0].split("\t") != COLUMNS:
        return [f"header must be {COLUMNS}"]
    out, seen = [], {k: {} for k in ("pack", "bin", "port", "base_path")}
    for n, line in enumerate(lines[1:], 2):
        cells = line.split("\t")
        if len(cells) != len(COLUMNS):
            out.append(f"line {n}: {len(cells)} cells, not {len(COLUMNS)}")
            continue
        r = dict(zip(COLUMNS, cells))
        if r["bin"] != f"openmax-{r['cli']}":
            out.append(f"{r['pack']}: bin {r['bin']} is not openmax-{r['cli']} (R19)")
        if not r["port"].isdigit() or not 1024 <= int(r["port"]) <= 65535:
            out.append(f"{r['pack']}: port {r['port']!r} is not 1024 to 65535")
        elif int(r["port"]) in HUB_RANGE and "port kept" not in r["note"]:
            out.append(f"{r['pack']}: port {r['port']} is in a hub console's range 8770 to 8799 (a pack already on hosts says 'port kept')")
        if not r["base_path"].startswith("/") or r["base_path"].endswith("/"):
            out.append(f"{r['pack']}: base_path {r['base_path']!r} is not /name")
        for k in seen:
            if r[k] in seen[k]:
                out.append(f"{r['pack']}: {k} {r[k]} is also {seen[k][r[k]]}'s")
            seen[k][r[k]] = r["pack"]
    return out


def test_the_table_is_sound():
    with open(TABLE, encoding="utf-8") as f:
        found = problems(f.read())
    assert found == [], found


def test_each_break_is_seen():
    with open(TABLE, encoding="utf-8") as f:
        good = f.read()
    rows = good.splitlines()
    first = rows[1].split("\t")
    for want, text in {
        "is also": good + "\t".join(["x-skill-pack", "x", "openmax-x", first[3], "/x", ""]) + "\n",
        "not openmax-": good.replace("\topenmax-seo\t", "\tcoco-seo\t", 1),
        "hub console's range": good + "x-skill-pack\tx\topenmax-x\t8779\t/x\t\n",
        "not /name": good + "x-skill-pack\tx\topenmax-x\t8899\tx\t\n",
        "header": good.replace("base_path", "path", 1),
    }.items():
        assert any(want in p for p in problems(text)), (want, problems(text))


def test_add_zylos_takes_the_port_from_here():
    sys.path.insert(0, os.path.join(os.path.dirname(TABLE), "..", "..", "scaffold"))
    import add_zylos  # noqa: E402
    assert add_zylos.default_port("meta-ads-skill-pack") == 8801 and add_zylos.default_port("seo-skill-pack") == 8766
    assert 8800 <= add_zylos.default_port("not-in-the-table-skill-pack") < 9800, "a pack with no row: the hash, as before"


if __name__ == "__main__":
    raise SystemExit(main(globals()))
