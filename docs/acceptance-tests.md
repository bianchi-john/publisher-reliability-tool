# Research Demo Acceptance Tests

**Status:** Normative verification contract

AT-001–AT-047 and AT-051–AT-056 form the core release gate on a normal CPU
workstation. AT-048–AT-050 are optional stress/fault tests. Optional failures
are reported but do not block the core demo.

Tests observe public API/UI/CLI behavior and documented CSV files, not private
classes or implementation call graphs.

## A. Core startup and storage

### AT-001 — Native startup

On clean Ubuntu 24.04 with locked dependencies, `publisher-reliability serve`
validates paths, reserves the port, initializes/verifies state, imports the seed,
scans models, then starts UI/API/docs on `127.0.0.1:8000`; the first accepted
readiness request is ready and no startup live-but-not-ready phase is exposed.

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
middle row, broken reference, or existing partial/misnamed seven-ledger state
also fails startup, creates no missing ledger, and serves no HTTP endpoint.

### AT-006 — Restarted jobs

On shutdown, admission stops and the process exits within five seconds even if
non-cancellable work remains. After restart, queued evaluations and queued
upload jobs with intact acquired sources are queued again; queued upload jobs
without source and all jobs left running become failed with
`PROCESS_INTERRUPTED`. Committed rows remain visible even if their job is
failed.

### AT-007 — Six exact ledgers

A fresh store contains exactly the seven documented CSV ledgers with exact
UTF-8 headers and reconstructs every persisted API resource without another
database.

### AT-008 — Corrupt final append fails closed

Given one truncated final physical record in an append-only ledger, startup
returns `STORAGE_ERROR`, changes no authoritative row, and serves no endpoint.

### AT-009 — Atomic mutable-ledger replacement

Model, job, saved-content, and content-delete updates expose either the old or
new valid complete file when killed before/after atomic rename; a leftover temp
file is not treated as committed state.

### AT-010 — Interrupted import is idempotent

Killing import between deterministic model/run/import replacements may leave
that committed prefix visible. Restart retries an incomplete bundled import;
resubmitting the same user source converges to one import identity and one run
per article/model without duplicates. No custom transaction marker is claimed.

## B. Dataset and import

### AT-011 — Bundled release verification

The committed schema-2 manifest verifies part size/SHA-256, the stable
original-row content digest, empty editorial fields, 17,283
`dataset_original` rows, BERT/RoBERTa-only original columns, complete
finite five-class probability vectors for both families, and the exact count
and shape of any `user_evaluation` rows.

### AT-012 — Bundled import identity

First startup produces 17,269 derived articles, 34,564 immutable runs, and 10
historical BERT/RoBERTa model identities over 372 publishers, none with fewer
than 20 classified articles. Every run has five probabilities.
Restart returns the existing digest import without changing those counts.

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

With outbound connections blocked, bundled articles, publishers, runs and
imports can be browsed and exported offline, and a publisher class can still be
derived from the stored runs.

### AT-022 — Strict offline transport

Strict offline mode produces zero DNS/HTTP connection attempts. Stored-run
reuse, browsing, and aggregation work locally; a request requiring retrieval fails
`NETWORK_REQUIRED` without changing readiness.

### AT-023 — URL normalization fixtures

Frozen fixtures verify IDNA UTS #46, default ports, fragments, malformed
escapes, tracking-key removal, and preservation of retained query order,
duplicates, `+`, encoding, path case, and trailing slash.

### AT-024 — Retrieval safety

Direct/redirected private, loopback, link-local, reserved, multicast, and
unspecified destinations are rejected before an application request. Public
retrieval disables environment proxies and enforces hop validation, five
redirects, HTML MIME, timeouts, and an 8-MiB decompressed body limit.

### AT-025 — Extraction and English validation

The request contains `Accept-Language: en-US,en;q=0.9`. Frozen HTML passed to
Newspaper3k uses `language="en"` and no secondary extractor. Newspaper3k parser
failure is `EXTRACTION_FAILED`, minimum-length failure is `TEXT_TOO_SHORT`, and
seed-zero language validation accepts exact `en` or returns `NON_ENGLISH`.

## E. Evaluation and provenance

### AT-026 — Single-article reuse

Given an exact stored run, default single-article evaluation selects that run,
makes no network/model call, creates no run/evaluation, and reports provenance.

### AT-027 — Explicit recomputation

Two accepted recompute requests freshly retrieve and create two different
immutable UUIDv4 runs. Earlier runs remain queryable. Each new run appears
exactly once in the private, git-ignored
`dataset/predictions/user-predictions.csv` with
`prediction_origin=user_evaluation`, matching run/model/fold/label and all five
probabilities; restarting adds no duplicate, and the tracked
`dataset/predictions/predictions.csv` release is never modified.

