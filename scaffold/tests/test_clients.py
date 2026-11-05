#!/usr/bin/env python3
"""scaffold/clients.py on a SYNTHETIC clients root: each rule shown both ways.

  1. the root: --root, else CLIENTS_DIR, else the config file; none set is a refusal, never a guess.
  2. check: a whole folder passes; each missing piece, a bad index, a file with no row, a row with no file,
     a secret outside .machine/, open connections, a link target outside the folder: each one named.
  3. source: a file is copied (the original stays), its row gets the next id and its sha256; a URL is a row;
     the same bytes again are refused; a file already in the inbox gets its row in place with duplicate_of.
  4. relink: links made, a correct one kept, a wrong one replaced, a real file in the way never touched.
"""

import io
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.dont_write_bytecode = True
PLAYBOOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLAYBOOK / "scaffold"))
sys.path.insert(0, str(PLAYBOOK))

import clients as C  # noqa: E402
from kit.testing.check import check, finish, tmp_dir  # noqa: E402


def run(*argv: str, env: dict | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    old = dict(os.environ)
    os.environ.pop("CLIENTS_DIR", None)
    os.environ.update(env or {})
    try:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                rc = C.main(list(argv))
            except SystemExit as e:                     # argparse refuses a bad choice itself
                rc = e.code
    finally:
        os.environ.clear()
        os.environ.update(old)
    return rc, out.getvalue(), err.getvalue()


def make(root: Path, name: str = "acme") -> Path:
    c = root / name
    for d in ("intake", "sources/inbox", "reports", ".machine/connections"):
        (c / d).mkdir(parents=True, exist_ok=True)
    (c / ".machine" / "connections").chmod(0o700)
    (c / "README.md").write_text("# Acme\n", "utf-8")
    for f in C.INTAKE:
        (c / "intake" / f).write_text("x\n", "utf-8")
    (c / "sources" / "INDEX.tsv").write_text("\t".join(C.INDEX_HEADER) + "\n", "utf-8")
    return c


def test_root() -> None:
    print("[1] the root")
    r = Path(tmp_dir("clients-root-"))
    home = Path(tmp_dir("clients-home-"))
    rc, _, err = run("where", env={"HOME": str(home)})
    check("nothing set: refused, naming both ways to set it", rc == 2 and "CLIENTS_DIR" in err and "--set" in err, err)
    rc, out, _ = run("where", env={"HOME": str(home), "CLIENTS_DIR": str(r)})
    check("CLIENTS_DIR names it", rc == 0 and out.strip() == str(r.resolve()), out)
    rc, out, _ = run("where", "--set", str(r), env={"HOME": str(home)})
    check("--set writes the config file", rc == 0 and (home / ".config/openmax/clients_dir").read_text().strip()
          == str(r.resolve()), out)
    rc, out, _ = run("where", env={"HOME": str(home)})
    check("the config file names it when CLIENTS_DIR is unset", rc == 0 and out.strip() == str(r.resolve()), out)
    other = Path(tmp_dir("clients-other-"))
    rc, out, _ = run("where", env={"HOME": str(home), "CLIENTS_DIR": str(other)})
    check("CLIENTS_DIR wins over the file", out.strip() == str(other.resolve()), out)
    rc, _, err = run("where", env={"HOME": str(home), "CLIENTS_DIR": str(r / "gone")})
    check("a root that is not a folder: refused", rc == 2 and "not a folder" in err, err)


def test_check() -> None:
    print("[2] check")
    r = Path(tmp_dir("clients-check-"))
    c = make(r)
    (r / "_backups").mkdir()
    rc, out, _ = run("--root", str(r), "check")
    check("a whole folder passes; _backups is no client", rc == 0 and "ok: 1 client" in out, out)
    cases = []

    def broken(label, do, undo, want):
        do()
        cases.append((label, C.check(c), want))
        undo()
    broken("no card", lambda: (c / "README.md").unlink(), lambda: (c / "README.md").write_text("x"),
           "README.md (the client's card) is missing")
    broken("no brief", lambda: (c / "intake/brief.md").unlink(), lambda: (c / "intake/brief.md").write_text("x"),
           "intake/brief.md is missing")
    f = c / "sources/inbox/2026-11-05-client/a.txt"
    broken("a file with no row", lambda: (f.parent.mkdir(parents=True, exist_ok=True), f.write_text("a")),
           lambda: f.unlink(), "has no INDEX row")
    idx = c / "sources/INDEX.tsv"
    head = idx.read_text()
    row = "\t".join(["EV-001", "2026-11-05", "client", "file", "t", "inbox/x/gone.txt", "1", "1", "h", "", "", ""])
    broken("a row with no file", lambda: idx.write_text(head + row + "\n"), lambda: idx.write_text(head),
           "inbox/x/gone.txt does not exist")
    broken("an id used twice", lambda: idx.write_text(head + row.replace("inbox/x/gone.txt", "https://e.test/a") + "\n"
                                                      + row.replace("inbox/x/gone.txt", "https://e.test/b") + "\n"),
           lambda: idx.write_text(head), "EV-001 is used twice")
    broken("an unknown source", lambda: idx.write_text(head + row.replace("client", "rumour").replace(
        "inbox/x/gone.txt", "https://e.test/a") + "\n"), lambda: idx.write_text(head), "source 'rumour'")
    broken("a bad header", lambda: idx.write_text("id\tpath\n"), lambda: idx.write_text(head), "header is not")
    broken("a secret outside .machine/", lambda: (c / "reports/.env").write_text("K=v"),
           lambda: (c / "reports/.env").unlink(), "reports/.env: a secret's place is under .machine/")
    broken("open connections", lambda: (c / ".machine/connections").chmod(0o755),
           lambda: (c / ".machine/connections").chmod(0o700), "chmod 700")
    links = c / ".machine/links.tsv"
    broken("a link target outside the folder", lambda: links.write_text("path\ttarget\tnote\n~/x\t../other\tn\n"),
           lambda: links.unlink(), "must be a path inside the client folder")
    for label, got, want in cases:
        check(f"named: {label}", any(want in x for x in got), got)
    check("and the whole folder passes again", C.check(c) == [], C.check(c))


def test_source() -> None:
    print("[3] source")
    r = Path(tmp_dir("clients-source-"))
    c = make(r)
    orig = Path(tmp_dir("clients-dl-")) / "meeting notes.md"
    orig.write_text("notes", "utf-8")
    rc, out, _ = run("--root", str(r), "source", "acme", str(orig), "--from", "meeting", "--title", "Kickoff notes",
                     "--date", "2026-11-05")
    kept = c / "sources/inbox/2026-11-05-meeting/meeting notes.md"
    check("a file is copied into the day's inbox, the original stays, EV-001",
          rc == 0 and out.startswith("EV-001") and kept.read_text() == "notes" and orig.exists(), out)
    _, rows = C.read_index(c / "sources/INDEX.tsv")
    check("its row: source, kind, path, bytes, sha256", rows[0]["source"] == "meeting" and rows[0]["kind"] == "file"
          and rows[0]["path"] == "inbox/2026-11-05-meeting/meeting notes.md" and rows[0]["bytes"] == "5"
          and len(rows[0]["sha256"]) == 64, rows)
    rc, out, _ = run("--root", str(r), "source", "acme", "https://video.example.com/v/123", "--from", "chat",
                     "--title", "Reference video the client sent", "--date", "2026-11-05")
    check("a URL is a link row with the next id", rc == 0 and out.startswith("EV-002 ")
          and C.read_index(c / "sources/INDEX.tsv")[1][1]["kind"] == "link", out)
    rc, _, err = run("--root", str(r), "source", "acme", str(orig), "--from", "client", "--title", "again")
    check("the same bytes again: refused, the earlier id named", rc == 2 and "EV-001" in err, err)
    loose = c / "sources/inbox/2026-11-05-client/copy.md"
    loose.parent.mkdir(parents=True, exist_ok=True)
    loose.write_text("notes", "utf-8")
    rc, out, _ = run("--root", str(r), "source", "acme", str(loose), "--from", "client", "--title", "a kept copy",
                     "--date", "2026-11-05")
    _, rows = C.read_index(c / "sources/INDEX.tsv")
    check("a file already in the inbox: its row in place, no copy, duplicate_of names the same bytes",
          rc == 0 and rows[-1]["path"] == "inbox/2026-11-05-client/copy.md" and rows[-1]["duplicate_of"] == "EV-001"
          and len(list(loose.parent.iterdir())) == 1, rows[-1])
    check("and the folder passes check", C.check(c) == [], C.check(c))
    import new_hub
    check("the hub's sources README names every source this tool takes",
          all(f"`{x}`" in new_hub.SOURCES_README for x in C.SOURCES), new_hub.SOURCES_README[:400])
    rc, _, err = run("--root", str(r), "source", "acme", str(orig), "--from", "rumour", "--title", "x")
    check("an unknown --from: refused by the parser", rc == 2 and "invalid choice" in err, err)


def test_relink() -> None:
    print("[4] relink")
    r = Path(tmp_dir("clients-relink-"))
    c = make(r)
    (c / ".machine/workspace").mkdir()
    away = Path(tmp_dir("clients-away-"))
    (c / ".machine/links.tsv").write_text(
        "path\ttarget\tnote\n"
        f"{away}/ws\t.machine/workspace\tthe tools use this path\n"
        f"{away}/wrong\t.machine/workspace\twas pointing elsewhere\n"
        f"{away}/real\t.machine/workspace\ta real folder is in the way\n", "utf-8")
    (away / "wrong").symlink_to(away)
    (away / "real").mkdir()
    rc, out, _ = run("--root", str(r), "relink", "acme")
    check("links made, a wrong one replaced, a real folder reported and left",
          (away / "ws").resolve() == (c / ".machine/workspace").resolve()
          and (away / "wrong").resolve() == (c / ".machine/workspace").resolve()
          and (away / "real").is_dir() and not (away / "real").is_symlink() and "SKIP" in out and rc == 1, out)
    rc, out, _ = run("--root", str(r), "relink", "acme")
    check("again: the correct links are kept", out.count("ok ") == 2, out)


if __name__ == "__main__":
    test_root()
    test_check()
    test_source()
    test_relink()
    raise SystemExit(finish())
