# Local REST API Contract

**Status:** Normative research-demo API
**Base:** `/api/v1`
**Media type:** UTF-8 JSON unless stated otherwise

## 1. General rules

- The API serves the bundled local frontend and reproducibility scripts. It is
  not a remotely supported public API.
- Unknown request fields are rejected. Names are snake_case; timestamps are UTC
  RFC 3339 ending in `Z`.
- URL strings are at most 8,192 UTF-8 bytes. Non-upload JSON is at most 1 MiB.
- There is no authentication, CORS configuration, `Idempotency-Key`, SSE,
  cancellation, or retry endpoint.
- The server binds host loopback only. Every request's `Host` must equal the
  configured local host/port; mismatch is `INVALID_HOST`. No permissive CORS
  header is emitted.
- Double-submit prevention is a frontend concern. Scientifically meaningful
  deduplication is server-side: identical imports reuse their digest identity,
  `reuse` creates no run, model scans reuse exact model identity, and every
  accepted `recompute` intentionally creates a new run.
- Ordinary resources, jobs, errors, and exports never contain saved/ephemeral
  title, body, authors, raw HTML, or snippets. Only the dedicated content GET
  returns explicitly saved title/body.
- OpenAPI is `/api/openapi.json`; local Swagger UI is `/api/docs` with bundled
  assets.

## 2. Errors and HTTP mapping

