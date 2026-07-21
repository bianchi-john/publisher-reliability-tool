# CSV Storage Contract

**Status:** Normative MVP persistence contract  
**Storage schema version:** `1`

## 1. Purpose

All authoritative mutable application state is stored as human-inspectable CSV.
No SQL database, embedded key-value store, browser database, or opaque binary
index is authoritative. In-memory indexes are disposable projections rebuilt
from committed CSV rows.

The store supports one writer process, concurrent HTTP readers in that process,
crash recovery, idempotent import, record versioning, and multi-file logical
transactions.

## 2. Directory layout

```text
<data-dir>/
├── .writer.lock
├── state/
│   ├── meta.csv
│   ├── transactions.csv
│   ├── publishers.csv
│   ├── articles.csv
│   ├── models.csv
│   ├── predictions.csv
│   ├── evaluations.csv
│   ├── evaluation_articles.csv
│   ├── jobs.csv
│   ├── imports.csv
│   └── import_rejections.csv
├── backups/
├── logs/
├── managed-models/
└── uploads/
```

Only files under `state/` are the database. Lock, backup, log, managed-model,
and upload files are operational support files and are not queryable records.

## 3. Physical CSV rules

- Encoding: UTF-8 without BOM.
- Line ending written by the application: LF.
- Dialect: RFC 4180-compatible comma delimiter and double-quote escaping.
- Header: required, exact, and written once as the first physical record.
- Embedded commas, quotes, CR, and LF: allowed only through standard CSV
  quoting.
- Null optional scalar: empty field.
- Empty required string: invalid.
- Boolean: lowercase `true` or `false`.
- Integer: base-10 with no grouping.
- Float: finite decimal or scientific notation accepted on read; canonical
  writes use Python round-trip representation. `NaN` and infinities are invalid.
- Timestamp: UTC RFC 3339 with microseconds and terminal `Z`, for example
  `2026-07-21T14:05:12.123456Z`.
- JSON-valued field: compact UTF-8 JSON with sorted object keys; CSV quoting is
  applied outside JSON. Arrays use `[]`, not an empty field.
- URL: normalized absolute HTTP(S) URL.
- Probabilities: either all five fields are empty or all five are finite in
  `[0,1]` and sum to `1` within `1e-5`.
- Record order: append order. Logical ordering is determined by query rules,
  never by assuming physical adjacency.
- Maximum UTF-8 field sizes: URL 8,192 bytes, title 1 MiB, text 16 MiB,
  `authors_json` 1 MiB, and every other scalar or JSON field 1 MiB. An
  oversized imported row is rejected with `CONTENT_TOO_LARGE`; an oversized
  committed database field is corruption.

CSV parsing uses Python's `csv` module with `newline=""`; line-oriented shell
tools are not used to parse article bodies containing embedded newlines.
`csv.field_size_limit(16777216)` is set before parsing, followed by the exact
UTF-8 byte checks above.

## 4. Identifier rules

- Transaction, job, evaluation, and import IDs: lowercase canonical UUIDv4.
- Application UUID namespace:
  `6f63a5f4-97aa-4bb8-a73f-2a30fc9fcf31`.
- Publisher ID: UUIDv5 of `publisher:<normalized_hostname>` in that namespace.
- Article ID: UUIDv5 of `article:<canonical_url>` in that namespace.
- Model ID: lowercase 64-character SHA-256 of the canonical model-identity JSON
  defined by the scientific contract.
- Prediction ID: lowercase SHA-256 of
  `prediction:<article_id>:<model_id>`.
- Evaluation-article row ID: lowercase SHA-256 of
  `evaluation-article:<evaluation_id>:<position>`.
- Record version: positive integer starting at `1` and increasing by exactly
  one for each new version of the same record ID. A compacted baseline may
  begin above `1` under section 10 and later versions increment from it.

## 5. Common version fields

Every entity ledger except `meta.csv` and `transactions.csv` ends with:

```text
record_version,record_operation,transaction_id,recorded_at
```

