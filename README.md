# Publisher Reliability Tool

> A local research application for exploring article predictions and
> aggregating them at publisher level.

**Local only** · **Prediction-only data** · **Inspectable CSV storage**

PRT turns the bundled model outputs into browsable articles, publishers and
reproducible evaluations. It serves a web interface and REST API at
`http://127.0.0.1:8000`.

> [!IMPORTANT]
> Results are model predictions—not facts, fact checks or ground-truth ratings.

## Start

Requires Ubuntu/Linux, Python 3.12 and [`uv` 0.8.3](https://docs.astral.sh/uv/).

```bash
uv sync --frozen --extra models
source .venv/bin/activate
publisher-reliability dataset verify ./dataset/predictions
publisher-reliability serve
```

The `models` extra installs the locked PyTorch, Transformers and safetensors
dependencies required to scan checkpoints and validate custom bundles. Use
`uv sync --frozen` only for a lightweight stored-prediction-only environment.

Open **<http://127.0.0.1:8000>**. API documentation is available at
**<http://127.0.0.1:8000/api/docs>**.

### Docker

```bash
mkdir -p data models
sudo chown -R 10001:10001 data
docker compose up --build
```

The service is published only on `127.0.0.1:8000`.

## What works

| Area | Available |
| --- | --- |
| Dataset | Verified automatic import of the bundled predictions |
| Exploration | Articles, publishers, runs, models, imports and jobs |
| Evaluation | Single-article reuse and publisher aggregation |
| Methods | Majority vote, ordinal mean and mean probabilities |
| Import | Privacy-preserving CSV and CSV.GZ import |
| Persistence | Seven readable CSV ledgers under `data/state` |
| Access | Browser UI, REST API, OpenAPI and CLI |
| Offline | Browsing, reuse and stored aggregation |

The bundled release produces:

- **19,411** derived articles;
- **38,854** immutable prediction runs with complete five-class probabilities;
- **10** historical BERT/RoBERTa model/fold identities.

Imports are identified by content digest, so restarting or importing the same
dataset again does not duplicate data.

## Current limit

The repository does not distribute model weights. The Models page safely scans
configured roots, validates recognized BERT/RoBERTa state dictionaries and
keeps local checkpoints separate from historical dataset identities. This
version does not yet retrieve new pages or run inference; operations requiring
a new prediction fail explicitly instead of creating synthetic results.

Stored dataset predictions remain fully browseable by article, publisher,
model/fold and class probability. Publisher aggregations created in the
workspace are tracked separately.

Evaluate derives its choices from both the local Models inventory and the
stored prediction coverage for the submitted URL. For fold-indexed dataset
articles, checkpoint fold `N` is offered only for articles assigned to held-out
test fold `N`; checkpoints trained on that article are hidden and rejected.
New URLs with no stored run report that inference is required instead of
appearing as a generic compatibility failure.

The Models page also accepts a constrained custom Transformers `.zip` bundle
using `safetensors` and a local tokenizer. It validates and registers supported
five-class `AutoModelForSequenceClassification` architectures without loading
custom Python code. Imported custom models remain non-runnable until the new-web
inference pipeline is implemented.

Official artifacts are available separately from
[OSF](https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74)
and remain outside version control.

## Privacy and reproducibility

- Protected labels, scores and provider metadata are never persisted.
- Imported titles, article text and authors are discarded.
- Authors and raw HTML have no storage field.
- Every publisher evaluation records the exact model, articles and runs used.
- Every bundled historical run includes all five class probabilities.
- The only tracked dataset is the prediction release in `dataset/predictions`.

See [dataset/README.md](dataset/README.md) for the dataset format.

## Useful commands

```bash
# Verify a dataset without changing application state
publisher-reliability dataset verify PATH

# Import predictions into the configured data directory
publisher-reliability dataset import PATH

# Verify the seven CSV ledgers
publisher-reliability storage verify

# Run in strict offline mode
publisher-reliability serve --offline

# Run the test suite
uv run --frozen python -m unittest discover -s tests -v
```

## Project guide

| Path | Purpose |
| --- | --- |
| `src/publisher_reliability/` | Application, API, services and storage |
| `dataset/predictions/` | Public prediction-only release |
| `models/` | Local, untracked model artifacts |
| `docs/` | Scientific, API, storage and deployment contracts |
| `tests/` | Automated tests |

Start with:

- [Product specification](docs/product-specification.md)
- [API contract](docs/api-contract.md)
- [Scientific contract](docs/scientific-contract.md)
- [CSV storage contract](docs/csv-storage-contract.md)
- [Deployment guide](docs/deployment.md)

## License

Software and documentation are Apache-2.0. Project-owned prediction outputs and
database arrangement use the limited CC0 dedication described in
[MODEL-OUTPUT-LICENSE.md](MODEL-OUTPUT-LICENSE.md). Third-party URLs, pages,
names, trademarks, models and weights are excluded.
