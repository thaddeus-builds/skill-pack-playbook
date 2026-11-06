"""The film spec, `filmkit.film/1`: one JSON document that says everything about a film, so a maker pack writes a spec and filmkit renders it. Times are seconds, coordinates are pixels of the
spec's own canvas (the design size), the order of `overlays` is their stacking order, and a shot owns the span [start, end] (a transition is centred on the cut that opens a shot).

    {"schema": "filmkit.film/1", "id": "...", "canvas": {"w": 1080, "h": 1920, "fps": 30}, "duration": 44.0, "bpm": 90,
     "assets": {"clip1": {"type": "video", "path": "raw/clip1.mp4"}, "logo": {"type": "image", "path": "logo.png"},
                "matte1": {"type": "frames", "path": "matte/m_%04d.png", "fps": 30}},        # video, image, or frames (a numbered picture sequence)
     "fonts": {"black": "...otf"},                                   # optional: roles black, bold, med, reg, serif
     "shots": [{"id": "s1", "asset": "clip1", "start": 0, "end": 4, "in": 8.0, "speed": 1.0, "fit": "fill",     # fit: fill, card, panel (+ "panel"), split (+ "split"); + "cutout"
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
import math
import re
from pathlib import Path

from . import cutout as CO
from . import grade as G
from . import panel as PN
from .elements import ELEMENTS
from .fonts import ROLES as FONT_ROLES
from .transitions import GHOST_MAX, TYPES
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


BITRATE = re.compile(r"^\d+(\.\d+)?[kKmM]?$")
ANCHORS = ("l", "m", "r")
# the numeric parameters of the elements and the range each may take; a wrong type or a number outside it is a line of `validate`, never a crash in the middle of a render
NUM_PARAMS = {
    "x": (-5000, 10000), "y": (-5000, 10000), "x0": (-5000, 10000), "x1": (-5000, 10000), "top": (-5000, 10000), "size": (1, 2000), "suffix_size": (1, 2000), "name_size": (1, 2000),
    "tracking": (-100, 300), "stagger": (0, 5), "dur": (0, 10), "rise": (-500, 500), "lead": (0.5, 3), "out": (0, 600), "out_dur": (0, 10), "alpha": (0, 1), "width": (1, 10000),
    "max_width": (1, 10000), "max_height": (1, 10000), "opacity": (0, 1), "fade_in": (0, 10), "fade_out": (0, 10), "target": (0, 1e9), "hold": (0, 10), "suffix_scale": (0.1, 3),
    "period": (0.1, 30), "typewriter": (1, 200), "sweep": (0.05, 3), "settle": (0.05, 3), "shadow": (0, 1), "tracking_in": (-100, 300), "tracking_dur": (0.05, 10), "thickness": (1, 200), "arm": (1, 2000), "step": (1, 5000), "gap": (0, 30), "first": (0, 30),
}
GRADE_KEYS = {"black": (-0.2, 0.5), "contrast": (0.2, 3), "s_curve": (-1, 1), "saturation": (0, 3), "gamma": (0.3, 3), "vignette": (0, 1), "grain": (0, 60)}
MUSIC_LISTS = ("impacts", "whooshes", "pings")


class _Constant(ValueError):
    pass


def _no_constant(name: str):
    raise _Constant(f"{name} is not a number a spec may hold")


def load(path: str | Path) -> tuple[dict, Path]:
    """The spec and the folder its relative paths are read from (absolute, so a file name that looks like an option or a URL is still a file). A spec that is not a JSON object is a FilmkitError."""
    p = Path(path).resolve()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"), parse_constant=_no_constant)
    except OSError as e:
        raise FilmkitError(f"cannot read the spec {path}: {e}") from e
    except ValueError as e:
        raise FilmkitError(f"the spec {path} is not valid JSON: {e}") from e
    if not isinstance(doc, dict):
        raise FilmkitError(f"the spec {path} is not a JSON object")
    return doc, p.parent


def _dur(t) -> float:
    """What a transition adds to the windows of the two shots it joins: nothing for a cut."""
    return 0.0 if not isinstance(t, dict) or t.get("type") == "cut" else max(0.0, float(t.get("dur", 0.0) or 0.0))


def windows(spec: dict) -> list[tuple[float, float]]:
    """The span each shot is on screen, its transitions included."""
    shots = spec["shots"]
    out = []
    for i, s in enumerate(shots):
        din = _dur(s.get("transition")) if i > 0 else 0.0
        dout = _dur(shots[i + 1].get("transition")) if i + 1 < len(shots) else 0.0
        out.append((s["start"] - din / 2, s["end"] + dout / 2))
    return out


def _n(v, lo=None, hi=None) -> bool:
    """A real, finite number (not a bool) within [lo, hi]."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and (lo is None or v >= lo) and (hi is None or v <= hi)