### AT-028 — Saved local content lifecycle

Without `save_local`, extracted title/body/authors/HTML persist nowhere. With
explicit consent, only title/body appear in `local_content.csv` and dedicated
GET. Confirmed DELETE removes active content, preserves prediction runs, and
warns that backups are unchanged. DELETE returns `INVALID_INPUT` while any
evaluation job is running. Content-only retrieval for a reused run performs no
inference and stores nothing if canonical identity changes.

### AT-029 — Explicit article list

Two to fifty distinct same-publisher URLs create one evaluation containing the
exact ordered article/run IDs. Duplicate normalized URLs or mixed publishers
return `INVALID_INPUT` and create no evaluation. Candidates run in submitted
order; URLs converging to one canonical article also fail. Any later failure
leaves earlier article-level runs/content valid but creates no evaluation.

### AT-030 — Derived publisher class

A publisher class is read from stored runs and never written: the request creates
no row in any ledger. Each model is counted separately over its own leakage-safe
articles and never mixed with another model's predictions. Changing the counting
rule, or excluding articles, changes the reported class without changing stored
data; fewer than two counted articles reports no class for that model. Evaluating
several articles as one operation is not offered by the API or the interface.

### AT-031 — Majority vote

Classes `[0,1,1,3]` yield class 1; tie `[1,3]` yields the smaller class 1.

### AT-032 — Ordinal mean

Classes `[0,1,4]` store `1.666666...`, display `1.667`, and yield class 2 using
`floor(mean + 0.5)`.

### AT-033 — Mean probabilities

Complete vectors are averaged component-wise and smallest maximum index wins.
The importer rejects a missing vector; corrupted legacy state still returns
`PROBABILITIES_REQUIRED` without fabricating data.

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
API path outside configured roots. Killing a validated upload after its atomic
move but before model-ledger registration leaves a non-runnable, unregistered
candidate; restart ignores it and only a later explicit full scan may register
it.

### AT-037 — Missing dependency or resource

A recognized model with missing base/tokenizer or device becomes non-runnable
with safe guidance; browsing remains usable. Online first use may acquire only
the pinned official tokenizer/configuration files, while offline first use
returns `NETWORK_REQUIRED` if they are not already cached.

### AT-038 — Missing artifact preserves history

Removing a registered artifact changes availability/runnability only. Its exact
historical runs remain browseable and aggregable; restoring identical
bytes restores the same model ID. Restart refreshes availability of that known
locator but does not discover an unrelated newly copied artifact until scan.

### AT-039 — Scientific identity portability

Native and Compose scans of identical scientific resources produce the same
model ID despite different locators; changing any output-relevant manifest,
artifact, tokenizer, revision, class order, padding, adapter, dtype, or
quantization value changes it.

## G. UI, persistence, and repository

### AT-040 — Essential navigation

Evaluate, Articles, Publishers, Models, and Jobs are keyboard reachable and
present loading, empty, offline, missing-model, partial, and error states with
clear English actions. The top-bar status control opens a keyboard-reachable
popover with workspace counts and runtime details. Articles exposes distinct dataset and
user-evaluated filters/badges derived from run origin rather than URL heuristics.
An imported article with a later local run remains dataset-backed and also
shows the user-evaluated badge. The UI exposes one light palette with the
system Times New Roman font throughout, no theme
control, no dark mode, and no remote font or style dependency. Route changes
keep the top bar mounted, keep its first navigation item visible, and do not
collapse page height or scrollbar space.

### AT-041 — Transparent results

Evaluate and article/publisher pages show prediction—not fact—warning, predicted
class, all five available probabilities, exact model/fold/run, dataset or user
origin, contributing articles, method/version, and accessible tables containing
the same values as visual probability bars. Recent local article predictions
remain visible in Evaluate after refresh.

### AT-042 — Export privacy

The prediction CSV export contains the exact documented header and one filtered
row per stored prediction run, each naming its model and carrying all five class
probabilities, but no title, body, author, HTML, snippet, protected value, or
full model path.

### AT-043 — Job polling

Evaluation, dataset import, and model validation jobs move through only their
documented phases and terminal state, and reported progress never moves
backwards. Evaluation reports each slow step so the progress bar advances
gradually instead of jumping from start to completion. The UI observes them by
polling;
there is no event, cancel, or retry route. Equivalent CLI verify/import/scan
commands execute synchronously and create no job requiring a server worker.

### AT-044 — Restart persistence

