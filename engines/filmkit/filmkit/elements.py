"""The graphics layer: animated elements, each a small function of time. A spec lists them as {element, t0, t1, ...params}; coordinates and sizes are design pixels of the spec's canvas, times
inside an element are seconds after its `t0` (so moving an element in time moves all of it). Every element has three parts: `check` (what is wrong with its params), `draw` (a frame of it on
an RGBA layer) and `boxes` (where its type sits at a time, in design pixels: the layout check reads these to find a line off the safe area or two lines on each other).

    title    lines of type that rise and fade in one after another (a mask reveal), optionally out again; `max_width` and `max_height` shrink the size until the lines fit
    text     one tracked line that fades in (a tagline, a small label); `max_width` shrinks it to fit
    chip     a rounded label with a pulsing dot (a section tag); `max_width` shrinks the text so the whole chip fits
    brackets four corner brackets that grow out from the centre of a box
    scan     a sweeping line with a trail and a measuring rule on the edge of a box
    callout  a data label on a point: a dot with a ring, a leader line that draws on to a thin-bordered box with a small label over a big value and its unit
    counter  a number that counts up to a target, then a suffix (its own size: `suffix_size`) that pops; `max_width` scales both down to fit
    steps    a vertical progress line with numbered items that appear in turn (`name_size`; `max_width`: the items' titles shrink to fit it)
    rule     a line that grows from its centre (or from its left end: `grow`: "left")
    logo     the brand's mark, faded in and out (`max_height`: a square mark is made narrower; the layout check sees its box)
    kinetic  one big word in the serif face that sweeps in from an edge (a trail, a lean) and settles, shrinking, into a subtitle line at `to`
    year     a big serif number or phrase that rises into place with a soft shadow, optionally held and faded out
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from .util import Ctx, ease_out, prog, smooth

BLUE = (63, 160, 240)
WHITE = (255, 255, 255)
ELEMENTS: dict = {}


def element(name):
    def deco(cls):
        ELEMENTS[name] = cls
        return cls
    return deco


def rgb(v, default):
    return tuple(int(c) for c in v[:3]) if isinstance(v, (list, tuple)) and len(v) >= 3 else default


def track_text(d, xy, text, f, fill, tracking=0.0, anchor="l", q=1.0, shadow=True, limit=None, stroke=None):
    """`text` one character at a time with `tracking` pixels between, from `xy` (anchor l, m or r). Returns its width. A shadow sits under type that has an alpha. `limit`: draw only the
    first characters (a typewriter) while the line is placed as the whole text is, so a centred line does not slide as it fills."""
    x, y = xy
    widths = [d.textlength(ch, font=f) + tracking * q for ch in text]
    total = sum(widths) - tracking * q
    if anchor == "m":
        x -= total / 2
    elif anchor == "r":
        x -= total
    for ch, w in list(zip(text, widths))[:limit]:
        if shadow and len(fill) == 4:
            d.text((x + 1.5 * q, y + 3.5 * q), ch, font=f, fill=(0, 0, 0, int(fill[3] * 0.55)))
        if stroke:
            d.text((x, y), ch, font=f, fill=fill, stroke_width=max(1, int(round(stroke["width"] * q))), stroke_fill=(*rgb(stroke.get("color"), (0, 0, 0)), int(fill[3] * stroke.get("alpha", 0.85)) if len(fill) == 4 else 255))
        else:
            d.text((x, y), ch, font=f, fill=fill)
        x += w
    return total


def text_width(cx: Ctx, text: str, kind: str, size: float, tracking: float = 0.0) -> float:
    """The width of `text` in design pixels (measured at the render scale and scaled back, so a preview and a final agree)."""
    d = ImageDraw.Draw(Image.new("L", (4, 4)))
    f = cx.font(kind, size)
    return (sum(d.textlength(ch, font=f) + tracking * cx.q for ch in text) - tracking * cx.q) / cx.q


def fitted(cx: Ctx, texts: list[str], kind: str, size: float, tracking: float, max_width: float | None, floor: float = 0.6) -> float:
    """The size (design pixels) at which the widest of `texts` fits `max_width`: `size` itself when it already does, else scaled down to fit, never below `floor` of it (a line that
    still does not fit is for the layout check to name). The tracking between letters does not shrink with the size, so the room for the letters themselves is what is left of
    `max_width` after it. No `max_width`: `size`."""
    if not max_width:
        return size
    best = size
    for t in texts:
        if text_width(cx, t, kind, size, tracking) <= max_width:
            continue
        glyphs = text_width(cx, t, kind, size, 0.0)
        room = max_width - tracking * max(0, len(t) - 1)
        best = min(best, size * room / glyphs * 0.98 if glyphs > 0 and room > 0 else 0.0)
    return max(size * floor, best)


def title_size(cx: Ctx, p: dict) -> float:
    """A title's size: its own, shrunk until the widest line fits `max_width` and the lines fit `max_height` (design pixels; never below 60 percent)."""
    size = fitted(cx, p["lines"], p["font"], p["size"], max(p["tracking"], p.get("tracking_in") or p["tracking"]), p.get("max_width"))       # sized for the widest the letters get
    mh = p.get("max_height")
    if mh and len(p["lines"]) * size * p["lead"] > mh:
        size = max(p["size"] * 0.6, mh / (len(p["lines"]) * p["lead"]) * 0.98)
    return size


def paste_clipped(layer, tmp, y):
    if y < 0 or y + tmp.height > layer.height:
        tmp = tmp.crop((0, max(0, -y), tmp.width, min(tmp.height, layer.height - y)))
        y = max(0, y)
    if tmp.height > 0:
        layer.alpha_composite(tmp, (0, y))


