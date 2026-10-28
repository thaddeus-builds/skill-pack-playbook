<!-- One pull request, one concern (CLAUDE.md). No client names or data. -->

## What this changes, and why

## Where it was seen
<!-- The skill pack and the merged commit or MR. If seen once, say once. -->

## Who needs it
<!-- Skill packs that import or need this, by name. One: it lives in the pack named for its concern. Two, merged to their main branches: `base`. -->

## Checklist
- [ ] An agent or a person read the diff, the release note and the issue text for a description that identifies a client (the leak guard only matches listed terms, at push); the term list grew if a new client appears
- [ ] One concern: not a kit change, a build-tool change and a scaffold change together
- [ ] A test that fails without this change
- [ ] Channel code stays out: no platform API, field or vocabulary in `kit/`, `console/`, `build/` or `scaffold/`
- [ ] If a byte the vendor tool copies changed (`kit/` minus `tests/`): `kit/VERSION` bumped, `python3 kit/tools/manifest.py kit` run, a line in `CHANGELOG.md` whose newest heading equals the version. Otherwise: not applicable
- [ ] If a module is moved, renamed or removed: the owner said yes first
- [ ] `python3 run_all.py` ends `RESULT: N passed`
