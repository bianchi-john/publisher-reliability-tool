# Publisher Reliability Tool

> A local research application for classifying news articles and reading a
> publisher's reliability class from the articles already classified.

**Local only** · **Predictions, no ground-truth labels** · **Plain CSV storage**

> [!IMPORTANT]
> Every result is a model prediction — not a fact, a fact check, or a
> ground-truth rating.

<!-- TODO: replace arXiv.PLACEHOLDER with the real arXiv identifier once it
     is assigned. The same placeholder appears in paper/references.bib. -->
This tool is the reference implementation of *From Articles to Publishers:
Aggregating Language Model Predictions for News Source Reliability Inference*
(Bianchi, Pratelli, Pinelli and Petrocchi, IEEE Transactions on Computational
Social Systems, 2026, under review) — preprint:
<https://arxiv.org/abs/arXiv.PLACEHOLDER>. Every number the tool shows comes from
that study's five-fold, publisher-disjoint protocol.

## Start

Requires Linux, Python 3.12 and [`uv`](https://docs.astral.sh/uv/).

**One-time setup:**

```bash
uv sync --frozen --extra models
```

**Every time you want to run it:**

```bash
source .venv/bin/activate
publisher-reliability serve
```

Open **<http://127.0.0.1:8000>**; the API documentation is at
**<http://127.0.0.1:8000/api/docs>**.

Plain `uv sync --frozen` (without `--extra models`) gives a lighter environment
that can browse and reuse stored predictions but not classify anything new.

With Docker: `docker compose up --build` — see the
[deployment guide](docs/deployment.md).

## Documentation

Start with the [user guide](docs/user-guide.md) for a walkthrough of Evaluate,
Publishers, Export and Jobs. [dataset/README.md](dataset/README.md) and
[models/README.md](models/README.md) cover what's shipped and how to add
checkpoints.

Full contracts: [product specification](docs/product-specification.md) ·
[API](docs/api-contract.md) · [scientific](docs/scientific-contract.md) ·
[CSV storage](docs/csv-storage-contract.md) ·
[custom model bundle](docs/custom-model-bundle.md) ·
[architecture](docs/architecture.md) · [deployment](docs/deployment.md).

## License

Software and documentation are Apache-2.0. Project-owned prediction outputs and
the database arrangement use the limited CC0 dedication described in
[MODEL-OUTPUT-LICENSE.md](MODEL-OUTPUT-LICENSE.md). Third-party URLs, pages,
names, trademarks, models and weights are excluded.
