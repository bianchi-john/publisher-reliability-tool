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
REQUIRED_ADAPTER_FILES = {
    "adapter_config.json",
    "adapter_model.safetensors",
    "prt-model.json",
    "tokenizer_config.json",
    "tokenizer.json",
}
CUSTOM_LLM_BASES = {
    "llama": "meta-llama/Meta-Llama-3-8B",
    "mistral": "mistralai/Mistral-Small-24B-Base-2501",
}
SUPPORTED_CUSTOM_MODEL_TYPES = {
    "albert",
    "bert",
    "camembert",
    "deberta",
    "deberta-v2",
    "distilbert",
    "electra",
    "modernbert",
    "mpnet",
    "rembert",
    "roberta",
    "xlm-roberta",
}


def _require_supported_model_type(model_type: object) -> str:
    value = str(model_type)
    if value not in SUPPORTED_CUSTOM_MODEL_TYPES:
        raise AppError(
            "INVALID_INPUT",
            "Custom models must use a supported encoder-only classifier architecture.",
            {"supported_model_types": sorted(SUPPORTED_CUSTOM_MODEL_TYPES)},
        )
    return value


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
        if path.is_symlink():
            raise OSError("Managed model bundles cannot contain symbolic links.")
        if not path.is_file():
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
        "training_data", "model_kind", "architecture",
    }
    if set(manifest) - allowed:
        raise AppError("INVALID_INPUT", "Custom manifest contains unknown fields.")
    family = manifest.get("family")
    fold_id = manifest.get("fold_id")
    training = manifest.get("training_data")
    base_model = manifest.get("base_model", "")
    base_revision = manifest.get("base_revision", "")
    common_invalid = (
        type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") not in {1, 2}
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
    )
    if common_invalid:
        raise AppError(
            "INVALID_INPUT",
            "Custom manifest does not satisfy the PRT Transformer bundle contract.",
        )
    schema_version = manifest["schema_version"]
    if schema_version == 1:
        contract_invalid = bool(
            manifest.get("model_kind")
            or manifest.get("architecture")
        )
    else:
        architecture = manifest.get("architecture")
        adapter_max_tokens = manifest.get("max_tokens")
        contract_invalid = (
            manifest.get("model_kind") != "peft_sequence_classifier"
            or architecture not in CUSTOM_LLM_BASES
            or base_model != CUSTOM_LLM_BASES.get(str(architecture), "")
            or re.fullmatch(r"[0-9a-f]{40}", base_revision) is None
            or manifest.get("padding_policy") != "dynamic_longest"
            or (
                architecture == "llama"
                and (
                    type(adapter_max_tokens) is not int
                    or adapter_max_tokens > 256
                )
            )
            or (
                architecture == "mistral"
                and (
                    type(adapter_max_tokens) is not int
                    or adapter_max_tokens > 1024
                )
            )
        )
    if contract_invalid:
        raise AppError(
            "INVALID_INPUT",
            "Custom manifest does not satisfy the PRT Transformer bundle contract.",
        )
    return manifest


def _validate_peft_adapter(
    root: Path,
    *,
    manifest: dict[str, object],
) -> dict[str, object]:
    missing = sorted(name for name in REQUIRED_ADAPTER_FILES if not (root / name).is_file())
    if missing:
        raise AppError(
            "INVALID_INPUT",
            "Custom PEFT classifier bundle is incomplete.",
            {"missing": missing},
        )
    adapter = _json_file(root / "adapter_config.json")
    tokenizer_json = _json_file(root / "tokenizer_config.json")
    if "auto_map" in tokenizer_json or tokenizer_json.get("trust_remote_code"):
        raise AppError("INVALID_INPUT", "Custom tokenizer code mappings are forbidden.")
    architecture = str(manifest["architecture"])
    expected_targets = (
        {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "down_proj", "up_proj"}
        if architecture == "llama"
        else {"q_proj", "k_proj", "v_proj", "o_proj"}
    )
    targets = set(adapter.get("target_modules", []))
    if (
        adapter.get("base_model_name_or_path") != manifest["base_model"]
        or adapter.get("peft_type") != "LORA"
        or adapter.get("task_type") != "SEQ_CLS"
        or not targets
        or not targets.issubset(expected_targets)
        or type(adapter.get("r")) is not int
        or not 1 <= int(adapter["r"]) <= 256
        or not isinstance(adapter.get("lora_alpha"), (int, float))
        or not set(adapter.get("modules_to_save") or []) & {"classifier", "score"}
    ):
        raise AppError(
            "INVALID_INPUT",
            "Custom PEFT adapter is not a compatible five-class sequence classifier.",
        )
    try:
        import torch
        from safetensors import safe_open
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise AppError(
            "MODEL_NOT_RUNNABLE",
            "Install the project 'models' extra to validate custom adapters.",
        ) from exc
    try:
        AutoTokenizer.from_pretrained(
            root,
            local_files_only=True,
            trust_remote_code=False,
        )
        with safe_open(
            root / "adapter_model.safetensors",
            framework="pt",
            device="cpu",
        ) as weights:
            keys = set(weights.keys())
            heads = [
                key
                for key in keys
                if key.endswith(("score.weight", "classifier.weight"))
                or ".modules_to_save." in key
                and key.endswith(".weight")
                and ("score" in key or "classifier" in key)
            ]
            if not heads or not any(weights.get_tensor(key).shape[0] == 5 for key in heads):
                raise ValueError("classification head does not contain exactly five rows")
            lora_a = {key.replace("lora_A", "lora_B") for key in keys if "lora_A" in key}
            if not lora_a or not lora_a.issubset(keys):
                raise ValueError("LoRA A/B tensor pairs are incomplete")
            parameter_count = 0
            for key in sorted(keys):
                tensor = weights.get_tensor(key)
                if not bool(torch.isfinite(tensor).all()):
                    raise ValueError(f"non-finite tensor values in {key}")
                parameter_count += tensor.numel()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "INVALID_INPUT",
            f"Custom PEFT adapter validation failed: {exc}",
        ) from exc
    return {
        "architecture": architecture,
        "model_type": architecture,
        "parameter_count": parameter_count,
        "tensor_count": len(keys),
        "adapter_r": adapter["r"],
        "adapter_alpha": adapter["lora_alpha"],
        "target_modules": sorted(targets),
    }


