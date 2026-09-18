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
2. A publisher method aggregates the compatible article runs of one exact model
   and one normalized publisher: every leakage-safe article the caller has not
   excluded, and at least two of them. Below two, the method reports no class
   rather than presenting a single article as an aggregate.

Every persisted run is immutable. A publisher class is not persisted at all: it
is derived on request from the stored article runs, and it names the model and
the exact articles counted. A newer run never changes an older result, but it
does enter the next reading of its publisher.

## 3. Dataset inputs

The working release is `dataset/predictions/manifest.json` plus
`predictions.csv`. Part size/checksum, row counts, schema, and the stable
`prt-dataset-content-v1` digest of original rows are verified before import.
Schema version 2 declares the `prediction_origin` field, but the tracked
release itself carries only `dataset_original` rows: a user's own
`user_evaluation` rows are mirrored to a separate, private, git-ignored
`dataset/predictions/user-predictions.csv` file instead, and never enter the
tracked release or version control (see §7).

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

The generated bundled release contains 17,283 released URLs, restricted to the
372 publishers with at least 20 classified articles each; outlets below that
threshold are excluded from the release, which is why it carries fewer domains
than the study scraped. Runtime normalization yields 17,269 article IDs, 34,564
unique runs, and 10 historical BERT/RoBERTa family/fold identities. Every run
has one complete five-class probability vector.

Normalization also reveals 13 canonical article identities assigned to more
than one test fold (26 article/family memberships across BERT and RoBERTa).
Their historical predictions remain consultable, but no fold checkpoint is
treated as leakage-safe for a new article or a derived publisher class. A
derived publisher class excludes those identities, and evaluating one directly
fails with `TRAINING_DATA_LEAKAGE`. The application never guesses a fold from
conflicting evidence.

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

The application never executes code from an artifact. Core BERT/RoBERTa
checkpoints cache only pinned tokenizer resources and never download base-model
weights.

### 5.1 Core CPU demo

| Family | Artifact | Base/input recipe |
| --- | --- | --- |
| BERT | `bert_fold_N.pt` | `bert-base-uncased`, five-label sequence classifier, fixed padding/truncation to 256 |
| RoBERTa | `roberta_fold_N.pt` | `roberta-large`, five-label sequence classifier, fixed padding/truncation to 256 |

Both use `torch.load(..., map_location="cpu", weights_only=True)`, strict tensor
keys/shapes, `eval()`, and softmax over five logits. Core compatibility requires
a frozen CPU float32 reference fixture.

### 5.2 One supported model shape

The tool supports exactly one model shape: a five-class encoder classifier built
to the recipe above. There is no second bundle schema, no adapter path and no
reserved import route for another family.

The tool is built to run on an ordinary laptop, so it ships the two encoders
rather than the study's Llama 3 8B and Mistral 24B, which need a CUDA GPU and
tens of gigabytes of weights per fold. Those checkpoints remain published with
the paper for anyone who has that hardware.

Almost nothing is given up by leaving them out, and this is the study's own
finding rather than a convenient excuse:

- RoBERTa is the most accurate publisher-level model of the four (0.69 accuracy,
  ahead of Mistral 24B at 0.68), and publisher-level inference is precisely what
  this tool performs;
- RoBERTa also leads on article-level macro F1 (0.55) and on tolerant accuracy
  (0.84);
- the 24B decoder shows no measurable gain despite a context window four times
  longer, which the study reads as performance being limited by the weak
  supervision in the labels rather than by model size;
- the error analysis finds the same directional biases in all four families,
  describing them as structural properties of the task rather than of any
  architecture or scale.

Scale did not buy accuracy in the study, so a decoder path would cost every
visitor a GPU and return nothing the encoders do not already show. What this
tool demonstrates is the two-stage pipeline — article classification under a
leakage-safe protocol, then publisher-level aggregation — and that demonstration
is complete, and at its most accurate, with the encoders it can actually run.

### 5.3 Custom Transformers bundle

A user model is accepted only as the constrained PRT bundle documented in
`custom-model-bundle.md`: a ZIP container holding a declarative
`prt-model.json`, a Hugging Face `config.json`, a local tokenizer, and exactly
one full `model.safetensors` whose architecture is on the encoder allowlist. The
manifest declares five classes and uses a `custom_...` family plus held-out fold
`1..5`. A bundle declaring any other schema version, or carrying a `model_kind`
or `architecture` field, is refused as invalid input for the reason given in
5.2.

