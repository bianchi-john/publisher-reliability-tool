# REST API Contract

**Status:** Normative MVP API  
**Base path:** `/api/v1`  
**Media type:** `application/json` unless stated otherwise

## 1. General rules

- JSON is UTF-8 and uses snake_case field names.
- Unknown request fields are rejected.
- Missing optional values are `null`; response fields are not omitted based on
  value except where an endpoint explicitly defines a union.
- URL request strings are at most 8,192 UTF-8 bytes.
- Timestamps are UTC RFC 3339 strings ending in `Z`.
- IDs follow `csv-storage-contract.md`.
- API versioning occurs in the path. Breaking changes require `/api/v2`.
- `X-Request-ID` accepts a client UUID; otherwise the server creates one. Every
  response returns it.
- Every job/resource-creating POST requires `Idempotency-Key`, 8–128 visible
  ASCII characters: content purge; model scan/upload/validate;
  evaluation jobs/stored selection; job retry; and import upload. Missing is a
  `422` field error. Cancel and read-only POST preflight/availability accept no
  key and follow their documented current-state semantics. Scope is API
  version, method, normalized route template, and canonical path-parameter IDs
  for member routes. JSON hashes use RFC 8785
  JCS after schema defaults; upload hashes use canonical form fields plus each
  acquired file's transport SHA-256 and length. The persistent CSV ledger
  retains keys for 30 days across restart/compaction. Same scope/key/hash
  returns the original resource before current-state/queue/source checks;
  another hash returns `IDEMPOTENCY_CONFLICT`.
- Requests larger than 1 MiB are rejected except documented streaming uploads.
- Responses set `Cache-Control: no-store` unless serving fingerprinted assets.
- Every `q` filter applies Unicode NFC normalization followed by Python
  `str.casefold()` to query and documented target, then substring matching.
  Filters combine with AND; repeated values of one filter combine with OR.
- Normal resources, jobs, lists, exports, and errors never return a title,
  article body, author value, raw HTML, or snippet. The sole exception is the
  dedicated local-content read endpoint in section 6, which returns only a
  title/body that this user explicitly chose to save. Authors and raw HTML are
  never returned or persisted under any option.
- Every member route validates its path ID before performing work. An absent
  article, publisher, prediction run, evaluation, model, job, or import returns
  the corresponding section-3 `*_NOT_FOUND` code. A job-creating route also
  validates referenced persisted IDs synchronously before admission, except
  URL identities that can only be established by the accepted background job.

OpenAPI is served at `/api/openapi.json`; local interactive documentation is at
`/api/docs`.

## 2. Loopback request security

Authentication and non-loopback service are outside the MVP. Middleware checks
every request's `Host`/absolute-form authority against the single configured loopback
origin; mismatch returns `421 INVALID_HOST`. Browser mutations with a present
`Origin` require its exact scheme/host/port, and `Sec-Fetch-Site: cross-site` is
rejected with `403 ORIGIN_NOT_ALLOWED`. Missing `Origin` is accepted for
non-browser clients. No CORS allow-origin header is emitted.

## 3. Error envelope

Every non-2xx JSON error uses:

