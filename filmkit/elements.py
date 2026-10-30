"""The graphics layer: animated elements, each a small function of time. A spec lists them as {element, t0, t1, ...params}; coordinates and sizes are design pixels of the spec's canvas, times
inside an element are seconds after its `t0` (so moving an element in time moves all of it). Every element has three parts: `check` (what is wrong with its params), `draw` (a frame of it on
an RGBA layer) and `boxes` (where its type sits at a time, in design pixels: the layout check reads these to find a line off the safe area or two lines on each other).

    title    lines of type that rise and fade in one after another (a mask reveal), optionally out again; `max_width` shrinks the size until the widest line fits
    text     one tracked line that fades in (a tagline, a small label)
    chip     a rounded label with a pulsing dot (a section tag)
    brackets four corner brackets that grow out from the centre of a box
    scan     a sweeping line with a trail and a measuring rule on the edge of a box
    counter  a number that counts up to a target, then a suffix (its own size: `suffix_size`) that pops
    steps    a vertical progress line with numbered items that appear in turn (`name_size`; `max_width`: the items' titles shrink to fit it)
    rule     a line that grows from its centre (or from its left end: `grow`: "left")
    logo     the brand's mark, faded in and out
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

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


def track_text(d, xy, text, f, fill, tracking=0.0, anchor="l", q=1.0, shadow=True):
    """`text` one character at a time with `tracking` pixels between, from `xy` (anchor l, m or r). Returns its width. A shadow sits under type that has an alpha."""
    x, y = xy
    widths = [d.textlength(ch, font=f) + tracking * q for ch in text]
    total = sum(widths) - tracking * q
    if anchor == "m":
        x -= total / 2
    elif anchor == "r":
        x -= total
    for ch, w in zip(text, widths):
        if shadow and len(fill) == 4:
            d.text((x + 1.5 * q, y + 3.5 * q), ch, font=f, fill=(0, 0, 0, int(fill[3] * 0.55)))
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
    still does not fit is for the layout check to name). No `max_width`: `size`."""
    if not max_width:
        return size
    widest = max(text_width(cx, t, kind, size, tracking) for t in texts)
    if widest <= max_width:
        return size
    return max(size * floor, size * max_width / widest * 0.995)


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


def line_box(cx, text, x, y, kind, size, lead, anchor, tracking):
    w = text_width(cx, text, kind, size, tracking)
    x0 = x if anchor == "l" else (x - w / 2 if anchor == "m" else x - w)
    return (x0, y, x0 + w, y + size * lead)


@element("title")
class Title:
    defaults = dict(font="black", size=96, fill=[255, 255, 255], anchor="l", tracking=0.0, stagger=0.14, dur=0.55, rise=46, lead=1.12, out=None, out_dur=0.35)

    @staticmethod
    def check(p):
        out = []
        if not isinstance(p.get("lines"), list) or not p["lines"] or not all(isinstance(x, str) for x in p["lines"]):
            out.append("lines must be a list of strings")
        for k in ("x", "y"):
            if not isinstance(p.get(k), (int, float)):
                out.append(f"{k} must be a number")
        return out

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        t0 = el["t0"]
        fill = rgb(p["fill"], WHITE)
        for i, line in enumerate(p["lines"]):
            a = ease_out(prog(t, t0 + i * p["stagger"], p["dur"]))
            if p["out"] is not None:
                a *= 1 - smooth(prog(t, t0 + p["out"] + i * 0.05, p["out_dur"]))
            if a <= 0.001:
                continue
            size, lead = fitted(cx, p["lines"], p["font"], p["size"], p["tracking"], p.get("max_width")), p["lead"]
            ly = p["y"] + i * size * lead
            tmp = Image.new("RGBA", (cx.W, int(size * lead * cx.q) + 12), (0, 0, 0, 0))
            d = ImageDraw.Draw(tmp)
            yy = (1 - a) * p["rise"] * cx.q + 6
            track_text(d, (p["x"] * cx.q, yy), line, cx.font(p["font"], size), (*fill, int(255 * min(1.0, a * 1.4))), p["tracking"], p["anchor"], cx.q)
            paste_clipped(layer, tmp, int((ly - 6) * cx.q))

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        if t < el["t0"]:
            return []
        out = []
        size = fitted(cx, p["lines"], p["font"], p["size"], p["tracking"], p.get("max_width"))
        for i, line in enumerate(p["lines"]):
            if t >= el["t0"] + i * p["stagger"] + 0.2:
                out.append((f"title:{line[:18]}", *line_box(cx, line, p["x"], p["y"] + i * size * p["lead"], p["font"], size, 1.0, p["anchor"], p["tracking"])))
        return out


