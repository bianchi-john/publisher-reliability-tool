# Custom Transformers bundle

> Safe local import contract for user-created, five-class text classifiers.

Custom bundles are always marked `user_custom`. They are never relabelled as
paper artifacts, even when their architecture or filename resembles one. An
official paper model uses the separate OSF checksum workflow described in the
[user guide](user-guide.md).

## Dependencies

Encoder validation and inference:

```bash
uv sync --frozen --extra models
```

## Encoder classifier bundle

The ZIP contains one full, unsharded safe model:

```text
my-encoder/
├── prt-model.json
├── config.json
├── model.safetensors
├── tokenizer_config.json
└── tokenizer resources
```

Example manifest:

```json
{
  "schema_version": 1,
  "display_name": "My five-class DeBERTa",
  "family": "custom_my_deberta",
  "fold_id": 3,
  "class_order": [0, 1, 2, 3, 4],
  "max_tokens": 256,
  "padding_policy": "fixed_max_length",
  "base_model": "local-training-recipe",
  "base_revision": "experiment-2026-07-27",
  "training_data": {"kind": "five_fold", "held_out_fold": 3}
}
```

Allowed model types are `albert`, `bert`, `camembert`, `deberta`,
`deberta-v2`, `distilbert`, `electra`, `modernbert`, `mpnet`, `rembert`,
`roberta`, and `xlm-roberta`.

## Adapter bundles for larger decoder models

A second schema exists for LoRA sequence-classification adapters over the
study's larger decoder bases (Llama 3 8B, Mistral 24B). **It is under
development and refused in this release**: an upload declaring
`"schema_version": 2` returns `FEATURE_UNAVAILABLE` and installs nothing.

Each such fold needs a CUDA GPU and several gigabytes of base weights, which the
single-machine CPU demo cannot assume. The manifest vocabulary, validation rules
and loader recipe are kept in the codebase so the family can be enabled without
changing the storage contract or the model-identity rules. BERT and RoBERTa,
which do run here on CPU, report comparable accuracy in the study.

## Shared rules and validation

- `family` matches `custom_[a-z0-9][a-z0-9_-]{1,47}`;
- fold and `training_data.held_out_fold` are the same integer `1..5`;
- class order is exactly `[0,1,2,3,4]`;
- display name is 1–80 characters;
- files may be at ZIP root or under one common directory;
- unknown manifest fields, unsafe paths, links, encrypted entries, executable
  code, native libraries, pickle and `.pt` files are rejected;
- `auto_map` and `trust_remote_code` are rejected;
- tokenizer resources must be local;
- safetensor keys, shapes and finite values are checked without executing
  artifact code;
- the ordered file inventory determines model identity.

The validated bundle is atomically installed below
`data/managed-models/<model_id>`. The acquired upload is deleted after success
or failure. Inference rechecks the installed digest before loading.

## Fold leakage

The manifest states that model fold `N` held out fold `N`. The application can
enforce this only when imported predictions establish article membership for
the same family. For a custom family trained on another corpus, membership in
the bundled paper dataset is unknown; the manifest is provenance, not proof
that an arbitrary article was absent from training.
