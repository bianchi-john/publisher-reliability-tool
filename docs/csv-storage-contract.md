# CSV Storage Contract

**Status:** Normative research-demo persistence contract
**Schema version:** `1`

## 1. Scope

The demo stores essential persistent state in seven UTF-8 CSV ledgers. It is a
single-process research store, not a transactional database. Files are designed
to be inspected with Python or a spreadsheet and reconstructed at startup.

```text
<data-dir>/
├── .writer.lock
├── state/
│   ├── meta.csv
│   ├── models.csv
│   ├── prediction_runs.csv
│   ├── evaluations.csv
│   ├── imports.csv
│   ├── jobs.csv
│   └── local_content.csv
├── staging/
├── uploads/
├── managed-models/
└── logs/
```

Only `state/*.csv` is authoritative. Articles and publishers are derived views
over prediction runs. Uploads, staging files, managed model artifact bytes,
indexes, logs, and the writer lock are operational; losing managed artifact
bytes disables new inference but does not lose historical scientific records.

## 2. Physical rules

- UTF-8 without BOM; application writes LF line endings.
- Python `csv` dialect: comma delimiter, double-quote escaping, quoted embedded
  commas/newlines.
- Exact header as documented below.
- Null optional scalar is an empty field; JSON fields are compact sorted-key
  JSON and use `[]`/`{}` rather than an empty field when required.
- Boolean is `true` or `false`; timestamps are UTC RFC 3339 ending in `Z`.
- Integers are base 10; floats are finite Python round-trip decimals.
- URLs are normalized absolute HTTP(S) URLs.
- Probability fields are either all empty or five finite values in `[0,1]`
  summing to one within `1e-5`.
- Maximum URL is 8,192 UTF-8 bytes, saved title 1 MiB, saved text 16 MiB, and
  other individual fields 1 MiB.

## 3. Identifiers

Application UUID namespace:
`6f63a5f4-97aa-4bb8-a73f-2a30fc9fcf31`.

- `article_id`: UUIDv5 of `article:<canonical_url>`.
- `publisher_id`: UUIDv5 of `publisher:<normalized_hostname>`.
- local prediction run, evaluation, job, and structurally invalid import:
  UUIDv4.
- successful or row-validatable import: UUIDv5 of
  `import:<content_sha256>:<schema_version>`.
- imported run: UUIDv5 of
  `prediction-run:<article_id>:<model_id>:import:<import_id>`.
- `model_id`: lowercase SHA-256 of the scientific identity JSON.

IDs and immutable rows are never reused for another scientific result.

## 4. Write rules

One process holds `.writer.lock`; a process mutex serializes all writes.

Immutable ledgers (`prediction_runs.csv`, `evaluations.csv`, `imports.csv`) use
one complete CSV record append followed by flush/fsync. A malformed incomplete
final physical record can therefore be backed up and removed at startup. A
malformed middle record, duplicate immutable ID, invalid reference, or invalid
scientific value is `STORAGE_ERROR` and is not guessed or repaired.

Small mutable ledgers (`models.csv`, `jobs.csv`, `local_content.csv`) are loaded
as keyed maps. An update writes the complete new ledger to `<name>.tmp`, verifies
it, flushes/fsyncs it, and replaces the live file atomically. A leftover valid
temporary file is ignored and removed at startup because the live filename is
the only committed mutable state.

Import is the one multi-file operation. Parsing writes projected rows under a
private staging directory. After full conflict validation, the importer writes
complete replacement candidates for `prediction_runs.csv`, `imports.csv`, and
`models.csv`, fsyncs them, and writes `staging/import.pending.json` containing
the import ID, three target names, and their SHA-256 digests. It then replaces
the three targets and removes the marker. On startup, each target that already
has its recorded digest is complete; otherwise its still-present prepared file
must match and is installed. If neither copy matches, startup fails closed.
This small, import-specific roll-forward rule replaces a generic transaction
system.

No compaction, record versions, tombstones, transaction ledger, commit
sequence, or pagination snapshot is part of schema version 1.

## 5. Ledger schemas

### 5.1 `meta.csv`

```text
schema_version,created_at,application_version
```

Exactly one data row. Unknown schema versions fail startup.

### 5.2 `models.csv`

```text
model_id,family,fold_id,display_name,artifact_kind,artifact_locator,artifact_sha256,official_manifest_entry_sha256,loader_recipe,loader_recipe_version,base_model,base_revision,tokenizer_source,tokenizer_revision,class_order_json,max_tokens,padding_policy,adapter_config_sha256,runtime_scientific_json,status,artifact_available,runnable,status_detail,registered_at,last_validated_at
```

- `family`: `bert`, `roberta`, `llama`, `mistral`, or the imported historical
  family name allowed by the scientific contract.
- `status`: `compatible`, `historical_only`, `artifact_missing`,
  `dependency_missing`, `resource_unavailable`, or `invalid`.
- `artifact_locator` is deployment metadata and excluded from identity; API
  output reduces it to a root label and relative path.
- Historical virtual models have no locator/artifact and are not runnable.
- Every output-relevant recipe, revision, tokenizer, class order, length,
  padding, adapter, dtype, and quantization setting participates in model ID.

### 5.3 `prediction_runs.csv`

```text
prediction_run_id,article_id,canonical_url,publisher_id,normalized_hostname,model_id,predicted_class,prob_class_0,prob_class_1,prob_class_2,prob_class_3,prob_class_4,origin,action,input_source,content_retention,source_import_id,job_id,inference_started_at,inference_completed_at,duration_ms,device,software_versions_json,recorded_at
```

