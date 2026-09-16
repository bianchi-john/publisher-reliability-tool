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
| `TRAINING_DATA_LEAKAGE` | 409 | Selected checkpoint was trained on the known fold-indexed dataset article |
| `PROBABILITIES_REQUIRED` | 409 | Selected exact runs lack complete probabilities |
| `INSUFFICIENT_ARTICLES` | 422 | Fewer than two compatible successful runs or requested count unmet |
| `IMPORT_INVALID` | 422 | Dataset schema/container/row conflict prevents requested import result |
| `STORAGE_ERROR` | 503 | Lock, structure, reference, write, fsync, or space failure |
| `PROCESS_INTERRUPTED` | 409 | A queued job lost its acquired source or a running job ended with the process |
| `FEATURE_UNAVAILABLE` | 501 | A documented extension point exists but the feature is not finished in this release |
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

Returns `200 {"status":"ready"}` after CSV verification, frontend and worker
startup, and HTTP acceptance. Startup exposes no HTTP socket before that
point, so there is no supported live-but-not-ready startup phase. Readiness does
not predict whether a future request has a model, saved body, or network.

### `GET /api/v1/status`

Returns application/schema version, offline/device flags, bundled import state,
ledger counts, model-state counts, and current job ID/status. It exposes no full
paths, content, metrics history, or operational administration.

## 5. Articles and runs

### `GET /api/v1/articles`

Derived from prediction runs. Filters: `q` substring over canonical URL,
`publisher`, `model_id`, `predicted_class`, and `origin`.
`article_source=dataset|user_evaluation` distinguishes articles with any
imported run from articles created solely by local inference. A dataset article
that also has local runs remains in `dataset` and exposes
`has_user_evaluation=true`. Sort is
`updated_desc` (default) or `url_asc`. Each item returns article/publisher IDs,
canonical URL/hostname, distinct model count, run count, latest run summary,
source type, imported/local run counts, `has_user_evaluation`, `content_saved`,
first seen, and last updated.

### `GET /api/v1/articles/{article_id}`

Returns the derived article summary and every run summary for that article,
newest first. It never embeds saved content. Absent ID is `NOT_FOUND`.

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

Streams one row per stored prediction run as CSV using the list filters, so every
model that evaluated an article is a separate, fully described row. Runs of the
same article stay adjacent, ordered by family then fold. Header:

```text
article_id,url,domain,publisher_id,prediction_origin,prediction_run_id,model_id,prediction_family,prediction_fold_id,prediction_model_name,prediction_model_provenance,prediction_official_manifest_entry_sha256,predicted_label,prob_class_0,prob_class_1,prob_class_2,prob_class_3,prob_class_4,prediction_action,input_source,content_retention,job_id,inference_started_at,inference_completed_at,duration_ms,device,software_versions_json,recorded_at
```

The attachment is named `article-predictions.csv`. Column names match the
user-prediction block of `dataset/predictions/predictions.csv`. No option can
include saved or ephemeral content, and no column exposes an artifact path.

### `DELETE /api/v1/user-data`

Synchronous, permanent purge of every locally created evaluation. Body requires
`{"confirmation":"DELETE"}`. It rejects while any evaluation job is running.
It then removes the private prediction mirror
(`dataset/predictions/user-predictions.csv`) before replacing `prediction_runs.csv`
with everything except `local_inference` rows, and replaces `local_content.csv`
with nothing — that ledger holds only content the user chose to save locally,
regardless of which run's prediction they were viewing when they saved it. The
released dataset and every `bundled_import`/`user_import` run are untouched.
Returns `200` with `{"deleted_predictions":<int>,"deleted_saved_content":<int>}`.
Bad confirmation is `INVALID_INPUT`.

## 6. Publishers

### `GET /api/v1/publishers`

Derived publisher list. Filters: `q` over hostname and `model_id`; order is
latest evaluation descending then hostname ascending. Items return IDs,
hostname, article/run/evaluation counts, and latest evaluation time. No homepage
is invented from article URLs.

### `GET /api/v1/publishers/{publisher_id}`

Returns the derived summary, counts by model/class, and the 20 newest articles.

### `GET /api/v1/publishers/{publisher_id}/aggregation`

Derives the publisher class from stored article runs and writes nothing. Query
parameters are `method` (`majority_vote` default, `ordinal_mean`,
`mean_probabilities`) and a repeatable `exclude=<article_id>`.

Each model is aggregated only over its own leakage-safe articles and never mixed
with another model's predictions; one run per article per model is counted, the
newest by effective time. The response returns the method, the excluded IDs, the
exact article set considered with canonical URLs, and one entry per model with
available/used/excluded counts, result class, ordinal mean, mean probabilities
and class counts. A model with fewer than two counted articles reports no class
and states why. An unknown method is `INVALID_INPUT`; an unknown publisher is
`NOT_FOUND`.

## 7. Models

### `GET /api/v1/models`

Returns every historical/registered model with family, fold, model ID, core or
optional support level, status, artifact availability, runnable flag, redacted
root-relative locator, digest, recipe/version, immutable base/tokenizer
revisions, input policy, provenance (`paper_official`, `user_custom`,
`paper_dataset`, or `local_checkpoint`), and safe status detail. Optional `family`/`status`
filters are supported. This endpoint is also the model detail source.

### `POST /api/v1/models/scan`

Body is `{}`. Creates a `model_validation` job that scans configured roots and
the internal managed-model root for recognized BERT/RoBERTa checkpoints and runs
required fixtures. It accepts no path. Returns `202 {"job_id":"uuid"}`.

