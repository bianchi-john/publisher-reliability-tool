"""Safe discovery and structural validation of local core checkpoints."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path

from .custom_models import directory_identity
from .identity import sha256_json
from .storage import Storage, json_field, utc_now


CORE_ARTIFACT = re.compile(r"^(bert|roberta)_fold_([1-5])\.pt$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_checkpoint(path: Path, family: str) -> tuple[int, int]:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is not installed; install the project 'models' extra."
        ) from exc

    state = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    if not isinstance(state, Mapping) or not state:
        raise ValueError("Checkpoint root is not a non-empty state dictionary.")
    if not all(isinstance(key, str) and isinstance(value, torch.Tensor) for key, value in state.items()):
        raise ValueError("Checkpoint contains values other than named tensors.")

    if family == "bert":
        embedding_key = "bert.embeddings.word_embeddings.weight"
        classifier_key = "classifier.weight"
        layer_prefix = "bert.encoder.layer."
        expected_embedding = (30522, 768)
        expected_classifier = (5, 768)
        expected_tensors = 201
        expected_layers = 12
    else:
        embedding_key = "roberta.embeddings.word_embeddings.weight"
        classifier_key = "classifier.out_proj.weight"
        layer_prefix = "roberta.encoder.layer."
        expected_embedding = (50265, 1024)
        expected_classifier = (5, 1024)
        expected_tensors = 393
        expected_layers = 24

    if embedding_key not in state or tuple(state[embedding_key].shape) != expected_embedding:
        raise ValueError(f"Unexpected {family.upper()} embedding shape.")
    if classifier_key not in state or tuple(state[classifier_key].shape) != expected_classifier:
        raise ValueError("The classification head must contain exactly five classes.")
    if len(state) != expected_tensors:
        raise ValueError(
            f"Unexpected tensor count: found {len(state)}, expected {expected_tensors}."
        )

    layers = {
        int(key[len(layer_prefix) :].split(".", 1)[0])
        for key in state
        if key.startswith(layer_prefix)
        and key[len(layer_prefix) :].split(".", 1)[0].isdigit()
    }
    if layers != set(range(expected_layers)):
        raise ValueError(f"Expected encoder layers 0 through {expected_layers - 1}.")
    nonfinite = [name for name, tensor in state.items() if not bool(torch.isfinite(tensor).all())]
    if nonfinite:
        raise ValueError(f"Checkpoint contains non-finite values in {nonfinite[0]}.")
    return len(state), sum(tensor.numel() for tensor in state.values())


def _model_row(
    *,
    identifier: str,
    family: str,
    fold_id: int,
    locator: str,
    digest: str,
    tensor_count: int,
    parameter_count: int,
    timestamp: str,
) -> dict[str, object]:
    base_model = "bert-base-uncased" if family == "bert" else "roberta-large"
    return {
        "model_id": identifier,
        "family": family,
        "fold_id": fold_id,
        "display_name": f"{family.upper()} fold {fold_id} (local checkpoint)",
        "artifact_kind": "pytorch_state_dict",
        "artifact_locator": locator,
        "artifact_sha256": digest,
        "official_manifest_entry_sha256": "",
        "loader_recipe": f"{family}_state_dict",
        "loader_recipe_version": "1",
        "base_model": base_model,
        "base_revision": "",
        "tokenizer_source": base_model,
        "tokenizer_revision": "",
        "class_order_json": json_field([0, 1, 2, 3, 4]),
        "max_tokens": "256",
        "padding_policy": "fixed_max_length",
        "adapter_config_sha256": "",
        "runtime_scientific_json": json_field(
            {
                "dtype": "float32",
                "parameter_count": parameter_count,
                "quantization": None,
                "tensor_count": tensor_count,
            }
        ),
        "status": "validated_not_runnable",
        "artifact_available": True,
        "runnable": False,
        "status_detail": (
            "Checkpoint structure and values are valid. New inference remains disabled "
            "until an immutable tokenizer/base revision and inference pipeline are registered."
        ),
        "registered_at": timestamp,
        "last_validated_at": timestamp,
    }


def scan_model_roots(storage: Storage, roots: tuple[Path, ...]) -> dict[str, object]:
    """Discover recognized files below configured roots and register validated artifacts."""

    timestamp = utc_now()
    discovered: list[dict[str, object]] = []
    rejected: list[dict[str, str]] = []
    seen_digests: set[str] = set()

    for root_index, configured_root in enumerate(roots, start=1):
        root = configured_root.resolve()
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            match = CORE_ARTIFACT.fullmatch(path.name)
            if match is None or not path.is_file() or path.is_symlink():
                continue
            family, fold_value = match.groups()
            locator = f"root-{root_index}/{path.name}"
            try:
                digest = _sha256_file(path)
                tensor_count, parameter_count = _validate_checkpoint(path, family)
            except Exception as exc:
                rejected.append({"locator": locator, "error": str(exc)})
                continue
            seen_digests.add(digest)
            identity = {
                "identity_kind": "local_validated_artifact",
                "artifact_sha256": digest,
                "family": family,
                "fold_id": int(fold_value),
                "loader_recipe": f"{family}_state_dict",
                "loader_recipe_version": "1",
                "class_order": [0, 1, 2, 3, 4],
            }
            discovered.append(
                _model_row(
                    identifier=sha256_json(identity),
                    family=family,
                    fold_id=int(fold_value),
                    locator=locator,
                    digest=digest,
                    tensor_count=tensor_count,
                    parameter_count=parameter_count,
                    timestamp=timestamp,
                )
            )

    historical = [
        row for row in storage.rows["models"] if row["artifact_kind"] == "historical_virtual"
    ]
    previous_local = [
        row for row in storage.rows["models"] if row["artifact_kind"] != "historical_virtual"
    ]
    current_by_id = {str(row["model_id"]): row for row in discovered}
    for row in previous_local:
        if row["artifact_kind"] == "custom_transformer_bundle":
            custom_path = storage.data_dir / row["artifact_locator"]
            current = dict(row)
            if custom_path.is_dir() and not custom_path.is_symlink():
                try:
                    digest = directory_identity(custom_path)[0]
                except OSError:
                    digest = ""
                if digest == row["artifact_sha256"]:
                    current.update(
                        artifact_available=True,
                        last_validated_at=timestamp,
                    )
                else:
                    current.update(
                        status="artifact_invalid",
                        artifact_available=False,
                        runnable=False,
                        status_detail=(
                            "The imported custom Transformer bundle failed its "
                            "integrity check."
                        ),
                        last_validated_at=timestamp,
                    )
            else:
                current.update(
                    status="artifact_missing",
                    artifact_available=False,
                    runnable=False,
                    status_detail="The imported custom Transformer bundle is missing.",
                    last_validated_at=timestamp,
                )
            current_by_id[row["model_id"]] = current
            continue
        if row["model_id"] in current_by_id:
            current_by_id[row["model_id"]]["registered_at"] = row["registered_at"]
        elif row["artifact_sha256"] not in seen_digests:
            missing = dict(row)
            missing.update(
                status="artifact_missing",
                artifact_available=False,
                runnable=False,
                status_detail="The previously registered local checkpoint is no longer present.",
                last_validated_at=timestamp,
            )
            current_by_id[row["model_id"]] = missing
    storage.replace("models", [*historical, *current_by_id.values()])
    return {
        "registered": len(discovered),
        "rejected": rejected,
        "message": (
            f"Validated {len(discovered)} local checkpoint(s)."
            if discovered
            else "No valid supported local checkpoints were found."
        ),
    }