def _line(v) -> bool:
    return isinstance(v, str) and v.isprintable()


def _is_file(base_dir: Path, v) -> bool:
    try:
        p = Path(v)
        return (p if p.is_absolute() else base_dir / p).is_file()
    except (TypeError, ValueError, OSError):
        return False


FRAMES = re.compile(r"%0?\d*d")


def _asset_present(base_dir: Path, a: dict) -> bool:
    """Whether the file an asset names is there; for `frames`, whether its first numbered picture is."""
    if a.get("type") == "frames":
        from .media import frames_first
        p = Path(a["path"])
        return frames_first(str(p if p.is_absolute() else base_dir / p)) is not None
    return _is_file(base_dir, a["path"])


def all_overlays(spec: dict) -> list[dict]:
    """The overlays the film draws: the spec's own, then the type of each panel shot (its title and caption), which lives as long as the shot."""
    derived = [el for s in spec.get("shots", []) if isinstance(s, dict) for el in PN.overlays(s, spec["canvas"])]
    return derived + list(spec.get("overlays", []))


def _overlay_problems(el: dict, w: str, assets: dict) -> list[str]:
    out: list[str] = []
    for k, (lo, hi) in NUM_PARAMS.items():
        if el.get(k) is not None and not _n(el[k], lo, hi):                  # an explicit null is "not given" (a title's `out`, a steps list's `name_size`)
            out.append(f"{w}.{k}: must be a number from {lo:g} to {hi:g}")
    if "font" in el and el["font"] not in FONT_ROLES:
        out.append(f"{w}.font: must be one of {', '.join(FONT_ROLES)}")
    if "suffix_font" in el and el["suffix_font"] is not None and el["suffix_font"] not in FONT_ROLES:
        out.append(f"{w}.suffix_font: must be one of {', '.join(FONT_ROLES)}")
    if "anchor" in el and el["anchor"] not in ANCHORS:
        out.append(f"{w}.anchor: must be one of {', '.join(ANCHORS)}")
    for k in ("text", "suffix"):
        if k in el and not _line(el[k]):
            out.append(f"{w}.{k}: must be text on one line")
    if "lines" in el and not (isinstance(el["lines"], list) and el["lines"] and all(_line(x) for x in el["lines"])):
        out.append(f"{w}.lines: must be a list of lines of text, each on one line")
    if "items" in el and not (isinstance(el["items"], list) and el["items"] and all(isinstance(i, list) and len(i) == 2 and _line(str(i[0])) and _line(i[1]) for i in el["items"])):
        out.append(f"{w}.items: must be a list of [number, title] pairs, each on one line")
    if "box" in el and not (isinstance(el["box"], list) and len(el["box"]) == 4 and all(_n(x, -5000, 10000) for x in el["box"]) and el["box"][0] < el["box"][2] and el["box"][1] < el["box"][3]):
        out.append(f"{w}.box: must be [x0, y0, x1, y1] with x0 < x1 and y0 < y1")
    if el.get("element") == "rule" and _n(el.get("x0")) and _n(el.get("x1")) and el["x1"] <= el["x0"]:
        out.append(f"{w}.x1: must be greater than x0")
    for k in ("color", "fill", "accent"):
        if k in el and el[k] is not None and not (isinstance(el[k], list) and len(el[k]) >= 3 and all(_n(c, 0, 255) for c in el[k][:3])):
            out.append(f"{w}.{k}: must be [r, g, b], each from 0 to 255")
    if "dir" in el and el["dir"] not in ("left", "right", "top", "bottom"):
        out.append(f"{w}.dir: must be left, right, top or bottom")
    if "align" in el and el["align"] not in ("l", "m"):
        out.append(f"{w}.align: must be l or m")
    if "grow" in el and el["grow"] not in ("left", "middle", None):
        out.append(f"{w}.grow: must be left or middle")
    if "dot" in el and not isinstance(el["dot"], bool):
        out.append(f"{w}.dot: must be true or false")
    if el.get("element") == "logo" and el.get("asset") not in assets:
        out.append(f"{w}.asset: {el.get('asset')!r} is not in assets")
    elif el.get("element") == "logo" and assets[el["asset"]].get("type") != "image":
        out.append(f"{w}.asset: the logo must be an image asset")
    return out


