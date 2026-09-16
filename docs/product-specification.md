# Product Specification

**Status:** Normative research-demo MVP contract

## 1. Purpose and audience

Publisher Reliability Tool is a single-user local reference implementation for
the paper's article classification and publisher aggregation workflow. Its
audience is a researcher running the demo on one workstation, inspecting its
provenance, or extending its code.

It is not a SaaS product, public server, multi-user system, high-availability
service, or long-lived organizational database. Simplicity and scientific
transparency take precedence over production-scale throughput and exhaustive
fault tolerance.

## 2. Supported environment

- Native reference: Ubuntu 24.04 LTS, x86-64, Python 3.12.
- Container reference: one Docker Compose service on x86-64 Linux.
- Browser: current or previous Firefox/Chromium release.
- Address: `http://127.0.0.1:8000`; non-loopback binding is unsupported.
- One process, one worker thread for long jobs, one data-directory writer, and
  one local user.
- Demonstrated scale: the bundled dataset and compatible user imports up to
  300,000 source rows and 512 MiB compressed/upload bytes. Larger inputs are
  unsupported rather than promised to stream at arbitrary scale.

## 3. Included scope

The MVP shall:

- start through one native command or a simple Compose service;
- serve a local bundled browser UI, REST API, OpenAPI document, and health
  endpoints;
- verify/import the bundled public prediction manifest on first startup;
- import user CSV or CSV.GZ files after safe projection and validation;
- persist essential models, runs, imports, jobs, and explicitly saved local
  content in six inspectable CSV ledgers;
- mirror every locally inferred article run into a private, git-ignored
  `dataset/predictions/user-predictions.csv` with explicit origin, exact label,
  probabilities and provenance, entirely separate from the tracked
  `predictions.csv` release, which the application never modifies;
- derive article and publisher views from persisted prediction runs;
- scan configured model roots for supported checkpoints;
- provide BERT and RoBERTa as the core CPU demo;
- refuse, with an explicit `FEATURE_UNAVAILABLE` explanation, any attempt to
  import the study's larger decoder checkpoints (Llama 3 8B, Mistral 24B),
  whose support is still under development;
- import constrained five-class custom encoder classifiers using local
  declarative metadata, tokenizer and `safetensors`;
- evaluate one article, 2–50 explicit same-publisher articles, or one publisher
  with a requested count of 2–50;
- reuse exact stored runs or explicitly create a new immutable run;
- aggregate exact compatible runs with the three scientific methods;
- derive Evaluate choices from locally present models: safe matching stored
  family/fold coverage or runnable local IDs for new single-article inference;
- prevent a checkpoint from evaluating known imported articles outside its
  held-out test fold;
- display exact model/fold/run/article provenance and scientific warnings;
- work offline for browsing, reuse, and deriving a publisher class from stored runs;
- optionally retain extracted title/body with explicit per-request consent.

## 4. Explicitly excluded or deferred

- public/private-network hosting, authentication, users, configurable CORS,
  reverse proxies, TLS, or remote administration;
- general `Idempotency-Key` support, persistent event streams, job retry,
  cancellation, queue priorities, or parallel candidates within one job;
- storage compaction, record versioning, commit watermarks, transactional CSV
  database semantics, automatic backup retention, or online maintenance;
- dataset ZIP import, generic dataset archive manifests, API dataset import
  from a server path, or arbitrary import roots;
- generic custom-model manifests outside the documented PRT bundle, plugins,
  runtime code loading, arbitrary base models, credential management,
  or general-purpose cache management;
- model training, tuning, calibration, automatic ensembling, hosted inference,
  telemetry, analytics, or production metrics;
- automatic deletion from user backups or external copies;
- a hard latency SLA or mandatory GPU release gate.

## 5. CLI

The stable MVP surface is:

```text
publisher-reliability serve [OPTIONS]
publisher-reliability dataset verify PATH
publisher-reliability dataset import PATH
publisher-reliability models scan
publisher-reliability storage verify
```

