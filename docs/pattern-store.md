# The pattern store: what a client's outputs taught, per client

A skill pack that makes things a client pays to run (ads, posts, emails) should let what worked steer what it makes next. The pattern store keeps that as **abstract rows in the client's own database**, and reads them back as shrunk rates that always carry their counts. Module: [`kit/patternstore.py`](../kit/patternstore.py), pack `learning` (`[kit] packs = ["learning"]`). The process around it (a factor catalog, the owner's definition of a winner, rules pending until a variant confirms them): [templates/outcome-learning.md](../templates/outcome-learning.md).

*Seen once:* the video-ads skill pack built it for its first client (2026-10-12) and is the worked example: its `pkg/patterns.py` (the rows and the export), `pkg/patterns_query.py` (the query) and its `docs/patterns.md`. It keeps its own copy for now; this module is that copy with the channel taken out.

## When to use it

When a skill pack has outcomes per output (a rank, a click rate, a reply) and should learn from them for this client: which audience, which objection answered, which opening worked, and with how much evidence. Not for learning across clients: **each client's evidence stays in its own store** and a query reads only that client's file. A cross-client design was considered and dropped (owner, 2026-10-12).

## The row

A **pattern** is a context × an ICP archetype × a playbook: three groups (`context`, `icp`, `play`) whose fields the skill pack names in a `Shape`. An **evidence row** says how many items had exactly one pattern vector:

| Key | Value |
| --- | --- |
| `schema`, `id` | the skill pack's schema id; the first 16 hex of the sha256 of the row without `id`, as canonical JSON |
| `source`, `label_rule` | one of the skill pack's sources, and a label rule that source takes |
| `period` | `YYYY-MM/YYYY-MM` |
| `context`, `icp`, `play` | exactly the shape's fields; each value an id of its closed vocabulary or null (not observed, or not counted); a field may also be a `{key: id}` mapping or a sequence of ids (`Seq`) |
| `n`, `families` | the items, and the independent families they come from as `f_` + 10 hex tokens (near-copies count once as evidence) |
| outcomes | `win`, `mid`, `lose`, `thin` (the shape may name others), summing to `n`; absent on a presence-only source |
| a source's extras | scalar closed fields only that source carries (a spend-share band, say) |

## The rules

1. **Closed vocabularies only.** `validate(row, shape, vocab)` never raises and returns the problems; it refuses free text (a trailing newline included), unknown or missing keys, wrong types, a bad sum and an id that does not recompute, and a problem names the field, never the value. One problem refuses the whole export. A client's words never reach a row; a family id is hashed.
2. **Sources, never pooled.** A skill pack declares as many sources as it has; each row names one. The video-ads skill pack has three: the client's own past outputs (ranked within the account), the outputs the skill pack made and tested, and competitors as **presence only** (`Source(outcomes=False)`: how often, never good or bad). A query reads each source apart.
3. **The agent maps, the code validates.** Judgement fields (an objection class, an awareness level) are the agent's map, written by the skill pack's skill; the code only checks them against the vocabularies. When unsure, the field is null.
4. **Two coders, one floor.** A coded field counts only when two independent coders agree at the floor (`agreement()`, `meets_floor()`, 0.70 by default, read from the counts); below it the field is null for every item.
5. **Append-only.** `TABLES` go into the skill pack's schema as extra human tables with `APPEND_ONLY` (kit.db's triggers refuse UPDATE, DELETE and an INSERT over a key). A row is retracted by appending a reason; an export supersedes the live rows it no longer makes (`plan()`, `apply()`), so new data replaces old and nothing is counted twice; a row retracted by hand stays out until a reinstatement lifts it.
6. **Shrunk, with counts, never one winner.** `shrink(cells)` is empirical Bayes (beta-binomial) toward the store's own mean, anchored off the edges ((wins + 0.5) / (labelled + 1), so an all-win field keeps an interval): kappa by the method of moments, clipped to 5–10 tests' worth; each cell's rate comes with its interval (the 10th and 90th percentiles), its raw counts and a competition rank (ties share). A field with fewer than two labelled cells gets counts only, with the reason. A null value is its own cell: no rate, no status, never in the prior.

## What the skill pack supplies

- **Its shape and vocabularies:** `Shape(schema, context, icp, play, sources, required)` and `{field: ids}` from its own registries (retired ids kept, so history stays readable). `shape_problems(shape, vocab)` belongs in its own test.
- **Its sources:** the readers that turn its exports, tags and maps into items (`{source, period, label_rule, context, icp, play, family, outcome}`); `group(items, shape)` pools them into rows.
- **Its scope and storage:** the scope word (a project, a product line), the transaction (`kit.db.keep_human_rows`), `now` and who wrote it, the closed list of reasons for a retraction by hand.
- **Its query:** which fields to group by, the thresholds for a cell to read (the video-ads skill pack: at least 3 labelled items in two families), and how a person sees it.
