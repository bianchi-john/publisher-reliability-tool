# Architecture

**Status:** Normative MVP architecture

## 1. Fixed technology stack

| Layer | Required technology |
| --- | --- |
| Language/runtime | Python 3.12 |
| HTTP/API | FastAPI with generated OpenAPI 3.1 |
| ASGI server | Uvicorn, exactly one worker |
| Validation | Pydantic v2 models shared by API and services |
| Frontend | React + TypeScript built by Vite |
| Charts | Chart.js bundled locally |
| Styling | Project-owned CSS; no runtime CDN or remote font |
| Persistence | Python CSV module over append-only UTF-8 CSV ledgers |
| Data frames | Optional Polars for bounded streaming import/query indexes; never authoritative storage |
| Background work | In-process bounded executor with persisted CSV job state |
| HTTP retrieval | `httpx` plus `newspaper3k` extraction |
| Language check | `langdetect` with `DetectorFactory.seed = 0` |
| Models | PyTorch, Transformers, PEFT, and bitsandbytes where required |
| Packaging | Python wheel, OCI image, Docker Compose v2 |

Changing one of these technologies is an architecture change and requires an
updated contract and acceptance coverage before implementation.

## 2. Process topology

```mermaid
flowchart LR
    CLI[Linux CLI] --> APP[Single FastAPI process]
    UI[Bundled React UI] --> API[/api/v1]
    CLIENT[Local API client] --> API
    APP --> JOBS[Bounded background executor]
    APP --> CSV[CSV store + in-memory indexes]
    JOBS --> MODELS[Local model runtimes]
    JOBS --> RETRIEVAL[Controlled article retrieval]
    RETRIEVAL -. explicit network need .-> WEB[Publisher/article sites]
    MODELS --> ARTIFACTS[Mounted/local model artifacts]
```

The UI is static content served by FastAPI and communicates only with the same
origin API. There is no separate frontend server in production. Native and
container deployments run one application process, one CSV writer, and one job
executor.

## 3. Module boundaries

| Python package | Responsibility |
| --- | --- |
| `config` | CLI/environment parsing, typed settings, safety validation |
| `api` | Versioned routes, authentication, error envelope, OpenAPI |
| `services` | Shared use cases used by API and startup commands |
| `storage` | CSV schema, transactions, locks, indexes, recovery, compaction |
| `imports` | Streaming dataset/manifest verification and projection |
| `identity` | URL normalization, canonical resolution, publisher hostname identity |
| `retrieval` | Safe HTTP, robots policy, discovery, `newspaper3k` extraction |
| `language` | Deterministic English and minimum-text validation |
| `models.registry` | Artifact discovery, manifests, compatibility, identity |
| `models.loaders` | Versioned BERT, RoBERTa, Llama, and Mistral adapters |
| `inference` | Tokenization, execution, softmax validation, provenance |
| `aggregation` | Versioned aggregation formulas and availability checks |
| `content` | Explicit local-content save/read/purge policy and recovery |
| `jobs` | Queue, progress, cancellation, recovery, concurrency limits |
| `frontend` | Compiled React assets only; source lives in a separate frontend tree |

No API route reads or writes CSV directly. It calls a service, which validates
the command and uses the storage abstraction. This enforces identical behavior
for UI, API, CLI imports, and startup seed import.

## 4. Authoritative data architecture

The authoritative mutable database is the CSV store described in
`csv-storage-contract.md`. It consists of append-only entity ledgers plus a
transaction ledger. In-memory indexes accelerate reads but are disposable and
are rebuilt from committed CSV rows at startup.

The only exception to physical append-only history is a confirmed local-content
purge, which irreversibly blanks editorial fields under sections 16 and the CSV
purge contract without changing scientific records.

The repository seed release is immutable input. On first startup it is verified
and projected into the local CSV store. The source parts are never edited and
contain empty editorial compatibility fields. New article identifiers and
prediction runs are written only to the configured data directory. Extracted
title/body are written there only after explicit `content_retention=save_local`;
authors and raw HTML are never persisted.

