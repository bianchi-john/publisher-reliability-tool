# Deployment Contract

**Status:** Normative local research-demo operation

## 1. Supported artifacts

A release provides a Python 3.12 wheel/source distribution, one CPU OCI image,
simple `compose.yaml`, locked Python/frontend dependencies, generated OpenAPI,
and checksums. Model weights and base-model caches are never bundled.

This is local execution documentation, not a public deployment guide. Reverse
proxy, TLS, authentication, replicas, orchestration, and remote hosting are
outside scope.

## 2. Native start

Reference platform: Ubuntu 24.04 LTS x86-64. Use `uv` 0.8.3 with the committed
`uv.lock`. One-time setup:

```bash
uv sync --frozen --extra models
```

Every subsequent start needs only:

```bash
source .venv/bin/activate
publisher-reliability serve
```

The `models` extra is required for local checkpoint scanning and custom
Transformer validation. A base-only sync remains sufficient for browsing,
imports and stored aggregation.

`publisher-reliability dataset verify ./dataset/predictions` is an optional,
read-only check: it validates the bundled release without changing any state.
`serve` imports that same release itself on every start, keyed by content
digest, so a repeat start never re-imports or duplicates it.


Production frontend assets are built into the package. Successful startup
prints the local UI, API, docs, data directory, and offline/device state. The
host is fixed to `127.0.0.1`; only the port is configurable.

## 3. Simple Compose service

The logical contract is one service:

```yaml
services:
  app:
    build: .
    image: publisher-reliability-tool:${PRT_VERSION:-dev}
    restart: "no"
    init: true
    stop_grace_period: 7s
    user: "10001:10001"
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      PRT_PORT: "8000"
      PRT_DATA_DIR: "/data"
      PRT_MODELS_DIR: "/models"
      PRT_SEED_DATASET: "/app/dataset/predictions"
      PRT_OFFLINE: "${PRT_OFFLINE:-false}"
      PRT_DEVICE: "${PRT_DEVICE:-auto}"
      PRT_LOG_LEVEL: "${PRT_LOG_LEVEL:-info}"
      PRT_DATASET_UPLOAD_MAX_BYTES: "${PRT_DATASET_UPLOAD_MAX_BYTES:-536870912}"
      PRT_MODEL_UPLOAD_MAX_BYTES: "${PRT_MODEL_UPLOAD_MAX_BYTES:-8589934592}"
    volumes:
      - ./data:/data
      - ./models:/models:ro
      - ./dataset:/app/dataset
```

The image's fixed entry point may listen on container `0.0.0.0:8000`; this is
an image-internal exception enabled only by an image marker. Compose publishes
host loopback only. The actual file contains no privileged mode, host network,
Docker socket, source-code mount, replica, restart loop, or production health
orchestration.

Prepare writable state and prediction mirror once:

```bash
mkdir -p data models dataset/predictions
sudo chown -R 10001:10001 data dataset/predictions
docker compose up --build
```

The read-only models directory may remain owned by the user if UID 10001 can
read it. The dataset mount is intentionally writable: local inference rows are
mirrored to `dataset/predictions/user-predictions.csv`, a private file that is
never part of the tracked release and is listed in `.gitignore`. The released
`predictions.csv` and its manifest are never modified by the running
application. `docker compose down` preserves both bind-mounted locations.

GPU examples may be documented in a separate optional
`compose.gpu.example.yaml`; they are not part of the required Compose path or
core release gate.

## 4. Configuration

Precedence is CLI, environment, default. No configuration file is loaded.

