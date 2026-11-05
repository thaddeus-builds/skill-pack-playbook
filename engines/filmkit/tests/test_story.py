"""The story-film features: a ghost whip, a typewriter and spaced-in letters, the serif role with the year and kinetic elements, the panel and split shots, and the presenter cutout. Every
picture here is synthetic (generated clips, a moving ellipse for a matte); nothing is a client's."""
import copy

import numpy as np
from PIL import Image

import _t
from filmkit import problems, still
from filmkit import spec as S
from filmkit.check import all_checks, context
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


if __name__ == "__main__":
    _t.main(globals())
