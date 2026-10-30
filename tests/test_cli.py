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


if __name__ == "__main__":
    _t.main(globals())
