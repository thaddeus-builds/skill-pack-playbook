# _parked: code set aside, not deleted

Code written from one harness that no harness imports from the kit. It is **not vendored** (`kit/tools/vendor.py` copies `kit/` only), **not in `kit/MANIFEST.sha256`**, and **not run by `run_all.py`**. Nothing in `kit/`, `console/`, `build/`, `scaffold/` or `templates/` may import it (`tests/test_admission.py`). The designs stay in `docs/`; a doc test still reads the code here so the two do not drift apart.

| Folder | Holds | Written from | Why parked | Design |
| --- | --- | --- | --- | --- |
| `workbook/` | `workbook`, `workbook_map`, `workbook_store`, `workbook_patch`, `file_gate`, `testing/xlsx.py`, their tests and message codes (kit 0.11.0 to 0.21.0) | the KOL harness's client workbook, whose import is still planned | seen once, no importer | [docs/workbook-and-browser-ops.md](../docs/workbook-and-browser-ops.md) |
| `learning/` | `patternstore`, `pathweights`, `questions` and their tests (kit 0.13.0 to 0.28.0) | the video-ads harness, which keeps its own copy | seen once, no importer | [docs/pattern-store.md](../docs/pattern-store.md), [docs/path-weights.md](../docs/path-weights.md), [docs/rules.md](../docs/rules.md) rule 13 |
| `autonomy/` | `autonomy` and its test (kit 0.27.0) | the SEO harness, which keeps its own gate | seen once, no importer | [docs/autonomy.md](../docs/autonomy.md) |

Parked on 2026-10-14 (kit 0.31.0). The last kit that carried them is 0.30.1.

## Bringing a pack back

It comes back when a harness imports it in production, and not before ([the admission rule](../docs/kit-and-tools.md#the-admission-rule)).

1. `git mv _parked/<pack>/<file> kit/<file>` for each file, keeping the same relative path (`tests/` goes to `kit/tests/`, `message_codes.d/` to `kit/message_codes.d/`, `testing/` to `kit/testing/`).
2. Add each module's row to `kit/packs.tsv` (a pack named for its concern, never `base`).
3. Bump `kit/VERSION` (a minor), regenerate `kit/MANIFEST.sha256` (`python3 kit/tools/manifest.py kit`), add the CHANGELOG line.
4. Record the harness that imports it in `ROADMAP.md`, Links (`pack <name>: <harness> imports it in production`).
5. `python3 run_all.py` must end `RESULT: N passed`.

## Leaving for good

Each folder has a ROADMAP row under Parked with a `Review on` day. On that day the owner revives it, deletes it, or moves the day with their words quoted in Decisions. `tests/test_playbook_roadmap.py` fails after the day, so `_parked/` cannot turn into a drawer nobody opens.
