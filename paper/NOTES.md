# PRT — Code analysis notes for the ECIR 2027 demo paper

Written from the repository at commit `745c690`, branch `main`. Everything below
is derived from files in this repository (source, docs, dataset, runtime state,
the training notebook `2 - Reliability - 5Fold - Separate.ipynb`) and from the
submitted IEEE TCSS manuscript the tool accompanies. Items I could not establish
are collected in §9 as open questions rather than guessed.

> **Update.** §1, §4, §5 and §9 were revised after receiving the source paper and
> the training notebook. The class direction, the label provider, the corpus
> provenance and the demo hardware are now established facts, not open questions.


---

## 1. What problem the tool solves

The repository is the reference implementation accompanying a research paper
whose title is recorded verbatim inside
`src/publisher_reliability/official-model-manifest-v1.json`:

> **"From Articles to Publishers: Aggregating Language Model Predictions for
> News Source Reliability Inference"** — OSF project `https://osf.io/r9atz/`

The scientific task (`docs/scientific-contract.md` §2) has two levels:

1. **Article level** — a text classifier maps one English news article body to
   one ordered class index in `0..4` plus a five-component softmax vector.
2. **Publisher level** — a deterministic aggregation function combines 2–50
   article-level runs from *one exact model* and *one normalized publisher* into
   a single publisher-level class.

The ordered 0–4 classes are the five **NewsGuard** reliability bands, and their
direction is now established rather than inferred. The training notebook's own
dataframe output shows `nemontananews.com` with `score 32.0 → label 0` and
`truthdig.com` with `score 80.0 → label 3`, and the notebook maps labels by
`sorted(unique)` so model class index equals source label. Combined with Table I
of the manuscript this gives:

| Class | NewsGuard score | Band |
| ---: | --- | --- |
| 0 | 0–39 | Proceed with maximum caution |
| 1 | 40–59 | Proceed with caution |
| 2 | 60–74 | Credible with exceptions |
| 3 | 75–99 | Generally credible |
| 4 | 100 | High credibility |

**Class 0 is the least reliable, class 4 the most.** The provider columns
(`score, country, language, topics, paywall, opinion_advocacy, label`) are
listed in `dataset/predictions/manifest.json` as
`excluded_newsguard_columns` and are stripped from the release: the tool never
distributes, persists, logs or displays them. Classes appear only as `Class 0` …
`Class 4`, always framed as model predictions (`docs/scientific-contract.md`
§1, §9). The user has confirmed the provider may be named in the paper while the
original labels must never ship — model predictions trained on them are fine.

The gap the *tool* fills is therefore not "predict reliability" — the paper
already does that offline in notebooks. It is **making an offline, five-fold
cross-validated classification study interactively inspectable and safely
re-runnable**:

- the paper's ~19k article predictions become browsable by article, publisher,
  model family, fold and per-class probability;
- the paper's aggregation formulas become buttons a reader can press on a
  publisher of their choice;
- the paper's checkpoints can be re-run on *new*, previously unseen URLs;
- every one of those operations records enough provenance (exact model identity,
  run ID, contributing article IDs, software versions) to be audited from plain
  CSV;
- and a cross-validation **leakage guard** prevents the obvious misuse — asking
  fold-`N` checkpoint about an article it was trained on.

That last point is the genuinely non-obvious engineering contribution and is
probably the strongest angle for the demo paper.

---

## 2. Block architecture

