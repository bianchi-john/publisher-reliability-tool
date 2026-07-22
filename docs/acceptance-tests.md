# MVP Acceptance Tests

**Status:** Normative release gate

Every test is automated unless marked as a hardware-specific matrix test. The
MVP is releasable only when native Ubuntu 24.04 and Docker Compose CPU runs pass
the complete applicable suite. Tests inspect observable behavior and CSV state,
not private implementation methods.

## A. Startup and deployment

### AT-001 — Native startup

**Given** a clean supported Ubuntu environment and installed locked package,
**when** `publisher-reliability serve` starts, **then** readiness succeeds, the
terminal prints UI/API/docs URLs, and `127.0.0.1:8000` serves all three.

### AT-002 — Compose startup

**Given** the committed image and Compose file, **when** `docker compose up`
starts, **then** the UI is reachable only through host
`127.0.0.1:${PRT_PORT}`, readiness passes, and the container runs non-root.

### AT-003 — Native/container state compatibility

**Given** state created natively while stopped, **when** the same data directory
is mounted into the same application version in Compose, **then** storage
verification passes and API resources are identical except deployment metadata.

### AT-004 — Graceful shutdown

**Given** queued and running jobs, **when** the process receives `SIGTERM`,
**then** it rejects new jobs, dequeues no queued job, requeues persisted queued jobs on
restart, and gives running work 30 seconds to reach a documented boundary. At
deadline noncommitting work is terminated, any active CSV transaction finishes,
and restart marks only persisted running jobs `PROCESS_INTERRUPTED` without
committed loss.

### AT-005 — Port conflict

**Given** the configured port is occupied, **when** startup runs, **then** it
exits nonzero with one actionable message and creates/modifies no data-directory
file, lock, ledger, recovery artifact, model record, import, or job.

### AT-006 — Missing models

**Given** no compatible artifact, **when** startup completes, **then** browsing
works, model status and the OSF link are visible in terminal/UI, and evaluation
requiring inference returns `MODEL_NOT_FOUND` or a dependency-specific code.

### AT-007 — Missing seed dataset

**Given** no seed dataset and an empty valid CSV store, **when** startup runs,
**then** it serves an empty history and import instructions rather than failing.

### AT-008 — Invalid configuration

**Given** an unknown option, invalid port, malformed boolean, or unwritable data
directory, **when** startup runs, **then** it exits code `2` without accepting
an HTTP request or mutating persistent state. A socket reserved solely to prove
port availability is closed before exit.

## B. CSV storage

### AT-009 — CSV-only authoritative state

**Given** a completed workflow, **when** the data directory is audited, **then**
all authoritative records exist in documented CSV ledgers and no SQLite,
database, browser-storage, or opaque persistent index file is required to
reconstruct the API state.

### AT-010 — Exact headers and physical format

**Given** a fresh store, **when** every ledger is parsed, **then** it is UTF-8,
has the exact version-1 header, uses valid CSV quoting for embedded article
newlines, and every field passes its documented type rule.

### AT-011 — Single writer lock

**Given** one running process owns a data directory, **when** a second native or
container process starts against it, **then** the second fails with
`STORAGE_LOCKED` and neither process corrupts state.

### AT-012 — Transaction visibility

**Given** entity rows whose transaction lacks a `COMMITTED` event, **when** the
store is loaded, **then** none of those rows appear in indexes or API responses.

### AT-013 — Interrupted append recovery

**Given** a final malformed physical row belonging to an uncommitted
transaction, **when** startup recovery runs, **then** it creates a backup,
removes only the malformed tail, records the abort/warning, and passes verify.

### AT-014 — Committed corruption fails closed

**Given** a malformed committed middle row or broken committed foreign key,
**when** startup runs, **then** it exits with `STORAGE_CORRUPT`, closes the
reserved socket, serves no liveness/diagnostic HTTP endpoint, mutates no
authoritative row, and performs no guessed repair.

### AT-015 — Record version semantics

**Given** several committed versions and a final delete for one ID, **when**
current state is read, **then** the highest committed version governs and a
latest `DELETE` makes the record absent.

### AT-016 — Multi-ledger evaluation commit

