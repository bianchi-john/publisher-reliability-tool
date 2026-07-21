# Scientific and Data Contract

**Status:** Normative MVP scientific contract derived from the supplied dataset,
paper, and training notebooks. A loader is selectable only after its automated
reference fixture passes the reproducibility gate in Section 12.

## 1. Protected-data boundary

The tool may distribute and display model-produced outputs. It must not
distribute, reproduce, or persist the protected reference data used to train
and evaluate the models.

The following are excluded from the Git repository, tracked sample, application
CSV database, logs, API responses, UI, and exports:

- original reference labels;
- original numeric reference scores or ranges;
- metadata originating from the reference rating provider;
- mappings, tables, or derived fields that expose or reconstruct those values.

A private CSV containing those columns may be selected on the user's own
machine. Import is an allowlisted projection: blocked columns are ignored
before persistence, and the warning may name their columns but must never print
their values. The source CSV remains unchanged.

The public tool presents predicted output indices as `Class 0` through
`Class 4`. It does not include protected class names, score intervals, or a
mapping back to the reference provider.

## 2. Task definition

The released models implement a two-stage process:

1. an article-level classifier outputs one of five ordered predicted indices;
2. a publisher-level function aggregates compatible article predictions from
   several articles belonging to the same publisher.

The five public indices are exactly the integers `0`, `1`, `2`, `3`, and `4`.
The supplied notebook sorts the five input labels and maps them to contiguous
indices; for the inspected dataset that mapping is the identity mapping.

These values are model predictions. The tool must not present them as facts,
fact checks, or protected ground-truth ratings.

## 3. Dataset contract

The repository contains a public history as a manifest and ordered CSV parts.
The application validates and imports that release incrementally on first use.
At startup or through the frontend, the user may also select any CSV or
manifest directory that conforms to the supported schema; there is no
scientific requirement on its number of rows or total size.

`dataset/sampleDataset.csv` is a small, tracked, synthetic structural example.
The private `dataset/fullDataset.csv` remains ignored by Git. The generated
`dataset/predictions/` release contains scraped article fields and model outputs
but none of the protected reference-provider columns.

The current wide-format schema is:

| Field | Required | Meaning |
| --- | --- | --- |
| `article_id` | No | Source-local identifier; never the application identity |
| `url` | Yes | Canonical article URL and application article identity |
| `title` | No | Locally supplied or extracted title |
| `text` | No | Locally supplied or extracted article body |
| `authors` | No | Locally supplied or extracted author display value |
| `domain` | Yes | Normalized publisher domain and publisher identity |
| `<family>_predicted_label` | Yes for each represented family | Predicted integer in `0..4` |
| `<family>_fold_id` | Yes for each represented family | Fold integer in `1..5` |
| `<family>_prob_class_0` ... `<family>_prob_class_4` | No | Complete probability vector when released |

The recognized family prefixes are `bert`, `roberta`, `llama`, and `mistral`.
A family may be absent from an input file. A represented family must at least
provide its predicted-label and fold columns. Probability columns are accepted
only as a complete five-column vector; partial vectors are invalid.

The importer applies the following conversion without implementation-specific
guessing:

- source `article_id` values are never application identifiers; they are used
  only in an import diagnostic when present;
- `url` is stripped of surrounding whitespace and normalized under the URL
  contract below; that canonical URL becomes `article_id`;
- `domain` is recomputed from the canonical URL. A non-empty source `domain`
  that normalizes to a different publisher rejects the row;
- `title` and `text` are preserved exactly after RFC 4180 CSV decoding,
  including embedded newlines. The importer performs no trimming or cleaning;
- an empty `authors` value becomes `[]`. A valid JSON array containing only
  strings is preserved. Any other non-empty value becomes a one-element JSON
  string array; commas are never interpreted as author separators;
- for every represented model family, `predicted_label` must be an integer in
  `0..4` and `fold_id` must be an integer in `1..5` on every row;
- a probability vector must be either entirely empty or contain all five
  finite probabilities and satisfy the probability contract below.