```
                ┌──────────────────────────────────────────────┐
  browser ─────►│  FastAPI app (api.py) — loopback 127.0.0.1   │
  CLI    ─────► │  Host-check middleware, OpenAPI 3.1          │
                └───────────────┬──────────────────────────────┘
                                │  same Pydantic types + same service functions
                                ▼
                ┌──────────────────────────────────────────────┐
                │  ResearchService (services.py, ~1000 LOC)     │
                │  queries, availability logic, evaluate()      │
                └───┬──────────────┬─────────────┬─────────────┘
                    │              │             │
       ┌────────────▼───┐  ┌───────▼──────┐  ┌───▼────────────────┐
       │ Storage        │  │ JobQueue     │  │ AggregationMethod  │
       │ (storage.py)   │  │ (jobs.py)    │  │ (aggregation.py)   │
       │ 7 CSV ledgers  │  │ 1 FIFO worker│  │ 3 formulas         │
       │ flock + fsync  │  │ 3 job types  │  └────────────────────┘
       └────────┬───────┘  └───────┬──────┘
                │                  │
                │        ┌─────────▼───────────┐   ┌──────────────────┐
                │        │ ArticleRetriever +  │   │ ModelScanner /   │
                │        │ InferenceEngine     │◄──┤ OfficialModels / │
                │        │ (inference.py)      │   │ CustomModels     │
                │        │ httpx → Newspaper3k │   └──────────────────┘
                │        │ → langdetect → HF   │
                │        └─────────┬───────────┘
                │                  │
       ┌────────▼──────────────────▼───────────┐
       │ PredictionDatasetMirror                │
       │ (prediction_dataset.py)                │
       │ dataset/predictions/predictions.csv    │
       └────────────────────────────────────────┘
```

Module inventory (`src/publisher_reliability/`, LOC from `wc -l`):

| Module | LOC | Responsibility |
| --- | ---: | --- |
| `services.py` | 1294 | `ResearchService`: all read queries, `available_models()`, `evaluate()`, `clear_user_data()` |
| `inference.py` | 662 | Safe retrieval, English extraction, `InferenceEngine` (BERT and RoBERTa recipes) |
| `importer.py` | 631 | CSV / CSV.GZ projection, validation, conflict detection, idempotent import |
| `custom_models.py` | 601 | Validation/installation of user `.zip` model bundles (schema 1 & 2) |
| `api.py` | 581 | 27 HTTP routes, Pydantic request models, error mapping, static frontend |
| `official_models.py` | 459 | Checksum-authenticated import of large decoder artifacts; retained as an extension point, unreachable from any user-facing path |
| `prediction_dataset.py` | 449 | Public-release verification + idempotent mirroring and clearing of local runs |
| `storage.py` | 390 | Six CSV ledgers, `flock`, append+fsync, atomic rename |
| `jobs.py` | 329 | Single FIFO worker, persisted job rows, macro-phase progress, unconfirmed clear |
| `model_scanner.py` | 362 | Scans configured roots for recognized artifacts (no symlink following), reusing unchanged verifications |
| `cli.py` | 245 | `serve`, `dataset verify|import`, `models scan`, `storage verify` |
| `identity.py` | 150 | URL normalization, UUIDv5 article IDs, publisher hostname |
| `aggregation.py` | 137 | The three publisher-level formulas |
| `model_scan_cache.py` | 136 | Skips re-hashing a checkpoint whose file is untouched; self-invalidating |
| `config.py` | 85 | `PRT_*` env vars + CLI options |
| `errors.py` | 51 | 20 stable error codes with fixed HTTP statuses |
| `frontend/` | 1595 | `index.html` (41) + `styles.css` (258) + 9 page templates in `pages/*.html` (226) + 16 vanilla ES modules in `js/` (1070) |

Total application code ≈ 6.4k LOC Python + ~1.6k LOC frontend. Tests: 15 files,
~2.9k LOC, **83 tests, all passing** (verified: `python -m unittest discover -s
tests` → `Ran 83 tests in 2.122s / OK`). They cover the leakage guard across every
model family, publisher aggregation as a read-only derivation, the prediction
export, the checkpoint scan cache, the local-data purge's crash-safe ordering,
the job-history clear's queued/running guard, and the private mirror staying out
of version control.

### Deliberate non-architecture

`docs/architecture.md` §4 is explicit that there is **no** plugin registry, DI
framework, event bus, ORM, database, cache layer, or transaction log. Extension
is "ordinary Python composition". This is a defensible demo-paper talking point:
the reference implementation is meant to be read end-to-end by a researcher.

---

## 3. Persistence model

Seven authoritative CSV ledgers under `<data-dir>/state/`
(`docs/csv-storage-contract.md` §5):

| Ledger | Mutability | Contents |
| --- | --- | --- |
| `meta.csv` | mutable | schema version, creation time, app version |
| `models.csv` | mutable (atomic rewrite) | model identities + availability status |
| `prediction_runs.csv` | **immutable append** | every article-level prediction run |
| `imports.csv` | **immutable append** | every dataset import |
| `jobs.csv` | mutable (atomic rewrite) | job queue state |
| `local_content.csv` | mutable (atomic rewrite) | opt-in saved title/body |

