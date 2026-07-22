# Publisher Reliability Tool

This repository is the normative specification and public prediction dataset
for a local application derived from the paper *From Articles to Publishers:
Aggregating Language Model Predictions for News Source Reliability Inference*.

The application runs on Linux, starts from a terminal either natively or with
Docker Compose, and exposes the same functionality through:

- a browser interface at `http://127.0.0.1:8000/`;
- a versioned local REST API under `http://127.0.0.1:8000/api/v1`;
- interactive API documentation at `http://127.0.0.1:8000/api/docs`.

All model inference and persistent state remain local. Internet access is used
only when a request cannot reuse a stored run or user-saved local body, when an
explicit recomputation needs a fresh page, when publisher discovery needs URLs,
or when the user explicitly downloads a missing model dependency.

## Locked MVP decisions

- **Runtime:** Python 3.12, FastAPI, Uvicorn, React, TypeScript, Vite, and
  Chart.js. Frontend assets are built into and served by the backend; no CDN is
  used.
- **Deployment:** native Linux and a single-container Docker image orchestrated
  by Docker Compose. Both expose the same CLI, API, UI, and data formats.
- **Binding:** native execution binds to `127.0.0.1:8000`; Compose publishes
  container port `8000` only on host address `127.0.0.1`.
- **Persistence:** the authoritative local database is a set of UTF-8 CSV
  ledgers under the configured data directory. SQLite and other database
  engines are outside the MVP.
- **Bundled history:** `dataset/predictions/manifest.json` and its ordered CSV
  parts are verified and imported idempotently on first startup.
- **Models:** official or explicitly configured compatible artifacts are loaded
  from local paths. The program never trains models.
- **Language:** software text and API messages are English; newly inferred
  articles must be detected as English.
- **Identity:** an article is identified by its canonical URL, a publisher by
  its normalized hostname, a model by its exact artifact/recipe identity, and
  each immutable prediction run by its own run ID plus article/model IDs.
- **Reuse and reruns:** an existing model/article run is reused by default.
  Explicit recomputation creates a new immutable run and never overwrites prior
  outputs or evaluations.
- **Content retention:** scraped title/body are discarded by default. A user can
  explicitly save them only in the local CSV data directory; authors and raw
  HTML are never saved. The public repository dataset always keeps editorial
  fields empty.
- **Aggregation:** `majority_vote` is the paper-compatible default. The MVP
  also implements `ordinal_mean` and `mean_probabilities` under the exact rules
  in `docs/scientific-contract.md`.
- **Article counts:** publisher and explicit multi-article evaluations accept
  2 through 50 articles; the publisher-discovery default is 10.
- **Jobs:** model loading, retrieval, inference, import, and aggregation execute
  as inspectable background jobs. The API returns a job identifier immediately.
- **Security:** the MVP is loopback-only. Native execution binds a loopback
  address and Compose publishes only on host loopback. Non-loopback binds are
  rejected. Mutation requests from browsers additionally require a valid
  same-origin `Origin`; every request must pass the documented `Host` check.
- **Uploads:** dataset bytes are acquired into a private, bounded spool before
  an import job is created. The spool is operational, never authoritative, and
  is removed as soon as the job reaches a durable terminal state.
- **Maintenance:** compaction is an offline CLI operation. Content purge takes
  an exclusive maintenance lock, rewrites live state, and rebuilds indexes;
  external and application-created backups require explicit manual deletion.

## Offline and online behavior

The following work without internet access after software dependencies and CSV
state are present locally; model artifacts are unnecessary when all requested
predictions already exist:

- browse, search, filter, paginate, and export local article and publisher
  history;
- inspect stored predictions, probabilities, jobs, and evaluations;
- aggregate existing compatible predictions;
- use the frontend, API documentation, and charts.

Network access is required only for:

- evaluating an article that lacks a compatible stored run and has no
  user-saved local text;
- explicitly recomputing a prediction from a fresh page retrieval;
- explicitly adding local title/body to a known article that has no saved
  content;
- resolving redirects or a page-declared canonical URL after the offline URL
  lookup misses;
- discovering additional articles from a publisher homepage;
- downloading a missing base model or tokenizer with external model tooling;
  the application itself has no setup/download command.

Starting with `--offline` or `PRT_OFFLINE=true` disables every outbound HTTP
request. An operation that cannot complete locally fails with the stable error
code `NETWORK_REQUIRED`; browsing and other local operations remain available.