FITS = ("fill", "card", "panel", "split")


def _rgb(v) -> bool:
    return isinstance(v, list) and len(v) >= 3 and all(_n(c, 0, 255) for c in v[:3])


def _camera_problems(cam, where: str) -> list[str]:
    if cam is None:
        return []
    z = cam.get("zoom") if isinstance(cam, dict) else None
    c = cam.get("center") if isinstance(cam, dict) else None
    if not (isinstance(cam, dict) and (z is None or (isinstance(z, list) and len(z) == 2 and all(_n(x, 0.5, 6) for x in z)))
            and (c is None or (isinstance(c, list) and len(c) == 2 and all(isinstance(p, list) and len(p) == 2 and all(_n(x, 0, 1) for x in p) for p in c)))):
        return [f"{where}: must be {{zoom: [from, to], center: [[x, y], [x, y]]}}, zoom from 0.5 to 6 and the centre a fraction of the picture"]
    return []


def _panel_problems(s: dict, w: str) -> list[str]:
    pn = s.get("panel")
    if s.get("fit") != "panel":
        return [f"{w}.panel: only a shot with fit: panel has one"] if pn is not None else []
    if not isinstance(pn, dict):
        return [f"{w}.panel: a panel shot needs {{bg, title, frame, y, height, caption}}"]
    out = [f"{w}.panel.{k}: not a panel key (one of {', '.join(sorted(PN.KEYS))})" for k in pn if k not in PN.KEYS]
    for k in ("title_size", "caption_size"):
        if k in pn and not _n(pn[k], 1, 2000):
            out.append(f"{w}.panel.{k}: must be a number from 1 to 2000")
    for k, lo, hi in (("title_y", -5000, 10000), ("y", 0, 10000), ("height", 20, 10000), ("margin", 0, 5000)):
        if k in pn and not _n(pn[k], lo, hi):
            out.append(f"{w}.panel.{k}: must be a number from {lo:g} to {hi:g}")
    for k in ("bg", "bg2", "title_fill"):
        if k in pn and not _rgb(pn[k]):
            out.append(f"{w}.panel.{k}: must be [r, g, b], each from 0 to 255")
    for k in ("title_font", "caption_font"):
        if k in pn and pn[k] not in FONT_ROLES:
            out.append(f"{w}.panel.{k}: must be one of {', '.join(FONT_ROLES)}")
    if "title" in pn and not (isinstance(pn["title"], list) and 1 <= len(pn["title"]) <= 3 and all(_line(x) for x in pn["title"])):
        out.append(f"{w}.panel.title: must be one to three lines of text, each on one line")
    if "caption" in pn and not _line(pn["caption"]):
        out.append(f"{w}.panel.caption: must be text on one line")
    fr = pn.get("frame")
    if fr is not None and not (isinstance(fr, dict) and set(fr) <= {"width", "color"} and _n(fr.get("width", 10), 0, 100) and _rgb(fr.get("color", [255, 255, 255]))):
        out.append(f"{w}.panel.frame: must be {{width (0 to 100), color [r, g, b]}}")
    return out


def _split_problems(s: dict, w: str, assets: dict) -> list[str]:
    sp = s.get("split")
    if s.get("fit") != "split":
        return [f"{w}.split: only a shot with fit: split has one"] if sp is not None else []
    if not isinstance(sp, dict) or not isinstance(sp.get("bottom"), dict) or set(sp) - {"bottom", "at", "seam"}:
        return [f"{w}.split: a split shot needs {{bottom: {{asset, in, speed, camera}}, at, seam}}: the shot's own asset is the top half"]
    out = []
    b = sp["bottom"]
    if not isinstance(b.get("asset"), str) or b["asset"] not in assets:
        out.append(f"{w}.split.bottom.asset: {b.get('asset')!r} is not in assets")
    elif assets[b["asset"]].get("type") == "frames":
        out.append(f"{w}.split.bottom.asset: a picture sequence is for a matte, not a half")
    for k in b:
        if k not in ("asset", "in", "speed", "camera", "dim", "blur"):
            out.append(f"{w}.split.bottom.{k}: not a key of a half (asset, in, speed, camera, dim, blur)")
    if "in" in b and not _n(b["in"], 0, 36000):
        out.append(f"{w}.split.bottom.in: must be a number of seconds from 0")
    if "speed" in b and not _n(b["speed"], 0.05, 20):
        out.append(f"{w}.split.bottom.speed: must be a number from 0.05 to 20")
    out += _camera_problems(b.get("camera"), f"{w}.split.bottom.camera")
    if "at" in sp and not _n(sp["at"], 0.2, 0.8):
        out.append(f"{w}.split.at: must be a number from 0.2 to 0.8 (where the seam is, from the top)")
    sm = sp.get("seam")
    if sm is not None and not (isinstance(sm, dict) and set(sm) <= {"color", "width"} and _n(sm.get("width", 6), 1, 200) and _rgb(sm.get("color", [255, 255, 255]))):
        out.append(f"{w}.split.seam: must be {{color [r, g, b], width}}")
    return out


