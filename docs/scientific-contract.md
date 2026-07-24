# Scientific and Data Contract

**Status:** Normative research-demo scientific contract

## 1. Protected-data boundary

The demo distributes and displays model-produced outputs only. It shall not
distribute, persist, log, or expose original reference-provider labels, scores,
ranges, metadata, or any mapping that reconstructs them.

Private user CSVs may contain blocked columns. Import is an allowlist projection:
blocked values are discarded before staging, while `imports.csv` may retain
column names only. Source title, text, and author values are also discarded.
The exact user-supplied upload bytes may exist only in the private temporary
acquisition file required for that import and are deleted at terminal cleanup;
they are never copied into authoritative ledgers, warnings, or logs.
The public classes are displayed only as `Class 0` through `Class 4` and are
always described as model predictions, not facts or ground truth.

Project software/documentation uses Apache-2.0. Project-owned prediction
outputs and database arrangement use the limited CC0 dedication in
`MODEL-OUTPUT-LICENSE.md`; source pages, URLs, publisher names, trademarks,
models, and weights remain third-party material.

## 2. Scientific task

1. An article classifier produces one ordered class index in `0..4` and, for
   new inference, five softmax values.
2. A publisher method aggregates 2–50 compatible article runs from one exact
   model and one normalized publisher.

Every persisted run is immutable. Every publisher evaluation stores the exact
ordered run and article IDs it used. A newer run never changes an older result.

## 3. Dataset inputs

The working release is `dataset/predictions/manifest.json` plus
`predictions.csv`. Part size/checksum, row counts, schema, and the stable
`prt-dataset-content-v1` digest of original rows are verified before import.
Schema version 2 distinguishes `dataset_original` and `user_evaluation` through
the required `prediction_origin` field.

The bundled legacy wide schema contains:

| Field | Rule |
| --- | --- |
| `article_id` | Source-local compatibility value; never application identity |
| `url` | Required canonical-identity input |
| `title`, `text`, `authors` | Required and empty in bundled release; discarded on user import |
| `domain` | Bundled publisher compatibility value; runtime recomputes it |
| `<family>_predicted_label` | Integer `0..4` for each represented family |
| `<family>_fold_id` | Integer `1..5` |
| `<family>_prob_class_0..4` | Optional only as a complete valid vector |

Those columns are populated for `dataset_original` rows. A
`user_evaluation` row instead represents exactly one local run through the
generic fields `prediction_run_id`, `model_id`, `prediction_family`,
`prediction_fold_id`, `predicted_label`, `prob_class_0..4`,
`prediction_action`, `input_source`, `content_retention`, `job_id`, timestamps,
duration, device, software versions and recording time. Original wide-format
prediction cells are empty on such a row.

User CSV/CSV.GZ requires `url` and at least one represented family's label/fold
pair. Source ID, domain, title, text, and authors are optional. Supported family
prefixes are `bert` and `roberta`; each represented prediction requires all
five class probabilities.

Projection rules:

- normalize URL, derive UUIDv5 article ID, recompute publisher hostname/ID;
- exclude any URL port from publisher hostname/ID while retaining a valid
  non-default port in canonical article URL;
- discard editorial/blocked values before staging or error formatting;
- reject a non-empty source domain that disagrees after normalization;
- validate class `0..4`, fold `1..5`, and complete probability vector;
- deduplicate identical article/model output in one source;
- if outputs conflict for one article/model in that source, publish none of
  that pair and report safe row numbers under `IMPORT_INVALID`.

The generated bundled release contains 19,429 released URLs. Runtime
normalization yields 19,411 article IDs, 38,854 unique runs, and 10 historical
BERT/RoBERTa family/fold identities. Every run has one complete five-class
probability vector. Llama/Mistral hard labels are deliberately absent because
their class probabilities were not available.

The release-identity content digest is `prt-dataset-content-v1` as defined by
the storage contract and covers only the original wide-format values.
Appending a `user_evaluation` changes the physical file checksum and manifest
counts but not that original scientific identity. Equivalent CSV/CSV.GZ
projected original record sequences share identity; compression is not
scientific identity.

## 4. Article input

Online input follows this exact boundary:

1. retrieve HTML through the safe application client while sending
   `Accept-Language: en-US,en;q=0.9`;
2. parse the already downloaded HTML with Newspaper3k configured as
   `language="en"`;
