# Acceptance Tests

**Status:** Initial executable-behavior checklist for the MVP. These tests are
technology-independent and should later be automated.

## AT-001 - Local startup

**Given** a valid data directory and no model paths,
**when** the user starts the application,
**then** the server binds to `127.0.0.1`, prints its URL, and allows historical
browsing without requiring a model or GPU; the terminal explains where and how
to add compatible models.

## AT-002 - Historical import is repeatable

**Given** a user-selected schema-compatible CSV has already been imported,
**when** the application starts again with the same file checksum,
**then** it does not duplicate articles or predictions and does not modify the
source file.

## AT-003 - Historical prediction display

**Given** an imported article identifier with predictions from several model
families,
**when** the user opens it,
**then** each model's predicted class and fold are displayed and no original
reference label or score is present.

## AT-004 - Exact prediction reuse

**Given** a stored prediction with the same canonical article URL and selected
model identity,
**when** the user requests that article prediction again,
**then** the application returns the existing result without running inference
and labels the result as reused.

## AT-005 - URL normalization

**Given** a stored canonical article URL and a submitted URL that resolves to it
after redirects, canonical-page lookup, or removal of navigation parameters,
**when** the user requests a prediction,
**then** the application recognizes the existing article and does not create a
duplicate record.

## AT-006 - Different models are not interchangeable

**Given** a BERT prediction exists for an article,
**when** the user requests a RoBERTa prediction,
**then** the BERT result does not satisfy the request and RoBERTa inference runs
if a compatible RoBERTa model is available.

## AT-007 - Missing model

**Given** no compatible model is registered,
**when** the user requests a new prediction,
**then** no result is fabricated and the interface explains which model
requirements are missing, links to the frontend model-setup instructions, and
shows the official OSF model-release URL.

## AT-008 - Invalid custom model

**Given** an unrecognized checkpoint has no explicit supported family or
manifest, has an ambiguous predicted-class mapping, or requires executable
custom code,
**when** the user registers it,
**then** registration fails safely with specific validation errors and no model
code is executed implicitly.

## AT-009 - Successful local inference

**Given** a compatible registered model and a valid article,
**when** the user starts inference,
**then** the UI remains responsive, the completed prediction is stored, and its
canonical URL, model, extraction/tokenizer settings, timing, and origin are
inspectable.

## AT-010 - Failed inference

**Given** inference fails because of insufficient memory or another runtime
error,
**when** the job ends,
**then** the failure and actionable error are recorded, no completed prediction
is created, and the application remains usable.

## AT-011 - Publisher majority vote

**Given** one publisher has ten compatible predictions from the selected model,
six in `Class 4` and four in `Class 3`,
**when** the user creates a publisher evaluation,
**then** the result is `Class 4` and the exact ten predictions are linked to the
stored evaluation.

## AT-012 - No silent model mixing

**Given** a publisher has predictions from two incompatible model artifacts,
**when** the user requests a single-model publisher evaluation,
**then** only predictions matching the selected model are included and excluded
predictions are reported.

## AT-013 - Unresolved aggregation policy

**Given** majority voting results in a tie or the article count is below the
eventual minimum,
**when** no approved policy resolves that condition,
**then** the tool reports the evaluation as unresolved rather than choosing a
class implicitly.

## AT-014 - Persistence

**Given** a new prediction and publisher evaluation have completed,
**when** the application is stopped and restarted,
**then** both results and their complete provenance remain available.

## AT-015 - Local privacy boundary

**Given** the user requests inference for supplied article text,
**when** the model runs,
**then** no article content is transmitted over the network and any network
attempt outside an explicit fetch/download operation is treated as a defect.

## AT-016 - Protected columns are blocked

**Given** an import file contains an original reference label, score, or another
blocked provider field,
**when** the user attempts to import it,
**then** the application removes the blocked columns before any persistence,
reports only the column names, and never logs their values.

## AT-017 - Exports contain model outputs only

**Given** historical and newly computed predictions are available,
**when** the user exports results,
**then** the export contains predicted classes, permitted probabilities,
provenance, and only approved identifiers or metadata; it contains no original
reference label, score, or protected provider field.

## AT-018 - Historical grouping uses URL and domain

**Given** imported prediction records contain canonical `url` and normalized
`domain` values,
**when** the user opens a historical publisher evaluation,
**then** the tool groups article predictions by `domain` and links each record
to its canonical article URL.

## AT-019 - Existing URL is not rechecked for changes