def rrect(cx: Ctx, layer, box, r, fill=None, outline=None, width=2, alpha=1.0):
    tmp = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    b = tuple(int(v * cx.q) for v in box)
    d.rounded_rectangle(b, int(r * cx.q), fill=(*fill, int(255 * alpha)) if fill else None, outline=(*outline, int(255 * alpha)) if outline else None,
                        width=max(1, int(width * cx.q)))
    layer.alpha_composite(tmp)


def ink_rows(cx: Ctx, kind: str, size: float, text: str) -> tuple[float, float]:
    """The rows (design pixels, from the line's top: where `draw` puts `y`) between which the ink of `text` sits in the face: the font's own bounding box, so a descender or a CJK bottom is inside it."""
    _, top, _, bottom = cx.font(kind, size).getbbox(text or " ", anchor="la")
    return top / cx.q, bottom / cx.q


def line_box(cx, text, x, y, kind, size, anchor, tracking):
    """Where one line of tracked type is, in design pixels: its advance width across, the face's ink rows down."""
    w = text_width(cx, text, kind, size, tracking)
    x0 = x if anchor == "l" else (x - w / 2 if anchor == "m" else x - w)
    top, bottom = ink_rows(cx, kind, size, text)
    return (x0, y + top, x0 + w, y + bottom)


def scratch(cx: Ctx, kind: str, size: float) -> Image.Image:
    """A transparent strip for one line to be drawn into and pasted clipped (the reveal mask of a line that rises): as tall as the face itself, ascent and descent and 12 pixels."""
    asc, desc = cx.font(kind, size).getmetrics()
    return Image.new("RGBA", (cx.W, asc + desc + 12), (0, 0, 0, 0))


def anchor_problems(p) -> list[str]:
    return [] if p.get("anchor", "l") in ("l", "m", "r") else ["anchor must be l, m or r"]


@element("title")
class Title:
    defaults = dict(font="black", size=96, fill=[255, 255, 255], anchor="l", tracking=0.0, stagger=0.14, dur=0.55, rise=46, lead=1.12, out=None, out_dur=0.35,
                    typewriter=None, tracking_in=None, tracking_dur=0.9)

    @staticmethod
    def starts(p) -> list[float]:
        """When each line begins, in seconds after `t0`: one `stagger` after the last, or, with `typewriter` (characters a second), when the line before it has been typed."""
        cps = p.get("typewriter")
        if not cps:
            return [i * p["stagger"] for i in range(len(p["lines"]))]
        out, t = [], 0.0
        for line in p["lines"]:
            out.append(t)
            t += len(line) / cps + 0.12
        return out

    @staticmethod
    def spacing(p, t, ts) -> float:
        """The letter spacing at `t` for a line that begins at `ts`: `tracking_in` easing to `tracking` over `tracking_dur` when the title has one."""
        if p.get("tracking_in") is None:
            return p["tracking"]
        return p["tracking"] + (p["tracking_in"] - p["tracking"]) * (1 - ease_out(prog(t, ts, p["tracking_dur"])))

    @staticmethod
    def check(p):
        out = []
        if not isinstance(p.get("lines"), list) or not p["lines"] or not all(isinstance(x, str) for x in p["lines"]):
            out.append("lines must be a list of strings")
        for k in ("x", "y"):
            if not isinstance(p.get(k), (int, float)):
                out.append(f"{k} must be a number")
        return out + anchor_problems(p)

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        t0 = el["t0"]
        fill = rgb(p["fill"], WHITE)
        starts, cps = cls.starts(p), p.get("typewriter")
        for i, line in enumerate(p["lines"]):
            ts = t0 + starts[i]
            a = (1.0 if t >= ts else 0.0) if cps else ease_out(prog(t, ts, p["dur"]))
            if p["out"] is not None:
                a *= 1 - smooth(prog(t, t0 + p["out"] + i * 0.05, p["out_dur"]))
            if a <= 0.001:
                continue
            size, lead = title_size(cx, p), p["lead"]
            ly = p["y"] + i * size * lead
            tmp = scratch(cx, p["font"], size)
            d = ImageDraw.Draw(tmp)
            yy = (0 if cps else (1 - a) * p["rise"] * cx.q) + 6
            track_text(d, (p["x"] * cx.q, yy), line, cx.font(p["font"], size), (*fill, int(255 * min(1.0, a * 1.4))), cls.spacing(p, t, ts), p["anchor"], cx.q,
                       limit=int((t - ts) * cps) + 1 if cps else None)
            paste_clipped(layer, tmp, int((ly - 6) * cx.q))

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        if t < el["t0"]:
            return []
        out = []
        size = title_size(cx, p)
        starts = cls.starts(p)
        for i, line in enumerate(p["lines"]):
            gone = p["out"] is not None and t >= el["t0"] + p["out"] + i * 0.05 + p["out_dur"]          # a line that has faded out is no longer on the screen
            if t >= el["t0"] + starts[i] + 0.2 and not gone:                                              # the box of a typed line is the whole line's, from the moment it begins
                out.append((f"title:{line[:18]}", *line_box(cx, line, p["x"], p["y"] + i * size * p["lead"], p["font"], size, p["anchor"], cls.spacing(p, t, el["t0"] + starts[i]))))
        return out

    @staticmethod
    def texts(p):
        return [(p.get("font", "black"), line) for line in p["lines"]]


