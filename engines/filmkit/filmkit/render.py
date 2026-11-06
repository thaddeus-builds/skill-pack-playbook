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
    return Ctx(c["w"], c["h"], q, Fonts(spec.get("fonts"), base_dir), assets, kinds, {n: a["fps"] for n, a in spec["assets"].items() if "fps" in a}, base_dir)


def make_shots(spec: dict, cx: Ctx) -> list[Shot]:
    return [Shot(s, i, cx, a, b, spec["canvas"]["fps"]) for i, (s, (a, b)) in enumerate(zip(spec["shots"], S.windows(spec)))]


def scrim(spec: dict, cx: Ctx) -> Image.Image | None:
    cfg = spec.get("scrim")
    if cfg is False:
        return None
    cfg = cfg or {}
    key = ("scrim", cx.W, cx.H, json.dumps(cfg, sort_keys=True))
    if key not in cx.cache:
        top, bottom = cfg.get("top", 0.30), cfg.get("bottom", 0.60)
        ta, ba = cfg.get("top_alpha", 100), cfg.get("bottom_alpha", 165)
        ys = np.linspace(0, 1, cx.H)
        a = np.maximum(np.clip((ys - (1 - bottom)) / bottom, 0, 1) ** 1.4 * ba, np.clip((top - ys) / top, 0, 1) ** 1.6 * ta)
        arr = np.zeros((cx.H, cx.W, 4), np.uint8)
        arr[..., 3] = np.clip(a, 0, 255)[:, None].astype(np.uint8)
        cx.cache[key] = Image.fromarray(arr, "RGBA")
    return cx.cache[key]


def overlay_frame(spec: dict, t: float, cx: Ctx) -> Image.Image:
    layer = Image.new("RGBA", (cx.W, cx.H), (0, 0, 0, 0))
    for el in S.all_overlays(spec):
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


EPS = 1e-6                                       # a window that starts a hair after a frame's time still starts at that frame (`Shot.first` rounds the same way)


def footage_frame(spec: dict, shots: list[Shot], t: float, still: bool = False) -> np.ndarray:
    active = [s for s in shots if s.start - EPS <= t < s.end - EPS] or [shots[-1]]
    if len(active) == 1:
        return active[0].frame(t, still)
    first, second = active[0], active[1]
    tr = second.spec.get("transition") or {"type": "cut", "dur": 0.0}
    if tr.get("type", "cut") == "cut":
        return second.frame(t, still)
    d = max(1e-6, tr.get("dur", 0.0))
    p = clamp((t - (second.spec["start"] - d / 2)) / d)
    return blend(first.frame(t, still), second.frame(t, still), p, tr["type"])


def kbps(v) -> float:
    """A bitrate as ffmpeg writes it (`10M`, `8500k`, `9000000`) in kilobits a second."""
    t = str(v).strip().lower()
    return float(t.rstrip("mk")) * (1000 if t.endswith("m") else 1 if t.endswith("k") else 0.001)


def meet_floor(info: dict, enc: dict, again) -> dict:
    """A client's floor is a promise, not a hope: x264 spends less than its target on easy pictures (a short, still, dark film ended 40 kbps under), so take the video stream's own bitrate
    (`info["video_kbps"]`, from its packets) and, when it is under `minrate`, encode again with a higher target (`again(target_kbps)` returns the new report), twice at most and never above
    `maxrate`. The report gains `floor_kbps` and `floor_met`."""
    floor, target, cap = kbps(enc["minrate"]), kbps(enc["bitrate"]), kbps(enc.get("maxrate", enc["bitrate"]))
    for _ in range(2):
        video = info["video_kbps"]
        if video >= floor or target >= cap:
            break
        target = min(cap, target * floor * 1.04 / max(video, 1))
        info = again(target)
    return {**info, "floor_kbps": round(floor), "floor_met": info["video_kbps"] >= floor}


