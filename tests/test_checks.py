"""The checks that need no render: type outside the safe area, type on type, voice lines running together, cuts off the beat."""
import copy
import subprocess

import _t
from filmkit import check as C
from filmkit import spec as S
from filmkit.audio import SR


def test_a_good_layout_has_nothing_to_report_and_a_title_in_the_wrong_place_is_found():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"] = [e for e in spec["overlays"] if e["element"] in ("title", "chip")]
        assert C.layout(spec, d) == [], C.layout(spec, d)
        low = copy.deepcopy(spec)
        low["overlays"][0]["y"] = 1500                                                        # TikTok's own caption lives down there
        got = C.layout(low, d)
        assert got and "outside the safe area" in got[0], got
        right = copy.deepcopy(spec)
        right["overlays"][0].update(x=700, size=200, lines=["WIDE WIDE"])                    # past the right edge's buttons
        assert any("outside the safe area" in g for g in C.layout(right, d))
        free = copy.deepcopy(low)
        free["safe"] = {"profile": "full"}
        assert C.layout(free, d) == [], "with no safe-area demand the same place is fine"


def test_max_width_shrinks_a_title_and_a_steps_item_until_it_fits_and_the_check_sees_the_new_size():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        title = {"element": "title", "t0": 0.0, "t1": 3.0, "lines": ["WHO MEASURES", "YOUR GLASS?"], "x": 64, "y": 420, "size": 120}
        spec["overlays"] = [title]
        assert any("outside the safe area" in g for g in C.layout(spec, d)), "at its own size the line runs past the right edge"
        title["max_width"] = 900 - 64
        assert C.layout(spec, d) == [], C.layout(spec, d)
        steps = {"element": "steps", "t0": 0.0, "t1": 3.0, "x": 100, "top": 500, "step": 140, "items": [["01", "MATERIAL PRODUCTION"], ["02", "SHORT"]]}
        spec["overlays"] = [steps]
        assert any("step:MATERIAL PRODU" in g and "outside" in g for g in C.layout(spec, d)), C.layout(spec, d)
        steps["max_width"] = 900 - (100 + 56)
        assert C.layout(spec, d) == [], C.layout(spec, d)
        steps["name_size"] = 40
        del steps["max_width"]
        assert C.layout(spec, d) == [], "a smaller `name_size` fits as well"


def test_two_pieces_of_type_on_each_other_are_found_with_the_time():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"] = [
            {"element": "title", "t0": 0.0, "t1": 3.0, "lines": ["HOURS ON ONE", "SCAN POSITION."], "x": 70, "y": 700, "size": 58, "font": "bold"},
            {"element": "counter", "t0": 0.0, "t1": 3.0, "x": 64, "y": 470, "target": 4, "suffix": "+", "size": 300},      # the number's glyphs reach down into the label
        ]
        got = [g for g in C.layout(spec, d) if "overlap" in g]
        assert got and got[0].startswith("t=") and "counter" in got[0], got
        spec["overlays"][0]["y"] = 840
        assert [g for g in C.layout(spec, d) if "overlap" in g] == [], "moved down, the label is clear of the number"


def test_voice_lines_that_run_together_and_cuts_off_the_beat_are_found():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["audio"]["voice"] = [{"t": 0.5, "file": "vo.wav"}, {"t": 1.2, "file": "vo.wav"}]        # each is 1.2 s long: the first runs into the second
        got = C.timing(spec, d)
        assert any("runs to 1.70s, into the line at 1.20s" in g for g in got), got
        spec["audio"]["voice"] = [{"t": 0.5, "file": "vo.wav"}, {"t": 2.0, "file": "vo.wav"}]
        assert not any("runs to" in g for g in C.timing(spec, d))
        spec["shots"][1].update(start=2.3)
        spec["shots"][0].update(end=2.3)
        assert any("off the beat of 90 BPM" in g for g in C.timing(spec, d)), C.timing(spec, d)
        spec["audio"]["voice"] = [{"t": 5.5, "file": "vo.wav"}]
        assert any("past the end" in g for g in C.timing(spec, d))


if __name__ == "__main__":
    _t.main(globals())
