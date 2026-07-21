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
**then** it rejects new jobs, reaches a safe boundary within 30 seconds, flushes
CSV, marks unfinished jobs interrupted on restart, and exits without committed
record loss.

### AT-005 — Port conflict

**Given** the configured port is occupied, **when** startup runs, **then** it
exits nonzero with one actionable message and does not modify CSV state.

### AT-006 — Missing models

**Given** no compatible artifact, **when** startup completes, **then** browsing
works, model status and the OSF link are visible in terminal/UI, and evaluation
requiring inference returns `MODEL_NOT_FOUND` or a dependency-specific code.

### AT-007 — Missing seed dataset

**Given** no seed dataset and an empty valid CSV store, **when** startup runs,
**then** it serves an empty history and import instructions rather than failing.

### AT-008 — Invalid configuration

**Given** an unknown option, invalid port, malformed boolean, or unwritable data
directory, **when** startup runs, **then** it exits code `2` before binding HTTP.

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
**when** startup runs, **then** readiness fails with `STORAGE_CORRUPT` and no
automatic guessed repair occurs.

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

**Given** locally inferred predictions and evaluations, **when** the application
is stopped and restarted, **then** every committed record remains searchable and
the seed import is not duplicated.

## C. Public dataset and imports

### AT-019 — Bundled release verification

**Given** `dataset/predictions/manifest.json`, **when** verification runs,
**then** four listed parts match sizes and SHA-256, no part exceeds 24 MiB, and
the result reports 19,476 source rows, 19,429 released unique URLs, 42 duplicate
source groups, and 47 skipped later occurrences.

### AT-020 — Protected source data absent

**Given** every bundled part, local ledger, API response, UI payload, export,
log, and reachable Git object, **when** the protected-data audit runs, **then**
bundled and runtime CSV headers contain no protected source columns and no
original label, score, range, or reference-provider metadata value is present.
Blocked column names may appear only in documentation, manifest exclusion
metadata, and value-free warnings.

### AT-021 — Seed import idempotency

**Given** the bundled release was imported, **when** startup repeats, **then**
the first import yields exactly 19,411 canonical articles, 77,708 unique
predictions, and 20 historical virtual models; the same checksum/schema then
resolves to the existing import and those counts do not change.

### AT-022 — Streaming large import

**Given** a schema-compatible source larger than available browser memory,
**when** it is uploaded/imported, **then** backend memory remains bounded, the UI
shows job progress, and the browser never loads the complete file.

### AT-023 — Protected user-import projection

**Given** a private source containing allowed fields and blocked provider
columns, **when** import completes, **then** allowed records persist, blocked
column names appear in a value-free warning, and blocked values appear nowhere.

### AT-024 — User-import conflict

**Given** two user rows resolve to one canonical URL with conflicting content
or predictions, **when** import runs, **then** the conflict is counted and
rejected; the runtime does not apply the bundled first-occurrence policy. Its
source line and `IMPORT_CONFLICT` code remain queryable after restart without
persisting either conflicting body.

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
returns `IDEMPOTENCY_CONFLICT`.

### AT-032 — Error privacy

**Given** validation, network, model, and internal failures, **when** API errors
and logs are inspected, **then** API keys, authorization headers, article bodies,
protected values, unrestricted paths, and production stack traces are absent.

### AT-033 — SSE job events

**Given** a running job, **when** a client subscribes, disconnects, and resumes
with `Last-Event-ID`, **then** it receives ordered snapshots/progress/terminal
events without duplicating or cancelling the job.

### AT-034 — CSV export

**Given** filters returning more than one page, **when** export runs, **then** it
streams the complete filtered set as valid CSV; article text is absent unless
`include_text=true`, and protected fields are always absent.

## E. Local identity and offline behavior

### AT-035 — Offline URL hit

**Given** a stored prediction for normalized URL and exact model ID, **when** a
tracking-parameter variant is evaluated, **then** it returns the stored output,
records origin `reused`, and makes zero DNS/HTTP calls.

### AT-036 — Stored-text offline inference