A checkpoint whose file is unchanged since the previous scan reuses its recorded
verification instead of being hashed and loaded again; the job result reports how
many were reused. Full re-verification is deliberately not exposed over HTTP: it
reads every byte of every checkpoint and belongs to the operator, through
`publisher-reliability models scan --full`.

### `GET /api/v1/models/available`

Explains which local checkpoints may classify one article URL. The only query
parameter is `url`. An article is the only input there is: a publisher class is
read from the articles already classified, through the aggregation endpoint, so
there is no availability question to ask about a publisher.

`items` contains the historical model/fold identities whose stored prediction can
be reused, meaning a local checkpoint of the same family and fold is installed and
the leakage guard accepts it, plus the runnable local checkpoints that can create
the missing run. Each item includes `mode=stored_prediction|new_inference`, the
separate `local_model_id`, local status/runnable flag, safe held-out article
count, run count, probability count and `eligible`.

`availability` always explains the result with this separate, non-HTTP status
registry:

| Availability code | Meaning |
| --- | --- |
| `AVAILABLE` | At least one safe stored or runnable local model option is available |
| `NO_LOCAL_CHECKPOINTS` | No validated local artifact is currently present |
| `NEW_ARTICLE_REQUIRES_INFERENCE` | URL needs a new run but no runnable local model is available |
| `TRAINING_DATA_LEAKAGE` | Present local folds were trained on this known dataset article |
| `NO_MATCHING_LOCAL_MODEL` | Stored history has no family/fold present in the local inventory |

The object also returns `input_known`, local/eligible counts, and family/fold
entries blocked because the checkpoint was trained on the article. This
endpoint makes no network request and creates no job or prediction.

### `POST /api/v1/models/upload`

Multipart with one `file`, which must be a self-contained `.zip` satisfying
`custom-model-bundle.md`. Family, fold, input policy and five-class order come
only from the constrained `prt-model.json`; they are not independent request
fields.

The request is streamed to a private file and limited by
`PRT_MODEL_UPLOAD_MAX_BYTES` (default 8 GiB), then creates a
`model_validation` job. Validation permits at most 256 regular entries and the
same uncompressed-byte limit. It rejects traversal, links, executable/native or
pickle/PyTorch files, `auto_map`, `trust_remote_code`, non-local tokenizer
requirements, model types outside the documented encoder allowlist,
non-five-label configuration, non-finite tensors, and strict state-dictionary
key/shape mismatch.

Successful validation atomically moves the extracted bundle under
`<data-dir>/managed-models/<model_id>` and registers it in `models.csv` as
`custom_transformer_bundle`, accepting the documented encoder allowlist. A
bundle declaring the LoRA adapter schema for the study's larger decoder bases is
refused with `FEATURE_UNAVAILABLE` while that support is under development.
Terminal success/failure deletes the acquired ZIP. The returned job result
includes model ID, family, fold and validation status.

### `POST /api/v1/models/official-upload`

Reserved for importing the study's larger decoder checkpoints (Llama 3 8B,
Mistral 24B). That support is under development, so the endpoint refuses every
request with `501 FEATURE_UNAVAILABLE` before reading any upload bytes, and
registers nothing.

## 8. Evaluation

### `POST /api/v1/evaluation-jobs`

Creates one `evaluation` job and returns `202 {"job_id":"uuid"}`. One article is
the only accepted input. Fields are `input`, `model_id`, `prediction_action`
(`reuse` default or `recompute`), and `content_retention` (`discard` default or
`save_local`).

```json
{"input":{"type":"article","url":"https://example.org/a"},"model_id":"sha256","prediction_action":"reuse","content_retention":"discard"}
```

Evaluating several articles as one operation is not offered: any other `input`
type is rejected by request validation. A publisher-level class is obtained
instead from `GET /api/v1/publishers/{publisher_id}/aggregation`, which derives
it from the runs already stored and persists nothing.

## 9. Jobs

The persisted job-type registry is: `evaluation`, `dataset_import`,
`model_validation`. It matches the product and storage contracts.

### `GET /api/v1/jobs`

Paginated newest-first list filtered by `status` or `job_type`.

### `GET /api/v1/jobs/{job_id}`

Returns job type/status, macro phase, approximate progress, safe normalized
request, result IDs/counters/warnings, safe error code/message, and timestamps.
The frontend polls this endpoint about once per second while a job runs.
Failed jobs return HTTP
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
identical parse-complete content digest/schema resolves to its existing
successful, partial, or deterministic failed import during the job and creates
no runs. ZIP and manifest upload are unsupported; the bundled
manifest is startup/CLI-only. Terminal success/failure deletes the acquired
source; an interrupted running job is failed and cleaned at startup.

Supported prediction prefixes are `bert` and `roberta`. Each represented
label/fold pair requires all five probability columns; missing or incomplete
vectors fail `IMPORT_INVALID`.

## 11. Aggregation metadata

### `GET /api/v1/aggregation-methods`

Returns the three method identifiers, versions, formula text, minimum count,
probability requirement, tie rule, and scientific warning. Concrete
method availability is included in aggregation metadata and checked again by
the evaluation service. Concrete input/model/fold availability is provided by
`GET /api/v1/models/available`.

## 12. Endpoint and frontend contract

Every endpoint has generated OpenAPI success/error schemas. Frontend end-to-end
tests exercise these routes rather than private backend hooks. The API may add a
new field compatibly, but changing an identifier, formula, or existing field
meaning requires a contract/test update; formal public API lifecycle guarantees
are outside this research demo.
