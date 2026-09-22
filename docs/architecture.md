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
| Frontend | Bundled static HTML, CSS and browser JavaScript; system Times New Roman throughout |
| Persistence | Python `csv`, in-memory row lists, filesystem lock |
| Retrieval | `httpx` and English Newspaper3k extraction |
| Language | `langdetect`, seed zero |
| Models | PyTorch, Transformers and safetensors |
| Packaging | Python wheel and one simple Compose service |

## 3. Process and data flow

```text
browser/CLI -> FastAPI service -> Storage (six authoritative CSV files)
                         |
                         +-> AggregationMethod        (synchronous, read-only:
                         |                             a publisher class is
                         |                             derived per request and
                         |                             never written)
                         |
                         +-> FIFO job worker
                               -> ArticleRetriever
                               -> ModelLoader
                               -> InferenceService
                                      |
                                      +-> PredictionDatasetMirror
                                          -> dataset/predictions/user-predictions.csv
                                             (private, git-ignored; the tracked
                                             predictions.csv is never written)
```

Frontend and API use the same Pydantic request types and service functions.
There is no separate API implementation for the UI and no frontend access to
CSV files.

## 4. Concrete module boundaries

| Boundary | Responsibility | How to extend |
| --- | --- | --- |
| `Storage` | Load ledgers, lock data directory, append immutable rows, atomically rewrite small mutable files | Add a column/schema version and loader validation |
| `PredictionDatasetMirror` | Mirror local runs idempotently to a private, git-ignored file and restore mirrored runs at startup; never writes the tracked release | Add an explicit origin/run field without changing original-row identity |
| `ModelLoader` | Recognize one explicit family, validate resources, tokenize, run its frozen fixture | Add one Python class and scientific fixture; no plugin loader |
| `ScanCache` | Skip re-hashing and re-validating a checkpoint whose file is unchanged, and discard itself whenever the validation rules change | Extend the fingerprint, or bump the validation logic version so older entries are dropped; never widen what counts as unchanged |
| `ArticleRetriever` | Normalize URLs, enforce safe HTTP policy, parse supplied HTML | Add an extraction strategy behind the same content boundary |
| `InferenceService` | Select reuse/recompute, call loader, validate probabilities, create provenance | Add output fields explicitly to run schema |
| `AggregationMethod` | Report availability and compute a deterministic result from exact runs | Add a named function, version, fixture, and UI explanation |

Checkpoint verification is the slow part of startup: each `.pt` file is read
once for the SHA-256 that is its scientific identity and once for a strict-shape
`torch.load`. `model_scan_cache.py` records the result of a *successful*
verification against the file's device, inode, size and modification time, in
`<data-dir>/model-scan-cache.json`. Any difference in that fingerprint, a
rejected checkpoint, a change to the validation rules, or `models scan --full`
all force full verification again, and the file may be deleted at any time. A
cache hit therefore asserts that the file has not been touched since it was
verified, not that its bytes were re-read now: it does not lower the bar against
someone who can already write to the model directory, but silent corruption that
preserves size and timestamp is no longer caught automatically.

The modules behind those boundaries are `storage`, `prediction_dataset`,
`model_scanner` with `model_scan_cache`, `custom_models` and `official_models`,
`inference` (which owns both retrieval and the loaders), `services` and
`aggregation`. Supporting them are `config`, `api`, `openapi_examples`, `cli`,
`jobs`, `identity`, `errors` and `frontend`. Language detection has no module of
its own: `langdetect` is called at the one point in `inference` where extracted
text is validated. Avoid registries, dependency injection frameworks, plugin
discovery, or generic event buses; ordinary Python composition is the extension
mechanism.

The frontend is plain HTML, CSS and vanilla ES modules, with no build step. Each
screen's static markup is an ordinary HTML file in `frontend/pages/`, containing
`{{placeholder}}` slots; the module of the same name in `frontend/js/pages/`
fills those slots and wires up that screen's controls. Shared code is split by
concern: `api.js` (the only module that calls the backend), `format.js`
(escaping and label names), `components.js` (reusable fragments such as tables
and error cards), `job-progress.js`, `topbar.js`, `templates.js` (loads and
fills the page files) and `router.js`. To change how a screen looks, edit its
HTML file; to change what it does, edit its page module.

## 5. Storage approach

`csv-storage-contract.md` defines six authoritative CSV ledgers. Articles and
publishers are derived at startup from canonical URL, publisher hostname, and
prediction-run data. This avoids synchronizing a second entity store.

The prediction mirror is a deliberate, inspectable replica for user-created
article runs, kept in a private, git-ignored file
(`dataset/predictions/user-predictions.csv`) entirely separate from the tracked
`predictions.csv` release: a user's own evaluation history must never enter
version control. Original rows in the tracked release use
`prediction_origin=dataset_original` and are never rewritten by the running
application; one local inference uses one `prediction_origin=user_evaluation`
row identified by `prediction_run_id` in the private mirror. A run commits to
`prediction_runs.csv` first, then the mirror file is rewritten through a
sibling temporary file. At startup, mirrored local rows missing from state are
restored before all local runs are synchronized again. Thus the mirror can aid
recovery but never creates a competing run ID or duplicate on restart, and
never touches the tracked release.

