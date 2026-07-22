# Deployment Contract

**Status:** Normative native Linux and Docker Compose contract

## 1. Published artifacts

Each release publishes:

- a Python 3.12 wheel and source distribution;
- one versioned OCI image for CPU/runtime use;
- `compose.yaml` and `.env.example`;
- pinned Python and frontend lock files;
- a generated OpenAPI document;
- SHA-256 checksums for release artifacts.

Model weights and base-model caches are never embedded in the wheel or image.

## 2. Native Linux installation

Reference platform is Ubuntu 24.04 LTS x86-64. Required system packages are
Python 3.12, `python3.12-venv`, compiler/runtime libraries required by locked
Python wheels, and optional NVIDIA components for quantized GPU models.

Native installation uses the committed `uv.lock` and a documented compatible
`uv` version. Installation fails rather than resolving newer dependencies:

```bash
uv sync --frozen
source .venv/bin/activate
publisher-reliability dataset verify ./dataset/predictions
publisher-reliability serve \
  --data-dir ./data \
  --models-dir ./models \
  --seed-dataset ./dataset/predictions
```

An unlocked `pip install` is not a release procedure. Node 22 and the committed
frontend lock file are used only during development/image packaging. Frontend
production assets are built during packaging and never at application startup.

On successful startup the terminal prints:

```text
UI:       http://127.0.0.1:8000/
API:      http://127.0.0.1:8000/api/v1
API docs: http://127.0.0.1:8000/api/docs
Mode:     online-enabled
Data:     /absolute/path/to/data
```

## 3. Required Compose service

The repository root contains this logical Compose contract; image tags and
UID/GID values are release-specific but behavior is not:

```yaml
services:
  app:
    build:
      context: .
      target: runtime
    image: publisher-reliability-tool:${PRT_VERSION:-dev}
    restart: "no"
    init: true
    user: "10001:10001"
    ports:
      - "127.0.0.1:${PRT_PORT:-8000}:8000"
    environment:
      PRT_HOST: "0.0.0.0"
      PRT_PORT: "8000"
      PRT_PUBLIC_ORIGIN: "http://127.0.0.1:${PRT_PORT:-8000}"
      PRT_CONTAINER_LOOPBACK_ONLY: "true"
      PRT_DATA_DIR: "/data"
      PRT_MODELS_DIR: "/models:/data/managed-models"
      PRT_SEED_DATASET: "/app/dataset/predictions"
      PRT_HF_HOME: "/cache/huggingface"
      PRT_OFFLINE: "${PRT_OFFLINE:-false}"
    volumes:
      - ./data:/data
      - ./models:/models:ro
      - ./dataset:/app/dataset:ro
      - ./cache/huggingface:/cache/huggingface
    healthcheck:
      test: ["CMD", "python", "-m", "publisher_reliability.healthcheck"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    stop_grace_period: 35s
```

The actual `compose.yaml` shall contain no `privileged`, host network, Docker
socket mount, wildcard host port, or writable source-code mount.
No automatic restart policy is part of the MVP: permanent configuration,
storage, or port failures remain visible instead of looping. The runtime image contains the zero-byte, root-owned, non-writable marker
`/opt/publisher-reliability/.container-image`; native packages do not create it.

Prepare writable directories once, then start/stop:

```bash
sudo install -d -m 0750 -o 10001 -g 10001 ./data ./cache/huggingface
docker compose up --build
docker compose down
```

State survives `down` because it is bind-mounted in `./data`. `down -v` does not
delete bind-mounted host data but is not included in normal instructions.

## 4. GPU profile

The repository provides a mutually exclusive `gpu` service/profile with NVIDIA
device reservation and the same command, image version, volumes, port, and data
directory. It sets `PRT_DEVICE=cuda` and requires a working NVIDIA Container
Toolkit.

```bash
docker compose --profile gpu up app-gpu
```

Compose shall prevent `app` and `app-gpu` from being started together in
documented commands. If both are manually started, the second fails on the CSV
writer lock without corrupting state.

Llama and Mistral registration can succeed as `resource_unavailable` when CUDA
or sufficient memory is missing. The program does not invent universal VRAM
minimums; it reports measured artifact/runtime requirements and preflight
results. BERT and RoBERTa CPU inference remains available when their locked
runtime supports it.

## 5. Configuration precedence

Precedence, highest first:

1. CLI option;
2. `PRT_*` environment variable;
3. documented default.

There is no implicit configuration file in the MVP.