**Given** a canonical article URL already has a stored prediction for the
selected model,
**when** the user requests it again,
**then** the application returns the stored output without refetching the page,
hashing the text, or checking whether the article has changed.

## AT-020 - Duplicate URL import

**Given** two imported rows resolve to the same canonical URL,
**when** their model outputs agree,
**then** they are associated with one article; if outputs for the same model
conflict, the importer reports the conflict instead of choosing silently.

## AT-021 - Startup model discovery

**Given** default model directories and command-line paths contain a mixture of
compatible `.pt` checkpoints, Mistral PEFT directories, invalid artifacts, and
missing paths,
**when** the application starts,
**then** the terminal lists each candidate's status and the frontend model page
shows the same usable-model inventory.

## AT-022 - Several articles from one publisher

**Given** several submitted article URLs resolve to the same normalized domain,
**when** the user confirms the evaluation,
**then** compatible cached predictions are reused, missing predictions are
computed, the selected aggregation is applied, and all results are saved.

## AT-023 - Mixed publishers are rejected

**Given** submitted article URLs resolve to two or more normalized domains,
**when** the user requests one evaluation,
**then** the application shows the conflicting domains, starts no inference
job, and stores no partial publisher evaluation.

## AT-024 - Publisher URL requests an article count

**Given** the user submits one publisher homepage URL,
**when** the input is recognized as a publisher,
**then** the frontend asks for the number of articles, discovers up to that
number from the normalized domain, and shows the actual count before inference.

## AT-025 - Import source and personal results remain separate

**Given** a user-selected CSV has been imported and a new local
evaluation completes,
**when** the application is restarted or upgraded,
**then** the source CSV remains unchanged and the new articles, predictions,
and evaluation remain in the user's personal database.

## AT-026 - Aggregation method is explicit

**Given** more than one aggregation method is offered,
**when** a publisher evaluation is created,
**then** the interface names the exact method and the stored result records its
formula/version; an undefined generic "average" option is never executed.

## AT-027 - Publisher and article histories

**Given** imported and local evaluations exist,
**when** the user opens the Publishers or Articles page,
**then** the frontend lists and filters the combined history, identifies each
record's origin, and links to its detail page.

## AT-028 - Evaluate selected historical articles

**Given** a publisher detail page contains several stored articles,
**when** the user selects a subset, chooses a model and aggregation method, and
starts evaluation,
**then** only that publisher's selected articles are used and the new result is
stored and shown on the publisher page.

## AT-029 - Five-class probability display

**Given** a prediction contains a valid five-class probability vector,
**when** the user opens its article detail,
**then** all five exact values appear as percentages in a table and matching bar
chart alongside the predicted class.

## AT-030 - Missing probabilities

**Given** a historical prediction has only a hard predicted class,
**when** the user opens it,
**then** the frontend shows `Not available`, renders no fabricated probability
chart, and disables mean-probability aggregation for any set containing it.

## AT-031 - Multiple aggregation methods

**Given** a same-publisher article set has all required model outputs,
**when** the user opens aggregation options,
**then** Majority vote and Ordinal class mean are available, Mean class
probabilities is available only with complete vectors, and the selected method
is recorded with the result.

## AT-032 - English software interface

**Given** any supported terminal or browser workflow,
**when** labels, instructions, validation errors, charts, or generated exports
are presented,
**then** all user-visible software text is in English.

## AT-033 - English-only article inference

**Given** a manually submitted article is detected as non-English,
**when** evaluation is requested,
**then** inference does not start and an English validation message explains
that only English articles are supported.

## AT-034 - Non-English publisher candidates

**Given** publisher discovery finds both English and non-English articles,
**when** the requested article set is built,
**then** non-English candidates are excluded and the frontend reports requested,
discovered, excluded, and accepted counts.

## AT-035 - Charts retain exact accessible values

**Given** any probability, distribution, aggregation, or comparison chart,
**when** it is displayed,
**then** the same exact values are available in a table and no information is
communicated by color alone.

## AT-036 - Minimal navigation remains complete

**Given** the user opens the frontend,
**when** navigating Dashboard, Publishers, Articles, Evaluate, and Models,
**then** every required browsing, model-setup, input, evaluation, and result
workflow is reachable without additional top-level navigation items.

## AT-037 - Startup without a dataset

**Given** no CSV path is supplied and no prior personal database exists,
**when** the application starts,
**then** it opens an empty history, does not fail, and explains CSV import in
both the terminal and frontend.

## AT-038 - Dataset size is not part of the schema

