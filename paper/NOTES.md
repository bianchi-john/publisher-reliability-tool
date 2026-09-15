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
| `services.py` | 1004 | `ResearchService`: all read queries, `available_models()`, `evaluate()` |
| `api.py` | 574 | 30 HTTP routes, Pydantic request models, error mapping, static frontend |
| `custom_models.py` | 566 | Validation/installation of user `.zip` model bundles (schema 1 & 2) |
| `inference.py` | 543 | Safe retrieval, English extraction, `InferenceEngine` (4 loader recipes) |
| `importer.py` | 589 | CSV / CSV.GZ projection, validation, conflict detection, idempotent import |
| `prediction_dataset.py` | 490 | Public-release verification + idempotent mirroring of local runs |
| `official_models.py` | 445 | OSF filename/size/SHA-256 authentication of Llama/Mistral artifacts |
| `storage.py` | 312 | Seven CSV ledgers, `flock`, append+fsync, atomic rename |
| `model_scanner.py` | 303 | Scans configured roots for recognized artifacts (no symlink following) |
| `jobs.py` | 253 | Single FIFO worker, persisted job rows, macro-phase progress |
| `cli.py` | 200 | `serve`, `dataset verify|import`, `models scan`, `storage verify` |
| `aggregation.py` | 117 | The three publisher-level formulas |
| `identity.py` | 110 | URL normalization, UUIDv5 article IDs, publisher hostname |
| `config.py` | 79 | `PRT_*` env vars + CLI options |
| `errors.py` | 41 | 18 stable error codes with fixed HTTP statuses |
| `frontend/` | ~930 | `index.html` (52) + `app.js` (642, vanilla ES modules) + `styles.css` (240) |

Total application code ≈ 5.2k LOC Python + ~0.9k LOC frontend. Tests: 10 files,
~1.4k LOC, **30 tests, all passing** (verified: `python -m unittest discover -s
tests` → `Ran 30 tests in 1.449s / OK`).

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
| `evaluations.csv` | **immutable append** | every publisher-level aggregation |
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
2. rewrite `dataset/predictions/predictions.csv` adding one row with
   `prediction_origin=user_evaluation`, then refresh `manifest.json`.

Original release rows carry `prediction_origin=dataset_original` and are never
rewritten. The stable release identity is a content digest
(`prt-dataset-content-v1`, value
`7b15a415471653980b1bc38d05565afa25df5d96d50d9ca1e586035a2ada54c5`) computed
**only over original rows**, so appending user evaluations changes the file
checksum and counts but not the scientific identity of the release. At startup a
mirrored row missing from state can restore the run; `prediction_run_id`
uniqueness prevents duplication. This is a neat, paper-worthy detail: the
"dataset" doubles as a human-inspectable recovery log.

---

## 4. Dataset actually present in the repo

`dataset/predictions/` (tracked in git; ~7.4 MB):

| Measure | Value | Source |
| --- | ---: | --- |
| CSV rows (schema v2) | 19,432 | `manifest.json` |
| `dataset_original` rows | 19,429 | `manifest.json` |
| `user_evaluation` rows | 3 | `manifest.json` (grows with use) |
| Derived articles | 19,411 | recomputed from `prediction_runs.csv` |
| Prediction runs | 38,854 | recomputed |
| Distinct publishers | **838** | recomputed (not stated in any doc) |
| Publishers with ≥2 articles | **597** | recomputed |
| Median articles per publisher | **15**, max **294** | recomputed |
| Historical model/fold identities | 10 (BERT×5, RoBERTa×5) | recomputed |
| Articles in >1 fold (excluded from safe evaluation) | 16 (32 article/family memberships) | `docs/scientific-contract.md` §3 |

Predicted-class distribution over the 38,854 bundled runs (recomputed):
`class 0: 9,388 · 1: 5,919 · 2: 9,166 · 3: 11,308 · 4: 3,076`.

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

### ⚠ Two numbers that do not reconcile

These need the user's decision before submission:

1. **Publishers.** The manuscript reports **439** scraped domains (Table I:
   152+69+95+88+35) and says "19,476 articles from 439 publishers". The shipped
   release has **838** distinct values in its own `domain` column, and the tool's
   URL normalisation reproduces exactly those 838 — so this is not a
   normalisation artefact introduced by PRT, it is already in the training data.
   No article-count threshold reproduces 439 (≥10 articles → 466, ≥20 → 372).
2. **Cap per outlet.** The manuscript states a cap of 200 articles per outlet,
   but the largest publisher in the release has **294**.

I have written the release's own verifiable figures into the demo paper and
flagged both mismatches with a `% TODO:` there.

Only BERT and RoBERTa outputs are in the release. **Llama and Mistral hard
labels are deliberately absent because their per-class probabilities were not
available** (`docs/user-guide.md` §1, `docs/scientific-contract.md` §3) — a
limitation to state honestly in the paper rather than paper over.

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

### 5.2 Original paper LLMs (Llama 3 8B / Mistral 24B)