def _cutout_problems(s: dict, w: str, assets: dict) -> list[str]:
    c = s.get("cutout")
    if c is None:
        return []
    if s.get("fit", "fill") != "fill":
        return [f"{w}.cutout: only a fit: fill shot can carry a cutout"]
    if not isinstance(c, dict) or set(c) - CO.KEYS:
        return [f"{w}.cutout: must be {{matte, outline, bg}}"]
    out = []
    if c.get("matte") not in assets:
        out.append(f"{w}.cutout.matte: {c.get('matte')!r} is not in assets (a matte is an asset: filmkit makes none)")
    elif c["matte"] == s.get("asset"):
        out.append(f"{w}.cutout.matte: the matte cannot be the shot's own clip")
    ol = c.get("outline", {})
    if ol is not False:
        if not isinstance(ol, dict) or set(ol) - CO.OUTLINE_KEYS:
            out.append(f"{w}.cutout.outline: must be false or {{{', '.join(sorted(CO.OUTLINE_KEYS))}}}")
        else:
            if "color" in ol and not _rgb(ol["color"]):
                out.append(f"{w}.cutout.outline.color: must be [r, g, b], each from 0 to 255")
            for k, lo, hi in (("width", 1, 60), ("speed", -3000, 3000), ("offset", -60, 60)):
                if k in ol and not _n(ol[k], lo, hi):
                    out.append(f"{w}.cutout.outline.{k}: must be a number from {lo:g} to {hi:g}")
            if "dash" in ol and not (isinstance(ol["dash"], list) and len(ol["dash"]) == 2 and all(_n(x, 1, 1000) for x in ol["dash"])):
                out.append(f"{w}.cutout.outline.dash: must be [on, off], pixels from 1 to 1000")
    bg = c.get("bg", {})
    if not isinstance(bg, dict) or set(bg) - CO.BG_KEYS:
        out.append(f"{w}.cutout.bg: must be {{{', '.join(sorted(CO.BG_KEYS))}}}")
    else:
        for k, lo, hi in (("zoom", 1, 6), ("blur", 0, 200), ("tint_mix", 0, 1)):
            if k in bg and not _n(bg[k], lo, hi):
                out.append(f"{w}.cutout.bg.{k}: must be a number from {lo:g} to {hi:g}")
        if bg.get("tint") is not None and not _rgb(bg["tint"]):
            out.append(f"{w}.cutout.bg.tint: must be [r, g, b], each from 0 to 255")
        if bg.get("posterize") is not None and not (isinstance(bg["posterize"], int) and not isinstance(bg["posterize"], bool) and 2 <= bg["posterize"] <= 64):
            out.append(f"{w}.cutout.bg.posterize: must be a whole number of levels from 2 to 64")
    return out


