# Product Specification

**Status:** Normative research-demo MVP contract

## 1. Purpose and audience

Publisher Reliability Tool is a single-user local reference implementation for
the paper's article classification and publisher aggregation workflow. Its
audience is a researcher running the demo on one workstation, inspecting its
provenance, or extending its code.

It is not a SaaS product, public server, multi-user system, high-availability
service, or long-lived organizational database. Simplicity and scientific
transparency take precedence over production-scale throughput and exhaustive
fault tolerance.

## 2. Supported environment

- Native reference: Ubuntu 24.04 LTS, x86-64, Python 3.12.
- Container reference: one Docker Compose service on x86-64 Linux.
- Browser: current or previous Firefox/Chromium release.
- Address: `http://127.0.0.1:8000`; non-loopback binding is unsupported.
- One process, one worker thread for long jobs, one data-directory writer, and
  one local user.
- Demonstrated scale: the bundled dataset and compatible user imports up to
  300,000 source rows and 512 MiB compressed/upload bytes. Larger inputs are
  unsupported rather than promised to stream at arbitrary scale.

## 3. Included scope

The MVP shall:

- start through one native command or a simple Compose service;
- serve a local React UI, REST API, OpenAPI document, and health endpoints;
- verify/import the bundled public prediction manifest on first startup;
- import user CSV or CSV.GZ files after safe projection and validation;
- persist essential models, runs, evaluations, imports, jobs, and explicitly
  saved local content in seven inspectable CSV ledgers;
- derive article and publisher views from persisted prediction runs;
- scan configured model roots and accept browser uploads of supported official
  artifacts;
- provide BERT and RoBERTa as the core CPU demo;
- expose Llama and Mistral only as optional experimental GPU loaders;
- evaluate one article, 2–50 explicit same-publisher articles, or one publisher
  with a requested count of 2–50;
- reuse exact stored runs or explicitly create a new immutable run;
- aggregate exact compatible runs with the three scientific methods;
- display exact model/fold/run/article provenance and scientific warnings;
- work offline for browsing, reuse, and stored aggregation;
- optionally retain extracted title/body with explicit per-request consent.

## 4. Explicitly excluded or deferred

- public/private-network hosting, authentication, users, configurable CORS,
  reverse proxies, TLS, or remote administration;
- general `Idempotency-Key` support, persistent event streams, job retry,
  cancellation, queue priorities, or parallel candidates within one job;
- storage compaction, record versioning, commit watermarks, transactional CSV
  database semantics, automatic backup retention, or online maintenance;
- ZIP import, generic archive manifests, API import from a server path, or
  arbitrary import roots;
- generic custom-model manifests, plugins, runtime code loading, automatic
  downloads, credential management, or cache management;
- model training, tuning, calibration, automatic ensembling, hosted inference,
  telemetry, analytics, or production metrics;
- automatic deletion from user backups or external copies;
- a hard latency SLA or mandatory GPU release gate.

## 5. CLI

The stable MVP surface is:

```text
publisher-reliability serve [OPTIONS]
publisher-reliability dataset verify PATH
publisher-reliability dataset import PATH
publisher-reliability models scan
publisher-reliability storage verify
```

`serve` options:

| Option | Default | Meaning |
| --- | --- | --- |
| `--port` | `8000` | Loopback port `1..65535` |
| `--data-dir` | `./data` | CSV state, lock, temporary uploads, logs |
| `--models-dir` | `./models` | Repeatable configured model root |
| `--seed-dataset` | `./dataset/predictions` | Bundled manifest directory; missing is allowed |
| `--offline` | false | Deny all application HTTP retrieval |
| `--device` | `auto` | `auto`, `cpu`, or `cuda` |
| `--log-level` | `info` | `debug`, `info`, `warning`, `error` |

The host is fixed to `127.0.0.1`. `dataset verify` accepts CSV, CSV.GZ, or the
official manifest directory and changes no state. `dataset import` accepts CSV
or CSV.GZ and uses the same importer as the UI. `models scan` scans configured
roots only. `storage verify` checks headers, row types, identifiers, references,
and malformed final rows. There is no compaction or migration command in schema
version 1.

