"""The film spec, `filmkit.film/1`: one JSON document that says everything about a film, so a maker pack writes a spec and filmkit renders it. Times are seconds, coordinates are pixels of the
spec's own canvas (the design size), the order of `overlays` is their stacking order, and a shot owns the span [start, end] (a transition is centred on the cut that opens a shot).

    {"schema": "filmkit.film/1", "id": "...", "canvas": {"w": 1080, "h": 1920, "fps": 30}, "duration": 44.0, "bpm": 90,
     "assets": {"clip1": {"type": "video", "path": "raw/clip1.mp4"}, "logo": {"type": "image", "path": "logo.png"}},
     "fonts": {"black": "...otf"},                                   # optional: roles black, bold, med, reg
     "shots": [{"id": "s1", "asset": "clip1", "start": 0, "end": 4, "in": 8.0, "speed": 1.0, "fit": "fill",
                "camera": {"zoom": [1.3, 1.0], "center": [[0.4, 0.66], [0.5, 0.5]]}, "dim": [0, 0], "blur": 0,
                "transition": {"type": "dissolve", "dur": 0.4}}, ...],    # the transition is into this shot, so not on the first
     "grade": {"look": "teal_warm_soft", "over": {...}},
     "overlays": [{"element": "title", "t0": 0.4, "t1": 4.6, "lines": ["..."], "x": 64, "y": 330, ...}, ...],
     "scrim": {"top": 0.30, "bottom": 0.60, "top_alpha": 100, "bottom_alpha": 165},     # a soft gradient under the type; false for none
     "fade_out": {"t": 43.2, "dur": 0.8},
     "audio": {"voice": [{"t": 0.55, "file": "vo_0.wav"}], "music": {"bpm": 90, "pluck_from": 9.3, "impacts": [], "risers": [], "whooshes": [], "pings": []},
               "duck_db": -7, "lufs": -16, "fade_out": 1.4},
     "encode": {"bitrate": "10M", "minrate": "8500k", "maxrate": "12M", "bufsize": "24M"},       # or {"crf": 18}
     "safe": {"profile": "tiktok"}}                                    # read by `check` only
"""
from __future__ import annotations

import json
from pathlib import Path

from . import grade as G
from .elements import ELEMENTS
from .transitions import TYPES
from .util import FilmkitError

SCHEMA = "filmkit.film/1"
SAFE_PROFILES = {
    # design-space boxes for a 1080x1920 canvas: where type may sit. TikTok covers the top (the tabs), the bottom (the caption) and the right edge (the buttons); the guides disagree on the
    # exact numbers, so this is the stricter reading until TikTok's own template is read (docs/filmkit.md)
    "tiktok": [60, 250, 900, 1250],
    "reels": [60, 250, 900, 1350],
    "shorts": [60, 250, 900, 1350],
    "full": [40, 40, 1040, 1880],
}


def load(path: str | Path) -> tuple[dict, Path]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")), p.parent


def windows(spec: dict) -> list[tuple[float, float]]:
    """The span each shot is on screen, its transitions included."""
    shots = spec["shots"]
    out = []
    for i, s in enumerate(shots):
        din = (s.get("transition") or {}).get("dur", 0.0) if i > 0 else 0.0
        dout = (shots[i + 1].get("transition") or {}).get("dur", 0.0) if i + 1 < len(shots) else 0.0
        out.append((s["start"] - din / 2, s["end"] + dout / 2))
    return out


