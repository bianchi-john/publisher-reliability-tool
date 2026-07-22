# Product Specification

**Status:** Normative MVP contract

## 1. Product objective

Publisher Reliability Tool is a single-user local application for inspecting
historical article predictions, running compatible Transformer classifiers on
English articles, and aggregating compatible article predictions into a
publisher-level estimate.

The product is not a fact checker and does not expose protected ground-truth
ratings. Every result is identified as a model output and includes its model,
fold, input articles, origin, and aggregation method.

The same application is usable through a terminal-started web server, a local
REST API, and a browser frontend. API and frontend invoke the same service layer
and therefore cannot implement different validation or scientific behavior.

## 2. Supported operating environment

- Native reference platform: Ubuntu 24.04 LTS, x86-64, Python 3.12.
- Container reference platform: Docker Engine 26 or newer with Docker Compose
  v2 on x86-64 Linux.
- Browser baseline: current and previous major release of Firefox or Chromium.
- Default address: `http://127.0.0.1:8000`.
- Default API base: `http://127.0.0.1:8000/api/v1`.
- One application process and one Uvicorn worker per data directory.
- One human user per running instance.

Other Linux distributions are unsupported rather than silently assumed
compatible. macOS, Windows, ARM, multi-user hosting, and horizontally scaled
deployments are outside the MVP.

## 3. Included scope

The MVP shall:

- start natively from a Linux terminal and through Docker Compose;
- serve a responsive local frontend and versioned REST API;
- verify and import the bundled public prediction release on first startup;
- import additional compatible CSV files, manifest directories through the
  offline CLI, or supported upload containers;
- maintain all authoritative mutable state as local CSV ledgers;
- browse, search, filter, paginate, inspect, and export local articles,
  publishers, prediction runs, evaluations, models, imports, and jobs;
- discover and validate supported local model artifacts;
- register an official supported model from a configured server-local root or
  a streamed browser/API upload;
- show the official OSF download link and exact placement instructions;
- run model inference locally from explicitly saved local text for a missing
  reusable run, or from ephemeral article retrieval for a missing run or
  explicit recomputation;
- create a new immutable prediction run when recomputation is explicit;
- optionally save only extracted title/body to the ignored local CSV data
  directory after explicit per-request consent;
- evaluate one article, 2–50 explicit same-publisher articles, or one publisher
  homepage with a requested count of 2–50 articles;
- expose `majority_vote`, `ordinal_mean`, and `mean_probabilities` under their
  exact availability and tie rules;
- store every successful new prediction run and publisher evaluation across
  restarts;
- retain URL/publisher identity; discard title/body by default; never retain
  authors or raw HTML;
- show five-class model probabilities when present and `Not available` when
  absent;
- show accessible charts backed by the same exact values rendered in tables;
- operate in a strict offline mode that prevents all outbound HTTP requests;
- provide stable machine-readable error codes and inspectable background jobs.

## 4. Excluded scope

The MVP shall not:

- train, fine-tune, calibrate, or automatically ensemble models;
- provide hosted inference, cloud storage, accounts, or remote collaboration;
- use SQLite, PostgreSQL, browser storage, or another database as authoritative
  persistence;
- modify an imported source CSV;
- persist extracted title/body without explicit `save_local` consent;
- persist author values, raw HTML, or generated snippets under any option;
- publish original reference-provider labels, scores, ranges, or metadata;
- translate or evaluate non-English articles;
- bypass paywalls, authentication, robots exclusions, or publisher access
  controls;
- execute arbitrary Python code embedded in a model artifact;
- claim that softmax values are calibrated confidence;
- claim that a publisher result applies independently of its selected model,
  articles, fold, or aggregation method.
- bind a non-loopback interface, accept arbitrary server-local paths through
  the API, or support generic custom-model manifests;
- automatically download/setup model dependencies, rewrite backups during a
  content purge, resume SSE history across process restarts, or compact while
  the server is running.

## 5. Exact CLI surface

The installed executable is `publisher-reliability`. These commands are part
of the MVP and their exit codes are stable:

