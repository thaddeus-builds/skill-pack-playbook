"""The command line: every verb prints one JSON document, and a spec problem exits 1 with the list. Run through `python -m filmkit` so the entry point itself is what is tested."""
import json
import subprocess
import sys

import _t

ROOT = _t.Path(__file__).resolve().parent.parent


def cli(*args):
    r = subprocess.run([sys.executable, "-m", "filmkit", *map(str, args)], capture_output=True, text=True, cwd=ROOT, env={**_t.os.environ, "FILMKIT_NO_SYSTEM_FONTS": "1"})
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None), r.stderr


def test_the_listing_verbs_print_the_registries():
    code, doc, _ = cli("looks")
    assert code == 0 and "teal_warm_soft" in doc and "natural" in doc, doc
    code, doc, _ = cli("elements")
    assert code == 0 and {"title", "counter", "steps"} <= set(doc), doc


def test_validate_check_still_and_inspect_work_on_a_spec_file():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec_file = d / "film.json"
        spec_file.write_text(json.dumps(_t.film_spec(d)))
        code, doc, err = cli("validate", spec_file)
        assert code == 0 and doc["ok"], (doc, err)
        code, doc, err = cli("check", spec_file)
        assert code == 0 and doc["ok"], (doc, err)
        code, doc, err = cli("still", spec_file, "--at", 1.0, "--out", d / "f.png", "--scale", 0.5)
        assert code == 0 and (d / "f.png").is_file(), (doc, err)
        _t.ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=64x64:d=1", "-pix_fmt", "yuv420p", d / "g.mp4")
        code, doc, err = cli("inspect", d / "g.mp4")
        assert code == 0 and doc["width"] == 64, (doc, err)


def test_demo_writes_a_spec_that_validates_and_renders_a_preview():
    with _t.tmpdir() as d:
        code, doc, err = cli("demo", "--out", d / "demo")
        assert code == 0 and _t.Path(doc["spec"]).is_file(), (doc, err)
        code, doc, err = cli("validate", doc["spec"])
        assert code == 0 and doc["ok"], (doc, err)
        code, doc, err = cli("render", d / "demo" / "film.json", "--out", d / "demo.mp4", "--preview", 0.25)
        assert code == 0 and doc["duration"] == 6.0 and doc["width"] == 270, (doc, err[-300:])


def test_a_bad_spec_exits_one_with_the_problems():
    with _t.tmpdir() as d:
        bad = d / "bad.json"
        bad.write_text(json.dumps({"schema": "x"}))
        code, doc, _ = cli("validate", bad)
        assert code == 1 and doc["ok"] is False and doc["problems"], doc


def test_every_failure_is_one_json_document_with_an_exit_status_and_never_a_traceback():
    """Review M5: a missing or malformed spec, a PNG for inspect, a scale of 0, a time outside the film, a folder that is not there, a check that finds a problem."""
    with _t.tmpdir() as d:
        _t.make_assets(d)
        good = d / "film.json"
        good.write_text(json.dumps(_t.film_spec(d)))
        (d / "empty.json").write_text("")
        (d / "list.json").write_text("[1, 2]")
        (d / "nan.json").write_text('{"duration": NaN}')
        (d / "binary.json").write_bytes(bytes(range(256)))
        cases = [
            ("validate", d / "missing.json"), ("render", d / "missing.json", "--out", d / "o.mp4"), ("validate", d / "empty.json"), ("validate", d / "list.json"),
            ("validate", d / "nan.json"), ("validate", d / "binary.json"), ("inspect", d / "list.json"), ("inspect", d / "nothing.mp4"),
            ("still", good, "--at", 1.0, "--out", d / "x.png", "--scale", 0), ("still", good, "--at", 100, "--out", d / "x.png"), ("still", good, "--at", "nan", "--out", d / "x.png"),
            ("still", good, "--at", 1.0, "--out", d / "nodir" / "x.png"), ("render", good, "--out", d / "nodir" / "x.mp4"), ("render", good, "--out", d / "o.mp4", "--preview", 0),
            ("render", good, "--out", d / "o.mp4", "--preview", 5), ("render", good, "--out", d / "a.mp4", "--preview", 0.25), ("render", good, "--out", good),
        ]
        for args in cases:
            code, doc, err = cli(*args)
            assert code == 1 and doc and ("error" in doc or doc.get("ok") is False), (args, code, doc, err[-300:])
            assert "Traceback" not in err, (args, err[-300:])
        assert (d / "a.mp4").stat().st_size > 10000, "the render over an input was refused before it touched the file"
        code, doc, err = cli()
        assert code == 2 and "error" in doc and "Traceback" not in err, (code, doc, err)
        code, doc, err = cli("still", good)
        assert code == 2 and "error" in doc, (code, doc, err)


def test_check_exits_one_when_it_finds_a_problem():
    with _t.tmpdir() as d:
        _t.make_assets(d)
        spec = _t.film_spec(d)
        spec["overlays"][0]["y"] = 1500                                                       # in TikTok's own caption zone
        f = d / "film.json"
        f.write_text(json.dumps(spec))
        code, doc, err = cli("check", f)
        assert code == 1 and doc["ok"] is False and doc["layout"], (code, doc, err)


def test_a_terminated_render_leaves_no_work_folder_and_no_ffmpeg_behind():
    import os
    import signal
    import time
    with _t.tmpdir() as d:
        code, doc, _ = cli("demo", "--out", d / "demo")
        assert code == 0
        tmp = d / "tmp"
        tmp.mkdir()
        p = subprocess.Popen([sys.executable, "-m", "filmkit", "render", str(d / "demo" / "film.json"), "--out", str(d / "o.mp4"), "--preview", "0.5"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env={**os.environ, "FILMKIT_NO_SYSTEM_FONTS": "1", "TMPDIR": str(tmp)})
        assert "frame 0" in p.stderr.readline()                                              # the first frame is being made: the work folder exists
        assert any(x.name.startswith("filmkit-") for x in tmp.iterdir())
        p.send_signal(signal.SIGTERM)
        out, _err = p.communicate(timeout=60)
        assert p.returncode == 130 and "interrupted" in out, (p.returncode, out)
        time.sleep(0.3)
        assert not [x for x in tmp.iterdir()], list(tmp.iterdir())


if __name__ == "__main__":
    _t.main(globals())
