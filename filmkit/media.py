"""Shots: a video segment or a still, with a camera move (a zoom and a pan that ease), an optional dim and blur, and two ways to fill the frame: `fill` (the picture covers the canvas, the
camera crops it) or `card` (the picture sits on a blurred, darkened copy of itself, for a landscape photo in a portrait film). Video is decoded as a stream, one frame per output frame, so a
shot is asked for its frames in order, once each; `still_frame` is the random-access version used to look at one moment."""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .util import Ctx, clamp, ffmpeg_path, ffprobe_path, run, smooth


def probe(path: Path) -> dict:
    """{w, h, duration, fps, has_audio} of a video as it plays (a phone clip stored sideways reports its upright size)."""
    doc = json.loads(run([ffprobe_path(), "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate:stream_side_data=rotation",
                          "-of", "json", str(path)]))
    v = next((s for s in doc.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None:
        return {"w": 0, "h": 0, "duration": float(doc.get("format", {}).get("duration") or 0), "fps": 0.0, "has_audio": any(s.get("codec_type") == "audio" for s in doc.get("streams", []))}
    w, h = int(v["width"]), int(v["height"])
    rot = int((v.get("side_data_list") or [{}])[0].get("rotation", 0)) if v.get("side_data_list") else 0
    if abs(rot) in (90, 270):
        w, h = h, w
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    return {"w": w, "h": h, "duration": float(doc.get("format", {}).get("duration") or 0), "fps": float(num) / float(den or 1),
            "has_audio": any(s.get("codec_type") == "audio" for s in doc.get("streams", []))}


class Shot:
    def __init__(self, spec: dict, i: int, cx: Ctx, start: float, end: float, fps: int):
        self.spec, self.i, self.cx, self.fps = spec, i, cx, fps
        self.start, self.end = start, end            # the window it is on screen, transitions included
        self.first = math.ceil(start * fps - 1e-6)     # the first output frame it is asked for: the stream's frame 0 is that one, so `still` counts from it too
        self.proc = None
        self.last = None
        self.path = Path(cx.assets[spec["asset"]])
        self.kind = cx.assets_type[spec["asset"]]
        self.photo = None
        self.card_bg = None
        if self.kind == "image":
            self.photo = ImageOps.exif_transpose(Image.open(self.path)).convert("RGB")
            if spec.get("fit") == "card":
                self.card_bg = self.cover(self.photo).filter(ImageFilter.GaussianBlur(40 * cx.q))
        else:
            info = probe(self.path)
            self.sw, self.sh = info["w"], info["h"]

    def cover(self, im: Image.Image) -> Image.Image:
        W, H = self.cx.W, self.cx.H
        r = max(W / im.width, H / im.height)
        im2 = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
        x, y = (im2.width - W) // 2, (im2.height - H) // 2
        return im2.crop((x, y, x + W, y + H))

    # ---- streaming
    def open(self):
        if self.kind != "video" or self.proc:
            return
        s = self.spec
        speed = s.get("speed", 1.0)
        dur = (self.end - self.start) * speed + 0.5
        self.proc = subprocess.Popen([ffmpeg_path(), "-v", "error", "-ss", f"{s.get('in', 0.0):.3f}", "-t", f"{dur:.3f}", "-i", str(self.path), "-vf", f"setpts=PTS/{speed},fps={self.fps}",
                                      "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def close(self):
        if self.proc:
            self.proc.stdout.close()
            self.proc.kill()
            self.proc = None

    def source_frame(self) -> np.ndarray:
        self.open()
        n = self.sw * self.sh * 3
        raw = self.proc.stdout.read(n)
        if len(raw) < n:
            return self.last if self.last is not None else np.zeros((self.sh, self.sw, 3), np.uint8)
        self.last = np.frombuffer(raw, np.uint8).reshape(self.sh, self.sw, 3)
        return self.last

    def still_source(self, t: float) -> np.ndarray:
        """The source frame the stream would hand this shot at output time `t`: the same filter chain, so a phone clip of variable frame rate gives the same frame here and in a render."""
        s = self.spec
        n = max(0, round(t * self.fps) - self.first)
        vf = f"setpts=PTS/{s.get('speed', 1.0)},fps={self.fps},select=eq(n\\,{n})"
        raw = subprocess.run([ffmpeg_path(), "-v", "error", "-ss", f"{s.get('in', 0.0):.3f}", "-i", str(self.path), "-vf", vf, "-an", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) < self.sw * self.sh * 3:
            return np.zeros((self.sh, self.sw, 3), np.uint8)
        return np.frombuffer(raw, np.uint8).reshape(self.sh, self.sw, 3)

    # ---- the frame
    def frame(self, t: float, still: bool = False) -> np.ndarray:
        s, cx = self.spec, self.cx
        p = clamp((t - self.start) / max(1e-6, self.end - self.start))
        e = smooth(p)
        cam = s.get("camera") or {}
        z0, z1 = cam.get("zoom", [1.0, 1.0])
        (c0x, c0y), (c1x, c1y) = cam.get("center", [[0.5, 0.5], [0.5, 0.5]])
        z, cxn, cyn = z0 + (z1 - z0) * e, c0x + (c1x - c0x) * e, c0y + (c1y - c0y) * e
        if self.kind == "image":
            im = self.photo
        else:
            im = Image.fromarray(self.still_source(t) if still else self.source_frame())
        if s.get("fit") == "card":
            return self.card(im, z)
        sw, sh = im.size
        aspect = cx.w0 / cx.h0
        cw = min(sw, sh * aspect) / z
        ch = cw / aspect
        x0, y0 = clamp(cxn * sw - cw / 2, 0, sw - cw), clamp(cyn * sh - ch / 2, 0, sh - ch)
        out = im.resize((cx.W, cx.H), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))
        if s.get("blur"):
            out = out.filter(ImageFilter.GaussianBlur(s["blur"] * cx.q))
        a = np.asarray(out, dtype=np.float32)
        if s.get("dim"):
            d0, d1 = s["dim"]
            a = a * (1 - (d0 + (d1 - d0) * e) * smooth((t - self.start) / 0.6))
        return a

    def card(self, im: Image.Image, z: float) -> np.ndarray:
        cx = self.cx
        W, H = cx.W, cx.H
        bg = np.asarray(self.card_bg if self.card_bg is not None else self.cover(im).filter(ImageFilter.GaussianBlur(40 * cx.q)), dtype=np.float32) * 0.40
        card = self.spec.get("card") or {}
        fw = int(W * card.get("width", 0.84) * z)
        fh = int(fw * im.height / im.width)
        fg = im.resize((fw, fh), Image.LANCZOS)
        out = Image.fromarray(bg.astype(np.uint8))
        x, y = (W - fw) // 2, int(H * card.get("y", 0.52) - fh / 2)
        shadow = Image.new("RGBA", (fw + 80, fh + 80), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rectangle((40, 40, 40 + fw, 40 + fh), fill=(0, 0, 0, 170))
        shadow = shadow.filter(ImageFilter.GaussianBlur(24 * cx.q))
        out.paste(shadow, (x - 40, y - 28), shadow)
        out.paste(fg, (x, y))
        return np.asarray(out, dtype=np.float32)
