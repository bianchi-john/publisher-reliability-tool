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

The bundled release is `dataset/predictions/manifest.json` plus ordered CSV
parts. Part sizes/checksums, row counts, schema, and
`prt-dataset-content-v1` digest are verified before import.

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

User CSV/CSV.GZ requires `url` and at least one represented family's label/fold
pair. Source ID, domain, title, text, and authors are optional. Supported family
prefixes are `bert`, `roberta`, `llama`, and `mistral`.

Projection rules:

- normalize URL, derive UUIDv5 article ID, recompute publisher hostname/ID;
- discard editorial/blocked values before staging or error formatting;
- reject a non-empty source domain that disagrees after normalization;
- validate class `0..4`, fold `1..5`, and complete probability vector;
- deduplicate identical article/model output in one source;
- if outputs conflict for one article/model in that source, publish none of
  that pair and report safe row numbers under `IMPORT_INVALID`.

The generated bundled release alone uses its documented first-exact-URL policy:
19,476 source rows become 19,429 released URLs after 47 skipped later
occurrences in 42 groups. Runtime normalization yields 19,411 article IDs,
77,708 unique runs, and 20 historical family/fold model identities. A conflict
at that stage fails seed verification.

The sole content digest is `prt-dataset-content-v1` as defined by the storage
contract. Equivalent CSV/CSV.GZ projected record sequences share identity;
compression is not scientific identity.

## 4. Article input

Online input follows this exact boundary:

1. retrieve HTML through the safe application client;
2. give already downloaded HTML to `newspaper3k`;
3. take its extracted article text without cleaning, case normalization,
   stemming, or lemmatization;
4. trim only for minimum-length measurement; require at least 200 Unicode
   characters and 30 whitespace-delimited tokens;
5. run `langdetect` with `DetectorFactory.seed = 0` and require exact `en`;
6. pass unchanged extracted text to the selected tokenizer;
7. discard HTML/authors always and title/body unless `save_local` is explicit.

Tokenizer subwords, truncation, attention masks, and padding are model encoding,
not text cleaning. Saved local body is used unchanged for a missing run under
`reuse`. `recompute` always retrieves a fresh page.

## 5. Core and optional models

Official artifacts are manually obtained from:

<https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

The package contains `official-model-manifest-v1.json` with one immutable entry
per official family/fold: expected artifact digest, built-in loader recipe and
version, class order, input length/padding, output-relevant runtime options,
base/tokenizer repositories, and immutable revisions. The application does not
download dependencies or read a custom manifest from an artifact.

### 5.1 Core CPU demo

| Family | Artifact | Base/input recipe |
| --- | --- | --- |
| BERT | `bert_fold_N.pt` | `bert-base-uncased`, five-label sequence classifier, fixed padding/truncation to 256 |
| RoBERTa | `roberta_fold_N.pt` | `roberta-large`, five-label sequence classifier, fixed padding/truncation to 256 |

Both use `torch.load(..., map_location="cpu", weights_only=True)`, strict tensor
keys/shapes, `eval()`, and softmax over five logits. Core compatibility requires
a frozen CPU float32 reference fixture.

### 5.2 Optional GPU examples

| Family | Artifact | Recipe |
| --- | --- | --- |
| Llama | `llama_fold_N.pt` | Llama-3-8B five-label base, 4-bit NF4, documented LoRA, 256 tokens |
| Mistral | official fold PEFT directory | Mistral-Small-24B-Base-2501, 4-bit NF4, saved tokenizer/adapter, 1,024 tokens |

These loaders are experimental examples. They may require CUDA,
bitsandbytes/PEFT, licensed base access, and substantial memory. Absence or
failure does not fail the core release. Their exact notebook-derived LoRA
target modules, quantization, padding, and adapter configuration remain pinned
in the official manifest and participate in identity.

Adding a family means implementing a new explicit `ModelLoader`, defining its
complete identity object, and adding frozen tokenizer/output fixtures. A generic
manifest interpreter, `trust_remote_code`, executable pickle behavior, or
runtime module path is forbidden.

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
order, each in `[0,1]`, sum tolerance `1e-5`. Historical probabilities may be
missing and are never fabricated.

`reuse` chooses the latest run for exact `(article_id,model_id)` using effective
completion time descending and run ID ascending. It performs no network or
inference when found under `discard`. A missing run may use validated saved text
or retrieve the page. `recompute` always retrieves and creates a new UUIDv4 run.
Imported run ID is deterministic UUIDv5 from article/model/import.

Explicit `save_local` is independent of run selection. When an existing run is
reused and no content is saved, retrieval may add validated title/body without
inference only if the resolved canonical article ID still equals the run's
article ID. Otherwise nothing is saved.

Local `software_versions_json` records at least application, Python, torch,
transformers, tokenizers, PEFT, newspaper3k, and langdetect versions; an unused
optional library is JSON null. Imported runs use `{}` rather than guessed data.

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

Live pages are never scientific fixtures. Llama/Mistral/GPU fixtures are a
separate optional suite and do not block the CPU research demo.