| Environment variable | Default | Validation |
| --- | --- | --- |
| `PRT_HOST` | `127.0.0.1` | `127.0.0.1` or `::1`; image-internal `0.0.0.0` only with the container flag |
| `PRT_PORT` | `8000` | `1..65535` |
| `PRT_PUBLIC_ORIGIN` | derived loopback URL | Exact HTTP loopback origin; required when container host port differs |
| `PRT_CONTAINER_LOOPBACK_ONLY` | `false` | `true` only in the official loopback-published container contract |
| `PRT_DATA_DIR` | `./data` | Writable directory, no second writer |
| `PRT_MODELS_DIR` | `./models` | OS path list separated by `:` |
| `PRT_SEED_DATASET` | `./dataset/predictions` | Valid CSV or manifest directory; missing allowed |
| `PRT_OFFLINE` | `false` | Strict lowercase boolean |
| `PRT_DEVICE` | `auto` | `auto`, `cpu`, or `cuda` |
| `PRT_HF_HOME` | normal HF cache | Writable/cache-readable path |
| `PRT_LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `PRT_MODEL_UPLOAD_MAX_BYTES` | `10737418240` | Positive integer, default 10 GiB |
| `PRT_DATASET_UPLOAD_MAX_BYTES` | `2147483648` | Positive integer, default 2 GiB |
| `PRT_JOB_QUEUE_MAX` | `100` | Positive integer queued-job cap |
| `PRT_BACKUP_MAX_COUNT` | `3` | Positive application-created backup cap |
| `PRT_BACKUP_MAX_BYTES` | `21474836480` | Positive application-created backup byte cap |

Invalid values stop startup with exit code `2` and one actionable English
message.

## 6. Offline deployment

Offline application mode:

```bash
publisher-reliability serve --offline
```

or:

```bash
PRT_OFFLINE=true docker compose up
```

This is an application guarantee: the program refuses retrieval and downloads.
For a network-enforced environment, users additionally apply host/container
firewall policy; Compose does not claim to be a security boundary for outbound
traffic.

Offline readiness requires only verified CSV state, built indexes, executor,
and bundled frontend assets. Per-request preflight decides whether a particular
model/body/run can satisfy an operation; readiness never predicts future input.
`recompute` remains unavailable offline and no frontend asset has a remote
dependency.

The OSF link remains visible as text while offline but is not requested.

## 7. Model mounts and setup

Native paths are direct host paths. In Docker, only paths mounted into the
container can be registered. The standard read-only root is `/models`.

Example host layout:

```text
models/
├── bert_fold_1.pt
├── roberta_fold_3.pt
├── llama_fold_2.pt
└── mistral/
    └── fold_1/
        ├── adapter_config.json
        ├── adapter_model.safetensors
        └── tokenizer files
```

The base/tokenizer cache is separate from released fold artifacts. Dependency
setup uses external Transformers/Hugging Face tooling; the application has no
setup/download CLI. Inference never downloads a missing dependency implicitly.

## 8. File ownership

The container runs as fixed non-root `10001:10001`; no `PRT_UID`/`PRT_GID`
mechanism is promised. Users create/chown `data`, `cache/huggingface`, and other
writable mounts to that ID before starting. A missing seed/model directory is
allowed; if a configured path exists but is unreadable or wrong type, startup
fails. `/data` must be writable.

The application never changes permissions recursively and never makes model
files world-writable.

## 9. Upgrade procedure

1. Stop the application cleanly.
2. Copy the complete data directory as a backup.
3. Install/pull the target version.
4. Run `publisher-reliability storage verify` with the target version.
5. If a schema migration is required, run the explicit versioned migration
   command supplied by that release; no migration runs implicitly.
6. Start the application and verify readiness.

Downgrade is supported only when the target version recognizes the current CSV
schema. The application refuses an unknown newer schema.

## 10. Backup and restore

Backup while stopped:

```bash
publisher-reliability storage verify
tar --create --gzip --file publisher-reliability-data-backup.tar.gz ./data
```

Restore into an empty data directory, verify, then start. Model artifacts and
Hugging Face cache are backed up separately; losing them does not lose historical
predictions but can make inference unavailable.

If the user opted to save article title/body, the backup contains that
third-party content in `state/articles.csv`. It must be protected and handled
according to applicable rights. The in-app purge can rewrite only live state
and does not alter backups, including those in `data/backups`. The UI and purge
result require manual deletion of every backup/copy that must lose the content.

Application-created compaction/recovery backups retain at most 3 complete
generations and 20 GiB total, deleting oldest complete generations only after a
successful operation. User-created backups are not managed. Upload,
compaction, and purge enforce the free-space formulas in the storage contract;
ENOSPC fails safely without reporting an incomplete commit.

## 11. CI deployment matrix

Every release must pass:

- native Ubuntu 24.04 install, startup, API, UI smoke test, and offline test;
- CPU Compose build/start/readiness, persistence restart, and offline test;
- NVIDIA Compose registration/inference fixture when a GPU runner is available;
- clean browser test with all external network requests blocked;
- non-root writable-data/read-only-model mount test;
- graceful `SIGTERM` during retrieval, inference boundary, and CSV commit tests.
