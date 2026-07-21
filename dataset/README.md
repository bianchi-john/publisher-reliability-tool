# Dataset input and public release

`sampleDataset.csv` is a synthetic schema example, not research data. Its URLs,
predictions, and probabilities are illustrative placeholders; editorial
compatibility fields are empty.

The public research release is generated from the private source CSV with:

```bash
python3 scripts/prepare_public_dataset.py \
  /path/to/fullDataset.csv.gz \
  dataset/predictions \
  --duplicate-policy first
```

The command accepts `.csv`, `.csv.gz`, or a ZIP containing exactly one CSV. It
retains `url`, derives `domain`, and retains model predictions, fold identifiers,
and available class probabilities. Columns `title`, `text`, and `authors`
remain for compatibility but the generator always writes them as empty strings.
It excludes all NewsGuard reference fields:
`score`, `country`, `language`, `topics`, `paywall`, `opinion_advocacy`, and the
original `label`.

Parts are limited to 24 MiB by default. `manifest.json` records their row counts,
sizes, and SHA-256 checksums. The builder validates every source row before it
makes the output directory visible, preventing a truncated CSV from becoming a
release.

The paper source contains repeated exact URLs with conflicting scraped content
and predictions. The public release uses the explicit `first` policy: source
order is authoritative, the first row for each URL is retained, later rows are
skipped, and the manifest records both source and skipped-row counts.

The application then applies its stricter offline URL normalization during seed
import. In the current release, 18 later URL strings normalize to an earlier
article identity. For this bundled release only, first-occurrence article
URL/domain identity is retained and non-conflicting predictions from different folds are
merged. Seed state therefore contains 19,411 articles, 77,708 unique
article/model prediction runs, and 20 historical family/fold models; a same-model
prediction conflict would make seed verification fail.

Verify a generated release, including a field-by-field comparison with its
private source, before committing it:

```bash
python3 scripts/verify_public_dataset.py \
  dataset/predictions \
  --source /path/to/fullDataset.csv.gz
```

The release contains no article titles, bodies, or author strings. Generated
model outputs are dedicated under CC0-1.0 by
`../MODEL-OUTPUT-LICENSE.md`; that dedication does not cover URLs, publisher
names, trademarks, model weights, or source pages.

At first startup the application verifies this manifest and streams the release
into the authoritative CSV ledgers under the configured data directory. Import
is idempotent by the exact manifest-source checksum and import schema version;
the manifest's separate content digest remains the historical-model identity
input. The tracked parts remain immutable.

At runtime the user can also select a CSV, `.csv.gz`, single-CSV ZIP, manifest
directory, or ZIP containing one manifest and exactly its listed parts. A
server-local source is streamed subject to available disk and platform file
limits; browser/API uploads use the documented 2 GiB compressed and extracted
limits. The importer leaves a server-local source unchanged and projects URLs,
publisher domains, and model outputs into the local CSV store. Source title,
text, and author values are discarded. Protected reference columns are
reported by name only and their values never persist.

Arbitrary user imports do not use the release generator's first-occurrence
policy. Within one import, duplicate canonical URLs can merge different model
identities, but a different output for the same article/model identity is
rejected and counted. A later source with a different import identity creates a
separate immutable imported run. Discarded editorial fields never participate
in conflict checks.

`fullDataset.csv` and all datasets other than the tracked sample and generated
release directory are ignored by Git.