**Given** a publisher evaluation, **when** its transaction commits, **then** the
evaluation, exact contiguous evaluation-article rows, and job success become
visible together; no partial combination is ever visible.

### AT-017 — Compaction equivalence

**Given** a valid stopped store with old versions and aborted rows, **when**
`storage compact` completes, **then** an independent verify passes and every
current API resource and scientific value matches the pre-compaction snapshot.

### AT-018 — Restart persistence

**Given** locally inferred prediction runs and evaluations, **when** the application
is stopped and restarted, **then** every committed record remains searchable and
the seed import is not duplicated.

## C. Public dataset and imports

### AT-019 — Bundled release verification

**Given** `dataset/predictions/manifest.json`, **when** verification runs,
**then** its one listed part matches size and SHA-256, is below 24 MiB, all
`title`, `text`, and `authors` fields are empty, and the result reports 19,476
source rows, 19,429 released unique URLs, 42 duplicate source groups, and 47
skipped later occurrences.

### AT-020 — Protected source data absent

**Given** forbidden column-name fixtures and canary values unique to each
protected field (not ordinary scalar values such as `0` or `1`), **when** every
bundled/imported projection, ledger, API/UI payload, export, log, and reachable
Git object is audited, **then** no canary is present and no forbidden name exists
outside the explicitly permitted value-free documentation/audit locations. Bundled
and imported editorial fields are empty; runtime title/body can be non-empty
only after auditable `save_local`. Authors/raw HTML are absent.
Blocked column names may appear only in documentation, manifest exclusion
metadata, and value-free warnings.

### AT-021 — Seed import idempotency

**Given** the bundled release was imported, **when** startup repeats, **then**
the first import yields exactly 19,411 canonical articles, 77,708 unique
prediction runs, and 20 historical virtual models; the same content digest and
schema then resolve to the existing import and those counts do not change.

### AT-022 — Streaming large import

**Given** a generated 512 MiB, 600,000-row schema-compatible CSV, a browser
streaming fixture, and a worker cgroup limited to 256 MiB RSS, **when** it is
uploaded/imported with a 1 GiB limit and sufficient disk, **then** peak worker
RSS stays below 192 MiB, the acquired spool reaches exactly 512 MiB, progress is
observable, and browser JS never creates an ArrayBuffer/Blob above 8 MiB.

### AT-023 — Protected user-import projection

**Given** a private source containing allowed fields and blocked provider
columns plus editorial content, **when** import completes, **then** URLs and
model outputs persist, editorial fields are empty, blocked column names appear
in a value-free warning, and blocked/editorial values appear nowhere.

### AT-024 — User-import conflict

**Given** two rows in one user source resolve to one canonical URL with
conflicting outputs for the same model identity, **when** import runs, **then**
the conflict is counted, every occurrence of that article/model key is
rejected, and no run is created for it; the runtime does not apply the bundled
first-occurrence policy. Each source part/data-record and `IMPORT_CONFLICT`
remain queryable after restart without persisting editorial source values.

### AT-025 — Import source immutability

**Given** a source path, **when** import succeeds or fails, **then** its bytes and
mtime are unchanged and its SHA-256 is recorded.

### AT-026 — Archive safety

**Given** a ZIP with multiple CSVs, path traversal, symlink, unsupported member,
or decompressed-size limit violation, **when** import/upload runs, **then** it
fails safely without writing outside upload storage or committing data.

## D. API contract

### AT-027 — OpenAPI completeness

**Given** the running application, **when** `/api/openapi.json` is compared with
the approved snapshot, **then** every documented route, schema, response, and
error envelope matches and no undocumented mutation route exists.

### AT-028 — API/UI shared behavior

**Given** equivalent valid and invalid evaluation inputs, **when** submitted by
API and frontend, **then** they create the same normalized job request or the
same stable validation/error code.

### AT-029 — Pagination stability

**Given** a multi-page article query, **when** new articles commit between page
requests, **then** cursor traversal has no duplicate item, respects its stable
sort boundary, and a cursor with changed filters returns `INVALID_CURSOR`.

### AT-030 — Bounded page sizes