```text
publisher-reliability serve [OPTIONS]
publisher-reliability dataset verify PATH
publisher-reliability dataset import PATH
publisher-reliability models scan [PATH ...]
publisher-reliability storage verify
publisher-reliability storage compact
```

`serve` supports:

| Option | Default | Contract |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Must be a loopback bind; non-loopback is outside the MVP |
| `--port` | `8000` | Integer `1..65535`; startup fails if unavailable |
| `--data-dir` | `./data` | Authoritative CSV state, locks, logs, and uploads |
| `--models-dir` | repeatable `./models` | Recursively scanned; hidden directories are skipped |
| `--seed-dataset` | `./dataset/predictions` | CSV or manifest directory imported idempotently |
| `--offline` | false | Blocks all outbound application HTTP requests |
| `--log-level` | `info` | One of `debug`, `info`, `warning`, `error` |

`dataset verify PATH` is read-only and validates any supported import
container without creating a data directory. `dataset import PATH`,
`models scan [PATH ...]`, `storage verify`, and `storage compact` accept
`--data-dir PATH` with default `./data`. Each explicit `models scan` path is a
model root for that command; the no-path form uses `./models`. Every command
that reads or mutates database ledgers acquires the same exclusive writer lock
and fails `STORAGE_LOCKED`
rather than running beside the server. `models scan` with no path scans the
configured/default model roots. Successful commands print an English summary
and machine-stable IDs/counts; they never print editorial content or protected
values.

Example:

```bash
publisher-reliability serve \
  --data-dir ./data \
  --models-dir ./models \
  --seed-dataset ./dataset/predictions
```

Exit code `0` means success, `2` invalid CLI/configuration, `3` invalid dataset
or storage, and `1` any unexpected runtime failure. `serve` remains running
until `SIGINT` or `SIGTERM` and performs a bounded graceful shutdown.
`models scan` exits `0` when the scan itself completes even if individual
artifacts are invalid/unavailable or reported unsupported; its summary reports
each outcome, while only identities with an official manifest entry become
model records.

## 6. Startup contract

Startup performs these steps in order. Steps 1–3 are read-only with respect to
the data directory:

1. Parse CLI and environment configuration and reject unknown or conflicting
   values.
2. Create and bind the configured loopback socket without accepting
   connections. This reserves the port; an unavailable port terminates without
   creating, locking, or changing the data directory.
3. Validate existing path types/readability without creating state.
4. Acquire the writer lock, then create missing ledgers only when no compaction
   marker or staging directory exists.
5. Recover an uncommitted tail or interrupted offline compaction and verify all
   committed rows. Corrupt committed storage closes the reserved socket and
   terminates; no diagnostic HTTP server is started.
6. Verify/import the bundled dataset by content digest and schema version.
7. Scan configured model roots without following symlinks.
8. Requeue committed `queued` jobs and mark jobs left `running` failed with
   `PROCESS_INTERRUPTED`.
9. Put the reserved socket into listening mode and start the HTTP server and
   bounded executor. No request is accepted before this step.
10. Print the UI/API/documentation URLs and safe status summary.

A missing model or seed dataset is not a startup failure. The server enters
history-only or empty-history mode and displays corrective instructions. An
invalid existing CSV database, unsafe bind configuration, unavailable port, or
second writer is a startup failure and exposes no HTTP endpoint.

## 7. Operating modes

### 7.1 Local browsing

All list, detail, chart, filter, pagination, aggregation of already compatible
predictions, and CSV export operations complete without network access.

### 7.2 Ephemeral inference boundary

The public seed contains no editorial content. User-saved title/body can support
later local inference, but only after an earlier request explicitly used
`content_retention=save_local`. Authors and raw HTML are always ephemeral.

### 7.3 Network-assisted inference

Network access occurs when no reusable run or saved body can satisfy the
request, when `prediction_action=recompute`, when content is explicitly saved
but not yet present, or when publisher discovery is required. Each job records
attempted/final URLs, outcome, and network use. Unless `save_local` was explicit,
extracted title/body are discarded before the terminal state commits. Authors
and raw HTML are always discarded.

### 7.4 Strict offline mode

