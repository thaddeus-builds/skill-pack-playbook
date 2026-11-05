"""The panel shot (`fit: "panel"`): a solid colour, a title on the upper part, a picture with a white frame in the middle that slowly pushes in, a caption under the frame. The picture and
the colour are the shot's footage (graded with it); the title and the caption are type, so they are made here as ordinary `title` and `text` overlays that live as long as the shot, and
the layout check sees them and the frame as it does everything else.

    "panel": {"bg": [28, 84, 200], "title": ["TWO LINES", "AT THE TOP"], "title_size": 92, "title_y": 280, "frame": {"width": 10, "color": [255, 255, 255]},
              "margin": 120, "y": 540, "height": 580, "caption": "under the frame", "caption_size": 38}

`y` and `height` are the picture's top and height inside the frame (design pixels), `margin` the room each side of the frame. The push-in is the shot's `camera` zoom (1.0 to 1.08 when
it has none)."""
from __future__ import annotations

KEYS = {"bg", "title", "title_size", "title_y", "title_fill", "title_font", "frame", "margin", "y", "height", "caption", "caption_size", "caption_font"}
BG = (28, 84, 200)
WHITE = (255, 255, 255)


def geometry(pn: dict, w0: float, h0: float) -> dict:
    """The panel's numbers with the defaults in: `inner` (the picture's box), `outer` (with the frame), `fw`, `title_y`, `caption_y`, all in design pixels."""
    fr = pn.get("frame") or {}
    fw = fr.get("width", 10)
    margin = pn.get("margin", 120)
    y, height = pn.get("y", h0 * 0.28), pn.get("height", h0 * 0.30)
    inner = (margin, y, w0 - margin, y + height)
    return {"inner": inner, "outer": (inner[0] - fw, inner[1] - fw, inner[2] + fw, inner[3] + fw), "fw": fw, "frame_color": tuple(fr.get("color", WHITE)), "margin": margin,
            "title_y": pn.get("title_y", h0 * 0.145), "caption_y": y + height + fw + 28}


def overlays(shot: dict, canvas: dict) -> list[dict]:
    """The title and the caption of a panel shot as overlays that last as long as the shot."""
    pn = shot.get("panel")
    if shot.get("fit") != "panel" or not isinstance(pn, dict):
        return []
    w0, h0 = canvas["w"], canvas["h"]
    g = geometry(pn, w0, h0)
    out = []
    if pn.get("title"):
        out.append({"element": "title", "t0": shot["start"], "t1": shot["end"], "lines": list(pn["title"]), "x": w0 / 2, "y": g["title_y"], "anchor": "m", "size": pn.get("title_size", 92),
                    "font": pn.get("title_font", "black"), "fill": pn.get("title_fill", list(WHITE)), "max_width": w0 - 2 * g["margin"], "max_height": max(40.0, g["outer"][1] - 30 - g["title_y"]),
                    "tracking": 1.0})
    if pn.get("caption"):
        out.append({"element": "text", "t0": shot["start"], "t1": shot["end"], "text": pn["caption"], "x": w0 / 2, "y": g["caption_y"], "anchor": "m", "size": pn.get("caption_size", 38),
                    "font": pn.get("caption_font", "med"), "max_width": w0 - 2 * g["margin"], "alpha": 1.0, "dur": 0.4})
    return out


def frame_boxes(spec: dict, t: float) -> list[tuple[int, str, float, float, float, float]]:
    """(an id above any overlay's, a name, the box) of the picture and its frame of each panel shot that is on screen at `t`: the layout check keeps type off them. The `^` in the name says
    it takes room but is not type (it need not sit in the safe area)."""
    out = []
    for i, s in enumerate(spec.get("shots", [])):
        if s.get("fit") == "panel" and isinstance(s.get("panel"), dict) and s["start"] <= t < s["end"]:
            out.append((10_000 + i, "^panel frame", *geometry(s["panel"], spec["canvas"]["w"], spec["canvas"]["h"])["outer"]))
    return out