Validation is local-only and uses `trust_remote_code=false`. It rejects
`auto_map`, Python/native modules, pickle/PyTorch checkpoint files, unsafe ZIP
paths or links, unknown manifest fields, missing tokenizer resources,
non-finite weights, incompatible adapter/head metadata, and any key/shape
mismatch against the declared architecture.

The exact bundle file/digest inventory, manifest input policy, family/fold,
training convention and loader recipe determine identity. A valid bundle is
installed below `managed-models` and registered with `user_custom` provenance.
LLM adapters use the pinned base snapshot and may be non-runnable without CUDA.

## 6. Exact model identity

A model ID is SHA-256 of canonical UTF-8 JSON with sorted keys and no
insignificant whitespace. Each kind of model hashes its own document, and every
document carries an `identity_kind`, so two kinds can never collide even when
the rest of their settings coincide. Every key of the chosen document is
present, including nulls; a key that does not appear in it is not part of that
identity and therefore cannot change it.

A validated local core checkpoint:

```json
{
  "identity_kind": "local_validated_artifact",
  "artifact_sha256": "...",
  "family": "bert",
  "fold_id": 1,
  "loader_recipe": "bert_state_dict",
  "loader_recipe_version": "2",
  "base_model": "google-bert/bert-base-uncased",
  "base_revision": "86b5e0934494bd15c9632b12f734a8a67f723594",
  "tokenizer_source": "google-bert/bert-base-uncased",
  "tokenizer_revision": "86b5e0934494bd15c9632b12f734a8a67f723594",
  "class_order": [0, 1, 2, 3, 4],
  "max_tokens": 256,
  "padding_policy": "fixed_max_length"
}
```

An imported custom bundle uses its `artifact_kind` as `identity_kind`
(`custom_transformer_bundle`, or `custom_peft_adapter_bundle` for the refused
adapter contract of §5.2), the directory digest as `artifact_sha256`, and adds
the declared `training_data` object; it carries no tokenizer revision, because
its tokenizer is part of the hashed directory.

An official paper checkpoint is identified by its manifest entry alone, since
that entry already pins every file, digest and recipe:

```json
{
  "identity_kind": "paper_official",
  "official_manifest_entry_sha256": "..."
}
```

For one file, artifact digest is SHA-256 of exact bytes. For a directory, reject
symlinks, enumerate regular files as relative POSIX path/digest/size, sort by
UTF-8 path, canonical-JSON serialize, and hash. Filesystem locator, device path,
and cache path are excluded. A missing artifact changes availability, never the
scientific model ID or historical runs. The digest is rechecked immediately
before loading, preventing changed bytes from running under an earlier model
identity.

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
Only `bundled_import` and `user_import` runs establish held-out-fold evidence;
a local inference run never changes article membership.

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
to a private, git-ignored `dataset/predictions/user-predictions.csv` as
`prediction_origin=user_evaluation`. The mirror copies the same run ID, URL,
exact local model/fold, hard class, five probabilities and provenance. It
neither changes nor fills an original BERT or RoBERTa output, and it never
touches the tracked `predictions.csv` release: a user's own evaluation history
must never enter version control. Startup may restore a mirrored run absent
from state and then resynchronize all local runs; run IDs prevent duplication.
A mirrored row is re-validated before it may re-enter the ledger, and its
`prediction_origin` must be `user_evaluation`: the mirror is an editable file, and a
row claiming to be released dataset material must never be restored as a local
evaluation under a provenance it does not have.

## 8. Publisher aggregation

Every aggregation uses at least two runs from one exact checkpoint and one
normalized publisher; folds of the same family are separate measurements (§8.1).

1. `majority_vote`, version `2`: count hard classes; choose the smallest class
   among ties. This matches `pandas.Series.mode()[0]`.
2. `ordinal_mean`, version `2`: arithmetic mean of hard classes; store full
   finite value, display three decimals, and choose `floor(mean + 0.5)`.
3. `median_class`, version `1`: lower median of the hard classes, so a few
   extreme articles cannot move the verdict the way a mean can.
4. `mean_probabilities`, version `2`: require all five probabilities for every
   run, average each component, and choose the smallest maximum index.
5. `expected_class`, version `1`: centre of mass of the averaged probability
   vector, `sum(k * mean P(k))`, rounded by `floor(value + 0.5)`. This is the
   method closest to treating reliability as the 0–100 grade beneath the bands.
6. `confidence_weighted_vote`, version `1`: a majority vote in which each
   article contributes its own maximum probability instead of one whole vote.

