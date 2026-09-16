"""Stable application errors shared by the CLI and HTTP API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


HTTP_STATUS = {
    "INVALID_INPUT": 422,
    "INVALID_HOST": 421,
    "INVALID_URL": 422,
    "NOT_FOUND": 404,
    "PAYLOAD_TOO_LARGE": 413,
    "NETWORK_REQUIRED": 409,
    "NETWORK_ERROR": 502,
    "EXTRACTION_FAILED": 422,
    "TEXT_TOO_SHORT": 422,
    "NON_ENGLISH": 422,
    "MODEL_NOT_AVAILABLE": 404,
    "MODEL_NOT_RUNNABLE": 409,
    "TRAINING_DATA_LEAKAGE": 409,
    "PROBABILITIES_REQUIRED": 409,
    "INSUFFICIENT_ARTICLES": 422,
    "IMPORT_INVALID": 422,
    "STORAGE_ERROR": 503,
    "PROCESS_INTERRUPTED": 409,
    "FEATURE_UNAVAILABLE": 501,
    "INTERNAL_ERROR": 500,
}

# Large decoder checkpoints are an extension point, not a shipped feature: the
# loaders and identity rules exist, but importing one is refused until the work is
# finished. One message keeps the refusal identical wherever it is raised.
LLM_UNDER_DEVELOPMENT = (
    "Importing large decoder models (Llama, Mistral) is still under development "
    "and is not available yet. This release evaluates BERT and RoBERTa "
    "checkpoints, whose reported accuracy is comparable."
)


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in HTTP_STATUS:
            raise ValueError(f"unknown application error code: {self.code}")
        Exception.__init__(self, self.message)