def encode_args(spec: dict, preview: bool, bitrate_kbps: float | None = None) -> list[str]:
    """The video encode. `bitrate_kbps` replaces the spec's target (the floor's correction in `render`)."""
    e = spec.get("encode") or {"crf": 18}
    if preview:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    if e.get("bitrate"):
        target = f"{int(round(bitrate_kbps))}k" if bitrate_kbps else str(e["bitrate"])
        return ["-c:v", "libx264", "-preset", "slow", "-b:v", target, "-minrate", str(e.get("minrate", e["bitrate"])), "-maxrate", str(e.get("maxrate", e["bitrate"])),
                "-bufsize", str(e.get("bufsize", "2M")), "-profile:v", "high"]
    return ["-c:v", "libx264", "-preset", "slow", "-crf", str(e.get("crf", 18)), "-profile:v", "high"]


# The pictures are made as RGB and delivered as BT.709 limited-range YUV, said in the stream: ffmpeg's own RGB to YUV is BT.601, which a player that takes untagged HD as 709 shows
# shifted (a pure green came out 40 levels off). `scale` does the conversion with the 709 matrix and these tags say so.
BT709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
TO_709 = "scale=out_color_matrix=bt709:out_range=tv"


class Child:
    """An ffmpeg that is fed frames on its stdin: its messages go to a log in the work folder, a write that finds it gone says why, and its exit status is read."""

    def __init__(self, name: str, cmd: list[str], workdir: Path):
        self.name = name
        self.log = open(workdir / f"{name}.log", "wb+")
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=self.log, cwd=workdir)

    def tail(self) -> str:
        self.log.flush()
        self.log.seek(0)
        return self.log.read().decode(errors="replace").strip()[-400:]

    def write(self, data: bytes) -> None:
        try:
            self.p.stdin.write(data)
        except (BrokenPipeError, OSError) as e:
            raise FilmkitError(f"the {self.name} encoder stopped: {self.tail() or e}") from e

    def stop(self, kill: bool = False) -> None:
        if kill and self.p.poll() is None:
            self.p.kill()
        try:
            self.p.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        self.p.wait()

    def check(self) -> None:
        if self.p.returncode:
            raise FilmkitError(f"the {self.name} encoder failed ({self.p.returncode}): {self.tail()}")

    def close(self) -> None:
        self.log.close()


def resolved(spec: dict, base_dir: Path) -> set[Path]:
    """Every file the spec reads: footage, pictures, voice lines, fonts."""
    files = [a["path"] for a in spec["assets"].values()] + [v["file"] for v in (spec.get("audio") or {}).get("voice", [])] + [f for f in (spec.get("fonts") or {}).values() if f]
    return {(Path(f) if Path(f).is_absolute() else base_dir / f).resolve() for f in files}


def refuse_overwrite(spec: dict, base_dir: Path, out: Path, keep: list[Path]) -> Path:
    """The output's absolute path, or a FilmkitError when it is a file the film reads (a render over the client's own clip is a clip lost) or its folder is not there."""
    out = Path(out).resolve()
    if out in resolved(spec, base_dir) | {Path(k).resolve() for k in keep}:
        raise FilmkitError(f"--out {out} is a file the film reads: render to another name")
    if not out.parent.is_dir():
        raise FilmkitError(f"--out {out}: the folder {out.parent} is not there")
    return out


def preflight(spec: dict, cx: Ctx) -> None:
    """Draw every overlay once, in the middle of its time, before any frame is rendered: a graphic that cannot be drawn fails in a second, with its place in the spec, not minutes in."""
    own = len(spec.get("overlays") or [])
    for i, el in enumerate(S.all_overlays(spec)):
        layer = Image.new("RGBA", (cx.W, cx.H), (0, 0, 0, 0))
        try:
            ELEMENTS[el["element"]].draw(layer, (el["t0"] + el["t1"]) / 2, el, cx, el)
        except Exception as e:  # noqa: BLE001
            where = f"overlays[{i - (len(S.all_overlays(spec)) - own)}]" if i >= len(S.all_overlays(spec)) - own else "a panel's title or caption"
            raise FilmkitError(f"{where} ({el['element']}) cannot be drawn: {type(e).__name__}: {e}") from e