Any row that violates these rules is rejected with its source row number and a
stable error code. Valid rows from the same import continue to be processed.

The importer converts this wide format into the normalized CSV ledgers defined
in `csv-storage-contract.md`. It must leave a server-local source file
unchanged, retain an import checksum, and report
conflicting duplicate predictions instead of silently choosing one.

The generated bundled release is a documented exception chosen before
publication: exact duplicate URLs are resolved by retaining the first source
row in original CSV order. Its manifest records 19,476 source rows, 19,429
released rows, 42 duplicated URL groups, and 47 skipped later occurrences.

Runtime canonicalization further maps those 19,429 released URL strings to
19,411 article identities. There are 18 later normalized aliases. For this
verified bundled release only, article metadata comes from the first released
row in manifest part/row order, while later rows can contribute predictions for
a different family/fold identity. Identical repeated `(article, family, fold)`
outputs are deduplicated; a conflicting repeated output would fail seed import.
The current result is exactly 77,708 unique predictions across 20 historical
virtual family/fold models. This release rule does not authorize the runtime
importer to resolve conflicts silently in arbitrary user datasets.

The public release retains real URLs, domains, titles, article bodies, and
authors. Those article fields originate from their respective publishers; the
release does not claim ownership of them or change their copyright status.

## 4. Text acquisition and model input

The experimental text pipeline did not apply text cleaning, stemming,
lemmatization, case normalization, or any other linguistic preprocessing.

For a new URL, the application reproduces this boundary:

1. discover article URLs from a publisher homepage with `newspaper3k`, or
   accept an article URL directly;
2. download and parse each page with `newspaper3k`;
3. use the parser's extracted article text as the classifier text input;
4. run `langdetect` on that extracted text and accept it only when the detected
   code is `en`;
5. pass the unchanged extracted text to the selected model tokenizer.

Tokenizer operations such as subword tokenization, truncation, attention-mask
creation, and padding are required model-input encoding, not an additional
text-cleaning stage. URL canonicalization also does not modify the classifier
text.

Empty extraction and parser failure produce `EXTRACTION_FAILED` or `TEXT_EMPTY`.
Before language detection, the application normalizes no content but measures
the extracted string. Text is `TEXT_TOO_SHORT` when, after trimming surrounding
whitespace only, it contains fewer than 200 Unicode characters or fewer than 30
whitespace-delimited tokens. No inference runs on such text.

Language detection uses `langdetect.DetectorFactory.seed = 0`. A detector
exception is `LANGUAGE_DETECTION_FAILED`; any result other than exact code `en`
is `NON_ENGLISH`. These application validation gates do not claim to reproduce
an additional training-time preprocessing stage.

## 5. Released checkpoint recipes

The official model artifacts are available from:

<https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

The MVP provides the link and manual placement instructions but does not
automatically download large artifacts. BERT, RoBERTa, and Llama are PyTorch
`state_dict` `.pt` checkpoints. Mistral is different: its notebook saves each
fold with PEFT `save_pretrained()` and saves the tokenizer into the same fold
directory.

| Family | Recognized artifact | Reconstructed base | Tokenizer/input | Checkpoint status |
| --- | --- | --- | --- | --- |
| BERT | `bert_fold_N.pt` | `bert-base-uncased`, sequence classification, five labels | `AutoTokenizer`; truncate and fixed-pad to 256 tokens | Notebook-derived |
| RoBERTa | `roberta_fold_N.pt` | `roberta-large`, sequence classification, five labels | fast `AutoTokenizer`; truncate and fixed-pad to 256 tokens | Notebook-derived |
| Llama | `llama_fold_N.pt` | `meta-llama/Meta-Llama-3-8B`, five-label sequence classification, 4-bit base plus PEFT LoRA | pad token set to EOS; truncate and dynamically pad to 256 tokens | Notebook-derived; selectable only after strict-key and reference-output tests pass |
| Mistral | extracted Mistral `fold_N/` PEFT directory | `mistralai/Mistral-Small-24B-Base-2501`, five-label sequence classification, 4-bit base plus PEFT LoRA | saved tokenizer; pad token set to EOS; truncate to 1,024 tokens and dynamically pad to a multiple of 8 | Notebook-derived; selectable only after PEFT-config and reference-output tests pass |

