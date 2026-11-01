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


def test_a_counter_a_text_and_a_chip_shrink_to_max_width_and_a_title_to_max_height():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        counter = {"element": "counter", "t0": 0.0, "t1": 3.0, "x": 64, "y": 470, "target": 12000, "suffix": "HRS", "size": 300, "hold": 0.5}
        spec["overlays"] = [counter]
        assert any("counter" in g and "outside" in g for g in C.layout(spec, d)), "a big number with a suffix runs past the right edge"
        counter["max_width"] = 900 - 64
        assert C.layout(spec, d) == [], C.layout(spec, d)
        text = {"element": "text", "t0": 0.0, "t1": 3.0, "x": 64, "y": 600, "text": "A TAGLINE THAT IS TOO LONG HERE", "size": 40, "tracking": 7}
        spec["overlays"] = [text]
        assert any("outside" in g for g in C.layout(spec, d))
        text["max_width"] = 900 - 64
        assert C.layout(spec, d) == [], C.layout(spec, d)
        chip = {"element": "chip", "t0": 0.0, "t1": 3.0, "x": 64, "y": 350, "text": "A SECTION TAG THAT IS TOO LONG FOR IT"}
        spec["overlays"] = [chip]
        assert any("outside" in g for g in C.layout(spec, d))
        chip["max_width"] = 900 - 64
        assert C.layout(spec, d) == [], C.layout(spec, d)
        title = {"element": "title", "t0": 0.0, "t1": 3.0, "lines": ["ONE", "TWO", "THREE", "FOUR"], "x": 64, "y": 1000, "size": 80}
        spec["overlays"] = [title]
        assert any("outside" in g for g in C.layout(spec, d)), "four lines of 80 px from y 1000 end below the safe area"
        title["max_height"] = 1250 - 1000
        assert C.layout(spec, d) == [], C.layout(spec, d)


def test_a_logo_has_a_box_the_check_sees_and_max_height_narrows_a_square_mark():
    from PIL import Image
    with _t.tmpdir() as d:
        _t.make_assets(d)
        Image.new("RGBA", (400, 400), (46, 139, 216, 255)).save(d / "square.png")
        spec = _t.film_spec(d)
        spec["assets"]["sq"] = {"type": "image", "path": "square.png"}
        title = {"element": "title", "t0": 0.0, "t1": 3.0, "lines": ["A HOOK", "IN TWO LINES."], "x": 64, "y": 420, "size": 112}
        logo = {"element": "logo", "t0": 0.0, "t1": 3.0, "asset": "sq", "x": 64, "y": 250, "width": 280}
        spec["overlays"] = [title, logo]
        got = [g for g in C.layout(spec, d) if "overlap" in g]
        assert got and "logo:sq" in got[0], ("a 280 px wide square mark is 280 px tall and sits on the hook", C.layout(spec, d))
        logo["max_height"] = 150
        assert [g for g in C.layout(spec, d) if "overlap" in g] == [], C.layout(spec, d)
        wide = {"element": "logo", "t0": 0.0, "t1": 3.0, "asset": "logo", "x": 64, "y": 250, "width": 280, "max_height": 150}
        spec["overlays"] = [title, wide]
        assert [g for g in C.layout(spec, d) if "overlap" in g] == [], "a wordmark keeps its width: max_height does not touch what already fits"


def test_type_that_has_faded_out_is_no_longer_checked_against_what_comes_after():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        first = {"element": "title", "t0": 0.0, "t1": 5.0, "lines": ["FIRST", "LINES"], "x": 64, "y": 500, "size": 100, "out": 1.0}
        second = {"element": "title", "t0": 2.5, "t1": 5.0, "lines": ["SECOND", "LINES"], "x": 64, "y": 500, "size": 100}
        spec["duration"] = 6.0
        spec["overlays"] = [first, second]
        assert [g for g in C.layout(spec, d) if "overlap" in g] == [], "the first has left by 2.5 s: nothing to overlap"
        del first["out"]
        assert any("overlap" in g for g in C.layout(spec, d)), "without an exit the same two lines are on each other"
        steps = {"element": "steps", "t0": 0.0, "t1": 5.0, "x": 100, "top": 500, "step": 100, "items": [["01", "FIRST"], ["02", "SECOND"]], "out": 1.0}
        spec["overlays"] = [steps, {**second, "y": 560}]
        assert [g for g in C.layout(spec, d) if "overlap" in g] == [], "a steps list that has left is not checked either"


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


def _painted(el, cx, t, size):
    """The bounding box of what `draw` paints for one element at time `t`, in design pixels."""
    from PIL import Image
    from filmkit.elements import ELEMENTS
    layer = Image.new("RGBA", (cx.W, cx.H), (0, 0, 0, 0))
    ELEMENTS[el["element"]].draw(layer, t, el, cx, el)
    bb = layer.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    return bb


