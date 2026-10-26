# Working in the playbook

This repository is the **parent of every growth-marketing skill pack** (KOL, Amazon Ads, Meta ads, SEO, ...). A skill pack adds only its channel: its pulls, reports, registries and the hooks the kit calls. Everything here exists because two or more skill packs need it. Why it is shaped this way: [docs/history/restructure-2026-10.md](docs/history/restructure-2026-10.md). Read [ROADMAP.md](ROADMAP.md) before you start.

## Keep it small

- **Channel code stays in the skill pack.** A platform's API, fields and vocabulary do not enter `kit/`, `console/`, `build/` or `scaffold/`. If only one skill pack needs it, it lives there.
- **A new kit module goes in the pack named for its concern, never in `base`.** It moves to `base` once two skill packs import it from code merged to their main branches. A module no skill pack imports for two minor versions is deleted ([kit/packs.tsv](kit/packs.tsv)).
- **Packs stay decoupled.** A pack imports only `base` and itself, and a test enforces it. The kit is stdlib only, and `from kit import X` paths do not move.
- **A lesson arrives as a small change with a test,** from a skill pack that paid for it. Say where it was seen; if once, say once. No new rule without a check that fails when the rule is broken: a rule nothing enforces is deleted, not kept.

## Keep each change focused

- **One pull request, one concern.** A kit change, a build-tool change and a scaffold change are three pull requests, each with its own test.
- **A changed byte the vendor tool copies needs a `kit/VERSION` bump and a regenerated `kit/MANIFEST.sha256`** ([kit/README.md](kit/README.md), "Upgrades and drift"). A move or rename breaks every skill pack that imports it: ask first. Every such bump, and every change a skill pack would notice, adds its line to `CHANGELOG.md` (the newest heading must equal `kit/VERSION`; `tests/test_changelog.py`).
- **Never edit a skill pack's vendored copy;** the fix goes here first.
- **Docs have one home.** The README is the overview and stays short; detail goes in `docs/`; a lesson goes in `docs/lessons.md` once. No new top-level file without a reason in the pull request.

## Before you push

`python3 run_all.py` (Python 3.11 or newer; macOS's own `python3` is 3.9) must end `RESULT: N passed`. A hook runs it for you on every push: `git config core.hooksPath .githooks` once per clone (`git push --no-verify` skips it). CI runs the same command and cancels the run of an older push to the same pull request, because minutes are a quota on a private repository.

Issues and pull requests start from the templates in `.github/`: they ask for what the rules above need to be checked.