@element("text")
class Text:
    defaults = dict(font="med", size=36, fill=[255, 255, 255], anchor="l", tracking=0.0, dur=0.6, alpha=0.92, typewriter=None)

    @staticmethod
    def check(p):
        return ([] if isinstance(p.get("text"), str) and isinstance(p.get("x"), (int, float)) and isinstance(p.get("y"), (int, float)) else ["text, x and y are required"]) + anchor_problems(p)

    @staticmethod
    def texts(p):
        return [(p.get("font", "med"), p["text"])]

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        cps = p.get("typewriter")
        a = (1.0 if t >= el["t0"] else 0.0) if cps else ease_out(prog(t, el["t0"], p["dur"]))
        if a <= 0:
            return
        d = ImageDraw.Draw(layer)
        size = fitted(cx, [p["text"]], p["font"], p["size"], p["tracking"], p.get("max_width"))
        track_text(d, (p["x"] * cx.q, p["y"] * cx.q), p["text"], cx.font(p["font"], size), (*rgb(p["fill"], WHITE), int(255 * p["alpha"] * a)), p["tracking"], p["anchor"], cx.q,
                   limit=int((t - el["t0"]) * cps) + 1 if cps else None, stroke=p.get("stroke"))

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        size = fitted(cx, [p["text"]], p["font"], p["size"], p["tracking"], p.get("max_width"))
        return [("text", *line_box(cx, p["text"], p["x"], p["y"], p["font"], size, p["anchor"], p["tracking"]))] if t >= el["t0"] + 0.2 else []


@element("chip")
class Chip:
    @staticmethod
    def size(cx, p):
        """The text's size: 30, shrunk until the whole chip (its text and 84 pixels of padding) fits `max_width`."""
        return fitted(cx, [p["text"]], "med", 30, 5, (p["max_width"] - 84) if p.get("max_width") else None)

    @staticmethod
    def check(p):
        return [] if isinstance(p.get("text"), str) and isinstance(p.get("x"), (int, float)) and isinstance(p.get("y"), (int, float)) else ["text, x and y are required"]

    @staticmethod
    def texts(p):
        return [("med", p["text"])]

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        a = ease_out(prog(t, el["t0"], 0.5))
        if a <= 0:
            return
        x, y, text, dot = p["x"], p["y"], p["text"], p.get("dot", True)
        size = cls.size(cx, p)
        w = text_width(cx, text, "med", size, 5) + 84
        rrect(cx, layer, (x, y, x + w * a, y + 64), 32, fill=(8, 14, 22), outline=(255, 255, 255), width=2, alpha=0.78 * a)
        if a > 0.6:
            al = int(255 * (a - 0.6) / 0.4)
            d = ImageDraw.Draw(layer)
            if dot:
                r = 9 * cx.q
                d.ellipse(((x + 30) * cx.q - r, (y + 32) * cx.q - r, (x + 30) * cx.q + r, (y + 32) * cx.q + r), fill=(*rgb(p.get("accent"), BLUE), int(al * (0.55 + 0.45 * math.sin(t * 7)))))
            track_text(d, ((x + (52 if dot else 32)) * cx.q, (y + 12 + (30 - size) / 2) * cx.q), text, cx.font("med", size), (255, 255, 255, al), 5, "l", cx.q)

    @classmethod
    def boxes(cls, t, p, cx, el):
        if t < el["t0"] + 0.5:
            return []
        return [("chip", p["x"], p["y"], p["x"] + text_width(cx, p["text"], "med", cls.size(cx, p), 5) + 84, p["y"] + 64)]


@element("brackets")
class Brackets:
    @staticmethod
    def check(p):
        b = p.get("box")
        return [] if isinstance(b, list) and len(b) == 4 else ["box must be [x0, y0, x1, y1]"]

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        a = ease_out(prog(t, el["t0"], p.get("dur", 0.7)))
        if p.get("out") is not None:
            a *= 1 - smooth(prog(t, el["t0"] + p["out"], 0.4))
        if a <= 0:
            return
        x0, y0, x1, y1 = [v * cx.q for v in p["box"]]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ax, ay, bx, by = mx + (x0 - mx) * a, my + (y0 - my) * a, mx + (x1 - mx) * a, my + (y1 - my) * a
        tmp = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(tmp)
        col, arm, w = rgb(p.get("color"), WHITE), p.get("arm", 70) * cx.q, max(1, int(p.get("width", 5) * cx.q))
        for (px, py, sx, sy) in ((ax, ay, 1, 1), (bx, ay, -1, 1), (ax, by, 1, -1), (bx, by, -1, -1)):
            d.line((px, py, px + sx * arm, py), fill=(*col, int(235 * a)), width=w)
            d.line((px, py, px, py + sy * arm), fill=(*col, int(235 * a)), width=w)
        layer.alpha_composite(tmp)

    @classmethod
    def boxes(cls, t, p, cx, el):
        return [("~brackets", *p["box"])] if t >= el["t0"] + 0.3 else []