```json
{
  "error": {
    "code": "INVALID_URL",
    "message": "The submitted value is not a valid HTTP or HTTPS URL.",
    "details": {},
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

- `code` is stable and machine-readable.
- `message` is safe English display text.
- `details` contains field names, safe limits, IDs, or counters only.
- Validation errors return `422` with `details.fields`, a map from request field
  to a list of messages.
- Unhandled failures return `500 INTERNAL_ERROR` without a stack trace.

This is the single exhaustive code registry for API version 1. The status is
normative whenever a code is returned synchronously. A job accepted with `202`
is subsequently read with `200` even when terminal; its `error.code` contains
the domain code and does not change the job-read HTTP status.

| Code | HTTP status | Meaning |
| --- | ---: | --- |
| `INVALID_CURSOR` | 400 | Cursor is malformed or does not match the filters |
| `INVALID_HOST` | 421 | Host/absolute authority is not the configured loopback origin |
| `ORIGIN_NOT_ALLOWED` | 403 | Browser mutation is cross-origin |
| `INVALID_URL` | 422 | URL syntax/encoding is invalid |
| `UNSUPPORTED_SCHEME` | 422 | URL is not HTTP(S) |
| `CANONICAL_IDENTITY_CHANGED` | 409 | Content-only fetch resolved to another article |
| `DUPLICATE_URL_INPUT` | 422 | Input URLs collide after normalization |
| `MIXED_PUBLISHERS` | 422 | Explicit selection spans publisher identities |
| `ARTICLE_NOT_FOUND` | 404 | Article ID is absent |
| `PUBLISHER_NOT_FOUND` | 404 | Publisher ID is absent |
| `PREDICTION_RUN_NOT_FOUND` | 404 | Prediction-run ID is absent |
| `ARTICLE_CONTENT_NOT_FOUND` | 404 | Article exists but has no saved local content |
| `EVALUATION_NOT_FOUND` | 404 | Evaluation ID is absent |
| `MODEL_NOT_FOUND` | 404 | Model ID is absent |
| `JOB_NOT_FOUND` | 404 | Job ID is absent |
| `IMPORT_NOT_FOUND` | 404 | Import ID is absent |
| `IDEMPOTENCY_CONFLICT` | 409 | One key was reused with a different request body |
| `JOB_NOT_CANCELLABLE` | 409 | Job is already terminal |
| `SOURCE_NOT_AVAILABLE` | 409 | Retry requires an acquired source that no longer exists |
| `JOB_QUEUE_FULL` | 503 | Persisted queued-job limit is reached |
| `PAYLOAD_TOO_LARGE` | 413 | Request or upload exceeds its configured byte limit |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Body or archive type is not accepted |
| `RATE_LIMITED` | 429 | Local client exceeded a documented rate limit |
| `NETWORK_REQUIRED` | 409 | Operation cannot complete in strict offline/local state |
| `NETWORK_TIMEOUT` | 504 | Synchronous network operation timed out |
| `ROBOTS_DENIED` | 403 | Robots policy denies retrieval |
| `HTTP_ERROR` | 502 | Upstream HTTP retrieval failed |
| `CONTENT_TOO_LARGE` | 413 | Decompressed page/field exceeds its limit |
| `EXTRACTION_FAILED` | 422 | Article extraction failed |
| `TEXT_EMPTY` | 422 | Extracted text is empty |
| `TEXT_TOO_SHORT` | 422 | Text misses deterministic length limits |
| `LANGUAGE_DETECTION_FAILED` | 422 | Detector could not classify frozen input |
| `NON_ENGLISH` | 422 | Detected language is not English |
| `MODEL_NOT_RUNNABLE` | 409 | Historical/missing artifact cannot infer |
| `MODEL_INCOMPATIBLE` | 422 | Artifact/manifest violates a supported recipe |
| `MODEL_DEPENDENCY_MISSING` | 409 | Immutable base/tokenizer/runtime is absent |
| `MODEL_RESOURCE_INSUFFICIENT` | 409 | Required device/memory is unavailable |
| `PROBABILITIES_REQUIRED` | 409 | Selected runs cannot support probability mean |
| `INSUFFICIENT_ARTICLES` | 422 | Fewer than two compatible runs are available |
| `REQUESTED_COUNT_UNMET` | 422 | Partial result is forbidden and count is unmet |
| `IMPORT_SCHEMA_INVALID` | 422 | Dataset structure/schema is invalid |
| `IMPORT_CONFLICT` | 409 | One import contains conflicting article/model output |
| `PROCESS_INTERRUPTED` | 409 | Persisted running job was interrupted by restart |
| `STORAGE_LOCKED` | 409 | Another process owns the writer lock |
| `STORAGE_CORRUPT` | 503 | Committed state fails verification |
| `STORAGE_SPACE_INSUFFICIENT` | 507 | Required acquisition/maintenance headroom is absent |
| `SERVICE_UNAVAILABLE` | 503 | Exclusive maintenance temporarily blocks operation |
| `INTERNAL_ERROR` | 500 | Unexpected failure hidden behind a safe message |
| `SERVICE_NOT_READY` | 503 | Startup/recovery is incomplete or storage unavailable |

## 4. Pagination

List endpoints accept:

- `limit`: `25`, `50`, or `100`; default `25`;
- `cursor`: opaque cursor returned by the preceding page.

Response shape:

```json
{
  "items": [],
  "page": {
    "limit": 25,
    "next_cursor": null,
    "has_more": false
  }
}
```

Cursors encode the endpoint, normalized filters, last sort tuple, storage
schema version, and the maximum `commit_sequence` visible on the first page;
they are authenticated with a process secret. Every subsequent page resolves
record versions at that commit watermark, so concurrent inserts, updates, and
deletes do not change membership or ordering. A cursor used after process
restart, with changed filters, or against another endpoint returns
`400 INVALID_CURSOR`.

## 5. Health and status

### `GET /health/live`

Outside `/api/v1`. Returns `200 {"status":"alive"}` whenever the process event
loop is responsive. It does not imply storage readiness.

### `GET /health/ready`

Outside `/api/v1`. Returns `200 {"status":"ready"}` after CSV verification,
index build, and executor startup, provided exclusive maintenance is not active.
During exclusive maintenance it returns
`503 {"status":"not_ready","reason":"maintenance"}`; this health response is
outside the API error envelope.
It does not inspect hypothetical future URLs, saved bodies, models, or network
availability; those belong to per-request preflight. Startup storage corruption
starts no HTTP server at all.

### `GET /api/v1/status`

Returns application version, storage schema version, offline flag, bind safety,
seed import status, counts, model-state counts, active jobs, and whether network
operations are permitted. It contains no full filesystem paths.

## 6. Articles

### `GET /api/v1/articles`

Filters:

- `q`: case-insensitive substring over canonical URL;
- `publisher`: exact normalized hostname;
- `model_id`: exact model ID with at least one prediction run;
- `predicted_class`: integer `0..4` paired with `model_id`;
- `origin`: `bundled_import`, `user_import`, or `local_inference`;
- `updated_from`, `updated_to`: inclusive RFC 3339 bounds;
- `sort`: `updated_desc` (default) or `url_asc`.

Each summary returns article ID, canonical URL, publisher summary, available
model count, prediction-run count, most recent run summary, `content_saved`
boolean, first/last seen timestamps, and network-use flag. It never embeds a
title, author, body, or snippet. Its `updated_at` is the later of the current
article version's `recorded_at` and every prediction run's `recorded_at`; this value
drives `updated_*` filters and `updated_desc` sorting.

`available_model_count` counts distinct model IDs and `prediction_run_count`
counts all immutable runs. “Most recent” uses effective completion time
descending (`inference_completed_at`, or `recorded_at` for an imported run),
then `prediction_run_id` ascending. `predicted_class` filtering applies to the
latest reusable run for the required `model_id`; `origin` matches when at least
one run has that origin.

### `GET /api/v1/articles/{article_id}`

Returns URL/publisher and acquisition metadata plus bounded run summaries
grouped by model. Each summary contains prediction-run ID, class, nullable
five-probability vector, origin, action, input source, retention choice, model
summary, job/import ID, and timestamps. The default embedded history is the 20
newest runs; `prediction_run_count` and the paginated endpoint expose the rest.
It returns `content_saved` and `content_saved_at` but never embeds the content.

Returns `404 ARTICLE_NOT_FOUND` when absent.

### `GET /api/v1/articles/{article_id}/prediction-runs`

Paginated immutable run list. Supports `model_id`, `family`, `origin`, and
`action` filters; default order is effective completion time descending under
the imported-run fallback above, then `prediction_run_id` ascending.

### `GET /api/v1/prediction-runs/{prediction_run_id}`

Returns one immutable run, its safe article/model summaries, and complete
provenance fields. It returns `404 PREDICTION_RUN_NOT_FOUND` when absent and
never embeds saved or ephemeral article content.

### `GET /api/v1/articles/{article_id}/content`

Returns only locally saved content:

```json
{
  "article_id": "uuid",
  "canonical_url": "https://publisher.example/article",
  "title": "Locally saved title or an empty string",
  "text": "Locally saved validated article body",
  "content_saved_at": "2026-07-21T14:05:12.123456Z",
  "rights_notice": "Saved source content remains subject to third-party rights."
}
```

This endpoint is never included by another resource or bulk operation and
always sets `Cache-Control: no-store`. It returns `ARTICLE_CONTENT_NOT_FOUND`
when the article exists without saved content.

### `POST /api/v1/articles/{article_id}/content-purge-jobs`

Starts the physical purge defined by the CSV contract. Body:

```json
{
  "confirm_canonical_url": "https://publisher.example/article"
}
```

The confirmation value must exactly equal the stored canonical URL. The call
requires `Idempotency-Key` and returns `202` with a `content_purge` job. A
successful job removes title/body from every live CSV version, rebuilds indexes,
and records `backup_policy=manual_deletion_required` without deleting runs or
evaluations. Application-created and external backups are not changed. A
mismatched confirmation is `422`; an article with no saved content is
`404 ARTICLE_CONTENT_NOT_FOUND` and creates no job. Repeating the original
successful request/key still returns its original job after content is gone.

### `GET /api/v1/articles/export`

Streams `text/csv` and accepts the list filters. `include_text` is not a valid
parameter. Maximum unpaginated result is the complete filtered collection. The
response includes `X-Exported-At` in the storage contract's UTC timestamp
format and a safe `Content-Disposition` filename. Header order is exact:

```text
article_id,canonical_url,publisher_id,normalized_hostname,available_model_count,prediction_run_count,latest_prediction_run_id,latest_model_id,latest_predicted_class,latest_prob_class_0,latest_prob_class_1,latest_prob_class_2,latest_prob_class_3,latest_prob_class_4,latest_origin,content_saved,first_seen_at,last_seen_at,updated_at
```

The five probability fields are all empty when the latest run has no vector.
`content_saved` is metadata only; content itself is never exported.

## 7. Publishers

### `GET /api/v1/publishers`

Filters: `q` over normalized hostname, `article_count_min`,
`article_count_max`, `model_id`, `evaluated_from`, `evaluated_to`, and sort
`updated_desc` or `hostname_asc`. Count bounds are non-negative integers and
minimum cannot exceed maximum.

Each summary returns publisher ID, normalized hostname, nullable homepage
candidate/resolved URLs, stored
article count, prediction-run count, evaluation count, and last
evaluation timestamp. Its `updated_at` is the maximum current `recorded_at`
across the publisher, its articles, their prediction runs, and its evaluations;
this value drives `updated_desc`.

### `GET /api/v1/publishers/{publisher_id}`

Returns publisher summary plus counts by model and class. It does not embed
unbounded articles or evaluations.

### `GET /api/v1/publishers/{publisher_id}/articles`

Uses standard pagination and article filters. Default order is `first_seen_at`
descending then canonical URL ascending. This is also the stored-candidate
ordering used for publisher evaluation.

### `GET /api/v1/publishers/{publisher_id}/evaluations`

Filters by `model_id` and `method`; default order is creation time descending.

### `GET /api/v1/evaluations/{evaluation_id}`

Returns evaluation fields, exact ordered contributing
article/prediction-run summaries, class counts, nullable mean probabilities,
warnings, requested/used counts, partial flag, input/discovery mode, and
scientific warnings. Historical evaluations never retarget to a newer run.

### `GET /api/v1/publishers/export`

Streams filtered publisher summaries as CSV; editorial content is never
embedded. It uses the same `X-Exported-At` and `Content-Disposition` response
headers as article export. CSV header order is exact:

```text
publisher_id,normalized_hostname,homepage_candidate_url,homepage_resolved_url,stored_article_count,prediction_run_count,evaluation_count,last_evaluation_at,updated_at
```

## 8. Models

### `GET /api/v1/models`

Filters: `family`, `status`, and `q` over safe display name. Returns compatibility
state, `artifact_available`, `runnable`, fold, artifact kind, redacted locator,
checksum, official-manifest/recipe/base/tokenizer identity, class order, max
tokens, padding/runtime scientific options, registration/validation time, and
safe status detail.

### `GET /api/v1/models/{model_id}`

Returns the full safe model record and dependency/resource checks. It never
returns unrestricted absolute paths or secrets.

### `POST /api/v1/models/scan`

Body:

```json
{
  "recursive": true
}
```

All configured roots are scanned with the same no-symlink policy. Arbitrary
paths are not accepted. Returns `202` with a `model_scan` job. Each recognized
official artifact is registered directly under its scientific `model_id` and a
deployment-only locator; ambiguous/unknown artifacts are reported unsupported.
There is no separate path-based register endpoint.

### `POST /api/v1/models/upload`

Consumes `multipart/form-data` with:

- `file`: one `.pt`, `.safetensors`, `.zip`, or `.tar.gz` stream;
- `family`: required unless an official manifest entry is unambiguous;
- `fold_id`: optional integer;
- `expected_upload_sha256`: optional lowercase digest of the received file or
  archive bytes, checked before extraction; it is distinct from the normalized
  artifact digest used in model identity.

The server streams to `<data-dir>/uploads/models`, limits total bytes using
`PRT_MODEL_UPLOAD_MAX_BYTES` (default 10 GiB), rejects archive traversal/links,
checks free space, computes the transport hash, fsyncs, and atomically acquires
the spool before committing idempotency/job rows and returning `202`;
pre-acquisition failure creates neither. The worker then validates before an
atomic move to managed storage and deletes failed spools. A model archive has at most 10,000
entries and its total extracted regular-file bytes cannot exceed the upload
limit. Nested archives are treated as ordinary model files and are never
recursively extracted. Returns `202` with a `model_upload` job.

### `POST /api/v1/models/{model_id}/validate`

Revalidates artifact, dependencies, and resources. Returns `202` with a job.

Model deletion is outside the MVP. Missing artifacts become
`artifact_missing`, `artifact_available=false`, and `runnable=false`; the model
record and every historical run/evaluation remain queryable and aggregable.

## 9. Evaluation preflight and jobs

### `POST /api/v1/evaluation-preflight`

Accepts exactly one of the evaluation request bodies below and performs a
read-only, offline preflight. It normalizes URLs, inspects local articles,
saved-content state, model state, and reusable runs, but performs no DNS, HTTP,
extraction, inference, mutation, or job creation.

The response contains `eligible`, a nullable `blocking_error_code`, normalized
input summary, and one check per explicit article with:

- `article_id` or `null`;
- `reusable_prediction_run_id` or `null`;
- `content_saved`;
- `planned_operation`: `reuse_run`, `infer_saved_content`,
  `resolve_then_reuse_or_infer`, `resolve_then_reuse_or_fail`,
  `fetch_content_only`, or `recompute`;
- `network_required` and stable `network_reasons`.

For a publisher input it additionally returns local candidate counts by
reusable run, saved body, and known URL plus whether homepage discovery can be
required. It cannot enumerate undiscovered articles and does not promise that
retrieval or inference will succeed. The evaluation-job endpoint repeats all
validation against current state, so a preflight response is advisory and is
never an authorization token.

### `POST /api/v1/evaluation-jobs`

Creates one job from a discriminated request. Returns `202`:

```json
{
  "job_id": "uuid",
  "status": "queued",
  "links": {
    "self": "/api/v1/jobs/uuid",
    "events": "/api/v1/jobs/uuid/events"
  }
}
```

`model_id` can identify a runnable `compatible` model or a non-runnable
`historical_only`/`artifact_missing` identity with stored runs. Non-runnable
models reject `prediction_action=recompute`. A publisher input additionally requires
`stored_only + reuse + discard`. Single-article, explicit-list, and stored-
selection inputs may use `save_local` with a reusable historical run; this
performs content retrieval only, never inference. If an explicit URL lacks the
run after online canonical resolution, the accepted job terminates
`MODEL_NOT_RUNNABLE` before extracting/saving content for that URL.

Every request includes two independent controls:

- `prediction_action`: `reuse` or `recompute`; omitted means `reuse`;
- `content_retention`: `discard` or `save_local`; omitted means `discard`.

`reuse` selects the latest reusable run under the CSV ordering rule. If none
exists, a runnable model infers from saved validated text when available or
retrieves the page. `recompute` always retrieves the current page and creates a
new immutable run. `save_local` stores only validated title/body; it does not
change run selection. `discard` applies only to content acquired for this
request and never erases content already saved; erasure requires the dedicated
purge job. Defaults are deliberately network- and retention-minimal.

#### Single article request

```json
{
  "input": {
    "type": "article",
    "url": "https://publisher.example/article"
  },
  "model_id": "64-hex-model-id",
  "prediction_action": "reuse",
  "content_retention": "discard"
}
```

No aggregation field is accepted.

#### Explicit article-list request

```json
{
  "input": {
    "type": "article_list",
    "urls": [
      "https://publisher.example/a",
      "https://publisher.example/b"
    ]
  },
  "model_id": "64-hex-model-id",
  "aggregation_method": "majority_vote",
  "prediction_action": "reuse",
  "content_retention": "discard"
}
```

`urls` contains 2–50 distinct pre-normalization strings and must remain distinct
after normalization. `aggregation_method` is required; the API never inserts
the frontend's majority-vote default.

#### Publisher request

```json
{
  "input": {
    "type": "publisher",
    "url": "https://publisher.example/",
    "requested_article_count": 10,
    "discovery_mode": "stored_first",
    "allow_partial": true
  },
  "model_id": "64-hex-model-id",
  "aggregation_method": "majority_vote",
  "prediction_action": "reuse",
  "content_retention": "discard"
}
```

`requested_article_count` is `2..50`. API clients must send it together with
`aggregation_method`, `discovery_mode`, and `allow_partial`; omission is `422`.
`stored_only` additionally requires `prediction_action=reuse` and
`content_retention=discard`, because it guarantees zero network activity and
does not create or enrich article records.

### `POST /api/v1/evaluation-jobs/from-stored-selection`

Body contains `article_ids` (2–50), `model_id`, `aggregation_method`,
`prediction_action`, and `content_retention`; the latter two use the same safe
defaults. The first three fields are required. All articles must resolve to one current publisher. This avoids
translating frontend selections back into URLs.

For every job type, repeating the same body and `Idempotency-Key` returns the
same job and therefore the same created run IDs. A new key with
`prediction_action=recompute` authorizes a new fetch and a new immutable run;
it never overwrites the earlier run.

## 10. Jobs

`job_type` is exactly one of `article_evaluation`,
`article_list_evaluation`, `publisher_evaluation`, `dataset_import`,
`model_scan`, `model_upload`, `model_validate`, or `content_purge`, matching the
product and CSV contracts.

### `GET /api/v1/jobs`

Filters: `status`, `job_type`, `created_from`, `created_to`; newest first.

### `GET /api/v1/jobs/{job_id}`

Returns ID, type, state, phase, progress, safe normalized request, counters,
result links, warnings, error envelope, cancellation state, retry relationship,
`retry_available`, nullable `retry_unavailable_code`, and timestamps. A failed
job resource itself returns HTTP `200`.

Evaluation results include ordered `selected_prediction_run_ids` and
per-article safe subresults (`reused`, `inferred`, `recomputed`,
`content_saved`, `failed`). They never contain title/body. A content-purge job
returns article ID, live rows rewritten, purge audit ID, and
`backup_policy=manual_deletion_required`.

### `GET /api/v1/jobs/{job_id}/events`

Returns `text/event-stream`. Events are `snapshot`, `progress`, `warning`, and
`terminal`. IDs are `<process_stream_id>:<counter>` and are retained in a
bounded current-process ring. A retained current-stream `Last-Event-ID` resumes
after that event. An unknown/old stream—including after restart—receives one
fresh snapshot of persisted current job state and new IDs; intermediate old
progress is not reconstructed. A heartbeat comment is sent every 15 seconds.
Disconnecting does not cancel the job.

### `POST /api/v1/jobs/{job_id}/cancel`

Valid only for `queued` or `running`. Returns `202` with
`cancel_requested=true`. Terminal jobs return `409 JOB_NOT_CANCELLABLE`.

### `POST /api/v1/jobs/{job_id}/retry`

Valid only for a failed/cancelled job with `retry_available=true`. It creates a
linked job and revalidates roots/model/network conditions. Dataset/model upload
requires the exact acquired spool; absent source returns
`409 SOURCE_NOT_AVAILABLE` and creates no job. A successful admission
atomically transfers the spool capability to the new job, so concurrent retries
cannot share it. Returns `202` otherwise.

## 11. Imports

### `GET /api/v1/imports`

Paginated newest-first import history.

### `GET /api/v1/imports/{import_id}`

Returns source kind/name, format-independent content SHA-256, optional transport
SHA-256, schema, status, counters, protected column names, warnings, and
timestamps. No protected values or unrestricted path. Server-local path import
is CLI-only in the MVP; there is no corresponding API route.

### `POST /api/v1/imports/upload`

Streams one `.csv`, `.csv.gz`, `.zip`, or manifest `.zip`. Default limit is
2 GiB, configurable by `PRT_DATASET_UPLOAD_MAX_BYTES`. The same archive safety
rules as model upload apply, with at most 1,024 entries and total extracted
bytes no greater than the dataset upload limit. A ZIP contains either exactly
one CSV or one top-level `manifest.json` plus exactly its listed CSV parts; no
other entries or nested archives are accepted. For `.csv.gz`, decompression is
streamed and stops when uncompressed bytes exceed the same dataset limit.
The request stream is hashed into a private mode-`0600` spool with continuous
size/free-space checks. It is fsynced and atomically acquired before the job and
idempotency rows commit; failure/disconnect/ENOSPC before that point returns an
error and creates no job. Parsing computes the `prt-dataset-content-v1` digest
and stages only projected rows. The acquired source/staging data is removed
after a durable terminal transaction (or retained for 24 hours only after a
process interruption). Returns `202` only after acquisition.

### `GET /api/v1/imports/{import_id}/rejections`

Returns safe rejection records in ascending manifest-part position then
`(source_row,rejection_id)` using standard cursor pagination. Each record names
the safe logical part; it never returns raw rows, editorial values, or protected
provider values.

## 12. Aggregation metadata

### `GET /api/v1/aggregation-methods`

Returns the three exact method identifiers, display names, method versions,
formulas in human-readable English, minimum count, required inputs, and
scientific warnings. Availability for a concrete selection is returned by:

### `POST /api/v1/aggregation-methods/availability`

Body contains ordered `prediction_run_ids` (2–50). Each run must exist and all
must share one exact model and publisher. Response reports each method enabled
or disabled with a stable reason and echoes those exact IDs. It performs no run
selection, inference, or mutation. Evaluation workflows that start from article
IDs select the latest reusable exact-model run using the single reuse ordering
rule before calling the same availability service. An absent run is
`PREDICTION_RUN_NOT_FOUND`, mixed publishers are `MIXED_PUBLISHERS`, and mixed
model IDs are a `422 details.fields` validation error.

## 13. Configuration exposure

### `GET /api/v1/config/public`

Returns only safe UI configuration: offline state, article/queue limits,
upload-enabled flags and limits, allowed page sizes, enabled model families,
and OSF URL. It excludes filesystem roots, proxy credentials, and environment
values.

## 14. HTTP status mapping

Section 3 is the complete normative mapping. Success semantics are: `200` for a
synchronous success/resource read and `202` only after a durable job is
admitted (and, for uploads, after acquisition). Schema field errors are `422`
with `details.fields` and no separate code. Failures after acceptance appear in
a terminal job resource whose read remains HTTP `200`.

## 15. Rate and resource limits

Loopback API limits each client to 120 requests/minute with a burst of 30;
health and SSE heartbeat traffic are excluded. Job creation is limited to
10/minute and uploads to one active upload per instance. Rate excess returns
`429` with `Retry-After`. The default maximum of 100 queued jobs is separate;
overflow returns `503 JOB_QUEUE_FULL` and creates no job/idempotency row.
An existing matching idempotency key is resolved before queue admission and
still returns its original resource when the queue is full.

## 16. API compatibility tests

The committed OpenAPI document generated in CI must be diffed against an
approved snapshot. Every endpoint requires tests for success, validation,
Host/Origin security, stable error code, and CSV persistence effects.
Frontend end-to-end tests use the public API; no test-only backend route may
bypass the contract.
