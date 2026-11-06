"""The story-film features: a ghost whip, a typewriter and spaced-in letters, the serif role with the year and kinetic elements, the panel and split shots, and the presenter cutout. Every
picture here is synthetic (generated clips, a moving ellipse for a matte); nothing is a client's."""
import copy

import numpy as np
from PIL import Image, ImageDraw

import _t
from filmkit import cutout as CO
from filmkit import problems, render, still
from filmkit import spec as S
from filmkit.check import all_checks, context
from filmkit.demo import story_spec
from filmkit.elements import ELEMENTS
from filmkit.transitions import blend


def layer_of(spec, base, t, q=0.25):
    from filmkit.render import overlay_frame
    cx = context(spec, base, q)
    spec = {**spec, "scrim": False}
    return np.asarray(overlay_frame(spec, t, cx))[..., 3].astype(np.float32)


def boxes_at(spec, base, i, t):
    cx = context(spec, base)
    el = spec["overlays"][i]
    return ELEMENTS[el["element"]].boxes(t, el, cx, el)


def test_a_ghost_is_a_quick_whip_that_starts_and_ends_clean_and_smears_at_the_middle():
    ramp = np.tile(np.linspace(0, 255, 64, dtype=np.float32)[None, :, None], (8, 1, 3))
    other = np.zeros_like(ramp)
    assert np.allclose(blend(ramp, other, 0.0, "ghost"), ramp) and np.allclose(blend(ramp, other, 1.0, "ghost"), other)
    mid, plain = blend(ramp, other, 0.5, "ghost"), blend(ramp, other, 0.5, "dissolve")
    assert mid.shape == ramp.shape and np.abs(mid - plain).mean() > 1.0, "the middle of a whip is not the dissolve's"
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["shots"][1]["transition"] = {"type": "ghost", "dur": 0.25}
        assert problems(spec, d) == []
        spec["shots"][1]["transition"] = {"type": "ghost", "dur": 0.8}
        assert any("quick whip" in m for m in problems(spec, d)), problems(spec, d)


def test_a_typewriter_fills_a_line_but_its_box_is_the_whole_lines_and_a_centred_line_does_not_slide():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"] = [{"element": "text", "t0": 0.5, "t1": 3.0, "x": 540, "y": 800, "text": "A LINE TYPED IN", "anchor": "m", "typewriter": 8, "size": 60},
                            {"element": "title", "t0": 0.5, "t1": 5.0, "lines": ["FIRST LINE", "SECOND"], "x": 540, "y": 1000, "anchor": "m", "typewriter": 10, "size": 80}]
        assert problems(spec, d) == [], problems(spec, d)
        early, late = boxes_at(spec, d, 0, 0.8), boxes_at(spec, d, 0, 2.9)
        assert early == late and len(early) == 1, (early, late)
        a, b, c = layer_of(spec, d, 0.9), layer_of(spec, d, 1.5), layer_of(spec, d, 2.9)
        assert 0 < (a > 0).sum() < (b > 0).sum() < (c > 0).sum(), ((a > 0).sum(), (b > 0).sum(), (c > 0).sum())
        cols = lambda m: np.where((m[int(780 * 0.25):int(880 * 0.25)] > 0).any(axis=0))[0]
        assert cols(a).min() >= cols(c).min() - 1, "the first letters sit where they will stay"
        t = boxes_at(spec, d, 1, 0.9)
        assert [n for n, *_ in t] == ["title:FIRST LINE"], t                       # the second line has not begun, so it is not on the screen to be checked
        assert len(boxes_at(spec, d, 1, 3.0)) == 2
        spec["overlays"][0]["typewriter"] = 0
        assert any("typewriter" in m for m in problems(spec, d)), problems(spec, d)


def test_title_letters_ease_from_wide_to_normal_while_it_fades_in_and_the_size_fits_the_widest():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"] = [{"element": "title", "t0": 0.5, "t1": 4.0, "lines": ["TRACKED IN"], "x": 540, "y": 900, "anchor": "m", "size": 90, "tracking": 2, "tracking_in": 40, "tracking_dur": 1.0,
                             "max_width": 900}]
        assert problems(spec, d) == []
        width = lambda t: (lambda b: b[0][3] - b[0][1])(boxes_at(spec, d, 0, t))
        w0, w1, w2 = width(0.75), width(1.2), width(3.0)
        assert w0 > w1 > w2, (w0, w1, w2)
        assert w0 <= 900 + 1, w0                                                    # the widest state still fits max_width
        plain = copy.deepcopy(spec)
        del plain["overlays"][0]["tracking_in"]
        assert abs(width(3.0) - (lambda b: b[0][3] - b[0][1])(boxes_at(plain, d, 0, 3.0))) < 120, "settled, it is the normal line"
        spec["overlays"][0]["tracking_in"] = 1000
        assert any("tracking_in" in m for m in problems(spec, d))


