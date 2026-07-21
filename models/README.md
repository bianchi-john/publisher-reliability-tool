# Local model artifacts

This directory is a default local model root. Artifact contents are ignored by
Git; only this README is tracked. Another root can be passed with `--models-dir`
or mounted read-only at `/models` in Docker.

Official artifacts are downloaded manually from:

<https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

The terminal and Models page display this exact link and setup instructions.
Inference never downloads an artifact or missing base model implicitly.

## Official `.pt` folds

Recognized filenames are exact, with `N` in `1..5`:

```text
bert_fold_N.pt
roberta_fold_N.pt
llama_fold_N.pt
```

Each file is a PyTorch `state_dict`, not a self-contained Transformers package.
Registration reconstructs the exact built-in base/tokenizer recipe, loads with
safe `weights_only` behavior, requires strict keys and shapes, and runs the
family reference fixture before status becomes `compatible`.

A renamed file is not recognized as official. It can be registered only with an
explicit custom manifest that supplies the same unambiguous information.

## Official Mistral folds

Mistral is a PEFT directory rather than a `.pt` file:

```text
models/
└── mistral/
    └── fold_N/
        ├── adapter_config.json
        ├── adapter_model.safetensors
        ├── tokenizer_config.json
        ├── tokenizer.json or tokenizer.model
        └── other tokenizer files referenced by configuration
```

Exactly one adapter weight file is required:
`adapter_model.safetensors` or the standard PEFT fallback `adapter_model.bin`.
Archive/directory validation rejects missing configuration, missing weights,
path traversal, symlinks outside the root, multiple conflicting weight files,
wrong class count, or a base identity other than
`mistralai/Mistral-Small-24B-Base-2501`.

The directory does not contain the 24B base weights. They must already exist in
the configured Transformers cache or be downloaded through an explicit setup
action while online.

## Supported layouts

Scanning is recursive and accepts official artifacts at any depth below a
configured root, including the observed release layouts:

```text
models/Fold 1/bert_fold_1.pt
models/Fold 1/roberta_fold_1.pt
models/Fold 1/llama_fold_1.pt
models/mistral/fold_1/adapter_config.json
```

Hidden directories, `.ipynb_checkpoints`, temporary upload directories, and
symlinks resolving outside the configured root are skipped. Duplicate paths to
the same resolved artifact produce one registry candidate.

## Custom model manifest

A custom supported classifier requires `publisher-reliability-model.json`
beside the artifact. Unknown keys are rejected. Version 1 contains:

```json
{
  "manifest_version": 1,
  "family": "custom",
  "fold_id": null,
  "artifact_kind": "hf_directory",
  "artifact_file": ".",
  "artifact_sha256": "64 lowercase hex characters",
  "base_model": "organization/model-name",
  "base_revision": "immutable revision",
  "tokenizer_source": "organization/tokenizer-name",
  "tokenizer_revision": "immutable revision",
  "loader_recipe": "hf_sequence_classification",
  "loader_recipe_version": "1",
  "class_count": 5,
  "max_tokens": 256,
  "padding_policy": "fixed_max_length",
  "class_order": [0, 1, 2, 3, 4]
}
```

Version 1 custom manifests accept two generic recipes:

- `hf_sequence_classification`: a local standard Transformers directory with
  `config.json`, exactly one supported safe weight set, tokenizer files,
  `num_labels=5`, and no custom code;
- `peft_sequence_classification`: a standard local PEFT sequence-classification
  adapter plus immutable base/tokenizer identities already supported by the
  installed Transformers/PEFT versions.

A raw custom `.pt` `state_dict` is accepted only when it explicitly selects one
of the built-in BERT/RoBERTa/Llama recipes and passes that recipe's strict
shape/reference tests; a manifest cannot describe arbitrary Python architecture.

The manifest cannot contain executable code, import paths, remote Python
modules, shell commands, or `trust_remote_code=true`. A request for another
recipe is `unsupported`, not dynamically executed.

The manifest's `artifact_sha256` uses the exact file/directory digest algorithm
in `docs/scientific-contract.md`. The manifest file itself is excluded from a
directory digest, avoiding a self-referential checksum. Any mismatch makes the
registration `invalid`.

## Registration states

- `compatible`: inference is selectable.
- `historical_only`: imported virtual model; stored-run reuse, aggregation,
  browsing, and content-only enrichment of an article with that run, but no
  inference.
- `dependency_missing`: artifact recognized; base/tokenizer/runtime absent.
- `resource_unavailable`: dependencies exist; required device/resources do not.
- `invalid`: expected artifact fails validation.
- `unsupported`: no explicit built-in or supported custom recipe.

Any official fold can be registered independently. Folds are never silently
ensembled. Artifact checksum, fold, recipe, tokenizer, base revision, maximum
length, and padding policy determine exact runnable model identity.