**Given** a stored English article with valid text but no prediction for a
compatible local model, **when** evaluated with outbound networking blocked,
**then** inference succeeds from stored text and records `network_used=false`.

### AT-037 — Missing local content offline

**Given** an unknown article or insufficient stored text and strict offline
mode, **when** evaluation runs, **then** the job fails `NETWORK_REQUIRED`, makes
zero outbound calls, and browsing remains usable.

### AT-038 — Offline frontend

**Given** all external network requests blocked, **when** every frontend route,
chart, and API documentation page is opened, **then** assets load locally and no
CDN, font, analytics, or documentation request leaves the origin.

### AT-039 — Canonical redirect hit

**Given** offline lookup misses but online redirect/canonical resolution reaches
a stored URL, **when** evaluated, **then** the second lookup reuses stored output
and does not download/compare article text after the hit.

### AT-040 — URL normalization boundaries

**Given** fragments, default ports, `utm_*`, `fbclid`, `homepagePosition`, path
case, trailing slashes, and semantic query parameters, **when** normalized,
**then** the exact `urllib.parse` algorithm is reproducible, only documented
tracking/default components change, duplicate query pairs survive, and semantic
components remain identity-significant.

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
job fails before connection and no request reaches that address.

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

**Given** a valid article and compatible model, **when** single evaluation
completes, **then** one article prediction with five probabilities commits and
no publisher evaluation is created.

### AT-049 — Explicit same-publisher list

**Given** 2–50 distinct same-publisher URLs, **when** all succeed, **then** one
evaluation commits with exactly the ordered predictions and selected method.

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
request runs with the network blocked, **then** it uses deterministic stored
ordering, makes zero network calls, and commits requested count predictions.

### AT-053 — Stored-first publisher request

**Given** fewer eligible stored articles than requested and network access,
**when** `stored_first` runs, **then** stored candidates are used first and only
the missing count is sought from normalized web candidates.

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

**Given** 2–50 selected articles on one publisher page, **when** evaluated,
**then** no discovery occurs and only the selected article IDs can contribute.

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
`stored_first` and `web_only` requests with that model are rejected before any
network access.

## I. Models

### AT-066 — Official BERT/RoBERTa registration

**Given** an official `.pt` fold and available base/tokenizer, **when** validated,
**then** strict tensor keys/shapes and frozen reference outputs pass before the
model becomes `compatible`.

### AT-067 — Official Llama registration

**Given** the released fold and authorized cached base, **when** validated,
**then** the exact 4-bit/LoRA/tokenizer recipe and reference fixture pass or the
model remains non-compatible with a specific reason.

### AT-068 — Official Mistral registration

**Given** a released PEFT fold directory, **when** validated, **then** declared
24B base identity, adapter config, tokenizer, class count, 1,024-token policy,
and reference output pass before compatibility.

### AT-069 — Missing model dependency

**Given** a recognized artifact without base/tokenizer/runtime, **when** scanned,
**then** it becomes `dependency_missing`, setup instructions identify the
missing dependency, and no implicit inference download starts.

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

### AT-077 — Non-loopback safety

**Given** a non-loopback host without an API key, **when** startup runs, **then**
it fails unless it is the exact documented container flag combination. The flag
is rejected natively. With a valid key and explicit origins, protected API
calls require the Bearer key and wildcard origin remains rejected.

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
**then** p95 server time is at most 2 seconds and article bodies are not scanned.

### AT-081 — Repository integrity

**Given** every reachable branch, tag, commit, and Git object, **when** audited,
**then** no private full source, model weight, training notebook, protected
reference field/value, credential, or local data directory is present, and
`LICENSE` plus `MODEL-OUTPUT-LICENSE.md` exist without claiming rights over
third-party article text.

### AT-082 — Native/Compose scientific equivalence

**Given** identical frozen text, exact model artifact, recipe, and device class,
**when** native and container inference run, **then** class matches and each
probability is within the loader fixture tolerance.

### AT-083 — Full offline smoke test

**Given** strict offline mode, bundled history, and one fully cached compatible
model, **when** a user browses history, aggregates stored predictions, and runs
stored-text inference, **then** all succeed and captured outbound connection
count is zero.
