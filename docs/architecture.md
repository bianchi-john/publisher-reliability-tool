# Architecture

**Status:** Normative research-demo architecture

## 1. Design rule

The architecture is optimized for a readable local reference implementation,
not for horizontal scale, remote clients, or exhaustive crash tolerance. One
Python process owns one data directory, serves the UI/API, and runs one FIFO
background worker. CSV remains inspectable and replaceable with ordinary tools.

## 2. Fixed stack

| Layer | Technology |
| --- | --- |
| Runtime | Python 3.12 |
| API | FastAPI, Pydantic v2, generated OpenAPI 3.1 |
| Server | Uvicorn, one worker, fixed loopback binding |
| Frontend | Bundled static HTML, CSS and browser JavaScript; local Gloock and Instrument Sans |
| Persistence | Python `csv`, in-memory row lists, filesystem lock |
| Retrieval | `httpx` and English Newspaper3k extraction |
| Language | `langdetect`, seed zero |
| Models | PyTorch, Transformers and safetensors |
| Packaging | Python wheel and one simple Compose service |

## 3. Process and data flow

```text
browser/CLI -> FastAPI service -> Storage (seven authoritative CSV files)
                         |
                         +-> FIFO job worker
                               -> ArticleRetriever
                               -> ModelLoader
                               -> InferenceService
                               -> AggregationMethod
                                      |
                                      +-> PredictionDatasetMirror
                                          -> dataset/predictions/predictions.csv
```

Frontend and API use the same Pydantic request types and service functions.
There is no separate API implementation for the UI and no frontend access to
CSV files.

## 4. Concrete module boundaries

| Boundary | Responsibility | How to extend |
| --- | --- | --- |
| `Storage` | Load ledgers, lock data directory, append immutable rows, atomically rewrite small mutable files | Add a column/schema version and loader validation |
| `PredictionDatasetMirror` | Upgrade the public CSV schema, mirror local runs idempotently, refresh its manifest, and restore mirrored runs at startup | Add an explicit origin/run field without changing original-row identity |
| `ModelLoader` | Recognize one explicit family, validate resources, tokenize, run its frozen fixture | Add one Python class and scientific fixture; no plugin loader |
| `ArticleRetriever` | Normalize URLs, enforce safe HTTP policy, parse supplied HTML | Add an extraction strategy behind the same content boundary |
| `InferenceService` | Select reuse/recompute, call loader, validate probabilities, create provenance | Add output fields explicitly to run schema |
| `AggregationMethod` | Report availability and compute a deterministic result from exact runs | Add a named function, version, fixture, and UI explanation |

Supporting modules are `config`, `api`, `imports`, `jobs`, `identity`,
`language`, and `frontend`. Avoid registries, dependency injection frameworks,
plugin discovery, or generic event buses; ordinary Python composition is the
extension mechanism.

## 5. Storage approach

`csv-storage-contract.md` defines seven authoritative CSV ledgers. Articles and
publishers are derived at startup from canonical URL, publisher hostname, and
prediction-run data. This avoids synchronizing a second entity store.

The prediction release is a deliberate, inspectable replica for user-created
article runs. Original rows use `prediction_origin=dataset_original`; one local
inference uses one `prediction_origin=user_evaluation` row identified by
`prediction_run_id`. A run commits to `prediction_runs.csv` first, then the
mirror rewrites `predictions.csv` and `manifest.json` through sibling temporary
files. At startup, valid CSV content can reconcile stale mutable manifest
metadata when the immutable original digest still matches; mirrored local rows
missing from state are then restored before all local runs are synchronized
again. Thus the dataset copy can aid recovery but never creates a competing run
ID or duplicate on restart.

- Immutable scientific rows (`prediction_runs.csv`, `evaluations.csv`, and
  `imports.csv`) are appended, flushed, and fsynced.
- Small mutable state (`models.csv`, `jobs.csv`, `local_content.csv`) is written
  completely to a sibling temporary file, verified, fsynced, and atomically
  renamed.
- A process-wide write mutex serializes writes; a POSIX `flock` prevents a
  second process from using the directory.
- Malformed authoritative CSV fails closed; startup does not trim or infer
  missing data.
- Import validates the complete source, then replaces models, runs, and import
  history in deterministic order. Repeating the same source converges without
  duplicate identities; there is no custom transaction protocol.

