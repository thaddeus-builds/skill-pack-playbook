"""The colour grade: a 3D LUT made from a few numbers (named looks), plus a vignette and film grain, applied by ffmpeg over the footage layer so the type on top stays pure."""
from __future__ import annotations

from pathlib import Path

import numpy as np

LOOKS = {
    "natural": dict(black=0.0, contrast=1.0, s_curve=0.0, shadow=(0, 0, 0), highlight=(0, 0, 0), saturation=1.0, gamma=1.0, vignette=0.0, grain=0),
    # the sample's look: the haze off the blacks, shadows leaning teal-blue and highlights warm, a little more colour, a touch darker in the mids, a soft vignette, fine grain
    "teal_warm_soft": dict(black=0.035, contrast=1.10, s_curve=0.10, shadow=(-0.010, 0.012, 0.034), highlight=(0.034, 0.014, -0.028), saturation=1.06, gamma=1.05, vignette=0.6, grain=6),
}


def look(name: str, over: dict | None = None) -> dict:
    if name not in LOOKS:
        raise KeyError(f"look {name!r} is not one of {', '.join(LOOKS)}")
    return {**LOOKS[name], **(over or {})}


def write_cube(path: Path, lk: dict, size: int = 33) -> Path:
    g = np.linspace(0, 1, size)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")           # the .cube order: red varies fastest
    rgb = np.stack([r, gg, b], axis=-1)
    luma = (rgb * np.array([0.2126, 0.7152, 0.0722])).sum(-1, keepdims=True)
    x = np.clip((rgb - lk["black"]) * lk["contrast"], 0, 1)
    x = x + (x - 0.5) * lk["s_curve"] * (1 - np.abs(x - 0.5) * 2)
    x = x + (1 - luma) ** 2 * np.array(lk["shadow"]) + luma ** 2 * np.array(lk["highlight"])
    grey = (x * np.array([0.2126, 0.7152, 0.0722])).sum(-1, keepdims=True)
    x = np.clip(grey + (x - grey) * lk["saturation"], 0, 1) ** lk["gamma"]
    lines = ['TITLE "filmkit"', f"LUT_3D_SIZE {size}"] + [f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}" for p in x.reshape(-1, 3)]
    Path(path).write_text("\n".join(lines) + "\n")
    return Path(path)


def escape(v: str) -> str:
    """A file name as a filter option: the characters that a filter graph reads as syntax are escaped."""
    for ch in "\\:',[]=;":
        v = v.replace(ch, "\\" + ch)
    return v


def ffmpeg_filter(cube: str | Path, lk: dict) -> str:
    """The grade as an ffmpeg filter chain. `cube` is the LUT's file name: run ffmpeg in the folder that holds it, so the name is a plain one."""
    parts = [f"lut3d=file={escape(str(cube))}:interp=tetrahedral"]
    if lk["vignette"] > 0:
        parts.append("vignette=angle=PI/5")
    if lk["grain"] > 0:
        parts.append(f"noise=alls={int(lk['grain'])}:allf=t+u")
    return ",".join(parts)