Exit codes are `0` success, `2` invalid configuration/input, `3` invalid
dataset/storage, and `1` unexpected runtime failure.

## 6. Startup and shutdown

Startup order is:

1. parse configuration;
2. bind and retain the loopback socket without accepting requests, proving the
   port is available before data-directory mutation;
3. acquire the exclusive data-directory lock;
4. create a fresh seven-ledger store or verify the existing one;
5. remove an incomplete final physical row only from an append-only ledger;
   any other structural corruption fails startup;
6. verify/import the optional bundled release by content digest;
7. load lightweight indexes and model records;
8. requeue `queued` jobs and mark jobs left `running` as
   `PROCESS_INTERRUPTED`;
9. start the single long-job worker and HTTP serving.

Missing seed/models are valid empty/history-only modes. An occupied port causes
no data mutation. Corrupt storage closes the reserved socket and starts no HTTP
server.

On `SIGINT`/`SIGTERM`, new jobs stop being accepted. The current macro-step is
allowed up to 30 seconds to finish; the process never exits during an atomic
file replacement or CSV row fsync. A still-running job is marked interrupted on
the next startup. No attempt is made to resume partially executed inference.

## 7. Main research workflow

### 7.1 Bundled history

On first startup the official manifest and part checksums are verified. Its
normalized runs are imported once by `(content_sha256, schema_version)`.
Articles and publishers are views derived from those runs.

### 7.2 Models

The researcher manually downloads official artifacts, copies them below a
configured model root, and starts a scan. Scan/validation is a
`model_validation` job because checksums and reference fixtures can be slow.
The Models page reports compatible, dependency-missing, resource-unavailable,
artifact-missing, and historical-only identities. It never downloads anything.

BERT/RoBERTa CPU behavior is part of the core gate. Llama/Mistral are optional
and may remain unavailable without failing the demo.

### 7.3 Evaluation controls

Every evaluation has:

- `prediction_action`: `reuse` (default) or `recompute`;
- `content_retention`: `discard` (default) or `save_local`.

`reuse` selects the latest exact-model run by effective completion time
descending then run ID ascending. If absent, a runnable model uses saved local
text or retrieves the page. `recompute` always retrieves and creates a new run.
`save_local` stores only validated title/body and never changes which run is
selected. With an existing run but no saved content, `reuse + save_local`
retrieves/validates content without inference; the resolved canonical article
must still equal the run's article or nothing is saved. `discard` never deletes
content saved by an earlier request.
Content is committed only after an exact run has been selected or created, so
`local_content.csv` cannot introduce an article absent from run history.

Single-article evaluation creates no publisher aggregate. Explicit lists must
contain 2–50 distinct URLs that resolve to one publisher. Publisher evaluation
uses stored compatible runs first, then known URLs requiring inference, then
simple homepage discovery until the requested count is reached or candidates
end. Candidates are processed sequentially. `allow_partial=true` permits an
aggregate with 2..requested successful runs; otherwise an unmet count fails.

Every evaluation stores the ordered article and prediction-run IDs actually
used. A later run cannot change an earlier evaluation.

### 7.4 Import

The API accepts one CSV or CSV.GZ upload. It writes a private temporary file,
computes its SHA-256, enforces the byte/row limits, parses incrementally, and
stages only allowlisted projected values. After complete validation it publishes
accepted immutable runs and one import record. The temporary file is then
deleted.

The user schema requires `url` and at least one model family's predicted class
and fold. `title`, `text`, `authors`, source-local ID, and domain are optional;
editorial values are discarded and domain is recomputed. Conflicting outputs
for the same canonical article/model in one source reject that pair before
publication. A repeated successful content digest returns the existing import.
The selected source file is never modified.

### 7.5 Saved content and purge

Saved title/body live only in `local_content.csv` and are returned only by the
dedicated content endpoint. A synchronous confirmed delete is accepted only
when no evaluation job is running, then rewrites that small ledger through a
temporary file and atomic rename. It affects active state only. User-created
backups and external copies must be deleted manually.

