"""Fonts: a spec names four roles (black, bold, med, reg) as files; nothing is shipped (a face's licence is the client's to check). A role with no file falls back to Noto Sans CJK in the
usual places, then to the face Pillow carries, so a render never stops for a missing font and the check says which fallback was used."""
from __future__ import annotations

import os
from pathlib import Path

from PIL import ImageFont

ROLES = ("black", "bold", "med", "reg")
CANDIDATES = {
    "black": ["NotoSansCJKsc-Black.otf", "NotoSansSC-Black.otf", "NotoSans-Black.ttf"],
    "bold": ["NotoSansCJKsc-Bold.otf", "NotoSansSC-Bold.otf", "NotoSans-Bold.ttf"],
    "med": ["NotoSansCJKsc-Medium.otf", "NotoSansSC-Medium.otf", "NotoSans-Medium.ttf"],
    "reg": ["NotoSansCJKsc-Regular.otf", "NotoSansSC-Regular.otf", "NotoSans-Regular.ttf"],
}
DIRS = [Path.home() / "Library/Fonts", Path("/Library/Fonts"), Path("/usr/share/fonts/opentype/noto"), Path("/usr/share/fonts/truetype/noto"), Path.home() / ".fonts"]


class Fonts:
    def __init__(self, files: dict | None = None, base_dir: Path = Path(".")):
        self.files: dict[str, str | None] = {}
        self.fallback: list[str] = []
        for role in ROLES:
            given = (files or {}).get(role)
            path = None
            if given:
                p = Path(given)
                path = str(p if p.is_absolute() else (base_dir / p))
                if not Path(path).is_file():
                    raise FileNotFoundError(f"font {role}: {path} is not a file")
            elif not os.environ.get("FILMKIT_NO_SYSTEM_FONTS"):          # tests set it so a render does not depend on this machine's fonts
                for d in DIRS:
                    for name in CANDIDATES[role]:
                        if (d / name).is_file():
                            path = str(d / name)
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
            self._cache[key] = ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
        return self._cache[key]