There is no transaction ledger, record versioning, compaction, commit
watermark, or snapshot history.

The seven ledgers are loaded into simple in-memory row lists. Query services
derive temporary dictionaries/groupings as needed; there is no separate index
format or cache invalidation layer. Offset pagination reflects committed state
at each request, so a concurrent local write can shift later pages, which is
acceptable for this single-user demo.

## 6. Jobs

One FIFO worker runs `evaluation`, `dataset_import`, and `model_validation`
jobs. Admission persists a queued row; the worker rewrites job state at
macrophase boundaries. The browser polls every two seconds.

No persistent event stream, cancellation, retry endpoint, priority queue, lane,
or job-level parallelism exists. Publisher candidates are sequential. On
restart, queued jobs are admitted again when every acquired source they require
still exists; otherwise they fail. A running job becomes failed with
`PROCESS_INTERRUPTED` and its temporary source is cleaned up. The user uploads
again rather than resuming or retrying it.

Shutdown stops admission, requests the worker to stop, waits five seconds, then
lets the process exit at its current boundary. It does not claim to cancel
model/kernel/filesystem calls safely; the ordinary append/rename write rules
leave already committed rows intact after an abrupt process stop.

The complete startup order and the per-job macro phases are owned by the
product specification. This architecture does not insert an HTTP-serving or
background-worker phase before structural verification completes.

## 7. URL and publisher identity

Offline normalization:

1. trim surrounding whitespace and reject controls/user-info;
2. accept explicit HTTP(S) with a DNS hostname;
3. apply IDNA UTS #46 non-transitional processing and lowercase the host;
4. remove the fragment and default port;
5. normalize empty path to `/`;
6. remove only query components whose decoded key starts `utm_` or equals
   `fbclid`, `gclid`, `mc_cid`, `mc_eid`, or `homepageposition`;
7. preserve order, duplicates, `+`, percent encoding, path case, and trailing
   slash for every retained component.

Online resolution follows at most five safe redirects and uses the first
same-publisher canonical link from the already downloaded HTML; it does not
request that link. Article identity is the normalized canonical URL and its
persisted ID is UUIDv5. Publisher identity is the normalized hostname with one
leading `www.` removed; the URL port is not part of publisher identity and
registrable-domain guessing is not used.

## 8. Retrieval boundary

The retriever accepts HTTP(S), resolves and validates every hop, rejects private,
loopback, link-local, multicast, reserved, and unspecified addresses, disables
environment proxies with `trust_env=false`, enforces five redirects, a
10-second connect/20-second request timeout, HTML MIME, and an 8 MiB
decompressed page limit.

The request sends `Accept-Language: en-US,en;q=0.9`. Newspaper3k receives only
the already downloaded HTML and is configured with `language="en"`; it cannot
issue a second request. No secondary extractor is registered: parsing failure
is `EXTRACTION_FAILED`, and insufficient Newspaper3k text is `TEXT_TOO_SHORT`.
HTML, authors, and extracted content stay in job memory. Only validated
title/body may cross into `local_content.csv` after `save_local`; authors and
raw HTML are always released. Offline mode blocks retrieval and configures core
tokenizer acquisition with local-files-only behavior.

The top bar and primary navigation live outside the route content boundary.
Navigation retains the existing view until the target view is ready, while a
stable scrollbar gutter and minimum content height prevent layout movement.
Route completion returns the document to the top and moves keyboard focus to
the main content with scroll prevention, so the sticky bar cannot cover the
first navigation item.
The top bar contains a light/dark theme control. The initial theme follows
`prefers-color-scheme`, an explicit choice is stored in browser local storage,
and both warm orange/terracotta palettes use locally bundled Gloock for display
headings and Instrument Sans for body text, navigation and controls. Both font
families retain their SIL Open Font License files in the frontend package.

## 9. Model lifecycle

Missing configured model roots are skipped. Existing roots must be real
readable directories. Scanning never
follows symlinks; a candidate containing a symlink is rejected. API clients can
scan configured roots or upload an artifact but cannot submit arbitrary server
paths.

The internal `<data-dir>/managed-models` directory stores successful official
and custom imports. Startup does not rerun their full Transformers validation; a
scan verifies the registered directory digest and marks a missing or altered
bundle unavailable. Startup scans configured roots for BERT/RoBERTa checkpoints
and exact OSF Llama/Mistral file sets so copied, removed, or restored
checkpoints are reflected before readiness; the UI/API
scan remains available for changes made while the service is running.

