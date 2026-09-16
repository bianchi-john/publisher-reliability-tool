# Publisher Reliability Tool

> A local research application for classifying news articles and reading a
> publisher's reliability class from the articles already classified.

**Local only** · **Predictions, no ground-truth labels** · **Plain CSV storage**

The tool ships the model outputs of the study as a browsable dataset, lets you
classify a new article URL with a local BERT or RoBERTa checkpoint, and derives a
publisher-level class on demand. It serves a web interface and a REST API on
`http://127.0.0.1:8000` and nothing else.

> [!IMPORTANT]
> Every result is a model prediction — not a fact, a fact check, or a
> ground-truth rating. Softmax values are not necessarily calibrated confidence.

## Start

Requires Linux, Python 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --frozen --extra models
source .venv/bin/activate
publisher-reliability dataset verify ./dataset/predictions
publisher-reliability serve
```

Then open **<http://127.0.0.1:8000>**; the API documentation is at
**<http://127.0.0.1:8000/api/docs>**.

The `models` extra installs the pinned PyTorch and Transformers dependencies
needed to run checkpoints. Plain `uv sync --frozen` gives a lighter environment
that can browse and reuse stored predictions but cannot classify anything new.

With Docker:

```bash
mkdir -p data models dataset/predictions
sudo chown -R 10001:10001 data dataset/predictions
docker compose up --build
```

## What it does

The bundled release imports on first start and yields **17,269** articles,
**34,564** immutable prediction runs with complete five-class probabilities, and
**10** BERT/RoBERTa fold identities, over **372** publishers. It ships only
outlets with at least 20 classified articles, since a publisher verdict resting
on two or three articles says more about the sample than about the outlet. An
import is keyed by content digest, so starting again never duplicates anything.

**Evaluate** classifies one article URL. You pick a model among those actually
usable for that URL, and the run is stored with all five class probabilities.

**Publishers** reads a class rather than creating one. It is recomputed from the
stored article predictions each time you ask, per model, under the counting rule
you choose — majority vote, ordinal mean or mean probabilities — and over the
articles you leave in. Two checkpoints that disagree are shown disagreeing
instead of being averaged into a number neither produced. Nothing is stored.

**Export** downloads one row per prediction, so every model that judged an
article appears separately with its own label, probabilities, readable name,
provenance and run identifier.

## Models

The repository distributes no weights. Copy `bert_fold_N.pt` or
`roberta_fold_N.pt` into `models/` (see [models/README.md](models/README.md));
checkpoints are discovered by exact filename and validated before use. The
Models page also imports custom five-class encoder classifiers as self-contained
`.zip` bundles.

Weights are published separately on
[OSF](https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74).

**Leakage is blocked, not warned about.** Every family in the study shares one
publisher-disjoint five-fold split, so an article's held-out fold identifies the
training set of every checkpoint. Fold `N` may score an article only if that
article was held out in fold `N`; the rest are withheld from the selector and
refused by the backend. The withheld checkpoints are named on screen, so a
missing option is never unexplained.

The study also fine-tuned Llama 3 8B and Mistral 24B, but **importing them is
under development and unavailable here**: each fold needs a CUDA GPU and several
gigabytes of weights, which a single-machine CPU demo cannot assume. Attempting
it returns `FEATURE_UNAVAILABLE` and installs nothing. The identity, loader and
leakage rules are written so the family can be added later without changing the
storage contract.

## Privacy

- Protected labels, scores and provider metadata are never persisted.
- Article text, titles and authors are discarded; raw HTML has no storage field.
- **Your own evaluations never enter version control.** Each local run is
  committed to `data/state/prediction_runs.csv` and mirrored to
  `dataset/predictions/user-predictions.csv`, which is git-ignored. The tracked
  `predictions.csv` holds only the released rows and is never modified by the
  running application.

See [dataset/README.md](dataset/README.md) for the dataset format.

## Commands

```bash
publisher-reliability dataset verify PATH   # check a dataset, change nothing
publisher-reliability dataset import PATH   # import into the data directory
publisher-reliability storage verify        # check the six CSV ledgers
publisher-reliability models scan --full    # re-verify every checkpoint byte
publisher-reliability serve --offline       # stored predictions only
python -m unittest discover -s tests        # run the test suite
```

## Where things are

| Path | Purpose |
| --- | --- |
| `src/publisher_reliability/` | Application, API, services and storage |
| `src/publisher_reliability/frontend/` | Page templates in `pages/`, ES modules in `js/` |
| `dataset/predictions/` | The released, prediction-only dataset |
| `models/` | Local model artifacts, untracked |
| `docs/` | Scientific, API, storage and deployment contracts |
| `tests/` | Automated tests |

Start with the [user guide](docs/user-guide.md). The contracts are the
[product specification](docs/product-specification.md),
[API](docs/api-contract.md), [scientific](docs/scientific-contract.md),
[CSV storage](docs/csv-storage-contract.md),
[custom model bundle](docs/custom-model-bundle.md),
[architecture](docs/architecture.md) and [deployment](docs/deployment.md).

## License

Software and documentation are Apache-2.0. Project-owned prediction outputs and
the database arrangement use the limited CC0 dedication described in
[MODEL-OUTPUT-LICENSE.md](MODEL-OUTPUT-LICENSE.md). Third-party URLs, pages,
names, trademarks, models and weights are excluded.