@element("scan")
class Scan:
    @staticmethod
    def check(p):
        b = p.get("box")
        return [] if isinstance(b, list) and len(b) == 4 else ["box must be [x0, y0, x1, y1]"]

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        t1 = el["t1"]
        if not (el["t0"] <= t <= t1):
            return
        fade = smooth(prog(t, el["t0"], 0.4)) * (1 - smooth(prog(t, t1 - 0.5, 0.5)))
        x0, y0, x1, y1 = [int(v * cx.q) for v in p["box"]]
        y = y0 + int((y1 - y0) * (((t - el["t0"]) / p.get("period", 2.0)) % 1.0))
        col = rgb(p.get("color"), BLUE)
        tmp = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(tmp)
        trail = int(190 * cx.q)
        for k in range(0, trail, 3):
            yy = y - k
            if y0 <= yy <= y1:
                d.line((x0, yy, x1, yy), fill=(*col, int(75 * (1 - k / trail) ** 2 * fade)), width=3)
        d.line((x0, y, x1, y), fill=(190, 230, 255, int(255 * fade)), width=max(2, int(4 * cx.q)))
        layer.alpha_composite(tmp)
        d = ImageDraw.Draw(layer)
        for k in range(17):
            yy = y0 + (y1 - y0) * k / 16
            ln = (26 if k % 4 == 0 else 14) * cx.q
            d.line((x0 - 8 * cx.q - ln, yy, x0 - 8 * cx.q, yy), fill=(255, 255, 255, int(190 * fade)), width=max(1, int(2 * cx.q)))

    @classmethod
    def boxes(cls, t, p, cx, el):
        x0, y0, x1, y1 = p["box"]
        return [("~scan", x0 - 8 - 26, y0, x1, y1)] if el["t0"] + 0.2 <= t <= el["t1"] else []


@element("callout")
class Callout:
    """A data label on a point of the picture (a HUD call-out): a dot with a ring at (x, y), a leader line that draws on (a short diagonal, then level) to a thin-bordered box holding a small
    `label` over a big `value` and its `unit`. `side` is the side of the point the box sits on, `len` the horizontal reach from the point to the box's near edge. The box is type for the layout check;
    the dot and the line are a decoration."""
    defaults = dict(unit="", side="right", len=300, draw=0.5, label_size=28, value_size=64, unit_size=30, pad=22, elbow=70, hold=None, accent=list(BLUE))

    @staticmethod
    def check(p):
        bad = [] if all(isinstance(p.get(k), (int, float)) for k in ("x", "y")) else ["x and y (the point) are required"]
        if not isinstance(p.get("label"), str) or not p["label"]:
            bad.append("label is required")
        if not (isinstance(p.get("value"), (str, int, float)) and not isinstance(p.get("value"), bool) and str(p["value"]).isprintable() and str(p["value"])):
            bad.append("value is required (a number or one line of text)")
        return bad

    @staticmethod
    def texts(p):
        return [("med", p["label"]), ("black", str(p["value"]))] + ([("med", p["unit"])] if p.get("unit") else [])

    @staticmethod
    def sizes(cx, p):
        """(label size, value size, unit size): as given, scaled down together until the box's text fits the room between the box's near edge and the canvas edge (never below 60 percent)."""
        ls, vs, us = p["label_size"], p["value_size"], p["unit_size"]
        room = (cx.w0 - (p["x"] + p["len"]) if p["side"] == "right" else p["x"] - p["len"]) - 2 * p["pad"] - 6
        w = max(text_width(cx, p["label"], "med", ls, 3), text_width(cx, str(p["value"]), "black", vs) + (text_width(cx, p["unit"], "med", us) + 10 if p["unit"] else 0))
        if room > 0 and w > room:
            k = max(0.6, room / w * 0.98)
            ls, vs, us = ls * k, vs * k, us * k
        return ls, vs, us

    @classmethod
    def geometry(cls, cx, p):
        """The polyline from the point to the box's near edge, and the box (x0, y0, x1, y1), in design pixels."""
        ls, vs, us = cls.sizes(cx, p)
        dr = 1 if p["side"] == "right" else -1
        w = max(text_width(cx, p["label"], "med", ls, 3), text_width(cx, str(p["value"]), "black", vs) + (text_width(cx, p["unit"], "med", us) + 10 if p["unit"] else 0)) + 2 * p["pad"]
        h = 2 * p["pad"] + ls * 1.3 + 6 + vs * 1.15
        el = min(p["elbow"], p["len"] * 0.5)
        pts = [(p["x"], p["y"]), (p["x"] + dr * el, p["y"] - el), (p["x"] + dr * p["len"], p["y"] - el)]
        ey = p["y"] - el
        edge = pts[-1][0]
        box = (edge, ey - h / 2, edge + w, ey + h / 2) if dr == 1 else (edge - w, ey - h / 2, edge, ey + h / 2)
        return pts, box, (ls, vs, us)

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        out = 1.0 if el["t1"] is None else 1 - smooth(prog(t, el["t1"] - 0.3, 0.3))
        dot = ease_out(prog(t, el["t0"], 0.25))
        if dot <= 0 or out <= 0:
            return
        pts, (bx0, by0, bx1, by1), (ls, vs, us) = cls.geometry(cx, p)
        q = cx.q
        col = rgb(p["accent"], BLUE)
        line = ease_out(prog(t, el["t0"] + 0.15, p["draw"]))
        box_a = smooth(prog(t, el["t0"] + 0.15 + p["draw"], 0.35)) * out
        tmp = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(tmp)
        x, y = pts[0]
        ring = 10 + 26 * ((t - el["t0"]) % 1.4) / 1.4                       # a ring that spreads and fades, a radar ping
        ra = int(150 * (1 - ((t - el["t0"]) % 1.4) / 1.4) * dot * out)
        d.ellipse(((x - ring) * q, (y - ring) * q, (x + ring) * q, (y + ring) * q), outline=(*col, ra), width=max(1, int(2 * q)))
        r = 8 * q
        d.ellipse((x * q - r, y * q - r, x * q + r, y * q + r), fill=(*col, int(255 * dot * out)))
        lens = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        left = line * sum(lens)
        a = (x * q, y * q)
        for (p0, p1), ln in zip(zip(pts, pts[1:]), lens):
            if left <= 0:
                break
            k = min(1.0, left / ln)
            b = ((p0[0] + (p1[0] - p0[0]) * k) * q, (p0[1] + (p1[1] - p0[1]) * k) * q)
            d.line((p0[0] * q, p0[1] * q, *b), fill=(255, 255, 255, int(235 * out)), width=max(1, int(2.5 * q)))
            left -= ln
        layer.alpha_composite(tmp)
        if box_a <= 0:
            return
        rrect(cx, layer, (bx0, by0, bx1, by1), 4, fill=(8, 18, 34), outline=(255, 255, 255), width=2, alpha=0.62 * box_a)
        tmp = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(tmp)
        arm, w = 16 * q, max(2, int(4 * q))
        for (px, py, sx, sy) in ((bx0, by0, 1, 1), (bx1, by0, -1, 1), (bx0, by1, 1, -1), (bx1, by1, -1, -1)):
            d.line((px * q, py * q, px * q + sx * arm, py * q), fill=(*col, int(255 * box_a)), width=w)
            d.line((px * q, py * q, px * q, py * q + sy * arm), fill=(*col, int(255 * box_a)), width=w)
        al = int(255 * box_a)
        tx = (bx0 + p["pad"]) * q
        track_text(d, (tx, (by0 + p["pad"]) * q), p["label"], cx.font("med", ls), (210, 228, 250, al), 3, "l", q, shadow=False)
        vy = (by0 + p["pad"] + ls * 1.3 + 6) * q
        wv = track_text(d, (tx, vy), str(p["value"]), cx.font("black", vs), (255, 255, 255, al), 0, "l", q, shadow=False)
        if p["unit"]:
            track_text(d, (tx + wv + 10 * q, vy + (vs - us) * 0.8 * q), p["unit"], cx.font("med", us), (*col, al), 0, "l", q, shadow=False)
        layer.alpha_composite(tmp)

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        pts, box, _ = cls.geometry(cx, p)
        if t < el["t0"] + 0.15 + p["draw"] + 0.17:
            return [("~callout", min(x for x, _ in pts) - 10, min(y for _, y in pts) - 10, max(x for x, _ in pts) + 10, max(y for _, y in pts) + 10)] if t >= el["t0"] + 0.1 else []
        return [("callout", *box), ("~callout-line", min(x for x, _ in pts) - 10, min(y for _, y in pts) - 10, max(x for x, _ in pts) + 10, max(y for _, y in pts) + 10)]


