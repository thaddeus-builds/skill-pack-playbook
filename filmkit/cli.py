"""python -m filmkit validate|check|still|render|inspect|looks|elements|demo  (every verb prints one JSON document; a problem exits 1 with the list)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import check as C
from . import grade as G
from . import spec as S
from .demo import make_demo
from .elements import ELEMENTS
from .render import inspect as inspect_film, render as render_film, still as still_frame   # the package re-exports `render`, so `from . import render` would be the function
from .util import FilmkitError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="filmkit", description=__doc__)
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
                doc["ok"] = not doc["layout"] and not doc["timing"]
            elif a.verb == "still":
                doc = {"png": str(still_frame(spec, base, a.at, Path(a.out), a.scale))}
            else:
                doc = render_film(spec, base, Path(a.out), preview=a.preview, workdir=Path(a.workdir) if a.workdir else None,
                               progress=lambda k, n: print(f"frame {k} of {n}", file=sys.stderr, flush=True))
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return 0
    except FilmkitError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=1))
        return 1


if __name__ == "__main__":
    sys.exit(main())