`--offline` and `PRT_OFFLINE=true` install a deny-all application HTTP transport
before any service/model code loads. All internal clients use that transport;
model loaders are local-files-only. A network-dependent job fails with
`NETWORK_REQUIRED`; it never silently switches to a partial or different input.

## 8. Evaluation workflows

Every request carries two independent controls:

- `prediction_action`: `reuse` (default) or `recompute`;
- `content_retention`: `discard` (default) or `save_local`.

`reuse` selects the latest reusable exact-model run by
`inference_completed_at` descending then `prediction_run_id` ascending, using
the CSV contract's imported-run fallback. If none exists, it infers from validated
user-saved text when available, otherwise retrieves the page. `recompute`
always retrieves the current page and creates a new immutable run, even when a
run or saved body exists. `save_local` stores only the extracted title and body;
it never changes run selection. When combined with reuse of an existing run, it
fetches only if local content is absent and does not run inference.

`discard` governs the current extraction only; it never deletes title/body
saved by an earlier request. Only the confirmed purge workflow deletes saved
content. `save_local` replaces older saved title/body with the newly validated
extraction when they differ; an identical extraction creates no redundant
article version.

Every recomputation or missing-run inference creates a new
`prediction_run_id`; no run is overwritten. Existing publisher evaluations keep
references to the exact runs originally aggregated.

Evaluation selectors list `compatible` runnable models and non-runnable
`historical_only`/`artifact_missing` identities separately. A non-runnable
model can reuse/aggregate stored runs and add title/body to an article whose run
is found, but cannot create a missing run or recompute. If any required article
lacks that exact output after canonical resolution, the job fails
`MODEL_NOT_RUNNABLE` before extraction/content saving for that article and
suggests provisioning/relinking the exact identity; it never attributes a
stored prediction to a different local checksum.

A publisher request using a non-runnable model accepts only
`discovery_mode=stored_only`; the UI disables `stored_first` and `web_only`, and
the API rejects either with `MODEL_NOT_RUNNABLE` before job creation. Because
`stored_only` itself requires `reuse + discard`, content enrichment for
stored runs is done through single article, explicit article list, or stored
selection instead. Those modes remain allowed because every URL can be checked
for an existing historical output without assuming discovery.

### WF-001 — Evaluate one article

1. The user submits one HTTP(S) article URL, one model, `prediction_action`, and
   `content_retention`.
2. The application performs offline URL normalization and checks for the
   article, latest compatible run, and optional saved local content.
3. `reuse + discard` returns an existing run with zero network access. If no run
   exists, it infers from saved validated body or retrieves the page.
4. `reuse + save_local` returns the existing run and, only when content is not
   already saved, retrieves/validates the page and commits title/body without
   inference. That content-only retrieval is pinned to the run's article: if
   redirect/canonical resolution produces another article identity, saving
   fails `CANONICAL_IDENTITY_CHANGED` and the reused run remains intact. With
   no run it performs normal missing-run inference and saves the same
   extraction under its resolved identity.
5. `recompute` requires a runnable model, retrieves and validates the current
   page, and creates a new run. `save_local` additionally commits the current
   title/body; `discard` does not retain the fresh extraction and leaves any
   earlier saved content unchanged.
6. Content saving and run selection/creation are independent, durable
   subresults. An article satisfies the request only when a run is available
   and, for `save_local`, its validated content is saved. If either requested
   subresult fails, that article fails, but an already committed counterpart is
   retained and reported; for example, saved content survives a later inference
   failure and a pre-existing reused run remains valid after a save failure.
7. The response shows the selected/created run ID, class, five probabilities,
   model identity, content-saved state, network-use flag, and warnings.

Authors and raw HTML never cross the in-memory boundary. Title/body cross it
only under explicit `save_local`; they are available through the dedicated
local-content UI/API and excluded from normal article/job responses and exports.

No publisher aggregation is created for a single-article request.

### WF-002 — Evaluate explicit articles

1. The user submits 2–50 distinct HTTP(S) URLs, one model, one aggregation
   method, `prediction_action`, and `content_retention`; the controls apply to
   every URL.
