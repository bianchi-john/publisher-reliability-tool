# Research Demo Acceptance Tests

**Status:** Normative verification contract

AT-001–AT-045 form the core release gate on a normal CPU workstation.
AT-046–AT-047 are optional GPU tests. AT-048–AT-050 are optional stress/fault
tests. Optional failures are reported but do not block the core demo.

Tests observe public API/UI/CLI behavior and documented CSV files, not private
classes or implementation call graphs.

## A. Core startup and storage

### AT-001 — Native startup

On clean Ubuntu 24.04 with locked dependencies, `publisher-reliability serve`
starts the UI/API/docs on `127.0.0.1:8000` and readiness becomes ready.

### AT-002 — Compose startup

The committed one-service Compose file starts the same demo as non-root and
publishes only `127.0.0.1:8000`.

### AT-003 — Port conflict has no state effect

With the port occupied, startup exits nonzero and creates or changes no data
file, lock, import, model, job, or recovery artifact.

### AT-004 — Empty demo mode

With seed and model directories absent, startup succeeds with empty history,
the official model link, and actionable import/model instructions.

### AT-005 — Single writer and corrupt storage

A second process using the data directory fails `STORAGE_ERROR`. A malformed
middle row or broken reference also fails startup and serves no HTTP endpoint.

### AT-006 — Restarted jobs

After a forced process restart, persisted queued jobs are queued again and jobs
left running become failed with `PROCESS_INTERRUPTED`; committed runs and
evaluations remain visible.

### AT-007 — Seven exact ledgers

A fresh store contains exactly the seven documented CSV ledgers with exact
UTF-8 headers and reconstructs every persisted API resource without another
database.

### AT-008 — Interrupted final append

Given one truncated final physical record in an append-only ledger, startup
backs up that file, removes only the incomplete tail, and verifies successfully.

### AT-009 — Atomic mutable-ledger replacement

Model, job, saved-content, and content-delete updates expose either the old or
new valid complete file when killed before/after atomic rename; a leftover temp
file is not treated as committed state.

### AT-010 — Import marker recovery

Killing import between its three prepared-file replacements causes startup to
roll forward the exact digest-matching run/import/model files once; mismatched
marker data fails `STORAGE_ERROR` rather than guessing.

## B. Dataset and import

### AT-011 — Bundled release verification

The committed manifest verifies part size/SHA-256, content digest, empty
editorial fields, 19,476 source rows, 19,429 released URLs, 42 duplicate groups,
and 47 skipped later occurrences.

### AT-012 — Bundled import identity

First startup produces 19,411 derived articles, 77,708 immutable runs, and 20
historical model identities. Restart returns the existing digest import without
changing those counts.

### AT-013 — Protected user-import projection

A CSV fixture containing valid predictions, editorial values, protected
columns, and unique protected canaries persists only URL/model outputs and
blocked column names. Canary values, title/text/authors, and ground truth are
absent from ledgers, API/UI, logs, and exports.

### AT-014 — Intra-import conflict

If the final occurrence conflicts with an earlier output for the same canonical
article/model, no run for that pair is published; other valid pairs publish and
safe row numbers/counts remain in the import warning.

### AT-015 — CSV and CSV.GZ identity

The same ordered projected records in CSV and CSV.GZ compute the same
`prt-dataset-content-v1` digest; the second import returns the existing import
and creates no runs.

### AT-016 — Upload limits and cleanup

A CSV/CSV.GZ upload within 512 MiB and 300,000 rows is acquired to a private
temporary file and imported; byte, decompressed-byte, or row overflow returns
`PAYLOAD_TOO_LARGE`. Success/failure removes the temporary source. ZIP is
rejected as `INVALID_INPUT`.

## C. API and local boundary

### AT-017 — OpenAPI completeness

Generated OpenAPI contains every documented endpoint, request/response, and
stable error schema and no removed SSE/retry/cancel/compaction/idempotency route.

### AT-018 — Loopback and Host

Native configuration cannot bind non-loopback; Compose publishes host loopback.
Wrong hostname, port, or suffix-trick `Host` returns `421 INVALID_HOST`.

### AT-019 — Simple pagination

List endpoints accept only limits 25/50/100 and non-negative bounded offsets,
return deterministic ordering for one state snapshot, and document that a later
mutation requires refreshing from offset zero.

### AT-020 — Errors and privacy

Each stable synchronous error returns its normative HTTP status and envelope;
failed job reads remain `200`. Errors/logs contain no content, protected values,
credentials, absolute artifact path, or production stack trace.

## D. Offline, identity, and retrieval

### AT-021 — Offline browsing and aggregation

With outbound connections blocked, bundled articles, publishers, runs, imports,
and evaluations can be browsed/exported and stored compatible runs aggregated.

### AT-022 — Strict offline transport

Strict offline mode produces zero DNS/HTTP connection attempts. Reuse and saved-
body inference work locally; a request requiring retrieval fails
`NETWORK_REQUIRED` without changing readiness.

### AT-023 — URL normalization fixtures

Frozen fixtures verify IDNA UTS #46, default ports, fragments, malformed
escapes, tracking-key removal, and preservation of retained query order,
duplicates, `+`, encoding, path case, and trailing slash.

### AT-024 — Retrieval safety

Direct/redirected private, loopback, link-local, reserved, multicast, and
unspecified destinations never receive a connection. Public retrieval enforces
validated peer, redirects, robots, MIME, timeouts, rate, and 10-MiB body limit.

### AT-025 — Extraction and English validation

Frozen HTML passed to `newspaper3k` yields unchanged expected text. Empty/parser
failure is `EXTRACTION_FAILED`, minimum-length failure is `TEXT_TOO_SHORT`, and
seed-zero language validation accepts exact `en` or returns `NON_ENGLISH`.

