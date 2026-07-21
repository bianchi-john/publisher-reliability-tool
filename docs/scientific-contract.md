# Scientific and Data Contract

**Status:** Updated from the supplied dataset summary and training notebooks.
BERT, RoBERTa, Llama, and Mistral now have notebook-derived loading recipes;
each recipe still requires a reference test against a downloaded release
artifact before implementation is declared scientifically compatible.

## 1. Protected-data boundary

The tool may distribute and display model-produced outputs. It must not
distribute, reproduce, or persist the protected reference data used to train
and evaluate the models.

The following are excluded from the Git repository, tracked sample, application
database, logs, API responses, UI, and exports:

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
| `<family>_fold_id` | Yes for each represented family | Fold integer, normally `1..5` |
| `<family>_prob_class_0` ... `<family>_prob_class_4` | No | Complete probability vector when released |

The recognized family prefixes are `bert`, `roberta`, `llama`, and `mistral`.
A family may be absent from an input file. A represented family must at least
provide its predicted-label and fold columns. Probability columns are accepted
only as a complete five-column vector; partial vectors are invalid.

The importer may convert this wide format into normalized database rows. It
must preserve the original file, retain an import checksum, and report
conflicting duplicate predictions instead of silently choosing one.

The generated bundled release is a documented exception chosen before
publication: exact duplicate URLs are resolved by retaining the first source
row in original CSV order. Its manifest records 19,476 source rows, 19,429
released rows, 42 duplicated URL groups, and 47 skipped later occurrences.
This release rule does not authorize the runtime importer to resolve conflicts
silently in arbitrary user datasets.

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

Empty extraction, parser failure, `langdetect` failure, and short or ambiguous
text must produce an inspectable validation result rather than inference on an
unknown input. The exact short-text policy remains **OPEN**.

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
| Llama | `llama_fold_N.pt` | `meta-llama/Meta-Llama-3-8B`, five-label sequence classification, 4-bit base plus PEFT LoRA | pad token set to EOS; truncate and dynamically pad to 256 tokens | Notebook-derived; actual checkpoint keys still require a release test |
| Mistral | extracted Mistral `fold_N/` PEFT directory | `mistralai/Mistral-Small-24B-Base-2501`, five-label sequence classification, 4-bit base plus PEFT LoRA | saved tokenizer; pad token set to EOS; truncate to 1,024 tokens and dynamically pad to a multiple of 8 | Notebook-derived; released directory contents still require a reference test |

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
- values in `[0, 1]` whose sum is within a declared numeric tolerance of `1`.

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
that model has no output, the application may fetch the article and run the
selected model.

## 8. English-language scope

All newly evaluated articles must be detected as English by `langdetect` after
`newspaper3k` extraction and before tokenization.

- A manually supplied non-English article is rejected with an English message.
- In a multi-article request, non-English items are excluded and reported.
- During publisher discovery, non-English candidates are skipped and requested,
  extracted, rejected, and accepted counts are shown.
- The application does not translate articles.

## 9. Publisher aggregation

A publisher evaluation uses either an explicit same-domain article list or a
user-selected number of articles discovered from one publisher homepage.
Articles from different normalized domains cannot be combined.

The paper-compatible default is the mode of article-level predicted classes:

```text
publisher_prediction(p) = mode(article_predictions for p)
```

The MVP may expose three explicitly named methods:

1. **Majority vote**: the paper-compatible default.
2. **Ordinal class mean**: arithmetic mean of the ordered indices; the decimal
   is shown, and conversion to one class requires a declared rounding rule.
3. **Mean class probabilities**: element-wise mean of complete five-class
   vectors, plus its `argmax` class.

The methods are not interchangeable. Probability averaging is disabled when
any included prediction lacks a vector.

The minimum and default article counts, deterministic tie policy, ordinal
rounding policy, and discovery ordering remain **OPEN**. Until defined, a tie
or insufficient article set is reported as unresolved.

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

## 11. Required scientific warnings

The UI makes these limitations accessible near results:

- an article prediction is an estimate, not factual verification;
- publisher majority voting does not model confidence or uncertainty;
- softmax values are not necessarily calibrated confidence;
- the paper defines the validation scope and should be consulted before
  interpreting outputs;
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
6. absence of protected fields in fixtures, database, logs, UI, and exports.

Live webpages are not stable scientific fixtures. Reference tests must freeze
their allowed input text instead of depending on a publisher page remaining
unchanged.
