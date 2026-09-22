# User Guide

This guide describes the current browser workflow for models, article
predictions, and publisher aggregations.

The predictions and the method behind them come from *From Articles to
Publishers: Aggregating Language Model Predictions for News Source Reliability
Inference* (Bianchi, Pratelli, Pinelli and Petrocchi, IEEE Transactions on
Computational Social Systems, 2026, under review), preprint at
<https://arxiv.org/abs/2609.24219>.

## 1. Understand the workspace overview

Click the status badge in the top bar — **Ready · online**, or **Ready ·
offline** whenever network retrieval is disabled — to open a compact overview
popover with the same counts a dashboard would show:

- **Stored predictions** are immutable article-level outputs. The bundled
  release contains BERT and RoBERTa only, with one predicted label and all five
  class probabilities for every run.
- **Model identities** includes historical identities from imported data and
  local runnable artifacts. A historical identity is useful for provenance but
  is not itself an installed checkpoint.

The bundled release produces 17,269 normalized articles, 34,564 prediction
runs, and 10 historical BERT/RoBERTa family/fold identities, spread over 372
publishers. It carries only outlets with at least 20 classified articles, so
every publisher in it has enough material to aggregate.

## 2. Make models available

Install the locked inference dependencies before starting the application:

```bash
uv sync --frozen --extra models
```

There are two supported model paths: core BERT/RoBERTa checkpoints and custom
five-class Transformers.

### Core BERT or RoBERTa checkpoint

1. Copy `bert_fold_N.pt` or `roberta_fold_N.pt` below a configured models
   directory, normally `./models`.
2. Restart the application or open **Models** and select **Scan configured
   directories**.
3. Confirm that the local identity is `compatible` and runnable.

Startup scans configured roots automatically. The Models page also performs one
session scan when it finds no local identities; the explicit scan button is
available after files are added, removed, or replaced.

The first scan of a checkpoint is slow, because the file is read once for its
SHA-256 and once more to verify its structure. A checkpoint that has not changed
since the previous scan reuses that recorded result, so later starts are quick;
a new, moved, replaced or modified file is verified again in full. To re-read
every byte on demand, for example when a disk may be failing, run:

```bash
publisher-reliability models scan --full
```

Core checkpoints contain model weights but not the official tokenizer files.
On first online inference the application may cache only the small tokenizer
and configuration resources from the pinned immutable Hugging Face revision.
It never downloads base-model weights.

### Only five-class encoder models are supported

This tool runs one model shape: a five-class encoder classifier built to the same
recipe as BERT and RoBERTa. It is meant to work on an ordinary laptop, so the
study's Llama 3 8B and Mistral 24B are left out: each fold needs a CUDA GPU and
tens of gigabytes of weights.

You lose very little by that. In the study RoBERTa is the most accurate
publisher-level model of all four, the 24B decoder gained nothing from a context
window four times longer, and every family made the same kinds of error. The
larger models did not win, so the tool runs the ones that did, on hardware you
already have. A bundle of any other shape is refused at import as invalid.

### Custom Transformers model

A custom model uses one self-contained ZIP. A full encoder bundle contains:

```text
prt-model.json
config.json
model.safetensors
tokenizer_config.json
tokenizer resources
```

Open **Models → Import a custom five-class Transformer**, review the example shown
above the upload control, select the ZIP, and wait for the validation job. A
valid bundle is installed under the managed data directory and marked
**User custom**.

The application rejects executable code, pickle/PyTorch
weights, unsafe ZIP paths, remote tokenizer dependencies, non-finite tensors,
and state-dictionary key/shape mismatches. See
[Custom Transformers bundle](custom-model-bundle.md) for the complete manifest
and export contract.

## 3. Evaluate one article

1. Open **Evaluate**. One article is the only thing the page classifies.
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
the backend rejects direct attempts with `TRAINING_DATA_LEAKAGE`. This applies
to every family, because all families in the study share the same
publisher-disjoint folds: an article's held-out fold identifies the training set
of every one of them. For an
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
prediction-run ID, and a link to the complete article history. The card belongs
to the evaluation you just ran; earlier local predictions are listed under
**Articles & predictions → User-evaluated articles**, which survives a refresh.

Every completed new inference is stored in two coordinated places:

- `data/state/prediction_runs.csv` is the authoritative application ledger;
- `dataset/predictions/user-predictions.csv` contains an inspectable mirror row
  with `prediction_origin=user_evaluation`. This file is private: it is listed
  in `.gitignore` and never becomes part of the tracked repository, because a
  user's own reading and evaluation history must never be committed alongside
  the shared research dataset.

