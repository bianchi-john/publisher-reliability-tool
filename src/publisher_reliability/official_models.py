"""Verified import of the Llama and Mistral checkpoints published with the paper."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable

from .custom_models import directory_identity
from .errors import AppError
from .identity import sha256_json
from .storage import Storage, json_field, utc_now


MANIFEST_PATH = Path(__file__).with_name("official-model-manifest-v1.json")
MANAGED_ARTIFACT_KINDS = {
    "paper_llama_state_dict_bundle",
    "paper_mistral_adapter_bundle",
    "custom_transformer_bundle",
    "custom_peft_adapter_bundle",
}


def official_manifest() -> dict[str, object]:
    try:
        value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("The packaged official-model manifest is invalid.") from exc
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or not isinstance(value.get("models"), list)
    ):
        raise RuntimeError("The packaged official-model manifest has an unknown schema.")
    return value


def official_catalog() -> list[dict[str, object]]:
    """Return the public, immutable import catalog used by the Models page."""

    manifest = official_manifest()
    return [
        {
            "family": entry["family"],
            "fold_id": entry["fold_id"],
            "display_name": entry["display_name"],
            "files": [
                {
                    "name": file["name"],
                    "size": file["size"],
                    "download_url": file["download_url"],
                }
                for file in entry["files"]
            ],
            "base_model": entry["base_model"],
            "base_revision": entry["base_revision"],
        }
        for entry in manifest["models"]
    ]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_entry_digest(entry: dict[str, object]) -> str:
    return sha256_json(entry)


def _identify_entry(
    sources: Iterable[Path],
    source_names: Iterable[str] | None = None,
) -> dict[str, object]:
    paths = list(sources)
    if not paths:
        raise AppError("INVALID_INPUT", "Select at least one official model file.")
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise AppError("INVALID_INPUT", "An official model upload is missing or unsafe.")
    names = list(source_names) if source_names is not None else [path.name for path in paths]
    if len(names) != len(paths) or any(Path(name).name != name for name in names):
        raise AppError("INVALID_INPUT", "Official model filenames are invalid.")
    if len(names) != len(set(names)):
        raise AppError("INVALID_INPUT", "Official model files must have distinct names.")

    candidates = [
        entry
        for entry in official_manifest()["models"]
        if {file["name"] for file in entry["files"]} == set(names)
    ]
    if not candidates:
        recognized = {
            file["name"]
            for entry in official_manifest()["models"]
            for file in entry["files"]
        }
        partial = sorted(set(names) & recognized)
        raise AppError(
            "INVALID_INPUT",
            (
                "The selected files do not form one complete official OSF checkpoint. "
                "Llama requires both .z01 and .z02 files from the same fold."
            ),
            {"recognized_files": partial, "selected_files": sorted(names)},
        )
    entry = candidates[0]
    expected = {file["name"]: file for file in entry["files"]}
    for path, name in zip(paths, names, strict=True):
        metadata = expected[name]
        actual_size = path.stat().st_size
        if actual_size != metadata["size"]:
            raise AppError(
                "INVALID_INPUT",
                f"{name} does not have the size published in the OSF manifest.",
            )
        if _sha256_file(path) != metadata["sha256"]:
            raise AppError(
                "INVALID_INPUT",
                f"{name} failed the official OSF SHA-256 check.",
            )
    return entry


def _zip_regular_files(source: Path) -> tuple[zipfile.ZipFile, list[zipfile.ZipInfo]]:
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise AppError("INVALID_INPUT", f"{source.name} is not a valid ZIP archive.") from exc
    files = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = PurePosixPath(info.filename)
        mode = info.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if (
            not path.parts
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in info.filename
            or info.flag_bits & 0x1
            or stat.S_ISLNK(mode)
            or (file_type and file_type != stat.S_IFREG)
        ):
            archive.close()
            raise AppError("INVALID_INPUT", "Official archive contains an unsafe entry.")
        files.append(info)
    return archive, files


def _install_llama(entry: dict[str, object], sources: dict[str, Path], root: Path) -> str:
    output_path = root / "model.pt"
    output_digest = hashlib.sha256()
    expected_member = f"llama_fold_{entry['fold_id']}.pt"
    with output_path.open("xb") as output:
        for metadata in entry["files"]:
            source = sources[metadata["name"]]
            archive, members = _zip_regular_files(source)
            with archive:
                if len(members) != 1 or PurePosixPath(members[0].filename).name != expected_member:
                    raise AppError(
                        "INVALID_INPUT",
                        f"{source.name} does not contain the expected checkpoint segment.",
                    )
                with archive.open(members[0]) as stream:
                    while block := stream.read(1024 * 1024):
                        output.write(block)
                        output_digest.update(block)
    if output_path.stat().st_size < 5_000_000_000:
        raise AppError("INVALID_INPUT", "The reconstructed Llama checkpoint is incomplete.")
    return output_digest.hexdigest()


def _install_mistral(
    entry: dict[str, object],
    source: Path,
    root: Path,
    *,
    max_uncompressed_bytes: int,
) -> str:
    archive, members = _zip_regular_files(source)
    with archive:
        total = sum(info.file_size for info in members)
        if len(members) > 64 or total > max_uncompressed_bytes:
            raise AppError("PAYLOAD_TOO_LARGE", "Official Mistral archive exceeds safe limits.")
        first_parts = {PurePosixPath(info.filename).parts[0] for info in members}
        strip_root = (
            next(iter(first_parts))
            if len(first_parts) == 1
            and all(len(PurePosixPath(info.filename).parts) > 1 for info in members)
            else None
        )
        relative_paths: set[PurePosixPath] = set()
        for info in members:
            path = PurePosixPath(info.filename)
            relative = PurePosixPath(*(path.parts[1:] if strip_root else path.parts))
            if relative in relative_paths or len(relative.parts) > 2:
                raise AppError("INVALID_INPUT", "Official Mistral archive has invalid paths.")
            relative_paths.add(relative)
            target = root / Path(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as input_stream, target.open("xb") as output:
                shutil.copyfileobj(input_stream, output, length=1024 * 1024)

    required = {
        "adapter_config.json",
        "adapter_model.safetensors",
        "tokenizer_config.json",
        "tokenizer.json",
    }
    missing = sorted(name for name in required if not (root / name).is_file())
    if missing:
        raise AppError(
            "INVALID_INPUT",
            "Official Mistral adapter is incomplete.",
            {"missing": missing},
        )
    try:
        adapter = json.loads((root / "adapter_config.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AppError("INVALID_INPUT", "Official adapter_config.json is invalid.") from exc
    recipe = entry["recipe"]
    if (
        adapter.get("base_model_name_or_path") != entry["base_model"]
        or adapter.get("peft_type") != "LORA"
        or adapter.get("task_type") != "SEQ_CLS"
        or adapter.get("r") != recipe["lora_r"]
        or adapter.get("lora_alpha") != recipe["lora_alpha"]
        or sorted(adapter.get("target_modules", [])) != sorted(recipe["target_modules"])
    ):
        raise AppError(
            "INVALID_INPUT",
            "Official Mistral adapter metadata differs from the paper recipe.",
        )
    return directory_identity(root)[0]


def llm_runtime_status() -> tuple[str, bool, str]:
    missing = [
        package
        for package in ("accelerate", "bitsandbytes", "peft", "torch", "transformers")
        if importlib.util.find_spec(package) is None
    ]
    if missing:
        return (
            "dependency_missing",
            False,
            "Validated artifact; install the 'llm-models' extra for inference "
            f"(missing: {', '.join(missing)}).",
        )
    try:
        import torch
    except ImportError:  # pragma: no cover - guarded above
        return "dependency_missing", False, "PyTorch is unavailable."
    if not torch.cuda.is_available():
        return (
            "resource_unavailable",
            False,
            "Validated artifact; Llama/Mistral QLoRA inference requires a CUDA GPU.",
        )
    return (
        "compatible",
        True,
        "Official checkpoint and runtime dependencies are available for local inference.",
    )


def _metadata_file(root: Path, entry: dict[str, object]) -> None:
    value = {
        "schema_version": 1,
        "provenance": "paper_official",
        "official_manifest_entry_sha256": _manifest_entry_digest(entry),
        "family": entry["family"],
        "fold_id": entry["fold_id"],
    }
    (root / "paper-model.json").write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def import_official_model(
    storage: Storage,
    sources: Iterable[Path],
    *,
    source_names: Iterable[str] | None = None,
    max_uncompressed_bytes: int,
) -> dict[str, object]:
    """Authenticate, install and register one exact paper checkpoint."""

    source_paths = list(sources)
    names = list(source_names) if source_names is not None else [path.name for path in source_paths]
    entry = _identify_entry(source_paths, names)
    manifest_digest = _manifest_entry_digest(entry)
    identifier = sha256_json(
        {
            "identity_kind": "paper_official",
            "official_manifest_entry_sha256": manifest_digest,
        }
    )
    destination = storage.data_dir / "managed-models" / identifier
    if not destination.exists():
        with tempfile.TemporaryDirectory(
            prefix="official-model-",
            dir=storage.data_dir / "staging",
        ) as temporary:
            root = Path(temporary) / "bundle"
            root.mkdir()
            by_name = dict(zip(names, source_paths, strict=True))
            if entry["family"] == "llama":
                artifact_digest = _install_llama(entry, by_name, root)
            else:
                artifact_digest = _install_mistral(
                    entry,
                    source_paths[0],
                    root,
                    max_uncompressed_bytes=max_uncompressed_bytes,
                )
            _metadata_file(root, entry)
            if entry["family"] == "mistral":
                artifact_digest = directory_identity(root)[0]
            os.replace(root, destination)
    else:
        if not destination.is_dir() or destination.is_symlink():
            raise AppError("STORAGE_ERROR", "Managed official model path is unsafe.")
        if entry["family"] == "llama":
            checkpoint = destination / "model.pt"
            if not checkpoint.is_file():
                raise AppError("STORAGE_ERROR", "Managed Llama checkpoint is incomplete.")
            artifact_digest = _sha256_file(checkpoint)
        else:
            artifact_digest = directory_identity(destination)[0]

    status, runnable, detail = llm_runtime_status()
    now = utc_now()
    existing = next(
        (row for row in storage.rows["models"] if row["model_id"] == identifier),
        None,
    )
    artifact_kind = (
        "paper_llama_state_dict_bundle"
        if entry["family"] == "llama"
        else "paper_mistral_adapter_bundle"
    )
    row: dict[str, object] = {
        "model_id": identifier,
        "family": entry["family"],
        "fold_id": entry["fold_id"],
        "display_name": entry["display_name"],
        "artifact_kind": artifact_kind,
        "artifact_locator": f"managed-models/{identifier}",
        "artifact_sha256": artifact_digest,
        "official_manifest_entry_sha256": manifest_digest,
        "loader_recipe": entry["loader_recipe"],
        "loader_recipe_version": entry["loader_recipe_version"],
        "base_model": entry["base_model"],
        "base_revision": entry["base_revision"],
        "tokenizer_source": entry["tokenizer_source"],
        "tokenizer_revision": entry["tokenizer_revision"],
        "class_order_json": json_field([0, 1, 2, 3, 4]),
        "max_tokens": entry["max_tokens"],
        "padding_policy": entry["padding_policy"],
        "adapter_config_sha256": (
            _sha256_file(destination / "adapter_config.json")
            if entry["family"] == "mistral"
            else ""
        ),
        "runtime_scientific_json": json_field(
            {
                "classification": "single_label_multiclass",
                "class_count": 5,
                "provenance": "paper_official",
                "recipe": entry["recipe"],
                "source_files": [
                    {
                        "name": file["name"],
                        "sha256": file["sha256"],
                        "size": file["size"],
                    }
                    for file in entry["files"]
                ],
            }
        ),
        "status": status,
        "artifact_available": True,
        "runnable": runnable,
        "status_detail": detail,
        "registered_at": existing["registered_at"] if existing else now,
        "last_validated_at": now,
    }
    storage.upsert("models", "model_id", row)
    return {
        "model_id": identifier,
        "family": entry["family"],
        "fold_id": entry["fold_id"],
        "provenance": "paper_official",
        "status": status,
        "runnable": runnable,
        "message": f"{entry['display_name']} authenticated against OSF and imported.",
    }


def verify_managed_model(storage: Storage, row: dict[str, str]) -> tuple[bool, str]:
    """Recheck a managed model without executing checkpoint code."""

    candidate = storage.data_dir / row["artifact_locator"]
    if candidate.is_symlink():
        return False, "Managed model path is a symbolic link."
    path = candidate.resolve()
    managed = (storage.data_dir / "managed-models").resolve()
    if path.parent != managed or not path.is_dir():
        return False, "Managed model bundle is missing."
    if row.get("official_manifest_entry_sha256"):
        try:
            metadata = json.loads(
                (path / "paper-model.json").read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False, "Official model provenance metadata is missing or invalid."
        if (
            metadata.get("provenance") != "paper_official"
            or metadata.get("official_manifest_entry_sha256")
            != row["official_manifest_entry_sha256"]
        ):
            return False, "Official model provenance metadata has changed."
    try:
        if row["artifact_kind"] == "paper_llama_state_dict_bundle":
            actual = _sha256_file(path / "model.pt")
        else:
            actual = directory_identity(path)[0]
    except OSError:
        return False, "Managed model bundle could not be read."
    if actual != row["artifact_sha256"]:
        return False, "Managed model bundle failed its integrity check."
    return True, ""
