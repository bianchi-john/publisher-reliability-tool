# Local models

> Place manually downloaded model artifacts here. Their contents are ignored by
> Git and are never distributed with this repository.

Official artifacts are available from
[OSF](https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74).

Expected filenames:

```text
bert_fold_1.pt
…
bert_fold_5.pt

roberta_fold_1.pt
…
roberta_fold_5.pt
```

> [!NOTE]
> The Models page scans these filenames and safely validates BERT/RoBERTa
> checkpoint structure, shapes and finite tensor values. A validated checkpoint
> is not treated as the identity that produced historical dataset predictions.
> A compatible checkpoint can classify new public English article URLs. Its
> pinned official tokenizer is cached on first online use.

Verifying a checkpoint reads it twice, once for its SHA-256 and once for its
structure, so the first scan of several gigabytes takes a while. A file left
untouched since the previous scan reuses that result and later starts are quick;
adding, replacing or modifying a file has it verified again. Run
`publisher-reliability models scan --full` to re-read every byte on demand.

## Larger decoder checkpoints are not importable yet

The study also fine-tuned Llama 3 8B and Mistral 24B, and their artifacts are on
OSF, but **this release cannot import them**. Each fold needs a CUDA GPU and
several gigabytes of weights, which a single-machine CPU demo cannot assume, so
any attempt to import one is refused with `FEATURE_UNAVAILABLE` and nothing is
installed. BERT and RoBERTa run here on CPU and report comparable accuracy in
the study.

## Custom models

Custom five-class Hugging Face **encoder** sequence classifiers are imported from
the Models page as self-contained `.zip` bundles and are marked as user models.
Decoder-only architectures and PEFT adapters are rejected for the same reason as
above. See [`docs/custom-model-bundle.md`](../docs/custom-model-bundle.md) for
the exact safe format.

The application never manages Hugging Face credentials or executes code supplied
by an artifact. BERT and RoBERTa acquire only pinned tokenizer resources; no
base-model weights are ever downloaded.