2. If offline-normalized submitted hostnames do not resolve to one publisher,
   the request is rejected before job creation with `MIXED_PUBLISHERS`.
3. Each URL follows WF-001 lookup and acquisition rules.
4. After canonical resolution, every accepted URL must have the same normalized
   publisher hostname. If any differs, the complete job fails with
   `MIXED_PUBLISHERS`; no publisher evaluation is committed.
5. Per-article run successes already completed before a later failure remain
   valid article outputs and are explicitly reported; they are not
   presented as a completed publisher evaluation.
6. When all requested articles succeed, the selected aggregation is computed
   and committed with exact ordered article and prediction-run identifiers.

Duplicate submitted URLs after normalization are rejected with
`DUPLICATE_URL_INPUT` before any job starts.

### WF-003 — Evaluate one publisher

1. The user submits one HTTP(S) publisher homepage URL, requested count `2..50`
   (default `10`), one model, one aggregation method, discovery mode,
   `allow_partial`, `prediction_action`, and `content_retention`.
2. The submitted seed is stored only as `homepage_candidate_url`. It becomes
   `homepage_resolved_url` only after a successful same-publisher fetch whose
   final normalized URL has path `/` and no query; a section/query candidate is
   never asserted as the publisher homepage.
3. The normalized publisher hostname is resolved.
4. `stored_only` selects only eligible stored articles and never accesses the
   network; it accepts only `reuse + discard`. `stored_first` first reuses
   suitable stored runs, then retrieves known same-publisher URLs lacking a
   suitable run, and only
   then discovers new URLs for the remaining count. `web_only` ignores all
   stored URLs for candidate selection and performs web discovery.
5. Both reusable and retrieval-required stored URL groups are ordered by
   `first_seen_at` descending and canonical URL ascending. Discovered candidates
   are normalized, deduplicated, restricted to the publisher hostname, and
   ordered by canonical URL ascending.
6. Candidates are processed sequentially within this job until the requested
   number satisfies both the
   prediction and requested retention controls or no
   candidates remain. Rejected, failed, reused, recomputed, inferred,
   content-saved, and used counts are shown.
7. If fewer than two articles succeed, the job fails with
   `INSUFFICIENT_ARTICLES` and no publisher evaluation is committed.
8. If 2..requested-count articles succeed and `allow_partial=false`, the job
   fails with `REQUESTED_COUNT_UNMET`. If `allow_partial=true`, it succeeds with
   `partial=true`, an explicit warning, and both requested and used counts.
9. Aggregation is committed using only successful compatible predictions.

The UI defaults to count `10`, `stored_first`, and `allow_partial=true`. The API
requires all three values explicitly so automated clients never inherit a
hidden discovery/partial/count default.

A stored article is reusable only when its latest exact selected-model run
satisfies the aggregation method. A run missing probabilities is ineligible for
`mean_probabilities` and is not converted. `stored_only` skips every other
article. With `reuse`, `stored_first` exhausts reusable runs, then infers from
saved local bodies, then retrieves known URLs, then discovers. With `recompute`,
it ignores prior runs/saved bodies and freshly retrieves each chosen URL.

### WF-004 — Re-evaluate stored publisher articles

From a publisher detail page, the user selects 2–50 stored articles, a model,
an aggregation method, and the two controls. The application follows WF-002 and
never discovers additional articles. The UI disables selection of articles
whose publisher identity differs from the current page.

### WF-005 — Import a dataset

1. The user selects one `.csv`, `.csv.gz`, a directory containing
   `manifest.json` and listed CSV parts, or a `.zip` containing either exactly
   one CSV or one top-level manifest plus exactly its listed CSV parts.
2. The browser streams the source. The backend enforces byte/free-space limits,
   computes a transport SHA-256 while writing a private mode-`0600` spool,
   fsyncs it, and atomically renames it. Only then does it commit and return a
   `dataset_import` job. Failed acquisition creates no job.
3. Only allowlisted fields are projected. Protected columns are named in a
   warning but their values are neither logged nor persisted. Source `title`,
   `text`, and `authors` values are discarded unconditionally; their
   compatibility columns remain empty.
