# Prediction dataset

> This directory contains the project’s only dataset: public model predictions,
> without ground-truth labels or article content.

## Contents

```text
predictions/
├── manifest.json      # schema, counts and SHA-256 checksums
└── predictions.csv    # URLs, model classes, folds and probabilities
```

| Measure | Value |
| --- | ---: |
| Source rows | 19,476 |
| Released URLs | 19,429 |
| Derived articles | 19,411 |
| Prediction runs | 77,708 |
| Model/fold identities | 20 |

`title`, `text` and `authors` are empty compatibility columns. Protected
provider labels, scores and metadata are not included.

## Verify

```bash
publisher-reliability dataset verify ./dataset/predictions
```

Or use the standalone script:

```bash
python3 scripts/verify_public_dataset.py dataset/predictions
```

Verification checks the schema, row counts, part size, SHA-256 and content
digest without changing application state.

## Import format

User imports may be `.csv` or `.csv.gz` and require:

- `url`;
- at least one `<family>_predicted_label`;
- the matching `<family>_fold_id`.

Supported families are `bert`, `roberta`, `llama` and `mistral`. Probability
columns are optional, but a vector must contain all five classes.

Titles, text, authors and protected values are discarded before persistence.
Equivalent CSV and CSV.GZ contents share one import identity.

## Rebuild the public release

This is needed only when preparing a new release from an authorized private
source:

```bash
python3 scripts/prepare_public_dataset.py \
  /path/to/source.csv.gz \
  dataset/predictions \
  --duplicate-policy first
```

The generator never modifies the source file.

## License

The limited CC0 dedication for generated outputs and database arrangement is
described in [MODEL-OUTPUT-LICENSE.md](../MODEL-OUTPUT-LICENSE.md). URLs,
publishers, source pages, trademarks, models and weights remain third-party
material.