def _shot_problems(s, i: int, shots: list, assets: dict, prev_end: float, ids: set) -> tuple[list[str], float | None]:
    w = f"shots[{i}]"
    out: list[str] = []
    if not isinstance(s, dict):
        return [f"{w}: must be an object"], None
    if not isinstance(s.get("id"), str) or not s["id"]:
        out.append(f"{w}.id: must be a name")
    elif s["id"] in ids:
        out.append(f"{w}.id: {s['id']!r} is used twice")
    ids.add(s.get("id") if isinstance(s.get("id"), str) else None)
    if not isinstance(s.get("asset"), str) or s["asset"] not in assets:
        out.append(f"{w}.asset: {s.get('asset')!r} is not in assets")
    if not (_n(s.get("start")) and _n(s.get("end")) and s["start"] < s["end"]):
        return out + [f"{w}: start and end must be numbers with start before end"], None
    if abs(s["start"] - prev_end) > 1e-3:
        out.append(f"{w}.start: {s['start']} leaves a gap or an overlap after the last shot ({prev_end}); shots must follow one another")
    if s.get("fit", "fill") not in FITS:
        out.append(f"{w}.fit: must be one of {', '.join(FITS)}")
    if "speed" in s and not _n(s["speed"], 0.05, 20):
        out.append(f"{w}.speed: must be a number from 0.05 to 20")
    if "in" in s and not _n(s["in"], 0, 36000):
        out.append(f"{w}.in: must be a number of seconds from 0")
    if "blur" in s and not _n(s["blur"], 0, 100):
        out.append(f"{w}.blur: must be a number from 0 to 100")
    if "dim" in s and not (isinstance(s["dim"], list) and len(s["dim"]) == 2 and all(_n(x, 0, 1) for x in s["dim"])):
        out.append(f"{w}.dim: must be [from, to], each from 0 to 1")
    if "card" in s and not (isinstance(s["card"], dict) and all(_n(v, 0.05, 1.0) for v in s["card"].values()) and set(s["card"]) <= {"width", "y"}):
        out.append(f"{w}.card: must be {{width, y}}, each from 0.05 to 1")
    out += _camera_problems(s.get("camera"), f"{w}.camera")
    out += _panel_problems(s, w)
    out += _split_problems(s, w, assets)
    out += _cutout_problems(s, w, assets)
    t = s.get("transition")
    if t is not None:
        if i == 0:
            out.append(f"{w}.transition: the first shot has nothing to come from")
        elif not isinstance(t, dict):
            out.append(f"{w}.transition: must be an object {{type, dur}}")
        elif t.get("type") not in TYPES:
            out.append(f"{w}.transition.type: must be one of {', '.join(TYPES)}")
        elif t["type"] != "cut":
            prev = shots[i - 1] if isinstance(shots[i - 1], dict) and _n(shots[i - 1].get("start")) and _n(shots[i - 1].get("end")) else None
            if not _n(t.get("dur"), 0.02, 3):
                out.append(f"{w}.transition.dur: must be a number of seconds from 0.02 to 3 (a cut has none)")
            elif prev is not None and t["dur"] > min(s["end"] - s["start"], prev["end"] - prev["start"]) / 2 + 1e-6:
                out.append(f"{w}.transition.dur: longer than half of a shot it joins")
            elif t["type"] == "ghost" and t["dur"] > GHOST_MAX:
                out.append(f"{w}.transition.dur: a ghost is a quick whip, {GHOST_MAX:g} s at most (0.15 to 0.3 reads best)")
    return out, s["end"]


def _media_problems(spec: dict, base_dir: Path) -> list[str]:
    """What the files are: a video asset has a video stream and a shot does not start after its clip ends; an image asset opens as a picture."""
    from PIL import Image

    from .media import probe
    out: list[str] = []
    info: dict = {}
    for name, a in spec["assets"].items():
        if not _is_file(base_dir, a["path"]):
            continue
        p = Path(a["path"])
        p = p if p.is_absolute() else base_dir / p
        if a["type"] == "frames":
            continue                                                         # looked at below, with the matte it serves
        if a["type"] == "image":
            try:
                with Image.open(p) as im:
                    im.verify()
            except Exception as e:  # noqa: BLE001 - anything Pillow refuses is not a picture
                out.append(f"assets.{name}.path: {a['path']!r} is not a picture Pillow can open ({type(e).__name__})")
        else:
            try:
                info[name] = probe(p)
            except FilmkitError as e:
                out.append(f"assets.{name}.path: {a['path']!r} cannot be read as a video ({str(e)[:120]})")
                continue
            if not info[name]["w"]:
                out.append(f"assets.{name}.path: {a['path']!r} has no video stream")
    for i, s in enumerate(spec["shots"]):
        meta = info.get(s.get("asset"))
        if meta and meta["w"] and meta["duration"] and s.get("in", 0) >= meta["duration"] - 0.05:
            out.append(f"shots[{i}].in: {s['in']} is at or after the end of the clip ({meta['duration']:.2f} s): the shot would be black")
        b = (s.get("split") or {}).get("bottom") if isinstance(s.get("split"), dict) else None
        bmeta = info.get(b.get("asset")) if isinstance(b, dict) else None
        if bmeta and bmeta["w"] and bmeta["duration"] and b.get("in", 0) >= bmeta["duration"] - 0.05:
            out.append(f"shots[{i}].split.bottom.in: {b['in']} is at or after the end of its clip ({bmeta['duration']:.2f} s): the half would be black")
        out += _matte_problems(spec, i, s, base_dir, info)
    return out


