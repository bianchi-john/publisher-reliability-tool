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
| `PREDICTION_NOT_FOUND` | 404 | Prediction ID is absent |
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

- `q`: case-insensitive substring over canonical URL and title;
- `publisher`: exact normalized hostname;
- `model_id`: exact model ID with a current prediction;
- `predicted_class`: integer `0..4` paired with `model_id`;
- `origin`: `bundled_import`, `user_import`, or `local_inference`;
- `updated_from`, `updated_to`: inclusive RFC 3339 bounds;
- `sort`: `updated_desc` (default), `title_asc`, or `url_asc`.

Each summary returns article ID, canonical URL, publisher summary, title,
authors, text availability, available prediction count, most recent prediction
summary, first/last seen timestamps, and network-use flag. Article body is not
included. Its `updated_at` is the later of the current article version's
`recorded_at` and every current prediction version's `recorded_at`; this value
drives `updated_*` filters and `updated_desc` sorting.

### `GET /api/v1/articles/{article_id}`

Returns complete current article metadata, article text, and all current
predictions ordered by family, fold, and model ID. Each prediction contains
class, nullable five-probability vector, origin, model summary, job/import ID,
and timestamps.

Returns `404 ARTICLE_NOT_FOUND` when absent.

### `GET /api/v1/articles/{article_id}/predictions`

Paginated prediction list. Supports `model_id` and `family` filters.

### `GET /api/v1/articles/export`

Streams `text/csv`. Accepts the list filters plus `include_text=false` by
default. Maximum unpaginated result is the complete filtered collection. The
response includes `X-Exported-At` in the storage contract's UTC timestamp
format and a safe `Content-Disposition` filename.

## 7. Publishers

### `GET /api/v1/publishers`

Filters: `q` over hostname/display name, `model_id`, `evaluated_from`,
`evaluated_to`, and sort `updated_desc` or `hostname_asc`.

Each summary returns publisher ID, normalized hostname, homepage URL, display
name, stored article count, prediction count, evaluation count, and last
evaluation timestamp. Its `updated_at` is the maximum current `recorded_at`
across the publisher, its articles, their predictions, and its evaluations;
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

Returns evaluation fields, exact ordered contributing article/prediction
summaries, class counts, nullable mean probabilities, warnings, requested/used
counts, partial flag, input/discovery mode, and scientific warnings.

### `GET /api/v1/publishers/export`

Streams filtered publisher summaries as CSV; article text is never embedded.
It uses the same export headers as the article export.

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

## 9. Evaluation jobs

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
`historical_only` virtual model. The latter succeeds only when every required
prediction already exists; otherwise the terminal job code is
`MODEL_NOT_RUNNABLE`.

#### Single article body

```json
{
  "input": {
    "type": "article",
    "url": "https://publisher.example/article"
  },
  "model_id": "64-hex-model-id"
}
```

No aggregation field is accepted.

#### Explicit article list body

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
  "aggregation_method": "majority_vote"
}
```

`urls` contains 2–50 distinct pre-normalization strings and must remain distinct
after normalization.

#### Publisher body

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
  "aggregation_method": "majority_vote"
}
```

`requested_article_count` is `2..50`. API clients must send
`discovery_mode` and `allow_partial`; omission is `422`.

### `POST /api/v1/evaluation-jobs/from-stored-selection`

Body contains `article_ids` (2–50), `model_id`, and `aggregation_method`.
All articles must resolve to one current publisher. This avoids translating
frontend selections back into URLs.

## 10. Jobs

### `GET /api/v1/jobs`

Filters: `status`, `job_type`, `created_from`, `created_to`; newest first.

### `GET /api/v1/jobs/{job_id}`

Returns ID, type, state, phase, progress, safe normalized request, counters,
result links, warnings, error envelope, cancellation state, retry relationship,
and timestamps.

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
streamed and stops when uncompressed bytes exceed the same dataset limit. The
uploaded source is deleted
after the import job reaches any terminal state; its checksum and projected
records remain. Returns `202`.

### `GET /api/v1/imports/{import_id}/rejections`

Returns safe rejection records in ascending `(source_row,rejection_id)` order
using the standard cursor pagination contract. It never returns raw rejected
rows, article bodies, author values, or protected-provider values.

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