**Given** list requests with absent, allowed, or excessive limits, **when** they
run, **then** default is 25, allowed values are 25/50/100, and others return
`422`.

### AT-031 — Idempotency key

**Given** a mutation request and key, **when** the same body/key is repeated,
**then** it returns the original job/resource; a different body with that key
returns `IDEMPOTENCY_CONFLICT`. The same assertions hold after process restart
and after offline compaction; an expired 30-day record may create a new resource.

### AT-032 — Error privacy

**Given** validation, network, model, and internal failures, **when** API errors
and logs are inspected, **then** credentials, authorization headers, editorial content,
protected values, unrestricted paths, and production stack traces are absent.

### AT-033 — SSE job events

**Given** a running job, **when** a client reconnects with a retained current-
process `Last-Event-ID`, **then** later events are ordered and the job is not
cancelled. After restart or ring eviction, the old ID yields one new full
persisted snapshot and no promise to replay intermediate progress.

### AT-034 — CSV export

**Given** filters returning more than one page, **when** export runs, **then** it
streams the complete filtered set as valid CSV; editorial and protected fields
contain no source values, and `include_text` is rejected as an unknown option.

## E. Local identity and offline behavior

### AT-035 — Offline URL hit

**Given** a stored run for normalized URL and exact model ID, **when** a
tracking-parameter variant is evaluated with `reuse + discard`, **then** it
returns that exact run, records a `reused` job subresult, creates no run, and
makes zero DNS/HTTP calls.

### AT-036 — Offline inference from saved local content

**Given** a known URL with a validated locally saved body but no run for the
selected compatible model, **when** evaluated in strict offline mode with
`reuse + discard`, **then** it creates one run with input source `saved_local`,
makes zero DNS/HTTP calls, and leaves the saved content unchanged.

### AT-037 — Missing local content offline

**Given** an unknown article, or a known article with neither a reusable run nor
saved body, and strict offline mode, **when** `reuse` evaluation runs, **then**
the job fails `NETWORK_REQUIRED`, makes zero outbound calls, and browsing
remains usable.

### AT-038 — Offline frontend

**Given** all external network requests blocked, **when** every frontend route,
chart, and API documentation page is opened, **then** assets load locally and no
CDN, font, analytics, or documentation request leaves the origin.

### AT-039 — Canonical redirect hit

**Given** offline lookup misses but online redirect/canonical resolution reaches
a stored URL, **when** evaluated with `reuse + discard`, **then** the second
lookup reuses the exact stored run and discards already received page bytes
without extraction or inference.

### AT-040 — URL normalization boundaries

**Given** committed fixtures covering IDNA UTS #46, default ports, malformed and
mixed-case percent escapes, fragments, tracking keys, `+`, empty/duplicate query
components, path case and trailing slash, **when** normalized, **then** expected
bytes match exactly: only tracking/default/fragment components change and all
retained query order, duplicates, and encoding remain identity-significant.

### AT-041 — Publisher hostname identity

**Given** `www.example.com`, `example.com`, and `news.example.com`, **when**
normalized, **then** the first two share publisher identity and the third is a
different publisher.

## F. Retrieval and language validation

### AT-042 — Safe article retrieval

**Given** a public HTML article, **when** retrieval runs, **then** redirect,
timeout, response-size, MIME, robots, rate, and user-agent policies are enforced
and exact extracted text is passed unchanged to validation/tokenization.

### AT-043 — SSRF defense

**Given** direct or redirected URLs resolving to private, loopback, link-local,
reserved, multicast, or unspecified addresses, **when** requested, **then** the
job fails before connection and no request reaches that address. A DNS-rebinding
fixture and an ambient proxy environment cannot change the validated connected
peer or bypass the block.

### AT-044 — Extraction failures

**Given** unsupported MIME, body above 10 MiB, parser failure, or empty text,
**when** evaluated, **then** the stable corresponding error is reported and no
prediction commits.

### AT-045 — Short-text rule

**Given** extracted text below 200 characters or below 30 whitespace tokens,
**when** validated, **then** it fails `TEXT_TOO_SHORT` before language detection
or inference.

### AT-046 — Deterministic English validation