4. The format-independent content digest, optional transport checksum, row
   counts, accepted rows, rejected rows, duplicate
   conflicts, and warnings are committed to `imports.csv`.
   Each rejected data row also creates a safe, value-minimized entry in
   `import_rejections.csv` containing logical source part/data-record number and
   stable error code.
5. Reimporting the same content digest and schema version is idempotent.
6. The source is never modified.

Parsing writes projected, non-authoritative staging ledgers without holding the
CSV writer mutex or exposing rows. Whole-input duplicate/conflict validation
finishes before a short final transaction commits all accepted rows, rejection
records, and the import summary. A conflict found late therefore excludes the
staged pair before either prediction run is authoritative. The acquired upload
and staging files are deleted immediately after the terminal transaction; a
crash may leave them only for the documented recovery/retry policy.

An import with both accepted and rejected rows finishes
`succeeded_with_rejections`; accepted rows commit atomically with the import
summary and safe rejection records. A structurally unreadable import or one
with zero acceptable rows is `failed` and commits no article or prediction.

Within one import, duplicate canonical URLs can merge non-conflicting outputs
from distinct model identities. A different output for the same article/model
identity marks that key conflicted: every occurrence for that key is rejected,
reported, and produces no prediction run. For simple row counters/provenance,
each source row containing a conflicted key is rejected in full; its otherwise
non-conflicting outputs do not commit. Editorial source differences
are discarded before comparison and cannot create a conflict. A later import
with a different content digest creates separate imported runs. The
first-occurrence metadata policy applies only to the already generated bundled
release.
Import rejection details remain available after restart through the UI and API.

### WF-006 — Register a model

The user scans configured model roots or uploads one file/archive. Scan directly
registers recognized official identities; free-form server paths are never
accepted by the API. Generic custom manifests are outside the MVP.
Uploads are streamed into the configured data directory and validated before
registration. Directory artifacts are uploaded as `.zip` or `.tar.gz`. A model
does not become selectable until family, fold, artifact checksum, loader recipe,
base/tokenizer dependencies, class count, and runtime compatibility pass.

### WF-007 — Clear saved local content

From article detail, the user confirms the canonical URL and starts a
`content_purge` job. It takes exclusive maintenance access, temporarily rejects
affected reads and all mutations, rewrites every live `articles.csv` version,
fsyncs and swaps the file, rebuilds indexes, and appends a purge audit row
before service resumes. Prediction runs and evaluations remain unchanged. No
backup is rewritten automatically; the UI requires acknowledgement that all
backups and external copies containing the content need manual deletion.

## 9. Aggregation controls

The exact method identifiers are:

- `majority_vote` — always available for two or more compatible hard classes;
- `ordinal_mean` — always available for two or more compatible hard classes;
- `mean_probabilities` — available only when every included prediction has a
  complete valid five-class vector.

The frontend explains disabled methods inline. It never substitutes one method
for another. Detailed formulas and deterministic tie rules are defined only in
`scientific-contract.md`.

## 10. Frontend information architecture

The frontend uses seven top-level destinations:

| Route | Purpose |
| --- | --- |
| `/` | Dashboard: health, offline state, dataset/model status, active jobs, recent evaluations |
| `/evaluate` | Single article, article list, and publisher evaluation forms |
| `/articles` | Searchable and paginated article history |
| `/publishers` | Searchable and paginated publisher history |
| `/imports` | Dataset import by upload, history, counters, warnings, and rejection reports |
| `/models` | Model compatibility, registration, upload, OSF instructions |
| `/jobs` | Active and completed job history, progress, warnings, and errors |

### 10.1 Minimal design rules

- One primary action per page section.
- Visible text labels accompany icons.
- No decorative animation, auto-playing content, hidden gestures, or CDN asset.
- Desktop content width is capped for readability; tables scroll horizontally
  on narrow screens.
- Every asynchronous action immediately shows its job and progress.
- Destructive actions require confirmation naming the target.
- Empty, loading, offline, error, partial, and no-model states have dedicated
  English copy and a corrective action.