def ink(m, level=20):
    ys, xs = np.where(m > level)
    return (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None


def test_the_serif_role_is_reported_like_the_others_and_its_glyphs_are_checked():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"] = [{"element": "year", "t0": 0.5, "t1": 3.0, "x": 540, "y": 700, "anchor": "m", "text": "1998 \u8d77"}]
        checks = all_checks(spec, d)
        assert "font role serif: no file found, the fallback face is used" in checks["fonts"], checks["fonts"]
        assert any(m.startswith("font serif: no glyph") for m in checks["glyphs"]), checks["glyphs"]
        spec["fonts"] = {"serif": "nowhere.otf"}
        assert any(m.startswith("fonts.serif") for m in problems(spec, d))


def test_kinetic_sweeps_in_from_its_edge_then_settles_into_a_subtitle_where_the_spec_says():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"] = [{"element": "kinetic", "t0": 0.5, "t1": 4.0, "text": "SINCE", "size": 260, "dir": "left", "to": {"x": 540, "y": 1000, "size": 60}, "max_width": 900}]
        assert problems(spec, d) == [], problems(spec, d)
        assert layer_of(spec, d, 0.4).max() == 0, "nothing before its time"
        early, rest, end = ink(layer_of(spec, d, 0.6)), ink(layer_of(spec, d, 1.2)), ink(layer_of(spec, d, 3.0))
        assert early is not None and early[0] < rest[0] + 5 and early[2] < rest[2], (early, rest)      # coming from the left edge
        assert rest[3] - rest[1] > 2.5 * (end[3] - end[1]), (rest, end)                                 # big, then small
        cx, cy = (end[0] + end[2]) / 2 / 0.25, (end[1] + end[3]) / 2 / 0.25
        assert abs(cx - 540) < 30 and abs(cy - 1000) < 40, (cx, cy)
        assert boxes_at(spec, d, 0, 0.7) == [] and len(boxes_at(spec, d, 0, 1.0)) == 1
        (name, x0, y0, x1, y1), = boxes_at(spec, d, 0, 3.0)
        assert abs((x0 + x1) / 2 - 540) < 2 and abs((y0 + y1) / 2 - 1000) < 2 and y1 - y0 < 100, (x0, y0, x1, y1)
        assert (boxes_at(spec, d, 0, 1.0)[0][3] - boxes_at(spec, d, 0, 1.0)[0][1]) > 200
        for dirn in ("right", "top", "bottom"):
            spec["overlays"][0]["dir"] = dirn
            assert layer_of(spec, d, 0.6).max() >= 0 and problems(spec, d) == []
        bad = {**spec["overlays"][0]}
        del bad["to"]
        spec["overlays"] = [bad]
        assert any("to must be" in m for m in problems(spec, d)), problems(spec, d)
        spec["overlays"] = [{**bad, "to": {"x": 540, "y": 1000, "size": 60}, "dir": "up"}]
        assert any("dir" in m for m in problems(spec, d))


def test_year_rises_into_place_holds_and_fades_out_and_the_layout_check_sees_it():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"] = [{"element": "year", "t0": 0.5, "t1": 5.0, "text": "1998", "x": 540, "y": 700, "anchor": "m", "size": 240, "hold": 1.0, "out_dur": 0.5, "rise": 200}]
        assert problems(spec, d) == []
        a, b, c = ink(layer_of(spec, d, 0.7)), ink(layer_of(spec, d, 1.0)), ink(layer_of(spec, d, 2.0))
        assert a is None or a[1] > c[1], (a, c)
        assert c[1] > b[1] - 1 or b[1] >= c[1] - 120, (b, c)
        assert b[1] > c[1], "it is still rising at 1.0 s"
        c = ink(layer_of(spec, d, 2.0), 250)                                              # the type itself, not its shadow
        assert abs((c[0] + c[2]) / 2 / 0.25 - 540) < 8, c
        assert layer_of(spec, d, 3.5).max() == 0, "faded out after the hold"
        assert len(boxes_at(spec, d, 0, 2.0)) == 1 and boxes_at(spec, d, 0, 3.5) == []
        spec["overlays"][0]["x"] = 1000
        assert any("year" in m and "safe" in m for m in (lambda r: r["layout"])(all_checks({**spec, "safe": {"profile": "tiktok"}}, d))), "type off the safe area is named"


def test_a_callout_draws_a_dot_then_a_line_to_a_box_that_the_layout_check_sees_and_names_when_it_leaves_the_canvas():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"] = [{"element": "callout", "t0": 0.5, "t1": 4.0, "x": 300, "y": 900, "label": "FLOOR AREA", "value": "43,246", "unit": "m2", "side": "right", "len": 360, "draw": 0.6}]
        assert problems(spec, d) == [], problems(spec, d)
        dot, line, full = layer_of(spec, d, 0.6), layer_of(spec, d, 0.95), layer_of(spec, d, 2.0)
        assert 0 < (dot > 0).sum() < (line > 0).sum() < (full > 0).sum(), ((dot > 0).sum(), (line > 0).sum(), (full > 0).sum())
        cols = np.where((full > 0).any(axis=0))[0]
        assert cols.min() / 0.25 < 300 and cols.max() / 0.25 > 660, "the line reaches out to the box on the right of the point"
        assert [n for n, *_ in boxes_at(spec, d, 0, 0.8)] == ["~callout"], "while the line is drawing there is no type yet"
        names = [n for n, *_ in boxes_at(spec, d, 0, 2.0)]
        assert names == ["callout", "~callout-line"], names
        x0, y0, x1, y1 = boxes_at(spec, d, 0, 2.0)[0][1:]
        assert x0 >= 660 - 1 and y0 < 900 and x1 > x0 and y1 > y0
        assert layer_of(spec, d, 4.2).max() == 0 or layer_of(spec, d, 4.5).max() == 0, "gone after t1"
        left = copy.deepcopy(spec)
        left["overlays"][0].update(x=800, side="left")
        a, b = boxes_at(left, d, 0, 2.0)[0][1:], boxes_at(spec, d, 0, 2.0)[0][1:]
        assert a[2] <= 800 - 360 + 1 and a[0] < b[0], (a, b)
        wide = copy.deepcopy(spec)
        wide["overlays"][0].update(value="1234567890123", label="A LABEL THAT RUNS ON AND ON")
        assert problems(wide, d) == [] and boxes_at(wide, d, 0, 2.0)[0][3] <= 1081, "the text shrinks to the room the canvas leaves"
        off = copy.deepcopy(spec)
        off["overlays"][0].update(x=1000, side="right")
        assert any("callout" in m for m in all_checks({**off, "safe": {"profile": "tiktok"}}, d)["layout"]), "a box off the safe area is named"
        bad = copy.deepcopy(spec)
        bad["overlays"][0].update(side="up", len=5, draw=0)
        del bad["overlays"][0]["value"]
        msgs = problems(bad, d)
        assert any("side" in m for m in msgs) and any("len" in m for m in msgs) and any("draw" in m for m in msgs), msgs
        bad["overlays"][0].update(side="left", len=300, draw=0.5)
        assert any("value is required" in m for m in problems(bad, d)), problems(bad, d)
        assert ("med", "FLOOR AREA") in ELEMENTS["callout"].texts(spec["overlays"][0]) and ("black", "43,246") in ELEMENTS["callout"].texts(spec["overlays"][0])
        glyph = copy.deepcopy(spec)
        glyph["overlays"][0]["label"] = "\U0001F48A"
        assert all_checks(glyph, d)["glyphs"], "a glyph the face lacks is named like any other type"


def px(png, q=0.25):
    return np.asarray(Image.open(png).convert("RGB"), dtype=np.float32)


def plain(spec):
    """The film with nothing on it that would be graded or shaded: only the picture of the shots."""
    spec = copy.deepcopy(spec)
    spec.update(audio=None, grade={"look": "natural"}, scrim=False, overlays=[], safe={"profile": "full"})
    spec.pop("fade_out", None)
    return spec


def test_a_panel_shot_is_a_colour_a_framed_picture_that_pushes_in_and_type_the_layout_check_sees():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = plain(_t.film_spec(d))
        spec["shots"][2].update(fit="panel", panel={"bg": [28, 84, 200], "title": ["A TITLE", "OF TWO LINES"], "caption": "under the frame", "frame": {"width": 12, "color": [255, 255, 255]}})
        del spec["shots"][2]["camera"]
        assert problems(spec, d) == [], problems(spec, d)
        a, b = px(still(spec, d, 4.2, d / "a.png", q=0.25)), px(still(spec, d, 5.9, d / "b.png", q=0.25))
        assert np.abs(a[2, 2] - [28, 84, 200]).max() < 3 and np.abs(a[-3, -3] - [28, 84, 200]).max() < 3, "a solid colour round it"
        g = S.__dict__["PN"].geometry(spec["shots"][2]["panel"], 1080, 1920)
        ix0, iy0, ix1, iy1 = (v * 0.25 for v in g["inner"])
        assert a[int((iy0 + iy1) / 2), int(ix0 - 3)].min() > 245, "the white frame is just outside the picture"
        gold = lambda im: float((np.abs(im[int(iy0):int(iy1), int(ix0):int(ix1)] - [220, 190, 120]).max(axis=2) < 40).sum())
        assert gold(b) > gold(a) * 1.05, (gold(a), gold(b))                                    # the picture pushes in: the disc in it grows
        top = (slice(int(iy0) - 2, int(iy0)), slice(int(ix0) + 2, int(ix1) - 2))
        assert a[top].min() > 245 and b[top].min() > 245, "the frame itself stays where it is"
        over = S.all_overlays(spec)
        assert [e["element"] for e in over] == ["title", "text"] and over[0]["lines"] == ["A TITLE", "OF TWO LINES"] and over[0]["t0"] == 4.0 and over[0]["t1"] == 6.0, over
        spec = _t.film_spec(d)
        spec["shots"][2].update(fit="panel", panel={"title": ["A TITLE"], "title_y": 1020, "y": 900, "height": 400, "caption": "under"})
        assert any("panel frame" in m for m in all_checks(spec, d)["layout"]), all_checks(spec, d)["layout"]
        assert not any("outside the safe area" in m and "panel frame" in m for m in all_checks({**_t.film_spec(d), "shots": spec["shots"]}, d)["layout"]), "the picture is not type"
        spec["shots"][2]["panel"] = {"nope": 1, "title": []}
        bad = problems(spec, d)
        assert any("panel.nope" in m for m in bad) and any("panel.title" in m for m in bad), bad
        spec["shots"][2].pop("fit")
        assert any(".panel: only a shot with fit: panel" in m for m in problems(spec, d))


def test_a_panel_background_can_run_from_one_colour_to_another_and_a_text_can_have_an_outline():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = plain(_t.film_spec(d))
        spec["shots"][2].update(fit="panel", panel={"bg": [10, 20, 100], "bg2": [200, 220, 250], "title": ["A TITLE"], "caption": "under the frame"})
        del spec["shots"][2]["camera"]
        assert problems(spec, d) == [], problems(spec, d)
        a = px(still(spec, d, 4.2, d / "g.png", q=0.25))
        assert np.abs(a[1, 1] - [10, 20, 100]).max() < 6 and np.abs(a[-2, 1] - [200, 220, 250]).max() < 6, (a[1, 1], a[-2, 1])
        assert 40 < a[a.shape[0] // 2, 1].sum() / 3 < 190, "somewhere between at the middle"
        spec["shots"][2]["panel"]["bg2"] = [300, 0, 0]
        assert any("panel.bg2" in m for m in problems(spec, d)), problems(spec, d)
        # an outline puts dark pixels round white type on a white picture, and none without it
        base = plain(_t.film_spec(d))
        base["overlays"] = [{"element": "text", "t0": 0.0, "t1": 3.0, "text": "WWWW", "x": 540, "y": 900, "anchor": "m", "size": 160, "font": "bold", "alpha": 1.0, "dur": 0.01}]
        for sh in base["shots"][:1]:
            sh["dim"] = [0, 0]
        plainimg = px(still(base, d, 1.0, d / "p.png", q=0.5))
        base["overlays"][0]["stroke"] = {"width": 6, "color": [0, 0, 0]}
        outlined = px(still(base, d, 1.0, d / "o.png", q=0.5))
        assert (outlined.sum(axis=2) < plainimg.sum(axis=2) - 60).sum() > 200, "the outline darkens the pixels round the letters"


def test_what_the_review_found_a_bad_panel_stroke_or_half_is_named_before_rendering_and_a_short_matte_is_counted():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = plain(_t.film_spec(d))
        spec["shots"][2].update(fit="panel", panel={"bg": [28, 84, 200], "margin": 600})
        assert any("framed picture" in m and "canvas" in m for m in problems(spec, d)), problems(spec, d)
        spec["shots"][2]["panel"] = {"bg": [28, 84, 200], "margin": 0}
        assert any("framed picture" in m for m in problems(spec, d)), "the frame would hang over the edge"
        spec = plain(_t.film_spec(d))
        spec["overlays"] = [{"element": "text", "t0": 0.0, "t1": 2.0, "text": "A", "x": 540, "y": 900, "stroke": bad} for bad in ({"color": [0, 0, 0]}, "x", {"width": "a"})]
        bad = problems(spec, d)
        assert sum(".stroke: must be" in m for m in bad) == 3, bad
        spec = plain(_t.film_spec(d))
        spec["shots"][2].update(fit="split", split={"bottom": {"asset": spec["shots"][2]["asset"], "dim": "x", "blur": "y"}})
        bad = problems(spec, d)
        assert any("split.bottom.dim" in m for m in bad) and any("split.bottom.blur" in m for m in bad), bad
        # a numbered sequence shorter than what the shot reads of the clip
        spec = plain(_t.film_spec(d))
        spec["assets"]["mt"] = {"type": "frames", "path": "short/m_%04d.png", "fps": 30}
        (d / "short").mkdir()
        import subprocess
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(d / spec["assets"][spec["shots"][0]["asset"]]["path"])], capture_output=True, text=True).stdout.split()[0].split(",")
        for k in range(1, 6):
            Image.new("L", (int(probe[0]), int(probe[1])), 255).save(d / "short" / f"m_{k:04d}.png")
        spec["shots"][0]["cutout"] = {"matte": "mt"}
        bad = problems(spec, d)
        assert any("the sequence has 5 pictures" in m for m in bad), bad


