"""Inspectable six-ledger CSV persistence."""

from __future__ import annotations

import csv
import fcntl
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from . import SCHEMA_VERSION, __version__
from .errors import AppError


HEADERS = {
    "meta": ["schema_version", "created_at", "application_version"],
    "models": [
        "model_id", "family", "fold_id", "display_name", "artifact_kind",
        "artifact_locator", "artifact_sha256", "official_manifest_entry_sha256",
        "loader_recipe", "loader_recipe_version", "base_model", "base_revision",
        "tokenizer_source", "tokenizer_revision", "class_order_json", "max_tokens",
        "padding_policy", "adapter_config_sha256", "runtime_scientific_json",
        "status", "artifact_available", "runnable", "status_detail",
        "registered_at", "last_validated_at",
    ],
    "prediction_runs": [
        "prediction_run_id", "article_id", "canonical_url", "publisher_id",
        "normalized_hostname", "model_id", "predicted_class", "prob_class_0",
        "prob_class_1", "prob_class_2", "prob_class_3", "prob_class_4", "origin",
        "action", "input_source", "content_retention", "source_import_id", "job_id",
        "inference_started_at", "inference_completed_at", "duration_ms", "device",
        "software_versions_json", "recorded_at",
    ],
    "imports": [
        "import_id", "source_kind", "source_name", "content_sha256",
        "transport_sha256", "schema_version", "status", "source_rows",
        "accepted_rows", "rejected_rows", "duplicate_rows",
        "protected_columns_json", "warnings_json", "started_at", "completed_at",
    ],
    "jobs": [
        "job_id", "job_type", "status", "phase", "progress", "request_json",
        "result_json", "error_code", "error_message", "created_at", "started_at",
        "finished_at", "updated_at",
    ],
    "local_content": [
        "article_id", "canonical_url", "title", "text", "content_saved_at",
    ],
}
IMMUTABLE = {"prediction_runs", "imports"}
MUTABLE = {"models", "jobs", "local_content"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def json_field(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Storage:
    """Own one data directory and keep its authoritative CSV rows in memory."""

    def __init__(self, data_dir: Path | str, *, lock: bool = True):
        self.data_dir = Path(data_dir).resolve()
        self.state_dir = self.data_dir / "state"
        self._mutex = threading.RLock()
        self._lock_stream = None
        self.rows: dict[str, list[dict[str, str]]] = {}

        self.data_dir.mkdir(parents=True, exist_ok=True)
        for name in ("staging", "uploads", "managed-models", "logs"):
            (self.data_dir / name).mkdir(exist_ok=True)
        if lock:
            self._acquire_lock()
        self._initialize_or_validate()
        self.reload()
        self._recover_jobs()

    def _acquire_lock(self) -> None:
        lock_path = self.data_dir / ".writer.lock"
        self._lock_stream = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._lock_stream.close()
            self._lock_stream = None
            raise AppError(
                "STORAGE_ERROR", "Another process is using this data directory."
            ) from exc

    def close(self) -> None:
        if self._lock_stream is not None:
            fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_UN)
            self._lock_stream.close()
            self._lock_stream = None

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _initialize_or_validate(self) -> None:
        """Create the six ledgers, or refuse to open a directory that is not them.

        Partial or unexpected state fails closed rather than being repaired: silently
        recreating a missing ledger would hide data loss behind an apparently healthy
        start, and the ledgers are the only record this workspace keeps.
        """

        if not self.state_dir.exists():
            self.state_dir.mkdir()
            for name, header in HEADERS.items():
                path = self.path(name)
                with path.open("x", encoding="utf-8", newline="") as stream:
                    csv.writer(stream, lineterminator="\n").writerow(header)
                    if name == "meta":
                        csv.writer(stream, lineterminator="\n").writerow(
                            [SCHEMA_VERSION, utc_now(), __version__]
                        )
                    stream.flush()
                    os.fsync(stream.fileno())
            self._fsync_directory(self.state_dir)
            return
        if not self.state_dir.is_dir():
            raise AppError("STORAGE_ERROR", "State path is not a directory.")

        self._migrate_schema_1_store()

        actual = {path.name for path in self.state_dir.glob("*.csv")}
        expected = {f"{name}.csv" for name in HEADERS}
        if actual != expected:
            raise AppError(
                "STORAGE_ERROR",
                "State directory does not contain the six exact ledgers.",
                {"missing": sorted(expected - actual), "extra": sorted(actual - expected)},
            )
        for name, expected_header in HEADERS.items():
            try:
                with self.path(name).open(encoding="utf-8", newline="") as stream:
                    actual_header = next(csv.reader(stream))
            except (OSError, UnicodeError, StopIteration, csv.Error) as exc:
                raise AppError("STORAGE_ERROR", f"Cannot read {name}.csv.") from exc
            if actual_header != expected_header:
                raise AppError("STORAGE_ERROR", f"Invalid header in {name}.csv.")

    def _migrate_schema_1_store(self) -> None:
        """Bring a schema-1 store forward by dropping the retired evaluations ledger.

        Schema 1 kept publisher aggregations the user had explicitly created. They are
        now derived on demand from the article predictions instead, so the ledger has
        no writer and is removed rather than left to rot as a file nothing updates.
        Every aggregation it held can be recomputed from the runs that produced it.

        The migration runs only on a store that is exactly schema 1 plus that one extra
        file; anything else still fails closed, so an unrelated stray CSV is never
        deleted on the assumption that it is ours.
        """

        retired = self.state_dir / "evaluations.csv"
        meta_path = self.state_dir / "meta.csv"
        if not retired.is_file() or not meta_path.is_file():
            return
        present = {path.name for path in self.state_dir.glob("*.csv")}
        if present != {f"{name}.csv" for name in HEADERS} | {"evaluations.csv"}:
            return
        try:
            with meta_path.open(encoding="utf-8", newline="") as stream:
                meta_rows = list(csv.DictReader(stream))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise AppError("STORAGE_ERROR", "Cannot read meta.csv.") from exc
        if len(meta_rows) != 1 or meta_rows[0].get("schema_version") != "1":
            return

        retired.unlink()
        self.replace_meta_schema_version()

    def replace_meta_schema_version(self) -> None:
        """Rewrite meta.csv with the current schema version, atomically."""

        meta_path = self.state_dir / "meta.csv"
        try:
            with meta_path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            temporary = meta_path.with_suffix(".csv.tmp")
            with temporary.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=HEADERS["meta"], lineterminator="\n"
                )
                writer.writeheader()
                for row in rows:
                    writer.writerow({**row, "schema_version": SCHEMA_VERSION})
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, meta_path)
            self._fsync_directory(self.state_dir)
        except OSError as exc:
            raise AppError("STORAGE_ERROR", "Could not migrate meta.csv.") from exc

    def path(self, name: str) -> Path:
        if name not in HEADERS:
            raise ValueError(f"unknown ledger: {name}")
        return self.state_dir / f"{name}.csv"

    def reload(self) -> None:
        """Read every ledger into memory, rejecting any file that is not intact.

        The whole dataset is small enough to hold in memory, which keeps reads simple
        and lets a malformed row stop startup instead of surfacing much later as a
        confusing query result.
        """

        loaded: dict[str, list[dict[str, str]]] = {}
        for name in HEADERS:
            try:
                with self.path(name).open(encoding="utf-8", newline="") as stream:
                    reader = csv.DictReader(stream)
                    rows = list(reader)
                    if reader.fieldnames != HEADERS[name] or any(None in row for row in rows):
                        raise ValueError("malformed CSV record")
                    loaded[name] = rows
            except (OSError, UnicodeError, csv.Error, ValueError) as exc:
                raise AppError("STORAGE_ERROR", f"Invalid {name}.csv.") from exc
        if len(loaded["meta"]) != 1 or loaded["meta"][0]["schema_version"] != SCHEMA_VERSION:
            raise AppError("STORAGE_ERROR", "Unsupported or malformed storage metadata.")
        self._validate_unique_ids(loaded)
        self.rows = loaded

    @staticmethod
    def _validate_unique_ids(rows: dict[str, list[dict[str, str]]]) -> None:
        """Enforce the referential rules a database would normally provide.

        Identifiers must be unique, and a run or evaluation must point at records that
        exist: a prediction whose model is gone could no longer be reproduced, which is
        the one property this tool exists to guarantee.
        """

        keys = {
            "models": "model_id",
            "prediction_runs": "prediction_run_id",
            "imports": "import_id",
            "jobs": "job_id",
            "local_content": "article_id",
        }
        for ledger, key in keys.items():
            values = [row[key] for row in rows[ledger]]
            if len(values) != len(set(values)):
                raise AppError("STORAGE_ERROR", f"Duplicate identifier in {ledger}.csv.")

        model_ids = {row["model_id"] for row in rows["models"]}
        for run in rows["prediction_runs"]:
            if run["model_id"] not in model_ids:
                raise AppError("STORAGE_ERROR", "Prediction run references a missing model.")

    def verify(self) -> dict[str, int]:
        self.reload()
        return {name: len(rows) for name, rows in self.rows.items()}

    def append(self, name: str, row: dict[str, object]) -> None:
        """Add one row to an append-only ledger and flush it to disk.

        Scientific records are never edited in place, so history stays auditable. The
        explicit fsync means a completed prediction survives a crash immediately after
        it was reported, rather than sitting in a buffer.
        """

        if name not in IMMUTABLE:
            raise ValueError("append is reserved for immutable ledgers")
        normalized = self._normalized_row(name, row)
        with self._mutex:
            try:
                with self.path(name).open("a", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(
                        stream, fieldnames=HEADERS[name], lineterminator="\n"
                    )
                    writer.writerow(normalized)
                    stream.flush()
                    os.fsync(stream.fileno())
                self.rows[name].append(normalized)
            except OSError as exc:
                raise AppError("STORAGE_ERROR", f"Could not append {name}.csv.") from exc

    def replace(self, name: str, rows: Iterable[dict[str, object]]) -> None:
        """Rewrite a whole ledger atomically.

        The new content is written to a temporary file, flushed, and only then renamed
        over the original, so a crash leaves either the complete old file or the
        complete new one: a reader can never observe a half-written ledger.
        """

        if name not in MUTABLE and name not in IMMUTABLE:
            raise ValueError("unknown ledger")
        normalized = [self._normalized_row(name, row) for row in rows]
        path = self.path(name)
        temporary = path.with_suffix(".csv.tmp")
        with self._mutex:
            try:
                with temporary.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(
                        stream, fieldnames=HEADERS[name], lineterminator="\n"
                    )
                    writer.writeheader()
                    writer.writerows(normalized)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                self._fsync_directory(self.state_dir)
                self.rows[name] = normalized
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise AppError("STORAGE_ERROR", f"Could not replace {name}.csv.") from exc

    def upsert(self, name: str, key: str, row: dict[str, object]) -> None:
        """Insert or update one row of a mutable ledger.

        Only derived state (models, jobs, saved content) is mutable; the immutable
        ledgers reject this path so a prediction can never be rewritten after the fact.
        """

        if name not in MUTABLE:
            raise ValueError("upsert is reserved for mutable ledgers")
        value = str(row[key])
        rows: list[dict[str, object]] = [
            current for current in self.rows[name] if current[key] != value
        ]
        rows.append(row)
        self.replace(name, rows)

    def delete(self, name: str, key: str, value: str) -> bool:
        rows = [row for row in self.rows[name] if row[key] != value]
        if len(rows) == len(self.rows[name]):
            return False
        self.replace(name, rows)
        return True

    def _recover_jobs(self) -> None:
        changed = False
        now = utc_now()
        recovered = []
        for row in self.rows["jobs"]:
            current = dict(row)
            if current["status"] == "running":
                current.update(
                    status="failed",
                    phase="",
                    error_code="PROCESS_INTERRUPTED",
                    error_message="The operation was interrupted by process shutdown.",
                    finished_at=now,
                    updated_at=now,
                )
                changed = True
            recovered.append(current)
        if changed:
            self.replace("jobs", recovered)

    @staticmethod
    def _normalized_row(name: str, row: dict[str, object]) -> dict[str, str]:
        unknown = set(row) - set(HEADERS[name])
        missing = set(HEADERS[name]) - set(row)
        if unknown or missing:
            raise AppError(
                "STORAGE_ERROR",
                f"Invalid fields for {name}.csv.",
                {"missing": sorted(missing), "unknown": sorted(unknown)},
            )
        return {
            key: (
                "true"
                if value is True
                else "false"
                if value is False
                else str(value)
                if value is not None
                else ""
            )
            for key, value in row.items()
        }

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

