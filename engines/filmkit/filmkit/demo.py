"""A demo film in one call: synthetic clips (one stored sideways, as a phone does), a landscape photo, a logo with a transparent page, a tone for a voice line, and a spec that uses every
element, every kind of shot and a transition of each family (`film.json`); and a second, `story.json`, with one example of each story-film feature: a presenter cutout (a moving ellipse
is its synthetic matte, as a video and as a picture sequence), a panel shot, a split shot, a ghost whip, the kinetic and year elements, a typewriter and spaced-in letters.
`python -m filmkit demo --out DIR` writes them and prints the specs' paths; the tests build on the same files. Nothing here is a client's."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from .util import ffmpeg_path


def ffmpeg(*args):
    subprocess.run([ffmpeg_path(), "-v", "error", "-y", *args], check=True)


def make_assets(d: Path) -> Path:
    """Two clips (one stored sideways, as a phone does), a landscape photo, a logo with a transparent page, a voice-like tone: all synthetic."""
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30:duration=4", "-pix_fmt", "yuv420p", str(d / "a.mp4"))
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4", "-metadata:s:v", "rotate=90", "-pix_fmt", "yuv420p", str(d / "b.mp4"))
    im = Image.new("RGB", (1440, 1080), (40, 90, 140))
    ImageDraw.Draw(im).ellipse((500, 300, 940, 760), fill=(220, 190, 120))
    im.save(d / "photo.jpg")
    lg = Image.new("RGBA", (400, 100), (0, 0, 0, 0))
    ImageDraw.Draw(lg).rectangle((0, 0, 90, 90), fill=(46, 139, 216, 255))
    ImageDraw.Draw(lg).rectangle((110, 20, 390, 70), fill=(255, 255, 255, 255))
    lg.save(d / "logo.png")
    ffmpeg("-f", "lavfi", "-i", "sine=f=220:r=44100:d=1.2", "-ac", "1", str(d / "vo.wav"))
    # a matte for a.mp4: a white ellipse that sways on black, the same size and length as the clip (a stand-in for what a segmentation tool would make)
    ffmpeg("-f", "lavfi", "-i", "color=c=black:s=720x1280:r=30:d=4,format=gray,geq=lum='if(lt(hypot((X-360-120*sin(2*T))/150,(Y-700)/380),1),255,0)'", "-pix_fmt", "yuv420p", str(d / "matte.mp4"))
    (d / "matte").mkdir(exist_ok=True)
    ffmpeg("-i", str(d / "matte.mp4"), "-vf", "format=gray", str(d / "matte" / "m_%04d.png"))
    return d


def film_spec(d: Path | None = None) -> dict:
    return {
        "schema": "filmkit.film/1", "id": "test", "canvas": {"w": 1080, "h": 1920, "fps": 30}, "duration": 6.0, "bpm": 90,
        "assets": {"a": {"type": "video", "path": "a.mp4"}, "b": {"type": "video", "path": "b.mp4"}, "p": {"type": "image", "path": "photo.jpg"}, "logo": {"type": "image", "path": "logo.png"}},
        "shots": [
            {"id": "s1", "asset": "a", "start": 0.0, "end": 2.0, "in": 0.5, "camera": {"zoom": [1.3, 1.0], "center": [[0.4, 0.6], [0.5, 0.5]]}},
            {"id": "s2", "asset": "b", "start": 2.0, "end": 4.0, "in": 0.0, "speed": 1.0, "dim": [0.3, 0.3], "blur": 2, "transition": {"type": "dissolve", "dur": 0.4}},
            {"id": "s3", "asset": "p", "start": 4.0, "end": 6.0, "fit": "card", "camera": {"zoom": [1.0, 1.05], "center": [[0.5, 0.5], [0.5, 0.5]]}, "transition": {"type": "push", "dur": 0.4}},
        ],
        "grade": {"look": "teal_warm_soft"},
        "overlays": [
            {"element": "title", "t0": 0.3, "t1": 2.2, "lines": ["A TITLE", "THAT RISES."], "x": 64, "y": 420, "size": 112},
            {"element": "chip", "t0": 2.2, "t1": 4.0, "x": 64, "y": 350, "text": "A SECTION TAG"},
            {"element": "brackets", "t0": 2.3, "t1": 4.0, "box": [150, 600, 930, 1180]},
            {"element": "scan", "t0": 2.5, "t1": 4.0, "box": [150, 600, 930, 1180], "period": 1.2},
            {"element": "counter", "t0": 2.4, "t1": 4.0, "x": 64, "y": 470, "target": 4, "suffix": "+", "size": 300},
            {"element": "steps", "t0": 4.2, "t1": 6.0, "x": 100, "top": 500, "step": 190, "items": [["01", "FIRST STEP"], ["02", "SECOND STEP"]]},
            {"element": "rule", "t0": 4.4, "t1": 6.0, "x0": 160, "x1": 800, "y": 1300},
            {"element": "text", "t0": 4.6, "t1": 6.0, "x": 540, "y": 1100, "text": "A TRACKED TAGLINE", "anchor": "m", "tracking": 6},
            {"element": "logo", "t0": 0.5, "t1": 5.5, "asset": "logo", "x": 64, "y": 250, "width": 280},
        ],
        "fade_out": {"t": 5.5, "dur": 0.5},
        "audio": {"voice": [{"t": 0.5, "file": "vo.wav"}], "music": {"bpm": 90, "pluck_from": 2.0, "impacts": [0.0, 4.0], "risers": [[1.0, 2.0]], "whooshes": [3.6], "pings": [4.4]}, "lufs": -16},
        "encode": {"crf": 20},
        "safe": {"profile": "tiktok"},
    }


def story_spec(d: Path | None = None) -> dict:
    """One of each story-film feature on a vertical film (every number a synthetic example; the type is Latin so the face Pillow carries can set it)."""
    return {
        "schema": "filmkit.film/1", "id": "story-demo", "canvas": {"w": 1080, "h": 1920, "fps": 30}, "duration": 11.0,
        "assets": {"a": {"type": "video", "path": "a.mp4"}, "b": {"type": "video", "path": "b.mp4"}, "p": {"type": "image", "path": "photo.jpg"},
                   "matte": {"type": "video", "path": "matte.mp4"}, "frames": {"type": "frames", "path": "matte/m_%04d.png", "fps": 30}},
        "shots": [
            {"id": "cut", "asset": "a", "start": 0.0, "end": 3.0, "in": 0.5, "camera": {"zoom": [1.15, 1.0], "center": [[0.5, 0.5], [0.5, 0.5]]},
             "cutout": {"matte": "matte", "outline": {"color": [255, 255, 255], "width": 6, "dash": [38, 24], "speed": 140, "offset": 4},
                        "bg": {"zoom": 1.8, "blur": 40, "tint": [150, 200, 255], "tint_mix": 0.5, "posterize": 6}}},
            {"id": "panel", "asset": "p", "start": 3.0, "end": 5.5, "fit": "panel", "transition": {"type": "ghost", "dur": 0.24},
             "panel": {"bg": [28, 84, 200], "title": ["A PANEL TITLE", "IN TWO LINES"], "frame": {"width": 10, "color": [255, 255, 255]}, "caption": "a caption under the frame"}},
            {"id": "split", "asset": "a", "start": 5.5, "end": 8.0, "in": 0.0, "camera": {"zoom": [1.0, 1.15], "center": [[0.5, 0.5], [0.5, 0.5]]}, "transition": {"type": "wipe", "dur": 0.3},
             "fit": "split", "split": {"at": 0.5, "seam": {"color": [255, 255, 255], "width": 6}, "bottom": {"asset": "b", "in": 0.5, "camera": {"zoom": [1.2, 1.0], "center": [[0.5, 0.5], [0.5, 0.5]]}}}},
            {"id": "frames", "asset": "a", "start": 8.0, "end": 11.0, "in": 0.5, "transition": {"type": "dissolve", "dur": 0.3},
             "cutout": {"matte": "frames", "outline": {"color": [255, 230, 120], "width": 8, "dash": [60, 30], "speed": -120, "offset": 8}, "bg": {"zoom": 1.5, "blur": 30, "tint": [120, 170, 240], "posterize": 5}}},
        ],
        "grade": {"look": "natural"},
        "overlays": [
            {"element": "kinetic", "t0": 0.4, "t1": 3.0, "text": "SINCE", "size": 260, "dir": "left", "at": {"x": 480, "y": 760}, "to": {"x": 480, "y": 1150, "size": 64}, "max_width": 780},
            {"element": "text", "t0": 5.8, "t1": 8.0, "x": 480, "y": 1120, "anchor": "m", "text": "typed one letter at a time", "size": 46, "typewriter": 14},
            {"element": "year", "t0": 8.3, "t1": 11.0, "text": "1998", "x": 480, "y": 480, "anchor": "m", "size": 260, "max_width": 700, "hold": 1.2, "out_dur": 0.5},
            {"element": "title", "t0": 8.5, "t1": 11.0, "lines": ["SPACED IN"], "x": 480, "y": 950, "anchor": "m", "size": 84, "tracking": 2, "tracking_in": 36, "tracking_dur": 1.0, "max_width": 800},
        ],
        "encode": {"crf": 20},
        "safe": {"profile": "tiktok"},
    }


def make_demo(d: Path) -> Path:
    """Write the assets, `film.json` and `story.json` into `d`; the path of `film.json`."""
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    make_assets(d)
    out = d / "film.json"
    out.write_text(json.dumps(film_spec(d), indent=1), encoding="utf-8")
    (d / "story.json").write_text(json.dumps(story_spec(d), indent=1), encoding="utf-8")
    return out