- `record_operation` is `UPSERT` or `DELETE`.
- A `DELETE` row retains the record identity fields, leaves other entity fields
  empty where permitted, and makes the record absent from current state.
- `transaction_id` must resolve to a committed transaction.
- `recorded_at` is when that version was appended.

Current state contains the highest committed `record_version` for each record
ID unless that version is `DELETE`.

## 6. Ledger schemas

The following header order is exact. Changing a header requires a new storage
schema version and migration command.

### 6.1 `meta.csv`

```text
schema_version,created_at,application_version
```

It contains exactly one data row. `schema_version` is `1`. Startup rejects a
newer unknown schema and never rewrites it automatically.

### 6.2 `transactions.csv`

```text
transaction_id,event,commit_sequence,operation,actor,request_id,occurred_at
```

- `event`: `BEGIN`, `COMMITTED`, or `ABORTED`.
- `commit_sequence` is empty for `BEGIN` and `ABORTED`; each `COMMITTED` event
  receives the next positive integer. Values are unique and strictly increase;
  gaps are permitted only after documented compaction removes obsolete
  transactions.
- `operation`: stable operation name such as `seed_import`, `prediction_create`,
  `evaluation_create`, `model_register`, or `job_update`.
- `actor`: `startup`, `cli`, `api`, or `recovery`.
- `request_id`: optional API request UUID.

A transaction is visible only if its last valid event is `COMMITTED`. An
`ABORTED` transaction is never visible. More than one terminal event is
corruption.

### 6.3 `publishers.csv`

```text
publisher_id,normalized_hostname,homepage_url,display_name,first_seen_at,last_seen_at,record_version,record_operation,transaction_id,recorded_at
```

Constraints:

- `publisher_id` and `normalized_hostname` are unique in current state.
- `homepage_url` is `https://<normalized_hostname>/` unless a successfully
  resolved homepage URL is stored.
- `display_name` is optional scraped/local metadata and not identity.

### 6.4 `articles.csv`

```text
article_id,canonical_url,publisher_id,title,text,authors_json,detected_language,text_origin,network_used,first_seen_at,last_seen_at,record_version,record_operation,transaction_id,recorded_at
```

Constraints:

- `article_id` and `canonical_url` are unique in current state.
- `publisher_id` resolves to a current publisher.
- `authors_json` is a JSON array of strings.
- `detected_language` is empty for unvalidated imported text or `en` for text
  accepted for new inference. Other codes are not stored as accepted articles.
- `text_origin`: `bundled_import`, `user_import`, `web_extraction`, or
  `synthetic`.
- `network_used` describes acquisition of this stored version.
- Updating scraped metadata creates a new version; normal prediction reuse does
  not update or refetch an article.

### 6.5 `models.csv`

```text
model_id,family,fold_id,artifact_kind,artifact_path,artifact_sha256,loader_recipe,loader_recipe_version,base_model,base_revision,tokenizer_source,tokenizer_revision,max_tokens,class_count,status,status_detail,registered_at,last_validated_at,record_version,record_operation,transaction_id,recorded_at
```

Constraints:

- `family`: `bert`, `roberta`, `llama`, `mistral`, or `custom`.
- `fold_id`: integer `1..5` for official folds; optional only for custom models.
- `artifact_kind`: `state_dict`, `peft_directory`, `hf_directory`,
  `custom_manifest`, or `historical_virtual`.
- `class_count` is exactly `5` for a selectable model.
- `status` is one registry state defined in `architecture.md`.
- `historical_virtual` records use a logical release identity, have empty path
  and artifact checksum fields, and use status `historical_only`.
- API responses redact `artifact_path`; the complete path remains local CSV
  state because the loader needs it.

### 6.6 `predictions.csv`

```text
prediction_id,article_id,model_id,predicted_class,prob_class_0,prob_class_1,prob_class_2,prob_class_3,prob_class_4,origin,source_import_id,job_id,inference_started_at,inference_completed_at,duration_ms,device,software_versions_json,record_version,record_operation,transaction_id,recorded_at
```

Constraints:

