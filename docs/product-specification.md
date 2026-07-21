# Product Specification

**Status:** Initial draft
**Target:** Documentation baseline for the MVP

## 1. Objective

The tool makes the paper's experimental outputs inspectable and its trained
models usable without writing Python code. It supports two related activities:

1. inspecting predictions already produced during the experiments;
2. producing local predictions for articles not already evaluated by a
   compatible model, then aggregating them at publisher level.

The complete software interface, including terminal output, frontend labels,
validation messages, setup guidance, and generated exports, is in English. The
MVP accepts and evaluates English-language articles only.

The tool must never imply that an article prediction is an independent fact
check. Original labels, scores, and metadata supplied by the reference rating
provider are outside the distributable product and must never be imported,
stored, displayed, logged, or exported.

## 2. Intended users

### Primary user

A researcher or technically competent reader of the paper using Linux and able
to download model artifacts.

### Secondary user

A non-programmer who can start the application with a documented terminal
command and use the browser interface.

## 3. MVP scope

### Included

- Start a local web server from the terminal.
- Accept a model directory, multiple model paths, or a parent directory that
  contains models.
- Validate and register compatible local models.
- Show the official OSF model-release link and manual setup instructions in the
  terminal and Models page.
- Import a user-supplied schema-compatible CSV selected at startup or through
  the frontend; use `dataset/sampleDataset.csv` as the tracked structural
  example.
- Start in history-only mode when no compatible model is available and explain
  model installation in both the terminal and browser.
- Search and filter historical model outputs using only approved,
  redistributable identifiers and metadata.
- Browse dedicated histories of evaluated publishers and articles.
- Display all available model-specific predictions for an identified article.
- Display each available five-class probability vector in a table and compact
  chart.
- Display publisher-level charts for class distribution, aggregation, and
  model comparison where the required data exist.
- Select previously stored articles from a publisher page and request a new
  evaluation for that subset.
- Request predictions by supplying one article URL, several article URLs from
  the same publisher, or one publisher homepage URL.
- Discover a user-selected number of articles from a submitted publisher URL.
- Reject a multi-article request containing more than one publisher.
- Reuse an existing prediction only when its article and model identities are
  compatible with the request.
- Store new predictions locally.
- Aggregate article predictions for one publisher using a selected model.
- Choose among explicitly defined aggregation methods, subject to data
  availability.
- Display complete provenance for every prediction and aggregate evaluation.
- Register a trusted custom model from a local path or local file selection.

### Excluded from the first version

- Training or fine-tuning models.
- A hosted inference service.
- Multi-user accounts and remote collaboration.
- Automatic publication of results.
- Treating the CSV itself as a writable database.
- Bundling or redistributing the original experimental CSV; a private local
  copy may be selected and projected through the allowlist.
- Displaying original provider labels, scores, or provider-supplied metadata.
- Automatically executing arbitrary code shipped with an untrusted model.

### Desired after the MVP

- Automatic or assisted model download from the release repository.
- Export of selected results.
- Optional remote access with authentication.

## 4. Core workflows

### WF-001 - Start the application

1. The application locates the user's personal application database and any
   CSV path supplied at startup.
2. If a CSV is supplied, it validates its schema and imports its permitted
   prediction and article fields.
3. It recursively discovers models from default locations and any files or
   directories supplied by the user, ignoring hidden directories such as
   `.ipynb_checkpoints`.
4. It validates every discovered model and prints a model-status summary.
5. The server binds to `127.0.0.1` by default.
6. The command prints the local browser URL and startup diagnostics.
7. If no compatible model is available, the server still starts and the
   terminal prints actionable instructions for adding one.
8. If no CSV is supplied, the server starts with the existing personal database
   or an empty history and explains how to import a dataset.

Illustrative command only; the final command name and flags are **OPEN**:

```bash
publisher-reliability serve \
  --dataset /path/to/predictions.csv \
  --models-dir /path/to/models
```

### WF-002 - Inspect a historical prediction

1. The user searches by approved article or publisher identifiers and, only
   where redistribution is permitted, by URL, title, or domain.
2. The application shows only approved redistributable article identifiers and
   metadata.