The application shall not use SQLite as a cache, index, queue, or fallback. A
process-local Python index is allowed because CSV remains authoritative and a
restart can reconstruct the exact state.

## 5. Write transaction model

Only one application process may own a data directory. Startup acquires an
exclusive POSIX `flock` on `<data-dir>/.writer.lock` and retains it until clean
shutdown. Failure to acquire it is `STORAGE_LOCKED`.

Every ordinary logical mutation uses this sequence; content purge instead uses
the privacy-monotonic rewrite protocol in section 16:

1. Acquire the process write mutex.
2. Append a `BEGIN` record with a UUID transaction identifier to
   `transactions.csv`; flush and `fsync`.
3. Append all entity versions carrying that transaction identifier; flush and
   `fsync` each affected ledger.
4. Append `COMMITTED` to `transactions.csv`; flush and `fsync`.
5. Apply the committed versions to in-memory indexes.
6. Release the mutex.

Readers expose only rows whose latest transaction state is `COMMITTED`. An
interruption before step 4 leaves invisible rows. Recovery reports and ignores
uncommitted transactions. A malformed final physical row is backed up and
truncated only by the explicit recovery routine before the HTTP server binds.

Multi-ledger consistency is therefore determined by the transaction commit
marker, not by assuming several file appends are atomically simultaneous.

## 6. Read architecture and indexes

Startup streams committed latest record versions into indexes for:

- article by canonical URL and article ID;
- publisher by normalized hostname and publisher ID;
- model by model ID and artifact path;
- all prediction runs and the latest reusable run by `(article_id, model_id)`;
- saved-content presence and article-row offset, without indexing title/body;
- evaluations by publisher, model, method, and time;
- jobs and imports by ID and status;
- case-folded URL and hostname search fields.

Saved title/body are never copied into a search index, cache, job, or normal API
projection. Their dedicated read seeks the current article CSV row using a
byte-offset index. Other detail reads use the same mechanism. The index retains lightweight
`(record_id,record_version,commit_sequence,offset)` history needed to resolve a
pagination snapshot. Pagination sorts by an indexed stable tuple and uses the
commit watermark defined by the API contract.

After a transaction commits, its new versions update indexes synchronously
before the HTTP response reports success. Failed index update is fatal: the
process stops and rebuilds from CSV on restart rather than serving stale state.

## 7. Background execution

The API creates a job in a committed transaction before work is queued. The
executor has separate bounded lanes:

- network/extraction lane: maximum 4 concurrent tasks;
- CPU inference lane: exactly 1 concurrent task;
- GPU inference lane: exactly 1 concurrent task;
- CSV commit lane: exactly 1 writer through the storage mutex.

The exhaustive phase identifiers and ordering rules are defined in Product
Specification section 12. The executor maps retrieval work to `retrieving`,
model execution to `inferring`, and privacy erasure to `purging_content`
followed by `verifying` and `committing`; it shall not emit architecture-only aliases.
Phase and integer progress are persisted at meaningful boundaries, not for
every token or HTTP byte.

On startup, `queued` jobs return to the queue. A job left `running` is appended
as `failed` with `PROCESS_INTERRUPTED`; it is never silently resumed after a
potentially partial model or network operation. The user can retry it as a new
job linked by `retry_of_job_id`.

## 8. URL and publisher identity flow

### 8.1 Offline normalization

For an HTTP(S) URL the application uses Python `urllib.parse` and:

1. trims surrounding whitespace;
2. rejects control characters and every `%` not followed by two hexadecimal
   digits, then parses with `urllib.parse.urlsplit`, rejects user-info, and
   accepts only an explicit case-insensitive `http` or `https` scheme plus a
   non-empty host;
3. lowercases the scheme, lowercases and IDNA-normalizes the hostname, and
   preserves a valid non-default numeric port;