- Current `(article_id,model_id)` is unique and maps to `prediction_id`.
- `predicted_class` is integer `0..4`.
- `origin`: `bundled_import`, `user_import`, or `local_inference`.
- Imported missing probability vectors use five empty fields.
- New local inference requires all five probabilities.
- `source_import_id` is required for imported predictions and empty otherwise.
- `job_id` is required for local inference and empty for startup seed import.
- `device` examples: `cpu`, `cuda:0`; empty for imported predictions.

An existing prediction is immutable scientific output. Re-running the same
article/model combination returns it. A different checkpoint or recipe creates
a different model ID and therefore a different prediction ID.

### 6.7 `evaluations.csv`

```text
evaluation_id,publisher_id,model_id,method,method_version,input_mode,discovery_mode,requested_count,used_count,partial,result_class,ordinal_mean,prob_class_0,prob_class_1,prob_class_2,prob_class_3,prob_class_4,job_id,created_at,warnings_json,record_version,record_operation,transaction_id,recorded_at
```

Constraints:

- `method`: `majority_vote`, `ordinal_mean`, or `mean_probabilities`.
- `input_mode`: `article_list`, `publisher`, or `stored_selection`.
- `discovery_mode`: empty unless input mode is `publisher`; otherwise
  `stored_only`, `stored_first`, or `web_only`.
- `requested_count` is `2..50`; `used_count` is `2..requested_count`.
- `partial=true` exactly when `used_count < requested_count`.
- `result_class` is `0..4`.
- `ordinal_mean` is populated only for `ordinal_mean`.
- Probability fields are populated only for `mean_probabilities`.
- `warnings_json` is a JSON array of stable warning objects without article
  bodies or protected values.

### 6.8 `evaluation_articles.csv`

```text
evaluation_article_id,evaluation_id,position,article_id,prediction_id,record_version,record_operation,transaction_id,recorded_at
```

Constraints:

- `position` starts at `1`, is contiguous, and preserves aggregation order.
- Each prediction resolves to the same article and model as its evaluation.
- A committed evaluation has exactly `used_count` current rows.

### 6.9 `jobs.csv`

```text
job_id,job_type,status,phase,progress,request_json,result_json,error_code,error_message,retry_of_job_id,cancel_requested,created_at,started_at,finished_at,record_version,record_operation,transaction_id,recorded_at
```

Constraints:

- `job_type`: `article_evaluation`, `article_list_evaluation`,
  `publisher_evaluation`, `dataset_import`, `model_scan`, `model_register`,
  `model_upload`, `storage_verify`, or `storage_compact`.
- `status`: `queued`, `running`, `succeeded`, `failed`, or `cancelled`.
- `progress`: integer `0..100`.
- `request_json` contains normalized request parameters, not API keys or article
  bodies.
- `result_json` contains safe IDs and counters, not duplicated article bodies.
- `error_message` is English and safe for display.

Job status changes append versions; existing physical rows are never edited.

### 6.10 `imports.csv`

```text
import_id,source_kind,source_name,source_sha256,schema_version,status,source_rows,accepted_rows,rejected_rows,duplicate_rows,protected_columns_json,warnings_json,started_at,completed_at,record_version,record_operation,transaction_id,recorded_at
```

Constraints:

- `source_kind`: `bundled_manifest`, `manifest_directory`, `csv`, `csv_gz`,
  `zip_csv`, or `zip_manifest`.
- `source_sha256` is SHA-256 of exact source-file bytes for `csv`, `csv_gz`, and
  `zip_csv`, and `zip_manifest`; for a manifest directory it is SHA-256 of exact
  `manifest.json` bytes after every listed part digest has been verified.
- `source_name` is a basename or logical release name, never an unrestricted
  user path in API output.
- `status` is `succeeded`, `succeeded_with_rejections`, or `failed`.
- `succeeded_with_rejections` requires at least one accepted and one rejected
  row; accepted records commit and every rejection is recorded separately.
- `failed` is used when the container/schema cannot be processed or no row is
  acceptable; it contributes no articles or predictions.
- Current `(source_sha256,schema_version)` with status `succeeded` or
  `succeeded_with_rejections` is unique.
