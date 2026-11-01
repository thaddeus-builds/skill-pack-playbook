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


def test_a_floor_is_met_by_encoding_again_with_a_higher_target_and_never_above_the_maxrate():
    from filmkit.render import kbps, meet_floor
    assert kbps("10M") == 10000 and kbps("8500k") == 8500 and kbps("9000000") == 9000
    enc = {"bitrate": "10M", "minrate": "8500k", "maxrate": "12M"}
    calls = []

    def again(ratio):
        def f(target):
            calls.append(round(target))
            return {"video_kbps": target * ratio}
        return f
    ok = meet_floor({"video_kbps": 9100}, enc, again(0.8))
    assert calls == [] and ok["floor_met"] and ok["video_kbps"] == 9100, "already over the floor: nothing is encoded again"
    got = meet_floor({"video_kbps": 8300}, enc, again(0.8))
    assert len(calls) == 1 and 10000 < calls[0] <= 12000 and got["floor_met"] and got["video_kbps"] >= 8500, (calls, got)
    calls.clear()
    stuck = meet_floor({"video_kbps": 7000}, enc, again(0.5))
    assert calls == [12000] and not stuck["floor_met"] and stuck["floor_kbps"] == 8500, (calls, stuck)           # the target went to the cap at once; a second try at the cap would change nothing


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


def _colour_film(d, look="natural", over=None):
    """A film of one picture made of flat bands of known colours, nothing on it, no sound."""
    from PIL import Image
    colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (200, 150, 120), (128, 128, 128)]
    im = Image.new("RGB", (270, 480))
    for k, c in enumerate(colours):
        im.paste(c, (0, k * 60, 270, (k + 1) * 60))
    im.save(d / "bands.png")
    grade = {"look": look}
    if over:
        grade["over"] = over
    spec = {"schema": "filmkit.film/1", "id": "colour", "canvas": {"w": 270, "h": 480, "fps": 10}, "duration": 1.0, "assets": {"p": {"type": "image", "path": "bands.png"}},
            "shots": [{"id": "s", "asset": "p", "start": 0.0, "end": 1.0}], "grade": grade, "scrim": False, "encode": {"crf": 12}}
    return spec, colours


def _decoded_as_709(path, t=0.5):
    """The frame the way a player that takes untagged HD as BT.709 decodes it."""
    import io
    from PIL import Image
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1", "-vf", "scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24", "-f", "image2pipe", "-vcodec", "png", "-"],
                         capture_output=True, check=True).stdout
    return np.asarray(Image.open(io.BytesIO(out)).convert("RGB"), dtype=np.int32)


def test_the_colours_play_as_graded_on_a_player_that_reads_bt709_and_the_file_says_so():
    """Review H2: the pictures were converted with BT.601 and carried no tags, so a pure green played 40 levels off on most players."""
    import PIL.Image as I
    with _t.tmpdir() as d:
        spec, colours = _colour_film(d)
        out = d / "c.mp4"
        info = render(spec, d, out)
        assert info["color_space"] == "bt709" and info["color_range"] == "tv", info
        frame = _decoded_as_709(out)
        for k, c in enumerate(colours):
            patch = frame[k * 60 + 20:k * 60 + 40, 100:170].reshape(-1, 3).mean(0)
            assert float(np.abs(patch - np.array(c)).max()) < 8, (c, patch)                    # a 601 conversion moved a channel by 40
        # the filters that sit in front of the conversion (vignette, grain) must not bring a 601 conversion in: the render agrees with the still, which never goes through YUV
        spec, _ = _colour_film(d, over={"vignette": 0.6, "grain": 4})
        render(spec, d, d / "v.mp4")
        ref = np.asarray(I.open(still(spec, d, 0.5, d / "v.png")).convert("RGB"), dtype=np.int32)
        got = _decoded_as_709(d / "v.mp4")
        for k in range(len(colours)):
            a = ref[k * 60 + 20:k * 60 + 40, 100:170].reshape(-1, 3).mean(0)
            b = got[k * 60 + 20:k * 60 + 40, 100:170].reshape(-1, 3).mean(0)
            assert float(np.abs(a - b).max()) < 12, (k, a, b)