@element("text")
class Text:
    defaults = dict(font="med", size=36, fill=[255, 255, 255], anchor="l", tracking=0.0, dur=0.6, alpha=0.92)

    @staticmethod
    def check(p):
        return [] if isinstance(p.get("text"), str) and isinstance(p.get("x"), (int, float)) and isinstance(p.get("y"), (int, float)) else ["text, x and y are required"]

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        a = ease_out(prog(t, el["t0"], p["dur"]))
        if a <= 0:
            return
        d = ImageDraw.Draw(layer)
        track_text(d, (p["x"] * cx.q, p["y"] * cx.q), p["text"], cx.font(p["font"], p["size"]), (*rgb(p["fill"], WHITE), int(255 * p["alpha"] * a)), p["tracking"], p["anchor"], cx.q)

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        return [("text", *line_box(cx, p["text"], p["x"], p["y"], p["font"], p["size"], 1.0, p["anchor"], p["tracking"]))] if t >= el["t0"] + 0.2 else []


@element("chip")
class Chip:
    @staticmethod
    def check(p):
        return [] if isinstance(p.get("text"), str) and isinstance(p.get("x"), (int, float)) and isinstance(p.get("y"), (int, float)) else ["text, x and y are required"]

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        a = ease_out(prog(t, el["t0"], 0.5))
        if a <= 0:
            return
        x, y, text, dot = p["x"], p["y"], p["text"], p.get("dot", True)
        w = text_width(cx, text, "med", 30, 5) + 84
        rrect(cx, layer, (x, y, x + w * a, y + 64), 32, fill=(8, 14, 22), outline=(255, 255, 255), width=2, alpha=0.78 * a)
        if a > 0.6:
            al = int(255 * (a - 0.6) / 0.4)
            d = ImageDraw.Draw(layer)
            if dot:
                r = 9 * cx.q
                d.ellipse(((x + 30) * cx.q - r, (y + 32) * cx.q - r, (x + 30) * cx.q + r, (y + 32) * cx.q + r), fill=(*rgb(p.get("accent"), BLUE), int(al * (0.55 + 0.45 * math.sin(t * 7)))))
            track_text(d, ((x + (52 if dot else 32)) * cx.q, (y + 12) * cx.q), text, cx.font("med", 30), (255, 255, 255, al), 5, "l", cx.q)

    @classmethod
    def boxes(cls, t, p, cx, el):
        if t < el["t0"] + 0.5:
            return []
        return [("chip", p["x"], p["y"], p["x"] + text_width(cx, p["text"], "med", 30, 5) + 84, p["y"] + 64)]


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
        return []


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
        return []


