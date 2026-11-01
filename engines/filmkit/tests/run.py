"""python3 tests/run.py : every tests/test_*.py in its own process (numpy, Pillow, scipy and ffmpeg are needed: `uv run --with numpy --with pillow --with scipy python3 tests/run.py`)."""
import re
import subprocess
import sys
from pathlib import Path

here = Path(__file__).parent
total, bad = 0, 0
for f in sorted(here.glob("test_*.py")):
    r = subprocess.run([sys.executable, str(f)], capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    m = re.match(r"RESULT: (\d+) passed", last)
    total += int(m.group(1)) if m else 0
    print(("ok    " if r.returncode == 0 else "FAIL  ") + f.name + "  " + last)
    if r.returncode:
        bad += 1
        print(r.stdout[-1500:], r.stderr[-1500:])
print(f"RESULT: {total} passed" if not bad else f"FAILED: {bad} of {len(list(here.glob('test_*.py')))} files")
sys.exit(1 if bad else 0)