def _validate_transformer(root: Path, *, max_tokens: int) -> dict[str, object]:
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
        _require_supported_model_type(config.model_type)
        if config.num_labels != 5:
            raise ValueError("configuration must declare exactly five labels")
        maximum_positions = getattr(config, "max_position_embeddings", None)
        if (
            isinstance(maximum_positions, int)
            and maximum_positions > 0
            and max_tokens > maximum_positions
        ):
            raise ValueError(
                f"max_tokens exceeds the architecture limit ({maximum_positions})"
            )
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
        is_adapter = manifest["schema_version"] == 2
        validation = (
            _validate_peft_adapter(root, manifest=manifest)
            if is_adapter
            else _validate_transformer(
                root,
                max_tokens=int(manifest["max_tokens"]),
            )
        )
        artifact_digest, entries = directory_identity(root)
        artifact_kind = (
            "custom_peft_adapter_bundle"
            if is_adapter
            else "custom_transformer_bundle"
        )
        loader_recipe = (
            "custom_peft_sequence_classification"
            if is_adapter
            else "custom_auto_sequence_classification_safetensors"
        )
        identity = {
            "identity_kind": artifact_kind,
            "artifact_sha256": artifact_digest,
            "family": manifest["family"],
            "fold_id": manifest["fold_id"],
            "class_order": manifest["class_order"],
            "max_tokens": manifest["max_tokens"],
            "padding_policy": manifest["padding_policy"],
            "training_data": manifest["training_data"],
            "base_model": manifest.get("base_model", ""),
            "base_revision": manifest.get("base_revision", ""),
            "loader_recipe": loader_recipe,
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
    if is_adapter:
        from .official_models import llm_runtime_status

        status, runnable, status_detail = llm_runtime_status()
    else:
        status, runnable, status_detail = (
            "compatible",
            True,
            "Custom Transformer and tokenizer validated without custom code. "
            "Local inference is available.",
        )
    row: dict[str, object] = {
        "model_id": identifier,
        "family": manifest["family"],
        "fold_id": manifest["fold_id"],
        "display_name": str(manifest["display_name"]).strip(),
        "artifact_kind": artifact_kind,
        "artifact_locator": f"managed-models/{identifier}",
        "artifact_sha256": artifact_digest,
        "official_manifest_entry_sha256": "",
        "loader_recipe": loader_recipe,
        "loader_recipe_version": "2",
        "base_model": manifest.get("base_model", ""),
        "base_revision": manifest.get("base_revision", ""),
        "tokenizer_source": f"local-sha256:{artifact_digest}",
        "tokenizer_revision": artifact_digest,
        "class_order_json": json_field(manifest["class_order"]),
        "max_tokens": manifest["max_tokens"],
        "padding_policy": manifest["padding_policy"],
        "adapter_config_sha256": (
            hashlib.sha256((destination / "adapter_config.json").read_bytes()).hexdigest()
            if is_adapter
            else ""
        ),
        "runtime_scientific_json": json_field(
            {
                **validation,
                "bundle_entries": len(entries),
                "dtype": "from_safetensors",
                "quantization": (
                    "bitsandbytes-nf4-double-quant-bfloat16" if is_adapter else None
                ),
                "provenance": "user_custom",
                "training_data": manifest["training_data"],
            }
        ),
        "status": status,
        "artifact_available": True,
        "runnable": runnable,
        "status_detail": status_detail,
        "registered_at": existing["registered_at"] if existing else now,
        "last_validated_at": now,
    }
    storage.upsert("models", "model_id", row)
    return {
        "model_id": identifier,
        "family": manifest["family"],
        "fold_id": manifest["fold_id"],
        "status": row["status"],
        "provenance": "user_custom",
        "message": (
            "Custom PEFT sequence classifier validated and imported."
            if is_adapter
            else "Custom Transformer bundle validated and imported."
        ),
    }