| Variable | Default | Rule |
| --- | --- | --- |
| `PRT_PORT` | `8000` | Integer `1..65535` |
| `PRT_DATA_DIR` | `./data` | Created after port reservation if absent; existing directory or parent must be writable; one process lock |
| `PRT_MODELS_DIR` | `./models` | `:`-separated readable roots; missing allowed |
| `PRT_SEED_DATASET` | `./dataset/predictions` | Official manifest plus a writable, git-ignored user-prediction mirror file; missing allowed |
| `PRT_OFFLINE` | `false` | Lowercase boolean |
| `PRT_DEVICE` | `auto` | `auto`, `cpu`, `cuda` |
| `PRT_LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `PRT_DATASET_UPLOAD_MAX_BYTES` | `536870912` | Positive, maximum 512 MiB in supported demo |
| `PRT_MODEL_UPLOAD_MAX_BYTES` | `8589934592` | Positive, maximum 8 GiB |
| `PRT_PUBLIC_HOST` | empty | Hostname, optionally with a port, that this instance answers on when published; empty means a single-user local instance |

CORS, API keys, job lanes, backup retention and UID/GID remapping are
intentionally not configurable.

## 4.1 Publishing the instance

The application was written for one person on a loopback address. Two of its
assumptions stop holding once it is reachable by anyone: that whoever reaches it
may run administrative operations, and that the `Host` header can only be the
loopback address. Setting `PRT_PUBLIC_HOST` (or `--public-host`) states the name
the instance answers on and switches both.

A published instance:

- accepts that one extra `Host` value, and nothing else. The check still refuses
  every other name, because it exists to defeat DNS rebinding rather than to be
  switched off;
- **does not serve** `POST /api/v1/models/scan`, `POST /api/v1/models/upload` or
  `POST /api/v1/imports/upload`. They are not registered at all, so they answer
  `404` and the generated OpenAPI describes exactly what that deployment can do;
- **forces `content_retention` to `discard`**, so a visitor cannot ask the server
  to keep the text of a third party's article;
- reports `public_instance: true` from `GET /api/v1/status`, which the interface
  reads to hide the controls calling those routes;
- caps the queue at 20 waiting jobs and answers `429 TOO_MANY_REQUESTS` beyond
  that, because one worker classifying an article in seconds would otherwise
  promise an unbounded wait.

Classifying an article stays available: that is the demonstration.

Run it behind a reverse proxy that terminates TLS and forwards to the loopback
port. The proxy must pass the public name through as `Host`:

```nginx
server {
    server_name prt.example.org;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;   # a RoBERTa-large classification takes seconds
    }
}
```

Start it with the matching name:

```bash
publisher-reliability serve --public-host prt.example.org
```

Resource use is modest and was measured rather than estimated: about 100 MB with
the ledgers loaded, 0.96 GB while BERT is resident and 1.85 GB while
RoBERTa-large is, since only one checkpoint stays in memory at a time. Allow
roughly 2 GB of RAM for the process and about 16 GB of disk for the virtual
environment, the ten checkpoints and the data directory.

Run exactly one process. The data directory takes an exclusive lock, so a second
worker fails with `STORAGE_ERROR` rather than corrupting the ledgers.

## 5. Offline operation

```bash
publisher-reliability serve --offline
```

or `PRT_OFFLINE=true docker compose up`. The application creates a deny-all
HTTP transport before services/model loaders. Browsing, reuse, import, and
stored aggregation remain available. A retrieval-dependent operation returns
`NETWORK_REQUIRED`. Model loaders use local files only.

A host/container firewall can provide an additional research-test boundary,
but the application guarantee is itself tested by capturing connection
attempts.

## 6. Models

Download `bert_fold_N.pt` and `roberta_fold_N.pt` manually from the OSF link,
copy them under a configured root, and scan. Family and fold are read from the
exact filename.

On first online BERT/RoBERTa inference the application may cache the small
tokenizer/configuration files from the immutable revisions recorded in model
identity. BERT/RoBERTa CPU is the supported core path.

Plan for the first start to be slow: every checkpoint is read once for its
SHA-256 and once more for structural validation, which for the paper's ten folds
is roughly 8.8 GB. Later starts reuse the recorded result for any file left
untouched, through `<data-dir>/model-scan-cache.json`, and take seconds instead.
The cache is disposable — deleting it only makes the next start slow again — and
`publisher-reliability models scan --full` forces complete re-verification, which
is the right thing to run when storage integrity is in question.

Custom Transformers are a complete allowlisted encoder classifier. The
application does not execute artifact code. Use **Models → Import a custom
five-class Transformer**.
See
[Custom Transformers bundle](custom-model-bundle.md) for the full contract.

New article extraction is part of the `models` extra. Retrieval requests
English content explicitly and Newspaper3k is the only body extractor, parsing
with `language="en"`. Deterministic language detection still rejects extracted
text that is not English.

The frontend uses the system Times New Roman font, so no font files are
bundled. The single light theme needs no remote asset or CDN.

## 7. Backup and restore

For backup, stop the application, run `publisher-reliability storage verify`
and `publisher-reliability dataset verify ./dataset/predictions`, then copy or
archive both the complete data directory and `dataset/predictions`. Restore
both copies and verify before startup. The state ledger is authoritative; the
dataset copy preserves the additional inspectable/recoverable
`user_evaluation` rows.

The application has no backup scheduler, retention policy, compaction, or
automatic backup purge. A backup containing `state/local_content.csv` may
contain third-party title/body saved by the user. Deleting active content does
not change backups; the user must delete relevant copies manually.

## 8. Release checks

Core CI runs native Ubuntu and CPU Compose startup, bundled import, API/UI smoke,
restart persistence, core model fixture, and strict offline tests. Optional GPU
and stress/fault suites report separately. Performance is observed on a typical
four-core/16-GiB workstation but is not a release-blocking latency SLA.
