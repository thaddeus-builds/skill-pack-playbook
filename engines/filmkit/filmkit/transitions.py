"""Transitions between two frames (float arrays of the same size) at progress p, 0 to 1. A shot's `transition` {type, dur} is centred on the cut it opens."""
from __future__ import annotations

import math

import numpy as np

from .util import ease_out, smooth

TYPES = ("cut", "dissolve", "flash", "push", "dip", "wipe", "ghost")
GHOST_MAX = 0.5                          # a ghost is a whip: longer than this it is a smear (`validate` says so)


def shifted(a: np.ndarray, k: int) -> np.ndarray:
    """`a` moved `k` pixels to the left (to the right when negative), the edge held, so nothing wraps round."""
    if k == 0:
        return a
    out = np.empty_like(a)
    if k > 0:
        out[:, :-k] = a[:, k:]
        out[:, -k:] = a[:, -1:]
    else:
        out[:, -k:] = a[:, :k]
        out[:, :-k] = a[:, :1]
    return out


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
    if kind == "ghost":                      # a quick whip: the dissolve smeared along x into an echo that trails to the left, widest at the middle, none at either end
        mix = a * (1 - e) + b * e
        reach = int(math.sin(math.pi * p) * 0.22 * a.shape[1])
        n = 7
        out = np.zeros_like(mix)
        total = 0.0
        for k in range(n):
            w = 1.0 - k / n * 0.7
            out += shifted(mix, reach * k // (n - 1)) * w
            total += w
        return out / total
    return b
