"""The Chinese glossary (docs/glossary-zh.md) names every key of kit.pagestyle.ZH, and the words an advertiser does
not say (issue #302) are gone from the kit's defaults and its Chinese labels."""

from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from kit import pagestyle  # noqa: E402

GLOSSARY = open(os.path.join(ROOT, "docs", "glossary-zh.md"), encoding="utf-8").read()
OLD = ("降权", "有希望", "如果行", "如果不行", "存疑", "搁置", "赚钱")


def test_every_zh_key_is_on_the_glossary():
    missing = [k for k in pagestyle.ZH if f"`{k}`" not in GLOSSARY]
    assert not missing, missing


def test_old_words_are_gone_from_the_defaults():
    zh = " ".join(pagestyle.ZH.values())
    assert not [w for w in OLD if w in zh], zh
    files = glob.glob(os.path.join(ROOT, "kit", "constants.d", "*.tsv")) + glob.glob(os.path.join(ROOT, "kit", "message_codes.d", "*.tsv"))
    for path in files:
        for line in open(path, encoding="utf-8"):
            cells = line.rstrip("\n").split("\t")
            zh_cells = " ".join(c for c in cells if any("一" <= ch <= "鿿" for ch in c))
            assert not [w for w in OLD if w in zh_cells], (path, line[:80])


def test_the_states_are_the_glossary_words():
    z = pagestyle.ZH
    assert (z["state_promising"], z["state_down"], z["state_closed"]) == ("表现良好", "表现下滑", "已停止")


if __name__ == "__main__":
    _t.main(globals())
