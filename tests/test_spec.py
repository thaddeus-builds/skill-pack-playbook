"""The film spec's validation: a good spec has no problems, and each way to be wrong is named with where it is."""
import copy

import _t
from filmkit import spec as S


def test_a_good_spec_has_no_problems_and_windows_include_the_transitions():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        assert S.problems(spec, d) == []
        w = S.windows(spec)
        assert w[0] == (0.0, 2.2) and w[1] == (1.8, 4.2) and w[2] == (3.8, 6.0), w          # a dissolve of 0.4 s is centred on the cut at 2.0; a push of 0.4 s on the cut at 4.0


def test_each_way_to_be_wrong_is_named():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        base = _t.film_spec(d)

        def bad(edit, needle, with_files=True):
            spec = copy.deepcopy(base)
            edit(spec)
            got = S.problems(spec, d if with_files else None)
            assert any(needle in g for g in got), (needle, got)

        bad(lambda s: s.update(schema="x"), "schema")
        bad(lambda s: s["canvas"].update(w=1081), "even")
        bad(lambda s: s.update(duration=7.0), "the duration is 7.0")
        bad(lambda s: s["shots"][1].update(start=2.5), "gap or an overlap")
        bad(lambda s: s["shots"][1].update(asset="nope"), "shots[1].asset")
        bad(lambda s: s["shots"][0].update(transition={"type": "dissolve", "dur": 0.2}), "nothing to come from")
        bad(lambda s: s["shots"][1]["transition"].update(type="spin"), "transition.type")
        bad(lambda s: s["shots"][1]["transition"].update(dur=1.5), "longer than half")
        bad(lambda s: s["shots"][1].update(speed=0), "speed")
        bad(lambda s: s["shots"][2].update(fit="stretch"), "fit")
        bad(lambda s: s["overlays"][0].update(element="sparkle"), "overlays[0].element")
        bad(lambda s: s["overlays"][0].update(lines="x"), "lines: must be a list")
        bad(lambda s: s["overlays"][0].update(t0=3, t1=2), "t0 before t1")
        bad(lambda s: s["overlays"][8].update(asset="gone"), "overlays[8].asset")
        bad(lambda s: s["grade"].update(look="neon"), "grade.look")
        bad(lambda s: s["assets"]["a"].update(path="missing.mp4"), "is not a file")
        bad(lambda s: s["audio"]["voice"][0].update(file="missing.wav"), "audio.voice[0].file")
        spec = copy.deepcopy(base)
        spec["shots"][1]["id"] = "s1"
        assert any("used twice" in g for g in S.problems(spec, d))


def test_typed_checks_name_a_wrong_type_or_range_instead_of_crashing_later():
    """Review H3/M8: a NaN, a bool, a string where a number goes, a negative duration, an unknown safe profile were not caught by `validate` and failed deep inside a render."""
    with _t.tmpdir() as d:
        _t.make_assets(d)
        base = _t.film_spec(d)

        def bad(edit, needle):
            spec = copy.deepcopy(base)
            edit(spec)
            got = S.problems(spec, d)
            assert any(needle in g for g in got), (needle, got)

        nan = float("nan")
        bad(lambda s: s.update(duration=nan), "duration")
        bad(lambda s: s.update(duration=1e9), "duration")
        bad(lambda s: s.update(duration=True), "duration")
        bad(lambda s: s.update(bpm=0), "bpm")
        bad(lambda s: s["canvas"].update(fps=0), "canvas.fps")
        bad(lambda s: s["canvas"].update(w=True), "canvas.w")
        bad(lambda s: s["shots"][1]["transition"].update(dur=nan), "transition.dur")
        bad(lambda s: s["shots"][1]["transition"].update(dur=-1), "transition.dur")
        bad(lambda s: s["shots"][1]["transition"].update(dur="0.4"), "transition.dur")
        bad(lambda s: s["shots"][1].update(**{"in": -1}), "shots[1].in")
        bad(lambda s: s["shots"][1].update(camera={"zoom": [1.0]}), "shots[1].camera")
        bad(lambda s: s["shots"][1].update(dim=[0.2]), "shots[1].dim")
        bad(lambda s: s["shots"][1].update(blur=-3), "shots[1].blur")
        bad(lambda s: s["overlays"][0].update(size="big"), "overlays[0].size")
        bad(lambda s: s["overlays"][0].update(tracking=nan), "overlays[0].tracking")
        bad(lambda s: s["overlays"][0].update(font="comic"), "overlays[0].font")
        bad(lambda s: s["overlays"][0].update(color=[300, 0, 0]), "overlays[0].color")
        bad(lambda s: s["overlays"][0].update(t0=nan), "t0 and t1")
        bad(lambda s: s.update(scrim={"top": "x"}), "scrim")
        bad(lambda s: s.update(fade_out={"t": 5}), "fade_out")
        bad(lambda s: s.update(fade_out={"t": 5, "dur": 0}), "fade_out")
        bad(lambda s: s.update(safe={"profile": "myspace"}), "safe.profile")
        bad(lambda s: s.update(safe={"box": [1, 2, 3]}), "safe.box")
        bad(lambda s: s.update(encode={"bitrate": "fast"}), "encode.bitrate")
        bad(lambda s: s.update(encode={"crf": 99}), "encode.crf")
        bad(lambda s: s["audio"].update(lufs="loud"), "audio.lufs")
        bad(lambda s: s["audio"]["voice"][0].update(t=-1), "audio.voice[0]")
        bad(lambda s: s["grade"].update(over={"contrast": 99}), "grade.over.contrast")
        bad(lambda s: s["grade"].update(over={"nope": 1}), "grade.over")


