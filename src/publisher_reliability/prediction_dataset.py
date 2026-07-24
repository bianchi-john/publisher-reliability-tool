"""Synchronize user inference runs with the readable prediction dataset CSV."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Iterable

from .errors import AppError
from .identity import article_id, normalize_url, normalized_hostname, publisher_id
from .storage import HEADERS, Storage, json_field, utc_now


BASE_PUBLIC_COLUMNS = [
    "article_id",
    "url",
    "title",
    "text",
    "authors",
    "domain",
    "bert_predicted_label",
    "bert_fold_id",
    "roberta_predicted_label",
    "roberta_fold_id",
    *[f"bert_prob_class_{index}" for index in range(5)],
    *[f"roberta_prob_class_{index}" for index in range(5)],
]

USER_PREDICTION_COLUMNS = [
    "prediction_origin",
    "prediction_run_id",
    "model_id",
    "prediction_family",
    "prediction_fold_id",
    "predicted_label",
    *[f"prob_class_{index}" for index in range(5)],
    "prediction_action",
    "input_source",
    "content_retention",
    "job_id",
    "inference_started_at",
    "inference_completed_at",
    "duration_ms",
    "device",
    "software_versions_json",
    "recorded_at",
]

PUBLIC_COLUMNS = [*BASE_PUBLIC_COLUMNS, *USER_PREDICTION_COLUMNS]
DATASET_ORIGIN = "dataset_original"
USER_ORIGIN = "user_evaluation"


def _serialized_original(row: dict[str, str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=BASE_PUBLIC_COLUMNS,
        lineterminator="\n",
    )
    writer.writerow({column: row.get(column, "") for column in BASE_PUBLIC_COLUMNS})
    return buffer.getvalue().encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _user_values(row: dict[str, str]) -> tuple[int, tuple[float, ...]]:
    try:
        predicted = int(row["predicted_label"])
        fold = int(row["prediction_fold_id"])
        probabilities = tuple(float(row[f"prob_class_{index}"]) for index in range(5))
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(
            "IMPORT_INVALID",
            "User prediction row has invalid class, fold, or probabilities.",
        ) from exc
    if predicted not in range(5) or fold not in range(1, 6):
        raise AppError("IMPORT_INVALID", "User prediction class or fold is out of range.")
    if (
        any(
            not math.isfinite(value) or value < 0 or value > 1
            for value in probabilities
        )
        or abs(sum(probabilities) - 1) > 1e-5
    ):
        raise AppError("IMPORT_INVALID", "User prediction probabilities are invalid.")
    if (
        not row.get("prediction_run_id")
        or not row.get("model_id")
        or not row.get("prediction_family")
    ):
        raise AppError("IMPORT_INVALID", "User prediction identity is incomplete.")
    return fold, probabilities


def _read_dataset(
    release_dir: Path,
) -> tuple[dict[str, object], Path, list[dict[str, str]]]:
    manifest_path = release_dir / "manifest.json"
    dataset_path = release_dir / "predictions.csv"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with dataset_path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            fieldnames = reader.fieldnames
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
        raise AppError("STORAGE_ERROR", "Prediction dataset cannot be synchronized.") from exc
    if fieldnames != BASE_PUBLIC_COLUMNS and fieldnames != PUBLIC_COLUMNS:
        raise AppError("STORAGE_ERROR", "Prediction dataset has an unsupported header.")
    if any(None in row for row in rows):
        raise AppError("STORAGE_ERROR", "Prediction dataset contains a malformed row.")
    upgraded = []
    user_run_ids: set[str] = set()
    for row in rows:
        normalized = {column: row.get(column, "") or "" for column in PUBLIC_COLUMNS}
        if not normalized["prediction_origin"]:
            normalized["prediction_origin"] = DATASET_ORIGIN
        if normalized["prediction_origin"] not in {DATASET_ORIGIN, USER_ORIGIN}:
            raise AppError("STORAGE_ERROR", "Prediction dataset has an invalid origin.")
        if normalized["prediction_origin"] == USER_ORIGIN:
            run_id = normalized["prediction_run_id"]
            if run_id in user_run_ids:
                raise AppError(
                    "STORAGE_ERROR",
                    "Prediction dataset contains a duplicate user run identity.",
                )
            user_run_ids.add(run_id)
        upgraded.append(normalized)
    return manifest, dataset_path, upgraded


def _dataset_row(run: dict[str, str], model: dict[str, str]) -> dict[str, str]:
    row = {column: "" for column in PUBLIC_COLUMNS}
    row.update(
        {
            "article_id": run["article_id"],
            "url": run["canonical_url"],
            "domain": run["normalized_hostname"],
            "prediction_origin": USER_ORIGIN,
            "prediction_run_id": run["prediction_run_id"],
            "model_id": run["model_id"],
            "prediction_family": model["family"],
            "prediction_fold_id": model["fold_id"],
            "predicted_label": run["predicted_class"],
            **{
                f"prob_class_{index}": run[f"prob_class_{index}"]
                for index in range(5)
            },
            "prediction_action": run["action"],
            "input_source": run["input_source"],
            "content_retention": run["content_retention"],
            "job_id": run["job_id"],
            "inference_started_at": run["inference_started_at"],
            "inference_completed_at": run["inference_completed_at"],
            "duration_ms": run["duration_ms"],
            "device": run["device"],
            "software_versions_json": run["software_versions_json"],
            "recorded_at": run["recorded_at"],
        }
    )
    return {key: str(value) for key, value in row.items()}


def sync_user_predictions(
    release_dir: Path | None,
    runs: Iterable[dict[str, str]],
    models_by_id: dict[str, dict[str, str]],
) -> int:
    """Add missing local inference runs to predictions.csv without duplication."""

    if release_dir is None or not release_dir.exists():
        return 0
    manifest, dataset_path, rows = _read_dataset(release_dir)
    by_run_id = {
        row["prediction_run_id"]: row
        for row in rows
        if row["prediction_origin"] == USER_ORIGIN
    }
    added = 0
    for run in sorted(
        (row for row in runs if row["origin"] == "local_inference"),
        key=lambda row: (row["recorded_at"], row["prediction_run_id"]),
    ):
        model = models_by_id.get(run["model_id"])
        if model is None:
            raise AppError(
                "STORAGE_ERROR",
                "Local prediction cannot be mirrored because its model is missing.",
            )
        candidate = _dataset_row(run, model)
        existing = by_run_id.get(run["prediction_run_id"])
        if existing is not None:
            if existing != candidate:
                raise AppError(
                    "STORAGE_ERROR",
                    "Prediction dataset contains a conflicting user run identity.",
                )
            continue
        _user_values(candidate)
        rows.append(candidate)
        by_run_id[candidate["prediction_run_id"]] = candidate
        added += 1
    if not added and manifest.get("schema_version") == 2:
        return 0

    original_rows = [
        row for row in rows if row["prediction_origin"] == DATASET_ORIGIN
    ]
    user_rows = [row for row in rows if row["prediction_origin"] == USER_ORIGIN]
    original_digest = hashlib.sha256()
    for row in original_rows:
        original_digest.update(_serialized_original(row))
    for row in user_rows:
        _user_values(row)

    release_dir.mkdir(parents=True, exist_ok=True)
    csv_fd, csv_name = tempfile.mkstemp(
        prefix="predictions-", suffix=".csv.tmp", dir=release_dir
    )
    manifest_fd, manifest_name = tempfile.mkstemp(
        prefix="manifest-", suffix=".json.tmp", dir=release_dir
    )
    os.close(csv_fd)
    os.close(manifest_fd)
    csv_temporary = Path(csv_name)
    manifest_temporary = Path(manifest_name)
    try:
        with csv_temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=PUBLIC_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())

        urls = {row["url"] for row in rows}
        updated_manifest = {
            **manifest,
            "schema_version": 2,
            "records": len(rows),
            "unique_urls": len(urls),
            "duplicate_url_rows": len(rows) - len(urls),
            "columns": PUBLIC_COLUMNS,
            "dataset_original_records": len(original_rows),
            "user_evaluation_records": len(user_rows),
            "content_digest_sha256": original_digest.hexdigest(),
            "parts": [
                {
                    "file": "predictions.csv",
                    "rows": len(rows),
                    "bytes": csv_temporary.stat().st_size,
                    "sha256": _sha256_file(csv_temporary),
                }
            ],
        }
        with manifest_temporary.open("w", encoding="utf-8", newline="") as stream:
            json.dump(updated_manifest, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        os.replace(csv_temporary, dataset_path)
        os.replace(manifest_temporary, release_dir / "manifest.json")
        directory_fd = os.open(release_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise AppError(
            "STORAGE_ERROR",
            "Could not write user predictions to dataset/predictions/predictions.csv.",
        ) from exc
    finally:
        csv_temporary.unlink(missing_ok=True)
        manifest_temporary.unlink(missing_ok=True)
    return added


def restore_user_predictions(storage: Storage, release_dir: Path | None) -> int:
    """Restore mirrored user runs that are absent from the authoritative ledger."""

    if release_dir is None or not release_dir.exists():
        return 0
    _manifest, _dataset_path, rows = _read_dataset(release_dir)
    existing_run_ids = {
        row["prediction_run_id"] for row in storage.rows["prediction_runs"]
    }
    models_by_id = {row["model_id"]: row for row in storage.rows["models"]}
    restored = 0
    for row in rows:
        if row["prediction_origin"] != USER_ORIGIN:
            continue
        fold, _probabilities = _user_values(row)
        canonical = normalize_url(row["url"])
        identifier = article_id(canonical)
        if row["article_id"] != identifier:
            raise AppError(
                "STORAGE_ERROR",
                "Mirrored user prediction has an invalid article identity.",
            )
        model_identifier = row["model_id"]
        model = models_by_id.get(model_identifier)
        if model is None:
            timestamp = row["recorded_at"] or utc_now()
            model = {column: "" for column in HEADERS["models"]}
            model.update(
                {
                    "model_id": model_identifier,
                    "family": row["prediction_family"],
                    "fold_id": fold,
                    "display_name": (
                        f"{row['prediction_family'].upper()} fold {fold} "
                        "(restored user prediction)"
                    ),
                    "artifact_kind": "historical_virtual",
                    "loader_recipe": "restored_user_prediction",
                    "loader_recipe_version": "1",
                    "class_order_json": json_field([0, 1, 2, 3, 4]),
                    "runtime_scientific_json": json_field({}),
                    "status": "historical_only",
                    "artifact_available": False,
                    "runnable": False,
                    "status_detail": "Restored from the prediction dataset mirror.",
                    "registered_at": timestamp,
                    "last_validated_at": timestamp,
                }
            )
            storage.upsert("models", "model_id", model)
            models_by_id[model_identifier] = {
                key: str(value) for key, value in model.items()
            }
        elif (
            model["family"] != row["prediction_family"]
            or int(model["fold_id"]) != fold
        ):
            raise AppError(
                "STORAGE_ERROR",
                "Mirrored user prediction conflicts with its model identity.",
            )
        if row["prediction_run_id"] in existing_run_ids:
            continue
        run = {
            "prediction_run_id": row["prediction_run_id"],
            "article_id": identifier,
            "canonical_url": canonical,
            "publisher_id": publisher_id(normalized_hostname(canonical)),
            "normalized_hostname": normalized_hostname(canonical),
            "model_id": model_identifier,
            "predicted_class": row["predicted_label"],
            **{
                f"prob_class_{index}": row[f"prob_class_{index}"]
                for index in range(5)
            },
            "origin": "local_inference",
            "action": row["prediction_action"] or "missing_run_inference",
            "input_source": row["input_source"] or canonical,
            "content_retention": row["content_retention"] or "discard",
            "source_import_id": "",
            "job_id": row["job_id"],
            "inference_started_at": row["inference_started_at"],
            "inference_completed_at": row["inference_completed_at"],
            "duration_ms": row["duration_ms"],
            "device": row["device"],
            "software_versions_json": row["software_versions_json"] or json_field({}),
            "recorded_at": row["recorded_at"] or row["inference_completed_at"],
        }
        storage.append("prediction_runs", run)
        existing_run_ids.add(row["prediction_run_id"])
        restored += 1
    return restored
