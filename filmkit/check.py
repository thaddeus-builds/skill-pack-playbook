"""Checks that need no render: where type sits (inside the safe area? on top of other type?), whether voice lines run into each other, whether the cuts land on the beat. These are the
things a person finds by looking and a machine can find by measuring."""
from __future__ import annotations

from pathlib import Path

from . import spec as S
from .audio import read_audio, SR
from .elements import ELEMENTS
from .fonts import Fonts
from .util import Ctx


def context(spec: dict, base_dir: Path, q: float = 1.0) -> Ctx:
    c = spec["canvas"]
    return Ctx(c["w"], c["h"], q, Fonts(spec.get("fonts"), base_dir), {}, {}, base_dir)


def safe_box(spec: dict) -> list[float] | None:
    s = spec.get("safe")
    if not s:
        return None
    box = s.get("box") or S.SAFE_PROFILES.get(s.get("profile"))
    if box is None:
        return None
    c = spec["canvas"]
    sx, sy = c["w"] / 1080, c["h"] / 1920
    return [box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy]


def layout(spec: dict, base_dir: Path, step: float = 0.2) -> list[str]:
    """Type outside the safe area, and two pieces of type on each other, found by sampling every `step` seconds."""
    cx = context(spec, base_dir)
    sb = safe_box(spec)
    found, seen = [], set()
    t = 0.0
    while t < spec["duration"]:
        boxes = []
        for i, el in enumerate(spec.get("overlays", [])):
            if el["t0"] <= t < el["t1"]:
                for name, x0, y0, x1, y1 in ELEMENTS[el["element"]].boxes(t, el, cx, el):
                    boxes.append((i, name, x0, y0, x1, y1))
        for i, name, x0, y0, x1, y1 in boxes:
            if sb and (x0 < sb[0] - 1 or y0 < sb[1] - 1 or x1 > sb[2] + 1 or y1 > sb[3] + 1) and (i, name, "safe") not in seen:
                seen.add((i, name, "safe"))
                found.append(f"t={t:.1f}s: {name} ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f}) is outside the safe area {[round(v) for v in sb]}")
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                (i, na, ax0, ay0, ax1, ay1), (j, nb, bx0, by0, bx1, by1) = boxes[a], boxes[b]
                if i == j:
                    continue
                ow, oh = min(ax1, bx1) - max(ax0, bx0), min(ay1, by1) - max(ay0, by0)
                if ow > 8 and oh > 8 and (i, j, "over") not in seen:
                    seen.add((i, j, "over"))
                    found.append(f"t={t:.1f}s: {na} and {nb} overlap by {ow:.0f}x{oh:.0f} px")
        t += step
    return found


def timing(spec: dict, base_dir: Path) -> list[str]:
    """Voice lines that run into the next one or past the end, and cuts that miss the beat by more than 80 ms (when the spec has a bpm)."""
    found = []
    voice = sorted((spec.get("audio") or {}).get("voice", []), key=lambda v: v["t"])
    ends = []
    for v in voice:
        p = Path(v["file"])
        ends.append((v["t"], v["t"] + len(read_audio(p if p.is_absolute() else base_dir / p)) / SR))
    for (a0, a1), (b0, b1) in zip(ends, ends[1:]):
        if a1 > b0 + 0.02:
            found.append(f"voice at {a0:.2f}s runs to {a1:.2f}s, into the line at {b0:.2f}s")
    if ends and ends[-1][1] > spec["duration"] + 0.02:
        found.append(f"the last voice line runs to {ends[-1][1]:.2f}s, past the end ({spec['duration']}s)")
    bpm = spec.get("bpm")
    if bpm:
        beat = 60 / bpm
        for s in spec["shots"][1:]:
            off = s["start"] % beat
            off = min(off, beat - off)
            if off > 0.08:
                found.append(f"the cut at {s['start']}s is {off * 1000:.0f} ms off the beat of {bpm} BPM")
    return found


def fonts_note(spec: dict, base_dir: Path) -> list[str]:
    f = Fonts(spec.get("fonts"), base_dir)
    return [f"font role {r}: no file found, the fallback face is used" for r in f.fallback]


def all_checks(spec: dict, base_dir: Path) -> dict:
    return {"layout": layout(spec, base_dir), "timing": timing(spec, base_dir), "fonts": fonts_note(spec, base_dir)}