After a clean restart, models, runs, imports, jobs, and explicitly
saved content reproduce the same public resources from the six CSV ledgers.
Mirrored `user_evaluation` dataset rows restore a missing local run and are then
resynchronized idempotently; original rows and their stable content digest are
unchanged.

### AT-045 — Repository and CPU equivalence

Git contains no private source, protected canary, credentials, model weights, or
runtime data. Native/Compose inference over identical frozen text/model on CPU
matches class and reference probabilities within absolute `1e-6`, relative
`1e-5`.

## H. Custom Transformer import

### AT-046 — Valid custom Transformer import

A custom allowlisted five-label encoder bundle installs below
`managed-models/<model_id>`, is marked `user_custom`, registers exact
digest/input/fold provenance and deletes the upload. It then produces a
five-probability local run. Importing one of the study's larger decoder
checkpoints, by upload or by LoRA-adapter bundle, is refused with
`FEATURE_UNAVAILABLE` and registers nothing.

### AT-047 — Unsafe or incompatible custom bundle

Traversal, absolute paths, links, decompression overflow, Python/native/pickle
files, `auto_map`, `trust_remote_code`, unknown manifest fields, missing local
tokenizer, unsupported base/model types, labels other than five, invalid fold
convention, non-finite values, or strict key/shape mismatch fail without
registration or an installed bundle.

## I. Optional stress and fault suite

### AT-048 — Demonstrated-scale import

A generated 300,000-row input within 512 MiB imports on a four-core, 16-GiB
workstation without exceeding 4 GiB RSS and reports macro progress; this is a
demo-scale observation, not a larger-input guarantee.

### AT-049 — Filesystem interruption matrix

Fault injection around immutable append and mutable rename yields either a
complete row/file or a fail-closed store. Interrupted multi-file import is
resolved by resubmitting the same deterministic source.

### AT-050 — Disk-full smoke

Representative ENOSPC injection during upload acquisition and atomic
replacement returns `STORAGE_ERROR` and reports no success. Any partial
multi-file import is resolved by resubmitting the same source.

## J. Fold-safe evaluation availability

### AT-051 — Local inventory intersection

Given only local BERT fold 1 and RoBERTa fold 1 checkpoints, availability never
offers absent custom families or folds 2–5. A held-out fold-1 dataset article
offers the two matching stored identities while preserving separate local and
historical model IDs.

### AT-052 — Training-data leakage guard

Given a known article assigned to test fold 2, local BERT/RoBERTa fold 1 are
hidden with `TRAINING_DATA_LEAKAGE`. A checkpoint of any family is blocked for
that article on the same evidence, because fold membership is recorded per
article rather than per family. Direct service/API attempts to infer with those
checkpoints also fail with that code. Publisher and explicit-list
workflows exclude or reject the same unsafe article; fold-1 held-out articles
remain eligible. A local inference over an external URL does not add that URL
to the imported fold registry and therefore cannot manufacture a later leakage
block. If normalization maps one article identity to more than one imported fold, its
stored runs remain consultable but every checkpoint is blocked for direct
evaluation and the identity is excluded from publisher aggregation.

### AT-053 — Availability explanation

A new URL absent from stored history offers every runnable local model with mode
`new_inference`; when none is runnable it returns
`NEW_ARTICLE_REQUIRES_INFERENCE`. Other empty states distinguish no local
checkpoints and no matching family/fold. Evaluate presents one article URL and
one model, with no publisher count, aggregation method or partial-result
control, because a publisher class is read on the Publishers page instead of
being requested here. Checkpoints withheld by the leakage guard are named
beneath the selector.

### AT-054 — Bundled release replacement

Starting with the obsolete four-family bundled import and then loading the
current manifest removes old bundled runs, their unreferenced historical model
identities and the obsolete bundled import row. It then imports exactly 34,564
BERT/RoBERTa runs. No stored publisher aggregate has to be removed, because none
is ever written. User imports, their models and runs, saved content, jobs and local
checkpoint registrations are unchanged.

### AT-055 — Local evaluation purge

A confirmed bulk purge deletes every `local_inference` run, all saved content,
and the private prediction mirror in one operation, while every
`bundled_import`/`user_import` run, its model identities, and the tracked
release remain unchanged. It returns `INVALID_INPUT` while any evaluation job
is running or the typed confirmation does not match, and its response counts
exactly what was removed. After a restart, none of the purged rows returns,
because the mirror that would have restored them was removed before the
ledger, not after.

### AT-056 — Unconfirmed job-history clear

Clearing job history takes no confirmation and no request body, unlike the
purges above: one action deletes every job row and reports how many were
removed. It returns `INVALID_INPUT` and removes nothing while any job is
`queued` or `running`.
