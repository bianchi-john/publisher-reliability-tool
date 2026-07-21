# Publisher Reliability Tool - Specification

This repository contains the initial product and scientific specification for a
local tool derived from the paper *From Articles to Publishers: Aggregating
Language Model Predictions for News Source Reliability Inference*.

The repository is intentionally documentation-only. Its purpose is to settle
the behavior of the tool before implementation begins.

## Product in one sentence

A Linux command starts a local web application that can browse historical
article predictions from a user-supplied CSV, load one or more locally stored
Transformer checkpoints, run a missing article prediction, and aggregate
compatible article predictions into a publisher-level reliability estimate.

## Current product boundary

- The application runs locally and is started from a Linux terminal.
- The browser interface is served on `localhost` by default.
- Model inference is local; article text is not sent to a remote inference API.
- Models are supplied as local paths at startup or registered from the local
  browser interface.
- A supplied Models directory is scanned recursively; hidden folders such as
  `.ipynb_checkpoints` are ignored.
- Released `bert_fold_N.pt`, `roberta_fold_N.pt`, and `llama_fold_N.pt`
  checkpoints use notebook-derived built-in loading recipes; any fold may be
  selected independently.
- Released Mistral folds are PEFT directories built on
  `mistralai/Mistral-Small-24B-Base-2501`; they are not single `.pt` files.
- The observed `Fold 1/` layout for the three `.pt` files and `fold_1/` layout
  for Mistral are both accepted without renaming.
- The user supplies a schema-compatible CSV at startup or through the frontend;
  `dataset/sampleDataset.csv` is the tracked structural example.
- Large or private datasets such as `dataset/fullDataset.csv` remain local and
  are excluded from Git.
- New predictions and publisher evaluations persist across restarts.
- If no model is available, the server still starts in history-only mode and
  explains model setup in both the terminal and browser interface.
- The browser accepts one article URL, several article URLs from one publisher,
  or one publisher homepage URL at a time.
- The browser provides searchable histories for evaluated publishers and
  articles, and lets the user select existing articles for a new evaluation.
- Article and publisher detail pages include compact probability and
  aggregation charts backed by accessible data tables.
- All terminal messages, frontend text, and documentation presented by the
  software are in English; inference accepts English-language articles only.
- New article text is extracted with `newspaper3k`, validated with `langdetect`,
  and sent unchanged to the selected tokenizer; no additional text cleaning is
  applied.
- Publisher-level inference follows the paper's majority-vote aggregation for
  the reproducible default and also exposes explicitly named alternative
  aggregation methods when their required outputs are available.
- Model training is not part of the first version.

## Essential documents

| Document | Purpose |
| --- | --- |
| [`docs/product-specification.md`](docs/product-specification.md) | Scope, users, requirements, workflows, and open product decisions |
| [`docs/scientific-contract.md`](docs/scientific-contract.md) | Meaning of labels, predictions, aggregation, and model compatibility |
| [`docs/architecture.md`](docs/architecture.md) | Minimal local architecture, persistence, security, and data flow |
| [`docs/acceptance-tests.md`](docs/acceptance-tests.md) | Observable conditions that an implementation must satisfy |

## Status notation

The documents use three markers:

- **DECIDED**: accepted starting point;
- **PROPOSED**: recommended design, still changeable;
- **OPEN**: a decision or artifact is still required.

## Source material available at initialization

- Paper draft dated July 2026.
- A diagnostic summary of the experimental DataFrame, consulted only to
  identify the model-output fields that may be released.
- `dataset/sampleDataset.csv`, which defines the example import structure.
- The BERT/RoBERTa/Llama and Mistral training notebooks, used to derive built-in
  loading recipes for the released fold checkpoints.
- The model release referenced by the paper:
  <https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

The tracked sample contains synthetic values only. The full dataset and model
weights are local inputs and must not be committed.

If a private input CSV contains blocked reference-provider columns, the importer
projects only the permitted fields and never persists the blocked values.

A released BERT, RoBERTa, or Llama `.pt` contains a `state_dict`, not a
self-contained Transformers package. A released Mistral fold contains a PEFT
adapter and tokenizer but not its 24B base weights. The application recipe
reconstructs the correct architecture, while every missing base dependency
must be present in the local cache or downloaded during explicit setup.

The terminal and frontend Models page always show the official OSF link. When
no compatible model is installed, they also explain how to download, extract
when necessary, place, and register an artifact.

## Terminology

- **Protected reference data**: original labels, scores, and provider-supplied
  metadata used in the research. These data are excluded from the repository,
  imports, database, UI, and exports.
- **Article**: a record identified uniquely by its canonical URL.
- **Publisher**: a record identified uniquely by its normalized domain, with
  its homepage URL stored for navigation.
- **Article prediction**: the freely releasable output produced by one
  identified model artifact for one canonical article URL.
- **Publisher evaluation**: an aggregation of compatible article predictions
  belonging to one publisher.

The tool exposes model predictions, not the protected labels against which the
models were evaluated.
