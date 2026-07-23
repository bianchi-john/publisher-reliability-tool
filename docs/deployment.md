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
`uv.lock`:

```bash
uv sync --frozen
source .venv/bin/activate
publisher-reliability dataset verify ./dataset/predictions
publisher-reliability serve
```

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
      PRT_MODEL_UPLOAD_MAX_BYTES: "${PRT_MODEL_UPLOAD_MAX_BYTES:-4294967296}"
    volumes:
      - ./data:/data
      - ./models:/models:ro
      - ./dataset:/app/dataset:ro
```

The image's fixed entry point may listen on container `0.0.0.0:8000`; this is
an image-internal exception enabled only by an image marker. Compose publishes
host loopback only. The actual file contains no privileged mode, host network,
Docker socket, source-code mount, replica, restart loop, or production health
orchestration.

Prepare writable state once:

```bash
mkdir -p data models
sudo chown -R 10001:10001 data
docker compose up --build
```

The read-only models directory may remain owned by the user if UID 10001 can
read it. `docker compose down` preserves bind-mounted state.

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
| `PRT_SEED_DATASET` | `./dataset/predictions` | Official manifest directory; missing allowed |
| `PRT_OFFLINE` | `false` | Lowercase boolean |
| `PRT_DEVICE` | `auto` | `auto`, `cpu`, `cuda` |
| `PRT_LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `PRT_DATASET_UPLOAD_MAX_BYTES` | `536870912` | Positive, maximum 512 MiB in supported demo |
| `PRT_MODEL_UPLOAD_MAX_BYTES` | `4294967296` | Positive, maximum 4 GiB in supported demo |

Host, public origin, CORS, API keys, job lanes, queue limits, backup retention,
and UID/GID remapping are intentionally not configurable.

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

Download artifacts manually from the official OSF link, copy them under a
configured root, and use the Models page/CLI scan. Base models and tokenizers
are provisioned separately with normal Hugging Face/Transformers tooling. The
application has no download manager, setup command, credentials, or cache
administrator.

BERT/RoBERTa CPU is the supported core path. GPU dependencies and optional
Llama/Mistral examples are installed and operated by the researcher.

## 7. Backup and restore

For backup, stop the application, run `publisher-reliability storage verify`,
and copy or archive the complete data directory. Restore that copy into an empty
directory and verify before startup.

The application has no backup scheduler, retention policy, compaction, or
automatic backup purge. A backup containing `state/local_content.csv` may
contain third-party title/body saved by the user. Deleting active content does
not change backups; the user must delete relevant copies manually.

## 8. Release checks

Core CI runs native Ubuntu and CPU Compose startup, bundled import, API/UI smoke,
restart persistence, core model fixture, and strict offline tests. Optional GPU
and stress/fault suites report separately. Performance is observed on a typical
four-core/16-GiB workstation but is not a release-blocking latency SLA.