- Color never carries meaning alone; text and symbols accompany status colors.
- Keyboard navigation, visible focus, semantic headings, form labels, and data
  tables meet WCAG 2.2 AA behavior.

### 10.2 Articles page

Filters: canonical-URL search, publisher hostname, model identity, predicted
class, origin, and updated date. Columns: canonical URL, publisher, available
model count, most recent prediction, origin, and updated time. Default ordering
is updated time descending then canonical URL ascending.

Article detail shows URL/publisher and acquisition provenance, every
model-specific immutable run, five exact probability values and bar chart when
available, checkpoint/fold identity, job provenance, content-saved state, and
scientific warning. Saved title/body are hidden behind `View local content` and
served from a dedicated endpoint; author/raw HTML never appear. `Clear local
content` requires confirmation and starts a physical purge job.
The local-content view renders title/body strictly as text with normal React
escaping; it never injects saved content as HTML or executes detected links.

### 10.3 Publishers page

Filters: hostname, available article count, evaluated model, and
evaluation date. Publisher detail shows stored articles with selection controls,
previous evaluations, requested/used counts, aggregation method and version,
class distribution, exact contributing predictions, and accessible charts.

### 10.4 Evaluate page

Three tabs correspond exactly to the three input modes. Switching tabs clears
mode-specific validation but preserves the selected model. The submit button is
disabled until client validation passes; the server repeats every validation.

- **Single article:** one URL and one model; no aggregation control is shown.
- **Article list:** a textarea with exactly one URL per non-empty line, live
  distinct-count `2..50`, one model, and one aggregation selector defaulting to
  `majority_vote`.
- **Publisher:** one publisher seed URL, numeric requested count `2..50`
  defaulting to `10`, one model, one aggregation selector defaulting to
  `majority_vote`, discovery-mode radio group defaulting to `stored_first`, and
  `Allow fewer articles` enabled by default.

No model is silently selected; the user chooses one explicit runnable or
historical identity before submit.

Every tab shows a `Prediction` choice (`Reuse existing when available`, default;
`Recompute from current page`) and an unchecked `Save extracted title and body
locally` checkbox. The checkbox explains that content stays in ignored local
CSV, can be viewed through this instance, is excluded from normal exports, and
may be subject to publisher rights.

Before submission the UI calls evaluation preflight. For each known article it
shows whether a compatible run and saved content exist. When a compatible run
exists, a confirmation dialog offers exactly: reuse it; recompute; optionally
save title/body. These map directly to the two controls and never create a
third implicit behavior. An unknown/missing-run article displays the expected
network requirement instead of an existing-result prompt.

For a non-runnable selection, `Recompute` is disabled with model setup
guidance. `Save extracted title and body locally` remains available for an
explicit article that has a reusable historical run; it is disabled in the
historical publisher form because that form is constrained to
`stored_only + reuse + discard`.

The model selector separates runnable and non-runnable stored-output entries and displays
family, fold, shortened model ID, and status. Aggregation choices show their
formula summary and disabled reason. Before submission the page states whether
the selected operation can require network access; strict offline mode never
offers a control that claims to enable it.

### 10.5 Charts

Charts are limited to probability bars, article-class counts, mean-probability
bars, and model/aggregation comparison bars. Every chart has an adjacent table
using the exact same API values and an accessible text summary.

## 11. Search, pagination, and export

- Default page size: 25; allowed sizes: 25, 50, 100; maximum 100.
- API pagination is cursor-based and stable under new inserts.
- Text search applies Unicode NFC normalization and Python `str.casefold()` to
  both query and explicitly documented fields, then performs substring
  matching; it is not fuzzy or locale-dependent search.
- Filters combine with logical AND; multiple values within one filter combine
  with OR.
- CSV export streams the complete filtered result. The response supplies an
  `X-Exported-At` UTC timestamp; the effective filters are the request query
  parameters and are not persisted as database state. Protected fields and
  full model paths are excluded.

## 12. Job behavior