**Given** a small sample and a much larger CSV share the supported columns,
**when** either is imported,
**then** both follow the same validation rules, import incrementally, and do not
require the entire file or result set to be loaded into browser memory.

## AT-039 - Tracked sample is safe and structural

**Given** the repository is scanned,
**when** `dataset/sampleDataset.csv` is inspected,
**then** it contains only synthetic article data and permitted model outputs,
contains no protected label, score, or provider metadata, and documents every
supported wide-format prediction field.

## AT-040 - Recognized BERT fold checkpoint

**Given** a trusted `bert_fold_N.pt` produced by the supplied notebook,
**when** it is registered,
**then** the tool reconstructs `bert-base-uncased` with five labels, uses
256-token truncation and fixed padding, loads the tensor-only `state_dict`, and
records `N` as part of model identity.

## AT-041 - Fold choice is user-controlled

**Given** only one otherwise compatible released fold checkpoint is present,
**when** startup model discovery runs,
**then** that fold is registered without requiring fold 1 or all five folds and
is never silently presented as an ensemble.

## AT-042 - Missing base or tokenizer dependency

**Given** a recognized `.pt` or PEFT adapter directory exists but its required
base configuration, base weights, or tokenizer is not cached and cannot be
downloaded,
**when** model validation runs,
**then** registration remains unavailable and the terminal and frontend name
the exact missing dependency and how to provide it.

## AT-043 - Five-class softmax output

**Given** a compatible built-in model produces five logits,
**when** inference succeeds,
**then** the stored predicted class is an integer in `0..4`, exactly five finite
softmax probabilities are stored in index order, and they sum to `1` within the
declared tolerance.

## AT-044 - Article extraction has no cleaning stage

**Given** `newspaper3k` successfully extracts English article text,
**when** a new prediction is run,
**then** `langdetect` returns `en` and the exact extracted text is passed to the
model tokenizer without lowercasing, stemming, lemmatization, or other text
cleaning by the application.

## AT-045 - Released Mistral fold registration

**Given** an extracted released Mistral `fold_N/` directory with its standard
PEFT adapter configuration and weights plus saved tokenizer files,
**when** registration is attempted on compatible hardware,
**then** the tool validates `mistralai/Mistral-Small-24B-Base-2501`, five output
classes, 4-bit NF4 with double quantization and `bfloat16`, LoRA `r=16` and
alpha `32` targeting `q_proj`, `k_proj`, `v_proj`, and `o_proj`, a 1,024-token
limit, dynamic padding to a multiple of 8, and records `N` as the fold.

## AT-046 - Invalid Mistral directory fails closed

**Given** a selected Mistral directory is missing adapter weights or tokenizer
files, declares another base model, or has an incompatible PEFT recipe,
**when** registration is attempted,
**then** the artifact remains unavailable, the exact mismatch is reported, and
the application does not guess, execute remote code, or start loading the 24B
base model.

## AT-047 - Official model download guidance

**Given** the application starts with or without registered models,
**when** terminal status or the Models page is shown,
**then** it exposes the exact URL
`https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74`;
the no-model state also explains how to download, extract when needed, place,
and register a released artifact.

## AT-048 - Mistral hardware preflight

**Given** a valid Mistral fold but no compatible CUDA/quantization runtime or
insufficient available resources,
**when** the user selects it for inference,
**then** preflight stops before model loading, reports the missing requirement
without creating a prediction, and leaves historical browsing usable.

## AT-049 - Repository history contains no protected reference material

**Given** a release archive or Git clone of this repository,
**when** all reachable commits, tags, tracked paths, and retained Git objects
are audited,
**then** no private source CSV, original reference value, protected provider
metadata, training notebook output, or model weight is recoverable; real rows
may appear only in the generated public release and contain exactly its
allowlisted article fields and model outputs.

## AT-050 - Bundled sharded release is complete

**Given** `dataset/predictions/manifest.json` and its listed CSV parts,
**when** release verification runs,
**then** every part matches its declared size and SHA-256, no part exceeds the
configured limit, all headers match the public schema, article identifiers are
contiguous, and the manifest reports 19,476 source rows, 19,429 released rows,
42 duplicated source-URL groups, and 47 skipped later occurrences, with no
protected column in any released part.

## Scientific reference tests still required

The following tests cannot be completed until one released artifact per family
and an approved frozen text fixture are available:

- reference predictions for a fixed article sample from every model family;
- probability tolerance checks for every supported loader;
- fold/checkpoint compatibility checks;
- reproduction of publisher majority-vote results for selected domains;
- resource checks for CPU, CUDA, precision, and adapter configurations.