@element("counter")
class Counter:
    defaults = dict(size=300, fill=[255, 255, 255], hold=1.0, suffix="", suffix_scale=0.8, suffix_font=None)

    @staticmethod
    def check(p):
        return [] if all(isinstance(p.get(k), (int, float)) for k in ("x", "y", "target")) else ["x, y and target must be numbers"]

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        a = ease_out(prog(t, el["t0"], p["hold"]))
        shown = f"{p['target'] * a:.0f}"
        f = cx.font("black", p["size"])
        d = ImageDraw.Draw(layer)
        al = int(255 * min(1.0, (t - el["t0"]) / 0.3)) if t >= el["t0"] else 0
        if al <= 0:
            return
        d.text((p["x"] * cx.q, p["y"] * cx.q), shown, font=f, fill=(*rgb(p["fill"], WHITE), al))
        pop = ease_out(prog(t, el["t0"] + p["hold"], 0.35))
        if p["suffix"] and pop > 0:
            wnum = d.textlength(shown, font=f)
            sz = p.get("suffix_size", p["size"]) * (p["suffix_scale"] + (1 - p["suffix_scale"]) * pop)
            d.text((p["x"] * cx.q + wnum + 6 * cx.q, p["y"] * cx.q), p["suffix"], font=cx.font(p.get("suffix_font") or "black", sz), fill=(*rgb(p.get("accent"), BLUE), int(255 * pop)))

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        if t < el["t0"] + 0.3:
            return []
        w = text_width(cx, f"{p['target']:.0f}", "black", p["size"]) + (text_width(cx, p["suffix"], p.get("suffix_font") or "black", p["size"]) + 6 if p["suffix"] else 0)
        return [("counter", p["x"], p["y"] + p["size"] * 0.12, p["x"] + w, p["y"] + p["size"] * 0.95)]


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
            tmp = Image.new("RGBA", (cx.W, int(size * 1.12 * cx.q) + 12), (0, 0, 0, 0))
            track_text(ImageDraw.Draw(tmp), ((x + 56) * cx.q, (1 - a) * 30 * cx.q + 6), name, cx.font("black", size), (255, 255, 255, int(255 * min(1.0, a * 1.4))), -0.5, "l", cx.q)
            paste_clipped(layer, tmp, int((y + 18 - 6) * cx.q))

    @classmethod
    def boxes(cls, t, p, cx, el):
        p = {**cls.defaults, **p}
        out = []
        for i, (num, name) in enumerate(p["items"]):
            if t >= el["t0"] + p["first"] + i * p["gap"] + 0.3:
                size = cls.name_size(cx, p, name)
                out.append((f"step:{name[:14]}", p["x"] + 56, p["top"] + i * p["step"] + 18, p["x"] + 56 + text_width(cx, name, "black", size, -0.5), p["top"] + i * p["step"] + 18 + size))
        return out


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
        return []


@element("logo")
class Logo:
    defaults = dict(width=300, opacity=0.95, fade_in=0.6, fade_out=0.5, rise=0, align="l")

    @staticmethod
    def check(p):
        return [] if isinstance(p.get("asset"), str) and isinstance(p.get("x"), (int, float)) and isinstance(p.get("y"), (int, float)) else ["asset, x and y are required"]

    @classmethod
    def draw(cls, layer, t, p, cx, el):
        p = {**cls.defaults, **p}
        a = ease_out(prog(t, el["t0"], p["fade_in"])) * (1 - smooth(prog(t, el["t1"] - p["fade_out"], p["fade_out"])))
        if a <= 0:
            return
        key = ("logo", p["asset"], p["width"], cx.q)
        if key not in cx.cache:
            im = Image.open(cx.assets[p["asset"]]).convert("RGBA")
            w = int(p["width"] * cx.q)
            cx.cache[key] = im.resize((w, max(1, int(im.height * w / im.width))), Image.LANCZOS)
        lg = cx.cache[key].copy()
        lg.putalpha(lg.getchannel("A").point(lambda v: int(v * a * p["opacity"])))
        x = p["x"] - (p["width"] / 2 if p["align"] == "m" else 0)
        layer.alpha_composite(lg, (int(x * cx.q), int((p["y"] - p["rise"] * (1 - a)) * cx.q)))

    @classmethod
    def boxes(cls, t, p, cx, el):
        return []
