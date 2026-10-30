"""Render a film spec: the footage layer (shots, camera moves, transitions) streamed into ffmpeg with the grade, the graphics layer (overlay elements, the scrim, the fade) streamed into a second
ffmpeg as an alpha video, the soundtrack mixed in numpy, then one more ffmpeg puts the three together and encodes. `preview` renders at a fraction of the size for a quick look; `still` makes
one frame of the finished film without rendering the rest."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import audio as A
from . import grade as G
from . import spec as S
from .elements import ELEMENTS
from .fonts import Fonts
from .media import Shot
from .transitions import blend
from .util import Ctx, FilmkitError, clamp, ffmpeg_path, ffprobe_path, prog, run, smooth


def make_ctx(spec: dict, base_dir: Path, q: float) -> Ctx:
    c = spec["canvas"]
    assets, kinds = {}, {}
    for name, a in spec["assets"].items():
        p = Path(a["path"])
        assets[name] = str(p if p.is_absolute() else base_dir / p)
        kinds[name] = a["type"]
    return Ctx(c["w"], c["h"], q, Fonts(spec.get("fonts"), base_dir), assets, kinds, base_dir)


def make_shots(spec: dict, cx: Ctx) -> list[Shot]:
    return [Shot(s, i, cx, a, b, spec["canvas"]["fps"]) for i, (s, (a, b)) in enumerate(zip(spec["shots"], S.windows(spec)))]


def scrim(spec: dict, cx: Ctx) -> Image.Image | None:
    cfg = spec.get("scrim", {})
    if cfg is False:
        return None
    key = ("scrim", cx.W, cx.H, json.dumps(cfg, sort_keys=True))
    if key not in cx.cache:
        top, bottom = cfg.get("top", 0.30), cfg.get("bottom", 0.60)
        ta, ba = cfg.get("top_alpha", 100), cfg.get("bottom_alpha", 165)
        ys = np.linspace(0, 1, cx.H)
        a = np.maximum(np.clip((ys - (1 - bottom)) / bottom, 0, 1) ** 1.4 * ba, np.clip((top - ys) / top, 0, 1) ** 1.6 * ta)
        arr = np.zeros((cx.H, cx.W, 4), np.uint8)
        arr[..., 3] = a[:, None].astype(np.uint8)
        cx.cache[key] = Image.fromarray(arr, "RGBA")
    return cx.cache[key]


def overlay_frame(spec: dict, t: float, cx: Ctx) -> Image.Image:
    layer = Image.new("RGBA", (cx.W, cx.H), (0, 0, 0, 0))
    for el in spec.get("overlays", []):
        if el["t0"] <= t < el["t1"]:
            ELEMENTS[el["element"]].draw(layer, t, el, cx, el)
    sc = scrim(spec, cx)
    out = sc.copy() if sc is not None else Image.new("RGBA", (cx.W, cx.H), (0, 0, 0, 0))
    out.alpha_composite(layer)
    fo = spec.get("fade_out")
    if fo:
        f = smooth(prog(t, fo["t"], fo["dur"]))
        if f > 0:
            out.alpha_composite(Image.new("RGBA", (cx.W, cx.H), (0, 0, 0, int(255 * f))))
    return out


def footage_frame(spec: dict, shots: list[Shot], t: float, still: bool = False) -> np.ndarray:
    active = [s for s in shots if s.start <= t < s.end] or [shots[-1]]
    if len(active) == 1:
        return active[0].frame(t, still)
    first, second = active[0], active[1]
    tr = second.spec.get("transition") or {"type": "cut", "dur": 0.0}
    d = max(1e-6, tr.get("dur", 0.0))
    p = clamp((t - (second.spec["start"] - d / 2)) / d)
    return blend(first.frame(t, still), second.frame(t, still), p, tr.get("type", "dissolve"))


def kbps(v) -> float:
    """A bitrate as ffmpeg writes it (`10M`, `8500k`, `9000000`) in kilobits a second."""
    t = str(v).strip().lower()
    return float(t.rstrip("mk")) * (1000 if t.endswith("m") else 1 if t.endswith("k") else 0.001)


def meet_floor(info: dict, enc: dict, audio_k: float, again) -> dict:
    """A client's floor is a promise, not a hope: x264 spends less than its target on easy pictures (a short, still, dark film ended 40 kbps under), so measure the video's bitrate
    (the file's less the audio's) and, when it is under `minrate`, encode again with a higher target (`again(target_kbps)` returns the new report), twice at most and never above
    `maxrate`. The report gains `video_kbps`, `floor_kbps` and `floor_met`."""
    floor, target, cap = kbps(enc["minrate"]), kbps(enc["bitrate"]), kbps(enc.get("maxrate", enc["bitrate"]))
    for _ in range(2):
        video = info["bitrate_kbps"] - audio_k
        if video >= floor or target >= cap:
            break
        target = min(cap, target * floor * 1.04 / max(video, 1))
        info = again(target)
    video = info["bitrate_kbps"] - audio_k
    return {**info, "video_kbps": video, "floor_kbps": round(floor), "floor_met": video >= floor}


def encode_args(spec: dict, preview: bool, bitrate_kbps: float | None = None) -> list[str]:
    """The video encode. `bitrate_kbps` replaces the spec's target (the floor's correction in `render`)."""
    e = spec.get("encode") or {"crf": 18}
    if preview:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    if e.get("bitrate"):
        target = f"{int(round(bitrate_kbps))}k" if bitrate_kbps else e["bitrate"]
        return ["-c:v", "libx264", "-preset", "slow", "-b:v", target, "-minrate", e.get("minrate", e["bitrate"]), "-maxrate", e.get("maxrate", e["bitrate"]),
                "-bufsize", e.get("bufsize", "2M"), "-profile:v", "high"]
    return ["-c:v", "libx264", "-preset", "slow", "-crf", str(e.get("crf", 18)), "-profile:v", "high"]


def render(spec: dict, base_dir: Path, out: Path, *, preview: float | None = None, workdir: Path | None = None, progress=None) -> dict:
    """Render `spec` to `out` (mp4). Returns what came out (duration, size, bitrate, loudness) and the voice and font notes."""
    S.require(spec, base_dir)
    q = preview or 1.0
    cx = make_ctx(spec, base_dir, q)
    fps, dur = spec["canvas"]["fps"], spec["duration"]
    n = int(round(dur * fps))
    tmp = None
    if workdir is None:
        tmp = tempfile.TemporaryDirectory(prefix="filmkit-")
        workdir = Path(tmp.name)
    workdir.mkdir(parents=True, exist_ok=True)
    lk = G.look((spec.get("grade") or {}).get("look", "natural"), (spec.get("grade") or {}).get("over"))
    cube = G.write_cube(workdir / "grade.cube", lk)
    shots = make_shots(spec, cx)
    foot = subprocess.Popen([ffmpeg_path(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{cx.W}x{cx.H}", "-r", str(fps), "-i", "-", "-vf", G.ffmpeg_filter(cube, lk),
                             "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", str(workdir / "footage.mp4")], stdin=subprocess.PIPE)
    over = subprocess.Popen([ffmpeg_path(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{cx.W}x{cx.H}", "-r", str(fps), "-i", "-",
                             "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", str(workdir / "overlay.mov")], stdin=subprocess.PIPE)
    try:
        for k in range(n):
            t = k / fps
            for s in shots:
                if s.end <= t and s.proc:
                    s.close()
            foot.stdin.write(np.clip(footage_frame(spec, shots, t), 0, 255).astype(np.uint8).tobytes())
            over.stdin.write(np.asarray(overlay_frame(spec, t, cx), dtype=np.uint8).tobytes())
            if progress and k % 30 == 0:
                progress(k, n)
    finally:
        for s in shots:
            s.close()
        foot.stdin.close()
        over.stdin.close()
        foot.wait()
        over.wait()
    notes = {}
    cmd = [ffmpeg_path(), "-v", "error", "-y", "-i", str(workdir / "footage.mp4"), "-i", str(workdir / "overlay.mov")]
    sound = spec.get("audio")
    if sound:
        notes = A.mix(sound, dur, base_dir, workdir / "mix.wav")
        cmd += ["-i", str(workdir / "mix.wav")]
    cmd += ["-filter_complex", "[0:v][1:v]overlay=format=auto[v]", "-map", "[v]"]
    if sound:
        cmd += ["-map", "2:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    tail = ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    run(cmd + encode_args(spec, preview is not None) + tail)
    info = inspect(Path(out))
    enc = spec.get("encode") or {}
    if preview is None and enc.get("bitrate") and enc.get("minrate"):
        def again(target: float) -> dict:
            run(cmd + encode_args(spec, False, target) + tail)
            return inspect(Path(out))
        info = meet_floor(info, enc, 192 if sound else 0, again)
    info.update(notes)
    info["fonts_fallback"] = cx.fonts.fallback
    if tmp:
        tmp.cleanup()
    return info


def still(spec: dict, base_dir: Path, t: float, out_png: Path, q: float = 1.0) -> Path:
    """One frame of the finished film at time `t`: the footage (graded) with the graphics on it, without rendering the rest."""
    S.require(spec, base_dir)
    cx = make_ctx(spec, base_dir, q)
    shots = make_shots(spec, cx)
    a = np.clip(footage_frame(spec, shots, t, still=True), 0, 255).astype(np.uint8)
    lk = G.look((spec.get("grade") or {}).get("look", "natural"), (spec.get("grade") or {}).get("over"))
    with tempfile.TemporaryDirectory(prefix="filmkit-still-") as d:
        d = Path(d)
        Image.fromarray(a).save(d / "raw.png")
        run([ffmpeg_path(), "-v", "error", "-y", "-i", str(d / "raw.png"), "-vf", G.ffmpeg_filter(G.write_cube(d / "g.cube", lk), lk), str(d / "graded.png")])
        base = Image.open(d / "graded.png").convert("RGBA")
    base.alpha_composite(overlay_frame(spec, t, cx))
    base.convert("RGB").save(out_png)
    return Path(out_png)


def inspect(path: Path) -> dict:
    """Duration, size, resolution, average bitrate and loudness of a finished file."""
    doc = json.loads(run([ffprobe_path(), "-v", "error", "-show_entries", "format=duration,size,bit_rate:stream=codec_type,width,height", "-of", "json", str(path)]))
    v = next((s for s in doc["streams"] if s.get("codec_type") == "video"), {})
    r = subprocess.run([ffmpeg_path(), "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    lufs = peak = None
    for line in r.stderr.splitlines():
        s = line.strip()
        if s.startswith("I:"):
            lufs = float(s.split()[1])
        elif s.startswith("Peak:"):
            peak = float(s.split()[1])
    f = doc["format"]
    return {"path": str(path), "duration": round(float(f["duration"]), 3), "size_bytes": int(f["size"]), "bitrate_kbps": round(int(f["bit_rate"]) / 1000),
            "width": v.get("width"), "height": v.get("height"), "lufs": lufs, "true_peak_db": peak}
