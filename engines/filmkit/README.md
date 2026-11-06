# filmkit

A film spec in, a finished film out. One JSON document (`filmkit.film/1`) says everything about a film: the shots and their camera moves, the transitions, a colour grade, animated type
and graphics, own-synthesis music and effects around the voice lines you bring, a loudness target and the encode. filmkit checks it (type off the safe area, overlapping lines, a cut off the beat,
a voice line running long), shows any frame as a still, and renders it with ffmpeg. It is the engine under a maker pack: the pack owns the story, the facts and who may appear; filmkit owns how
the film is made; the spec is all they share.

filmkit lives in the skill-pack playbook, in `engines/filmkit/` (it moved there from its own repository on 2026-11-01, history kept). It has its own `VERSION`, its own tests and its own
dependencies, and is not part of `kit/`: a pack that makes no films never carries ffmpeg. Who should use it: [docs/who-should-use.md](docs/who-should-use.md).

```
filmkit/            the package: spec, elements (title, text, chip, brackets, scan, counter, steps, rule, logo, kinetic, year), media (shots, camera), panel (the panel shot), cutout (the presenter cutout), transitions, grade, audio, check, render, cli, demo
docs/filmkit.md     the spec, the elements, the checks, the craft rules, the limits
skills/filmkit/     an agent's order of work
tests/              python3 engines/filmkit/tests/run.py  (offline: synthetic clips; from the playbook's root, `python3 run_all.py filmkit`)
VERSION             the version a pack's copy names (equal to pyproject.toml and filmkit.__version__; tests/test_parts.py holds them together)
```

```
python3 -m filmkit demo --out /tmp/demo                        # synthetic assets + film.json
python3 -m filmkit validate /tmp/demo/film.json
python3 -m filmkit check /tmp/demo/film.json
python3 -m filmkit still /tmp/demo/film.json --at 1.0 --out /tmp/demo/f.png
python3 -m filmkit render /tmp/demo/film.json --out /tmp/demo/film.mp4
python3 -m filmkit inspect /tmp/demo/film.mp4                  # duration, size, bitrate, LUFS, true peak
```

Needs Python 3.10+, numpy, Pillow, scipy and `ffmpeg`/`ffprobe` on the PATH (`uv run --with numpy --with pillow --with scipy python3 -m filmkit ...`). Fonts are not shipped: a spec names four
(black, bold, medium, regular, and `serif` for display type) or the Noto Sans CJK (Noto Serif CJK for `serif`) on the machine is used. Nothing third-party ends up in a film.

Use it from another project by vendoring `engines/filmkit/filmkit/` as a plain copy (never edit the copy: fix it in the playbook and take it again; the proofcut pack's `tools/vendor_filmkit.py` is the worked example). It is not stdlib-only, so a pack that
holds to the kit's stdlib rule calls it as a program (`python3 -m filmkit`) rather than importing it into its own package.