Write discipline: one process-wide mutex; a POSIX `flock` on the data directory
so a second process cannot attach; appends are flushed + `fsync`ed; small
mutable files are written to a sibling temp file, verified, fsynced and
`rename()`d. Malformed authoritative CSV **fails closed at startup** — the
process never serves HTTP over data it could not verify.

Articles and publishers are *not stored*. They are derived views over
`prediction_runs.csv` at query time (canonical URL → UUIDv5 article ID;
hostname minus one leading `www.` → publisher ID). This removes a whole class of
synchronization bugs and is worth one sentence in the paper.

### The dual-write mirror

Every local inference is written twice, in a fixed order:

1. append to `data/state/prediction_runs.csv` (authoritative, `origin=local_inference`);
2. add one `prediction_origin=user_evaluation` row to
   `dataset/predictions/user-predictions.csv`.

That second file is **private**: it is listed in `.gitignore` and never enters
version control, because a user's own reading and evaluation history is not
release data. The tracked `dataset/predictions/predictions.csv` holds only
`prediction_origin=dataset_original` rows and is never rewritten by the running
application — only the release-preparation script produces it — so its content
digest (`prt-dataset-content-v1`, value
`f492a7d30056d0588e93e81202299673229a7c980b881517fee2fe9df0e39451`) is
untouched by anything a user does.

At startup a mirrored row missing from state restores the run, so the local
history survives deleting `data/`; `prediction_run_id` uniqueness prevents
duplication. The paper-worthy detail is the split itself: the same row shape
serves as a human-inspectable recovery log without the shared corpus ever
absorbing private activity.

**Clearing it.** One confirmed action deletes every `local_inference` run, all
saved content and this mirror. Order matters and is asserted by a test: the
mirror goes first, because clearing the ledger first and crashing would let the
surviving mirror restore the "deleted" runs at the next start.

---

## 4. Dataset actually present in the repo

`dataset/predictions/` (tracked in git; ~6.6 MB):

| Measure | Value | Source |
| --- | ---: | --- |
| `dataset_original` rows | 17,283 | `manifest.json` |
| `user_evaluation` rows | 0 (private mirror, not this file) | `manifest.json` |
| Derived articles | 17,269 | recomputed from `prediction_runs.csv` |
| Prediction runs | 34,564 | recomputed |
| Distinct publishers | **372** | recomputed |
| Minimum articles per publisher | **20** (release threshold) | by construction |
| Median articles per publisher | **33**, max **294** | recomputed |
| Historical model/fold identities | 10 (BERT×5, RoBERTa×5) | recomputed |
| Articles in >1 fold (excluded from safe evaluation) | 13 (26 article/family memberships) | `docs/scientific-contract.md` §3 |

Predicted-class distribution over the 34,564 bundled runs (recomputed):
`class 0: 8,755 · 1: 4,985 · 2: 7,847 · 3: 10,296 · 4: 2,681`.

Largest publishers by run count: `politicshome.com` (588), `ntd.com` (458),
`theguardian.com` (420), `news.sky.com` (402), `middleeasteye.net` (400).

### Corpus provenance (from the manuscript, §IV)

Publishers were filtered to NewsGuard outlets tagged *Political News and
Commentary*, publishing primarily in English, without a paywall; `l1` was capped
at 175 publishers to stop the corpus being dominated by unreliable sources,
giving 669 selected outlets. Articles were scraped from each publisher's
homepage with Newspaper3k, at most 200 per outlet, keeping only items of at
least 100 words — 25,822 articles. `langdetect` then removed 6,346 non-English
articles, leaving **19,476**. Each article inherits its publisher's band, so
supervision is weak by construction.

### Publisher threshold, and the one number still unreconciled

**Publishers — settled by a decision, not by analysis.** The manuscript reports
**439** scraped domains (Table I: 152+69+95+88+35) and says "19,476 articles
from 439 publishers", while the source prediction file carried **838** distinct
values in its own `domain` column. That gap was already present in the training
data, not introduced by PRT's URL normalisation, and no article-count threshold
reproduces 439 exactly (≥10 articles → 466, ≥20 → 372).