`N` is the fold and is part of model identity. Any available fold may be used
independently; the MVP does not silently ensemble folds.

The inspected Llama recipe uses:

- 4-bit NF4 quantization with double quantization and `bfloat16` computation;
- LoRA `r=8`, alpha `16`, dropout `0.05`, no bias, task `SEQ_CLS`;
- target modules `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`,
  `down_proj`, and `up_proj`.

The inspected Mistral recipe uses:

- base model `mistralai/Mistral-Small-24B-Base-2501`;
- 4-bit NF4 quantization with double quantization and `bfloat16` computation;
- LoRA `r=16`, alpha `32`, task `SEQ_CLS`, and target modules `q_proj`,
  `k_proj`, `v_proj`, and `o_proj`;
- PEFT defaults for LoRA options not overridden by the notebook, with the
  released `adapter_config.json` treated as the final machine-readable source;
- maximum sequence length 1,024, no tokenizer-time padding, followed by
  `DataCollatorWithPadding(..., pad_to_multiple_of=8)`;
- Flash Attention 2 when installed and an eager-attention fallback otherwise;
- a CUDA device in the experimental implementation.

Although the supplied notebook filename contains `mistral22B`, its executable
configuration and result path identify the 24B model. The loader contract
therefore follows `Mistral-Small-24B-Base-2501`; it must not infer a 22B base
from the notebook filename.

Because a `state_dict` contains weights but no tokenizer files or reliable
architecture metadata, the relevant base configuration and tokenizer must be
available in the local Transformers cache or downloaded during an explicit
setup action. A Mistral fold directory includes its adapter configuration,
adapter weights, and tokenizer files, but not the 24B base weights. Llama may
additionally require authorized access to its base model. No released artifact
eliminates its declared base-model dependency.

### Built-in loading contract

For BERT and RoBERTa, the adapter follows this logical sequence:

```python
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
model = AutoModelForSequenceClassification.from_pretrained(
    BASE_MODEL,
    num_labels=5,
)
state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
model.load_state_dict(state, strict=True)
model.eval()
probabilities = torch.softmax(model(**encoded).logits, dim=-1)
predicted_class = int(probabilities.argmax(dim=-1))
```

The Llama adapter must first reconstruct the documented quantized base and PEFT
wrapper, then validate checkpoint keys before enabling inference.

For Mistral, the adapter follows this logical sequence:

```python
peft_config = PeftConfig.from_pretrained(fold_directory)
assert peft_config.base_model_name_or_path == MISTRAL_BASE_MODEL
validate_mistral_lora_recipe(peft_config)

tokenizer = AutoTokenizer.from_pretrained(fold_directory)
tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token

base = AutoModelForSequenceClassification.from_pretrained(
    MISTRAL_BASE_MODEL,
    num_labels=5,
    quantization_config=MISTRAL_4BIT_NF4_CONFIG,
    device_map="auto",
    dtype=torch.bfloat16,
)
base.config.pad_token_id = tokenizer.pad_token_id
model = PeftModel.from_pretrained(base, fold_directory)
model.eval()
```

Inference tokenization uses truncation at 1,024 tokens and dynamic padding to a
multiple of 8. Flash Attention 2 is an optional optimization, not a condition
for prediction equivalence; eager attention is the documented fallback.
Loading an official checkpoint must not execute code embedded in the artifact.

The filename is sufficient only for a recognized official `.pt` recipe.
Mistral recognition uses its standard PEFT configuration plus the approved
base-model identity and expected fold directory. An unknown custom checkpoint
requires an explicit supported family selection or a separate manifest
describing architecture, tokenizer, input length, class count, adapter
relationship, and runtime requirements. The tool must reject ambiguity instead
of guessing.

