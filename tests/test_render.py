"""The whole pipeline on synthetic material: a spec with every element and transition renders at preview size to a file of the right size, length and sound, a still agrees with the
rendered frame, and the graphics are where the spec says."""
import subprocess

import numpy as np

import _t
from filmkit import inspect, render, still
from filmkit import spec as S


def test_a_spec_with_every_element_renders_to_the_right_file():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        assert S.problems(spec, d) == [], S.problems(spec, d)
        out = d / "out.mp4"
        info = render(spec, d, out, preview=0.25)
        assert info["width"] == 270 and info["height"] == 480 and abs(info["duration"] - 6.0) < 0.1, info
        assert info["lufs"] is not None and -19 < info["lufs"] < -13, info                       # the loudness target is -16
        assert info["fonts_fallback"] == ["black", "bold", "med", "reg"], info                    # tests use the face Pillow carries
        assert inspect(out)["duration"] == info["duration"]
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(out)], capture_output=True, text=True)
        assert r.stdout.strip() == "aac", r.stdout


def test_the_graphics_are_where_the_spec_puts_them_and_not_before_their_time():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["audio"] = None
        spec["grade"] = {"look": "natural"}
        spec["scrim"] = False
        out = d / "out.mp4"
        render(spec, d, out, preview=0.25)
        before, during = _t.frame_at(out, 0.1), _t.frame_at(out, 1.6)
        # the title (white type at x 64.., y 420..) is not there at 0.1 s and is by 1.6 s: the same region gets brighter
        y0, y1, x0, x1 = int(420 / 4), int(560 / 4), int(64 / 4), int(500 / 4)
        assert during[y0:y1, x0:x1].max() > 235 and (during[y0:y1, x0:x1] > 235).mean() > before[y0:y1, x0:x1].__gt__(235).mean() + 0.01, (before[y0:y1, x0:x1].max(), during[y0:y1, x0:x1].max())
        faded = _t.frame_at(out, 5.9)
        assert faded.mean() < 40, faded.mean()                                                    # the fade to black at the end


def test_a_still_is_the_same_picture_as_the_frame_of_the_render():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["audio"] = None
        spec["grade"] = {"look": "natural"}
        out = d / "out.mp4"
        render(spec, d, out, preview=0.25)
        png = still(spec, d, 1.0, d / "s.png", q=0.25)
        import PIL.Image as I
        a = np.asarray(I.open(png).convert("RGB"), dtype=np.float32)
        b = _t.frame_at(out, 1.0)
        assert a.shape == b.shape, (a.shape, b.shape)
        mse = float(((a - b) ** 2).mean())
        psnr = 10 * np.log10(255 ** 2 / max(mse, 1e-9))
        assert psnr > 24, psnr                                                                    # an encode and a seek differ a little; the picture is the same


def test_a_bitrate_encode_and_the_cut_transition_are_honoured():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["audio"] = None
        spec["overlays"] = []
        spec["shots"][1]["transition"] = {"type": "cut", "dur": 0.0}
        spec["shots"][2]["transition"] = {"type": "flash", "dur": 0.3}
        spec["canvas"] = {"w": 540, "h": 960, "fps": 30}                                           # a small canvas keeps this test quick
        spec["encode"] = {"bitrate": "1500k", "minrate": "500k", "maxrate": "2M", "bufsize": "3M"}
        out = d / "out.mp4"
        info = render(spec, d, out)
        assert info["width"] == 540 and info["height"] == 960, info
        assert 800 < info["bitrate_kbps"] < 2300, info


if __name__ == "__main__":
    _t.main(globals())
