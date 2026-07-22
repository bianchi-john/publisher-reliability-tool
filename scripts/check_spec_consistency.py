#!/usr/bin/env python3
"""Small structural checks for the normative research-demo contracts."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def unique_contiguous(errors: list[str], values: list[str], prefix: str) -> None:
    counts = Counter(values)
    duplicate = sorted(value for value, count in counts.items() if count > 1)
    if duplicate:
        errors.append(f"duplicate {prefix} IDs: {duplicate}")
    numbers = sorted(int(value.split("-")[1]) for value in counts)
    expected = list(range(1, max(numbers, default=0) + 1))
    if numbers != expected:
        errors.append(f"missing {prefix} numbers: {sorted(set(expected) - set(numbers))}")


def main() -> int:
    errors: list[str] = []
    product = (DOCS / "product-specification.md").read_text(encoding="utf-8")
    acceptance = (DOCS / "acceptance-tests.md").read_text(encoding="utf-8")
    traceability = (DOCS / "traceability.md").read_text(encoding="utf-8")
    api = (DOCS / "api-contract.md").read_text(encoding="utf-8")
    storage = (DOCS / "csv-storage-contract.md").read_text(encoding="utf-8")
    deployment = (DOCS / "deployment.md").read_text(encoding="utf-8")
    normative = {
        path: path.read_text(encoding="utf-8")
        for path in [ROOT / "README.md", *sorted(DOCS.glob("*.md"))]
    }

    fr_ids = re.findall(r"^\| (FR-\d{3}) \|", product, re.MULTILINE)
    nfr_ids = re.findall(r"^\| (NFR-\d{3}) \|", product, re.MULTILINE)
    at_ids = re.findall(r"^### (AT-\d{3})\b", acceptance, re.MULTILINE)
    unique_contiguous(errors, fr_ids, "FR")
    unique_contiguous(errors, nfr_ids, "NFR")
    unique_contiguous(errors, at_ids, "AT")

    requirements = set(fr_ids + nfr_ids)
    traced_requirements = set(re.findall(r"\b(?:FR|NFR)-\d{3}\b", traceability))
    if requirements != traced_requirements:
        errors.append(
            "requirement/traceability mismatch: "
            f"untraced={sorted(requirements - traced_requirements)}, "
            f"unknown={sorted(traced_requirements - requirements)}"
        )

    expected_owners = {
        "scientific-contract.md",
        "csv-storage-contract.md",
        "api-contract.md",
        "deployment.md",
        "product-specification.md",
        "architecture.md",
    }
    ownership_block = re.search(
        r"## Contract ownership and precedence\n\n(.*?)(?:\n\nFor an owner-specific)",
        traceability,
        re.DOTALL,
    )
    owners = (
        set(re.findall(r"`([^`]+\.md)`", ownership_block.group(1)))
        if ownership_block
        else set()
    )
    if owners != expected_owners:
        errors.append(
            "normative owner mismatch: "
            f"missing={sorted(expected_owners - owners)}, "
            f"unknown={sorted(owners - expected_owners)}"
        )

    tests = set(at_ids)
    traced_tests = set(re.findall(r"\bAT-\d{3}\b", traceability))
    if tests != traced_tests:
        errors.append(
            "acceptance/traceability mismatch: "
            f"untraced={sorted(tests - traced_tests)}, "
            f"unknown={sorted(traced_tests - tests)}"
        )
    all_test_refs = set(re.findall(r"\bAT-\d{3}\b", "\n".join(normative.values())))
    dangling = sorted(all_test_refs - tests)
    if dangling:
        errors.append(f"normative documents reference unknown tests: {dangling}")

    error_rows = re.findall(
        r"^\| `([A-Z][A-Z0-9_]*)` \| (\d{3}) \|", api, re.MULTILINE
    )
    error_codes = [code for code, _ in error_rows]
    duplicate_errors = sorted(
        code for code, count in Counter(error_codes).items() if count > 1
    )
    if duplicate_errors:
        errors.append(f"duplicate error-code rows: {duplicate_errors}")
    code_like = set(
        re.findall(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b", "\n".join(normative.values()))
    )
    referenced_errors = {
        code
        for code in code_like
        if not code.startswith("PRT_") and code not in {"SEQ_CLS"}
    }
    undocumented = sorted(referenced_errors - set(error_codes))
    if undocumented:
        errors.append(f"code-like errors absent from API registry: {undocumented}")

    endpoints = re.findall(
        r"^### `((?:GET|POST|PUT|PATCH|DELETE) )([^`]+)`", api, re.MULTILINE
    )
    endpoint_keys = [f"{method.strip()} {path}" for method, path in endpoints]
    duplicate_endpoints = sorted(
        key for key, count in Counter(endpoint_keys).items() if count > 1
    )
    if duplicate_endpoints:
        errors.append(f"duplicate endpoint headings: {duplicate_endpoints}")

    ledger_layout = set(re.findall(r"[├└]── ([a-z_]+\.csv)", storage))
    ledger_headers = re.findall(
        r"^### 5\.\d+ `([a-z_]+\.csv)`\n\n```text\n([^\n]+)\n```",
        storage,
        re.MULTILINE,
    )
    header_names = [name for name, _ in ledger_headers]
    if ledger_layout != set(header_names):
        errors.append(
            "ledger layout/header mismatch: "
            f"layout-only={sorted(ledger_layout - set(header_names))}, "
            f"header-only={sorted(set(header_names) - ledger_layout)}"
        )
    for name, header in ledger_headers:
        fields = header.split(",")
        if len(fields) != len(set(fields)) or any(
            not field or field.strip() != field for field in fields
        ):
            errors.append(f"invalid or duplicate field in {name} header")

    expected_jobs = {"evaluation", "dataset_import", "model_validation"}
    for label, text in {"product": product, "api": api, "storage": storage}.items():
        section = re.search(
            r"The persisted job-type registry is: ([^\n]+(?:\n`[^\n]+)?)\.",
            text,
        )
        jobs = set(re.findall(r"`([a-z]+(?:_[a-z]+)*)`", section.group(1))) if section else set()
        if jobs != expected_jobs:
            errors.append(f"{label} job registry differs: {sorted(jobs)}")

    expected_config = {
        "PRT_PORT",
        "PRT_DATA_DIR",
        "PRT_MODELS_DIR",
        "PRT_SEED_DATASET",
        "PRT_OFFLINE",
        "PRT_DEVICE",
        "PRT_LOG_LEVEL",
        "PRT_DATASET_UPLOAD_MAX_BYTES",
        "PRT_MODEL_UPLOAD_MAX_BYTES",
    }
    config_rows = set(
        re.findall(r"^\| `(PRT_[A-Z0-9_]+)` \|", deployment, re.MULTILINE)
    )
    if config_rows != expected_config:
        errors.append(
            "deployment configuration registry mismatch: "
            f"missing={sorted(expected_config - config_rows)}, "
            f"unknown={sorted(config_rows - expected_config)}"
        )
    referenced_config = set(
        re.findall(r"\bPRT_[A-Z0-9_]+\b", "\n".join(normative.values()))
    ) - {"PRT_VERSION"}
    if referenced_config != config_rows:
        errors.append(
            "configuration reference mismatch: "
            f"undocumented={sorted(referenced_config - config_rows)}, "
            f"unreferenced={sorted(config_rows - referenced_config)}"
        )

    removed_routes = ("/events", "/retry", "/cancel")
    for route in removed_routes:
        if any(route in key for key in endpoint_keys):
            errors.append(f"removed route still documented: {route}")
    removed_ledgers = {"idempotency_keys.csv", "transactions.csv", "purges.csv"}
    unexpected_ledgers = sorted(ledger_layout & removed_ledgers)
    if unexpected_ledgers:
        errors.append(f"removed ledgers still in layout: {unexpected_ledgers}")

    openapi_path = next(
        (path for path in (ROOT / "openapi.json", DOCS / "openapi.json") if path.exists()),
        None,
    )
    if openapi_path:
        openapi = json.loads(openapi_path.read_text(encoding="utf-8"))
        documented = {
            (path, method.strip().lower())
            for method, path in endpoints
            if path.startswith("/")
        }
        committed = {
            (path, method.lower())
            for path, item in openapi.get("paths", {}).items()
            for method in item
            if method.lower() in {"get", "post", "put", "patch", "delete"}
        }
        if documented != committed:
            errors.append(
                "OpenAPI endpoint mismatch: "
                f"missing={sorted(documented - committed)}, "
                f"extra={sorted(committed - documented)}"
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"spec consistency OK: {len(fr_ids)} FR, {len(nfr_ids)} NFR, "
        f"{len(at_ids)} AT, {len(error_codes)} error codes, "
        f"{len(endpoint_keys)} endpoints, {len(ledger_headers)} ledgers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
