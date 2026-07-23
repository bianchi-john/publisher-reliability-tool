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

Optional research artifacts use `llama_fold_N.pt` or an official Mistral PEFT
fold directory.

> [!NOTE]
> The current software version browses and aggregates historical predictions,
> but does not yet validate or execute these artifacts. Model loading and new
> inference are the next implementation milestone.

The application never downloads weights, manages Hugging Face credentials or
executes code supplied by an artifact.
