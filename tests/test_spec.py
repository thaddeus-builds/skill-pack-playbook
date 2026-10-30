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
        bad(lambda s: s["overlays"][0].update(lines="x"), "lines must be a list")
        bad(lambda s: s["overlays"][0].update(t0=3, t1=2), "t0 before t1")
        bad(lambda s: s["overlays"][8].update(asset="gone"), "overlays[8].asset")
        bad(lambda s: s["grade"].update(look="neon"), "grade.look")
        bad(lambda s: s["assets"]["a"].update(path="missing.mp4"), "is not a file")
        bad(lambda s: s["audio"]["voice"][0].update(file="missing.wav"), "audio.voice[0].file")
        spec = copy.deepcopy(base)
        spec["shots"][1]["id"] = "s1"
        assert any("used twice" in g for g in S.problems(spec, d))


if __name__ == "__main__":
    _t.main(globals())