def test_a_render_never_overwrites_a_file_the_film_reads_and_names_a_missing_folder_at_once():
    with _t.tmpdir() as d:
        spec, _ = _colour_film(d)
        before = (d / "bands.png").read_bytes()
        for out in (d / "bands.png", d / "." / "bands.png"):
            try:
                render(spec, d, out)
            except _t.FilmkitError as e:
                assert "file the film reads" in str(e), e
            else:
                raise AssertionError("rendered over an input")
        assert (d / "bands.png").read_bytes() == before
        try:
            render(spec, d, d / "nodir" / "x.mp4")
        except _t.FilmkitError as e:
            assert "is not there" in str(e), e
        else:
            raise AssertionError("no error for a missing folder")


def test_a_still_past_the_end_of_a_short_clip_is_its_last_frame_as_in_the_render_and_a_time_outside_the_film_is_refused():
    with _t.tmpdir() as d:
        _t.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=270x480:rate=10:duration=1", "-pix_fmt", "yuv420p", str(d / "short.mp4"))
        spec = {"schema": "filmkit.film/1", "id": "short", "canvas": {"w": 270, "h": 480, "fps": 10}, "duration": 3.0, "assets": {"a": {"type": "video", "path": "short.mp4"}},
                "shots": [{"id": "s", "asset": "a", "start": 0.0, "end": 3.0}], "grade": {"look": "natural"}, "scrim": False}
        import PIL.Image as I
        late = np.asarray(I.open(still(spec, d, 2.5, d / "late.png")).convert("RGB"), dtype=np.float32)
        end = np.asarray(I.open(still(spec, d, 0.9, d / "end.png")).convert("RGB"), dtype=np.float32)
        assert late.mean() > 20 and abs(late.mean() - end.mean()) < 6, (late.mean(), end.mean())          # not black: the last frame is held
        for bad in (-1.0, 3.0, 100.0, float("nan")):
            try:
                still(spec, d, bad, d / "x.png")
            except _t.FilmkitError:
                continue
            raise AssertionError(f"a still at {bad} was made")


def test_a_work_folder_with_filter_syntax_in_its_name_still_renders_and_a_failed_child_is_named():
    with _t.tmpdir() as d:
        spec, _ = _colour_film(d)
        info = render(spec, d, d / "o.mp4", workdir=d / "w:colon,comma[1] it's", preview=1.0)
        assert info["width"] == 270, info
        from filmkit import grade as G
        assert G.escape("a:b,c[d]'e\\f") == "a\\:b\\,c\\[d\\]\\'e\\\\f"


def test_a_clip_with_a_non_square_pixel_is_decoded_at_its_displayed_shape_and_an_hdr_clip_is_noted():
    from filmkit.media import probe
    from filmkit.render import make_ctx, make_shots
    with _t.tmpdir() as d:
        _t.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=240x270:rate=10:duration=1", "-vf", "setsar=2", "-pix_fmt", "yuv420p", str(d / "sar.mp4"))
        _t.ffmpeg("-f", "lavfi", "-i", "testsrc2=size=270x480:rate=10:duration=1", "-pix_fmt", "yuv420p", "-x264-params", "transfer=arib-std-b67:colorprim=bt2020:colormatrix=bt2020nc", str(d / "hdr.mp4"))
        assert probe(d / "sar.mp4")["w"] == 480 and probe(d / "sar.mp4")["h"] == 270, probe(d / "sar.mp4")
        assert probe(d / "hdr.mp4")["hdr"] is True
        spec = {"schema": "filmkit.film/1", "id": "sar", "canvas": {"w": 270, "h": 480, "fps": 10}, "duration": 2.0,
                "assets": {"a": {"type": "video", "path": "sar.mp4"}, "h": {"type": "video", "path": "hdr.mp4"}},
                "shots": [{"id": "s1", "asset": "a", "start": 0.0, "end": 1.0}, {"id": "s2", "asset": "h", "start": 1.0, "end": 2.0}], "grade": {"look": "natural"}, "scrim": False}
        cx = make_ctx(spec, d, 1.0)
        shots = make_shots(spec, cx)
        frame = shots[0].source_frame()
        assert frame.shape == (270, 480, 3), frame.shape
        assert shots[0].still_source(0.3).shape == (270, 480, 3)
        assert any("HDR" in n for n in cx.notes), cx.notes
        for sh in shots:
            sh.close()


