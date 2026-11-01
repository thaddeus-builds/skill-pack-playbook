"""python3 engines/filmkit/tests/run.py : every tests/test_*.py in its own process (numpy, Pillow, scipy and ffmpeg are needed: `uv run --with numpy --with pillow --with scipy python3 tests/run.py`)."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import numpy, PIL, scipy  # noqa: E401,F401
except ImportError:             # the playbook's own Python has none of the three: borrow them from uv for this run (nothing is installed)
    if shutil.which("uv") and not os.environ.get("FILMKIT_UV_REEXEC"):
        os.environ["FILMKIT_UV_REEXEC"] = "1"
        os.execvp("uv", ["uv", "run", "--no-project", "--with", "numpy", "--with", "pillow", "--with", "scipy", "python3", __file__])
    print("FAILED: numpy, Pillow and scipy are needed (pip install numpy pillow scipy, or install uv)")
    sys.exit(1)

HERE = Path(__file__).parent
total, bad = 0, 0
for f in sorted(HERE.glob("test_*.py")):
    r = subprocess.run([sys.executable, str(f)], capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    m = re.match(r"RESULT: (\d+) passed", last)
    total += int(m.group(1)) if m else 0
    print(("ok    " if r.returncode == 0 else "FAIL  ") + f.name + "  " + last)
    if r.returncode:
        bad += 1
        print(r.stdout[-1500:], r.stderr[-1500:])
print(f"RESULT: {total} passed" if not bad else f"FAILED: {bad} of {len(list(HERE.glob('test_*.py')))} files")
sys.exit(1 if bad else 0)
