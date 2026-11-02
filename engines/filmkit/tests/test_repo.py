"""What makes filmkit safe to keep in a public repository: one version everywhere, and no font, footage, picture or audio file in the folder."""
import re
import subprocess
from pathlib import Path

import _t
import filmkit

ROOT = Path(__file__).resolve().parents[1]
# what may be tracked here: code and text; everything else (a font, a clip, a photo, a voice line) is a client's or a licence's to keep
ALLOWED = {".py", ".md", ".toml", ".json", ".txt", ".gitignore", "VERSION"}


def test_the_version_is_the_same_in_VERSION_pyproject_and_the_package():
    v = (ROOT / "VERSION").read_text().strip()
    py = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    skill = re.search(r"^version: (\S+)", (ROOT / "skills/filmkit/SKILL.md").read_text(), re.M).group(1)
    assert v == py == skill == filmkit.__version__, (v, py, skill, filmkit.__version__)


def test_no_font_or_media_file_is_tracked_here():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", "."], capture_output=True, text=True)
    files = out.stdout.split() if out.returncode == 0 else []
    if not files:                                                                  # not a checkout: look at the folder
        files = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    stray = [f for f in files if Path(f).suffix.lower() not in ALLOWED and Path(f).name not in ALLOWED]
    assert not stray, stray


if __name__ == "__main__":
    _t.main(globals())