@element("counter")
class Counter:
    defaults = dict(size=300, fill=[255, 255, 255], hold=1.0, suffix="", suffix_scale=0.8, suffix_font=None)

    @staticmethod
    def check(p):
        return [] if all(isinstance(p.get(k), (int, float)) for k in ("x", "y", "target")) else ["x, y and target must be numbers"]

    @staticmethod
    def sizes(cx, p):
        """(the number's size, the suffix's size) in design pixels: as given, both scaled down together until the number and its suffix fit `max_width` (never below half)."""
        size, sfx = p["size"], p.get("suffix_size", p["size"])
        mw = p.get("max_width")
        if mw:
            w = text_width(cx, f"{p['target']:.0f}", "black", size) + (text_width(cx, p["suffix"], p.get("suffix_font") or "black", sfx) + 6 if p["suffix"] else 0)
            if w > mw:
                k = max(0.5, mw / w * 0.98)
                size, sfx = size * k, sfx * k
        return size, sfx

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        a = ease_out(prog(t, el["t0"], p["hold"]))
        shown = f"{p['target'] * a:.0f}"
        size, sfx_size = cls.sizes(cx, p)
        f = cx.font("black", size)
        d = ImageDraw.Draw(layer)
        al = int(255 * min(1.0, (t - el["t0"]) / 0.3)) if t >= el["t0"] else 0
        if al <= 0:
            return
        d.text((p["x"] * cx.q, p["y"] * cx.q), shown, font=f, fill=(*rgb(p["fill"], WHITE), al))
        pop = ease_out(prog(t, el["t0"] + p["hold"], 0.35))
        if p["suffix"] and pop > 0:
            wnum = d.textlength(shown, font=f)
            sz = sfx_size * (p["suffix_scale"] + (1 - p["suffix_scale"]) * pop)
            d.text((p["x"] * cx.q + wnum + 6 * cx.q, p["y"] * cx.q), p["suffix"], font=cx.font(p.get("suffix_font") or "black", sz), fill=(*rgb(p.get("accent"), BLUE), int(255 * pop)))

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        if t < el["t0"] + 0.3:
            return []
        size, sfx_size = cls.sizes(cx, p)
        shown = f"{p['target']:.0f}"
        w = text_width(cx, shown, "black", size) + (text_width(cx, p["suffix"], p.get("suffix_font") or "black", sfx_size) + 6 if p["suffix"] else 0)
        top, bottom = ink_rows(cx, "black", size, shown)
        if p["suffix"]:
            st, sb = ink_rows(cx, p.get("suffix_font") or "black", sfx_size, p["suffix"])
            top, bottom = min(top, st), max(bottom, sb)
        return [("counter", p["x"], p["y"] + top, p["x"] + w, p["y"] + bottom)]

    @staticmethod
    def texts(p):
        return [("black", f"{p['target']:.0f}")] + ([(p.get("suffix_font") or "black", p["suffix"])] if p.get("suffix") else [])