From `official-model-manifest-v1.json` — 10 entries, 5 folds each:

| Family | Base (pinned revision) | Artifact shape | LoRA | Max tokens |
| --- | --- | --- | --- | ---: |
| Llama 3 8B | `meta-llama/Meta-Llama-3-8B` @ `8cde5ca8…` | two OSF segments `llama_fold_N.pt.z01` + `.z02` reconstructed into one quantized state dict (~5.8 GB/fold) | r=8, α=16, dropout 0.05 | 256 |
| Mistral 24B | `mistralai/Mistral-Small-24B-Base-2501` | one PEFT adapter `mistral_fold_N.zip` | r=16, α=32 | 1024 |

Both: `AutoModelForSequenceClassification`, 5 logits, NF4 double quantization +
bfloat16, dynamic-longest padding, LoRA targets
`q_proj,k_proj,v_proj,o_proj,gate_proj,down_proj,up_proj`. Import authenticates
the **exact filename set + published byte size + SHA-256** against the packaged
manifest before marking an artifact `paper_official`. Running them needs CUDA,
the `llm-models` extra and access to the pinned (for Llama, *gated*) base
snapshot; on an unsuitable machine the model stays `validated_not_runnable` —
verified and inspectable but not executable.

**Honest limitation already recorded in the repo**
(`docs/scientific-contract.md` §5.2): the training notebooks name the two base
repositories but did not record training-time commits. The manifest revisions
are "frozen reconstruction references selected on 2026-07-27", *not* a claim
about the commit actually used during training.

### 5.3 User custom bundles

A constrained `.zip` with a declarative `prt-model.json`:
- **schema 1** — complete encoder classifier (`config.json` +
  `model.safetensors` + local tokenizer), architecture allowlist;
- **schema 2** — PEFT LoRA adapter for exactly the two bases above.

Both must declare 5 classes in order 0–4 and a held-out fold `1..5`. Validation
is offline with `trust_remote_code=false` and rejects `auto_map`, Python/native
files, pickle/`.pt` weights, unsafe ZIP paths or symlinks, remote tokenizer
dependencies, non-finite tensors and any key/shape mismatch. **The application
never executes code shipped inside an artifact** (FR-013).

### 5.4 Model identity

A runnable model ID is `SHA-256` of canonical sorted-key JSON over *every*
output-relevant setting — artifact digest, manifest-entry digest, family, fold,
loader recipe + version, base model + immutable revision, tokenizer source +
revision, class order, max tokens, padding policy, adapter digest, dtype and
quantization — and **excludes filesystem location**. The artifact digest is
re-checked immediately before loading, so bytes changed after scanning cannot
run under the earlier identity. Imported history gets a separate
non-runnable `historical_virtual` ID. Consequence: a historical dataset
prediction and a locally installed checkpoint of the same family/fold keep
*distinct* scientific IDs and are never conflated — this is enforced in
`available_models()` by intersecting them on `(family, fold)` while returning
both `model_id` and `local_model_id`.

---

## 6. The leakage guard (the interesting bit)

`docs/scientific-contract.md` §8.1, implemented in
`ResearchService._imported_fold_registry()` / `_fold_is_safe()` /
`assert_not_training_article()`.

For the imported five-fold corpus, `<family>_fold_id=N` means the stored
prediction was produced *for held-out test fold N*, i.e. checkpoint `N` was
trained on the other four folds. Therefore:

- checkpoint fold `N` **may** evaluate a known article assigned to test fold `N`;
- checkpoint fold `N` **must reject** a known article assigned to any other
  fold, with the stable error `TRAINING_DATA_LEAKAGE` (HTTP 409);
- publisher evaluation silently **excludes** every known article outside the
  checkpoint's held-out fold;
- the 16 articles that normalize into more than one fold are excluded from safe
  evaluation entirely, because no single held-out fold can be established;
- the guard is enforced **server-side** for single articles, explicit lists and
  publisher candidates — not merely by hiding options in the UI.

And a carefully stated non-claim: absence from the registry is *not* proof an
arbitrary external URL was outside every possible training corpus. The tool
never infers membership from publication date, hostname, text similarity or a
previous local inference; evaluating an external URL with fold 1 does not assign
it to fold 1 and does not block fold 2.

---

## 7. Interaction flow

Entry: `publisher-reliability serve` → `http://127.0.0.1:8000`, or
`docker compose up --build` (published only on `127.0.0.1:8000`).

Startup is an 11-step ordered sequence (`docs/product-specification.md` §6),
notably: reserve the port *before* touching the data directory; acquire the
directory lock; structurally verify all seven ledgers (fail closed); verify and
import the bundled release by content digest; scan model roots; restore and
re-synchronize the prediction mirror; start the FIFO worker; only then accept
HTTP and report `ready`.

Seven UI pages (`frontend/index.html` nav + `app.js` `routes`):
**Dashboard · Evaluate · Articles & predictions · Publishers · Models ·
Imports · Jobs**, plus a link to `/api/docs`.

