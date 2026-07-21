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
- Mutation requests accept `Idempotency-Key`, 8–128 visible ASCII characters.
  Reusing a key with a different body returns `409 IDEMPOTENCY_CONFLICT`.
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

OpenAPI is served at `/api/openapi.json`; local interactive documentation is at
`/api/docs`.

## 2. Authentication

Effective loopback mode means either native loopback binding or the exact
loopback-published container exception in the architecture contract; it
requires no authorization. Every other non-loopback binding requires every
`/api/v1` endpoint except health to receive:

```http
Authorization: Bearer <configured-api-key>
```

Missing or invalid credentials return `401 AUTHENTICATION_REQUIRED`. The key is
never returned by the API, logged, or stored in CSV.

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

The following transport and resource codes are exhaustive for this API
version. Domain/job codes are the exhaustive list in Product Specification
section 13.

| Code | HTTP status | Meaning |
| --- | ---: | --- |
| `INVALID_CURSOR` | 400 | Cursor is malformed or does not match the filters |
| `AUTHENTICATION_REQUIRED` | 401 | Bearer credential is absent or invalid |
| `FORBIDDEN` | 403 | Authenticated request cannot use the path, origin, or action |
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
| `PAYLOAD_TOO_LARGE` | 413 | Request or upload exceeds its configured byte limit |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Body or archive type is not accepted |
| `RATE_LIMITED` | 429 | Local client exceeded a documented rate limit |
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

Outside `/api/v1`. Returns `200 {"status":"ready"}` only after CSV verification,
index build, and job executor startup. Otherwise `503` with a safe reason.

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
successful job removes title/body from all application-managed CSV versions
and backups without deleting runs or evaluations. It cannot affect external
copies. A mismatched confirmation is `422`; an article with no saved content is
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