def test_the_boxes_the_check_reads_contain_the_ink_the_draw_paints_descenders_and_all_anchors_included():
    """Review M1/H1: the box was `size` tall from `y` whatever the face; a descender, a counter's bottom or an anchor other than l were outside or beside it. And the line itself was clipped at rest."""
    from filmkit.elements import ELEMENTS
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        cx = C.context(spec, d)
        els = [
            {"element": "title", "t0": 0.0, "t1": 5.0, "lines": ["gypsy jqp", "Quickly, Egg"], "x": 64, "y": 400, "size": 124},
            {"element": "title", "t0": 0.0, "t1": 5.0, "lines": ["gypsy jqp"], "x": 540, "y": 800, "size": 90, "anchor": "m"},
            {"element": "title", "t0": 0.0, "t1": 5.0, "lines": ["gypsy jqp"], "x": 900, "y": 1000, "size": 90, "anchor": "r", "tracking": 6},
            {"element": "text", "t0": 0.0, "t1": 5.0, "x": 100, "y": 1200, "text": "pqrstuvwxyz, gypsy", "size": 60},
            {"element": "counter", "t0": 0.0, "t1": 5.0, "x": 64, "y": 500, "target": 4, "suffix": "+", "size": 300, "hold": 0.5},
        ]
        for el in els:
            t = 3.0
            bb = _painted(el, cx, t, 0)
            boxes = ELEMENTS[el["element"]].boxes(t, el, cx, el)
            ux0, uy0, ux1, uy1 = min(b[1] for b in boxes), min(b[2] for b in boxes), max(b[3] for b in boxes), max(b[4] for b in boxes)
            assert bb is not None
            assert bb[0] >= ux0 - 6 and bb[2] <= ux1 + 6 and bb[1] >= uy0 - 4 and bb[3] <= uy1 + 8, (el["element"], el.get("anchor"), bb, (ux0, uy0, ux1, uy1))   # 8: the drop shadow
        # the descender of the last title line is painted: its ink reaches the bottom of its box
        bb = _painted(els[1], cx, 3.0, 0)
        from PIL import Image, ImageDraw
        ref = Image.new("L", (1080, 400), 0)
        ImageDraw.Draw(ref).text((0, 0), "gypsy jqp", font=cx.font("black", 90), fill=255)
        rb = ref.point(lambda v: 255 if v > 8 else 0).getbbox()
        assert abs((bb[3] - bb[1]) - (rb[3] - rb[1])) <= 6, ((bb[3] - bb[1]), (rb[3] - rb[1]))             # the whole glyph at rest: nothing cut off the bottom


def test_a_character_the_face_has_no_glyph_for_is_named_and_ok_turns_false():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"] = [{"element": "title", "t0": 0.0, "t1": 3.0, "lines": ["HEALTH \u5065\u5eb7 OK"], "x": 64, "y": 420, "size": 100}]
        got = C.glyphs(spec, d)
        assert got and "\u5065" in got[0] and "font black" in got[0], got
        spec["overlays"][0]["lines"] = ["PLAIN CAPITALS 123"]
        assert C.glyphs(spec, d) == []


def test_a_safe_box_the_caller_gives_is_used_as_it_is_and_a_profile_scales_with_the_canvas_and_a_typo_is_a_problem():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["canvas"] = {"w": 720, "h": 1280, "fps": 30}
        spec["safe"] = {"box": [40, 160, 640, 1100]}
        assert C.safe_box(spec) == [40.0, 160.0, 640.0, 1100.0]
        spec["safe"] = {"profile": "tiktok"}
        box = C.safe_box(spec)
        assert abs(box[0] - 60 * 720 / 1080) < 1e-6 and abs(box[3] - 1250 * 1280 / 1920) < 1e-6, box
        spec["safe"] = {"profile": "tik_tok"}
        assert any("safe.profile" in x for x in S.problems(spec, d)), S.problems(spec, d)


def test_a_rule_or_brackets_beyond_the_canvas_are_found_and_may_sit_on_type():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"] = [{"element": "rule", "t0": 0.0, "t1": 3.0, "x0": 100, "x1": 1300, "y": 1300}, {"element": "title", "t0": 0.0, "t1": 3.0, "lines": ["ON THE RULE"], "x": 160, "y": 1280, "size": 60}]
        got = C.layout(spec, d)
        assert any("rule" in g and "outside the canvas" in g for g in got), got
        assert not any("overlap" in g for g in got), "a rule may sit under type"
        steps = {"element": "steps", "t0": 0.0, "t1": 3.0, "x": 30, "top": 500, "step": 190, "items": [["01", "FIRST"]]}
        spec["overlays"] = [steps]
        got = C.layout(spec, d)
        assert any("step-dot" in g and "outside the safe area" in g for g in got), got                   # the rail's dot was invisible to the check


if __name__ == "__main__":
    _t.main(globals())
