"""Fonts: a spec names four roles (black, bold, med, reg) as files; nothing is shipped (a face's licence is the client's to check). A role with no file falls back to Noto Sans CJK in the
usual places, then to the face Pillow carries, so a render never stops for a missing font and the check says which fallback was used."""
from __future__ import annotations

import os
from pathlib import Path

from PIL import ImageFont

from .util import FilmkitError

ROLES = ("black", "bold", "med", "reg")
# (file name, face index): the split OTF release (macOS) and the .ttc collections Debian and Ubuntu install (`fonts-noto-cjk`; Black and Medium come with `fonts-noto-cjk-extra`), in which Simplified Chinese is face 2
CANDIDATES = {
    "black": [("NotoSansCJKsc-Black.otf", 0), ("NotoSansSC-Black.otf", 0), ("NotoSans-Black.ttf", 0), ("NotoSansCJK-Black.ttc", 2)],
    "bold": [("NotoSansCJKsc-Bold.otf", 0), ("NotoSansSC-Bold.otf", 0), ("NotoSans-Bold.ttf", 0), ("NotoSansCJK-Bold.ttc", 2)],
    "med": [("NotoSansCJKsc-Medium.otf", 0), ("NotoSansSC-Medium.otf", 0), ("NotoSans-Medium.ttf", 0), ("NotoSansCJK-Medium.ttc", 2)],
    "reg": [("NotoSansCJKsc-Regular.otf", 0), ("NotoSansSC-Regular.otf", 0), ("NotoSans-Regular.ttf", 0), ("NotoSansCJK-Regular.ttc", 2)],
}
DIRS = [Path.home() / "Library/Fonts", Path("/Library/Fonts"), Path("/usr/share/fonts/opentype/noto"), Path("/usr/share/fonts/truetype/noto"), Path.home() / ".fonts"]


class Fonts:
    def __init__(self, files: dict | None = None, base_dir: Path = Path(".")):
        self.files: dict[str, str | None] = {}
        self.index: dict[str, int] = {}
        self.fallback: list[str] = []
        for role in ROLES:
            given = (files or {}).get(role)
            path = None
            if given:
                p = Path(given)
                path = str(p if p.is_absolute() else (base_dir / p))
                if not Path(path).is_file():
                    raise FilmkitError(f"font {role}: {path} is not a file")
            elif not os.environ.get("FILMKIT_NO_SYSTEM_FONTS"):          # tests set it so a render does not depend on this machine's fonts
                for d in DIRS:
                    for name, index in CANDIDATES[role]:
                        if (d / name).is_file():
                            path, self.index[role] = str(d / name), index
                            break
                    if path:
                        break
            if path is None:
                self.fallback.append(role)
            self.files[role] = path
        self._cache: dict = {}

    def get(self, role: str, px: float):
        key = (role, int(round(px)))
        if key not in self._cache:
            size = max(8, int(round(px)))
            path = self.files.get(role)
            self._cache[key] = ImageFont.truetype(path, size, index=self.index.get(role, 0)) if path else ImageFont.load_default(size)
        return self._cache[key]

    def missing(self, role: str, text: str) -> list[str]:
        """The characters of `text` the face of `role` has no glyph for (it would draw its empty box): those whose picture is the face's own picture for a character it cannot have."""
        f = self.get(role, 48)
        none = f.getmask("\U0010fffd")
        blank = (none.size, bytes(none))
        out: list[str] = []
        for ch in dict.fromkeys(text):
            if ch.isspace() or not ch.isprintable():
                continue
            m = f.getmask(ch)
            if (m.size, bytes(m)) == blank and ch not in out:
                out.append(ch)
        return out
