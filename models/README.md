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

A renamed file is not recognized as official. Generic custom manifests are
outside the MVP.

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
path traversal, every symlink, multiple conflicting weight files,
wrong class count, or a base identity other than
`mistralai/Mistral-Small-24B-Base-2501`.

The directory does not contain the 24B base weights. They must already exist in
the configured cache or be provisioned with external Transformers/Hugging Face
tooling. The application has no setup command.

## Supported layouts

Scanning is recursive and accepts official artifacts at any depth below a
configured root, including the observed release layouts:

```text
models/Fold 1/bert_fold_1.pt
models/Fold 1/roberta_fold_1.pt
models/Fold 1/llama_fold_1.pt
models/mistral/fold_1/adapter_config.json
```

Hidden directories, `.ipynb_checkpoints`, and temporary upload directories are
skipped. Every encountered symlink causes that artifact candidate to be
rejected. The same symlink rule applies in scan, registration, validation,
upload, and retry; registration is the result of scan/upload, not a separate
path API.

## Official model manifest

The application package embeds the versioned official manifest described in
`docs/scientific-contract.md`. It pins immutable base/tokenizer revisions and
all scientific settings before dependencies are installed. Unknown or renamed
artifacts are `unsupported`; no arbitrary architecture or artifact code runs.

## Registration states

- `compatible`: inference is selectable.
- `historical_only`: imported virtual model; stored-run reuse, aggregation,
  browsing, and content-only enrichment of an article with that run, but no
  inference.
- `artifact_missing`: the scientific identity and history remain usable but the
  deployment locator is absent and new inference is disabled.
- `dependency_missing`: artifact recognized; base/tokenizer/runtime absent.
- `resource_unavailable`: dependencies exist; required device/resources do not.
- `invalid`: expected artifact fails validation.

`unsupported` is a scan outcome for an unknown artifact, not a registry state:
without an official manifest entry there is no scientific model ID/row.

Any official fold can be registered independently. Folds are never silently
ensembled. Artifact checksum, manifest, fold, recipe, tokenizer/base revisions,
class order, adapter configuration, scientific runtime settings, maximum length,
and padding determine identity. Filesystem locator is excluded.
