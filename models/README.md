# Local model directory

Place trusted checkpoints here or pass another path when starting the future
application. Model weights are intentionally ignored by Git.

Download the official released artifacts from:

<https://osf.io/r9atz/overview?view_only=e4bda170a3e74ca3ae245475d4486d74>

The application scans every supplied model path recursively. The observed
release layout is:

```text
Models/
├── Fold 1/
│   ├── .ipynb_checkpoints/       # ignored
│   ├── bert_fold_1.pt
│   ├── llama_fold_1.pt
│   └── roberta_fold_1.pt
└── fold_1/
    ├── adapter_config.json
    ├── adapter_model.safetensors
    ├── README.md                 # optional, never executed
    ├── tokenizer_config.json
    └── tokenizer.json
```

No renaming is required. `Fold 1` and `fold_1` may coexist on Linux. Hidden
directories such as `.ipynb_checkpoints` are ignored.

The BERT, RoBERTa, and Llama notebooks save fold-specific PyTorch `state_dict`
files. Their recognized names are:

- `bert_fold_N.pt`;
- `roberta_fold_N.pt`;
- `llama_fold_N.pt`.

Mistral uses the complete `fold_N/` directory rather than a `.pt` file. The
four required files are `adapter_config.json`, `adapter_model.safetensors`,
`tokenizer_config.json`, and `tokenizer.json`; `README.md` is optional. The
application validates the PEFT configuration and file contents instead of
trusting the directory name alone.

Any available fold may be used. All four families use versioned built-in
loading recipes documented in `docs/scientific-contract.md`.

The `.pt` file does not contain its tokenizer or full base-model configuration.
The Mistral directory contains its adapter and tokenizer, but not
`mistralai/Mistral-Small-24B-Base-2501`. Required base-model dependencies must
already be cached locally or be downloaded during an explicit setup action.
