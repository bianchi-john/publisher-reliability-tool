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
| `api` | Versioned routes, Host/Origin boundary, error envelope, OpenAPI |
| `services` | Shared use cases used by API and startup commands |
| `storage` | CSV schema, transactions, locks, indexes, recovery, compaction |
| `imports` | Bounded upload acquisition, staged dataset verification, and projection |
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
purge, which exclusively rewrites live `articles.csv`; backups are not rewritten
by purge and the user must remove relevant copies manually.

The repository seed release is immutable input. On first startup it is verified
and projected into the local CSV store. The source parts are never edited and
contain empty editorial compatibility fields. New article identifiers and
prediction runs are written only to the configured data directory. Extracted
title/body are written there only after explicit `content_retention=save_local`;
authors and raw HTML are never persisted.

The application shall not use SQLite as a cache, index, queue, or fallback. A
process-local Python index is allowed because CSV remains authoritative and a
restart can reconstruct the exact state.

Dataset/model upload acquisition is operational storage, not authoritative
state: mode-`0600` spools are inaccessible to API reads, bounded by configured
size/free-space checks, and referenced only by their job. Dataset projection
may stage allowlisted rows on disk so the complete source is checked before a
short commit. Terminal cleanup removes source/staging bytes immediately; only
a process interruption may leave a source temporarily available for retry.

## 5. Write transaction model

Only one application process may own a data directory. After successful
loopback socket reservation, startup acquires an
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
truncated only by the explicit recovery routine before the reserved socket is
put into listening mode and any HTTP request can be accepted.

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

The queue admits at most the configured 100 jobs by default. Admission and the
job row commit occur under one mutex, so concurrent requests cannot exceed the
limit. Publisher candidates are sequential within one job; the four network
slots are shared by different jobs.

The exhaustive phase identifiers and ordering rules are defined in Product
Specification section 12. The executor maps retrieval work to `retrieving`,
model execution to `inferring`, and privacy erasure to `purging_content`
followed by `verifying` and `committing`; it shall not emit architecture-only aliases.
Phase and integer progress are persisted at meaningful boundaries, not for
every token or HTTP byte.

On startup, `queued` jobs (which by definition have no started side effect)
return to the queue. A job left `running` is appended as `failed` with
`PROCESS_INTERRUPTED`; it is never resumed. Retry creates a new linked job only
when the persisted safe request is sufficient. Upload retry additionally
requires its acquired source file; terminal cleanup normally makes it
unavailable and forces a new upload.

## 8. URL and publisher identity flow

### 8.1 Offline normalization

For an HTTP(S) URL the application uses Python `urllib.parse` plus the locked
`idna` package and:

1. trims surrounding whitespace;
2. rejects control characters and every `%` not followed by two hexadecimal
   digits, then parses with `urllib.parse.urlsplit`, rejects user-info, and
   accepts only an explicit case-insensitive `http` or `https` scheme plus a
   non-empty DNS host; IPv4/IPv6 literal article hosts are outside the MVP;
3. NFC-normalizes the hostname and applies IDNA UTS #46 non-transitional
   processing with STD3 rules, then lowercases its ASCII result and preserves a
   valid non-default numeric port;
4. removes the fragment;
5. removes default port `80` for HTTP and `443` for HTTPS;
6. normalizes an empty path to `/`;
7. splits the raw query only on `&`, preserving empty components, order,
   duplicates, `+`, and percent-escape case. For the tracking check only, it
   takes bytes before the first `=`, percent-decodes strict UTF-8, and
   ASCII-casefolds them. It drops components whose decoded key starts `utm_` or
   equals `fbclid`, `gclid`, `mc_cid`, `mc_eid`, or `homepageposition`;
8. rejoins retained raw components with `&` without sorting or re-encoding;
9. does not alter path case, trailing slash, percent encoding, query value
   encoding, order, or duplicates.

Malformed percent escapes, an invalid port, missing host, username/password,
or control character make the URL `INVALID_URL`. A syntactically valid URL with
a scheme other than HTTP(S) is `UNSUPPORTED_SCHEME`. Internationalized
hostnames are stored in lowercase ASCII IDNA form. Malformed/non-UTF-8 tracking
keys are invalid rather than guessed; retained non-tracking query components
remain byte-equivalent.

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

A publisher may have a submitted `homepage_candidate_url` without any verified
homepage. `homepage_resolved_url` is stored only after a successful safe fetch
ends on the same publisher with normalized path `/` and no query. Article or
section URLs never cause the application to invent `https://hostname/`.

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

Absent configured roots are skipped. Existing roots are resolved once at
startup and must be readable real directories, not symlinks.
Scan, validate, and retry reject every symlink encountered below a root;
managed uploads reject links before extraction. The API can start a scan of all
configured roots but cannot submit filesystem paths. Registry states are:

- `compatible`: artifact and every runtime dependency are ready;
- `historical_only`: virtual imported model identity whose predictions can be
  browsed and aggregated but which has no runnable artifact;
- `artifact_missing`: a previously registered scientific identity whose
  locator is absent; historical runs remain browseable/aggregable;
- `dependency_missing`: artifact recognized but base/tokenizer/runtime missing;
- `resource_unavailable`: recognized but required device/resources unavailable;
- `invalid`: expected official artifact has a validation failure.

An unknown/ambiguous artifact has no scientific model ID and therefore no
`models.csv` row; scan reports it as an `unsupported` outcome only in the safe
job/CLI result.

Every response separately exposes `artifact_available` and `runnable`. Only
`compatible` records with both true can start inference. `historical_only` and
`artifact_missing` models remain
selectable for browsing, reusing/aggregating stored runs, and content-only
enrichment after a run is resolved; they never start inference. Loading is lazy and cached
by model ID. The cache contains at most one large quantized model at a time and
evicts an idle model before another is loaded. Eviction never deletes artifact
files.

The artifact locator is mutable deployment metadata and is excluded from model
identity. Relinking an identical digest updates the record without changing its
model ID. Preflight checks disk readability, artifact checksum, expected tensors/config,
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

## 12. Loopback request boundary

The MVP binds only `127.0.0.1` or `::1`. The official container may listen on
`0.0.0.0` internally only with the image marker and
`PRT_CONTAINER_LOOPBACK_ONLY=true`, while Compose publishes host loopback
exactly. Every other bind is invalid configuration; API-key/non-loopback mode
is deferred.

Before routing, middleware validates `Host` against the one exact configured
`PRT_PUBLIC_ORIGIN` host and port (default
`http://127.0.0.1:8000`). Absolute-form targets must have the same authority.
Compose passes the host-published port explicitly. Any mismatch is
`421 INVALID_HOST`, preventing DNS rebinding from treating a loopback socket as
an arbitrary-host service.

For unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) a present browser
`Origin` must exactly equal the configured scheme/host/port, and
`Sec-Fetch-Site: cross-site` is rejected. Missing `Origin` remains valid for
non-browser CLI clients. `null`, wildcard, suffix, and sibling origins are not
accepted. CORS response headers are not emitted because the UI is same-origin.

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
model caches. The service runs as the fixed non-root UID/GID `10001:10001`;
writable host mounts are prepared for that identity as defined by the
deployment contract. Compose declares one replica and never starts multiple
workers.

GPU execution is a separate Compose profile that requests NVIDIA devices. CPU
and GPU profiles use the same image version and CSV directory but must not run
simultaneously because the writer lock prevents it.

## 14. Observability and privacy

Structured JSON logs include timestamp, level, request ID, job ID, phase, error
code, duration, and safe identifiers. They exclude all editorial content, protected
values, credentials, authorization headers, cookies, full upload paths, and model
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
| CSV checksum/schema failure | Reserved socket closes; process exits without any HTTP server |
| Process interruption | Running jobs become failed on restart; committed data remains visible |
| Insufficient RAM/VRAM | Preflight fails the job before model load and preserves browsing |
| Frontend build missing | Reserved socket closes and the process exits without accepting HTTP requests |
| Content purge interrupted | Startup completes or rolls forward the live-file swap, rebuilds indexes, and records the audit; backups remain untouched |
| Full disk | Acquisition/maintenance fails before commit with `STORAGE_SPACE_INSUFFICIENT`; a visible commit is never reported without all required fsyncs |

## 16. Local-content purge recovery

Content purge is the one documented exception to ordinary append-only entity
history. The worker takes a service-wide maintenance lock, drains readers,
blocks mutations, writes and verifies a redacted live `articles.csv` sibling,
fsyncs it and the state directory, records a small purge marker, atomically
replaces the live file, rebuilds indexes, and commits `purges.csv` audit state.
The marker makes restart roll forward a completed replacement and never restore
unredacted live content. Backups are deliberately not scanned or rewritten;
the confirmation and terminal result list their directory and manual-deletion
obligation without claiming deletion of open file descriptors or external
copies.

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
   A deny-all transport is injected before startup imports clients, loaders run
   local-files-only, and ambient proxy settings remain disabled.
9. Container and native modes produce scientifically identical CSV state;
   deployment locators may differ and are ignored by compatibility checks.
10. Every externally observable behavior is covered by an acceptance test.
11. Authors and raw HTML never enter authoritative state; title/body persist
    only after explicit `save_local` and can be purged from live state under
    exclusive access, with backup deletion left explicit and manual.