4. removes the fragment;
5. removes default port `80` for HTTP and `443` for HTTPS;
6. normalizes an empty path to `/`;
7. parses the query with `urllib.parse.parse_qsl(keep_blank_values=True)`,
   removes every pair whose key, compared with ASCII case-insensitivity,
   matches `utm_*`, `fbclid`, `gclid`, `mc_cid`, `mc_eid`, or
   `homepageposition`;
8. sorts remaining decoded `(key,value)` pairs lexicographically, preserving
   duplicate pairs, then encodes them with `urllib.parse.urlencode`;
9. does not alter path case, trailing slash, or percent-encoded path data.

Malformed percent escapes, an invalid port, missing host, username/password,
or control character make the URL `INVALID_URL`. A syntactically valid URL with
a scheme other than HTTP(S) is `UNSUPPORTED_SCHEME`. Internationalized
hostnames are stored in lowercase ASCII IDNA form. Query normalization
deliberately normalizes equivalent encodings; it never discards a
non-allowlisted query key.

This normalized candidate is checked locally before any network operation.

### 8.2 Online canonical resolution

Only when the requested control requires current page access and offline mode
is false, retrieval follows at most five safe redirects. A reusable run or
saved validated body can therefore avoid retrieval under the exact product
rules. Relative canonical links are resolved against the
final response URL. The canonical URL is the first document-order
`<link rel="canonical">` whose normalized publisher identity equals that of
the final response; invalid or cross-publisher canonical links are ignored with
a warning. If none qualifies, the final response URL is used. The result is
normalized again and checked locally a second time. Reading a canonical link
does not trigger a request to that link.

### 8.3 Publisher identity

Publisher identity is the canonical article hostname lowercased and
IDNA-normalized with one leading `www.` removed. Other subdomains are preserved
and are different publishers unless an explicit user-managed alias feature is
added after the MVP. Registrable-domain guessing is not used.

## 9. Retrieval safety

The retrieval client:

- accepts only `http` and `https`;
- resolves DNS and rejects loopback, link-local, multicast, unspecified,
  private, and reserved destination addresses before every request and redirect;
- connects only to an address from that validated resolution result, preserves
  the original hostname for HTTP Host/TLS SNI, and verifies the connected peer
  address remains in the approved set, preventing DNS-rebinding between check
  and connection;
- uses the fixed user agent `PublisherReliabilityTool/<version> (+project URL)`;
- respects `robots.txt`; denial is `ROBOTS_DENIED`;
- limits redirects to 5;
- uses 10-second connect and 30-second total response timeouts;
- retries at most twice for connection failures, `408`, `429`, and `5xx`, with
  bounded exponential backoff and `Retry-After` support;
- allows at most one request per second per hostname;
- accepts HTML/XHTML responses only;
- stops after 10 MiB decompressed response body per page;
- never sends cookies, credentials, browser session state, or referrer data;
- uses `httpx` with `trust_env=false`, so ambient proxy/credential environment
  variables cannot bypass destination checks;
- does not bypass access controls or execute page JavaScript.

Robots policy is evaluated for the fixed user agent before each homepage or
article fetch. A successful robots response is parsed with Python
`urllib.robotparser`; an explicit denial is `ROBOTS_DENIED`. HTTP `404` or
`410` means no robots rules. Other robots `4xx`, `5xx`, DNS, TLS, timeout, or
parse failures stop that candidate with the corresponding safe HTTP/network
error rather than assuming permission. One robots result per
`(scheme,hostname,port)` is cached only for the lifetime of the job.

Publisher discovery uses `newspaper3k` only to produce candidate links. Every
candidate still passes URL, hostname, robots, response-size, extraction,
language, and duplicate validation.

`newspaper3k` never performs an unchecked network request. The retrieval
component fetches robots files, homepages, and article HTML through the safe
`httpx` client above, then supplies already downloaded HTML to newspaper's
parsing/building APIs. Redirect and DNS validation therefore cannot be bypassed
by the extraction library.

