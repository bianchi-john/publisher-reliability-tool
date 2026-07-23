"""Environment and CLI configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import AppError


def _boolean(value: str) -> bool:
    if value not in {"true", "false"}:
        raise AppError("INVALID_INPUT", "Boolean configuration must be true or false.")
    return value == "true"


@dataclass(slots=True)
class Config:
    port: int = 8000
    data_dir: Path = Path("./data")
    models_dirs: tuple[Path, ...] = (Path("./models"),)
    seed_dataset: Path = Path("./dataset/predictions")
    offline: bool = False
    device: str = "auto"
    log_level: str = "info"
    dataset_upload_max_bytes: int = 536_870_912
    model_upload_max_bytes: int = 4_294_967_296
    container_internal: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        model_roots = os.environ.get("PRT_MODELS_DIR", "./models").split(os.pathsep)
        config = cls(
            port=int(os.environ.get("PRT_PORT", "8000")),
            data_dir=Path(os.environ.get("PRT_DATA_DIR", "./data")),
            models_dirs=tuple(Path(value) for value in model_roots if value),
            seed_dataset=Path(
                os.environ.get("PRT_SEED_DATASET", "./dataset/predictions")
            ),
            offline=_boolean(os.environ.get("PRT_OFFLINE", "false")),
            device=os.environ.get("PRT_DEVICE", "auto"),
            log_level=os.environ.get("PRT_LOG_LEVEL", "info"),
            dataset_upload_max_bytes=int(
                os.environ.get("PRT_DATASET_UPLOAD_MAX_BYTES", "536870912")
            ),
            model_upload_max_bytes=int(
                os.environ.get("PRT_MODEL_UPLOAD_MAX_BYTES", "4294967296")
            ),
            container_internal=_boolean(
                os.environ.get("PRT_CONTAINER_INTERNAL", "false")
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise AppError("INVALID_INPUT", "Port must be between 1 and 65535.")
        if self.device not in {"auto", "cpu", "cuda"}:
            raise AppError("INVALID_INPUT", "Device must be auto, cpu, or cuda.")
        if self.log_level not in {"debug", "info", "warning", "error"}:
            raise AppError("INVALID_INPUT", "Invalid log level.")
        if not 0 < self.dataset_upload_max_bytes <= 536_870_912:
            raise AppError("INVALID_INPUT", "Invalid dataset upload byte limit.")
        if not 0 < self.model_upload_max_bytes <= 4_294_967_296:
            raise AppError("INVALID_INPUT", "Invalid model upload byte limit.")
