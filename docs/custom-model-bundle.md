# Custom Transformers bundle

> Safe local import contract for user-created five-class text classifiers.

The Models page accepts one self-contained `.zip`. Import validates and
registers the model; it never downloads files and never executes code from the
bundle. New-page inference remains unavailable in the current release, so a
successful custom import has status `validated_not_runnable`.

Install the locked model-validation dependencies before starting the
application:

```bash
uv sync --frozen --extra models
```

## Required layout

Files may be at ZIP root or below one common top-level directory:

```text
my-model/
├── prt-model.json
├── config.json
├── model.safetensors
├── tokenizer_config.json
└── tokenizer resources
```

Tokenizer resources are the local files produced by
`tokenizer.save_pretrained(...)`, for example `tokenizer.json`, `vocab.txt`,
`vocab.json`, `merges.txt`, `spiece.model`, `special_tokens_map.json`, or
`added_tokens.json`.

Exactly one unsharded `model.safetensors` is supported. Do not include
`pytorch_model.bin`, `.pt`, pickle files, Python modules, native libraries,
symlinks or absolute/parent paths.

## Manifest

`prt-model.json` has an exact, closed field vocabulary:

```json
{
  "schema_version": 1,
  "display_name": "My five-class DeBERTa",
  "family": "custom_my_deberta",
  "fold_id": 3,
  "class_order": [0, 1, 2, 3, 4],
  "max_tokens": 256,
  "padding_policy": "fixed_max_length",
  "base_model": "local-deberta-training-recipe",
  "base_revision": "experiment-2026-07-24",
  "training_data": {
    "kind": "five_fold",
    "held_out_fold": 3
  }
}
```

Rules:

- `family` matches `custom_[a-z0-9][a-z0-9_-]{1,47}`;
- `fold_id` and `training_data.held_out_fold` are the same integer `1..5`;
- the classifier has exactly five labels in order `[0,1,2,3,4]`;
- `max_tokens` is `8..4096`;
- padding is `fixed_max_length` or `dynamic_longest`;
- display name is 1–80 characters;
- unknown manifest fields are rejected.

`base_model` and `base_revision` are optional provenance strings. They do not
cause a download.

## Export example

Use only a Transformers architecture supported by the locked project version:

```python
model.save_pretrained("my-model", safe_serialization=True)
tokenizer.save_pretrained("my-model")
```

Add `prt-model.json`, then create a ZIP:

```bash
python -m zipfile -c my-model.zip my-model/
```

Upload `my-model.zip` from Models → Import custom Transformer.

## Validation

The background model-validation job:

1. streams the ZIP under the configured byte limit;
2. rejects traversal, links, more than 256 files, decompression overflow and
   executable/pickle file types;
3. loads JSON and rejects `auto_map` or `trust_remote_code`;
4. resolves config and tokenizer with `local_files_only=true`;
5. constructs `AutoModelForSequenceClassification` from installed code;
6. requires `num_labels=5`;
7. compares every safetensors key and shape with the derived architecture;
8. rejects NaN or infinite tensor values;
9. hashes the ordered file inventory and scientific manifest into model
   identity;
10. atomically installs the bundle under `data/managed-models/<model_id>`.

The upload ZIP is deleted after terminal success or failure.

## Fold leakage

The manifest asserts a five-fold training convention: model fold `N` was
trained on the other four folds and held out fold `N`. The existing leakage
guard therefore permits known dataset articles only when their family/fold
registry establishes that they belong to the matching held-out fold.

For a genuinely different training corpus, the current manifest is not
expressive enough to prove per-article exclusion. Do not mislabel such a model
as fold-safe; extending training-provenance formats requires a new manifest
schema and scientific review.