The release therefore ships only publishers with **≥20 classified articles**,
which is a defensible line on its own terms: the aggregation needs at least two
leakage-safe articles, and a publisher verdict resting on two or three says more
about the sample than about the outlet. It removes 466 of the 838 domains but
only 2,146 of 19,429 rows (11%), so the demonstration keeps almost all of its
evidence while every remaining outlet is substantial enough to aggregate. The
released domain count is now *below* the study's 439 and is explained as a
deliberate subset, which is a far easier sentence to defend than an unexplained
838.

**Still open — cap per outlet.** The manuscript states a cap of 200 articles per
outlet, but the largest publisher in the release has **294**. The threshold does
not touch this; it is flagged with a `% TODO:` in the paper.

Only BERT and RoBERTa outputs are in the release, which matches the tool's
scope: the larger decoder families are not importable here at all.

---

## 5. Models

Four families, three acquisition paths.

### 5.1 Core CPU path (BERT / RoBERTa)

| Family | Artifact | Base | Encoding |
| --- | --- | --- | --- |
| BERT | `bert_fold_N.pt` | `bert-base-uncased` | 5-label head, fixed pad/truncate to 256 |
| RoBERTa | `roberta_fold_N.pt` | `roberta-large` | 5-label head, fixed pad/truncate to 256 |

Loaded with `torch.load(..., map_location="cpu", weights_only=True)`, strict
key/shape check, `eval()`, softmax over 5 logits. These are the reproducibility
gate: a frozen CPU float32 fixture must match to absolute `1e-6` / relative
`1e-5` before a loader is marked `compatible`
(`docs/scientific-contract.md` §10).

**Measured on the demo machine** (AMD Ryzen 7 2700U, 4 cores/8 threads,
16 GB RAM, Ubuntu 26.04, no CUDA — `torch.cuda.is_available()` is `False`),
inference only, 5 warm repetitions on a ~256-token article:

| Family | Load + first inference | Warm inference (median) | Range |
| --- | ---: | ---: | ---: |
| BERT fold 1 | 8.8 s | **0.90 s** | 0.80–1.21 s |
| RoBERTa fold 1 | 4.8 s | **2.87 s** | 2.28–3.12 s |

End-to-end (retrieval + extraction + inference), from the three committed
`user_evaluation` rows: 5.1 s, 5.6 s, 6.9 s. Load times include first-use
tokenizer acquisition and are sensitive to page cache, so only the warm and
end-to-end figures went into the paper.

Present locally (`models/`, untracked, ~7.7 GB) at the time of this analysis:
`bert_fold_1..5.pt` (418 MB each) and `roberta_fold_1..4.pt` (1.35 GB each) —
`roberta_fold_5.pt` was missing, consistent with `data/state/models.csv`
holding 19 rows (10 `historical_only` + 5 BERT `compatible` + 4 RoBERTa
`compatible`). The user confirmed this was their own oversight, not a
deliberate exclusion, and is adding the fold-5 checkpoint locally; it is
git-ignored like the rest of `models/*.pt`, so this needed no repository
change.

### 5.2 Larger decoder models are no longer part of the tool

The study also fine-tuned Llama 3 8B and Mistral 24B, but this release neither
imports nor runs them, by decision: each fold needs a CUDA GPU and several
gigabytes of weights that the demo machine does not have, and the two encoders
report comparable accuracy in the study. Any import attempt is refused with
`FEATURE_UNAVAILABLE` and installs nothing.

What is claimed in the paper is the *extensibility*, not the feature: model
identity is content-addressed over output-relevant settings rather than an
architecture name, the loader registry is keyed by family, and the leakage guard
records fold membership per article, so a family added later is already covered.
The validation and loader code for LoRA adapters remains in the codebase as that
extension point; it is unreachable from any user-facing path.

### Incomplete, absent or unverifiable here

- **`roberta_fold_5.pt` is missing** from `models/`, so one of the ten core
  checkpoints cannot be exercised locally.