**Given** a frozen valid English fixture, **when** detection repeats across
native and container runs with seed zero, **then** result is `en`; non-English
and detector exceptions return their exact codes and never reach inference.

### AT-047 — Publisher candidate filtering

**Given** publisher discovery containing duplicates, other hosts, non-HTML,
short, non-English, and valid articles, **when** processed, **then** only valid
same-host unique articles count and every rejection category is reported.

## G. Evaluation workflows

### AT-048 — Single article

**Given** a valid article, compatible model, and no reusable exact-model run,
**when** single evaluation
with the default `reuse + discard` completes, **then** one immutable article
run with five probabilities commits and no publisher evaluation is created.
API payloads, frontend state, logs, caches, temporary directories, and every
CSV editorial field contain no extracted title, body, author, or raw HTML value
after completion.

### AT-049 — Explicit same-publisher list

**Given** 2–50 distinct same-publisher URLs, **when** all requested prediction
and retention subresults succeed, **then** one evaluation commits with exactly
the ordered prediction-run IDs and selected method.

### AT-050 — Duplicate list input

**Given** submitted URLs that become duplicates after normalization, **when**
validation runs, **then** `DUPLICATE_URL_INPUT` occurs before job creation.

### AT-051 — Mixed publishers

**Given** an explicit list whose canonical URLs contain two publisher
hostnames, **when** processed, **then** the job fails `MIXED_PUBLISHERS`, no
evaluation commits, and already committed individual predictions remain clearly
reported as article outputs only.

### AT-052 — Stored-only publisher request

**Given** enough eligible stored articles, **when** a `stored_only` publisher
request runs, **then** it follows documented deterministic ordering, accepts
only `reuse + discard`, makes zero network calls, and commits an evaluation
using the requested number of existing runs. Any other control combination is
rejected before job creation.

### AT-053 — Stored-first publisher request

**Given** fewer eligible stored articles than requested and network access,
**when** `stored_first` runs, **then** stored predictions are reused first,
saved local bodies that lack the output are inferred next, known stored URLs
still lacking it are retrieved next, and homepage discovery seeks only the
still-missing count.

### AT-054 — Web-only publisher request

**Given** stored history and network access, **when** `web_only` runs, **then**
stored articles are not selected as candidates unless independently rediscovered
as web candidates; exact final URLs remain eligible for cache reuse.

### AT-055 — Partial publisher success

**Given** requested 10 and exactly 6 successful compatible predictions, **when**
`allow_partial=true`, **then** evaluation succeeds with `partial=true`, requested
10, used 6, warning/counters, and exact six contributing predictions.

### AT-056 — Partial publisher rejection

**Given** requested 10 and exactly 6 successes, **when**
`allow_partial=false`, **then** the job fails `REQUESTED_COUNT_UNMET` and no
publisher evaluation commits.

### AT-057 — Insufficient publisher articles

**Given** fewer than two successful predictions, **when** any publisher
aggregation is requested, **then** it fails `INSUFFICIENT_ARTICLES` regardless
of `allow_partial`.

### AT-058 — Stored selection

**Given** 2–50 selected articles on one publisher page, **when** evaluated with
explicit prediction/retention controls, **then** no discovery occurs and only
the selected article IDs and their exact selected/created run IDs can
contribute.

## H. Aggregation

### AT-059 — Paper majority vote

**Given** hard classes `[0, 1, 1, 3]`, **when** `majority_vote` version 1 runs,
**then** result is `Class 1` and counts are stored.

### AT-060 — Majority tie

**Given** hard classes `[1, 3]`, **when** `majority_vote` runs, **then** the tied
smallest class `1` is selected, matching `pandas.Series.mode()[0]`.

### AT-061 — Ordinal mean and rounding

**Given** hard classes `[0, 1, 4]`, **when** `ordinal_mean` runs, **then** raw
mean `1.666666...` is stored, UI displays `1.667`, and result class is `2` using
`floor(mean + 0.5)`.

### AT-062 — Mean probabilities

**Given** complete valid vectors, **when** `mean_probabilities` runs, **then**
each stored component is its arithmetic mean and result is the smallest maximum
component index.

### AT-063 — Missing probabilities