Response bytes, parsed HTML, titles, author values, and extracted bodies start
in bounded job memory and are never placed in a shared cache or temporary
spool. With `content_retention=discard`, every editorial value is released
before terminal job persistence. With explicit `save_local`, only the extracted
title and validated body may be committed to `articles.csv`; authors and raw
HTML are released in all cases. Prediction-run and job rows never embed any of
these values. The saved body can later be read only through the dedicated
content endpoint or used as inference input under `reuse`; `recompute` ignores
it and retrieves afresh.

When retrieval exists only to add content to an already selected reusable run,
the resolved canonical article ID must equal that run's article ID. Otherwise
the worker commits no content and reports `CANONICAL_IDENTITY_CHANGED`; it does
not attach current page text to an older identity. Missing-run inference and
recomputation instead attach their new run/content to the normally resolved
canonical identity.

Content saving and inference are separate durable subresults. A candidate is a
request success only when it has a selected/created run and, if requested, a
saved validated body. Failure of one does not roll back an already committed
other subresult, and the job reports both states without copying content into
its result.

## 10. Model lifecycle

Artifacts are discovered from configured roots, excluding hidden directories,
temporary files, and symlinks that resolve outside a configured root. Registry
states are:

- `compatible`: artifact and every runtime dependency are ready;
- `historical_only`: virtual imported model identity whose predictions can be
  browsed and aggregated but which has no runnable artifact;
- `dependency_missing`: artifact recognized but base/tokenizer/runtime missing;
- `resource_unavailable`: recognized but required device/resources unavailable;
- `invalid`: expected artifact has a validation failure;
- `unsupported`: no explicit supported recipe or custom manifest.

Only `compatible` models can start inference. `historical_only` models remain
selectable for browsing, reusing/aggregating stored runs, and content-only
enrichment after a run is resolved; they never start inference. Loading is lazy and cached
by model ID. The cache contains at most one large quantized model at a time and
evicts an idle model before another is loaded. Eviction never deletes artifact
files.

Preflight checks disk readability, artifact checksum, expected tensors/config,
base/tokenizer availability, device backend, and a conservative free-memory
estimate. Failure produces a specific state without terminating historical
browsing.

## 11. API and frontend boundary

FastAPI serves:

- `/` and frontend routes with SPA fallback;
- `/assets/*` immutable fingerprinted frontend assets;
- `/api/v1/*` JSON and streaming CSV responses;
- `/api/docs` Swagger UI using locally bundled assets;
- `/api/openapi.json` OpenAPI 3.1;
- `/health/live` process liveness;
- `/health/ready` storage/index readiness.

The frontend never parses CSV directly. It uses documented API resources. API
responses never include unrestricted server paths; artifact paths are displayed
as redacted basename plus configured root label.

## 12. Network exposure and authentication

Native loopback binding requires no login and CORS is disabled because UI and
API are same-origin. The only no-key non-loopback process bind is the official
container's internal `0.0.0.0:8000`, and only when
`PRT_CONTAINER_LOOPBACK_ONLY=true`; the official Compose file simultaneously
publishes that port on host `127.0.0.1` only. This flag is invalid for native
execution—recognized by the absence of the image-baked read-only marker
`/opt/publisher-reliability/.container-image`—and invalid together with an API
key. Its name and startup warning make the trust boundary explicit because the
process cannot inspect the container engine's host publishing rule.

Every other non-loopback `--host` requires an API key of at least 32 random
bytes. The API accepts it only as `Authorization: Bearer <key>`. The frontend
prompts for the key and stores it in session memory only, never local storage or
CSV.

For non-loopback mode, allowed origins must be explicitly configured; wildcard
CORS is rejected. TLS termination is outside the MVP, so documentation labels
non-loopback HTTP as appropriate only for a trusted private network behind a
user-managed secure proxy.

## 13. Native and container deployment