No method silently substitutes another. Fewer than two compatible runs is
`INSUFFICIENT_ARTICLES`; missing probability input is
`PROBABILITIES_REQUIRED`. Input order does not change formulas but is stored for
provenance.

### 8.1 One measurement is one checkpoint

Runs are never pooled across models, not even across folds of one family. The
study split publishers between folds, so each checkpoint saw a different part of
the corpus; merging their verdicts would report a number no model produced, and
would hide any publisher whose articles unexpectedly straddle a fold boundary.
Those cases are anomalies worth surfacing, not smoothing over. One run per
article per model is counted, the newest by effective time.

### 8.2 No tolerant counting mode

The study reports a tolerant accuracy, which counts a prediction correct when it
lands in a band adjacent to the true one. That metric requires a true label.
Aggregation has none: it compares articles with the verdict they themselves
produced. Spreading each vote onto its neighbours would therefore not measure
tolerance to error but merely smooth the vote histogram, using a weight nobody
measured, and it would duplicate what `ordinal_mean`, `median_class` and
`expected_class` already do openly. An adjacent-class allowance is applied only
where it needs no ground truth: to the dispersion statistics below.

### 8.3 Dispersion

Every result reports, over the counted articles: the mean class, the population
variance of the class indices, the share of articles matching the verdict
exactly and within one class, and a variance that charges nothing for landing in
an adjacent class. These are statements about how far the articles sit from each
other and from the verdict, so they need no true label. The two that allow an
adjacent class are measured relative to the verdict and therefore move when the
counting rule does. The variance is banded by publisher-level error rates
measured on the study corpus at ten articles per outlet:

| Variance | Majority error | Tolerant error | Band |
| --- | --- | --- | --- |
| below 0.25 | about 4% | about 1% | stable |
| 0.25 to 1.00 | 43–55% | 12–18% | elevated |
| 1.00 and above | 64–82% | 22–43% | high |

The cliff at 0.25 is the reason the bands exist: immediately above it the
publisher-level error rate multiplies roughly tenfold. A verdict is never shown
without its band.

### 8.4 Cross-validation leakage guard

For the imported five-fold corpus, `<family>_fold_id=N` means that the stored
prediction was produced for held-out test fold `N`. The corresponding local
checkpoint fold `N` was trained on the other four folds.

Fold membership is a property of the article, not of the model family. Every
family in the study was split by the same publisher-disjoint
`StratifiedKFold(n_splits=5, shuffle=True, random_state=42)` over the same
publisher list, so an article held out in fold `N` is held out in fold `N` for
every family, and was in the training set of the other four folds of every
family. The released dataset carries BERT and RoBERTa predictions only;
recording the registry per family would therefore leave any other family with no
fold evidence at all, and the guard would pass every article for exactly those
models. The registry is keyed by article so the guard applies uniformly to every
family, including one added later.

Before any new inference, the service compares the normalized article identity
with the imported fold registry:

- checkpoint fold `N` may evaluate a known article assigned to test fold `N`;
- checkpoint fold `N` must reject a known article assigned to any other fold
  with `TRAINING_DATA_LEAKAGE`, whatever the checkpoint's family;
- a derived publisher class excludes every known article that is not in the
  checkpoint's held-out fold;
- the guard is checked by the service, both for the single article an
  evaluation classifies and for every article a derived publisher class counts,
  not only by frontend filtering.

Stored historical predictions retain their original fold provenance and are
already held-out outputs for that family/fold. Evaluate exposes such a stored
identity only when a local checkpoint with the same family and fold is present.
This inventory match does not relabel the historical run or claim that the
local artifact digest produced it.

Absence from the imported URL/fold registry is not proof that an arbitrary
external article was absent from every possible training corpus. Such an input
may be classified by a runnable local model, with leakage membership explicitly
unknown outside the registered corpus. The application never infers training
membership from publication date, hostname, text similarity, or a previous
local inference. Evaluating an external URL with fold 1 does not assign that
URL to test fold 1 and does not by itself block fold 2.

## 9. Required result provenance

Classes are always labelled `Class 0` through `Class 4` and always described as
model predictions, never as facts or ground truth (§1). The demo calculates no
accuracy, because it holds no reference labels to calculate one against.

Rather than repeat a standing disclaimer beside every result, each result names
what it actually depends on:

- an article result names its exact model, fold, run identifier and origin;
- a publisher result names the counting method and the exact articles counted,
  and reports the dispersion of those articles and its risk band, so a class is
  never shown without the disagreement behind it;
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