- Immutable scientific rows (`prediction_runs.csv` and
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

The six ledgers are loaded into simple in-memory row lists. Query services
derive temporary dictionaries/groupings as needed; there is no separate index
format or cache invalidation layer. Offset pagination reflects committed state
at each request, so a concurrent local write can shift later pages, which is
acceptable for this single-user demo.

## 6. Jobs

One FIFO worker runs `evaluation`, `dataset_import`, and `model_validation`
jobs. Admission persists a queued row; the worker rewrites job state at
phase boundaries, including every evaluation step that can take noticeable
time. The browser polls about once per second while a job runs.

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

Online resolution follows at most five safe redirects and then normalizes the
URL the final response was served from. A `<link rel="canonical">` in the page
body is deliberately *not* consulted: it is publisher-controlled content, it
would let a page reassign its own identity, and honouring it could move an
article onto an identity whose imported fold differs from the one the leakage
guard already cleared. Article identity is the normalized canonical URL and its
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

Two checks stand between a URL and the classifier, because Newspaper3k extracts
text from any page with paragraphs in it and a publisher's front page comes back
as a long wall of headlines that clears every length floor. Before the request,
`page_kind.refuse_site_address` rejects a URL whose path names a site or a
section rather than a page (`PUBLISHER_HOMEPAGE`); after parsing,
`page_kind.refuse_non_article_text` rejects a page that declares an `og:type`
other than an article, or whose extracted text is not mostly long blocks
(`NOT_AN_ARTICLE`). Both are heuristics, tuned to catch the obvious mistake
rather than to adjudicate: a page the checks let through may still be unusual.
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
The interface uses one light palette, defined as CSS custom properties at the
top of `styles.css`; there is no
theme control and no dark mode. Display headings, body text, navigation and
controls all use the system Times New Roman serif font, so no font files are
bundled with the frontend.

## 9. Model lifecycle

Missing configured model roots are skipped. Existing roots must be real
readable directories. Scanning never
follows symlinks; a candidate containing a symlink is rejected. API clients can
scan configured roots or upload an artifact but cannot submit arbitrary server
paths.

The internal `<data-dir>/managed-models` directory stores successful custom
imports. Startup does not rerun their full Transformers validation; a scan
verifies the registered directory digest and marks a missing or altered bundle
unavailable. Startup scans configured roots for BERT/RoBERTa checkpoints so
copied, removed, or restored checkpoints are reflected before readiness; the
UI/API scan remains available for changes made while the service is running.

Upload validation moves a successful artifact into that root before the
atomic model-ledger registration. A crash in between may leave an unregistered
candidate. Startup ignores it; uploading the same deterministic bundle again
registers the already matching artifact. No separate upload transaction or
orphan ledger is introduced.

Built-in official recipes determine scientific model identity independently of
filesystem location. States are `compatible`, `historical_only`,
`artifact_missing`, `dependency_missing`, `resource_unavailable`, and `invalid`.
Historical runs remain browseable and aggregable when an artifact disappears.
The exact file/directory digest is checked again before a model is loaded, so a
checkpoint changed after scanning cannot run under its previous scientific ID.

A scan reconciles the ledger against the filesystem, and two rules keep that
reconciliation from producing a store that can no longer be opened:

- a local row that a prediction run still names is never deleted, only marked
  `artifact_missing`. Because identity is content-addressed, the same bytes
  refiled under another family or fold become a *different* model, so the old
  identity can disappear from a scan while its runs remain; dropping the row
  would leave those runs pointing at nothing, which `Storage.reload` rejects;
- when a checkpoint that was absent during mirror restore comes back, the scan
  rediscovers the identity that `restore_user_predictions` had recreated as a
  historical placeholder. Only the rediscovered local row is written: emitting
  both would duplicate a model identifier, which `Storage.reload` also rejects.

Symmetrically, an import registers a historical identity only for a family/fold
it actually published runs for, so a wholly rejected import leaves no model row
explaining no prediction.

BERT and RoBERTa loaders and fixtures are core. Custom import accepts only the
fixed PRT manifest vocabulary: an allowlisted complete encoder classifier.
`auto_map`, `trust_remote_code`, Python/native files, and pickle weights are
rejected. Unknown artifacts are reported and ignored.

There is one loader and one bundle contract. Decoder families are out of scope:
they require a CUDA GPU and tens of gigabytes per fold, which neither the CPU
demo nor its host can provide, so the code carries no dormant path for them.
Model identity remains content-addressed over output-relevant settings rather
than over an architecture name, and the leakage guard records fold membership
per article, so neither would have to be redesigned if that ever changed.

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
| Private prediction mirror is unwritable | Preserve the committed state run, fail the dependent inference operation, and report storage failure |
| (no deletion path exists) | The application never removes a stored row; discarding data is done by removing the data directory on the host |
| Confirmed clear of all local user data | Remove the private mirror first, then the `local_inference` runs and saved content; imported rows and the tracked release are untouched |

Manual stopped-server copying of the data directory is the backup and restore
procedure. Exhaustive ENOSPC matrices, automatic backup rotation, online
recovery UI, and high-availability behavior are outside the demo.

## 12. Invariants

1. A publisher class always names exact immutable runs from one model and is
   computed on request, never stored.
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