The mirrored row includes the run ID, URL, exact model ID/family/fold, predicted
label, all five probabilities, action, timestamps, duration, device and
software versions. The tracked `dataset/predictions/predictions.csv` holds only
`prediction_origin=dataset_original` rows and is never modified by the running
application. A repeated start or synchronization does not duplicate a
prediction because the run ID is unique.

Common availability messages have distinct meanings:

- **No validated local checkpoint**: add/scan a supported artifact or import a
  custom ZIP.
- **New article requires inference, but no runnable local model is available**:
  a model identity may exist, but no installed artifact passed runnable
  validation.
- **Training-data leakage**: the local fold was trained on that known dataset
  article. The checkpoints withheld for this reason are named beneath the
  selector, so a hidden option is never unexplained.

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

**Export predictions CSV** downloads `article-predictions.csv`: one row per
stored prediction, so each model that evaluated an article appears separately
with its own predicted label, all five class probabilities, family, fold,
readable model name, provenance, run ID, model ID, and the job ID of the
evaluation that produced it. Rows of the same article stay adjacent, and the
active source filter applies to the download. It never includes saved body
text, authors, raw HTML, or a checkpoint path.

Run origin in the application ledger (`local_inference`) and row origin in the
combined prediction dataset (`user_evaluation`) describe the same user-created
inference at two storage boundaries.

Nothing in the tool deletes anything. There is no button, and no API route, that
removes a prediction, saved content or a job record — not on the hosted site and
not on your own machine. The capability was taken out of the code rather than
hidden behind a setting, so that reaching past the interface finds nothing that
destroys stored work. To discard what the tool holds, remove its data directory
(`./data` by default) and, if you want the local evaluations gone too, the
private mirror at `dataset/predictions/user-predictions.csv`. That is an act of
administration on the host, not a feature of the application.

## 5. Read a publisher's class

A publisher class is not something you create. It is a reading of the articles
already classified, so it is computed when you ask for it and never stored.

Open **Publishers**, or click a publisher name anywhere an article is listed.
The page shows one class per model, each counted only over that model's
leakage-safe articles. Two models may disagree, and that disagreement is shown
rather than averaged away: mixing predictions from different checkpoints would
report a number no model produced. Folds of one family are not pooled either.
The corpus was split so that a publisher's articles belong to a single fold, so
a publisher appearing under two folds of the same family is an anomaly you
should be able to see rather than one the page quietly smooths over.

Two controls change the reading:

- **How article verdicts are counted** selects the aggregation method. Each one
  answers a slightly different question — majority vote takes the most common
  class, the ordinal mean and the median use the fact that the classes are
  ordered, mean probabilities and expected class work from the full probability
  vectors, and confidence-weighted vote lets a hesitant article count for less.
  A description of the current choice is shown beneath it.
- **Articles counted** lists every article of that publisher with a
  leakage-safe prediction. Clear a checkbox to leave it out; each model is
  recounted over what remains.

Each verdict carries the spread of the articles behind it: how many of them
match the class exactly, how many are within one class of it, the variance of
the classes, and a band — **stable**, **elevated** or **high** — from error
rates measured on the study corpus. A high band means the model has no stable
opinion about this publisher, and the verdict should be read as indicative only.

Note what these numbers do and do not say. They measure how far the articles sit
from each other and from the verdict they produced. They are not accuracy: this
tool ships no reference labels, so nothing here can tell you whether a class is
*right*. That is also why there is no option to count adjacent classes as near
misses when voting — an allowance for near misses needs a true label to be near
to. The allowance appears only in the dispersion figures, where "within one
class" and "variance allowing adjacent" describe agreement, not correctness.

**Charts** plots the same counted articles. Pick between the class
distribution, one dot per article against how sure the model was, the variance
against the risk bands, the averaged probability profile, and a side-by-side
comparison of the models.

All of this acts on the display only. Nothing is written, so a different reading
is always one click away, and the stored predictions never change. A reading
needs at least two counted articles to report a class; below that it reports
none rather than presenting a single article as an aggregate.

## 6. Appearance and navigation

The interface uses one light palette, defined as CSS custom properties at the
top of `styles.css`; there is no
dark mode or theme control. Titles, paragraphs, navigation, forms and buttons
all use the system Times New Roman serif font, so nothing is fetched from a
font or style CDN. The top bar remains mounted while navigating; the current
page is retained until the next page is ready so the header and scrollbar do
not flicker between tabs.

## 7. About

**About** is a fixed page: what the tool does, the study it implements and where
to find its preprint, what is in the bundled release, and what a predicted class
is not. It makes no request and shows no stored data, so it reads the same on a
published instance as it does on your own machine.

## 8. Jobs

**Jobs** lists every model scan, dataset import and evaluation the worker has
run, newest first. The list only grows: as with everything else the tool stores,
there is no operation that clears it.