def test_a_cut_and_a_window_that_starts_a_hair_after_a_frame_choose_the_same_shot_as_the_stream_counts_from():
    from filmkit.render import footage_frame

    class FakeShot:
        def __init__(self, start, end, name, transition=None):
            self.start, self.end, self.spec, self.name = start, end, {"start": start, "transition": transition}, name

        def frame(self, t, still=False):
            return np.full((2, 2, 3), 10.0 if self.name == "a" else 200.0)
    a, b = FakeShot(0.0, 1.8800000000000001, "a"), FakeShot(1.8800000000000001, 4.0, "b", {"type": "cut", "dur": 0.0})
    assert footage_frame({}, [a, b], 47 / 25)[0, 0, 0] == 200.0, "frame 47 of 25 fps is 1.88 s: the second shot has begun"
    assert footage_frame({}, [a, b], 46 / 25)[0, 0, 0] == 10.0


def test_an_overlay_that_cannot_be_drawn_fails_before_any_frame_with_its_place_in_the_spec():
    with _t.tmpdir() as d:
        spec, _ = _colour_film(d)
        spec["overlays"] = [{"element": "logo", "t0": 0.0, "t1": 1.0, "asset": "p", "x": 10, "y": 10, "width": 100}]
        import filmkit.elements as E
        real = E.Logo.draw
        E.Logo.draw = classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        try:
            try:
                render(spec, d, d / "o.mp4")
            except _t.FilmkitError as e:
                assert "overlays[0] (logo)" in str(e) and "boom" in str(e), e
            else:
                raise AssertionError("no error")
        finally:
            E.Logo.draw = real


def test_the_films_tempo_is_the_beds_unless_the_music_names_its_own_and_the_sound_is_made_before_any_frame():
    import filmkit.audio as A
    with _t.tmpdir() as d:
        spec, _ = _colour_film(d)
        _t.ffmpeg("-f", "lavfi", "-i", "sine=f=220:r=44100:d=0.5", "-ac", "1", str(d / "vo.wav"))
        spec["bpm"] = 120
        spec["audio"] = {"music": {"bed": True}, "lufs": -16}
        seen = []
        real = A.bed
        A.bed = lambda dur, bpm=90, *a, **k: (seen.append(bpm), real(dur, bpm, *a, **k))[1]
        try:
            render(spec, d, d / "o.mp4", preview=1.0)
            spec["audio"] = {"music": {"bed": True, "bpm": 100}}
            render(spec, d, d / "o2.mp4", preview=1.0)
        finally:
            A.bed = real
        assert seen == [120, 100], seen
        _t.ffmpeg("-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.5", str(d / "silent.wav"))
        spec["audio"] = {"voice": [{"t": 0.1, "file": "silent.wav"}]}
        frames = []
        try:
            render(spec, d, d / "o3.mp4", preview=1.0, progress=lambda k, n: frames.append(k))
        except _t.FilmkitError as e:
            assert "silent" in str(e), e
        else:
            raise AssertionError("a silent voice line was rendered")
        assert frames == [], "the sound failed before the first frame was made"


if __name__ == "__main__":
    _t.main(globals())