**Given** one included prediction without probabilities, **when** availability
is requested, **then** hard-class methods are enabled,
`mean_probabilities` is disabled with `PROBABILITIES_REQUIRED`, and no vector is
fabricated.

### AT-064 — Exact model compatibility

**Given** predictions from different folds, artifact checksums, recipes, or
tokenizer revisions, **when** aggregation is requested, **then** they cannot be
combined into one evaluation.

### AT-065 — Historical virtual model

**Given** bundled predictions for a historical virtual family/fold, **when**
aggregated, **then** aggregation succeeds; when a missing prediction is requested
from that virtual model, inference fails because it is not runnable. Publisher
`stored_first`, `web_only`, and `recompute` requests with that model are
rejected before inference/network discovery. An explicit article with an
existing historical run may use `save_local` as content-only retrieval without
creating or relabelling a run; a URL still lacking the historical run after
canonical resolution saves no content and fails `MODEL_NOT_RUNNABLE`.

## I. Models

### AT-066 — Official BERT/RoBERTa registration

**Given** an official `.pt` fold and available base/tokenizer, **when** validated,
**then** the embedded official manifest supplies immutable base/tokenizer
revisions and complete scientific identity, and strict tensor keys/shapes plus
frozen reference outputs pass before the model becomes `compatible`.

### AT-067 — Official Llama registration

**Hardware-specific, non-blocking for the CPU release gate.**

**Given** the released fold and authorized cached base, **when** validated,
**then** the exact 4-bit/LoRA/tokenizer recipe and reference fixture pass or the
model remains non-compatible with a specific reason.

### AT-068 — Official Mistral registration

**Hardware-specific, non-blocking for the CPU release gate.**

**Given** a released PEFT fold directory, **when** validated, **then** declared
24B base identity, adapter config, tokenizer, class count, 1,024-token policy,
and reference output pass before compatibility.

### AT-069 — Missing model dependency

**Given** a recognized artifact without base/tokenizer/runtime, **when** scanned,
**then** its deterministic model ID is still computed from the official
manifest, it becomes `dependency_missing`, instructions identify external
provisioning, and no implicit application download starts.

### AT-070 — Insufficient resources

**Given** a valid model without required device or measured memory, **when**
preflight runs, **then** status/job is `resource_unavailable` or
`MODEL_RESOURCE_INSUFFICIENT` before model loading and browsing remains usable.

### AT-071 — Untrusted or ambiguous artifact

**Given** an unrecognized checkpoint or mismatching manifest, **when**
registered, **then** it is rejected without executing embedded code or guessing
architecture/class order.

### AT-072 — Model upload safety

**Given** a streamed valid artifact and sufficient disk, **when** upload and
validation complete, **then** checksum matches and it moves atomically into
managed storage; traversal, link, oversize, and failed artifacts leave no
registered model.

## J. Frontend, security, and privacy

### AT-073 — Minimal navigation

**Given** the frontend, **when** keyboard navigation visits Dashboard, Evaluate,
Articles, Publishers, Imports, Models, and Jobs, **then** every required
capability is reachable, focus is visible, and no icon-only required action
exists.

### AT-074 — State presentation

**Given** loading, empty, offline, no-model, partial, error, and active-job
states, **when** each is rendered, **then** it has explicit English text and an
appropriate corrective or next action.

### AT-075 — Accessible charts

**Given** every probability/distribution/aggregation chart, **when** inspected
without color or canvas access, **then** an adjacent semantic table and text
summary convey the exact same API values.

### AT-076 — Loopback security

**Given** default native and Compose configuration, **when** sockets and CORS
are inspected, **then** host exposure is loopback-only, wildcard CORS is absent,
and no authentication is requested locally.

### AT-077 — Non-loopback rejection

**Given** any native non-loopback bind, **when** startup runs, **then** it fails
before data mutation. The image-internal exception succeeds only with its
immutable marker/flag and the committed Compose file publishes host loopback;
using the flag natively fails.

### AT-078 — No telemetry or external assets

**Given** normal UI/API/model/history use, **when** all network destinations are
captured, **then** no analytics, telemetry, remote font, CDN, or hosted inference
request occurs.

### AT-079 — Scientific warnings