## 8. Jobs and UI

Only operations that can take noticeable time are jobs.
The persisted job-type registry is: `evaluation`, `dataset_import`, `model_validation`.
Status is
`queued`, `running`, `succeeded`, or `failed`. Progress is an approximate
integer `0..100` updated at these macro phases only:

- evaluation: `preparing`, `retrieving`, `inferring`, `aggregating`, `saving`;
- import: `parsing`, `validating`, `saving` (upload reception precedes job
  creation);
- model validation: `scanning`, `validating`, `testing`, `saving`.

One FIFO worker executes jobs. The frontend polls the job endpoint every two
seconds; SSE, cancellation, and retry are absent. After restart, queued jobs run
again from their persisted request; running jobs fail as interrupted.

The UI has Dashboard, Evaluate, Articles, Publishers, Models, Imports, and Jobs.
It favors provenance and scientific explanation over administration. Charts
have adjacent semantic tables. Loading, empty, offline, missing-model, partial,
and error states use clear English text.

## 9. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-001 | Native and Compose startup shall expose the same loopback-only demo. |
| FR-002 | The bundled prediction release shall verify and import once by content digest. |
| FR-003 | User CSV/CSV.GZ imports shall project only allowed scientific fields and reject intra-import conflicts before publication. |
| FR-004 | Protected ground truth, authors, and raw HTML shall never persist or appear in ordinary output. |
| FR-005 | Title/body shall persist only after explicit `save_local` and active-state deletion shall be available. |
| FR-006 | Article and publisher history shall remain browsable and aggregable offline. |
| FR-007 | `reuse` shall select the latest exact-model immutable run without creating another run. |
| FR-008 | `recompute` and missing-run inference shall create new immutable runs with exact provenance. |
| FR-009 | Every publisher evaluation shall reference the exact ordered runs and articles used. |
| FR-010 | The three aggregation methods shall implement the scientific formulas and availability rules exactly. |
| FR-011 | Missing historical probabilities shall remain missing. |
| FR-012 | Exact model identity shall include every output-relevant setting and exclude filesystem location. |
| FR-013 | Only built-in safe loaders shall read artifacts; artifact code shall never execute. |
| FR-014 | BERT and RoBERTa shall form the core CPU demo; Llama and Mistral shall be optional. |
| FR-015 | New web inference shall use safe retrieval, unchanged extracted text, and deterministic English validation. |
| FR-016 | Strict offline mode shall prevent every application-initiated outbound HTTP request. |
| FR-017 | Essential state shall survive restart in the seven documented CSV ledgers. |
| FR-018 | Long operations shall use the three simple persisted job types and polling. |
| FR-019 | The local API shall validate Host and reject non-loopback configuration. |
| FR-020 | UI and API shall expose model, fold, run, contributing articles, method, and scientific limitations. |

## 10. Non-functional requirements

| ID | Requirement |
| --- | --- |
| NFR-001 | The main workflow and module boundaries shall be understandable without distributed-systems or database-internals knowledge. |
| NFR-002 | The UI shall remain usable with the bundled dataset on a typical four-core, 16-GiB research workstation; no hard latency SLA applies. |
| NFR-003 | Dependency locks, dataset checksums, and core model fixtures shall make the demo reproducible. |
| NFR-004 | CSV writes shall use one writer, fsync, and atomic replacement or append-tail recovery as documented. |
| NFR-005 | Logs and errors shall exclude editorial content, protected data, credentials, and unrestricted paths. |
| NFR-006 | Frontend assets and API documentation shall be bundled locally without telemetry or CDN dependencies. |
| NFR-007 | User-visible text, errors, and exports shall be English and accessible. |
| NFR-008 | API and frontend shall share the same service and validation functions. |

## 11. Release gate

The core release suite runs on a normal CPU workstation natively and with
Compose. Optional GPU and stress/fault tests report separately. Passing the core
gate demonstrates scientific correctness, privacy, essential persistence,
import, inference, aggregation, local startup, and offline behavior; it does
not certify the demo for public or production deployment.
