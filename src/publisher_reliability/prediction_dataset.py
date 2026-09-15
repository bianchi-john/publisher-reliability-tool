"""Mirror local user inference runs to a private, git-ignored CSV.

The released ``predictions.csv`` in this directory is the shared research corpus:
it ships with the repository and is never modified after preparation. A user's own
evaluations are a different thing entirely — personal browsing/reading history that
must never enter version control — so they are mirrored to a sibling file
(``user-predictions.csv``) instead of being appended to the tracked one. That file is
listed in ``.gitignore`` and exists only on the machine that created it.

The mirror exists so a user's local evaluation history survives even if
``data/`` (the authoritative but git-ignored application state) is deleted: on
startup, any row present here but missing from the ledger is restored.
"""

from __future__ import annotations

import csv
import io
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
    "prediction_model_name",
    "prediction_model_provenance",
    "prediction_official_manifest_entry_sha256",
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
    """Serialize only the original-dataset columns of one row, deterministically.

    Used to compute the content digest of an imported dataset over the columns that
    are actually released, independent of any per-row prediction/provenance columns
    that only apply to a user's own evaluations.
    """

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=BASE_PUBLIC_COLUMNS,
        lineterminator="\n",
    )
    writer.writerow({column: row.get(column, "") for column in BASE_PUBLIC_COLUMNS})
    return buffer.getvalue().encode("utf-8")


def _user_values(row: dict[str, str]) -> tuple[int, tuple[float, ...]]:
    """Validate one mirrored user prediction read back from the dataset file.

    The mirror is an ordinary CSV that a user may edit, so its rows are re-checked
    before they can re-enter the ledger: class, fold and probability vector must all be
    valid and the model identity complete.
    """

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
        or not row.get("prediction_model_name")
        or row.get("prediction_model_provenance")
        not in {"paper_official", "user_custom", "local_checkpoint"}
    ):
        raise AppError("IMPORT_INVALID", "User prediction identity is incomplete.")
    official_digest = row.get("prediction_official_manifest_entry_sha256", "")
    if (
        row["prediction_model_provenance"] == "paper_official"
        and (
            not isinstance(official_digest, str)
            or len(official_digest) != 64
            or any(character not in "0123456789abcdef" for character in official_digest)
        )
    ):
        raise AppError("IMPORT_INVALID", "Official model provenance digest is invalid.")
    if row["prediction_model_provenance"] != "paper_official" and official_digest:
        raise AppError("IMPORT_INVALID", "Only paper models can carry an official digest.")
    return fold, probabilities


def _dataset_row(run: dict[str, str], model: dict[str, str]) -> dict[str, str]:
    """Render one local inference run as a row of the combined prediction dataset.

    User rows carry their own prediction columns and leave the original per-family
    columns empty, which keeps them distinguishable from the released rows beside them.
    """

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
            "prediction_model_name": model["display_name"],
            "prediction_model_provenance": (
                "paper_official"
                if model["official_manifest_entry_sha256"]
                else "user_custom"
                if model["artifact_kind"].startswith("custom_")
                else "local_checkpoint"
            ),
            "prediction_official_manifest_entry_sha256": model[
                "official_manifest_entry_sha256"
            ],
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


USER_PREDICTIONS_FILENAME = "user-predictions.csv"


def _user_predictions_path(release_dir: Path) -> Path:
    return release_dir / USER_PREDICTIONS_FILENAME


def _read_user_predictions(release_dir: Path) -> list[dict[str, str]]:
    """Read the private mirror file, or return no rows when it does not exist yet.

    A fresh clone, or a machine that has never evaluated an article locally, has no
    such file: that is the normal starting state, not an error.
    """

    path = _user_predictions_path(release_dir)
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            fieldnames = reader.fieldnames
    except (OSError, UnicodeError, csv.Error) as exc:
        raise AppError(
            "STORAGE_ERROR", "User prediction mirror cannot be read."
        ) from exc
    if fieldnames is not None and fieldnames != PUBLIC_COLUMNS:
        raise AppError(
            "STORAGE_ERROR", "User prediction mirror has an unsupported header."
        )
    seen_run_ids: set[str] = set()
    for row in rows:
        if None in row:
            raise AppError(
                "STORAGE_ERROR", "User prediction mirror contains a malformed row."
            )
        run_id = row.get("prediction_run_id", "")
        if run_id in seen_run_ids:
            raise AppError(
                "STORAGE_ERROR",
                "User prediction mirror contains a duplicate run identity.",
            )
        seen_run_ids.add(run_id)
    return rows


def _write_user_predictions(release_dir: Path, rows: list[dict[str, str]]) -> None:
    """Rewrite the mirror file atomically, the same way the CSV ledgers are written.

    The file is private to this machine, but a crash mid-write must still never leave
    a half-written CSV behind.
    """

    release_dir.mkdir(parents=True, exist_ok=True)
    path = _user_predictions_path(release_dir)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="user-predictions-", suffix=".csv.tmp", dir=release_dir
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=PUBLIC_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(release_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise AppError(
            "STORAGE_ERROR",
            f"Could not write user predictions to {USER_PREDICTIONS_FILENAME}.",
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def sync_user_predictions(
    release_dir: Path | None,
    runs: Iterable[dict[str, str]],
    models_by_id: dict[str, dict[str, str]],
) -> int:
    """Mirror local inference runs into the private, git-ignored prediction file.

    Only ``local_inference`` runs are mirrored; the released dataset rows are never
    touched. Re-running this with the same runs adds nothing, which is what makes a
    repeated startup or a resubmitted evaluation converge instead of duplicating rows.
    """

    if release_dir is None:
        return 0
    rows = _read_user_predictions(release_dir)
    by_run_id = {row["prediction_run_id"]: row for row in rows}
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
                    "Prediction mirror contains a conflicting user run identity.",
                )
            continue
        _user_values(candidate)
        rows.append(candidate)
        by_run_id[candidate["prediction_run_id"]] = candidate
        added += 1
    if added:
        _write_user_predictions(release_dir, rows)
    return added


def restore_user_predictions(storage: Storage, release_dir: Path | None) -> int:
    """Restore mirrored user runs that are absent from the authoritative ledger.

    ``data/`` is git-ignored and disposable by design; this is what lets a user delete
    it (or lose it) without losing the record of articles they personally evaluated,
    as long as the mirror file survives alongside the repository checkout.
    """

    if release_dir is None or not release_dir.exists():
        return 0
    rows = _read_user_predictions(release_dir)
    existing_run_ids = {
        row["prediction_run_id"] for row in storage.rows["prediction_runs"]
    }
    models_by_id = {row["model_id"]: row for row in storage.rows["models"]}
    restored = 0
    for row in rows:
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
                        row["prediction_model_name"]
                    ),
                    "artifact_kind": "historical_virtual",
                    "official_manifest_entry_sha256": row[
                        "prediction_official_manifest_entry_sha256"
                    ],
                    "loader_recipe": "restored_user_prediction",
                    "loader_recipe_version": "1",
                    "class_order_json": json_field([0, 1, 2, 3, 4]),
                    "runtime_scientific_json": json_field(
                        {
                            "source_model_provenance": row[
                                "prediction_model_provenance"
                            ]
                        }
                    ),
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
