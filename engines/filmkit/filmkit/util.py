"""Small shared helpers: easing, ffmpeg, and the render context every element and shot draws in."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def smooth(x: float) -> float:
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out(x: float) -> float:
    x = clamp(x)
    return 1 - (1 - x) ** 3


def prog(t: float, a: float, d: float) -> float:
    """How far `t` is through the span that starts at `a` and lasts `d` seconds, 0 to 1."""
    return clamp((t - a) / d) if d > 0 else (1.0 if t >= a else 0.0)


class FilmkitError(Exception):
    """A spec or a tool problem the caller can fix; the message says what and where."""


def ffmpeg_path() -> str:
    p = shutil.which("ffmpeg")
    if not p:
        raise FilmkitError("ffmpeg is not on PATH: filmkit decodes, grades and encodes with it")
    return p


def ffprobe_path() -> str:
    p = shutil.which("ffprobe")
    if not p:
        raise FilmkitError("ffprobe is not on PATH")
    return p


def run(cmd: list[str], cwd: Path | None = None) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode:
        raise FilmkitError(f"{cmd[0]} failed ({r.returncode}): {r.stderr.strip()[-400:]}")
    return r.stdout


@dataclass
class Ctx:
    """What an element or a shot needs to draw: the design canvas (the spec's own size, in which every coordinate is written), the render scale `q` (a preview renders smaller), the
    fonts and the resolved assets. Coordinates and sizes in a spec are design pixels; `s(v)` makes one a pixel of this render."""
    w0: int
    h0: int
    q: float
    fonts: object
    assets: dict = field(default_factory=dict)
    assets_type: dict = field(default_factory=dict)
    assets_fps: dict = field(default_factory=dict)        # the rate of a picture sequence (asset type `frames`)
    base_dir: Path = Path(".")
    cache: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)          # what a render says about its material that is not a problem (an HDR clip)

    @property
    def W(self) -> int:
        return int(self.w0 * self.q) // 2 * 2

    @property
    def H(self) -> int:
        return int(self.h0 * self.q) // 2 * 2

    def s(self, v: float) -> float:
        return v * self.q

    def font(self, kind: str, size: float):
        return self.fonts.get(kind, size * self.q)