3. if Newspaper3k cannot parse the document, return `EXTRACTION_FAILED`; no
   secondary extractor or page request is attempted;
4. retain Newspaper3k's extracted text without case normalization, stemming, or
   lemmatization;
5. trim only for minimum-length measurement; require at least 200 Unicode
   characters and 30 whitespace-delimited tokens;
6. run `langdetect` with `DetectorFactory.seed = 0` and require exact `en`;
7. pass unchanged extracted text to the selected tokenizer;
8. discard HTML/authors always and title/body unless `save_local` is explicit.

Tokenizer subwords, truncation, attention masks, and padding are model encoding,
not text cleaning. A missing run under `reuse` and every `recompute` retrieve a
fresh page.

## 5. Core and custom models

Official artifacts are manually obtained from:

<https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

The package contains `official-model-manifest-v1.json` with one immutable entry
per official family/fold: expected artifact digest, built-in loader recipe and
version, class order, input length/padding, output-relevant runtime options,
base/tokenizer repositories, and immutable revisions. The application does not
download base-model weights or execute code from an artifact. For core
checkpoints it may cache only the official tokenizer/configuration resources
from the manifest's immutable revision on first online inference.

### 5.1 Core CPU demo

| Family | Artifact | Base/input recipe |
| --- | --- | --- |
| BERT | `bert_fold_N.pt` | `bert-base-uncased`, five-label sequence classifier, fixed padding/truncation to 256 |
| RoBERTa | `roberta_fold_N.pt` | `roberta-large`, five-label sequence classifier, fixed padding/truncation to 256 |

Both use `torch.load(..., map_location="cpu", weights_only=True)`, strict tensor
keys/shapes, `eval()`, and softmax over five logits. Core compatibility requires
a frozen CPU float32 reference fixture.

### 5.2 Custom Transformers bundle

A user model is accepted only as the constrained PRT bundle documented in
`custom-model-bundle.md`: ZIP container, declarative `prt-model.json`, local
Hugging Face `config.json` and tokenizer, and exactly one
`model.safetensors`. It must resolve through the installed
`AutoModelForSequenceClassification` registry, declare five labels and use a
`custom_...` family plus held-out fold `1..5`.

Validation is local-only and uses `trust_remote_code=false`. It rejects
`auto_map`, Python/native modules, pickle/PyTorch checkpoint files, unsafe ZIP
paths or links, unknown manifest fields, missing tokenizer resources,
non-finite weights, and any key/shape mismatch against the architecture derived
from `config.json`.

The exact bundle file/digest inventory, manifest input policy, family/fold,
training convention and loader recipe determine identity. A valid bundle is
installed below `managed-models` and registered as
`compatible`; its local tokenizer and safetensors weights can be used for new
article inference without network model acquisition.

## 6. Exact model identity

A runnable model ID is SHA-256 of canonical UTF-8 JSON with sorted keys and no
insignificant whitespace. Every key, including nulls, is present:

```json
{
  "artifact_sha256": "...",
  "official_manifest_entry_sha256": "...",
  "family": "bert",
  "fold_id": 1,
  "loader_recipe": "bert_state_dict",
  "loader_recipe_version": "1",
  "base_model": "bert-base-uncased",
  "base_revision": "immutable-commit",
  "tokenizer_source": "bert-base-uncased",
  "tokenizer_revision": "immutable-commit",
  "class_order": [0, 1, 2, 3, 4],
  "max_tokens": 256,
  "padding_policy": "fixed_max_length",
  "adapter_config_sha256": null,
  "runtime_scientific": {"dtype": "float32", "quantization": null}
}
```

For one file, artifact digest is SHA-256 of exact bytes. For a directory, reject
symlinks, enumerate regular files as relative POSIX path/digest/size, sort by
UTF-8 path, canonical-JSON serialize, and hash. Filesystem locator, device path,
and cache path are excluded. A missing artifact changes availability, never the
scientific model ID or historical runs.

Mutable base/tokenizer revisions such as `main` are invalid. A local dependency
uses `local-sha256:<directory_digest>`.

Imported history has no trustworthy artifact digest. It uses a non-runnable
historical virtual model ID over:

```json
{
  "identity_kind": "historical_virtual",
  "release_id": "user_import:<content_sha256>",
  "dataset_content_digest": "<prt-dataset-content-v1>",
  "family": "bert",
  "fold_id": 1,
  "loader_recipe_version": "1"
}
```

