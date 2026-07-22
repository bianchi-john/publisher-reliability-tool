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
| Frontend | React, TypeScript, Vite, locally bundled assets |
| Persistence | Python `csv`, small in-memory indexes, filesystem lock |
| Retrieval | `httpx` and `newspaper3k` parsing |
| Language | `langdetect`, seed zero |
| Models | PyTorch/Transformers; PEFT/bitsandbytes only for optional loaders |
| Packaging | Python wheel and one simple Compose service |

## 3. Process and data flow

```text
browser/CLI -> FastAPI service -> Storage (seven CSV files)
                         |
                         +-> FIFO job worker
                               -> ArticleRetriever
                               -> ModelLoader
                               -> InferenceService
                               -> AggregationMethod
```

Frontend and API use the same Pydantic request types and service functions.
There is no separate API implementation for the UI and no frontend access to
CSV files.

## 4. Concrete module boundaries

| Boundary | Responsibility | How to extend |
| --- | --- | --- |
| `Storage` | Load ledgers, lock data directory, append immutable rows, atomically rewrite small mutable files | Add a column/schema version and loader validation |
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

- Immutable scientific rows (`prediction_runs.csv`, `evaluations.csv`, and
  `imports.csv`) are appended, flushed, and fsynced.
- Small mutable state (`models.csv`, `jobs.csv`, `local_content.csv`) is written
  completely to a sibling temporary file, verified, fsynced, and atomically
  renamed.
- A process-wide write mutex serializes writes; a POSIX `flock` prevents a
  second process from using the directory.
- Startup may remove one malformed, incomplete final physical CSV record from
  an append-only ledger. Middle-row or semantic corruption fails closed.
- Import prepares projected rows in a private staging directory. A small
  `import.pending.json` marker names prepared final run/import/model files;
  startup completes only those exact renames whose live target does not already
  have the recorded digest, or fails if neither target nor prepared file
  matches.

This special import marker is the only multi-file commit mechanism. There is no
generic transaction ledger, record versioning, compaction, commit watermark,
or snapshot history.

In-memory indexes cover ID/URL/model lookups, latest exact-model run, publisher
grouping, and simple list filters. They are rebuilt at startup and are never
authoritative. Offset pagination reflects committed state at each request; a
concurrent local write can shift later pages, which is acceptable for this
single-user demo.

## 6. Jobs

One FIFO worker runs `evaluation`, `dataset_import`, and `model_validation`
jobs. Admission persists a queued row; the worker rewrites job state at
macrophase boundaries. The browser polls every two seconds.

No persistent event stream, cancellation, retry endpoint, priority queue, lane,
or job-level parallelism exists. Publisher candidates are sequential. On
restart, queued jobs are admitted again only while any acquired source they
need still exists; otherwise they fail. A running job becomes failed with
`PROCESS_INTERRUPTED` and its temporary source is cleaned up. The user uploads
again rather than resuming or retrying it.

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
leading `www.` removed; registrable-domain guessing is not used.

## 8. Retrieval boundary

The retriever accepts HTTP(S), resolves every hop, rejects private, loopback,
link-local, multicast, reserved, and unspecified addresses, connects to the
validated peer with `trust_env=false`, enforces five redirects, 10-second
connect/30-second response timeout, HTML MIME, robots policy, one request per
second per hostname, and 10 MiB decompressed page size.

`newspaper3k` receives already downloaded HTML and cannot issue unchecked
network calls. HTML, authors, and extracted content stay in job memory. Only
validated title/body may cross into `local_content.csv` after `save_local`;
authors and raw HTML are always released. Offline mode injects a deny-all HTTP
transport before application services are created.

## 9. Model lifecycle

Configured model roots must be real readable directories. Scanning never
follows symlinks; a candidate containing a symlink is rejected. API clients can
scan configured roots or upload an artifact but cannot submit arbitrary server
paths.

Built-in official recipes determine scientific model identity independently of
filesystem location. States are `compatible`, `historical_only`,
`artifact_missing`, `dependency_missing`, `resource_unavailable`, and `invalid`.
Historical runs remain browseable and aggregable when an artifact disappears.

BERT and RoBERTa loaders and fixtures are core. Llama and Mistral loaders are
optional modules activated only when installed dependencies/hardware allow.
Unknown artifacts are reported and ignored; no manifest or code from an
artifact changes loader behavior.

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
| Malformed incomplete final append | Back up that file and remove only the tail |
| Other storage corruption | Exit without serving HTTP |
| Running job at restart | Mark `PROCESS_INTERRUPTED` |
| Network unavailable/offline | Preserve browsing/reuse; fail the dependent job |
| Missing artifact | Preserve historical model identity and runs |
| Purge | Rewrite active local-content file; backups remain the user's responsibility |

Manual stopped-server copying of the data directory is the backup and restore
procedure. Exhaustive ENOSPC matrices, automatic backup rotation, online
recovery UI, and high-availability behavior are outside the demo.

## 12. Invariants

1. A publisher evaluation always names exact immutable runs from one model.
2. Protected reference data never crosses the import projection.
3. Authors/raw HTML never persist; title/body require explicit consent.
4. `reuse` does not infer; `recompute` creates a new run.
5. Model identity contains scientific settings, never deployment paths.
6. Offline mode makes no application HTTP connection.
7. CSV is sufficient to reconstruct every persisted API resource.
8. UI and API call the same services and formulas.
