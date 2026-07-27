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

The scanner also recognizes the exact official OSF filenames
`mistral_fold_N.zip` and the pair
`llama_fold_N.pt.z01` + `llama_fold_N.pt.z02`. It imports a complete fold only
after checking the packaged OSF size and SHA-256 values. The same workflow is
available from **Models → Import an original paper model from OSF**, where the
download catalog is shown directly.

Custom five-class Hugging Face sequence classifiers—including compatible Llama
3 8B and Mistral 24B PEFT adapters—are imported from the Models page as
self-contained `.zip` bundles and are marked as user models. See
[`docs/custom-model-bundle.md`](../docs/custom-model-bundle.md) for the exact
safe format.

The application never manages Hugging Face credentials or executes code
supplied by an artifact. BERT/RoBERTa acquire only pinned tokenizer resources.
Llama/Mistral inference requires the pinned base-model snapshot; authenticate
with Hugging Face outside this application when a gated repository requires it.