The bundled release uses its fixed OSF release ID. A local artifact always has
its separate exact runnable identity; historical outputs are never relabelled.

## 7. Prediction runs and reuse

New inference returns one integer `0..4` and five finite probabilities in class
order, each in `[0,1]`, sum tolerance `1e-5`. Bundled and user-imported
predictions also require complete vectors; probabilities are never fabricated.

`reuse` chooses the latest run for exact `(article_id,model_id)` using effective
completion time descending and run ID ascending. It performs no network or
inference when found under `discard`. A missing run retrieves the page and
creates a new UUIDv4 run with action `missing_run_inference`. `recompute` also
retrieves and creates a new UUIDv4 run. Imported run ID is deterministic UUIDv5
from article/model/import.

Explicit `save_local` is independent of run selection. When an existing run is
reused and no content is saved, retrieval may add validated title/body without
inference only if the resolved canonical article ID still equals the run's
article ID. Otherwise nothing is saved.

Local `software_versions_json` records at least application, Python, torch,
transformers, tokenizers, Newspaper3k, and langdetect versions; an unused
optional library is JSON null. Imported runs use `{}` rather than guessed data.

After the state-ledger append, every local inference is mirrored idempotently
to the schema-2 dataset as `prediction_origin=user_evaluation`. The mirror
copies the same run ID, URL, exact local model/fold, hard class, five
probabilities and provenance. It neither changes nor fills an original BERT or
RoBERTa output. Startup may restore a mirrored run absent from state and then
resynchronize all local runs; run IDs prevent duplication.

## 8. Publisher aggregation

Every evaluation uses 2–50 exact runs from one model and publisher.

1. `majority_vote`, version `1`: count hard classes; choose the smallest class
   among ties. This matches `pandas.Series.mode()[0]`.
2. `ordinal_mean`, version `1`: arithmetic mean of hard classes; store full
   finite value, display three decimals, and choose `floor(mean + 0.5)`.
3. `mean_probabilities`, version `1`: require all five probabilities for every
   run, average each component, and choose the smallest maximum index.

No method silently substitutes another. Fewer than two compatible runs is
`INSUFFICIENT_ARTICLES`; missing probability input is
`PROBABILITIES_REQUIRED`. Input order does not change formulas but is stored for
provenance.

## 8.1 Cross-validation leakage guard

For the imported five-fold corpus, `<family>_fold_id=N` means that the stored
prediction was produced for held-out test fold `N`. The corresponding local
checkpoint fold `N` was trained on the other four folds.

Before any new inference, the service compares the normalized article identity
with the imported fold registry for the selected family:

- checkpoint fold `N` may evaluate a known article assigned to test fold `N`;
- checkpoint fold `N` must reject a known article assigned to any other fold
  with `TRAINING_DATA_LEAKAGE`;
- publisher evaluation excludes every known article that is not in the
  checkpoint's held-out fold;
- the guard is checked by the service for single articles, explicit lists and
  publisher candidates, not only by frontend filtering.

Stored historical predictions retain their original fold provenance and are
already held-out outputs for that family/fold. Evaluate exposes such a stored
identity only when a local checkpoint with the same family and fold is present.
This inventory match does not relabel the historical run or claim that the
local artifact digest produced it.

Absence from the imported URL/fold registry is not proof that an arbitrary
external article was absent from every possible training corpus. Such an input
may be classified by a runnable local model, with leakage membership explicitly
unknown outside the registered corpus. The application never infers training
membership from publication date, hostname or text similarity.

## 9. Required result warnings

Article/publisher details state that:

- predictions are estimates, not fact checks;
- softmax values are not necessarily calibrated confidence;
- the demo does not calculate accuracy against protected labels;
- a publisher result depends on selected articles, exact checkpoint/fold, and
  aggregation method;
- optional saved source content remains subject to third-party rights.

## 10. Reproducibility gate

Before a core loader is `compatible`, automated tests verify exact tokenizer,
truncation/padding, strict keys/shapes, frozen English input, predicted class,
five reference probabilities (CPU float32 absolute `1e-6`, relative `1e-5`),
fold identity, aggregation, and absence of protected/editorial leakage.

Live pages are never scientific fixtures. Custom bundle validation is separate
from the frozen core-model output-equivalence fixtures. A custom bundle becomes
runnable after its local tokenizer, architecture, finite safetensors values and
strict key/shape compatibility all pass the documented validation.
