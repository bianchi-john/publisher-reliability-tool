# Dataset input

`sampleDataset.csv` is a synthetic schema example, not research data. Its URLs,
texts, authors, predictions, and probabilities are illustrative placeholders.

At runtime the user may select a CSV of any size with the same permitted
structure. The importer reads it incrementally, leaves it unchanged, and stores
only allowlisted article identifiers and model outputs in the local database.
Protected reference labels, scores, and provider metadata are ignored before
persistence and must never be committed.

`fullDataset.csv` and all datasets other than the tracked sample are ignored by
Git.