The exhaustive persisted job types are `article_evaluation`,
`article_list_evaluation`, `publisher_evaluation`, `dataset_import`,
`model_scan`, `model_upload`, `model_validate`, and `content_purge`. CLI dataset
import may create `dataset_import`; storage verify/compaction are synchronous
offline CLI operations and never job types.

Job states are `queued`, `running`, `succeeded`, `failed`, and `cancelled`.
Progress is an integer `0..100`. The exhaustive phase identifiers are
`queued`, `validating`, `scanning`, `resolving_local`, `discovering`,
`retrieving`, `extracting`, `language_check`, `loading_model`, `inferring`,
`aggregating`, `importing`, `purging_content`, `verifying`, `committing`,
`cancelling`, `completed`, `failed`, and `cancelled`. Jobs use only applicable
phases. Article jobs follow local resolution, optional retrieval/extraction/
language validation, optional model loading/inference, and commit. List and
publisher jobs repeat that candidate sequence; publisher discovery may occur
between candidate attempts. Once `aggregating` starts, no candidate phase may
reappear. Import jobs use `importing -> verifying -> committing`; model jobs use
`scanning` or validation/loading as applicable. Compaction is not a job and
reports progress only on the offline CLI. Content purge uses
`purging_content -> verifying -> committing`. A cancellation request switches
to `cancelling` at the next safe boundary. Terminal phases are `completed` for
`succeeded`, `failed` for `failed`, and `cancelled` for `cancelled`. Queued jobs
have progress `0`, successful completed jobs have `100`,
and progress never decreases within one job even when a candidate phase
reappears. Failed/cancelled jobs retain their last percentage. A completed
publisher evaluation is visible only after its transaction commits.
Cancellation is cooperative: committed article runs and explicit content saves
remain valid, but no publisher evaluation is created unless aggregation
committed before cancellation.

Allowed status transitions are `queued -> running`, `queued -> cancelled`, and
`running -> succeeded|failed|cancelled`; terminal status never changes. A
running cancellation request sets phase `cancelling` until the job reaches a
safe boundary.

At most one GPU inference job and four network/extraction jobs run concurrently.
CPU-only inference concurrency is exactly one in the MVP. CSV commits are
serialized. Candidates within one publisher job are sequential; network lanes
serve different jobs. At most `PRT_JOB_QUEUE_MAX` jobs are `queued` (default
`100`); overflow creates no job and returns `JOB_QUEUE_FULL`.

On shutdown, accepting and dequeuing stop immediately. A safe boundary is
before or after one network call, one candidate, one inference, or one complete
CSV transaction—never inside a transaction. Workers have 30 seconds to reach a
boundary. At the deadline the process exits after any in-progress CSV
transaction finishes; noncommitting retrieval/inference may be terminated. On
restart, `queued` jobs are requeued and persisted `running` jobs become failed
with `PROCESS_INTERRUPTED`; no running job is resumed.

Retry creates a linked job only from reproducible input. Evaluation and model
scan/validate jobs are retryable. Upload jobs are
retryable only while their acquired spool exists. After terminal cleanup the
job exposes `retry_available=false`; retry returns `SOURCE_NOT_AVAILABLE` and
the user must upload again.

## 13. Stable error behavior

`api-contract.md` section 3 is the single exhaustive definition and synchronous
HTTP mapping of every stable error code. Reading an accepted job remains HTTP
`200`; a terminal job embeds one of those codes in its `error` field.
Implementations shall not create a second registry or invent an unversioned
stable code.

Errors never include protected source values, editorial content, access tokens,
credentials, or full stack traces. Debug traces remain in local logs only when
debug logging is explicitly enabled and are still content/secret-redacted.

