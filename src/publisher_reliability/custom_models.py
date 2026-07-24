"""Safe import of self-contained custom Hugging Face classifier bundles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .errors import AppError
from .identity import sha256_json
from .storage import Storage, json_field, utc_now


CUSTOM_FAMILY = re.compile(r"custom_[a-z0-9][a-z0-9_-]{1,47}")
DENIED_SUFFIXES = {
    ".bin", ".dll", ".dylib", ".exe", ".pkl", ".pickle", ".pt", ".py",
    ".pyc", ".so",
}
REQUIRED_FILES = {
    "config.json",
    "model.safetensors",
    "prt-model.json",
    "tokenizer_config.json",
}


def _json_file(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AppError("INVALID_INPUT", f"{path.name} is invalid JSON.") from exc
    if not isinstance(value, dict):
        raise AppError("INVALID_INPUT", f"{path.name} must contain one JSON object.")
    return value


def _safe_extract(
    source: Path,
    destination: Path,
    *,
    max_uncompressed_bytes: int,
) -> Path:
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise AppError("INVALID_INPUT", "Custom model upload is not a valid ZIP.") from exc
    with archive:
        files: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        total = 0
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if (
                info.is_dir()
                or not path.parts
            ):
                continue
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in info.filename
                or len(path.parts) > 3
            ):
                raise AppError("INVALID_INPUT", "Custom bundle contains an unsafe path.")
            mode = info.external_attr >> 16
            if info.flag_bits & 0x1:
                raise AppError("INVALID_INPUT", "Encrypted custom bundles are unsupported.")
            file_type = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode) or (file_type and file_type != stat.S_IFREG):
                raise AppError(
                    "INVALID_INPUT",
                    "Custom bundle can contain only regular files.",
                )
            if path.suffix.lower() in DENIED_SUFFIXES:
                raise AppError(
                    "INVALID_INPUT",
                    f"Custom bundle contains forbidden file type {path.suffix}.",
                )
            total += info.file_size
            if len(files) >= 256 or total > max_uncompressed_bytes:
                raise AppError("PAYLOAD_TOO_LARGE", "Custom model bundle exceeds safe limits.")
            files.append((info, path))
        if not files:
            raise AppError("INVALID_INPUT", "Custom model bundle is empty.")

        first_parts = {path.parts[0] for _, path in files}
        strip_root = (
            next(iter(first_parts))
            if len(first_parts) == 1 and all(len(path.parts) > 1 for _, path in files)
            else None
        )
        relative_paths = [
            PurePosixPath(*(path.parts[1:] if strip_root else path.parts))
            for _, path in files
        ]
        if len(relative_paths) != len(set(relative_paths)):
            raise AppError("INVALID_INPUT", "Custom bundle contains duplicate paths.")
        for info, archive_path in files:
            relative_parts = archive_path.parts[1:] if strip_root else archive_path.parts
            relative = Path(*relative_parts)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as input_stream, target.open("xb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
    return destination


def directory_identity(root: Path) -> tuple[str, list[dict[str, object]]]:
    entries = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": digest.hexdigest(),
                "size": path.stat().st_size,
            }
        )
    return sha256_json(entries), entries


def _manifest(root: Path) -> dict[str, object]:
    manifest = _json_file(root / "prt-model.json")
    allowed = {
        "schema_version", "display_name", "family", "fold_id", "class_order",
        "max_tokens", "padding_policy", "base_model", "base_revision",
        "training_data",
    }
    if set(manifest) - allowed:
        raise AppError("INVALID_INPUT", "Custom manifest contains unknown fields.")
    family = manifest.get("family")
    fold_id = manifest.get("fold_id")
    training = manifest.get("training_data")
    base_model = manifest.get("base_model", "")
    base_revision = manifest.get("base_revision", "")
    if (
        type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 1
        or not isinstance(manifest.get("display_name"), str)
        or not 1 <= len(str(manifest["display_name"]).strip()) <= 80
        or not isinstance(family, str)
        or CUSTOM_FAMILY.fullmatch(family) is None
        or type(fold_id) is not int
        or fold_id not in range(1, 6)
        or type(manifest.get("class_order")) is not list
        or any(type(value) is not int for value in manifest["class_order"])
        or manifest["class_order"] != [0, 1, 2, 3, 4]
        or type(manifest.get("max_tokens")) is not int
        or not 8 <= int(manifest["max_tokens"]) <= 4096
        or manifest.get("padding_policy") not in {"fixed_max_length", "dynamic_longest"}
        or not isinstance(base_model, str)
        or len(base_model) > 256
        or not isinstance(base_revision, str)
        or len(base_revision) > 256
        or not isinstance(training, dict)
        or type(training.get("held_out_fold")) is not int
        or training != {"kind": "five_fold", "held_out_fold": fold_id}
    ):
        raise AppError(
            "INVALID_INPUT",
            "Custom manifest does not satisfy the PRT Transformer bundle contract.",
        )
    return manifest


def _validate_transformer(root: Path) -> dict[str, object]:
    missing = sorted(name for name in REQUIRED_FILES if not (root / name).is_file())
    if missing:
        raise AppError(
            "INVALID_INPUT",
            "Custom model bundle is incomplete.",
            {"missing": missing},
        )
    config_json = _json_file(root / "config.json")
    tokenizer_json = _json_file(root / "tokenizer_config.json")
    if "auto_map" in config_json or "auto_map" in tokenizer_json:
        raise AppError("INVALID_INPUT", "Custom code mappings are forbidden.")
    if config_json.get("trust_remote_code"):
        raise AppError("INVALID_INPUT", "trust_remote_code is forbidden.")
    try:
        import torch
        from safetensors import safe_open
        from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise AppError(
            "MODEL_NOT_RUNNABLE",
            "Install the project 'models' extra to validate custom Transformers.",
        ) from exc

    try:
        config = AutoConfig.from_pretrained(
            root,
            local_files_only=True,
            trust_remote_code=False,
        )
        if config.num_labels != 5:
            raise ValueError("configuration must declare exactly five labels")
        AutoTokenizer.from_pretrained(
            root,
            local_files_only=True,
            trust_remote_code=False,
        )
        with torch.device("meta"):
            model = AutoModelForSequenceClassification.from_config(
                config,
                trust_remote_code=False,
            )
        expected = model.state_dict()
        with safe_open(root / "model.safetensors", framework="pt", device="cpu") as weights:
            actual_keys = set(weights.keys())
            expected_keys = set(expected)
            if actual_keys != expected_keys:
                raise ValueError(
                    f"state dictionary keys differ: missing={len(expected_keys - actual_keys)}, "
                    f"unexpected={len(actual_keys - expected_keys)}"
                )
            parameter_count = 0
            for name in sorted(actual_keys):
                tensor = weights.get_tensor(name)
                if tuple(tensor.shape) != tuple(expected[name].shape):
                    raise ValueError(f"tensor shape mismatch for {name}")
                if not bool(torch.isfinite(tensor).all()):
                    raise ValueError(f"non-finite tensor values in {name}")
                parameter_count += tensor.numel()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "INVALID_INPUT",
            f"Custom Transformer validation failed: {exc}",
        ) from exc
    return {
        "architecture": config.architectures[0] if config.architectures else type(model).__name__,
        "model_type": config.model_type,
        "parameter_count": parameter_count,
        "tensor_count": len(expected),
    }


def import_custom_transformer_bundle(
    storage: Storage,
    source: Path,
    *,
    max_uncompressed_bytes: int,
) -> dict[str, object]:
    """Validate, atomically install and register one custom Transformer ZIP."""

    with tempfile.TemporaryDirectory(prefix="custom-model-", dir=storage.data_dir / "staging") as temporary:
        extracted = Path(temporary) / "bundle"
        extracted.mkdir()
        root = _safe_extract(
            source,
            extracted,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        manifest = _manifest(root)
        validation = _validate_transformer(root)
        artifact_digest, entries = directory_identity(root)
        identity = {
            "identity_kind": "custom_transformer_bundle",
            "artifact_sha256": artifact_digest,
            "family": manifest["family"],
            "fold_id": manifest["fold_id"],
            "class_order": manifest["class_order"],
            "max_tokens": manifest["max_tokens"],
            "padding_policy": manifest["padding_policy"],
            "training_data": manifest["training_data"],
            "loader_recipe": "custom_auto_sequence_classification_safetensors",
            "loader_recipe_version": "2",
        }
        identifier = sha256_json(identity)
        destination = storage.data_dir / "managed-models" / identifier
        if destination.exists():
            if (
                not destination.is_dir()
                or destination.is_symlink()
                or directory_identity(destination)[0] != artifact_digest
            ):
                raise AppError(
                    "STORAGE_ERROR",
                    "An existing managed custom model does not match its identity.",
                )
        else:
            os.replace(root, destination)

    now = utc_now()
    existing = next(
        (row for row in storage.rows["models"] if row["model_id"] == identifier),
        None,
    )
    row: dict[str, object] = {
        "model_id": identifier,
        "family": manifest["family"],
        "fold_id": manifest["fold_id"],
        "display_name": str(manifest["display_name"]).strip(),
        "artifact_kind": "custom_transformer_bundle",
        "artifact_locator": f"managed-models/{identifier}",
        "artifact_sha256": artifact_digest,
        "official_manifest_entry_sha256": "",
        "loader_recipe": "custom_auto_sequence_classification_safetensors",
        "loader_recipe_version": "2",
        "base_model": manifest.get("base_model", ""),
        "base_revision": manifest.get("base_revision", ""),
        "tokenizer_source": f"local-sha256:{artifact_digest}",
        "tokenizer_revision": artifact_digest,
        "class_order_json": json_field(manifest["class_order"]),
        "max_tokens": manifest["max_tokens"],
        "padding_policy": manifest["padding_policy"],
        "adapter_config_sha256": "",
        "runtime_scientific_json": json_field(
            {
                **validation,
                "bundle_entries": len(entries),
                "dtype": "from_safetensors",
                "quantization": None,
                "training_data": manifest["training_data"],
            }
        ),
        "status": "compatible",
        "artifact_available": True,
        "runnable": True,
        "status_detail": (
            "Custom Transformer and tokenizer validated without custom code. "
            "Local inference is available."
        ),
        "registered_at": existing["registered_at"] if existing else now,
        "last_validated_at": now,
    }
    storage.upsert("models", "model_id", row)
    return {
        "model_id": identifier,
        "family": manifest["family"],
        "fold_id": manifest["fold_id"],
        "status": row["status"],
        "message": "Custom Transformer bundle validated and imported.",
    }