def problems(spec: dict, base_dir: Path | None = None) -> list[str]:
    """Everything wrong with a spec, each as `where: what`. [] when it can be rendered. Files are looked for when `base_dir` is given."""
    out: list[str] = []
    if spec.get("schema") != SCHEMA:
        out.append(f"schema: must be {SCHEMA!r}")
    c = spec.get("canvas") or {}
    for k in ("w", "h", "fps"):
        if not isinstance(c.get(k), int) or c[k] <= 0:
            out.append(f"canvas.{k}: must be a positive integer")
    if isinstance(c.get("w"), int) and (c["w"] % 2 or c.get("h", 2) % 2):
        out.append("canvas: width and height must be even (H.264)")
    dur = spec.get("duration")
    if not isinstance(dur, (int, float)) or dur <= 0:
        out.append("duration: must be a positive number of seconds")
        return out
    assets = spec.get("assets") or {}
    for name, a in assets.items():
        if a.get("type") not in ("video", "image"):
            out.append(f"assets.{name}.type: must be video or image")
        if base_dir is not None and not (Path(a.get("path", "")) if Path(a.get("path", "")).is_absolute() else base_dir / a.get("path", "")).is_file():
            out.append(f"assets.{name}.path: {a.get('path')!r} is not a file")
    shots = spec.get("shots")
    if not isinstance(shots, list) or not shots:
        return out + ["shots: at least one shot"]
    ids, prev_end = set(), 0.0
    for i, s in enumerate(shots):
        w = f"shots[{i}]"
        if s.get("id") in ids:
            out.append(f"{w}.id: {s.get('id')!r} is used twice")
        ids.add(s.get("id"))
        if s.get("asset") not in assets:
            out.append(f"{w}.asset: {s.get('asset')!r} is not in assets")
        if not (isinstance(s.get("start"), (int, float)) and isinstance(s.get("end"), (int, float)) and s["start"] < s["end"]):
            out.append(f"{w}: start and end must be numbers with start before end")
            continue
        if abs(s["start"] - prev_end) > 1e-3:
            out.append(f"{w}.start: {s['start']} leaves a gap or an overlap after the last shot ({prev_end}); shots must follow one another")
        prev_end = s["end"]
        if s.get("fit", "fill") not in ("fill", "card"):
            out.append(f"{w}.fit: must be fill or card")
        if s.get("speed", 1.0) <= 0:
            out.append(f"{w}.speed: must be above 0")
        t = s.get("transition")
        if i == 0 and t:
            out.append(f"{w}.transition: the first shot has nothing to come from")
        if t:
            if t.get("type") not in TYPES:
                out.append(f"{w}.transition.type: must be one of {', '.join(TYPES)}")
            elif t["type"] != "cut" and t.get("dur", 0) > min(s["end"] - s["start"], shots[i - 1]["end"] - shots[i - 1]["start"]) / 2 + 1e-6:
                out.append(f"{w}.transition.dur: longer than half of a shot it joins")
    if abs(prev_end - dur) > 1e-3:
        out.append(f"shots: end at {prev_end}, the duration is {dur}")
    for i, el in enumerate(spec.get("overlays", [])):
        w = f"overlays[{i}]"
        cls = ELEMENTS.get(el.get("element"))
        if cls is None:
            out.append(f"{w}.element: {el.get('element')!r} is not one of {', '.join(ELEMENTS)}")
            continue
        if not (isinstance(el.get("t0"), (int, float)) and isinstance(el.get("t1"), (int, float)) and el["t0"] < el["t1"]):
            out.append(f"{w}: t0 and t1 must be numbers with t0 before t1")
        out += [f"{w} ({el['element']}): {m}" for m in cls.check(el)]
        if el["element"] == "logo" and el.get("asset") not in assets:
            out.append(f"{w}.asset: {el.get('asset')!r} is not in assets")
    gr = spec.get("grade") or {}
    if gr.get("look", "natural") not in G.LOOKS:
        out.append(f"grade.look: must be one of {', '.join(G.LOOKS)}")
    for i, v in enumerate((spec.get("audio") or {}).get("voice", [])):
        if not isinstance(v.get("t"), (int, float)) or not v.get("file"):
            out.append(f"audio.voice[{i}]: t and file are required")
        elif base_dir is not None and not (Path(v["file"]) if Path(v["file"]).is_absolute() else base_dir / v["file"]).is_file():
            out.append(f"audio.voice[{i}].file: {v['file']!r} is not a file")
    return out


def require(spec: dict, base_dir: Path | None = None) -> None:
    bad = problems(spec, base_dir)
    if bad:
        raise FilmkitError("the film spec has problems:\n  " + "\n  ".join(bad))