@element("steps")
class Steps:
    defaults = dict(x=100, top=500, step=190, gap=0.95, first=0.2, out=None, name_size=None, max_width=None)

    @staticmethod
    def name_size(cx, p, name):
        """The size an item's title is set at: `name_size`, else 66 (54 for a long one), and never wider than `max_width` (the room right of the number)."""
        base = p["name_size"] or (66 if len(name) < 20 else 54)
        return fitted(cx, [name], "black", base, -0.5, p["max_width"])

    @staticmethod
    def check(p):
        it = p.get("items")
        return [] if isinstance(it, list) and it and all(isinstance(i, list) and len(i) == 2 for i in it) else ["items must be a list of [number, title] pairs"]

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        items, x, top, step = p["items"], p["x"], p["top"], p["step"]
        t0 = el["t0"]
        d = ImageDraw.Draw(layer)
        span = step * (len(items) - 1) + 30
        leave = 1 - smooth(prog(t, t0 + p["out"], 0.5)) if p["out"] is not None else 1.0       # the rail leaves with the rows
        d.line((x * cx.q, top * cx.q, x * cx.q, (top + span) * cx.q), fill=(255, 255, 255, int(70 * smooth(prog(t, t0, 0.5)) * leave)), width=max(2, int(3 * cx.q)))
        full = p["gap"] * (len(items) - 1) + 0.6
        d.line((x * cx.q, top * cx.q, x * cx.q, (top + span * ease_out(prog(t, t0 + p["first"], full))) * cx.q), fill=(*BLUE, int(255 * leave)), width=max(3, int(5 * cx.q)))
        for i, (num, name) in enumerate(items):
            ti = t0 + p["first"] + i * p["gap"]
            a = ease_out(prog(t, ti, 0.5))
            a *= leave
            if a <= 0:
                continue
            y = top + i * step
            r = (16 + 6 * (1 - a)) * cx.q
            d.ellipse((x * cx.q - r, (y + 14) * cx.q - r, x * cx.q + r, (y + 14) * cx.q + r), fill=(*BLUE, int(255 * a)), outline=(255, 255, 255, int(255 * a)), width=max(2, int(3 * cx.q)))
            track_text(d, ((x + 56) * cx.q, (y - 22) * cx.q), str(num), cx.font("bold", 40), (*BLUE, int(255 * a)), 4, "l", cx.q)
            size = cls.name_size(cx, p, name)
            tmp = scratch(cx, "black", size)
            track_text(ImageDraw.Draw(tmp), ((x + 56) * cx.q, (1 - a) * 30 * cx.q + 6), name, cx.font("black", size), (255, 255, 255, int(255 * min(1.0, a * 1.4))), -0.5, "l", cx.q)
            paste_clipped(layer, tmp, int((y + 18 - 6) * cx.q))

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        out = []
        if p["out"] is not None and t >= el["t0"] + p["out"] + 0.5:                                  # the list has faded out
            return out
        for i, (num, name) in enumerate(p["items"]):
            if t >= el["t0"] + p["first"] + i * p["gap"] + 0.3:
                size = cls.name_size(cx, p, name)
                y = p["top"] + i * p["step"]
                nt, nb = ink_rows(cx, "bold", 40, str(num))
                tt, tb = ink_rows(cx, "black", size, name)
                out.append((f"step-dot:{num}", p["x"] - 18, y + 14 - 18, p["x"] + 18, y + 14 + 18))
                out.append((f"step-number:{num}", p["x"] + 56, y - 22 + nt, p["x"] + 56 + text_width(cx, str(num), "bold", 40, 4), y - 22 + nb))
                out.append((f"step:{name[:14]}", p["x"] + 56, y + 18 + tt, p["x"] + 56 + text_width(cx, name, "black", size, -0.5), y + 18 + tb))
        return out

    @staticmethod
    def texts(p):
        return [("bold", str(num)) for num, _ in p["items"]] + [("black", name) for _, name in p["items"]]


@element("rule")
class Rule:
    @staticmethod
    def check(p):
        return [] if all(isinstance(p.get(k), (int, float)) for k in ("x0", "x1", "y")) else ["x0, x1 and y must be numbers"]

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        a = ease_out(prog(t, el["t0"], p.get("dur", 0.6)))
        if a <= 0:
            return
        th = p.get("thickness", 6)
        if p.get("grow") == "left":                       # from x0 to the right
            x0, x1 = p["x0"], p["x0"] + (p["x1"] - p["x0"]) * a
        else:                                             # from the middle out
            mid, half = (p["x0"] + p["x1"]) / 2, (p["x1"] - p["x0"]) / 2 * a
            x0, x1 = mid - half, mid + half
        rrect(cx, layer, (x0, p["y"], x1, p["y"] + th), th / 2, fill=rgb(p.get("color"), BLUE))

    @classmethod
    def boxes(cls, t, p, cx, el):
        if t < el["t0"] + p.get("dur", 0.6) * 0.5:
            return []
        x0, x1 = min(p["x0"], p["x1"]), max(p["x0"], p["x1"])
        return [("~rule", x0, p["y"], x1, p["y"] + p.get("thickness", 6))]


