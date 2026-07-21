#!/usr/bin/env python3
"""Build the public, prediction-only dataset release.

The input may be a CSV, a gzip-compressed CSV, or a ZIP archive containing
exactly one CSV file. Output is written only after the entire input passes
validation, so a truncated source cannot produce an apparently valid release.
Editorial title, text, and author values are always replaced with empty fields.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO
from urllib.parse import urlsplit


PUBLIC_COLUMNS = [
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
    "llama_predicted_label",
    "llama_fold_id",
    "mistral_predicted_label",
    "mistral_fold_id",
    "bert_prob_class_0",
    "bert_prob_class_1",
    "bert_prob_class_2",
    "bert_prob_class_3",
    "bert_prob_class_4",
    "roberta_prob_class_0",
    "roberta_prob_class_1",
    "roberta_prob_class_2",
    "roberta_prob_class_3",
    "roberta_prob_class_4",
]

# These compatibility columns remain in the public schema, but their source
# values are deliberately never redistributed.
REDACTED_EDITORIAL_COLUMNS = ["title", "text", "authors"]

EXCLUDED_NEWSGUARD_COLUMNS = [
    "score",
    "country",
    "language",
    "topics",
    "paywall",
    "opinion_advocacy",
    "label",
]

PREDICTION_COLUMNS = [
    "bert_predicted_label",
    "roberta_predicted_label",
    "llama_predicted_label",
    "mistral_predicted_label",
]

FOLD_COLUMNS = [
    "bert_fold_id",
    "roberta_fold_id",
    "llama_fold_id",
    "mistral_fold_id",
]

PROBABILITY_GROUPS = {
    model: [f"{model}_prob_class_{index}" for index in range(5)]
    for model in ("bert", "roberta")
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Source .csv, .csv.gz, or .zip")
    parser.add_argument("output_dir", type=Path, help="New output directory")
    parser.add_argument(
        "--max-part-mib",
        type=float,
        default=24.0,
        help="Maximum shard size in MiB (default: 24)",
    )
    parser.add_argument(
        "--duplicate-policy",
        choices=("error", "first", "keep"),
        default="error",
        help="How to handle repeated exact URLs (default: error)",
    )
    return parser.parse_args()


@contextmanager
def open_source(path: Path) -> Iterator[TextIO]:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, mode="rt", encoding="utf-8-sig", newline="") as stream:
            yield stream
        return

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(members) != 1:
                raise ValueError(
                    f"ZIP input must contain exactly one CSV; found {len(members)}"
                )
            with archive.open(members[0], mode="r") as raw:
                with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
                    yield stream
        return

    with path.open(mode="r", encoding="utf-8-sig", newline="") as stream:
        yield stream


def normalized_domain(url: str) -> str:
    hostname = urlsplit(url.strip()).hostname
    if not hostname:
        raise ValueError(f"URL has no hostname: {url!r}")
    hostname = hostname.lower()
    return hostname[4:] if hostname.startswith("www.") else hostname


def serialize_csv_row(values: dict[str, object], *, include_header: bool = False) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=PUBLIC_COLUMNS, lineterminator="\n")
    if include_header:
        writer.writeheader()
    else:
        writer.writerow(values)
    return buffer.getvalue().encode("utf-8")


def validate_model_values(row: dict[str, str], row_number: int) -> None:
    for column in PREDICTION_COLUMNS:
        value = int(row[column])
        if value not in range(5):
            raise ValueError(f"row {row_number}: {column} must be between 0 and 4")

    for column in FOLD_COLUMNS:
        value = int(row[column])
        if value not in range(1, 6):
            raise ValueError(f"row {row_number}: {column} must be between 1 and 5")

    for model, columns in PROBABILITY_GROUPS.items():
        probabilities = [float(row[column]) for column in columns]
        if any(value < 0.0 or value > 1.0 for value in probabilities):
            raise ValueError(f"row {row_number}: {model} probability outside [0, 1]")
        if abs(sum(probabilities) - 1.0) > 0.01:
            raise ValueError(f"row {row_number}: {model} probabilities do not sum to 1")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_release(
    input_path: Path,
    output_dir: Path,
    max_part_mib: float,
    duplicate_policy: str = "error",
) -> None:
    if not input_path.is_file():
        raise ValueError(f"input file does not exist: {input_path}")
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    if max_part_mib <= 0:
        raise ValueError("--max-part-mib must be greater than zero")

    max_bytes = int(max_part_mib * 1024 * 1024)
    header_bytes = serialize_csv_row({}, include_header=True)
    if len(header_bytes) >= max_bytes:
        raise ValueError("part size limit is smaller than the CSV header")

    output_parent = output_dir.parent.resolve()
    output_parent.mkdir(parents=True, exist_ok=True)

    source_digest = hashlib.sha256()
    url_counts: Counter[str] = Counter()
    seen_urls: set[str] = set()
    duplicate_urls: set[str] = set()
    part_metadata: list[dict[str, object]] = []
    total_rows = 0
    source_rows = 0
    skipped_duplicate_rows = 0

    with tempfile.TemporaryDirectory(prefix="dataset-release-", dir=output_parent) as temp_name:
        temp_dir = Path(temp_name)
        current_file = None
        current_path: Path | None = None
        current_size = 0
        current_rows = 0

        def close_part() -> None:
            nonlocal current_file, current_path, current_size, current_rows
            if current_file is None or current_path is None:
                return
            current_file.close()
            actual_size = current_path.stat().st_size
            if actual_size != current_size:
                raise RuntimeError(f"size accounting mismatch for {current_path.name}")
            part_metadata.append(
                {
                    "file": current_path.name,
                    "rows": current_rows,
                    "bytes": actual_size,
                    "sha256": sha256_file(current_path),
                }
            )
            current_file = None
            current_path = None
            current_size = 0
            current_rows = 0

        def open_part() -> None:
            nonlocal current_file, current_path, current_size, current_rows
            part_number = len(part_metadata) + 1
            current_path = temp_dir / f"predictions-part-{part_number:04d}.csv"
            current_file = current_path.open("wb")
            current_file.write(header_bytes)
            current_size = len(header_bytes)
            current_rows = 0

        with open_source(input_path) as source:
            reader = csv.DictReader(source)
            if reader.fieldnames is None:
                raise ValueError("source CSV has no header")

            missing = sorted(set(PUBLIC_COLUMNS + EXCLUDED_NEWSGUARD_COLUMNS) - set(reader.fieldnames))
            if missing:
                raise ValueError(f"source CSV is missing required columns: {missing}")

            for source_row_number, row in enumerate(reader, start=2):
                source_rows += 1
                if None in row:
                    raise ValueError(
                        f"row {source_row_number}: unexpected extra fields; source may be malformed"
                    )
                if any(row[column] is None for column in reader.fieldnames):
                    raise ValueError(
                        f"row {source_row_number}: missing fields; source may be truncated"
                    )

                validate_model_values(row, source_row_number)
                url = row["url"].strip()
                if not url:
                    raise ValueError(f"row {source_row_number}: empty URL")

                if url in seen_urls:
                    duplicate_urls.add(url)
                    if duplicate_policy == "error":
                        raise ValueError(
                            f"row {source_row_number}: duplicate URL; select an explicit duplicate policy"
                        )
                    if duplicate_policy == "first":
                        skipped_duplicate_rows += 1
                        continue
                else:
                    seen_urls.add(url)

                public_row: dict[str, object] = {
                    column: row[column] for column in PUBLIC_COLUMNS
                }
                public_row["article_id"] = total_rows
                public_row["url"] = url
                public_row["domain"] = normalized_domain(url)
                for column in REDACTED_EDITORIAL_COLUMNS:
                    public_row[column] = ""

                row_bytes = serialize_csv_row(public_row)
                if len(header_bytes) + len(row_bytes) > max_bytes:
                    raise ValueError(
                        f"row {source_row_number} alone exceeds the configured part limit"
                    )

                if current_file is None:
                    open_part()
                if current_rows > 0 and current_size + len(row_bytes) > max_bytes:
                    close_part()
                    open_part()

                assert current_file is not None
                current_file.write(row_bytes)
                current_size += len(row_bytes)
                current_rows += 1
                total_rows += 1
                url_counts[url] += 1
                source_digest.update(row_bytes)

        close_part()

        if total_rows == 0:
            raise ValueError("source CSV contains no data rows")

        manifest = {
            "schema_version": 1,
            "source_records": source_rows,
            "records": total_rows,
            "unique_urls": len(url_counts),
            "duplicate_url_rows": total_rows - len(url_counts),
            "duplicate_policy": duplicate_policy,
            "duplicate_source_url_groups": len(duplicate_urls),
            "skipped_duplicate_rows": skipped_duplicate_rows,
            "columns": PUBLIC_COLUMNS,
            "redacted_editorial_columns": REDACTED_EDITORIAL_COLUMNS,
            "excluded_newsguard_columns": EXCLUDED_NEWSGUARD_COLUMNS,
            "max_part_bytes": max_bytes,
            "content_digest_sha256": source_digest.hexdigest(),
            "parts": part_metadata,
        }
        manifest_path = temp_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        os.replace(temp_dir, output_dir)


def main() -> int:
    args = parse_args()
    try:
        prepare_release(
            args.input,
            args.output_dir,
            args.max_part_mib,
            args.duplicate_policy,
        )
    except (OSError, ValueError, csv.Error, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Public dataset created at {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
