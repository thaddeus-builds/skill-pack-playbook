"""Shots: a video segment or a still, with a camera move (a zoom and a pan that ease), an optional dim and blur, and four ways to fill the frame: `fill` (the picture covers the canvas, the
camera crops it), `card` (the picture sits on a blurred, darkened copy of itself, for a landscape photo in a portrait film), `panel` (a solid colour with a framed picture that pushes in:
panel.py) and `split` (two pictures stacked, each with its own clip and camera). A `fill` shot may carry a `cutout` (cutout.py). Video is decoded as a stream, one frame per output frame,
so a shot is asked for its frames in order, once each; `still_frame` is the random-access version used to look at one moment."""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import cutout as CO
from . import panel as PN
from .util import Ctx, FilmkitError, clamp, ffmpeg_path, ffprobe_path, run, smooth


# demuxers that do more than read one file: a clip that names other files or addresses is not footage
REFUSED_FORMATS = {"concat", "hls", "applehttp", "dash", "sdp", "rtp", "rtsp", "tee", "lavfi", "ffmetadata", "data"}
SAFE_INPUT = ["-protocol_whitelist", "file,pipe"]


def probe(path: Path) -> dict:
    """{w, h, duration, fps, has_audio, hdr} of a video as it plays: a phone clip stored sideways reports its upright size, one with a non-square pixel its displayed width."""
    doc = json.loads(run([ffprobe_path(), "-v", "error", *SAFE_INPUT, "-show_entries", "format=duration,format_name:stream=codec_type,width,height,r_frame_rate,sample_aspect_ratio,color_transfer:stream_side_data=rotation",
                          "-of", "json", str(path)]))
    fmt = doc.get("format", {})
    if REFUSED_FORMATS & set(str(fmt.get("format_name", "")).split(",")):
        raise FilmkitError(f"{path} is a {fmt['format_name']!r} file, not footage: it names other files or addresses")
    streams = doc.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    duration = float(fmt.get("duration") or 0)
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if v is None:
        return {"w": 0, "h": 0, "duration": duration, "fps": 0.0, "has_audio": has_audio, "hdr": False}
    w, h = int(v["width"]), int(v["height"])
    rot = int((v.get("side_data_list") or [{}])[0].get("rotation", 0)) if v.get("side_data_list") else 0
    sar = 1.0
    try:
        a, b = str(v.get("sample_aspect_ratio") or "1:1").split(":")
        sar = float(a) / float(b) if float(a) > 0 and float(b) > 0 else 1.0
    except (ValueError, ZeroDivisionError):
        pass
    square = abs(sar - 1.0) < 0.01 or abs(rot) in (90, 270)
    if abs(rot) in (90, 270):
        w, h = h, w
    if not square:
        w = max(2, int(round(w * sar / 2)) * 2)                  # the displayed width, even
    try:
        num, den = str(v.get("r_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except ValueError:
        fps = 0.0
    return {"w": w, "h": h, "duration": duration, "fps": fps, "has_audio": has_audio, "square": square, "hdr": v.get("color_transfer") in ("arib-std-b67", "smpte2084")}


def _stderr_tail(f) -> str:
    try:
        f.flush()
        f.seek(0)
        return f.read().decode(errors="replace").strip()[-300:]
    except (OSError, ValueError):
        return ""


def crop_resize(im: Image.Image, aspect: float, w: int, h: int, z: float, cxn: float, cyn: float) -> Image.Image:
    """The part of `im` the camera sees (zoom `z` on the centre (`cxn`, `cyn`), a fraction of the picture, the box of the given aspect) resized to w x h."""
    sw, sh = im.size
    cw = min(sw, sh * aspect) / z
    ch = cw / aspect
    x0, y0 = clamp(cxn * sw - cw / 2, 0, sw - cw), clamp(cyn * sh - ch / 2, 0, sh - ch)
    return im.resize((w, h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def frames_first(pattern: str) -> int | None:
    """The number of the first picture of a sequence named by `pattern` (`m_%04d.png`): 0 or 1, whichever is a file; None when neither is."""
    try:
        return next((n for n in (0, 1) if Path(pattern % n).is_file()), None)
    except (TypeError, ValueError):
        return None


class Shot:
    def __init__(self, spec: dict, i: int, cx: Ctx, start: float, end: float, fps: int):
        self.spec, self.i, self.cx, self.fps = spec, i, cx, fps
        self.start, self.end = start, end            # the window it is on screen, transitions included
        self.first = math.ceil(start * fps - 1e-6)     # the first output frame it is asked for: the stream's frame 0 is that one, so `still` counts from it too
        self.proc = None
        self.err = None
        self.last = None
        self.path = Path(cx.assets[spec["asset"]])
        self.kind = cx.assets_type[spec["asset"]]
        self.photo = None
        self.card_bg = None
        self.clip = 0.0
        self.pre = ""
        self.parts: list[Shot] = []
        self.matte: Shot | None = None
        self.first_no = 0
        if spec.get("fit") == "split":                  # two shots of their own, each in the half of the canvas it fills, stacked by `frame`
            self.split_parts(i, cx, start, end, fps)
            return
        if self.kind == "image":
            self.photo = ImageOps.exif_transpose(Image.open(self.path)).convert("RGB")
            if spec.get("fit") == "card":
                self.card_bg = self.cover(self.photo).filter(ImageFilter.GaussianBlur(40 * cx.q))
        else:
            if self.kind == "frames":                   # a picture sequence read at the asset's own rate (a matte, usually)
                self.first_no = frames_first(str(self.path)) or 0
                with Image.open(str(self.path) % self.first_no) as im0:
                    info = {"w": im0.width, "h": im0.height, "duration": 0.0, "square": True, "hdr": False}
                self.src_fps = cx.assets_fps.get(spec["asset"], 30)
            else:
                info = probe(self.path)
            if not info["w"]:
                raise FilmkitError(f"shots[{i}]: {self.path} has no video stream")
            self.sw, self.sh, self.clip = info["w"], info["h"], info["duration"]
            if not info["square"]:
                self.pre = f"scale={self.sw}:{self.sh},setsar=1,"          # a non-square pixel is stretched to the shape it is shown in, so the bytes of a frame are what `probe` said
            if info["hdr"]:
                cx.notes.append(f"shots[{i}]: {self.path.name} is HDR (HLG or PQ): it is not tone-mapped, so its colours will look flat")
        c = spec.get("cutout")
        if c:                                           # the matte plays beside the clip: the same `in` and `speed`, so frame for frame
            self.matte = Shot({"id": f"{spec.get('id')}:matte", "asset": c["matte"], "in": spec.get("in", 0.0), "speed": spec.get("speed", 1.0)}, i, cx, start, end, fps)

    def split_parts(self, i, cx, start, end, fps):
        sp = spec = self.spec
        sp = spec["split"]
        at = sp.get("at", 0.5)
        ht = int(cx.H * at) // 2 * 2
        hb = cx.H - ht
        top = {k: spec[k] for k in ("asset", "in", "speed", "camera", "dim", "blur") if k in spec}
        bottom = {k: v for k, v in sp["bottom"].items()}
        for k, part in (("top", top), ("bottom", bottom)):
            part.update({"id": f"{spec.get('id')}:{k}", "start": spec["start"], "end": spec["end"]})
        self.ht = ht
        self.parts = [Shot(top, i, replace(cx, h0=(ht + 0.5) / cx.q), start, end, fps), Shot(bottom, i, replace(cx, h0=(hb + 0.5) / cx.q), start, end, fps)]

    def busy(self) -> bool:
        """Whether a decoder of this shot (or of its matte or its halves) is running."""
        return bool(self.proc) or any(p.busy() for p in self.parts) or bool(self.matte and self.matte.busy())

    def cover(self, im: Image.Image) -> Image.Image:
        W, H = self.cx.W, self.cx.H
        r = max(W / im.width, H / im.height)
        im2 = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
        x, y = (im2.width - W) // 2, (im2.height - H) // 2
        return im2.crop((x, y, x + W, y + H))

    # ---- streaming
    def source_args(self) -> list[str]:
        """What ffmpeg is told about the input before `-i`: the protocols allowed, and for a picture sequence its rate and first number."""
        return [*SAFE_INPUT, *(["-framerate", str(self.src_fps), "-start_number", str(self.first_no)] if self.kind == "frames" else [])]

    def open(self):
        if self.kind not in ("video", "frames") or self.proc:
            return
        s = self.spec
        speed = s.get("speed", 1.0)
        dur = (self.end - self.start) * speed + 0.5
        self.err = tempfile.TemporaryFile()
        self.proc = subprocess.Popen([ffmpeg_path(), "-v", "error", *self.source_args(), "-ss", f"{s.get('in', 0.0):.3f}", "-t", f"{dur:.3f}", "-i", str(self.path), "-vf", f"{self.pre}setpts=PTS/{speed},fps={self.fps}",
                                      "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=self.err)

    def close(self):
        for p in self.parts:
            p.close()
        if self.matte:
            self.matte.close()
        if self.proc:
            self.proc.stdout.close()
            self.proc.kill()
            self.proc.wait()
            self.proc = None
        if self.err:
            self.err.close()
            self.err = None

    def source_frame(self) -> np.ndarray:
        self.open()
        n = self.sw * self.sh * 3
        raw = self.proc.stdout.read(n)
        if len(raw) < n:
            if self.last is None:                                           # the stream gave nothing at all: say why instead of showing black
                raise FilmkitError(f"shots[{self.i}]: no frame decoded from {self.path} at in={self.spec.get('in', 0.0)}: {_stderr_tail(self.err) or 'the clip ends before this point'}")
            return self.last                                                # the clip is shorter than the shot: its last frame is held
        self.last = np.frombuffer(raw, np.uint8).reshape(self.sh, self.sw, 3)
        return self.last

    def still_source(self, t: float) -> np.ndarray:
        """The source frame the stream would hand this shot at output time `t`: the same filter chain, so a phone clip of variable frame rate gives the same frame here and in a render, and a shot that
        outlasts its clip shows the clip's last frame, as the render holds it."""
        s = self.spec
        speed = s.get("speed", 1.0)
        n = max(0, round(t * self.fps) - self.first)
        last = max(0, int(max(0.0, self.clip - s.get("in", 0.0)) / speed * self.fps + 1e-6) - 1)
        n = min(n, last) if self.clip else n
        need = self.sw * self.sh * 3
        why = ""
        for k in (n, n - 1, n - 2):
            if k < 0:
                break
            vf = f"{self.pre}setpts=PTS/{speed},fps={self.fps},select=eq(n\\,{k})"
            r = subprocess.run([ffmpeg_path(), "-v", "error", *self.source_args(), "-ss", f"{s.get('in', 0.0):.3f}", "-i", str(self.path), "-vf", vf, "-an", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               capture_output=True)
            if len(r.stdout) >= need:
                return np.frombuffer(r.stdout[:need], np.uint8).reshape(self.sh, self.sw, 3)
            why = r.stderr.decode(errors="replace").strip()[-300:]
        raise FilmkitError(f"shots[{self.i}]: no frame decoded from {self.path} at in={s.get('in', 0.0)}: {why or 'the clip ends before this point'}")

    # ---- the frame
    def source_image(self, t: float, still: bool = False) -> Image.Image:
        """The picture this shot is made of at `t`, before any camera: its photo, or the clip's frame (the stream's next one, or, for a still, the one at `t`)."""
        if self.kind == "image":
            return self.photo
        return Image.fromarray(self.still_source(t) if still else self.source_frame())

    def frame(self, t: float, still: bool = False) -> np.ndarray:
        s, cx = self.spec, self.cx
        if self.parts:
            return self.split(t, still)
        p = clamp((t - self.start) / max(1e-6, self.end - self.start))
        e = smooth(p)
        cam = s.get("camera") or {}
        z0, z1 = cam.get("zoom", [1.0, 1.08] if s.get("fit") == "panel" else [1.0, 1.0])
        (c0x, c0y), (c1x, c1y) = cam.get("center", [[0.5, 0.5], [0.5, 0.5]])
        z, cxn, cyn = z0 + (z1 - z0) * e, c0x + (c1x - c0x) * e, c0y + (c1y - c0y) * e
        im = self.source_image(t, still)
        if s.get("fit") == "card":
            return self.card(im, z)
        if s.get("fit") == "panel":
            return self.panel(im, z, cxn, cyn)
        aspect = cx.w0 / cx.h0
        out = crop_resize(im, aspect, cx.W, cx.H, z, cxn, cyn)
        if self.matte:
            out = self.cut_out(out, im, t, still, aspect, z, cxn, cyn)
        if s.get("blur"):
            out = out.filter(ImageFilter.GaussianBlur(s["blur"] * cx.q))
        a = np.asarray(out, dtype=np.float32)
        if s.get("dim"):
            d0, d1 = s["dim"]
            a = a * (1 - (d0 + (d1 - d0) * e) * smooth((t - self.start) / 0.6))
        return a

    def cut_out(self, fg: Image.Image, im: Image.Image, t: float, still: bool, aspect: float, z: float, cxn: float, cyn: float) -> Image.Image:
        """`fg` (the camera's picture) with its backdrop replaced by the enlarged, blurred and tinted frame, and the outline on the subject's edge."""
        cx, c = self.cx, self.spec["cutout"]
        _, bg = CO.settings(c)
        matte = self.matte.source_image(t, still).convert("L")
        if matte.size != im.size:
            matte = matte.resize(im.size, Image.BILINEAR)
        k = 0.25 if bg["blur"] * cx.q >= 8 else 1.0
        w, h = max(2, int(cx.W * k)), max(2, int(cx.H * k))
        back = CO.backdrop(crop_resize(im, aspect, w, h, z * bg["zoom"], cxn, cyn), bg, cx.q, (cx.W, cx.H))
        m = np.asarray(crop_resize(matte, aspect, cx.W, cx.H, z, cxn, cyn), dtype=np.uint8)
        return Image.fromarray(np.clip(CO.compose(np.asarray(fg, dtype=np.float32), back, m, c, t - self.start, cx.q), 0, 255).astype(np.uint8))

    def panel(self, im: Image.Image, z: float, cxn: float, cyn: float) -> np.ndarray:
        """A solid colour, the picture in a frame at `panel.y`, pushed in by the camera's zoom (the frame itself stays)."""
        cx, pn = self.cx, self.spec["panel"]
        g = PN.geometry(pn, cx.w0, cx.h0)
        q = cx.q
        top = np.array(pn.get("bg", PN.BG)[:3], np.float32)
        if pn.get("bg2"):
            k = np.linspace(0.0, 1.0, cx.H, dtype=np.float32)[:, None, None]
            grad = top[None, None, :] * (1 - k) + np.array(pn["bg2"][:3], np.float32)[None, None, :] * k
            out = Image.fromarray(np.repeat(grad, cx.W, axis=1).astype(np.uint8), "RGB")
        else:
            out = Image.new("RGB", (cx.W, cx.H), tuple(int(v) for v in top))
        ox0, oy0, ox1, oy1 = (int(round(v * q)) for v in g["outer"])
        ix0, iy0, ix1, iy1 = (int(round(v * q)) for v in g["inner"])
        ImageDraw.Draw(out).rectangle((ox0, oy0, ox1 - 1, oy1 - 1), fill=tuple(int(v) for v in g["frame_color"][:3]))
        out.paste(crop_resize(im, (ix1 - ix0) / (iy1 - iy0), ix1 - ix0, iy1 - iy0, z, cxn, cyn), (ix0, iy0))
        return np.asarray(out, dtype=np.float32)

    def split(self, t: float, still: bool) -> np.ndarray:
        """The two halves stacked, the seam line (if any) across the join."""
        out = np.concatenate([p.frame(t, still) for p in self.parts], axis=0)
        sm = self.spec["split"].get("seam")
        if sm:
            w = max(1, int(round(sm.get("width", 6) * self.cx.q)))
            out[max(0, self.ht - w // 2): self.ht - w // 2 + w] = np.array(sm.get("color", [255, 255, 255])[:3], np.float32)
        return out

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
