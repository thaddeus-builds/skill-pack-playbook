"""The presenter cutout (a shot's `cutout`): the picture behind a subject is the same frame enlarged, blurred and tinted into a flat, soft backdrop; the subject, cut out by a matte, stays
sharp on top; and a dashed outline follows the matte's edge, its dashes marching along it as the film plays.

    "cutout": {"matte": "matte_asset", "outline": {"color": [255, 255, 255], "width": 6, "dash": [38, 24], "speed": 140, "offset": 4},
               "bg": {"zoom": 1.8, "blur": 40, "tint": [150, 200, 255], "tint_mix": 0.45, "posterize": 6}}

filmkit makes no matte: it is an input, a grayscale video, image sequence (asset type `frames`) or picture whose white is the subject, as big as the shot's clip and in step with it,
made by whatever segmented the footage. Only numpy, scipy.ndimage and Pillow are used: the outline is the outer edge of the thresholded matte, walked once round (Moore tracing) so the
dashes can be laid along it."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

OUTLINE = dict(color=[255, 255, 255], width=6, dash=[38, 24], speed=140.0, offset=4.0)
BG = dict(zoom=1.8, blur=40.0, tint=None, tint_mix=0.45, posterize=None, dx=0.0, dy=0.0)
KEYS = {"matte", "outline", "bg", "fg", "echo"}
FG_KEYS = {"scale", "dx", "dy"}
ECHO_KEYS = {"n", "dx", "alpha", "dur"}
OUTLINE_KEYS = set(OUTLINE)
BG_KEYS = set(BG)
MIN_AREA = 0.002                          # a blob smaller than this share of the picture is noise, not a subject
CLOCKWISE = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def settings(c: dict) -> tuple[dict, dict]:
    """(outline, bg) with the defaults in; `outline: false` leaves the outline out (None)."""
    ol = c.get("outline", {})
    return (None if ol is False else {**OUTLINE, **ol}), {**BG, **(c.get("bg") or {})}


def backdrop(small: Image.Image, bg: dict, q: float, size: tuple[int, int]) -> np.ndarray:
    """The enlarged crop `small` (made at a quarter size when the blur is wide, which costs nothing a blur would have kept) blurred, tinted and posterised, brought up to `size`."""
    sc = small.width / size[0]
    im = small.filter(ImageFilter.GaussianBlur(max(0.0, bg["blur"] * q * sc))) if bg["blur"] else small
    a = np.asarray(im.resize(size, Image.BICUBIC) if im.size != size else im, dtype=np.float32)
    if bg["tint"] is not None:
        a = a * (1 - bg["tint_mix"]) + np.array(bg["tint"][:3], np.float32) * bg["tint_mix"]
    if bg["posterize"]:
        n = bg["posterize"] - 1
        a = np.round(a / 255.0 * n) / n * 255.0
    return a


def place(fg: np.ndarray, matte: np.ndarray, p: dict, W: int, H: int) -> tuple[np.ndarray, np.ndarray]:
    """The subject layer (its picture and its matte) scaled by `scale` about the middle of the bottom edge, then moved `dx` of the width and `dy` of the height: the subject smaller and off
    to one side of where the clip had it, so the enlarged backdrop behind it is a second, bigger figure. Outside the moved picture the matte is black."""
    sc = float(p.get("scale", 1.0))
    w, h = max(2, int(round(W * sc))), max(2, int(round(H * sc)))
    x0, y0 = int(round(W / 2 - w / 2 + p.get("dx", 0.0) * W)), int(round(H - h + p.get("dy", 0.0) * H))
    out_fg, out_m = np.zeros((H, W, 3), np.float32), np.zeros((H, W), np.uint8)
    f = np.asarray(Image.fromarray(np.clip(fg, 0, 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), dtype=np.float32)
    m = np.asarray(Image.fromarray(matte).resize((w, h), Image.BILINEAR), dtype=np.uint8)
    sx0, sy0 = max(0, -x0), max(0, -y0)
    dx0, dy0 = max(0, x0), max(0, y0)
    cw, ch = min(w - sx0, W - dx0), min(h - sy0, H - dy0)
    if cw > 0 and ch > 0:
        out_fg[dy0:dy0 + ch, dx0:dx0 + cw] = f[sy0:sy0 + ch, sx0:sx0 + cw]
        out_m[dy0:dy0 + ch, dx0:dx0 + cw] = m[sy0:sy0 + ch, sx0:sx0 + cw]
    return out_fg, out_m


def echo(back: np.ndarray, fg: np.ndarray, matte: np.ndarray, e: dict, t: float, q: float) -> np.ndarray:
    """Ghosts of the subject trailing behind it for `dur` seconds from the start of the shot (a whip in): `n` copies, each `dx` pixels further along x, fainter the further they are, all
    fading out as the time runs. Drawn on the backdrop, under the subject."""
    dur = float(e.get("dur", 0.35))
    if t >= dur:
        return back
    u = t / dur
    out = back.copy()
    n, dx, al = int(e.get("n", 3)), float(e.get("dx", -70.0)) * q, float(e.get("alpha", 0.5))
    for k in range(n, 0, -1):
        sh = int(round(dx * k * (1 - u)))
        f, m = np.roll(fg, sh, axis=1), np.roll(matte, sh, axis=1)
        if sh > 0:
            f[:, :sh], m[:, :sh] = 0, 0
        elif sh < 0:
            f[:, sh:], m[:, sh:] = 0, 0
        a = (m.astype(np.float32) / 255.0 * al * (1 - k / (n + 1)) * (1 - u))[..., None]
        out = out * (1 - a) + f * a
    return out


def trace(mask: np.ndarray) -> list[tuple[int, int]]:
    """The outer edge of the blob `mask` (bool, one 8-connected piece) as (row, column) steps, clockwise, from its topmost left pixel (Moore tracing: stable from frame to frame, so a dash
    pattern laid from the start does not jump)."""
    pad = np.pad(mask, 1)
    ys, xs = np.nonzero(pad)
    if not len(ys):
        return []
    start = (int(ys[0]), int(xs[0]))
    cur, back = start, 6
    pts = [start]
    limit = 4 * int(mask.sum()) + 8
    while len(pts) < limit:
        for k in range(1, 9):
            d = (back + k) % 8
            ny, nx = cur[0] + CLOCKWISE[d][0], cur[1] + CLOCKWISE[d][1]
            if pad[ny, nx]:
                py, px = cur[0] + CLOCKWISE[(d - 1) % 8][0], cur[1] + CLOCKWISE[(d - 1) % 8][1]
                cur, back = (ny, nx), CLOCKWISE.index((py - ny, px - nx))
                break
        else:
            break                                                    # a single pixel
        if cur == start and len(pts) > 2:
            break
        pts.append(cur)
    return [(y - 1, x - 1) for y, x in pts]


def contours(mask: np.ndarray) -> list[np.ndarray]:
    """The closed outlines (N x 2 arrays of x, y) of the pieces of `mask` big enough to be a subject, largest first, three at most."""
    lab, n = ndimage.label(mask, structure=np.ones((3, 3), int))
    if n == 0:
        return []
    area = np.bincount(lab.ravel(), minlength=n + 1)[1:]
    boxes = ndimage.find_objects(lab)
    out = []
    for idx in np.argsort(-area)[:3]:
        if area[idx] < MIN_AREA * mask.size:
            break
        sl = boxes[idx]
        pts = trace(lab[sl] == idx + 1)
        if len(pts) > 8:
            a = np.array(pts, np.float64)[:, ::-1] + [sl[1].start, sl[0].start]
            out.append(a)
    return out


def smoothed(pts: np.ndarray, k: int) -> np.ndarray:
    """A closed outline with the staircase of the pixel grid averaged out over `k` neighbours each side."""
    k = max(1, min(k, len(pts) // 4))
    ker = np.ones(2 * k + 1) / (2 * k + 1)
    ext = np.concatenate([pts[-k:], pts, pts[:k]])
    return np.stack([np.convolve(ext[:, c], ker, mode="valid") for c in (0, 1)], axis=1)


def outward(pts: np.ndarray, offset: float) -> np.ndarray:
    """`pts` moved `offset` pixels out along the normal (in, when negative)."""
    if not offset:
        return pts
    tan = np.roll(pts, -3, axis=0) - np.roll(pts, 3, axis=0)
    norm = np.stack([tan[:, 1], -tan[:, 0]], axis=1)                 # the right-hand normal of the path (x, y)
    norm /= np.maximum(np.linalg.norm(norm, axis=1, keepdims=True), 1e-6)
    area = 0.5 * np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1])
    return pts + norm * offset * (1.0 if area > 0 else -1.0)         # (the sign of the shoelace area says which way round it was walked, so which normal points out)


def dashes(pts: np.ndarray, on: float, off: float, phase: float) -> list[np.ndarray]:
    """The runs of `pts` (a closed outline) that are on in a pattern of `on` pixels on and `off` off, the pattern slid `phase` pixels along."""
    step = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    s = np.cumsum(step) - step / 2
    lit = ((s - phase) % (on + off)) < on
    runs, i, n = [], 0, len(pts)
    while i < n:
        if lit[i]:
            j = i
            while j + 1 < n and lit[j + 1]:
                j += 1
            runs.append(pts[i:min(n, j + 2)])
            i = j + 1
        else:
            i += 1
    return runs


def draw_outline(out: np.ndarray, outlines: list[np.ndarray], ol: dict, t: float, q: float) -> None:
    """Draw the dashed outline into `out` (float RGB, in place), antialiased by drawing at twice the size inside the subject's own box."""
    w = max(1.0, ol["width"] * q)
    on, off = ol["dash"][0] * q, ol["dash"][1] * q
    for pts in outlines:
        pts = outward(smoothed(pts, max(3, len(pts) // 250)), ol["offset"] * q)
        pad = int(w + 6)
        x0, y0 = np.floor(pts.min(axis=0)).astype(int) - pad
        x1, y1 = np.ceil(pts.max(axis=0)).astype(int) + pad
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(out.shape[1], x1), min(out.shape[0], y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        m = Image.new("L", (2 * (x1 - x0), 2 * (y1 - y0)), 0)
        d = ImageDraw.Draw(m)
        for run in dashes(pts, on, off, ol["speed"] * q * t):
            if len(run) > 1:
                d.line([((x - x0) * 2, (y - y0) * 2) for x, y in run], fill=255, width=max(2, int(round(w * 2))), joint="curve")
        a = np.asarray(m.resize((x1 - x0, y1 - y0), Image.BOX), dtype=np.float32)[..., None] / 255.0
        col = np.array(ol["color"][:3], np.float32)
        out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1 - a) + col * a


def compose(fg: np.ndarray, back: np.ndarray, matte: np.ndarray, c: dict, t: float, q: float) -> np.ndarray:
    """The frame: `back` where the matte is black, `fg` where it is white, the dashed outline on the edge. `fg` and `back` are float RGB, `matte` gray (uint8), all the same size; `t` is
    seconds into the shot (the dashes march with it)."""
    ol, _ = settings(c)
    out = back.copy()
    rows, cols = np.nonzero(matte.max(axis=1) > 0)[0], np.nonzero(matte.max(axis=0) > 0)[0]
    if len(rows) and len(cols):                                      # the subject's own box is all that differs from the backdrop
        box = (slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1))
        a = np.clip((matte[box].astype(np.float32) / 255.0 - 0.35) / 0.3, 0, 1)[..., None]
        out[box] = back[box] * (1 - a) + fg[box] * a
    if ol is not None:
        draw_outline(out, contours(matte >= 128), ol, t, q)
    return out