3. It lists predicted classes separately for BERT, RoBERTa, Llama, and Mistral,
   including fold/checkpoint information where available.
4. It does not expose, infer, or reconstruct original reference labels or
   scores.

### WF-003 - Evaluate one article URL

1. The user enters one article URL and selects a registered model.
2. The application resolves the article's canonical URL and the publisher's
   normalized domain.
3. It checks for an exactly compatible stored prediction.
4. If found, it returns that prediction and marks it as reused.
5. Otherwise, it validates model availability and hardware requirements.
6. It runs inference locally and stores the result with provenance.
7. If no compatible model is available, it explains how to register one and
   does not create an incomplete result.
8. A newly computed article and prediction are saved in the user's personal
   local database.

### WF-004 - Evaluate several article URLs

1. The user enters two or more article URLs and selects a registered model.
2. The application resolves every canonical URL and normalized domain.
3. If the articles belong to more than one domain, the request is rejected
   before inference and the conflicting domains are shown.
4. Existing compatible predictions are reused and missing ones are computed.
5. The application applies the selected aggregation rule to the article
   predictions.
6. The articles, new predictions, and aggregate publisher evaluation are saved
   in the user's personal local database.

### WF-005 - Evaluate a publisher URL

1. The user enters one publisher homepage URL and selects a registered model.
2. The application resolves the normalized publisher domain.
3. The interface asks how many articles should be discovered and evaluated.
4. The application discovers that number of valid article URLs from the
   publisher, or reports how many were actually available.
5. It reuses stored model outputs and computes only missing predictions.
6. It applies the selected aggregation rule and saves the complete evaluation
   in the user's personal local database.

### WF-006 - Register a released or custom model

1. The user downloads one or more released models from the official OSF page,
   extracts directory-based artifacts when necessary, and selects trusted local
   checkpoint files or directories.
2. A released filename such as `bert_fold_1.pt` selects the corresponding
   built-in `state_dict` recipe. A Mistral fold directory is recognized from
   `adapter_config.json`, `adapter_model.safetensors`,
   `tokenizer_config.json`, `tokenizer.json`, and the approved base-model
   identity; its `README.md` is optional and never executed.
3. The application records the fold as part of model identity and reconstructs
   the documented architecture, tokenizer, output head, quantization/adapter
   configuration, and input settings without executing model-supplied code.
4. If required base-model or tokenizer resources are neither cached locally nor
   downloadable, registration stops with exact setup instructions in both the
   terminal and frontend.
5. An unrecognized custom checkpoint requires an explicit supported family or
   a separate manifest; the application does not guess its architecture.
6. Registration does not copy a large model unless the user explicitly chooses
   managed storage.

### WF-007 - Start without models

1. Model discovery finds no compatible model.
2. The terminal clearly states that historical results remain available but
   new predictions cannot be computed.
3. The terminal shows the official OSF download URL, accepted artifact layouts,
   model locations, and an example startup command.
4. The browser displays the same status, a clickable OSF link, and a model-setup
   page.
5. Attempts to start a new evaluation link to those instructions rather than
   creating a failed inference job.

Official release URL:

<https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

### WF-008 - Browse history and reevaluate selected articles

1. The user opens the publisher history and searches or filters by domain,
   model availability, origin, or evaluation status.
2. The user opens one publisher and sees its stored articles and previous
   aggregate evaluations.
3. The user selects one or more stored articles and may add further article
   URLs from the same publisher.
4. The application rejects any added URL that resolves to another publisher.
5. The user selects a model and aggregation method, then starts the evaluation.
6. The resulting predictions, probabilities when available, charts, and stored
   publisher evaluation are shown on the same publisher page.

### WF-009 - Import a dataset

1. The user supplies a local CSV path at startup or selects a CSV from the
   frontend import page.
2. The application validates required columns against the same rules exercised
   by `dataset/sampleDataset.csv`.
3. It projects only allowed fields; blocked reference-provider columns are
   ignored with a value-free warning and are never persisted.
4. It imports the file in chunks without assuming the row count or file size.
5. The imported history becomes searchable together with previously saved
   personal results.

## 5. Minimal frontend

The interface should remain visually minimal while exposing every required
function. The primary navigation contains only:

- **Dashboard**: application/model status, recent evaluations, and short
  history summary;
- **Publishers**: searchable and filterable publisher history;
- **Articles**: searchable and filterable article history;
- **Evaluate**: the three supported URL-input modes;
- **Models**: discovered models, compatibility status, and setup guidance.

The Models page always includes a clearly labeled **Download official models**
link to the OSF release, even when compatible models are already installed.

### Publisher detail

The publisher page shows:

- normalized domain and homepage link;
- previous publisher evaluations and their aggregation methods;
- stored articles with selection checkboxes, canonical URLs, models already
  applied, predicted classes, and origin;
- controls to evaluate selected articles or add same-publisher URLs;
- a bar chart of article counts by predicted class;
- aggregation results and, when available, aggregate class probabilities;
- a comparison of model results when more than one model evaluated the same
  article set.

### Article detail

The article page shows:

- canonical URL, publisher, available metadata, and evaluation origin;
- one result panel per model;
- predicted class, fold/checkpoint, and inference provenance;
- probability for each of the five output classes as both percentages and a
  horizontal bar chart;
- `Not available` rather than estimated values when historical probabilities
  were not released.

### Visualization rules

- Prefer compact bar charts over decorative visualizations.
- Always provide the exact numeric values in a table adjacent to or accessible
  from the chart.
- Use a consistent class-color mapping throughout the application.
- Do not rely on color alone to communicate a class or status.
- Avoid animations and non-essential dashboard elements.

## 6. Functional requirements

