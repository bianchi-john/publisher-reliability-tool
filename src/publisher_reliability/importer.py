"""Prediction-only dataset verification and import."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, TextIO

from .errors import AppError
from .identity import (
    article_id,
    import_id,
    imported_run_id,
    normalize_url,
    normalized_hostname,
    publisher_id,
    sha256_json,
)
from .storage import Storage, json_field, utc_now


FAMILIES = ("bert", "roberta", "llama", "mistral")
PUBLIC_COLUMNS = [
    "article_id", "url", "title", "text", "authors", "domain",
    "bert_predicted_label", "bert_fold_id",
    "roberta_predicted_label", "roberta_fold_id",
    "llama_predicted_label", "llama_fold_id",
    "mistral_predicted_label", "mistral_fold_id",
    *[f"bert_prob_class_{index}" for index in range(5)],
    *[f"roberta_prob_class_{index}" for index in range(5)],
]
EDITORIAL_COLUMNS = {"title", "text", "authors"}
PROTECTED_COLUMNS = {
    "score", "country", "language", "topics", "paywall",
    "opinion_advocacy", "label",
}


@dataclass(slots=True)
class Candidate:
    source_row: int
    canonical_url: str
    article_id: str
    hostname: str
    publisher_id: str
    family: str
    fold_id: int
    predicted_class: int
    probabilities: tuple[float, ...] | None

    @property
    def output(self) -> tuple[object, ...]:
        return (self.predicted_class, self.probabilities)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_csv(path: Path) -> TextIO:
    if path.name.lower().endswith(".csv.gz"):
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    if path.suffix.lower() != ".csv":
        raise AppError("INVALID_INPUT", "Dataset must be CSV or CSV.GZ.")
    return path.open("r", encoding="utf-8-sig", newline="")


def _serialized_projection(row: dict[str, str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=PUBLIC_COLUMNS, lineterminator="\n")
    writer.writerow({column: row.get(column, "") for column in PUBLIC_COLUMNS})
    return buffer.getvalue().encode("utf-8")


def verify_manifest(release_dir: Path) -> dict[str, object]:
    try:
        manifest = json.loads(
            (release_dir / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AppError("IMPORT_INVALID", "Bundled dataset manifest is unreadable.") from exc
    if manifest.get("schema_version") != 1 or manifest.get("columns") != PUBLIC_COLUMNS:
        raise AppError("IMPORT_INVALID", "Bundled dataset schema is unsupported.")

    digest = hashlib.sha256()
    total = 0
    for part in manifest.get("parts", []):
        name = str(part.get("file", ""))
        if Path(name).name != name or not name.endswith(".csv"):
            raise AppError("IMPORT_INVALID", "Bundled dataset part name is unsafe.")
        path = release_dir / name
        if not path.is_file():
            raise AppError("IMPORT_INVALID", "Bundled dataset part is missing.")
        if path.stat().st_size != int(part["bytes"]) or sha256_file(path) != part["sha256"]:
            raise AppError("IMPORT_INVALID", "Bundled dataset part checksum failed.")
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != PUBLIC_COLUMNS:
                raise AppError("IMPORT_INVALID", "Bundled dataset columns are invalid.")
            count = 0
            for row in reader:
                if None in row or any(row[column] is None for column in PUBLIC_COLUMNS):
                    raise AppError("IMPORT_INVALID", "Bundled dataset row is malformed.")
                if any(row[column] for column in EDITORIAL_COLUMNS):
                    raise AppError("IMPORT_INVALID", "Bundled editorial fields must be empty.")
                digest.update(_serialized_projection(row))
                count += 1
                total += 1
            if count != int(part["rows"]):
                raise AppError("IMPORT_INVALID", "Bundled part row count is invalid.")
    if total != int(manifest.get("records", -1)):
        raise AppError("IMPORT_INVALID", "Bundled row count is invalid.")
    if digest.hexdigest() != manifest.get("content_digest_sha256"):
        raise AppError("IMPORT_INVALID", "Bundled content digest failed.")
    return manifest


def _historical_model_id(
    content_digest: str, release_id: str, family: str, fold_id: int
) -> str:
    return sha256_json(
        {
            "identity_kind": "historical_virtual",
            "release_id": release_id,
            "dataset_content_digest": content_digest,
            "family": family,
            "fold_id": fold_id,
            "loader_recipe_version": "1",
        }
    )


def _model_row(
    model_id: str, family: str, fold_id: int, timestamp: str
) -> dict[str, object]:
    return {
        "model_id": model_id,
        "family": family,
        "fold_id": fold_id,
        "display_name": f"{family.upper()} fold {fold_id} (historical)",
        "artifact_kind": "historical_virtual",
        "artifact_locator": "",
        "artifact_sha256": "",
        "official_manifest_entry_sha256": "",
        "loader_recipe": "historical_import",
        "loader_recipe_version": "1",
        "base_model": "",
        "base_revision": "",
        "tokenizer_source": "",
        "tokenizer_revision": "",
        "class_order_json": json_field([0, 1, 2, 3, 4]),
        "max_tokens": "",
        "padding_policy": "",
        "adapter_config_sha256": "",
        "runtime_scientific_json": json_field({}),
        "status": "historical_only",
        "artifact_available": False,
        "runnable": False,
        "status_detail": "Imported predictions can be browsed and aggregated; inference is unavailable.",
        "registered_at": timestamp,
        "last_validated_at": timestamp,
    }


def _parse_candidates(
    rows: Iterator[dict[str, str]],
    fieldnames: list[str],
    *,
    max_rows: int,
    legacy_bare_percent: bool = False,
) -> tuple[list[Candidate], int, set[str], bytes]:
    candidates: list[Candidate] = []
    source_rows = 0
    protected = (set(fieldnames) - set(PUBLIC_COLUMNS)) | (
        set(fieldnames) & PROTECTED_COLUMNS
    )
    content_digest = hashlib.sha256()
    represented = [
        family
        for family in FAMILIES
        if f"{family}_predicted_label" in fieldnames
        or f"{family}_fold_id" in fieldnames
    ]
    if "url" not in fieldnames or not represented:
        raise AppError(
            "IMPORT_INVALID",
            "Dataset requires url and at least one prediction label/fold pair.",
        )

    for source_rows, raw in enumerate(rows, start=1):
        if source_rows > max_rows:
            raise AppError("PAYLOAD_TOO_LARGE", "Dataset exceeds the row limit.")
        if None in raw:
            raise AppError("IMPORT_INVALID", f"Row {source_rows} has extra fields.")
        projected = {column: raw.get(column, "") or "" for column in PUBLIC_COLUMNS}
        for column in EDITORIAL_COLUMNS:
            projected[column] = ""
        content_digest.update(_serialized_projection(projected))

        raw_url = (raw.get("url") or "").strip()
        if legacy_bare_percent:
            raw_url = re.sub(r"%(?![0-9A-Fa-f]{2})", "%25", raw_url)
        canonical = normalize_url(raw_url)
        hostname = normalized_hostname(canonical)
        supplied_domain = (raw.get("domain") or "").strip().lower()
        if supplied_domain.startswith("www."):
            supplied_domain = supplied_domain[4:]
        if supplied_domain and supplied_domain != hostname:
            raise AppError(
                "IMPORT_INVALID", f"Row {source_rows} has a mismatching domain."
            )
        art_id = article_id(canonical)
        pub_id = publisher_id(hostname)

        row_has_model = False
        for family in represented:
            label_name = f"{family}_predicted_label"
            fold_name = f"{family}_fold_id"
            label_raw = (raw.get(label_name) or "").strip()
            fold_raw = (raw.get(fold_name) or "").strip()
            if not label_raw and not fold_raw:
                continue
            if not label_raw or not fold_raw:
                raise AppError(
                    "IMPORT_INVALID",
                    f"Row {source_rows} has an incomplete {family} label/fold pair.",
                )
            try:
                label, fold = int(label_raw), int(fold_raw)
            except ValueError as exc:
                raise AppError(
                    "IMPORT_INVALID", f"Row {source_rows} has a non-integer label or fold."
                ) from exc
            if label not in range(5) or fold not in range(1, 6):
                raise AppError(
                    "IMPORT_INVALID", f"Row {source_rows} has an out-of-range label or fold."
                )

            probability_names = [f"{family}_prob_class_{index}" for index in range(5)]
            probability_values = [(raw.get(name) or "").strip() for name in probability_names]
            probabilities: tuple[float, ...] | None = None
            if any(probability_values):
                if not all(probability_values):
                    raise AppError(
                        "IMPORT_INVALID",
                        f"Row {source_rows} has an incomplete {family} probability vector.",
                    )
                try:
                    probabilities = tuple(float(value) for value in probability_values)
                except ValueError as exc:
                    raise AppError(
                        "IMPORT_INVALID",
                        f"Row {source_rows} has invalid probabilities.",
                    ) from exc
                if (
                    any(value < 0 or value > 1 for value in probabilities)
                    or abs(sum(probabilities) - 1) > 1e-5
                ):
                    raise AppError(
                        "IMPORT_INVALID",
                        f"Row {source_rows} has an invalid probability vector.",
                    )
            candidates.append(
                Candidate(
                    source_rows, canonical, art_id, hostname, pub_id,
                    family, fold, label, probabilities,
                )
            )
            row_has_model = True
        if not row_has_model:
            raise AppError(
                "IMPORT_INVALID", f"Row {source_rows} has no complete model output."
            )
    if source_rows == 0:
        raise AppError("IMPORT_INVALID", "Dataset contains no data rows.")
    return candidates, source_rows, protected, content_digest.digest()


def import_csv(
    storage: Storage,
    source: Path,
    *,
    source_kind: str | None = None,
    source_name: str | None = None,
    release_id: str | None = None,
    known_content_digest: str | None = None,
    max_rows: int = 300_000,
    legacy_bare_percent: bool = False,
) -> dict[str, str]:
    started = utc_now()
    transport_digest = sha256_file(source)
    kind = source_kind or ("csv_gz" if source.name.lower().endswith(".csv.gz") else "csv")
    try:
        with open_csv(source) as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise AppError("IMPORT_INVALID", "Dataset has no header.")
            candidates, source_rows, protected, digest_bytes = _parse_candidates(
                iter(reader),
                reader.fieldnames,
                max_rows=max_rows,
                legacy_bare_percent=legacy_bare_percent,
            )
    except (OSError, UnicodeError, csv.Error, gzip.BadGzipFile) as exc:
        raise AppError("IMPORT_INVALID", "Dataset cannot be parsed safely.") from exc

    content_digest = known_content_digest or digest_bytes.hex()
    identifier = import_id(content_digest)
    existing = next(
        (row for row in storage.rows["imports"] if row["import_id"] == identifier),
        None,
    )
    if existing is not None:
        return existing

    logical_release = release_id or f"user_import:{content_digest}"
    timestamp = utc_now()
    models: dict[tuple[str, int], dict[str, object]] = {}
    model_ids: dict[tuple[str, int], str] = {}
    for candidate in candidates:
        key = (candidate.family, candidate.fold_id)
        if key not in models:
            model_identifier = _historical_model_id(
                content_digest, logical_release, *key
            )
            model_ids[key] = model_identifier
            models[key] = _model_row(model_identifier, *key, timestamp)

    grouped: dict[tuple[str, str], list[Candidate]] = {}
    for candidate in candidates:
        model_identifier = model_ids[(candidate.family, candidate.fold_id)]
        grouped.setdefault((candidate.article_id, model_identifier), []).append(candidate)

    conflicts: list[dict[str, object]] = []
    duplicate_rows = 0
    selected: list[tuple[Candidate, str]] = []
    accepted_source_rows: set[int] = set()
    for (art_id, model_identifier), group in grouped.items():
        outputs = {candidate.output for candidate in group}
        if len(outputs) > 1:
            conflicts.append(
                {
                    "code": "IMPORT_INVALID",
                    "rows": [candidate.source_row for candidate in group],
                    "reason": "conflicting article/model output",
                }
            )
            continue
        selected.append((group[0], model_identifier))
        accepted_source_rows.update(candidate.source_row for candidate in group)
        duplicate_rows += len(group) - 1

    run_rows: list[dict[str, object]] = []
    for candidate, model_identifier in selected:
        probabilities = candidate.probabilities or ("", "", "", "", "")
        run_rows.append(
            {
                "prediction_run_id": imported_run_id(
                    candidate.article_id, model_identifier, identifier
                ),
                "article_id": candidate.article_id,
                "canonical_url": candidate.canonical_url,
                "publisher_id": candidate.publisher_id,
                "normalized_hostname": candidate.hostname,
                "model_id": model_identifier,
                "predicted_class": candidate.predicted_class,
                **{
                    f"prob_class_{index}": probabilities[index]
                    for index in range(5)
                },
                "origin": "bundled_import" if kind == "bundled_manifest" else "user_import",
                "action": "import",
                "input_source": "unavailable",
                "content_retention": "discard",
                "source_import_id": identifier,
                "job_id": "",
                "inference_started_at": "",
                "inference_completed_at": "",
                "duration_ms": "",
                "device": "",
                "software_versions_json": json_field({}),
                "recorded_at": timestamp,
            }
        )

    rejected_rows = source_rows - len(accepted_source_rows)
    status = (
        "failed"
        if not run_rows
        else "succeeded_with_rejections"
        if conflicts
        else "succeeded"
    )
    import_row: dict[str, object] = {
        "import_id": identifier,
        "source_kind": kind,
        "source_name": source_name or source.name,
        "content_sha256": content_digest,
        "transport_sha256": transport_digest,
        "schema_version": "1",
        "status": status,
        "source_rows": source_rows,
        "accepted_rows": len(accepted_source_rows),
        "rejected_rows": rejected_rows,
        "duplicate_rows": duplicate_rows,
        "protected_columns_json": json_field(sorted(protected)),
        "warnings_json": json_field(conflicts),
        "started_at": started,
        "completed_at": timestamp,
    }

    existing_model_ids = {row["model_id"] for row in storage.rows["models"]}
    existing_run_ids = {
        row["prediction_run_id"] for row in storage.rows["prediction_runs"]
    }
    merged_models = list(storage.rows["models"]) + [
        row for row in models.values() if str(row["model_id"]) not in existing_model_ids
    ]
    merged_runs = list(storage.rows["prediction_runs"]) + [
        row for row in run_rows if str(row["prediction_run_id"]) not in existing_run_ids
    ]
    storage.replace("models", merged_models)
    storage.replace("prediction_runs", merged_runs)
    storage.replace("imports", [*storage.rows["imports"], import_row])
    return {key: str(value) for key, value in import_row.items()}


def import_bundled_release(storage: Storage, release_dir: Path) -> dict[str, str] | None:
    if not release_dir.exists():
        return None
    manifest = verify_manifest(release_dir)
    digest = str(manifest["content_digest_sha256"])
    identifier = import_id(digest)
    existing = next(
        (row for row in storage.rows["imports"] if row["import_id"] == identifier),
        None,
    )
    if existing is not None:
        return existing

    parts = list(manifest["parts"])
    if len(parts) == 1:
        source = release_dir / str(parts[0]["file"])
        return import_csv(
            storage,
            source,
            source_kind="bundled_manifest",
            source_name="bundled-predictions-v1",
            release_id="osf:r9atz",
            known_content_digest=digest,
            legacy_bare_percent=True,
        )

    temporary = storage.data_dir / "staging" / "bundled-joined.csv"
    try:
        with temporary.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=PUBLIC_COLUMNS, lineterminator="\n")
            writer.writeheader()
            for part in parts:
                with (release_dir / str(part["file"])).open(
                    encoding="utf-8", newline=""
                ) as stream:
                    writer.writerows(csv.DictReader(stream))
        return import_csv(
            storage,
            temporary,
            source_kind="bundled_manifest",
            source_name="bundled-predictions-v1",
            release_id="osf:r9atz",
            known_content_digest=digest,
            legacy_bare_percent=True,
        )
    finally:
        temporary.unlink(missing_ok=True)