def _matte_problems(spec: dict, i: int, s: dict, base_dir: Path, info: dict) -> list[str]:
    """A matte is as big as the clip it cuts out and as long: a different size is stretched to fit (the outline would sit off the subject), a shorter one holds its last frame."""
    from PIL import Image
    c = s.get("cutout")
    if not isinstance(c, dict) or c.get("matte") not in spec["assets"]:
        return []
    ma, clip = spec["assets"][c["matte"]], spec["assets"].get(s.get("asset"), {})
    w = f"shots[{i}].cutout.matte"
    p = Path(ma["path"])
    p = p if p.is_absolute() else base_dir / p
    size = None
    if ma["type"] == "frames":
        from .media import frames_first
        n = frames_first(str(p))
        try:
            with Image.open(str(p) % n) as im:
                size = im.size
        except Exception as e:  # noqa: BLE001
            return [f"{w}: the first picture of {ma['path']!r} cannot be opened ({type(e).__name__})"]
    elif ma["type"] == "image" and p.is_file():
        try:
            with Image.open(p) as im:
                size = im.size
        except Exception:  # noqa: BLE001
            return []
    elif c["matte"] in info:
        size = (info[c["matte"]]["w"], info[c["matte"]]["h"])
    out = []
    ref = info.get(s.get("asset"))
    if clip.get("type") == "image" and clip.get("path") and _is_file(base_dir, clip["path"]):
        try:
            with Image.open(Path(clip["path"]) if Path(clip["path"]).is_absolute() else base_dir / clip["path"]) as im:
                ref = {"w": im.width, "h": im.height, "duration": 0}
        except Exception:  # noqa: BLE001
            ref = None
    if size and ref and ref.get("w") and tuple(size) != (ref["w"], ref["h"]):
        out.append(f"{w}: the matte is {size[0]}x{size[1]} and the clip {ref['w']}x{ref['h']}: they must be the same size")
    mm = info.get(c["matte"])
    if mm and ref and mm["duration"] and ref.get("duration") and mm["duration"] < ref["duration"] - 0.1:
        out.append(f"{w}: the matte runs {mm['duration']:.2f} s and the clip {ref['duration']:.2f} s: they must have the same frames")
    return out


def problems(spec: dict, base_dir: Path | None = None) -> list[str]:
    """Everything wrong with a spec, each as `where: what`. [] when it can be rendered. Files are looked for (and read as what they claim to be) when `base_dir` is given. Never raises:
    a shape this does not foresee is a line too."""
    try:
        return _problems(spec, base_dir)
    except Exception as e:  # noqa: BLE001
        return [f"spec: malformed ({type(e).__name__}: {e})"]


