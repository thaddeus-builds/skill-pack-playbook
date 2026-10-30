# {{name}} roadmap
Updated: {{today}}
<!-- The one roadmap format; kit.guards.roadmap holds it (tests/test_roadmap.py). One line per item, `- [ID] YYYY-MM-DD text`: the id's letter names the section (N now, W waiting on the owner, X next, D done, P parked, R decisions) and is never reused; the date is the day the row was written. At every session end set Updated and move rows (docs/session-handoff.md). Replace the example rows. Optional `## Milestones` right after Next: one row per integration unit, `- [M1] YYYY-MM-DD name. includes: X1, X2. closes when: the proof`; at most three open; when every item is Done the row leaves and a Done row records it (docs/operating.md, "Integrate by milestone"). When the file has grown, move old Done and Parked rows to a file next to it and name it on a line of its own before the first section, `Archive: ROADMAP-ARCHIVE.md` (the archive is `# <name> roadmap archive` with `## Done` and `## Parked`; ids stay unique across both files). -->
## Now
- [N1] {{today}} the one turn in progress, in a sentence an agent can act on
## Waiting on owner
- [W1] {{today}} what the owner must provide or decide, and why. unblocks: X1
## Next
- [X1] {{today}} the next turn, one session's worth; rows in the order they will be done
## Done
- [D1] {{today}} what finished, in one line, ending in its reference (no ref)
## Parked
- [P1] {{today}} what the owner decided not to do yet, and why
## Decisions
- [R1] {{today}} "the owner's words, verbatim" (where they said it)
## Links
- repository: where the code lives
- console: where the owner's asks and answers live