## 14. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-001 | The native CLI and Docker Compose shall start the same single-user application contract. |
| FR-002 | The application shall expose the frontend, REST API, OpenAPI document, and health endpoint from one origin. |
| FR-003 | Every MVP publication shall be loopback-only and validate Host/Origin on the documented boundary. |
| FR-004 | Every authoritative mutable record shall be persisted in the versioned CSV store. |
| FR-005 | The bundled manifest release shall be verified and imported idempotently. |
| FR-006 | Protected reference-provider fields shall never cross the import projection boundary. |
| FR-007 | Browsing, filtering, export, and aggregation of stored compatible predictions shall work offline. |
| FR-008 | `reuse` shall select the latest compatible immutable run without network when one exists. |
| FR-009 | Title/body retention shall require explicit `save_local`; default discard, authors/raw HTML shall never enter authoritative state, and purge shall blank live state while backups require manual deletion. |
| FR-010 | Missing-run inference may use user-saved validated text; otherwise it requires network, while `recompute` always requires fresh retrieval. |
| FR-011 | The three evaluation input modes and their limits shall be identical in UI and API. |
| FR-012 | Mixed-publisher explicit lists shall never create a publisher evaluation. |
| FR-013 | Publisher discovery shall expose requested, considered, rejected, failed, reused, recomputed, inferred, content-saved, and used counts. |
| FR-014 | Every publisher result shall record exact ordered article and immutable prediction-run identities. |
| FR-015 | Aggregation methods shall follow the scientific formulas and availability rules exactly. |
| FR-016 | Every new successful run shall contain one class and five finite probabilities summing to one within tolerance. |
| FR-017 | Missing historical probabilities shall remain missing and display as `Not available`. |
| FR-018 | Exact model identity shall include every scientific setting and immutable dependency revision but no filesystem locator; artifact loss shall not invalidate historical runs. |
| FR-019 | Unsupported or ambiguous models shall fail closed without executing artifact code. |
| FR-020 | New article inference shall use unchanged `newspaper3k` text after deterministic English validation. |
| FR-021 | Long operations shall be inspectable and cancellable background jobs. |
| FR-022 | CSV writes shall be serialized, transaction-marked, flushed, and recoverable after interruption. |
| FR-023 | API list endpoints shall use stable cursor pagination and bounded page sizes. |
| FR-024 | Frontend charts shall have exact accessible table equivalents. |
| FR-025 | Strict offline mode shall prevent all application-initiated outbound HTTP requests. |
| FR-026 | Loopback requests shall resist DNS rebinding through exact Host validation and same-origin browser mutation checks. |
| FR-027 | Upload acquisition and staged import shall be bounded, crash-safe, atomic, and idempotent by content digest plus schema version. |
| FR-028 | Native and container deployments shall pass the same acceptance suite. |
| FR-029 | Idempotency keys shall survive restart and compaction through a documented CSV ledger. |
| FR-030 | The job queue shall be bounded and restart/retry behavior shall depend only on persisted state and source availability. |
| FR-031 | Compaction, live-state purge, uploads, and backups shall enforce deterministic recovery, retention, and free-space rules. |

## 15. Non-functional requirements

| ID | Requirement |
| --- | --- |
| NFR-001 | With 100,000 articles and 400,000 predictions on reference hardware, a filtered first page shall return within 2 seconds after indexes load. |
| NFR-002 | Startup shall stream seed import, verify tracked editorial fields are empty, and keep opt-in runtime content only under the ignored data directory. |
| NFR-003 | Frontend interaction shall remain responsive while jobs run. |
| NFR-004 | Graceful shutdown shall stop accepting jobs, wait 30 seconds for documented safe boundaries, never interrupt a CSV commit, and let restart fail persisted running jobs as interrupted. |
| NFR-005 | Every persisted timestamp shall be UTC RFC 3339 and every identifier format shall follow the CSV contract. |
| NFR-006 | The image and frontend shall contain no model weights, base models, remote fonts, analytics, or CDN dependency. |
| NFR-007 | Logs shall rotate locally and exclude secrets and editorial content at every level. |
| NFR-008 | API and frontend shall use one shared validation/service implementation. |
| NFR-009 | All user-visible text, API error messages, and generated exports shall be English. |
| NFR-010 | The repository shall provide reproducible dependency lock files and deterministic dataset verification. |

## 16. Release gate

The application is not an MVP release until every applicable CPU-gate
acceptance test passes (hardware-specific tests report separately),
OpenAPI matches the API contract, CSV verification survives forced interruption
tests, native and Compose behavior match, and a clean offline run can browse and
aggregate the bundled history without any outbound connection.
