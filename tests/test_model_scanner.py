import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publisher_reliability.custom_models import directory_identity
from publisher_reliability.model_scan_cache import CACHE_FILENAME
from publisher_reliability.model_scanner import CHECKPOINT_SHAPES, scan_model_roots
from publisher_reliability.storage import HEADERS, Storage


class ModelScannerTest(unittest.TestCase):
    def test_scan_restores_custom_bundle_availability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with Storage(root / "data") as storage:
                bundle = storage.data_dir / "managed-models" / "custom-model"
                bundle.mkdir()
                (bundle / "config.json").write_text("{}", encoding="utf-8")
                digest = directory_identity(bundle)[0]
                model = {field: "" for field in HEADERS["models"]}
                model.update(
                    model_id="custom-model",
                    family="custom_example",
                    fold_id=1,
                    display_name="Custom example",
                    artifact_kind="custom_transformer_bundle",
                    artifact_locator="managed-models/custom-model",
                    artifact_sha256=digest,
                    loader_recipe="custom_auto_sequence_classification_safetensors",
                    loader_recipe_version=2,
                    class_order_json="[0,1,2,3,4]",
                    max_tokens=256,
                    padding_policy="fixed_max_length",
                    runtime_scientific_json="{}",
                    status="artifact_missing",
                    artifact_available=False,
                    runnable=False,
                    registered_at="2026-07-24T00:00:00Z",
                    last_validated_at="2026-07-24T00:00:00Z",
                )
                storage.upsert("models", "model_id", model)

                scan_model_roots(storage, ())

                restored = storage.rows["models"][0]
                self.assertEqual(restored["status"], "compatible")
                self.assertEqual(restored["artifact_available"], "true")
                self.assertEqual(restored["runnable"], "true")

                (bundle / "unsafe-link").symlink_to(bundle / "config.json")
                scan_model_roots(storage, ())
                invalid = storage.rows["models"][0]
                self.assertEqual(invalid["status"], "invalid")
                self.assertEqual(invalid["artifact_available"], "false")
                self.assertEqual(invalid["runnable"], "false")

    def test_scan_registers_only_recognized_validated_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")
            (models / "renamed.pt").write_bytes(b"ignored")

            with Storage(root / "data") as storage:
                with (
                    patch(
                        "publisher_reliability.model_scanner._sha256_file",
                        return_value="a" * 64,
                    ),
                    patch(
                        "publisher_reliability.model_scanner._validate_checkpoint",
                        return_value=(201, 109_486_085),
                    ),
                ):
                    result = scan_model_roots(storage, (models,))

                self.assertEqual(result["registered"], 1)
                self.assertEqual(result["rejected"], [])
                self.assertEqual(len(storage.rows["models"]), 1)
                model = storage.rows["models"][0]
                self.assertEqual(model["family"], "bert")
                self.assertEqual(model["fold_id"], "1")
                self.assertEqual(model["artifact_locator"], "root-1/bert_fold_1.pt")
                self.assertEqual(model["artifact_available"], "true")
                self.assertEqual(model["status"], "compatible")
                self.assertEqual(model["runnable"], "true")


class ScanCacheTest(unittest.TestCase):
    """The cache must save work without ever weakening what a scan asserts."""

    def setUp(self) -> None:
        self.verifications: list[Path] = []

    def _scan(self, storage: Storage, models: Path, *, digest: str = "a" * 64, **kwargs):
        """Scan with verification stubbed out, recording which files were verified."""

        def verify(path: Path, family: str) -> tuple[int, int]:
            self.verifications.append(path)
            return (201, 109_486_085)

        with (
            patch(
                "publisher_reliability.model_scanner._sha256_file",
                return_value=digest,
            ),
            patch(
                "publisher_reliability.model_scanner._validate_checkpoint",
                side_effect=verify,
            ),
        ):
            return scan_model_roots(storage, (models,), **kwargs)

    def test_unchanged_checkpoint_reuses_the_previous_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models)
                first = dict(storage.rows["models"][0])
                self.assertEqual(len(self.verifications), 1)

                result = self._scan(storage, models)

                # Nothing was read a second time, and the registered identity is the same.
                self.assertEqual(len(self.verifications), 1)
                self.assertEqual(result["reused_from_cache"], 1)
                self.assertEqual(result["registered"], 1)
                self.assertEqual(
                    storage.rows["models"][0]["artifact_sha256"],
                    first["artifact_sha256"],
                )
                self.assertTrue((storage.data_dir / CACHE_FILENAME).exists())

    def test_modified_checkpoint_is_verified_again(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            checkpoint = models / "bert_fold_1.pt"
            checkpoint.write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models)
                checkpoint.write_bytes(b"a different checkpoint entirely")

                result = self._scan(storage, models, digest="b" * 64)

                self.assertEqual(len(self.verifications), 2)
                self.assertEqual(result["reused_from_cache"], 0)
                self.assertEqual(storage.rows["models"][0]["artifact_sha256"], "b" * 64)

    def test_full_scan_ignores_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models)
                result = self._scan(storage, models, full=True)

                self.assertEqual(len(self.verifications), 2)
                self.assertEqual(result["reused_from_cache"], 0)

    def test_stricter_validation_rules_discard_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models)

                # A checkpoint accepted under the old rules must not stay accepted
                # merely because it was cached before the rules were tightened.
                with patch.dict(CHECKPOINT_SHAPES["bert"], {"tensor_count": 202}):
                    result = self._scan(storage, models)

                self.assertEqual(len(self.verifications), 2)
                self.assertEqual(result["reused_from_cache"], 0)

    def test_rejected_checkpoint_is_never_remembered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                with (
                    patch(
                        "publisher_reliability.model_scanner._sha256_file",
                        return_value="a" * 64,
                    ),
                    patch(
                        "publisher_reliability.model_scanner._validate_checkpoint",
                        side_effect=ValueError("Unexpected tensor count."),
                    ) as validate,
                ):
                    first = scan_model_roots(storage, (models,))
                    second = scan_model_roots(storage, (models,))

                self.assertEqual(validate.call_count, 2)
                self.assertEqual(len(first["rejected"]), 1)
                self.assertEqual(len(second["rejected"]), 1)
                self.assertEqual(second["reused_from_cache"], 0)

    def test_corrupt_cache_file_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                (storage.data_dir / CACHE_FILENAME).write_text("{not json", encoding="utf-8")

                result = self._scan(storage, models)

                self.assertEqual(result["registered"], 1)
                self.assertEqual(result["reused_from_cache"], 0)


if __name__ == "__main__":
    unittest.main()