@element("logo")
class Logo:
    defaults = dict(width=300, opacity=0.95, fade_in=0.6, fade_out=0.5, rise=0, align="l")

    @staticmethod
    def check(p):
        return [] if isinstance(p.get("asset"), str) and isinstance(p.get("x"), (int, float)) and isinstance(p.get("y"), (int, float)) else ["asset, x and y are required"]

    @staticmethod
    def size(cx, p):
        """(width, height) in design pixels: `width`, or less when `max_height` would be passed (a square mark is not as wide as a wordmark)."""
        key = ("logo-dims", p["asset"])
        if key not in cx.cache:
            with Image.open(cx.assets[p["asset"]]) as im:
                cx.cache[key] = im.size
        iw, ih = cx.cache[key]
        w = p["width"]
        if p.get("max_height") and w * ih / iw > p["max_height"]:
            w = p["max_height"] * iw / ih
        return w, w * ih / iw

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        a = ease_out(prog(t, el["t0"], p["fade_in"])) * (1 - smooth(prog(t, el["t1"] - p["fade_out"], p["fade_out"])))
        if a <= 0:
            return
        width, _ = cls.size(cx, p)
        key = ("logo", p["asset"], round(width, 2), cx.q)
        if key not in cx.cache:
            im = Image.open(cx.assets[p["asset"]]).convert("RGBA")
            w = max(1, int(width * cx.q))
            cx.cache[key] = im.resize((w, max(1, int(im.height * w / im.width))), Image.LANCZOS)
        lg = cx.cache[key].copy()
        lg.putalpha(lg.getchannel("A").point(lambda v: int(v * a * p["opacity"])))
        x = p["x"] - (width / 2 if p["align"] == "m" else 0)
        layer.alpha_composite(lg, (int(x * cx.q), int((p["y"] - p["rise"] * (1 - a)) * cx.q)))

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        if t < el["t0"] + p["fade_in"] * 0.5 or t >= el["t1"] - p["fade_out"]:
            return []
        w, h = cls.size(cx, p)
        x = p["x"] - (w / 2 if p["align"] == "m" else 0)
        return [(f"logo:{p['asset']}", x, p["y"], x + w, p["y"] + h)]


# ---- serif display type: a word or number set on its own strip with a soft shadow, then moved, leaned and echoed as a picture
CREAM = (245, 236, 214)


def sprite(cx: Ctx, text: str, kind: str, size: float, fill, tracking: float = 0.0, shadow: float = 0.6) -> tuple[Image.Image, int, int, int]:
    """`text` on a transparent strip with a blurred drop shadow: (the picture, the margin, the width in pixels, the face's ink rows middle). The text's origin (where `draw` puts `x`, `y`)
    is at (margin, margin) in the picture. Cached by what it is made of."""
    key = ("sprite", text, kind, int(round(size * cx.q)), tuple(fill), tracking, round(shadow, 3), cx.q)
    if key in cx.cache:
        return cx.cache[key]
    f = cx.font(kind, size)
    px = size * cx.q
    m = int(px * 0.4) + 6
    w = int(sum(ImageDraw.Draw(Image.new("L", (4, 4))).textlength(ch, font=f) + tracking * cx.q for ch in text) - tracking * cx.q) + 1
    asc, desc = f.getmetrics()
    _, top, _, bottom = f.getbbox(text or " ", anchor="la")
    img = Image.new("RGBA", (w + 2 * m, asc + desc + 2 * m), (0, 0, 0, 0))
    if shadow > 0:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        track_text(ImageDraw.Draw(sh), (m + px * 0.03, m + px * 0.06), text, f, (0, 0, 0, int(255 * shadow)), tracking, "l", cx.q, shadow=False)
        a = sh.getchannel("A").filter(ImageFilter.GaussianBlur(max(1.0, px * 0.05)))
        sh.putalpha(a)
        img.alpha_composite(sh)
    track_text(ImageDraw.Draw(img), (m, m), text, f, (*fill, 255), tracking, "l", cx.q, shadow=False)
    cx.cache[key] = (img, m, w, m + (top + bottom) // 2)
    return cx.cache[key]


def faded(im: Image.Image, k: float) -> Image.Image:
    """`im` with its opacity times `k`."""
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, min(1.0, k)))))
    return out


def paste_rgba(layer: Image.Image, im: Image.Image, x: float, y: float) -> None:
    """Composite `im` with its top left at (x, y), clipped to the layer (a sprite is allowed to be half off the picture)."""
    x, y = int(round(x)), int(round(y))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(layer.width, x + im.width), min(layer.height, y + im.height)
    if x1 > x0 and y1 > y0:
        layer.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


