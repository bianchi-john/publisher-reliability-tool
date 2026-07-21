#!/usr/bin/env python3
"""Verify public dataset shards, manifest, and optionally their private source."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from itertools import zip_longest
from pathlib import Path

try:
    from .prepare_public_dataset import (
        PUBLIC_COLUMNS,
        REDACTED_EDITORIAL_COLUMNS,
        normalized_domain,
        open_source,
        serialize_csv_row,
        sha256_file,
        validate_model_values,
    )
except ImportError:
    from prepare_public_dataset import (
        PUBLIC_COLUMNS,
        REDACTED_EDITORIAL_COLUMNS,
        normalized_domain,
        open_source,
        serialize_csv_row,
        sha256_file,
        validate_model_values,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path)
    parser.add_argument(
        "--source",
        type=Path,
        help="Optional private .csv, .csv.gz, or .zip for field-by-field comparison",
    )
    return parser.parse_args()


def iter_release_rows(release_dir: Path, part_names: list[str]):
    for part_name in part_names:
        part_path = release_dir / part_name
        with part_path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != PUBLIC_COLUMNS:
                raise ValueError(f"unexpected columns in {part_name}")
            yield from reader


def verify_release(release_dir: Path, source_path: Path | None = None) -> dict[str, int]:
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("columns") != PUBLIC_COLUMNS:
        raise ValueError("manifest columns do not match the public schema")
    if manifest.get("redacted_editorial_columns") != REDACTED_EDITORIAL_COLUMNS:
        raise ValueError("manifest editorial-redaction declaration is invalid")

    max_part_bytes = int(manifest["max_part_bytes"])
    part_names: list[str] = []
    expected_part_rows: list[int] = []
    for part in manifest["parts"]:
        part_name = str(part["file"])
        if Path(part_name).name != part_name:
            raise ValueError(f"unsafe part name: {part_name}")
        part_path = release_dir / part_name
        if not part_path.is_file():
            raise ValueError(f"missing part: {part_name}")
        if part_path.stat().st_size != int(part["bytes"]):
            raise ValueError(f"size mismatch: {part_name}")
        if part_path.stat().st_size > max_part_bytes:
            raise ValueError(f"part exceeds configured limit: {part_name}")
        if sha256_file(part_path) != part["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {part_name}")
        part_names.append(part_name)
        expected_part_rows.append(int(part["rows"]))

    unexpected_csv = sorted(
        path.name for path in release_dir.glob("*.csv") if path.name not in part_names
    )
    if unexpected_csv:
        raise ValueError(f"CSV files absent from manifest: {unexpected_csv}")

    digest = hashlib.sha256()
    url_counts: Counter[str] = Counter()
    total_rows = 0
    actual_part_rows: list[int] = []

    for part_name in part_names:
        count = 0
        for row in iter_release_rows(release_dir, [part_name]):
            row_number = total_rows + 2
            if row["article_id"] != str(total_rows):
                raise ValueError(f"non-contiguous article_id at release row {row_number}")
            if row["domain"] != normalized_domain(row["url"]):
                raise ValueError(f"domain mismatch at release row {row_number}")
            for column in REDACTED_EDITORIAL_COLUMNS:
                if row[column] != "":
                    raise ValueError(
                        f"editorial field {column} is not empty at release row {row_number}"
                    )
            validate_model_values(row, row_number)
            digest.update(serialize_csv_row(row))
            url_counts[row["url"]] += 1
            total_rows += 1
            count += 1
        actual_part_rows.append(count)

    if actual_part_rows != expected_part_rows:
        raise ValueError("per-part row counts do not match manifest")
    if total_rows != int(manifest["records"]):
        raise ValueError("total row count does not match manifest")
    if len(url_counts) != int(manifest["unique_urls"]):
        raise ValueError("unique URL count does not match manifest")
    if total_rows - len(url_counts) != int(manifest["duplicate_url_rows"]):
        raise ValueError("duplicate URL count does not match manifest")
    if digest.hexdigest() != manifest["content_digest_sha256"]:
        raise ValueError("content digest does not match manifest")

    if source_path is not None:
        release_rows = iter_release_rows(release_dir, part_names)
        duplicate_policy = manifest.get("duplicate_policy", "keep")
        source_record_count = 0
        skipped_duplicate_count = 0
        seen_source_urls: set[str] = set()

        def selected_source_rows(source_reader):
            nonlocal source_record_count, skipped_duplicate_count
            for source_row in source_reader:
                source_record_count += 1
                url = source_row["url"].strip()
                if duplicate_policy == "first" and url in seen_source_urls:
                    skipped_duplicate_count += 1
                    continue
                seen_source_urls.add(url)
                yield source_row

        with open_source(source_path) as source:
            source_rows = csv.DictReader(source)
            for index, pair in enumerate(
                zip_longest(selected_source_rows(source_rows), release_rows), start=0
            ):
                source_row, release_row = pair
                if source_row is None or release_row is None:
                    raise ValueError("source and release contain different row counts")
                for column in PUBLIC_COLUMNS:
                    if column == "article_id":
                        expected = str(index)
                    elif column == "domain":
                        expected = normalized_domain(source_row["url"])
                    elif column == "url":
                        expected = source_row[column].strip()
                    elif column in REDACTED_EDITORIAL_COLUMNS:
                        expected = ""
                    else:
                        expected = source_row[column]
                    if release_row[column] != expected:
                        raise ValueError(
                            f"source mismatch at row {index + 2}, column {column}"
                        )
        if source_record_count != int(manifest.get("source_records", total_rows)):
            raise ValueError("source row count does not match manifest")
        if skipped_duplicate_count != int(manifest.get("skipped_duplicate_rows", 0)):
            raise ValueError("skipped duplicate count does not match manifest")

    return {
        "records": total_rows,
        "parts": len(part_names),
        "unique_urls": len(url_counts),
        "duplicate_url_rows": total_rows - len(url_counts),
        "skipped_duplicate_rows": int(manifest.get("skipped_duplicate_rows", 0)),
    }


def main() -> int:
    args = parse_args()
    try:
        result = verify_release(args.release_dir, args.source)
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