- **Large decoder import is disabled in the product** and the machine has **no
  CUDA** (`torch.cuda.is_available()` is `False`). The checksum authentication,
  QLoRA reconstruction and decoder inference paths are therefore retained but never
  run-verified. Per the user's instruction this is now a deliberate framing
  rather than a gap: the paper presents BERT/RoBERTa as the demonstrated path
  and the LLM checkpoints as extensibility.
- **Publisher classes are derived, never stored** — there is no ledger for them; zero publisher
  aggregations have ever been created in this workspace. The aggregation code
  path is unit-tested but has no stored real result.
- **Zero user CSV imports**: `imports.csv` holds only the bundled-manifest row.
- `docs/acceptance-tests.md` defines AT-001…AT-054; only 30 automated tests
  exist. The mapping from acceptance tests to automated tests is not machine-
  checkable and several ATs (Compose startup, disk-full, fault matrices, UI
  navigation) are clearly manual.
- No CI configuration, no `.github/` directory.
- No demo video, no hosted demo, no screenshots in the repo — the user is
  producing both the screencast and the screenshots.
- No accuracy/evaluation numbers of any kind — by design: the tool "does not
  calculate accuracy against protected labels"
  (`docs/scientific-contract.md` §9). The demo paper has **no quantitative
  results section available from this repository**.
- Explicitly out of scope (`docs/product-specification.md` §4): auth, multi-user,
  non-loopback hosting, TLS, job retry/cancel, SSE, storage compaction, model
  training/tuning/calibration, hosted inference, telemetry.

---

## 9. Open questions — status after receiving the paper and notebook

**Resolved.**

1. ~~Naming the label provider~~ — NewsGuard, and the user has confirmed it may
   be named. Original labels/scores must never ship; predictions from models
   trained on them may.
2. ~~Semantics of classes 0–4~~ — established from the notebook output and
   Table I: 0 = score 0–39 (least reliable) … 4 = score 100 (most reliable).
   See §1.
3. ~~Corpus provenance~~ — NewsGuard *Political News and Commentary*, English,
   paywall-free, Newspaper3k homepage scrape, ≤200 per outlet, ≥100 words,
   `langdetect` filter. See §4.
4. ~~Training setup~~ — from the notebook: 5-fold publisher-stratified CV, seed
   42, 5 epochs. BERT `bert-base-uncased`, AdamW, lr 2e-5, max_len 256, batch
   32/16. RoBERTa `roberta-large`, lr 2e-5, max_len 256, batch 16/8, AMP with
   `GradScaler`, deterministic algorithms enabled.
5. ~~Paper status~~ — under review at IEEE Transactions on Computational Social
   Systems; cited as such. Single-blind review, so the self-citation is fine.
7. ~~Demo hosting~~ — the user will record the screencast; the paper keeps a
   placeholder URL.
8. ~~Authorship~~ — Bianchi (IMT Lucca), Pratelli (IIT-CNR), Pinelli (IMT
   Lucca), Petrocchi (IIT-CNR + IMT Lucca), in that order.
10. ~~CUDA availability~~ — none on the demo machine. The tool now refuses to
    import the larger decoder models altogether, and the paper presents
    BERT/RoBERTa as the shipped path with the decoder family described only as
    a prepared extension point.
11. ~~ORCID identifiers~~ — the user supplied the real IDs (`\orcidID` in
    `main.tex`): Bianchi `0009-0006-2582-1480`, Pratelli `0000-0002-9978-791X`,
    Pinelli `0000-0003-1058-6917`, Petrocchi `0000-0003-0591-877X`.
12. ~~Repository visibility~~ — confirmed public by the user; the Availability
    TODO asking to confirm it was removed.
13. ~~`roberta_fold_5.pt` missing~~ — the user confirmed it was their own
    oversight, not a deliberate exclusion, and is adding it locally. It is
    git-ignored like the rest of `models/*.pt` (only `models/README.md` is
    tracked), so no repository change was needed for this.

**Still open.**

- **The 200-vs-294 article cap** (§4). The 439-vs-838 publisher gap is settled:
  the release now ships only outlets with ≥20 classified articles (372). The
  user has seen this and will look into it separately — the `% TODO:` in
  `main.tex` is left as-is rather than reconciled or removed.
- **Funding for the demo paper.** The acknowledgement currently reuses the
  manuscript's SIMULARE project; confirm that is the right attribution here.