`serve` options:

| Option | Default | Meaning |
| --- | --- | --- |
| `--port` | `8000` | Loopback port `1..65535` |
| `--data-dir` | `./data` | CSV state, lock, temporary uploads, logs |
| `--models-dir` | `./models` | Repeatable configured model root |
| `--seed-dataset` | `./dataset/predictions` | Bundled manifest and a writable, git-ignored local-prediction mirror file; missing is allowed |
| `--offline` | false | Deny all application HTTP retrieval |
| `--device` | `auto` | `auto`, `cpu`, or `cuda` |
| `--log-level` | `info` | `debug`, `info`, `warning`, `error` |

The host is fixed to `127.0.0.1`. `dataset verify` accepts CSV, CSV.GZ, or the
official manifest directory and changes no state. `dataset import` accepts CSV
or CSV.GZ and uses the same importer as the UI. `models scan` scans configured
roots plus the internal managed-upload root. `storage verify` checks headers,
row types, identifiers, references,
and malformed final rows. There is no compaction or migration command in schema
version 1.

The non-server commands perform their work synchronously and print macro
progress. They call the same verification/import/model-scan service functions
as the server, but do not create a persisted job that would require a running
worker.

Exit codes are `0` success, `2` invalid configuration/input, `3` invalid
dataset/storage, and `1` unexpected runtime failure.

## 6. Startup and shutdown

Startup order is:

1. parse configuration;
2. bind and retain the loopback socket without accepting requests, proving the
   port is available before data-directory mutation;
3. create the data directory and operational subdirectories if absent, then
   acquire its exclusive lock; creation occurs only after port reservation;
4. create all six ledgers only when `state/` is absent; an existing partial
   state directory is `STORAGE_ERROR`, not a fresh store;
5. load and structurally verify the complete store, marking previously running
   jobs `PROCESS_INTERRUPTED`; malformed records fail closed and are not
   repaired automatically;
6. verify/import the optional bundled release by content digest;
7. scan configured core model roots and refresh managed-bundle integrity;
8. restore any run present in the private, git-ignored user-prediction mirror
   but absent from the authoritative state ledger, then idempotently
   synchronize all local inference runs back to that same mirror file; the
   released `predictions.csv` and its manifest are never written by the
   running application;
9. start the FIFO worker, requeue persisted queued jobs, and fail an
    upload-backed job when its acquired source is missing;
10. accept HTTP requests; readiness is then `ready`.

Missing seed/models are valid empty/history-only modes. An occupied port causes
no data mutation. Corrupt storage closes the reserved socket and starts no HTTP
server.

On `SIGINT`/`SIGTERM`, new jobs stop being accepted and the worker receives a
stop request. The process waits at most five seconds, then exits even if a
non-cancellable retrieval, model call, or filesystem call remains. On next
startup the job is failed as interrupted; already committed rows remain valid.
No inference/upload is resumed.

## 7. Main research workflow

### 7.1 Bundled history

On first startup the official manifest and part checksums are verified. Its
normalized runs are imported once by `(content_sha256, schema_version)`.
Articles and publishers are views derived from those runs.

### 7.2 Models

The researcher manually downloads official artifacts and copies them below a
configured model root. Startup scans those roots; an explicit
`model_validation` job is also available after files change while the service
is running. A checkpoint is fully verified — hashed and structurally validated —
the first time it is seen and whenever its file changes; a checkpoint left
untouched since the previous scan reuses that recorded result, so restarting does
not re-read gigabytes for nothing. `publisher-reliability models scan --full`
re-reads every byte on demand. The Models page reports compatible, validated-not-runnable,
dependency-missing, resource-unavailable, artifact-missing, paper-official, custom and
historical-only identities. On first online inference for a compatible core
checkpoint, the application caches only its tokenizer/configuration resources
from a pinned immutable official revision.

