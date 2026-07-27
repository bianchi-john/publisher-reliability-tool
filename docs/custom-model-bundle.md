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

Llama 3 8B or Mistral 24B adapter inference:

```bash
uv sync --frozen --extra llm-models
```

LLM bundles can be validated and registered without CUDA, but remain
`resource_unavailable` until a CUDA device is present.

## Schema 1: complete encoder classifier

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

## Schema 2: Llama/Mistral PEFT classifier

This is a LoRA adapter for `AutoModelForSequenceClassification`, not a
prompt-based generative model:

```text
my-adapter/
├── prt-model.json
├── adapter_config.json
├── adapter_model.safetensors
├── tokenizer_config.json
├── tokenizer.json
└── optional tokenizer resources
```

Mistral example:

```json
{
  "schema_version": 2,
  "model_kind": "peft_sequence_classifier",
  "architecture": "mistral",
  "display_name": "My Mistral classifier",
  "family": "custom_mistral_experiment",
  "fold_id": 1,
  "class_order": [0, 1, 2, 3, 4],
  "max_tokens": 1024,
  "padding_policy": "dynamic_longest",
  "base_model": "mistralai/Mistral-Small-24B-Base-2501",
  "base_revision": "<40-character commit SHA>",
  "training_data": {"kind": "five_fold", "held_out_fold": 1}
}
```

For Llama use:

- `architecture`: `llama`;
- `base_model`: `meta-llama/Meta-Llama-3-8B`;
- `max_tokens`: at most `256`;
- dynamic padding.

For Mistral, `max_tokens` is at most `1024`. In both cases
`base_revision` must be an immutable 40-character commit SHA. The adapter must
declare PEFT `LORA`, task `SEQ_CLS`, a `score` or `classifier` module to save,
compatible target modules, and a head with exactly five rows.

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