| ID | Status | Requirement |
| --- | --- | --- |
| FR-001 | DECIDED | A terminal command shall start and stop the local server cleanly. |
| FR-002 | DECIDED | The server shall bind to localhost unless the user explicitly changes the network configuration. |
| FR-003 | DECIDED | At startup the application shall discover, validate, and report zero, one, or multiple local models. |
| FR-004 | DECIDED | The application shall import a user-supplied schema-compatible CSV; `dataset/sampleDataset.csv` shall be the tracked example and `dataset/fullDataset.csv` shall remain ignored. |
| FR-005 | DECIDED | Historical predictions shall be searchable through allowlisted identifiers and metadata; protected reference-provider fields shall never become searchable. |
| FR-006 | DECIDED | The canonical article URL shall be the unique article identifier; the normalized publisher domain shall be the unique publisher identifier. |
| FR-007 | DECIDED | If a prediction already exists for the same canonical URL and selected model, it shall be reused without refetching or comparing the article text. |
| FR-008 | DECIDED | Inference shall run locally and record success, failure, duration, parameters, and environment metadata. |
| FR-009 | DECIDED | Publisher aggregation shall operate only on predictions compatible with the selected model configuration. |
| FR-010 | DECIDED | Every displayed result shall identify whether it was imported, reused, or newly computed. |
| FR-011 | PROPOSED | Long inference operations shall execute as background jobs so the web interface remains responsive. |
| FR-012 | PROPOSED | Interrupted or failed jobs shall remain inspectable and retryable without being presented as completed results. |
| FR-013 | DECIDED | Released fold files and directories with recognized layouts shall use built-in loader recipes; an unrecognized custom model shall require an explicit type selection or manifest. |
| FR-014 | DECIDED | The browser shall accept exactly three evaluation inputs: one article URL, multiple article URLs, or one publisher homepage URL. |
| FR-015 | DECIDED | The MVP shall guide the user to download models manually from `https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74` and register the downloaded file or extracted directory; automatic download is not required. |
| FR-016 | DECIDED | The importer shall persist only fields on an explicit allowlist. Original labels, scores, and all other reference-provider fields in a private local CSV shall be ignored before persistence with a warning that names columns but never values. |
| FR-017 | DECIDED | Protected fields shall never be persisted, displayed, logged, cached, or included in exports. |
| FR-018 | DECIDED | A submitted URL shall be resolved online to the page's canonical URL when possible; redirects, fragments, and non-identifying navigation or tracking parameters shall not create a second article. |
| FR-019 | DECIDED | Predictions remain model-specific: an existing prediction from one model shall not satisfy a request for another model. |
| FR-020 | DECIDED | A multi-article evaluation shall contain articles from exactly one normalized publisher domain; mixed-domain input shall be rejected before inference. |
| FR-021 | DECIDED | A publisher-URL evaluation shall ask the user how many articles to discover and evaluate. |
| FR-022 | DECIDED | With no compatible model, the application shall still start in history-only mode and provide model-setup instructions in the terminal and frontend. |
| FR-023 | DECIDED | Every newly discovered article, model prediction, and publisher evaluation shall be added to the user's personal local database. |
| FR-024 | DECIDED | Imported CSV files shall remain unchanged; personal results shall be persisted in the application database. |
| FR-025 | PROPOSED | The MVP shall offer paper-compatible majority voting, ordinal class mean, and mean class probabilities when their required inputs are available. |
| FR-026 | DECIDED | The frontend shall provide searchable histories for evaluated publishers and articles. |
| FR-027 | DECIDED | From a publisher page, the user shall be able to select stored articles and request a new evaluation for that single publisher. |
| FR-028 | DECIDED | Every new inference from a fully compatible model shall store and display the predicted class and all five class probabilities; historical results shall display them when released. |
| FR-029 | DECIDED | Missing historical probability vectors shall be displayed as `Not available` and shall never be reconstructed from a hard predicted class. |
| FR-030 | DECIDED | Article and publisher detail pages shall provide compact charts for probabilities, article-class distribution, aggregation results, and applicable model comparisons. |
| FR-031 | DECIDED | All terminal output, frontend text, validation messages, setup guidance, and software-generated exports shall be in English. |
| FR-032 | DECIDED | The MVP shall evaluate English-language articles only. |
| FR-033 | DECIDED | A manually supplied non-English article shall be rejected before inference; non-English candidates discovered from a publisher shall be excluded and reported. |
| FR-034 | DECIDED | The application shall start with an empty or existing personal history when no dataset is supplied and shall explain dataset import in the terminal and frontend. |
| FR-035 | DECIDED | Import shall not impose a fixed dataset size or row count and shall process large CSV files incrementally. |
| FR-036 | DECIDED | Released checkpoints shall be recognized from a validated family-and-fold filename or standard artifact directory; the selected fold shall be used independently without requiring all folds. |
| FR-037 | DECIDED | Every built-in reliability classifier shall expose exactly five ordered public output indices, `0` through `4`, without embedding protected reference labels, score ranges, or provider metadata. |
| FR-038 | DECIDED | The first loader registry shall implement the notebook-derived BERT, RoBERTa, Llama, and Mistral recipes. |
| FR-039 | DECIDED | Model validation shall check checkpoint shape plus required base-model, tokenizer, runtime, and device dependencies before inference and provide actionable English setup guidance for anything missing. |
| FR-040 | DECIDED | New article content shall be extracted with `newspaper3k`, checked as English with `langdetect`, and passed to the selected model tokenizer without additional text cleaning or linguistic preprocessing. |
| FR-041 | DECIDED | A released Mistral fold shall be accepted as an extracted PEFT directory containing a valid adapter configuration and weights plus saved tokenizer files; it is not expected to be a single `.pt` file. |
| FR-042 | DECIDED | Terminal startup output and the frontend Models page shall always expose the exact official OSF release link; the no-model state shall additionally show copyable placement and startup instructions. |
| FR-043 | DECIDED | The built-in Mistral adapter shall enforce the documented 24B base-model identity, five outputs, 1,024-token input limit, dynamic padding, 4-bit NF4 configuration, and LoRA recipe before registration succeeds. |
| FR-044 | DECIDED | Model discovery shall scan supplied directories recursively, ignore hidden directories including `.ipynb_checkpoints`, and accept direct file or fold-directory paths. |
| FR-045 | DECIDED | BERT, RoBERTa, and Llama family/fold identity shall come from each `.pt` filename rather than its parent directory; Mistral identity shall come from validated PEFT contents plus a fold parsed from a case-insensitive `fold`, `fold_`, `fold-`, or `fold ` directory name. |
| FR-046 | DECIDED | A Mistral release directory shall require `adapter_config.json`, `adapter_model.safetensors`, `tokenizer_config.json`, and `tokenizer.json`; `README.md` shall be optional data and shall never influence loading. |