def test_validate_never_raises_on_a_spec_of_the_wrong_shape():
    """The validator is the safety net of the render: whatever it is given, it answers with lines."""
    with _t.tmpdir() as d:
        _t.make_assets(d)
        base = _t.film_spec(d)
        junk = [None, 0, "x", [], [1], {}, {"a": 1}, True, float("nan"), -1]
        for top in ("canvas", "assets", "shots", "overlays", "audio", "grade", "encode", "safe", "scrim", "fade_out", "fonts", "bpm", "duration"):
            for j in junk:
                spec = copy.deepcopy(base)
                spec[top] = j
                got = S.problems(spec, d)
                assert isinstance(got, list) and all(isinstance(x, str) for x in got), (top, j, got)
        for j in junk:
            assert isinstance(S.problems(j, d), list)
        for key in list(base["shots"][1]) + list(base["overlays"][0]):
            for j in junk:
                spec = copy.deepcopy(base)
                spec["shots"][1][key] = j
                S.problems(spec, d)
                spec = copy.deepcopy(base)
                spec["overlays"][0][key] = j
                S.problems(spec, d)
        # elements, shots and assets that are not objects
        for j in junk:
            spec = copy.deepcopy(base)
            spec["shots"][0] = j
            S.problems(spec, d)
            spec = copy.deepcopy(base)
            spec["overlays"][0] = j
            S.problems(spec, d)


def test_a_clip_shorter_than_the_shot_and_a_file_that_is_not_a_picture_are_named():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        base = _t.film_spec(d)
        spec = copy.deepcopy(base)
        spec["shots"][0]["in"] = 500
        assert any("end of the clip" in g for g in S.problems(spec, d)), S.problems(spec, d)
        spec = copy.deepcopy(base)
        (d / "notapic.png").write_text("this is text", encoding="utf-8")
        spec["assets"]["fake"] = {"type": "image", "path": "notapic.png"}
        assert any("not a picture" in g for g in S.problems(spec, d)), S.problems(spec, d)


def test_load_refuses_what_is_not_a_json_object_and_nan():
    with _t.tmpdir() as d:
        for text in ("[1, 2]", "not json", '{"duration": NaN}'):
            f = d / "s.json"
            f.write_text(text, encoding="utf-8")
            try:
                S.load(f)
            except S.FilmkitError:
                continue
            raise AssertionError(f"load accepted {text!r}")


def test_an_explicit_null_is_the_same_as_a_key_not_given():
    """The first client sample carries `"out": null` on its titles: a validator that wanted a number there refused a spec that renders."""
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"][0].update(out=None, max_width=None, max_height=None)
        spec["overlays"][5].update(out=None, name_size=None, max_width=None)
        assert S.problems(spec, d) == [], S.problems(spec, d)


if __name__ == "__main__":
    _t.main(globals())