## E. Evaluation and provenance

### AT-026 — Single-article reuse

Given an exact stored run, default single-article evaluation selects that run,
makes no network/model call, creates no run/evaluation, and reports provenance.

### AT-027 — Explicit recomputation

Two accepted recompute requests freshly retrieve and create two different
immutable UUIDv4 runs. Earlier runs remain queryable.

### AT-028 — Saved local content lifecycle

Without `save_local`, extracted title/body/authors/HTML persist nowhere. With
explicit consent, only title/body appear in `local_content.csv` and dedicated
GET. Confirmed DELETE removes active content, preserves runs/evaluations, and
warns that backups are unchanged. DELETE returns `INVALID_INPUT` while any
evaluation job is running. Content-only retrieval for a reused run performs no
inference and stores nothing if canonical identity changes.

### AT-029 — Explicit article list

Two to fifty distinct same-publisher URLs create one evaluation containing the
exact ordered article/run IDs. Duplicate normalized URLs or mixed publishers
return `INVALID_INPUT` and create no evaluation.

### AT-030 — Publisher evaluation

A publisher request uses eligible stored runs first, then sequential known/new
candidates, stops at requested count, and never creates extra run/content.
With at least two but fewer than requested, `allow_partial=true` records a
partial evaluation; false returns `INSUFFICIENT_ARTICLES`.

### AT-031 — Majority vote

Classes `[0,1,1,3]` yield class 1; tie `[1,3]` yields the smaller class 1.

### AT-032 — Ordinal mean

Classes `[0,1,4]` store `1.666666...`, display `1.667`, and yield class 2 using
`floor(mean + 0.5)`.

### AT-033 — Mean probabilities

Complete vectors are averaged component-wise and smallest maximum index wins.
Any missing vector returns `PROBABILITIES_REQUIRED` without fabricating data.

### AT-034 — Exact compatibility and historical models

Runs with different model IDs/folds/recipes cannot aggregate. Historical
virtual runs can aggregate but a missing historical prediction cannot be
inferred and returns `MODEL_NOT_RUNNABLE`.

## F. Models and reproducibility

### AT-035 — Core BERT/RoBERTa loaders

Each official core fixture validates immutable manifest entry, artifact digest,
strict keys/shapes, tokenizer policy, five probabilities, expected class, and
CPU float32 tolerance before status `compatible`.

### AT-036 — Artifact safety

Unknown, renamed, symlinked, traversal-containing, mismatching, or executable-
code-dependent artifacts never load or create a runnable model. Scans accept no
API path outside configured roots.

### AT-037 — Missing dependency or resource

A recognized model with missing base/tokenizer or device becomes non-runnable
with safe guidance; browsing remains usable and no automatic download starts.

### AT-038 — Missing artifact preserves history

Removing a registered artifact changes availability/runnability only. Its exact
historical runs/evaluations remain browseable and aggregable; restoring identical
bytes restores the same model ID.

### AT-039 — Scientific identity portability

Native and Compose scans of identical scientific resources produce the same
model ID despite different locators; changing any output-relevant manifest,
artifact, tokenizer, revision, class order, padding, adapter, dtype, or
quantization value changes it.

## G. UI, persistence, and repository

### AT-040 — Essential navigation

Dashboard, Evaluate, Articles, Publishers, Models, Imports, and Jobs are keyboard
reachable and present loading, empty, offline, missing-model, partial, and error
states with clear English actions.

### AT-041 — Transparent results

Article/publisher pages show prediction—not fact—warning, exact model/fold/run,
contributing articles, method/version, probability limitations, and accessible
tables containing the same values as charts.

### AT-042 — Export privacy

Article CSV export contains the exact documented header and filtered derived
rows but no title, body, author, HTML, snippet, protected value, or full model
path.

### AT-043 — Job polling

Evaluation, dataset import, and model validation jobs move through only their
documented macro phases and terminal state. The UI observes them by polling;
there is no event, cancel, or retry route.

### AT-044 — Restart persistence

After a clean restart, models, runs, evaluations, imports, jobs, and explicitly
saved content reproduce the same public resources from the seven CSV ledgers.

### AT-045 — Repository and CPU equivalence

Git contains no private source, protected canary, credentials, model weights, or
runtime data. Native/Compose inference over identical frozen text/model on CPU
matches class and reference probabilities within absolute `1e-6`, relative
`1e-5`.

## H. Optional GPU suite

### AT-046 — Optional Llama loader

When authorized base, CUDA, and optional dependencies exist, the pinned 4-bit
LoRA fixture passes. Otherwise it reports unavailable and does not affect the
core gate.

### AT-047 — Optional Mistral loader

When the official PEFT fold, 24B base, CUDA, and optional dependencies exist,
the pinned tokenizer/adapter fixture passes. Otherwise it reports unavailable
and does not affect the core gate.

## I. Optional stress and fault suite

### AT-048 — Demonstrated-scale import

A generated 300,000-row input within 512 MiB imports on a four-core, 16-GiB
workstation without exceeding 4 GiB RSS and reports macro progress; this is a
demo-scale observation, not a larger-input guarantee.

### AT-049 — Filesystem interruption matrix

Fault injection around immutable append, mutable rename, and the two import
marker replacements yields either the old or documented rolled-forward state,
never silent malformed success.

### AT-050 — Disk-full smoke

Representative ENOSPC injection during upload acquisition and atomic
replacement returns `STORAGE_ERROR`, reports no success, and leaves a store that
passes verification after documented temp cleanup/marker recovery.