## 6. Probability contract

A fully compatible adapter for new inference returns:

- one predicted integer in `0..4`;
- five finite softmax values in class-index order;
- values in `[0, 1]` whose sum differs from `1` by at most `1e-5`.

The available historical table contains probability vectors for BERT and
RoBERTa but not for Llama and Mistral. Missing historical vectors remain
missing: the tool must not fabricate a one-hot vector or rerun a model unless
the user explicitly requests a new model-specific evaluation.

The UI calls softmax outputs "model probabilities", not calibrated confidence,
unless calibration is separately demonstrated.

## 7. URL identity and historical reuse

The MVP adopts this identity policy:

```text
article identity    = canonical article URL
publisher identity  = normalized publisher domain
prediction identity = canonical article URL + model identity
```

No content hash or article-version comparison is used. For a submitted URL,
the application removes fragments and known non-identifying parameters,
checks local history, and only on a miss follows redirects and reads a declared
canonical URL. It then checks history again and derives the publisher domain
from the final URL.

If the canonical URL and selected model already have an output, that output is
returned without downloading or comparing article text. If the URL exists but
that model has no output, stored text is usable only when it passes the minimum
length gate and deterministic English check. Imported text with an empty
`detected_language` is checked locally at this point; on successful prediction,
the same transaction appends an article version with `detected_language=en`
without changing its text. Fetching occurs only when stored text is absent or
fails either gate and strict offline mode is false.

## 8. English-language scope

All newly evaluated articles must be detected as English by `langdetect` after
`newspaper3k` extraction and before tokenization.

- A manually supplied non-English article is rejected with an English message.
- In a multi-article request, non-English items are excluded and reported.
- During publisher discovery, non-English candidates are skipped and requested,
  extracted, rejected, and accepted counts are shown.
- The application does not translate articles.

## 9. Publisher aggregation

A publisher evaluation uses 2–50 compatible predictions from one exact model
identity and one normalized publisher hostname. Input is either an explicit
same-publisher list or a publisher request whose default requested count is 10.
Articles from different normalized hostnames cannot be combined.

The paper-compatible default is the mode of article-level predicted classes:

```text
publisher_prediction(p) = mode(article_predictions for p)
```

The MVP exposes exactly three methods:

1. **`majority_vote`**, method version `1`: count hard predicted classes. The
   result is the class with maximum count. If several classes tie, choose the
   numerically smallest tied class. This matches the notebook expression
   `group[column].mode()[0]` and is the paper-compatible default.
2. **`ordinal_mean`**, method version `1`: compute
   `raw_mean = sum(predicted_class) / n`. Store the full finite float, display it
   to three decimal places, and compute the result class as
   `floor(raw_mean + 0.5)`. Because inputs are `0..4`, the result remains `0..4`.
3. **`mean_probabilities`**, method version `1`: require a complete valid vector
   for every prediction, compute each output component as its arithmetic mean,
   and choose the numerically smallest class whose mean component equals the
   maximum. Store all five mean components and the result class.

The methods are not interchangeable. Probability averaging is disabled with
`PROBABILITIES_REQUIRED` when any included prediction lacks a vector. Fewer
than two compatible successful predictions is `INSUFFICIENT_ARTICLES`; no
publisher result is created. Ordering does not change these commutative formulas
but is preserved exactly for provenance.

## 10. Compatibility and provenance

- Predictions from different artifacts or folds are not mixed unless an
  explicit ensemble is later defined.
- A changed base revision, tokenizer, input length, padding policy, class order,
  or adapter configuration changes model identity.
- Each imported output retains its family and fold.
- Each new output retains the checkpoint checksum, recipe version, extraction
  and tokenizer settings, software versions, device, timing, and status.
- Imported, reused, and newly computed results retain distinct provenance.
- Probability aggregation requires complete vectors for every included item.
- The class order remains `0 < 1 < 2 < 3 < 4`; no protected score mapping is
  stored or shown.

