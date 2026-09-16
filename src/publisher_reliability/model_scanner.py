"""Safe discovery and structural validation of local core checkpoints."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from .errors import AppError
from .identity import sha256_json
from .inference import CORE_MODELS
from .model_scan_cache import CACHE_FILENAME, ScanCache
from .official_models import (
    MANAGED_ARTIFACT_KINDS,
    llm_runtime_status,
    verify_managed_model,
)
from .storage import Storage, json_field, utc_now


CORE_ARTIFACT = re.compile(r"^(bert|roberta)_fold_([1-5])\.pt$")

# What a valid checkpoint of each family must contain. Kept as data rather than as
# branches inside the validator so that the scan cache can fingerprint the rules: any
# edit here changes that fingerprint and re-verifies every checkpoint automatically.
CHECKPOINT_SHAPES: dict[str, dict[str, object]] = {
    "bert": {
        "embedding_key": "bert.embeddings.word_embeddings.weight",
        "embedding_shape": (30522, 768),
        "classifier_key": "classifier.weight",
        "classifier_shape": (5, 768),
        "layer_prefix": "bert.encoder.layer.",
        "layer_count": 12,
        "tensor_count": 201,
    },
    "roberta": {
        "embedding_key": "roberta.embeddings.word_embeddings.weight",
        "embedding_shape": (50265, 1024),
        "classifier_key": "classifier.out_proj.weight",
        "classifier_shape": (5, 1024),
        "layer_prefix": "roberta.encoder.layer.",
        "layer_count": 24,
        "tensor_count": 393,
    },
}

# Bump when _validate_checkpoint changes in a way the shape table above does not
# express, so that cached verifications made under the looser code are discarded.
VALIDATION_LOGIC_VERSION = 1


def validation_rules_fingerprint() -> str:
    """Identify the rules a cached verification was produced under."""

    return sha256_json(
        {
            "artifact_pattern": CORE_ARTIFACT.pattern,
            "logic_version": VALIDATION_LOGIC_VERSION,
            "shapes": CHECKPOINT_SHAPES,
        }
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_checkpoint(path: Path, family: str) -> tuple[int, int]:
    """Confirm a .pt file really is the expected classifier before trusting it.

    Weights are read with ``weights_only`` so a checkpoint can never execute code while
    loading. Shapes, tensor and layer counts are then matched against the known BERT
    and RoBERTa architectures and non-finite values rejected: a file that merely
    unpickles cleanly could still be the wrong model or a truncated download.
    """

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

    rules = CHECKPOINT_SHAPES[family]
    embedding_key = rules["embedding_key"]
    classifier_key = rules["classifier_key"]
    layer_prefix = rules["layer_prefix"]
    expected_embedding = rules["embedding_shape"]
    expected_classifier = rules["classifier_shape"]
    expected_tensors = rules["tensor_count"]
    expected_layers = rules["layer_count"]

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
    """Describe one validated local checkpoint as a models ledger row.

    The locator is stored relative to a configured root rather than as an absolute
    path, so the same artifact keeps one identity across machines and container layouts.
    """

    base_model = CORE_MODELS[family]["base_model"]
    base_revision = CORE_MODELS[family]["revision"]
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
        "loader_recipe_version": "2",
        "base_model": base_model,
        "base_revision": base_revision,
        "tokenizer_source": base_model,
        "tokenizer_revision": base_revision,
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
        "status": "compatible",
        "artifact_available": True,
        "runnable": True,
        "status_detail": (
            "Checkpoint is valid and local inference is available. The pinned tokenizer "
            "is cached on first online use."
        ),
        "registered_at": timestamp,
        "last_validated_at": timestamp,
    }


def scan_model_roots(
    storage: Storage,
    roots: tuple[Path, ...],
    *,
    on_progress: Callable[[str], None] | None = None,
    full: bool = False,
) -> dict[str, object]:
    """Discover recognized files below configured roots and register validated artifacts.

    Verifying a checkpoint reads all of it twice, for its SHA-256 and for a
    strict-shape ``torch.load``, which is the slow step when large local checkpoints
    are configured. A checkpoint whose file is unchanged since the previous scan
    therefore reuses that previous result from :mod:`.model_scan_cache`; ``full=True``
    ignores the cache and re-reads every byte.

    ``on_progress`` is an optional callback invoked with a short human-readable
    message before each checkpoint that is actually being verified, so a cached scan
    stays silent. Callers that want terminal feedback during that wait (the CLI,
    ``serve`` at startup) should pass a callback, while callers that already report
    progress through their own channel (the background ``model_validation`` job,
    whose status is polled by the UI) should leave it unset.
    """

    timestamp = utc_now()
    cache = ScanCache(storage.data_dir / CACHE_FILENAME, validation_rules_fingerprint())
    reused = 0
    discovered: list[dict[str, object]] = []
    rejected: list[dict[str, str]] = []
    seen_digests: set[str] = set()
    # Kept at zero: importing the paper's large decoder checkpoints is not a
    # shipped feature yet, so a scan never registers one.
    official_registered = 0

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
            verified = None if full else cache.lookup(path)
            if verified is None:
                if on_progress is not None:
                    size_mb = path.stat().st_size / (1024 * 1024)
                    on_progress(f"Verifying {path.name} ({size_mb:.0f} MB)…")
                try:
                    digest = _sha256_file(path)
                    tensor_count, parameter_count = _validate_checkpoint(path, family)
                except Exception as exc:
                    # Deliberately not remembered: a rejected file is reported again
                    # on every scan until it is fixed or removed.
                    rejected.append({"locator": locator, "error": str(exc)})
                    continue
                cache.remember(
                    path,
                    {
                        "digest": digest,
                        "tensor_count": tensor_count,
                        "parameter_count": parameter_count,
                    },
                )
            else:
                digest = str(verified["digest"])
                tensor_count = int(verified["tensor_count"])
                parameter_count = int(verified["parameter_count"])
                reused += 1
            seen_digests.add(digest)
            identity = {
                "identity_kind": "local_validated_artifact",
                "artifact_sha256": digest,
                "family": family,
                "fold_id": int(fold_value),
                "loader_recipe": f"{family}_state_dict",
                "loader_recipe_version": "2",
                "base_model": CORE_MODELS[family]["base_model"],
                "base_revision": CORE_MODELS[family]["revision"],
                "tokenizer_source": CORE_MODELS[family]["base_model"],
                "tokenizer_revision": CORE_MODELS[family]["revision"],
                "class_order": [0, 1, 2, 3, 4],
                "max_tokens": 256,
                "padding_policy": "fixed_max_length",
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
        if row["artifact_kind"] in MANAGED_ARTIFACT_KINDS:
            current = dict(row)
            valid, problem = verify_managed_model(storage, row)
            if valid:
                if row["artifact_kind"] in {
                    "paper_llama_state_dict_bundle",
                    "paper_mistral_adapter_bundle",
                    "custom_peft_adapter_bundle",
                }:
                    status, runnable, detail = llm_runtime_status()
                else:
                    status, runnable, detail = (
                        "compatible",
                        True,
                        "Custom Transformer bundle integrity is valid. "
                        "Local inference is available.",
                    )
                current.update(
                    status=status,
                    artifact_available=True,
                    runnable=runnable,
                    status_detail=detail,
                    last_validated_at=timestamp,
                )
            else:
                custom_path = storage.data_dir / row["artifact_locator"]
                if custom_path.exists():
                    current.update(
                        status="invalid",
                        artifact_available=False,
                        runnable=False,
                        status_detail=problem,
                        last_validated_at=timestamp,
                    )
                else:
                    current.update(
                        status="artifact_missing",
                        artifact_available=False,
                        runnable=False,
                        status_detail="The imported managed model bundle is missing.",
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
    cache.save()
    registered = len(discovered) + official_registered
    if registered:
        message = f"Validated {registered} local checkpoint(s)."
        if reused:
            message += f" {reused} were unchanged and reused a previous verification."
    else:
        message = "No valid supported local checkpoints were found."
    return {
        "registered": registered,
        "official_registered": official_registered,
        "reused_from_cache": reused,
        "rejected": rejected,
        "message": message,
    }