BERT/RoBERTa CPU behavior is part of the core gate. The study's larger decoder
checkpoints are not importable in this release: each fold needs a CUDA GPU and
several gigabytes of weights, so the demo ships the two encoder families, whose
reported accuracy is comparable, and keeps the identity and loader contracts
open for a later decoder family. A custom upload is one self-contained `.zip`
using the exact encoder format in `custom-model-bundle.md`. Validation runs as a `model_validation` job, installs
a successful bundle under `managed-models`, preserves official-versus-custom
provenance, and never imports executable artifact code.

Evaluate never presents all historical identities as if they were installed
checkpoints. For stored results it intersects prediction identities with local
artifacts by family/fold while retaining separate scientific IDs. For a single
new URL it offers runnable local model IDs directly and creates a new run.

### 7.3 Evaluation controls

Every evaluation has:

- `prediction_action`: `reuse` (default) or `recompute`;
- `content_retention`: `discard` (default) or `save_local`.

`reuse` selects the latest exact-model run by effective completion time
descending then run ID ascending. If absent, a runnable model retrieves the page
and creates a new run. `recompute` always retrieves and creates a new run.
`save_local` stores only validated title/body and never changes which run is
selected. With an existing run but no saved content, `reuse + save_local`
retrieves/validates content without inference; the resolved canonical article
must still equal the run's article or nothing is saved. `discard` never deletes
content saved by an earlier request.
Content is committed only after an exact run has been selected or created, so
`local_content.csv` cannot introduce an article absent from run history.

One article is the only thing an evaluation accepts, and it creates no publisher
aggregate. A publisher-level class is not an operation a user performs: it is a
reading over the articles already classified, derived on request by the publisher
aggregation endpoint and never stored. The application never crawls a publisher
to discover articles it has not been given.

Before submission, Evaluate reports whether the URL is known, requires new
inference, lacks a matching local checkpoint, or is blocked for training-data
leakage. Checkpoints withheld by the leakage guard are named, so a hidden option
is never unexplained.

After single-article completion, the new immutable run is appended to the
authoritative state ledger and mirrored to a private, git-ignored
`dataset/predictions/user-predictions.csv` as
`prediction_origin=user_evaluation`. The row stores one exact run and never
touches the tracked release. Evaluate keeps a prominent result card on the
page with the predicted `Class 0..4`, all five decimal/percentage
probabilities, exact model/fold, stored-versus-new origin, run ID, and a link to
the complete article history. Earlier local runs are read from Articles &
predictions rather than repeated on the Evaluate page. Articles & predictions
provides separate filters and visual badges for
dataset-backed articles and articles created solely by a user inference; a
dataset article evaluated locally retains both facts.

For a five-fold imported corpus, checkpoint fold `N` may evaluate known
articles assigned to held-out test fold `N` and must not evaluate known articles
assigned to any other fold. The same rule filters publisher candidates and is
enforced again by the backend. Unknown external URLs have no registered fold
membership; their absence is not represented as proof of training exclusion.
A local inference never creates fold-membership evidence for a previously
unknown URL.

Every evaluation stores the ordered article and prediction-run IDs actually
used. A later run cannot change an earlier evaluation.

Explicit-list candidates run in submitted order and all must succeed. Submitted
and online-resolved canonical article IDs must remain distinct; otherwise the
job fails `INVALID_INPUT`. On any failure no evaluation is written, while
already committed individual runs/content stay valid. Publisher stored
candidates are ordered by effective latest-run time descending then canonical
URL ascending. Publisher input does not discover or infer additional articles.
Publisher failure or partial success does not roll back previously committed
individual runs/content.

### 7.4 Import

The API accepts one CSV or CSV.GZ upload. It writes a private temporary file,
computes its SHA-256, enforces the byte/row limits, parses incrementally, and
retains only allowlisted projected values in memory. After complete validation
it replaces models, runs, and the import record in deterministic order. This is
idempotent but not a multi-file transaction; after interruption, resubmitting
the same user file converges without duplicate identities. The temporary file
is deleted at terminal job cleanup.