Every non-2xx API error is:

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "Safe English explanation.",
    "details": {},
    "request_id": "uuid"
  }
}
```

This is the exhaustive stable registry. Field validation uses `INVALID_INPUT`
with `details.fields`. A failed background job is still read with HTTP `200` and
contains one of these codes in its `error_code` field.

| Code | HTTP | Meaning |
| --- | ---: | --- |
| `INVALID_INPUT` | 422 | Schema, range, duplicate input, mixed publisher, or unsupported option |
| `INVALID_HOST` | 421 | Host is not the configured local origin |
| `INVALID_URL` | 422 | URL syntax, encoding, scheme, or hostname is invalid |
| `NOT_FOUND` | 404 | Requested article, run, publisher, evaluation, model, job, import, or content is absent |
| `PAYLOAD_TOO_LARGE` | 413 | Request, upload, field, or extracted body exceeds a demo limit |
| `NETWORK_REQUIRED` | 409 | Strict offline/local state cannot satisfy the operation |
| `NETWORK_ERROR` | 502 | DNS, timeout, TLS, robots denial, unsafe address, or upstream HTTP failure |
| `EXTRACTION_FAILED` | 422 | HTML type/parsing or empty extraction prevents use |
| `TEXT_TOO_SHORT` | 422 | Extracted text misses the deterministic minimum |
| `NON_ENGLISH` | 422 | Language validation is non-English or indeterminate |
| `MODEL_NOT_AVAILABLE` | 404 | Requested model identity is absent |
| `MODEL_NOT_RUNNABLE` | 409 | Historical, missing, incompatible, dependency, or resource state cannot infer |
| `PROBABILITIES_REQUIRED` | 409 | Selected exact runs lack complete probabilities |
| `INSUFFICIENT_ARTICLES` | 422 | Fewer than two compatible successful runs or requested count unmet |
| `IMPORT_INVALID` | 422 | Dataset schema/container/row conflict prevents requested import result |
| `STORAGE_ERROR` | 503 | Lock, structure, reference, write, fsync, or space failure |
| `PROCESS_INTERRUPTED` | 409 | A running job ended with the process |
| `INTERNAL_ERROR` | 500 | Unexpected failure hidden behind a safe message |

Synchronous status is exactly the table value. Job creation returns `202` once
the job row is persisted; later domain failure is visible through job polling.

## 3. Pagination

List endpoints accept `limit` (`25`, `50`, `100`, default `25`) and zero-based
`offset` (default `0`, maximum `1,000,000`). Response:

```json
{"items": [], "page": {"limit": 25, "offset": 0, "next_offset": null}}
```

Ordering is deterministic per endpoint. Pagination is not a persistent
snapshot: a local write between requests may shift later pages. The UI refreshes
from offset zero after a mutation.

## 4. Health and status

### `GET /health/live`

Returns `200 {"status":"alive"}` when the event loop responds.

### `GET /health/ready`

Returns `200 {"status":"ready"}` after CSV verification, indexes, frontend,
and worker startup. It does not predict whether a future request has a model,
saved body, or network. Before readiness it returns
`503 {"status":"not_ready"}` outside the API error envelope.

### `GET /api/v1/status`

Returns application/schema version, offline/device flags, bundled import state,
ledger counts, model-state counts, and current job ID/status. It exposes no full
paths, content, metrics history, or operational administration.

## 5. Articles and runs

### `GET /api/v1/articles`

Derived from prediction runs. Filters: `q` substring over canonical URL,
`publisher`, `model_id`, `predicted_class`, and `origin`. Sort is
`updated_desc` (default) or `url_asc`. Each item returns article/publisher IDs,
canonical URL/hostname, distinct model count, run count, latest run summary,
`content_saved`, first seen, and last updated.

### `GET /api/v1/articles/{article_id}`

Returns the derived article summary and up to 20 newest run summaries. It never
embeds saved content. Absent ID is `NOT_FOUND`.

### `GET /api/v1/prediction-runs`

Paginated immutable runs filtered by `article_id`, `publisher_id`, `model_id`,
`family`, or `origin`. Order is effective completion time descending then run
ID ascending.

### `GET /api/v1/prediction-runs/{prediction_run_id}`

Returns one immutable run, safe article/model summary, exact class/probabilities,
action, input source, retention choice, import/job provenance, device, software
versions, and timestamps.

### `GET /api/v1/articles/{article_id}/content`

Returns only explicitly saved local content:

```json
{
  "article_id": "uuid",
  "canonical_url": "https://publisher.example/article",
  "title": "Saved title or empty string",
  "text": "Saved validated body",
  "content_saved_at": "2026-07-21T14:05:12Z"
}
```

Always `Cache-Control: no-store`; absent content is `NOT_FOUND`.

### `DELETE /api/v1/articles/{article_id}/content`

Synchronous local-state purge. Body requires
`{"confirm_canonical_url":"<exact stored URL>"}`. It rejects while any
evaluation job is running, rewrites `local_content.csv` atomically, and
returns `200` with `deleted=true` plus
`backup_notice="User backups and external copies are unchanged."`. Missing
content is `NOT_FOUND`; bad confirmation is `INVALID_INPUT`.

### `GET /api/v1/articles/export`

Streams all filtered article summaries as CSV using the list filters. Header:

```text
article_id,canonical_url,publisher_id,normalized_hostname,model_count,run_count,latest_prediction_run_id,latest_model_id,latest_predicted_class,content_saved,first_seen_at,updated_at
```

No option can include saved or ephemeral content.

## 6. Publishers and evaluations

### `GET /api/v1/publishers`

Derived publisher list. Filters: `q` over hostname and `model_id`; order is
latest evaluation descending then hostname ascending. Items return IDs,
hostname, article/run/evaluation counts, and latest evaluation time. No homepage
is invented from article URLs.

### `GET /api/v1/publishers/{publisher_id}`

Returns the derived summary, counts by model/class, 20 newest articles, and 20
newest evaluation summaries.

### `GET /api/v1/evaluations`

Paginated immutable evaluations filtered by `publisher_id`, `model_id`, or
`method`; newest first.

### `GET /api/v1/evaluations/{evaluation_id}`

Returns result, method/version, requested/used counts, partial flag, exact
ordered article IDs and run summaries, class counts or mean probabilities, and
scientific warnings. It never retargets newer runs.

## 7. Models

### `GET /api/v1/models`

Returns every historical/registered model with family, fold, model ID, core or
optional support level, status, artifact availability, runnable flag, redacted
root-relative locator, digest, recipe/version, immutable base/tokenizer
revisions, input policy, and safe status detail. Optional `family`/`status`
filters are supported. This endpoint is also the model detail source.

### `POST /api/v1/models/scan`

Body is `{}`. Creates a `model_validation` job that scans configured roots only,
validates recognized official artifacts, and runs required fixtures. It accepts
no path. Returns `202 {"job_id":"uuid"}`.

### `POST /api/v1/models/upload`

Multipart with one `file` (`.pt`, `.safetensors`, or `.tar.gz` only for the
official optional PEFT directory layout), optional `family`, and optional
`fold_id`. The request is streamed to a private file, limited by
`PRT_MODEL_UPLOAD_MAX_BYTES` (default 4 GiB), checksum-verified, and safely
extracted without traversal or links. Optional PEFT archives are limited to
10,000 regular entries and 4 GiB total extracted bytes. It then creates a
`model_validation` job. Failed acquisition creates no job. Generic
archives/manifests are unsupported. Successful validation atomically moves the
artifact under `<data-dir>/managed-models`; failed validation deletes the
temporary upload.

## 8. Evaluation

### `POST /api/v1/evaluation-jobs`

Creates one `evaluation` job and returns `202 {"job_id":"uuid"}`. Shared fields
are `model_id`, `prediction_action` (`reuse` default or `recompute`), and
`content_retention` (`discard` default or `save_local`).

Single article:

```json
{"input":{"type":"article","url":"https://example.org/a"},"model_id":"sha256","prediction_action":"reuse","content_retention":"discard"}
```

Explicit list:

```json
{"input":{"type":"article_list","urls":["https://example.org/a","https://example.org/b"]},"model_id":"sha256","aggregation_method":"majority_vote","prediction_action":"reuse","content_retention":"discard"}
```

Publisher:

```json
{"input":{"type":"publisher","url":"https://example.org/","requested_article_count":10,"allow_partial":true},"model_id":"sha256","aggregation_method":"majority_vote","prediction_action":"reuse","content_retention":"discard"}
```

Lists contain 2–50 distinct same-publisher URLs. Publisher evaluation always
uses stored eligible runs first and sequentially retrieves/discovers only the
remaining count; there are no separate discovery modes. A historical or missing
artifact model may reuse stored exact runs but cannot create missing runs or
recompute. `reuse + save_local` may retrieve content for an existing run but
does not infer; if retrieval resolves to another article, the job returns
`INVALID_INPUT` and stores nothing. Validation that depends only on submitted/
local state is synchronous; network/canonical/extraction failures appear on the
accepted job.

## 9. Jobs

The persisted job-type registry is: `evaluation`, `dataset_import`,
`model_validation`. It matches the product and storage contracts.

### `GET /api/v1/jobs`

Paginated newest-first list filtered by `status` or `job_type`.

### `GET /api/v1/jobs/{job_id}`

Returns job type/status, macro phase, approximate progress, safe normalized
request, result IDs/counters/warnings, safe error code/message, and timestamps.
The frontend polls this endpoint every two seconds. Failed jobs return HTTP
`200`; absent jobs return `NOT_FOUND`.

## 10. Imports

### `GET /api/v1/imports`

Paginated newest-first import summaries.

### `GET /api/v1/imports/{import_id}`

Returns source kind/name, content and optional transport SHA-256, schema,
status, counts, protected column names, safe warning summaries, and timestamps.

### `POST /api/v1/imports/upload`

Streams one `.csv` or `.csv.gz`, maximum 512 MiB and 300,000 logical data rows.
It saves a private temporary source, computes transport SHA-256, then creates a
`dataset_import` job. CSV.GZ decompression stops at 512 MiB uncompressed. An
identical successful content digest resolves to the existing import during the
job and creates no runs. ZIP and manifest upload are unsupported; the bundled
manifest is startup/CLI-only. Terminal success/failure deletes the acquired
source; an interrupted running job is failed and cleaned at startup.

## 11. Aggregation metadata

### `GET /api/v1/aggregation-methods`

Returns the three method identifiers, versions, formula text, minimum count,
probability requirement, tie rule, and scientific warning. Concrete
availability is included in article/publisher selection responses and checked
again by the evaluation service; there is no separate availability endpoint.

## 12. Endpoint and frontend contract

Every endpoint has generated OpenAPI success/error schemas. Frontend end-to-end
tests exercise these routes rather than private backend hooks. The API may add a
new field compatibly, but changing an identifier, formula, or existing field
meaning requires a contract/test update; formal public API lifecycle guarantees
are outside this research demo.