def render(spec: dict, base_dir: Path, out: Path, *, preview: float | None = None, workdir: Path | None = None, progress=None, keep: list[Path] = ()) -> dict:
    """Render `spec` to `out` (mp4). Returns what came out (duration, size, bitrate, loudness) and the voice and font notes. `keep`: more files `out` must not overwrite (the CLI gives the spec file)."""
    S.require(spec, base_dir)
    out = refuse_overwrite(spec, base_dir, out, list(keep))
    q = preview or 1.0
    cx = make_ctx(spec, base_dir, q)
    if cx.W < 2 or cx.H < 2:
        raise FilmkitError(f"--preview {preview} leaves a picture of {cx.W}x{cx.H}")
    fps, dur = spec["canvas"]["fps"], spec["duration"]
    n = int(round(dur * fps))
    tmp = None
    if workdir is None:
        tmp = tempfile.TemporaryDirectory(prefix="filmkit-")
        workdir = Path(tmp.name)
    workdir = Path(workdir).resolve()
    kids: list[Child] = []
    shots: list[Shot] = []
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        preflight(spec, cx)
        notes: dict = {}
        sound = spec.get("audio")
        if sound:                                                          # the sound first: its mistakes (a voice file that is not audio) cost seconds, not a rendered picture
            if sound.get("music"):                                         # the film's tempo is the bed's unless the music names its own
                sound = {**sound, "music": {"bpm": spec.get("bpm", 90), **sound["music"]}}
            notes = A.mix(sound, dur, base_dir, workdir / "mix.wav")
        lk = G.look((spec.get("grade") or {}).get("look", "natural"), (spec.get("grade") or {}).get("over"))
        G.write_cube(workdir / "grade.cube", lk)
        shots = make_shots(spec, cx)
        size = f"{cx.W}x{cx.H}"
        foot = Child("footage", [ffmpeg_path(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", size, "-r", str(fps), "-i", "-",
                                 "-vf", f"{G.ffmpeg_filter('grade.cube', lk)},{TO_709},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", *BT709, "footage.mp4"], workdir)
        kids.append(foot)
        over = Child("graphics", [ffmpeg_path(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", size, "-r", str(fps), "-i", "-",
                                  "-vf", f"{TO_709},format=yuva444p10le", "-c:v", "prores_ks", "-profile:v", "4", *BT709, "overlay.mov"], workdir)
        kids.append(over)
        for k in range(n):
            t = k / fps
            for s in shots:
                if s.end <= t and s.busy():
                    s.close()
            foot.write(np.clip(footage_frame(spec, shots, t), 0, 255).astype(np.uint8).tobytes())
            over.write(np.asarray(overlay_frame(spec, t, cx), dtype=np.uint8).tobytes())
            if progress and k % 30 == 0:
                progress(k, n)
        for c in kids:
            c.stop()
        for c in kids:
            c.check()
        cmd = [ffmpeg_path(), "-v", "error", "-y", "-i", "footage.mp4", "-i", "overlay.mov"]
        if sound:
            cmd += ["-i", "mix.wav"]
        cmd += ["-filter_complex", "[0:v][1:v]overlay=format=auto[v]", "-map", "[v]"]
        if sound:
            cmd += ["-map", "2:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        tail = ["-pix_fmt", "yuv420p", *BT709, "-movflags", "+faststart", str(out)]
        run(cmd + encode_args(spec, preview is not None) + tail, cwd=workdir)
        info = inspect(out)
        enc = spec.get("encode") or {}
        if preview is None and enc.get("bitrate") and enc.get("minrate"):
            def again(target: float) -> dict:
                run(cmd + encode_args(spec, False, target) + tail, cwd=workdir)
                return inspect(out)
            info = meet_floor(info, enc, again)
        info.update(notes)
        info["fonts_fallback"] = cx.fonts.fallback
        if cx.notes:
            info["notes"] = cx.notes
        return info
    finally:
        for s in shots:
            s.close()
        for c in kids:
            c.stop(kill=True)
            c.close()
        if tmp:
            tmp.cleanup()


def still(spec: dict, base_dir: Path, t: float, out_png: Path, q: float = 1.0) -> Path:
    """One frame of the finished film at time `t`: the footage (graded) with the graphics on it, without rendering the rest."""
    S.require(spec, base_dir)
    if not (isinstance(t, (int, float)) and 0 <= t < spec["duration"]):
        raise FilmkitError(f"--at {t}: the film runs from 0 to {spec['duration']} s")
    out_png = Path(out_png).resolve()
    if not out_png.parent.is_dir():
        raise FilmkitError(f"--out {out_png}: the folder {out_png.parent} is not there")
    cx = make_ctx(spec, base_dir, q)
    if cx.W < 2 or cx.H < 2:
        raise FilmkitError(f"--scale {q} leaves a picture of {cx.W}x{cx.H}")
    shots = make_shots(spec, cx)
    try:
        a = np.clip(footage_frame(spec, shots, t, still=True), 0, 255).astype(np.uint8)
    finally:
        for s in shots:
            s.close()
    lk = G.look((spec.get("grade") or {}).get("look", "natural"), (spec.get("grade") or {}).get("over"))
    with tempfile.TemporaryDirectory(prefix="filmkit-still-") as d:
        d = Path(d)
        Image.fromarray(a).save(d / "raw.png")
        G.write_cube(d / "g.cube", lk)
        run([ffmpeg_path(), "-v", "error", "-y", "-i", "raw.png", "-vf", G.ffmpeg_filter("g.cube", lk), "graded.png"], cwd=d)
        base = Image.open(d / "graded.png").convert("RGBA")
    base.alpha_composite(overlay_frame(spec, t, cx))
    base.convert("RGB").save(out_png)
    return out_png


def stream_kbps(path: Path, kind: str, duration: float) -> float | None:
    """The bitrate of one stream (`v` or `a`) from the sizes of its packets, in kilobits a second: what the stream is, without the container's own bytes."""
    r = run([ffprobe_path(), "-v", "error", "-select_streams", kind, "-show_entries", "packet=size", "-of", "csv=p=0", str(path)])
    sizes = [int(x) for x in r.split() if x.strip().isdigit()]
    return round(sum(sizes) * 8 / duration / 1000, 1) if sizes and duration > 0 else None


def inspect(path: Path) -> dict:
    """Duration, size, resolution, colour tags, average and per-stream bitrate and loudness of a finished media file (a FilmkitError for anything ffprobe cannot read as one)."""
    path = Path(path)
    if not path.is_file():
        raise FilmkitError(f"{path} is not a file")
    doc = json.loads(run([ffprobe_path(), "-v", "error", "-show_entries", "format=duration,size,bit_rate:stream=codec_type,width,height,color_space,color_range,color_primaries,color_transfer", "-of", "json", str(path)]))
    v = next((s for s in doc.get("streams", []) if s.get("codec_type") == "video"), {})
    f = doc.get("format", {})
    if not f.get("duration"):
        raise FilmkitError(f"{path} is not a media file with a duration")
    r = subprocess.run([ffmpeg_path(), "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    lufs = peak = None
    for line in r.stderr.splitlines():
        s = line.strip()
        if s.startswith("I:"):
            lufs = float(s.split()[1])
        elif s.startswith("Peak:"):
            peak = float(s.split()[1])
    duration = float(f["duration"])
    return {"path": str(path), "duration": round(duration, 3), "size_bytes": int(f.get("size") or 0), "bitrate_kbps": round(int(f.get("bit_rate") or 0) / 1000),
            "width": v.get("width"), "height": v.get("height"), "color_space": v.get("color_space"), "color_range": v.get("color_range"), "color_transfer": v.get("color_transfer"),
            "video_kbps": stream_kbps(path, "v", duration), "audio_kbps": stream_kbps(path, "a", duration), "lufs": lufs, "true_peak_db": peak}