Native execution binds directly to `127.0.0.1`. The container listens on
`0.0.0.0:8000` internally, while Compose publishes
`127.0.0.1:8000:8000` and sets `PRT_CONTAINER_LOOPBACK_ONLY=true`. Compose
mounts:

- `./data:/data` read-write;
- `./models:/models:ro`;
- `./dataset:/app/dataset:ro`;
- an optional Hugging Face cache read-write at `/cache/huggingface`.

The image contains application and frontend assets, not model weights or base
model caches. The service runs as a non-root UID/GID configurable to match the
host. Compose declares one replica and never starts multiple workers.

GPU execution is a separate Compose profile that requests NVIDIA devices. CPU
and GPU profiles use the same image version and CSV directory but must not run
simultaneously because the writer lock prevents it.

## 14. Observability and privacy

Structured JSON logs include timestamp, level, request ID, job ID, phase, error
code, duration, and safe identifiers. They exclude all editorial content, protected
values, API keys, authorization headers, cookies, full upload paths, and model
tensor contents. URLs are logged only at `debug`; normal logs use article ID and
hostname.

Logs rotate at 10 MiB with five retained files. Metrics are available only from
the loopback endpoint `/api/v1/status`; no telemetry leaves the machine.

## 15. Failure strategy

| Failure | Required behavior |
| --- | --- |
| Missing model | History remains usable; evaluation is blocked with setup guidance |
| Missing base/tokenizer | Model is `dependency_missing`; no implicit download during inference |
| Network unavailable | Browsing, run reuse, aggregation, and inference from a saved validated body continue; a retrieval/recompute/discovery operation returns `NETWORK_REQUIRED` or `NETWORK_TIMEOUT` |
| Too few publisher articles | No aggregate unless partial is allowed and at least two succeed |
| Mixed publishers | No publisher evaluation transaction commits |
| Missing probabilities | Hard-class methods remain available; probability mean is disabled |
| CSV tail interrupted | Recovery backs up and removes only the malformed uncommitted tail |
| CSV checksum/schema failure | Readiness fails; no mutation or HTTP serving beyond liveness |
| Process interruption | Running jobs become failed on restart; committed data remains visible |
| Insufficient RAM/VRAM | Preflight fails the job before model load and preserves browsing |
| Frontend build missing | Production readiness fails and the server does not bind |
| Content purge interrupted | Before readiness, recovery idempotently finishes blanking every application-managed live/backup copy; predictions and evaluations remain intact |

## 16. Local-content purge recovery

Content purge is the one documented exception to ordinary append-only entity
history. It is privacy-monotonic: once confirmed, recovery never restores an
older title/body merely to regain transaction symmetry.

With the writer lock held, the worker enumerates the live `articles.csv` and
every application-created CSV backup, writes a verified redacted sibling for
each, fsyncs it and its directory, and atomically replaces that file. The
operation is idempotent. If the process stops after only some replacements,
startup detects the interrupted `content_purge` job, completes the same
redaction across the remaining managed files before readiness, then records a
recovery warning. The old job is still terminally marked `failed` with
`PROCESS_INTERRUPTED`; the deterministic startup recovery is a separate
storage-recovery action, not a resumed job. No unredacted staging copy is left
behind. External user-created copies are outside the managed set and the UI
warns about them before confirmation.

## 17. Architecture invariants

1. CSV is the only authoritative mutable persistence.
2. One data directory has at most one writer process.
3. Uncommitted transaction rows are never visible.
4. UI and API share service and validation logic.
5. `reuse` plus an existing compatible run prevents inference; it also prevents
   article network access unless unsaved content was explicitly requested.
6. A publisher evaluation references exact immutable prediction runs from one
   model.
7. No protected reference field passes the import boundary.
8. Offline mode creates no outbound application connection.
9. Container and native modes produce byte-compatible CSV state.
10. Every externally observable behavior is covered by an acceptance test.
11. Authors and raw HTML never persist; title/body persist only after explicit
    `save_local` and can be physically purged from every managed CSV copy.
