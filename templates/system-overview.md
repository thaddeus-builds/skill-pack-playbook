# System overview page

One page that lets an owner or a new agent see what a harness can do and how it works, without reading code. The example is the Ecommerce SEO Skill Pack: `tools/pipeline.py` writes `docs/pipeline.html` from its registries.

## Use the standard for each question

Invent no notation. Each question has an established answer; draw that and nothing more.

| The reader asks | Standard | On the page |
| --- | --- | --- |
| What can it do? | Business capability map (TOGAF, ArchiMate) | Boxes grouped by kind of work. Solid = it exists, dashed = not yet, with the story ids that would add it |
| In what order, and who clicks? | The workflow itself (the stages registry) | The flow by phase, human steps marked |
| What is it made of, and what runs where? | C4 levels 1 and 2 (context, containers); in arc42 terms the building-block and deployment views | Stage → who → command → code file; the places things run |
| What goes on a page? | A content-model catalogue | One table: the pieces a page is built from, what each proves, where it sits |

Do not draw C4 component or code level: it is out of date by the next merge. The page is not a PRD (the stories are) and not a "blueprint" (an informal word); call it the system overview.

## Rules

1. **Generated, committed, checked.** A stdlib script reads the registries and writes the page; the file is committed so the owner finds it in the repo; the test runs the script's `--check`, which fails when the committed file is stale. A merge conflict in it is never resolved by hand: merge, regenerate, commit.
2. **Status is read, never typed.** A capability box points at a stage or at story ids. It shows as existing when the stage exists or every story is `done` in the story table, so it flips by itself when the story is done.
3. **Common first, then the differences.** When the harness serves more than one business type, each catalogue row carries an applicability column in the same grammar the other registries use (`sells=goods&buyer=business`). The page groups rows by the set of types the expression holds for: first what every type uses, then what two share, then what one type adds. A type with no rows of its own says so on the page; it does not borrow another type's.
4. **Every stage and every row is on the page.** A test fails when one is missing, and when a box points at a stage or story that does not exist.
5. **One page.** A view that needs hand-written prose belongs in a how-to, not here.

*Paid for:* the first catalogue listed every module in one table, and readers took the pieces that only a manufacturer needs for pieces every site needs; a software client had none of its own and nobody could see that. Diagrams drawn in a chat went out of date the same week.
