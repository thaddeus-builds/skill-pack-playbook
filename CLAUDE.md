# Working in the playbook

This repository is the **parent of every growth-marketing harness** (KOL, Amazon Ads, Meta ads, SEO, ...). A harness adds only its channel: its pulls, reports, registries and the hooks the kit calls. Everything here exists because two or more harnesses need it. Why it is shaped this way: [RESTRUCTURE.md](RESTRUCTURE.md). Read [ROADMAP.md](ROADMAP.md) before you start.

## Keep it small

- **Channel code stays in the harness.** A platform's API, fields and vocabulary do not enter `kit/`, `console/`, `build/` or `scaffold/`. If only one harness needs it, it lives there.
- **Extract, don't invent.** The parent holds what harnesses already run. A lesson seen in one harness arrives as a note in `docs/`, with where and when it was seen. It becomes kit code only when a harness imports the kit's version in production; a harness that keeps its own copy is not an importer.
- **The guardrails are the parent; the features are the channel.** `base` is what makes a write safe and checkable (the gate, the human tables, the queue, dry-run, the write guard, the `--json` contract, coded messages), and its list is pinned in `tests/test_admission.py`. A new module goes in the pack named for its concern, never in `base`; it moves to `base` once two harnesses import it from code merged to their main branches.
- **Every pack names its importer.** A pack in `kit/` has a ROADMAP Links line `pack <name>: <harness> imports ... in production`, or a Parked row that names it with a `Review on` day. Code nobody imports lives in `_parked/` (not vendored, not run by CI, imported by nothing) until a harness imports it. `python3 tools/consumers.py` does the count; `tests/test_admission.py` and `tests/test_playbook_roadmap.py` fail when this is broken ([the rule and why](docs/kit-and-tools.md#the-admission-rule)).
- **Packs stay decoupled.** A pack imports only `base` and itself, and a test enforces it. The kit is stdlib only, and `from kit import X` paths do not move.
- **A lesson arrives as a small change with a test,** from a harness that paid for it. Say where it was seen; if once, say once, and keep it a note in `docs/` (the first bullet). No new rule without a check that fails when the rule is broken: a rule nothing enforces is deleted, not kept.

## Keep each change focused

- **One pull request, one concern.** A kit change, a build-tool change and a scaffold change are three pull requests, each with its own test.
- **A changed byte the vendor tool copies needs a `kit/VERSION` bump and a regenerated `kit/MANIFEST.sha256`** ([kit/README.md](kit/README.md), "Upgrades and drift"). A move or rename breaks every harness that imports it: ask first. Every such bump, and every change a harness would notice, adds its line to `CHANGELOG.md` (the newest heading must equal `kit/VERSION`; `tests/test_changelog.py`).
- **Never edit a harness's vendored copy;** the fix goes here first.
- **Docs have one home.** The README is the overview and stays short; detail goes in `docs/`; a lesson goes in `docs/lessons.md` once. No new top-level file without a reason in the pull request.

## Before you push

`python3 run_all.py` (Python 3.11 or newer; macOS's own `python3` is 3.9) must end `RESULT: N passed`.