def test_the_subject_can_be_placed_apart_from_a_shifted_backdrop_and_trail_ghosts_that_fade():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        ellipse_matte(d / "still_matte.png")
        spec = plain(_t.film_spec(d))
        spec["assets"]["matte"] = {"type": "image", "path": "still_matte.png"}
        spec["shots"][0].update(cutout={"matte": "matte", "outline": False, "fg": {"scale": 0.5, "dx": -0.25, "dy": 0.0}, "echo": {"n": 3, "dx": -80, "alpha": 0.6, "dur": 0.5},
                                        "bg": {"zoom": 2.0, "blur": 20, "dx": 0.1, "dy": 0.0}})
        assert problems(spec, d) == [], problems(spec, d)
        t0 = spec["shots"][0]["start"]
        near = px(still(spec, d, t0 + 0.05, d / "e0.png", q=0.25))
        late = px(still(spec, d, t0 + 0.9, d / "e1.png", q=0.25))
        assert np.abs(near - late).mean() > 0.2, "the picture changes"
        co = S.__dict__["CO"]
        fg, m = co.place(np.full((40, 20, 3), 200, np.float32), np.full((40, 20), 255, np.uint8), {"scale": 0.5, "dx": 0.25, "dy": 0.0}, 20, 40)
        assert m[:, :5].max() == 0 and m[25:, 10:18].min() == 255 and m[:15].max() == 0, "half size, bottom centre, moved right: empty above and to the left"
        back = np.zeros((40, 20, 3), np.float32)
        ghosted = co.echo(back, np.full((40, 20, 3), 255, np.float32), np.full((40, 20), 255, np.uint8), {"n": 2, "dx": -4, "alpha": 0.5, "dur": 1.0}, 0.0, 1.0)
        assert ghosted.max() > 0 and co.echo(back, back, np.zeros((40, 20), np.uint8), {"n": 2, "dx": -4, "dur": 1.0}, 1.5, 1.0) is back, "ghosts at the start, none after `dur`"
        spec["shots"][0]["cutout"]["fg"] = {"scale": 9}
        spec["shots"][0]["cutout"]["echo"] = {"n": 0}
        bad = problems(spec, d)
        assert any("cutout.fg.scale" in m for m in bad) and any("cutout.echo.n" in m for m in bad), bad


