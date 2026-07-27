# Prediction dataset

> This directory contains the project’s prediction dataset: the original public
> model outputs plus an append-style mirror of article evaluations created
> locally by the user. It contains no ground-truth labels or article content.

## Contents

```text
predictions/
├── manifest.json      # schema, counts and SHA-256 checksums
└── predictions.csv    # Original predictions and local user evaluations
```

| Measure | Value |
| --- | ---: |
| Original dataset rows | 19,429 |
| Current user-evaluation rows | See `manifest.json` |
| Derived articles | 19,411 |
| Original prediction runs | 38,854 |
| Original model/fold identities | 10 |
| Canonical articles assigned to multiple folds | 16 |

Schema version 2 uses `prediction_origin` to distinguish the two row types:

- `dataset_original`: one original wide-format BERT/RoBERTa dataset row;
- `user_evaluation`: one immutable local inference run, including its model ID,
  display name, official/custom/local provenance, family, fold, predicted label,
  all five probabilities, action, timestamps, device and software versions.

The original wide-format columns remain unchanged. Generic local-run fields are
`prediction_run_id`, `model_id`, `prediction_family`,
`prediction_fold_id`, `prediction_model_name`, `prediction_model_provenance`,
`prediction_official_manifest_entry_sha256`, `predicted_label`, `prob_class_0` through
`prob_class_4`, `prediction_action`, `input_source`, `content_retention`,
`job_id`, inference timestamps, `duration_ms`, `device`,
`software_versions_json` and `recorded_at`.

`title`, `text` and `authors` remain empty compatibility columns. Protected
provider labels, scores and metadata are not included.

The 16 canonical identities assigned to multiple folds correspond to 32
article/family memberships across BERT and RoBERTa. Their stored predictions
remain visible for inspection, but they are excluded from leakage-safe
evaluation because no single held-out fold can be established.

`data/state/prediction_runs.csv` is the application's authoritative operational
ledger. After a local inference commits there, the same run is written
idempotently to this CSV. At startup, mirrored `user_evaluation` rows can also
restore a missing local run before the mirror is synchronized again. Repeated
startup never duplicates a run because `prediction_run_id` is unique. If a
process stops after replacing the CSV but before replacing the manifest,
startup recalculates only the mutable counts and file checksum; it does so only
when the immutable original-row digest still matches.

## Verify

```bash
publisher-reliability dataset verify ./dataset/predictions
```

Or use the standalone script:

```bash
python3 scripts/verify_public_dataset.py dataset/predictions
```

Verification checks the schema, origin counts, row counts, part size, SHA-256
and content digest without changing application state. The stable content
digest covers only `dataset_original` rows; the part checksum and total/user
counts are refreshed whenever a local prediction is added.

## Import format

User imports may be `.csv` or `.csv.gz` and require:

- `url`;
- at least one `<family>_predicted_label`;
- the matching `<family>_fold_id`.

Supported prediction families are `bert` and `roberta`. Every represented
prediction must include all five probability columns; incomplete or absent
vectors are rejected.

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

## Write access

The application needs write access to `predictions.csv` and `manifest.json` to
mirror new user evaluations. The Compose configuration therefore mounts
`./dataset` read/write. For native use, the account running the application
must be able to replace files inside `dataset/predictions`.

## License

The limited CC0 dedication for generated outputs and database arrangement is
described in [MODEL-OUTPUT-LICENSE.md](../MODEL-OUTPUT-LICENSE.md). URLs,
publishers, source pages, trademarks, models and weights remain third-party
material.
