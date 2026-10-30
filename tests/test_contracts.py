"""contracts/ holds one schema and one example per contract, and says the same as the docs.

Checked: the file names follow `<name>-<version>.schema.json`; each schema parses, names itself
in `x-contract`, uses only the keywords contracts/README.md lists, never forbids unknown fields
(rule 2: a consumer ignores them), has a one-sentence `description` on every property and one of
the three statuses; a TSV schema's columns, `required` and `x-columns` agree; every `$ref` points
into the file; each example's first line is its mark; contracts/README.md's table and the table in
docs/portfolio.md list exactly the schemas that exist, the portfolio's with its producer and
consumers; the portfolio links to contracts/.
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "contracts")
KEYWORDS = {"type", "properties", "required", "items", "enum", "pattern", "minLength", "maxLength", "minItems",
            "maxItems", "minimum", "maximum", "$ref", "$defs", "title", "description", "$id", "$comment",
            "additionalProperties"}
STATUSES = {"in-use", "agreed", "draft"}
NAME = re.compile(r"^([a-z][a-z0-9_.]*)-([0-9]+)\.schema\.json$")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def schemas() -> dict[str, dict]:
    """{'ads.results/1': schema} for every file in contracts/ that looks like a schema."""
    out = {}
    for name in sorted(os.listdir(DIR)):
        if name.endswith(".schema.json"):
            m = NAME.match(name)
            assert m, f"{name}: not named <name>-<version>.schema.json"
            out[f"{m.group(1)}/{m.group(2)}"] = json.loads(read(os.path.join(DIR, name)))
    return out


def walk(node, path=""):
    """Every schema node under `node` (a schema), with its path; `properties` and `$defs` are maps of schemas."""
    yield path, node
    if not isinstance(node, dict):
        return
    for key in ("properties", "$defs"):
        for name, sub in (node.get(key) or {}).items():
            yield from walk(sub, f"{path}/{key}/{name}")
    if isinstance(node.get("items"), dict):
        yield from walk(node["items"], f"{path}/items")


def table_rows(text: str, heading_re: str) -> list[list[str]]:
    """The cells of each body row of the first table after a heading that matches `heading_re`."""
    m = re.search(heading_re, text, re.M)
    assert m, heading_re
    rows, started = [], False
    for line in text[m.end():].splitlines():
        if line.startswith("|"):
            started = True
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not set("".join(cells)) <= set("-: "):
                rows.append(cells)
        elif started:
            break
    return rows[1:]


def test_files_and_names():
    found = schemas()
    assert len(found) == 16, sorted(found)
    for kind, s in found.items():
        assert s.get("x-contract") == kind, (kind, s.get("x-contract"))
        assert s.get("title") == kind, (kind, s.get("title"))
        assert s.get("$id") == kind.replace("/", "-") + ".schema.json", (kind, s.get("$id"))
        assert s.get("x-status") in STATUSES, (kind, s.get("x-status"))
        assert s.get("x-format") in ("json", "tsv"), (kind, s.get("x-format"))
        assert s.get("x-producer") and s.get("x-consumers"), kind
        assert s.get("description"), kind


def test_keywords_and_unknown_fields():
    for kind, s in schemas().items():
        for path, node in walk(s):
            if not isinstance(node, dict):
                continue
            bad = sorted(k for k in node if k not in KEYWORDS and not k.startswith("x-"))
            assert not bad, f"{kind}{path}: keyword {bad} is not in contracts/README.md's list"
            assert node.get("additionalProperties", True) is not False, \
                f"{kind}{path}: a consumer ignores unknown fields, so no schema forbids them"
            if "type" in node:
                types = node["type"] if isinstance(node["type"], list) else [node["type"]]
                assert set(types) <= {"object", "array", "string", "number", "integer", "boolean", "null"}, \
                    (kind, path, types)


def test_every_property_is_described():
    for kind, s in schemas().items():
        for path, node in walk(s):
            if path.rsplit("/", 2)[-2:-1] == ["properties"]:
                d = node.get("description")
                assert d, f"{kind}{path}: no description"
                assert len(d) <= 600, f"{kind}{path}: a description is one sentence, this one is {len(d)} characters"


def test_refs_point_into_the_file():
    for kind, s in schemas().items():
        for path, node in walk(s):
            ref = node.get("$ref") if isinstance(node, dict) else None
            if ref is None:
                continue
            m = re.fullmatch(r"#/\$defs/([A-Za-z0-9_]+)", ref)
            assert m and m.group(1) in s.get("$defs", {}), f"{kind}{path}: {ref} is not in this file's $defs"


def test_tsv_schemas_agree_with_themselves():
    for kind, s in schemas().items():
        props = s.get("properties", {})
        if s["x-format"] == "json":
            assert s.get("type") == "object" and "x-columns" not in s, kind
            continue
        cols = s.get("x-columns")
        assert cols and len(set(cols)) == len(cols), kind
        assert set(cols) <= set(props), (kind, sorted(set(cols) - set(props)))
        assert set(s.get("required", [])) <= set(cols), (kind, sorted(set(s["required"]) - set(cols)))
        for name, sub in props.items():
            resolved = s["$defs"][sub["$ref"].rsplit("/", 1)[1]] if "$ref" in sub else sub
            assert resolved.get("type", "string" if "enum" in resolved else None) in ("string", "number"), \
                (kind, name, "a TSV cell is text or a decimal")
        order = list(props)
        assert [c for c in order if c in cols] == cols, f"{kind}: x-columns are in the order of properties"
        assert order[:len(cols)] == cols, f"{kind}: the optional columns come last"


def test_examples_carry_their_mark():
    found = schemas()
    names = sorted(os.listdir(os.path.join(DIR, "examples")))
    assert len(names) == len(found), names
    for kind, s in found.items():
        stem = kind.replace("/", "-") + ".example"
        ext = "tsv" if s["x-format"] == "tsv" else "json"
        assert f"{stem}.{ext}" in names, (kind, names)
        text = read(os.path.join(DIR, "examples", f"{stem}.{ext}"))
        assert text.splitlines()[0] == f"# {kind}", (kind, text.splitlines()[0])
        if ext == "json":
            json.loads(text.split("\n", 1)[1])


def test_the_two_tables_and_the_link():
    found = schemas()
    readme = read(os.path.join(DIR, "README.md"))
    mine = {c[0].strip("`"): c for c in table_rows(readme, r"^## The contracts$")}
    assert set(mine) == set(found), (sorted(set(mine) ^ set(found)))
    for kind, s in found.items():
        status = mine[kind][1]
        assert status == s["x-status"].replace("-", " "), (kind, status, s["x-status"])
    portfolio = read(os.path.join(ROOT, "docs", "portfolio.md"))
    theirs = {re.sub(r"`| \(exists.*\)$", "", c[0]): c for c in table_rows(portfolio, r"^## Contracts$")}
    assert set(theirs) == set(found), (sorted(set(theirs) ^ set(found)))
    assert "](../contracts/README.md)" in portfolio.split("## Engines in the kit")[0]
    readme_root = read(os.path.join(ROOT, "README.md"))
    assert "(contracts/README.md)" in readme_root


if __name__ == "__main__":
    _t.main(globals())