def _problems(spec, base_dir: Path | None) -> list[str]:
    if not isinstance(spec, dict):
        return ["spec: must be a JSON object"]
    out: list[str] = []
    if spec.get("schema") != SCHEMA:
        out.append(f"schema: must be {SCHEMA!r}")
    c = spec.get("canvas")
    c = c if isinstance(c, dict) else {}
    for k, hi in (("w", 8192), ("h", 8192), ("fps", 120)):
        if not (isinstance(c.get(k), int) and not isinstance(c.get(k), bool) and 0 < c[k] <= hi):
            out.append(f"canvas.{k}: must be a whole number from 1 to {hi}")
    if isinstance(c.get("w"), int) and isinstance(c.get("h"), int) and (c["w"] % 2 or c["h"] % 2):
        out.append("canvas: width and height must be even (H.264)")
    dur = spec.get("duration")
    fps = c.get("fps") if isinstance(c.get("fps"), int) and c["fps"] > 0 else 30
    if not _n(dur, 2.0 / fps, 600):
        return out + ["duration: must be a number of seconds from two frames to 600"]
    if "bpm" in spec and not _n(spec["bpm"], 20, 300):
        out.append("bpm: must be a number from 20 to 300")
    assets = spec.get("assets")
    if not isinstance(assets, dict):
        return out + ["assets: must be an object {name: {type, path}}"]
    for name, a in assets.items():
        if not isinstance(a, dict):
            out.append(f"assets.{name}: must be an object {{type, path}}")
            continue
        if a.get("type") not in ("video", "image", "frames"):
            out.append(f"assets.{name}.type: must be video, image or frames")
        if not isinstance(a.get("path"), str) or not a["path"]:
            out.append(f"assets.{name}.path: must be a file name")
        elif a.get("type") == "frames" and not FRAMES.search(a["path"]):
            out.append(f"assets.{name}.path: a frames asset is a numbered pattern such as matte/m_%04d.png")
        elif base_dir is not None and not _asset_present(base_dir, a):
            out.append(f"assets.{name}.path: {a['path']!r} is not a file")
        if "fps" in a and not (a.get("type") == "frames" and _n(a["fps"], 1, 240)):
            out.append(f"assets.{name}.fps: only a frames asset has one, a number from 1 to 240")
    if base_dir is not None and isinstance(spec.get("fonts"), dict):
        for role, f in spec["fonts"].items():
            if role not in FONT_ROLES:
                out.append(f"fonts.{role}: a font role is one of {', '.join(FONT_ROLES)}")
            elif f is not None and not _is_file(base_dir, f):
                out.append(f"fonts.{role}: {f!r} is not a file")
    elif "fonts" in spec and not isinstance(spec["fonts"], dict):
        out.append("fonts: must be an object {role: file}")
    shots = spec.get("shots")
    if not isinstance(shots, list) or not shots:
        return out + ["shots: at least one shot"]
    ids: set = set()
    prev_end = 0.0
    ok_shots = True
    for i, s in enumerate(shots):
        bad, end = _shot_problems(s, i, shots, assets, prev_end, ids)
        out += bad
        if end is None:
            ok_shots = False
        else:
            prev_end = end
    if ok_shots and abs(prev_end - dur) > 1e-3:
        out.append(f"shots: end at {prev_end}, the duration is {dur}")
    overlays = spec.get("overlays", [])
    if not isinstance(overlays, list):
        out.append("overlays: must be a list")
        overlays = []
    for i, el in enumerate(overlays):
        w = f"overlays[{i}]"
        if not isinstance(el, dict):
            out.append(f"{w}: must be an object")
            continue
        cls = ELEMENTS.get(el.get("element"))
        if cls is None:
            out.append(f"{w}.element: {el.get('element')!r} is not one of {', '.join(ELEMENTS)}")
            continue
        if not (_n(el.get("t0")) and _n(el.get("t1")) and el["t0"] < el["t1"]):
            out.append(f"{w}: t0 and t1 must be numbers with t0 before t1")
        typed = _overlay_problems(el, w, assets)
        out += typed
        if not typed:
            out += [f"{w} ({el['element']}): {m}" for m in cls.check(el)]
    scrim = spec.get("scrim")
    if scrim is not None and scrim is not False and not (isinstance(scrim, dict) and all(_n(scrim[k], 0, 255 if k.endswith("alpha") else 1) for k in scrim) and
                                                         set(scrim) <= {"top", "bottom", "top_alpha", "bottom_alpha"}):
        out.append("scrim: must be false, or {top, bottom (fractions), top_alpha, bottom_alpha (0 to 255)}")
    fo = spec.get("fade_out")
    if fo is not None and not (isinstance(fo, dict) and _n(fo.get("t"), 0) and _n(fo.get("dur"), 0.01, 30) and set(fo) <= {"t", "dur"}):
        out.append("fade_out: must be {t, dur}, seconds, dur above 0")
    gr = spec.get("grade") if isinstance(spec.get("grade"), dict) else {}
    if "grade" in spec and not isinstance(spec["grade"], dict):
        out.append("grade: must be an object {look, over}")
    elif gr.get("look", "natural") not in G.LOOKS:
        out.append(f"grade.look: must be one of {', '.join(G.LOOKS)}")
    over = gr.get("over")
    if over is not None:
        if not isinstance(over, dict) or [k for k in over if k not in G.LOOKS["natural"]]:
            out.append(f"grade.over: must be an object of the look's numbers ({', '.join(G.LOOKS['natural'])})")
        else:
            for k, v in over.items():
                rng = GRADE_KEYS.get(k)
                if rng is not None and not _n(v, *rng):
                    out.append(f"grade.over.{k}: must be a number from {rng[0]:g} to {rng[1]:g}")
                elif rng is None and not (isinstance(v, list) and len(v) == 3 and all(_n(x, -1, 1) for x in v)):
                    out.append(f"grade.over.{k}: must be [r, g, b], each from -1 to 1")
    out += _audio_problems(spec.get("audio"), base_dir)
    enc = spec.get("encode")
    if enc is not None:
        if not isinstance(enc, dict) or set(enc) - {"bitrate", "minrate", "maxrate", "bufsize", "crf"}:
            out.append("encode: must be {bitrate, minrate, maxrate, bufsize} or {crf}")
        else:
            for k in ("bitrate", "minrate", "maxrate", "bufsize"):
                if k in enc and not (isinstance(enc[k], (str, int, float)) and not isinstance(enc[k], bool) and BITRATE.match(str(enc[k]))):
                    out.append(f"encode.{k}: must look like 10M, 8500k or 9000000")
            if "crf" in enc and not _n(enc["crf"], 0, 51):
                out.append("encode.crf: must be a number from 0 to 51")
    safe = spec.get("safe")
    if safe is not None:
        if not isinstance(safe, dict) or set(safe) - {"profile", "box"}:
            out.append("safe: must be {profile} or {box}")
        else:
            if "profile" in safe and safe["profile"] not in SAFE_PROFILES:
                out.append(f"safe.profile: must be one of {', '.join(SAFE_PROFILES)}")
            if "box" in safe and not (isinstance(safe["box"], list) and len(safe["box"]) == 4 and all(_n(x, 0, 10000) for x in safe["box"]) and safe["box"][0] < safe["box"][2] and safe["box"][1] < safe["box"][3]):
                out.append("safe.box: must be [x0, y0, x1, y1] in the canvas's own pixels")
    if base_dir is not None and not out:
        out += _media_problems(spec, base_dir)
    return out