- `protected_columns_json` lists column names only.

### 6.11 `import_rejections.csv`

```text
rejection_id,import_id,source_row,error_code,safe_identifier,message,record_version,record_operation,transaction_id,recorded_at
```

Constraints:

- one row is written for every rejected source data row; CSV header rows are
  not counted as source rows;
- `rejection_id` is UUIDv4 and `source_row` is the one-based physical CSV line
  on which the logical record begins;
- `safe_identifier` is the canonical article URL when URL normalization
  succeeded, otherwise empty;
- `error_code` is a stable import code and `message` is safe English text;
- rejected titles, bodies, authors, protected-provider values, and raw malformed
  input are never copied into this ledger;
- records are paginated by `(source_row,rejection_id)` in the API.

## 7. Transaction rules

One use case that changes several ledgers uses one transaction ID. Examples:

- New inference: publisher/article version if new, prediction, job success.
- Publisher evaluation: evaluation, all evaluation-article rows, job success.
- Seed/user import: import, publishers, articles, predictions, and any import
  rejections.

The implementation appends entity rows before the `COMMITTED` marker. Readers
load transaction states first and ignore entity rows from every uncommitted or
aborted transaction.

The process write mutex covers the complete sequence. HTTP requests can perform
read work concurrently, but their final commits serialize.

## 8. Startup verification and recovery

Startup performs:

1. exact filename and header verification;
2. UTF-8 and CSV structure validation;
3. transaction state validation;
4. monotonic record-version validation;
5. type, foreign-key, uniqueness, probability, and method constraints;
6. index reconstruction from committed latest versions;
7. referential count checks for evaluations.

If only the final physical record of a ledger is malformed and its transaction
is not committed, recovery:

1. copies the original ledger to `backups/<timestamp>-<filename>`;
2. truncates bytes after the last valid complete CSV record;
3. appends an `ABORTED` transaction event when a valid transaction ID exists;
4. records a warning and continues.

Any malformed committed row, invalid middle row, unknown header, duplicate
committed identity, or broken committed foreign key is `STORAGE_CORRUPT` and
prevents readiness. The application never guesses a repair.

## 9. Idempotency and duplicate handling

- Seed/user import identity is source SHA-256 plus import schema version.
- Reimporting a successful identical source returns the existing import.
- Article identity is canonical URL; model identity is exact model ID.
- An identical article/prediction pair is reused.
- Conflicting duplicate rows in arbitrary user imports are rejected and counted
  as `IMPORT_CONFLICT`; no first-row choice is made.
- The bundled release has 19,429 exact released URL rows. Its separately
  documented canonicalization exception imports 19,411 articles, 77,708 unique
  predictions, and 20 historical virtual family/fold models.

## 10. Compaction

`publisher-reliability storage compact` requires the writer lock and refuses to
run while the server owns it. It:

1. verifies the full store;
2. writes a new temporary `state/` containing committed current entity rows;
   each retains its record ID, record version, scientific/entity fields, and
   original `recorded_at`, but points to one new
   `storage_compact_baseline` transaction with commit sequence `1`;
3. verifies the temporary store independently;
4. renames the current state to a timestamped backup;
5. atomically renames the verified temporary directory to `state/`;
6. retains the backup until the user explicitly removes it.

Compaction never changes record IDs, versions, scientific values, or evaluation
membership. It is optional; normal operation does not compact automatically.
Startup permits a first visible record version above `1` only when its
transaction operation is `storage_compact_baseline`; any other missing version
history is corruption.

## 11. Export

Exports are derived views, not database files. They use UTF-8 CSV with the same
physical rules, stream to the client, and contain only documented public fields.
Article text is excluded from bulk exports by default and included only when the
request explicitly sets `include_text=true`. Protected reference fields are
impossible to request because they are absent from storage schemas.

## 12. Backup and portability

A consistent manual backup requires stopping the server and copying the entire
data directory. Copying individual ledgers while the server runs is not a
supported backup. Native and Docker deployments use identical bytes and can
move a stopped data directory between them, provided model paths are
re-registered when mount paths differ.
