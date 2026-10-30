"""python -m filmkit validate|check|still|render|inspect|looks|elements|demo  (every verb prints one JSON document; a problem exits 1 with the list)."""
from __future__ import annotations

import argparse
import json
import math
import signal
import sys
from pathlib import Path

from . import check as C
from . import grade as G
from . import spec as S
from .demo import make_demo
from .elements import ELEMENTS
from .render import inspect as inspect_film, render as render_film, still as still_frame   # the package re-exports `render`, so `from . import render` would be the function
from .util import FilmkitError


class _Parser(argparse.ArgumentParser):
    def error(self, message):                      # a wrong command line is a JSON document too, with the usual exit 2
        print(json.dumps({"error": f"{self.prog}: {message}"}, ensure_ascii=False, indent=1))
        sys.exit(2)


def _terminated(*_):
    raise KeyboardInterrupt                         # a job timeout (SIGTERM) unwinds like Ctrl-C: the render's work folder and ffmpeg children are cleaned up


def main(argv=None) -> int:
    ap = _Parser(prog="filmkit", description=__doc__)
    sub = ap.add_subparsers(dest="verb", required=True)
    for name in ("validate", "check"):
        sub.add_parser(name).add_argument("spec")
    p = sub.add_parser("still")
    p.add_argument("spec")
    p.add_argument("--at", type=float, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--scale", type=float, default=1.0)
    p = sub.add_parser("render")
    p.add_argument("spec")
    p.add_argument("--out", required=True)
    p.add_argument("--preview", type=float, help="render at this fraction of the size, quickly, at low quality")
    p.add_argument("--workdir")
    sub.add_parser("inspect").add_argument("file")
    p = sub.add_parser("demo")
    p.add_argument("--out", required=True, help="a folder to write the demo assets and film.json into")
    sub.add_parser("looks")
    sub.add_parser("elements")
    a = ap.parse_args(argv)
    try:
        signal.signal(signal.SIGTERM, _terminated)
    except ValueError:                              # not the main thread: the caller owns signals
        pass
    try:
        if a.verb == "looks":
            doc = G.LOOKS
        elif a.verb == "demo":
            doc = {"spec": str(make_demo(Path(a.out)))}
        elif a.verb == "elements":
            doc = {k: (v.__doc__ or "").strip() for k, v in ELEMENTS.items()} | {"_see": "filmkit/elements.py: the params of each"}
        elif a.verb == "inspect":
            doc = inspect_film(Path(a.file))
        else:
            spec, base = S.load(a.spec)
            if a.verb == "validate":
                bad = S.problems(spec, base)
                doc = {"ok": not bad, "problems": bad}
                if bad:
                    print(json.dumps(doc, ensure_ascii=False, indent=1))
                    return 1
            elif a.verb == "check":
                S.require(spec, base)
                doc = C.all_checks(spec, base)
                doc["ok"] = not (doc["layout"] or doc["timing"] or doc["glyphs"])
                print(json.dumps(doc, ensure_ascii=False, indent=1))
                return 0 if doc["ok"] else 1
            elif a.verb == "still":
                if not math.isfinite(a.at) or not math.isfinite(a.scale) or a.scale <= 0:
                    raise FilmkitError("--at and --scale must be finite numbers, --scale above 0")
                doc = {"png": str(still_frame(spec, base, a.at, Path(a.out), a.scale))}
            else:
                if a.preview is not None and not (math.isfinite(a.preview) and 0 < a.preview <= 1):
                    raise FilmkitError("--preview must be a fraction above 0 and up to 1")
                doc = render_film(spec, base, Path(a.out), preview=a.preview, workdir=Path(a.workdir) if a.workdir else None, keep=[Path(a.spec)],
                                  progress=lambda k, n: print(f"frame {k} of {n}", file=sys.stderr, flush=True))
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return 0
    except FilmkitError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=1))
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"error": "interrupted"}, ensure_ascii=False, indent=1))
        return 130
    except Exception as e:  # noqa: BLE001 - the CLI's promise is one JSON document and an exit status, never a traceback
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False, indent=1))
        return 1


if __name__ == "__main__":
    sys.exit(main())
