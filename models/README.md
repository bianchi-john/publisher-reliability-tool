# Local models

> Place manually downloaded model artifacts here. Their contents are ignored by
> Git and are never distributed with this repository.

Official artifacts are available from
[OSF](https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74).

Expected core filenames:

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

Custom five-class Hugging Face sequence classifiers are imported from the
Models page as self-contained `.zip` bundles. See
[`docs/custom-model-bundle.md`](../docs/custom-model-bundle.md) for the exact
safe format.

The application never downloads base-model weights, manages Hugging Face
credentials or executes code supplied by an artifact. It may acquire only the
pinned tokenizer/configuration files required by a core checkpoint.