- This is immutable append-only history.
- `origin`: `bundled_import`, `user_import`, or `local_inference`.
- `action`: `import`, `missing_run_inference`, or `recompute`.
- `input_source`: `unavailable`, `saved_local`, or `ephemeral_web`.
- Imports require `source_import_id`; inference requires `job_id`.
- New inference requires five probabilities. Historical vectors may be absent.
- Canonical URL and normalized hostname are intentionally denormalized so the
  complete article/publisher history is understandable in one ledger.

The reusable run for `(article_id,model_id)` is the greatest effective
completion time (`inference_completed_at`, falling back to `recorded_at` for
imports), then lexicographically smallest run ID on a timestamp tie.

### 5.4 `evaluations.csv`

```text
evaluation_id,publisher_id,normalized_hostname,model_id,method,method_version,input_mode,requested_count,used_count,partial,result_class,ordinal_mean,prob_class_0,prob_class_1,prob_class_2,prob_class_3,prob_class_4,article_ids_json,prediction_run_ids_json,job_id,created_at,warnings_json
```

- Immutable append-only publisher result.
- `input_mode`: `article_list` or `publisher`.
- `article_ids_json` and `prediction_run_ids_json` are equally sized ordered
  arrays of 2–50 exact IDs; every run resolves to its paired article, publisher,
  and evaluation model.
- `method`: `majority_vote`, `ordinal_mean`, or `mean_probabilities`.
- `partial=true` exactly when `used_count < requested_count`.

Keeping ordered membership in this row avoids a separate join ledger and makes
the scientific provenance directly inspectable.

### 5.5 `imports.csv`

```text
import_id,source_kind,source_name,content_sha256,transport_sha256,schema_version,status,source_rows,accepted_rows,rejected_rows,duplicate_rows,protected_columns_json,warnings_json,started_at,completed_at
```

- `source_kind`: `bundled_manifest`, `csv`, or `csv_gz`.
- `status`: `succeeded`, `succeeded_with_rejections`, or `failed`.
- `source_name` is a basename/logical release name, never an absolute path.
- Warnings may contain safe row number/error-category summaries but never raw
  rows, title/text/author values, or protected values.
- A successful `(content_sha256,schema_version)` is unique and reused.

`content_sha256` uses `prt-dataset-content-v1`: parse logical records in source
order, project the supported public columns, serialize each projected record
with the repository generator's UTF-8 RFC-4180 field order, and SHA-256 their
concatenation. Editorial/blocked fields are excluded. CSV and CSV.GZ therefore
share identity; the bundled manifest part boundaries do not affect it.

### 5.6 `jobs.csv`

```text
job_id,job_type,status,phase,progress,request_json,result_json,error_code,error_message,created_at,started_at,finished_at,updated_at
```

The persisted job-type registry is: `evaluation`, `dataset_import`,
`model_validation`.

- `job_type`: `evaluation`, `dataset_import`, or `model_validation`.
- `status`: `queued`, `running`, `succeeded`, or `failed`.
- `request_json` contains normalized URLs/IDs/options, never editorial content,
  credentials, or unrestricted server paths.
- `result_json` contains safe IDs, counters, and warnings.
- Progress is approximate and macro-phase-only.
- A job left running at startup is rewritten failed with
  `PROCESS_INTERRUPTED`; queued jobs remain queued.

### 5.7 `local_content.csv`

```text
article_id,canonical_url,title,text,content_saved_at
```

One current row per article. This is the only ledger that may contain editorial
content. It contains title and validated extracted body only after explicit
`save_local`; authors and raw HTML have no schema field. Ordinary resources and
exports reveal only a `content_saved` boolean.

Confirmed deletion rewrites this ledger without the target row using the small
mutable-file rule. It does not modify prediction runs/evaluations or claim to
delete user backups and external copies.

## 6. Import projection and conflicts

User input requires `url` plus at least one represented family's
`predicted_label` and `fold_id`. Optional source `article_id`, `domain`, `title`,
`text`, and `authors` are compatibility inputs: source ID is diagnostic only,
domain is recomputed, and editorial fields are discarded before staging.
Protected columns are ignored by value and reported by name only.

Within one import, identical outputs for an article/model are deduplicated.
Different outputs for that same pair mark the pair conflicted and exclude every
occurrence before publish. Other valid pairs remain accepted. One warning stores
safe row numbers and `IMPORT_INVALID`; no rejection ledger is maintained.

The default user upload limit is 512 MiB and 300,000 source rows. Parsing is
incremental, but the demo may use disk staging and bounded in-memory conflict
maps; arbitrary multi-gigabyte operation is not supported.
CLI/import processing never opens a source path for writing and preserves its
bytes and modification time.

## 7. Verification, backup, and recovery

Startup/storage verify checks exact headers, UTF-8/CSV structure, ID derivation,
unique IDs, model/run/evaluation references, probabilities, JSON types, and the
import marker. It rebuilds disposable indexes only after these checks pass.

A backup is a stopped-server copy of the complete data directory. Restore means
placing that copy at the configured path and running `storage verify`. The
application creates a timestamped copy only before trimming a malformed final
append record. It does not rotate, compact, or rewrite backups.

Purge affects active `local_content.csv` only. Users must manually delete any
backup or external copy that should no longer contain saved title/body.