### Exact and historical model identity

`artifact_sha256` is deterministic. For a single-file artifact it is SHA-256
of the exact file bytes. For a directory artifact, symlinks are rejected; the
application recursively enumerates regular files, excludes only
`publisher-reliability-model.json`, represents each as
`{"path":<relative POSIX path>,"sha256":<file digest>,"size":<bytes>}`,
sorts entries by the UTF-8 bytes of `path`, serializes the array as canonical
JSON (sorted object keys, no insignificant whitespace), and hashes those UTF-8
bytes. Empty directories and filesystem metadata are not represented. Uploaded
archives are hashed after safe extraction using this directory rule, so archive
compression and entry order do not change model identity.

A runnable model ID is the SHA-256 of UTF-8 canonical JSON with sorted keys and
no insignificant whitespace containing:

```json
{
  "artifact_sha256": "...",
  "base_model": "...",
  "base_revision": "...",
  "family": "bert",
  "fold_id": 1,
  "loader_recipe": "bert_state_dict",
  "loader_recipe_version": "1",
  "max_tokens": 256,
  "padding_policy": "fixed_max_length",
  "tokenizer_revision": "...",
  "tokenizer_source": "bert-base-uncased"
}
```

Every key is required. Any changed artifact, revision, tokenizer, length,
padding, or recipe creates a new model ID.

Remote Hugging Face identities resolve `base_revision` and
`tokenizer_revision` to immutable repository commit hashes; mutable names such
as `main` are never stored as exact revisions. A fully local base or tokenizer
uses `local-sha256:<directory_digest>` with the directory algorithm above. If
an immutable revision cannot be established, registration is
`MODEL_INCOMPATIBLE` rather than creating a non-reproducible identity.

The public historical CSV does not contain artifact checksums. Its importer
therefore creates one `historical_virtual` model per family and fold. Its model
ID is the SHA-256 of canonical JSON:

```json
{
  "dataset_content_digest": "76d1434f47df497c62c0dc360b824f3edf797c6501e2bcde560ff2c3378867ea",
  "family": "bert",
  "fold_id": 1,
  "identity_kind": "historical_virtual",
  "loader_recipe_version": "1",
  "release_id": "osf:r9atz:e4bda170a3e74ca3ae245475d4486d74"
}
```

`family` and `fold_id` vary per imported output. A user-supplied historical
import uses `release_id = "user_import:<source_sha256>"` and that import's
`dataset_content_digest` is exactly the lowercase SHA-256 of the uploaded or
server-local source bytes. For the bundled multipart release only, it is the
manifest's verified `content_digest_sha256`. These rules prevent unrelated
files from sharing a virtual model and avoid an undefined reserialization step.

Such a model is `historical_only`: stored outputs can be browsed and aggregated
but it cannot infer a missing prediction. Registering a local artifact creates
a separate exact model ID; historical outputs are not silently claimed as
outputs of that artifact. A missing exact prediction can still be computed
offline from stored article text.

## 11. Required scientific warnings

The UI makes these limitations accessible near results:

- an article prediction is an estimate, not factual verification;
- publisher majority voting does not model confidence or uncertainty;
- softmax values are not necessarily calibrated confidence;
- the paper defines the validation scope governing interpretation of outputs;
- the public tool does not calculate accuracy against protected labels;
- a publisher result depends on the selected articles, checkpoint, and
  aggregation method.

## 12. Reproducibility gate

Before a family adapter is called compatible, an automated fixture must verify:

1. the documented tokenizer, truncation, and padding behavior;
2. strict checkpoint-key and tensor-shape compatibility;
3. the expected predicted index for a frozen synthetic or otherwise
   redistributable English text fixture;
4. five probabilities matching a reference run within tolerance;
5. correct fold identity and publisher aggregation;
6. absence of protected fields in fixtures, CSV database, logs, UI, and exports.

Live webpages are not stable scientific fixtures. Reference tests must freeze
their allowed input text instead of depending on a publisher page remaining
unchanged.