Upload validation moves a successful artifact into that root before the
atomic model-ledger registration. A crash in between may leave an unregistered
candidate. Startup ignores it; uploading the same deterministic bundle again
registers the already matching artifact. No separate upload transaction or
orphan ledger is introduced.

Built-in official recipes determine scientific model identity independently of
filesystem location. States are `compatible`, `validated_not_runnable`,
`historical_only`, `artifact_missing`, `dependency_missing`,
`resource_unavailable`, and `invalid`.
Historical runs remain browseable and aggregable when an artifact disappears.
The exact file/directory digest is checked again before a model is loaded, so a
checkpoint changed after scanning cannot run under its previous scientific ID.

BERT and RoBERTa loaders and fixtures are core. Official Llama 3 8B and Mistral
24B use built-in, notebook-derived QLoRA sequence-classification recipes and
are identified by exact OSF checksums. Custom import accepts only the fixed PRT
manifest vocabulary: an allowlisted complete encoder or a PEFT adapter for
those two exact bases. `auto_map`, `trust_remote_code`, Python/native files, and
pickle weights are rejected. LLM artifacts can be valid but non-runnable when
CUDA, dependencies or pinned base access is unavailable. Unknown artifacts are
reported and ignored.

## 10. Local HTTP boundary

Native execution binds only `127.0.0.1`. The official container may listen on
`0.0.0.0` internally because Compose publishes it as
`127.0.0.1:${PRT_PORT}:8000`; the image-only flag enabling that exception is not
a general deployment mode.

A small middleware compares `Host` with the configured local origin to reduce
accidental DNS-rebinding exposure. There is no authentication or configurable
CORS. The application emits no permissive CORS header. SSRF protection is
required because a local user can still submit a dangerous retrieval URL.

## 11. Observability and failure behavior

Plain structured logs record startup, job ID/type/status, import counts, model
validation, retrieval outcome, inference duration, aggregation method, and safe
error code. They omit page content, authors, raw HTML, protected values,
credentials, headers, and absolute artifact paths. Standard library rotating
logs retain three 5-MiB files; this is a convenience, not an audit system.

| Failure | Demo behavior |
| --- | --- |
| Missing seed/model/dependency | Start normally and show guidance |
| Port occupied | Exit before data mutation |
| Second process | Exit with `STORAGE_ERROR` |
| Malformed or incomplete authoritative CSV | Exit with `STORAGE_ERROR` without serving HTTP |
| Queued upload job whose acquired source is missing | Mark `PROCESS_INTERRUPTED` |
| Running job at restart | Mark `PROCESS_INTERRUPTED` |
| Network unavailable/offline | Preserve browsing/reuse; fail the dependent job |
| Missing artifact | Preserve historical model identity and runs |
| Prediction mirror is unwritable | Preserve the committed state run, fail the dependent inference operation, and report storage failure |
| Purge | Rewrite active local-content file; backups remain the user's responsibility |

Manual stopped-server copying of the data directory is the backup and restore
procedure. Exhaustive ENOSPC matrices, automatic backup rotation, online
recovery UI, and high-availability behavior are outside the demo.

## 12. Invariants

1. A publisher evaluation always names exact immutable runs from one model.
2. Protected reference data never crosses the import projection.
3. Authors/raw HTML never persist; title/body require explicit consent.
4. `reuse` creates no run when an exact run exists; a missing-run `reuse` and
   every `recompute` create a new immutable run.
5. Model identity contains scientific settings, never deployment paths.
6. Offline mode makes no application HTTP connection.
7. CSV is sufficient to reconstruct every persisted API resource.
8. UI and API call the same services and formulas.
9. A known fold-indexed article is never sent to a checkpoint trained on its
   fold; only its held-out checkpoint fold is eligible.
10. Matching a local checkpoint to stored coverage by family/fold never changes
    either the local model ID or the historical prediction model ID.
11. Article source badges are derived from run origin: imports establish
    dataset membership, while `local_inference` establishes user evaluation.
12. Every committed local inference has at most one schema-2 dataset row with
    the same `prediction_run_id`; original dataset rows are never rewritten as
    user rows.
