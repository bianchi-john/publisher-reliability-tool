# Dataset input and public release

`sampleDataset.csv` is a synthetic schema example, not research data. Its URLs,
texts, authors, predictions, and probabilities are illustrative placeholders.

The public research release is generated from the private source CSV with:

```bash
python3 scripts/prepare_public_dataset.py \
  /path/to/fullDataset.csv.gz \
  dataset/predictions \
  --duplicate-policy first
```

The command accepts `.csv`, `.csv.gz`, or a ZIP containing exactly one CSV. It
retains scraped article fields (`url`, `title`, `text`, and `authors`), derives
`domain` from the URL, and retains model predictions, fold identifiers, and
available class probabilities. It excludes all NewsGuard reference fields:
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
metadata is retained and non-conflicting predictions from different folds are
merged. Seed state therefore contains 19,411 articles, 77,708 unique
article/model predictions, and 20 historical family/fold models; a same-model
prediction conflict would make seed verification fail.

Verify a generated release, including a field-by-field comparison with its
private source, before committing it:

```bash
python3 scripts/verify_public_dataset.py \
  dataset/predictions \
  --source /path/to/fullDataset.csv.gz
```

Article titles, bodies, and author strings originate from their respective
publishers. Their inclusion does not transfer ownership or imply that they are
copyright-free. Model outputs are intended for free redistribution, but the
project owner must publish their exact license terms; a software license cannot
license the third-party article fields.

At first startup the application verifies this manifest and streams the release
into the authoritative CSV ledgers under the configured data directory. Import
is idempotent by release content digest and schema version; the tracked parts
remain immutable.

At runtime the user can also select a CSV, `.csv.gz`, single-CSV ZIP, manifest
directory, or ZIP containing one manifest and exactly its listed parts. A
server-local source is streamed subject to available disk and platform file
limits; browser/API uploads use the documented 2 GiB compressed and extracted
limits. The importer leaves a server-local source unchanged and projects
allowlisted article fields and model outputs into the local CSV store.
Protected reference columns are reported by name only and their values never
persist.

Arbitrary user imports do not use the release generator's first-occurrence
policy. Conflicting duplicate canonical URLs are rejected and counted so the
application never silently selects one.

`fullDataset.csv` and all datasets other than the tracked sample and generated
release directory are ignored by Git.