## 7. URL identity and cache policy

The MVP deliberately uses a simple identity rule:

```text
article identity   = canonical article URL
publisher identity = normalized domain
stored prediction  = canonical article URL + model identity
```

When the user supplies an article URL, the application first normalizes it
locally by removing the fragment and known non-identifying tracking or
navigation parameters, then checks the database. Only if no match is found does
it access the page, follow redirects, and read its declared canonical URL. The
resulting canonical URL is checked again and stored in the same `url` field used
by the historical file.

If that canonical URL is already present, the application treats it as the same
article and does not compare or hash the text. If the requested model already
has a stored prediction, that prediction is returned. If the URL exists but the
selected model has no prediction, the selected model may still be run.

This rule intentionally accepts that a publisher may modify the page while
retaining the same URL. Detecting article revisions is outside the MVP.

## 8. Non-functional requirements

| ID | Status | Requirement |
| --- | --- | --- |
| NFR-001 | DECIDED | Article text and inference inputs shall remain on the local machine, except when the user explicitly requests URL retrieval. |
| NFR-002 | DECIDED | Results shall persist across normal application restarts. |
| NFR-003 | DECIDED | The same model artifact, extracted text, tokenizer settings, and inference parameters shall produce a traceable, reproducible run subject to documented hardware limitations. |
| NFR-004 | DECIDED | The application shall not require a GPU merely to browse historical results. |
| NFR-005 | PROPOSED | The application shall detect insufficient RAM, VRAM, disk space, or missing runtime support before inference whenever feasible. |
| NFR-006 | DECIDED | Importing a user-supplied CSV shall be chunked and shall not require loading all records into browser memory. |
| NFR-007 | PROPOSED | The UI shall remain usable while an inference job is running. |
| NFR-008 | OPEN | Supported Linux distributions, Python versions, GPU backends, and minimum hardware must be defined after inspecting the released models. |
| NFR-009 | DECIDED | Every chart shall have an exact tabular representation and shall not rely on color alone. |
| NFR-010 | PROPOSED | The minimal frontend shall use a small, consistent navigation structure and avoid non-functional decorative components. |
| NFR-011 | DECIDED | Browsing imported history shall work offline; new inference shall work offline once every required base model, tokenizer, and runtime dependency is cached locally. |

## 9. Required result provenance

Every article prediction must retain:

- canonical article URL;
- model name, architecture, version, artifact checksum, and fold/checkpoint;
- extraction library/version and tokenizer input settings;
- class probabilities when the model provides them;
- detected article language and language-validation result;
- predicted class;
- start time, completion time, duration, and execution status;
- software version and relevant runtime/hardware information;
- origin: identified CSV import, cache reuse, or new local inference.

Every publisher evaluation must additionally retain:

- normalized publisher domain and homepage URL;
- exact canonical article URLs included;
- aggregation method and version;
- tie-breaking and minimum-article policies;
- final predicted class and any uncertainty/warning information;
- input mode: publisher URL or explicit article list;
- requested and successfully evaluated article counts.

## 10. Open decisions before implementation

1. Finalize the URL-normalization fallback used when a page is unreachable or
   does not declare a canonical URL.
2. Run a tensor-level reference prediction with one downloaded artifact from
   each family; the observed OSF Mistral directory layout is now documented.
3. Define the fallback manifest contract for unrecognized custom checkpoints.
4. Define minimum, maximum, default, and selectable article counts for a
   publisher-URL evaluation.
5. Define article discovery and ordering: homepage, RSS, sitemap, recency, and
   fallback behavior when fewer articles are available.
6. Define deterministic behavior when majority voting produces a tie.
7. Confirm the rounding/display rule for ordinal class mean and the
    availability rule for mean-probability aggregation.
8. Decide whether a browser "upload" copies models or merely registers paths.
9. Decide the supported CPU, CUDA, and quantized-model configurations and
   document the practical Mistral hardware minimum.
10. Define how `langdetect` failures and very short or ambiguous extracted
    texts are reported; ordinary acceptance is `detect(text) == "en"`.
11. Record licenses and redistribution conditions for every public model-output
    and article-metadata field.