**Given** article and publisher results, **when** detail pages/API resources are
read, **then** they identify model output—not fact checking—probability
calibration limits, exact model/fold, selected articles, and aggregation method.

## K. Performance and release integrity

### AT-080 — Bounded query latency

**Given** 100,000 articles and 400,000 predictions with startup indexes already
built on Ubuntu 24.04, four x86-64 CPU cores, 16 GiB RAM, and local SSD storage,
**when** 20 sequential filtered first-page requests run after one warm-up,
**then** p95 wall time from request send through complete response is at most 2
seconds. A unique 1 MiB saved-content canary appears only in the dedicated
content response and never in normal search/list/detail/export responses; the
test does not inspect private index classes.

### AT-081 — Repository integrity

**Given** every reachable branch, tag, commit, and Git object, **when** audited,
**then** no private full source, model weight, training notebook, protected
reference field/value, credential, or local data directory is present, and
`LICENSE` is Apache-2.0 and `MODEL-OUTPUT-LICENSE.md` applies CC0-1.0 only to
project-owned generated outputs/database arrangement.

### AT-082 — Native/Compose scientific equivalence

**Given** identical frozen UTF-8 text, exact model identity, CPU device class,
float32 logits/softmax, and deterministic algorithms enabled, **when** native
and CPU-container inference run, **then** class matches and each float64-decoded
response probability has absolute error at most `1e-6` and relative error at
most `1e-5` versus the committed reference vector. CUDA/quantized equivalence
is hardware-specific and non-blocking for the CPU gate.

### AT-083 — Full offline smoke test

**Given** strict offline mode, bundled history, and one fully cached compatible
model, **when** a user browses history, aggregates stored predictions, and runs
an exact stored-run lookup plus missing-run inference from a previously saved
body, **then** all succeed and captured outbound connection count is zero; a
missing run without saved content returns `NETWORK_REQUIRED`, and recomputation
is unavailable.

### AT-084 — Evaluation preflight

**Given** existing runs, saved and unsaved known articles, an unknown URL, and
each model state, **when** preflight is called for all three input modes and
control combinations, **then** it performs no DNS/HTTP call or mutation and
returns the exact planned operation, reusable run, content state, network
reason, local publisher counts, and blocking code defined by the API contract.
The frontend renders those facts before confirmation and job submission repeats
validation against current state.

### AT-085 — Immutable recomputation and exact evaluation references

**Given** an existing article/model run, **when** two successful `recompute`
requests use different idempotency keys, **then** each freshly retrieves the
page and creates a distinct UUIDv4 run without updating/deleting the earlier
run. Repeating either request with its original key returns its original job and
run. An evaluation continues to resolve exactly the run IDs committed with it
after newer runs exist and after restart.

### AT-086 — Opt-in content lifecycle

**Given** an unsaved article, **when** `reuse + save_local` is requested and a
run already exists, **then** the page is fetched/validated, only title/body are
saved, no inference/new run occurs, and dedicated content read succeeds while
normal resources/exports remain content-free and the frontend renders it as
inert text. **When** purge is confirmed,
**then** every live CSV version is physically blanked, indexes are rebuilt,
authors/raw HTML never appear, and runs/evaluations remain unchanged. Managed
and external backups are untouched and explicitly reported as requiring manual
deletion; an interrupted live swap finishes idempotently before readiness. A
later `discard` request never purges or replaces previously
saved content. If content-only retrieval resolves to another canonical article,
it returns `CANONICAL_IDENTITY_CHANGED`, saves nothing under the old identity,
and leaves the reused run intact.

## L. Recovery, capacity, and contract completeness

### AT-087 — Compaction crash matrix

**Given** a stopped valid store, **when** compaction is killed before the first
rename, between the two renames, and after swap before cleanup, **then** the next
verify follows the marker/directory matrix, never creates empty ledgers, and
exposes exactly the pre-compaction current resources in every case.

### AT-088 — Full-disk failure safety

**Given** deterministic fault injection that raises `ENOSPC` on each write,
fsync, and rename boundary of upload acquisition, import commit, compaction, and
purge, **when** the operation runs, **then** it returns
`STORAGE_SPACE_INSUFFICIENT`, reports no incomplete success/commit, and verify or
documented marker recovery restores one valid state.

