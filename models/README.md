# Local model artifacts

This is the default model root. Artifact contents are ignored by Git; only this
guide is tracked. Download official artifacts manually from:

<https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

Copy files here and start a scan from the Models page or:

```bash
publisher-reliability models scan
```

The application does not download weights/base models, manage Hugging Face
credentials/caches, or interpret custom manifests.

## Core CPU demo

Recognized official folds (`N` is `1..5`):

```text
bert_fold_N.pt
roberta_fold_N.pt
```

These are PyTorch state dictionaries. Built-in loaders reconstruct the exact
manifest-pinned base/tokenizer recipe, use safe `weights_only` loading, require
strict keys/shapes, and run a frozen CPU reference fixture before status becomes
`compatible`.

## Optional GPU examples

Llama `.pt` folds and official Mistral PEFT fold directories are optional
research examples. They require their documented base model, CUDA, memory, and
optional PEFT/bitsandbytes dependencies. Missing optional resources do not fail
the core demo.

```text
llama_fold_N.pt
mistral/fold_N/
  adapter_config.json
  adapter_model.safetensors
  tokenizer files
```

## Safety and extension

Configured roots must be real readable directories. Hidden/temp directories are
skipped; any symlink in an artifact candidate rejects that candidate. API scan
accepts no filesystem path. Upload safely accepts only recognized official
file/optional PEFT layouts and rejects traversal, links, ambiguity, and unknown
code.

Scientific identity includes artifact digest, official manifest-entry digest,
fold, recipe, immutable base/tokenizer revisions, class order, input/padding,
adapter config, dtype, and quantization. Filesystem location is excluded.
Removing an artifact makes it unavailable but does not invalidate stored runs.

To add a new model family, implement one explicit Python `ModelLoader`, add its
complete identity construction and frozen tokenizer/output fixture, then update
the scientific contract. This direct extension is preferred to a universal
manifest/plugin system.
