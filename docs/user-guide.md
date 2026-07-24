# User Guide

This guide describes the current browser workflow for models, article
predictions, and publisher aggregations.

> Predictions are estimates, not fact checks or ground-truth ratings. Softmax
> values are not necessarily calibrated confidence.

## 1. Understand the dashboard counts

- **Stored predictions** are immutable article-level outputs. The bundled
  release contains BERT and RoBERTa only, with one predicted label and all five
  class probabilities for every run.
- **Created aggregations** are publisher-level results explicitly created in
  Evaluate. This count can be zero even when tens of thousands of stored article
  predictions are available.
- **Model identities** includes historical identities from imported data and
  local runnable artifacts. A historical identity is useful for provenance but
  is not itself an installed checkpoint.

The bundled release produces 19,411 normalized articles, 38,854 prediction
runs, and 10 historical BERT/RoBERTa family/fold identities. Llama and Mistral
outputs are not included because their five per-class probabilities were not
available.

## 2. Make models available

Install the locked inference dependencies before starting the application:

```bash
uv sync --frozen --extra models
```

There are two supported model paths.

### Core BERT or RoBERTa checkpoint

1. Copy `bert_fold_N.pt` or `roberta_fold_N.pt` below a configured models
   directory, normally `./models`.
2. Restart the application or open **Models** and select **Scan configured
   directories**.
3. Confirm that the local identity is `compatible` and runnable.

Startup scans configured roots automatically. The Models page also performs one
session scan when it finds no local identities; the explicit scan button is
available after files are added, removed, or replaced.

Core checkpoints contain model weights but not the official tokenizer files.
On first online inference the application may cache only the small tokenizer
and configuration resources from the pinned immutable Hugging Face revision.
It never downloads base-model weights.

### Custom Transformers model

A standalone `.pt` file is not a custom model bundle. Export a self-contained
ZIP containing:

```text
prt-model.json
config.json
model.safetensors
tokenizer_config.json
tokenizer resources
```

Open **Models → Import custom Transformer**, review the three-step example shown
above the upload control, select the ZIP, and wait for the validation job. A
valid bundle is installed under the managed data directory, appears as
`compatible`, and is immediately runnable without a network model download.

The model must be a five-label architecture supported by the locked
Transformers version. The application rejects executable code, pickle/PyTorch
weights, unsafe ZIP paths, remote tokenizer dependencies, non-finite tensors,
and state-dictionary key/shape mismatches. See
[Custom Transformers bundle](custom-model-bundle.md) for the complete manifest
and export contract.

## 3. Evaluate one article

1. Open **Evaluate** and choose **Single article**.
2. Enter the full public article URL.
3. Wait for the application to inspect stored prediction coverage and the local
   Models inventory.
4. Select one of the options actually available for that URL and start the job.

The selector does not show a hard-coded catalog:

- `stored prediction` means a compatible prediction already exists and can be
  reused;
- `new local inference` means the URL has no exact stored run and the selected
  local checkpoint will retrieve and classify it;
- historical identities or absent folds are not presented as runnable choices.

For known five-fold dataset articles, checkpoint fold `N` is permitted only
when the article belongs to held-out fold `N`. Other checkpoints are hidden and
the backend rejects direct attempts with `TRAINING_DATA_LEAKAGE`. For an
external URL not present in the fold registry, training membership is unknown;
the application does not pretend that absence proves exclusion from every
possible training corpus.

New-page retrieval:

- allows only public HTTP(S) destinations and validates every redirect;
- sends `Accept-Language: en-US,en;q=0.9`;
- gives the downloaded HTML to Newspaper3k with `language="en"`;
- uses no secondary extractor when Newspaper3k cannot parse the page;
- requires at least 200 characters and 30 words;
- accepts only text deterministically detected as English.

The completed Evaluate card shows the predicted `Class 0..4`, every probability
as a decimal and percentage bar, exact family/fold, stored-versus-new status,
prediction-run ID, and a link to the complete article history. The **Recent
user article evaluations** table reloads persisted local inference runs after a
page refresh.

Every completed new inference is stored in two coordinated places:

- `data/state/prediction_runs.csv` is the authoritative application ledger;
- `dataset/predictions/predictions.csv` contains an inspectable mirror row with
  `prediction_origin=user_evaluation`.

The mirrored row includes the run ID, URL, exact model ID/family/fold, predicted
label, all five probabilities, action, timestamps, duration, device and
software versions. Existing release rows use
`prediction_origin=dataset_original`. A repeated start or synchronization does
not duplicate a prediction because the run ID is unique.

Common availability messages have distinct meanings:

- **No validated local checkpoint**: add/scan a supported artifact or import a
  custom ZIP.
- **New article requires inference, but no runnable local model is available**:
  a model identity may exist, but no installed artifact passed runnable
  validation.
- **Training-data leakage**: the local fold was trained on that known dataset
  article.
- **Insufficient safe articles**: a publisher does not have enough compatible
  held-out stored runs for the requested count.

Retrieval, extraction, language, tokenizer, model-loading, and inference
failures are reported separately. Strict offline mode can reuse stored runs but
cannot retrieve a new article.

## 4. Browse Articles & predictions

The page exposes **All**, **Dataset**, and **User-evaluated** views.

- A **Dataset article** has at least one run imported from the bundled release
  or a user CSV/CSV.GZ.
- A **User evaluated** article has no imported run and was created through
  local inference.
- A dataset article that is subsequently inferred locally remains a dataset
  article and also displays **Also evaluated by user**.

Article details list every run, including all five probabilities, exact
model/fold, origin, and run ID. The API derives these source fields from run
origins; it does not guess from the URL:

| Run origin | Display meaning |
| --- | --- |
| `bundled_import` | Original dataset |
| `user_import` | Imported dataset |
| `local_inference` | User evaluation |

The article CSV export includes the same derived source counts and flags but
never includes saved body text, authors, or raw HTML.

Run origin in the application ledger (`local_inference`) and row origin in the
combined prediction dataset (`user_evaluation`) describe the same user-created
inference at two storage boundaries.

## 5. Evaluate a publisher

Choose **Publisher**, enter its URL, select an available stored model/fold, an
aggregation method, and a requested count from 2 to 50. Publisher mode
aggregates only compatible leakage-safe predictions already stored for that
publisher; it does not crawl the site or infer missing publisher articles.

**Use the available articles** permits a partial aggregate only when at least
two safe articles exist. **Require the full count** fails unless the requested
number is available. Publisher count, aggregation method, and partial-result
controls are hidden in single-article mode because they do not apply there.

Publisher pages distinguish:

- article and prediction counts already present in history; and
- publisher evaluations explicitly created in this workspace.

An evaluation count of zero therefore does not mean that the publisher has no
article predictions.

## 6. Theme and navigation

Use the button in the top bar to switch between light and dark mode. Without an
explicit choice the interface follows the operating-system preference. A manual
choice is saved only in browser local storage and restored on later visits.

The application bundles open-source Gloock for titles/headings and Instrument
Sans for paragraphs, navigation, forms and buttons, together with both SIL Open
Font License files. The paired light/dark palettes use cream, terracotta,
burnt-orange and cocoa tones and do not contact a font or style CDN. The top bar
remains mounted while navigating; the current page is retained until the next
page is ready so the header and scrollbar do not flicker between tabs.
