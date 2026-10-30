"""A tiny test helper: the fixtures every test file builds on (synthetic clips, a photo, a logo, a voice line) and a runner. Nothing here is a client's."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["FILMKIT_NO_SYSTEM_FONTS"] = "1"

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


@contextmanager
def tmpdir():
    with tempfile.TemporaryDirectory(prefix="filmkit-test-") as d:
        yield Path(d)


from filmkit.demo import film_spec, make_assets  # noqa: E402,F401   the fixtures live in the library: `python -m filmkit demo` makes the same


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def frame_at(path: Path, t: float) -> np.ndarray:
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    import io
    return np.asarray(Image.open(io.BytesIO(out)).convert("RGB"), dtype=np.float32)


def main(g: dict) -> None:
    failed = 0
    names = [n for n in g if n.startswith("test_") and callable(g[n])]
    for n in names:
        try:
            g[n]()
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL {n}")
            traceback.print_exc()
    print(f"RESULT: {len(names) - failed} passed" if not failed else f"FAILED: {failed} of {len(names)}")
    sys.exit(1 if failed else 0)
