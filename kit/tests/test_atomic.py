#!/usr/bin/env python3
"""kit.atomic and kit.single_instance.

  * a write that fails mid-way leaves the target untouched and no temp
    file; a write that succeeds replaces it whole; JSON keeps non-ASCII;
  * the temp is fsynced before it replaces the target, and a writer
    killed mid-write (SIGKILL) leaves the old file whole, its leftover
    temp never in the way of the next write;
  * makedirs=True creates the missing parent folders (default: it does
    not, and the write fails as before); write_text_atomic;
  * hold(): the first holder gets True, a second (another open file, or
    another process) gets False without waiting; the lock goes with its
    holder; the lock file stays.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _shop  # noqa: E402
from kit import atomic, single_instance  # noqa: E402
from kit.testing.check import check, finish, raises, tmp_dir  # noqa: E402


def main() -> int:
    d = Path(tmp_dir("atomic-"))
    target = d / "raw.json"

    print("[1] atomic writes")
    atomic.write_json_atomic(target, {"a": "价格", "n": [1, 2]})
    check("write_json_atomic: the object, non-ASCII kept",
          json.loads(target.read_text("utf-8")) == {"a": "价格", "n": [1, 2]}
          and "价格" in target.read_text("utf-8"))

    def crash():
        with atomic.open_atomic(target) as f:
            f.write('{"half": ')
            raise OSError("disk full")
    check("a failure mid-write propagates", raises(crash, OSError) is not None)
    check("… the target is untouched and no temp file is left",
          json.loads(target.read_text("utf-8"))["a"] == "价格"
          and sorted(os.listdir(d)) == ["raw.json"], os.listdir(d))
    atomic.write_bytes_atomic(target, b"\x00bytes")
    check("write_bytes_atomic replaces it whole",
          target.read_bytes() == b"\x00bytes" and os.listdir(d) == ["raw.json"])
    with atomic.open_atomic(str(d / "t.txt")) as f:
        f.write("text")
    check("open_atomic takes a str path too", (d / "t.txt").read_text() == "text")
    check("two temp names for one path differ",
          atomic._tmp_for(target) != atomic._tmp_for(target)
          and atomic.is_temp(atomic._tmp_for(target)))
    mode = (d / "t.txt").stat().st_mode & 0o777
    umask = os.umask(0)
    os.umask(umask)
    check("the file gets the umask's mode, like a plain open()",
          mode == 0o666 & ~umask, oct(mode))

    synced = []
    real_fsync = os.fsync
    with mock.patch.object(os, "fsync",
                           lambda fd: (synced.append(fd), real_fsync(fd))):
        atomic.write_json_atomic(target, {"n": 1})
        atomic.write_bytes_atomic(d / "b.bin", b"x")
    check("the temp is flushed to disk (fsync) before the rename",
          len(synced) == 2, synced)
    atomic.write_json_atomic(target, {"rows": [1, 2, 3]})
    k = subprocess.run(
        [sys.executable, "-B", "-c",
         "import sys, os, signal; sys.path.insert(0, %r)\n"
         "from kit import atomic\n"
         "with atomic.open_atomic(sys.argv[1]) as f:\n"
         "    f.write('{\"rows\": [1'); f.flush()\n"
         "    os.kill(os.getpid(), signal.SIGKILL)"
         % str(_shop.PLAYBOOK), str(target)], capture_output=True, text=True)
    check("a killed writer leaves the old file whole",
          k.returncode == -9
          and json.loads(target.read_text("utf-8")) == {"rows": [1, 2, 3]}, k)
    atomic.write_json_atomic(target, {"rows": []})
    check("… and the leftover temp does not block the next write",
          json.loads(target.read_text("utf-8")) == {"rows": []}
          and sorted(n for n in os.listdir(d) if not atomic.is_temp(n))
          == ["b.bin", "raw.json", "t.txt"], os.listdir(d))

    print("\n[1b] makedirs and write_text_atomic")
    deep = d / "raw" / "pull" / "src" / "2026-10-28"
    for label, write in (
            ("write_json_atomic", lambda p, **k: atomic.write_json_atomic(p, {"a": 1}, **k)),
            ("write_bytes_atomic", lambda p, **k: atomic.write_bytes_atomic(p, b"x", **k)),
            ("write_text_atomic", lambda p, **k: atomic.write_text_atomic(p, "x", **k)),
            ("open_atomic", lambda p, **k: atomic.open_atomic(p, **k).__enter__())):
        check(f"{label}: by default no folder is created (FileNotFoundError)",
              raises(lambda: write(deep / "f.json"), FileNotFoundError) is not None
              and not (d / "raw").exists())
    atomic.write_json_atomic(deep / "f.json", {"a": 1}, makedirs=True)
    check("makedirs=True creates nested folders, then writes",
          json.loads((deep / "f.json").read_text("utf-8")) == {"a": 1}
          and os.listdir(deep) == ["f.json"])
    atomic.write_bytes_atomic(deep / "g" / "b.bin", b"\x01", makedirs=True)
    atomic.write_text_atomic(deep / "h" / "t.txt", "你好", makedirs=True)
    with atomic.open_atomic(deep / "i" / "o.txt", makedirs=True) as f:
        f.write("o")
    check("… for bytes, text and open_atomic too",
          (deep / "g" / "b.bin").read_bytes() == b"\x01"
          and (deep / "h" / "t.txt").read_text("utf-8") == "你好"
          and (deep / "i" / "o.txt").read_text() == "o")
    atomic.write_text_atomic(deep / "f.json", "{}", makedirs=True)
    check("makedirs=True on an existing folder is fine",
          (deep / "f.json").read_text() == "{}")
    nested = {"é": "价格", "l": [1, {"k": None}]}
    atomic.write_json_atomic(d / "j.json", nested, indent=1)
    check("write_json_atomic(indent=1) is json.dumps(ensure_ascii=False, indent=1), byte for byte",
          (d / "j.json").read_bytes()
          == json.dumps(nested, ensure_ascii=False, indent=1).encode("utf-8"))
    atomic.write_text_atomic(d / "x.txt", "old")

    def crash_new():
        with atomic.open_atomic(deep / "new" / "x.txt", makedirs=True) as f:
            f.write("half")
            raise OSError("disk full")
    check("a failure after makedirs propagates", raises(crash_new, OSError) is not None)
    check("… the temp is removed and no target appears",
          os.listdir(deep / "new") == [])

    def crash_old():
        with atomic.open_atomic(d / "x.txt", makedirs=True) as f:
            f.write("half")
            raise OSError("disk full")
    raises(crash_old, OSError)
    check("… and an existing target is left whole",
          (d / "x.txt").read_text() == "old" and not any(
              n.startswith("x.txt.") and atomic.is_temp(n) for n in os.listdir(d)),
          os.listdir(d))
    shutil.rmtree(d / "raw")

    print("\n[2] single_instance.hold")
    lock = d / "locks" / "run.lock"
    with single_instance.hold(lock) as first:
        with single_instance.hold(str(lock)) as second:
            check("first holder True, a second open False (no wait)",
                  first is True and second is False)
        r = subprocess.run(
            [sys.executable, "-B", "-c",
             "import sys; sys.path.insert(0, %r)\n"
             "from kit import single_instance\n"
             "with single_instance.hold(%r) as ok: print(ok)"
             % (str(_shop.PLAYBOOK), str(lock))],
            capture_output=True, text=True)
        check("another process gets False while we hold it",
              r.stdout.strip() == "False", r)
    with single_instance.hold(lock) as again:
        check("released on exit: the next holder gets True", again is True)
    check("the lock file stays (and its parent dir was created)",
          lock.is_file())
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
