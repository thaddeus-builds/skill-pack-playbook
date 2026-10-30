# contracts/: the files skill packs exchange

Skill packs never read one another's databases. They exchange files, and each file kind is defined here, once, by a JSON schema. Why packs talk this way, and who produces and reads what: [docs/portfolio.md](../docs/portfolio.md), "Contracts".

A contract is named `<name>/<version>`, for example `ads.results/1`. It has one schema, `<name>-<version>.schema.json`, and one example, `examples/<name>-<version>.example.*`.

## The rules

1. **The first line names the file.** `# <name>/<version>`, for example `# ads.results/1`. A reader refuses a file whose first line is not the mark it expects, and a version it does not know.
2. **A consumer ignores fields it does not know.** A schema therefore never says `"additionalProperties": false`, and a producer may add a field to a version at any time. Adding is not a breaking change.
3. **A breaking change is a new version.** Removing or renaming a field, changing its meaning or type, or adding a required field is. The producer writes the old and the new version side by side for one release, so a consumer has that long to move, then stops writing the old.
4. **A file is written once.** Into the client hub's exchange folder, `exchange/<contract>/<producer>/<date>.<ext>`, or, without a hub, to the path a `--out` flag names. The same bytes written again are a no-op; different bytes under the same name are refused. A consumer saves what it reads into its own raw files as it was received, so raw only grows. The kit's `contracts` module (pack `exchange`, [kit/contracts.py](../kit/contracts.py)) does all four: it writes the first line, checks a document against its schema, writes once to `--out`, and saves a file it reads into the caller's raw as it came. A hub's exchange folder is added when the hub has one.

## Two formats

- **JSON** (every new contract): the first line, then one JSON document. The schema describes the document.
- **TSV** (`ads.creatives/1`, `ads.results/1` and its second version `ads.results/2` only, because they were already in use): the first line, a header line, then one line per row, tab-separated. The schema describes **one row**: its columns are `properties`, each cell is text, `"type": "number"` means the cell parses as a finite decimal, and a blank cell of a column that is not in `required` means unknown, never 0. `x-columns` lists the columns the header must have, in the order they are written; `required` lists those whose cell may not be blank; a column in `properties` but not in `x-columns` is optional and written last. The two schemas state the existing formats and change nothing in them.

## The schema keywords

A schema uses only: `type` (also a list, for `null`), `properties`, `required`, `items`, `enum`, `pattern`, `minLength`, `maxLength`, `minItems`, `maxItems`, `minimum`, `maximum`, `$ref` and `$defs` (within the file), and `title`, `description`, `$id` and `$comment` for people. The `x-` keys are ours and say nothing to a validator: `x-contract` (the name and version), `x-status`, `x-format` (`json` or `tsv`), `x-producer`, `x-consumers`, `x-columns` (TSV), `x-vocabulary` (the words a column usually holds; a word outside it is kept, not refused) and `x-rules` (what no keyword can say: the rules that hold across rows or fields, which the packs' own readers and tests keep).

Every property has a `description` of one sentence.

## The contracts

| Contract | Status | Producer | Consumers | Schema | Example |
| --- | --- | --- | --- | --- | --- |
| `ads.creatives/1` | in use | a maker (adcut) | operators (video-ads) | [schema](ads.creatives-1.schema.json) | [TSV](examples/ads.creatives-1.example.tsv) |
| `ads.results/1` | in use | an operator (video-ads; any operator may) | makers (adcut), measurement, creator-program | [schema](ads.results-1.schema.json) | [TSV](examples/ads.results-1.example.tsv) |
| `ads.results/2` | draft | an operator (video-ads; any operator may) | makers (adcut), measurement, creator-program | [schema](ads.results-2.schema.json) | [TSV](examples/ads.results-2.example.tsv) |
| `creators.roster/1` | agreed | creator-program | video-ads | [schema](creators.roster-1.schema.json) | [JSON](examples/creators.roster-1.example.json) |
| `ads.demand/1` | draft | an operator | makers | [schema](ads.demand-1.schema.json) | [JSON](examples/ads.demand-1.example.json) |
| `handoff.batch/1` | draft | asset-handoff | operators | [schema](handoff.batch-1.schema.json) | [JSON](examples/handoff.batch-1.example.json) |
| `copy.proposals/1` | draft | ad-copy | operators, asset-handoff | [schema](copy.proposals-1.schema.json) | [JSON](examples/copy.proposals-1.example.json) |
| `ads.changes/1` | draft | an operator | measurement | [schema](ads.changes-1.schema.json) | [JSON](examples/ads.changes-1.example.json) |
| `catalog/1` | draft | product-feed | operators, makers, seo | [schema](catalog-1.schema.json) | [JSON](examples/catalog-1.example.json) |
| `messages/1` | draft | the messaging owner | makers, ad-copy, gads, kos | [schema](messages-1.schema.json) | [JSON](examples/messages-1.example.json) |
| `truth/1` | draft | measurement | operators | [schema](truth-1.schema.json) | [JSON](examples/truth-1.example.json) |
| `intel/1` | draft | search-intel | gads, ppc, seo, pseo | [schema](intel-1.schema.json) | [JSON](examples/intel-1.example.json) |
| `ads.spend/1` | draft | an operator | measurement, the other operators | [schema](ads.spend-1.schema.json) | [JSON](examples/ads.spend-1.example.json) |
| `ads.status/1` | draft | an operator | the daily page, the owner's console | [schema](ads.status-1.schema.json) | [JSON](examples/ads.status-1.example.json) |
| `intel.ads/1` | draft | search-intel | ad-copy, gads, ppc | [schema](intel.ads-1.schema.json) | [JSON](examples/intel.ads-1.example.json) |
| `leads/1` | draft | outbound | sdr | [schema](leads-1.schema.json) | [JSON](examples/leads-1.example.json) |

**Status** (`x-status`):
- `in-use`: two packs already write and read it. The schema states the format they hold; it changes nothing in it, and the packs' definitions (adcut's `adcut/contracts.py`, the video-ads skill pack's `docs/contract.md`) stay the longer account of what the columns mean.
- `agreed`: both sides have named the fields. The producer builds it as written here.
- `draft`: drawn from the portfolio page's table. It may change **without** a new version until a producer writes it and a consumer reads it from merged code; whichever pack gets there first settles the fields by a change to this schema. After that it is `agreed`, and rule 3 applies.

## Open points

- `creators.roster/1`: the video-ads skill pack's K5 (`docs/creator-split.md`) names the creator key `creator_ref`; creator-program's `crp compute roster` prints `creator`, and also `tier`, `script_id` and `permission_expired`. The schema lists both creator keys as optional and the rest as the verb prints them. creator-program and video-ads settle one key; until then a reader takes `creator_ref` if present, else `creator`.
- Only the keywords above are checked by a validator. A rule across rows (a code on one row only, `nk` unique) or across fields (a `fission` needs its `scored_at`) is in `x-rules` and stays with the packs' own readers.

## Changing a contract

1. A change to a schema is a pull request here, with the example changed to match and the schema copied to `kit/contracts.d/` (a vendored byte: `kit/VERSION`, the manifest and `CHANGELOG.md` move with it). `kit/tests/test_contracts.py` fails when the two copies differ. `tests/test_contracts.py` holds the shape of every schema and that the table above, the files and [docs/portfolio.md](../docs/portfolio.md) list the same contracts.
2. A new contract starts as `draft` with a row in the portfolio's table, which names its producer and its consumers.
