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

Verify a generated release, including a field-by-field comparison with its
private source, before committing it:

```bash
python3 scripts/verify_public_dataset.py \
  dataset/predictions \
  --source /path/to/fullDataset.csv.gz
```

Article titles, bodies, and author strings originate from their respective
publishers. Their inclusion does not transfer ownership or imply that they are
copyright-free. Model outputs are released separately under the project license.

At runtime the user may select a CSV of any size with the same permitted
structure. The importer reads it incrementally, leaves it unchanged, and stores
only allowlisted article identifiers and model outputs in the local database.
Protected reference labels, scores, and provider metadata are ignored before
persistence and must never be committed.

`fullDataset.csv` and all datasets other than the tracked sample and generated
release directory are ignored by Git.