The characteristic flow is **Evaluate**:

1. User picks *Single article* or *Publisher* and pastes a URL.
2. Frontend calls `GET /api/v1/models/available` (debounced). The backend
   normalizes the URL, looks up stored coverage for that article/publisher,
   intersects it with the **local** model inventory by `(family, fold)`, applies
   the leakage guard, and returns per-option `mode`
   (`stored_prediction` | `new_local_inference`), `article_count`, `run_count`,
   `eligible`, `local_status`, `local_runnable` — plus explicit explanations for
   the empty case. The selector is therefore *derived*, never a hard-coded
   catalog.
3. User chooses `prediction_action` (`reuse` default | `recompute`) and
   `content_retention` (`discard` default | `save_local`). In single-article
   mode, publisher count / aggregation method / partial-result controls are
   hidden because they do not apply.
4. `POST /api/v1/evaluation-jobs` → 202 + job ID; the browser polls
   `GET /api/v1/jobs/{id}` every 2 s (no SSE, no cancel, no retry).
5. On a new inference the worker: fetches the page over the hardened client
   (HTTP(S) only, ≤5 validated redirects, private/loopback/link-local/multicast
   addresses rejected, `trust_env=false`, 10 s connect / 20 s request, HTML MIME,
   8 MiB decompressed cap, `Accept-Language: en-US,en;q=0.9`) → Newspaper3k with
   `language="en"` on the already-downloaded HTML (no second request, no
   fallback extractor) → requires ≥200 characters and ≥30 tokens → `langdetect`
   with `DetectorFactory.seed = 0` requiring exactly `en` → tokenizer → model →
   softmax.
6. The result card shows predicted `Class 0..4`, all five probabilities as
   decimals and percentage bars, exact family/fold, stored-vs-new origin, run ID
   and a link to full article history. A "Recent user article evaluations" table
   survives a page refresh.

Observed CPU latency from the three real `user_evaluation` rows currently in
`dataset/predictions/predictions.csv` (end-to-end, retrieval + extraction +
inference, `device=cpu`): BERT **6,903 ms** and **5,584 ms**, RoBERTa
**5,058 ms**. Sample of three — not a benchmark.

Publisher mode aggregates only *already stored*, leakage-safe runs for that
hostname; it never crawls the site or infers missing articles. `allow_partial`
switches between "use 2..requested safe articles" and "require the full count"
(`INSUFFICIENT_ARTICLES` otherwise).

Aggregation formulas (`aggregation.py`, all version `1`, all requiring 2–50
runs from one model):

| Method | Rule | Tie-break |
| --- | --- | --- |
| `majority_vote` | most frequent hard class (matches `pandas.Series.mode()[0]`) | smallest class |
| `ordinal_mean` | mean of hard classes, stored full precision, displayed to 3 dp, class = `floor(mean + 0.5)` | halves round up |
| `mean_probabilities` | component-wise mean of the five vectors | smallest argmax index |

Every evaluation persists the **ordered** article IDs and prediction-run IDs it
used, so a later run can never change an earlier result.

---

## 8. What is done vs. what is not

### Working (verified by running the code or by reading tracked state)

- 30/30 automated tests pass on this machine.
- Bundled release verified and imported: 38,854 runs, 19,411 articles,
  838 publishers, 19 model rows in `models.csv`.
- Nine of ten core checkpoints registered `compatible` and runnable on CPU.
- Three real local inferences committed and mirrored end-to-end.
- Full REST API + OpenAPI 3.1 at `/api/docs`; CLI with 5 commands; Docker
  Compose service; offline mode; local fonts, no CDN, no telemetry.

### Incomplete, absent or unverifiable here

- **`roberta_fold_5.pt` is missing** from `models/`, so one of the ten core
  checkpoints cannot be exercised locally.
- **No Llama or Mistral artifact is present** (`models/` holds only BERT and
  RoBERTa `.pt` files), and the machine has **no CUDA**
  (`torch.cuda.is_available()` is `False`). The OSF authentication, QLoRA
  reconstruction and LLM inference paths are therefore code-verified but never
  run-verified. Per the user's instruction this is now a deliberate framing
  rather than a gap: the paper presents BERT/RoBERTa as the demonstrated path
  and the LLM checkpoints as extensibility.
- **`data/state/evaluations.csv` contains only its header** — zero publisher
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
10. ~~CUDA availability~~ — none on the demo machine. This is why the paper
    presents BERT/RoBERTa as the demonstrated path and Llama/Mistral as
    extensibility, per the user's instruction.
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

- **The 439-vs-838 publisher count and the 200-vs-294 article cap** (§4). The
  user has seen this and will look into it separately — the `% TODO:` in
  `main.tex` is left as-is rather than reconciled or removed.
- **Funding for the demo paper.** The acknowledgement currently reuses the
  manuscript's SIMULARE project; confirm that is the right attribution here.
