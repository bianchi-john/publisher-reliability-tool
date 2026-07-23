# Publisher Reliability Tool

Publisher Reliability Tool (PRT) is the local research demo associated with
*From Articles to Publishers: Aggregating Language Model Predictions for News
Source Reliability Inference*. It is a reference implementation for inspecting
released predictions, running compatible article classifiers, and reproducing
publisher-level aggregation. It is not a hosted service or a production data
platform.

The supported path is intentionally short:

```text
install -> start locally -> inspect bundled predictions -> copy model files
-> scan models -> evaluate articles or a publisher -> inspect provenance
```

The application serves one local web UI and REST API at
`http://127.0.0.1:8000`. Docker Compose publishes the same loopback address.
There are no users, authentication, remote deployment mode, reverse proxy
configuration, telemetry, or cloud services.

## Research-demo scope

The core demo provides:

- verification and automatic import of the bundled public prediction release;
- CSV and CSV.GZ user imports through the CLI or local browser;
- browsing of articles, publishers, immutable prediction runs, imports, jobs,
  and publisher evaluations;
- manual placement and scanning of official local model artifacts;
- BERT and RoBERTa CPU inference as the core reproducibility target;
- optional experimental Llama and Mistral loaders when suitable GPU hardware
  and dependencies are already available;
- single-article, explicit article-list, and publisher evaluation;
- `majority_vote`, `ordinal_mean`, and `mean_probabilities` with exact
  contributing prediction-run IDs;
- strict offline mode and persistent essential results in inspectable CSV.

The demo deliberately omits general idempotency keys, SSE, job retry and
cancellation, online compaction, ZIP imports, custom model manifests, automatic
model downloads, public-network binding, accounts, and production-grade
observability or fault recovery.

## Scientific and privacy boundaries

- Results are model predictions, not facts or ground-truth ratings.
- Every run records the exact model/fold and every publisher evaluation records
  the exact immutable runs it used.
- Protected reference-provider labels, scores, ranges, and metadata never enter
  the repository or runtime store.
- Authors and raw HTML are never persisted.
- Extracted title/body are discarded by default and persist only after explicit
  `save_local` consent. They are excluded from ordinary API responses, jobs,
  logs, and exports.
- `reuse` returns the latest exact-model run without creating another run.
  `recompute` always creates a new immutable run.
- Missing historical probabilities remain missing.
- Model artifacts are loaded only by built-in recipes; artifact code is never
  executed.

## Quick start

The normative native reference platform is Ubuntu 24.04, x86-64, Python 3.12.
This repository revision contains the normative contracts, dataset, and dataset
preparation/verification scripts, but not yet the backend, frontend, package,
Compose file, OpenAPI snapshot, dependency lock, or official model manifest.
The commands below are the target application contract and become executable
once those implementation artifacts are added.

With the implementation and locked dependencies present:

```bash
uv sync --frozen
source .venv/bin/activate
publisher-reliability dataset verify ./dataset/predictions
publisher-reliability serve
```

Then open `http://127.0.0.1:8000/`. A missing seed directory or model directory
is allowed; the UI explains how to import data or place official model files.

Docker Compose is an equivalent convenience path:

```bash
docker compose up --build
```

Model artifacts are downloaded manually from:

<https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

Copy supported files under `./models`, then run a scan from the Models page or
the `models scan` CLI command. Restart only refreshes availability of already
registered models; it does not discover new files. The application does not
manage downloads, Hugging Face credentials, or dependency caches.

Strict offline mode is:

```bash
publisher-reliability serve --offline
```

Browsing, reuse, and aggregation of stored results continue to work. Retrieval
or recomputation that requires the network fails with `NETWORK_REQUIRED`.

## Data and extension points

Runtime state lives under `./data/state` in seven CSV ledgers. Prediction runs
and evaluations are immutable append-only records; small mutable ledgers are
rewritten through a temporary file and atomic rename. Articles and publishers
are derived views over prediction runs rather than a second transactional data
model. See `docs/csv-storage-contract.md`.

The implementation is organized around five concrete boundaries:

- `Storage` — CSV loading and atomic writes;
- `ModelLoader` — one explicit loader per supported family;
- `ArticleRetriever` — safe retrieval and extraction;
- `InferenceService` — exact model input and prediction provenance;
- `AggregationMethod` — deterministic publisher formulas.

A researcher extends the demo by adding a Python implementation and fixture at
one of these boundaries, then updating the relevant contract and acceptance
test. There is no plugin framework or universal manifest language.

## Normative documents

| Document | Owns |
| --- | --- |
| `docs/product-specification.md` | Demo scope, workflows, UI, jobs, requirements |
| `docs/architecture.md` | Modules, local process, data flow, extension points |
| `docs/api-contract.md` | Local REST endpoints, schemas, pagination, errors |
| `docs/csv-storage-contract.md` | Seven CSV ledgers, identifiers, write/recovery rules |
| `docs/scientific-contract.md` | Model/input identity, formulas, provenance, warnings |
| `docs/deployment.md` | Native and simple Compose operation |
| `docs/acceptance-tests.md` | Core, optional GPU, and optional stress/fault tests |
| `docs/traceability.md` | Requirement-to-test mapping and precedence |

Owner precedence for an overlapping subject is scientific, storage, API,
deployment, then product. Architecture constrains cross-cutting boundaries but
does not redefine an owner-specific schema or formula. Acceptance tests verify
requirements and do not create new ones.

## Repository data boundary

The only dataset tracked in this repository is the public, prediction-only
release under `dataset/predictions`. Its CSV contains URLs and model outputs,
with empty `title`, `text`, and `authors` compatibility columns; the accompanying
manifest provides integrity and release metadata. Private source data,
source-page content, sample datasets, and model weights are not tracked.

Software and documentation use Apache-2.0. Project-owned model outputs and
database arrangement are dedicated under CC0-1.0 by
`MODEL-OUTPUT-LICENSE.md`; third-party URLs, pages, names, trademarks, models,
and weights are excluded from that dedication.

The demo is releasable when the core CPU acceptance suite passes natively and
with Compose, the bundled dataset verifies, OpenAPI matches the API contract,
and the offline smoke test observes no outbound connection. Optional GPU and
stress/fault suites report separately.