Evaluation requests use `prediction_action=reuse` and
`content_retention=discard` by default. `reuse` returns the latest compatible
run when one exists, otherwise it infers from explicitly saved local text or
retrieves the page. `recompute` always retrieves the current page and creates a
new immutable run. `save_local` stores only the newspaper-extracted title and
body in local CSV after validation.

## User input modes

The Evaluate page and `POST /api/v1/evaluation-jobs` accept exactly one of:

1. one article URL;
2. a list of 2–50 article URLs from one normalized publisher;
3. one publisher homepage URL plus a requested count of 2–50 articles.

For a publisher request, the user selects `stored_only`, `stored_first`, or
`web_only`. `stored_first` is the default: eligible local articles are used
before the application attempts web discovery for the missing count.

## Repository map

| Path | Normative purpose |
| --- | --- |
| `docs/product-specification.md` | Product scope, workflows, UI behavior, requirements, and error rules |
| `docs/architecture.md` | Fixed technology stack, components, data flow, concurrency, security, and deployment architecture |
| `docs/api-contract.md` | REST resources, payloads, status codes, pagination, jobs, and error envelope |
| `docs/csv-storage-contract.md` | Authoritative local CSV database layout, schemas, transactions, recovery, and import rules |
| `docs/scientific-contract.md` | Model recipes, class outputs, text pipeline, reuse, aggregation, and scientific warnings |
| `docs/deployment.md` | Exact native Linux, Docker, Compose, configuration, model mounts, and offline commands |
| `docs/acceptance-tests.md` | End-to-end conditions required before the MVP is releasable |
| `docs/traceability.md` | Mapping from every functional/non-functional requirement to acceptance coverage |
| `dataset/README.md` | Public dataset generation, verification, licensing notice, and runtime import behavior |
| `models/README.md` | Official artifact layouts and local registration behavior |
| `LICENSE` | Apache-2.0 terms for project-owned software and documentation |
| `MODEL-OUTPUT-LICENSE.md` | CC0-1.0 dedication limited to project-owned generated outputs/database arrangement |

Contract ownership is disjoint. When text overlaps, the owner governs, and the
architecture supplies cross-cutting invariants:

1. `scientific-contract.md`: formulas, model/input identity, and scientific
   compatibility;
2. `csv-storage-contract.md`: durable representation, transactions, recovery,
   retention, and maintenance;
3. `api-contract.md`: HTTP schemas, status codes, security, and error mapping;
4. `deployment.md`: process/container configuration and operating procedures;
5. `product-specification.md`: scope, workflows, UI, and requirements;
6. `architecture.md`: component boundaries and cross-contract invariants. It
   may constrain all owners but cannot redefine an owner-specific schema or
   formula.

If two owner-specific rules still conflict, the earlier owner in this list
governs only that overlapping subject. Acceptance tests are verification, not
an independent source of requirements.

An ambiguity discovered during implementation is a specification defect. It
must be resolved in these documents and covered by an acceptance test before
the implementation is merged.

## Public and protected data boundary

The repository contains model-produced outputs, article URLs, and publisher
domains. In the tracked public dataset, compatibility columns for `title`,
`text`, and `authors` are present but must be empty. User-saved local content
lives only under the ignored runtime data directory. The repository
must never contain original reference-provider labels, scores, score ranges, or
provider-supplied metadata. The public classes are displayed only as `Class 0`
through `Class 4`; the tool contains no mapping back to protected names or score
ranges.

The private source dataset and model weights are ignored by Git. The generated
public release retains the first source occurrence of each exact URL and records
the deduplication counts in its manifest. It contains no article titles, bodies,
or author strings.

The software is licensed under Apache-2.0 in `LICENSE`. Model-produced labels,
fold identifiers, probabilities, and the project-owned database arrangement are
dedicated under CC0-1.0 in `MODEL-OUTPUT-LICENSE.md`. Neither license applies to
third-party URLs, publisher names, trademarks, model weights, or source pages.

## Official model release

The terminal and Models page always show the official download location:

<https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

BERT, RoBERTa, and Llama folds are released as notebook-defined `.pt`
`state_dict` files. Mistral folds are PEFT directories and require the declared
24B base model. Exact loader contracts are normative in
`docs/scientific-contract.md`.

## Definition of done

The MVP is complete only when every applicable CPU-gate acceptance test passes
in native Linux and Docker Compose (hardware-specific tests report separately),
the OpenAPI document matches `docs/api-contract.md`, all local
state is inspectable as CSV, browsing works with outbound networking disabled,
and no protected reference field is present in Git history, runtime state,
logs, API responses, UI state, or exports. Blocked source column names may
persist only in the explicitly documented value-free import audit metadata.