def test_a_split_shot_stacks_two_clips_each_with_its_own_in_and_camera_and_a_seam_between():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = plain(_t.film_spec(d))
        spec["shots"][2].update(fit="split", asset="a", split={"at": 0.5, "seam": {"color": [255, 255, 255], "width": 8}, "bottom": {"asset": "p", "camera": {"zoom": [1.0, 1.0]}}})
        del spec["shots"][2]["camera"]
        assert problems(spec, d) == [], problems(spec, d)
        im = px(still(spec, d, 5.0, d / "s.png", q=0.25))
        h = im.shape[0]
        assert np.abs(im[h // 2 - 1:h // 2 + 1] - 255).max() < 2, "a seam across the join"
        gold = lambda part: float((np.abs(part - [220, 190, 120]).max(axis=2) < 40).mean())
        assert gold(im[h // 2 + 6:]) > 0.02 and gold(im[:h // 2 - 6]) == 0.0, "the photo is below, the clip above"
        spec["shots"][2]["split"]["bottom"]["asset"] = "nope"
        spec["shots"][2]["split"]["at"] = 0.95
        bad = problems(spec, d)
        assert any("split.bottom.asset" in m for m in bad) and any("split.at" in m for m in bad), bad
        spec["shots"][2]["split"] = {"seam": {}}
        assert any("a split shot needs" in m for m in problems(spec, d))
        spec["shots"][2].update(fit="fill")
        assert any("only a shot with fit: split" in m for m in problems(spec, d))


def ellipse_matte(path, size=(720, 1280)):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse((size[0] / 2 - 160, size[1] * 0.55 - 380, size[0] / 2 + 160, size[1] * 0.55 + 380), fill=255)
    m.save(path)


def test_the_cutout_keeps_the_subject_sharp_on_a_flat_tinted_backdrop_with_marching_dashes_on_its_edge():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        ellipse_matte(d / "still_matte.png")
        spec = plain(_t.film_spec(d))
        spec["assets"]["m"] = {"type": "image", "path": "still_matte.png"}
        spec["shots"][0].update(camera={"zoom": [1.0, 1.0]}, cutout={"matte": "m", "outline": {"color": [255, 255, 255], "width": 6, "dash": [40, 40], "speed": 200, "offset": 0},
                                                                          "bg": {"zoom": 1.8, "blur": 40, "tint": [10, 10, 10], "tint_mix": 1.0}})
        assert problems(spec, d) == [], problems(spec, d)
        a, b = px(still(spec, d, 0.5, d / "a.png", q=0.25)), px(still(spec, d, 0.8, d / "b.png", q=0.25))
        assert np.abs(a[3, 3] - 10).max() < 3, a[3, 3]                                          # outside the subject: the tint, flat
        h, w = a.shape[:2]
        inside = a[int(h * 0.45):int(h * 0.65), int(w * 0.4):int(w * 0.6)]
        assert inside.std() > 20 and inside.mean() > 60, (inside.std(), inside.mean())          # the subject: the clip's own picture
        white = lambda im: (im.min(axis=2) > 235)
        wa, wb = white(a), white(b)
        assert wa.sum() > 80 and abs(int(wa.sum()) - int(wb.sum())) < 0.4 * wa.sum(), (wa.sum(), wb.sum())    # a dashed line of about the same length
        assert (wa & wb).sum() < 0.7 * wa.sum(), "and the dashes have moved on in 0.3 s"
        ys, xs = np.where(wa)
        cy, cx_ = h * 0.55, w / 2
        r = np.hypot((xs - cx_) / (160 * 1.5 * 0.25), (ys - cy) / (380 * 1.5 * 0.25))      # the matte is 720 wide, the canvas 1080: 1.5, at a quarter size
        assert np.median(np.abs(r - 1)) < 0.12, "the dashes lie on the matte's edge"
        spec["shots"][0]["cutout"]["outline"] = False
        c = px(still(spec, d, 0.5, d / "c.png", q=0.25))
        assert white(c).sum() < 0.3 * wa.sum(), "no outline when it is switched off"


def test_a_matte_can_be_a_video_or_a_picture_sequence_and_they_agree_and_a_wrong_one_is_named():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = plain(story_spec())
        spec["shots"] = spec["shots"][:1]
        spec["duration"] = 3.0
        spec["shots"][0]["cutout"]["outline"] = False
        assert problems(spec, d) == [], problems(spec, d)
        video = px(still(spec, d, 1.0, d / "v.png", q=0.25))
        spec["shots"][0]["cutout"]["matte"] = "frames"
        assert problems(spec, d) == [], problems(spec, d)
        seq = px(still(spec, d, 1.0, d / "f.png", q=0.25))
        assert np.abs(video - seq).mean() < 4, np.abs(video - seq).mean()                       # the same matte, read two ways
        spec["assets"]["tiny"] = {"type": "image", "path": "photo.jpg"}
        spec["shots"][0]["cutout"]["matte"] = "tiny"
        assert any("same size" in m for m in problems(spec, d)), problems(spec, d)
        spec["shots"][0]["cutout"] = {"matte": "nope", "outline": {"width": 0, "dash": [1]}, "bg": {"zoom": 0.5, "posterize": 1}, "extra": 1}
        assert len(problems(spec, d)) >= 1
        spec["shots"][0]["cutout"] = {"matte": "frames", "outline": {"width": 0, "dash": [1], "color": [1]}, "bg": {"zoom": 0.5, "posterize": 1}}
        bad = problems(spec, d)
        assert all(any(k in m for m in bad) for k in ("outline.width", "outline.dash", "outline.color", "bg.zoom", "bg.posterize")), bad
        spec["shots"][0]["cutout"] = {"matte": "frames"}
        spec["shots"][0]["fit"] = "card"
        assert any("only a fit: fill shot" in m for m in problems(spec, d))
        spec["shots"][0].pop("fit")
        spec["assets"]["frames"]["path"] = "matte/none_%04d.png"
        assert any("is not a file" in m for m in problems(spec, d)), problems(spec, d)
        spec["assets"]["frames"]["path"] = "matte/m_0001.png"
        assert any("numbered pattern" in m for m in problems(spec, d))


def test_the_outline_is_walked_once_round_the_edge_and_dashes_are_laid_along_it():
    m = np.zeros((60, 80), bool)
    m[10:40, 20:70] = True
    pts = CO.trace(m)
    assert len(pts) == 2 * (30 + 50) - 4 and pts[0] == (10, 20) and len(set(pts)) == len(pts), (len(pts), pts[:3])
    cs = CO.contours(np.pad(m, 0))
    assert len(cs) == 1
    tiny = m.copy()
    tiny[50:52, 5:7] = True
    assert len(CO.contours(tiny)) == 1, "a speck is not a subject"
    ring = np.array([[np.cos(a) * 100, np.sin(a) * 100] for a in np.linspace(0, 2 * np.pi, 628, endpoint=False)])
    runs = CO.dashes(ring, 30, 20, 0)
    lit = sum(len(r) - 1 for r in runs) / 628
    assert 0.5 < lit < 0.7 and 11 <= len(runs) <= 14, (lit, len(runs))                          # 3 in 5 on, 628 / 50 dashes
    moved = CO.dashes(ring, 30, 20, 25)
    assert not np.allclose(moved[1][0], runs[1][0]), "the phase slides them"
    out = CO.outward(ring, 10)
    assert abs(np.linalg.norm(out, axis=1).mean() - 110) < 1.0 and abs(np.linalg.norm(CO.outward(ring[::-1].copy(), 10), axis=1).mean() - 110) < 1.0, "outward is out whichever way it was walked"


def test_the_story_demo_validates_checks_clean_and_renders_a_preview():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = story_spec()
        assert problems(spec, d) == [], problems(spec, d)
        checks = all_checks(spec, d)
        assert checks["layout"] == [] and checks["glyphs"] == [] and checks["timing"] == [], checks
        info = render(spec, d, d / "story.mp4", preview=0.25)
        assert info["width"] == 270 and abs(info["duration"] - 11.0) < 0.1, info
        for t in (0.3, 1.0, 3.2, 4.5, 7.0, 9.5):
            still(spec, d, t, d / f"{t}.png", q=0.25)


if __name__ == "__main__":
    _t.main(globals())