@element("kinetic")
class Kinetic:
    """`text` enters from the `dir` edge in `sweep` seconds with an echo and a lean, rests big at `at` for `hold`, then in `settle` seconds shrinks and moves to `to` and stays. Positions are
    the middle of the line ({x, y}; `to.anchor` l or r makes x its left or right end); `at` defaults to the middle of the canvas, a little above it."""
    defaults = dict(font="serif", size=240, fill=list(CREAM), dir="left", sweep=0.4, hold=0.45, settle=0.45, shadow=0.6, tracking=0.0, max_width=None)

    @staticmethod
    def check(p):
        out = []
        if not isinstance(p.get("text"), str) or not p["text"]:
            out.append("text is required")
        to = p.get("to")
        if not (isinstance(to, dict) and all(isinstance(to.get(k), (int, float)) and not isinstance(to.get(k), bool) for k in ("x", "y", "size")) and 1 <= to["size"] <= 2000
                and to.get("anchor", "m") in ANCHORS_ALL and set(to) <= {"x", "y", "size", "anchor"}):
            out.append("to must be {x, y, size} (and optionally anchor l, m or r): where the line settles")
        at = p.get("at")
        if at is not None and not (isinstance(at, dict) and set(at) <= {"x", "y"} and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in at.values())):
            out.append("at must be {x, y}: the middle of the big word")
        return out

    @staticmethod
    def texts(p):
        return [(p.get("font", "serif"), p["text"])]

    @classmethod
    def sizes(cls, cx, p):
        """(the big size, the settled size) in design pixels, each shrunk to fit `max_width`."""
        return (fitted(cx, [p["text"]], p["font"], p["size"], p["tracking"], p["max_width"]), fitted(cx, [p["text"]], p["font"], p["to"]["size"], p["tracking"], p["max_width"]))

    @classmethod
    def state(cls, t, p, cx, el):
        """(size, middle x, middle y, how far through the sweep 0 to 1) at `t`, in design pixels; the position before the sweep is on its edge."""
        big, small = cls.sizes(cx, p)
        at, to = p.get("at") or {}, p["to"]
        ax, ay = at.get("x", cx.w0 / 2), at.get("y", cx.h0 * 0.4)
        w_to = text_width(cx, p["text"], p["font"], small, p["tracking"])
        tx = to["x"] + {"l": w_to / 2, "m": 0, "r": -w_to / 2}[to.get("anchor", "m")]
        t1 = el["t0"] + p["sweep"] + p["hold"]
        s = smooth(prog(t, t1, p["settle"]))
        u = prog(t, el["t0"], p["sweep"])
        w_big = text_width(cx, p["text"], p["font"], big, p["tracking"])
        top, bottom = ink_rows(cx, p["font"], big, p["text"])
        edge = {"left": (-w_big / 2 - 40, ay), "right": (cx.w0 + w_big / 2 + 40, ay), "top": (ax, -(bottom - top) / 2 - 40), "bottom": (ax, cx.h0 + (bottom - top) / 2 + 40)}[p["dir"]]
        k = ease_out(u)
        x, y = edge[0] + (ax - edge[0]) * k, edge[1] + (ay - edge[1]) * k
        return big + (small - big) * s, x + (tx - x) * s, y + (to["y"] - y) * s, u, edge

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        if t < el["t0"]:
            return
        size, x, y, u, edge = cls.state(t, p, cx, el)
        fill = rgb(p["fill"], CREAM)
        spr, m, w, mid = sprite(cx, p["text"], p["font"], size, fill, p["tracking"], p["shadow"])
        q = cx.q
        vx, vy = (x - edge[0]), (y - edge[1])                      # where it has come from: the echo trails back toward the edge
        speed = (1 - u) ** 2 if u < 1 else 0.0                     # the ease's speed: all of the echo at the start, none on arrival
        if speed > 0.01:
            lean = {"left": 1, "right": -1}.get(p["dir"], 0) * 0.32 * speed
            norm = max(1.0, math.hypot(vx, vy))
            reach = min(norm, 0.4 * max(cx.w0, cx.h0)) * speed
            body = spr.transform(spr.size, Image.AFFINE, (1, lean, -lean * spr.height / 2, 0, 1, 0), Image.BICUBIC) if lean else spr
            n = 6
            for j in range(n, -1, -1):
                ox, oy = -vx / norm * reach * j / n, -vy / norm * reach * j / n
                paste_rgba(layer, faded(body, min(1.0, u * 3) * (1.0 if j == 0 else 0.5 * (1 - j / (n + 1)))), (x + ox) * q - m - w / 2, (y + oy) * q - mid)
        else:
            paste_rgba(layer, faded(spr, min(1.0, u * 3)), x * q - m - w / 2, y * q - mid)

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        if t < el["t0"] + p["sweep"] + 0.05:                       # while it is still coming in, it is not yet anywhere
            return []
        size, x, y, _, _ = cls.state(t, p, cx, el)
        w = text_width(cx, p["text"], p["font"], size, p["tracking"])
        top, bottom = ink_rows(cx, p["font"], size, p["text"])
        h = bottom - top
        return [("kinetic", x - w / 2, y - h / 2, x + w / 2, y + h / 2)]


ANCHORS_ALL = ("l", "m", "r")


@element("year")
class Year:
    defaults = dict(font="serif", size=220, fill=list(CREAM), anchor="l", tracking=0.0, rise=180, dur=0.8, hold=None, out_dur=0.5, shadow=0.6, max_width=None)

    @staticmethod
    def check(p):
        return ([] if isinstance(p.get("text"), str) and p["text"] and isinstance(p.get("x"), (int, float)) and isinstance(p.get("y"), (int, float)) else ["text, x and y are required"]) + anchor_problems(p)

    @staticmethod
    def texts(p):
        return [(p.get("font", "serif"), p["text"])]

    @classmethod
    def alpha(cls, t, p, el):
        a = ease_out(prog(t, el["t0"], p["dur"]))
        if p["hold"] is not None:
            a *= 1 - smooth(prog(t, el["t0"] + p["dur"] + p["hold"], p["out_dur"]))
        return a

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        a = cls.alpha(t, p, el)
        if a <= 0.001:
            return
        size = fitted(cx, [p["text"]], p["font"], p["size"], p["tracking"], p["max_width"])
        spr, m, w, _ = sprite(cx, p["text"], p["font"], size, rgb(p["fill"], CREAM), p["tracking"], p["shadow"])
        rise = p["rise"] * (1 - ease_out(prog(t, el["t0"], p["dur"])))
        x0 = p["x"] * cx.q - {"l": 0, "m": w / 2, "r": w}[p["anchor"]]
        paste_rgba(layer, faded(spr, a * 1.3), x0 - m, (p["y"] + rise) * cx.q - m)

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        if t < el["t0"] + p["dur"] * 0.5 or (p["hold"] is not None and t >= el["t0"] + p["dur"] + p["hold"] + p["out_dur"]):
            return []
        size = fitted(cx, [p["text"]], p["font"], p["size"], p["tracking"], p["max_width"])
        return [("year", *line_box(cx, p["text"], p["x"], p["y"], p["font"], size, p["anchor"], p["tracking"]))]