The user schema requires `url` and at least one model family's predicted class
and fold. `title`, `text`, `authors`, source-local ID, and domain are optional;
editorial values are discarded and domain is recomputed. Conflicting outputs
for the same canonical article/model in one source reject that pair before
publication. A repeated parse-complete content digest/schema returns its
existing successful, partial, or deterministic failed import.
The selected source file is never modified.

### 7.5 Saved content and purge

Saved title/body live only in `local_content.csv` and are returned only by the
dedicated content endpoint. A synchronous confirmed delete is accepted only
when no evaluation job is running, then rewrites that small ledger through a
temporary file and atomic rename. It affects active state only. User-created
backups and external copies must be deleted manually.

### 7.6 Clearing local user data

A single confirmed operation deletes everything a user produced on this
machine — every `local_inference` prediction run, every row of saved content
regardless of which run it accompanies, and the private prediction mirror —
and nothing else: bundled and user-imported dataset rows, their model
identities, and the tracked release are never touched. It is refused while any
evaluation job is running or the typed confirmation does not match, exactly
like the single-article purge above.

Order is safety-critical, not incidental: the private mirror is removed before
`prediction_runs.csv` is rewritten. An interruption between those two steps
leaves an already-doomed row sitting in the ledger, recoverable by repeating
the operation; the reverse order would let a surviving mirror silently restore
every deleted run at the next start, undoing a deletion already reported as
complete.

## 8. Jobs and UI

Only operations that can take noticeable time are jobs.
The persisted job-type registry is: `evaluation`, `dataset_import`, `model_validation`.
Status is
`queued`, `running`, `succeeded`, or `failed`. Progress is an approximate
integer `0..100` that only ever moves forward. Phases are readable English
sentences, not opaque codes:

- evaluation reports every step that can take noticeable time, so the interface
  is never frozen on one value: checking the selected model, retrieving and
  extracting the page, verifying and loading the checkpoint, classifying the
  text, then saving. Reuse of a stored prediction and publisher aggregation
  report their own shorter sequences;
- import: `parsing`, then terminal `saving` (upload reception precedes job
  creation);
- model validation: `scanning`, then terminal `saving`.

One FIFO worker executes jobs. The frontend polls the job endpoint about once
per second while a job runs; SSE, cancellation, and retry are absent. After restart, queued jobs run
again only when every acquired source they require still exists. A queued job
with a missing source and every running job fail as `PROCESS_INTERRUPTED`;
terminal job handling cleans its acquired temporary upload.

An unconfirmed action on the Jobs page deletes every job row outright: this is
disposable operational history, not user-produced data, so it carries none of
the confirmation the purges in §7.5–7.6 require. It still refuses while any
job is `queued` or `running`, because the ledger disappearing out from under a
live job either loses a queued one before it runs or lets a running one
resurrect its own row when it finishes.

The UI has Evaluate, Articles, Publishers, Models, and Jobs. Evaluate is the
default and first navigation item. The top-bar status control (`Ready ·
local`/`Ready · offline`) opens a small popover with workspace counts and
runtime details, replacing a dedicated dashboard page. It favors provenance
and scientific explanation over administration. Loading,
empty, offline, missing-model, partial, and error states use clear English text.
The persistent top bar does not remount or shift during route changes. The UI
uses one light visual system with no theme
control and no dark mode, and the system Times New Roman serif font throughout,
without a CDN.

