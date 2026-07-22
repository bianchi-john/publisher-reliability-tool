#!/usr/bin/env python3
"""Small structural checks for the normative Markdown contracts."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def require_unique_contiguous(
    errors: list[str], values: list[str], prefix: str
) -> None:
    counts = Counter(values)
    duplicates = sorted(value for value, count in counts.items() if count > 1)
    if duplicates:
        fail(errors, f"duplicate {prefix} IDs: {', '.join(duplicates)}")
    numbers = sorted(int(value.split("-")[1]) for value in counts)
    expected = list(range(1, max(numbers, default=0) + 1))
    if numbers != expected:
        missing = sorted(set(expected) - set(numbers))
        fail(errors, f"missing {prefix} numbers: {missing}")


def main() -> int:
    errors: list[str] = []
    product = (DOCS / "product-specification.md").read_text(encoding="utf-8")
    acceptance = (DOCS / "acceptance-tests.md").read_text(encoding="utf-8")
    traceability = (DOCS / "traceability.md").read_text(encoding="utf-8")
    api = (DOCS / "api-contract.md").read_text(encoding="utf-8")
    storage = (DOCS / "csv-storage-contract.md").read_text(encoding="utf-8")
    normative = {
        path: path.read_text(encoding="utf-8")
        for path in [ROOT / "README.md", *sorted(DOCS.glob("*.md"))]
    }

    fr_ids = re.findall(r"^\| (FR-\d{3}) \|", product, re.MULTILINE)
    nfr_ids = re.findall(r"^\| (NFR-\d{3}) \|", product, re.MULTILINE)
    at_ids = re.findall(r"^### (AT-\d{3})\b", acceptance, re.MULTILINE)
    require_unique_contiguous(errors, fr_ids, "FR")
    require_unique_contiguous(errors, nfr_ids, "NFR")
    require_unique_contiguous(errors, at_ids, "AT")

    defined_requirements = set(fr_ids + nfr_ids)
    requirement_refs = set(re.findall(r"\b(?:FR|NFR)-\d{3}\b", traceability))
    unknown_requirements = sorted(requirement_refs - defined_requirements)
    if unknown_requirements:
        fail(errors, f"traceability references unknown requirements: {unknown_requirements}")
    missing_requirements = sorted(defined_requirements - requirement_refs)
    if missing_requirements:
        fail(errors, f"requirements absent from traceability: {missing_requirements}")

    defined_tests = set(at_ids)
    traced_tests = set(re.findall(r"\bAT-\d{3}\b", traceability))
    missing_tests = sorted(defined_tests - traced_tests)
    if missing_tests:
        fail(errors, f"acceptance tests absent from traceability: {missing_tests}")
    unknown_tests = sorted(traced_tests - defined_tests)
    if unknown_tests:
        fail(errors, f"traceability references unknown tests: {unknown_tests}")
    all_test_refs = set(
        re.findall(r"\bAT-\d{3}\b", "\n".join(normative.values()))
    )
    dangling_tests = sorted(all_test_refs - defined_tests)
    if dangling_tests:
        fail(errors, f"normative documents reference unknown tests: {dangling_tests}")

    error_rows = re.findall(
        r"^\| `([A-Z][A-Z0-9_]*)` \| (\d{3}) \|", api, re.MULTILINE
    )
    error_codes = [code for code, _ in error_rows]
    duplicate_codes = sorted(
        code for code, count in Counter(error_codes).items() if count > 1
    )
    if duplicate_codes:
        fail(errors, f"duplicate error-code rows: {duplicate_codes}")

    code_like = set(
        re.findall(
            r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b", "\n".join(normative.values())
        )
    )
    non_error_prefixes = ("PRT_", "MISTRAL_")
    non_errors = {"BASE_MODEL", "SEQ_CLS"}
    referenced_errors = {
        code
        for code in code_like
        if not code.startswith(non_error_prefixes) and code not in non_errors
    }
    undocumented_codes = sorted(referenced_errors - set(error_codes))
    if undocumented_codes:
        fail(errors, f"code-like errors absent from API registry: {undocumented_codes}")

    endpoints = re.findall(
        r"^### `((?:GET|POST|PUT|PATCH|DELETE) )([^`]+)`", api, re.MULTILINE
    )
    endpoint_keys = [f"{method.strip()} {path}" for method, path in endpoints]
    duplicate_endpoints = sorted(
        key for key, count in Counter(endpoint_keys).items() if count > 1
    )
    if duplicate_endpoints:
        fail(errors, f"duplicate API endpoint headings: {duplicate_endpoints}")

    ledger_layout = set(re.findall(r"[├└]── ([a-z_]+\.csv)", storage))
    ledger_sections = set(
        re.findall(r"^### 6\.\d+ `([a-z_]+\.csv)`", storage, re.MULTILINE)
    )
    if ledger_layout != ledger_sections:
        fail(
            errors,
            "ledger layout/schema mismatch: "
            f"layout-only={sorted(ledger_layout - ledger_sections)}, "
            f"schema-only={sorted(ledger_sections - ledger_layout)}",
        )

    ledger_headers = re.findall(
        r"^### 6\.\d+ `([a-z_]+\.csv)`\n\n```text\n([^\n]+)\n```",
        storage,
        re.MULTILINE,
    )
    header_names = [name for name, _ in ledger_headers]
    duplicate_headers = sorted(
        name for name, count in Counter(header_names).items() if count > 1
    )
    if duplicate_headers:
        fail(errors, f"duplicate ledger headers: {duplicate_headers}")
    missing_headers = sorted(ledger_sections - set(header_names))
    if missing_headers:
        fail(errors, f"ledger sections without an exact header: {missing_headers}")
    common_suffix = (
        "record_version,record_operation,transaction_id,recorded_at"
    )
    for name, header in ledger_headers:
        fields = header.split(",")
        if any(not field or field.strip() != field for field in fields):
            fail(errors, f"invalid field token in {name} header")
        if name not in {"meta.csv", "transactions.csv"} and not header.endswith(
            common_suffix
        ):
            fail(errors, f"{name} is missing the common version-field suffix")

    def job_types_between(text: str, start: str, end: str) -> set[str]:
        match = re.search(re.escape(start) + r"(.*?)" + re.escape(end), text, re.DOTALL)
        if not match:
            fail(errors, f"cannot locate job-type registry starting {start!r}")
            return set()
        return set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", match.group(1)))

    product_jobs = job_types_between(
        product, "The exhaustive persisted job types are", ". CLI dataset"
    )
    api_jobs = job_types_between(api, "`job_type` is exactly one of", ", matching")
    storage_jobs = job_types_between(storage, "- `job_type`:", ".\n  Offline")
    if not (product_jobs == api_jobs == storage_jobs):
        fail(
            errors,
            "job-type registries differ: "
            f"product={sorted(product_jobs)}, api={sorted(api_jobs)}, "
            f"storage={sorted(storage_jobs)}",
        )

    openapi_path = next(
        (path for path in (ROOT / "openapi.json", DOCS / "openapi.json") if path.exists()),
        None,
    )
    if openapi_path is not None:
        openapi = json.loads(openapi_path.read_text(encoding="utf-8"))
        documented = {
            (path, method.strip().lower())
            for method, path in endpoints
            if path.startswith("/")
        }
        committed = {
            (path, method)
            for path, item in openapi.get("paths", {}).items()
            for method in item
            if method.lower() in {"get", "post", "put", "patch", "delete"}
        }
        missing_openapi = sorted(documented - committed)
        if missing_openapi:
            fail(errors, f"documented endpoints absent from OpenAPI: {missing_openapi}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"spec consistency OK: {len(fr_ids)} FR, {len(nfr_ids)} NFR, "
        f"{len(at_ids)} AT, {len(error_codes)} error codes, "
        f"{len(endpoint_keys)} endpoints"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