Each summary returns publisher ID, normalized hostname, homepage URL, stored
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
publisher_id,normalized_hostname,homepage_url,stored_article_count,prediction_run_count,evaluation_count,last_evaluation_at,updated_at
```

## 8. Models

### `GET /api/v1/models`

Filters: `family`, `status`, and `q` over safe display name. Returns compatibility
state, fold, artifact kind, redacted path, checksum, recipe/base/tokenizer
identity, max tokens, registration time, validation time, and safe status detail.

### `GET /api/v1/models/{model_id}`

Returns the full safe model record and dependency/resource checks. It never
returns unrestricted absolute paths or secrets.

### `POST /api/v1/models/scan`

Body:

```json
{
  "paths": ["/models"],
  "recursive": true
}
```

Paths are server-local. In Docker they must be inside mounted roots. Returns
`202` with a `model_scan` job.

### `POST /api/v1/models/register`

Body:

```json
{
  "path": "/models/bert_fold_1.pt",
  "family": "bert",
  "fold_id": 1,
  "custom_manifest": null
}
```

The resolved path must remain inside a configured model root and must not
traverse through a symlink outside it. `family` and `fold_id` can be `null` only
when an unambiguous official artifact name/config supplies them. The backend
never guesses among multiple recipes. Returns `202` with a `model_register`
job.

### `POST /api/v1/models/upload`

Consumes `multipart/form-data` with:

- `file`: one `.pt`, `.safetensors`, `.zip`, or `.tar.gz` stream;
- `family`: required string unless a bundled custom manifest is present;
- `fold_id`: optional integer;
- `expected_upload_sha256`: optional lowercase digest of the received file or
  archive bytes, checked before extraction; it is distinct from the normalized
  artifact digest used in model identity.

The server streams to `<data-dir>/uploads`, limits total bytes using
`PRT_MODEL_UPLOAD_MAX_BYTES` (default 10 GiB), rejects archive traversal and
links, checks free disk space, validates before moving to managed model storage,
and deletes failed temporary uploads. A model archive has at most 10,000
entries and its total extracted regular-file bytes cannot exceed the upload
limit. Nested archives are treated as ordinary model files and are never
recursively extracted. Returns `202` with a `model_upload` job.

### `POST /api/v1/models/{model_id}/validate`

Revalidates artifact, dependencies, and resources. Returns `202` with a job.

Model deletion is outside the MVP. Users remove unmanaged artifacts manually;
missing artifacts become invalid on the next scan without deleting provenance.

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

`model_id` can identify a runnable `compatible` model or a
`historical_only` virtual model. The latter rejects
`prediction_action=recompute`. A publisher input additionally requires
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

### `GET /api/v1/jobs`

Filters: `status`, `job_type`, `created_from`, `created_to`; newest first.

### `GET /api/v1/jobs/{job_id}`

Returns ID, type, state, phase, progress, safe normalized request, counters,
result links, warnings, error envelope, cancellation state, retry relationship,
and timestamps.

Evaluation results include ordered `selected_prediction_run_ids` and
per-article safe subresults (`reused`, `inferred`, `recomputed`,
`content_saved`, `failed`). They never contain title/body. A content-purge job
returns the article ID and counts of rewritten managed files/rows.

### `GET /api/v1/jobs/{job_id}/events`

Returns `text/event-stream`. Events are `snapshot`, `progress`, `warning`, and
`terminal`. Each event contains the current job version and can be resumed with
`Last-Event-ID`. A heartbeat comment is sent every 15 seconds. Disconnecting
does not cancel the job.

### `POST /api/v1/jobs/{job_id}/cancel`

Valid only for `queued` or `running`. Returns `202` with
`cancel_requested=true`. Terminal jobs return `409 JOB_NOT_CANCELLABLE`.

### `POST /api/v1/jobs/{job_id}/retry`

Valid only for `failed` or `cancelled`. Creates a new job from the safe stored
request and links `retry_of_job_id`. It revalidates current model and network
conditions. Returns `202`.

## 11. Imports

### `GET /api/v1/imports`

Paginated newest-first import history.

### `GET /api/v1/imports/{import_id}`

Returns source kind/name/checksum, schema, status, counters, protected column
names, warnings, and timestamps. No protected values or unrestricted path.

### `POST /api/v1/imports/from-path`

Body:

```json
{
  "path": "/data/imports/predictions.csv.gz"
}
```

Path must be inside configured import roots. Returns `202` with a dataset-import
job.

### `POST /api/v1/imports/upload`

Streams one `.csv`, `.csv.gz`, `.zip`, or manifest `.zip`. Default limit is
2 GiB, configurable by `PRT_DATASET_UPLOAD_MAX_BYTES`. The same archive safety
rules as model upload apply, with at most 1,024 entries and total extracted
bytes no greater than the dataset upload limit. A ZIP contains either exactly
one CSV or one top-level `manifest.json` plus exactly its listed CSV parts; no
other entries or nested archives are accepted. For `.csv.gz`, decompression is
streamed and stops when uncompressed bytes exceed the same dataset limit.
Dataset uploads are parsed and hashed directly from the request stream; unlike
model uploads, their original bytes are never written under `<data-dir>` or a
system temporary directory. Only projected URL/domain/model-output rows and the
source checksum commit. Returns `202`.

### `GET /api/v1/imports/{import_id}/rejections`

Returns safe rejection records in ascending `(source_row,rejection_id)` order
using the standard cursor pagination contract. It never returns raw rejected
rows, editorial values, or protected-provider values.

## 12. Aggregation metadata

### `GET /api/v1/aggregation-methods`

Returns the three exact method identifiers, display names, method versions,
formulas in human-readable English, minimum count, required inputs, and
scientific warnings. Availability for a concrete selection is returned by:

### `POST /api/v1/aggregation-methods/availability`

Body contains `article_ids` and `model_id`. Response reports each method as
enabled or disabled with a stable reason. It performs no inference or mutation.

## 13. Configuration exposure

### `GET /api/v1/config/public`

Returns only safe UI configuration: offline state, article-count limits,
upload-enabled flags and limits, allowed page sizes, enabled model families,
and OSF URL. It excludes API keys, filesystem roots, proxy credentials, and
environment values.

## 14. HTTP status mapping

| Status | Use |
| --- | --- |
| `200` | Successful synchronous read/action |
| `202` | Background job accepted |
| `400` | Invalid cursor or syntactically invalid operation |
| `401` | Authentication required/invalid |
| `403` | Valid authentication but forbidden path/origin/action |
| `404` | Resource absent |
| `409` | Current-state conflict, duplicate idempotency key, unavailable method, locked storage |
| `413` | Upload/request exceeds configured byte limit |
| `415` | Unsupported content or archive type |
| `422` | Field validation failure |
| `429` | Local API request rate limit exceeded |
| `500` | Unexpected internal failure |
| `503` | Application not ready or storage unavailable |

Network retrieval failures occur inside accepted jobs and therefore appear as
terminal job error codes rather than changing the original `202` response.

## 15. Rate and resource limits

Loopback API limits each client to 120 requests/minute with a burst of 30;
health and SSE heartbeat traffic are excluded. Non-loopback mode limits to 60
requests/minute. Job creation is limited to 10/minute and uploads to one active
upload per instance. Exceeding a limit returns `429` with `Retry-After`.

## 16. API compatibility tests

The committed OpenAPI document generated in CI must be diffed against an
approved snapshot. Every endpoint requires tests for success, validation,
authentication when enabled, stable error code, and CSV persistence effects.
Frontend end-to-end tests use the public API; no test-only backend route may
bypass the contract.