## 9. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-001 | Native and Compose startup shall expose the same loopback-only demo. |
| FR-002 | The bundled prediction release shall verify and import once by content digest. |
| FR-003 | User CSV/CSV.GZ imports shall project only allowed scientific fields and reject intra-import conflicts before publication. |
| FR-004 | Protected ground truth, authors, and raw HTML shall never persist or appear in ordinary output. |
| FR-005 | Title/body shall persist only after explicit `save_local` and active-state deletion shall be available. |
| FR-006 | Article and publisher history shall remain browsable and aggregable offline. |
| FR-007 | `reuse` shall select the latest exact-model immutable run without creating another run. |
| FR-008 | `recompute` and missing-run inference shall create new immutable runs with exact provenance and idempotently mirror each run to the prediction dataset as `user_evaluation`. |
| FR-009 | A publisher class shall be derived on request from stored article runs, never persisted, and shall report the model and exact articles counted. |
| FR-010 | The three aggregation methods shall implement the scientific formulas and availability rules exactly. |
| FR-011 | Bundled and user-imported predictions shall contain all five finite class probabilities; values shall never be fabricated. |
| FR-012 | Exact model identity shall include every output-relevant setting and exclude filesystem location. |
| FR-013 | Only built-in safe loaders shall read artifacts; artifact code shall never execute. |
| FR-014 | BERT and RoBERTa shall form the built-in core model path. |
| FR-015 | New web inference shall use safe retrieval, unchanged extracted text, and deterministic English validation. |
| FR-016 | Strict offline mode shall prevent every application-initiated outbound HTTP request. |
| FR-017 | Essential state shall survive restart in the six documented CSV ledgers; user-evaluation rows in the dataset CSV shall provide an additional recoverable mirror, not a second independent identity system. |
| FR-018 | UI/API long operations shall use the three simple persisted job types and polling; CLI commands shall run the same work synchronously. |
| FR-019 | The local API shall validate Host and reject non-loopback configuration. |
| FR-020 | UI, API and the prediction CSV shall expose model, fold, run, contributing articles where applicable, method, all available probabilities, dataset-versus-user origin, and scientific limitations. |
| FR-021 | Evaluate shall offer only locally present safe models: stored family/fold coverage for reuse and runnable local IDs for new single-article inference; every empty result shall be explained. |
| FR-022 | A local checkpoint shall be blocked from evaluating any known imported article outside its held-out test fold for single, list, and publisher workflows. |
| FR-023 | The bundled dataset shall contain only BERT/RoBERTa outputs with complete five-class probability vectors and shall replace obsolete bundled releases without touching user imports. |
| FR-024 | Custom import shall accept only the documented five-class encoder contract and mark it `user_custom`, rejecting executable code, pickle, unsafe paths, invalid folds, bases and tensor/head mismatches; importing the study's larger decoder checkpoints shall be refused with `FEATURE_UNAVAILABLE` while that support is under development. |
| FR-025 | A confirmed bulk purge shall permanently delete every local prediction, its saved content, and its private mirror, in an order that cannot resurrect a deleted run on restart, without touching bundled or user-imported dataset rows. |
| FR-026 | Clearing job history shall need no confirmation and shall delete every job row, but shall refuse outright while any job is queued or running. |

## 10. Non-functional requirements

| ID | Requirement |
| --- | --- |
| NFR-001 | The main workflow and module boundaries shall be understandable without distributed-systems or database-internals knowledge. |
| NFR-002 | The UI shall remain usable with the bundled dataset on a typical four-core, 16-GiB research workstation; no hard latency SLA applies. |
| NFR-003 | Dependency locks, dataset checksums, and core model fixtures shall make the demo reproducible. |
| NFR-004 | CSV writes shall use one writer, fsync, atomic replacement for complete-file updates, and fail-closed structural verification as documented. |
| NFR-005 | Logs and errors shall exclude editorial content, protected data, credentials, and unrestricted paths. |
| NFR-006 | Frontend assets and API documentation shall be bundled locally without telemetry or CDN dependencies; the frontend shall use the system Times New Roman font rather than bundled font files. |
| NFR-007 | User-visible text, errors, exports and the persistent top bar shall be English and accessible. |
| NFR-008 | API and frontend shall share the same service and validation functions. |

## 11. Release gate

The core release suite runs on a normal CPU workstation natively and with
Compose. Optional GPU and stress/fault tests report separately. Passing the core
gate demonstrates scientific correctness, privacy, essential persistence,
import, inference, aggregation, local startup, and offline behavior; it does
not certify the demo for public or production deployment.
