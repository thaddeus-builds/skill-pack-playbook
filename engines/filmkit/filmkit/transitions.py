"""Transitions between two frames (float arrays of the same size) at progress p, 0 to 1. A shot's `transition` {type, dur} is centred on the cut it opens."""
from __future__ import annotations

import numpy as np

from .util import ease_out, smooth

TYPES = ("cut", "dissolve", "flash", "push", "dip", "wipe")


def blend(a: np.ndarray, b: np.ndarray, p: float, kind: str) -> np.ndarray:
    e = smooth(p)
    if kind == "dissolve":
        return a * (1 - e) + b * e
    if kind == "flash":                      # a dissolve with a white pulse at the middle: the cut lands on an impact
        return np.minimum(255.0, a * (1 - e) + b * e + 255.0 * 0.55 * (1 - abs(2 * p - 1)) ** 1.5)
    if kind == "dip":                        # through black
        return a * (1 - 2 * p) if p < 0.5 else b * (2 * p - 1)
    if kind == "push":                       # the next shot pushes the last one up and out
        h = a.shape[0]
        both = np.concatenate([a, b], axis=0)
        k = int(ease_out(p) * h)
        return both[k:k + h]
    if kind == "wipe":                       # the next shot is drawn in from the left
        w = a.shape[1]
        k = int(ease_out(p) * w)
        out = a.copy()
        out[:, :k] = b[:, :k]
        return out
    return b
