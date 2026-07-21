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
only when an explicit request requires an article that is not usable from the
local CSV data, when publisher discovery needs additional articles, or when the
user explicitly downloads a missing model dependency.

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
  its normalized hostname, and a prediction by article plus exact model
  identity.
- **Reuse:** a compatible stored prediction is returned without refetching or
  comparing article text. Stored article text can be used for a missing model
  prediction without a network connection.
- **Aggregation:** `majority_vote` is the paper-compatible default. The MVP
  also implements `ordinal_mean` and `mean_probabilities` under the exact rules
  in `docs/scientific-contract.md`.
- **Article counts:** publisher and explicit multi-article evaluations accept
  2 through 50 articles; the publisher-discovery default is 10.
- **Jobs:** model loading, retrieval, inference, import, and aggregation execute
  as inspectable background jobs. The API returns a job identifier immediately.
- **Security:** no authentication is required for native loopback or the
  documented loopback-published Compose service. Every other non-loopback bind
  is rejected unless an API key is configured.

## Offline and online behavior

The following work without internet access after software dependencies, CSV
state, and selected model dependencies are present locally:

- browse, search, filter, paginate, and export local article and publisher
  history;
- inspect stored predictions, probabilities, jobs, and evaluations;
- aggregate existing compatible predictions;
- infer with a local model from article text already stored in CSV;
- use the frontend, API documentation, and charts.

Network access is required only for:

- fetching an article whose usable text is absent locally;
- resolving redirects or a page-declared canonical URL after the offline URL
  lookup misses;
- discovering additional articles from a publisher homepage;
- explicitly downloading a missing base model or tokenizer.

Starting with `--offline` or `PRT_OFFLINE=true` disables every outbound HTTP
request. An operation that cannot complete locally fails with the stable error
code `NETWORK_REQUIRED`; browsing and other local operations remain available.

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

If two documents appear to conflict, the more specific contract governs:

1. scientific behavior: `scientific-contract.md`;
2. CSV persistence: `csv-storage-contract.md`;
3. HTTP behavior: `api-contract.md`;
4. deployment behavior: `deployment.md`;
5. product presentation and workflows: `product-specification.md`.

An ambiguity discovered during implementation is a specification defect. It
must be resolved in these documents and covered by an acceptance test before
the implementation is merged.

## Public and protected data boundary

The repository contains model-produced outputs and scraped article fields. It
must never contain original reference-provider labels, scores, score ranges, or
provider-supplied metadata. The public classes are displayed only as `Class 0`
through `Class 4`; the tool contains no mapping back to protected names or score
ranges.

The private source dataset and model weights are ignored by Git. The generated
public release retains the first source occurrence of each exact URL and records
the deduplication counts in its manifest. Article titles, bodies, and author
strings remain attributable to their respective publishers; inclusion does not
change their copyright status.

Before an application release, the project owner must add `LICENSE` for the
software and `MODEL-OUTPUT-LICENSE.md` for generated predictions. Those terms
must not claim to relicense third-party article text. Absence of either file is
a release blocker, not permission inferred from public access.

## Official model release

The terminal and Models page always show the official download location:

<https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

BERT, RoBERTa, and Llama folds are released as notebook-defined `.pt`
`state_dict` files. Mistral folds are PEFT directories and require the declared
24B base model. Exact loader contracts are normative in
`docs/scientific-contract.md`.

## Definition of done

The MVP is complete only when every acceptance test passes in native Linux and
Docker Compose, the OpenAPI document matches `docs/api-contract.md`, all local
state is inspectable as CSV, browsing works with outbound networking disabled,
and no protected reference field is present in Git history, runtime state,
logs, API responses, UI state, or exports.