### AT-089 — Upload retry source availability

**Given** one normally failed upload whose terminal cleanup removed its spool
and one process-interrupted upload with an intact matching spool, **when** retry
is requested, **then** the first exposes `retry_available=false` and returns
`SOURCE_NOT_AVAILABLE`, while the second can create one linked retry until its
24-hour expiry. No source is reconstructed from request metadata.

### AT-090 — Exclusive purge and index rebuild

**Given** saved content and concurrent reads, **when** purge runs, **then** it
drains readers, rejects affected reads/all mutations with
`SERVICE_UNAVAILABLE`, swaps verified live state, rebuilds indexes, appends one
purge audit, and subsequently returns content-not-found while historical runs
remain queryable. Backups remain byte-identical.

### AT-091 — Missing artifact preserves history

**Given** a model with persisted runs/evaluations, **when** its artifact is
removed and a scan runs, **then** status becomes `artifact_missing`, runnable
and artifact availability are false, new inference is blocked, and exact old
runs/evaluations remain browseable and aggregable. Relinking identical bytes
restores the same model ID.

### AT-092 — Bounded job queue

**Given** queue maximum 3 and three committed queued jobs held from execution,
**when** two creation requests race, **then** neither can increase queued count
above 3; each rejected request is `503 JOB_QUEUE_FULL` and has no job or
idempotency row.

### AT-093 — Host and Origin defense

**Given** loopback service fixtures, **when** Host/absolute authorities contain
an attacker hostname, wrong port, suffix trick, or DNS-rebinding name, **then**
each is `421 INVALID_HOST`. Browser mutations from cross-site, `null`, or
lookalike origins are `403 ORIGIN_NOT_ALLOWED`; exact same-origin and a
non-browser request without Origin behave as documented.

### AT-094 — Complete error mapping

**Given** the complete API section-3 registry, one public synchronous emitter
fixture for every synchronously reachable code, and terminal-job fixtures for
job-only codes, **when** executed, **then** every synchronous status matches the
registry/OpenAPI; job creation is `202` and every terminal job read is `200`
with its domain code embedded.

### AT-095 — Late import conflict remains atomic

**Given** a large input whose final row conflicts with its first row for the
same article/model, **when** validation completes, **then** no authoritative row
was visible during staging, the conflicting pair creates no prediction run,
all other accepted rows and safe rejection records become visible in one final
transaction, and the writer mutex was not held while reading the source.

### AT-096 — Format-independent dataset digest

**Given** identical ordered projected records encoded as CSV, CSV.GZ,
single-CSV ZIP, manifest directory, and manifest ZIP with varying compression,
filenames, and part boundaries, **when** imported, **then** each computes the
same `prt-dataset-content-v1` digest and historical virtual model IDs; the first
successful digest/schema import is reused by the rest.

### AT-097 — Root and symlink path safety

**Given** artifacts inside/outside configured roots plus file/directory
symlinks, archive traversal entries, changed roots, and retries after relocation,
**when** scan/registration/validate/retry/upload execute, **then** only current
regular non-symlink descendants of configured roots are read, archive links are
rejected, and no API request explores an arbitrary server path.

### AT-098 — Publisher homepage evidence

**Given** publishers first observed from article URLs, a section/query seed, a
failed root fetch, and a successful same-publisher root fetch, **when** records
are read, **then** no `https://hostname/` was invented, the section/query exists
only as `homepage_candidate_url`, failed retrieval leaves resolved URL empty,
and only the successful normalized root becomes `homepage_resolved_url`.

### AT-099 — Local readiness and request preflight

**Given** verified local state but no models, saved bodies, or network access,
**when** readiness is requested, **then** it is `200 ready`. A subsequent
request that needs those resources reports its model/body/network condition in
preflight or job error without changing readiness for available local features.

### AT-100 — Sequential publisher candidate cap

**Given** one publisher job requesting two articles and candidates whose worker
barriers would expose overlap, **when** four network lanes are available,
**then** that job has at most one candidate active, stops scheduling after two
successes, and creates no extra run/content. Separate publisher jobs may occupy
the other lanes.
