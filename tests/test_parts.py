"""The small parts: transitions at their ends, the grade's LUT, the audio synthesis and mix."""
import numpy as np

import _t
from filmkit import audio, grade
from filmkit.transitions import TYPES, blend


def test_every_transition_starts_on_the_first_frame_and_ends_on_the_second():
    a = np.full((8, 6, 3), 10.0)
    b = np.full((8, 6, 3), 200.0)
    for kind in TYPES:
        if kind == "cut":
            continue
        assert np.allclose(blend(a, b, 0.0, kind), a), kind
        assert np.allclose(blend(a, b, 1.0, kind), b), kind
        mid = blend(a, b, 0.5, kind)
        assert mid.shape == a.shape, kind
    mid = blend(a, b, 0.5, "flash")
    assert mid.mean() > blend(a, b, 0.5, "dissolve").mean(), "the flash pulses white at the middle"
    assert blend(a, b, 0.5, "dip").mean() < 1.0, "dip goes through black at the middle"
    assert np.allclose(blend(a, b, 0.5, "cut"), b)


def test_the_grade_lut_is_a_valid_cube_and_the_natural_look_leaves_colour_alone():
    with _t.tmpdir() as d:
        p = grade.write_cube(d / "n.cube", grade.look("natural"), size=5)
        lines = p.read_text().splitlines()
        assert lines[1] == "LUT_3D_SIZE 5" and len(lines) == 2 + 125, len(lines)
        vals = np.array([[float(x) for x in ln.split()] for ln in lines[2:]])
        g = np.linspace(0, 1, 5)
        r = np.tile(g, 25)                                                                      # red varies fastest
        assert np.allclose(vals[:, 0], r, atol=1e-5), "the natural look is the identity"
        q = grade.write_cube(d / "t.cube", grade.look("teal_warm_soft"), size=5)
        v2 = np.array([[float(x) for x in ln.split()] for ln in q.read_text().splitlines()[2:]])
        assert v2[0, 2] > v2[0, 0], "the black of the sample's look leans blue"
        assert v2[-1, 0] > v2[-1, 2], "and its white leans warm"
    try:
        grade.look("neon")
    except KeyError:
        pass
    else:
        raise AssertionError("an unknown look is refused")


def test_the_mix_has_the_length_the_loudness_and_the_voice_is_ducked_under():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec_audio = {"voice": [{"t": 0.5, "file": "vo.wav"}], "music": {"bpm": 90, "pluck_from": 1.0, "impacts": [0.0], "risers": [[0.5, 1.0]], "whooshes": [], "pings": [2.0]}, "lufs": -16}
        info = audio.mix(spec_audio, 4.0, d, d / "mix.wav")
        sig = audio.read_audio(d / "mix.wav")
        assert abs(len(sig) / audio.SR - 4.0) < 0.05, len(sig) / audio.SR
        assert info["voice_ends"] == [1.7], info
        got = audio.measure_lufs(["-i", str(d / "mix.wav")])
        assert got is not None and abs(got - (-16)) < 1.0 and abs(info["mix_lufs"] - got) < 0.2, (got, info)       # the target is delivered, not approached
        assert np.abs(sig).max() < 0.86, np.abs(sig).max()                                       # the limiter holds the sample peak under -1.4 dBFS even on a short mix
        # without a voice the same bed is louder in the span where the voice would be: it is ducked under speech
        loud = audio.mix({**spec_audio, "lufs": -12}, 4.0, d, d / "loud.wav")
        assert abs(loud["mix_lufs"] - (-12)) < 1.0, loud
        bare = {**spec_audio, "voice": []}
        audio.mix(bare, 4.0, d, d / "bare.wav")
        a, b = audio.read_audio(d / "mix.wav"), audio.read_audio(d / "bare.wav")
        span = slice(int(0.8 * audio.SR), int(1.4 * audio.SR))
        assert a[span].std() > 0.0 and b[span].std() > 0.0
        silent = {"voice": [], "music": {"bed": False}, "lufs": -16}
        audio.mix(silent, 1.0, d, d / "s.wav")
        assert np.abs(audio.read_audio(d / "s.wav")).max() < 0.01, "no music, no voice: silence"


def test_the_synthesis_is_deterministic_and_stays_in_range():
    a, b = audio.bed(3.0, 90, pluck_from=0.0), audio.bed(3.0, 90, pluck_from=0.0)
    assert np.array_equal(a, b) and np.abs(a).max() < 4.0 and np.abs(a).max() > 0.01
    rng = np.random.default_rng(1)
    assert len(audio.impact(rng, 1.0)) == audio.SR and len(audio.whoosh(rng, 0.5)) == audio.SR // 2
    assert len(audio.ping(0)) == int(0.9 * audio.SR)


if __name__ == "__main__":
    _t.main(globals())