def _audio_problems(a, base_dir: Path | None) -> list[str]:
    if a is None:
        return []
    if not isinstance(a, dict):
        return ["audio: must be an object"]
    out: list[str] = []
    for k, lo, hi in (("duck_db", -60, 0), ("lufs", -40, -5), ("fade_out", 0.01, 30)):
        if k in a and not _n(a[k], lo, hi):
            out.append(f"audio.{k}: must be a number from {lo:g} to {hi:g}")
    voice = a.get("voice", [])
    if not isinstance(voice, list):
        out.append("audio.voice: must be a list of {t, file}")
        voice = []
    for i, v in enumerate(voice):
        if not isinstance(v, dict) or not _n(v.get("t"), 0) or not isinstance(v.get("file"), str) or not v["file"]:
            out.append(f"audio.voice[{i}]: t (from 0) and file are required")
        elif base_dir is not None and not _is_file(base_dir, v["file"]):
            out.append(f"audio.voice[{i}].file: {v['file']!r} is not a file")
        elif "gain" in v and not _n(v["gain"], 0, 8):
            out.append(f"audio.voice[{i}].gain: must be a number from 0 to 8")
    m = a.get("music")
    if m is not None:
        if not isinstance(m, dict):
            return out + ["audio.music: must be an object"]
        if "bpm" in m and not _n(m["bpm"], 20, 300):
            out.append("audio.music.bpm: must be a number from 20 to 300")
        if "pluck_from" in m and not _n(m["pluck_from"], 0):
            out.append("audio.music.pluck_from: must be a number of seconds from 0")
        if "bed" in m and not isinstance(m["bed"], bool):
            out.append("audio.music.bed: must be true or false")
        for k in MUSIC_LISTS:
            if k in m and not (isinstance(m[k], list) and all(_n(x, 0) for x in m[k])):
                out.append(f"audio.music.{k}: must be a list of times in seconds from 0")
        if "risers" in m and not (isinstance(m["risers"], list) and all(isinstance(r, list) and len(r) == 2 and _n(r[0], 0) and _n(r[1], 0) and r[0] < r[1] for r in m["risers"])):
            out.append("audio.music.risers: must be a list of [from, to] times in seconds with from before to")
    return out


def require(spec: dict, base_dir: Path | None = None) -> None:
    bad = problems(spec, base_dir)
    if bad:
        raise FilmkitError("the film spec has problems:\n  " + "\n  ".join(bad))
